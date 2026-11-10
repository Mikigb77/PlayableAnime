"""A player's stories as plain data, for the account export (T12).

Everything the player has seen: each story's premise and settings, and every scene with the
action, narration, choices, the reasoning shown in scene details and in-world time, and what they
sent for a turn that was decided and shown but whose scene isn't saved yet (A3). The world state
stays out, because it holds hidden truths the player hasn't learned (C6, N7).
"""

from django.db.models import Prefetch

from stories import unfinished
from stories.models import Scene, Story


def scene_data(scene: Scene) -> dict:
    has_image = scene.image_planned or scene.image_status or scene.image_url
    return {
        "turn": scene.turn,
        "kind": scene.kind,
        "player_action": scene.player_action,
        "input_mode": scene.input_mode,
        "narration": scene.narration,
        "choices": scene.choices,
        "details": scene.details,
        "event": scene.event,
        "time": {
            "world_start_s": scene.world_start_s,
            "world_end_s": scene.world_end_s,
            "label": scene.time_label,
            "duration_label": scene.duration_label,
            "personal_label": scene.personal_label or None,
        },
        "image": (
            {"kind": scene.image_kind, "status": scene.image_status, "url": scene.image_url}
            if has_image
            else None
        ),
        # C8: a rewind took it back out of the story, though the player saw it.
        "rewound": scene.rewound_at is not None,
        "created_at": scene.created_at.isoformat(),
    }


def story_data(story: Story) -> dict:
    return {
        "id": str(story.id),
        "title": story.title,
        "premise": story.premise,
        "genre": story.genre,
        "rating": story.rating,
        "settings": story.settings,
        "turn": story.turn,
        "version": story.version,
        "unfinished_turn": unfinished.sent(story),
        "created_at": story.created_at.isoformat(),
        "updated_at": story.updated_at.isoformat(),
        "scenes": [scene_data(scene) for scene in story.scenes.all()],
    }


def export_stories(owner_id) -> list[dict]:
    """Every story the user owns, oldest first, each with all its scenes in turn order, and the
    ones a rewind took back (C8) before the scene played anew in their turn."""
    stories = (
        Story.objects.filter(owner_id=owner_id)
        .order_by("created_at")
        .prefetch_related(Prefetch("scenes", queryset=Scene.objects.order_by("turn", "created_at")))
    )
    return [story_data(story) for story in stories]
