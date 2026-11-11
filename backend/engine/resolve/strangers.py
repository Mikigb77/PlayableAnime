"""F1, W1, W2. Someone the story hasn't met, made real when a harmful step aims at them.

"I grab a knife and kill some random guy" names nobody the scene holds. Before anything resolves,
code checks that the place holds someone like that right now, as it would a stone a beat reaches
for (R2): plausible is found, uncertain is rolled, and absent is nobody there, which ends the step.
Someone found becomes a real minor character where the actor is, so the harm has a victim, the
deed has witnesses and the world answers it like any other (W1, W2, W11).

Who they turn out to be is rolled, since nobody can tell from a glance (A2):

- **Most are ordinary**: tier 1, the world's ordinary person, with an average adult's body.
- **About 1 in 15 is tougher than they look**: someone who knows how to fight, one step of power
  above an ordinary person and a level above them in body, who can stop a weak attacker but not
  a strong one.
- **A hidden master is rare**, and rarer where the extraordinary is (about 1 in 1,000 in a
  grounded world, 1 in 200 where powers are everywhere): one step above the attacker, capped at
  the strongest the world holds (A9), with a body at a person's peak, and alert, so they always
  see it coming, whatever the interpret step proposed.

Their body is on the sheet they are made with (G13), so a throw against them reads their level
like anyone's (A3).

What is done before a crowd is public (W2), whoever it is done to: when it does someone harm
and nobody there but those it fell on is awake to see it, one of the crowd is made real too
(`onlooker`), so a killing in a busy street has a witness who can go to the law (W11).
"""

from dataclasses import dataclass, field

from engine.context import TurnContext
from engine.contracts.delta import CharacterChange, StateDelta
from engine.contracts.intent import IntentStep, OutcomeClass, Plausibility, UseSource
from engine.contracts.resolution import BeatResolution, BeatVerdict
from engine.invariants import is_real_name
from engine.resolve.checks import Settled, find_roll
from engine.resolve.power import base_tier, scale
from engine.resolve.words import cap
from engine.rng import SeededRng
from engine.state.bible import Prevalence
from engine.state.cast import Character, Prominence
from engine.state.records import StepResult
from engine.state.sheet import Attributes, CharacterSheet, PowerAxes, PowerAxis
from engine.state.world import WorldState
from engine.world.geography import characters_at, perceives

# How often a stranger is tougher than they look (someone who knows how to fight), and how often
# a hidden master, by how common the extraordinary is in the world (G6). Miki, 2026-11-05: a master
# is rare, never every other stranger on a killing spree, and rarer where nothing is extraordinary.
TOUGH_ODDS = 1 / 15
MASTER_ODDS = {
    Prevalence.NONE: 1 / 1000,
    Prevalence.HIDDEN: 1 / 500,
    Prevalence.RARE: 1 / 500,
    Prevalence.COMMON: 1 / 200,
}
ORDINARY_TIER = 1
# The best a real person can be, such as a veteran killer: a hidden master in a world with no
# ladder can be this strong even when nobody recorded yet is (A9, G6).
PEAK_PERSON_TIER = 4
# G13, A3. The body of a stranger who can fight, on the attribute scale where 3 is an average
# adult and 5 the best a person can be: a level above ordinary, and two for a hidden master.
TOUGH_BODY = 4
MASTER_BODY = 5
ANYONE = "a passer-by"
ONLOOKER = "an onlooker"


@dataclass(frozen=True)
class Met:
    """Who a step found: the stranger it aims at and any onlooker, the check on the find, the
    changes that make them real, and whether the stranger sees the step coming. When nobody is
    there, `settled` is the empty search that ends the step and `people` is empty."""

    check: BeatResolution
    people: list[Character] = field(default_factory=list)
    effects: StateDelta = field(default_factory=StateDelta)
    alert: bool = False
    settled: Settled | None = None


def meet(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    index: int,
    ctx: TurnContext,
    rng: SeededRng,
) -> Met:
    """The stranger a harmful step aims at, made real, or the empty search that ends the step."""
    assert step.stranger is not None
    who = _who(step.stranger.who)
    beat = f"find {who}"
    plausibility = step.stranger.plausibility
    found_roll = None

    def empty(outcome_class: OutcomeClass, reason: str, roll=None) -> Met:
        check = BeatResolution(
            text=beat,
            thing=who,
            source=UseSource.NEW,
            verdict=BeatVerdict.EMPTY,
            reason=reason,
            roll=roll,
        )
        return Met(check=check, settled=Settled(outcome_class, StepResult.FAILURE, reason, roll))

    if plausibility is Plausibility.ABSENT:
        return empty(OutcomeClass.RULED_OUT, f"There is nobody like {who} here.")
    if plausibility is Plausibility.UNCERTAIN:
        found_roll = find_roll(beat, ctx, rng.child("found"))
        if found_roll.result is not StepResult.SUCCESS:
            return empty(OutcomeClass.CONTESTED, f"Nobody like {who} comes by.", found_roll)

    place_id = state.scene.place_id or actor.location_id
    if place_id not in state.places:
        place_id = None
    stranger_id = _fresh_id(state, f"stranger-{ctx.turn}-{index}")
    might, master = _measure(state, actor, rng.child("who"))
    body = _body(might, master)
    stranger = Character(
        id=stranger_id,
        name=who,
        prominence=Prominence.MINOR,
        description=f"{cap(who)}, a stranger the story hadn't met.",
        location_id=place_id,
        sheet=CharacterSheet(axes=PowerAxes(might=might), attributes=body or Attributes()),
    )
    people = [stranger]
    changes = [
        _made(stranger).model_copy(
            update={"attributes": body, "meets_player": actor.id == state.player_id}
        )
    ]
    reason = f"There is {who} here." if found_roll is None else f"There is {who} here after all."
    check = BeatResolution(
        text=beat,
        thing=who,
        source=UseSource.NEW,
        verdict=BeatVerdict.MADE_CANON,
        reason=reason,
        roll=found_roll,
    )
    return Met(check=check, people=people, effects=StateDelta(characters=changes), alert=master)


def _measure(state: WorldState, actor: Character, rng: SeededRng) -> tuple[int, bool]:
    """The stranger's might, and whether they are a hidden master (A2, A9)."""
    draw = rng.random()
    measure = scale(state, PowerAxis.MIGHT, actor)
    step = max(1, round(measure.step))
    master = master_odds(state)
    if draw < master:
        mine = base_tier(state, actor, PowerAxis.MIGHT)
        return max(ORDINARY_TIER, min(mine + step, strongest(state))), True
    if draw < master + TOUGH_ODDS:
        return ORDINARY_TIER + step, False
    return ORDINARY_TIER, False


def _body(might: int, master: bool) -> Attributes | None:
    """G13. The body a stranger who can fight is made with, or None for an ordinary one."""
    if master:
        return Attributes(
            strength=MASTER_BODY, speed=MASTER_BODY, toughness=MASTER_BODY, wits=MASTER_BODY
        )
    if might > ORDINARY_TIER:
        return Attributes(strength=TOUGH_BODY, speed=TOUGH_BODY, toughness=TOUGH_BODY)
    return None


def master_odds(state: WorldState) -> float:
    """How likely a stranger is a hidden master here: as likely as the most common
    extraordinary thing in the world makes it (G6)."""
    prevalences = [e.prevalence for e in state.bible.extraordinary] or [Prevalence.NONE]
    return max(MASTER_ODDS[p] for p in prevalences)


def strongest(state: WorldState) -> int:
    """A9. The strongest the world holds: its highest rung of might, the strongest body in it,
    or the best a real person can be, so a hidden master is never a champion that couldn't
    exist."""
    ladders = [lad for lad in state.bible.ladders if lad.axis is PowerAxis.MIGHT]
    rungs = [r.tier for lad in ladders for r in lad.rungs]
    bodies = [base_tier(state, c, PowerAxis.MIGHT) for c in state.characters.values() if c.alive]
    return max([PEAK_PERSON_TIER, *rungs, *bodies])


def _made(person: Character) -> CharacterChange:
    """The change that makes someone the plan thought up real."""
    return CharacterChange(
        id=person.id,
        name=person.name,
        prominence=Prominence.MINOR,
        description=person.description,
        location_id=person.location_id,
        axes=person.sheet.axes,
    )


def crowded(step: IntentStep) -> bool:
    """W2. Whether people the scene doesn't name are around to see a step, as the interpret
    step says of every step (`StepFacts.crowd`), or said of a stranger it aimed at."""
    return step.facts.crowd or (step.stranger is not None and step.stranger.crowd)


def onlooker(
    state: WorldState, place_id: str | None, apart: set[str], turn: int, index: int
) -> tuple[Character, CharacterChange] | None:
    """W2, W11. Someone in the crowd who saw what was done there, made real, with the change
    that does it. None when someone the record already puts at the place is awake to see it,
    besides those in `apart` (the doer and those it fell on): then it has its witness."""
    if place_id is None or place_id not in state.places:
        return None
    if any(c.id not in apart and perceives(c) for c in characters_at(state, place_id)):
        return None
    person = Character(
        id=_fresh_id(state, f"onlooker-{turn}-{index}"),
        name=ONLOOKER,
        prominence=Prominence.MINOR,
        description="Someone in the crowd who saw it happen.",
        location_id=place_id,
    )
    return person, _made(person)


def _who(words: str) -> str:
    text = " ".join(words.split())[:120]
    return text if is_real_name(text) else ANYONE


def _fresh_id(state: WorldState, wanted: str) -> str:
    record_id, n = wanted, 1
    while record_id in state.characters:
        n += 1
        record_id = f"{wanted}-{n}"
    return record_id
