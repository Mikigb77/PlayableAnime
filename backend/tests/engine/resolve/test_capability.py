"""A2, A3, A8, G13, G14: what a character throws for a step, and the number it has to reach.

The dice say how good the character is: a technique throws by its mastery, a step with no named
move by the skill it draws on, and a raw feat by the attributes it tests. The number says what
they are up against today: ten for each level of the thing or of whoever answers, less what the
story's difficulty takes off, and moved in steps of 5 by everything else that counts, each one
named. Code builds both from the records, and nothing hidden is left.
"""

import pytest

from engine.context import Difficulty
from engine.contracts import (
    ActionKind,
    Challenge,
    Edge,
    EdgeSource,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    SheetPart,
    SheetUse,
    StepFacts,
)
from engine.resolve import capability, resolve_intent
from engine.resolve import throw as dice
from engine.resolve.checks import Drawn
from engine.samples import cultivation_world, farm_world
from engine.state import (
    Attitude,
    Attributes,
    Character,
    CharacterSheet,
    DieKind,
    Fact,
    Faction,
    Health,
    Item,
    ItemKind,
    Mastery,
    PowerAxis,
    Reserve,
    Skill,
    SkillLevel,
    StepResult,
    Technique,
    Trait,
    TraitKind,
    WorldState,
)
from tests.engine.resolve.worlds import (
    MANY_SEEDS,
    SEEDS,
    add,
    besides_rank,
    burn_the_hall,
    ctx,
    facts,
    give,
    power,
    resolve,
    rng,
    shielded_mage,
    step,
)

BALANCED = Difficulty.BALANCED


def farm(**attributes) -> WorldState:
    """Tomas at his gate at dusk, with a lit lantern fallen in the straw."""
    state = farm_world()
    state.scene.props.append("a lit lantern fallen in the straw")
    state.characters["tomas"].sheet.attributes = Attributes(**attributes)
    return state


def gift(state: WorldState, trait: str, kind: TraitKind = TraitKind.GIFT) -> WorldState:
    state.player.sheet.traits.append(Trait(name=trait, kind=kind))
    return state


def stamp(challenge: Challenge | None = Challenge.MODERATE, *uses: SheetUse, **kw) -> IntentStep:
    kw.setdefault("opposition", "the lantern's flame")
    return step(
        "stamp the lantern out against the floor",
        ActionKind.INSTANT,
        2,
        verb="stamp out",
        uses=list(uses),
        facts=StepFacts(challenge=challenge, **kw),
    )


def lock(challenge: Challenge = Challenge.HARD, *uses: SheetUse, **kw) -> IntentStep:
    return step(
        "pick the lock on the granary door",
        ActionKind.TASK,
        120,
        verb="pick",
        uses=[skill("lockpicking"), *uses],
        facts=StepFacts(opposition="a good lock", challenge=challenge, **kw),
    )


def picker(level: SkillLevel | None = SkillLevel.FAIR, **attributes) -> WorldState:
    state = farm(**attributes)
    if level is not None:
        state.player.sheet.skills.append(Skill(name="lockpicking", level=level))
    return state


def attribute(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.ATTRIBUTE, ref=name)


def trait(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.TRAIT, ref=name)


def skill(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.SKILL, ref=name)


def technique(name: str) -> SheetUse:
    return SheetUse(part=SheetPart.TECHNIQUE, ref=name)


def plan(*steps: IntentStep) -> Intent:
    return Intent(steps=list(steps))


def one(state: WorldState, a_step: IntentStep, seed: int = 0, difficulty=BALANCED, scene=""):
    resolution = resolve_intent(state, plan(a_step), ctx(difficulty), rng(seed), scene=scene)
    return resolution.steps[0]


def parts(settled) -> list[tuple[str, int]]:
    return [(part.text, part.points) for part in settled.roll.throw.made_of]


# --- the hand (G14, A4) -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "hand", "why"),
    [
        (None, 1, "Lockpicking (untrained), 1 die"),
        (SkillLevel.NOVICE, 1, "Lockpicking (novice), 1 die"),
        (SkillLevel.FAIR, 2, "Lockpicking (fair), 2 dice"),
        (SkillLevel.SKILLED, 3, "Lockpicking (skilled), 3 dice"),
        (SkillLevel.EXPERT, 4, "Lockpicking (expert), 4 dice"),
        (SkillLevel.MASTER, 5, "Lockpicking (master), 5 dice"),
    ],
)
def test_a_step_with_no_named_move_throws_by_the_skill_it_draws_on(level, hand, why):
    settled = one(picker(level), lock(Challenge.VERY_HARD))
    thrown = settled.roll.throw
    assert (thrown.hand, thrown.hand_why) == (hand, why)
    assert thrown.number == 37 and thrown.most == 20 * hand
    # No move of their own is in it, so every die is plain.
    assert {die.kind for die in thrown.dice} == {DieKind.PLAIN}


@pytest.mark.parametrize(("speed", "hand"), [(1, 1), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5)])
def test_a_raw_feat_throws_from_the_attribute_it_tests(speed, hand):
    leap = step(
        "leap the flooded ditch",
        ActionKind.MOVE,
        3,
        verb="leap",
        uses=[attribute("agility")],
        facts=StepFacts(means=MeansVerdict.CLOSE_CALL, challenge=Challenge.VERY_HARD),
    )
    thrown = one(farm(speed=speed), leap).roll.throw
    assert thrown.hand == hand
    assert thrown.hand_why == f"Speed, {hand} {'die' if hand == 1 else 'dice'}"


def test_an_ordinary_hand_is_two_dice():
    thrown = one(farm(), stamp()).roll.throw
    assert (thrown.hand, thrown.hand_why) == (2, "An ordinary hand, 2 dice")


def blade(mastery: Mastery) -> WorldState:
    """Lin Feng with an aura blade he has to that mastery, and a thief of his own realm."""
    state = cultivation_world()
    state.player.sheet.techniques.append(
        Technique(id="aura-blade", name="Aura blade", mastery=mastery)
    )
    thief = Character(id="thief", name="Hu", location_id="well", sheet=CharacterSheet())
    return add(state, thief)


def cut(*uses: SheetUse, **kw) -> IntentStep:
    kw.setdefault("opposition_ids", ["thief"])
    kw.setdefault("can_respond", True)
    kw.setdefault("answers_with", "speed")
    return step(
        "cut the purse from Hu's belt with an aura blade",
        verb="cut",
        axis=PowerAxis.MIGHT,
        uses=[technique("aura blade"), *uses],
        facts=facts(**kw),
    )


@pytest.mark.parametrize(
    ("mastery", "hand", "own", "why"),
    [
        (Mastery.LEARNING, 1, DieKind.VIOLET, "Aura blade (learning), 1 die"),
        (Mastery.PRACTICED, 2, DieKind.VIOLET, "Aura blade (practiced), 2 dice"),
        (Mastery.SKILLED, 3, DieKind.VIOLET, "Aura blade (skilled), 3 dice"),
        (Mastery.SECOND_NATURE, 4, DieKind.GOLD, "Aura blade (second nature), 4 dice"),
    ],
)
def test_a_technique_throws_by_its_mastery_with_its_own_die_last(mastery, hand, own, why):
    state = blade(mastery)
    state.characters["thief"].sheet.attributes = Attributes(speed=5)  # level 4: always open
    for seed in range(40):
        thrown = one(state, cut(), seed).roll.throw
        assert (thrown.hand, thrown.hand_why) == (hand, why)
        held = [die for die in thrown.dice if not die.sprung]
        assert [die.kind for die in held] == [DieKind.PLAIN] * (hand - 1) + [own]


def test_the_best_technique_the_step_uses_sets_the_hand():
    state = blade(Mastery.LEARNING)
    state.player.sheet.techniques.append(
        Technique(id="aura-step", name="Aura step", mastery=Mastery.SKILLED)
    )
    thrown = one(state, cut(technique("aura step"))).roll.throw
    assert thrown.hand_why == "Aura step (skilled), 3 dice"


def test_a_step_keeps_what_it_was_done_with_and_how_well_thrown_or_not():
    """R4 (live run, 2026-11-10): a novice's stroke with nothing in its way was told like a
    master's, because a step with no throw said nothing of the hand. Every step that got as far
    as being tried now keeps the skill or the move it was done with and its level."""
    thrown = one(picker(SkillLevel.NOVICE), lock(Challenge.VERY_HARD))
    assert thrown.roll is not None and thrown.hand == "Lockpicking (novice)"
    # Nothing to throw for, and the hand is still told.
    easy = one(picker(SkillLevel.NOVICE), lock(Challenge.TRIVIAL))
    assert (easy.roll, easy.result) == (None, StepResult.SUCCESS)
    assert easy.hand == "Lockpicking (novice)"
    # A skill the sheet doesn't hold is untrained, and a move of theirs goes by its mastery.
    assert one(picker(None), lock(Challenge.TRIVIAL)).hand == "Lockpicking (untrained)"
    assert one(blade(Mastery.LEARNING), cut()).hand == "Aura blade (learning)"
    # A raw feat names no skill: the sheet's attributes say the rest.
    assert one(farm(), stamp()).hand == ""


def test_a_skill_they_hold_is_found_by_the_steps_own_words():
    # Miki's forest runner failed to climb a tree: the interpret step had named nothing from
    # the sheet, so the climb rolled like anyone's.
    state = farm()
    state.player.sheet.skills.append(Skill(name="Climbing", level=SkillLevel.EXPERT))
    climb = step(
        "leap onto the nearest tree and climb it",
        ActionKind.MOVE,
        25,
        verb="climb",
        facts=StepFacts(challenge=Challenge.VERY_HARD, opposition="the trunk"),
    )
    assert one(state, climb).roll.throw.hand_why == "Climbing (expert), 4 dice"
    # Two levels under an expert's four dice, the same trunk is nothing to throw for.
    easy = climb.model_copy(update={"facts": StepFacts(challenge=Challenge.MODERATE)})
    settled = one(state, easy)
    assert settled.outcome_class is OutcomeClass.CERTAIN and settled.roll is None


def test_a_skill_is_found_by_its_words_either_way():
    state = farm()
    state.player.sheet.skills.append(Skill(name="Tree climbing", level=SkillLevel.MASTER))
    climb = step(
        "go up the cliff",
        ActionKind.MOVE,
        25,
        verb="scale",
        uses=[skill("climbing")],
        facts=StepFacts(challenge=Challenge.EXTREME, opposition="the cliff"),
    )
    assert one(state, climb).roll.throw.hand_why == "Tree climbing (master), 5 dice"


def test_where_a_power_does_the_work_only_the_attributes_the_step_names_count():
    state = cultivation_world()
    lin = state.player
    lin.sheet.attributes = Attributes(strength=6, speed=6, wits=5)
    lin.sheet.powers.append(
        lin.sheet.powers[0].model_copy(
            update={"id": "keen-eye", "name": "Keen Eye", "time": None, "costs": []}
        )
    )
    search = step(
        "search the courtyard for the hidden trapdoor",
        ActionKind.TASK,
        60,
        verb="search",
        uses=[power("keen-eye")],
        facts=StepFacts(opposition="a well-hidden trapdoor", challenge=Challenge.HARD),
    )
    # "Search" would test his wits (5, four dice), but the power does the looking.
    assert one(state, search).roll.throw.hand_why == "Keen Eye, 2 dice"
    named = search.model_copy(update={"uses": [power("keen-eye"), attribute("perception")]})
    assert one(state, named).roll.throw.hand_why == "Wits, 4 dice"


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


@pytest.mark.parametrize(
    ("text", "verb", "names"),
    [
        ("leap onto the nearest tree and climb it", "climb", ("speed",)),
        ("search the room for the letter", "search", ("wits",)),
        ("pry the crate open", "pry", ("strength",)),
        ("talk her into lending the horse", "persuade", ("charm",)),
        ("wait by the fire", "wait", ()),
    ],
)
def test_a_steps_own_words_say_what_it_tests_when_it_names_no_attribute(text, verb, names):
    assert capability.attributes_used(step(text, verb=verb), None) == names


# --- the number: a thing's level (A3, A5) -------------------------------------------------------


@pytest.mark.parametrize(
    ("challenge", "number", "words"),
    [
        (Challenge.EASY, 7, "an easy task, level 1"),
        (Challenge.MODERATE, 17, "a real effort, level 2"),
        (Challenge.HARD, 27, "a hard task, level 3"),
        (Challenge.VERY_HARD, 37, "a very hard task, level 4"),
        (Challenge.EXTREME, 47, "a feat almost nobody manages, level 5"),
    ],
)
def test_a_things_level_is_the_word_it_was_judged_by(challenge, number, words):
    settled = one(farm(), stamp(challenge))
    assert settled.roll.throw.number == number
    assert parts(settled) == [(f"the lantern's flame, {words}", number)]
    assert settled.roll.throw.against == "The lantern's flame stands in the way."


def test_a_trivial_thing_is_nothing_to_throw_for():
    for seed in SEEDS:
        settled = one(farm(), stamp(Challenge.TRIVIAL), seed)
        assert settled.outcome_class is OutcomeClass.CERTAIN
        assert settled.result is StepResult.SUCCESS and settled.roll is None
    assert settled.reason == (
        "An ordinary hand, 2 dice, against the lantern's flame, a trivial task, level 0: no "
        "throw, it can't stop you."
    )


def test_a_thing_nobody_judged_is_a_real_effort():
    settled = one(farm(), stamp(None))
    assert parts(settled) == [("the lantern's flame, a real effort, level 2", 17)]


@pytest.mark.parametrize(
    ("difficulty", "number"),
    [(Difficulty.STORY, 21), (Difficulty.BALANCED, 24), (Difficulty.BRUTAL, 27)],
)
def test_the_storys_difficulty_comes_off_the_level_and_nothing_else(difficulty, number):
    state = picker()
    state.player.sheet.condition.health = Health.WOUNDED
    settled = one(state, lock(Challenge.MODERATE, hindrances=["no light"]), difficulty=difficulty)
    assert settled.roll.throw.number == number + 3  # the level's ten less the ease, then 5 and 5
    assert [points for _, points in parts(settled)][1:] == [5, 5]
    assert settled.roll.difficulty is difficulty


def test_the_storys_difficulty_never_decides_whether_there_is_a_throw():
    state = picker(SkillLevel.EXPERT)
    for difficulty in Difficulty:
        sure = one(state, lock(Challenge.MODERATE), difficulty=difficulty)
        assert sure.outcome_class is OutcomeClass.CERTAIN and sure.roll is None, difficulty
        open_ = one(state, lock(Challenge.HARD), difficulty=difficulty)
        assert open_.roll is not None, difficulty


# --- the number: what moves it, in steps of 5 (A3, A8) ------------------------------------------


def test_wounds_exhaustion_and_a_dry_reserve_are_named_on_the_number():
    state = picker()
    condition = state.player.sheet.condition
    condition.health = Health.BADLY_WOUNDED
    condition.fatigue = 3
    condition.reserves.append(Reserve(name="qi", level=0))
    settled = one(state, lock())
    assert parts(settled) == [
        ("a good lock, a hard task, level 3", 27),
        ("you are badly wounded", 10),
        ("you are exhausted", 5),
        ("you are drained of qi", 5),
    ]
    assert settled.roll.throw.number == 47
    assert "you are badly wounded (+10); you are exhausted (+5)" in settled.reason


@pytest.mark.parametrize(
    ("health", "points"),
    [(Health.HURT, 0), (Health.WOUNDED, 5), (Health.BADLY_WOUNDED, 10)],
)
def test_each_wound_is_a_step_of_5(health, points):
    state = picker()
    state.player.sheet.condition.health = health
    assert one(state, lock()).roll.throw.number == 27 + points


def test_each_thing_in_the_scene_against_them_adds_5_two_at_most():
    against = ["no light", "numb fingers", "a rusted keyhole"]
    settled = one(picker(), lock(hindrances=against))
    assert parts(settled)[1:] == [("no light", 5), ("numb fingers", 5)]


def test_a_flaw_in_the_way_adds_5_and_a_gift_that_fits_takes_5_off():
    clumsy = gift(picker(), "butterfingers", TraitKind.FLAW)
    assert parts(one(clumsy, lock(Challenge.HARD, trait("butterfingers"))))[1:] == [
        ("your butterfingers", 5)
    ]
    deft = gift(picker(), "thief's touch")
    assert parts(one(deft, lock(Challenge.HARD, trait("thief's touch"))))[1:] == [
        ("your thief's touch", -5)
    ]


def test_a_trait_is_found_by_the_steps_own_words_and_a_named_one_wins():
    state = picker()
    state.player.sheet.traits.append(
        Trait(name="Locksmith's son", kind=TraitKind.GIFT, description="Grew up picking locks.")
    )
    assert parts(one(state, lock()))[1:] == [("your Locksmith's son", -5)]
    # The interpret step named the trait it uses, so the unnamed gift stays out of it.
    gift(state, "steady hands")
    assert parts(one(state, lock(Challenge.HARD, trait("steady hands"))))[1:] == [
        ("your steady hands", -5)
    ]


def test_a_trait_sharing_one_word_with_the_step_doesnt_count():
    state = picker()
    state.player.sheet.traits.append(
        Trait(name="Afraid of doors", kind=TraitKind.FLAW, description="Thresholds unsettle him.")
    )
    assert parts(one(state, lock()))[1:] == []


def test_a_body_clearly_better_or_worse_at_what_the_step_tests_moves_the_number():
    # The dice come from the skill, so the hands that hold the picks count on the number.
    deft = parts(one(picker(speed=5), lock(Challenge.HARD, attribute("dexterity"))))
    assert deft[1:] == [("your speed", -5)]
    clumsy = parts(one(picker(speed=1), lock(Challenge.HARD, attribute("dexterity"))))
    assert clumsy[1:] == [("your speed", 5)]
    average = parts(one(picker(), lock(Challenge.HARD, attribute("dexterity"))))
    assert average[1:] == []


def test_attributes_that_gave_the_dice_dont_count_again_on_the_number():
    leap = step(
        "leap the flooded ditch",
        ActionKind.MOVE,
        3,
        verb="leap",
        uses=[attribute("agility")],
        facts=StepFacts(means=MeansVerdict.CLOSE_CALL, challenge=Challenge.VERY_HARD),
    )
    settled = one(farm(speed=5), leap)
    assert settled.roll.throw.hand == 4
    assert parts(settled) == [("a very hard task, level 4", 37)]


def test_all_help_together_takes_at_most_10_off():
    state = gift(gift(picker(speed=6), "thief's touch"), "steady hands")
    named = lock(Challenge.HARD, attribute("dexterity"), trait("thief's touch"))
    settled = one(state, named)
    assert sum(points for _, points in parts(settled)[1:]) == -10
    assert settled.roll.throw.number == 17


# --- the number: whoever answers (A3, A8, G14) --------------------------------------------------


def rival(speed: int = 3, **sheet) -> Character:
    return Character(
        id="greta",
        name="Greta",
        age=30,
        location_id="farm",
        sheet=CharacterSheet(attributes=Attributes(speed=speed), **sheet),
    )


def grab(*uses: SheetUse, **kw) -> IntentStep:
    kw.setdefault("opposition_ids", ["greta"])
    kw.setdefault("can_respond", True)
    return step(
        "snatch the lantern before Greta can",
        ActionKind.INSTANT,
        2,
        verb="snatch",
        axis=PowerAxis.MIGHT,
        uses=list(uses),
        facts=StepFacts(**kw),
    )


def test_whoever_answers_sets_the_number_by_what_they_answer_with():
    quick = add(farm(), rival(speed=5))
    settled = one(quick, grab(answers_with="speed"))
    assert parts(settled) == [("Greta's speed, level 4", 37)]
    assert settled.roll.throw.against == "Greta can answer."

    trained = add(farm(), rival(skills=[Skill(name="Sleight of hand", level=SkillLevel.SKILLED)]))
    settled = one(trained, grab(answers_with="sleight of hand"))
    assert parts(settled) == [("Greta's sleight of hand (skilled), level 3", 27)]

    drilled = add(
        farm(),
        rival(techniques=[Technique(id="snatch", name="Magpie snatch", mastery=Mastery.OWN)]),
    )
    settled = one(drilled, grab(answers_with="magpie snatch"))
    assert parts(settled) == [("Greta's Magpie snatch (made their own), level 5", 47)]


def test_with_no_word_they_answer_with_the_skill_the_step_draws_on_or_the_axis():
    state = add(farm(), rival(skills=[Skill(name="Knife-fighting", level=SkillLevel.EXPERT)]))
    state.player.sheet.skills.append(Skill(name="Knife-fighting", level=SkillLevel.SKILLED))
    settled = one(state, grab(skill("knife-fighting")))
    assert settled.roll.throw.hand_why == "Knife-fighting (skilled), 3 dice"
    assert parts(settled) == [("Greta's knife-fighting (expert), level 4", 37)]
    # Nothing named: the attributes a step of might calls on.
    plain = one(add(farm(), rival(speed=5)), grab())
    assert parts(plain) == [("Greta's strength and speed, level 3", 27)]


def test_two_people_untrained_in_it_meet_on_what_their_bodies_give_them():
    state = add(farm(), rival())
    settled = one(state, grab(skill("knife-fighting")))
    assert settled.roll.throw.hand_why == "Knife-fighting (untrained), 1 die"
    assert parts(settled) == [("Greta's strength and speed, level 2", 17)]


def test_their_wounds_come_off_the_number_and_yours_go_on():
    state = add(farm(), rival())
    state.characters["greta"].sheet.condition.health = Health.WOUNDED
    state.player.sheet.condition.health = Health.BADLY_WOUNDED
    settled = one(state, grab(answers_with="speed"))
    assert parts(settled) == [
        ("Greta's speed, level 2", 17),
        ("Greta is wounded", -5),
        ("you are badly wounded", 10),
    ]


def test_each_extra_foe_near_the_strongest_adds_5_two_at_most():
    def crowd(*speeds: int) -> list[tuple[str, int]]:
        state = add(farm(), rival(speed=4))
        ids = ["greta"]
        for i, speed in enumerate(speeds):
            other = rival(speed=speed).model_copy(update={"id": f"hand{i}", "name": f"Hand {i}"})
            add(state, other)
            ids.append(other.id)
        return parts(one(state, grab(answers_with="speed", opposition_ids=ids)))

    assert crowd() == [("Greta's speed, level 3", 27)]
    assert crowd(3)[1:] == [("one more at their side", 5)]
    assert crowd(3, 4, 4)[1:] == [("two more at their side", 10)]
    # Someone two levels under the strongest is no help to them.
    assert crowd(1)[1:] == []


def test_two_levels_under_the_hand_they_cant_push_back_with_no_throw():
    state = add(picker(SkillLevel.EXPERT), rival())
    for seed in SEEDS:
        settled = one(state, grab(skill("lockpicking"), answers_with="speed"), seed)
        assert settled.outcome_class is OutcomeClass.CERTAIN
        assert settled.result is StepResult.SUCCESS and settled.roll is None
    assert settled.reason == (
        "Lockpicking (expert), 4 dice, against Greta's speed, level 2: no throw, Greta can't "
        "push back."
    )


def test_a_faction_in_the_way_is_never_nothing():
    state = picker(SkillLevel.MASTER)
    state.factions["watch"] = Faction(id="watch", name="the night watch")
    watched = lock(Challenge.TRIVIAL, opposition_ids=["watch"])
    watched.facts.opposition = "the night watch"
    settled = one(state, watched)
    assert settled.roll is not None and settled.outcome_class is OutcomeClass.CONTESTED
    assert parts(settled) == [("the night watch, an easy task, level 1", 7)]


def talk(verb: str = "persuade", **kw) -> IntentStep:
    kw.setdefault("opposition_ids", ["greta"])
    kw.setdefault("can_respond", True)
    kw.setdefault("answers_with", "willpower")
    return step(
        "talk Greta into lending the cart",
        ActionKind.CONVERSATION,
        60,
        verb=verb,
        axis=PowerAxis.INFLUENCE,
        target_ids=["greta"],
        facts=StepFacts(**kw),
    )


def listener(**attitude) -> WorldState:
    state = add(farm(), rival())
    state.characters["greta"].sheet.disposition.attitudes["tomas"] = Attitude(**attitude)
    return state


def test_how_the_listener_feels_moves_a_step_of_words():
    warm = parts(one(listener(affinity=60, trust=40), talk()))
    assert warm[1:] == [("Greta likes and trusts you", -5)]
    cold = parts(one(listener(affinity=-60, trust=-40), talk()))
    assert cold[1:] == [("Greta neither likes nor trusts you", 5)]
    assert parts(one(listener(), talk()))[1:] == []
    # A threat rests on fear, never on warmth.
    afraid = parts(one(listener(fear=50, affinity=80, trust=80), talk("threaten")))
    assert afraid[1:] == [("Greta fears you", -5)]


# --- whether there is anything to throw for (A2) ------------------------------------------------


def test_a_close_call_with_nothing_in_the_way_is_thrown_against_the_task():
    leap = step(
        "leap from the hayloft onto the cart",
        ActionKind.MOVE,
        3,
        verb="leap",
        uses=[attribute("agility")],
        facts=StepFacts(means=MeansVerdict.CLOSE_CALL, challenge=Challenge.HARD),
    )
    average = one(farm(), leap)
    assert parts(average) == [("a hard task, level 3", 27)]
    assert average.roll.throw.against == "A close call."
    # A tumbler's five dice leave no real doubt about a task two levels under them.
    tumbler = farm()
    tumbler.player.sheet.skills.append(Skill(name="acrobatics", level=SkillLevel.MASTER))
    sure = leap.model_copy(update={"uses": [skill("acrobatics")]})
    settled = one(tumbler, sure)
    assert settled.outcome_class is OutcomeClass.CERTAIN and settled.roll is None
    assert settled.reason == (
        "Acrobatics (master), 5 dice, against a hard task, level 3: no throw, there is no real "
        "doubt."
    )


def test_with_no_verdict_on_the_means_a_real_effort_or_harder_is_a_close_call():
    def reach(challenge: Challenge | None) -> IntentStep:
        return step(
            "reach the loft by the rope",
            ActionKind.MOVE,
            20,
            verb="climb",
            facts=StepFacts(challenge=challenge),
        )

    for challenge in (None, Challenge.TRIVIAL, Challenge.EASY):
        settled = one(farm(), reach(challenge))
        assert settled.outcome_class is OutcomeClass.CERTAIN and settled.roll is None, challenge
        assert settled.reason == "Nothing stands in the way."
    for challenge in (Challenge.MODERATE, Challenge.HARD):
        assert one(farm(), reach(challenge)).roll is not None, challenge


def test_a_step_a_throw_decides_is_a_long_shot_under_15_in_100():
    fair = one(picker(), lock(Challenge.HARD))
    assert fair.roll.odds == pytest.approx(0.2888) and fair.outcome_class is OutcomeClass.CONTESTED
    slim = one(picker(), lock(Challenge.VERY_HARD))
    assert slim.roll.odds == pytest.approx(0.075) and slim.outcome_class is OutcomeClass.LONG_SHOT
    assert slim.roll.odds_label == slim.roll.throw.line


def test_a_step_passes_at_the_chance_its_roll_records():
    state = picker(SkillLevel.SKILLED)
    results = [one(state, lock(), seed) for seed in MANY_SEEDS]
    (odds,) = {r.roll.odds for r in results}  # the chance comes from the facts, not the seed
    assert odds == pytest.approx(0.6877)
    rate = sum(r.result is StepResult.SUCCESS for r in results) / len(results)
    assert rate == pytest.approx(odds, abs=0.02)
    # So close is partly done, and only a miss by more than 5 fails.
    assert {r.result for r in results} == set(StepResult)
    for r in results:
        assert r.result is dice.result_of(r.roll.throw.mark, dice.ALL_RESULTS)


def test_a_throw_is_told_with_its_hand_its_number_and_its_mark():
    state = gift(picker(), "butterfingers", TraitKind.FLAW)
    settled = one(state, lock(Challenge.HARD, trait("butterfingers")))
    thrown = settled.roll.throw
    assert settled.reason == (
        "Lockpicking (fair), 2 dice, against a good lock, a hard task, level 3; your "
        f"butterfingers (+5): {thrown.total} against 32, {dice.MARK_WORDS[thrown.mark]}."
    )


# --- green dice: advantages that hold (A3) ------------------------------------------------------


def edge(text: str, source: EdgeSource, ref: str = "") -> Edge:
    return Edge(text=text, source=source, ref=ref)


def holds(state: WorldState, an_edge: Edge, a_step: IntentStep | None = None, **kw) -> bool:
    kw.setdefault("passed", frozenset())
    kw.setdefault("scene", "")
    return capability.holds(state, state.player, a_step or lock(), Drawn(), an_edge, **kw)


def test_an_advantage_from_an_earlier_step_holds_only_if_that_step_passed():
    first = edge("the door is already open", EdgeSource.STEP, "1")
    assert holds(farm(), first, passed={0})
    assert not holds(farm(), first, passed={1})
    assert not holds(farm(), first)
    assert holds(farm(), edge("oiled hinges", EdgeSource.STEP, "step 2"), passed={1})
    assert not holds(farm(), edge("oiled hinges", EdgeSource.STEP, "the last one"), passed={0})


def test_an_advantage_on_record_holds_only_if_the_record_does():
    state = farm()
    state.facts["spare-key"] = Fact(id="spare-key", text="The spare key hangs in the barn.")
    state.facts["rumour"] = Fact(id="rumour", text="The lock is broken.", is_true=False)
    give(state, "tomas", Item(id="picks", name="lockpicks", kind=ItemKind.GEAR))
    give(state, "tomas", Item(id="wax", name="wax", kind=ItemKind.CONSUMABLE, quantity=0))

    def record(ref: str, a_step: IntentStep | None = None) -> bool:
        return holds(state, edge("it helps", EdgeSource.RECORD, ref), a_step)

    assert record("spare-key") and not record("rumour")
    assert record("picks") and not record("wax")
    assert record("ilse")  # at his side in the doorway
    assert not record("bram")  # in the village
    assert not record("tomas")
    assert record("farm") and not record("village")
    assert not record("a lucky feeling")


def test_whoever_the_step_is_up_against_is_never_an_advantage():
    state = add(farm(), rival())
    with_her = edge("Greta is here", EdgeSource.RECORD, "greta")
    assert holds(state, with_her)
    assert not holds(state, with_her, grab())  # she is the one who answers


def test_an_advantage_from_the_scene_holds_only_if_its_words_are_there():
    state = farm()
    quoted = edge("the lantern lights the lock", EdgeSource.SCENE, "a lit lantern")
    assert holds(state, quoted)  # the scene's props hold it
    told = "Rain hammers the yard, and the dog has gone quiet."
    assert holds(
        state, edge("the rain covers the noise", EdgeSource.SCENE, "rain hammers"), scene=told
    )
    assert not holds(state, edge("the watch is drunk", EdgeSource.SCENE, "the drunk watchman"))
    assert not holds(state, edge("the watch is drunk", EdgeSource.SCENE), scene=told)


def test_each_advantage_that_holds_adds_a_green_die_two_at_most():
    state = farm()
    state.facts["spare-key"] = Fact(id="spare-key", text="The spare key hangs in the barn.")
    edges = [
        edge("the lantern lights the lock", EdgeSource.SCENE, "a lit lantern"),
        edge("the watch is drunk", EdgeSource.SCENE, "the drunk watchman"),  # doesn't hold
        edge("the lantern lights the lock", EdgeSource.SCENE, "lit lantern"),  # said twice
        edge("he knows where the spare key is", EdgeSource.RECORD, "spare-key"),
        edge("Ilse keeps watch", EdgeSource.RECORD, "ilse"),
    ]
    picked = picker()
    picked.facts.update(state.facts)
    settled = one(picked, lock(Challenge.VERY_HARD, edges=edges))
    thrown = settled.roll.throw
    assert thrown.greens == ["the lantern lights the lock", "he knows where the spare key is"]
    assert thrown.hand == 4 and thrown.most == 80
    held = [die.kind for die in thrown.dice if not die.sprung]
    assert held == [DieKind.PLAIN, DieKind.PLAIN, DieKind.GREEN, DieKind.GREEN]
    assert (
        "Lockpicking (fair), 2 dice, and a green die for the lantern lights the lock, and a "
        "green die for he knows where the spare key is, against a good lock" in settled.reason
    )
    # The chance on the record counts them.
    assert settled.roll.odds == pytest.approx(dice.chance(dice.Hand(2), 2, 37), abs=0.0001)


def test_an_advantage_that_doesnt_hold_gives_no_die():
    lied = [edge("the watch is drunk", EdgeSource.SCENE, "the drunk watchman")]
    settled = one(picker(), lock(Challenge.VERY_HARD, edges=lied))
    assert settled.roll.throw.greens == [] and settled.roll.throw.hand == 2
    assert settled.roll.odds == one(picker(), lock(Challenge.VERY_HARD)).roll.odds


def test_an_earlier_step_of_the_plan_that_passed_gives_the_next_one_a_green_die():
    state = picker(SkillLevel.MASTER)
    oil = step("oil the hinges", ActionKind.TASK, 30, verb="oil")
    after = lock(
        Challenge.VERY_HARD,
        edges=[edge("the hinges are oiled", EdgeSource.STEP, "1")],
    )
    resolution = resolve(state, plan(oil, after))
    assert resolution.steps[1].roll.throw.greens == ["the hinges are oiled"]
    # Named as the first step of a plan, it rests on nothing.
    alone = resolve(state, plan(after)).steps[0]
    assert alone.roll.throw.greens == []


# --- what a place remembers a judged thing by -------------------------------------------------


def test_a_judged_thing_is_found_again_by_the_same_words_only():
    again = lock().model_copy(update={"text": "try the granary lock once more"})
    assert capability.thing_key(lock()) == capability.thing_key(again)
    other = lock()
    other.facts.opposition = "the cellar padlock"
    assert capability.thing_key(other) != capability.thing_key(lock())
    unnamed = step("climb the old oak", verb="climb")
    assert capability.thing_key(unnamed) == capability.thing_key(
        step("climb the old oak", verb="climbing")
    )


# --- the defence hand (N6) ----------------------------------------------------------------------


def test_the_defence_is_thrown_with_the_skill_the_step_drew_on_or_their_speed():
    state = farm(speed=4)
    lin = state.player
    swing = step("swing the hoe at the wolf", verb="swing")
    assert capability.defence_hand(state, lin, swing, Drawn()) == dice.Hand(3, "Speed, 3 dice")
    lin.sheet.skills.append(Skill(name="Staff fighting", level=SkillLevel.EXPERT))
    drawn = Drawn(skills=["staff fighting"])
    assert capability.defence_hand(state, lin, swing, drawn) == dice.Hand(
        4, "Staff fighting (expert), 4 dice"
    )
    lin.sheet.skills[-1].level = SkillLevel.FAIR  # his speed serves him better
    assert capability.defence_hand(state, lin, swing, drawn).why == "Speed, 3 dice"


# --- a plan that goes around the strength (A9) --------------------------------------------------


def _guard(level: SkillLevel | None) -> WorldState:
    state = shielded_mage()
    if level is not None:
        state.characters["su-yan"].sheet.skills.append(Skill(name="Perception", level=level))
    return state


def _sneak(**kw) -> Intent:
    aware = facts(opposition_ids=["su-yan"], can_respond=True, answers_with="perception", **kw)
    return Intent(steps=[burn_the_hall(facts=aware)])


def test_a_chain_setup_is_thrown_against_whoever_can_see_it_coming_with_no_rungs():
    # Su Yan stands three realms above Lin, and the plan goes around her power.
    novice = resolve(_guard(SkillLevel.NOVICE), _sneak()).steps[0]
    assert parts(novice) == [("Su Yan's perception (novice), level 1", 7)]
    master = resolve(_guard(SkillLevel.MASTER), _sneak()).steps[0]
    assert parts(master) == [("Su Yan's perception (master), level 5", 47)]
    assert master.roll.odds < novice.roll.odds
    assert master.roll.allowed == dice.YES_OR_NO
    assert master.roll.throw.against == "Su Yan may see it coming."


def test_a_chain_setup_that_misses_is_seen_coming():
    state = _guard(SkillLevel.MASTER)
    missed = next(
        s
        for s in (resolve(state, _sneak(), seed).steps[0] for seed in SEEDS)
        if s.result is StepResult.FAILURE
    )
    assert missed.reason.startswith("Su Yan sees it coming in time. An ordinary hand, 2 dice, ")
    # No link of the chain plays, and nothing happens to her.
    assert missed.chain == []
    assert [change.id for change in besides_rank(missed)] in ([], ["lin"])
