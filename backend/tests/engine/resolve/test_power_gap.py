"""T17 "Power gap" and "Fair long shots" (A2, A3, A5, A8, G18, G25).

A gap in power never refuses a step: each rung someone stands above the character adds to the
number where the step meets that power head-on, so a Qi Condensation disciple attacking a Core
Formation elder almost always misses, and can still land it. Against a gravely wounded elder the
same attack is a fair throw. Using time stop, the result is the same on every seed, with no roll.
The one thing a gap rules out is what the world's ladder states: harm from that many rungs below
can't get through by ordinary means."""

import pytest

from engine.context import Difficulty
from engine.contracts import Edge, EdgeSource, Intent, OutcomeClass, SheetPart, SheetUse
from engine.resolve import resolve_intent
from engine.resolve import throw as dice
from engine.rng import SeededRng
from engine.state import (
    CharacterStatus,
    Health,
    Mastery,
    PowerAxis,
    Skill,
    SkillLevel,
    StepResult,
    Technique,
)

from .worlds import (
    MANY_SEEDS,
    SEEDS,
    add,
    ctx,
    disciple,
    facts,
    resolve,
    rng,
    sect,
    shielded_mage,
    step,
    stop_time,
    strike,
    wounded,
)

ONE_UP = "one rung above you, Foundation Establishment over Qi Condensation, met head-on"


def parts(settled) -> list[tuple[str, int]]:
    return [(part.text, part.points) for part in settled.roll.throw.made_of]


def test_a_head_on_attack_two_realms_up_is_still_a_throw_and_almost_always_misses():
    state = sect()
    intent = Intent(steps=[strike("elder-mo")])

    results = [resolve(state, intent, seed).steps[0] for seed in range(2000)]

    assert all(r.roll is not None for r in results)
    assert {r.outcome_class for r in results} == {OutcomeClass.LONG_SHOT}
    settled = results[0]
    assert parts(settled) == [
        ("Elder Mo's strength and speed, level 2", 17),
        ("two rungs above you, Core Formation over Qi Condensation, met head-on", 20),
    ]
    assert settled.roll.odds == pytest.approx(0.075)
    wins = [r for r in results if r.result is StepResult.SUCCESS]
    assert 0 < len(wins) < 0.12 * len(results)
    assert all(c.status is CharacterStatus.DEAD for w in wins for c in w.effects.characters)
    # The reason is in the world's words, and the attempt is a deed the elder answers (A8, W1).
    missed = next(r for r in results if r.result is StepResult.FAILURE)
    thrown = missed.roll.throw
    assert missed.reason == (
        "Strength and speed, 2 dice, against Elder Mo's strength and speed, level 2; two rungs "
        "above you, Core Formation over Qi Condensation, met head-on (+20): "
        f"{thrown.total} against 37, missed."
    )
    assert missed.effects.empty
    (deed,) = missed.deeds
    assert deed.target_ids == ["elder-mo"] and deed.victim_ids == []
    assert deed.severity >= 3


def test_against_a_gravely_wounded_elder_the_same_attack_is_a_fair_throw():
    state = wounded(sect(), "elder-mo", Health.BADLY_WOUNDED)
    intent = Intent(steps=[strike("elder-mo")])

    results = [resolve(state, intent, seed).steps[0] for seed in range(2000)]

    assert {r.outcome_class for r in results} == {OutcomeClass.CONTESTED}
    assert parts(results[0])[-1] == ("Elder Mo is badly wounded", -10)
    assert results[0].roll.throw.number == 27
    assert "Elder Mo is badly wounded (-10)" in results[0].reason
    wins = [r for r in results if r.result is StepResult.SUCCESS]
    assert 0.2 * len(results) < len(wins) < 0.4 * len(results)
    assert all(c.status is CharacterStatus.DEAD for w in wins for c in w.effects.characters)


def test_with_time_stop_the_attack_ends_the_same_on_every_seed_with_no_roll():
    state = sect()
    intent = Intent(steps=[stop_time(), strike("elder-mo", proposed_personal_s=2)])

    outcomes = {
        (s.outcome_class, s.result, s.roll is None, s.reason)
        for seed in SEEDS
        for s in resolve(state, intent, seed).steps[1:]
    }

    assert len(outcomes) == 1
    ((outcome_class, result, no_roll, reason),) = outcomes
    assert no_roll and outcome_class is not OutcomeClass.CONTESTED
    assert "frozen in stopped time" in reason


def test_two_realms_down_the_stronger_side_wins_with_no_roll():
    state = sect()
    # Elder Mo swats the disciple: the disciple can respond but can't push back.
    intent = Intent(actor_id="elder-mo", steps=[strike("lin")])
    intent.steps[0].uses.clear()

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
        )
        assert settled.roll is None
    assert settled.reason == (
        "Strength and speed, 2 dice, against your strength and speed, level 2; two rungs below "
        "Elder Mo, Qi Condensation under Core Formation, met head-on (-20): no throw, you can't "
        "push back."
    )


def test_one_realm_up_adds_one_level_to_the_number():
    state = sect()  # Zhao Kun stands at Foundation Establishment, one realm above Lin.
    (settled,) = resolve(state, Intent(steps=[strike("zhao")])).steps

    assert parts(settled) == [
        ("Zhao Kun's strength and speed, level 3", 27),
        (ONE_UP, 10),
    ]
    assert settled.outcome_class is OutcomeClass.LONG_SHOT
    assert settled.roll.throw.against == "Zhao Kun can answer."


def test_a_world_can_say_a_rung_counts_for_two_levels():
    state = sect()
    state.bible.ladders[0].rung_levels = 2
    (settled,) = resolve(state, Intent(steps=[strike("zhao")])).steps
    assert parts(settled)[1] == (ONE_UP, 20)
    assert settled.roll.throw.number == 47


def test_they_answer_with_what_the_interpret_step_names_from_their_sheet():
    state = sect()
    named = strike("zhao", facts=facts(opposition_ids=["zhao"], answers_with="fist techniques"))
    (settled,) = resolve(state, Intent(steps=[named])).steps
    assert parts(settled)[0] == ("Zhao Kun's fist techniques (skilled), level 3", 27)


def wrestle(head_on: bool | None, **kw):
    return step(
        "take the bucket back from Zhao",
        verb="take",
        axis=PowerAxis.MIGHT,
        facts=facts(opposition_ids=["zhao"], can_respond=True, head_on=head_on),
        **kw,
    )


def test_a_step_that_goes_around_their_power_counts_no_rungs():
    state = sect()
    met = resolve(state, Intent(steps=[wrestle(True)])).steps[0]
    assert parts(met)[1:] == [(ONE_UP, 10)]
    around = resolve(state, Intent(steps=[wrestle(False)])).steps[0]
    assert parts(around) == [("Zhao Kun's strength and speed, level 3", 27)]
    # With no word either way, a step measured on an axis meets it.
    assert parts(resolve(state, Intent(steps=[wrestle(None)])).steps[0]) == parts(met)


def test_a_blow_always_meets_the_body_whatever_was_proposed():
    state = sect()
    feint = strike("zhao", facts=facts(opposition_ids=["zhao"], can_respond=True, head_on=False))
    (settled,) = resolve(state, Intent(steps=[feint])).steps
    assert parts(settled)[1:] == [(ONE_UP, 10)]


# --- what a rung shrugs off (G18) ---------------------------------------------------------------


def test_harm_from_three_rungs_below_cant_get_through_by_ordinary_means():
    state = shielded_mage()  # Su Yan at Nascent Soul, three realms above Lin.
    intent = Intent(steps=[strike("su-yan")])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
        )
        assert settled.roll is None
        # Nothing happens to her; what she does about it is her own blow (N6).
        assert all(change.id != "su-yan" for change in settled.effects.characters)
    assert settled.reason == (
        "Su Yan at Nascent Soul stands three rungs above you, and harm from that far below "
        "can't get through by ordinary means."
    )


def test_a_weapon_with_a_history_or_a_move_of_their_own_is_no_ordinary_means():
    blade = shielded_mage()
    blade.player.sheet.item("sword").history = "Forged to cut what no blade should."
    (settled,) = resolve(blade, Intent(steps=[strike("su-yan")])).steps
    assert settled.roll is not None
    assert parts(settled)[1] == (
        "three rungs above you, Nascent Soul over Qi Condensation, met head-on",
        30,
    )

    trained = shielded_mage()
    trained.player.sheet.techniques.append(
        Technique(id="severing", name="Severing cut", mastery=Mastery.SKILLED)
    )
    cut = strike("su-yan")
    cut.uses.append(SheetUse(part=SheetPart.TECHNIQUE, ref="severing cut"))
    (settled,) = resolve(trained, Intent(steps=[cut])).steps
    assert settled.roll is not None
    assert settled.roll.throw.hand_why == "Severing cut (skilled), 3 dice"


def test_each_ladder_states_what_its_rungs_shrug_off():
    state = sect()
    state.bible.ladders[0].shrugs_off = 2
    (settled,) = resolve(state, Intent(steps=[strike("elder-mo")])).steps
    assert settled.outcome_class is OutcomeClass.RULED_OUT and settled.roll is None
    assert settled.reason.startswith("Elder Mo at Core Formation stands two rungs above you, ")


# --- fair throws (A3, A5) -----------------------------------------------------------------------


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_throw_passes_at_its_stated_chance(difficulty):
    state = sect()
    intent = Intent(steps=[strike("zhao")])

    results = [resolve(state, intent, seed, difficulty).steps[0] for seed in MANY_SEEDS]

    stated = {r.roll.odds for r in results}
    assert len(stated) == 1  # the chance comes from the facts, not the seed
    (odds,) = stated
    rate = sum(r.result is StepResult.SUCCESS for r in results) / len(results)
    assert rate == pytest.approx(odds, abs=0.02)
    assert {r.outcome_class for r in results} == {dice.class_of(odds)}


def test_the_difficulty_comes_off_the_number_of_every_throw():
    state = sect()
    intent = Intent(steps=[strike("zhao")])

    by_difficulty = {d: resolve(state, intent, 0, d).steps[0] for d in Difficulty}

    story, balanced, brutal = (
        by_difficulty[d].roll for d in (Difficulty.STORY, Difficulty.BALANCED, Difficulty.BRUTAL)
    )
    assert (story.throw.number, balanced.throw.number, brutal.throw.number) == (34, 37, 40)
    assert story.odds > balanced.odds > brutal.odds
    assert all(s.roll.difficulty is d for d, s in by_difficulty.items())
    # The same seed throws the same dice whatever the difficulty.
    assert story.throw.dice == balanced.throw.dice == brutal.throw.dice


def test_a_clever_approach_adds_a_die_only_where_the_scene_shows_it():
    state = sect()
    plain = resolve(state, Intent(steps=[strike("zhao")])).steps[0]
    edges = [
        Edge(text="he is off balance", source=EdgeSource.SCENE, ref="draws back his foot"),
        Edge(text="the sun is in his eyes", source=EdgeSource.SCENE, ref="the low sun"),
        Edge(text="wet stones", source=EdgeSource.SCENE, ref="wet stones underfoot"),
    ]
    clever_step = strike(
        "zhao", facts=facts(opposition_ids=["zhao"], can_respond=True, edges=edges)
    )
    clever = resolve(state, Intent(steps=[clever_step])).steps[0]

    assert clever.roll.throw.greens == ["he is off balance"]
    assert clever.roll.throw.hand == plain.roll.throw.hand + 1
    assert clever.roll.throw.number == plain.roll.throw.number
    assert clever.roll.odds > plain.roll.odds
    # No band holds a throw down: what the dice can reach decides its class.
    assert clever.outcome_class is dice.class_of(clever.roll.odds) is OutcomeClass.CONTESTED


def test_what_the_last_scene_told_can_be_quoted_for_an_advantage():
    state = sect()
    told = "The low sun stands behind Lin, straight in Zhao's eyes."
    edges = [Edge(text="the sun is in his eyes", source=EdgeSource.SCENE, ref="the low sun")]
    blinded = strike("zhao", facts=facts(opposition_ids=["zhao"], can_respond=True, edges=edges))
    (settled,) = resolve_intent(state, Intent(steps=[blinded]), ctx(), rng(), scene=told).steps
    assert settled.roll.throw.greens == ["the sun is in his eyes"]


def test_evenly_matched_fighters_throw_at_their_own_level_and_skill_adds_dice():
    state = add(sect(), disciple("wei", "Wei Ming"))
    even = resolve(state, Intent(steps=[strike("wei")])).steps[0]
    state.characters["lin"].sheet.skills.append(
        Skill(name="swordsmanship", level=SkillLevel.SKILLED)
    )
    skilled_step = strike("wei")
    skilled_step.uses.append(SheetUse(part=SheetPart.SKILL, ref="swordsmanship"))
    skilled = resolve(state, Intent(steps=[skilled_step])).steps[0]

    assert even.outcome_class is OutcomeClass.CONTESTED
    assert parts(even) == [("Wei Ming's strength and speed, level 2", 17)]
    assert even.roll.odds == pytest.approx(0.70)
    assert skilled.roll.throw.hand_why == "Swordsmanship (skilled), 3 dice"
    assert skilled.roll.odds == pytest.approx(0.93)


def test_numbers_count_against_you():
    state = add(sect(), disciple("wei", "Wei Ming"), disciple("bo", "Bo Han"))
    one = resolve(state, Intent(steps=[strike("wei")])).steps[0]
    two = strike("wei")
    two.target_ids.append("bo")
    two.facts.opposition_ids.append("bo")
    both = resolve(state, Intent(steps=[two])).steps[0]

    assert both.roll.odds < one.roll.odds
    assert parts(both)[1:] == [("one more at their side", 5)]
    assert both.roll.throw.against == "Wei Ming and Bo Han can answer."


def test_every_throw_replays_from_its_seed():
    state = sect()
    (settled,) = resolve(state, Intent(steps=[strike("zhao")]), 17).steps

    stream = SeededRng(settled.roll.seed)
    thrown = settled.roll.throw
    assert [die.face for die in thrown.dice] == [stream.randint(1, 20) for _ in thrown.dice]
    assert thrown.total == sum(die.value for die in thrown.dice)
    assert resolve(state, Intent(steps=[strike("zhao")]), 17) == resolve(
        state, Intent(steps=[strike("zhao")]), 17
    )
