"""W10, W7: a trip takes the time the map says, the character arrives, a trip over new ground
writes its route and one cut short keeps what is left (Miki's review, 2026-11-11: a ride to
another city took minutes, and the next scene had the character back where they set out)."""

import pytest

from engine import pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import (
    ActionKind,
    Aim,
    Challenge,
    Intent,
    OutcomeClass,
    PlaceChange,
    ProposedDeed,
    Resolution,
    SceneEnd,
    StateDelta,
    StepResolution,
    Trip,
)
from engine.director import rules
from engine.resolve.durations import step_timing
from engine.rng import SeededRng
from engine.samples import farm_world
from engine.state import (
    Item,
    ItemKind,
    Journey,
    Mark,
    PendingEvent,
    Place,
    PlaceSetting,
    PowerAxis,
    Route,
    StepResult,
    WorldState,
)
from engine.world import journeys
from engine.world.geography import has_route, route_s, routes_from, travel_s
from tests.engine.resolve.power_worlds import stop_time
from tests.engine.resolve.worlds import SEEDS, ctx, facts, give, item, resolve, rng, sect, step

TRAVEL, MOVE = ActionKind.TRAVEL, ActionKind.MOVE


@pytest.fixture(autouse=True)
def quiet_road(monkeypatch):
    """Nothing the road brings stops a trip here (W16): that is `tests/engine/director/
    test_road.py`'s. These tests are about the way itself."""
    monkeypatch.setattr(rules, "ROAD_MIN_S", 10**12)


WALK = 40 * MINUTE  # the farm to the village, by the map
ROAD = 3 * DAY  # the village to the city, by the map
FORD = 20 * HOUR  # the village to the ford, by the map


def valley() -> WorldState:
    """Tomas at his farm in the Long Valley. By the map the village is forty minutes off, and
    beyond it the city of Harrowgate is three days away and Greywater Ford twenty hours. The
    old mill is on no map, and the cellar is under the farmhouse."""
    state = farm_world()
    state.places["ford"] = Place(
        id="ford",
        name="Greywater Ford",
        kind="wilds",
        routes=[Route(to_id="village", travel_s=FORD, mode="on foot")],
        known_by=["tomas"],
    )
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        routes=[Route(to_id="village", travel_s=ROAD, mode="by cart")],
        known_by=["tomas"],
    )
    state.places["mill"] = Place(
        id="mill", name="the old mill", kind="building", parent_id="valley", known_by=["tomas"]
    )
    state.places["cellar"] = Place(
        id="cellar",
        name="the cellar",
        kind="room",
        parent_id="farm",
        known_by=["tomas"],
        visited_by=["tomas"],
    )
    return state


def go(text: str, to: str, seconds: int, kind: ActionKind = TRAVEL, **kw):
    return step(text, kind, seconds, destination=to, **kw)


def one(state: WorldState, *steps, seed: int = 0) -> StepResolution:
    resolution = resolve(state, Intent(summary="go", steps=list(steps)), seed)
    return resolution.steps[-1]


def play(state: WorldState, *steps, seed: int = 0) -> pipeline.PlayOut:
    resolution = resolve(state, Intent(summary="go", steps=list(steps)), seed)
    return pipeline.play_out(state, resolution, ctx(), rng(seed))


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


def told(state: WorldState, place_id: str | None, present=("tomas",), places=()) -> WorldState:
    """The state once a narrator's update that ends the scene in `place_id` is applied."""
    delta = StateDelta(
        places=list(places),
        scene_end=SceneEnd(ended_on="The road.", place_id=place_id, present_ids=list(present)),
    )
    return apply_delta(state, delta, ctx(), source=DeltaSource.NARRATOR).state


# --- the map ---------------------------------------------------------------------------------


def test_a_route_is_what_the_way_takes_and_routes_chain():
    state = valley()

    assert route_s(state, "farm", "village") == WALK
    assert route_s(state, "village", "farm") == WALK
    assert route_s(state, "farm", "city") == WALK + ROAD
    assert has_route(state, "village", "city") and has_route(state, "city", "village")
    assert not has_route(state, "farm", "city")


def test_the_short_walk_into_a_place_is_no_route():
    state = valley()

    # The map connects them, but only by the rough quarter of an hour between a place and the
    # one it lies in, which is no time to hold someone's steps to.
    assert travel_s(state, "farm", "cellar") == 15 * MINUTE
    assert route_s(state, "farm", "cellar") is None
    assert route_s(state, "farm", "mill") is None
    assert route_s(state, "farm", "farm") is None
    assert route_s(state, "farm", None) is None and route_s(state, "nowhere", "farm") is None


def test_routes_from_lists_what_the_map_reaches_with_its_time():
    state = valley()

    assert routes_from(state, "farm") == {
        "village": WALK,
        "city": WALK + ROAD,
        "ford": WALK + FORD,
    }
    # From the cellar the way runs up into the farm and then along its road.
    assert routes_from(state, "cellar")["village"] == 15 * MINUTE + WALK
    assert routes_from(state, None) == {} and routes_from(state, "nowhere") == {}


# --- where a step goes -------------------------------------------------------------------------


@pytest.mark.parametrize("named", ["village", "Millbrook", "millbrook", " Millbrook "])
def test_a_step_names_where_it_goes_by_id_or_by_name(named):
    state = valley()

    trip = journeys.heading(state, state.player, go("walk to town", named, 60), "farm")

    assert trip == Trip(from_id="farm", to_id="village", route_s=WALK)


def test_a_step_that_goes_to_the_one_place_it_targets_is_a_trip():
    state = valley()
    walk = step("walk to the village", MOVE, 60, target_ids=["village"])
    talk = step("talk about the village", ActionKind.CONVERSATION, 60, target_ids=["village"])

    assert journeys.heading(state, state.player, walk, "farm").to_id == "village"
    assert journeys.heading(state, state.player, talk, "farm") is None


def test_a_place_the_record_doesnt_hold_is_kept_in_the_players_words():
    state = valley()

    trip = journeys.heading(state, state.player, go("ride out", "the salt marshes", HOUR), "farm")

    assert trip == Trip(from_id="farm", to_id=None, to="the salt marshes", route_s=None)


def test_a_name_never_reaches_a_place_the_story_hasnt_brought_near():
    state = valley()
    state.places["far"] = Place(id="far", name="Port Sorrow", kind="city")  # unknown to Tomas

    trip = journeys.heading(state, state.player, go("sail", "Port Sorrow", DAY), "farm")

    assert trip.to_id is None and trip.to == "Port Sorrow"


def test_travelling_with_nowhere_named_is_still_a_trip_and_staying_put_is_none():
    state = valley()

    wander = journeys.heading(state, state.player, step("wander off", TRAVEL, HOUR), "farm")
    stay = journeys.heading(state, state.player, go("stay", "farm", 60), "farm")
    hoe = journeys.heading(
        state, state.player, step("hoe the field", ActionKind.WORK, HOUR), "farm"
    )

    assert wander == Trip(from_id="farm")
    assert stay is None and hoe is None


# --- how long it takes ---------------------------------------------------------------------------


@pytest.mark.parametrize("proposed", [20, 5 * MINUTE, 10 * HOUR])
@pytest.mark.parametrize("kind", [MOVE, TRAVEL])
def test_a_trip_takes_the_routes_time_whatever_was_proposed(proposed, kind):
    settled_step = one(valley(), go("walk to the village", "village", proposed, kind))

    assert settled_step.duration_s == WALK
    assert settled_step.trip == Trip(
        from_id="farm", to_id="village", route_s=WALK, takes_s=WALK, arrived=True
    )


def test_a_trip_days_long_holds_whatever_its_kind_allows():
    # The first model called a ride to the city a move of two minutes.
    ride = one(valley(), go("ride to Harrowgate", "city", 2 * MINUTE, MOVE))

    assert ride.duration_s == WALK + ROAD
    assert ride.trip.arrived


def test_the_same_trip_takes_the_same_time_every_time():
    spans = {
        one(
            valley(), go("walk", "village", 30 * MINUTE, duration_uncertain=True), seed=s
        ).duration_s
        for s in range(40)
    }

    assert spans == {WALK}  # the road is as long as it is: never rolled


def test_something_of_their_own_carries_them_there_sooner():
    state = give(valley(), "tomas", Item(id="mare", name="a grey mare", kind=ItemKind.OTHER))
    ride = go("ride the mare to the village", "village", 10 * MINUTE, uses=[item("mare")])
    slow = go("lead the mare to the village", "village", 3 * HOUR, uses=[item("mare")])

    ridden, led = one(state, ride), one(state, slow)

    assert ridden.duration_s == 10 * MINUTE
    assert ridden.trip.takes_s == 10 * MINUTE and ridden.trip.route_s == WALK
    assert ridden.trip.arrived and ridden.trip.by_own_means
    assert led.duration_s == WALK  # never longer than the road


def test_over_ground_no_route_covers_the_trip_takes_what_was_judged():
    walk = one(valley(), go("walk to the old mill", "mill", 50 * MINUTE))

    assert walk.duration_s == 50 * MINUTE
    assert walk.trip == Trip(from_id="farm", to_id="mill", arrived=True)


def test_a_trip_the_world_rules_out_goes_nowhere():
    fly = go("fly to the village", "village", 60, facts=facts(world_allows=False))

    settled_step = one(valley(), fly)

    assert settled_step.outcome_class is OutcomeClass.RULED_OUT
    assert settled_step.trip.arrived is False and settled_step.trip.takes_s is None
    assert settled_step.duration_s == 60  # only its proposed time


def test_a_throw_over_the_top_never_shortens_the_way():
    """A3 halves a task thrown over the top. The map's time for a trip and a time the player
    set are not the throw's to shorten."""
    hard = facts(opposition="the flooded lane", challenge=Challenge.MODERATE)
    mapped = go("wade the lane to the village", "village", 20 * MINUTE, MOVE, facts=hard)
    timed = go("wade toward the mill for 20 minutes", "mill", 20 * MINUTE, MOVE, facts=hard)
    timed = timed.model_copy(update={"timed": True})
    over = 0
    for seed in SEEDS:
        for walk, takes in ((mapped, WALK), (timed, 20 * MINUTE)):
            settled_step = one(valley(), walk, seed=seed)
            if settled_step.result is StepResult.FAILURE:
                continue
            assert settled_step.duration_s == takes
            if settled_step.roll.throw.mark is Mark.OVER_THE_TOP:
                over += 1
                assert "half the time" not in settled_step.extra

    assert over  # some of those throws were over the top


def test_a_walk_is_never_squeezed_into_the_last_seconds_of_a_time_stop():
    """W10a. Lin's stop holds three seconds. The inner court is forty minutes off by the map,
    whatever the first model proposed, so he lives the stop out on the way and the world's
    clock runs for the rest of it."""
    walk = go("walk to the inner court", "inner-court", 2, MOVE, proposed_personal_s=2)

    stopped, walked = resolve(sect(), Intent(steps=[stop_time(), walk])).steps

    assert stopped.duration_s == 0
    assert walked.personal_s == WALK and walked.trip.arrived
    assert walked.duration_s == WALK - 2  # two seconds of the stop were left


def test_a_step_that_goes_somewhere_to_do_something_takes_at_least_the_way():
    """Only a step that is the going itself takes exactly the map's time. Sleeping at the inn
    in the village is a night, not a forty minutes' walk, and it leaves them in the village."""
    night = step("sleep at the inn in Millbrook until dusk", ActionKind.REST, 8 * HOUR)
    night = night.model_copy(update={"until": "18:00", "destination": "village"})
    harvest = step("help with the harvest in Millbrook", ActionKind.WORK, 4 * HOUR)
    harvest = harvest.model_copy(update={"destination": "village"})
    errand = step("buy nails in Harrowgate", ActionKind.TASK, HOUR, destination="city")

    slept, worked, bought = (one(valley(), each) for each in (night, harvest, errand))

    assert slept.duration_s == 12 * HOUR and worked.duration_s == 4 * HOUR
    assert bought.duration_s == WALK + ROAD  # the errand can't be done sooner than the way there
    for settled_step in (slept, worked, bought):
        assert settled_step.trip.arrived and settled_step.trip.to_id in ("village", "city")
    assert not journeys.on_the_road(valley(), "tomas", slept)  # a night is no time on the road
    assert journeys.on_the_road(valley(), "tomas", one(valley(), go("walk", "village", 60)))


def test_an_event_in_the_night_at_the_inn_finds_them_there_and_one_on_the_walk_doesnt():
    night = step("sleep at the inn in Millbrook", ActionKind.REST, 8 * HOUR, destination="village")

    def woken_after(seconds: int) -> pipeline.PlayOut:
        state = valley()
        state.pending_events = {
            "knock": PendingEvent(id="knock", kind="test", due_s=seconds, needs_player=True)
        }
        return play(state, night)

    late, early = woken_after(2 * HOUR), woken_after(20 * MINUTE)

    assert late.resolution.steps[0].interrupted and late.resolution.steps[0].trip.arrived
    assert late.state.player.location_id == "village" and late.state.journey is None
    assert early.resolution.steps[0].trip.arrived is False
    assert early.state.player.location_id == "farm"
    assert early.state.journey.left_s == 20 * MINUTE


def test_each_step_of_a_plan_sets_out_from_where_the_last_one_arrived():
    resolution = resolve(
        valley(),
        Intent(
            summary="to the village, then on to the city, then home",
            steps=[
                go("walk to the village", "village", 60),
                go("ride on to Harrowgate", "city", 60),
                go("come home", "farm", 60),
            ],
        ),
    )

    assert [s.duration_s for s in resolution.steps] == [WALK, ROAD, ROAD + WALK]
    assert [s.trip.from_id for s in resolution.steps] == ["farm", "village", "city"]


# --- a trip the player timed -------------------------------------------------------------------


def test_a_trip_until_a_time_of_day_stops_on_the_way():
    # The day starts at 06:00, so dusk at 18:00 is twelve hours off and the city is days away.
    ride = one(valley(), go("ride for Harrowgate until dusk", "city", HOUR, until="18:00"))

    assert ride.duration_s == 12 * HOUR
    assert ride.trip.arrived is False and ride.trip.takes_s == WALK + ROAD


def test_a_trip_that_is_shorter_than_the_time_set_arrives_before_it():
    walk = one(valley(), go("walk to the village by dusk", "village", HOUR, until="18:00"))

    assert walk.duration_s == WALK
    assert walk.trip.arrived


def test_a_trip_for_a_set_time_stops_when_the_time_is_up():
    two_hours = go("ride toward Harrowgate for two hours", "city", 2 * HOUR, timed=True)
    all_week = go("take a week over the walk to the village", "village", 7 * DAY, timed=True)

    short, long = one(valley(), two_hours), one(valley(), all_week)

    assert short.duration_s == 2 * HOUR and short.trip.arrived is False
    assert long.duration_s == WALK and long.trip.arrived


def test_a_timed_trip_over_ground_no_route_covers_is_left_to_the_telling():
    walk = one(valley(), go("walk toward the mill for an hour", "mill", HOUR, timed=True))

    assert walk.duration_s == HOUR
    assert walk.trip.arrived is None  # nobody can say whether an hour was enough


def test_a_step_with_no_trip_is_timed_as_before():
    rest = one(valley(), step("sleep until dusk", ActionKind.REST, 8 * HOUR, until="18:00"))
    work = one(valley(), step("hoe for two hours", ActionKind.WORK, 2 * HOUR, timed=True))

    assert rest.trip is None and rest.duration_s == 12 * HOUR
    assert work.trip is None and work.duration_s == 2 * HOUR


def test_a_fixed_time_stands_in_for_the_proposal_and_is_never_rolled():
    walk = go("walk", "village", 30, MOVE, duration_uncertain=True)

    timing = step_timing(walk, frozen=False, rolls=True, rng=SeededRng("s"), fixed_s=WALK)
    hasted = step_timing(walk, frozen=False, rolls=True, rng=SeededRng("s"), fixed_s=WALK, rate=2)

    assert (timing.duration_s, timing.personal_s, timing.rolled_s) == (WALK, None, None)
    # Twice as fast on their own clock: the way is as long, and the world sees half of it.
    assert (hasted.duration_s, hasted.personal_s) == (WALK // 2, WALK)


# --- arriving ------------------------------------------------------------------------------------


def test_whoever_arrives_is_there_and_the_scene_is_left_for_the_telling():
    played = play(valley(), go("walk to the village", "village", 60))

    assert played.state.world_s == WALK
    assert played.state.player.location_id == "village"
    assert played.state.scene.place_id == "farm"  # the narrator says where its scene ends
    assert played.state.journey is None


def test_what_they_do_after_arriving_happens_there():
    state = valley()
    resolution = Resolution(
        steps=[
            settled(0, WALK, trip=Trip(from_id="farm", to_id="village", arrived=True)),
            settled(
                1, MINUTE, deeds=[ProposedDeed(kind="speech", text="Called out in the square")]
            ),
        ]
    )

    played = pipeline.play_out(state, resolution, ctx(), rng())

    (deed,) = played.state.deeds.values()
    assert deed.place_id == "village"
    assert "bram" in deed.witness_ids and "ilse" not in deed.witness_ids


def test_a_trip_that_failed_leaves_them_where_they_were():
    state = valley()
    failed = settled(0, 5 * MINUTE, trip=Trip(from_id="farm", to_id="village")).model_copy(
        update={"result": StepResult.FAILURE}
    )

    played = pipeline.play_out(state, Resolution(steps=[failed]), ctx(), rng())

    assert played.state.player.location_id == "farm" and played.state.journey is None


# --- cut short -----------------------------------------------------------------------------------


def at_the_village() -> WorldState:
    state = valley()
    state.player.location_id = "village"
    state.scene.place_id = "village"
    state.scene.present_ids = ["tomas"]
    return state


def stopped_on_the_road() -> pipeline.PlayOut:
    """Riders stop Tomas eight hours out of the village, on the twenty hours' road to the ford."""
    state = at_the_village()
    state.pending_events = {
        "riders": PendingEvent(id="riders", kind="test", due_s=8 * HOUR, needs_player=True)
    }
    return play(state, go("walk to Greywater Ford", "ford", HOUR))


def test_a_trip_an_event_cuts_short_keeps_what_is_left_of_the_way():
    played = stopped_on_the_road()

    (walk,) = played.resolution.steps
    assert walk.interrupted and walk.duration_s == 8 * HOUR
    assert walk.trip.arrived is False
    assert played.state.player.location_id == "village"  # not there yet
    assert played.state.journey == Journey(
        from_id="village", to_id="ford", total_s=FORD, done_s=8 * HOUR, at_id="village"
    )
    assert played.state.journey.left_s == 12 * HOUR


def test_the_rest_of_the_way_takes_what_is_left_and_turning_back_what_was_done():
    state = stopped_on_the_road().state
    state.pending_events = {}

    onward = play(state, go("walk on to the ford", "ford", HOUR))
    back = play(state, go("turn back for the village", "village", HOUR))

    assert onward.resolution.steps[0].duration_s == 12 * HOUR
    assert onward.state.player.location_id == "ford" and onward.state.journey is None
    assert back.resolution.steps[0].duration_s == 8 * HOUR
    assert back.resolution.steps[0].trip.arrived and back.state.journey is None


def test_a_journey_goes_on_from_the_place_the_scene_stopped_in():
    played = stopped_on_the_road()
    camp = PlaceChange(id="camp", name="a camp by the road", kind="camp", setting="outdoors")
    after = told(played.state, "camp", places=[camp])

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert notes == [] and state.scene.place_id == "camp"
    assert state.journey.at_id == "camp" and state.journey.left_s == 12 * HOUR
    # No route is written for a trip that didn't arrive.
    assert not has_route(state, "village", "camp")
    onward = one(state, go("walk on to the ford", "ford", HOUR))
    back = one(state, go("walk back to Millbrook", "village", HOUR))
    assert onward.duration_s == 12 * HOUR and back.duration_s == 8 * HOUR


def test_a_second_stop_on_the_same_way_adds_to_what_is_behind_them():
    state = stopped_on_the_road().state
    state.pending_events = {
        "storm": PendingEvent(id="storm", kind="test", due_s=14 * HOUR, needs_player=True)
    }

    played = play(state, go("walk on to the ford", "ford", HOUR))

    assert played.state.journey.done_s == 14 * HOUR
    assert played.state.journey.left_s == 6 * HOUR


# --- at a stop on the way ------------------------------------------------------------------------


def camped() -> WorldState:
    """Tomas eight hours out on the road to the ford, in a camp the scene added, with twelve
    hours of the way left."""
    played = stopped_on_the_road()
    camp = PlaceChange(id="camp", name="a camp by the road", kind="camp", setting="outdoors")
    after = told(played.state, "camp", places=[camp])
    state, _ = journeys.settle(played.state, after, played.resolution, told=True)
    state.pending_events = {}
    return state


def after_scene(state: WorldState, played: pipeline.PlayOut, place_id: str, places=()):
    """The state once the narrator ended the scene of `played` in `place_id`."""
    ended = told(played.state, place_id, places=places)
    return journeys.settle(played.state, ended, played.resolution, told=True)[0]


def test_what_they_do_at_a_stop_leaves_the_journey_as_it_is():
    """What the road brings sends them off it: down to the stream, into a tent for the night."""
    state = camped()
    stream = go("go down to the stream", "the stream", 5 * MINUTE, MOVE)
    night = go("sleep in the tent until dusk", "the tent", 8 * HOUR, ActionKind.REST)
    night = night.model_copy(update={"until": "18:00"})

    for aside in (stream, night):
        played = play(state, aside)
        assert played.state.journey == state.journey
        assert after_scene(state, played, "camp").journey == state.journey


def test_a_journey_goes_with_them_to_a_spot_nearby():
    state = camped()
    ruin = PlaceChange(id="ruin", name="the ruin above the road", kind="ruin", setting="outdoors")

    played = play(state, go("climb to the ruin above the road", "the ruin", 20 * MINUTE))
    after = after_scene(state, played, "ruin", places=[ruin])

    assert after.journey.at_id == "ruin" and after.journey.left_s == 12 * HOUR
    onward = one(after, go("walk on", "", HOUR))  # no place named: the way they were on
    assert onward.trip.to_id == "ford" and onward.duration_s == 12 * HOUR


def test_a_scene_the_telling_moves_a_little_keeps_the_journey():
    state = camped()
    lane = PlaceChange(id="lane", name="the sunken lane", kind="road", setting="outdoors")
    moved = told(state, "lane", places=[lane])

    after, notes = journeys.settle(state, moved, Resolution(steps=[settled(0, 60)]), told=True)

    # The lane is a spot of the camp they were in (R8), which is where the journey stopped.
    assert notes == ["the scene added 'lane' and not where it lies: within 'camp'"]
    assert after.scene.place_id == "lane" and journeys.under_way(after, "lane") == after.journey
    assert after.journey.at_id == "camp" and after.journey.left_s == 12 * HOUR


def test_a_place_inside_the_one_they_stopped_in_is_still_on_the_way():
    state = camped()
    state.places["tent"] = Place(
        id="tent", name="the tent", kind="room", parent_id="camp", known_by=["tomas"]
    )

    played = play(state, go("crawl into the tent", "tent", 60, MOVE))
    after = after_scene(state, played, "tent")

    assert after.scene.place_id == "tent" and after.journey.at_id == "camp"
    assert journeys.under_way(after, "tent") == after.journey
    onward = play(after, go("walk on to the ford", "ford", HOUR))
    assert onward.resolution.steps[0].duration_s == 12 * HOUR
    assert onward.state.player.location_id == "ford" and onward.state.journey is None
    # Stopped again, the way behind them is still counted from where they first set out.
    after.pending_events = {
        "storm": PendingEvent(
            id="storm", kind="test", due_s=after.world_s + 6 * HOUR, needs_player=True
        )
    }
    again = play(after, go("walk on to the ford", "ford", HOUR)).state.journey
    assert (again.from_id, again.done_s, again.left_s) == ("village", 14 * HOUR, 6 * HOUR)


@pytest.mark.parametrize("end", ["ford", "village"])
def test_a_scene_that_stands_at_either_end_of_the_journey_ends_it(end):
    state = camped()

    after, _ = journeys.settle(
        state, told(state, end), Resolution(steps=[settled(0, 60)]), told=True
    )

    assert after.journey is None


def test_setting_out_somewhere_else_gives_the_journey_up():
    state = give(camped(), "tomas", Item(id="mare", name="a grey mare", kind=ItemKind.OTHER))
    far = go("strike out for the old mill", "mill", 3 * HOUR)
    ridden = go("gallop off to the old mill", "mill", 10 * MINUTE, uses=[item("mare")])

    for away in (far, ridden):  # nobody can say how far the mare carried them
        played = play(state, away)
        assert after_scene(state, played, "mill").journey is None


def test_what_carried_them_sooner_counts_the_way_in_the_maps_time():
    state = give(
        at_the_village(), "tomas", Item(id="mare", name="a grey mare", kind=ItemKind.OTHER)
    )
    state.pending_events = {
        "riders": PendingEvent(id="riders", kind="test", due_s=5 * HOUR, needs_player=True)
    }

    played = play(state, go("gallop to the ford", "ford", 10 * HOUR, uses=[item("mare")]))

    # Half of a ten hours' gallop is half of the twenty hours' road.
    assert played.resolution.steps[0].duration_s == 5 * HOUR
    assert played.state.journey.done_s == FORD // 2


# --- where the scene ends ------------------------------------------------------------------------


def test_a_scene_that_ends_where_the_trip_went_stands():
    played = play(valley(), go("walk to the village", "village", 60))
    after = told(played.state, "village", present=("tomas", "bram"))

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert state is after and notes == []


def test_a_scene_told_as_if_the_trip_never_happened_is_put_where_it_went():
    start = valley()
    played = play(start, go("walk to the village", "village", 60))
    after = told(played.state, "farm", present=("tomas", "ilse", "bram"))

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert state.scene.place_id == "village" and state.player.location_id == "village"
    assert notes == ["the scene ended in 'farm', where the trip left: now 'village'"]
    # Ilse was with him as the scene ended, so she came; Bram was in the village all along.
    assert state.characters["ilse"].location_id == "village"
    assert state.scene.present_ids == ["tomas", "ilse", "bram"]
    assert after.scene.place_id == "farm"  # the state passed in is never touched


def test_a_scene_that_ends_inside_the_place_the_trip_reached_stands():
    played = play(valley(), go("walk to the village", "village", 60))
    inn = PlaceChange(id="inn", name="the Plough", kind="building", parent_id="village")
    after = told(played.state, "inn", places=[inn])

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert state.scene.place_id == "inn" and notes == []


def test_a_scene_that_ends_in_a_corner_of_the_place_they_left_is_put_where_they_went():
    played = play(valley(), go("walk to the village", "village", 60))
    after = told(played.state, "cellar")

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert state.scene.place_id == "village"


def moved_to(state: WorldState, change: PlaceChange, *steps) -> tuple[WorldState, list[str]]:
    """The state once a scene that played `steps` added a place and ended in it."""
    played = play(state, *steps) if steps else None
    before = played.state if played else state
    resolution = played.resolution if played else Resolution(steps=[settled(0, 60)])
    return journeys.settle(before, told(before, change.id, places=[change]), resolution, told=True)


def spot(place_id: str, name: str, setting: str | None = None, **more) -> PlaceChange:
    return PlaceChange(id=place_id, name=name, kind="spot", setting=setting, **more)


def test_a_spot_the_scene_moves_to_without_saying_where_it_lies_is_where_they_were():
    """R8. On the real model (2026-11-11) a place a scene added could lie nowhere, and whoever
    came to the village for the character would not find them at its inn."""
    state = valley()
    state.scene.place_id = state.player.location_id = "village"

    after, notes = moved_to(state, spot("inn", "the Plough", "indoors"))

    assert after.places["inn"].parent_id == "village" and after.scene.place_id == "inn"
    assert notes == ["the scene added 'inn' and not where it lies: within 'village'"]
    assert state.places.get("inn") is None  # the state passed in is never touched
    # So is a place with no setting, and a place under the sky where they were under it too.
    assert moved_to(state, spot("inn", "the Plough"))[0].places["inn"].parent_id == "village"
    state.places["village"].setting = PlaceSetting.OUTDOORS
    square = moved_to(state, spot("square", "the square", "outdoors"))[0]
    assert square.places["square"].parent_id == "village"


def test_a_place_the_scene_put_on_the_map_itself_is_left_where_it_said():
    state = valley()
    state.scene.place_id = state.player.location_id = "village"

    # It said where the place lies, or how far it is.
    told_where = spot("inn", "the Plough", "indoors", parent_id="valley")
    after, notes = moved_to(state, told_where)
    assert after.places["inn"].parent_id == "valley" and notes == []
    far = spot("shrine", "the hill shrine", routes=[Route(to_id="village", travel_s=HOUR)])
    after, notes = moved_to(state, far)
    assert after.places["shrine"].parent_id is None and notes == []

    # A place that was on record before the turn stays as it was.
    state.places["hut"] = Place(id="hut", name="a hut", known_by=["tomas"])
    after, notes = journeys.settle(
        state, told(state, "hut"), Resolution(steps=[settled(0, 60)]), told=True
    )
    assert after.places["hut"].parent_id is None and notes == []


def test_a_new_place_at_the_end_of_a_trip_lies_where_the_trip_went_or_is_the_tellings():
    # The trip reached the village, and the scene ended at a new spot there.
    after, notes = moved_to(
        valley(), spot("inn", "the Plough", "indoors"), go("walk to the village", "village", 60)
    )
    assert after.places["inn"].parent_id == "village" and after.scene.place_id == "inn"

    # A trip to somewhere the record didn't hold: the new place is where it went, apart.
    after, _ = moved_to(
        valley(), spot("mine", "the old mine"), go("walk to the old mine", "the old mine", HOUR)
    )
    assert after.scene.place_id == "mine" and after.places["mine"].parent_id is None

    # A trip that stopped on the way: the place it stopped in is the telling's to put.
    played = stopped_on_the_road()
    camp = spot("camp", "a camp by the road", "outdoors")
    after, _ = journeys.settle(
        played.state, told(played.state, "camp", places=[camp]), played.resolution, told=True
    )
    assert after.places["camp"].parent_id is None


def test_a_place_a_step_names_and_takes_no_real_way_to_is_a_spot_of_where_they_were():
    """R8. "I take a seat outside the Plough and rest there for an hour": the step names a
    place the record doesn't hold, and the hour is the rest, not the way."""
    state = at_the_village()
    inn = spot("inn", "the Plough", "indoors")
    roads = list(state.places["village"].routes)

    rest = step("rest outside the Plough", ActionKind.REST, HOUR, destination="the Plough")
    after, notes = moved_to(state, inn, rest)
    assert after.places["inn"].parent_id == "village"
    assert notes == ["the scene added 'inn' and not where it lies: within 'village'"]
    # An hour's rest is no hour's road.
    assert after.places["inn"].routes == [] and after.places["village"].routes == roads

    # A few steps over to it are no trip either.
    stroll = go("walk over to the Plough", "the Plough", 2 * MINUTE, MOVE)
    assert moved_to(state, inn, stroll)[0].places["inn"].parent_id == "village"

    # A real walk there is: the inn is apart, as far as the walk took.
    after, notes = moved_to(state, inn, go("walk to the Plough", "the Plough", HOUR))
    assert after.places["inn"].parent_id is None and notes == []
    assert route_s(after, "village", "inn") == HOUR

    # After a real walk off the record, a few steps more are still off it.
    after, _ = moved_to(
        state,
        inn,
        go("walk to the old mine", "the old mine", HOUR),
        go("step into its hut", "the hut", MINUTE, MOVE),
    )
    assert after.places["inn"].parent_id is None


def test_a_place_under_the_sky_is_never_put_inside_one_that_may_have_a_roof():
    """R8: out of the temple into the forest it lies in, never a clearing inside the temple."""
    state = valley()
    state.places["forest"] = Place(id="forest", name="the forest", setting="outdoors")
    state.places["temple"] = Place(
        id="temple", name="the temple", setting="underground", parent_id="forest"
    )
    state.places["crypt"] = Place(
        id="crypt", name="the crypt", setting="underground", parent_id="temple"
    )
    state.scene.place_id = state.player.location_id = "crypt"

    out = moved_to(state, spot("clearing", "a clearing", "outdoors"))[0]
    assert out.places["clearing"].parent_id == "forest"
    # Nor one with no setting, which may be under the sky.
    assert moved_to(state, spot("ledge", "a ledge"))[0].places["ledge"].parent_id == "forest"
    # Another chamber lies beside the crypt, within the temple's walls, and a chamber reached
    # from the temple itself lies within it.
    deeper = moved_to(state, spot("vault", "the vault", "underground"))[0]
    assert deeper.places["vault"].parent_id == "temple"
    state.scene.place_id = state.player.location_id = "temple"
    hall = moved_to(state, spot("hall", "the hall", "underground"))[0]
    assert hall.places["hall"].parent_id == "temple"

    # From a place with no setting, a place under the sky lies around it, not in it.
    state.scene.place_id = state.player.location_id = "farm"
    yard = moved_to(state, spot("yard", "the yard", "outdoors"))[0]
    assert yard.places["yard"].parent_id == "valley"
    barn = moved_to(state, spot("barn", "the barn", "indoors"))[0]
    assert barn.places["barn"].parent_id == "farm"
    # With nothing around that isn't closed in, it lies nowhere.
    state.places["temple"].parent_id = None
    state.scene.place_id = state.player.location_id = "crypt"
    lost = moved_to(state, spot("clearing", "a clearing", "outdoors"))
    assert lost[0].places["clearing"].parent_id is None and lost[1] == []


def test_a_scene_nobody_ended_is_put_where_the_trip_went_with_who_is_there():
    played = play(valley(), go("walk to the village", "village", 60))

    state, notes = journeys.settle(played.state, played.state, played.resolution, told=False)

    assert state.scene.place_id == "village" and state.player.location_id == "village"
    assert notes == []
    # Nobody told who came along, so nobody did, and the farm's things stay at the farm.
    assert state.scene.present_ids == ["tomas"]
    assert state.characters["ilse"].location_id == "farm"
    assert state.scene.props == [] and state.scene.positions == []


def test_a_scene_never_ends_in_a_place_the_trip_didnt_reach():
    played = stopped_on_the_road()
    after = told(played.state, "ford")

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert state.scene.place_id == "village" and state.player.location_id == "village"
    assert notes == ["the scene ended in 'ford', which the trip didn't reach: now 'village'"]
    assert state.journey.at_id == "village" and state.journey.left_s == 12 * HOUR


def test_where_a_timed_trip_over_unmapped_ground_ends_is_the_tellings_to_say():
    played = play(valley(), go("walk toward the mill for an hour", "mill", HOUR, timed=True))
    after = told(played.state, "mill")

    state, notes = journeys.settle(played.state, after, played.resolution, told=True)

    assert state.scene.place_id == "mill" and notes == []
    assert not has_route(state, "farm", "mill")  # nobody knows it took the whole hour


def test_another_characters_trip_never_moves_the_players_scene():
    played = play(valley(), go("walk to the village", "village", 60))
    theirs = played.resolution.model_copy(update={"actor_id": "ilse"})

    state, notes = journeys.settle(played.state, played.state, theirs, told=False)

    assert state is played.state and notes == []


# --- new ground ----------------------------------------------------------------------------------


def test_a_trip_over_new_ground_writes_its_route():
    played = play(valley(), go("walk to the old mill", "mill", 50 * MINUTE))
    after = told(played.state, "mill")

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert route_s(state, "farm", "mill") == 50 * MINUTE
    assert route_s(state, "mill", "farm") == 50 * MINUTE  # a road runs both ways
    # So the same trip takes the same time from then on, whatever is proposed.
    again = one(state, go("walk back to the farm", "farm", 5 * MINUTE))
    assert again.duration_s == 50 * MINUTE


def test_a_trip_to_a_place_the_scene_adds_writes_its_route_to_where_the_scene_ended():
    played = play(valley(), go("ride out to the salt marshes", "the salt marshes", 5 * HOUR))
    marsh = PlaceChange(id="marsh", name="the salt marshes", kind="wilds", setting="outdoors")
    after = told(played.state, "marsh", places=[marsh])

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert route_s(state, "farm", "marsh") == 5 * HOUR


def test_a_trip_replaces_a_route_the_telling_gave_for_the_same_way():
    played = play(valley(), go("ride out to the salt marshes", "the salt marshes", 5 * HOUR))
    marsh = PlaceChange(
        id="marsh",
        name="the salt marshes",
        kind="wilds",
        routes=[Route(to_id="farm", travel_s=2 * DAY)],
    )
    after = told(played.state, "marsh", places=[marsh])

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert route_s(state, "farm", "marsh") == 5 * HOUR
    assert route_s(state, "marsh", "farm") == 5 * HOUR


@pytest.mark.parametrize(
    ("to", "seconds", "why"),
    [
        ("cellar", 20 * MINUTE, "a room of the farm is inside it, not a trip away"),
        ("mill", 5 * MINUTE, "a few minutes' walk is a move, not a road"),
        ("village", 60, "the map had the way already"),
    ],
)
def test_no_route_is_written_for(to, seconds, why):
    before = valley()
    played = play(before, go("go", to, seconds, MOVE))
    after = told(played.state, to)

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert {p.id: p.routes for p in state.places.values()} == {
        p.id: p.routes for p in before.places.values()
    }, why


def test_no_route_is_written_from_what_their_own_means_took():
    state = give(valley(), "tomas", Item(id="mare", name="a grey mare", kind=ItemKind.OTHER))
    played = play(state, go("gallop to the mill", "mill", 12 * MINUTE, uses=[item("mare")]))
    after = told(played.state, "mill")

    state, _ = journeys.settle(played.state, after, played.resolution, told=True)

    assert played.resolution.steps[0].trip.by_own_means
    assert not has_route(state, "farm", "mill")  # the mare's time says nothing of the road


def test_what_a_step_does_where_it_went_is_done_there():
    """W1, W2: Tomas walks to Millbrook and knocks old Bram down. It was done in Millbrook,
    before whoever is there, and Ilse, who watched him leave the farm, saw none of it."""
    blow = step(
        "walk to Millbrook and knock old Bram down",
        verb="attack",
        aim=Aim.SUBDUE,
        target_ids=["bram"],
        axis=PowerAxis.MIGHT,
        facts=facts(opposition_ids=["bram"], can_respond=True),
        destination="village",
    )
    state = valley()
    state.characters["bram"].location_id = "village"
    assert "ilse" in state.scene.present_ids
    seed = next(s for s in SEEDS if one(state, blow, seed=s).result is StepResult.SUCCESS)
    played = play(state, blow, seed=seed)

    [done] = played.resolution.steps
    assert done.trip.arrived and [d.place_id for d in done.deeds] == ["village"]
    [deed] = played.state.deeds.values()
    assert deed.place_id == "village" and "ilse" not in deed.witness_ids
    assert played.state.player.location_id == "village"
    # The going itself is done on the way, wherever the record has them when it is recorded.
    ride = go("ride through Millbrook, knocking old Bram down", "village", WALK, verb="attack")
    ride = ride.model_copy(update={"aim": Aim.SUBDUE, "target_ids": ["bram"]})
    assert [d.place_id for d in one(state, ride).deeds] == [None]
