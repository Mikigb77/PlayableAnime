"""Credits (K1, K2, K7, M7) and per-user usage counters (T9).

The ledger is append-only: every change to a balance is a new `LedgerEntry`, written in the same
transaction that updates `CreditAccount.balance_cents` under a row lock, so the balance always
equals the sum of the account's entries. The database refuses a negative balance and any update
of a ledger row.

Everything here belongs to one user and is deleted with the account (T12). There's no real money
in the first version; when top-ups arrive (K4, K5), payment records will need keeping for
accounting, and that's the time to revisit.
"""

import uuid

from django.conf import settings as django_settings
from django.db import models
from django.utils import timezone

from billing.config import Use

# Cents, to a hundredth of a thousandth of a dollar: a turn costs about 2 cents (API.md).
_CENTS = {"max_digits": 14, "decimal_places": 4}


class CreditAccount(models.Model):
    """One per user. The row is locked for every balance change, so balances can't race."""

    user = models.OneToOneField(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="credit_account",
    )
    balance_cents = models.DecimalField(default=0, **_CENTS)
    # K1's starter credit is granted once, when the account first qualifies.
    starter_granted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # A balance can never be overdrawn (K2, M7), whatever the code above does.
            models.CheckConstraint(
                condition=models.Q(balance_cents__gte=0), name="credit_balance_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.balance_cents}¢"


class EntryKind(models.TextChoices):
    STARTER = "starter", "Starter credit"
    TURN = "turn", "Turn"
    DRAFT = "draft", "Draft"
    IMAGE = "image", "Picture"
    TOPUP = "topup", "Top-up"
    ADJUSTMENT = "adjustment", "Adjustment"


class LedgerEntry(models.Model):
    """One change to a balance, never edited or removed (K2).

    `amount_cents` is positive when credits are added and negative when they are spent. An owner's
    entry (K7) spends nothing but still records our model cost, so T5's numbers stay honest. A
    call on the player's own key costs us nothing and writes no entry (K6).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    kind = models.CharField(max_length=16, choices=EntryKind.choices)
    amount_cents = models.DecimalField(**_CENTS)
    balance_after_cents = models.DecimalField(**_CENTS)
    # Our raw model cost in dollars, before the margin. Zero for credits added.
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    # The owner's unlimited credits paid for this (K7): nothing was taken from the balance.
    unlimited = models.BooleanField(default=False)
    # Not foreign keys: an entry outlives the story or picture it paid for.
    story_id = models.UUIDField(null=True, blank=True)
    turn = models.PositiveIntegerField(null=True, blank=True)
    image_id = models.CharField(max_length=64, blank=True)
    # The ticket that paid for this, so a repeated charge never bills twice.
    ticket_id = models.UUIDField(null=True, blank=True, unique=True)
    request_id = models.CharField(max_length=64, blank=True)
    # Numbers only, never prompt or story text (T6): tokens, calls, models, any shortfall.
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "ledger entries"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="ledger_user_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance_after_cents__gte=0), name="ledger_balance_not_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount_cents}¢ → {self.balance_after_cents}¢"

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValueError("Ledger entries are append-only. Add an adjustment instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Ledger entries are append-only. Add an adjustment instead.")


class CreditHold(models.Model):
    """Credits set aside while a model call runs (K2, M7).

    A request holds its estimated cost before it starts, so two requests can't both spend the
    same credits, and gives the hold back when it is charged or fails. A request that died leaves
    its hold behind, and the hold stops counting once it expires.
    """

    # The ticket's id.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credit_holds"
    )
    use = models.CharField(max_length=16, choices=[(u.value, u.name.title()) for u in Use])
    amount_cents = models.DecimalField(**_CENTS)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["user", "expires_at"], name="credit_hold_user_exp_idx")]

    def __str__(self) -> str:
        return f"{self.use} hold of {self.amount_cents}¢"


class UsageCounter(models.Model):
    """A fixed-window counter per user and bucket, such as `turn:minute` or `turn:day` (T9).

    One row per user and bucket that rolls over in place, so the table stays small. It lives in
    Postgres, so a limit holds across every Cloud Run instance.
    """

    user = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="usage_counters"
    )
    bucket = models.CharField(max_length=32)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "bucket"], name="usage_counter_user_bucket"),
        ]

    def __str__(self) -> str:
        return f"{self.bucket}: {self.count} since {self.window_start:%Y-%m-%d %H:%M}"
