"""N6: how a turn ends the player character's story, and what an ending's note may ask for.

A story never ends by itself (S4). It reaches an ending in two ways: the player character dies,
or the player ends it with `/end`. A note on how it should end is read like any action and
checked by the engine first. An ending only keeps what the world already allows: a part the world
rules out, or that would take a long shot to earn, is refused with its reason, since a long shot
is something to play for, not to end on. Contested parts are rolled as in any scene (A2).
"""

from __future__ import annotations

from engine import pipeline
from engine.context import TurnContext
from engine.contracts import Intent, OutcomeClass
from engine.rng import SeededRng
from engine.state.world import WorldState
from graph.turn.errors import RefusedStep
from graph.turn.types import Ending, TurnKind

# What an ending's note can't ask for (N6).
REFUSED = (OutcomeClass.RULED_OUT, OutcomeClass.LONG_SHOT)


def ending_of(
    before: WorldState, after: WorldState, intent: Intent | None, kind: TurnKind
) -> Ending | None:
    """The ending this turn reached, if any: the player character died in it, or the player
    ended the story and they lived."""
    player_id = before.player_id
    if before.player.alive and not after.player.alive:
        return Ending(
            kind="death", character_id=player_id, self_inflicted=_aimed_at_self(intent, player_id)
        )
    if kind is TurnKind.END:
        return Ending(kind="chosen", character_id=player_id)
    return None


def _aimed_at_self(intent: Intent | None, player_id: str) -> bool:
    """Whether the player aimed harm at their own body this turn (F1), as opposed to dying of
    something else, such as the blast of their own throw (W10a)."""
    if intent is None:
        return False
    return any(step.aim.harmful and player_id in step.target_ids for step in intent.steps)


def earned(
    world: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng
) -> tuple[Intent | None, list[RefusedStep]]:
    """The note's steps the world allows, and the ones it refuses with their reasons. A plan
    stops at its first refused step (R6), so the check runs again on what is left until nothing
    more is refused, and every refusal is named at once. It changes nothing: the turn resolves
    what is kept on its own. None when nothing is kept, so the epilogue tells things as they
    stand."""
    kept = list(intent.steps)
    refused: list[RefusedStep] = []
    while kept:
        trial = intent.model_copy(update={"steps": kept})
        resolution = pipeline.resolve(world, trial, ctx, rng)
        out = {s.index: s for s in resolution.steps if s.outcome_class in REFUSED}
        if not out:
            break
        refused += [
            RefusedStep(text=s.text, reason=s.reason, outcome_class=s.outcome_class.value)
            for s in out.values()
        ]
        kept = [step for i, step in enumerate(kept) if i not in out]
    if not kept:
        return None, refused
    return intent.model_copy(update={"steps": kept}), refused
