"""M1, M4, M5: a place or a face that changes for good gets a new look version, so its picture is
drawn once more; anything less keeps the picture it has. A face changes only through a stated
lasting change (`look_change`), so the narrator rewording an appearance never redraws one."""

from engine.apply import DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import CharacterChange, PlaceChange, StateDelta
from engine.looks import appearance_words, look_after, place_looks, place_version
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


def test_only_a_stated_lasting_change_is_a_new_look():
    lin = cultivation_world().characters["lin"]
    kept = lin.appearance
    scarred = "16, slight, black hair tied back, a blade scar where his left eye was."

    assert look_after(lin, appearance=scarred, look_change=None) is None
    assert look_after(lin, appearance=None, look_change=" . ") is None
    assert look_after(lin, appearance=scarred, look_change="lost his left eye") == scarred
    # Written without the change, or the same look in other words: the change is added to it.
    same = "Slight and 16, with steady eyes and black hair tied back"
    assert look_after(lin, appearance=same, look_change="lost his left eye") == (
        f"{same} Lost his left eye."
    )
    assert look_after(lin, appearance=None, look_change="grey at the temples.") == (
        f"{kept} Grey at the temples."
    )
    assert appearance_words(kept) == appearance_words(
        "Steady eyes, slight; black hair tied back, 16"
    )


def test_a_lasting_change_to_a_face_moves_the_look_on_once():
    state = cultivation_world()
    assert state.characters["lin"].look_version == 1
    scarred = "16, slight, black hair tied back, one eye lost to a blade."

    state = look(state, appearance=scarred, look_change="lost an eye to Zhao's blade")
    assert state.characters["lin"].look_version == 2
    assert state.characters["lin"].appearance == scarred
    # The narrator writes the appearance again, in other words or not, without a change: none.
    state = look(state, appearance="Slight, 16: black hair tied back, one eye lost to a blade.")
    state = look(state, appearance="16, slight, a patch over one eye, a scar.")
    state = look(state, location_id="well")
    assert state.characters["lin"].look_version == 2
    # Years later, old age is a change of its own. The years themselves are the world's to
    # count (W10, `engine.world.lives`): the scene tells only how they show.
    state = look(state, look_change="white-haired and stooped with age")
    assert state.characters["lin"].look_version == 3
    assert state.characters["lin"].appearance.endswith("White-haired and stooped with age.")


def test_a_new_character_starts_at_the_first_look():
    state = look(
        cultivation_world(), "mo", name="Elder Mo", appearance="70, white beard", look_change="x y"
    )

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
    place.status = PlaceStatus.DAMAGED
    assert place_looks(place) == place.description  # damage mends; the picture doesn't keep it
    place.status = PlaceStatus.OCCUPIED
    assert place_looks(place).endswith("It is occupied now.")
