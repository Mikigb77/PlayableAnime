"""The model client that graph nodes call: one retry, typed errors, telemetry (B6, T5, T7).

A node asks for a structured result, plain text, a streamed structured result or a picture. The
client resolves the node's model and settings from config, applies the rating's safety settings
(F5), runs the call on its backend with a deadline, retries a transient failure once, and turns
anything else into `LLMUnavailable`, `LLMBlocked` or `BadKey`. Every call, failed or not, leaves
one `CallRecord` with its recorder.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, cast

from pydantic import BaseModel, ValidationError

from graph.llm.config import ModelConfig
from graph.llm.errors import BadKey, LLMBlocked, LLMError, LLMUnavailable
from graph.llm.jsonstream import JsonFieldStreamer, strip_code_fence
from graph.llm.pricing import estimate_cost
from graph.llm.safety import safety_settings
from graph.llm.telemetry import CallRecord, CallRecorder, Outcome
from graph.llm.types import (
    Backend,
    CallOptions,
    Chunk,
    Finish,
    ImagePart,
    ImageSpec,
    Node,
    Prompt,
    ProviderError,
    Rating,
    Request,
    Usage,
)

logger = logging.getLogger("graph.llm")

ATTEMPTS = 2  # one try and one retry (T7)


@dataclass(frozen=True)
class TextDelta:
    """New text of the streamed field."""

    text: str


@dataclass(frozen=True)
class StreamRestart:
    """The attempt failed after text was streamed and is being retried: clear the partial text."""

    reason: Literal["retry"] = "retry"


@dataclass(frozen=True)
class Completed[T]:
    """The parsed result. Always the last event of a successful stream."""

    value: T


type StreamEvent[T] = TextDelta | StreamRestart | Completed[T]


@dataclass(frozen=True, repr=False)
class GeneratedImage:
    data: bytes
    mime_type: str

    def __repr__(self) -> str:
        return f"GeneratedImage(mime_type={self.mime_type!r}, bytes={len(self.data)})"


class _BadOutput(Exception):
    """The model answered, but not usably (cut off, unparseable, empty). Worth one retry."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class ModelClient:
    """Model access for one request, bound to the story's rating and the request's recorder.

    Build it with `graph.llm.build_client`. When it was built with a player's key, call
    `aclose()` once the request is done.
    """

    def __init__(
        self,
        backend: Backend,
        config: ModelConfig,
        *,
        rating: Rating,
        recorder: CallRecorder | None = None,
        byok: bool = False,
        owns_backend: bool = False,
        retry_delay_s: float = 0.5,
    ):
        self._backend = backend
        self._config = config
        self._rating: Rating = rating
        self._recorder = recorder
        self._byok = byok
        self._owns_backend = owns_backend
        self._retry_delay_s = retry_delay_s
        safety_settings(rating)  # fail fast on an unknown rating

    @property
    def byok(self) -> bool:
        return self._byok

    async def aclose(self) -> None:
        if self._owns_backend:
            await self._backend.aclose()

    async def structured[T: BaseModel](
        self, node: Node, prompt: Prompt, schema: type[T], *, options: CallOptions | None = None
    ) -> T:
        """One structured-output call, validated against `schema`."""
        return cast(T, await self._complete(node, prompt, schema=schema, options=options))

    async def text(self, node: Node, prompt: Prompt, *, options: CallOptions | None = None) -> str:
        """One plain-text call."""
        return cast(str, await self._complete(node, prompt, options=options))

    async def image(
        self,
        node: Node,
        prompt: Prompt,
        *,
        spec: ImageSpec | None = None,
        options: CallOptions | None = None,
    ) -> GeneratedImage:
        """One picture (M8). Reference images (M5) go in `prompt.images`."""
        return cast(
            GeneratedImage,
            await self._complete(node, prompt, image=spec or ImageSpec(), options=options),
        )

    def stream_structured[T: BaseModel](
        self,
        node: Node,
        prompt: Prompt,
        schema: type[T],
        *,
        field: str,
        options: CallOptions | None = None,
    ) -> AsyncIterator[StreamEvent[T]]:
        """One structured-output call that streams the text of one string field as it arrives.

        Yields `TextDelta`s, a `StreamRestart` if a retry follows streamed text, and finally
        `Completed` with the validated result. Wrap the iteration in `contextlib.aclosing`.
        Raises the typed errors like the other calls; `LLMBlocked.streamed` says whether text
        had already been shown.
        """
        if field not in schema.model_fields:
            raise ValueError(f"{schema.__name__} has no field {field!r}")
        return self._run(node, prompt, schema=schema, stream_field=field, options=options)

    async def _complete(self, node: Node, prompt: Prompt, **kwargs: Any) -> object:
        async with aclosing(self._run(node, prompt, **kwargs)) as events:
            async for event in events:
                if isinstance(event, Completed):
                    return event.value
        raise AssertionError("A model call ended without a result")  # pragma: no cover

    async def _run(
        self,
        node: Node,
        prompt: Prompt,
        *,
        schema: type[BaseModel] | None = None,
        stream_field: str | None = None,
        image: ImageSpec | None = None,
        options: CallOptions | None = None,
    ) -> AsyncIterator[StreamEvent[Any]]:
        settings = self._config.node(node)
        opts = settings.options.merged(options)
        request = Request(
            node=node,
            model=settings.model,
            prompt=prompt,
            options=opts,
            safety=safety_settings(self._rating, picture=image is not None),
            json_schema=_json_schema(schema) if schema is not None else None,
            image=image,
        )
        trace = _Trace(request, self._backend.provider, self._byok, self._config.location)
        try:
            for attempt in range(1, ATTEMPTS + 1):
                trace.attempts = attempt
                streamer = JsonFieldStreamer(stream_field) if stream_field else None
                streamed = False
                parts: list[str] = []
                images: list[ImagePart] = []
                finish: Finish | None = None
                try:
                    async with aclosing(self._attempt(request)) as chunks:
                        async for chunk in chunks:
                            trace.usage += chunk.usage
                            images.extend(chunk.images)
                            finish = chunk.finish or finish
                            if not chunk.text:
                                continue
                            parts.append(chunk.text)
                            if streamer is not None and (delta := streamer.feed(chunk.text)):
                                trace.saw_first_token()
                                streamed = True
                                yield TextDelta(delta)
                    value = self._result(request, schema, "".join(parts), images, finish, streamed)
                except (ProviderError, _BadOutput, TimeoutError) as failure:
                    reason = _reason(failure)
                    if isinstance(failure, ProviderError) and failure.kind != "transient":
                        raise self._fatal(failure, trace) from None
                    if attempt == ATTEMPTS:
                        trace.finish("unavailable", reason)
                        logger.error(
                            "Model call failed after a retry",
                            extra={"llm": trace.log_fields(reason=reason)},
                        )
                        raise LLMUnavailable(node=node.value, model=request.model) from None
                    trace.retry_reasons.append(reason)
                    logger.warning(
                        "Model call failed, retrying once",
                        extra={"llm": trace.log_fields(reason=reason)},
                    )
                    if streamed:
                        trace.first_token_ms = None  # the player sees the retry's text first
                        yield StreamRestart()
                    await asyncio.sleep(self._retry_delay_s)
                    continue
                if isinstance(value, GeneratedImage):
                    trace.images = 1
                trace.finish("ok")
                self._emit(trace)  # before the yield, so a caller that stops here is counted
                yield Completed(value)
                return
        except LLMBlocked as blocked:
            trace.blocked(blocked)
            logger.warning("Model call blocked", extra={"llm": trace.log_fields()})
            raise
        finally:
            self._emit(trace)

    async def _attempt(self, request: Request) -> AsyncIterator[Chunk]:
        """One backend attempt under the node's deadline. Odd backend errors become `invalid`.

        The deadline counts only time spent waiting for the model, never the caller's time
        between chunks, so a slow reader can't time out a healthy stream. A call can wait at most
        two deadlines, one per attempt, plus the retry delay.
        """
        budget = request.options.timeout_s or None
        loop = asyncio.get_running_loop()
        stream = self._backend.stream(request)
        try:
            while True:
                started = loop.time()
                try:
                    async with asyncio.timeout(budget):
                        chunk = await anext(stream)
                except StopAsyncIteration:
                    return
                if budget is not None:
                    budget = max(0.0, budget - (loop.time() - started))
                yield chunk
        except (ProviderError, TimeoutError, AssertionError):
            raise  # an AssertionError is a bug (or a fake out of script), never a model failure
        except Exception as error:
            logger.exception(
                "Model backend raised an unexpected error",
                extra={"llm": {"node": request.node.value, "model": request.model}},
            )
            raise ProviderError("invalid", type(error).__name__) from None
        finally:
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()

    def _result(
        self,
        request: Request,
        schema: type[BaseModel] | None,
        text: str,
        images: list[ImagePart],
        finish: Finish | None,
        streamed: bool,
    ) -> object:
        if finish is not None and finish.reason == "blocked":
            raise LLMBlocked(
                node=request.node.value,
                model=request.model,
                categories=finish.categories,
                stage=finish.stage,
                streamed=streamed,
            )
        if finish is not None and finish.reason != "stop":
            raise _BadOutput(finish.reason)
        if request.image is not None:
            if not images:
                raise _BadOutput("no_image")
            return GeneratedImage(images[0].data, images[0].mime_type)
        if not text.strip():
            raise _BadOutput("empty")
        if schema is None:
            return text
        try:
            return schema.model_validate_json(strip_code_fence(text))
        except ValidationError:
            raise _BadOutput("invalid_output") from None

    def _fatal(self, failure: ProviderError, trace: _Trace) -> LLMError:
        node, model = trace.request.node.value, trace.request.model
        if failure.kind == "auth" and self._byok:
            trace.finish("bad_key", "auth")
            logger.info("Player's API key was rejected", extra={"llm": trace.log_fields()})
            return BadKey(node=node, model=model)
        trace.finish("unavailable", failure.kind)
        logger.error(
            "Model call rejected",
            extra={"llm": trace.log_fields(reason=failure.kind, detail=failure.detail)},
        )
        return LLMUnavailable(node=node, model=model)

    def _emit(self, trace: _Trace) -> None:
        if trace.emitted:
            return
        trace.emitted = True
        record = trace.record()
        if self._recorder is not None:
            self._recorder.record(record)
        logger.debug("Model call", extra={"llm_call": record.as_log()})


@lru_cache(maxsize=256)
def _schema_text(schema: type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema())


def _json_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """The schema's JSON schema, built once per class. A fresh copy each call, since the SDK
    may rewrite it in place."""
    return json.loads(_schema_text(schema))


def _reason(failure: Exception) -> str:
    if isinstance(failure, _BadOutput):
        return failure.reason
    if isinstance(failure, TimeoutError):
        return "timeout"
    if isinstance(failure, ProviderError) and failure.status:
        return f"{failure.kind}_{failure.status}"
    return getattr(failure, "kind", type(failure).__name__)


class _Trace:
    """What one logical call did, across its attempts."""

    def __init__(self, request: Request, provider: str, byok: bool, location: str):
        self.request = request
        self.provider = provider
        self.byok = byok
        self.location = location
        self.started = time.monotonic()
        self.usage = Usage()
        self.attempts = 0
        self.retry_reasons: list[str] = []
        self.first_token_ms: int | None = None
        self.images = 0
        self.outcome: Outcome = "cancelled"
        self.error_kind: str | None = None
        self.block: LLMBlocked | None = None
        self.emitted = False
        self.ended: float | None = None

    def saw_first_token(self) -> None:
        if self.first_token_ms is None:
            self.first_token_ms = self._elapsed_ms()

    def finish(self, outcome: Outcome, error_kind: str | None = None) -> None:
        self.outcome = outcome
        self.error_kind = error_kind
        self.ended = time.monotonic()

    def blocked(self, block: LLMBlocked) -> None:
        self.block = block
        self.finish("blocked", "blocked")

    def _elapsed_ms(self) -> int:
        end = self.ended if self.ended is not None else time.monotonic()
        return round((end - self.started) * 1000)

    def log_fields(self, **extra: str) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "node": self.request.node.value,
            "model": self.request.model,
            "provider": self.provider,
            "byok": self.byok,
            "attempt": self.attempts,
        }
        if self.block is not None:
            fields["block_categories"] = list(self.block.categories)
            fields["block_stage"] = self.block.stage
        return fields | extra

    def record(self) -> CallRecord:
        cost, known = estimate_cost(
            self.request.model, self.usage, images=self.images, location=self.location
        )
        return CallRecord(
            node=self.request.node.value,
            model=self.request.model,
            provider=self.provider,
            byok=self.byok,
            outcome=self.outcome,
            input_tokens=self.usage.input_tokens,
            output_tokens=self.usage.output_tokens,
            thinking_tokens=self.usage.thinking_tokens,
            images=self.images,
            latency_ms=self._elapsed_ms(),
            first_token_ms=self.first_token_ms,
            attempts=self.attempts,
            retries=len(self.retry_reasons),
            retry_reasons=tuple(self.retry_reasons),
            blocked=self.block is not None,
            block_categories=self.block.categories if self.block else (),
            block_stage=self.block.stage if self.block else None,
            cost_usd=cost,
            price_known=known,
            error_kind=self.error_kind,
        )
