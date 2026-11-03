"""Checks that every balance equals the sum of its ledger entries (K2). Exits 1 if any doesn't."""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from billing.models import CreditAccount, LedgerEntry


class Command(BaseCommand):
    help = "Checks that every credit balance equals the sum of its ledger entries."

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
        checked = 0
        wrong = []
        for account in accounts.iterator():
            checked += 1
            if account.ledger != account.balance_cents:
                wrong.append(account)
                self.stderr.write(
                    f"{account.user_id}: balance {account.balance_cents}, ledger {account.ledger}"
                )
        if wrong:
            raise CommandError(f"{len(wrong)} of {checked} balances don't match their ledger.")
        self.stdout.write(f"All {checked} balances match their ledger.")
