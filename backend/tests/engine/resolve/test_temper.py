"""G15: disposition shapes the character but never takes control from the player.

A step that only the character's own temperament, fear or pride stands in the way of is the
player's choice, so it happens. A hot temper makes keeping calm harder, and the roll decides only
how hard it was: done cleanly, or done with the strain showing. It never fails, and a plan carries
on past it (R6).
"""

import pytest

from engine.contracts import (
    ActionKind,
    Aim,
    Intent,
    MeansVerdict,
    OutcomeClass,
    SheetPart,
    SheetUse,
)
from engine.samples import cultivation_world
from engine.state import StepResult, Trait, TraitKind
from tests.engine.resolve.worlds import MANY_SEEDS, SEEDS, facts, resolve, step


def hot_headed():
    state = cultivation_world()
    lin = state.characters["lin"]
    lin.sheet.traits.append(
        Trait(name="hot temper", kind=TraitKind.FLAW, description="Flares at any insult.")
    )
    lin.sheet.disposition.temperament.traits.append("hot-headed")
    return state


def keep_calm(temper: bool = True, **fact_kw):
    fact_kw.setdefault("opposition", "Lin's own pride")
    fact_kw.setdefault("proposed_class", OutcomeClass.CONTESTED)
    return step(
        "keep my temper, bow and walk away",
        ActionKind.EXCHANGE,
        10,
        verb="keep calm",
        uses=[SheetUse(part=SheetPart.TRAIT, ref="hot temper")] if temper else [],
        facts=facts(**fact_kw),
    )


def plan(*steps):
    return Intent(steps=list(steps))


def test_keeping_calm_is_never_lost_outright_and_a_temper_makes_it_harder():
    results = {True: set(), False: set()}
    odds = {}
    for temper in (True, False):
        state = hot_headed() if temper else cultivation_world()
        for seed in MANY_SEEDS:
            settled = resolve(state, plan(keep_calm(temper)), seed).steps[0]
            assert settled.result is not StepResult.FAILURE, (temper, seed, settled.reason)
            assert settled.effects.empty and not settled.deeds
            assert settled.roll is not None and StepResult.FAILURE not in settled.roll.allowed
            results[temper].add(settled.result)
            odds[temper] = settled.roll.odds
    assert results[True] == results[False] == {StepResult.SUCCESS, StepResult.PARTIAL}
    assert odds[True] < odds[False]


def test_the_reason_says_the_choice_is_the_players_and_how_hard_it_was():
    state = hot_headed()
    seen = {}
    for seed in SEEDS:
        settled = resolve(state, plan(keep_calm()), seed).steps[0]
        seen[settled.result] = settled.reason
    assert seen[StepResult.SUCCESS].startswith("Lin's own pride pushes back, but the choice is")
    assert "yours" in seen[StepResult.SUCCESS] and seen[StepResult.SUCCESS].endswith("you do it.")
    assert seen[StepResult.PARTIAL].endswith("you do it, but the strain shows.")


@pytest.mark.parametrize(
    "fact_kw",
    [
        {"opposition": "", "inner": True},  # the interpret step says so
        {"opposition": "his own temper"},  # or describes it, with no flag
        {"opposition": "Lin Feng's own fear"},
        {"opposition": "his temper and his pride"},
        {"opposition": "fear"},
        {"opposition": "", "opposition_ids": ["lin"]},  # or names the actor
    ],
)
def test_the_inner_step_is_recognised_from_the_flag_the_words_or_the_actor(fact_kw):
    state = hot_headed()
    for seed in SEEDS:
        settled = resolve(state, plan(keep_calm(**fact_kw)), seed).steps[0]
        assert settled.result is not StepResult.FAILURE, (fact_kw, seed, settled.reason)


@pytest.mark.parametrize(
    "fact_kw",
    [
        {"opposition": "the storm and his own fear"},  # something else pushes back too
        {"opposition": "your own men's panic"},  # other people
        {"opposition": "the sect's own law"},
        {"opposition": "Zhao's sneer and his own pride"},  # someone else is in the words
        {"opposition": "his own temper", "opposition_ids": ["outer-court"]},  # a faction
        {"opposition": "the storm and his own fear", "inner": True},  # words outweigh the flag
        {"opposition": "the cliff", "opposition_ids": ["lin"]},
        {"opposition": "his own fear", "means": MeansVerdict.CLEARLY_NOT},  # body not up to it
    ],
)
def test_anything_else_pushing_back_can_still_beat_the_step(fact_kw):
    state = hot_headed()
    results = {resolve(state, plan(keep_calm(**fact_kw)), s).steps[0].result for s in SEEDS}
    assert StepResult.FAILURE in results, fact_kw


def test_someone_in_the_way_or_harm_aimed_at_someone_is_never_inner():
    state = hot_headed()
    stare_down = keep_calm(inner=True, opposition_ids=["zhao"], can_respond=True)
    results = {resolve(state, plan(stare_down), s).steps[0].result for s in SEEDS}
    assert StepResult.FAILURE in results
    lash_out = keep_calm(inner=True).model_copy(update={"aim": Aim.WOUND, "target_ids": ["zhao"]})
    settled = resolve(state, plan(lash_out), 0).steps[0]
    assert "the choice is" not in settled.reason


def test_an_easy_inner_step_is_certain_and_a_hard_one_is_never_ruled_out():
    state = hot_headed()
    for easy_kw in (
        {"proposed_class": OutcomeClass.CERTAIN},
        {"proposed_class": None, "means": MeansVerdict.CLEARLY_ENOUGH},
    ):
        easy = resolve(state, plan(keep_calm(**easy_kw)), 0).steps[0]
        assert easy.outcome_class is OutcomeClass.CERTAIN and easy.roll is None
        assert easy.result is StepResult.SUCCESS
    for proposed in (OutcomeClass.RULED_OUT, OutcomeClass.LONG_SHOT):
        for seed in SEEDS:
            settled = resolve(state, plan(keep_calm(proposed_class=proposed)), seed).steps[0]
            assert settled.outcome_class is OutcomeClass.LONG_SHOT, proposed
            assert settled.result is not StepResult.FAILURE
            assert "very hard" in settled.reason


def test_a_plan_carries_on_past_a_temper_held_in_with_strain():
    """R6 stops a plan at a step that doesn't cleanly succeed, but here the step was done: the
    temper never takes the rest of the plan from the player."""
    state = hot_headed()
    bow = step("bow to Zhao", ActionKind.INSTANT, 2, verb="bow")
    walk = step("walk away", ActionKind.MOVE, 30, verb="walk")
    strained = 0
    for seed in SEEDS:
        resolution = resolve(state, plan(keep_calm(), bow, walk), seed)
        strained += resolution.steps[0].result is StepResult.PARTIAL
        assert len(resolution.steps) == 3 and resolution.stopped_at_step is None, seed
    assert strained
