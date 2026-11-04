"""Gemini through LangChain, on Vertex AI or with a player's own Gemini API key (B6, B11, S9).

This module imports LangChain and google-genai, so only the factory imports it, on the first real
model call (B10).

We use `ChatGoogleGenerativeAI` from `langchain-google-genai`: since version 4 it calls Vertex AI
as well as the Gemini API, and `langchain-google-vertexai`'s `ChatVertexAI` is deprecated in its
favour (deprecated in 3.2.0, removed in 4.0.0). On Vertex AI it authenticates with Application
Default Credentials only: the Cloud Run service account in production, and
`gcloud auth application-default login` on a laptop. No key file exists anywhere (B11).
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import aclosing
from functools import lru_cache
from typing import Any

import httpx
from google.auth import exceptions as auth_errors
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from google.genai.types import HarmBlockThreshold, HarmCategory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, Modality
from langchain_google_genai.chat_models import (
    ChatGoogleGenerativeAIError,
    GoogleAPIError,
    GoogleAuthenticationError,
    GoogleContextOverflowError,
    GoogleInvalidRequestError,
    GoogleModelNotFoundError,
    GooglePermissionDeniedError,
    GoogleRateLimitError,
)

from graph.llm.types import (
    Chunk,
    Finish,
    FinishReason,
    ImagePart,
    Prompt,
    Provider,
    ProviderError,
    Request,
    Usage,
)

# Pinned so that no environment variable (such as LANGSMITH_GATEWAY) can route a player's key
# anywhere but Google.
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/"

_BLOCKED = {
    "SAFETY",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "IMAGE_SAFETY",
    "IMAGE_PROHIBITED_CONTENT",
    "JAILBREAK",
    "MODEL_ARMOR",
}
_RECITATION = {"RECITATION", "IMAGE_RECITATION"}

logger = logging.getLogger(__name__)

# The part of JSON Schema that Gemini takes in `response_json_schema`, less what only makes its
# constraint bigger. Gemini refuses a schema whose constraint has too many states (long runs of
# optional properties, numeric bounds, many `anyOf` branches) with a bare 400 "Request contains
# an invalid argument." that names nothing (https://ai.google.dev/gemini-api/docs/structured-output):
# on 2026-11-04 every draft failed that way on Vertex AI. Pydantic's `default`, `title` and bounds
# are left out; the client still validates each answer against the full model, so an answer out
# of bounds is retried like any unreadable one.
GEMINI_SCHEMA_KEYWORDS = frozenset(
    {"$defs", "$ref", "type", "properties", "required", "items", "enum", "anyOf", "description"}
)
# A schema Gemini refused all the same goes in the system prompt instead, as JSON mode with no
# schema, which it always takes. Refused schemas are remembered per model for the process.
SCHEMA_IN_PROMPT = (
    "Reply with one JSON value and nothing else. It must match this JSON Schema, with every "
    "property in the order given:\n"
)
_REFUSED_SCHEMAS: set[tuple[str, str]] = set()


class GeminiBackend:
    """One provider target: our Vertex AI project, or one request's player key.

    All models share one google-genai client, made from the first model asked for, because each
    client opens its own connections (a new TLS handshake per node would eat into S3's 2 s). The
    client belongs to the event loop that first used it, so models are kept per loop, and the
    models of a closed loop are dropped.
    """

    def __init__(
        self,
        *,
        provider: Provider,
        make_model: Callable[[str], ChatGoogleGenerativeAI],
        secret: str | None = None,
    ):
        self.provider: Provider = provider
        self._make_model = make_model
        self._secret = secret
        self._loops: dict[asyncio.AbstractEventLoop, dict[str, ChatGoogleGenerativeAI]] = {}

    @classmethod
    def vertex(cls, *, project: str, location: str) -> GeminiBackend:
        def make_model(model: str) -> ChatGoogleGenerativeAI:
            return ChatGoogleGenerativeAI(
                model=model, vertexai=True, project=project, location=location, max_retries=1
            )

        return cls(provider="vertex", make_model=make_model)

    @classmethod
    def with_api_key(cls, api_key: str) -> GeminiBackend:
        """A backend for one request with a player's key. It is never cached or stored."""

        def make_model(model: str) -> ChatGoogleGenerativeAI:
            return ChatGoogleGenerativeAI(
                model=model,
                vertexai=False,
                api_key=api_key,
                base_url=GEMINI_API_BASE_URL,
                max_retries=1,  # 1 means no SDK retry; the client retries once itself (T7)
            )

        return cls(provider="gemini_api", make_model=make_model, secret=api_key)

    async def stream(self, request: Request) -> AsyncIterator[Chunk]:
        """Streams one attempt. A response schema Gemini refuses is sent again in the prompt,
        once, before anything is streamed; the next calls with it go straight to the prompt."""
        if request.transcription is not None:
            async with aclosing(self._transcribe(request)) as chunks:
                async for chunk in chunks:
                    yield chunk
            return
        key = _schema_key(request)
        in_prompt = key is not None and key in _REFUSED_SCHEMAS
        streamed = False
        try:
            async with aclosing(self._stream(request, schema_in_prompt=in_prompt)) as chunks:
                async for chunk in chunks:
                    streamed = True
                    yield chunk
            return
        except ProviderError as failure:
            if key is None or in_prompt or streamed or not _refused_schema(failure):
                raise
            _REFUSED_SCHEMAS.add(key)
            logger.warning(
                "Gemini refused the response schema; sending it in the prompt instead",
                extra={
                    "llm": {
                        "node": request.node.value,
                        "model": request.model,
                        "reason": "schema_refused",
                        "schema": str((request.json_schema or {}).get("title", "")),
                        "detail": failure.detail,
                    }
                },
            )
        async with aclosing(self._stream(request, schema_in_prompt=True)) as chunks:
            async for chunk in chunks:
                yield chunk

    async def _stream(self, request: Request, *, schema_in_prompt: bool) -> AsyncIterator[Chunk]:
        failure: ProviderError | None = None
        try:
            model = self._model(request.model)
            prompt = with_schema_in_prompt(request) if schema_in_prompt else request.prompt
            kwargs = call_kwargs(request, schema_in_prompt=schema_in_prompt)
            async with aclosing(model.astream(to_messages(prompt), **kwargs)) as messages:
                async for message in messages:
                    yield to_chunk(message)
        except Exception as error:
            failure = classify(error, byok=self._secret is not None)
            if self._secret is None:
                raise failure from error
        if failure is not None and self._secret is not None:
            # Raised outside the handler, so no traceback or `__context__` holds the original
            # error, whose text could echo the player's key (T6).
            raise ProviderError(
                failure.kind, failure.detail.replace(self._secret, "***"), status=failure.status
            )

    async def _transcribe(self, request: Request) -> AsyncIterator[Chunk]:
        """One speech-to-text attempt (V6), straight through google-genai: LangChain has no way
        to send `audio_transcription_config`. It shares the models' client and connections. The
        recording goes inline, never through the Files API, which would keep it for two days."""
        failure: ProviderError | None = None
        chunk: Chunk | None = None
        try:
            aio = self._model(request.model).async_client
            response = await aio.models.generate_content(
                model=request.model,
                contents=to_audio_contents(request),
                config=transcription_config(request),
            )
            chunk = transcription_chunk(response)
        except Exception as error:
            failure = classify(error, byok=self._secret is not None)
            if self._secret is None:
                raise failure from error
        if failure is not None and self._secret is not None:
            raise ProviderError(  # outside the handler, as in `_stream` (T6)
                failure.kind, failure.detail.replace(self._secret, "***"), status=failure.status
            )
        if chunk is not None:
            yield chunk

    async def aclose(self) -> None:
        """Closes the client this loop uses. Clients of other loops are only dropped."""
        models = self._loops.pop(asyncio.get_running_loop(), {})
        self._loops.clear()
        if models:
            with contextlib.suppress(RuntimeError):
                await next(iter(models.values())).aclose()

    def _model(self, name: str) -> ChatGoogleGenerativeAI:
        for stale in [loop for loop in self._loops if loop.is_closed()]:
            del self._loops[stale]
        models = self._loops.setdefault(asyncio.get_running_loop(), {})
        if name not in models:
            if models:
                # A copy shares the first model's client; only the model name changes.
                first = next(iter(models.values()))
                models[name] = first.model_copy(update={"model": name})
            else:
                models[name] = self._make_model(name)
        return models[name]


@lru_cache
def vertex_backend(project: str, location: str) -> GeminiBackend:
    """The shared Vertex AI backend for our own credentials."""
    return GeminiBackend.vertex(project=project, location=location)


def to_messages(prompt: Prompt) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(prompt.system)] if prompt.system else []
    last = len(prompt.messages) - 1
    for index, message in enumerate(prompt.messages):
        if message.role == "model":
            messages.append(AIMessage(message.text))
        elif index == last and prompt.images:
            content: list[str | dict[str, Any]] = [{"type": "text", "text": message.text}]
            content += [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.mime_type};base64,"
                        + base64.b64encode(image.data).decode()
                    },
                }
                for image in prompt.images
            ]
            messages.append(HumanMessage(content=content))
        else:
            messages.append(HumanMessage(message.text))
    return messages


def to_audio_contents(request: Request) -> list[genai_types.Part]:
    if request.audio is None:
        raise ValueError("A speech request needs its recording")
    return [genai_types.Part.from_bytes(data=request.audio.data, mime_type=request.audio.mime_type)]


def transcription_config(request: Request) -> genai_types.GenerateContentConfig:
    """Gemini 3.5 Transcribe's settings (V6): the language hints (V4), the names as custom
    vocabulary (C6), and smart mode, which drops filler and applies self-corrections (V3).
    No safety settings: see `ModelClient.transcribe`."""
    spec = request.transcription
    if spec is None:
        raise ValueError("Not a speech request")
    audio = genai_types.AudioTranscriptionConfig(
        language_codes=list(spec.language_codes) or None,
        custom_vocabulary=list(spec.vocabulary) or None,
        mode=genai_types.AudioTranscriptionConfigMode.SMART if spec.smart else None,
    )
    config = genai_types.GenerateContentConfig(audio_transcription_config=audio)
    if request.options.max_output_tokens is not None:
        config.max_output_tokens = request.options.max_output_tokens
    return config


def transcription_chunk(response: Any) -> Chunk:
    """The transcript, usage and finish of a speech response. A part carries its words as text,
    or in `audio_transcription` (Vertex AI's samples read both); thoughts are skipped."""
    candidates = getattr(response, "candidates", None) or []
    candidate = candidates[0] if candidates else None
    pieces = []
    content = getattr(candidate, "content", None)
    for part in getattr(content, "parts", None) or []:
        if getattr(part, "thought", False):
            continue
        words = getattr(part, "text", None)
        if not words:
            words = getattr(getattr(part, "audio_transcription", None), "text", None)
        if words and words.strip():
            pieces.append(words.strip())
    usage = getattr(response, "usage_metadata", None)
    thinking = _count(usage, "thoughts_token_count")
    feedback = getattr(response, "prompt_feedback", None)
    metadata = {
        "prompt_feedback": {
            "block_reason": getattr(feedback, "block_reason", None),
            "safety_ratings": _dumped(getattr(feedback, "safety_ratings", None)),
        },
        "finish_reason": getattr(candidate, "finish_reason", None),
        "safety_ratings": _dumped(getattr(candidate, "safety_ratings", None)),
    }
    return Chunk(
        text=" ".join(pieces),
        usage=Usage(
            _count(usage, "prompt_token_count"),
            _count(usage, "candidates_token_count") + thinking,
            thinking,
        ),
        finish=_finish(metadata) or Finish("stop"),
    )


def _count(usage: Any, name: str) -> int:
    return int(getattr(usage, name, None) or 0)


def _dumped(ratings: Any) -> list[Any]:
    return [r.model_dump() if hasattr(r, "model_dump") else r for r in ratings or []]


def gemini_schema(schema: Any) -> Any:
    """`schema` with only the keywords Gemini takes (`GEMINI_SCHEMA_KEYWORDS`), at every level.
    A `const` becomes a one-value `enum`; the names under `properties` and `$defs` are kept."""
    if isinstance(schema, list):
        return [gemini_schema(item) for item in schema]
    if not isinstance(schema, Mapping):
        return schema
    kept: dict[str, Any] = {}
    for key, value in schema.items():
        if key in ("properties", "$defs") and isinstance(value, Mapping):
            kept[key] = {name: gemini_schema(sub) for name, sub in value.items()}
        elif key == "const" and "enum" not in schema:
            kept["enum"] = [value]
        elif key in GEMINI_SCHEMA_KEYWORDS:
            kept[key] = gemini_schema(value)
    return kept


def with_schema_in_prompt(request: Request) -> Prompt:
    """The request's prompt with its response schema at the end of the system instruction."""
    schema = json.dumps(_without_titles(request.json_schema), separators=(",", ":"))
    system = f"{request.prompt.system}\n\n{SCHEMA_IN_PROMPT}{schema}".lstrip()
    return dataclasses.replace(request.prompt, system=system)


def _without_titles(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_without_titles(item) for item in schema]
    if not isinstance(schema, Mapping):
        return schema
    return {
        key: {name: _without_titles(sub) for name, sub in value.items()}
        if key in ("properties", "$defs") and isinstance(value, Mapping)
        else _without_titles(value)
        for key, value in schema.items()
        if key != "title"
    }


def _schema_key(request: Request) -> tuple[str, str] | None:
    if request.json_schema is None:
        return None
    text = json.dumps(request.json_schema, sort_keys=True, separators=(",", ":"))
    return request.model, hashlib.sha256(text.encode()).hexdigest()


def _refused_schema(failure: ProviderError) -> bool:
    """A bare 400 for a request with a schema; a context overflow is no schema's fault."""
    return (
        failure.kind == "invalid"
        and failure.status == 400
        and not failure.detail.startswith("GoogleContextOverflowError")
    )


def call_kwargs(request: Request, *, schema_in_prompt: bool = False) -> dict[str, Any]:
    options = request.options
    kwargs: dict[str, Any] = {"safety_settings": to_safety_settings(request.safety)}
    if options.timeout_s:
        kwargs["timeout"] = options.timeout_s
    if options.temperature is not None:
        kwargs["temperature"] = options.temperature
    if options.max_output_tokens is not None:
        kwargs["max_output_tokens"] = options.max_output_tokens
    if options.thinking is not None and request.image is None:
        kwargs["thinking_level"] = options.thinking
    if options.seed is not None:
        kwargs["seed"] = options.seed
    if request.json_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        if not schema_in_prompt:
            kwargs["response_json_schema"] = gemini_schema(request.json_schema)
    if request.image is not None:
        kwargs["response_modalities"] = [Modality.IMAGE]
        kwargs["image_config"] = {
            "aspect_ratio": request.image.aspect_ratio,
            "image_size": request.image.size,
        }
    return kwargs


def to_safety_settings(safety: Mapping[str, str]) -> dict[HarmCategory, HarmBlockThreshold]:
    return {
        HarmCategory[f"HARM_CATEGORY_{category.upper()}"]: HarmBlockThreshold[threshold.upper()]
        for category, threshold in safety.items()
    }


def to_chunk(message: Any) -> Chunk:
    """Turns one LangChain message chunk into ours: text, pictures, usage and how it ended."""
    usage = message.usage_metadata or {}
    reasoning = (usage.get("output_token_details") or {}).get("reasoning", 0)
    return Chunk(
        text=message.text or "",
        images=_images(message.content),
        usage=Usage(usage.get("input_tokens", 0), usage.get("output_tokens", 0), reasoning),
        finish=_finish(message.response_metadata or {}),
    )


def _images(content: Any) -> tuple[ImagePart, ...]:
    if not isinstance(content, list):
        return ()
    images = []
    for block in content:
        if not isinstance(block, dict):
            continue
        url = ""
        if block.get("type") == "image_url":
            url = (block.get("image_url") or {}).get("url", "")
        elif block.get("type") == "image" and block.get("base64"):
            url = f"data:{block.get('mime_type', 'image/png')};base64,{block['base64']}"
        if url.startswith("data:") and ";base64," in url:
            header, data = url[5:].split(";base64,", 1)
            images.append(ImagePart(base64.b64decode(data), header or "image/png"))
    return tuple(images)


def _finish(metadata: Mapping[str, Any]) -> Finish | None:
    feedback = metadata.get("prompt_feedback") or {}
    block_reason = _name(feedback.get("block_reason"))
    if block_reason and block_reason != "BLOCKED_REASON_UNSPECIFIED":
        categories = _blocked_categories(feedback.get("safety_ratings")) or (block_reason.lower(),)
        return Finish("blocked", categories, "prompt")
    reason = _name(metadata.get("finish_reason"))
    if not reason:
        return None
    if reason in _BLOCKED:
        categories = _blocked_categories(metadata.get("safety_ratings")) or (reason.lower(),)
        return Finish("blocked", categories, "response")
    kind: FinishReason
    if reason == "STOP":
        kind = "stop"
    elif reason == "MAX_TOKENS":
        kind = "max_tokens"
    elif reason in _RECITATION:
        kind = "recitation"
    else:
        kind = "other"
    return Finish(kind)


def _blocked_categories(ratings: Any) -> tuple[str, ...]:
    categories = []
    for rating in ratings or []:
        if isinstance(rating, Mapping) and rating.get("blocked"):
            name = _name(rating.get("category")).removeprefix("HARM_CATEGORY_").lower()
            if name:
                categories.append(name)
    return tuple(dict.fromkeys(categories))


def _name(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "name", value))


def classify(error: BaseException, *, byok: bool) -> ProviderError:
    """Sorts a LangChain, google-genai, google-auth or httpx error for the client."""
    detail = f"{type(error).__name__}: {error}"
    if isinstance(error, GoogleContextOverflowError):
        return ProviderError("invalid", detail, status=400)
    if isinstance(error, GoogleAuthenticationError | GooglePermissionDeniedError):
        return ProviderError("auth", detail, status=401)
    if isinstance(error, GoogleInvalidRequestError):
        kind = "auth" if byok and _mentions_api_key(error) else "invalid"
        return ProviderError(kind, detail, status=400)
    if isinstance(error, GoogleRateLimitError):
        return ProviderError("transient", detail, status=429)
    if isinstance(error, GoogleModelNotFoundError):
        return ProviderError("invalid", detail, status=404)
    if isinstance(error, GoogleAPIError | genai_errors.ServerError):
        return ProviderError("transient", detail, status=getattr(error, "code", 500))
    if isinstance(error, genai_errors.ClientError):
        return _classify_status(error.code, error, detail, byok=byok)
    if isinstance(error, ChatGoogleGenerativeAIError):
        # LangChain wraps statuses it has no class for (408, 499, other 4xx) in the base class.
        cause = error.__cause__
        if isinstance(cause, genai_errors.APIError):
            return _classify_status(cause.code, error, detail, byok=byok)
        return ProviderError("invalid", detail)
    if isinstance(error, httpx.TimeoutException | httpx.TransportError | TimeoutError):
        return ProviderError("transient", detail)
    if isinstance(error, ConnectionError):
        return ProviderError("transient", detail)
    if isinstance(error, auth_errors.DefaultCredentialsError):
        return ProviderError("invalid", "No Application Default Credentials found")
    if isinstance(error, auth_errors.RefreshError):
        return ProviderError("auth", detail)
    if isinstance(error, auth_errors.TransportError):
        return ProviderError("transient", detail)
    return ProviderError("invalid", detail)


def _classify_status(
    status: int, error: BaseException, detail: str, *, byok: bool
) -> ProviderError:
    if status in (401, 403):
        return ProviderError("auth", detail, status=status)
    if status == 400 and byok and _mentions_api_key(error):
        return ProviderError("auth", detail, status=status)
    if status in (408, 429, 499) or status >= 500:
        return ProviderError("transient", detail, status=status)
    return ProviderError("invalid", detail, status=status)


def _mentions_api_key(error: BaseException) -> bool:
    text = str(error).lower()
    return "api key" in text or "api_key" in text
