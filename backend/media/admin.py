from django.contrib import admin

from media.models import Image, PremiseCover, ScenePicture
from moderation.access import StoryTextAdmin


@admin.register(Image)
class ImageAdmin(StoryTextAdmin, admin.ModelAdmin):
    """Read-only: pictures are drawn and charged by the picture endpoints, never by hand. What a
    picture shows comes from the story's text, so only staff handling reports read it (T16)."""

    story_text_fields = ("brief",)

    list_display = ("story", "kind", "subject", "version", "status", "skip_reason", "model")
    list_filter = ("kind", "status", "skip_reason", "payer")
    search_fields = ("id", "story__id", "story__title", "subject")
    raw_id_fields = ("story",)
    readonly_fields = [f.name for f in Image._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ScenePicture)
class ScenePictureAdmin(admin.ModelAdmin):
    list_display = ("scene", "image", "planned", "trigger", "created_at")
    raw_id_fields = ("scene", "image")
    readonly_fields = ("scene", "image", "planned", "trigger", "created_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(PremiseCover)
class PremiseCoverAdmin(admin.ModelAdmin):
    """Read-only: `manage.py draw_premise_covers` draws them. Deleting one removes its file, and
    the command draws it again."""

    list_display = ("premise_id", "model", "cost_usd", "offline", "drawn_at")
    list_filter = ("offline", "model")
    readonly_fields = [f.name for f in PremiseCover._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
