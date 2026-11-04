"""The shapes that pass between graph nodes, the model client and a model backend.

A node builds a `Prompt` and calls `ModelClient`. The client turns it into a `Request` for a
`Backend`, which streams `Chunk`s back. Backends never decide anything: retries, typed errors,
parsing and telemetry all live in the client, so the fake backend exercises the same code paths
as the real one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Any, Literal, Protocol

Rating = Literal["teen", "mature"]
"""A story's rating (F2). It picks the safety settings (F5)."""

Thinking = Literal["minimal", "low", "medium", "high"]
"""Gemini's thinking level. Every Gemini 3 model accepts `low` and `high`."""

Provider = Literal["vertex", "gemini_api", "fake"]


class Node(StrEnum):
    """The model roles, each with its own model in config (B6)."""

    INTERPRET = "interpret"
    NARRATOR = "narrator"
    CHECKER = "checker"
    TICK = "tick"
    SUMMARIZER = "summarizer"
    DRAFTER = "drafter"
    PICTURE = "picture"
    JUDGE = "judge"  # the evals' model judge (T15, T17, T18); never on a player's turn


@dataclass(frozen=True, repr=False)
class Message:
    role: Literal["user", "model"]
    text: str

    def __repr__(self) -> str:
        return f"Message(role={self.role!r}, chars={len(self.text)})"


@dataclass(frozen=True, repr=False)
class ImagePart:
    """An image sent to the model, such as a reference portrait (M5), or one it made."""

    data: bytes
    mime_type: str = "image/png"

    def __repr__(self) -> str:
        return f"ImagePart(mime_type={self.mime_type!r}, bytes={len(self.data)})"


@dataclass(frozen=True, repr=False)
class Prompt:
    """What a node sends to a model.

    Its repr shows only sizes, so a stray log line can never carry a full prompt (T6).
    `images` go with the last user message.
    """

    system: str
    messages: tuple[Message, ...]
    images: tuple[ImagePart, ...] = ()

    def __post_init__(self) -> None:
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("A prompt must end with a user message")

    @classmethod
    def build(
        cls,
        system: str,
        user: str,
        *,
        history: Sequence[Message] = (),
        images: Sequence[ImagePart] = (),
    ) -> Prompt:
        return cls(system=system, messages=(*history, Message("user", user)), images=tuple(images))

    def __repr__(self) -> str:
        chars = len(self.system) + sum(len(m.text) for m in self.messages)
        return f"Prompt(messages={len(self.messages)}, chars={chars}, images={len(self.images)})"


@dataclass(frozen=True)
class CallOptions:
    """Per-call generation settings. A `None` field keeps the node's default from config."""

    temperature: float | None = None
    max_output_tokens: int | None = None
    thinking: Thinking | None = None
    seed: int | None = None
    timeout_s: float | None = None

    def merged(self, override: CallOptions | None) -> CallOptions:
        if override is None:
            return self
        changes = {
            f.name: getattr(override, f.name)
            for f in fields(override)
            if getattr(override, f.name) is not None
        }
        return replace(self, **changes)


@dataclass(frozen=True)
class ImageSpec:
    """Asks for a picture instead of text (M8). 1K fits a phone screen."""

    aspect_ratio: str = "3:4"
    size: Literal["1K", "2K", "4K"] = "1K"


@dataclass(frozen=True, repr=False)
class Request:
    """One model call as a backend sees it. Safety names are ours (see `graph.llm.safety`)."""

    node: Node
    model: str
    prompt: Prompt
    options: CallOptions
    safety: Mapping[str, str]
    json_schema: Mapping[str, Any] | None = None
    image: ImageSpec | None = None

    def __repr__(self) -> str:
        return f"Request(node={self.node.value!r}, model={self.model!r}, prompt={self.prompt!r})"


@dataclass(frozen=True)
class Usage:
    """Token counts. `output_tokens` includes `thinking_tokens`, which Gemini bills as output."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.thinking_tokens + other.thinking_tokens,
        )


FinishReason = Literal["stop", "max_tokens", "blocked", "recitation", "other"]


@dataclass(frozen=True)
class Finish:
    """How a model response ended.

    `blocked` covers safety filters, the non-configurable filters and prompt blocks. `stage`
    says whether the prompt or the response was blocked, and `categories` names what fired, in
    our lowercase names (`sexually_explicit`, `prohibited_content`...), for F4's block log.
    """

    reason: FinishReason
    categories: tuple[str, ...] = ()
    stage: Literal["prompt", "response"] = "response"


@dataclass(frozen=True)
class Chunk:
    """One piece of a streamed response. `usage` is this chunk's share; the client sums them."""

    text: str = ""
    images: tuple[ImagePart, ...] = ()
    usage: Usage = field(default_factory=Usage)
    finish: Finish | None = None


ProviderErrorKind = Literal["transient", "auth", "invalid"]


class ProviderError(Exception):
    """A backend failure, sorted into what the client does with it.

    `transient` (timeouts, 429, 5xx, network) is retried once. `auth` is a rejected key or a
    missing permission. `invalid` is a request the provider will never accept as sent (an unknown
    model, a context overflow), so retrying it is pointless.
    """

    def __init__(self, kind: ProviderErrorKind, detail: str, *, status: int | None = None):
        super().__init__(detail)
        self.kind: ProviderErrorKind = kind
        self.detail = detail
        self.status = status


class Backend(Protocol):
    """Talks to one model provider. Every call streams, so blocks and usage look the same."""

    provider: Provider

    def stream(self, request: Request) -> AsyncIterator[Chunk]:
        """Streams one attempt. Raises `ProviderError` for failures; never retries."""
        ...

    async def aclose(self) -> None:
        """Releases connections. Called after a request that used a BYOK client."""
        ...
