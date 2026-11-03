"""Read-only views of balances and the ledger for staff (B1). The ledger is append-only (K2):
corrections are new adjustment entries, made with `billing.credits.credit`."""

from django.contrib import admin

from billing.models import CreditAccount, LedgerEntry


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CreditAccount)
class CreditAccountAdmin(_ReadOnly):
    list_display = ("user", "balance_cents", "starter_granted", "updated_at")
    search_fields = ("user__email",)
    list_select_related = ("user",)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(_ReadOnly):
    list_display = (
        "created_at",
        "user",
        "kind",
        "amount_cents",
        "balance_after_cents",
        "cost_usd",
        "unlimited",
        "story_id",
        "turn",
    )
    list_filter = ("kind", "unlimited")
    search_fields = ("user__email", "story_id", "request_id")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
