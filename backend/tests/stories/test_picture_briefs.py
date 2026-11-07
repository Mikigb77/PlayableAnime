"""What the turn asks a planned scene picture to show (M1, M5): the people the narrator's image
prompt names, the subject first, who "you" is and the time of day."""

from engine.contracts import PictureKind, PictureTrigger
from engine.samples import grounded_world
from engine.state.cast import Character, Prominence
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
    # The premise tells how the story began, not this scene (M5).
    assert planned.look.setting == ""


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


def test_a_cover_shows_the_scene_it_is_planned_in_never_the_premise():
    """M5 (Miki, 2026-11-07): the cover is shown in the scene it is planned in, so it is drawn
    as that scene, at its hour, with what the player character has on them, and the premise,
    whose places and things the scene may not have, stays out of it."""
    state = grounded_world()
    cover = ScenePicture(kind=PictureKind.COVER, prompt="You stand alone in the rain.")

    planned = brief(STORY, state, cover, PictureTrigger.COVER)

    assert [f.id for f in planned.figures] == ["luca"]
    assert (planned.you, planned.time) == ("Luca Esposito", "evening")
    assert planned.figures[0].carries == ("Beretta pistol", "flick knife")
    assert STORY.premise not in build_prompt("cover", planned).user
