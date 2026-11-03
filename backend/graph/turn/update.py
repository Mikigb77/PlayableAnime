"""B5 step 6: the narrator's proposed update applied to the world, and the turn closed.

`apply_narration` stands in for `engine.apply.apply_delta(state, delta, ctx,
source=DeltaSource.NARRATOR)` from WS2's second PR, with the same result shape, so swapping it
is a one-line change. Until then it takes only what can't break an invariant (C1): the moment the
scene ends on (R3) and the rolling summary. Every other proposed change is reported as rejected,
so nothing the narrator invents reaches the state unchecked.
"""

from dataclasses import dataclass

from engine.context import TurnContext
from engine.contracts import StateDelta
from engine.state.cast import CharacterStatus
from engine.state.scene import SceneFrame
from engine.state.world import WorldState

# The rolling summary is flavour, never the only copy of anything (C2), so it stays short.
MAX_SUMMARY_CHARS = 2000

_WAITING = "applied once engine.apply lands (WS2)"


@dataclass(frozen=True)
class Rejection:
    """A proposed change that wasn't applied, and why. Mirrors `engine.apply.Rejection`."""

    subject: str
    change: str
    reason: str


@dataclass(frozen=True)
class Applied:
    """The new state (the input is never touched) and what was refused."""

    state: WorldState
    rejected: tuple[Rejection, ...] = ()


def apply_narration(state: WorldState, delta: StateDelta, ctx: TurnContext) -> Applied:
    """Applies the narrator's update: the scene end and the summary for now."""
    new = state.model_copy(deep=True)
    rejected: list[Rejection] = []

    end = delta.scene_end
    if end is not None:
        place_id = end.place_id
        if place_id is not None and place_id not in new.places:
            rejected.append(Rejection(place_id, "scene_end.place_id", "no such place"))
            place_id = None
        present = []
        for character_id in dict.fromkeys(end.present_ids):
            character = new.characters.get(character_id)
            if character is None:
                rejected.append(Rejection(character_id, "scene_end.present_ids", "no such person"))
            elif character.status is CharacterStatus.DEAD:
                rejected.append(Rejection(character_id, "scene_end.present_ids", "dead"))
            else:
                present.append(character_id)
        new.scene = SceneFrame(
            place_id=place_id or new.scene.place_id,
            present_ids=present,
            positions=end.positions,
            props=end.props,
            ended_on=end.ended_on.strip(),
            encounter=new.scene.encounter,
        )

    if delta.summary and delta.summary.strip():
        new.summary = delta.summary.strip()[:MAX_SUMMARY_CHARS]

    for name in ("characters", "factions", "places", "facts", "items", "leads", "rule_changes"):
        changes = getattr(delta, name)
        if changes:
            rejected.append(Rejection(name, f"{len(changes)} proposed", _WAITING))
    return Applied(state=new, rejected=tuple(rejected))


def close_turn(state: WorldState, ctx: TurnContext) -> WorldState:
    """The state as saved: `turn` is the turn just played. `apply_delta` stamps records with
    `ctx.turn` but never bumps it, so the graph does."""
    return state.model_copy(update={"turn": ctx.turn})
