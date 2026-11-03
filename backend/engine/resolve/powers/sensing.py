"""Sensing and hiding strength (G20).

Where the world's ladder can be sensed, a character senses others' strength up to their own rung:
anyone higher is simply beyond them. A character can hide their strength and show a lower rung,
which fools everyone who can't see through it, so NPCs treat them by what they can perceive. Only
someone already above the hider's true rung sees through the disguise. A reveal shifts attitudes
at once, by how far each onlooker underestimated them, and it is a public deed that starts
rumors (W1, W13).
"""

from engine.contracts.delta import AttitudeShift, CharacterChange, StateDelta
from engine.contracts.intent import IntentStep, OutcomeClass
from engine.contracts.resolution import ProposedDeed
from engine.resolve.checks import Settled
from engine.resolve.words import cap, name, possessive
from engine.state.bible import PowerLadder
from engine.state.cast import Character
from engine.state.records import StepResult
from engine.state.sheet import LadderPosition, PowerAxis
from engine.state.world import WorldState

# How much each rung an onlooker underestimated someone moves their attitude on a reveal.
FEAR_PER_RUNG = 20
RESPECT_PER_RUNG = 5
MAX_SHIFT = 60
REVEAL_SEVERITY = 2


def position(character: Character, ladder_id: str) -> LadderPosition | None:
    return next((p for p in character.sheet.ladders if p.ladder_id == ladder_id), None)


def shown_rung(position_: LadderPosition) -> int:
    return (
        position_.rung
        if position_.shown_rung is None
        else min(position_.shown_rung, position_.rung)
    )


def perceived_rung(
    state: WorldState, observer: Character, subject: Character, ladder_id: str
) -> int | None:
    """G20. The rung `observer` takes `subject` to stand on: the true one for someone above it,
    otherwise the rung shown, capped one above the observer's own where the ladder is sensed,
    since anything higher is simply beyond them. None if the subject isn't on that ladder."""
    ladder = state.bible.ladder(ladder_id)
    theirs = position(subject, ladder_id)
    if ladder is None or theirs is None:
        return None
    mine = position(observer, ladder_id)
    own = mine.rung if mine is not None else -1
    if own > theirs.rung:
        return theirs.rung
    shown = shown_rung(theirs)
    if ladder.sensing:
        return min(shown, own + 1)
    return shown


def _ladder(state: WorldState, actor: Character, ladder_id: str) -> PowerLadder | None:
    return state.bible.ladder(ladder_id)


def check(state: WorldState, actor: Character, step: IntentStep) -> Settled | None:
    """G20. A character can show less than they have, never more, and only on a ladder they
    stand on."""
    show = step.show_strength
    assert show is not None
    who = name(state, actor.id)
    ladder = _ladder(state, actor, show.ladder_id)
    mine = position(actor, show.ladder_id)
    if ladder is None or mine is None:
        return Settled(
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
            f"{cap(who)} {'have' if actor.id == state.player_id else 'has'} no strength like"
            " that to show.",
        )
    if show.shown_rung is not None and show.shown_rung > mine.rung:
        return Settled(
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
            f"{cap(who)} can't show more strength than {_they(state, actor)}"
            f" {_have(state, actor)}.",
        )
    if show.shown_rung is None and mine.shown_rung is None:
        return Settled(
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            f"{cap(possessive(state, actor.id))} strength was never hidden.",
        )
    return None


def _they(state: WorldState, actor: Character) -> str:
    return "you" if actor.id == state.player_id else "they"


def _have(state: WorldState, actor: Character) -> str:
    return "have" if actor.id == state.player_id else "has"


def settle(
    state: WorldState, actor: Character, step: IntentStep
) -> tuple[str, StateDelta, ProposedDeed | None]:
    """G20. Hide strength, or reveal it: the sheet records what others sense, and a reveal moves
    every onlooker who underestimated them, at once."""
    show = step.show_strength
    assert show is not None
    ladder = _ladder(state, actor, show.ladder_id)
    mine = position(actor, show.ladder_id)
    assert ladder is not None and mine is not None
    who = name(state, actor.id)
    if show.shown_rung is not None:
        hidden = mine.model_copy(update={"shown_rung": show.shown_rung})
        change = CharacterChange(id=actor.id, ladders=[hidden])
        shows = ladder.rungs[show.shown_rung].name
        hides = f"{_hide(state, actor)} {_their(state, actor)} strength"
        reason = f"{cap(who)} {hides}: others sense {shows}."
        return reason, StateDelta(characters=[change]), None

    true_name = ladder.rungs[mine.rung].name
    onlookers = [
        state.characters[cid]
        for cid in state.scene.present_ids
        if cid != actor.id and cid in state.characters and state.characters[cid].alive
    ]
    changes = [CharacterChange(id=actor.id, ladders=[mine.model_copy(update={"shown_rung": None})])]
    witnesses: list[str] = []
    for onlooker in onlookers:
        witnesses.append(onlooker.id)
        seen = perceived_rung(state, onlooker, actor, ladder.id)
        surprise = mine.rung - (seen if seen is not None else mine.rung)
        if surprise <= 0:
            continue
        fear = min(MAX_SHIFT, FEAR_PER_RUNG * surprise)
        respect = min(MAX_SHIFT, RESPECT_PER_RUNG * surprise) if ladder.standing_follows else 0
        toward = actor.id if actor.id != state.player_id else None
        shift = AttitudeShift(toward_id=toward, fear=fear, affinity=respect)
        changes.append(CharacterChange(id=onlooker.id, attitudes=[shift]))
    deed = ProposedDeed(
        kind="reveal",
        text=f"{cap(who)} {_reveal(state, actor)} {_their(state, actor)} strength: {true_name}",
        actor_id=actor.id if actor.id != state.player_id else None,
        target_ids=[],
        place_id=actor.location_id or state.scene.place_id,
        severity=REVEAL_SEVERITY,
        witness_ids=witnesses,
    )
    reason = (
        f"{cap(who)} {_reveal(state, actor)} {_their(state, actor)} true strength: {true_name}."
    )
    return reason, StateDelta(characters=changes), deed


def _hide(state: WorldState, actor: Character) -> str:
    return "hide" if actor.id == state.player_id else "hides"


def _reveal(state: WorldState, actor: Character) -> str:
    return "reveal" if actor.id == state.player_id else "reveals"


def _their(state: WorldState, actor: Character) -> str:
    return "your" if actor.id == state.player_id else "their"


def apparent_tier(state: WorldState, character: Character, tier: int) -> int:
    """G20. The might the world can measure while strength is hidden: the shown rung's tier on a
    might ladder, in place of the true one."""
    for found in character.sheet.ladders:
        if found.shown_rung is None:
            continue
        ladder = state.bible.ladder(found.ladder_id)
        if ladder is None or ladder.axis is not PowerAxis.MIGHT:
            continue
        shown = shown_rung(found)
        if 0 <= shown < len(ladder.rungs):
            tier = min(tier, ladder.rungs[shown].tier)
    return tier
