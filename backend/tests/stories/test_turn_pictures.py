"""Turns on the scripted model that draw a place or a face once more after it changed for good
(M1, M4, M5): the director picks it, the turn plans it at the new look version, and every later
scene reuses that picture."""

from engine.state import PlaceStatus, StatusChange, WorldState
from graph.llm import Node, Reply
from media.models import Image, ImageStatus, ScenePicture
from stories.models import Scene, Story
from tests.stories.conftest import opening, play

OPENING = {
    "narration": "Cold water slops over your sandals as you lift the bucket from the well.",
    "image_prompt": "Lin Feng at the well at dawn, a full bucket in hand.",
    "update": {
        "scene_end": {
            "ended_on": "Zhao blocks the path.",
            "place_id": "well",
            "present_ids": ["lin", "zhao"],
        }
    },
}
LOOK_AROUND = {
    "summary": "Lin looks around.",
    "steps": [{"text": "look around", "verb": "look", "kind": "observe", "proposed_duration_s": 5}],
}
SCARRED = "16, slight, black hair tied back, a blade scar where his left eye was."


def narrated(update: dict | None = None, prompt: str | None = None) -> dict:
    return {
        "narration": "You take in the courtyard.",
        "image_prompt": prompt,
        "update": update or {"scene_end": {"ended_on": "The courtyard is quiet."}},
    }


def opened(player, make_story, model) -> Story:
    story = make_story(player)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    assert play(player, story, opening(story)).names[-1] == "scene.completed"
    return Story.objects.get(pk=story.pk)


def change(story: Story, edit) -> None:
    """Edits the saved world between turns, as the engine would have in a turn of its own."""
    state = WorldState.model_validate(story.state)
    edit(state)
    Story.objects.filter(pk=story.pk).update(state=state.model_dump(mode="json"))


def act(player, story: Story, model, narration: dict) -> Scene:
    story.refresh_from_db()
    model.backend.script(Node.INTERPRET, Reply(json=LOOK_AROUND))
    model.backend.script(Node.NARRATOR, Reply(json=narration))
    played = play(
        player,
        story,
        {"kind": "action", "action": "I look around.", "expected_version": story.version},
    )
    assert played.names[-1] == "scene.completed", played.events
    return Scene.objects.get(story=story, turn=played.completed["scene"]["turn"])


def picture_of(scene: Scene) -> Image | None:
    link = ScenePicture.objects.select_related("image").filter(scene=scene).first()
    return link.image if link else None


def seen_already(state: WorldState) -> None:
    """The cover, Zhao and the well were pictured on earlier turns, so nothing else competes."""
    state.director.pictured += ["cover", "portrait:zhao", "portrait:zhao:v1"]
    state.director.pictured += ["place:well", "place:well:v1"]


def test_a_ruined_place_is_drawn_once_more_and_reused_on_every_return(player, make_story, model):
    story = opened(player, make_story, model)
    first = Image.objects.create(
        story=story, kind="place", subject="well", version=1, status=ImageStatus.READY
    )

    def ruin(state: WorldState) -> None:
        seen_already(state)
        well = state.places["well"]
        well.status_history.append(
            StatusChange(status="ruined", from_status="thriving", turn=1, world_s=state.world_s)
        )
        well.status = PlaceStatus.RUINED

    change(story, ruin)
    changed = picture_of(act(player, story, model, narrated(prompt="The well, a heap of stones.")))

    assert (changed.kind, changed.subject, changed.version) == ("place", "well", 2)
    assert changed.pk != first.pk and changed.status == ImageStatus.PLANNED
    assert changed.trigger == "place_changed"
    assert changed.brief["subject_appearance"].endswith("It is ruined now.")
    assert changed.brief["description"] == "The well, a heap of stones."
    # Later turns there don't draw it again.
    assert picture_of(act(player, story, model, narrated())) is None
    assert Image.objects.filter(story=story, subject="well").count() == 2


def test_a_face_that_changed_for_good_gets_its_portrait_drawn_once_more(player, make_story, model):
    story = opened(player, make_story, model)
    first = Image.objects.get(story=story, kind="portrait", subject="lin")
    change(story, seen_already)

    # The narrator records the lost eye (C9, G17); the next scene redraws him.
    lost_eye = narrated(
        {
            "characters": [{"id": "lin", "appearance": SCARRED, "look_change": "lost an eye"}],
            "scene_end": {"ended_on": "Blood runs down Lin's face."},
        }
    )
    assert picture_of(act(player, story, model, lost_eye)) is None
    story.refresh_from_db()
    assert story.state["characters"]["lin"]["look_version"] == 2

    redrawn = picture_of(act(player, story, model, narrated(prompt="Lin, scarred, at the well.")))

    assert (redrawn.kind, redrawn.subject, redrawn.version) == ("portrait", "lin", 2)
    assert redrawn.pk != first.pk and redrawn.trigger == "look_changed"
    assert redrawn.brief["subject_appearance"] == SCARRED
    # An appearance written again without a lasting change is none, and nothing is drawn again.
    reworded = narrated(
        {"characters": [{"id": "lin", "appearance": "Slight, 16, a scar over an empty socket."}]}
    )
    assert picture_of(act(player, story, model, reworded)) is None
    assert picture_of(act(player, story, model, narrated())) is None
    story.refresh_from_db()
    assert story.state["characters"]["lin"]["look_version"] == 2
    assert Image.objects.filter(story=story, subject="lin").count() == 2


def test_a_scene_that_scars_the_person_it_pictures_draws_the_new_look_once(
    player, make_story, model
):
    """The director picks Zhao's first portrait before the scene is told; the scene then scars
    him. The portrait is drawn with the scar, at his new look, and never redrawn for it."""
    story = opened(player, make_story, model)

    def zhao_unmet(state: WorldState) -> None:
        state.director.pictured += ["cover", "place:well", "place:well:v1"]

    change(story, zhao_unmet)
    scar = narrated(
        {
            "characters": [
                {
                    "id": "zhao",
                    "appearance": "19, broad, a fresh scar across his jaw.",
                    "look_change": "a scar across his jaw",
                }
            ]
        },
        prompt="Zhao Kun, a fresh scar on his jaw.",
    )

    met = picture_of(act(player, story, model, scar))

    assert (met.kind, met.subject, met.trigger, met.version) == (
        "portrait",
        "zhao",
        "first_meeting",
        2,
    )
    assert met.brief["subject_appearance"] == "19, broad, a fresh scar across his jaw."
    # S7: drawn at the age the story gives him.
    assert met.brief["subject_age"] == 19
    assert picture_of(act(player, story, model, narrated())) is None
    assert Image.objects.filter(story=story, subject="zhao").count() == 1
