"""N6: how a turn ends the player character's story, and what an ending's note may ask for.

A story never ends by itself (S4). It reaches an ending in two ways: the player character dies,
or the player ends it with `/end`. A note on how it should end is read like any action and
checked by the engine first. An ending only keeps what the world already allows: a part the world
rules out, or that would take a long shot to earn, is refused with its reason, since a long shot
is something to play for, not to end on. Contested parts are rolled as in any scene (A2). An
outcome or another's reaction the note claims ("and the sect names me emperor") is refused too:
the player never writes those (A6), and an ending is no exception.
"""

from __future__ import annotations

from engine import pipeline
from engine.context import TurnContext
from engine.contracts import Intent, OutcomeClass, Resolution
from engine.rng import SeededRng
from engine.state.world import WorldState
from graph.turn.errors import RefusedStep
from graph.turn.types import Ending, TurnKind

# What an ending's note can't ask for (N6).
REFUSED = (OutcomeClass.RULED_OUT, OutcomeClass.LONG_SHOT)

# Why a note's outcome claim is refused (A6), in the world's words.
CLAIMED = "How others take it, and how things turn out, is for the world to decide."


def ending_of(
    before: WorldState,
    after: WorldState,
    intent: Intent | None,
    resolution: Resolution,
    kind: TurnKind,
) -> Ending | None:
    """The ending this turn reached, if any: the player character died in it, or the player
    ended the story and they lived."""
    player_id = before.player_id
    if before.player.alive and not after.player.alive:
        own = _died_by_own_hand(intent, resolution, player_id)
        return Ending(kind="death", character_id=player_id, self_inflicted=own)
    if kind is TurnKind.END:
        return Ending(kind="chosen", character_id=player_id)
    return None


def _died_by_own_hand(intent: Intent | None, resolution: Resolution, player_id: str) -> bool:
    """Whether the step that killed the player aimed harm at their own body (F1). Harm aimed at
    yourself ends the plan once it kills you, so that is the last step played. Dying of
    something else is not, even after cutting your own palm earlier in the plan, and nor is the
    blast of your own throw (W10a)."""
    if intent is None or not resolution.steps:
        return False
    last = resolution.steps[-1].index
    if last >= len(intent.steps):
        return False
    step = intent.steps[last]
    return step.aim.harmful and player_id in step.target_ids


def earned(
    world: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng
) -> tuple[Intent | None, list[RefusedStep]]:
    """The note as the world allows it, and the parts it refuses with their reasons. A plan
    stops at its first refused step (R6), so the check runs again on what is left until nothing
    more is refused, and every refusal is named at once. The note's outcome claims are refused
    as well (A6). It changes nothing: the turn resolves what is kept on its own.

    A note with nothing refused comes back as it was. Otherwise what is kept loses the claims,
    and its summary is its steps, so nothing refused reaches the narrator; None when nothing is
    left, so the epilogue tells things as they stand."""
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
    refused += [
        RefusedStep(text=claim, reason=CLAIMED, outcome_class=OutcomeClass.RULED_OUT.value)
        for claim in intent.outcome_claims
    ]
    if not refused:
        return intent, []
    rest = intent.model_copy(
        update={
            "steps": kept,
            "outcome_claims": [],
            "summary": "; ".join(step.text for step in kept),
        }
    )
    if not (rest.steps or rest.standing or rest.theories or rest.backstory or rest.goals):
        return None, refused
    return rest, refused
