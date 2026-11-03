"""M1, M4, M5: a place or a face that changes for good gets a new look version, so its picture is
drawn once more; anything less keeps the picture it has."""

from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, PlaceChange, StateDelta
from engine.looks import (
    appearance_changed,
    changes_look,
    life_stage,
    place_looks,
    place_version,
)
from engine.samples import cultivation_world
from engine.state import Cause, CauseMechanism, CauseRef, Deed, PlaceStatus, WorldState


def apply(state: WorldState, source=DeltaSource.NARRATOR, **delta) -> WorldState:
    applied = apply_delta(
        state, StateDelta(**delta), TurnContext(story_id="s1", turn=3), source=source
    )
    assert not applied.rejected, applied.rejected
    return applied.state


def look(state: WorldState, character_id: str = "lin", **change) -> WorldState:
    return apply(state, characters=[CharacterChange(id=character_id, **change)])


def test_the_same_look_in_other_words_is_no_change():
    kept = "16, slight, black hair tied back, steady eyes."

    assert not appearance_changed(kept, "Slight and 16, with steady eyes and black hair tied back")
    assert not appearance_changed("", "16, slight")  # written for the first time
    assert not appearance_changed(kept, "")
    assert appearance_changed(kept, "16, slight, black hair tied back, one eye lost.")
    assert appearance_changed(kept, "16, slight, steady eyes.")  # something no longer shows


def test_old_age_is_a_new_stage_of_life_and_a_birthday_is_not():
    assert [life_stage(age) for age in (None, 8, 16, 25, 40, 50, 70)] == [None, 0, 1, 2, 3, 4, 5]
    lin = cultivation_world().characters["lin"]

    assert not changes_look(lin, appearance=None, age=17)
    assert changes_look(lin, appearance=None, age=18)
    assert not changes_look(lin, appearance=None, age=None)


def test_a_lasting_change_to_a_face_moves_the_look_on_once():
    state = cultivation_world()
    assert state.characters["lin"].look_version == 1

    state = look(state, appearance="16, slight, black hair tied back, one eye lost to a blade.")
    assert state.characters["lin"].look_version == 2
    # The narrator writes the same look again in other words, or only moves her: no change.
    state = look(state, appearance="Slight, 16: black hair tied back, one eye lost to a blade.")
    state = look(state, location_id="well")
    assert state.characters["lin"].look_version == 2
    # Years later, both a new stage of life and a new appearance count once together.
    state = look(state, age=61, appearance="61, stooped, white hair, one eye lost to a blade.")
    assert state.characters["lin"].look_version == 3


def test_a_new_character_starts_at_the_first_look():
    state = look(cultivation_world(), "mo", name="Elder Mo", appearance="70, white beard", age=70)

    assert state.characters["mo"].look_version == 1


def test_a_place_counts_only_its_changes_for_good():
    state = cultivation_world()
    state.deeds["deed-1"] = Deed(
        id="deed-1", actor_id="lin", kind="rebuild", text="", turn=3, world_s=0, target_ids=["well"]
    )
    rebuilt = Cause(
        mechanism=CauseMechanism.REBUILD, ref_kind=CauseRef.DEED, ref_id="deed-1", text="x"
    )

    def status(state, status, source=DeltaSource.NARRATOR, **kw):
        return apply(state, source, places=[PlaceChange(id="well", status=status, **kw)])

    assert place_version(state.places["well"]) == 1
    state = status(state, PlaceStatus.DAMAGED)
    assert place_version(state.places["well"]) == 1  # damage mends
    state = status(state, PlaceStatus.RUINED, DeltaSource.ENGINE)
    assert place_version(state.places["well"]) == 2
    state = status(state, PlaceStatus.THRIVING, DeltaSource.ENGINE, cause=rebuilt)
    assert place_version(state.places["well"]) == 3
    state = status(state, PlaceStatus.OCCUPIED)
    assert place_version(state.places["well"]) == 4


def test_a_place_is_drawn_as_it_is_now():
    place = cultivation_world().places["well"]
    assert place_looks(place) == place.description
    place.status = PlaceStatus.OCCUPIED
    assert place_looks(place).endswith("It is occupied now.")
