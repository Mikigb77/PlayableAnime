"""W16, W10, E7: what comes in fits the time that passed on the story's clock.

Miki, 2026-11-11: "100 scenes in the same hour should get events that make sense for this time
lap", and of skipped time, "we will see if you just train for a week, or maybe during that week
there is something happening that forces a scene". Stall pressure counts the player's quiet
turns; the clock decides what may come of it: an event of a size the time since the last ones
has room for, or a moment, a small thing of here and now, or nothing yet. And time the player
skips is the story's to grant: a few days may well hold something."""

from itertools import pairwise

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import EventFrequency
from engine.contracts import ActionKind, ChoiceKind, EventKind, EventSource, PlannedEvent
from engine.director import rules
from engine.director.clock import (
    ALL_SIZES,
    clock_after,
    clock_is_slow,
    sizes_in_time,
    small_thing_fits,
)
from engine.director.deck import CastRole
from engine.director.due import MONTAGE_KIND
from engine.director.moments import BY_ID, MOMENTS, draw_moment
from engine.director.montage import schedule_stretch, stretch_gap
from engine.director.pressure import Pressure
from engine.director.sources import pick_event
from engine.director.suggestions import plan_suggestions
from engine.director.talk import plan_talk
from engine.director.themes import allowed_themes
from engine.samples import farm_world, grounded_world
from engine.state import (
    ActiveTimeEffect,
    DirectorState,
    Encounter,
    EncounterKind,
    EventSize,
    Origin,
    OriginKind,
    PendingEvent,
    Thread,
    ThreadKind,
    ThreadStatus,
    TimeEffect,
)
from tests.engine.director.helpers import act, ctx, farming, play_turn, rng

P, L, W = EventSize.PERSONAL, EventSize.LOCAL, EventSize.WORLD
GAP = {size: rules.EVENT_GAP_S[size.value] for size in EventSize}
SMALL = rules.SMALL_GAP_S
STORIES = [f"clock-{i}" for i in range(200)]

# Short scenes, each a different thing, so nothing here is a repeated low-stakes action.
SHORT = (
    ("Look out over the yard", "look"),
    ("Say a word to Ilse", "say"),
    ("Pick up the bucket", "pick up"),
    ("Scratch the dog's ears", "scratch"),
    ("Kick a stone off the path", "kick"),
    ("Straighten the gate", "straighten"),
    ("Drink from the well", "drink"),
)


def short(n: int, seconds: int = MINUTE, kind: ActionKind = ActionKind.TASK):
    text, verb = SHORT[n % len(SHORT)]
    return act(text, verb, kind, seconds)


def short_scenes(story: str, turns: int, seconds: int = MINUTE, kind=ActionKind.TASK, **settings):
    """A run of short quiet scenes on the farm, from the opening on. When an event needs a
    decision, the player deals with it in the next scene, which is as short as the rest."""
    state = farm_world()
    played = []
    answer: list[str] = []
    for turn in range(1, turns + 1):
        intent = short(turn, seconds, kind).model_copy(update={"responds_to": answer})
        played.append(play_turn(state, turn, intent, story=story, **settings))
        state = played[-1].state
        event = played[-1].plan.event
        answer = [event.thread_id] if event and event.needs_decision and event.thread_id else []
    return state, played


def since(small: int | None = None, **last: int) -> DirectorState:
    """The director's memory with the last event of each size given, by when it came in, and
    the last small thing."""
    events = {EventSize(size): at_s for size, at_s in last.items()}
    return DirectorState(last_event_s=events, last_small_s=small)


# --- what the time that passed has room for ------------------------------------------------------


def test_a_story_with_no_event_yet_has_room_for_any():
    assert sizes_in_time(DirectorState(), 0) == ALL_SIZES
    assert sizes_in_time(DirectorState(), 10 * YEAR) == ALL_SIZES


def test_a_personal_event_needs_hours_a_local_one_days_and_a_world_one_weeks():
    assert GAP[P] == 2 * HOUR and GAP[L] == 2 * DAY and GAP[W] == 14 * DAY
    start = 5 * DAY
    after_world = since(world=start)

    assert sizes_in_time(after_world, start + MINUTE) == frozenset()
    assert sizes_in_time(after_world, start + GAP[P] - 1) == frozenset()
    assert sizes_in_time(after_world, start + GAP[P]) == {P}
    assert sizes_in_time(after_world, start + GAP[L] - 1) == {P}
    assert sizes_in_time(after_world, start + GAP[L]) == {P, L}
    assert sizes_in_time(after_world, start + GAP[W] - 1) == {P, L}
    assert sizes_in_time(after_world, start + GAP[W]) == ALL_SIZES


def test_no_event_follows_another_sooner_than_the_smaller_of_the_two_needs():
    start = DAY
    after_personal = since(personal=start)
    after_local = since(local=start)

    # A flood is not held back for days by a visitor, only for the visitor's hours.
    assert sizes_in_time(after_personal, start + GAP[P] - 1) == frozenset()
    assert sizes_in_time(after_personal, start + GAP[P]) == ALL_SIZES
    # And after a flood, life's own small dramas go on within hours, with no second flood for days
    # and no war on its heels.
    assert sizes_in_time(after_local, start + GAP[P]) == {P}
    assert sizes_in_time(after_local, start + GAP[L]) == ALL_SIZES


def test_each_size_waits_on_the_last_of_every_size():
    now = 30 * DAY
    memory = since(world=now - 20 * DAY, local=now - DAY, personal=now - 3 * HOUR)

    assert sizes_in_time(memory, now) == {P}  # the local event a day ago still bars another
    assert sizes_in_time(memory, now + DAY) == ALL_SIZES


def test_the_directors_clock_is_saved_with_the_story():
    memory = since(small=3 * HOUR, world=0, local=HOUR, personal=2 * HOUR)
    memory.recent_moments = ["sound", "mishap"]

    assert DirectorState.model_validate_json(memory.model_dump_json()) == memory
    assert memory.model_dump(mode="json")["last_event_s"] == {
        "world": 0,
        "local": HOUR,
        "personal": 2 * HOUR,
    }
    # A story saved before the clock was kept has room for anything, as a new one has.
    old = DirectorState.model_validate({"turns_without_stakes": 3, "last_event_turn": 7})
    assert old.last_event_s == {} and old.last_small_s is None
    assert sizes_in_time(old, 5 * DAY) == ALL_SIZES and small_thing_fits(old, 5 * DAY)


def test_an_event_ahead_of_the_clock_bars_nothing():
    """W10a: after a return to an earlier time, what is still to come is no reason to wait."""
    assert sizes_in_time(since(world=10 * DAY), 2 * DAY) == ALL_SIZES


@pytest.mark.parametrize("at_s", [0, HOUR, 3 * HOUR, DAY, 3 * DAY, 20 * DAY])
def test_room_for_a_bigger_event_is_room_for_a_smaller_one(at_s):
    memory = since(world=0, local=HOUR, personal=2 * HOUR)
    sizes = sizes_in_time(memory, 2 * HOUR + at_s)

    assert not (W in sizes and L not in sizes) and not (L in sizes and P not in sizes)


def test_a_small_thing_needs_minutes_since_the_last_one_and_since_the_last_event():
    assert SMALL == 10 * MINUTE < GAP[P]
    start = DAY

    assert small_thing_fits(DirectorState(), 0)
    for memory in (since(small=start), since(personal=start), since(world=start)):
        assert not small_thing_fits(memory, start)
        assert not small_thing_fits(memory, start + SMALL - 1)
        assert small_thing_fits(memory, start + SMALL)
    assert small_thing_fits(since(small=start), start - HOUR)  # W10a: ahead of the clock
    # Each waits on the latest of them.
    assert not small_thing_fits(since(small=start + 5 * MINUTE, personal=start), start + SMALL)


# --- every source keeps to those sizes -----------------------------------------------------------


def test_every_source_keeps_to_the_sizes_there_is_room_for():
    state = grounded_world()  # a clan's man: local in scale, with plans and threads around him
    state.threads["feud"] = Thread(
        id="feud",
        title="The feud with the docks",
        kind=ThreadKind.THREAT,
        status=ThreadStatus.DORMANT,
        origin=Origin(kind=OriginKind.PREMISE, text="An old feud"),
        last_active_turn=0,
    )
    allowed = allowed_themes(state, ctx(40))
    drawn = {size: set() for size in EventSize}
    for story in STORIES[:80]:
        for sizes in (frozenset({P}), frozenset({P, L}), ALL_SIZES):
            pick = pick_event(
                state, ctx(40, story=story), rng(story), allowed, recent=[], sizes=sizes
            )
            assert pick is not None and pick.event.size in sizes, (story, sizes)
            drawn[max(sizes, key=list(EventSize).index)].add(pick.event.source)
        assert pick_event(state, ctx(40), rng(story), allowed, recent=[], sizes=frozenset()) is None
    # With room for local events the world's own sources speak (a faction's move, the feud).
    assert drawn[L] - {EventSource.DECK}


def test_a_private_life_with_room_only_for_a_world_event_it_never_draws_gets_none():
    """The deck's scale still holds: a farmer draws no world event however long it has been."""
    state = farm_world()
    allowed = allowed_themes(state, ctx())
    for story in STORIES[:40]:
        pick = pick_event(state, ctx(story=story), rng(story), allowed, recent=[])
        assert pick is not None and pick.event.size is not W


# --- a hundred scenes in the same hour -----------------------------------------------------------


@pytest.mark.parametrize("frequency", list(EventFrequency))
def test_many_short_scenes_in_one_hour_hold_one_event_at_most_and_a_few_moments(frequency):
    for story in STORIES[:12]:
        state, played = short_scenes(story, 60, event_frequency=frequency)
        events = [t for t in played if t.plan.event is not None]
        came = [t for t in played if t.plan.event or t.plan.moment or t.plan.talk]

        assert state.world_s - farm_world().world_s == 60 * MINUTE
        assert len(events) == 1, story  # the story's first event, and no second inside the hour
        assert 2 <= sum(1 for t in played if t.plan.moment is not None) <= 6, story
        for turn in played:
            assert turn.plan.event is None or turn.plan.moment is None
        # Whatever the story's frequency, a small thing keeps ten minutes from what came before.
        for earlier, later in pairwise(came):
            if later.plan.event is None:
                assert later.state.world_s - earlier.state.world_s >= SMALL, story


def test_scenes_of_a_few_seconds_get_nothing_until_minutes_have_passed():
    """Miki: "100 or 1,000 short parts that takes no more than a second, that's player choice"."""
    for story in STORIES[:6]:
        state, played = short_scenes(story, 150, seconds=3, kind=ActionKind.INSTANT)
        events = [t for t in played if t.plan.event is not None]
        moments = [t for t in played if t.plan.moment is not None]

        assert state.world_s - farm_world().world_s == 150 * 3  # seven and a half minutes
        assert len(events) == 1 and moments == [], story
        # And the quiet goes on counting, so a moment comes as soon as there is room for one.
        after = played[-1].state.director
        assert after.turns_without_stakes > rules.THRESHOLDS[EventFrequency.NORMAL]
        for turn in range(151, 160):
            turn_played = play_turn(state, turn, short(turn), story=story)
            state = turn_played.state
            if turn_played.plan.moment is not None:
                break
        assert turn_played.plan.moment is not None, story


def test_once_the_hours_have_passed_an_event_comes_again():
    for story in STORIES[:12]:
        state, played = short_scenes(story, 40)
        first = next(t for t in played if t.plan.event is not None)
        came_s = first.state.director.last_event_s[first.plan.event.size]
        assert played[-1].plan.event is None

        later = []
        for turn in range(41, 60):  # each scene now takes half an hour
            later.append(play_turn(state, turn, short(turn, 30 * MINUTE), story=story))
            state = later[-1].state
            if later[-1].plan.event is not None:
                break
        event = later[-1].plan.event
        assert event is not None, story
        assert state.world_s - came_s >= GAP[P], story
        assert state.director.last_event_s[event.size] == state.world_s


def test_no_two_events_come_closer_together_than_their_size_allows():
    for story in STORIES[:8]:
        state = farm_world()
        last: dict[EventSize, int] = {}
        for turn in range(1, 120):
            # Scenes of twenty minutes: on normal, pressure would bring an event every 100.
            played = play_turn(state, turn, short(turn, 20 * MINUTE), story=story)
            state = played.state
            event = played.plan.event
            if event is None:
                continue
            if event.source is not EventSource.DUE:  # what came due comes when it is due (E2)
                for size, at_s in last.items():
                    smaller = min(size, event.size, key=list(EventSize).index)
                    assert state.world_s - at_s >= GAP[smaller], (story, turn, event.title)
            last[event.size] = state.world_s
        assert len(last) >= 1 and state.director.last_event_s == last


def test_scenes_that_take_hours_get_their_events_as_before():
    """The clock holds nothing back from a life lived in hours: the quiet-life rhythm stands."""
    band = rules.THRESHOLDS[EventFrequency.NORMAL] * (1 + rules.DRIFT_SPAN)
    for story in STORIES[:12]:
        state = farm_world()
        quiet = 0
        for turn in range(1, 40):
            played = play_turn(state, turn, farming(), story=story)
            state = played.state
            assert played.plan.moment is None, (story, turn)
            quiet = 0 if played.plan.event is not None else quiet + 1
            assert quiet <= band + 1, story


# --- a moment asks nothing -----------------------------------------------------------------------


def a_moment(story: str = "clock-0"):
    """The farm a few short scenes after its first event, at the scene a moment comes into."""
    state = farm_world()
    for turn in range(1, 60):
        played = play_turn(state, turn, short(turn), story=story)
        if played.plan.moment is not None:
            return state, played, turn
        state = played.state
    raise AssertionError("no moment came")


def test_a_moment_opens_nothing_schedules_nothing_and_starts_the_quiet_over():
    before, played, _turn = a_moment()
    plan, after = played.plan, played.state

    assert plan.event is None and plan.talk is None  # one small thing in a scene, at most
    assert plan.updates.new_threads == [] and plan.updates.schedule == []
    assert plan.updates.new_leads == []
    assert after.threads.keys() == before.threads.keys()
    assert after.director.turns_without_stakes == 0
    assert after.director.recent_moments[-1] == plan.moment.id
    assert after.director.last_event_s == before.director.last_event_s  # it is no event
    assert after.director.last_small_s == after.world_s
    assert plan.moment.brief == BY_ID[plan.moment.id].brief


def test_a_moment_is_seeded_and_the_same_one_doesnt_come_twice_running():
    state = farm_world()
    first = draw_moment(state, ctx(), rng())
    assert draw_moment(state, ctx(), rng()) == first
    drawn = {draw_moment(state, ctx(story=s), rng(s)).id for s in STORIES}
    assert len(drawn) >= len(MOMENTS) - 2  # every story its own small things

    recent: list[str] = []
    for n in range(40):
        moment = draw_moment(state, ctx(), rng(turn=n + 2), recent=recent)
        assert moment.id not in recent
        recent = [*recent, moment.id][-rules.RECENT_MOMENTS :]
    assert rules.RECENT_MOMENTS < len(MOMENTS) - 1  # so there is always one left to draw


def test_a_familiar_face_is_someone_they_know_nearby_or_it_isnt_drawn():
    state = farm_world()
    cast = [m for m in MOMENTS if m.cast is not CastRole.NONE]
    assert cast
    faces = {
        tuple(moment.cast_ids)
        for moment in (draw_moment(state, ctx(story=s), rng(s)) for s in STORIES)
        if BY_ID[moment.id].cast is not CastRole.NONE
    }
    assert faces and all(ids and ids[0] in state.characters for ids in faces)
    assert state.player_id not in {i for ids in faces for i in ids}

    for npc in state.npcs():
        npc.met_by = []  # a stranger to everyone here
    alone = {draw_moment(state, ctx(story=s), rng(s)).id for s in STORIES}
    assert alone.isdisjoint(m.id for m in cast)


def test_moments_name_nothing_of_any_one_genre():
    """G5: the narrator dresses each in the world's own form."""
    genre_words = {"sword", "tavern", "phone", "car", "ship", "magic", "gun", "horse", "inn"}
    assert len({m.id for m in MOMENTS}) == len(MOMENTS)
    for moment in MOMENTS:
        words = {w.strip(".,:;'").lower() for w in moment.brief.split()}
        assert words.isdisjoint(genre_words), moment.id
        assert moment.weight > 0


def stalled(state):
    """The state on the story's second day, with the quiet at its threshold and an event an hour
    ago, so pressure brings something and the clock has no room for an event."""
    state.world_s = DAY
    state.director.turns_without_stakes = 20
    state.director.last_event_s = {P: state.world_s - HOUR}
    return state


def direct(state, turn: int = 9, story: str = "clock-0"):
    context = ctx(turn, story=story)
    intent = short(turn)
    resolution = pipeline.resolve(state, intent, context, rng(story, turn))
    return pipeline.direct(state, resolution, context, rng(story, turn), intent=intent)


def test_pressure_with_no_room_for_an_event_brings_a_moment():
    plan = direct(stalled(farm_world()))

    assert plan.event is None and plan.moment is not None


def test_pressure_with_no_room_even_for_a_moment_brings_nothing_and_keeps_counting():
    state = stalled(farm_world())
    state.director.last_small_s = state.world_s - MINUTE
    plan = direct(state)

    assert plan.event is None and plan.moment is None and plan.talk is None
    assert plan.updates.memory.turns_without_stakes == 21
    assert plan.updates.memory.last_small_s == state.world_s - MINUTE


def test_talk_of_the_place_is_a_small_thing_and_keeps_to_the_clock():
    state = farm_world()
    quiet = Pressure(1.0, 5.0, False, False, 1, 1, None)
    resolution = pipeline.resolve(state, short(2), ctx(), rng())
    offers = [
        plan_talk(state, resolution, rng(s), pressure=quiet, busy=False, small=small)
        for small in (True, False)
        for s in STORIES
    ]

    assert any(offers[: len(STORIES)])  # the place's own talk, now and then
    assert not any(offers[len(STORIES) :])  # and never minutes after the last small thing

    # A scene that carried talk is the last small thing, for the next one to keep its minutes.
    for turn in range(2, 80):
        played = play_turn(state, turn, short(turn, 11 * MINUTE), story="clock-1")
        state = played.state
        if played.plan.talk is not None:
            break
    assert played.plan.talk is not None and state.director.last_small_s == state.world_s


def test_no_moment_inside_stopped_time_in_an_encounter_or_on_the_opening():
    frozen = stalled(farm_world())
    frozen.time_effects.append(
        ActiveTimeEffect(
            character_id=frozen.player_id,
            power_id="time-stop",
            effect=TimeEffect.STOP,
            started_personal_s=0,
        )
    )
    assert direct(frozen).moment is None  # nothing stirs while the world stands still

    fighting = stalled(farm_world())
    fighting.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=8, started_s=0
    )
    assert direct(fighting).moment is None

    assert direct(stalled(farm_world()), turn=1).moment is None


def test_a_scene_that_tells_what_came_to_pass_gets_no_moment_on_top():
    state = stalled(farm_world())
    card = {
        "size": "personal",
        "kind": "windfall",
        "source": "deck",
        "card_id": "good-day",
        "title": "A good day",
        "brief": "Everything goes right for once.",
        "needs_decision": False,
    }
    state.pending_events["rolled"] = PendingEvent(
        id="rolled",
        kind=MONTAGE_KIND,
        title="A good day",
        due_s=state.world_s,
        timeline_id=state.timeline_id,
        payload={"pick": {"event": card, "key": "deck:good-day"}},
    )
    plan = direct(state)

    assert [h.title for h in plan.happenings] == ["A good day"]
    assert plan.moment is None and plan.event is None


# --- skipped time is the story's to grant --------------------------------------------------------


def cut_short(length_s: int, frequency=EventFrequency.NORMAL, stories=STORIES) -> list[int]:
    """When each story's skip of `length_s` is cut short by something that needs a decision, in
    seconds from its start, for the stories where it is."""
    stops = []
    for story in stories:
        context = ctx(2, story=story, event_frequency=frequency)
        rolled = schedule_stretch(farm_world(), 0, length_s, context, rng(story))
        stops += [e.due_s for e in rolled.pending_events.values() if e.needs_player]
    return stops


def test_a_few_skipped_days_may_well_hold_something():
    """Miki: "during those 3 days, even if you are in your room, something could happen"."""
    three_days = len(cut_short(3 * DAY)) / len(STORIES)
    a_week = len(cut_short(7 * DAY)) / len(STORIES)
    a_day = len(cut_short(DAY)) / len(STORIES)

    assert 0.03 <= a_day <= 0.2, a_day
    assert 0.2 <= three_days <= 0.4, three_days
    assert 0.45 <= a_week <= 0.7, a_week  # a week of training: we will see
    assert a_day < three_days < a_week


def test_the_storys_frequency_makes_skipped_time_calmer_or_busier():
    calm, normal, dramatic = (len(cut_short(7 * DAY, f)) for f in EventFrequency)

    assert calm < normal < dramatic
    assert calm >= len(STORIES) // 5  # even on calm, a week is no sure thing


def test_a_long_stretch_is_told_more_coarsely():
    context = ctx()
    base = rules.MONTAGE_MEAN_GAP_S[EventFrequency.NORMAL]
    assert stretch_gap(3 * DAY, context) == stretch_gap(2 * base, context) == base
    assert stretch_gap(YEAR, context) == YEAR // rules.MONTAGE_LONG_SHARE

    month, year, century = (cut_short(length) for length in (30 * DAY, YEAR, 100 * YEAR))
    for stops in (month, year, century):
        assert 0.75 <= len(stops) / len(STORIES) <= 0.95  # as surely a year as a month
    # A year stops some months in, never in its first week every time.
    assert 60 * DAY <= sum(year) / len(year) <= 200 * DAY
    assert sum(1 for due_s in year if due_s <= 7 * DAY) <= len(year) // 10


def test_what_a_skip_rolls_keeps_to_the_time_since_the_last_events():
    state = farm_world()
    state.director.last_event_s = {L: 0}  # the river rose this morning
    start = 3 * HOUR
    sizes = []
    for story in STORIES:
        rolled = schedule_stretch(state, start, start + 36 * HOUR, ctx(2, story=story), rng(story))
        sizes += [
            e.payload["pick"]["event"]["size"]
            for e in rolled.pending_events.values()
            if e.kind == MONTAGE_KIND
        ]

    assert sizes and set(sizes) == {"personal"}  # no second flood inside two days


# --- a way to let time pass, offered and never pushed --------------------------------------------

RUN = rules.SLOW_CLOCK_SCENES
TIME = ChoiceKind.TIME


def offers(played) -> list[int]:
    """The turns whose suggestions hold a way to let time pass."""
    return [n for n, turn in enumerate(played, start=1) if TIME in turn.plan.suggestions.kinds]


def test_a_slow_clock_is_a_long_run_of_scenes_that_took_next_to_no_time():
    assert (RUN, rules.SLOW_CLOCK_S) == (12, 30 * MINUTE)
    minutes = [n * MINUTE for n in range(RUN)]

    assert clock_is_slow(minutes)
    assert not clock_is_slow(minutes[1:])  # a shorter run is not one yet
    assert not clock_is_slow([n * 3 * MINUTE for n in range(RUN)])  # scenes of minutes move on
    assert clock_is_slow([HOUR] * RUN)  # stopped clocks and instants: no time at all
    assert not clock_is_slow([*minutes[:-1], -HOUR])  # a clock that went back (W10a)

    memory = DirectorState(recent_clock=minutes)
    assert clock_after(memory, HOUR) == [*minutes[1:], HOUR]  # the last ones, this scene last
    assert clock_after(DirectorState(), 0) == [0]


@pytest.mark.parametrize("frequency", list(EventFrequency))
def test_a_long_run_of_short_scenes_is_offered_a_way_to_let_time_pass_now_and_then(frequency):
    """Miki, 2026-11-11: playing a hundred short scenes in the same hour is the player's choice.
    So nothing pushes the clock on: one choice among the others, once in a long while."""
    for story in STORIES[:10]:
        _state, played = short_scenes(story, 60, event_frequency=frequency)
        turns = offers(played)

        assert turns and turns[0] >= RUN  # only after a long run
        assert all(later - sooner >= RUN for sooner, later in pairwise(turns))
        assert len(turns) <= 60 // RUN
        for turn in turns:
            plan = played[turn - 1].plan
            kinds = plan.suggestions.kinds
            # One such choice, beside the others, in a scene with nothing to decide.
            assert kinds.count(TIME) == 1 and 3 <= len(kinds) == plan.suggestions.count <= 4
            assert set(kinds) - {TIME}
            assert plan.event is None or not plan.event.needs_decision


def test_scenes_that_move_the_clock_on_are_never_offered_it():
    for story in STORIES[:10]:
        _state, minutes = short_scenes(story, 60, 5 * MINUTE)
        _state, hours = short_scenes(story, 40, 3 * HOUR)

        assert offers(minutes) == [] and offers(hours) == []


def test_with_suggestions_off_nothing_is_offered():
    _state, played = short_scenes("clock-0", 40, suggestions=False)

    assert all(turn.plan.suggestions.count == 0 for turn in played)


def slow(state):
    """The state after a long run of scenes inside a few minutes, on a quiet day."""
    state.world_s = DAY
    state.director.recent_clock = [DAY - n * 10 for n in range(RUN, 0, -1)]
    return state


def test_a_slow_clock_offers_time_in_a_quiet_scene_and_the_run_starts_over():
    state = slow(farm_world())
    plan = direct(state)

    assert TIME in plan.suggestions.kinds
    assert plan.updates.memory.recent_clock == []
    # The next scene is the first of a new run.
    after = pipeline.record_direction(state, plan, ctx(9, story="clock-0"))
    again = direct(after, turn=10)
    assert TIME not in again.suggestions.kinds
    assert again.updates.memory.recent_clock == [after.world_s]


def test_it_is_never_offered_where_the_scene_is_about_something_else():
    # In an encounter (W10): the scene is the fight's.
    fight = slow(farm_world())
    fight.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=8, started_s=0
    )
    # Inside stopped time (W10a): there is no time to let pass.
    stopped = slow(farm_world())
    stopped.time_effects.append(
        ActiveTimeEffect(
            character_id=stopped.player_id,
            power_id="time-stop",
            effect=TimeEffect.STOP,
            started_personal_s=0,
        )
    )
    for state in (fight, stopped):
        plan = direct(state)
        assert TIME not in plan.suggestions.kinds
        # The run is kept, so the offer comes once the scene has room for it.
        assert len(plan.updates.memory.recent_clock) == RUN


def test_the_time_choice_is_a_fourth_choice_or_takes_the_side_matters_place():
    calm = Pressure(0.0, 5.0, False, False, 0, 1, None)
    building = Pressure(4.0, 5.0, False, False, 4, 1, None)
    fighting = Pressure(0.0, 5.0, False, True, 0, 1, None)
    event = PlannedEvent(
        size=P,
        kind=EventKind.ARRIVAL,
        source=EventSource.DECK,
        title="An old friend in trouble",
        brief="",
    )
    c = ctx()

    def kinds(pressure, *, event=None, thread_id="t"):
        plan = plan_suggestions(c, pressure=pressure, event=event, thread_id=thread_id, time=True)
        assert plan.count == len(plan.kinds) <= 4
        return plan.kinds

    T, PERSONAL, SIDE, WILD = (
        ChoiceKind.THREAD,
        ChoiceKind.PERSONAL,
        ChoiceKind.SIDE,
        ChoiceKind.WILD,
    )
    assert kinds(calm) == [T, PERSONAL, SIDE, TIME]
    assert kinds(calm, thread_id=None) == [PERSONAL, SIDE, WILD, TIME]
    assert kinds(building) == [T, PERSONAL, TIME, WILD]  # four already
    # Never beside an event that needs a decision, or in an encounter.
    assert TIME not in kinds(calm, event=event)
    assert TIME not in kinds(fighting)
    off = plan_suggestions(
        ctx(suggestions=False), pressure=calm, event=None, thread_id="t", time=True
    )
    assert off.count == 0


def test_the_run_of_short_scenes_is_saved_with_the_story():
    memory = DirectorState(recent_clock=[0, MINUTE, 2 * MINUTE])

    assert DirectorState.model_validate(memory.model_dump(mode="json")) == memory
    assert DirectorState.model_validate({}).recent_clock == []  # a story saved before this
