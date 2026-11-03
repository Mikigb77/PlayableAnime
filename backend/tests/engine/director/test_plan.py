"""The director's plan as a whole: pure and seeded, its suggestions (S2), its montage rolls (E7),
and recording it into the state with provisional ids (B5)."""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, YEAR
from engine.context import EventFrequency
from engine.contracts import (
    ActionKind,
    ChoiceKind,
    DirectorPlan,
    DirectorUpdates,
    EventKind,
    EventSource,
    PlannedEvent,
)
from engine.director import rules
from engine.director.due import MONTAGE_KIND, PLAYS_OUT_KIND
from engine.director.montage import schedule_stretch
from engine.director.pressure import Pressure
from engine.director.suggestions import AWAY, plan_suggestions
from engine.samples import farm_world, grounded_world
from engine.state import (
    Encounter,
    EncounterKind,
    EventSize,
    EventStatus,
    Lead,
    Origin,
    OriginKind,
    PendingEvent,
    Thread,
    ThreadKind,
)
from tests.engine.director.helpers import act, ctx, farming, play_turn, rng
from tests.engine.director.test_scenarios import quiet_life

SEEDS = [f"seed-{i}" for i in range(8)]


def test_direct_never_changes_the_state_and_is_seeded():
    state = farm_world()
    state.director.turns_without_stakes = 9
    context = ctx(3)
    resolution = pipeline.resolve(state, farming(), context, rng(turn=3))
    before = state.model_dump(mode="json")
    plans = [
        pipeline.direct(state, resolution, context, rng(turn=3), intent=farming()) for _ in range(3)
    ]
    assert state.model_dump(mode="json") == before
    assert plans[0] == plans[1] == plans[2]
    assert plans[0].event is not None


def test_different_stories_get_different_events_from_the_same_life():
    titles = {
        tuple(p.event.title if p.event else "" for p in quiet_life(story, EventFrequency.NORMAL)[1])
        for story in SEEDS
    }
    assert len(titles) > len(SEEDS) // 2


def test_every_scene_offers_zero_to_four_suggestions_with_one_away_from_the_thread():
    for story in SEEDS[:4]:
        state, plans = quiet_life(story, EventFrequency.DRAMATIC)
        for plan in plans:
            kinds = plan.suggestions.kinds
            assert 0 <= plan.suggestions.count == len(kinds) <= 4
            assert set(kinds) & set(AWAY), kinds
            assert len(plan.callbacks) <= rules.MAX_CALLBACKS
    off = play_turn(farm_world(), 2, farming(), suggestions=False).plan.suggestions
    assert off.count == 0 and off.kinds == []


def quiet(value=0.0, *, encounter=False) -> Pressure:
    return Pressure(value, 5.0, False, encounter, int(value), 1, None)


def test_suggestions_answer_the_scene_and_never_follow_a_thread_that_isnt_there():
    event = PlannedEvent(
        size=EventSize.PERSONAL,
        kind=EventKind.ARRIVAL,
        source=EventSource.DECK,
        title="An old friend in trouble",
        brief="",
    )
    c = ctx()
    fight = plan_suggestions(c, pressure=quiet(encounter=True), event=None, thread_id="t")
    assert fight.kinds == [ChoiceKind.THREAD, ChoiceKind.THREAD, ChoiceKind.WILD]
    arrival = plan_suggestions(c, pressure=quiet(), event=event, thread_id="t")
    assert arrival.kinds == [ChoiceKind.THREAD, ChoiceKind.THREAD, ChoiceKind.PERSONAL]
    calm = plan_suggestions(c, pressure=quiet(), event=None, thread_id="t")
    assert calm.kinds == [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE]
    building = plan_suggestions(c, pressure=quiet(4), event=None, thread_id="t")
    assert building.count == 4 and building.kinds[-1] is ChoiceKind.WILD
    none = plan_suggestions(c, pressure=quiet(), event=None, thread_id=None)
    assert ChoiceKind.THREAD not in none.kinds and none.thread_id is None


def test_a_time_skip_rolls_its_events_inside_the_stretch_and_stops_at_a_decision():
    rolled_any = False
    for story in SEEDS * 2:
        state = farm_world()
        scheduled = schedule_stretch(state, 0, YEAR, ctx(2, story=story), rng(story))
        events = sorted(
            (e for e in scheduled.pending_events.values() if e.kind == MONTAGE_KIND),
            key=lambda e: e.due_s,
        )
        assert len(events) <= rules.MONTAGE_MAX_STEPS
        assert all(0 < e.due_s <= YEAR for e in events)
        needing = [e for e in events if e.needs_player]
        assert len(needing) <= 1
        if needing:
            assert events[-1] is needing[0]  # nothing is rolled after the stop
        rolled_any = rolled_any or bool(events)
        assert state.pending_events == {}  # the input state is never touched
    assert rolled_any


def test_no_montage_for_a_short_stretch_or_inside_an_encounter():
    state = farm_world()
    assert schedule_stretch(state, 0, 20 * HOUR, ctx(), rng()) is state
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=2, started_s=0
    )
    assert schedule_stretch(state, 0, YEAR, ctx(), rng()) is state


def plan_with_new_records() -> DirectorPlan:
    thread = Thread(
        id="thread-1",
        title="An offer",
        kind=ThreadKind.QUEST,
        origin=Origin(kind=OriginKind.EVENT),
        known_by=["tomas"],
    )
    waiting = PendingEvent(
        id="director-event-1",
        kind=PLAYS_OUT_KIND,
        due_s=DAY,
        origin=Origin(kind=OriginKind.EVENT, ref_id="thread-1"),
        payload={"event": {"thread_id": "thread-1"}, "thread_id": "thread-1", "lingers": False},
    )
    lead = Lead(id="lead-1", text="An offer", thread_id="thread-1")
    return DirectorPlan(
        updates=DirectorUpdates(new_threads=[thread], schedule=[waiting], new_leads=[lead])
    )


def test_recording_keeps_provisional_ids_that_are_free_and_bumps_the_counters():
    state = farm_world()
    after = pipeline.record_direction(state, plan_with_new_records(), ctx())
    assert set(after.threads) == {"thread-1"} and set(after.leads) == {"lead-1"}
    assert after.new_id("thread") == "thread-2"
    assert after.new_id("lead") == "lead-2"
    assert after.new_id("director-event") == "director-event-2"
    assert state.threads == {}  # the input state is never touched


def test_recording_remaps_an_id_taken_in_the_meantime_and_its_references_follow():
    state = farm_world()
    state.leads["lead-1"] = Lead(id="lead-1", text="The narrator's own lead")
    state.id_counters["lead"] = 1
    state.threads["thread-1"] = Thread(
        id="thread-1", title="Taken", kind=ThreadKind.QUEST, origin=Origin(kind=OriginKind.DEED)
    )
    state.id_counters["thread"] = 1
    after = pipeline.record_direction(state, plan_with_new_records(), ctx())
    assert after.threads["thread-1"].title == "Taken"
    assert after.threads["thread-2"].title == "An offer"
    assert after.leads["lead-1"].text == "The narrator's own lead"
    assert after.leads["lead-2"].thread_id == "thread-2"
    waiting = after.pending_events["director-event-1"]
    assert waiting.payload["thread_id"] == "thread-2"
    assert waiting.payload["event"]["thread_id"] == "thread-2"
    assert waiting.origin.ref_id == "thread-2"


@pytest.mark.parametrize(
    ("status", "applied_turn", "kind", "expected"),
    [
        (EventStatus.PENDING, None, PLAYS_OUT_KIND, EventStatus.CANCELLED),
        # The clock applied it during the very action that took it up: it never happened.
        (EventStatus.APPLIED, 3, PLAYS_OUT_KIND, EventStatus.CANCELLED),
        (EventStatus.APPLIED, 2, PLAYS_OUT_KIND, EventStatus.APPLIED),
        (EventStatus.APPLIED, 3, "arrival", EventStatus.APPLIED),  # never the world's own events
    ],
)
def test_cancelling_touches_only_what_can_still_be_undone(status, applied_turn, kind, expected):
    state = farm_world()
    state.pending_events["e"] = PendingEvent(
        id="e", kind=kind, due_s=DAY, status=status, applied_turn=applied_turn
    )
    plan = DirectorPlan(updates=DirectorUpdates(cancel_ids=["e"]))
    assert pipeline.record_direction(state, plan, ctx(3)).pending_events["e"].status is expected


def test_recording_marks_due_director_events_applied_and_keeps_the_memory():
    state = farm_world()
    state.world_s = 2 * DAY
    state.pending_events["e"] = PendingEvent(id="e", kind=PLAYS_OUT_KIND, due_s=DAY)
    plan = DirectorPlan(updates=DirectorUpdates(applied_ids=["e"]))
    plan.updates.memory.turns_without_stakes = 7
    after = pipeline.record_direction(state, plan, ctx(4))
    applied = after.pending_events["e"]
    assert applied.status is EventStatus.APPLIED and applied.applied_turn == 4
    assert applied.applied_s == 2 * DAY
    assert after.director.turns_without_stakes == 7


def test_the_first_turn_after_a_skip_lands_starts_on_the_event_it_stopped_at():
    stops = 0
    for story in SEEDS:
        played = play_turn(
            grounded_world(),
            2,
            act("Lie low for a year", "lie low", ActionKind.TIME_SKIP, YEAR),
            story=story,
        )
        stop = played.play.interrupted_by
        if stop is not None and stop.kind == MONTAGE_KIND:
            assert played.plan.event is not None and played.plan.event.title == stop.title
            assert played.state.pending_events[stop.id].status is EventStatus.APPLIED
            assert played.plan.event.plays_out_s is not None
            stops += 1
    assert stops >= len(SEEDS) // 2  # in a year, the Esposito family's plans reach Luca


def test_events_rolled_for_time_that_was_never_lived_never_happen():
    """E7: a skip cut short by something earlier leaves its later rolls behind; they are dropped."""
    story = next(  # the first seed whose year holds something
        s
        for s in (f"roll-{i}" for i in range(50))
        if schedule_stretch(farm_world(), 0, YEAR, ctx(2, story=s), rng(s)).pending_events
    )
    rolled = schedule_stretch(farm_world(), 0, YEAR, ctx(2, story=story), rng(story))
    later = [e for e in rolled.pending_events.values() if e.kind == MONTAGE_KIND]
    # Something stopped the clock on day two, before any of them.
    rolled.world_s = 2 * DAY
    for event in later:
        event.due_s = max(event.due_s, 3 * DAY)
    context = ctx(2, story=story)
    resolution = pipeline.resolve(rolled, farming(), context, rng(story))
    plan = pipeline.direct(rolled, resolution, context, rng(story), intent=farming())
    assert set(plan.updates.cancel_ids) >= {e.id for e in later}
    after = pipeline.record_direction(rolled, plan, context)
    assert {after.pending_events[e.id].status for e in later} == {EventStatus.CANCELLED}


def two_decisions_due(state):
    """A world event that needs the player and a rolled event that needs a decision, both due."""
    from engine.director.deck import CARDS
    from engine.director.due import pick_payload
    from engine.director.sources import from_card

    state.world_s = DAY
    state.pending_events["guards"] = PendingEvent(
        id="guards", kind="arrival", title="The bailiff comes", due_s=DAY, needs_player=True
    )
    pick = from_card(state, CARDS["nature-turns"], rng())
    state.pending_events["director-event-1"] = PendingEvent(
        id="director-event-1",
        kind=MONTAGE_KIND,
        title=pick.event.title,
        due_s=DAY,
        payload={"pick": pick_payload(pick)},
    )
    return state


def test_a_second_event_needing_a_decision_waits_for_the_next_scene():
    """One decision at a time: the other one is neither lost nor told as settled (W16, E2)."""
    state = two_decisions_due(farm_world())
    first = play_turn(state, 2, act("Look up", "look", ActionKind.INSTANT, 2))
    assert first.plan.event is not None and first.plan.event.title == "The bailiff comes"
    assert first.plan.happenings == []
    waiting = [
        e
        for e in first.state.pending_events.values()
        if e.kind == MONTAGE_KIND and e.status is EventStatus.PENDING
    ]
    assert len(waiting) == 1 and waiting[0].due_s == first.state.world_s

    second = play_turn(first.state, 3, act("Look up", "look", ActionKind.INSTANT, 2))
    assert second.plan.event is not None and second.plan.event.needs_decision
    assert second.plan.event.title == waiting[0].title
    assert second.plan.event.thread_id in second.state.threads
