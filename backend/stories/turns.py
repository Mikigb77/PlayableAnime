"""Playing a turn over HTTP: what it reads, the stream it sends and the one transaction that
saves it (B5, B7, B12, S3, T5, T10, K2, V7).

    prepared = await sync_to_async(prepare)(story, body, user)  # may raise validation errors
    ticket = await meter.astart(user, meter.TURN, byok=byok is not None)
    return event_stream(stream(prepared, ticket=ticket, byok=byok, request=request))

The checks that can fail (auth, ownership, rating, version, the request itself, then credits,
rate limit and quota) run before the stream starts, so they come back as JSON errors. Once the
stream has started, a failure is an `error` event. Nothing is saved until the turn completes: the
world state, the scene, its pending events, its picture plan, the ledger entry and the version
bump are saved in one transaction, or none of them are (API.md).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest, StreamingHttpResponse
from django.utils import timezone

from billing import meter
from engine.context import ContentPrefs, Rating, TurnContext
from engine.contracts import PictureKind
from engine.invariants import InvariantError
from engine.labels import scene_time
from engine.state.world import WorldState
from engine.visibility import clock_view
from graph.llm import BadKey, ByokKey, LLMError, LLMUnavailable, TurnTelemetry, build_client
from graph.turn import (
    CHAPTER_TURNS,
    NarrationDelta,
    NarrationReset,
    PastScene,
    ScenePicture,
    TurnInput,
    TurnKind,
    TurnResult,
    UnreadableAction,
    run_turn,
)
from graph.turn.types import RECENT_SCENES
from lucid.errors import DEFAULT_MESSAGES, ApiError, ErrorCode, field_error, version_conflict
from media.plans import plan_picture
from media.prompts import MAX_FIGURES, Brief, Figure, WorldLook
from stories import pending, responses
from stories.models import Scene, Story
from stories.schemas import TurnIn

logger = logging.getLogger("stories.turns")

# Scenes since the last chapter are read in full for the next summary (C3). If summaries keep
# failing, older scenes stop being read past this many, so a turn's reads stay bounded.
MAX_PAST_SCENES = 3 * CHAPTER_TURNS


@dataclass(frozen=True)
class PreparedTurn:
    """A turn that passed every check that can fail before the stream starts."""

    story: Story
    input: TurnInput
    input_mode: str | None
    # The story version the turn read; it saves only if the story is still at it (T10).
    read_version: int


def prepare(story: Story, body: TurnIn, user) -> PreparedTurn:
    """Reads what the turn needs: the world state with its pending events (B12), the scenes the
    narrator and the summarizer read (C3), and the label of a picked suggestion. Raises
    `validation_error` for a turn that can't be played on this story as it stands."""
    state = pending.load(story, WorldState.model_validate(story.state))
    kind = TurnKind(body.kind)
    if kind is TurnKind.OPENING and state.turn != 0:
        raise field_error("kind", "This story has already opened.", type="already_opened")
    if kind is not TurnKind.OPENING and state.turn == 0:
        raise field_error(
            "kind", "This story hasn't opened yet: play its opening first.", type="not_opened"
        )
    action = body.action
    if kind is TurnKind.CHOICE:
        action = _choice_label(story, state.turn, body.choice_id)
    ctx = TurnContext(
        story_id=str(story.pk),
        turn=state.turn + 1,
        settings=responses.settings_of(story),
        rating=Rating(story.rating),
        content_prefs=ContentPrefs.model_validate(user.content_prefs or {}),
    )
    turn = TurnInput(
        state=state,
        ctx=ctx,
        kind=kind,
        action=action,
        standing=body.standing,
        premise=story.premise,
        scenes=_past_scenes(story, state),
    )
    return PreparedTurn(story=story, input=turn, input_mode=body.mode, read_version=story.version)


def _choice_label(story: Story, turn: int, choice_id: str | None) -> str:
    scene = Scene.objects.filter(story=story, turn=turn).only("choices").first()
    for choice in (scene.choices if scene else None) or []:
        if isinstance(choice, dict) and choice.get("id") == choice_id and choice.get("label"):
            return str(choice["label"])
    raise field_error("choice_id", "Unknown choice for the current scene.", type="unknown_choice")


def _past_scenes(story: Story, state: WorldState) -> tuple[PastScene, ...]:
    """Every scene since the last chapter, and never fewer than the last `RECENT_SCENES`."""
    last_chapter = max((chapter.to_turn for chapter in state.chapters), default=0)
    after = max(min(last_chapter, state.turn - RECENT_SCENES), state.turn - MAX_PAST_SCENES, 0)
    rows = (
        Scene.objects.filter(story=story, turn__gt=after, turn__lte=state.turn)
        .order_by("turn")
        .values_list("turn", "narration", "player_action")
    )
    return tuple(
        PastScene(turn=t, narration=text, player_action=action) for t, text, action in rows
    )


def event_stream(events: AsyncIterator[bytes]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(events, content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    # Proxies must pass each event on as it comes (S3).
    response["X-Accel-Buffering"] = "no"
    return response


def sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _error(code: ErrorCode, message: str | None = None, details: dict | None = None) -> bytes:
    return sse(
        "error",
        {
            "code": str(code),
            "message": message or DEFAULT_MESSAGES[code],
            "details": details or {},
        },
    )


async def stream(
    prepared: PreparedTurn,
    *,
    ticket: meter.Ticket,
    byok: ByokKey | None,
    request: HttpRequest | None = None,
) -> AsyncIterator[bytes]:
    """The turn as API.md's server-sent events: `turn.started`, the narration as it is written,
    then `scene.completed` once it is saved, or `error` with nothing saved and nothing charged.
    The credit hold is given back whatever happens, including the player leaving mid-turn."""
    turn = prepared.input
    telemetry = TurnTelemetry()
    started = time.monotonic()
    first_text_ms: int | None = None
    # Until the turn ends one way or another: a player who leaves mid-turn abandons it.
    outcome = "abandoned"
    result: TurnResult | None = None
    llm = None
    try:
        yield sse("turn.started", {"turn": turn.ctx.turn})
        llm = build_client(rating=turn.ctx.rating.value, byok=byok, recorder=telemetry)
        async with aclosing(run_turn(turn, llm)) as events:
            async for event in events:
                if isinstance(event, NarrationDelta):
                    if first_text_ms is None:
                        first_text_ms = int((time.monotonic() - started) * 1000)
                    yield sse("narration.delta", {"text": event.text})
                elif isinstance(event, NarrationReset):
                    yield sse("narration.reset", {"reason": event.reason})
                else:
                    result = event.result
        if result is None:
            raise RuntimeError("the turn ended without a result")
        completed = await asave(
            prepared, result, telemetry=telemetry, ticket=ticket, request=request
        )
        outcome = "ok"
        yield sse("scene.completed", completed)
    except UnreadableAction as error:
        # F4: the one block the player sees. The app offers to rephrase or retry.
        outcome = error.code
        yield _error(ErrorCode.UNREADABLE_ACTION, error.message, getattr(error, "details", None))
    except BadKey:
        outcome = "bad_key"
        yield _error(ErrorCode.BAD_KEY, BadKey.default_message)
    except LLMError:
        # T7: the model failed twice. A provider's own message can carry details, so it's
        # never passed on.
        outcome = "llm_unavailable"
        yield _error(ErrorCode.LLM_UNAVAILABLE, LLMUnavailable.default_message)
    except ApiError as error:
        # Another turn was saved first (T10), or the story was deleted mid-turn.
        outcome = str(error.code)
        yield _error(error.code, error.message, error.details)
    except InvariantError as error:
        # C1: an engine bug. The rules and ids, never the details, which can quote the story.
        logger.error(
            "A turn broke the world's invariants, so nothing was saved",
            extra={
                "invariants": [{"rule": v.rule, "subject": v.subject} for v in error.violations]
            },
        )
        logger.debug("Invariant details: %s", error)
        outcome = "internal_error"
        yield _error(ErrorCode.INTERNAL_ERROR)
    except Exception:
        logger.exception("A turn failed, so nothing was saved")
        outcome = "internal_error"
        yield _error(ErrorCode.INTERNAL_ERROR)
    finally:
        try:
            if llm is not None:
                await llm.aclose()
        finally:
            await meter.arelease(ticket)
            _log(prepared, result, telemetry, outcome, started, first_text_ms)


def save(
    prepared: PreparedTurn,
    result: TurnResult,
    *,
    telemetry: TurnTelemetry,
    ticket: meter.Ticket,
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    """Saves the turn in one transaction and returns `scene.completed`'s data. Raises
    `version_conflict` when another turn was saved since this one read the story (T10)."""
    story = prepared.story
    state = result.state
    draft = result.scene
    with transaction.atomic():
        saved = Story.objects.filter(pk=story.pk, version=prepared.read_version).update(
            state=state.model_dump(mode="json"),
            turn=state.turn,
            version=F("version") + 1,
            updated_at=timezone.now(),
        )
        if saved != 1:
            current = Story.objects.filter(pk=story.pk).values_list("version", flat=True).first()
            if current is None:
                raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
            raise version_conflict(current)
        lived = draft.personal_elapsed_s
        times = scene_time(
            state.bible.calendar,
            draft.world_start_s,
            draft.world_end_s,
            lived if lived is not None else draft.world_end_s - draft.world_start_s,
        )
        scene = Scene.objects.create(
            story=story,
            turn=draft.turn,
            kind=draft.kind.value,
            player_action=draft.player_action,
            input_mode=prepared.input_mode,
            narration=draft.narration,
            choices=[choice.model_dump(mode="json") for choice in draft.choices],
            details=draft.details.model_dump(mode="json"),
            event=draft.event.model_dump(mode="json") if draft.event else None,
            world_start_s=draft.world_start_s,
            world_end_s=draft.world_end_s,
            personal_elapsed_s=lived,
            time_label=times.label,
            duration_label=times.duration_label,
            personal_label=times.personal_label or "",
            timeline_id=draft.timeline_id,
            cast=cast(state),
            image_prompt=draft.picture.prompt if draft.picture else None,
        )
        pending.write_back(story, prepared.input.state, state)
        _plan_picture(story, scene, state, result)
        meter.charge(ticket, telemetry.calls, story_id=story.pk, turn=scene.turn)
    story.version = prepared.read_version + 1
    story.turn = state.turn
    shown = responses.scenes_out(story, [scene], request=request)[0]
    return {
        "scene": shown.model_dump(mode="json"),
        "story": {"version": story.version, "clock": clock_view(state).model_dump(mode="json")},
    }


asave = sync_to_async(save)


def cast(state: WorldState) -> list[dict[str, str]]:
    """The other characters there at the scene's end whom the player knows (M4, M5)."""
    player_id = state.player_id
    entries = []
    for character_id in dict.fromkeys(state.scene.present_ids):
        character = state.characters.get(character_id)
        if character is None or character_id == player_id or not character.alive:
            continue
        if player_id in character.known_by or player_id in character.met_by:
            entries.append({"character_id": character_id, "name": character.name})
    return entries


def _plan_picture(story: Story, scene: Scene, state: WorldState, result: TurnResult) -> None:
    """Plans the picture code chose for the scene (M1), drawn later in the app's own request
    (M3). A picture that can't be planned leaves the scene without one; the turn still saves."""
    picture = result.scene.picture
    decision = result.plan.picture
    if picture is None or decision is None:
        return
    try:
        with transaction.atomic():
            plan_picture(
                scene,
                kind=picture.kind.value,
                trigger=decision.trigger.value,
                brief=brief(story, state, picture),
                subject_id=picture.subject_id,
                # M5: a portrait whose subject looks different now is drawn again, once.
                redraw=picture.kind is PictureKind.PORTRAIT,
            )
    except Exception:
        logger.exception(
            "A scene's picture couldn't be planned, so the scene has none",
            extra={"picture": {"kind": picture.kind.value, "trigger": decision.trigger.value}},
        )


def brief(story: Story, state: WorldState, picture: ScenePicture) -> Brief:
    """What to draw: the prompt, the world's look (S7), and the subject or the known people in
    the scene with the appearance kept in their entries (C9, M5)."""
    bible = state.bible
    look = WorldLook(
        genre=bible.genre or story.genre, era=bible.era, tone=bible.tone, setting=story.premise
    )
    subject_id = picture.subject_id
    if picture.kind is PictureKind.PORTRAIT and subject_id in state.characters:
        character = state.characters[subject_id]
        return Brief(
            description=picture.prompt,
            look=look,
            subject_name=character.name,
            subject_appearance=character.appearance or character.description,
        )
    if picture.kind is PictureKind.PLACE and subject_id in state.places:
        place = state.places[subject_id]
        return Brief(
            description=picture.prompt,
            look=look,
            subject_name=place.name,
            subject_appearance=place.description,
        )
    people = [state.player, *(state.characters[e["character_id"]] for e in cast(state))]
    figures = tuple(
        Figure(id=person.id, name=person.name, appearance=person.appearance or person.description)
        for person in people[:MAX_FIGURES]
    )
    return Brief(description=picture.prompt, look=look, figures=figures)


def _log(
    prepared: PreparedTurn,
    result: TurnResult | None,
    telemetry: TurnTelemetry,
    outcome: str,
    started: float,
    first_text_ms: int | None,
) -> None:
    """T5's one line per turn, with how the action was entered (V7). Numbers, names and codes
    only: never the action, the narration or a prompt (T6)."""
    turn = prepared.input
    fields: dict[str, Any] = {
        "turn": turn.ctx.turn,
        "kind": turn.kind.value,
        "input_mode": prepared.input_mode,
        "outcome": outcome,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "first_text_ms": first_text_ms,
        "narration_mode": result.narration_mode if result else None,
        "issues": [issue.code for issue in result.issues] if result else [],
        "node_ms": dict(result.timings_ms) if result else {},
    } | telemetry.summary()
    logger.info("Turn %s", outcome, extra={"turn": fields})
