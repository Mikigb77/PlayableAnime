"""Reading aloud through the model layer (V9): the voice node, the Gemini backend's text-to-speech
call with google-genai's network call faked, the offline model, pricing and telemetry."""

from decimal import Decimal

import pytest
from google.genai import errors as genai_errors
from google.genai import types as gt

from engine.context import Language
from graph.llm import (
    Block,
    Fail,
    FakeBackend,
    LLMBlocked,
    LLMUnavailable,
    ModelConfig,
    Node,
    Reading,
    Reply,
    TurnTelemetry,
    build_client,
    offline_reply,
)
from graph.llm.config import DEFAULT_NODES
from graph.llm.fake import offline_speech, speech_tokens
from graph.llm.gemini import GEMINI_SPEECH_TYPE, GeminiBackend, reading_chunk
from graph.llm.pricing import estimate_cost, price_for
from graph.llm.types import Usage
from speech.voices import reading_locale
from tests.graph.conftest import run
from tests.graph.test_speech import Calls, _gemini_client, _response

PCM = b"\x01\x00" * 24_000  # a second at 24 kHz
READING = Reading(voice="Sulafat", language="es-ES")
TEXT = "Read this aloud as a storyteller would:\n\nThe bell rings once."


def _speech(data=PCM, mime_type=GEMINI_SPEECH_TYPE):
    return gt.Part(inline_data=gt.Blob(data=data, mime_type=mime_type))


def test_the_voice_node_is_gemini_38_flash_lite_tts_with_room_for_a_long_part():
    settings = DEFAULT_NODES[Node.VOICE]
    assert settings.model == "gemini-3.8-flash-lite-tts"
    assert settings.options.timeout_s == 40
    config = ModelConfig.from_env({"VOICE_MODEL": "gemini-3.8-flash-tts"})
    assert config.node(Node.VOICE).model == "gemini-3.8-flash-tts"


def test_the_voice_models_are_priced_at_their_2027_prices():
    lite, known = price_for("gemini-3.8-flash-lite-tts")
    assert known and (str(lite.input_per_m), str(lite.output_per_m)) == ("1.00", "12.00")
    flash, known = price_for("gemini-3.8-flash-tts-preview")
    assert known and str(flash.output_per_m) == "18.00"
    # A minute of speech is 1,500 audio tokens: about 1.8 cents on Flash-Lite TTS.
    cost, _ = estimate_cost("gemini-3.8-flash-lite-tts", Usage(100, 1500))
    assert cost == Decimal("0.0181")


def test_a_text_goes_to_gemini_with_the_voice_and_audio_out():
    telemetry = TurnTelemetry()
    calls = Calls(_response(_speech(), usage=(40, 25, 0)))

    spoken = run(_gemini_client(calls, telemetry).read_aloud(Node.VOICE, TEXT, READING))

    assert spoken.data == PCM and spoken.mime_type == GEMINI_SPEECH_TYPE
    [request] = calls.requests
    assert request["model"] == "gemini-3.8-flash-lite-tts"
    assert request["contents"] == TEXT
    config = request["config"]
    assert config.response_modalities == ["AUDIO"]
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Sulafat"
    # The language and accent are named, so Spanish is read as Spain speaks it (Miki, 2026-11-08).
    assert config.speech_config.language_code == "es-ES"
    assert config.safety_settings is None  # the player already read it (F5)
    [record] = telemetry.calls
    assert (record.node, record.input_tokens, record.output_tokens) == ("voice", 40, 25)
    assert record.cost_usd > 0 and record.price_known


def test_without_a_language_the_model_guesses_it():
    calls = Calls(_response(_speech()))

    run(_gemini_client(calls).read_aloud(Node.VOICE, TEXT, Reading(voice="Charon")))

    [request] = calls.requests
    assert request["config"].speech_config.language_code is None


def test_every_story_language_is_read_in_a_named_accent():
    """Spanish from Spain, never Latin American; English as dictation hears it (V4); Catalan."""
    assert {language: reading_locale(language) for language in Language} == {
        Language.EN: "en-US",
        Language.ES: "es-ES",
        Language.CA: "ca-ES",
    }


def test_speech_in_several_parts_is_joined_in_order():
    calls = Calls(_response(_speech(b"\x01\x00"), _speech(b"\x02\x00")))

    spoken = run(_gemini_client(calls).read_aloud(Node.VOICE, TEXT, READING))

    assert spoken.data == b"\x01\x00\x02\x00"


def test_a_part_without_a_type_is_geminis_pcm():
    chunk = reading_chunk(_response(gt.Part(inline_data=gt.Blob(data=PCM))))

    assert chunk.audio[0].mime_type == GEMINI_SPEECH_TYPE


def test_an_answer_without_speech_is_retried_then_unavailable():
    calls = Calls(_response(gt.Part(text="I can't.")), _response(gt.Part(text="I can't.")))

    with pytest.raises(LLMUnavailable):
        run(_gemini_client(calls).read_aloud(Node.VOICE, TEXT, READING))
    assert len(calls.requests) == 2


def test_a_refused_text_is_blocked():
    calls = Calls(_response(block=gt.BlockedReason.PROHIBITED_CONTENT))

    with pytest.raises(LLMBlocked):
        run(_gemini_client(calls).read_aloud(Node.VOICE, TEXT, READING))


def test_an_unknown_voice_or_model_is_not_retried():
    calls = Calls(genai_errors.ClientError(400, {"error": {"message": "Unknown voice"}}))

    with pytest.raises(LLMUnavailable):
        run(_gemini_client(calls).read_aloud(Node.VOICE, TEXT, READING))
    assert len(calls.requests) == 1


def test_a_players_key_never_reads_aloud():
    backend = GeminiBackend.with_api_key("AIzaSyFAKE")
    client = build_client(rating="teen", backend=backend)

    with pytest.raises(LLMUnavailable):
        run(client.read_aloud(Node.VOICE, TEXT, READING))


def test_the_offline_model_reads_a_tone_about_as_long_as_the_text(make_client):
    offline = FakeBackend(default=offline_reply)

    spoken = run(make_client(backend=offline).read_aloud(Node.VOICE, "x" * 80, READING))

    assert spoken.data == offline_speech("x" * 80)
    assert len(spoken.data) == 2 * 24_000 * 2  # two seconds
    [request] = offline.calls(Node.VOICE)
    assert request.reading == READING


def test_a_fake_failure_is_retried_and_a_fake_block_raises(make_client, fake):
    fake.script(Node.VOICE, Fail(), Reply(audio=PCM), Block())

    assert run(make_client().read_aloud(Node.VOICE, TEXT, READING)).data == PCM
    with pytest.raises(LLMBlocked):
        run(make_client().read_aloud(Node.VOICE, TEXT, READING))


def test_speech_is_billed_at_25_tokens_a_second():
    assert speech_tokens(PCM) == 25
