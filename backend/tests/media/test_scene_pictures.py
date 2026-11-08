"""A scene picture drawn from its finished scene (M5, C10): the note written from the scene's text
first, on the account that draws it, the portraits of only the people it shows, and the picture
of the place it happens in; and the cover, the story's poster, drawn with none of these (M1)."""

import pytest
from django.test import Client

from media.drawing import KeyCannotDraw, NoteFailed
from media.models import Image
from media.notes import PictureNote
from media.plans import plan_picture
from media.prompts import Brief, Figure, WorldLook
from tests.conftest import auth_headers
from tests.media.conftest import PNG, make_scene, make_story, story_owner

pytestmark = pytest.mark.django_db

LEAP = "You grip the bark and swing up, branch to branch through the old pines, at dusk."
LIN = Figure("lin", "Lin Feng", "a lean youth in grey", carries=())
ZHAO = Figure("zhao", "Zhao Yun", "a broad senior disciple")
NOTE = PictureNote(description="Lin Feng leaps between high pine branches.", people=["Lin Feng"])
BYOK = {"X-LLM-Provider": "gemini", "X-LLM-Api-Key": "k"}


@pytest.fixture
def client() -> Client:
    return Client(headers=auth_headers(story_owner()))


def _image(client: Client, story, turn: int, **headers):
    return client.post(f"/v1/stories/{story.id}/scenes/{turn}/image", headers=headers)


def _leap(story, *, kind="scene", turn=2, **brief):
    scene = make_scene(story, turn, narration=LEAP, player_action="I leap up the old pines")
    fields = {
        "description": "You crouch on a rooftop, dagger drawn.",
        "figures": (LIN, ZHAO),
        "you": "Lin Feng",
        "turn": turn,
    }
    plan_picture(scene, kind=kind, trigger="cover", brief=Brief(**(fields | brief)))
    return scene


def _ready(client, story, turn, subject, kind):
    """A ready portrait or place picture of `subject`, drawn in scene `turn`."""
    plan_picture(
        make_scene(story, turn), kind=kind, subject_id=subject, trigger="first_meeting",
        brief=Brief(subject_name=subject.title(), subject_appearance="as on record"),
    )  # fmt: skip
    assert _image(client, story, turn).json()["status"] == "ready"


def test_a_scene_picture_is_drawn_from_a_note_on_the_finished_scene(
    client, painters, meter, log_lines
):
    story = make_story()
    _leap(story)
    painters.ours.script_notes(NOTE)

    assert _image(client, story, 2).json()["status"] == "ready"

    [note] = painters.ours.note_prompts
    assert note.user.endswith(f"SCENE:\n{LEAP}")
    assert "PLAYER'S ACTION: I leap up the old pines" in note.user
    assert "You crouch on a rooftop, dagger drawn." in note.user  # the narrator's, as a draft
    assert "Lin Feng CARRIES: nothing" in note.user
    [request] = painters.ours.requests
    assert "What it shows: Lin Feng leaps between high pine branches." in request.prompt
    assert "rooftop" not in request.prompt and "dagger drawn" not in request.prompt
    # Only the people the note shows: Zhao's look stays out of the picture.
    assert "Zhao" not in request.prompt
    assert "Lin Feng carries no weapon" in request.prompt  # C10 still holds
    line = next(line for line in log_lines() if line.get("picture"))
    assert line["picture"]["noted"] is True
    assert "pine" not in str(log_lines())  # neither the scene nor the note is logged (T6)


def test_a_cover_is_the_storys_poster_with_no_note_and_no_place(client, painters, meter):
    """M1 (Miki, 2026-11-07): the cover sums up the story, so it gets no note from its scene and
    no picture of that scene's place, but it is drawn with the premise and only what the player
    character carries (C10)."""
    story = make_story(premise="Across the river stand the ruins of your clan's castle.")
    _ready(client, story, 1, "well", "place")
    scene = make_scene(story, 2, narration=LEAP)
    brief = Brief(
        description="Lin Feng above the sect's valley, the clan's ruins across the river.",
        look=WorldLook(setting=story.premise),
        figures=(LIN,),
        you="Lin Feng",
        turn=2,
        place_id="well",
    )
    plan_picture(scene, kind="cover", trigger="cover", brief=brief)

    assert _image(client, story, 2).json()["status"] == "ready"

    assert painters.ours.note_prompts == []
    request = painters.ours.requests[1]
    assert "ruins of your clan's castle" in request.prompt
    assert "Lin Feng carries no weapon" in request.prompt
    assert "like the poster of a film or the cover of a novel" in request.prompt
    assert request.references == () and request.aspect_ratio == "3:4"


def test_a_failed_note_leaves_the_narrators_description(client, painters, meter, log_lines):
    story = make_story()
    _leap(story)
    painters.ours.script_notes(NoteFailed("timeout"))

    assert _image(client, story, 2).json()["status"] == "ready"

    [request] = painters.ours.requests
    assert "You crouch on a rooftop, dagger drawn." in request.prompt
    assert "Zhao Yun" in request.prompt
    lines = log_lines()
    failed = next(line for line in lines if line.get("note"))
    assert failed["note"] == {"reason": "timeout", "byok": False}
    assert next(line for line in lines if line.get("picture"))["picture"]["noted"] is False
    assert len(meter.charged) == 1


def test_a_broken_note_never_costs_the_picture(client, painters, meter):
    story = make_story()
    _leap(story)
    painters.ours.script_notes(RuntimeError("bug"))

    assert _image(client, story, 2).json()["status"] == "ready"
    assert "You crouch on a rooftop" in painters.ours.requests[0].prompt


def test_a_note_that_fails_on_the_players_key_is_written_again_on_ours(client, painters, meter):
    story = make_story()
    _leap(story)
    painters.byok.script_notes(NoteFailed("auth")).script(KeyCannotDraw("bad_key"))
    painters.ours.script_notes(NOTE)

    assert _image(client, story, 2, **BYOK).json()["status"] == "ready"

    assert len(painters.byok.note_prompts) == len(painters.ours.note_prompts) == 1
    assert "Lin Feng leaps between high pine branches." in painters.ours.requests[0].prompt


def test_a_note_written_on_the_players_key_is_not_written_again(client, painters, meter, log_lines):
    story = make_story()
    _leap(story)
    painters.byok.script_notes(NOTE).script(KeyCannotDraw("free_tier"))

    assert _image(client, story, 2, **BYOK).json()["status"] == "ready"

    assert painters.ours.note_prompts == []
    assert "Lin Feng leaps between high pine branches." in painters.ours.requests[0].prompt
    line = next(line for line in log_lines() if line.get("picture"))
    assert line["picture"]["noted"] is True  # the player's key wrote it


def test_the_note_keeps_only_the_portraits_of_the_people_it_shows(client, painters, meter):
    story = make_story()
    _ready(client, story, 1, "zhao", "portrait")
    _leap(story)
    painters.ours.script_notes(PictureNote(description="Zhao Yun climbs.", people=["Zhao Yun"]))

    assert _image(client, story, 2).json()["status"] == "ready"
    assert [ref.name for ref in painters.ours.requests[1].references] == ["Zhao Yun"]

    other = make_story()
    _ready(client, other, 1, "zhao", "portrait")
    _leap(other)
    painters.ours.script_notes(NOTE)

    assert _image(client, other, 2).json()["status"] == "ready"
    assert painters.ours.requests[3].references == ()


def test_a_picture_keeps_what_it_was_drawn_from_for_staff(client, painters, meter, log_lines):
    """Miki, 2026-11-08: a picture that looks wrong can be traced. The note's description, the
    people it shows and the images that went along stay with the picture (T16), next to the brief
    as planned, which a later drawing still starts from, and none of it is logged (T6)."""
    story = make_story()
    _ready(client, story, 1, "zhao", "portrait")
    _leap(story)
    painters.ours.script_notes(
        PictureNote(description="Zhao Yun hauls Lin Feng onto a pine branch.", people=["Zhao Yun"])
    )

    assert _image(client, story, 2).json()["status"] == "ready"

    image = Image.objects.get(story=story, subject="turn-2")
    assert image.brief["drawn_from"] == {
        "description": "Zhao Yun hauls Lin Feng onto a pine branch.",
        "people": ["Lin Feng", "Zhao Yun"],
        "references": ["Image 1: the portrait of Zhao Yun."],
        "noted": True,
    }
    assert image.brief["description"] == "You crouch on a rooftop, dagger drawn."
    assert "hauls" not in str(log_lines())


def test_the_place_picture_goes_along_with_a_scene_that_happens_there(
    client, painters, meter, log_lines
):
    """M5: a place looks the same from scene to scene."""
    story = make_story()
    _ready(client, story, 1, "lin", "portrait")
    _ready(client, story, 2, "pines", "place")
    _leap(story, turn=3, place_id="pines", place_name="The Old Pines")
    painters.ours.script_notes(NOTE)

    assert _image(client, story, 3).json()["status"] == "ready"

    request = painters.ours.requests[2]
    assert [(ref.name, ref.data) for ref in request.references] == [
        ("Lin Feng", PNG),
        ("The Old Pines", PNG),
    ]
    assert [ref.label for ref in request.references] == [
        "Image 1: the portrait of Lin Feng.",
        "Image 2: The Old Pines, the place where this happens.",
    ]
    assert "The image labelled as the place is where this happens." in request.prompt
    line = [line for line in log_lines() if line.get("picture")][-1]
    assert (line["picture"]["references"], line["picture"]["place_reference"]) == (2, True)


def test_a_place_without_a_ready_picture_sends_none(client, painters, meter):
    story = make_story()
    _leap(story, place_id="pines", place_name="The Old Pines")

    assert _image(client, story, 2).json()["status"] == "ready"

    request = painters.ours.requests[0]
    assert request.references == ()
    assert "labelled as the place" not in request.prompt


def test_portraits_and_places_get_no_note(client, painters, meter):
    story = make_story()
    _ready(client, story, 1, "lin", "portrait")
    _ready(client, story, 2, "pines", "place")

    assert painters.ours.note_prompts == []
    assert Image.objects.filter(story=story).count() == 2
