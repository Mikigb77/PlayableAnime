"""A turn the engine decided and showed, but whose scene was never saved (A3, T10).

The engine decides a turn's steps before the narrator writes a word, and the stream shows them
at once (`steps.decided`): how each step went and why, its dice, what struck back. Left at that,
a player could look at a throw, or at a fall that kills them, close the app and send a different
action that suits them better. So a turn is kept on the story (`Story.unfinished_turn`) before
its steps are shown, until its scene is saved, and whatever turn is sent next plays that one out:
the same action, read the same way, under the same settings and on the same seed, so every step
and every die falls exactly as it was shown.

Kept: the turn's number and timeline, what the player sent (kind, action, standing, input mode,
`drop_refused`), the two settings the engine decides by as they stood then (difficulty, A5, and
how often events come, W16), and the interpret step's reading of the action
(`graph.turn.Reading`). The settings that only shape the telling, and what the player asked not
to be shown (F7), are read fresh. A turn with no steps to show, such as an opening, is not kept:
nothing of it was shown, and it stays all or nothing as before.

The column holds the player's own words, like a scene's `player_action`, so it is never logged
(T6) and it goes when the story does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from engine.context import Difficulty, EventFrequency
from engine.contracts import Intent, StandingAction
from engine.state.world import WorldState
from graph.turn import Reading, StepsDecided, TurnInput, TurnKind
from lucid.errors import ApiError, ErrorCode, version_conflict
from stories.models import Story

logger = logging.getLogger("stories.turns")


class _Kept(BaseModel):
    """The column's JSON."""

    turn: int
    timeline_id: str
    kind: TurnKind
    action: str | None = None
    standing: StandingAction | None = None
    input_mode: str | None = None
    drop_refused: bool = False
    difficulty: Difficulty
    event_frequency: EventFrequency
    intent: Intent
    overflow: list[str] = []


@dataclass(frozen=True)
class Unfinished:
    """The turn a story still owes: what was sent, and how it was read."""

    turn: int
    kind: TurnKind
    action: str | None
    standing: StandingAction | None
    input_mode: str | None
    drop_refused: bool
    difficulty: Difficulty
    event_frequency: EventFrequency
    reading: Reading

    @property
    def player_action(self) -> str | None:
        """What the player did, as a scene shows it: their words, a choice's label, or the
        standing action."""
        if self.kind is TurnKind.STANDING and self.standing is not None:
            return self.standing.value
        return self.action


def _read(story: Story) -> _Kept | None:
    data = story.unfinished_turn
    if not data:
        return None
    try:
        return _Kept.model_validate(data)
    except ValidationError:
        # Numbers only: the column holds the player's words (T6).
        logger.warning(
            "An unfinished turn couldn't be read, so it was left out",
            extra={"unfinished_turn": {"story_turn": story.turn}},
        )
        return None


def of_story(story: Story, state: WorldState) -> Unfinished | None:
    """The turn `story` still owes, if it was decided for the very next turn of the world as
    it stands. One kept for any other moment is stale, and one that can't be read is dropped
    from play: the story must never be stuck behind it."""
    kept = _read(story)
    if kept is None:
        return None
    if kept.turn != state.turn + 1 or kept.timeline_id != state.timeline_id:
        return None
    return Unfinished(
        turn=kept.turn,
        kind=kept.kind,
        action=kept.action,
        standing=kept.standing,
        input_mode=kept.input_mode,
        drop_refused=kept.drop_refused,
        difficulty=kept.difficulty,
        event_frequency=kept.event_frequency,
        reading=Reading(intent=kept.intent, overflow=tuple(kept.overflow)),
    )


def sent(story: Story) -> dict[str, Any] | None:
    """What the player sent for the turn `story` owes, for their account export (T12). Never
    how it was read: that is the engine's, and can hold what they haven't learned (C6)."""
    kept = _read(story)
    if kept is None:
        return None
    action = kept.standing.value if kept.standing is not None else kept.action
    return {"turn": kept.turn, "kind": kept.kind.value, "action": action}


def keep(
    story: Story, turn: TurnInput, decided: StepsDecided, *, input_mode: str | None, version: int
) -> None:
    """Keeps the turn on the story, before its steps are shown. Raises `version_conflict` when
    the story moved on since the turn read it, or already owes another turn, so of two actions
    sent at once only one is ever shown (T10)."""
    data: dict[str, Any] = _Kept(
        turn=turn.ctx.turn,
        timeline_id=turn.state.timeline_id,
        kind=turn.kind,
        action=turn.action,
        standing=turn.standing,
        input_mode=input_mode,
        drop_refused=turn.drop_refused,
        difficulty=turn.ctx.settings.difficulty,
        event_frequency=turn.ctx.settings.event_frequency,
        intent=decided.reading.intent,
        overflow=list(decided.reading.overflow),
    ).model_dump(mode="json")
    kept = Story.objects.filter(pk=story.pk, version=version, unfinished_turn__isnull=True).update(
        unfinished_turn=data
    )
    if kept == 1:
        return
    current = Story.objects.filter(pk=story.pk).values_list("version", flat=True).first()
    if current is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
    raise version_conflict(current)


def drop(story: Story) -> None:
    """Lets go of the turn the story owes, as when playing it out failed twice: a story is
    never stuck behind a turn that can't be finished."""
    Story.objects.filter(pk=story.pk).update(unfinished_turn=None)
