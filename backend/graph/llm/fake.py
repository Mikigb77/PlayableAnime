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

# The smallest valid PNG: one transparent pixel. The offline picture.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


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


OFFLINE_TEXT = "(Offline model: set LLM_PROVIDER=vertex or add your own API key for real stories.)"


def offline_reply(request: Request) -> Reply:
    """The offline model: a minimal valid answer for any schema, a note, or a blank picture."""
    if request.image is not None:
        return Reply(images=(TINY_PNG,))
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
