"""What the turn asks a planned scene picture to show (M1, M5): the people the narrator's image
prompt names, the subject first, who "you" is, the time of day, the scene's turn and its place."""

from engine.contracts import PictureKind, PictureTrigger
from engine.samples import grounded_world
from engine.state.cast import Character, CharacterStatus, DeathCertainty, Prominence
from graph.turn import ScenePicture
from media.prompts import build_prompt
from stories.models import Story
from stories.turns import brief

STORY = Story(premise="The boss is dead, and the family is splitting.", genre="crime")


def _scene(prompt: str, subject_id: str | None = None) -> ScenePicture:
    return ScenePicture(kind=PictureKind.SCENE, prompt=prompt, subject_id=subject_id)


def test_a_scene_picture_shows_the_people_its_prompt_names_at_the_hour():
    state = grounded_world()  # Luca, at the bar with Carmine, at 21:00

    planned = brief(STORY, state, _scene("Carmine raises a glass to you."))

    assert [f.id for f in planned.figures] == ["luca", "carmine"]
    assert (planned.you, planned.time) == ("Luca Esposito", "evening")
    # What Luca has on him, so the picture arms him with nothing else (C10).
    assert planned.figures[0].carries == ("Beretta pistol", "flick knife")
    # The premise tells how the story began, not this scene (M5): it goes along only for a cover.
    assert STORY.premise not in build_prompt("scene", planned).user
    # The scene it shows, for its note, and where it happens, for the place's picture (M5).
    assert planned.turn == state.turn
    assert (planned.place_id, planned.place_name) == ("bar", "Carmine's bar")
    assert planned.place_look == state.places["bar"].description


def test_the_subject_of_a_fight_leads_even_when_the_player_never_met_them():
    state = grounded_world()
    state.characters["sal"] = Character(
        id="sal", name="Sal the Knife", prominence=Prominence.KEY, appearance="a white suit"
    )

    planned = brief(
        STORY,
        state,
        _scene("A blade flashes under the lamps.", "sal"),
        PictureTrigger.FIGHT_START,
    )

    assert [f.id for f in planned.figures][:2] == ["sal", "luca"]


def test_an_arc_ending_or_an_event_has_no_person_as_its_subject():
    """Their subject is a thread, whose id must never be read as a character's."""
    state = grounded_world()
    state.characters["council"] = Character(id="council", name="Old Council")

    for trigger in (PictureTrigger.ARC_END, PictureTrigger.EVENT):
        planned = brief(STORY, state, _scene("Carmine smiles.", "council"), trigger)
        assert [f.id for f in planned.figures] == ["carmine"]


def test_a_cover_is_the_storys_poster_drawn_from_its_premise():
    """M1 (Miki, 2026-11-07): the cover is the story's poster, not the scene it comes with, so it
    is drawn from the premise around the main character, with no one scene's hour or place and
    nothing the scene tells, but still with what the player character has on them (C10)."""
    state = grounded_world()  # Luca, at the bar with Carmine
    story = Story(premise="You are Luca, and Carmine wants the family split.", genre="crime")
    cover = ScenePicture(kind=PictureKind.COVER, prompt="Carmine raises a glass to you.")

    planned = brief(story, state, cover, PictureTrigger.COVER)
    user = build_prompt("cover", planned).user

    # The main character first, then whom the premise names.
    assert [f.id for f in planned.figures] == ["luca", "carmine"]
    assert (planned.you, planned.time, planned.place_id) == ("Luca Esposito", "", "")
    assert planned.turn == state.turn
    assert planned.figures[0].carries == ("Beretta pistol", "flick knife")
    assert planned.description == (
        "The story's main character, Luca Esposito, in the world its premise tells: "
        f"{story.premise}"
    )
    # The premise once, as what it shows, and nothing of the scene.
    assert user.count(story.premise) == 1 and "setting:" not in user
    assert "raises a glass" not in user


def test_a_cover_shows_at_most_two_living_people_besides_the_main_character():
    """A family name in the premise names the whole family (`media.briefs.names`), and the dead
    stay off the poster, which stays the main character's."""
    state = grounded_world()
    for i in range(4):
        state.characters[f"cousin{i}"] = Character(id=f"cousin{i}", name=f"Cousin{i} Esposito")
    state.characters["cousin0"] = state.characters["cousin0"].model_copy(
        update={"status": CharacterStatus.DEAD, "death_certainty": DeathCertainty.CONFIRMED}
    )
    story = Story(premise="You are the heir of the Esposito family.", genre="crime")

    planned = brief(story, state, ScenePicture(kind=PictureKind.COVER, prompt=""))

    assert [f.id for f in planned.figures] == ["luca", "cousin1", "cousin2"]


def test_a_cover_with_no_premise_shows_the_main_character_alone():
    state = grounded_world()
    cover = ScenePicture(kind=PictureKind.COVER, prompt="Carmine raises a glass to you.")

    planned = brief(Story(genre="crime"), state, cover, PictureTrigger.COVER)

    assert planned.description == "The story's main character, Luca Esposito"
    assert [f.id for f in planned.figures] == ["luca"]
