"""W6, W4, W11: whoever the world sends somewhere comes back.

Nobody on record has a home. Before this, a key person's outing took them one place further
each time and never back, whoever came to face the player character stayed at their gate for
good, and a witness who rode off to report lived at the garrison from then on.
"""

from engine import bonds
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ProposedDeed
from engine.director import due as came_due
from engine.samples import farm_world
from engine.state import (
    Bond,
    BondStage,
    BondStep,
    Character,
    CharacterStatus,
    EventStatus,
    Faction,
    Membership,
    Place,
    Prominence,
    Route,
    WorldState,
)
from engine.state.sheet import PassingState
from engine.world import Kind
from engine.world.answers import Answer
from engine.world.events import apply_in_place
from engine.world.returns import left, trip_of
from engine.world.scheduling import World, schedule
from engine.world.tick import _npc_move
from engine.world.tuning import ERRAND_STAY_S, HELD_MAX_S, HELD_S, OUTING_STAY_S

from .test_world import at, ctx, deed_step, idle, moved_on, pending_of, play, rng

WALK = 40 * MINUTE  # the farm to Millbrook, by the map


def valley() -> WorldState:
    """Tomas and Ilse on the farm, old Bram in Millbrook forty minutes off, and Mara, who
    matters to the story, at the farm gate. Harrow is a day down the road from Millbrook."""
    state = farm_world()
    state.characters["mara"] = Character(
        id="mara", name="Mara", age=29, location_id="farm", prominence=Prominence.KEY
    )
    state.places["town"] = Place(id="town", name="Harrow", kind="town", known_by=["tomas"])
    state.places["village"].routes.append(Route(to_id="town", travel_s=DAY))
    state.scene.present_ids = ["tomas"]
    return state


def gone(state: WorldState, who: str, to: str, stay=OUTING_STAY_S):
    """The world moves `who` to `to`, as an outing of their own."""
    person = state.characters[who]
    was, person.location_id = person.location_id, to
    return left(at(state), person, was, stay)


def due(state: WorldState, event) -> WorldState:
    """The world at the moment an event falls due, with the event applied."""
    state.world_s = event.due_s
    return apply_in_place(state, event, ctx(), rng())


def where(state: WorldState, who: str) -> str | None:
    return state.characters[who].location_id


def test_an_outing_is_a_round_trip():
    state = valley()
    back = gone(state, "mara", "village")

    assert back.kind == Kind.RETURN and back.place_id == "farm"
    assert back.payload == {"character_id": "mara", "at_id": "village"}
    low, high = OUTING_STAY_S
    assert low + WALK <= back.due_s - state.world_s <= high + WALK  # her stay, and the way
    assert trip_of(state, "mara") is back
    state, fired = idle(state, back.due_s)
    assert where(state, "mara") == "farm" and trip_of(state, "mara") is None
    assert "Mara comes back to the Weller farm." in [f.text for f in state.facts.values()]


def test_a_key_person_goes_out_and_comes_back_and_goes_no_further_meanwhile():
    """W6. Over a season Mara is at the farm or one outing away from it, never further, and
    every outing ends at the farm."""
    state = valley()
    seen = set()
    for day in range(1, 91):
        state, _ = idle(state, day * DAY, turn=day + 2)
        seen.add(where(state, "mara"))
        trip = trip_of(state, "mara")
        assert (trip is None) == (where(state, "mara") == "farm")
        assert trip is None or trip.place_id == "farm"
    # She went out, to Millbrook or about the valley, and she came home each time. Harrow, a
    # day beyond Millbrook, is two outings away.
    assert seen >= {"farm", "village"} and seen <= {"farm", "village", "valley"}


def test_someone_already_away_makes_no_outing_of_an_outing():
    state = valley()
    gone(state, "mara", "village")
    for seed in range(40):
        again = state.model_copy(deep=True)
        w = World(state=again, ctx=ctx(), at_s=again.world_s, rng=rng().child(seed))
        _npc_move(w, again.characters["mara"])
        assert where(again, "mara") == "village"


def test_a_step_out_of_the_house_is_a_trip_too_and_off_the_map_is_none():
    state = valley()
    out = gone(state, "mara", "valley")  # the farm lies in the valley: a quarter of an hour
    assert out is not None and out.place_id == "farm"
    assert gone(state, "bram", None) is None  # off the map: nowhere to come back from
    assert [e.payload["character_id"] for e in pending_of(state, Kind.RETURN)] == ["mara"]


def test_going_on_somewhere_else_keeps_where_they_first_set_out_from():
    state = valley()
    first = gone(state, "mara", "village")
    state.world_s += 2 * HOUR
    second = gone(state, "mara", "town", ERRAND_STAY_S)

    assert second is first and first.place_id == "farm"
    assert first.payload["at_id"] == "town"
    assert first.due_s - state.world_s >= ERRAND_STAY_S[0] + DAY + WALK  # from Harrow now
    # And a move that brings them back ends the trip.
    assert gone(state, "mara", "farm") is None
    assert first.status is EventStatus.CANCELLED and trip_of(state, "mara") is None


def test_nothing_brings_back_someone_the_story_took_elsewhere():
    """A companion who left Millbrook with the player character is where the story has them."""
    state = valley()
    back = gone(state, "mara", "village")
    state.characters["mara"].location_id = "town"  # the scene took her along

    state = due(state, back)

    assert where(state, "mara") == "town" and trip_of(state, "mara") is None
    assert back.status is EventStatus.CANCELLED


def test_the_scene_holds_whoever_is_in_it():
    state = valley()
    back = gone(state, "mara", "village")
    state.characters["tomas"].location_id = state.scene.place_id = "village"
    state.scene.present_ids = ["tomas", "mara"]

    state = due(state, back)

    later = trip_of(state, "mara")
    assert where(state, "mara") == "village" and later is not None
    assert later.due_s == back.due_s + HELD_S + WALK and later.place_id == "farm"
    state.scene.present_ids = ["tomas"]
    assert where(due(state, later), "mara") == "farm"


def test_nobody_bound_or_senseless_walks_home():
    """They are asked for again a day later, then after as long again as they have been
    held, and weekly at the most: a year in a cell is no year of daily events (K8)."""
    state = valley()
    back = first = gone(state, "mara", "village")
    state.characters["mara"].sheet.condition.states.append(PassingState(name="bound"))

    waits = []
    for _ in range(6):
        state = due(state, back)
        assert where(state, "mara") == "village" and back.status is EventStatus.CANCELLED
        back = trip_of(state, "mara")
        waits.append(back.due_s - state.world_s - WALK)  # the way home comes on top
        assert waits[-1] == min(max(HELD_S, state.world_s - first.due_s), HELD_MAX_S)
    assert waits[0] == HELD_S and waits == sorted(waits) and waits[-2:] == [HELD_MAX_S] * 2
    assert back.payload["held_s"] == first.due_s
    # Freed, she walks home when she is next due.
    state.characters["mara"].sheet.condition.states.clear()
    assert where(due(state, back), "mara") == "farm"


def test_an_errand_still_to_come_holds_them_until_it_is_done():
    state = valley()
    back = gone(state, "mara", "village")
    errand = schedule(
        at(state),
        Kind.ANSWER,
        back.due_s + 3 * DAY,
        title="Mara comes for Tomas",
        payload={"answer": Answer.CONFRONT.value, "avenger_id": "mara", "target_id": "tomas"},
    )

    state = due(state, back)

    later = trip_of(state, "mara")
    assert where(state, "mara") == "village"
    assert later.due_s == errand.due_s + HELD_S + WALK


def test_the_dead_come_back_nowhere():
    state = valley()
    back = gone(state, "mara", "village")
    state.characters["mara"].status = CharacterStatus.DEAD

    state = due(state, back)

    assert where(state, "mara") == "village" and trip_of(state, "mara") is None


def test_whoever_is_there_sees_them_come_home_and_only_when_they_did():
    """A return is something the world did where they set out from, so a scene there shows
    it. One that brought nobody back came to nothing, and no scene is told they came."""
    state = valley()
    back = gone(state, "mara", "village")
    held = state.model_copy(deep=True)

    state = due(state, back)

    assert where(state, "mara") == "farm"
    assert [e.id for e in came_due.in_sight(state, ctx())] == [back.id]
    assert back.title == "Mara comes back to the Weller farm"
    # Bound in Millbrook she comes nowhere, and the farm sees nobody at its gate.
    back = trip_of(held, "mara")
    held.characters["mara"].sheet.condition.states.append(PassingState(name="bound"))
    held = due(held, back)
    assert back.status is EventStatus.CANCELLED and came_due.in_sight(held, ctx()) == ()
    # Nor does Millbrook see her go: where she is stays off the page until a scene has her.
    away = valley()
    back = gone(away, "mara", "village")
    away.characters["tomas"].location_id = away.scene.place_id = "village"
    away = due(away, back)
    assert where(away, "mara") == "farm" and came_due.in_sight(away, ctx()) == ()


# --- errands (W4, W11) ------------------------------------------------------------------------


def husband(state: WorldState) -> WorldState:
    """Mara is married to Jorn, the Millbrook smith, who is at his forge."""
    state.characters["mara"].location_id = "village"
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    state.bonds["bond-2"] = Bond(
        id="bond-2",
        a_id="jorn",
        b_id="mara",
        stage=BondStage.MARRIED,
        steps=[BondStep(stage=BondStage.MARRIED, how="As the story opens.")],
    )
    return state


def test_whoever_came_to_have_it_out_goes_home_afterwards():
    """W4. Jorn saw Tomas court his wife in Millbrook, and comes to the farm to have it out.
    Before this he stayed at the farm gate for good, on record."""
    state = husband(valley())
    state.characters["tomas"].location_id = state.scene.place_id = "village"
    state.scene.present_ids = ["tomas", "mara", "jorn"]
    affair = ProposedDeed(
        kind="court",
        text="Tomas courts Mara",
        target_ids=["mara"],
        wronged_ids=["jorn"],
        severity=bonds.AFFAIR,
    )
    state = play(state, deed_step(affair)).state
    state.characters["tomas"].location_id = state.scene.place_id = "farm"
    state = moved_on(state)
    (coming,) = pending_of(state, Kind.ANSWER)
    coming.place_id = "farm"  # he knows where Tomas lives
    coming.due_s += WALK

    state, fired = idle(state, coming.due_s)

    assert [e.needs_player for e in fired if e.kind == Kind.ANSWER] == [True]
    assert where(state, "jorn") == "farm"
    home = trip_of(state, "jorn")
    assert home is not None and home.place_id == "village"
    low, high = ERRAND_STAY_S
    assert low + WALK <= home.due_s - state.world_s <= high + WALK
    state, _ = idle(state, home.due_s)
    assert where(state, "jorn") == "village" and trip_of(state, "jorn") is None


def test_whoever_brought_word_to_the_garrison_goes_home_afterwards():
    """W11. Old Bram sees a killing in Millbrook and takes it to the wardens in Harrow, a
    day's ride off. Before this he lived at the garrison from then on."""
    state = valley()
    state.factions["wardens"] = Faction(id="wardens", name="the Wardens", kind="law")
    state.places["town"].controller_id = "wardens"
    state.places["village"].controller_id = "wardens"
    state.characters["captain"] = Character(
        id="captain",
        name="Captain Orrin",
        location_id="town",
        memberships=[Membership(faction_id="wardens", rank="captain")],
    )
    state.factions["wardens"].leader_ids = ["captain"]
    state.characters["pedlar"] = Character(id="pedlar", name="Pedlar", location_id="village")
    state.characters["tomas"].location_id = state.scene.place_id = "village"
    state.scene.present_ids = ["tomas", "bram", "pedlar"]
    killing = ProposedDeed(kind="kill", text="Tomas kills the pedlar", victim_ids=["pedlar"])
    state = moved_on(play(state, deed_step(killing, dead=("pedlar",))).state)

    reports = [e for e in pending_of(state, Kind.REPORT) if e.payload.get("moves")]
    assert [e.payload["witness_id"] for e in reports] == ["bram"]
    state, _ = idle(state, reports[0].due_s)
    assert where(state, "bram") == "town"
    home = trip_of(state, "bram")
    assert home is not None and home.place_id == "village"
    state, _ = idle(state, home.due_s)
    assert where(state, "bram") == "village"
