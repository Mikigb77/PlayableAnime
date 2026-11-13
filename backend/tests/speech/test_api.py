"""`POST /v1/transcriptions` (V6, docs/API.md): the app's recording, written down by the speech
model with the names the character knows, metered and billed like any model call (K2, T9)."""

import io
import json
import wave
from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role
from billing.models import CreditAccount, CreditHold, EntryKind, LedgerEntry
from drafts import service as drafts
from drafts.models import Draft
from engine.context import StorySettings
from engine.samples import cultivation_world
from graph.drafting import chain, samples
from graph.drafting.schema import DraftProposal
from graph.llm import Block, Fail, FakeBackend, Node, Reply
from graph.llm.fake import OFFLINE_TRANSCRIPT
from speech import api
from stories.models import Engine, Story
from tests.conftest import auth_headers

URL = "/v1/transcriptions"


def recording(seconds: float = 1.0) -> bytes:
    """What the app sends: 16 kHz 16-bit mono WAV."""
    out = io.BytesIO()
    with wave.open(out, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16_000)
        clip.writeframes(b"\x01\x00" * round(seconds * 16_000))
    return out.getvalue()


AUDIO = recording()


@pytest.fixture(autouse=True)
def funded_players(settings):
    """Every test account gets the starter credit (K1), and the limits stay out of the way unless
    a test sets them (T9)."""
    settings.BILLING = {
        **settings.BILLING,
        "STARTER_POLICY": "all",
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "speech": 1000},
        "PER_DAY": {**settings.BILLING["PER_DAY"], "speech": 1000},
    }


@pytest.fixture
def model(monkeypatch) -> FakeBackend:
    """The speech model for every request in the test."""
    fake = FakeBackend(default=lambda request: Reply(text="I bow to Senior Brother Zhao."))
    monkeypatch.setattr(api, "model_backend", lambda: fake)
    return fake


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


@pytest.fixture
def story(player) -> Story:
    state = cultivation_world()
    return Story.objects.create(
        owner=player,
        title=state.bible.title,
        premise="A premise.",
        genre=state.bible.genre,
        rating="mature",
        engine=Engine.GRAPH,
        state=state.model_dump(mode="json"),
        settings=StorySettings().model_dump(mode="json"),
        turn=0,
        version=1,
    )


@pytest.fixture
def draft(player) -> Draft:
    found = chain.Draft(
        premise="A street kid in Naples.",
        proposal=DraftProposal.model_validate(samples.naples()),
        rating="teen",
    )
    return Draft.objects.create(owner=player, **drafts.chain_fields(found))


def transcribe(client: Client, audio: bytes = AUDIO, content_type="audio/wav", **query):
    path = URL + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")
    return client.post(path, audio, content_type=content_type)


def balance(user) -> Decimal:
    return CreditAccount.objects.get(user=user).balance_cents


def test_a_recording_comes_back_as_text_with_the_storys_names(client, model, story, player):
    response = transcribe(client, story_id=story.id, language="en-US")

    assert response.status_code == 200, response.content
    assert response.json() == {"text": "I bow to Senior Brother Zhao."}
    [request] = model.calls(Node.SPEECH)
    assert request.audio.data == AUDIO and request.audio.mime_type == "audio/wav"
    assert request.transcription.language_codes == ("en-US",)
    assert request.transcription.vocabulary[:2] == ("Lin Feng", "Zhao Kun")
    assert "Elder Mo" not in request.transcription.vocabulary  # Lin hasn't heard of him (C6)
    assert request.transcription.smart


def test_a_dictation_is_charged_like_any_model_call(client, model, story, player):
    before = balance(player) if CreditAccount.objects.filter(user=player).exists() else None

    transcribe(client, story_id=story.id)

    [entry] = LedgerEntry.objects.filter(user=player, kind=EntryKind.SPEECH)
    assert entry.amount_cents < 0  # a fraction of a cent, but never free on our account
    assert entry.amount_cents > Decimal("-1")
    assert entry.cost_usd > 0
    assert str(entry.story_id) == str(story.id)
    assert entry.detail["models"] == ["gemini-3.5-transcribe-preview"]
    assert before is None or balance(player) == before + entry.amount_cents
    assert not CreditHold.objects.filter(user=player).exists()


def test_a_draft_gives_its_names_too(client, model, draft):
    response = transcribe(client, draft_id=draft.id)

    assert response.status_code == 200, response.content
    vocabulary = model.calls(Node.SPEECH)[0].transcription.vocabulary
    assert "Luca Esposito" in vocabulary


def test_without_a_story_or_a_draft_the_model_detects_the_language(client, model):
    response = transcribe(client)

    assert response.status_code == 200
    [request] = model.calls(Node.SPEECH)
    assert request.transcription.language_codes == () and request.transcription.vocabulary == ()


@pytest.mark.parametrize(
    ("sent", "expected"),
    [("audio/x-wav", "audio/wav"), ("audio/mp4", "audio/m4a"), ("audio/webm", "audio/webm")],
)
def test_each_audio_type_goes_to_the_model_under_its_gemini_name(client, model, sent, expected):
    assert transcribe(client, b"\x00" * 100, content_type=sent).status_code == 200
    assert model.calls(Node.SPEECH)[0].audio.mime_type == expected


def test_silence_is_an_empty_transcript(client, model):
    model.script(Node.SPEECH, Reply(text=""))

    response = transcribe(client)

    assert response.status_code == 200
    assert response.json() == {"text": ""}


def _field(response) -> dict:
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    [field] = body["details"]["fields"]
    return field


def test_a_body_that_isnt_audio_is_refused_before_any_model_call(client, model):
    response = client.post(URL, {"text": "hi"}, content_type="application/json")

    assert response.status_code == 400
    assert _field(response) | {"message": ""} == {
        "field": "Content-Type",
        "source": "header",
        "message": "",
        "type": "unsupported_audio",
    }
    assert model.requests == []


def test_an_empty_or_too_long_recording_is_refused(client, model, player):
    # Django's test client leaves out the Content-Type of an empty body; a real client sends it.
    empty = client.post(URL, b"", content_type="audio/wav", CONTENT_TYPE="audio/wav")
    assert _field(empty)["type"] == "missing"
    too_long = transcribe(client, b"\x00" * (api.MAX_AUDIO_BYTES + 1))
    assert too_long.status_code == 400
    assert _field(too_long)["type"] == "too_long"
    assert model.requests == []
    assert not LedgerEntry.objects.filter(user=player, kind=EntryKind.SPEECH).exists()


def test_a_minute_of_the_apps_recording_fits(client, model):
    assert len(recording(60)) <= api.MAX_AUDIO_BYTES
    assert transcribe(client, recording(60)).status_code == 200


def test_a_story_and_a_draft_together_are_refused(client, model, story, draft):
    response = transcribe(client, story_id=story.id, draft_id=draft.id)

    assert response.status_code == 400
    assert _field(response)["field"] == "draft_id"


def test_a_bad_language_tag_is_a_query_error(client, model):
    response = transcribe(client, language="english please")

    assert response.status_code == 400
    assert _field(response)["source"] == "query"


def test_someone_elses_story_or_draft_is_forbidden(model, story, draft, make_user):
    other = Client(headers=auth_headers(make_user("other@example.com")))

    assert transcribe(other, story_id=story.id).status_code == 403
    assert transcribe(other, draft_id=draft.id).status_code == 403
    assert transcribe(other, story_id="not-a-story").status_code == 404
    assert model.requests == []


def test_signing_in_is_required(model):
    assert transcribe(Client()).status_code == 401


@pytest.fixture
def broke(settings, make_user) -> Client:
    """An unverified email account, which gets no starter credit under the default policy (K1)."""
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "verified"}
    return Client(headers=auth_headers(make_user("broke@example.com")))


def test_out_of_credits_is_refused_before_the_model(broke, model):
    response = transcribe(broke)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "out_of_credits"
    assert model.requests == []


def test_the_owner_dictates_free_with_the_cost_recorded(model, make_user):
    owner = make_user("miki@example.com", role=Role.OWNER)

    assert transcribe(Client(headers=auth_headers(owner))).status_code == 200

    [entry] = LedgerEntry.objects.filter(user=owner, kind=EntryKind.SPEECH)
    assert entry.amount_cents == 0 and entry.unlimited
    assert Decimal(entry.detail["list_cents"]) > 0


def test_the_rate_limit_and_the_daily_quota_apply(client, model, settings, steady_minute):
    settings.BILLING = {
        **settings.BILLING,
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "speech": 1},
    }
    assert transcribe(client).status_code == 200
    limited = transcribe(client)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"

    settings.BILLING = {
        **settings.BILLING,
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "speech": 1000},
        "PER_DAY": {**settings.BILLING["PER_DAY"], "speech": 1},  # the first one counted
    }
    used_up = transcribe(client)
    assert used_up.status_code == 429
    assert used_up.json()["error"]["code"] == "quota_exceeded"
    assert "dictation" in used_up.json()["error"]["message"]


def test_a_model_failing_twice_is_unavailable_and_free(client, model, player):
    model.script(Node.SPEECH, Fail(), Fail())

    response = transcribe(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
    assert "Dictation" in response.json()["error"]["message"]
    assert not LedgerEntry.objects.filter(user=player, kind=EntryKind.SPEECH).exists()
    assert not CreditHold.objects.filter(user=player).exists()


def test_a_blocked_transcript_is_unreadable_and_free(client, model, player):
    model.script(Node.SPEECH, Block())

    response = transcribe(client)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unreadable_action"
    assert not LedgerEntry.objects.filter(user=player, kind=EntryKind.SPEECH).exists()


def test_the_players_own_key_is_never_used_for_speech(client, model, player):
    response = client.post(
        URL,
        AUDIO,
        content_type="audio/wav",
        headers={"X-LLM-Provider": "gemini", "X-LLM-Api-Key": "AIzaSyFAKE"},
    )

    assert response.status_code == 200
    assert LedgerEntry.objects.filter(user=player, kind=EntryKind.SPEECH).exists()


def test_the_log_line_has_numbers_and_never_the_words(client, model, story, log_lines):
    transcribe(client, story_id=story.id, language="en-US")

    [line] = [line for line in log_lines() if line.get("speech")]
    fields = line["speech"]
    assert fields["outcome"] == "ok"
    assert fields["audio_bytes"] == len(AUDIO)
    assert fields["context"] == "story" and fields["vocabulary"] >= 2
    assert fields["chars"] == len("I bow to Senior Brother Zhao.")
    assert fields["models"] == ["gemini-3.5-transcribe-preview"]
    raw = json.dumps(log_lines())
    assert "Senior Brother" not in raw and "Lin Feng" not in raw


def test_a_refused_dictation_is_logged_with_its_reason(broke, model, log_lines):
    transcribe(broke)

    [line] = [line for line in log_lines() if line.get("speech")]
    assert line["speech"]["outcome"] == "out_of_credits"
    assert line["severity"] == "WARNING"


def test_a_dictation_refused_before_the_model_is_logged_too(client, model, log_lines):
    transcribe(client, content_type="text/plain")
    transcribe(client, story_id="00000000-0000-0000-0000-000000000000")

    lines = [line["speech"] for line in log_lines() if line.get("speech")]
    assert [(line["outcome"], line["context"]) for line in lines] == [
        ("validation_error", "none"),
        ("not_found", "story"),
    ]
    assert lines[1]["audio_bytes"] == len(AUDIO) and lines[1]["calls"] == 0
    assert model.calls(Node.SPEECH) == []


def test_the_offline_model_answers_when_no_model_is_configured(client):
    response = transcribe(client)

    assert response.status_code == 200
    assert response.json() == {"text": OFFLINE_TRANSCRIPT}
