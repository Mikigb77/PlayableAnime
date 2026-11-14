"""W10, W4: someone near walks into the scene, when the world allows it.

In the first plays by hand on the real models (2026-11-14) the narrator told someone the
record had elsewhere into four scenes of ninety-nine: a commander whose boots were on the
path, a miller with a broken brace for the smith. The record kept them out, so the story and
its Memory parted ways. Code now says who may come (`engine.world.visits.within_reach`), the
record follows the scene for them, and the world sends them back.
"""

import pytest

from engine import bonds, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ProposedDeed, Resolution, SceneEnd, StateDelta
from engine.samples import farm_world
from engine.state import (
    Bond,
    BondStage,
    BondStep,
    Character,
    CharacterStatus,
    Encounter,
    EncounterKind,
    Place,
    Route,
    WorldState,
)
from engine.state.sheet import PassingState
from engine.world import Kind, visits
from engine.world.answers import Answer
from engine.world.returns import left, trip_of
from engine.world.scheduling import schedule
from engine.world.tuning import OUTING_STAY_S, VISIT_STAY_S, WALK_IN_MAX_S, WALK_IN_S

from .test_world import at, ctx, deed_step, idle, play, rng, settled

WALK = 40 * MINUTE  # the farm to Millbrook, by the map
TOLD = "Old Bram leans on the gate and nods at the fence."


def valley() -> WorldState:
    """Tomas and Ilse on the farm, old Bram in Millbrook forty minutes off, the miller three
    hours up the river and a tinker in Harrow, a day down the road from Millbrook."""
    state = farm_world()
    state.places["mill"] = Place(id="mill", name="the Upper Mill", kind="mill", parent_id="valley")
    state.places["farm"].routes.append(Route(to_id="mill", travel_s=3 * HOUR))
    state.places["town"] = Place(id="town", name="Harrow", kind="town", known_by=["tomas"])
    state.places["village"].routes.append(Route(to_id="town", travel_s=DAY))
    state.characters["miller"] = Character(id="miller", name="Hale", age=50, location_id="mill")
    state.characters["tinker"] = Character(id="tinker", name="Jorin", age=40, location_id="town")
    return state


def took(duration_s: int = 0) -> Resolution:
    return Resolution(steps=[settled(duration_s)])


def near(state: WorldState, told: str = TOLD, *, duration_s: int = 0, turn: int = 3) -> list[str]:
    return visits.within_reach(state, took(duration_s), turn, told)


def test_someone_the_scene_names_who_is_near_enough_may_walk_in():
    assert near(valley()) == ["bram"]


def test_a_list_that_names_someone_the_scene_never_told_brings_nobody():
    """The player read nothing of them, so a deed of the next turn would be seen by someone
    they never knew was there."""
    assert near(valley(), "The hens scatter as the gate creaks.") == []


def test_a_word_of_a_name_that_someone_in_the_scene_shares_names_nobody_new():
    state = valley()
    state.characters["bram"].name = "Ilse Marsh"

    assert near(state, "Ilse wipes her hands on her apron.") == []
    assert near(state, "Ilse Marsh stands at the gate with a basket.") == ["bram"]


def test_nobody_crosses_the_map_to_stand_in_a_doorway():
    """The way has to fit in the time the turn took, with an hour's start, and in a day at
    most: a month gone by brings in nobody from a day and forty minutes off."""
    state = valley()
    everyone = "Old Bram, Hale and Jorin stand at the gate."

    assert WALK <= WALK_IN_S < 3 * HOUR
    assert near(state, everyone) == ["bram"]
    assert near(state, everyone, duration_s=2 * HOUR) == ["bram", "miller"]
    assert near(state, everyone, duration_s=30 * DAY) == ["bram", "miller"]
    assert WALK_IN_MAX_S < DAY + WALK


def test_someone_off_the_map_comes_from_nowhere_the_scene_can_reach():
    state = valley()
    state.places["isle"] = Place(id="isle", name="the Isle", kind="island")
    state.characters["bram"].location_id = "isle"

    assert near(state) == []


@pytest.mark.parametrize("held", ["dead", "missing", "asleep", "answer", "report", "outing"])
def test_nobody_comes_whom_something_holds(held):
    """The dead and the missing, someone in no state to walk, and someone on an errand or a
    round trip of the world's making, whose comings and goings are the world's to time."""
    state = valley()
    bram = state.characters["bram"]
    if held == "dead":
        bram.status = CharacterStatus.DEAD
    elif held == "missing":
        bram.status = CharacterStatus.MISSING
    elif held == "asleep":
        bram.sheet.condition.states.append(PassingState(name="asleep"))
    elif held == "answer":
        payload = {"answer": Answer.CONFRONT.value, "avenger_id": "bram", "target_id": "tomas"}
        schedule(at(state), Kind.ANSWER, state.world_s + DAY, title="Bram comes", payload=payload)
    elif held == "report":
        payload = {"witness_id": "bram"}
        schedule(at(state), Kind.REPORT, state.world_s + DAY, title="Bram tells", payload=payload)
    else:  # he came to the mill on an outing of his own, and goes home from there
        bram.location_id = "mill"
        state.places["mill"].routes.append(Route(to_id="farm", travel_s=WALK))
        assert left(at(state), bram, "village", OUTING_STAY_S) is not None

    assert near(state) == []


def test_nobody_walks_in_on_a_turn_that_put_a_deed_on_record():
    """Who saw it was decided before the scene was told (W2, W17)."""
    state = valley()
    theft = ProposedDeed(kind="steal", text="Tomas takes the feed money", victim_ids=["ilse"])
    state = play(state, deed_step(theft), turn=3).state

    assert near(state, turn=3) == []
    assert near(state, turn=4) == ["bram"]  # the turn after has nothing to walk in on


def test_nobody_walks_into_a_fight_a_chase_or_talks():
    state = valley()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["ilse"], started_turn=2, started_s=0
    )

    assert near(state) == []


def test_nobody_walks_in_on_a_romance_that_wrongs_them():
    """W17. In the first stories about an affair on the real model (2026-11-13) the narrator
    walked the wronged wife into the scene from forty minutes away. Who walks in on a romance
    is the engine's to decide, by who sees a move, so she stays where the record has her."""
    state = valley()
    state.characters["mara"] = Character(id="mara", name="Mara", age=29, location_id="village")
    state.characters["tomas"].location_id = state.scene.place_id = "village"
    state.scene.present_ids = ["tomas", "mara"]
    state.characters["ilse"].location_id = "farm"
    told = "Ilse Weller comes round the corner of the mill with a basket."

    assert near(state, told) == ["ilse"]  # nothing between Tomas and Mara: his wife may come

    state.bonds["bond-2"] = Bond(
        id="bond-2",
        a_id="tomas",
        b_id="mara",
        stage=BondStage.COURTING,
        steps=[BondStep(stage=BondStage.COURTING, how="He walked her home.")],
    )
    assert bonds.wronged(state, "tomas", "mara") == ["ilse"]
    assert near(state, told) == []
    # Nor while Mara is out of the scene: a romance of his is the engine's to bring to light.
    state.scene.present_ids = ["tomas"]
    assert near(state, told) == []
    # One between two others of the scene keeps out whom it wrongs, and nobody else.
    del state.bonds["bond-2"]
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=30, location_id="village")
    state.scene.present_ids = ["tomas", "mara", "jorn"]
    state.bonds["bond-3"] = Bond(
        id="bond-3",
        a_id="mara",
        b_id="bram",
        stage=BondStage.TOGETHER,
        steps=[BondStep(stage=BondStage.TOGETHER, how="As the story opens.")],
    )
    state.bonds["bond-4"] = Bond(
        id="bond-4",
        a_id="jorn",
        b_id="mara",
        stage=BondStage.COURTING,
        steps=[BondStep(stage=BondStage.COURTING, how="He brought her flowers.", world_s=5)],
    )
    state.characters["bram"].location_id = "farm"
    assert near(state, "Old Bram and Ilse Weller come round the corner.") == ["ilse"]


def walked_in(state: WorldState, told: str = TOLD):
    """A narrated scene ends with Bram in it, on a turn that lets him come."""
    end = SceneEnd(ended_on="Bram leans on the gate.", present_ids=["tomas", "ilse", "bram"])
    return apply_delta(
        state,
        StateDelta(scene_end=end),
        ctx(3),
        source=DeltaSource.NARRATOR,
        near=pipeline.within_reach(state, took(), ctx(3), told),
    )


def test_the_record_follows_a_scene_that_has_them_and_the_world_sends_them_back():
    state = valley()

    applied = walked_in(state)

    assert not applied.rejected
    assert applied.came == (("bram", "village"),)
    assert applied.state.characters["bram"].location_id == "farm"
    assert applied.state.scene.present_ids == ["tomas", "ilse", "bram"]

    state = pipeline.settle_walk_ins(applied.state, applied.came, ctx(3), rng(3))
    home = trip_of(state, "bram")
    assert home is not None and home.kind == Kind.RETURN and home.place_id == "village"
    low, high = VISIT_STAY_S
    assert low + WALK <= home.due_s - state.world_s <= high + WALK  # his stay, and the way

    state.scene.present_ids = ["tomas", "ilse"]  # the scenes that follow no longer show him
    state, _ = idle(state, home.due_s)
    assert state.characters["bram"].location_id == "village"
    assert trip_of(state, "bram") is None


def test_nobody_came_leaves_the_state_as_it_was():
    state = valley()

    applied = walked_in(state, "The hens scatter as the gate creaks.")

    assert applied.came == ()
    assert applied.state.characters["bram"].location_id == "village"
    assert [(r.subject, r.change) for r in applied.rejected] == [("character bram", "presence")]
    assert pipeline.settle_walk_ins(applied.state, applied.came, ctx(3), rng(3)) is applied.state
