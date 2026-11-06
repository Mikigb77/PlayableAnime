"""`POST /v1/stories/{id}/scenes/{turn}/audio` (V8 to V10, docs/API.md): a scene read aloud in the
studio voice, a part at a time, each part read and charged once per voice and kept."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import Role
from billing.models import CreditHold, EntryKind, LedgerEntry
from engine.context import StorySettings
from engine.samples import cultivation_world
from graph.llm import Block, Fail, FakeBackend, Node, Reply
from graph.llm.fake import offline_speech
from media.storage import get_storage
from moderation.models import Report
from speech import reading_api
from speech.models import AudioStatus, SceneAudio
from speech.reading import READING_STYLE, reading_parts
from speech.voices import DEFAULT_VOICE
from stories.models import Engine, Scene, SceneKind, Story
from tests.conftest import auth_headers

LONG_PARAGRAPH = " ".join(
    ["Lin Feng crosses the courtyard, his sleeves snapping in the wind off the peaks."] * 12
)
NARRATION = (
    f"The bell of the *Azure Peak* rings once.\n\n{LONG_PARAGRAPH}\n\n"
    "Elder Mo waits at the gate, and he is smiling."
)


@pytest.fixture(autouse=True)
def funded_players(settings, tmp_path):
    """Every test account gets the starter credit (K1), the limits stay out of the way unless a
    test sets them (T9), and files go to a fresh folder."""
    settings.PICTURE_ROOT = tmp_path / "files"
    settings.BILLING = {
        **settings.BILLING,
        "STARTER_POLICY": "all",
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "voice": 1000},
        "PER_DAY": {**settings.BILLING["PER_DAY"], "voice": 1000},
    }


@pytest.fixture
def model(monkeypatch) -> FakeBackend:
    """The voice model for every request in the test: two seconds of speech for any part."""
    fake = FakeBackend(default=lambda request: Reply(audio=offline_speech("x" * 80)))
    monkeypatch.setattr(reading_api, "model_backend", lambda: fake)
    return fake


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


@pytest.fixture
def story(player) -> Story:
    state = cultivation_world()
    story = Story.objects.create(
        owner=player,
        title=state.bible.title,
        premise="A premise.",
        genre=state.bible.genre,
        rating="mature",
        engine=Engine.GRAPH,
        state=state.model_dump(mode="json"),
        settings=StorySettings().model_dump(mode="json"),
        turn=1,
        version=2,
    )
    Scene.objects.create(story=story, turn=1, kind=SceneKind.OPENING, narration=NARRATION)
    return story


def read(client: Client, story: Story, turn: int = 1, **query):
    path = f"/v1/stories/{story.id}/scenes/{turn}/audio"
    if query:
        path += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return client.post(path)


def entries(user):
    return LedgerEntry.objects.filter(user=user, kind=EntryKind.VOICE)


def test_the_first_part_comes_back_as_an_mp3_with_how_many_parts_there_are(
    client, model, story, player
):
    response = read(client, story)

    assert response.status_code == 200, response.content
    body = response.json()
    parts = reading_parts(NARRATION)
    assert body["status"] == "ready"
    assert body["part"] == 0 and body["parts"] == len(parts) > 1
    assert body["text"] == parts[0]
    assert body["duration_ms"] == 2000
    assert body["url"].startswith("http://testserver/media/stories/")
    assert body["url"].split("?")[0].endswith(".mp3") and body["expires_at"]
    [request] = model.calls(Node.VOICE)
    assert request.reading.voice == DEFAULT_VOICE
    text = request.prompt.messages[-1].text
    assert text.startswith(READING_STYLE) and text.endswith(parts[0])
    assert "*" not in text
    assert request.safety == {}  # the player already read it under the story's rating (F5)
    [audio] = SceneAudio.objects.all()
    assert get_storage().load(audio.storage_key)[:1] in (b"I", b"\xff")


def test_each_part_and_voice_is_read_once_and_kept(client, model, story, player):
    first = read(client, story, part=1).json()
    again = read(client, story, part=1).json()
    other_voice = read(client, story, part=1, voice="Charon").json()

    assert again["status"] == "ready" and again["url"].split("?")[0] == first["url"].split("?")[0]
    assert other_voice["url"].split("?")[0] != first["url"].split("?")[0]
    assert [r.reading.voice for r in model.calls(Node.VOICE)] == [DEFAULT_VOICE, "Charon"]
    assert entries(player).count() == 2  # hearing a part again costs nothing (V10)


def test_a_part_is_charged_like_any_model_call(client, model, story, player):
    read(client, story)

    [entry] = entries(player)
    assert Decimal("-3") < entry.amount_cents < 0
    assert entry.cost_usd > 0
    assert str(entry.story_id) == str(story.id) and entry.turn == 1
    assert entry.detail["models"] == ["gemini-3.8-flash-lite-tts"]
    assert not CreditHold.objects.filter(user=player).exists()


def test_the_owner_listens_free_with_the_cost_recorded(model, story, make_user):
    owner = make_user("miki@example.com", role=Role.OWNER)
    story.owner = owner
    story.save()

    assert read(Client(headers=auth_headers(owner)), story).status_code == 200

    [entry] = entries(owner)
    assert entry.amount_cents == 0 and entry.unlimited


def test_a_part_another_request_is_reading_answers_pending(client, model, story):
    scene = Scene.objects.get(story=story, turn=1)
    SceneAudio.objects.create(scene=scene, voice=DEFAULT_VOICE, part=0, status=AudioStatus.PENDING)

    body = read(client, story).json()

    assert body["status"] == "pending" and body["url"] is None
    assert model.requests == []


def test_a_part_left_pending_by_a_request_that_died_is_read_again(client, model, story):
    scene = Scene.objects.get(story=story, turn=1)
    stale = SceneAudio.objects.create(
        scene=scene, voice=DEFAULT_VOICE, part=0, status=AudioStatus.PENDING
    )
    SceneAudio.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(seconds=reading_api.STALE_AFTER_S + 1)
    )

    assert read(client, story).json()["status"] == "ready"
    assert len(model.calls(Node.VOICE)) == 1


def test_a_part_the_voice_refuses_is_blocked_for_good_and_free(client, model, story, player):
    model.script(Node.VOICE, Block(categories=("dangerous_content",)))

    first = read(client, story).json()
    again = read(client, story).json()

    assert first["status"] == again["status"] == "blocked"
    assert first["url"] is None and first["parts"] > 1
    assert first["text"] == reading_parts(NARRATION)[0]  # for the phone's voice to read
    assert len(model.calls(Node.VOICE)) == 1
    assert not entries(player).exists()


def test_a_model_failing_twice_is_unavailable_free_and_tried_again_later(
    client, model, story, player
):
    model.script(Node.VOICE, Fail(), Fail())

    response = read(client, story)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
    assert not entries(player).exists()
    assert not SceneAudio.objects.exists()
    assert not CreditHold.objects.filter(user=player).exists()
    assert read(client, story).json()["status"] == "ready"


def test_speech_that_cant_be_read_is_unavailable_and_free(client, model, story, player):
    model.script(Node.VOICE, Reply(audio=b"\x00" * 10, audio_type="audio/ogg"))

    assert read(client, story).status_code == 503
    assert not entries(player).exists()
    assert not SceneAudio.objects.exists()


@pytest.fixture
def broke(settings, make_user) -> Client:
    """An unverified email account, which gets no starter credit under the default policy (K1)."""
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "verified"}
    return make_user("broke@example.com")


def test_out_of_credits_is_refused_before_the_model(broke, model, story):
    story.owner = broke
    story.save()

    response = read(Client(headers=auth_headers(broke)), story)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "out_of_credits"
    assert model.requests == []
    assert not SceneAudio.objects.exists()  # nothing is left pending


def test_the_daily_quota_says_the_phones_voice_still_works(client, model, story, settings):
    settings.BILLING = {
        **settings.BILLING,
        "PER_DAY": {**settings.BILLING["PER_DAY"], "voice": 1},
    }
    assert read(client, story).status_code == 200

    used_up = read(client, story, part=1)

    assert used_up.status_code == 429
    assert used_up.json()["error"]["code"] == "quota_exceeded"
    assert "phone" in used_up.json()["error"]["message"]


def test_the_players_own_key_is_never_used(client, model, story, player):
    response = client.post(
        f"/v1/stories/{story.id}/scenes/1/audio",
        headers={"X-LLM-Provider": "gemini", "X-LLM-Api-Key": "AIzaSyFAKE"},
    )

    assert response.status_code == 200
    assert entries(player).exists()


def test_a_blocked_scene_is_never_read(client, model, story, player):
    scene = Scene.objects.get(story=story, turn=1)
    Report.objects.create(story=story, scene=scene, reporter=player, category="other", block=True)

    assert read(client, story).status_code == 404
    assert model.requests == []


def test_unknown_scenes_parts_and_voices_are_refused(client, model, story):
    assert read(client, story, turn=9).status_code == 404
    out_of_range = read(client, story, part=50)
    assert out_of_range.status_code == 400
    assert out_of_range.json()["error"]["details"]["fields"][0]["field"] == "part"
    unknown = read(client, story, voice="Robot")
    assert unknown.status_code == 400
    assert unknown.json()["error"]["details"]["fields"][0]["type"] == "unknown_voice"
    assert model.requests == []


def test_someone_elses_story_is_forbidden(model, story, make_user):
    other = Client(headers=auth_headers(make_user("other@example.com")))

    assert read(other, story).status_code == 403
    assert model.requests == []


def test_a_parts_file_leaves_with_its_story(
    client, model, story, django_capture_on_commit_callbacks
):
    read(client, story)
    [audio] = SceneAudio.objects.all()
    storage = get_storage()
    assert storage.exists(audio.storage_key)

    with django_capture_on_commit_callbacks(execute=True):
        story.delete()

    assert not SceneAudio.objects.exists()
    assert not storage.exists(audio.storage_key)


def test_the_log_line_has_numbers_and_never_the_words(client, model, story, log_lines):
    read(client, story)
    read(client, story)

    [first, kept] = [line["voice"] for line in log_lines() if line.get("voice")]
    assert first["outcome"] == "ok" and first["read"] and first["duration_ms"] == 2000
    assert first["models"] == ["gemini-3.8-flash-lite-tts"] and first["cost_usd"] > 0
    assert kept["outcome"] == "kept" and not kept["read"] and kept["calls"] == 0
    raw = json.dumps(log_lines())
    assert "Azure Peak" not in raw and "Lin Feng" not in raw
