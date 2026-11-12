"""The model client that graph nodes call: retries, typed errors, telemetry (B6, T5, T7).

A node asks for a structured result, plain text, a streamed structured result, a picture, the
words in a recording (V6) or a text read aloud (V9). The client resolves the node's model and
settings from config, applies the rating's safety settings (F5), runs the call on its backend with
a deadline, retries a transient failure once (a 429 on our shared quota twice, after longer
waits), and turns anything else into `LLMUnavailable`, `LLMBlocked` or `BadKey`. Every call,
failed or not, leaves one `CallRecord` with its recorder.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping
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
    MODEL_OUTPUT,
    REPAIRS,
    AudioPart,
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
    Reading,
    Request,
    Transcription,
    Usage,
)

logger = logging.getLogger("graph.llm")

ATTEMPTS = 2  # one try and one retry (T7)
# Our Vertex AI quota is shared, and answers 429 in bursts that pass within seconds: three in 11 s
# from one caller on 2026-11-04. So a 429 on our account gets one more try than other failures,
# after longer waits. A player's key isn't shared: its 429 is its own limit, retried once.
RATE_LIMIT_ATTEMPTS = 3
RATE_LIMIT_BACKOFF = (4, 12)  # times the retry delay before each retry: 2 s, then 6 s


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


@dataclass(frozen=True, repr=False)
class GeneratedAudio:
    """Speech the voice model read (V9), as it sent it: for Gemini, raw 16-bit PCM with the rate
    in `mime_type` (`audio/L16;codec=pcm;rate=24000`)."""

    data: bytes
    mime_type: str

    def __repr__(self) -> str:
        return f"GeneratedAudio(mime_type={self.mime_type!r}, bytes={len(self.data)})"


class _BadOutput(Exception):
    """The model answered, but not usably (cut off, unparseable, empty). Worth one retry.

    An answer that fails validation keeps where and how it failed, for the log: the place of each
    error by field names and list positions, and its type, never a value (T6)."""

    def __init__(self, reason: str, error: ValidationError | None = None, chars: int = 0):
        super().__init__(reason)
        self.reason = reason
        self.errors = _error_places(error) if error is not None else []
        self.error_count = error.error_count() if error is not None else 0
        self.chars = chars

    def log_fields(self) -> dict[str, Any]:
        if not self.error_count:
            return {}
        return {"errors": self.errors, "error_count": self.error_count, "output_chars": self.chars}


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

    @property
    def backend(self) -> Backend:
        """The provider target, for a check that must see its raw answers (`check_models`)."""
        return self._backend

    async def aclose(self) -> None:
        if self._owns_backend:
            await self._backend.aclose()

    async def structured[T: BaseModel](
        self,
        node: Node,
        prompt: Prompt,
        schema: type[T],
        *,
        form: Mapping[str, Any] | None = None,
        options: CallOptions | None = None,
    ) -> T:
        """One structured-output call, validated against `schema`. `form` is the JSON schema
        the model is asked for when a call asks for less than the whole of `schema`'s: what it
        leaves out keeps the model's defaults."""
        return cast(
            T, await self._complete(node, prompt, schema=schema, form=form, options=options)
        )

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

    async def transcribe(
        self,
        node: Node,
        audio: AudioPart,
        spec: Transcription | None = None,
        *,
        options: CallOptions | None = None,
    ) -> str:
        """The words in a recording (V6), or an empty string when it holds no speech.

        The rating's safety settings aren't sent: the transcript is the player's own words, which
        the turn that takes them reads under its rating (F5), and a filter here would only stop
        the player from seeing what they said.
        """
        prompt = Prompt.build("", "")
        return cast(
            str,
            await self._complete(
                node, prompt, audio=audio, transcription=spec or Transcription(), options=options
            ),
        )

    async def read_aloud(
        self,
        node: Node,
        text: str,
        reading: Reading,
        *,
        options: CallOptions | None = None,
    ) -> GeneratedAudio:
        """`text` read aloud in `reading`'s voice (V9), word for word. Scenes are sent with no
        style directions, since Gemini's TTS models have read them aloud (`speech.reading`).

        The rating's safety settings aren't sent, as for dictation: the text is narration the
        player has already read, written under the story's rating (F5), and a filter here would
        only stop them hearing it.
        """
        return cast(
            GeneratedAudio,
            await self._complete(node, Prompt.build("", text), reading=reading, options=options),
        )

    def stream_structured[T: BaseModel](
        self,
        node: Node,
        prompt: Prompt,
        schema: type[T],
        *,
        field: str | tuple[str, ...],
        options: CallOptions | None = None,
    ) -> AsyncIterator[StreamEvent[T]]:
        """One structured-output call that streams the text of a string field as it arrives,
        or of several, one after the other with a paragraph break between (`JsonFieldStreamer`).

        Yields `TextDelta`s, a `StreamRestart` if a retry follows streamed text, and finally
        `Completed` with the validated result. Wrap the iteration in `contextlib.aclosing`.
        Raises the typed errors like the other calls; `LLMBlocked.streamed` says whether text
        had already been shown.
        """
        fields = (field,) if isinstance(field, str) else field
        for name in fields:
            if name not in schema.model_fields:
                raise ValueError(f"{schema.__name__} has no field {name!r}")
        return self._run(node, prompt, schema=schema, stream_fields=fields, options=options)

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
        form: Mapping[str, Any] | None = None,
        stream_fields: tuple[str, ...] = (),
        image: ImageSpec | None = None,
        audio: AudioPart | None = None,
        transcription: Transcription | None = None,
        reading: Reading | None = None,
        options: CallOptions | None = None,
    ) -> AsyncIterator[StreamEvent[Any]]:
        settings = self._config.node(node)
        opts = settings.options.merged(options)
        request = Request(
            node=node,
            model=settings.model,
            prompt=prompt,
            options=opts,
            safety={}
            if transcription is not None or reading is not None
            else safety_settings(self._rating, picture=image is not None, node=node),
            json_schema=_asked(schema, form),
            image=image,
            audio=audio,
            transcription=transcription,
            reading=reading,
        )
        trace = _Trace(request, self._backend.provider, self._byok, self._config.location)
        try:
            for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
                trace.attempts = attempt
                streamer = JsonFieldStreamer(*stream_fields) if stream_fields else None
                streamed = False
                parts: list[str] = []
                images: list[ImagePart] = []
                sound: list[AudioPart] = []
                finish: Finish | None = None
                try:
                    async with aclosing(self._attempt(request)) as chunks:
                        async for chunk in chunks:
                            trace.usage += chunk.usage
                            images.extend(chunk.images)
                            sound.extend(chunk.audio)
                            finish = chunk.finish or finish
                            if not chunk.text:
                                continue
                            parts.append(chunk.text)
                            if streamer is not None and (delta := streamer.feed(chunk.text)):
                                trace.saw_first_token()
                                streamed = True
                                yield TextDelta(delta)
                    value = self._result(
                        request, schema, "".join(parts), images, sound, finish, streamed
                    )
                except (ProviderError, _BadOutput, TimeoutError) as failure:
                    reason = _reason(failure)
                    if isinstance(failure, ProviderError) and failure.kind != "transient":
                        raise self._fatal(failure, trace) from None
                    # The provider's own words, such as which quota ran out. A player's key is
                    # already masked out of them by the backend (T6).
                    detail = failure.detail if isinstance(failure, ProviderError) else ""
                    fields = trace.log_fields(reason=reason, detail=detail)
                    if isinstance(failure, _BadOutput):
                        fields |= failure.log_fields()
                    rate_limited = reason == "transient_429" and not self._byok
                    if attempt >= (RATE_LIMIT_ATTEMPTS if rate_limited else ATTEMPTS):
                        trace.finish("unavailable", reason)
                        logger.error("Model call failed after retrying", extra={"llm": fields})
                        raise LLMUnavailable(node=node.value, model=request.model) from None
                    trace.retry_reasons.append(reason)
                    logger.warning("Model call failed, retrying", extra={"llm": fields})
                    if streamed:
                        trace.first_token_ms = None  # the player sees the retry's text first
                        yield StreamRestart()
                    backoff = RATE_LIMIT_BACKOFF[attempt - 1] if rate_limited else 1
                    await asyncio.sleep(self._retry_delay_s * backoff)
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
        one deadline per attempt, plus the retry delays.
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
        sound: list[AudioPart],
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
        if request.reading is not None:
            # A streamed answer comes in pieces of one stream, all of the first piece's type.
            if not any(part.data for part in sound):
                raise _BadOutput("no_audio")
            return GeneratedAudio(b"".join(part.data for part in sound), sound[0].mime_type)
        if request.transcription is not None:
            return text.strip()  # silence is an empty transcript, not a failure
        if not text.strip():
            raise _BadOutput("empty")
        if schema is None:
            return text
        context: dict[str, Any] = {MODEL_OUTPUT: True, REPAIRS: []}
        try:
            value = schema.model_validate_json(strip_code_fence(text), context=context)
        except ValidationError as error:
            raise _BadOutput("invalid_output", error, len(text)) from None
        if repairs := sorted(set(context[REPAIRS])):
            # A schema that reads model output leniently noted what it repaired (`types.REPAIRS`).
            logger.info(
                "Model answer repaired",
                extra={
                    "llm": {
                        "node": request.node.value,
                        "model": request.model,
                        "repairs": repairs[:MAX_LOGGED_REPAIRS],
                        "repair_count": len(repairs),
                    }
                },
            )
        return value

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


def _asked(schema: type[BaseModel] | None, form: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The JSON schema a call sends: the caller's form where it gave one, else the class's own.
    A fresh copy either way."""
    if schema is None:
        return None
    return copy.deepcopy(dict(form)) if form is not None else _json_schema(schema)


# How many of an answer's validation errors are logged, and how a place in it is written: field
# names and list positions only. Any other key, such as one the model wrote in a map, is "*".
MAX_LOGGED_ERRORS = 12
MAX_LOGGED_REPAIRS = 40
_FIELD_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


def _error_places(error: ValidationError) -> list[str]:
    """Each error as "world.npcs.3.parent_ids: list_type", without the value that failed."""
    places = []
    for detail in error.errors(include_url=False, include_context=False, include_input=False):
        where = ".".join(
            str(part) if isinstance(part, int) or _FIELD_NAME.fullmatch(str(part)) else "*"
            for part in detail["loc"]
        )
        places.append(f"{where or '(answer)'}: {detail['type']}")
        if len(places) == MAX_LOGGED_ERRORS:
            break
    return places


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
            cached_tokens=self.usage.cached_tokens,
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
