"""Reporting and blocking a scene (F6), and the queries other apps need about it."""

import logging
from collections.abc import Iterable

from asgiref.sync import sync_to_async
from django.db import transaction

from moderation.models import Report, ReportStatus
from stories.models import Scene, Story

logger = logging.getLogger("moderation.reports")


def report_scene(
    story: Story, scene: Scene, reporter, *, category: str, note: str, block: bool
) -> Report:
    """Files the player's report, or updates the one they already filed on this scene.

    A repeat takes the new category, and the new note when there is one, and reopens a report
    staff had closed. A block is never undone by a later report without one.
    """
    if scene.story_id != story.id:
        raise ValueError("The scene belongs to another story.")
    with transaction.atomic():
        report, created = Report.objects.select_for_update().get_or_create(
            scene=scene,
            reporter=reporter,
            defaults={"story": story, "category": category, "note": note, "block": block},
        )
        reopened = False
        if not created:
            reopened = report.status != ReportStatus.OPEN
            report.category = category
            report.note = note or report.note
            report.block = report.block or block
            report.status = ReportStatus.OPEN
            report.save(update_fields=["category", "note", "block", "status", "updated_at"])
    # Never the note: it is the player's words about story text (T6, T16).
    logger.warning(
        "scene reported",
        extra={
            "report": {
                "id": str(report.id),
                "turn": scene.turn,
                "category": report.category,
                "block": report.block,
                "repeat": not created,
                "reopened": reopened,
            }
        },
    )
    return report


areport_scene = sync_to_async(report_scene)


async def blocked_turns(story: Story | str) -> set[int]:
    """The turns of a story whose text its player blocked (F6). The app shows these scenes
    without their text, so the scene list sets `blocked` from this."""
    story_id = story.pk if isinstance(story, Story) else story
    # A rewound scene's turn belongs to the scene played anew (C8).
    turns = Report.objects.filter(
        story_id=story_id, block=True, scene__rewound_at__isnull=True
    ).values_list("scene__turn", flat=True)
    return {turn async for turn in turns}


def export_reports(user) -> list[dict]:
    """The player's reports for the account export (T12): what they sent and where it stands.
    Staff notes stay out; they are about the review, not the player's data."""
    reports: Iterable[Report] = (
        Report.objects.filter(reporter=user).select_related("scene").order_by("created_at")
    )
    return [
        {
            "story_id": str(report.story_id),
            "turn": report.scene.turn,
            "category": report.category,
            "note": report.note,
            "block": report.block,
            "status": report.status,
            "created_at": report.created_at.isoformat(),
        }
        for report in reports
    ]
