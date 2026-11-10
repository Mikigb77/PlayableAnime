"""Nothing natural fails for no reason (decided 2026-11-10, Miki): the character's own moves.

"You have no power like that" and "You never learned that technique" are said only of something
no record of theirs names (A4, G14). A move made of the world's energy they hold, a way they are
still learning and a technique they know are theirs to try, whichever part of the sheet the
interpret step filed them under, and something filed as carried that is really such a move, or
that the scene or their looks hold, is at hand (C10). A squire who has trained with aura for
weeks is never told she has no such power, nor that she has no aura blade "on her".
"""

from engine.base import HOUR
from engine.contracts import (
    Beat,
    BeatUse,
    BeatVerdict,
    GrowthKind,
    Intent,
    OutcomeClass,
    SheetPart,
    SheetUse,
    UseSource,
)
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Extraordinary,
    Power,
    Practice,
    Prevalence,
    StepResult,
    Technique,
    WorldState,
)
from engine.state.records import Transfer

from .power_worlds import play, train
from .worlds import power, resolve, step


def technique(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.TECHNIQUE, ref=ref)


def item(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.ITEM, ref=ref)


def with_aura(state: WorldState) -> WorldState:
    """A world that also has combat aura, as a knightly story's would."""
    state.bible.extraordinary.append(
        Extraordinary(id="aura", kind="combat aura", prevalence=Prevalence.COMMON)
    )
    return state


def squire() -> WorldState:
    """Lin where combat aura exists, with an hour of aura training behind him and no power of
    it on his sheet yet."""
    state = with_aura(cultivation_world())
    state.player.sheet.practice.append(
        Practice(key="technique:aura-step", what="Aura Step", effort_s=HOUR)
    )
    return state


def attempt(state: WorldState, *uses: SheetUse):
    """Nothing pushes back, so only the sheet check can stop it."""
    (settled,) = resolve(state, Intent(steps=[step("split the log", uses=list(uses))])).steps
    return settled


def in_a_beat(state: WorldState, source: UseSource, thing: str, ref: str | None = None):
    beat = Beat(text=f"use {thing}", uses=[BeatUse(source=source, thing=thing, ref=ref)])
    (settled,) = resolve(state, Intent(steps=[step("split the log", beats=[beat])])).steps
    return settled


def test_a_move_of_an_energy_they_have_trained_is_theirs_to_try():
    state = squire()

    for use in (power("aura"), power("combat aura")):
        settled = attempt(state, use)
        assert settled.result is StepResult.SUCCESS, use
        # The energy alone is no move: nothing of the sheet is added, and nothing is learned.
        assert settled.drew_on == []
        assert not any(c.techniques for c in settled.effects.characters)

    # A move made of it is theirs, and the narrator is told it worked as they know it to (R1).
    leap = attempt(state, technique("aura leap"))
    assert leap.result is StepResult.SUCCESS
    assert leap.drew_on == ["Aura leap"]

    fist = in_a_beat(state, UseSource.POWER, "aura around my fist")
    assert fist.beats[0].verdict is BeatVerdict.HOLDS


def test_an_energy_they_never_touched_is_still_refused():
    state = with_aura(cultivation_world())  # the world has aura, and Lin never trained it

    assert attempt(state, power("aura")).reason == "You have no power like that."
    assert attempt(state, technique("aura leap")).reason == "You never learned that technique."
    assert in_a_beat(state, UseSource.POWER, "aura around my fist").reason == (
        "You have no power like that."
    )
    assert in_a_beat(state, UseSource.CARRIED, "an aura blade").reason == (
        "You have no aura blade on you."
    )


def test_the_energy_they_hold_or_a_ladder_they_stand_on_makes_a_move_theirs():
    state = cultivation_world()  # a reserve of qi, and the first of the realms: Qi Condensation
    lin = state.player.sheet

    assert attempt(state, power("qi")).result is StepResult.SUCCESS
    lin.condition.reserves.clear()  # the rung alone still says he cultivates qi
    assert attempt(state, power("a thread of qi")).result is StepResult.SUCCESS
    lin.ladders.clear()
    assert attempt(state, power("qi")).reason == "You have no power like that."


def test_a_way_they_are_still_learning_is_theirs_by_its_name():
    state = cultivation_world()
    state.player.sheet.practice.append(
        Practice(key="technique:rising-palm", what="Rising Palm", effort_s=HOUR)
    )

    whole = attempt(state, technique("the rising palm, with all my weight"))
    part = attempt(state, power("the palm"))

    assert (whole.result, part.result) == (StepResult.SUCCESS, StepResult.SUCCESS)
    # It is used under its own name, whatever words the step found for it.
    assert whole.drew_on == part.drew_on == ["Rising Palm"]


def test_one_shared_word_makes_nothing_theirs():
    """Knowing a cloud slash makes no one a void slasher, and practice at swordsmanship is no
    technique."""
    state = cultivation_world()
    sheet = state.player.sheet
    sheet.techniques.append(Technique(id="cloud-slash", name="Cloud Slash"))
    sheet.practice.append(Practice(key="skill:lightning-reflexes", what="lightning reflexes"))

    assert attempt(state, power("void slash")).reason == "You have no power like that."
    assert attempt(state, technique("void slash")).reason == "You never learned that technique."
    assert attempt(state, power("lightning")).reason == "You have no power like that."
    assert in_a_beat(state, UseSource.POWER, "a slash of black fire").beats[0].verdict is (
        BeatVerdict.EMPTY
    )


def test_a_technique_they_know_named_as_a_power_is_that_technique():
    state = cultivation_world()
    state.player.sheet.techniques.append(Technique(id="falling-leaf", name="Falling Leaf Palm"))

    settled = attempt(state, power("Falling Leaf Palm"))
    in_beat = in_a_beat(state, UseSource.POWER, "the falling leaf palm")

    assert settled.result is StepResult.SUCCESS
    assert settled.drew_on == ["Falling Leaf Palm"]
    assert in_beat.beats[0].verdict is BeatVerdict.HOLDS
    assert in_beat.drew_on == ["Falling Leaf Palm"]


def test_a_technique_named_as_a_power_still_waits_for_the_power_it_is_made_with():
    """G25: a technique of a power is that power at work, so it must be ready."""
    state = cultivation_world()
    sheet = state.player.sheet
    sheet.powers.append(Power(id="aura", name="Aura", ready_at_personal_s=10**9))
    sheet.techniques.append(Technique(id="crescent", name="Crescent Cut", power_id="aura"))

    settled = attempt(state, power("crescent cut"))
    in_beat = in_a_beat(state, UseSource.POWER, "a crescent cut")

    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert settled.reason == "Your Aura hasn't recovered yet."
    assert in_beat.reason == "Your Aura hasn't recovered yet."


def test_an_aura_blade_filed_as_something_carried_is_a_move_and_a_sword_stays_a_sword():
    state = squire()

    blade = in_a_beat(state, UseSource.CARRIED, "an aura blade")
    sword = in_a_beat(state, UseSource.CARRIED, "my sword")

    assert blade.beats[0].verdict is BeatVerdict.HOLDS
    assert attempt(state, item("aura blade")).result is StepResult.SUCCESS
    assert sword.reason == "You have no sword on you."
    assert attempt(state, item("my sword")).outcome_class is OutcomeClass.RULED_OUT


def test_something_carried_that_no_sheet_lists_is_at_hand_when_the_scene_or_their_looks_hold_it():
    """C10, C9, R3: the bottle they picked up last turn and the coat they wear are no items on
    the sheet, and both are plainly there."""
    state = grounded_world()  # a bottle of grappa on the bar
    state.player.appearance = "32, lean, in a dark overcoat and a grey felt hat."

    bottle = in_a_beat(state, UseSource.CARRIED, "the bottle of grappa")
    coat = in_a_beat(state, UseSource.CARRIED, "my overcoat")
    shotgun = in_a_beat(state, UseSource.CARRIED, "my shotgun")

    assert bottle.beats[0].verdict is BeatVerdict.HOLDS
    assert coat.beats[0].verdict is BeatVerdict.HOLDS
    assert attempt(state, item("the bottle of grappa")).result is StepResult.SUCCESS
    assert shotgun.reason == "You have no shotgun on you."

    # C10: looks are written once and go stale. What the record says left them is gone.
    state.transfers.append(Transfer(name="grey felt hat", quantity=1, from_id="luca", to_id=None))
    hat = in_a_beat(state, UseSource.CARRIED, "my hat")
    assert (hat.result, hat.reason) == (StepResult.FAILURE, "You have no hat on you.")
    assert in_a_beat(state, UseSource.CARRIED, "my overcoat").beats[0].verdict is BeatVerdict.HOLDS


def test_practising_a_technique_they_know_simply_happens_and_is_never_learned_twice():
    """A4: "You already know it" was a refusal that took the turn away for nothing."""
    state = cultivation_world()
    state.player.sheet.techniques.append(Technique(id="falling-leaf", name="Falling Leaf Sword"))

    played = play(state, Intent(steps=[train(GrowthKind.TECHNIQUE, "Falling Leaf Sword", 2)]))

    (settled,) = played.resolution.steps
    assert (settled.outcome_class, settled.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert settled.reason == "You already know Falling Leaf Sword, so this is practice."
    lin = played.state.player.sheet
    assert [t.name for t in lin.techniques] == ["Falling Leaf Sword"]
    assert lin.practice == [] and lin.growth == []
    assert played.state.world_s - state.world_s == 2 * HOUR
