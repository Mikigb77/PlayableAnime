"""A scripted fake model for tests, and the offline model behind `LLM_PROVIDER=fake`.

The fake is a backend, so every call still goes through the real client: retries, blocks,
parsing, streaming and telemetry behave exactly as they do with Gemini.

    fake = FakeBackend()
    fake.script(Node.INTERPRET, Reply(json={"verb": "throw", ...}))
    fake.script(Node.NARRATOR, Fail(), Reply(json=narration))       # a failure, then the retry
    fake.script(Node.NARRATOR, Block(after_text='{"narration": "You'))  # blocked mid-stream

Each node replays its own steps in order. A node with no steps left uses `default`, or fails the
test with a clear message when there is none.
"""

from __future__ import annotations

import asyncio
import json
import math
import struct
import zlib
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from graph.llm.types import (
    Chunk,
    Finish,
    FinishReason,
    ImagePart,
    Node,
    Provider,
    ProviderError,
    ProviderErrorKind,
    Request,
    Usage,
)


def png(width: int, height: int, rows: Callable[[int], bytes]) -> bytes:
    """A truecolor PNG from `rows(y)`, the RGB bytes of row `y` (no Pillow needed)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + rows(y) for y in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def offline_picture(aspect_ratio: str = "3:4") -> bytes:
    """The offline model's picture: a quiet dusk gradient in the picture's own shape, so the
    app's slot shows something real when it is drawn locally (M3)."""
    across, _, down = aspect_ratio.partition(":")
    try:
        ratio = int(across) / int(down)
    except (ValueError, ZeroDivisionError):
        ratio = 3 / 4
    height = 96
    width = max(1, round(height * ratio))
    top, bottom = (0x2E, 0x3A, 0x5C), (0x0B, 0x0D, 0x12)

    def row(y: int) -> bytes:
        t = y / (height - 1)
        pixel = bytes(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        return pixel * width

    return png(width, height, row)


TINY_PNG = png(1, 1, lambda _: b"\x2e\x3a\x5c")
"""A one-pixel picture, for tests and scripted runs that only need some image bytes."""


@dataclass(frozen=True)
class Reply:
    """A successful answer. Give `json` (a dict, list or Pydantic model) or `text`."""

    json: Any = None
    text: str | None = None
    images: tuple[bytes, ...] = ()
    usage: Usage | None = None  # default: about four characters per token
    finish: FinishReason = "stop"  # "max_tokens" or "recitation" to test a bad answer


@dataclass(frozen=True)
class Block:
    """A safety block, optionally after some streamed text."""

    categories: tuple[str, ...] = ("sexually_explicit",)
    stage: Literal["prompt", "response"] = "response"
    after_text: str = ""


@dataclass(frozen=True)
class Fail:
    """A provider failure, optionally after some streamed text. `transient` is retried."""

    kind: ProviderErrorKind = "transient"
    status: int | None = 503
    after_text: str = ""


@dataclass(frozen=True)
class Hang:
    """Never answers, to test the deadline."""


Step = Reply | Block | Fail | Hang


@dataclass
class FakeBackend:
    provider: Provider = "fake"
    default: Callable[[Request], Reply] | None = None
    chunk_size: int = 16
    keep_requests: bool = True
    requests: list[Request] = field(default_factory=list)
    _steps: dict[Node, deque[Step]] = field(
        default_factory=lambda: defaultdict(deque), init=False, repr=False
    )

    def script(self, node: Node, *steps: Step) -> FakeBackend:
        self._steps[node].extend(steps)
        return self

    def pending(self, node: Node | None = None) -> int:
        if node is not None:
            return len(self._steps[node])
        return sum(len(steps) for steps in self._steps.values())

    def calls(self, node: Node) -> list[Request]:
        return [r for r in self.requests if r.node == node]

    async def aclose(self) -> None:
        return None

    async def stream(self, request: Request) -> AsyncIterator[Chunk]:
        if self.keep_requests:
            self.requests.append(request)
        step = self._next(request)
        input_tokens = _tokens(request.prompt.system) + sum(
            _tokens(m.text) for m in request.prompt.messages
        )
        if request.audio is not None:
            input_tokens += audio_tokens(request.audio.data)
        if isinstance(step, Hang):
            await asyncio.Event().wait()
        if isinstance(step, Fail | Block) and step.after_text:
            for piece in self._pieces(step.after_text):
                yield Chunk(text=piece)
        if isinstance(step, Fail):
            raise ProviderError(step.kind, f"fake {step.kind} failure", status=step.status)
        if isinstance(step, Block):
            output = 0 if step.stage == "prompt" else _tokens(step.after_text)
            yield Chunk(
                usage=Usage(input_tokens, output),
                finish=Finish("blocked", step.categories, step.stage),
            )
            return
        assert isinstance(step, Reply)
        text = _reply_text(step)
        pieces = self._pieces(text)
        for piece in pieces[:-1]:
            yield Chunk(text=piece)
        yield Chunk(
            text=pieces[-1] if pieces else "",
            images=tuple(ImagePart(data) for data in step.images),
            usage=step.usage or Usage(input_tokens, _tokens(text) + 1120 * len(step.images)),
            finish=Finish(step.finish),
        )

    def _next(self, request: Request) -> Step:
        steps = self._steps[request.node]
        if steps:
            return steps.popleft()
        if self.default is not None:
            return self.default(request)
        raise AssertionError(f"FakeBackend has no scripted reply left for {request.node.value!r}")

    def _pieces(self, text: str) -> list[str]:
        size = max(1, self.chunk_size)
        return [text[i : i + size] for i in range(0, len(text), size)]


def _reply_text(step: Reply) -> str:
    if step.text is not None:
        return step.text
    if step.json is None:
        return ""
    if isinstance(step.json, BaseModel):
        return step.json.model_dump_json()
    return json.dumps(step.json, ensure_ascii=False)


def _tokens(text: str) -> int:
    return (len(text) + 3) // 4


def audio_tokens(data: bytes) -> int:
    """About what Gemini counts for a recording: 32 tokens a second, taking the bytes as the
    app's 16 kHz 16-bit mono WAV (32,000 bytes a second)."""
    return len(data) // 1000


OFFLINE_TEXT = "(Offline model: set LLM_PROVIDER=vertex or add your own API key for real stories.)"
# What the offline model "hears" in any recording, so dictation works end to end locally (V6).
OFFLINE_TRANSCRIPT = "I look around slowly and listen."


def offline_reply(request: Request) -> Reply:
    """The offline model: a minimal valid answer for any schema, a note, a plain picture, or a
    fixed transcript for any recording."""
    if request.transcription is not None:
        return Reply(text=OFFLINE_TRANSCRIPT)
    if request.image is not None:
        return Reply(images=(offline_picture(request.image.aspect_ratio),))
    if request.json_schema is not None:
        return Reply(json=fill_schema(request.json_schema))
    return Reply(text=OFFLINE_TEXT)


_FORMATS = {
    "date-time": "2026-01-01T00:00:00Z",
    "date": "2026-01-01",
    "time": "00:00:00",
    "duration": "PT0S",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "email": "offline@example.com",
    "uri": "https://example.com/",
}


def fill_schema(schema: Mapping[str, Any]) -> Any:
    """Builds a small value that satisfies a Pydantic-generated JSON schema.

    It handles types, enums, constants, defaults, references, unions, lengths, item counts,
    number bounds and the common string formats. It can't satisfy a `pattern`, so a schema the
    offline model must answer should not constrain strings by pattern.
    """
    return _fill(schema, schema.get("$defs", {}), "value")


def _fill(schema: Mapping[str, Any], defs: Mapping[str, Any], name: str) -> Any:
    if "$ref" in schema:
        return _fill(defs[schema["$ref"].rsplit("/", 1)[-1]], defs, name)
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return _fill(options[0], defs, name)
    kind = schema.get("type", "object")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object":
        properties = schema.get("properties", {})
        return {key: _fill(value, defs, key) for key, value in properties.items()}
    if kind == "array":
        count = schema.get("minItems", 0)
        return [_fill(schema.get("items", {}), defs, name) for _ in range(count)]
    if kind == "string":
        if schema.get("format") in _FORMATS:
            return _FORMATS[schema["format"]]
        text = OFFLINE_TEXT if name in ("narration", "text") else f"(offline {name})"
        minimum = schema.get("minLength", 0)
        maximum = schema.get("maxLength")
        text = text.ljust(minimum, ".")
        return text[:maximum] if maximum is not None else text
    if kind in ("integer", "number"):
        return _number(schema, integer=kind == "integer")
    if kind == "boolean":
        return False
    return None


def _number(schema: Mapping[str, Any], *, integer: bool) -> int | float:
    step = 1 if integer else 1e-6
    low = schema.get("minimum")
    if low is None and "exclusiveMinimum" in schema:
        low = schema["exclusiveMinimum"] + step
    high = schema.get("maximum")
    if high is None and "exclusiveMaximum" in schema:
        high = schema["exclusiveMaximum"] - step
    if low is not None and high is not None:
        value = low if integer else (low + high) / 2
    elif low is not None:
        value = low
    elif high is not None:
        value = min(0, high)
    else:
        value = 0
    return math.ceil(value) if integer else float(value)
