from django.contrib import admin

from moderation.access import StoryTextAdmin
from stories.models import PendingEvent, Scene, Story

# T16: story text is read only by staff handling reports (`moderation.access`). Everyone else on
# the staff sees titles, ratings, turns and numbers.


class SceneInline(StoryTextAdmin, admin.TabularInline):
    model = Scene
    story_text_fields = ("player_action",)
    extra = 0
    fields = ("turn", "kind", "player_action", "input_mode", "time_label", "image_status")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-turn",)

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Story)
class StoryAdmin(StoryTextAdmin, admin.ModelAdmin):
    story_text_fields = ("premise", "state")
    list_display = ("title", "owner", "genre", "rating", "engine", "turn", "updated_at")
    list_filter = ("rating", "engine")
    search_fields = ("id", "title", "owner__email")
    raw_id_fields = ("owner",)
    # Only a turn writes the world state and the version (B12, T10).
    readonly_fields = ("id", "engine", "state", "turn", "version", "created_at", "updated_at")
    inlines = [SceneInline]

    def save_model(self, request, obj, form, change) -> None:
        if not change:
            super().save_model(request, obj, form, change)
            return
        # Save only what staff changed: a full-row save would write back the world state and
        # version as they were when the form loaded, undoing a turn saved in between.
        changed = [name for name in form.changed_data if name in self._model_fields]
        if changed:
            obj.save(update_fields=[*changed, "updated_at"])

    @property
    def _model_fields(self) -> set[str]:
        return {field.name for field in Story._meta.concrete_fields}


@admin.register(Scene)
class SceneAdmin(StoryTextAdmin, admin.ModelAdmin):
    story_text_fields = (
        "player_action",
        "narration",
        "choices",
        "details",
        "event",
        "image_prompt",
    )
    list_display = ("story", "turn", "kind", "input_mode", "image_status", "created_at")
    list_filter = ("kind", "input_mode", "image_status")
    search_fields = ("story__id", "story__title")
    raw_id_fields = ("story",)
    readonly_fields = ("created_at",)


@admin.register(PendingEvent)
class PendingEventAdmin(StoryTextAdmin, admin.ModelAdmin):
    story_text_fields = ("payload",)
    list_display = ("story", "kind", "timeline_id", "due_world_s", "status", "created_turn")
    list_filter = ("status", "kind")
    search_fields = ("story__id", "story__title", "kind")
    raw_id_fields = ("story",)
    readonly_fields = ("id", "created_at")
