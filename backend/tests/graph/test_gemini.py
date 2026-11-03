"""The Gemini backend, through the real LangChain model with google-genai's network call faked."""

import base64

import pytest
from google.genai import errors as genai_errors
from google.genai import types as gt
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from graph.llm import (
    BadKey,
    CallOptions,
    Completed,
    ImagePart,
    ImageSpec,
    LLMBlocked,
    LLMUnavailable,
    Message,
    ModelClient,
    ModelConfig,
    Node,
    Prompt,
    TextDelta,
    TurnTelemetry,
)
from graph.llm.gemini import (
    GEMINI_API_BASE_URL,
    GeminiBackend,
    call_kwargs,
    classify,
    to_messages,
    to_safety_settings,
)
from graph.llm.safety import safety_settings
from graph.llm.types import Request
from tests.graph.conftest import Narration, collect, run

KEY = "AIzaSyFAKE-player-key"
PROMPT = Prompt.build("You are the narrator.", "I throw the stone.")


def _response(text=None, *, finish=None, usage=None, ratings=None, block=None, image=None):
    parts = []
    if text is not None:
        parts.append(gt.Part(text=text))
    if image is not None:
        parts.append(gt.Part(inline_data=gt.Blob(data=image, mime_type="image/png")))
    candidates = None
    if block is None:
        candidates = [
            gt.Candidate(
                content=gt.Content(role="model", parts=parts),
                finish_reason=finish,
                safety_ratings=ratings,
            )
        ]
    return gt.GenerateContentResponse(
        candidates=candidates,
        prompt_feedback=gt.GenerateContentResponsePromptFeedback(block_reason=block)
        if block
        else None,
        usage_metadata=gt.GenerateContentResponseUsageMetadata(
            prompt_token_count=usage[0],
            candidates_token_count=usage[1],
            thoughts_token_count=usage[2],
            total_token_count=sum(usage),
        )
        if usage
        else None,
        model_version="gemini-3.5-flash",
    )


class Script:
    """Replaces google-genai's streaming call with scripted attempts."""

    def __init__(self, *attempts):
        self.attempts = list(attempts)
        self.requests: list[dict] = []

    async def __call__(self, **request):
        self.requests.append(request)
        attempt = self.attempts.pop(0)
        if isinstance(attempt, Exception):
            raise attempt

        async def chunks():
            for item in attempt:
                if isinstance(item, Exception):
                    raise item
                yield item

        return chunks()


def _client(script: Script, *, byok: bool = True, telemetry=None) -> ModelClient:
    backend = (
        GeminiBackend.with_api_key(KEY)
        if byok
        else GeminiBackend.vertex(project="p", location="global")
    )
    make_model = backend._make_model

    def patched(name):
        model = make_model(name)
        model.client.aio.models.generate_content_stream = script
        return model

    backend._make_model = patched
    return ModelClient(
        backend, ModelConfig(), rating="mature", recorder=telemetry, byok=byok, retry_delay_s=0
    )


SCENE_JSON = '{"title": "Cave", "narration": "You crouch. You throw.", "choices": ["Run"]}'


def test_a_streamed_structured_call_end_to_end():
    telemetry = TurnTelemetry()
    script = Script(
        [
            _response(SCENE_JSON[:30], usage=(800, 10, 0)),
            _response(SCENE_JSON[30:], finish=gt.FinishReason.STOP, usage=(800, 40, 25)),
        ]
    )

    events = run(
        collect(
            _client(script, telemetry=telemetry).stream_structured(
                Node.NARRATOR, PROMPT, Narration, field="narration"
            )
        )
    )

    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "You crouch. You throw."
    assert events[-1] == Completed(Narration.model_validate_json(SCENE_JSON))
    [record] = telemetry.calls
    assert (record.input_tokens, record.output_tokens, record.thinking_tokens) == (800, 65, 25)
    assert record.provider == "gemini_api" and record.byok
    config = script.requests[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.thinking_config.thinking_level == "LOW"
    assert {s.category.name: s.threshold.name for s in config.safety_settings} == {
        "HARM_CATEGORY_HARASSMENT": "OFF",
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_ONLY_HIGH",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_ONLY_HIGH",
    }


def test_a_safety_finish_is_a_block_with_its_category():
    rating = gt.SafetyRating(
        category=gt.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        probability=gt.HarmProbability.HIGH,
        blocked=True,
    )
    script = Script(
        [
            _response('{"narration": "You', usage=(10, 3, 0)),
            _response("", finish=gt.FinishReason.SAFETY, ratings=[rating], usage=(10, 4, 0)),
        ]
    )

    with pytest.raises(LLMBlocked) as raised:
        run(
            collect(
                _client(script).stream_structured(
                    Node.NARRATOR, PROMPT, Narration, field="narration"
                )
            )
        )

    assert raised.value.categories == ("sexually_explicit",)
    assert raised.value.stage == "response"
    assert raised.value.streamed


def test_a_blocked_prompt_is_a_prompt_stage_block():
    script = Script([_response(block=gt.BlockedReason.PROHIBITED_CONTENT, usage=(10, 0, 0))])

    with pytest.raises(LLMBlocked) as raised:
        run(_client(script).structured(Node.INTERPRET, PROMPT, Narration))

    assert raised.value.stage == "prompt"
    assert raised.value.categories == ("prohibited_content",)
    assert len(script.requests) == 1


def test_an_invalid_player_key_is_bad_key_and_never_appears_in_errors(caplog):
    error = genai_errors.ClientError(
        400,
        {
            "error": {
                "code": 400,
                "message": f"API key not valid: {KEY}",
                "status": "INVALID_ARGUMENT",
            }
        },
    )
    script = Script(error)

    with pytest.raises(BadKey) as raised:
        run(_client(script).structured(Node.NARRATOR, PROMPT, Narration))

    assert raised.value.__cause__ is None and raised.value.__context__ is not None
    assert KEY not in str(raised.value)
    for record in caplog.records:
        assert KEY not in record.getMessage() and KEY not in repr(record.__dict__)


def test_an_overloaded_model_is_retried_once_then_unavailable():
    overloaded = genai_errors.ServerError(503, {"error": {"code": 503, "status": "UNAVAILABLE"}})
    telemetry = TurnTelemetry()
    script = Script(overloaded, [overloaded])

    with pytest.raises(LLMUnavailable):
        run(
            _client(script, byok=False, telemetry=telemetry).structured(
                Node.NARRATOR, PROMPT, Narration
            )
        )

    assert len(script.requests) == 2
    assert telemetry.calls[0].retries == 1


def test_a_permission_error_on_our_own_account_is_unavailable_not_bad_key():
    denied = genai_errors.ClientError(403, {"error": {"code": 403, "status": "PERMISSION_DENIED"}})
    script = Script(denied)

    with pytest.raises(LLMUnavailable):
        run(_client(script, byok=False).structured(Node.NARRATOR, PROMPT, Narration))
    assert len(script.requests) == 1


def test_a_picture_comes_back_as_bytes():
    png = b"\x89PNG\r\n\x1a\nfake"
    script = Script([_response(image=png, finish=gt.FinishReason.STOP, usage=(1200, 1120, 0))])

    image = run(_client(script).image(Node.PICTURE, PROMPT, spec=ImageSpec(aspect_ratio="16:9")))

    assert image.data == png and image.mime_type == "image/png"
    config = script.requests[0]["config"]
    assert config.response_modalities == ["IMAGE"]
    assert config.image_config.aspect_ratio == "16:9"
    assert config.image_config.image_size == "1K"
    assert config.thinking_config is None


def test_messages_carry_the_system_prompt_history_and_reference_images():
    prompt = Prompt(
        system="House style.",
        messages=(
            Message("user", "Draw Ren."),
            Message("model", "Done."),
            Message("user", "Now Zhao."),
        ),
        images=(ImagePart(b"face", "image/jpeg"),),
    )

    messages = to_messages(prompt)

    assert [type(m) for m in messages] == [SystemMessage, HumanMessage, AIMessage, HumanMessage]
    content = messages[-1].content
    assert content[0] == {"type": "text", "text": "Now Zhao."}
    expected = "data:image/jpeg;base64," + base64.b64encode(b"face").decode()
    assert content[1]["image_url"]["url"] == expected


def test_call_kwargs_map_our_settings_to_gemini():
    request = Request(
        node=Node.NARRATOR,
        model="gemini-3.5-flash",
        prompt=PROMPT,
        options=CallOptions(
            temperature=1.0, max_output_tokens=10, thinking="low", seed=3, timeout_s=9
        ),
        safety=safety_settings("teen"),
        json_schema=Narration.model_json_schema(),
    )

    kwargs = call_kwargs(request)

    assert kwargs["safety_settings"] == to_safety_settings(safety_settings("teen"))
    assert kwargs["thinking_level"] == "low"
    assert kwargs["temperature"] == 1.0 and kwargs["seed"] == 3 and kwargs["timeout"] == 9
    assert kwargs["response_json_schema"] == Narration.model_json_schema()


@pytest.mark.parametrize(
    ("error", "byok", "kind"),
    [
        (genai_errors.ClientError(429, {"error": {"code": 429}}), False, "transient"),
        (genai_errors.ClientError(404, {"error": {"code": 404}}), False, "invalid"),
        (genai_errors.ClientError(401, {"error": {"code": 401}}), True, "auth"),
        (genai_errors.ClientError(400, {"error": {"message": "bad schema"}}), True, "invalid"),
        (genai_errors.ServerError(500, {"error": {"code": 500}}), False, "transient"),
        (TimeoutError(), False, "transient"),
        (ConnectionResetError(), False, "transient"),
        (ValueError("API key required"), True, "invalid"),
    ],
)
def test_classify(error, byok, kind):
    assert classify(error, byok=byok).kind == kind


def test_httpx_failures_are_transient():
    import httpx

    assert classify(httpx.ReadTimeout("slow"), byok=False).kind == "transient"
    assert classify(httpx.ConnectError("down"), byok=False).kind == "transient"


def test_a_player_key_cannot_be_rerouted_by_the_environment(monkeypatch):
    monkeypatch.setenv("LANGSMITH_GATEWAY", "https://gateway.example")
    backend = GeminiBackend.with_api_key(KEY)

    model = backend._make_model("gemini-3.5-flash")

    assert model.client._api_client._http_options.base_url == GEMINI_API_BASE_URL
    assert KEY not in repr(model.google_api_key)
