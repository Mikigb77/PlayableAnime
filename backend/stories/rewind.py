"""C8: rewinding a story a few scenes after a death, by difficulty (N6, Miki 2026-11-05).

A death by others or by the world can be taken back: up to 5 scenes on Story, 1 on Balanced and
none on Brutal, by the difficulty the fatal scene was played on, so changing it afterwards changes
nothing. A death the player chose is always real, so it can't be taken back, and neither can an
ending told with `/end`. A rewind sits outside the fiction: the world goes back to exactly how it
was when the scene it goes back to ended, and nobody in the story remembers. The scenes after it
are taken out of the story, and what they cost isn't refunded. The dice for a moment stay the same
(A3), so doing exactly the same thing again goes the same way: a rewind is a chance to play it
differently, not a reroll.

Each saved turn keeps the world state it left (`TurnSnapshot`, saved with the turn, B12), and a
story keeps only those a rewind can reach, so never one from before its opening. Someone new
carrying the story on (N6) drops them all, so a rewind never reaches back into another character's
story. `POST /v1/stories/{id}/rewind` puts the story back to one of them in one transaction: the
world state and its pending events (W10), the scenes, the pictures, and the version moves on (T10).
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from engine.context import Difficulty
from engine.state.world import WorldState
from graph.turn import Ending
from lucid.errors import field_error, version_conflict
from media.plans import retire_rewound
from stories import endings, pending
from stories.models import Scene, Story, TurnSnapshot

logger = logging.getLogger("stories.rewind")

# How many scenes back a death on each difficulty can be rewound.
REACH = {Difficulty.STORY: 5, Difficulty.BALANCED: 1, Difficulty.BRUTAL: 0}
FARTHEST = max(REACH.values())
# How many turns back the kept states go: twice the farthest reach, so that after a rewind as far
# as it goes the next death can still reach as far again.
KEPT = 2 * FARTHEST


def keep(story: Story, turn: int, state: dict) -> None:
    """Keeps the world state turn `turn` left, as saved on the story, and drops the ones no rewind
    can reach any more. Call it in the turn's transaction."""
    TurnSnapshot.objects.update_or_create(story=story, turn=turn, defaults={"state": state})
    TurnSnapshot.objects.filter(story=story, turn__lt=turn - KEPT).delete()


def reach(story: Story, turn: int, difficulty: Difficulty, ending: Ending) -> int:
    """How many scenes back the ending turn `turn` reached can be rewound: a death not by the
    player character's own hand, up to its difficulty's reach and as far back as the story kept
    the world. Each scene in between can be rewound to as well."""
    if ending.kind != "death" or ending.self_inflicted:
        return 0
    most = REACH.get(difficulty, 0)
    if most <= 0:
        return 0
    kept = set(
        TurnSnapshot.objects.filter(story=story, turn__gte=turn - most, turn__lt=turn).values_list(
            "turn", flat=True
        )
    )
    scenes = 0
    while scenes < most and turn - scenes - 1 in kept:
        scenes += 1
    return scenes


def forget(story: Story) -> None:
    """Drops every kept state, as when someone new carries the story on (N6): their story starts
    there, and a rewind never reaches back into someone else's."""
    TurnSnapshot.objects.filter(story=story).delete()


def rewind(story: Story, expected_version: int, scenes: int) -> Story:
    """Takes the story back `scenes` scenes from its ending, to the world as it was then, with the
    version moving on (T10)."""
    with transaction.atomic():
        current = (
            Story.objects.select_for_update()
            .only("ending", "state", "turn", "version")
            .get(pk=story.pk)
        )
        if current.version != expected_version:
            raise version_conflict(current.version)
        state = WorldState.model_validate(current.state)
        ending = endings.of_story(current.ending, state)
        if ending is None:
            raise field_error(
                "story_id",
                "This story hasn't reached an ending, so there is nothing to rewind.",
                source="path",
                type="not_ended",
            )
        if ending.closed:
            raise field_error(
                "story_id",
                "This story is closed. Start again from its premise instead.",
                source="path",
                type="closed",
            )
        to_turn = current.turn - scenes
        snapshot = (
            TurnSnapshot.objects.filter(story=current, turn=to_turn).first()
            if scenes <= ending.rewind
            else None
        )
        if snapshot is None:
            raise _too_far(ending.rewind)
        restored = WorldState.model_validate(snapshot.state)
        # The events the rewound scenes applied wait again, and the ones they scheduled never
        # come (W10).
        pending.write_back(current, state, restored)
        pending.cancel_after(current, to_turn)
        now = timezone.now()
        rewound = list(
            Scene.objects.live()
            .filter(story=current, turn__gt=to_turn)
            .values_list("pk", flat=True)
        )
        Scene.objects.filter(pk__in=rewound).update(rewound_at=now)
        retire_rewound(current.pk, restored, rewound)
        TurnSnapshot.objects.filter(story=current, turn__gt=to_turn).delete()
        Story.objects.filter(pk=current.pk).update(
            state=snapshot.state,
            turn=to_turn,
            ending=None,
            successor=None,
            version=F("version") + 1,
            updated_at=now,
        )
    logger.info("Story rewound", extra={"rewind": {"scenes": scenes, "to_turn": to_turn}})
    story.refresh_from_db()
    return story


def _too_far(most: int):
    if most <= 0:
        message = "This ending can't be rewound."
    elif most == 1:
        message = "This ending can be rewound by one scene only."
    else:
        message = f"This ending can be rewound by at most {most} scenes."
    return field_error("scenes", message, type="too_far")
