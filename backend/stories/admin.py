from django.contrib import admin

from stories.models import PendingEvent, Scene, Story


class SceneInline(admin.TabularInline):
    model = Scene
    extra = 0
    fields = ("turn", "kind", "player_action", "input_mode", "time_label", "image_status")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-turn",)

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "genre", "rating", "engine", "turn", "updated_at")
    list_filter = ("rating", "engine")
    search_fields = ("id", "title", "owner__email")
    raw_id_fields = ("owner",)
    readonly_fields = ("id", "turn", "version", "created_at", "updated_at")
    inlines = [SceneInline]


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    list_display = ("story", "turn", "kind", "input_mode", "image_status", "created_at")
    list_filter = ("kind", "input_mode", "image_status")
    search_fields = ("story__id", "story__title")
    raw_id_fields = ("story",)
    readonly_fields = ("created_at",)


@admin.register(PendingEvent)
class PendingEventAdmin(admin.ModelAdmin):
    list_display = ("story", "kind", "timeline_id", "due_world_s", "status", "created_turn")
    list_filter = ("status", "kind")
    search_fields = ("story__id", "story__title", "kind")
    raw_id_fields = ("story",)
    readonly_fields = ("id", "created_at")
