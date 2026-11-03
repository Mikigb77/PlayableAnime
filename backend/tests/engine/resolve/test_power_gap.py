"""T17 "Power gap" and "Fair long shots" (A2, A3, A5, A8, G18, G25).

A Qi Condensation disciple attacking a Core Formation elder head-on fails almost every time and the
elder reacts to the insult. Against a gravely wounded elder the same attack can succeed. Using time
stop, the result is the same on every seed, with no roll. A long-shot plan succeeds at roughly its
stated odds over many seeds."""

import pytest

from engine.context import Difficulty
from engine.contracts import Intent, OutcomeClass, SheetPart, SheetUse
from engine.resolve import odds as odds_mod
from engine.rng import SeededRng
from engine.state import CharacterStatus, Health, StepResult

from .worlds import (
    MANY_SEEDS,
    SEEDS,
    add,
    disciple,
    facts,
    resolve,
    sect,
    stop_time,
    strike,
    wounded,
)


def test_a_head_on_attack_two_realms_up_is_ruled_out_on_every_seed():
    state = sect()
    intent = Intent(steps=[strike("elder-mo")])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert settled.outcome_class is OutcomeClass.RULED_OUT
        assert settled.result is StepResult.FAILURE
        assert settled.roll is None
        assert settled.effects.empty
    # The reason is in the world's words, and the attempt is a deed the elder answers (A8, W1).
    assert settled.reason == (
        "Elder Mo at Core Formation against you at Qi Condensation: head-on, there is no contest."
    )
    (deed,) = settled.deeds
    assert deed.target_ids == ["elder-mo"] and deed.victim_ids == []
    assert deed.severity >= 3


def test_against_a_gravely_wounded_elder_the_same_attack_is_a_long_shot_that_can_land():
    state = wounded(sect(), "elder-mo", Health.BADLY_WOUNDED)
    intent = Intent(steps=[strike("elder-mo")])

    results = [resolve(state, intent, seed).steps[0] for seed in range(2000)]

    assert {r.outcome_class for r in results} == {OutcomeClass.LONG_SHOT}
    assert "badly wounded" in results[0].reason
    wins = [r for r in results if r.result is StepResult.SUCCESS]
    assert 0 < len(wins) < 0.2 * len(results)
    assert all(c.status is CharacterStatus.DEAD for w in wins for c in w.effects.characters)
    assert all(r.roll is not None for r in results)


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
    assert "can't push back" in settled.reason


def test_one_realm_up_is_a_long_shot_at_best():
    state = sect()  # Zhao Kun stands at Foundation Establishment, one realm above Lin.
    (settled,) = resolve(state, Intent(steps=[strike("zhao")])).steps

    assert settled.outcome_class is OutcomeClass.LONG_SHOT
    low, high = odds_mod.LONG_SHOT_BAND
    assert low <= settled.roll.odds <= high
    assert settled.reason.startswith(
        "Zhao Kun at Foundation Establishment against you at Qi Condensation: a long shot"
    )


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_long_shot_succeeds_at_its_stated_odds(difficulty):
    state = sect()
    intent = Intent(steps=[strike("zhao")])

    results = [resolve(state, intent, seed, difficulty).steps[0] for seed in MANY_SEEDS]

    stated = {r.roll.odds for r in results}
    assert len(stated) == 1  # the odds come from the facts, not the seed
    (odds,) = stated
    rate = sum(r.result is StepResult.SUCCESS for r in results) / len(results)
    assert rate == pytest.approx(odds, abs=0.02)
    assert {r.outcome_class for r in results} == {OutcomeClass.LONG_SHOT}


def test_difficulty_shifts_the_odds_of_rolled_steps_and_never_their_class():
    state = sect()
    intent = Intent(steps=[strike("zhao")])

    by_difficulty = {d: resolve(state, intent, 0, d).steps[0] for d in Difficulty}

    story, balanced, brutal = (
        by_difficulty[d].roll.odds
        for d in (Difficulty.STORY, Difficulty.BALANCED, Difficulty.BRUTAL)
    )
    assert story > balanced > brutal
    assert {s.outcome_class for s in by_difficulty.values()} == {OutcomeClass.LONG_SHOT}
    assert all(s.roll.difficulty is d for d, s in by_difficulty.items())


def test_a_clever_approach_shifts_a_long_shot_only_within_its_bounds():
    state = sect()
    plain = resolve(state, Intent(steps=[strike("zhao")])).steps[0]
    clever = resolve(
        state,
        Intent(
            steps=[
                strike(
                    "zhao",
                    facts=facts(
                        opposition_ids=["zhao"],
                        can_respond=True,
                        edges=["he is off balance", "sun in his eyes", "wet stones", "taunted"],
                    ),
                )
            ]
        ),
    ).steps[0]

    assert clever.roll.odds > plain.roll.odds
    assert clever.roll.odds == odds_mod.LONG_SHOT_BAND[1]
    assert clever.outcome_class is OutcomeClass.LONG_SHOT


def test_evenly_matched_fighters_roll_at_even_odds_and_skill_tilts_them():
    state = add(sect(), disciple("wei", "Wei Ming"))
    even = resolve(state, Intent(steps=[strike("wei")])).steps[0]
    state.characters["lin"].sheet.skills.append(
        state.characters["zhao"].sheet.skills[0].model_copy(update={"name": "swordsmanship"})
    )
    skilled_step = strike("wei")
    skilled_step.uses.append(SheetUse(part=SheetPart.SKILL, ref="swordsmanship"))
    skilled = resolve(state, Intent(steps=[skilled_step])).steps[0]

    assert even.outcome_class is OutcomeClass.CONTESTED
    assert even.roll.odds == pytest.approx(0.5)
    assert even.reason == "Wei Ming at Qi Condensation against you at Qi Condensation: even odds."
    assert skilled.roll.odds > even.roll.odds


def test_numbers_count_against_you():
    state = add(sect(), disciple("wei", "Wei Ming"), disciple("bo", "Bo Han"))
    one = resolve(state, Intent(steps=[strike("wei")])).steps[0]
    two = strike("wei")
    two.target_ids.append("bo")
    two.facts.opposition_ids.append("bo")
    both = resolve(state, Intent(steps=[two])).steps[0]

    assert both.roll.odds < one.roll.odds
    assert "with others at their side" in both.reason


def test_every_roll_replays_from_its_seed():
    state = sect()
    (settled,) = resolve(state, Intent(steps=[strike("zhao")]), 17).steps

    assert SeededRng(settled.roll.seed).random() == settled.roll.value
    assert resolve(state, Intent(steps=[strike("zhao")]), 17) == resolve(
        state, Intent(steps=[strike("zhao")]), 17
    )
