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

# The validation context the client reads a model's structured answer with (`ModelClient`). A
# schema may read model output leniently only when MODEL_OUTPUT is set, so what code builds stays
# strict, and it notes each repair it makes in the context's REPAIRS list, as text with no value
# in it (T6). The client logs the repairs once per answer, with the call.
MODEL_OUTPUT = "model_output"
REPAIRS = "repairs"


class Node(StrEnum):
    """The model roles, each with its own model in config (B6)."""

    INTERPRET = "interpret"
    # B8: reads the player's words once more, on the rare turn whose first reading would do
    # something that can't be taken back, such as ending a friendly bout as an attack (W1).
    SECOND_READING = "second_reading"
    NARRATOR = "narrator"
    CHECKER = "checker"
    TICK = "tick"
    SUMMARIZER = "summarizer"
    DRAFTER = "drafter"
    PICTURE = "picture"
    PICTURE_NOTE = "picture_note"  # a scene picture's description, from the finished scene (M5)
    SPEECH = "speech"  # turns a player's dictation into text (V6)
    VOICE = "voice"  # reads a scene's narration aloud (V9)
    JUDGE = "judge"  # the evals' model judge (T15, T17, T18); never on a player's turn


@dataclass(frozen=True, repr=False)
class Message:
    role: Literal["user", "model"]
    text: str

    def __repr__(self) -> str:
        return f"Message(role={self.role!r}, chars={len(self.text)})"


@dataclass(frozen=True, repr=False)
class ImagePart:
    """An image sent to the model, such as a reference portrait (M5), or one it made. A `label`
    goes to the model as text just before the image, saying what it is ("Image 1: the portrait
    of Rosa.")."""

    data: bytes
    mime_type: str = "image/png"
    label: str = ""

    def __repr__(self) -> str:
        return f"ImagePart(mime_type={self.mime_type!r}, bytes={len(self.data)})"


@dataclass(frozen=True, repr=False)
class AudioPart:
    """A recording sent to the speech model (V6), held in memory only and never stored (V5), or
    speech the voice model read aloud (V9)."""

    data: bytes
    mime_type: str = "audio/wav"

    def __repr__(self) -> str:
        return f"AudioPart(mime_type={self.mime_type!r}, bytes={len(self.data)})"


@dataclass(frozen=True, repr=False)
class Transcription:
    """Asks the speech model for the words in `AudioPart` instead of an answer (V6).

    `language_codes` are BCP-47 hints, such as `en-US` (V4); none means the model detects the
    language. `vocabulary` biases recognition toward the story's names, most relevant first
    (C6). `smart` drops filler and false starts and applies inline self-corrections, as a
    dictation box should (V3). Its repr shows only sizes, since names are story text (T6).
    """

    language_codes: tuple[str, ...] = ()
    vocabulary: tuple[str, ...] = ()
    smart: bool = True

    def __repr__(self) -> str:
        return (
            f"Transcription(languages={list(self.language_codes)!r}, "
            f"vocabulary={len(self.vocabulary)}, smart={self.smart})"
        )


@dataclass(frozen=True)
class Reading:
    """Asks the voice model to read the prompt's text aloud instead of answering (V9), in one of
    its prebuilt voices, such as `Sulafat`. `language` is the BCP-47 code of the language and
    accent to read in, such as `es-ES` for Spanish from Spain (`speech.voices.READING_LOCALES`);
    without one the model guesses the language from the text, accent and all."""

    voice: str
    language: str | None = None


@dataclass(frozen=True, repr=False)
class Prompt:
    """What a node sends to a model.

    Its repr shows only sizes, so a stray log line can never carry a full prompt (T6).
    `images` go with the last user message. `stable_chars` is how much of a lone user message
    stays the same from call to call (the world, the rules): with the system text, the backend
    may keep it in a cache that Gemini bills at its cached rate (`graph.llm.cache`).
    """

    system: str
    messages: tuple[Message, ...]
    images: tuple[ImagePart, ...] = ()
    stable_chars: int = 0

    def __post_init__(self) -> None:
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("A prompt must end with a user message")
        if not 0 <= self.stable_chars <= len(self.messages[-1].text):
            raise ValueError("A prompt's stable start must be part of its last message")

    @classmethod
    def build(
        cls,
        system: str,
        user: str,
        *,
        history: Sequence[Message] = (),
        images: Sequence[ImagePart] = (),
        stable_chars: int = 0,
    ) -> Prompt:
        return cls(
            system=system,
            messages=(*history, Message("user", user)),
            images=tuple(images),
            stable_chars=stable_chars,
        )

    def stable_split(self) -> tuple[str, str] | None:
        """The stable start and the rest of a prompt that is one text message with a stable
        start, the rest without the blank line between them; None for any other prompt."""
        if not self.stable_chars or len(self.messages) != 1 or self.images:
            return None
        text = self.messages[0].text
        rest = text[self.stable_chars :].lstrip("\n")
        return (text[: self.stable_chars], rest) if rest else None

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
    # A speech request (V6): the recording, and how to write it down. Its prompt is empty.
    audio: AudioPart | None = None
    transcription: Transcription | None = None
    # A request to read the prompt's text aloud (V9), with the voice to read it in.
    reading: Reading | None = None

    def __repr__(self) -> str:
        return f"Request(node={self.node.value!r}, model={self.model!r}, prompt={self.prompt!r})"


@dataclass(frozen=True)
class Usage:
    """Token counts. `output_tokens` includes `thinking_tokens`, which Gemini bills as output, and
    `input_tokens` includes `cached_tokens`: the start of the prompt that Gemini had just seen,
    which it bills at its cheaper cached rate (implicit caching)."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.thinking_tokens + other.thinking_tokens,
            self.cached_tokens + other.cached_tokens,
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
    """One piece of a streamed response. `usage` is this chunk's share; the client sums them.
    `audio` is speech the voice model read (V9), as Gemini sends it: raw PCM, with the rate in
    its type, such as `audio/L16;codec=pcm;rate=24000`."""

    text: str = ""
    images: tuple[ImagePart, ...] = ()
    audio: tuple[AudioPart, ...] = ()
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
