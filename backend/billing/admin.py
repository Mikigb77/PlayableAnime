"""Read-only views of balances and the ledger for staff (B1). The ledger is append-only (K2):
corrections are new adjustment entries, made with `billing.credits.credit`."""

from django.contrib import admin
from django.core.exceptions import PermissionDenied

from billing.models import CreditAccount, LedgerEntry


class _ReadOnly(admin.ModelAdmin):
    """Nothing is added, changed or deleted here. Delete permission itself stays as Django
    decides, because deleting a user in the admin checks it for every row that goes with the
    user (T12); deleting these rows on their own is refused below."""

    actions = None  # no "delete selected"

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "show_delete": False}
        return super().change_view(request, object_id, form_url, extra_context)

    def delete_view(self, request, object_id, extra_context=None):
        raise PermissionDenied


@admin.register(CreditAccount)
class CreditAccountAdmin(_ReadOnly):
    list_display = (
        "user",
        "balance_cents",
        "starter_granted",
        "house_pictures_cents",
        "updated_at",
    )
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
        "house",
        "story_id",
        "turn",
    )
    list_filter = ("kind", "unlimited", "house")
    search_fields = ("user__email", "story_id", "request_id")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
