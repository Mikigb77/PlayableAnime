"""The clock through pending events (W10, W10a): in time order, cut short by what needs the
player, frozen in a stop."""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.context import StorySettings, TurnContext
from engine.contracts import (
    CharacterChange,
    OutcomeClass,
    ProposedDeed,
    Resolution,
    StateDelta,
    StepResolution,
    StopReason,
)
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    ActiveTimeEffect,
    CharacterStatus,
    EventStatus,
    PendingEvent,
    StepResult,
    TimeEffect,
    WorldState,
)
from engine.timekeeping import advance_clock, world_stopped


def ctx(turn: int = 2) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings())


def rng() -> SeededRng:
    return SeededRng.for_turn("s1", "main", 2)


def event(event_id: str, due_s: int, **kwargs) -> PendingEvent:
    return PendingEvent(id=event_id, kind="test", due_s=due_s, **kwargs)


def with_events(*events: PendingEvent) -> WorldState:
    state = grounded_world()
    state.pending_events = {e.id: e for e in events}
    return state


class Recorder:
    """An event handler that marks each event applied and remembers the clock it saw."""

    def __init__(self, schedule: dict[str, PendingEvent] | None = None) -> None:
        self.seen: list[tuple[str, int]] = []
        self.schedule = schedule or {}

    def __call__(self, state: WorldState, e: PendingEvent) -> WorldState:
        self.seen.append((e.id, state.world_s))
        new = state.model_copy(deep=True)
        new.pending_events[e.id].status = EventStatus.APPLIED
        new.pending_events[e.id].applied_s = new.world_s
        if e.id in self.schedule:
            follow = self.schedule[e.id]
            new.pending_events[follow.id] = follow
        return new


# --- advance_clock -------------------------------------------------------------------------


def test_events_apply_in_time_order_each_at_its_due_time():
    state = with_events(event("late", 300), event("early", 100), event("after", 900))
    handler = Recorder()

    passage = advance_clock(state, 500, handler)

    assert handler.seen == [("early", 100), ("late", 300)]
    assert [e.id for e in passage.fired] == ["early", "late"]
    assert (passage.started_s, passage.ended_s, passage.elapsed_s) == (0, 500, 500)
    assert passage.state.world_s == 500
    assert passage.state.pending_events["after"].status is EventStatus.PENDING
    assert passage.interrupted_by is None and not passage.capped


def test_an_event_scheduled_inside_the_stretch_applies_in_its_turn():
    state = with_events(event("witness-flees", 60))
    handler = Recorder(
        {
            "witness-flees": event("report", 600, created_s=60),
            "report": event("patrol", 5000, created_s=600),
        }
    )

    passage = advance_clock(state, HOUR, handler)

    assert handler.seen == [("witness-flees", 60), ("report", 600)]
    assert passage.state.pending_events["patrol"].status is EventStatus.PENDING


def test_the_first_event_that_needs_the_player_stops_the_clock_there():
    state = with_events(
        event("quiet", 1 * HOUR),
        event("door", 2 * HOUR, needs_player=True),
        event("same-second", 2 * HOUR, created_s=5),
        event("dawn", 6 * HOUR),
    )

    passage = advance_clock(state, 8 * HOUR, Recorder())

    assert passage.interrupted_by.id == "door"
    assert passage.ended_s == passage.state.world_s == 2 * HOUR
    assert [e.id for e in passage.fired] == ["quiet", "door"]
    for waiting in ("same-second", "dawn"):
        assert passage.state.pending_events[waiting].status is EventStatus.PENDING


def test_overdue_events_apply_at_the_current_time():
    state = with_events(event("overdue", 10))
    state.world_s = 100
    handler = Recorder()

    passage = advance_clock(state, 100, handler)

    assert handler.seen == [("overdue", 100)]
    assert passage.elapsed_s == 0


def test_only_events_on_this_timeline_apply():
    state = with_events(event("here", 10), event("there", 10, timeline_id="rewound"))

    passage = advance_clock(state, 100, Recorder())

    assert [e.id for e in passage.fired] == ["here"]


def test_the_clock_never_runs_backwards():
    state = grounded_world()
    state.world_s = 100

    with pytest.raises(ValueError, match="never runs backwards"):
        advance_clock(state, 50, Recorder())


def test_a_handler_must_settle_the_event_and_leave_the_clock_alone():
    state = with_events(event("e", 10))

    def leaves_it(s, e):
        return s

    def moves_clock(s, e):
        new = Recorder()(s, e)
        new.world_s += 5
        return new

    with pytest.raises(RuntimeError, match="left it pending"):
        advance_clock(state, 100, leaves_it)
    with pytest.raises(RuntimeError, match="moved the clock"):
        advance_clock(state, 100, moves_clock)


def test_a_runaway_handler_is_capped():
    state = with_events(event("e-0", 10))
    counter = iter(range(1, 10_000))

    def keeps_scheduling(s, e):
        new = Recorder()(s, e)
        n = next(counter)
        new.pending_events[f"e-{n}"] = event(f"e-{n}", 10, created_s=n)
        return new

    passage = advance_clock(state, 100, keeps_scheduling, max_events=20)

    assert passage.capped and len(passage.fired) == 20 and passage.ended_s == 10


def test_advance_clock_leaves_its_input_alone():
    state = with_events(event("e", 10))
    before = state.model_dump()

    advance_clock(state, 100, Recorder())

    assert state.model_dump() == before


# --- catch_up ------------------------------------------------------------------------------


def test_catch_up_applies_what_fell_due_through_apply_event():
    state = grounded_world()
    state.world_s = 11 * DAY

    passage = pipeline.catch_up(state, state.world_s, ctx(), rng())

    applied = passage.state.pending_events["council-meets"]
    assert [e.id for e in passage.fired] == ["council-meets"]
    assert applied.status is EventStatus.APPLIED
    assert (applied.applied_turn, applied.applied_s) == (2, 11 * DAY)


def stopped(state: WorldState) -> WorldState:
    state.time_effects.append(
        ActiveTimeEffect(
            character_id="lin",
            power_id="time-stop",
            effect=TimeEffect.STOP,
            started_personal_s=0,
            ends_personal_s=3,
        )
    )
    return state


def test_nothing_fires_while_a_time_stop_is_in_effect():
    state = stopped(cultivation_world())
    state.pending_events = {"e": event("e", 0)}

    passage = pipeline.catch_up(state, state.world_s, ctx(), rng())

    assert world_stopped(state)
    assert passage.fired == () and passage.state.pending_events["e"].status is EventStatus.PENDING


def test_a_stop_that_has_run_out_no_longer_holds_the_world():
    state = stopped(cultivation_world())
    state.player.personal_offset_s = 3

    assert not world_stopped(state)


# --- play_out ------------------------------------------------------------------------------


def settled(index: int, duration_s: int, **kwargs) -> StepResolution:
    return StepResolution(
        index=index,
        text=f"step {index}",
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=duration_s,
        **kwargs,
    )


def test_a_long_rest_is_cut_short_by_the_guards_at_the_door():
    state = with_events(event("rumor", 1 * HOUR), event("guards", 2 * HOUR, needs_player=True))
    rested = StateDelta(
        characters=[CharacterChange(id="luca", condition=None, description="Rested")]
    )
    resolution = Resolution(
        steps=[
            settled(0, 8 * HOUR, effects=rested, deeds=[ProposedDeed(kind="sleep", text="Slept")]),
            settled(1, 10 * MINUTE),
        ]
    )

    played = pipeline.play_out(state, resolution, ctx(), rng())

    (step,) = played.resolution.steps
    assert step.interrupted and not step.clean_success
    assert (step.start_s, step.end_s, step.duration_s) == (0, 2 * HOUR, 2 * HOUR)
    assert played.state.world_s == 2 * HOUR
    assert played.interrupted_by.id == "guards"
    assert [e.id for e in played.fired] == ["rumor", "guards"]
    assert played.resolution.stopped_at_step == 0
    assert played.resolution.stop_reason is StopReason.INTERRUPTED
    assert played.resolution.unplayed == ["step 1"]
    # The rest was settled for eight hours, so its effects and deeds don't happen.
    assert played.state.player.description != "Rested"
    assert played.state.deeds == {}


def test_lived_time_of_a_cut_step_is_in_proportion():
    state = with_events(event("knock", 30 * MINUTE, needs_player=True))
    resolution = Resolution(steps=[settled(0, HOUR, personal_s=2 * HOUR)])

    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert played.resolution.steps[0].personal_s == HOUR
    assert played.state.player.personal_offset_s == 30 * MINUTE


def test_events_that_dont_need_the_player_just_happen_and_the_plan_goes_on():
    state = with_events(event("rumor", 30))
    death = StateDelta(characters=[CharacterChange(id="carmine", status=CharacterStatus.DEAD)])
    resolution = Resolution(steps=[settled(0, 2, effects=death), settled(1, 60)])

    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert [e.id for e in played.fired] == ["rumor"]
    assert played.interrupted_by is None and played.resolution.stop_reason is None
    assert [s.end_s for s in played.resolution.steps] == [2, 62]
    # The step's own effects are the engine's, so a resolved death sticks (F4).
    assert played.state.characters["carmine"].status is CharacterStatus.DEAD
    assert played.rejected == ()


def test_an_event_at_the_very_end_of_a_step_lets_it_finish_and_stops_the_rest():
    state = with_events(event("call", 60, needs_player=True))
    resolution = Resolution(
        steps=[settled(0, 60, deeds=[ProposedDeed(kind="search", text="Searched")]), settled(1, 5)]
    )

    played = pipeline.play_out(state, resolution, ctx(), rng())

    (step,) = played.resolution.steps
    assert not step.interrupted
    assert len(played.state.deeds) == 1
    assert played.resolution.unplayed == ["step 1"]
    assert played.resolution.stopped_at_step == 0


def test_a_refused_effect_is_reported_not_applied():
    effects = StateDelta(characters=[CharacterChange(id="carmine", location_id="moon")])

    played = pipeline.play_out(
        grounded_world(), Resolution(steps=[settled(0, 1, effects=effects)]), ctx(), rng()
    )

    assert played.state.characters["carmine"].location_id == "bar"
    assert [r.change for r in played.rejected] == ["location"]


def test_nothing_fires_inside_a_time_stop():
    state = cultivation_world()
    state.pending_events = {"e": event("e", 1)}
    resolution = Resolution(steps=[settled(0, 0, personal_s=3)])

    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert played.fired == () and played.state.world_s == 0
    assert played.state.player.personal_offset_s == 3


def test_an_event_rolls_the_same_however_the_time_around_it_is_split():
    seeds: list[str] = []
    original = pipeline.apply_event

    def spy(state, e, context, stream):
        seeds.append(stream.seed)
        return original(state, e, context, stream)

    state = with_events(event("e", 90))
    one_step = Resolution(steps=[settled(0, 120)])
    two_steps = Resolution(steps=[settled(0, 60), settled(1, 60)])
    pipeline.apply_event = spy
    try:
        pipeline.play_out(state, one_step, ctx(), rng())
        pipeline.play_out(state, two_steps, ctx(), rng())
    finally:
        pipeline.apply_event = original

    assert len(seeds) == 2 and seeds[0] == seeds[1]
    assert seeds[0].endswith("/event/e")


def test_deeds_in_stopped_time_leave_their_immune_witnesses_unnoticed():
    elder_saw = ProposedDeed(
        kind="strike", text="Struck Zhao", witness_ids=["elder-mo"], in_stopped_time=True
    )

    played = pipeline.play_out(
        cultivation_world(),
        Resolution(steps=[settled(0, 0, personal_s=2, deeds=[elder_saw])]),
        ctx(),
        rng(),
    )

    (deed,) = played.state.deeds.values()
    assert deed.witness_ids == ["elder-mo"] and deed.unnoticed_witness_ids == ["elder-mo"]


def test_a_needs_player_check_can_read_the_state():
    state = with_events(event("guards", 60, needs_player=True), event("knock", 120))

    def only_where_the_player_is(s, e):
        return e.id == "knock"

    passage = advance_clock(state, 300, Recorder(), needs_player=only_where_the_player_is)

    assert passage.interrupted_by.id == "knock" and passage.ended_s == 120


def test_play_out_goes_through_catch_up_with_the_turns_own_rng(monkeypatch):
    calls = []
    original = pipeline.catch_up

    def spy(state, until_s, context, stream):
        calls.append((state.world_s, until_s, stream.seed))
        return original(state, until_s, context, stream)

    monkeypatch.setattr(pipeline, "catch_up", spy)
    resolution = Resolution(steps=[settled(0, 60), settled(1, 0), settled(2, 30)])

    pipeline.play_out(grounded_world(), resolution, ctx(), rng())

    assert calls == [(0, 60, rng().seed), (60, 90, rng().seed)]


def test_a_capped_stretch_still_takes_the_steps_time(monkeypatch):
    def runaway(state, e):
        new = Recorder()(state, e)
        n = len(new.pending_events)
        new.pending_events[f"e-{n}"] = event(f"e-{n}", new.world_s, created_s=n)
        return new

    def capped_catch_up(state, until_s, context, stream):
        return advance_clock(state, until_s, runaway, max_events=5)

    monkeypatch.setattr(pipeline, "catch_up", capped_catch_up)
    resolution = Resolution(steps=[settled(0, 100), settled(1, 10)])

    played = pipeline.play_out(with_events(event("e-0", 10)), resolution, ctx(), rng())

    assert played.capped and played.interrupted_by is None
    assert [s.end_s for s in played.resolution.steps] == [100, 110]
    assert not played.resolution.steps[0].interrupted


def test_someone_elses_time_stop_holds_the_world_during_play_out():
    state = stopped(cultivation_world())
    state.player_id = "zhao"  # Zhao acts while Lin's stop holds the world
    state.pending_events = {"e": event("e", 5)}

    played = pipeline.play_out(state, Resolution(steps=[settled(0, 60)]), ctx(), rng())

    assert played.state.world_s == 0 and played.fired == ()
