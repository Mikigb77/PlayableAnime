"""`POST /v1/stories/{id}/scenes/{turn}/audio`: a scene read aloud in the studio voice (V8 to V10).

The app reads a scene in parts (`speech.reading`): it asks for part 0, plays it as soon as it
comes, and asks for the next while it plays. Gemini's TTS model on Vertex AI reads each part in
the voice the player picked, and the MP3 is kept in the pictures' private bucket, so asking again
answers the same file at no charge (V10). Asking is always safe: a part is read and charged at
most once per voice, a repeat while it is read answers `pending`, and a part the voice model
refused answers `blocked`, which the app reads in the phone's own voice.

A part is billed like any model call (K2): the meter checks the rate limit, the daily quota and
the credits first, then charges the real cost plus the margin, about two cents for a long part.
It always runs on our account, even for a player with their own key, like dictation (V6).

The log line has sizes and numbers, never the words (T6).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from asgiref.sync import sync_to_async
from django.http import HttpRequest
from django.utils import timezone
from ninja import Field, Query, Router, Schema

from billing import meter
from graph.llm import LLMBlocked, LLMUnavailable, Node, Reading, TurnTelemetry, build_client
from lucid import logs
from lucid.errors import ApiError, ErrorCode, field_error
from media.api import absolute_url
from media.storage import get_storage, signed_url
from moderation.models import Report
from speech.audio import to_mp3
from speech.models import AudioStatus, SceneAudio
from speech.reading import reading_parts, reading_prompt
from speech.voices import DEFAULT_VOICE, VOICES
from stories.access import owned_story
from stories.models import Scene

logger = logging.getLogger("speech")

reading_router = Router(tags=["speech"])

# A part still `pending` after this was left by a request that died: the next request reads it
# again. Longer than the voice model's deadline and one retry.
STALE_AFTER_S = 120

UNAVAILABLE_MESSAGE = "The studio voice isn't available right now. Try again in a moment."


class AudioQuery(Schema):
    part: int = Field(default=0, ge=0, le=99)
    # One of `speech.voices.VOICES`.
    voice: str = Field(default=DEFAULT_VOICE, max_length=32)


class AudioOut(Schema):
    status: Literal["ready", "pending", "blocked"]
    part: int
    # How many parts the scene is read in: ask for each, from 0, in order.
    parts: int
    # The words this part reads, so the app can read a part the voice refused in the phone's
    # own voice, and the rest of the scene after a part that failed.
    text: str
    # Only when ready: a signed URL to the MP3, which works until `expires_at`, about an hour.
    url: str | None = None
    expires_at: datetime | None = None
    duration_ms: int | None = None


@dataclass
class _Reading:
    """What one request did, for its T5 line: numbers and names only (T6)."""

    voice: str
    part: int
    parts: int = 0
    chars: int = 0
    outcome: str = "ok"
    read: bool = False  # the voice model was called
    audio_bytes: int = 0
    duration_ms: int = 0
    started: float = field(default_factory=time.monotonic)


@reading_router.post("/{story_id}/scenes/{turn}/audio", response=AudioOut)
async def scene_audio(
    request: HttpRequest, story_id: str, turn: int, query: Query[AudioQuery]
) -> AudioOut:
    """Part `part` of the scene read aloud in `voice` (V9). See docs/API.md, Reading aloud."""
    record = _Reading(voice=query.voice, part=query.part)
    telemetry = TurnTelemetry()
    try:
        if query.voice not in VOICES:
            raise field_error(
                "voice", "Pick one of the studio voices.", source="query", type="unknown_voice"
            )
        story = await owned_story(request, story_id)
        logs.bind(story_id=str(story.id))
        scene = await Scene.objects.live().filter(story=story, turn=turn).afirst()
        if scene is None or await _blocked(scene):
            # A scene the player blocked (F6) is never read: its text stays out of sight.
            raise ApiError(ErrorCode.NOT_FOUND, "Scene not found.")
        parts = reading_parts(scene.narration)
        record.parts = len(parts)
        if query.part >= len(parts):
            raise field_error(
                "part", "The scene has no such part.", source="query", type="out_of_range"
            )
        text = parts[query.part]
        record.chars = len(text)
        row = await _claim(scene, query.voice, query.part, len(text))
        if row.status == AudioStatus.PENDING and not row.claimed:
            record.outcome = "pending"
            return _out(request, row, parts)
        if row.status != AudioStatus.PENDING:
            record.outcome = "kept" if row.status == AudioStatus.READY else str(row.status)
            record.duration_ms = row.duration_ms
            return _out(request, row, parts)
        await _read(request, story, scene, row, text, telemetry, record)
        return _out(request, row, parts)
    except ApiError as exc:
        if record.outcome in ("ok", "pending"):
            record.outcome = str(exc.code)
        raise
    except BaseException:
        record.outcome = "failed"
        raise
    finally:
        _log(record, telemetry)


async def _blocked(scene: Scene) -> bool:
    return await Report.objects.filter(scene=scene, block=True).aexists()


@dataclass
class _Row:
    """A part's row, and whether this request claimed it to read it."""

    audio: SceneAudio
    claimed: bool

    @property
    def status(self) -> str:
        return self.audio.status

    @property
    def duration_ms(self) -> int:
        return self.audio.duration_ms


async def _claim(scene: Scene, voice: str, part: int, chars: int) -> _Row:
    """The part's row: one already read or refused, one another request is reading, or one this
    request claims to read, new or left behind by a request that died (`STALE_AFTER_S`)."""
    # In a savepoint, so a request that loses the race to create it finds the winner's row.
    audio, created = await SceneAudio.objects.aget_or_create(
        scene=scene,
        voice=voice,
        part=part,
        defaults={"status": AudioStatus.PENDING, "chars": chars},
    )
    if created:
        return _Row(audio, claimed=True)
    if audio.status != AudioStatus.PENDING:
        return _Row(audio, claimed=False)
    cutoff = timezone.now() - timedelta(seconds=STALE_AFTER_S)
    taken = await SceneAudio.objects.filter(
        pk=audio.pk, status=AudioStatus.PENDING, updated_at__lt=cutoff
    ).aupdate(updated_at=timezone.now())
    return _Row(audio, claimed=taken == 1)


def model_backend():
    """The backend for the voice call, or None to let the model layer pick (Vertex AI, or the
    offline model with `LLM_PROVIDER=fake`). Tests replace this function."""
    return None


async def _read(
    request: HttpRequest,
    story,
    scene: Scene,
    row: _Row,
    text: str,
    telemetry: TurnTelemetry,
    record: _Reading,
) -> None:
    """Meters, reads, stores and charges one part. The meter refuses it first when the player is
    over the rate limit or the daily quota, or out of credits (T9, K2). A part that fails is
    never charged, and its row goes, so the next request tries again; a refused part stays
    refused, at no charge."""
    audio = row.audio
    try:
        ticket = await meter.astart(request.auth, meter.VOICE, byok=False)
    except ApiError:
        await audio.adelete()
        raise
    client = None
    try:
        client = await sync_to_async(_client, thread_sensitive=False)(story.rating, telemetry)
        record.read = True
        try:
            spoken = await client.read_aloud(
                Node.VOICE, reading_prompt(text), Reading(voice=audio.voice)
            )
            encoded = await sync_to_async(to_mp3, thread_sensitive=False)(
                spoken.data, spoken.mime_type
            )
        except LLMBlocked:
            record.outcome = "blocked"
            audio.status = AudioStatus.BLOCKED
            await audio.asave(update_fields=["status", "updated_at"])
            return
        except LLMUnavailable as exc:
            record.outcome = "unavailable"
            await audio.adelete()
            raise ApiError(ErrorCode.LLM_UNAVAILABLE, UNAVAILABLE_MESSAGE) from exc
        except ValueError as exc:
            # Speech in a form we can't read: worth a retry later, like a failed call.
            record.outcome = "unreadable_audio"
            await audio.adelete()
            raise ApiError(ErrorCode.LLM_UNAVAILABLE, UNAVAILABLE_MESSAGE) from exc
        key = f"stories/{scene.story_id}/voice/{audio.id}.mp3"
        await sync_to_async(get_storage().save, thread_sensitive=False)(
            key, encoded.data, encoded.mime_type
        )
        audio.storage_key = key
        audio.mime_type = encoded.mime_type
        audio.duration_ms = encoded.duration_ms
        audio.status = AudioStatus.READY
        await audio.asave(
            update_fields=["storage_key", "mime_type", "duration_ms", "status", "updated_at"]
        )
        record.audio_bytes = len(encoded.data)
        record.duration_ms = encoded.duration_ms
        # Charged once the file is kept, so a part the player paid for is always there.
        await meter.acharge(ticket, telemetry.calls, story_id=scene.story_id, turn=scene.turn)
    except BaseException:
        if audio.status == AudioStatus.PENDING and audio.pk is not None:
            # Anything else that went wrong (storage, a cancelled request): let the next one try.
            await SceneAudio.objects.filter(pk=audio.pk, status=AudioStatus.PENDING).adelete()
        raise
    finally:
        await meter.arelease(ticket)  # gives back the hold; nothing is held after a charge
        if client is not None:
            await client.aclose()


def _client(rating: str, telemetry: TurnTelemetry):
    """Built off the event loop: the first real client imports the model SDK (B10)."""
    return build_client(rating=rating, recorder=telemetry, backend=model_backend())


def _out(request: HttpRequest, row: _Row, parts: list[str]) -> AudioOut:
    audio = row.audio
    out = AudioOut(status=audio.status, part=audio.part, parts=len(parts), text=parts[audio.part])
    if audio.status == AudioStatus.READY:
        url = signed_url(audio.storage_key)
        out.url = absolute_url(request, url.url)
        out.expires_at = url.expires_at
        out.duration_ms = audio.duration_ms
    return out


def _log(record: _Reading, telemetry: TurnTelemetry) -> None:
    """T5: one line per request, with sizes and numbers only, never the words (T6)."""
    summary = telemetry.summary()
    fields = {
        "outcome": record.outcome,
        "voice": record.voice,
        "part": record.part,
        "parts": record.parts,
        "chars": record.chars,
        "read": record.read,
        "audio_bytes": record.audio_bytes,
        "duration_ms": record.duration_ms,
        "calls": summary["calls"],
        "models": summary["models"],
        "input_tokens": summary["input_tokens"],
        "output_tokens": summary["output_tokens"],
        "latency_ms": round((time.monotonic() - record.started) * 1000),
        "cost_usd": summary["cost_usd"],
        "billable_cost_usd": summary["billable_cost_usd"],
        "retries": summary["retries"],
    }
    quiet = record.outcome in ("ok", "kept", "pending", "blocked")
    logger.log(
        logging.INFO if quiet else logging.WARNING,
        "Reading aloud %s",
        record.outcome,
        extra={"voice": fields},
    )
