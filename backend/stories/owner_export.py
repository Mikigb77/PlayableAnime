"""The owner's own stories, whole, for reviewing real play (T16).

Miki and the threads that work on the game read real stories to find what to improve. Nobody
reads a player's stories that way (T16), so this covers only the accounts that hold the owner
role and whose email is in `OWNER_EMAILS` (K7): the owner looking at their own game from the
inside. Unlike the account export (T12, `stories.export`), it includes what the player hasn't
seen, the world state and the events waiting to happen, because that is what shows why a story
went the way it did.

It names no account and carries no row id, and it leaves the server only sealed for one reader
(`stories.sealed`, `manage.py export_owner_stories`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.db.models import Prefetch

from accounts.models import Role, User
from stories.export import scene_data
from stories.models import PendingEvent, Scene, Story

FORMAT = 1


def owners():
    """The owner accounts: the role, which only a verified Google sign-in grants, and an email
    that is still in `OWNER_EMAILS` (K7). Either alone isn't enough."""
    return User.objects.filter(role=Role.OWNER, email__in=settings.OWNER_EMAILS)


def _scene(scene: Scene) -> dict[str, Any]:
    data = scene_data(scene)
    # A picture's URL is signed for a player and names the story's row; its state is enough.
    if data["image"] is not None:
        data["image"] = {"kind": scene.image_kind, "status": scene.image_status}
    data["image_prompt"] = scene.image_prompt
    data["timeline_id"] = scene.timeline_id
    data["cast"] = scene.cast
    return data


def _pending_event(event: PendingEvent) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "status": event.status,
        "due_world_s": event.due_world_s,
        "timeline_id": event.timeline_id,
        "created_turn": event.created_turn,
        "applied_turn": event.applied_turn,
        "payload": event.payload,
    }


def _story(story: Story) -> dict[str, Any]:
    return {
        "title": story.title,
        "premise": story.premise,
        "genre": story.genre,
        "rating": story.rating,
        "engine": story.engine,
        "settings": story.settings,
        "turn": story.turn,
        "version": story.version,
        "ending": story.ending,
        "successor": story.successor,
        # A3: a turn that was decided and shown, and whose scene isn't saved yet, as kept.
        "unfinished_turn": story.unfinished_turn,
        "created_at": story.created_at.isoformat(),
        "updated_at": story.updated_at.isoformat(),
        "state": story.state,
        "scenes": [_scene(scene) for scene in story.scenes.all()],
        "pending_events": [_pending_event(event) for event in story.pending_events.all()],
    }


def export_owner_stories() -> dict[str, Any]:
    """Every story the owner accounts have, oldest first, each with all its scenes in turn order
    (the ones a rewind took back included, marked), its world state and its pending events."""
    stories = (
        Story.objects.filter(owner__in=owners())
        .order_by("created_at")
        .prefetch_related(
            Prefetch("scenes", queryset=Scene.objects.order_by("turn", "created_at")),
            Prefetch(
                "pending_events",
                queryset=PendingEvent.objects.order_by("due_world_s", "created_at"),
            ),
        )
    )
    return {
        "format": FORMAT,
        "exported_at": datetime.now(UTC).isoformat(),
        "stories": [_story(story) for story in stories],
    }
