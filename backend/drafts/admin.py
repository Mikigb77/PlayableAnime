from django.contrib import admin

from drafts.models import Draft
from moderation.access import StoryTextAdmin


@admin.register(Draft)
class DraftAdmin(StoryTextAdmin, admin.ModelAdmin):
    """Read-only: a draft changes only through the drafting API, and its proposal holds the
    story's hidden truth, for staff handling support. The premise and the proposal are story
    text, so only staff handling reports read them (T16)."""

    story_text_fields = ("premise", "proposal")

    list_display = ("id", "owner", "premise_id", "rating", "story", "updated_at")
    list_filter = ("rating", "premise_id")
    search_fields = ("id", "owner__email", "premise_id")
    raw_id_fields = ("owner", "story")
    readonly_fields = [field.name for field in Draft._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False
