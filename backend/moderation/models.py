"""Reports and blocks on scenes (F6), reviewed by staff who handle reports (T16).

A player reports a scene from the play screen and can block it, which hides its text in the app
at once. One report per scene and player: reporting the same scene again updates the report, so
the queue holds each scene once. Reports are the player's data, so they go with the story or the
account (T12, T16) and into the account export.
"""

import uuid

from django.conf import settings
from django.db import models

from stories.models import Scene, Story

# Only staff who handle reports may read the story text a report is about (T16). Superusers have
# every permission; everyone else gets this one through the report handlers group.
HANDLE_REPORTS = "moderation.handle_reports"
REPORT_HANDLERS_GROUP = "Report handlers"


class ReportCategory(models.TextChoices):
    """What the player says is wrong (docs/API.md)."""

    SEXUAL = "sexual", "Sexual content"
    MINOR = "minor", "A minor"
    HATE = "hate", "Hate"
    REAL_PERSON = "real_person", "A real person"
    SELF_HARM = "self_harm", "Self-harm"
    OTHER = "other", "Something else"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Open"
    ACTIONED = "actioned", "Action taken"
    DISMISSED = "dismissed", "Dismissed"


class Report(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="reports")
    scene = models.ForeignKey(Scene, on_delete=models.CASCADE, related_name="reports")
    # The story's owner: only they can open it (S8). Deleting the account deletes their
    # reports (T12, T16).
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports"
    )
    category = models.CharField(max_length=16, choices=ReportCategory.choices)
    # The player's own words. Story text by another name, so it is never logged (T6, T16).
    note = models.TextField(blank=True)
    # The player hid the scene's text (F6). Once blocked, a scene stays blocked.
    block = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, choices=ReportStatus.choices, default=ReportStatus.OPEN
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # What staff found and did, for whoever picks the report up next.
    resolution = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # The queue: oldest open report first.
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "reporter"], name="report_scene_reporter_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="report_queue_idx"),
            # The app's scene list asks which turns of a story are blocked.
            models.Index(
                fields=["story"], condition=models.Q(block=True), name="report_blocked_idx"
            ),
        ]
        permissions = [
            ("handle_reports", "Can handle reports and read the story text they are about"),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()} report on {self.scene}"
