"""R8: where the player character is stays clear. A scene always says where it ends, the record
follows it, and a place knows whether it is under the sky (Miki, 2026-11-08: a scene took the
character from a buried temple to "un claro", and the next one had them still in the temple)."""

from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import PlaceChange, SceneEnd, StateDelta
from engine.looks import place_looks
from engine.samples import cultivation_world
from engine.state import Place, PlaceSetting, SceneFrame, WorldState
from engine.world.geography import find_place
from graph.turn.outputs import NarratorOutput

NARRATOR = DeltaSource.NARRATOR
ENGINE = DeltaSource.ENGINE
UNDERGROUND = PlaceSetting.UNDERGROUND
OUTDOORS = PlaceSetting.OUTDOORS


def buried_temple() -> WorldState:
    """Lin Feng in the hall of a temple buried under the forest on Azure Peak."""
    state = cultivation_world()
    state.places["bosque"] = Place(
        id="bosque",
        name="El Bosque de los Susurros",
        kind="wilds",
        setting=OUTDOORS,
        parent_id="azure-peak",
        known_by=["lin"],
    )
    state.places["templo"] = Place(
        id="templo",
        name="el Templo Subterráneo",
        kind="building",
        setting=UNDERGROUND,
        parent_id="bosque",
        known_by=["lin"],
        visited_by=["lin"],
    )
    state.characters["lin"].location_id = "templo"
    state.scene = SceneFrame(
        place_id="templo",
        present_ids=["lin"],
        ended_on="Lin Feng stands before the stairs that climb toward a thin grey light.",
    )
    return state


def apply(state: WorldState, source: DeltaSource = NARRATOR, **delta):
    return apply_delta(
        state, StateDelta(**delta), TurnContext(story_id="s1", turn=4), source=source
    )


def end(place_id: str | None = None) -> SceneEnd:
    return SceneEnd(ended_on="Birdsong, and the trees close around him.", place_id=place_id)


CLEARING = PlaceChange(
    id="claro",
    name="el claro",
    kind="clearing",
    setting=OUTDOORS,
    parent_id="bosque",
    visited=True,
)


def test_a_scene_that_climbs_out_into_a_clearing_leaves_the_character_there():
    applied = apply(buried_temple(), places=[CLEARING], scene_end=end("claro"))

    state = applied.state
    assert applied.rejected == ()
    assert state.scene.place_id == "claro"
    assert state.player.location_id == "claro"
    assert state.places["claro"].parent_id == "bosque"  # out of the temple, in the forest
    assert state.places["claro"].setting is OUTDOORS
    assert "lin" in state.places["claro"].visited_by


def test_the_character_has_been_where_their_scene_ends_even_unmarked():
    clearing = CLEARING.model_copy(update={"visited": False})
    applied = apply(buried_temple(), places=[clearing], scene_end=end("claro"))
    place = applied.state.places["claro"]
    assert "lin" in place.visited_by and "lin" in place.known_by  # Memory lists it, as been


def test_a_scene_that_ends_in_the_forest_around_the_temple_takes_the_character_out():
    # The forest is known and the temple lies within it: leaving the temple for it is a move,
    # so the record no longer keeps Lin inside the temple.
    applied = apply(buried_temple(), scene_end=end("bosque"))
    assert applied.state.scene.place_id == "bosque"
    assert applied.state.player.location_id == "bosque"


def test_the_scene_place_is_read_by_its_name_or_any_spelling_of_its_id():
    state = buried_temple()
    state.characters["lin"].location_id = "bosque"
    state.scene.place_id = "bosque"
    for ref in ("el Templo Subterráneo", "templo ", "TEMPLO", "el-templo-subterraneo"):
        applied = apply(state, scene_end=end(ref))
        assert applied.rejected == (), ref
        assert applied.state.scene.place_id == "templo", ref
        assert applied.state.player.location_id == "templo", ref


def test_a_scene_end_without_its_place_follows_the_place_the_update_says_they_are_at():
    for ref in (None, "", "the_clearing_beyond"):
        applied = apply(buried_temple(), places=[CLEARING], scene_end=end(ref))
        assert applied.state.scene.place_id == "claro", ref
        assert applied.state.player.location_id == "claro", ref
        assert applied.rejected == (), ref


def test_a_place_nobody_recorded_never_moves_the_scene_and_says_so():
    applied = apply(buried_temple(), scene_end=end("claro"))

    assert applied.state.scene.place_id == "templo"
    assert applied.state.player.location_id == "templo"
    assert applied.state.scene.ended_on == "Birdsong, and the trees close around him."
    [rejection] = applied.rejected
    assert (rejection.subject, rejection.change) == ("scene", "place")


def test_a_scene_that_stays_put_names_its_own_place_or_none():
    for ref in ("templo", None):
        applied = apply(buried_temple(), scene_end=end(ref))
        assert applied.rejected == ()
        assert applied.state.scene.place_id == "templo"
        assert applied.state.player.location_id == "templo"


def test_the_place_they_left_never_stands_for_where_the_scene_ends():
    # The narrator marks the temple it left visited too, and names no place: the clearing wins.
    left = PlaceChange(id="templo", visited=True)
    applied = apply(buried_temple(), places=[CLEARING, left], scene_end=end(None))
    assert applied.state.scene.place_id == "claro"


def test_a_chamber_deeper_in_the_temple_is_still_inside_it():
    chamber = PlaceChange(
        id="camara", name="la cámara de las runas", kind="room", parent_id="templo"
    )
    applied = apply(buried_temple(), places=[chamber], scene_end=end("camara"))

    state = applied.state
    assert state.scene.place_id == "camara"
    assert state.player.location_id == "camara"
    assert state.places["camara"].parent_id == "templo"


def test_a_setting_is_told_once_and_only_the_engine_changes_it():
    state = buried_temple()
    state.places["well"].setting = None

    told = apply(state, places=[PlaceChange(id="well", setting=OUTDOORS)])
    moved = apply(state, places=[PlaceChange(id="templo", setting=OUTDOORS)])
    same = apply(state, places=[PlaceChange(id="templo", setting=UNDERGROUND)])
    caved_in = apply(state, ENGINE, places=[PlaceChange(id="templo", setting=OUTDOORS)])

    assert told.state.places["well"].setting is OUTDOORS
    assert moved.state.places["templo"].setting is UNDERGROUND
    assert [(r.subject, r.change, r.reason) for r in moved.rejected] == [
        ("place templo", "setting", "it is underground")
    ]
    assert same.rejected == ()
    assert caved_in.state.places["templo"].setting is OUTDOORS


def test_find_place_reads_ids_and_names_and_refuses_to_guess():
    places = buried_temple().places
    assert find_place(places, "templo") == "templo"
    assert find_place(places, "  el templo subterraneo ") == "templo"
    assert find_place(places, "El Bosque de los Susurros") == "bosque"
    assert find_place(places, "the inner court") == "inner-court"
    assert find_place(places, "inner_court") == "inner-court"
    assert find_place(places, "") is None
    assert find_place(places, None) is None
    assert find_place(places, "---") is None
    assert find_place(places, "claro") is None
    places["templo-2"] = Place(id="templo-2", name="el Templo Subterráneo")
    assert find_place(places, "el templo subterráneo") is None  # two places by that name
    assert find_place(places, "templo") == "templo"  # an exact id is never in doubt


def test_a_picture_of_a_place_knows_whether_it_is_under_the_sky():
    temple = buried_temple().places["templo"]
    temple.description = "Carved halls lit by blue runes."
    assert place_looks(temple) == "Carved halls lit by blue runes. Underground, with no sky above."
    temple.setting = None
    assert place_looks(temple) == "Carved halls lit by blue runes."
    assert place_looks(Place(id="x", name="X", setting=OUTDOORS)) == (
        "Outdoors, under the open sky."
    )


def test_the_narrator_is_always_asked_where_its_scene_ends():
    schema = NarratorOutput.model_json_schema()
    defs = schema["$defs"]
    assert "update" in schema["required"]
    delta = defs["StateDelta"]
    assert "scene_end" in delta["required"]
    scene_end = defs["SceneEnd"]
    assert scene_end["required"] == ["ended_on", "place_id"]
    assert scene_end["properties"]["place_id"]["type"] == "string"
    assert "setting" in defs["PlaceChange"]["properties"]
    # Code may still leave them out: the engine's own deltas have no scene end.
    assert StateDelta().scene_end is None
    assert SceneEnd(ended_on="x").place_id is None
