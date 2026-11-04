"""Checks that every balance equals the sum of its ledger entries (K2), and that what the house
has paid for each account's first pictures equals its house entries (K1, M7). Exits 1 if any
doesn't."""

from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from billing.models import CreditAccount, LedgerEntry


class Command(BaseCommand):
    help = (
        "Checks that every credit balance equals the sum of its ledger entries, and what the "
        "house paid for each account's first pictures its house entries."
    )

    def handle(self, *args, **options) -> None:
        totals = (
            LedgerEntry.objects.filter(user_id=OuterRef("user_id"))
            .order_by()
            .values("user_id")
            .annotate(total=Sum("amount_cents"))
            .values("total")
        )
        zero = Value(0, output_field=DecimalField(max_digits=14, decimal_places=4))
        accounts = CreditAccount.objects.annotate(ledger=Coalesce(Subquery(totals), zero))
        house = self._house_paid()
        checked = 0
        wrong = []
        for account in accounts.iterator():
            checked += 1
            paid = house.get(account.user_id, Decimal(0))
            if account.ledger != account.balance_cents:
                wrong.append(account)
                self.stderr.write(
                    f"{account.user_id}: balance {account.balance_cents}, ledger {account.ledger}"
                )
            elif paid != account.house_pictures_cents:
                wrong.append(account)
                self.stderr.write(
                    f"{account.user_id}: house pictures {account.house_pictures_cents}, "
                    f"ledger {paid}"
                )
        if wrong:
            raise CommandError(f"{len(wrong)} of {checked} accounts don't match their ledger.")
        self.stdout.write(
            f"All {checked} balances match their ledger, and so does what the house paid."
        )

    @staticmethod
    def _house_paid() -> dict:
        """What the house paid per account: the list price its house entries kept (K1, M7)."""
        paid: dict = defaultdict(Decimal)
        entries = LedgerEntry.objects.filter(house=True).values_list("user_id", "detail")
        for user_id, detail in entries.iterator():
            paid[user_id] += Decimal(str((detail or {}).get("list_cents", 0)))
        return paid
