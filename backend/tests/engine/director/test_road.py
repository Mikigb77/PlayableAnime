"""W10, W16: what the road brings. A journey is not always one scene: the longer the way, the
likelier it meets something, what needs a decision stops the trip where it happens, and the
rest of the way is kept (Miki, 2026-11-11: "during the journey I might want to do something, or
there might be some event, and you might encounter something")."""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.context import EventFrequency
from engine.contracts import ActionKind, EventSource, Intent, IntentStep
from engine.director import rules
from engine.director.deck import CARDS, DECK, ROAD, Tone, draw_road
from engine.director.due import MONTAGE_KIND, pick_from_payload
from engine.director.montage import road_steps, schedule_road
from engine.resolve import resolve_intent
from engine.samples import farm_world
from engine.state import Encounter, EncounterKind, Place, Route, WorldState
from engine.world import journeys
from engine.world.geography import route_s
from tests.engine.director.helpers import ctx, rng

STORIES = [f"road-{i}" for i in range(400)]
CITY = 3 * DAY  # the village to the city, by the map


def valley() -> WorldState:
    """Tomas in the village, three days by the map from the city of Harrowgate."""
    state = farm_world()
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        routes=[Route(to_id="village", travel_s=CITY, mode="by cart")],
        known_by=["tomas"],
    )
    state.places["mine"] = Place(id="mine", name="the old mine", kind="wilds", known_by=["tomas"])
    state.player.location_id = "village"
    state.scene.place_id = "village"
    state.scene.present_ids = ["tomas"]
    return state


def rolled(state: WorldState) -> list:
    events = [e for e in state.pending_events.values() if e.kind == MONTAGE_KIND]
    return sorted(events, key=lambda e: e.due_s)


def share_stopped(length_s: int, **settings) -> float:
    """How often a trip of that length meets something that needs a decision."""
    stopped = 0
    for story in STORIES:
        events = rolled(
            schedule_road(valley(), 0, length_s, ctx(2, story=story, **settings), rng(story))
        )
        stopped += any(e.needs_player for e in events)
    return stopped / len(STORIES)


def go(text: str, to: str, seconds: int = HOUR, **kw) -> Intent:
    step = IntentStep(
        text=text,
        verb="go",
        kind=ActionKind.TRAVEL,
        destination=to,
        proposed_duration_s=seconds,
        **kw,
    )
    return Intent(summary=text, steps=[step])


def travel(state: WorldState, intent: Intent, story: str) -> pipeline.PlayOut:
    context = ctx(2, story=story)
    resolution = resolve_intent(state, intent, context, rng(story))
    return pipeline.play_out(state, resolution, context, rng(story))


def first_story(found) -> tuple[str, pipeline.PlayOut]:
    """The first seed whose ride to the city goes as `found` says."""
    for story in STORIES:
        played = travel(valley(), go("ride to Harrowgate", "city"), story)
        if found(played):
            return story, played
    raise AssertionError("no seed in range")


def stopped(played: pipeline.PlayOut) -> bool:
    return played.resolution.steps[0].interrupted


# --- the table -----------------------------------------------------------------------------------


def test_the_road_has_its_own_cards_good_ones_included():
    assert len({card.id for card in ROAD}) == len(ROAD)
    assert not {card.id for card in ROAD} & {card.id for card in DECK}
    assert all(CARDS[card.id] is card for card in ROAD)
    assert {card.tone for card in ROAD} == set(Tone)
    for card in ROAD:
        assert card.id.startswith("road-") and card.title and card.brief
        # A stop on the way says what happens if they pass it by, so it plays out (W16).
        assert bool(card.consequence) is card.needs_decision
    assert any(not card.needs_decision for card in ROAD)  # the small good things on the way


def test_no_road_card_assumes_a_genre():
    """G5: the way is a mountain path, a motorway, a sea lane or a jump route."""
    words = " ".join(f"{card.title} {card.brief} {card.consequence}" for card in ROAD).casefold()
    for word in ("horse", "sword", "bandit", "wagon", "car ", "ship", "dragon", "magic"):
        assert word not in words


def test_a_road_card_is_drawn_by_seed_and_passes_over_recent_ones():
    context = ctx(2)
    first = draw_road(context, rng(), frozenset())
    assert draw_road(context, rng(), frozenset()) is first
    again = draw_road(context, rng(), frozenset(), recent=[first.source_key])
    assert again is not first
    everything = [card.source_key for card in ROAD]
    assert draw_road(context, rng(), frozenset(), recent=everything) in ROAD


# --- how often -----------------------------------------------------------------------------------


def test_a_short_walk_meets_nothing_and_nor_does_a_trip_inside_an_encounter():
    state = valley()
    for story in STORIES[:50]:
        assert schedule_road(state, 0, 40 * MINUTE, ctx(2, story=story), rng(story)) is state
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=2, started_s=0
    )
    assert all(
        schedule_road(state, 0, 30 * DAY, ctx(2, story=s), rng(s)) is state for s in STORIES[:50]
    )


def test_the_longer_the_way_the_likelier_it_meets_something():
    hours, day, days, weeks = (share_stopped(s) for s in (6 * HOUR, DAY, 3 * DAY, 21 * DAY))

    assert 0.02 < hours < 0.15  # an afternoon's walk is usually just a walk
    assert 0.15 < day < 0.40  # a day's travel meets something now and then
    assert 0.40 < days < 0.80  # three days' more often than not
    assert weeks > 0.95  # nobody crosses a country without a story
    assert hours < day < days < weeks


def test_the_storys_frequency_sets_how_eventful_the_road_is():
    calm = share_stopped(3 * DAY, event_frequency=EventFrequency.CALM)
    normal = share_stopped(3 * DAY)
    dramatic = share_stopped(3 * DAY, event_frequency=EventFrequency.DRAMATIC)

    assert 0 < calm < normal < dramatic < 1  # it never turns them off (S6)


def test_each_stop_makes_the_rest_of_the_way_quieter():
    def share(stops: int) -> float:
        hits = 0
        for story in STORIES:
            state = valley()
            state.director.road_stops = stops
            hits += bool(rolled(schedule_road(state, 0, 3 * DAY, ctx(2, story=story), rng(story))))
        return hits / len(STORIES)

    fresh, once, twice, often, always = (share(n) for n in (0, 1, 2, 4, 40))

    assert fresh > once > twice > often > 0
    assert often == always  # it never goes silent


def test_what_is_rolled_lies_on_the_way_in_time_order_and_stops_at_the_first_decision():
    for story in STORIES[:120]:
        state = valley()
        events = rolled(schedule_road(state, 100, 100 + 30 * DAY, ctx(2, story=story), rng(story)))
        assert len(events) <= rules.MONTAGE_MAX_STEPS
        assert all(100 < e.due_s <= 100 + 30 * DAY for e in events)
        needing = [e for e in events if e.needs_player]
        assert len(needing) <= 1
        if needing:
            assert events[-1] is needing[0]  # nothing is rolled after the stop
        for event in events:
            pick = pick_from_payload(event.payload["pick"])
            assert pick.event.source is EventSource.DECK and pick.event.card_id in CARDS
            assert CARDS[pick.event.card_id] in ROAD
            assert pick.event.place_id is None and event.place_id is None  # on the way
        assert state.pending_events == {}  # the input state is never touched


def test_a_trip_is_split_into_legs_of_at_least_an_hour():
    assert road_steps(0, 90 * MINUTE) == [(0, 90 * MINUTE)]
    assert road_steps(0, 3 * HOUR) == [(0, HOUR), (HOUR, 2 * HOUR), (2 * HOUR, 3 * HOUR)]
    assert len(road_steps(0, 90 * DAY)) == rules.MONTAGE_MAX_STEPS


# --- through a turn ------------------------------------------------------------------------------


def test_a_ride_of_days_is_one_scene_when_the_road_is_quiet():
    _, played = first_story(lambda p: not stopped(p))

    (ride,) = played.resolution.steps
    assert ride.duration_s == CITY and ride.trip.arrived
    assert played.state.player.location_id == "city"
    assert played.state.journey is None and played.state.director.road_stops == 0


def test_what_the_road_brings_stops_the_trip_there_and_becomes_the_scenes_event():
    story, played = first_story(stopped)
    (ride,) = played.resolution.steps

    assert 0 < ride.duration_s < CITY and ride.trip.arrived is False
    assert played.interrupted_by.kind == MONTAGE_KIND
    assert played.state.player.location_id == "village"  # not there yet
    journey = played.state.journey
    assert (journey.to_id, journey.done_s, journey.left_s) == (
        "city",
        ride.duration_s,
        CITY - ride.duration_s,
    )
    assert played.state.director.road_stops == 1

    context = ctx(2, story=story)
    plan = pipeline.direct(played.state, played.resolution, context, rng(story))
    assert plan.event is not None and plan.event.needs_decision
    assert CARDS[plan.event.card_id] in ROAD
    assert plan.event.place_id is None
    assert plan.event.plays_out_s is not None  # passed by, it plays out (W16)


def test_small_good_things_on_the_way_colour_the_trip_without_stopping_it():
    def coloured(played: pipeline.PlayOut) -> bool:
        return not stopped(played) and any(e.kind == MONTAGE_KIND for e in played.fired)

    story, played = first_story(coloured)

    assert played.resolution.steps[0].trip.arrived
    plan = pipeline.direct(played.state, played.resolution, ctx(2, story=story), rng(story))
    on_the_way = [h for h in plan.happenings if h.card_id and CARDS[h.card_id] in ROAD]
    assert on_the_way and not any(h.needs_decision for h in on_the_way)


def test_walking_on_carries_the_journey_on_and_arriving_starts_the_road_afresh():
    story, played = first_story(stopped)
    state = played.state
    state.pending_events = {}
    left = state.journey.left_s
    # "I walk on" names nowhere: it is the trip they are on.
    walk_on = IntentStep(
        text="walk on", verb="walk", kind=ActionKind.TRAVEL, proposed_duration_s=HOUR
    )

    onward = resolve_intent(
        state, Intent(summary="walk on", steps=[walk_on]), ctx(3, story=story), rng(story)
    )

    (step,) = onward.steps
    assert step.trip.to_id == "city" and step.duration_s == left
    journeys.follow(state, "tomas", step, planned_s=left)
    assert state.player.location_id == "city"
    assert state.journey is None and state.director.road_stops == 0


def test_a_stretch_the_player_sets_keeps_the_rest_of_the_way():
    state = valley()
    story = STORIES[0]

    played = travel(
        state, go("walk toward Harrowgate for half an hour", "city", 30 * MINUTE, timed=True), story
    )

    (walk,) = played.resolution.steps
    assert walk.duration_s == 30 * MINUTE and walk.trip.arrived is False
    assert not walk.interrupted and played.state.director.road_stops == 0
    assert played.state.journey.left_s == CITY - 30 * MINUTE


# --- over ground no route covers -----------------------------------------------------------------


def to_the_mine(story: str) -> pipeline.PlayOut:
    return travel(valley(), go("walk to the old mine", "mine", 2 * DAY), story)


def test_a_trip_over_unmapped_ground_that_is_stopped_keeps_the_time_judged_for_it():
    story = next(s for s in STORIES if stopped(to_the_mine(s)))
    played = to_the_mine(story)
    (walk,) = played.resolution.steps

    journey = played.state.journey
    assert not journey.mapped
    assert (journey.total_s, journey.done_s) == (2 * DAY, walk.duration_s)

    # The rest takes what is left of it, whatever is proposed this time.
    state = played.state
    state.pending_events = {}
    rest = resolve_intent(
        state, go("go on to the mine", "mine", 10 * MINUTE), ctx(3, story=story), rng(story)
    )
    assert rest.steps[0].duration_s == 2 * DAY - walk.duration_s


def test_a_journey_over_unmapped_ground_leaves_its_route_once_it_arrives():
    story = next(s for s in STORIES if stopped(to_the_mine(s)))
    state = to_the_mine(story).state
    state.pending_events = {}
    state.director.road_stops = 40  # a quiet road for the rest of it
    assert route_s(state, "village", "mine") is None

    quiet = next(
        s
        for s in STORIES
        if not stopped(travel(state, go("go on to the mine", "mine", 10 * MINUTE), s))
    )
    played = travel(state, go("go on to the mine", "mine", 10 * MINUTE), quiet)

    assert played.state.player.location_id == "mine" and played.state.journey is None
    assert route_s(played.state, "village", "mine") == 2 * DAY  # the whole way, as first judged
    assert route_s(played.state, "mine", "village") == 2 * DAY


@pytest.mark.parametrize("frequency", list(EventFrequency))
def test_every_frequency_has_a_road_rate(frequency):
    assert rules.ROAD_MEAN_GAP_S[frequency] < rules.MONTAGE_MEAN_GAP_S[frequency]
