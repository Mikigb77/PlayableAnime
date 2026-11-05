"""N6 over HTTP: a death or `/end` brings the story to its ending, which is saved with the turn and
sent with the story. A story at its ending takes no more turns, and the player closes it or starts
again from its premise. A note the world won't grant ends the turn with `ending.refused`, with
nothing saved or charged."""

import pytest
from django.test import Client

from graph.llm import Node, Reply
from stories.models import Scene, Story
from tests.conftest import auth_headers
from tests.stories.conftest import play
from tests.stories.test_turns import assert_nothing_saved, opened

pytestmark = pytest.mark.django_db

LEAP = {
    "summary": "Lin leaps into the well.",
    "steps": [
        {
            "text": "throw myself head first down the well",
            "verb": "leap",
            "kind": "exchange",
            "proposed_duration_s": 3,
            "aim": "kill",
            "target_ids": ["lin"],
            "facts": {"means": "clearly_enough"},
        }
    ],
}
FALL = {
    "narration": "Your hands grip the stone, then let go.",
    "suggestions": [{"label": "Climb out", "kind": "thread"}],
}
WALK_AWAY = {
    "text": "walk away from the sect for good",
    "verb": "walk",
    "kind": "move",
    "proposed_duration_s": 600,
    "facts": {"means": "clearly_enough"},
}
ASCEND = {
    "text": "become the sect's grand elder",
    "verb": "rule",
    "kind": "move",
    "proposed_duration_s": 600,
    "facts": {"means": "clearly_not"},
}
EPILOGUE = {"narration": "The well falls behind you, and the road runs on.", "suggestions": []}


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


def end(story: Story, note: str | None = None, **extra) -> dict:
    body = {"kind": "end", "expected_version": story.version, **extra}
    if note is not None:
        body["action"] = note
    return body


def dead(player, make_story, model) -> Story:
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=LEAP))
    model.backend.script(Node.NARRATOR, Reply(json=FALL))
    played = play(player, story, {"kind": "action", "action": "I leap in", "expected_version": 2})
    assert played.names[-1] == "scene.completed", played.events
    story.refresh_from_db()
    return story


def test_a_death_brings_the_story_to_its_ending(client, player, make_story, model):
    story = dead(player, make_story, model)

    ending = {
        "kind": "death",
        "character_id": "lin",
        "character": "Lin Feng",
        "self_inflicted": True,
        "turn": 2,
        "closed": False,
    }
    assert story.ending == ending
    assert Scene.objects.get(story=story, turn=2).choices == []
    shown = client.get(f"/v1/stories/{story.pk}").json()
    assert shown["ending"] == ending
    assert shown["premise"] == "A premise."
    [summary] = client.get("/v1/stories").json()
    assert summary["ending"] == ending


def test_the_turn_that_reaches_an_ending_sends_it(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.INTERPRET, Reply(json=LEAP))
    model.backend.script(Node.NARRATOR, Reply(json=FALL))

    played = play(player, story, {"kind": "action", "action": "I leap", "expected_version": 2})

    assert played.completed["story"]["ending"]["kind"] == "death"
    assert played.completed["scene"]["choices"] == []


def test_a_story_at_its_ending_takes_no_more_turns(player, make_story, model):
    story = dead(player, make_story, model)

    for body in (
        {"kind": "action", "action": "I climb out", "expected_version": story.version},
        end(story),
    ):
        played = play(player, story, body)
        assert played.status == 409
        assert played.body["error"]["code"] == "story_ended"
        assert played.body["error"]["details"]["ending"]["kind"] == "death"


def test_an_older_story_whose_character_is_dead_is_at_its_ending(player, make_story, model):
    story = opened(player, make_story, model)
    story.state["characters"]["lin"] |= {"status": "dead", "death_certainty": "confirmed"}
    story.save(update_fields=["state"])

    played = play(player, story, {"kind": "action", "action": "I rise", "expected_version": 2})
    assert played.status == 409
    assert played.body["error"]["details"]["ending"]["character_id"] == "lin"


def test_end_with_no_note_tells_an_epilogue(player, make_story, model):
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Reply(json=EPILOGUE))

    played = play(player, story, end(story))

    scene = played.completed["scene"]
    assert (scene["kind"], scene["player_action"], scene["input_mode"]) == ("end", None, None)
    assert scene["choices"] == []
    assert played.completed["story"]["ending"]["kind"] == "chosen"
    story.refresh_from_db()
    assert story.ending["kind"] == "chosen" and story.ending["turn"] == 2


def test_a_note_the_world_wont_grant_is_refused_and_nothing_is_saved(player, make_story, model):
    story = opened(player, make_story, model)
    note = {"summary": "end", "steps": [ASCEND, WALK_AWAY]}
    model.backend.script(Node.INTERPRET, Reply(json=note))

    played = play(player, story, end(story, "I become grand elder and leave"))

    assert played.names == ["turn.started", "ending.refused"]
    [refusal] = played.named("ending.refused")
    assert refusal["message"]
    [refused] = refusal["refused"]
    assert refused["text"] == "become the sect's grand elder"
    assert refused["class"] == "ruled_out" and refused["reason"]
    assert_nothing_saved(story, player)
    assert Story.objects.get(pk=story.pk).ending is None


def test_ending_without_what_was_refused(player, make_story, model):
    story = opened(player, make_story, model)
    note = {"summary": "end", "steps": [ASCEND, WALK_AWAY]}
    model.backend.script(Node.INTERPRET, Reply(json=note))
    model.backend.script(Node.NARRATOR, Reply(json=EPILOGUE))

    played = play(
        player,
        story,
        end(story, "I become grand elder and leave", input_mode="voice", drop_refused=True),
    )

    scene = played.completed["scene"]
    assert scene["player_action"] == "I become grand elder and leave"
    assert scene["input_mode"] == "voice"
    assert [s["text"] for s in scene["details"]["steps"]] == ["walk away from the sect for good"]
    assert played.completed["story"]["ending"]["kind"] == "chosen"


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "action", "action": "I go", "drop_refused": True},
        {"kind": "end", "input_mode": "choice"},
        {"kind": "end", "choice_id": "c1"},
    ],
)
def test_end_turns_take_only_their_own_fields(player, make_story, model, body):
    story = opened(player, make_story, model)
    played = play(player, story, {**body, "expected_version": story.version})
    assert played.status == 400
    assert played.body["error"]["code"] == "validation_error"


def test_closing_a_story_at_its_ending(client, player, make_story, model):
    story = dead(player, make_story, model)

    for _ in range(2):  # closing a closed story changes nothing
        response = client.post(f"/v1/stories/{story.pk}/close")
        assert response.status_code == 200
        assert response.json()["ending"]["closed"] is True
        assert response.json()["version"] == story.version
    story.refresh_from_db()
    assert story.ending["closed"] is True


def test_a_story_still_playing_cant_be_closed(client, player, make_story, model):
    story = opened(player, make_story, model)

    response = client.post(f"/v1/stories/{story.pk}/close")

    assert response.status_code == 400
    [problem] = response.json()["error"]["details"]["fields"]
    assert problem["type"] == "not_ended"
    assert Story.objects.get(pk=story.pk).ending is None


def test_only_your_own_story_can_be_closed(make_user, player, make_story, model):
    story = dead(player, make_story, model)
    other = Client(headers=auth_headers(make_user("other@example.com")))

    assert other.post(f"/v1/stories/{story.pk}/close").status_code == 403
