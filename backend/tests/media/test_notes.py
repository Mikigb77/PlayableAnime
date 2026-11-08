"""A scene picture's description, written from the finished scene (M5, C10): what the note step
reads, and how its answer becomes the brief the picture is drawn from."""

import pytest
from pydantic import ValidationError

from media.notes import (
    MAX_NOTE_CHARS,
    MAX_SCENE_CHARS,
    NOTE_SYSTEM,
    PictureNote,
    SceneText,
    apply_note,
    note_prompt,
)
from media.prompts import Brief, Figure, WorldLook

LEAP = (
    "You grip the rough bark and swing up. Branch to branch you climb the old pines, needles "
    "raining down, until the outer wall drops below you and the whole valley opens at dusk."
)
LIN = Figure("lin", "Lin Feng", "a lean youth in a patched grey robe", carries=(), age=16)
ZHAO = Figure("zhao", "Zhao Yun", "a broad senior disciple")
BRIEF = Brief(
    description="You crouch on a moonlit rooftop, your father's dagger drawn.",
    look=WorldLook(genre="cultivation", era="an ancient empire of sects", tone="grim"),
    figures=(LIN, ZHAO),
    you="Lin Feng",
    time="dusk",
    turn=2,
    place_id="pines",
    place_name="The Old Pines",
    place_look="Old pines behind the well, their roots in the sect's outer wall.",
)
SCENE = SceneText(LEAP, action="I leap from branch to branch up the old pines")


def test_the_note_reads_the_finished_scene_with_the_record_around_it():
    prompt = note_prompt("scene", BRIEF, SCENE)

    assert prompt.system == NOTE_SYSTEM
    user = prompt.user
    assert user.startswith("PICTURE: the scene's picture: the moment that matters most")
    # The narrator's description goes along as a draft, which the scene outranks.
    assert (
        "NARRATOR'S NOTE (written before the scene was finished, so trust SCENE over it): You "
        "crouch on a moonlit rooftop, your father's dagger drawn."
    ) in user
    assert 'PLAYER CHARACTER (the narration\'s "you"): Lin Feng' in user
    # S7: with the age the story gives them, so the description never makes them younger.
    assert (
        "PEOPLE (who may be in the picture, with their age and how they look): Lin Feng, aged "
        "16: a lean youth in a patched grey robe; Zhao Yun: a broad senior disciple"
    ) in user
    # C10: the player character's belongings are the whole record, so "nothing" is said.
    assert "Lin Feng CARRIES: nothing" in user
    assert "Zhao Yun CARRIES" not in user  # another's belongings are only what the story told
    assert "PLACE: The Old Pines: Old pines behind the well" in user
    assert "TIME OF DAY: dusk" in user
    assert "WORLD: cultivation; an ancient empire of sects" in user
    assert "PLAYER'S ACTION: I leap from branch to branch up the old pines" in user
    assert user.endswith(f"SCENE:\n{LEAP}")


def test_the_note_lists_what_the_player_character_carries():
    lin = Figure("lin", "Lin Feng", carries=("a bow", "20 arrows"))
    user = note_prompt("scene", Brief(figures=(lin,), you="Lin Feng"), SCENE).user

    assert "Lin Feng CARRIES: a bow, 20 arrows" in user
    assert "NARRATOR'S NOTE" not in user  # Illustrate on a scene with none: the scene alone
    assert "PLACE" not in user and "TIME OF DAY" not in user


@pytest.mark.parametrize("kind", ["portrait", "place", "cover"])
def test_only_a_scene_picture_gets_a_note(kind):
    """A cover is the story's poster (M1), not the moment of the scene it is planned in."""
    with pytest.raises(ValueError):
        note_prompt(kind, BRIEF, SCENE)


def test_a_long_scene_is_cut_to_its_end_from_a_paragraph():
    start = "The morning began quietly.\n"
    long = start + ("The bell tolls over the court. " * 300) + "\nLin leaps for the last branch."

    user = note_prompt("scene", BRIEF, SceneText(long)).user

    scene = user.split("SCENE:\n", 1)[1]
    assert len(scene) <= MAX_SCENE_CHARS
    assert scene.endswith("Lin leaps for the last branch.")
    assert "The morning began quietly." not in scene


def test_the_rules_keep_the_note_to_what_the_scene_tells():
    """M5, C10, M6: nothing the scene doesn't have, no gear the player doesn't carry, mild."""
    assert "Never add a place, building, ruin, river, creature, person or thing" in NOTE_SYSTEM
    assert "has only what CARRIES lists" in NOTE_SYSTEM
    assert "never give them any other weapon" in NOTE_SYSTEM
    assert "no nudity, nothing sexual, no gore" in NOTE_SYSTEM
    assert "Write in English, whatever language the scene is in" in NOTE_SYSTEM


def test_the_note_keeps_anyone_the_scene_only_mentions_in_the_background():
    """Miki, 2026-11-08: a scene of the player character and one other came out with a third
    person, one of the scouts the scene only said had joined the feast."""
    assert "each once" in NOTE_SYSTEM
    assert "a small, unnamed part of the background" in NOTE_SYSTEM
    assert "never a figure of their own" in NOTE_SYSTEM


def test_the_note_becomes_the_description_with_only_the_people_it_shows():
    note = PictureNote(
        description="Lin Feng leaps between high pine branches.", people=["lin feng"]
    )

    brief = apply_note(BRIEF, note)

    assert brief.description == "Lin Feng leaps between high pine branches."
    assert brief.figures == (LIN,)  # Zhao isn't in the moment, so his look stays out (M5)
    assert brief.figures[0].carries == ()
    assert (brief.place_id, brief.time, brief.turn) == ("pines", "dusk", 2)


def test_someone_the_note_names_stays_even_if_its_list_forgot_them():
    note = PictureNote(description="Zhao Yun watches Lin Feng climb.", people=["Lin Feng"])

    assert apply_note(BRIEF, note).figures == (LIN, ZHAO)


def test_a_note_that_says_you_keeps_the_player_character():
    note = PictureNote(description="You swing up into the pines.", people=[])

    assert apply_note(BRIEF, note).figures == (LIN,)


def test_a_note_with_no_one_in_it_shows_no_one():
    note = PictureNote(description="Empty pine branches sway against the dusk.", people=[])

    assert apply_note(BRIEF, note).figures == ()


def test_a_long_note_is_cut():
    note = PictureNote(description="Lin climbs. " * 200, people=["Lin Feng"])

    assert len(apply_note(BRIEF, note).description) <= MAX_NOTE_CHARS


def test_a_blank_note_is_refused():
    with pytest.raises(ValidationError):
        PictureNote(description="  ", people=[])


def test_scene_text_never_prints_the_scene():
    assert "pines" not in repr(SCENE)
    assert "pines" not in repr(note_prompt("scene", BRIEF, SCENE))
