"""W2, C6: someone who arrives hears what the place is saying (Miki, 2026-11-11: "maybe you
reach a new city, you hear some rumor"). Word that reached a place before the player character
is told to them as they get there, a few things at a time, and Memory keeps it."""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ActionKind, Intent
from engine.director import rules
from engine.state import Deed, PendingEvent, Place, Rumor, WorldState
from engine.visibility import memory_view
from engine.world import hearsay
from engine.world.rumors import Certainty
from engine.world.scheduling import World
from engine.world.tuning import TALK_FRESH_S, TALK_HEARD
from tests.engine.resolve.power_worlds import stop_time
from tests.engine.resolve.worlds import ctx, resolve, rng, sect, step
from tests.engine.test_journeys import MOVE, ROAD, WALK, after_scene, go, play, valley

NOON = 6 * HOUR  # the story's clock when the tests start: word older than this is from before


@pytest.fixture(autouse=True)
def quiet_road(monkeypatch):
    """Nothing the road brings stops a trip here (W16): these tests are about arriving."""
    monkeypatch.setattr(rules, "ROAD_MIN_S", 10**12)


def word(state: WorldState, rumor_id: str, text: str, *reached: str, **kwargs) -> Rumor:
    """Something people are saying in the places given, since `started_s`."""
    kwargs.setdefault("is_true", True)
    kwargs.setdefault("started_s", state.world_s)
    rumor = Rumor(id=rumor_id, text=text, reached_place_ids=list(reached), **kwargs)
    state.rumors[rumor.id] = rumor
    return rumor


def talking() -> WorldState:
    """The valley at noon, with Millbrook talking about the miller's barn."""
    state = valley()
    state.world_s = NOON
    word(state, "barn", "The miller's barn burned down in the night.", "village")
    return state


def heard(played: pipeline.PlayOut) -> list[str]:
    return played.resolution.steps[-1].trip.heard_ids


def to_the_village(state: WorldState) -> pipeline.PlayOut:
    return play(state, go("walk to the village", "village", 60))


def arrive(state: WorldState, to: str) -> tuple[list[str], WorldState]:
    """What they hear on a trip to `to`, and the state once the scene has ended there."""
    played = play(state, go(f"go to {to}", to, 60))
    return heard(played), after_scene(state, played, to)


def test_someone_who_arrives_hears_what_the_place_is_saying():
    played = to_the_village(talking())

    assert heard(played) == ["barn"]
    assert played.state.rumors["barn"].heard_at == {"tomas": NOON + WALK}
    # C6: it is in what they know, as something only heard.
    (entry,) = memory_view(played.state).rumors
    assert entry.text == "The miller's barn burned down in the night."
    assert entry.certainty is Certainty.UNCONFIRMED


def test_nothing_is_heard_twice_or_from_somewhere_else():
    state = talking()
    word(state, "duke", "The duke is dead.", "city")

    there, state = arrive(state, "village")
    home, state = arrive(state, "farm")
    back, state = arrive(state, "village")
    on, state = arrive(state, "city")

    assert there == ["barn"]  # the city's talk stays in the city
    assert home == [] and back == []
    assert on == ["duke"]


def test_old_news_and_another_timelines_word_are_not_the_talk_of_the_place():
    state = valley()
    state.world_s = TALK_FRESH_S + DAY
    word(state, "old", "A cow was stolen.", "village", started_s=0)
    word(state, "elsewhen", "The well ran dry.", "village", timeline_id="branch-2")
    word(state, "fresh", "The bridge is out.", "village", started_s=2 * DAY)

    assert heard(to_the_village(state)) == ["fresh"]


def test_a_place_tells_a_few_things_at_a_time_the_newest_first():
    state = talking()
    for hour in range(1, 5):
        word(state, f"word-{hour}", f"News number {hour}.", "village", started_s=hour * HOUR)

    first, state = arrive(state, "village")
    _, state = arrive(state, "farm")
    again, state = arrive(state, "village")

    assert len(first) == TALK_HEARD == 3
    assert first == ["barn", "word-4", "word-3"]
    assert again == ["word-2", "word-1"]  # the rest is still talk the next time they come


def test_word_that_reached_the_land_around_is_said_in_the_places_within_it():
    state = valley()
    word(state, "flood", "The river is rising.", "valley")

    assert heard(to_the_village(state)) == ["flood"]


def test_a_deed_is_told_once_in_its_best_telling():
    state = talking()
    state.rumors.clear()
    state.deeds["raid"] = Deed(
        id="raid", actor_id="bram", kind="theft", text="Bram stole a cart", turn=1, world_s=0
    )
    word(state, "vague", "Word has it that someone stole a cart.", "valley", deed_id="raid")
    word(state, "named", "Bram stole a cart.", "village", deed_id="raid", about_ids=["bram"])
    state.rumors["vague"].accuracy = 40

    first, state = arrive(state, "village")
    _, state = arrive(state, "farm")
    again, state = arrive(state, "village")

    assert first == ["named"]
    assert again == []  # the vaguer telling says nothing new


def test_what_they_did_themselves_comes_after_the_news_and_they_know_it_is_so():
    state = talking()
    state.deeds["fire"] = Deed(
        id="fire", actor_id="tomas", kind="arson", text="Tomas burned the mill", turn=1, world_s=0
    )
    word(state, "mill", "Word has it that someone burned the mill.", "village", deed_id="fire")
    state.rumors["mill"].started_s = NOON + 1  # the newer of the two, and still told second

    played = to_the_village(state)

    assert heard(played) == ["barn", "mill"]
    told = {entry.id: entry.certainty for entry in memory_view(played.state).rumors}
    assert told == {"barn": Certainty.UNCONFIRMED, "mill": Certainty.CONFIRMED}


def test_a_trip_that_stops_on_the_way_hears_nothing_yet():
    state = talking()
    state.pending_events = {
        "riders": PendingEvent(
            id="riders", kind="test", due_s=NOON + 10 * MINUTE, needs_player=True
        )
    }

    played = to_the_village(state)

    assert played.resolution.steps[0].trip.arrived is False
    assert heard(played) == [] and played.state.rumors["barn"].heard_at == {}


def test_someone_who_went_there_to_do_something_else_hears_it_too():
    night = step("sleep at the inn in Millbrook", ActionKind.REST, 8 * HOUR, destination="village")

    played = play(talking(), night)

    assert heard(played) == ["barn"] and not played.resolution.steps[0].trip.first_visit


def test_nobody_talks_while_time_stands_still():
    state = sect()
    state.places["gate"] = Place(id="gate", name="the gate", kind="gate", parent_id="well")
    word(state, "elder", "An elder has gone missing.", "gate")
    step_in = go("step through the gate", "gate", 1, MOVE, proposed_personal_s=1)

    resolution = resolve(state, Intent(steps=[stop_time(), step_in]))
    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert played.resolution.steps[1].trip.arrived
    assert heard(played) == [] and played.state.rumors["elder"].heard_at == {}


def test_the_talk_of_a_place_is_what_reached_it_in_the_order_it_is_heard():
    state = talking()
    word(state, "duke", "The duke is dead.", "city")
    w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())

    assert [r.id for r in hearsay.talk_of(state, "tomas", "village", NOON)] == ["barn"]
    assert hearsay.talk_of(state, "tomas", None, NOON) == []
    assert hearsay.on_arrival(w, "tomas", "city") == ["duke"]
    assert state.rumors["duke"].believed_by == ["tomas"]


# --- a place they have never seen ----------------------------------------------------------------


def test_a_first_visit_is_a_place_on_record_they_have_never_been_to():
    village = to_the_village(valley())
    city = play(valley(), go("ride to Harrowgate", "city", HOUR))

    assert not village.resolution.steps[0].trip.first_visit  # Tomas knows Millbrook well
    assert city.resolution.steps[0].trip.first_visit
    assert city.resolution.steps[0].duration_s == WALK + ROAD


def test_a_place_the_record_doesnt_hold_is_a_first_visit_only_after_a_real_trip():
    far = play(valley(), go("walk to the salt marshes", "the salt marshes", 5 * HOUR))
    near = play(valley(), go("cross to the well", "the well", MINUTE, MOVE))

    assert far.resolution.steps[0].trip.first_visit
    assert not near.resolution.steps[0].trip.first_visit
