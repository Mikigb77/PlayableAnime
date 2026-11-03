"""The report review queue (F6, T16): open reports first, oldest first, readable only by staff
who handle reports. A report shows what the player sent, the scene's own text and the scene
before it, so the reviewer can judge the moment without opening the story."""

import logging

from django.contrib import admin
from django.db.models import Case, IntegerField, Value, When
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from moderation.access import can_read_story_text
from moderation.models import Report, ReportStatus
from stories.models import Scene

logger = logging.getLogger("moderation.reports")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "category", "status", "block", "story_link", "turn", "reporter")
    list_filter = ("status", "category", "block")
    search_fields = ("id", "story__id", "reporter__email")
    list_select_related = ("story", "scene", "reporter")
    actions = ["mark_actioned", "mark_dismissed"]
    fieldsets = (
        (
            "Report",
            {
                "fields": (
                    "category",
                    "block",
                    "note",
                    "reporter",
                    "story_link",
                    "turn",
                    "created_at",
                )
            },
        ),
        ("Scene", {"fields": ("rating", "player_action", "narration", "scene_before")}),
        ("Review", {"fields": ("status", "resolution", "reviewer", "reviewed_at")}),
    )
    # Staff record a decision; what the player sent and the story itself never change here.
    readonly_fields = (
        "category",
        "block",
        "note",
        "reporter",
        "story_link",
        "turn",
        "created_at",
        "rating",
        "player_action",
        "narration",
        "scene_before",
        "reviewer",
        "reviewed_at",
    )

    # --- Who sees the queue (T16) ---

    def has_module_permission(self, request) -> bool:
        return can_read_story_text(request.user)

    def has_view_permission(self, request, obj=None) -> bool:
        return can_read_story_text(request.user)

    def has_change_permission(self, request, obj=None) -> bool:
        return can_read_story_text(request.user) and super().has_change_permission(request, obj)

    def has_add_permission(self, request) -> bool:
        return False  # reports come from players

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser

    # --- The queue ---

    def get_queryset(self, request):
        # Annotated before it is ordered, so the queue can sort by it.
        open_first = Case(
            When(status=ReportStatus.OPEN, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
        queryset = self.model._default_manager.get_queryset().annotate(queue_position=open_first)
        return queryset.order_by(*self.get_ordering(request))

    def get_ordering(self, request):
        return ("queue_position", "created_at")

    @admin.display(description="Story")
    def story_link(self, report: Report) -> str:
        url = reverse("admin:stories_story_change", args=[report.story_id])
        return format_html('<a href="{}">{}</a>', url, report.story.title)

    @admin.display(description="Turn", ordering="scene__turn")
    def turn(self, report: Report) -> int:
        return report.scene.turn

    @admin.display(description="Rating")
    def rating(self, report: Report) -> str:
        return report.story.get_rating_display()

    @admin.display(description="Player's action")
    def player_action(self, report: Report) -> str:
        return report.scene.player_action or "-"

    @admin.display(description="Narration")
    def narration(self, report: Report) -> str:
        return _paragraphs(report.scene.narration)

    @admin.display(description="The scene before")
    def scene_before(self, report: Report) -> str:
        before = (
            Scene.objects.filter(story_id=report.story_id, turn__lt=report.scene.turn)
            .order_by("-turn")
            .first()
        )
        if before is None:
            return "-"
        action = f"Action: {before.player_action}\n\n" if before.player_action else ""
        return _paragraphs(action + before.narration)

    # --- Decisions ---

    def save_model(self, request, obj: Report, form, change) -> None:
        if change and "status" in form.changed_data:
            self._reviewed(request, obj)
        super().save_model(request, obj, form, change)

    @admin.action(description="Mark the selected reports as actioned", permissions=["change"])
    def mark_actioned(self, request, queryset) -> None:
        self._close(request, queryset, ReportStatus.ACTIONED)

    @admin.action(description="Dismiss the selected reports", permissions=["change"])
    def mark_dismissed(self, request, queryset) -> None:
        self._close(request, queryset, ReportStatus.DISMISSED)

    def _close(self, request, queryset, status: ReportStatus) -> None:
        count = 0
        for report in queryset:
            report.status = status
            self._reviewed(request, report)
            report.save(update_fields=["status", "reviewer", "reviewed_at", "updated_at"])
            count += 1
        self.message_user(request, f"{count} report(s) marked {status.label.lower()}.")

    def _reviewed(self, request, report: Report) -> None:
        report.reviewer = request.user
        report.reviewed_at = timezone.now()
        logger.info(
            "report reviewed",
            extra={"report": {"id": str(report.id), "status": report.status}},
        )


def _paragraphs(text: str) -> str:
    parts = [p for p in text.split("\n") if p.strip()]
    return format_html_join("", "<p>{}</p>", ((p,) for p in parts)) or "-"
