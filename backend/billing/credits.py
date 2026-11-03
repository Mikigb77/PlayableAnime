"""Credit accounts and the append-only ledger (K1, K2, K7).

Every balance change locks the account row, applies the change and appends its ledger entry in
one transaction, so balances can't race and always equal the sum of their entries. The model-call
flow (hold, charge, release) is in `billing.meter`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from billing.config import StarterPolicy, get_config
from billing.models import CreditAccount, CreditHold, EntryKind, LedgerEntry
from lucid import logs

logger = logging.getLogger("billing")


def is_unlimited(user) -> bool:
    """The owner plays free (K7). The role is stored on the user, never decided here."""
    return bool(getattr(user, "is_owner", False))


def qualifies_for_starter(user) -> bool:
    """Whether the account gets K1's starter credit now.

    With the default "verified" policy only a verified account does, so throwaway emails can't
    farm it: a Google account at once, and an email account once WS6's `email_verified` is set.
    """
    if get_config().starter_policy == StarterPolicy.ALL:
        return True
    # Google verified the email of any account that signed in with it.
    return bool(getattr(user, "email_verified", False)) or bool(user.google_sub)


def locked_account(user_id, *, user=None, now: datetime | None = None) -> CreditAccount:
    """The user's account, row-locked until the caller's transaction ends.

    Opens the account on first use. Given the `user` itself, it also grants the starter credit
    when it is due, so a user created before billing existed, or whose account failed to open,
    is never left without one. Call it inside `transaction.atomic()`.
    """
    account = CreditAccount.objects.select_for_update().filter(user_id=user_id).first()
    if account is None:
        # Two first uses at once: one creates the row, the other waits for it and reads it.
        CreditAccount.objects.get_or_create(user_id=user_id)
        account = CreditAccount.objects.select_for_update().get(user_id=user_id)
    if user is not None and not account.starter_granted and qualifies_for_starter(user):
        account.starter_granted = True
        append(account, EntryKind.STARTER, get_config().starter_cents, now=now)
    return account


def open_account(user) -> CreditAccount:
    """Opens the user's account and grants the starter credit if it is due. Safe to repeat."""
    with transaction.atomic():
        return locked_account(user.pk, user=user)


def append(
    account: CreditAccount,
    kind: EntryKind,
    amount_cents: Decimal,
    *,
    now: datetime | None = None,
    **fields: Any,
) -> LedgerEntry:
    """Applies `amount_cents` to a locked account and records it, in the caller's transaction.

    The balance can't go below zero: callers clamp a charge first, and the database refuses a
    negative balance whatever happens.
    """
    amount = Decimal(amount_cents) or Decimal(0)  # no "-0" in the ledger or the logs
    if account.balance_cents + amount < 0:
        raise ValueError("A ledger entry can't take a balance below zero.")
    account.balance_cents += amount
    account.save(update_fields=["balance_cents", "starter_granted", "updated_at"])
    entry = LedgerEntry.objects.create(
        user_id=account.user_id,
        kind=kind,
        amount_cents=amount,
        balance_after_cents=account.balance_cents,
        request_id=logs.current_context().get("request_id") or "",
        created_at=now or timezone.now(),
        **fields,
    )
    logger.info(
        "Credits %s",
        "added" if amount > 0 else "spent" if amount < 0 else "recorded",
        extra={
            "billing": {
                "kind": str(kind),
                "amount_cents": float(amount),
                "balance_after_cents": float(account.balance_cents),
                "cost_usd": float(entry.cost_usd),
                "unlimited": entry.unlimited,
                "turn": entry.turn,
            }
        },
    )
    return entry


def credit(
    user, amount_cents: Decimal, kind: EntryKind = EntryKind.ADJUSTMENT, **fields: Any
) -> LedgerEntry:
    """Adds credits, or takes them away with a negative amount (an adjustment by staff)."""
    with transaction.atomic():
        return append(locked_account(user.pk, user=user), kind, Decimal(amount_cents), **fields)


def held_cents(user_id, now: datetime) -> Decimal:
    """Credits set aside by holds that haven't expired."""
    total = CreditHold.objects.filter(user_id=user_id, expires_at__gt=now).aggregate(
        total=Sum("amount_cents")
    )["total"]
    return total or Decimal(0)


def summary(user) -> dict[str, Any]:
    """The `credits` part of the User in API.md: `{balance_cents, unlimited}`."""
    account = CreditAccount.objects.filter(user_id=user.pk).first()
    if account is None or (not account.starter_granted and qualifies_for_starter(user)):
        account = open_account(user)
    return {"balance_cents": float(account.balance_cents), "unlimited": is_unlimited(user)}


asummary = sync_to_async(summary)


def reconcile(user_id) -> tuple[Decimal, Decimal]:
    """The account's balance and the sum of its ledger entries, which must be equal."""
    balance = (
        CreditAccount.objects.filter(user_id=user_id)
        .values_list("balance_cents", flat=True)
        .first()
    )
    total = LedgerEntry.objects.filter(user_id=user_id).aggregate(total=Sum("amount_cents"))[
        "total"
    ]
    return balance or Decimal(0), total or Decimal(0)
