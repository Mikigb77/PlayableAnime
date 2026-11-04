"""Dictation through the model layer (V6): the speech node, the Gemini backend's transcription
call with google-genai's network call faked, the offline model, pricing and telemetry."""

import pytest
from google.genai import errors as genai_errors
from google.genai import types as gt

from graph.llm import (
    AudioPart,
    Block,
    Fail,
    LLMBlocked,
    LLMUnavailable,
    ModelClient,
    ModelConfig,
    Node,
    Reply,
    Transcription,
    TurnTelemetry,
    build_client,
)
from graph.llm.config import DEFAULT_NODES
from graph.llm.fake import OFFLINE_TRANSCRIPT, audio_tokens
from graph.llm.gemini import GeminiBackend, transcription_chunk, transcription_config
from graph.llm.pricing import price_for
from graph.llm.types import CallOptions, Prompt, Request
from tests.graph.conftest import run

AUDIO = AudioPart(b"RIFF" + b"\x00" * 31_996, "audio/wav")  # about a second
SPEC = Transcription(language_codes=("en-US",), vocabulary=("Zhao", "Azure Cloud Sect"))


def _response(*parts, finish=gt.FinishReason.STOP, usage=(32, 6, 0), block=None, ratings=None):
    return gt.GenerateContentResponse(
        candidates=None
        if block
        else [
            gt.Candidate(
                content=gt.Content(role="model", parts=list(parts)),
                finish_reason=finish,
                safety_ratings=ratings,
            )
        ],
        prompt_feedback=gt.GenerateContentResponsePromptFeedback(block_reason=block)
        if block
        else None,
        usage_metadata=gt.GenerateContentResponseUsageMetadata(
            prompt_token_count=usage[0],
            candidates_token_count=usage[1],
            thoughts_token_count=usage[2],
        ),
    )


class Calls:
    """Replaces google-genai's `generate_content` with scripted attempts."""

    def __init__(self, *attempts):
        self.attempts = list(attempts)
        self.requests: list[dict] = []

    async def __call__(self, **request):
        self.requests.append(request)
        attempt = self.attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt
        return attempt


def _gemini_client(calls: Calls, telemetry: TurnTelemetry | None = None) -> ModelClient:
    backend = GeminiBackend.vertex(project="p", location="global")
    make_model = backend._make_model

    def patched(name):
        model = make_model(name)
        model.client.aio.models.generate_content = calls
        return model

    backend._make_model = patched
    return ModelClient(backend, ModelConfig(), rating="teen", recorder=telemetry, retry_delay_s=0)


def test_the_speech_node_is_gemini_35_transcribe_with_a_short_deadline():
    settings = DEFAULT_NODES[Node.SPEECH]
    assert settings.model == "gemini-3.5-transcribe-preview"
    assert settings.options.timeout_s == 20
    config = ModelConfig.from_env({"SPEECH_MODEL": "gemini-4-transcribe"})
    assert config.node(Node.SPEECH).model == "gemini-4-transcribe"


def test_the_speech_model_is_priced_from_the_table():
    price, known = price_for("gemini-3.5-transcribe-preview")
    assert known
    assert (str(price.input_per_m), str(price.output_per_m)) == ("2.00", "12.00")
    # The live model is another model, with another price.
    assert not price_for("gemini-3.5-transcribe-live-preview")[1]


def test_a_recording_goes_inline_with_dictations_settings():
    telemetry = TurnTelemetry()
    calls = Calls(_response(gt.Part(text="I bow to Senior Brother Zhao.")))

    text = run(_gemini_client(calls, telemetry).transcribe(Node.SPEECH, AUDIO, SPEC))

    assert text == "I bow to Senior Brother Zhao."
    [request] = calls.requests
    assert request["model"] == "gemini-3.5-transcribe-preview"
    [part] = request["contents"]
    assert part.inline_data.data == AUDIO.data
    assert part.inline_data.mime_type == "audio/wav"
    audio = request["config"].audio_transcription_config
    assert audio.language_codes == ["en-US"]
    assert audio.custom_vocabulary == ["Zhao", "Azure Cloud Sect"]
    assert audio.mode == gt.AudioTranscriptionConfigMode.SMART
    assert request["config"].safety_settings is None  # the player's words are never filtered
    [call] = telemetry.calls
    assert (call.node, call.input_tokens, call.output_tokens) == ("speech", 32, 6)
    assert call.price_known and call.cost_usd > 0


def test_a_transcript_in_audio_transcription_parts_is_read_too():
    response = _response(
        gt.Part(audio_transcription=gt.Transcription(text="I draw my blade.")),
        gt.Part(text="Then I wait.", thought=True),
        gt.Part(audio_transcription=gt.Transcription(text=" Then I wait. ")),
    )

    chunk = transcription_chunk(response)

    assert chunk.text == "I draw my blade. Then I wait."
    assert chunk.finish is not None and chunk.finish.reason == "stop"


def test_silence_is_an_empty_transcript_not_a_failure():
    calls = Calls(_response())

    assert run(_gemini_client(calls).transcribe(Node.SPEECH, AUDIO, SPEC)) == ""
    assert len(calls.requests) == 1  # never retried


def test_no_language_and_no_names_leave_the_model_to_detect_them():
    request = Request(
        node=Node.SPEECH,
        model="m",
        prompt=Prompt.build("", ""),
        options=CallOptions(max_output_tokens=512),
        safety={},
        audio=AUDIO,
        transcription=Transcription(smart=False),
    )

    config = transcription_config(request)

    audio = config.audio_transcription_config
    assert audio.language_codes is None and audio.custom_vocabulary is None
    assert audio.mode is None  # verbatim, the model's default
    assert config.max_output_tokens == 512


def test_an_overloaded_speech_model_is_retried_once_then_unavailable():
    overloaded = genai_errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
    telemetry = TurnTelemetry()
    calls = Calls(overloaded, overloaded)

    with pytest.raises(LLMUnavailable):
        run(_gemini_client(calls, telemetry).transcribe(Node.SPEECH, AUDIO, SPEC))

    assert len(calls.requests) == 2
    assert telemetry.calls[0].outcome == "unavailable"


def test_a_blocked_transcript_is_a_block():
    calls = Calls(_response(finish=gt.FinishReason.PROHIBITED_CONTENT))

    with pytest.raises(LLMBlocked) as blocked:
        run(_gemini_client(calls).transcribe(Node.SPEECH, AUDIO, SPEC))

    assert blocked.value.categories == ("prohibited_content",)


def test_the_fake_backend_scripts_transcripts_and_counts_audio_tokens(make_client, fake, telemetry):
    fake.script(Node.SPEECH, Fail(), Reply(text="  I run.  "))

    text = run(make_client().transcribe(Node.SPEECH, AUDIO, SPEC))

    assert text == "I run."
    [request, _retry] = fake.calls(Node.SPEECH)
    assert request.audio == AUDIO and request.transcription == SPEC
    assert request.safety == {}
    assert telemetry.calls[0].input_tokens == audio_tokens(AUDIO.data) == 32
    assert telemetry.calls[0].retries == 1


def test_a_scripted_block_is_a_block(make_client, fake):
    fake.script(Node.SPEECH, Block())

    with pytest.raises(LLMBlocked):
        run(make_client().transcribe(Node.SPEECH, AUDIO, SPEC))


def test_the_offline_model_hears_a_fixed_line():
    client = build_client(rating="teen", config=ModelConfig(provider="fake"))

    assert run(client.transcribe(Node.SPEECH, AUDIO)) == OFFLINE_TRANSCRIPT


def test_reprs_never_show_the_audio_or_the_names():
    assert repr(AUDIO) == "AudioPart(mime_type='audio/wav', bytes=32000)"
    assert "Zhao" not in repr(SPEC)
    assert repr(SPEC) == "Transcription(languages=['en-US'], vocabulary=2, smart=True)"
