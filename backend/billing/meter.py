"""Guards and billing around every model call: rate limits, quotas and credits (K2, K6, K7, M7, T9).

The turn endpoint, drafting, pictures and dictation all follow the same three steps:

    from billing import meter

    # 1. Before the stream starts. Raises ApiError rate_limited, quota_exceeded or out_of_credits.
    ticket = await meter.astart(user, meter.TURN, byok=byok_key is not None)
    try:
        ...  # run the model calls, collecting their telemetry records
        with transaction.atomic():  # the transaction that saves the turn
            ...  # save the scene, the state and the version bump
            meter.charge(ticket, telemetry.calls, story_id=story.id, turn=turn)
    finally:
        await meter.arelease(ticket)  # gives back the hold; does nothing after a charge

`start` counts the request against the per-minute rate limit (always, BYOK and the owner
included, K6, K7) and, on our key, the daily quota (not the owner's, K7), then holds an estimated
cost so concurrent requests can't spend the same credits. `charge` turns the hold into a ledger
entry at the real cost plus the margin, in the caller's transaction, so a turn and its charge are
saved together or not at all. A charge never takes a balance below zero: if the real cost is more
than the balance, the balance goes to zero and the shortfall is recorded. The owner (K7) passes
every credit check and gets an entry at zero charge; the player's own key (K6) is never charged.

A new player's first pictures can be on the house (K1, M7): a picture started with `house=True`
is held against the account's house allowance instead of its balance while the allowance has
room, and charged at zero, with what it would have cost kept on the entry and added to the
allowance used. Otherwise it is held and charged like any picture.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from billing import credits, limits
from billing.config import Use, get_config
from billing.models import CreditHold, EntryKind, LedgerEntry
from billing.pricing import BillableCall, bill, house_has_room
from lucid.errors import ApiError, ErrorCode

logger = logging.getLogger("billing")

TURN = Use.TURN
DRAFT = Use.DRAFT
IMAGE = Use.IMAGE
SPEECH = Use.SPEECH
VOICE = Use.VOICE

_ENTRY_KIND = {
    Use.TURN: EntryKind.TURN,
    Use.DRAFT: EntryKind.DRAFT,
    Use.IMAGE: EntryKind.IMAGE,
    Use.SPEECH: EntryKind.SPEECH,
    Use.VOICE: EntryKind.VOICE,
}

_QUOTA_MESSAGES = {
    Use.TURN: "Today's turns are used up.",
    Use.DRAFT: "Today's drafts are used up.",
    Use.IMAGE: "Today's pictures are used up.",
    Use.SPEECH: "Today's dictation is used up. Typing always works.",
    Use.VOICE: "Today's reading aloud is used up. The phone's own voice still works.",
}


@dataclass(frozen=True)
class Ticket:
    """Permission for one request's model calls, from `start` to `charge` or `release`."""

    id: uuid.UUID
    user_id: uuid.UUID
    use: Use
    byok: bool
    unlimited: bool
    # Credits held for this request; zero when nothing is (the owner, or the player's own key).
    held_cents: Decimal
    # The house pays for this picture, a new player's first (K1, M7): its hold is against the
    # house's allowance, and its charge takes nothing from the balance.
    house: bool = False


def start(
    user, use: Use, *, byok: bool = False, house: bool = False, now: datetime | None = None
) -> Ticket:
    """Checks the rate limit, the daily quota and the credits, and holds the estimated cost.

    Raises `ApiError` with `rate_limited` (details `retry_after_s`), `quota_exceeded` (details
    `resets_at`) or `out_of_credits` (details `balance_cents`), before anything is streamed.
    Nothing is counted or held when it raises.

    `house`: the request is one of a new player's first pictures, which the house pays for when
    the account qualifies for the starter credit and the house allowance has room (K1, M7). The
    ticket says whether it does; when it doesn't, the picture needs credits like any other.
    """
    use = Use(use)
    if house and use != Use.IMAGE:
        raise ValueError("Only a picture can be on the house.")
    now = now or timezone.now()
    config = get_config()
    unlimited = credits.is_unlimited(user)
    on_our_key = not byok
    with transaction.atomic():
        rate = limits.hit(
            user.pk,
            f"{use}:minute",
            limit=config.per_minute[use],
            window_s=limits.MINUTE,
            now=now,
        )
        if not rate.allowed:
            raise ApiError(
                ErrorCode.RATE_LIMITED,
                "Slow down a little, then try again.",
                {"retry_after_s": rate.retry_after_s(now)},
            )
        if on_our_key and not unlimited:
            # The owner plays without daily caps (K7, Miki 2026-11-04); the per-minute limit
            # above still guards a runaway client or a leaked token.
            quota = limits.hit(
                user.pk, f"{use}:day", limit=config.per_day[use], window_s=limits.DAY, now=now
            )
            if not quota.allowed:
                raise ApiError(
                    ErrorCode.QUOTA_EXCEEDED,
                    _QUOTA_MESSAGES[use],
                    {"resets_at": quota.window_end.isoformat()},
                )
        held = Decimal(0)
        on_the_house = False
        ticket_id = uuid.uuid4()
        if on_our_key and not unlimited:
            held = config.reserve_cents[use]
            account = credits.locked_account(user.pk, user=user, now=now)
            # Holds left by requests that died no longer count.
            CreditHold.objects.filter(user_id=user.pk, expires_at__lte=now).delete()
            on_the_house = house and _house_pays(account, user, config, now)
            if not on_the_house:
                available = account.balance_cents - credits.held_cents(user.pk, now)
                if available < held:
                    raise ApiError(
                        ErrorCode.OUT_OF_CREDITS,
                        "You're out of credits.",
                        {
                            "balance_cents": float(account.balance_cents),
                            # Less than the balance while another request holds part of it.
                            "available_cents": float(max(available, Decimal(0))),
                        },
                    )
            CreditHold.objects.create(
                id=ticket_id,
                user_id=user.pk,
                use=use,
                amount_cents=held,
                house=on_the_house,
                created_at=now,
                expires_at=now + timedelta(seconds=config.hold_ttl_s),
            )
    return Ticket(
        id=ticket_id,
        user_id=user.pk,
        use=use,
        byok=byok,
        unlimited=unlimited,
        held_cents=held,
        house=on_the_house,
    )


def _house_pays(account, user, config, now: datetime) -> bool:
    """Whether the house pays for one more of this account's first pictures (K1, M7): the same
    accounts as the starter credit, while the allowance has room. Call it under the account's
    row lock, so two pictures started at once can't both take the last of the allowance."""
    if not credits.qualifies_for_starter(user):
        return False
    held = credits.held_cents(user.pk, now, house=True)
    return house_has_room(account.house_pictures_cents, held, config.house_pictures_cents)


def charge(
    ticket: Ticket,
    calls: Iterable[BillableCall],
    *,
    story_id: uuid.UUID | str | None = None,
    turn: int | None = None,
    image_id: str = "",
    now: datetime | None = None,
) -> LedgerEntry | None:
    """Charges what the request's model calls cost on our key, plus the margin (K2, M7).

    Call it inside the transaction that saves what the calls produced, so the charge and the
    result are saved together or not at all. Releases the ticket's hold. Charging a ticket twice
    returns the first entry and bills nothing more. Returns None when nothing ran on our key
    (the player's own key, K6), which writes no entry. The owner's ticket (K7) and a house
    ticket (K1, M7) write an entry at zero charge that keeps what it would have cost.
    """
    now = now or timezone.now()
    config = get_config()
    billed = bill(calls, config.margin)
    with transaction.atomic():
        # Lock first, so a repeated charge waits for the first one and then finds its entry.
        account = credits.locked_account(ticket.user_id, now=now)
        existing = LedgerEntry.objects.filter(ticket_id=ticket.id).first()
        if existing is not None:
            return existing
        CreditHold.objects.filter(pk=ticket.id).delete()
        if not billed.used_our_key:
            return None
        detail = billed.detail()
        if ticket.byok:
            # A request started on the player's own key skipped the daily quota and the hold,
            # yet some calls ran on ours. They cost us, so they are charged, but the caller
            # should have started a ticket on our key for them (M7's fallback does).
            logger.warning(
                "A request started on the player's own key made calls on ours",
                extra={"billing": {"use": str(ticket.use), "models": list(billed.models)}},
            )
        if not billed.price_known:
            logger.warning(
                "A model call had no price in the table, so it was charged at the fallback",
                extra={"billing": {"use": str(ticket.use), "models": list(billed.models)}},
            )
        if ticket.unlimited:
            # The owner plays free, and the entry keeps what it would have cost (K7).
            amount = Decimal(0)
            detail["list_cents"] = str(billed.charge_cents)
        elif ticket.house:
            # A new player's first picture (K1, M7): the house pays, the entry keeps what it
            # would have cost, and that counts against the house allowance.
            amount = Decimal(0)
            detail["list_cents"] = str(billed.charge_cents)
            account.house_pictures_cents += billed.charge_cents
        else:
            # Never below zero (M7). The rest is ours to absorb, and recorded so T5 stays honest.
            # Every hold on this account is the same player's, so a charge may use the whole
            # balance: that leaves the least uncovered.
            amount = min(billed.charge_cents, account.balance_cents)
            if amount < billed.charge_cents:
                detail["uncovered_cents"] = str(billed.charge_cents - amount)
                logger.warning(
                    "A charge was more than the balance",
                    extra={
                        "billing": {
                            "use": str(ticket.use),
                            "charge_cents": float(billed.charge_cents),
                            "balance_cents": float(account.balance_cents),
                        }
                    },
                )
        return credits.append(
            account,
            _ENTRY_KIND[ticket.use],
            -amount,
            now=now,
            cost_usd=billed.cost_usd,
            unlimited=ticket.unlimited,
            house=ticket.house,
            story_id=story_id,
            turn=turn,
            image_id=str(image_id or ""),
            ticket_id=ticket.id,
            detail=detail,
        )


def charge_image(
    ticket: Ticket,
    calls: Iterable[BillableCall],
    *,
    story_id: uuid.UUID | str | None = None,
    turn: int | None = None,
    image_id: str = "",
    now: datetime | None = None,
) -> LedgerEntry | None:
    """`charge` for a picture (M7): the real cost plus the margin, never below zero."""
    if ticket.use != Use.IMAGE:
        raise ValueError("charge_image takes a ticket started for a picture.")
    return charge(ticket, calls, story_id=story_id, turn=turn, image_id=image_id, now=now)


def release(ticket: Ticket) -> None:
    """Gives back the ticket's hold when its request fails. Safe to repeat, and does nothing
    once the ticket is charged. Nothing is refunded to the rate limit or the quota: the model
    may have run, and it cost us either way."""
    if ticket.held_cents:
        CreditHold.objects.filter(pk=ticket.id).delete()


astart = sync_to_async(start)
acharge = sync_to_async(charge)
acharge_image = sync_to_async(charge_image)
arelease = sync_to_async(release)
