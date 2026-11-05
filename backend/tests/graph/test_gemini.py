"""The Gemini backend, through the real LangChain model with google-genai's network call faked."""

import asyncio
import base64
import logging

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
    gemini,
)
from graph.llm.gemini import (
    GEMINI_API_BASE_URL,
    GEMINI_SCHEMA_KEYWORDS,
    SCHEMA_IN_PROMPT,
    GeminiBackend,
    call_kwargs,
    classify,
    gemini_schema,
    to_messages,
    to_safety_settings,
)
from graph.llm.pricing import estimate_cost
from graph.llm.safety import safety_settings
from graph.llm.types import Request, Usage
from tests.graph.conftest import Narration, collect, run

KEY = "AIzaSyFAKE-player-key"
# Vertex AI's answer to a response schema outside what Gemini takes (2026-11-04).
SCHEMA_REFUSED = genai_errors.ClientError(
    400,
    {
        "error": {
            "code": 400,
            "message": "Request contains an invalid argument.",
            "status": "INVALID_ARGUMENT",
        }
    },
)


@pytest.fixture(autouse=True)
def _forget_refused_schemas():
    gemini._REFUSED_SCHEMAS.clear()
    yield
    gemini._REFUSED_SCHEMAS.clear()


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
            cached_content_token_count=usage[3] if len(usage) > 3 else None,
            total_token_count=sum(usage[:3]),
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
        backend,
        ModelConfig(),
        rating="mature",
        recorder=telemetry,
        byok=byok,
        owns_backend=byok,
        retry_delay_s=0,
    )


SCENE_JSON = '{"title": "Cave", "narration": "You crouch. You throw.", "choices": ["Run"]}'


def test_cached_prompt_tokens_are_recorded_and_billed_at_the_cached_rate():
    # Implicit caching: Gemini reports how much of the prompt it had just seen.
    telemetry = TurnTelemetry()
    script = Script(
        [
            _response(SCENE_JSON[:30], usage=(14000, 10, 0, 9000)),
            _response(SCENE_JSON[30:], finish=gt.FinishReason.STOP, usage=(14000, 40, 0, 9000)),
        ]
    )

    run(
        collect(
            _client(script, telemetry=telemetry).stream_structured(
                Node.NARRATOR, PROMPT, Narration, field="narration"
            )
        )
    )

    [record] = telemetry.calls
    assert (record.input_tokens, record.cached_tokens) == (14000, 9000)
    assert telemetry.summary()["cached_tokens"] == 9000
    full, _ = estimate_cost(record.model, Usage(14000, 40))
    assert record.cost_usd < full


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
        # The Mature narrator tells a chosen death; code holds F3's line on instructions.
        "HARM_CATEGORY_DANGEROUS_CONTENT": "OFF",
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

    chain, error = [], raised.value
    while error is not None:
        chain.append(error)
        error = error.__cause__ or error.__context__
    assert len(chain) == 2  # BadKey, then the scrubbed ProviderError, and nothing older
    for error in chain:
        assert KEY not in str(error) and KEY not in repr(vars(error))
    for record in caplog.records:
        assert KEY not in record.getMessage() and KEY not in repr(record.__dict__)


def test_a_quota_error_logs_its_reason_without_the_player_key(caplog):
    """A transient failure's log keeps the provider's words (which quota ran out) for whoever
    reads the logs, but never the player's key (T6)."""
    quota = genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": f"Quota exceeded for key {KEY} on gemini-3.5-flash.",
                "status": "RESOURCE_EXHAUSTED",
            }
        },
    )
    script = Script(quota, quota)
    caplog.set_level(logging.WARNING, logger="graph.llm")

    with pytest.raises(LLMUnavailable):
        run(_client(script).structured(Node.NARRATOR, PROMPT, Narration))

    details = [record.llm["detail"] for record in caplog.records if hasattr(record, "llm")]
    assert details and all("Quota exceeded" in detail for detail in details)
    for record in caplog.records:
        assert KEY not in record.getMessage() and KEY not in repr(record.__dict__)


def test_an_invalid_key_reported_mid_stream_is_still_bad_key():
    error = genai_errors.ClientError(
        400, {"error": {"code": 400, "message": "API key expired.", "status": "INVALID_ARGUMENT"}}
    )
    script = Script([error])

    with pytest.raises(BadKey):
        run(_client(script).structured(Node.NARRATOR, PROMPT, Narration))


@pytest.mark.parametrize(
    "error",
    [
        genai_errors.ClientError(408, {"error": {"code": 408}}),
        genai_errors.ClientError(499, {"error": {"code": 499}}),
        genai_errors.ServerError(504, {"error": {"code": 504}}),
    ],
)
def test_statuses_langchain_wraps_generically_are_still_retried(error):
    # Raised while iterating, where LangChain wraps unmapped statuses in its base error class.
    script = Script([error], [_response(SCENE_JSON, finish=gt.FinishReason.STOP)])

    result = run(_client(script, byok=False).structured(Node.NARRATOR, PROMPT, Narration))

    assert result.narration == "You crouch. You throw."
    assert len(script.requests) == 2


def test_every_node_of_a_request_shares_one_client():
    script = Script(
        [_response(SCENE_JSON, finish=gt.FinishReason.STOP)],
        [_response(SCENE_JSON, finish=gt.FinishReason.STOP)],
    )
    client = _client(script)

    async def two_nodes():
        await client.structured(Node.INTERPRET, PROMPT, Narration)
        await client.structured(Node.NARRATOR, PROMPT, Narration)
        models = list(client._backend._loops[asyncio.get_running_loop()].values())
        await client.aclose()
        return models

    interpret, narrator = run(two_nodes())

    assert [r["model"] for r in script.requests] == ["gemini-3.5-flash-lite", "gemini-3.5-flash"]
    assert interpret.client is narrator.client
    assert not client._backend._loops


def test_models_of_closed_event_loops_are_dropped():
    script = Script(*[[_response(SCENE_JSON, finish=gt.FinishReason.STOP)] for _ in range(3)])
    client = _client(script, byok=False)

    for _ in range(3):
        run(client.structured(Node.NARRATOR, PROMPT, Narration))

    assert len(client._backend._loops) == 1  # only the last loop, until the next call


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


def test_a_labelled_image_follows_its_label():
    """M5: each reference portrait goes right after the text saying whose it is."""
    prompt = Prompt(
        system="House style.",
        messages=(Message("user", "Draw the duel."),),
        images=(
            ImagePart(b"rosa", label="Image 1: the portrait of Rosa."),
            ImagePart(b"tonio", label="Image 2: the portrait of Tonio."),
        ),
    )

    content = to_messages(prompt)[-1].content

    kinds = [part["type"] for part in content]
    assert kinds == ["text", "text", "image_url", "text", "image_url"]
    assert content[1]["text"] == "Image 1: the portrait of Rosa."
    assert content[2]["image_url"]["url"].endswith(base64.b64encode(b"rosa").decode())
    assert content[3]["text"] == "Image 2: the portrait of Tonio."
    assert "Rosa" not in repr(prompt.images[0])  # names are story text (T6)


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
    assert kwargs["response_mime_type"] == "application/json"
    assert kwargs["response_json_schema"] == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "narration": {"type": "string"},
            "choices": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["narration"],
    }
    # In the prompt instead: JSON mode with no schema, which Gemini always takes.
    kwargs = call_kwargs(request, schema_in_prompt=True)
    assert kwargs["response_mime_type"] == "application/json"
    assert "response_json_schema" not in kwargs


def _app_schemas():
    from evals.judge import JudgeOutput
    from graph.drafting.chain import CharacterProposal, DraftProposal, WorldChange
    from graph.turn.nodes import ChapterOutput, Intent, NarratorOutput

    return [
        DraftProposal,
        WorldChange,
        CharacterProposal,
        Intent,
        NarratorOutput,
        ChapterOutput,
        JudgeOutput,
    ]


def _keywords(schema, found):
    """Every keyword in `schema`, not counting the names under `properties` and `$defs`."""
    if isinstance(schema, list):
        for item in schema:
            _keywords(item, found)
    elif isinstance(schema, dict):
        for key, value in schema.items():
            found.add(key)
            if key in ("properties", "$defs"):
                for sub in value.values():
                    _keywords(sub, found)
            else:
                _keywords(value, found)
    return found


def _property_names(schema, found):
    if isinstance(schema, list):
        for item in schema:
            _property_names(item, found)
    elif isinstance(schema, dict):
        for key, value in schema.items():
            if key in ("properties", "$defs"):
                found.update(f"{key}.{name}" for name in value)
            _property_names(value, found)
    return found


@pytest.mark.parametrize("schema", _app_schemas(), ids=lambda schema: schema.__name__)
def test_every_schema_the_app_sends_keeps_to_what_gemini_takes(schema):
    """A keyword Gemini doesn't take makes it refuse the whole request with a bare 400, so a
    keyword never sent before must fail here, not in production."""
    full = schema.model_json_schema()
    sent = gemini_schema(full)

    assert _keywords(sent, set()) <= GEMINI_SCHEMA_KEYWORDS
    assert _property_names(sent, set()) == _property_names(full, set())


def test_a_const_becomes_a_one_value_enum():
    assert gemini_schema({"const": "scene", "type": "string", "title": "Kind"}) == {
        "enum": ["scene"],
        "type": "string",
    }


def test_a_refused_schema_is_sent_again_in_the_prompt_and_remembered(caplog):
    caplog.set_level(logging.WARNING, logger="graph.llm")
    script = Script(
        SCHEMA_REFUSED,
        [_response(SCENE_JSON, finish=gt.FinishReason.STOP)],
        [_response(SCENE_JSON, finish=gt.FinishReason.STOP)],
    )
    client = _client(script, byok=False)

    async def two_calls():
        first = await client.structured(Node.DRAFTER, PROMPT, Narration)
        second = await client.structured(Node.DRAFTER, PROMPT, Narration)
        return first, second

    first, second = run(two_calls())

    assert first.narration == second.narration == "You crouch. You throw."
    refused, again, later = (request["config"] for request in script.requests)
    assert refused.response_json_schema is not None
    for config in (again, later):
        assert config.response_json_schema is None
        assert config.response_mime_type == "application/json"
        system = str(config.system_instruction)
        assert SCHEMA_IN_PROMPT.strip() in system and '"narration"' in system
        assert "You are the narrator." in system
    warnings = [
        record
        for record in caplog.records
        if getattr(record, "llm", {}).get("reason") == "schema_refused"
    ]
    assert len(warnings) == 1
    assert warnings[0].llm["node"] == "drafter" and warnings[0].llm["schema"] == "Narration"
    for record in caplog.records:
        assert "I throw the stone." not in repr(record.__dict__)  # never the prompt (T6)


def test_a_refused_schema_still_refused_in_the_prompt_is_unavailable():
    script = Script(SCHEMA_REFUSED, SCHEMA_REFUSED)

    with pytest.raises(LLMUnavailable):
        run(_client(script, byok=False).structured(Node.DRAFTER, PROMPT, Narration))

    assert len(script.requests) == 2  # the schema, then the prompt; never a third


def test_a_bare_400_without_a_schema_is_not_retried():
    script = Script(SCHEMA_REFUSED)

    with pytest.raises(LLMUnavailable):
        run(_client(script, byok=False).text(Node.NARRATOR, PROMPT))

    assert len(script.requests) == 1


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
