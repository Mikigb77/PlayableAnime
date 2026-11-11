"""W2, C6: what a place is saying, heard softly (Miki, 2026-11-11: "don't force it, like arriving
at a place, immediately hearing stuff ... if there is a rumor in a place, we might hear it at
some point ... and you might miss some rumors, that's also okay"). Nothing is heard by
arriving. A place has its talk, a scene may tell one piece of it, and only what a scene told is
heard, so Memory never lists what no scene said."""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import DirectorPlan, PlannedTalk
from engine.director import rules
from engine.state import Deed, Rumor, WorldState
from engine.visibility import memory_view
from engine.world import hearsay
from engine.world.rumors import Certainty
from engine.world.scheduling import World
from engine.world.tuning import TALK_FRESH_S
from tests.engine.resolve.worlds import ctx, rng
from tests.engine.test_journeys import MOVE, ROAD, WALK, go, play, valley

NOON = 6 * HOUR  # the story's clock when the tests start: word older than this is from before


@pytest.fixture(autouse=True)
def quiet_road(monkeypatch):
    """Nothing the road brings stops a trip here (W16): these tests are about being somewhere."""
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


def talk(state: WorldState, place_id: str | None = "village") -> list[str]:
    """What the place has to tell Tomas, in the order it would reach him."""
    return [r.id for r in hearsay.talk_of(state, "tomas", place_id, state.world_s)]


def hear(state: WorldState, rumor_id: str) -> bool:
    w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())
    return hearsay.hear(w, "tomas", rumor_id)


def told(state: WorldState, rumor_id: str | None) -> WorldState:
    """The state once a scene told the talk the director offered it."""
    plan = DirectorPlan(talk=PlannedTalk(rumor_id=rumor_id))
    return pipeline.hear_talk(state, plan, ctx(), rng())


# --- what a place is saying ----------------------------------------------------------------------


def test_someone_who_arrives_hears_nothing_by_arriving():
    played = play(talking(), go("walk to the village", "village", 60))

    assert played.resolution.steps[-1].trip.arrived
    assert played.state.rumors["barn"].heard_at == {}
    assert memory_view(played.state).rumors == []
    assert talk(played.state) == ["barn"]  # it is still there to be heard


def test_the_talk_of_a_place_is_what_reached_it():
    state = talking()
    word(state, "duke", "The duke is dead.", "city")

    assert talk(state) == ["barn"]  # the city's talk stays in the city
    assert talk(state, "city") == ["duke"]
    assert talk(state, None) == [] and talk(state, "nowhere on record") == []


def test_old_news_and_another_timelines_word_are_not_the_talk_of_the_place():
    state = valley()
    state.world_s = TALK_FRESH_S + DAY
    word(state, "old", "A cow was stolen.", "village", started_s=0)
    word(state, "elsewhen", "The well ran dry.", "village", timeline_id="branch-2")
    word(state, "fresh", "The bridge is out.", "village", started_s=2 * DAY)

    assert talk(state) == ["fresh"]


def test_the_newest_word_comes_first():
    state = talking()
    for hour in range(1, 4):
        word(state, f"word-{hour}", f"News number {hour}.", "village", started_s=hour * HOUR)

    assert talk(state) == ["barn", "word-3", "word-2", "word-1"]


def test_word_that_reached_the_land_around_is_said_in_the_places_within_it():
    state = valley()
    word(state, "flood", "The river is rising.", "valley")

    assert talk(state) == ["flood"]


def test_a_deed_is_told_once_in_its_best_telling():
    state = valley()
    state.deeds["raid"] = Deed(
        id="raid", actor_id="bram", kind="theft", text="Bram stole a cart", turn=1, world_s=0
    )
    word(state, "vague", "Word has it that someone stole a cart.", "valley", deed_id="raid")
    word(state, "named", "Bram stole a cart.", "village", deed_id="raid", about_ids=["bram"])
    state.rumors["vague"].accuracy = 40

    assert talk(state) == ["named"]
    assert hear(state, "named")
    assert talk(state) == []  # the vaguer telling says nothing new


def test_what_they_did_themselves_comes_after_the_news():
    state = talking()
    state.deeds["fire"] = Deed(
        id="fire", actor_id="tomas", kind="arson", text="Tomas burned the mill", turn=1, world_s=0
    )
    word(state, "mill", "Word has it that someone burned the mill.", "village", deed_id="fire")
    state.rumors["mill"].started_s = NOON + 1  # the newer of the two, and still told second

    assert talk(state) == ["barn", "mill"]


# --- only what a scene told is heard -------------------------------------------------------------


def test_talk_a_scene_told_is_heard_and_memory_keeps_it():
    state = talking()

    after = told(state, "barn")

    assert after.rumors["barn"].heard_at == {"tomas": NOON}
    assert after.rumors["barn"].believed_by == ["tomas"]
    assert state.rumors["barn"].heard_at == {}  # the state it was given is left as it was
    # C6: it is in what they know, as something only heard.
    (entry,) = memory_view(after).rumors
    assert entry.text == "The miller's barn burned down in the night."
    assert entry.certainty is Certainty.UNCONFIRMED


def test_what_is_said_of_their_own_deed_is_known_to_be_so():
    state = talking()
    state.deeds["fire"] = Deed(
        id="fire", actor_id="tomas", kind="arson", text="Tomas burned the mill", turn=1, world_s=0
    )
    word(state, "mill", "Word has it that someone burned the mill.", "village", deed_id="fire")

    after = told(state, "mill")

    (entry,) = memory_view(after).rumors
    assert entry.certainty is Certainty.CONFIRMED


def test_nothing_is_recorded_for_talk_the_story_made_up_or_the_record_doesnt_hold():
    state = talking()

    assert told(state, None) is state  # talk of the narrator's own making is no rumor
    assert told(state, "no-such-rumor") is state
    assert pipeline.hear_talk(state, DirectorPlan(), ctx(), rng()) is state


def test_nothing_is_heard_twice():
    state = talking()

    assert hear(state, "barn")
    assert not hear(state, "barn") and not hear(state, "no-such-rumor")
    assert told(state, "barn") is state
    assert talk(state) == []


# --- a place they have never seen ----------------------------------------------------------------


def test_a_first_visit_is_a_place_on_record_they_have_never_been_to():
    village = play(valley(), go("walk to the village", "village", 60))
    city = play(valley(), go("ride to Harrowgate", "city", HOUR))

    assert not village.resolution.steps[0].trip.first_visit  # Tomas knows Millbrook well
    assert city.resolution.steps[0].trip.first_visit
    assert city.resolution.steps[0].duration_s == WALK + ROAD


def test_a_place_the_record_doesnt_hold_is_a_first_visit_only_after_a_real_trip():
    far = play(valley(), go("walk to the salt marshes", "the salt marshes", 5 * HOUR))
    near = play(valley(), go("cross to the well", "the well", MINUTE, MOVE))

    assert far.resolution.steps[0].trip.first_visit
    assert not near.resolution.steps[0].trip.first_visit
