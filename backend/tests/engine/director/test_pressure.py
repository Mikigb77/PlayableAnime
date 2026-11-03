"""W16, E6: stall pressure in code, its thresholds and its drift."""

import pytest

from engine import pipeline
from engine.base import DAY
from engine.context import EventFrequency
from engine.director import rules
from engine.director.pressure import (
    Pressure,
    action_key,
    clock_pressure,
    measure,
    next_drift,
    threshold,
)
from engine.director.turn import read_turn
from engine.samples import farm_world, grounded_world
from engine.state import Clock, ClockStatus, Encounter, EncounterKind
from tests.engine.director.helpers import ctx, farming, fence, play_turn, rng


def pressure_after(state, intent, turn: int = 3, stakes: bool = False, **settings) -> Pressure:
    context = ctx(turn, **settings)
    resolution = pipeline.resolve(state, intent, context, rng(turn=turn))
    if stakes:
        resolution = resolution.model_copy(update={"stakes": True})
    facts = read_turn(state, resolution, context, intent)
    return measure(state, resolution, context, intent, facts)


@pytest.mark.parametrize(
    ("frequency", "turns"),
    [(EventFrequency.CALM, 10), (EventFrequency.NORMAL, 5), (EventFrequency.DRAMATIC, 3)],
)
def test_the_starting_thresholds_are_ten_five_and_three_turns(frequency, turns):
    assert threshold(frequency, 0.0) == turns


def test_drift_moves_the_threshold_a_little_and_never_past_its_band():
    for frequency, base in rules.THRESHOLDS.items():
        assert threshold(frequency, 1.0) == pytest.approx(base * (1 - rules.DRIFT_SPAN))
        assert threshold(frequency, -1.0) == pytest.approx(base * (1 + rules.DRIFT_SPAN))
    drift = 0.0
    for _ in range(100):
        drift = next_drift(drift, big=False, comfortable=True)
    assert drift == 1.0  # rising while in control, capped
    assert next_drift(1.0, big=True, comfortable=True) == pytest.approx(0.4)  # a big event
    assert next_drift(-0.9, big=True, comfortable=False) == -1.0
    assert next_drift(0.3, big=False, comfortable=False) == pytest.approx(0.25)  # settles back
    assert next_drift(-0.03, big=False, comfortable=False) == 0.0


def test_a_quiet_turn_adds_one_and_a_repeated_action_adds_more():
    state = farm_world()
    state.director.turns_without_stakes = 3
    quiet = pressure_after(state, farming())
    assert quiet.turns_without_stakes == 4
    assert quiet.low_stakes_streak == 1
    assert quiet.value == 4

    state.director.last_action_key = action_key(pipeline_resolution(state), farming())
    state.director.low_stakes_streak = 2
    repeated = pressure_after(state, farming())
    assert repeated.low_stakes_streak == 3
    assert repeated.value == 4 + 2 * rules.REPEAT_WEIGHT


def pipeline_resolution(state):
    return pipeline.resolve(state, farming(), ctx(3), rng(turn=3))


def test_the_action_key_ignores_filler_and_spots_the_same_action():
    assert action_key(pipeline_resolution(farm_world()), farming()) == "farm"
    assert action_key(pipeline_resolution(farm_world()), fence()) == "mend fence"


def test_turns_inside_an_encounter_never_count_as_quiet():
    state = farm_world()
    state.director.turns_without_stakes = 30
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=2, started_s=0
    )
    pressure = pressure_after(state, farming())
    assert pressure.encounter
    assert pressure.value == 0 and pressure.turns_without_stakes == 0
    assert not pressure.reached and pressure.early_chance == 0


def test_a_decision_with_stakes_resets_the_count():
    state = farm_world()
    state.director.turns_without_stakes = 8
    assert pressure_after(state, farming(), stakes=True).value == 0


def test_taking_up_an_open_thread_is_a_decision_with_stakes():
    state = grounded_world()
    state.director.turns_without_stakes = 8
    answered = pressure_after(state, farming(responds_to=["revenge"]))
    assert answered.stakes and answered.value == 0
    # A made-up or closed id is checked against the state and counts for nothing.
    assert not pressure_after(state, farming(responds_to=["nonsense"])).stakes


def test_the_opening_scene_has_no_pressure():
    state = farm_world()
    state.director.turns_without_stakes = 30
    assert pressure_after(state, farming(), turn=1).value == 0


def test_clocks_close_to_their_end_add_pressure_up_to_a_cap():
    state = farm_world()
    assert clock_pressure(state) == 0
    for i in range(3):
        state.clocks[f"c{i}"] = Clock(
            id=f"c{i}",
            name="a harvest",
            steps=["sown", "grown", "reaped"],
            filled=2,
            interval_s=DAY,
            next_step_s=state.world_s + DAY,
        )
    assert clock_pressure(state) == rules.CLOCK_CAP
    for clock in state.clocks.values():
        clock.next_step_s = state.world_s + 30 * DAY  # far off
    assert clock_pressure(state) == 0
    state.clocks["c0"].next_step_s = state.world_s + DAY
    state.clocks["c0"].status = ClockStatus.ENDED
    assert clock_pressure(state) == 0
    state.clocks["c1"].next_step_s = state.world_s
    assert clock_pressure(state) == rules.CLOCK_WEIGHT
    state.clocks["c1"].filled = 1  # two steps left
    assert clock_pressure(state) == 0


def test_an_event_may_come_early_from_sixty_percent_and_always_comes_at_the_threshold():
    def at(value: float) -> Pressure:
        return Pressure(value, 5.0, False, False, int(value), 1, None)

    assert at(2.9).early_chance == 0
    assert at(4).early_chance == pytest.approx(rules.EARLY_CHANCE * 0.5)
    assert at(5).early_chance == 1 and at(5).reached
    assert at(3).building and not at(2).building


@pytest.mark.parametrize("story", [f"seed-{i}" for i in range(8)])
def test_at_the_threshold_an_event_always_comes_and_well_below_it_never(story):
    state = farm_world()
    state.director.turns_without_stakes = 4  # this turn makes five, normal's threshold
    assert play_turn(state, 2, farming(), story=story).plan.event is not None
    state = farm_world()
    state.director.turns_without_stakes = 1  # two is below 60% of five
    assert play_turn(state, 2, farming(), story=story).plan.event is None
