"""W10, W4: someone near walks into the scene, when the world allows it.

In the first plays by hand on the real models (2026-11-14) the narrator told someone the
record had elsewhere into four scenes of ninety-nine: a commander whose boots were on the
path, a miller with a broken brace for the smith, a mermaid called from the beach. The record
kept them out, so the story and its Memory parted ways. Code now says who may come
(`engine.world.visits.within_reach`), the record follows the scene for them, and the world
sends them back. The four scenes are played again at the end.
"""

import pytest

from engine import bonds, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import CharacterChange, ProposedDeed, SceneEnd, StateDelta
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

from .test_world import at, ctx, deed_step, idle, play, rng

WALK = 40 * MINUTE  # the farm to Millbrook, by the map
TOLD = "Old Bram leans on the gate and nods at the fence."


def valley() -> WorldState:
    """Tomas and Ilse on the farm, old Bram in Millbrook forty minutes off, the miller three
    hours up the river and a tinker in Harrow, a day down the road from Millbrook. The story
    has shown none of the three."""
    state = farm_world()
    state.places["mill"] = Place(id="mill", name="the Upper Mill", kind="mill", parent_id="valley")
    state.places["farm"].routes.append(Route(to_id="mill", travel_s=3 * HOUR))
    state.places["town"] = Place(id="town", name="Harrow", kind="town", known_by=["tomas"])
    state.places["village"].routes.append(Route(to_id="town", travel_s=DAY))
    state.characters["miller"] = Character(id="miller", name="Hale", age=50, location_id="mill")
    state.characters["tinker"] = Character(id="tinker", name="Jorin", age=40, location_id="town")
    return state


def near(state: WorldState, told: str = TOLD, *, turn: int = 3, meets=()) -> list[str]:
    return visits.within_reach(state, turn, told, meets)


def test_someone_the_scene_names_who_is_near_enough_may_walk_in():
    assert near(valley()) == ["bram"]


def test_a_list_that_names_someone_the_scene_never_told_brings_nobody():
    """The player read nothing of them, so a deed of the next turn would be seen by someone
    they never knew was there."""
    assert near(valley(), "The hens scatter as the gate creaks.") == []


def test_someone_the_scene_has_meet_the_character_is_told_without_a_name():
    """C6: the scene shows someone the character doesn't know by their look, so its words
    can't name them. Its update says the two met."""
    told = "A stooped old man with a stick leans on the gate and nods at the fence."

    assert near(valley(), told) == []
    assert near(valley(), told, meets=["bram"]) == ["bram"]
    assert near(valley(), told, meets=["tinker"]) == []  # a meeting brings nobody from afar


def test_a_word_of_a_name_that_someone_in_the_scene_shares_names_nobody_new():
    state = valley()
    state.characters["bram"].name = "Ilse Marsh"

    assert near(state, "Ilse wipes her hands on her apron.") == []
    assert near(state, "Ilse Marsh stands at the gate with a basket.") == ["bram"]


def test_nobody_crosses_the_map_to_stand_in_a_doorway():
    """A day's way at most: the miller three hours up the river may come, and the tinker a
    day and forty minutes off may not, however long the story has run."""
    state = valley()
    everyone = "Old Bram, Hale and Jorin stand at the gate."

    assert 3 * HOUR <= WALK_IN_MAX_S < DAY + WALK
    assert near(state, everyone) == ["bram", "miller"]
    state.world_s += 30 * DAY
    assert near(state, everyone) == ["bram", "miller"]


def test_nobody_comes_whom_the_character_was_with_too_lately_to_have_made_the_way():
    """W6: the record keeps when the two were last in a scene together. Ten minutes after
    Tomas left the miller at his mill, three hours up the river, the miller isn't at the
    farm gate; that afternoon he may be. Bram, forty minutes off, has an hour's start."""
    state = valley()
    state.world_s = 2 * DAY
    for who in ("bram", "miller"):
        state.characters[who].seen_s = state.world_s - 10 * MINUTE
    both = "Old Bram and Hale stand at the gate."

    assert WALK <= WALK_IN_S < 3 * HOUR
    assert near(state, both) == ["bram"]
    state.world_s += 3 * HOUR
    assert near(state, both) == ["bram", "miller"]


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


def test_nobody_walks_in_on_a_turn_that_put_a_harm_on_record():
    """Who saw it was decided before the scene was told (W2, W17)."""
    state = valley()
    theft = ProposedDeed(kind="steal", text="Tomas takes the feed money", victim_ids=["ilse"])
    state = play(state, deed_step(theft), turn=3).state

    assert near(state, turn=3) == []
    assert near(state, turn=4) == ["bram"]  # the turn after has nothing to walk in on


def test_a_deed_that_harms_nobody_keeps_nobody_out():
    """Asking for something is on record as a deed too (W1), and is nothing to walk in on:
    in the plays the old fisherman's call to the mermaid was one."""
    state = valley()
    asked = ProposedDeed(kind="persuade", text="Tomas asks Ilse for the cart", target_ids=["ilse"])
    state = play(state, deed_step(asked), turn=3).state

    assert state.deeds and near(state, turn=3) == ["bram"]


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
    # Nor while Mara is out of the scene and at its place, where the scene may bring her in.
    state.scene.present_ids = ["tomas"]
    assert near(state, told) == []
    # With Mara somewhere else there is nothing to walk in on: his wife may come.
    state.characters["mara"].location_id = "mill"
    assert near(state, told) == ["ilse"]
    state.characters["mara"].location_id = "village"
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
    delta = StateDelta(scene_end=end)
    return apply_delta(
        state,
        delta,
        ctx(3),
        source=DeltaSource.NARRATOR,
        near=pipeline.within_reach(state, ctx(3), told, delta),
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


# --- The four scenes of the plays (2026-11-14), on their own maps ---------------------------


def told_in(state: WorldState, who: str, told: str, *, met: bool = True):
    """The narrator's scene as the plays had it: its end lists them, and its update has them
    meet the player character."""
    present = [state.player_id, who]
    delta = StateDelta(
        characters=[CharacterChange(id=who, meets_player=True)] if met else [],
        scene_end=SceneEnd(ended_on="They stand face to face.", present_ids=present),
    )
    reach = pipeline.within_reach(state, ctx(3), told, delta)
    return apply_delta(state, delta, ctx(3), source=DeltaSource.NARRATOR, near=reach)


def test_the_miller_brings_the_smith_a_broken_brace():
    """The blacksmith's opening: "a shadow falls across the threshold. It is not Gwenyth, but
    her husband, Aldous the Miller". The record had him at the mill, eighteen minutes off by
    the village. The smith's interest in the miller's wife is on record, and she is at the
    mill, so there is nothing at the forge for her husband to walk in on."""
    state = valley()
    places, people = state.places, state.characters
    places["forge"] = Place(id="forge", name="the Forge", kind="building", parent_id="village")
    places["mill"].parent_id = "village"
    places["village"].routes += [
        Route(to_id="forge", travel_s=360),
        Route(to_id="mill", travel_s=720),
    ]
    people["tomas"].location_id = state.scene.place_id = "forge"
    state.scene.present_ids = ["tomas"]
    people["miller"].name = "Aldous the Miller"
    people["gwenyth"] = Character(id="gwenyth", name="Gwenyth", age=30, location_id="mill")
    for bond_id, a, b, stage in (
        ("bond-2", "gwenyth", "miller", BondStage.MARRIED),
        ("bond-3", "tomas", "gwenyth", BondStage.INTEREST),
    ):
        state.bonds[bond_id] = Bond(
            id=bond_id, a_id=a, b_id=b, stage=stage, steps=[BondStep(stage=stage, how="Before.")]
        )

    applied = told_in(state, "miller", "It is not Gwenyth, but her husband, Aldous the Miller.")

    assert not applied.rejected
    assert applied.came == (("miller", "mill"),)
    assert applied.state.scene.present_ids == ["tomas", "miller"]


def test_the_mermaid_the_old_fisherman_calls_rises_from_the_water():
    """He drags himself to the beach and calls her: "La mirada profunda de la sirena es clava
    en la teva". Her name on record is a few words for her, "La Sirena ferida", which the
    scene never writes with its capital, and the record had her in the open sea, an hour and
    a half off by the map. His call is a deed on record, and harms nobody."""
    state = valley()
    state.places["sea"] = Place(id="sea", name="la mar oberta", kind="wilds")
    state.places["farm"].routes.append(Route(to_id="sea", travel_s=90 * MINUTE))
    state.scene.present_ids = ["tomas"]
    mermaid = Character(id="sirena", name="La Sirena ferida", age=200, location_id="sea")
    mermaid.met_by, mermaid.seen_s = ["tomas"], 0
    state.characters["sirena"] = mermaid
    state.world_s = 8 * 365 * DAY
    call = ProposedDeed(kind="persuade", text="Crido la sirena", target_ids=["sirena"])
    state = play(state, deed_step(call), turn=3).state
    told = "La mirada profunda de la sirena es clava en la teva."

    applied = told_in(state, "sirena", told)

    assert not applied.rejected
    assert applied.came == (("sirena", "sea"),)
    assert state.player_id in applied.state.characters["sirena"].met_by
    # The scene after has her where the record now does, with nothing to decide.
    again = told_in(applied.state, "sirena", told, met=False)
    assert not again.rejected and again.came == ()


def test_the_commander_whose_boots_were_on_the_path_steps_into_the_yard():
    """The sword saint's second scene: "A stern-faced man in the polished armor of a royal
    commander steps into the yard". The two had never met, so the scene shows him by his look
    and its update has them meet, and the record had him at the mountain pass, most of a
    day's ride off."""
    state = valley()
    state.places["pass"] = Place(id="pass", name="the Mountain Pass", kind="wilds")
    state.places["valley"].routes.append(Route(to_id="pass", travel_s=8 * HOUR))
    state.scene.present_ids = ["tomas"]
    state.characters["reynold"] = Character(
        id="reynold", name="Commander Reynold", age=42, location_id="pass"
    )
    told = "A stern-faced man in the polished armor of a royal commander steps into the yard."

    applied = told_in(state, "reynold", told)

    assert not applied.rejected
    assert applied.came == (("reynold", "pass"),)
    assert applied.state.characters["reynold"].location_id == "farm"
    # A scene whose end only lists him, with no word of him and no meeting, has nobody.
    listed = told_in(state, "reynold", "The plum tree drops a leaf.", met=False)
    assert [(r.subject, r.change) for r in listed.rejected] == [("character reynold", "presence")]
