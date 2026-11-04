"""`POST /v1/transcriptions`: the words in a dictated recording (V1, V2, V5, V6, docs/API.md).

The app records while the mic is on and sends the clip as the request body, with its audio type
as `Content-Type`. Gemini 3.5 Transcribe on Vertex AI writes it down in the story's language (V4),
biased toward the names the player character knows in that story or draft (C6), and the app puts
the words in the box for the player to check before sending (V2).

The recording is held in memory for the request only: never written to disk by us, never stored
in the Files API, never logged (V5). The log line has sizes and numbers, never the words (T6, V7).

A dictation is billed like any model call (K2): the meter checks the rate limit, the daily quota
and the credits first, then charges the real cost plus the margin, a fraction of a cent (T9).
It always runs on our account, even for a player with their own key (S9): Vertex AI serves
Gemini 3.5 Transcribe through `generateContent`, but the Gemini API serves it only through its
Interactions API, which the model layer doesn't speak yet.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from ninja import Field, Query, Router, Schema

from billing import meter
from drafts import service as drafts
from engine.state import WorldState
from engine.visibility import speech_vocabulary
from graph.llm import (
    AudioPart,
    LLMBlocked,
    LLMUnavailable,
    Node,
    Transcription,
    TurnTelemetry,
    build_client,
)
from lucid import logs
from lucid.errors import ApiError, ErrorCode, field_error
from stories.access import graph_stories, owned_story

logger = logging.getLogger("speech")

transcriptions_router = Router(tags=["speech"])

# The app sends at most a minute of 16 kHz 16-bit mono WAV, 1.92 MB: under the 2.5 MB that Django
# holds in memory, so the app's recordings never touch the disk.
MAX_AUDIO_BYTES = 2 * 1024 * 1024

# The audio types Gemini 3.5 Transcribe takes, by the names clients send them under.
AUDIO_TYPES = {
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mp3": "audio/mp3",
    "audio/mpeg": "audio/mpeg",
    "audio/aac": "audio/aac",
    "audio/m4a": "audio/m4a",
    "audio/x-m4a": "audio/m4a",
    "audio/mp4": "audio/m4a",
    "audio/ogg": "audio/ogg",
    "audio/opus": "audio/opus",
    "audio/webm": "audio/webm",
    "audio/flac": "audio/flac",
    "audio/x-flac": "audio/flac",
    "audio/aiff": "audio/aiff",
    "audio/x-aiff": "audio/aiff",
}

BLOCKED_MESSAGE = "That couldn't be written down. Try saying it another way, or type it."
UNAVAILABLE_MESSAGE = "Dictation isn't available right now. Try again in a moment, or type."


class TranscriptionQuery(Schema):
    """Where the words go, for the names to listen for (C6), and the language (V4)."""

    story_id: str | None = Field(default=None, max_length=64)
    draft_id: str | None = Field(default=None, max_length=64)
    # A BCP-47 tag such as `en-US`. Left out, the model detects the language.
    language: str | None = Field(
        default=None, max_length=35, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    )


class TranscriptionOut(Schema):
    # Empty when the recording held no speech.
    text: str


@dataclass
class _Request:
    """What one transcription did, for its T5 line: numbers and names only (T6)."""

    language: str | None
    context: str
    mime_type: str = ""
    audio_bytes: int = 0
    vocabulary: int = 0
    outcome: str = "ok"
    chars: int = 0
    started: float = field(default_factory=time.monotonic)


_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            audio: {"schema": {"type": "string", "format": "binary"}}
            for audio in sorted(set(AUDIO_TYPES.values()))
        },
    }
}


@transcriptions_router.post("", response=TranscriptionOut, openapi_extra=_BODY)
async def transcribe(request: HttpRequest, query: Query[TranscriptionQuery]) -> dict[str, str]:
    """The words in the recording in the body (V6). See docs/API.md, Dictation."""
    record = _Request(
        language=query.language,
        context="story" if query.story_id else "draft" if query.draft_id else "none",
    )
    telemetry = TurnTelemetry()
    try:
        mime_type = record.mime_type = _audio_type(request)
        audio = _audio(request)
        record.audio_bytes = len(audio)
        if query.story_id and query.draft_id:
            raise field_error(
                "draft_id", "Send a story or a draft, not both.", source="query", type="conflict"
            )
        rating, names = await _context(request, query)
        record.vocabulary = len(names)
        spec = Transcription(
            language_codes=(query.language,) if query.language else (), vocabulary=tuple(names)
        )
        text = await _transcribe(
            request, rating, AudioPart(audio, mime_type), spec, query.story_id, telemetry, record
        )
    except ApiError as exc:
        if record.outcome == "ok":
            record.outcome = str(exc.code)  # refused: the request, the story, credits or limits
        raise
    except BaseException:
        record.outcome = "failed"
        raise
    finally:
        _log(record, telemetry)
    return {"text": text}


def _audio_type(request: HttpRequest) -> str:
    content_type = (request.content_type or "").strip().lower()
    mime_type = AUDIO_TYPES.get(content_type)
    if mime_type is None:
        raise field_error(
            "Content-Type",
            "Send the recording as audio, such as audio/wav.",
            source="header",
            type="unsupported_audio",
        )
    return mime_type


def _audio(request: HttpRequest) -> bytes:
    """The recording, refused when it is too long. Under ASGI, Django has already read the body
    before the view runs, in memory up to FILE_UPLOAD_MAX_MEMORY_SIZE (2.5 MB, more than a minute
    of the app's audio) and in a temporary file above it; Cloud Run caps a request at 32 MB."""
    declared = request.headers.get("Content-Length") or "0"
    if not declared.isdigit() or int(declared) > MAX_AUDIO_BYTES:
        raise _too_long()
    audio = request.body
    if len(audio) > MAX_AUDIO_BYTES:
        raise _too_long()
    if not audio:
        raise field_error("body", "The recording is empty.", type="missing")
    return audio


def _too_long() -> ApiError:
    return field_error("body", "The recording is too long: a minute at most.", type="too_long")


async def _context(request: HttpRequest, query: TranscriptionQuery) -> tuple[str, list[str]]:
    """The rating and the names the player character knows in the story or draft (C6). Only
    the player's own, within their rating limit (S8, F8)."""
    if query.story_id:
        story = await owned_story(request, query.story_id, graph_stories())
        logs.bind(story_id=str(story.id))
        names = await sync_to_async(_story_names)(story.state)
        return story.rating, names
    if query.draft_id:
        row = await drafts.owned_draft(request, query.draft_id)
        logs.bind(draft_id=str(row.id))
        names = await sync_to_async(_draft_names)(row)
        return row.rating, names
    return "teen", []


def _story_names(state: dict[str, Any]) -> list[str]:
    return speech_vocabulary(WorldState.model_validate(state))


def _draft_names(row) -> list[str]:
    return speech_vocabulary(drafts.to_chain(row).state())


def model_backend():
    """The backend for the speech call, or None to let the model layer pick (Vertex AI, or the
    offline model with `LLM_PROVIDER=fake`). Tests replace this function."""
    return None


async def _transcribe(
    request: HttpRequest,
    rating: str,
    audio: AudioPart,
    spec: Transcription,
    story_id: str | None,
    telemetry: TurnTelemetry,
    record: _Request,
) -> str:
    """Meters and runs the speech call. The meter refuses it first when the player is over the
    rate limit or the daily quota, or out of credits (T9, K2); a failed call is never charged."""
    ticket = await meter.astart(request.auth, meter.SPEECH, byok=False)
    client = None
    try:
        client = await sync_to_async(_client, thread_sensitive=False)(rating, telemetry)
        try:
            text = await client.transcribe(Node.SPEECH, audio, spec)
        except LLMBlocked as exc:
            record.outcome = "blocked"
            raise ApiError(ErrorCode.UNREADABLE_ACTION, BLOCKED_MESSAGE) from exc
        except LLMUnavailable as exc:
            record.outcome = "unavailable"
            raise ApiError(ErrorCode.LLM_UNAVAILABLE, UNAVAILABLE_MESSAGE) from exc
        await meter.acharge(ticket, telemetry.calls, story_id=story_id or None)
        record.chars = len(text)
        return text
    finally:
        await meter.arelease(ticket)  # gives back the hold; nothing is held after a charge
        if client is not None:
            await client.aclose()


def _client(rating: str, telemetry: TurnTelemetry):
    """Built off the event loop: the first real client imports the model SDK (B10)."""
    return build_client(rating=rating, recorder=telemetry, backend=model_backend())


def _log(record: _Request, telemetry: TurnTelemetry) -> None:
    """T5: one line per dictation, with sizes and numbers only, never the words (T6, V7)."""
    summary = telemetry.summary()
    fields = {
        "outcome": record.outcome,
        "mime_type": record.mime_type,
        "audio_bytes": record.audio_bytes,
        "language": record.language,
        "context": record.context,
        "vocabulary": record.vocabulary,
        "chars": record.chars,
        "calls": summary["calls"],
        "models": summary["models"],
        "input_tokens": summary["input_tokens"],
        "output_tokens": summary["output_tokens"],
        "latency_ms": round((time.monotonic() - record.started) * 1000),
        "cost_usd": summary["cost_usd"],
        "billable_cost_usd": summary["billable_cost_usd"],
        "retries": summary["retries"],
    }
    level = logging.INFO if record.outcome == "ok" else logging.WARNING
    logger.log(level, "Dictation %s", record.outcome, extra={"speech": fields})
