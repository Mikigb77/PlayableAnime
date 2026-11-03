from django.contrib import admin

from drafts.models import Draft


@admin.register(Draft)
class DraftAdmin(admin.ModelAdmin):
    """Read-only: a draft changes only through the drafting API, and its proposal holds the
    story's hidden truth, for staff handling support."""

    list_display = ("id", "owner", "premise_id", "rating", "story", "updated_at")
    list_filter = ("rating", "premise_id")
    search_fields = ("id", "owner__email", "premise_id")
    raw_id_fields = ("owner", "story")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False
