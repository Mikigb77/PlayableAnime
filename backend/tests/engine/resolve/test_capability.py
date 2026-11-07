"""A2, A3, G14: the odds come from who the character is, not from a coin toss.

The interpret step judges how hard a step is for an ordinary person (its challenge), and code
weighs the character's attributes, skills, traits, powers and condition against it. A step a
capable character is sure to manage, with only things in the way, is certain. A run of misses
makes the player character's next roll likelier, so bad luck doesn't pile up on what they're good
at, without ever changing a step's class.
"""

import pytest

from engine import pipeline
from engine.context import Difficulty
from engine.contracts import (
    ActionKind,
    Aim,
    Challenge,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    SheetPart,
    SheetUse,
    StepFacts,
)
from engine.resolve import capability
from engine.resolve import odds as odds_mod
from engine.samples import cultivation_world, farm_world
from engine.state import (
    Attributes,
    Character,
    CharacterSheet,
    Faction,
    Health,
    PassingState,
    PowerAxis,
    Skill,
    SkillLevel,
    StepResult,
    Trait,
    TraitKind,
    WorldState,
)
from engine.state.records import RollRecord
from tests.engine.resolve.worlds import (
    MANY_SEEDS,
    SEEDS,
    add,
    burn_the_hall,
    ctx,
    disciple,
    facts,
    resolve,
    rng,
    sect,
    shielded_mage,
    step,
)


def farm(**attributes) -> WorldState:
    """Tomas at his gate at dusk, with a lit lantern fallen in the straw."""
    state = farm_world()
    state.scene.props.append("a lit lantern fallen in the straw")
    state.characters["tomas"].sheet.attributes = Attributes(**attributes)
    return state


def gift(state: WorldState, trait: str, kind: TraitKind = TraitKind.GIFT) -> WorldState:
    state.player.sheet.traits.append(Trait(name=trait, kind=kind))
    return state


def stamp(challenge: Challenge | None = Challenge.EASY, *uses: SheetUse, **kw) -> IntentStep:
    kw.setdefault("opposition", "the lantern's flame")
    kw.setdefault("proposed_class", OutcomeClass.CONTESTED)
    return step(
        "stamp the lantern out against the floor",
        ActionKind.INSTANT,
        2,
        verb="stamp out",
        uses=list(uses),
        facts=StepFacts(challenge=challenge, **kw),
    )


def attribute(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.ATTRIBUTE, ref=name)


def trait(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.TRAIT, ref=name)


def skill(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.SKILL, ref=name)


def plan(*steps: IntentStep) -> Intent:
    return Intent(steps=list(steps))


# --- the character counts --------------------------------------------------------------------


def test_a_nimble_character_stamping_out_a_lantern_is_certain_with_no_roll():
    state = gift(farm(speed=5), "cat's grace")
    nimble = stamp(Challenge.EASY, attribute("agility"), trait("cat's grace"))

    for seed in SEEDS:
        settled = resolve(state, plan(nimble), seed).steps[0]
        assert settled.outcome_class is OutcomeClass.CERTAIN
        assert settled.result is StepResult.SUCCESS and settled.roll is None
    assert settled.reason == (
        "The lantern's flame can't stop you: an easy task, your speed and your cat's grace in "
        "your favour."
    )


def test_a_clumsy_character_rolls_the_same_step_at_worse_odds():
    nimble = resolve(farm(speed=4), plan(stamp(Challenge.MODERATE, attribute("speed")))).steps[0]
    average = resolve(farm(), plan(stamp(Challenge.MODERATE, attribute("speed")))).steps[0]
    clumsy_state = gift(farm(speed=1), "butterfingers", TraitKind.FLAW)
    clumsy_step = stamp(Challenge.MODERATE, attribute("speed"), trait("butterfingers"))
    clumsy = resolve(clumsy_state, plan(clumsy_step)).steps[0]

    assert nimble.roll.odds > average.roll.odds > clumsy.roll.odds
    assert average.roll.odds == pytest.approx(capability.CHALLENGE_ODDS[Challenge.MODERATE])
    assert clumsy.reason == (
        "The lantern's flame can push back: a real effort, your speed and your butterfingers "
        f"against you, {clumsy.roll.odds_label}."
    )


def test_harder_challenges_have_lower_odds_for_the_same_character():
    harder = list(Challenge)
    state = farm()
    chances = {}
    for c in harder:
        settled = resolve(state, plan(stamp(c))).steps[0]
        chances[c] = 1.0 if settled.roll is None else settled.roll.odds
    assert [chances[c] for c in harder] == sorted(chances.values(), reverse=True)
    assert chances[Challenge.TRIVIAL] == 1.0  # anyone manages it: no roll
    long_shot = resolve(state, plan(stamp(Challenge.EXTREME))).steps[0]
    assert long_shot.outcome_class is OutcomeClass.LONG_SHOT


def test_training_counts_rank_by_rank_against_an_untrained_hand():
    def picking(level: SkillLevel | None):
        state = farm(speed=3)
        if level is not None:
            state.player.sheet.skills.append(Skill(name="lockpicking", level=level))
        lock = step(
            "pick the lock on the granary door",
            ActionKind.TASK,
            120,
            verb="pick",
            uses=[skill("lockpicking")],
            facts=StepFacts(opposition="a good lock", challenge=Challenge.HARD),
        )
        return resolve(state, plan(lock)).steps[0]

    untrained = picking(None)
    fair = picking(SkillLevel.FAIR)
    master = picking(SkillLevel.MASTER)
    assert untrained.roll.odds == pytest.approx(capability.CHALLENGE_ODDS[Challenge.HARD])
    assert untrained.roll.odds < fair.roll.odds < master.roll.odds
    assert master.roll.odds > 0.8
    assert "your lockpicking (master) in your favour" in master.reason


def test_wounds_and_exhaustion_weigh_on_a_task_nobody_is_measured_against():
    fresh = resolve(farm(), plan(stamp(Challenge.MODERATE))).steps[0]
    state = farm()
    state.player.sheet.condition.health = Health.WOUNDED
    state.player.sheet.condition.fatigue = 4
    worn = resolve(state, plan(stamp(Challenge.MODERATE))).steps[0]

    assert worn.roll.odds < fresh.roll.odds
    assert "your wounds and your exhaustion against you" in worn.reason


def test_a_power_the_step_uses_helps_where_nobody_is_measured_against_it():
    state = cultivation_world()
    lin = state.player
    lin.sheet.powers.append(
        lin.sheet.powers[0].model_copy(
            update={"id": "keen-eye", "name": "Keen Eye", "time": None, "costs": []}
        )
    )
    spot = step(
        "search the courtyard for the hidden trapdoor",
        ActionKind.TASK,
        60,
        verb="search",
        facts=StepFacts(opposition="a well-hidden trapdoor", challenge=Challenge.HARD),
    )
    plain = resolve(state, plan(spot)).steps[0]
    keen_step = spot.model_copy(
        update={"uses": [SheetUse(part=SheetPart.POWER, ref="keen-eye"), attribute("perception")]}
    )
    keen = resolve(state, plan(keen_step)).steps[0]

    assert keen.roll is None or keen.roll.odds > plain.roll.odds
    assert "your Keen Eye" in keen.reason


@pytest.mark.parametrize(
    ("ref", "names"),
    [
        ("agility", ("speed",)),
        ("dexterous hands", ("speed",)),
        ("Perception", ("wits",)),
        ("raw strength", ("strength",)),
        ("mind", ("wits", "knowledge", "willpower")),
        ("body", ("strength", "speed", "toughness")),
        ("bodies", ("strength", "speed", "toughness")),
        ("presence", ("charm", "nerve", "bearing")),
        ("will", ("willpower",)),
        ("force of will", ("willpower",)),
        ("luck", ()),
    ],
)
def test_attributes_are_found_by_the_words_a_step_names_them_by(ref, names):
    assert capability.attribute_names(ref) == names


# --- what can and can't make a step certain -----------------------------------------------------


def test_someone_or_a_faction_in_the_way_is_never_made_certain_by_the_sheet():
    state = gift(farm(speed=9), "cat's grace")
    state.factions["watch"] = Faction(id="watch", name="the night watch")
    sure = (attribute("speed"), trait("cat's grace"))
    watched = stamp(
        Challenge.TRIVIAL, *sure, opposition="the night watch", opposition_ids=["watch"]
    )

    settled = resolve(state, plan(watched)).steps[0]
    assert settled.outcome_class is OutcomeClass.CONTESTED
    assert settled.roll.odds == odds_mod.CONTESTED_BAND[1]


def test_a_step_the_interpret_step_called_certain_is_not_tossed_at_even_odds():
    # It named a thing in the way and judged no challenge; that is no reason for a coin toss.
    settled = resolve(farm(), plan(stamp(None, proposed_class=OutcomeClass.CERTAIN))).steps[0]
    assert settled.outcome_class is OutcomeClass.CERTAIN and settled.roll is None
    assert settled.reason == "The lantern's flame can't stop you."  # nothing more to say (A8)


def test_with_no_challenge_judged_an_average_character_still_rolls_at_even_odds():
    settled = resolve(farm(), plan(stamp(None))).steps[0]
    assert settled.roll.odds == pytest.approx(0.5)
    assert settled.reason == "The lantern's flame can push back: even odds."


def test_the_storys_difficulty_never_makes_a_step_certain():
    state = farm(speed=4)
    moderate = stamp(Challenge.MODERATE, attribute("speed"))
    for difficulty in Difficulty:
        settled = resolve(state, plan(moderate), difficulty=difficulty).steps[0]
        assert settled.outcome_class is OutcomeClass.CONTESTED, difficulty


def test_a_close_call_with_nothing_in_the_way_is_weighed_like_any_task():
    leap = step(
        "leap from the hayloft onto the cart",
        ActionKind.MOVE,
        3,
        verb="leap",
        uses=[attribute("agility")],
        facts=StepFacts(means=MeansVerdict.CLOSE_CALL, challenge=Challenge.MODERATE),
    )
    average = resolve(farm(), plan(leap)).steps[0]
    nimble = resolve(farm(speed=6), plan(leap)).steps[0]
    tumbler = gift(farm(speed=5), "born tumbler")
    tumbler.player.sheet.skills.append(Skill(name="acrobatics", level=SkillLevel.MASTER))
    sure = _with_use(_with_use(leap, skill("acrobatics")), trait("born tumbler"))
    acrobat = resolve(tumbler, plan(sure)).steps[0]

    assert average.roll.odds == pytest.approx(0.6)
    assert nimble.roll.odds > odds_mod.CLOSE_CALL_BAND[1]  # a judged task isn't capped at 80%
    assert acrobat.outcome_class is OutcomeClass.CERTAIN and acrobat.roll is None
    assert acrobat.reason == (
        "A real effort, your speed, your acrobatics (master) and your born tumbler in your "
        "favour, no real doubt."
    )


def test_a_blow_on_someone_helpless_keeps_its_close_call_between_harm_and_full_harm():
    state = cultivation_world()
    state.characters["zhao"].sheet.condition.states.append(PassingState(name="asleep"))
    stab = step(
        "stab the sleeping Zhao",
        target_ids=["zhao"],
        aim=Aim.KILL,
        facts=StepFacts(means=MeansVerdict.CLOSE_CALL, challenge=Challenge.MODERATE),
    )
    for seed in SEEDS:
        settled = resolve(state, plan(stab), seed).steps[0]
        if settled.roll is not None:
            assert settled.roll.allowed == odds_mod.HARM_DONE
            low, high = odds_mod.CLOSE_CALL_BAND
            assert low <= settled.roll.odds <= high


def test_a_sure_hand_never_makes_a_blow_on_a_tougher_sleeping_body_certain():
    # A2: being sure to get the blow in doesn't make it hurt a body a realm above.
    state = add(sect(), disciple("elder_wu", "Elder Wu", rung=1))
    state.characters["elder_wu"].sheet.condition.states.append(PassingState(name="asleep"))
    state.player.sheet.attributes = Attributes(strength=5, speed=5)
    state.player.sheet.traits.append(Trait(name="assassin's hands", kind=TraitKind.GIFT))
    cut = step(
        "slit the sleeping elder's throat",
        verb="attack",
        aim=Aim.KILL,
        target_ids=["elder_wu"],
        axis=PowerAxis.MIGHT,
        uses=[attribute("speed"), trait("assassin's hands")],
        facts=StepFacts(opposition="the creaking floorboards", challenge=Challenge.EASY),
    )
    settled = resolve(state, plan(cut)).steps[0]
    assert settled.outcome_class is not OutcomeClass.CERTAIN and settled.roll is not None


# --- measured contests --------------------------------------------------------------------------


def rival(speed: int) -> Character:
    return Character(
        id="ilse_rival",
        name="Greta",
        age=30,
        sheet=CharacterSheet(attributes=Attributes(speed=speed)),
    )


def grab(*uses: SheetUse) -> IntentStep:
    return step(
        "snatch the lantern before Greta can",
        ActionKind.INSTANT,
        2,
        verb="snatch",
        axis=PowerAxis.MIGHT,
        uses=list(uses),
        facts=StepFacts(opposition_ids=["ilse_rival"], challenge=Challenge.MODERATE),
    )


def test_against_someone_measured_the_attributes_are_weighed_against_theirs():
    even = resolve(add(farm(speed=4), rival(4)), plan(grab(attribute("speed")))).steps[0]
    quicker = resolve(add(farm(speed=5), rival(3)), plan(grab(attribute("speed")))).steps[0]
    slower = resolve(add(farm(speed=2), rival(4)), plan(grab(attribute("speed")))).steps[0]

    assert slower.roll.odds < even.roll.odds < quicker.roll.odds
    assert even.roll.odds == pytest.approx(0.5)  # the gap sets the base, not the challenge
    assert "your speed in your favour" in quicker.reason


def test_head_to_head_two_people_untrained_in_a_skill_are_even_in_it():
    untrained = resolve(add(farm(speed=4), rival(4)), plan(grab(skill("knife-fighting")))).steps[0]
    assert untrained.roll.odds == pytest.approx(0.5)
    assert "knife-fighting" not in untrained.reason

    trained = add(farm(speed=4), rival(4))
    trained.player.sheet.skills.append(Skill(name="Knife-fighting", level=SkillLevel.FAIR))
    settled = resolve(trained, plan(grab(skill("knife-fighting")))).steps[0]
    assert settled.roll.odds > untrained.roll.odds
    assert "your knife-fighting (fair) in your favour" in settled.reason


# --- a plan that goes around the strength (A9) --------------------------------------------------


def _guard(level: SkillLevel | None) -> WorldState:
    state = shielded_mage()
    if level is not None:
        state.characters["su-yan"].sheet.skills.append(Skill(name="Perception", level=level))
    return state


def _sneak(challenge: Challenge, proposed: OutcomeClass = OutcomeClass.CONTESTED) -> Intent:
    aware = facts(
        opposition_ids=["su-yan"],
        can_respond=True,
        challenge=challenge,
        proposed_class=proposed,
    )
    return Intent(steps=[burn_the_hall(facts=aware, uses=[skill("perception")])])


def test_a_chain_setup_is_harder_to_slip_past_a_watchful_rival():
    novice = resolve(_guard(SkillLevel.NOVICE), _sneak(Challenge.MODERATE)).steps[0]
    master = resolve(_guard(SkillLevel.MASTER), _sneak(Challenge.MODERATE)).steps[0]
    assert master.roll.odds < novice.roll.odds


def test_a_chain_setup_takes_its_class_from_the_weighed_odds_not_the_proposal():
    # An easy setup the model called a long shot isn't held to the long-shot band.
    easy = resolve(_guard(None), _sneak(Challenge.EASY, OutcomeClass.LONG_SHOT)).steps[0]
    assert easy.roll.odds > odds_mod.LONG_SHOT_BAND[1]
    extreme = resolve(_guard(None), _sneak(Challenge.EXTREME)).steps[0]
    assert extreme.roll.odds <= odds_mod.LONG_SHOT_BAND[1]


# --- a run of misses ----------------------------------------------------------------------------


def test_each_miss_in_a_row_makes_the_next_roll_likelier_up_to_a_cap():
    chances = []
    for misses in range(capability.MAX_MISSES + 2):
        state = farm()
        state.misses_in_a_row = misses
        settled = resolve(state, plan(stamp(Challenge.MODERATE))).steps[0]
        assert settled.outcome_class is OutcomeClass.CONTESTED
        chances.append(settled.roll.odds)
    assert chances == sorted(chances)
    assert len(set(chances[: capability.MAX_MISSES + 1])) == capability.MAX_MISSES + 1
    assert chances[-1] == chances[-2]  # capped
    state = farm()
    state.misses_in_a_row = 2
    assert "your last two misses in your favour" in resolve(state, plan(stamp())).steps[0].reason


def test_a_run_of_misses_never_lifts_a_long_shot_out_of_its_band():
    state = farm()
    state.misses_in_a_row = 9
    settled = resolve(state, plan(stamp(Challenge.EXTREME))).steps[0]
    assert settled.outcome_class is OutcomeClass.LONG_SHOT
    assert settled.roll.odds <= odds_mod.LONG_SHOT_BAND[1]


def test_npcs_get_no_lift_from_the_players_misses():
    state = farm()
    state.misses_in_a_row = 3
    theirs = resolve(state, Intent(actor_id="ilse", steps=[stamp(Challenge.MODERATE)])).steps[0]
    assert theirs.roll.odds == pytest.approx(capability.CHALLENGE_ODDS[Challenge.MODERATE])


def _roll(odds: float, result: StepResult, allowed=None) -> RollRecord:
    return RollRecord(
        seed="s",
        label="x",
        odds=odds,
        odds_label="",
        value=0.5,
        result=result,
        allowed=allowed or list(odds_mod.ALL_RESULTS),
        difficulty=Difficulty.BALANCED,
    )


def test_what_counts_as_a_miss():
    after = capability.misses_after
    assert after(2, _roll(0.5, StepResult.SUCCESS), StepResult.SUCCESS) == 0
    assert after(2, _roll(0.5, StepResult.FAILURE), StepResult.FAILURE) == 3
    assert after(2, _roll(0.5, StepResult.PARTIAL), StepResult.PARTIAL) == 3
    assert after(2, None, StepResult.FAILURE) == 2  # settled by the facts: no luck in it
    assert after(2, _roll(1.0, StepResult.FAILURE), StepResult.FAILURE) == 2  # only a duration
    own_choice = _roll(0.5, StepResult.PARTIAL, list(odds_mod.OWN_CHOICE))
    assert after(2, own_choice, StepResult.PARTIAL) == 2  # it couldn't fail


def test_playing_out_records_the_run_and_a_clean_success_ends_it():
    state = farm()
    for seed in SEEDS:
        resolution = resolve(state, plan(stamp(Challenge.HARD)), seed)
        played = pipeline.play_out(state, resolution, ctx(), rng(seed)).state
        missed = resolution.steps[0].result is not StepResult.SUCCESS
        assert played.misses_in_a_row == (1 if missed else 0)
    sure = gift(farm(speed=5), "cat's grace")
    sure.misses_in_a_row = 2
    certain = resolve(sure, plan(stamp(Challenge.EASY, attribute("speed"), trait("cat's grace"))))
    assert pipeline.play_out(sure, certain, ctx(), rng()).state.misses_in_a_row == 2


def test_five_misses_in_a_row_on_an_even_task_become_rare():
    # Without the lift, five misses running at even odds come up about 1 time in 32.
    runs = 0
    for seed in MANY_SEEDS[:2000]:
        state = farm()
        missed = 0
        for attempt in range(5):
            resolution = resolve(state, plan(stamp(None)), seed * 10 + attempt)
            state = pipeline.play_out(state, resolution, ctx(), rng(seed * 10 + attempt)).state
            if resolution.steps[0].result is StepResult.SUCCESS:
                break
            missed += 1
        runs += missed == 5
    assert runs / 2000 < 0.005


def _with_use(s: IntentStep, use: SheetUse) -> IntentStep:
    return s.model_copy(update={"uses": [*s.uses, use]})
