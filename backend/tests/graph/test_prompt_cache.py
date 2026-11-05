"""Explicit caches for prompts' stable starts (T5, K2): when one is made, used, extended or
dropped, and how the Gemini backend sends a call that names one."""

import asyncio

import pytest
from google.genai import errors as genai_errors
from google.genai import types as gt

from graph.llm import ModelClient, ModelConfig, Node, Prompt, TurnTelemetry
from graph.llm.cache import (
    MIN_CHARS,
    REFRESH_BELOW_S,
    RETRY_AFTER_S,
    TTL_S,
    USE_MARGIN_S,
    Made,
    PromptCache,
)
from graph.llm.gemini import GeminiBackend
from graph.llm.types import ProviderError
from tests.graph.test_gemini import KEY, Script, _response

MODEL = "gemini-3.5-flash"
SYSTEM = "You are the narrator."
STABLE = "## WORLD\n" + "w" * MIN_CHARS
REST = "## ACTION\nI throw the stone."
TOO_SMALL = ProviderError(
    "invalid",
    "ClientError: 400 INVALID_ARGUMENT. The cached content is of 1200 tokens. The minimum token "
    "count to start caching is 4096.",
    status=400,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Vertex:
    """Fake cache calls: each make returns the next name, or raises what it's given."""

    def __init__(self, *outcomes: Exception) -> None:
        self.outcomes = list(outcomes)
        self.made: list[tuple[str, str, str, int]] = []
        self.extended: list[tuple[str, str, int]] = []
        self.extend_error: Exception | None = None

    async def create(self, model: str, system: str, stable: str, ttl_s: int) -> Made:
        self.made.append((model, system, stable, ttl_s))
        if self.outcomes:
            raise self.outcomes.pop(0)
        return Made(f"cachedContents/{len(self.made)}", ttl_s, tokens=5000)

    async def extend(self, model: str, name: str, ttl_s: int) -> float:
        self.extended.append((model, name, ttl_s))
        if self.extend_error is not None:
            raise self.extend_error
        return ttl_s


def _cache(vertex: Vertex, clock: Clock) -> PromptCache:
    return PromptCache(vertex.create, vertex.extend, clock=clock)


async def _settle() -> None:
    for _ in range(3):
        await asyncio.sleep(0)


def test_a_new_start_is_sent_whole_while_its_cache_is_made_then_the_cache_is_named():
    vertex, clock = Vertex(), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        first = cache.use(MODEL, SYSTEM, STABLE)
        again = cache.use(MODEL, SYSTEM, STABLE)  # still being made: no second cache
        await _settle()
        return first, again, cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == (None, None, "cachedContents/1")
    assert vertex.made == [(MODEL, SYSTEM, STABLE, TTL_S)]


def test_another_model_system_or_start_gets_its_own_cache():
    vertex, clock = Vertex(), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        for model, system, stable in [
            (MODEL, SYSTEM, STABLE),
            ("gemini-3.5-flash-lite", SYSTEM, STABLE),
            (MODEL, SYSTEM + " Cut away.", STABLE),
            (MODEL, SYSTEM, STABLE + "x"),
        ]:
            cache.use(model, system, stable)
        await _settle()

    asyncio.run(scenario())
    assert len(vertex.made) == 4


def test_a_start_too_short_for_any_cache_is_never_sent_to_vertex():
    vertex = Vertex()

    async def scenario():
        return _cache(vertex, Clock()).use(MODEL, "short", "start")

    assert asyncio.run(scenario()) is None
    assert vertex.made == []


def test_a_cache_close_to_expiring_is_extended_in_the_background():
    vertex, clock = Vertex(), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += TTL_S - REFRESH_BELOW_S - 1  # not yet
        assert cache.use(MODEL, SYSTEM, STABLE) == "cachedContents/1"
        assert vertex.extended == []
        clock.now += 2
        assert cache.use(MODEL, SYSTEM, STABLE) == "cachedContents/1"
        assert cache.use(MODEL, SYSTEM, STABLE) == "cachedContents/1"  # one extension at a time
        await _settle()
        assert vertex.extended == [(MODEL, "cachedContents/1", TTL_S)]
        clock.now += TTL_S - USE_MARGIN_S - 1  # past the old expiry, within the new one
        return cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == "cachedContents/1"
    assert len(vertex.made) == 1


def test_a_cache_about_to_expire_is_not_named_and_a_new_one_is_made():
    vertex, clock = Vertex(), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += TTL_S - USE_MARGIN_S + 1
        missed = cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        return missed, cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == (None, "cachedContents/2")


def test_a_cache_that_cant_be_extended_is_dropped_and_made_again():
    vertex, clock = Vertex(), Clock()
    vertex.extend_error = ProviderError("invalid", "NotFound: 404", status=404)
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += TTL_S - REFRESH_BELOW_S + 1
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        dropped = cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        return dropped, cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == (None, "cachedContents/2")


def test_a_cache_that_failed_to_extend_for_a_moment_is_kept_and_extended_on_the_next_use():
    vertex, clock = Vertex(), Clock()
    vertex.extend_error = ProviderError("transient", "ServerError: 503", status=503)
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += TTL_S - REFRESH_BELOW_S + 1
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        vertex.extend_error = None
        kept = cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        return kept

    assert asyncio.run(scenario()) == "cachedContents/1"
    assert len(vertex.extended) == 2 and len(vertex.made) == 1


def test_a_start_vertex_finds_too_small_is_not_tried_again_nor_any_smaller(caplog):
    vertex, clock = Vertex(TOO_SMALL), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += RETRY_AFTER_S + 1
        assert cache.use(MODEL, SYSTEM, STABLE) is None
        assert cache.use(MODEL, SYSTEM, STABLE[:-1] + "y") is None  # as long: as small
        assert cache.use(MODEL, SYSTEM, STABLE + "longer") is None  # tried
        await _settle()
        return cache.use(MODEL, SYSTEM, STABLE + "longer")

    assert asyncio.run(scenario()) == "cachedContents/2"
    assert len(vertex.made) == 2
    [warning] = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warning.llm["reason"] == "cache_too_small"
    assert STABLE not in warning.getMessage() and "w" * 100 not in str(warning.llm)


def test_a_failed_cache_waits_before_its_start_is_tried_again():
    vertex, clock = Vertex(ProviderError("transient", "ServerError: 503", status=503)), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        clock.now += RETRY_AFTER_S - 1
        assert cache.use(MODEL, SYSTEM, STABLE) is None
        assert len(vertex.made) == 1
        clock.now += 2
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        return cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == "cachedContents/2"


def test_a_forgotten_cache_is_made_again_on_the_next_call():
    vertex, clock = Vertex(), Clock()
    cache = _cache(vertex, clock)

    async def scenario():
        cache.use(MODEL, SYSTEM, STABLE)
        await _settle()
        cache.forget("cachedContents/1")
        assert cache.use(MODEL, SYSTEM, STABLE) is None
        await _settle()
        return cache.use(MODEL, SYSTEM, STABLE)

    assert asyncio.run(scenario()) == "cachedContents/2"


def test_a_prompt_splits_into_its_stable_start_and_the_rest():
    prompt = Prompt.build(SYSTEM, f"{STABLE}\n\n{REST}", stable_chars=len(STABLE))

    assert prompt.stable_split() == (STABLE, REST)
    assert Prompt.build(SYSTEM, REST).stable_split() is None
    assert Prompt.build(SYSTEM, STABLE, stable_chars=len(STABLE)).stable_split() is None
    with pytest.raises(ValueError, match="stable start"):
        Prompt.build(SYSTEM, REST, stable_chars=len(REST) + 1)


# The Gemini backend, through the real LangChain model with google-genai's network call faked.

STABLE_PROMPT = Prompt.build(SYSTEM, f"{STABLE}\n\n{REST}", stable_chars=len(STABLE))
OK = [_response("ok", finish=gt.FinishReason.STOP, usage=(5200, 1, 0, 5000))]


def _vertex(script: Script, vertex: Vertex, telemetry=None) -> ModelClient:
    backend = GeminiBackend.vertex(project="p", location="global")
    backend.prompt_cache = PromptCache(vertex.create, vertex.extend)
    make_model = backend._make_model

    def patched(name):
        model = make_model(name)
        model.client.aio.models.generate_content_stream = script
        return model

    backend._make_model = patched
    return ModelClient(backend, ModelConfig(), rating="mature", recorder=telemetry, retry_delay_s=0)


def _texts(contents) -> list[str]:
    return [part.text for content in contents for part in content.parts]


def test_the_second_call_names_the_cache_and_sends_only_the_rest():
    telemetry = TurnTelemetry()
    script, vertex = Script(OK, OK), Vertex()
    client = _vertex(script, vertex, telemetry)

    async def scenario():
        await client.text(Node.NARRATOR, STABLE_PROMPT)
        await _settle()
        await client.text(Node.NARRATOR, STABLE_PROMPT)

    asyncio.run(scenario())

    whole, cached = script.requests
    assert whole["config"].cached_content is None
    assert whole["config"].system_instruction is not None
    assert _texts(whole["contents"]) == [f"{STABLE}\n\n{REST}"]
    assert cached["config"].cached_content == "cachedContents/1"
    assert cached["config"].system_instruction is None
    assert _texts(cached["contents"]) == [REST]
    assert vertex.made == [(MODEL, SYSTEM, STABLE, TTL_S)]
    assert [call.cached_tokens for call in telemetry.calls] == [5000, 5000]


def test_a_refused_cache_is_dropped_and_the_whole_prompt_sent_at_once():
    expired = genai_errors.ClientError(
        404,
        {"error": {"code": 404, "message": "Cached content not found.", "status": "NOT_FOUND"}},
    )
    script, vertex = Script(OK, expired, OK), Vertex()
    client = _vertex(script, vertex)

    async def scenario():
        await client.text(Node.NARRATOR, STABLE_PROMPT)
        await _settle()
        return await client.text(Node.NARRATOR, STABLE_PROMPT)

    assert asyncio.run(scenario()) == "ok"
    _, refused, whole = script.requests
    assert refused["config"].cached_content == "cachedContents/1"
    assert whole["config"].cached_content is None
    assert _texts(whole["contents"]) == [f"{STABLE}\n\n{REST}"]


def test_a_busy_cached_call_is_retried_by_the_client_still_naming_the_cache():
    busy = genai_errors.ServerError(
        503, {"error": {"code": 503, "message": "Overloaded.", "status": "UNAVAILABLE"}}
    )
    script, vertex = Script(OK, busy, OK), Vertex()
    client = _vertex(script, vertex)

    async def scenario():
        await client.text(Node.NARRATOR, STABLE_PROMPT)
        await _settle()
        return await client.text(Node.NARRATOR, STABLE_PROMPT)

    assert asyncio.run(scenario()) == "ok"
    assert [r["config"].cached_content for r in script.requests] == [
        None,
        "cachedContents/1",
        "cachedContents/1",
    ]


def test_a_players_own_key_never_makes_or_names_a_cache():
    script = Script(OK, OK)
    backend = GeminiBackend.with_api_key(KEY)
    make_model = backend._make_model

    def patched(name):
        model = make_model(name)
        model.client.aio.models.generate_content_stream = script
        return model

    backend._make_model = patched
    client = ModelClient(
        backend, ModelConfig(), rating="mature", byok=True, owns_backend=True, retry_delay_s=0
    )

    async def scenario():
        await client.text(Node.NARRATOR, STABLE_PROMPT)
        await _settle()
        await client.text(Node.NARRATOR, STABLE_PROMPT)

    asyncio.run(scenario())
    assert backend.prompt_cache is None
    assert [r["config"].cached_content for r in script.requests] == [None, None]
