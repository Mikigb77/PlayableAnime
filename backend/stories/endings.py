"""N6: a story's ending, as it is saved on the story row and sent as API.md's `Ending`.

A story reaches an ending when the player character dies, or when the player ends it with `/end`
and its epilogue is told. From then on it takes no more turns (`story_ended`). The player then
closes it, starts again from the same premise, or (later) carries on as someone else in the same
world. A story saved before endings were recorded, whose player character is already dead, is at
a death ending too.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from engine.state.world import WorldState
from graph.turn import Ending
from lucid.errors import ApiError, ErrorCode


class EndingOut(BaseModel):
    """API.md's `Ending`."""

    kind: Literal["death", "chosen"]
    # Who fell or retired, and their name as the story last knew it.
    character_id: str
    character: str
    # Harm they aimed at their own body killed them (F1): the app adds a quiet line on where to
    # find support.
    self_inflicted: bool = False
    # The scene it came in, or null for an older story whose scene wasn't recorded.
    turn: int | None = None
    # The player closed the story: it stays in the Library to read, and nothing more happens.
    closed: bool = False


def record(ending: Ending, state: WorldState, turn: int) -> dict[str, Any]:
    """The ending a turn reached, as saved on the story row."""
    character = state.characters.get(ending.character_id)
    return EndingOut(
        kind=ending.kind,
        character_id=ending.character_id,
        character=character.name if character else "",
        self_inflicted=ending.self_inflicted,
        turn=turn,
    ).model_dump(mode="json")


def of_story(saved: Any, state: WorldState | None = None) -> EndingOut | None:
    """The story's ending: the one saved with it, or a death read from a state whose player
    character is already dead. None while the story plays on."""
    if isinstance(saved, dict):
        return EndingOut.model_validate(saved)
    if state is not None and state.characters and not state.player.alive:
        return EndingOut(kind="death", character_id=state.player_id, character=state.player.name)
    return None


def ended(ending: EndingOut) -> ApiError:
    """`409 story_ended`: a turn on a story at its ending."""
    return ApiError(
        ErrorCode.STORY_ENDED,
        "This story has reached its ending. Close it, or start again from its premise.",
        {"ending": ending.model_dump(mode="json")},
    )
