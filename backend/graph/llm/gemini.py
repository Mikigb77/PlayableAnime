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
import weakref
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import aclosing
from functools import lru_cache
from typing import Any

import httpx
from google.auth import exceptions as auth_errors
from google.genai import errors as genai_errors
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


class GeminiBackend:
    """One provider target. Chat models are cached per event loop, because their HTTP clients
    belong to the loop that first used them."""

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
        self._models: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, dict[str, ChatGoogleGenerativeAI]
        ] = weakref.WeakKeyDictionary()

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
        model = self._model(request.model)
        try:
            async with aclosing(
                model.astream(to_messages(request.prompt), **call_kwargs(request))
            ) as messages:
                async for message in messages:
                    yield to_chunk(message)
        except ProviderError:
            raise
        except Exception as error:
            failure = classify(error, byok=self._secret is not None)
            if self._secret:
                failure.detail = failure.detail.replace(self._secret, "***")
                raise failure from None  # the original may carry request details
            raise failure from error

    async def aclose(self) -> None:
        for models in list(self._models.values()):
            for model in models.values():
                cleanup = getattr(model, "_client_cleanup", None)
                if cleanup is not None:
                    with contextlib.suppress(RuntimeError):  # closed on another loop
                        await cleanup.aclose()
        self._models.clear()

    def _model(self, name: str) -> ChatGoogleGenerativeAI:
        per_loop = self._models.setdefault(asyncio.get_running_loop(), {})
        if name not in per_loop:
            per_loop[name] = self._make_model(name)
        return per_loop[name]


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


def call_kwargs(request: Request) -> dict[str, Any]:
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
        kwargs["response_json_schema"] = dict(request.json_schema)
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
    if status in (408, 429):
        return ProviderError("transient", detail, status=status)
    return ProviderError("invalid", detail, status=status)


def _mentions_api_key(error: BaseException) -> bool:
    text = str(error).lower()
    return "api key" in text or "api_key" in text
