"""Playing a turn over HTTP: what it reads, the stream it sends and the one transaction that
saves it (B5, B7, B12, S3, T5, T10, K2, V7).

    prepared = await sync_to_async(prepare)(story, body, user)  # may raise validation errors
    ticket = await meter.astart(user, meter.TURN, byok=byok is not None)
    return TurnStream(stream(prepared, ticket=ticket, byok=byok, request=request), ticket)

The checks that can fail (auth, ownership, rating, version, the request itself, then credits,
rate limit and quota) run before the stream starts, so they come back as JSON errors. Once the
stream has started, a failure is an `error` event. Nothing of the world is saved until the turn
completes: the world state, the scene, its pending events, its picture plan, the ledger entry,
the version bump and the world state kept for a rewind (C8) are saved in one transaction, or none
of them are (API.md).

The engine decides the steps before the narrator writes, and the stream sends them at once
(`steps.decided`, A3). The turn is first kept on the story (`stories.unfinished`), so if its
scene is never saved, the next turn sent plays that one out, with the same steps and dice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import F, Q
from django.http import HttpRequest, StreamingHttpResponse
from django.utils import timezone
from pydantic import ValidationError

from billing import meter
from engine.context import ContentPrefs, Rating, TurnContext
from engine.contracts import PictureKind, PictureTrigger
from engine.invariants import InvariantError
from engine.labels import scene_time
from engine.looks import place_looks
from engine.state.world import WorldState
from engine.visibility import clock_view
from graph.llm import BadKey, ByokKey, LLMError, LLMUnavailable, TurnTelemetry, build_client
from graph.turn import (
    MAX_CHAPTER_TURNS,
    RECENT_SCENES,
    EndingRefused,
    NarrationDelta,
    NarrationReset,
    PastScene,
    ScenePicture,
    StepsDecided,
    TurnInput,
    TurnKind,
    TurnResult,
    UnreadableAction,
    run_turn,
    turn_graph,
)
from lucid.errors import ApiError, ErrorCode, envelope, field_error, version_conflict
from media.briefs import (
    THREAD_SUBJECTS,
    cover_brief,
    known_cast,
    scene_figures,
    scene_place,
    time_of_day,
)
from media.plans import look_for_story, plan_picture
from media.prompts import Brief
from stories import endings, pending, responses, rewind, unfinished
from stories.models import Scene, Story
from stories.schemas import RESUME, TurnIn

logger = logging.getLogger("stories.turns")


@dataclass(frozen=True)
class PreparedTurn:
    """A turn that passed every check that can fail before the stream starts."""

    story: Story
    input: TurnInput
    input_mode: str | None
    # The story version the turn read; it saves only if the story is still at it (T10).
    read_version: int
    # A3: this is a turn that was decided and shown before, played out now whatever was sent.
    resumed: bool = False


def prepare(story: Story, body: TurnIn, user) -> PreparedTurn:
    """Reads what the turn needs: the world state with its pending events (B12), the scenes the
    narrator and the summarizer read (C3), and the label of a picked suggestion. Raises
    `validation_error` for a turn that can't be played on this story as it stands."""
    state = pending.load(story, WorldState.model_validate(story.state))
    ending = endings.of_story(story.ending, state)
    if ending is not None:
        # N6: the player character's story is over; the story takes no more turns.
        raise endings.ended(ending)
    owed = unfinished.of_story(story, state)
    if owed is not None:
        try:
            return _resume(story, state, owed, user)
        except ValueError:
            # Kept under rules that have changed since: it can't be played as the story stands.
            logger.warning(
                "An unfinished turn couldn't be played out, so it was let go",
                extra={"unfinished_turn": {"story_turn": state.turn}},
            )
    if story.unfinished_turn:
        # One kept for another moment, or that can't be read or played any more, never holds a
        # story up.
        unfinished.drop(story)
    if body.kind == RESUME:
        raise field_error(
            "kind", "This story has no unfinished turn to play out.", type="nothing_unfinished"
        )
    kind = TurnKind(body.kind)
    # N6: a story carried on by someone new opens again, for them.
    opening_due = state.turn == 0 or state.opening_due
    if kind is TurnKind.OPENING and not opening_due:
        raise field_error("kind", "This story has already opened.", type="already_opened")
    if kind is not TurnKind.OPENING and opening_due:
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
        drop_refused=body.drop_refused,
    )
    return PreparedTurn(story=story, input=turn, input_mode=body.mode, read_version=story.version)


def _resume(story: Story, state: WorldState, owed: unfinished.Unfinished, user) -> PreparedTurn:
    """A3. The turn the story owes, whatever was sent: the same action, read as it was when
    it was first decided, under the settings the engine decided it by (A5, W16)."""
    settings = responses.settings_of(story).model_copy(
        update={"difficulty": owed.difficulty, "event_frequency": owed.event_frequency}
    )
    ctx = TurnContext(
        story_id=str(story.pk),
        turn=owed.turn,
        settings=settings,
        rating=Rating(story.rating),
        content_prefs=ContentPrefs.model_validate(user.content_prefs or {}),
    )
    turn = TurnInput(
        state=state,
        ctx=ctx,
        kind=owed.kind,
        action=owed.action,
        standing=owed.standing,
        premise=story.premise,
        scenes=_past_scenes(story, state),
        drop_refused=owed.drop_refused,
        reading=owed.reading,
    )
    return PreparedTurn(
        story=story,
        input=turn,
        input_mode=owed.input_mode,
        read_version=story.version,
        resumed=True,
    )


def _choice_label(story: Story, turn: int, choice_id: str | None) -> str:
    scene = Scene.objects.live().filter(story=story, turn=turn).only("choices").first()
    for choice in (scene.choices if scene else None) or []:
        if isinstance(choice, dict) and choice.get("id") == choice_id and choice.get("label"):
            return str(choice["label"])
    raise field_error("choice_id", "Unknown choice for the current scene.", type="unknown_choice")


def _past_scenes(story: Story, state: WorldState) -> tuple[PastScene, ...]:
    """The scenes the next chapter covers (at most `MAX_CHAPTER_TURNS` since the last chapter,
    C3), and never fewer than the last `RECENT_SCENES`, which the narrator reads in full."""
    last_chapter = max((chapter.to_turn for chapter in state.chapters), default=0)
    chapter = Q(turn__gt=last_chapter, turn__lte=last_chapter + MAX_CHAPTER_TURNS)
    recent = Q(turn__gt=state.turn - RECENT_SCENES)
    rows = (
        Scene.objects.live()
        .filter(story=story, turn__lte=state.turn)
        .filter(chapter | recent)
        .order_by("turn")
        .values_list("turn", "narration", "player_action")
    )
    return tuple(
        PastScene(turn=t, narration=text, player_action=action) for t, text, action in rows
    )


class TurnStream(StreamingHttpResponse):
    """The turn's event stream. If Django closes it before it ever started, as when the player
    left at once, it gives the credit hold back itself; once started, the stream does."""

    def __init__(self, events: AsyncIterator[bytes], ticket: meter.Ticket) -> None:
        self._ticket = ticket
        self._started = False
        super().__init__(self._tracked(events), content_type="text/event-stream; charset=utf-8")
        self["Cache-Control"] = "no-cache"
        # Proxies must pass each event on as it comes (S3).
        self["X-Accel-Buffering"] = "no"

    async def _tracked(self, events: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        self._started = True
        async with aclosing(events) as chunks:
            async for chunk in chunks:
                yield chunk

    def close(self) -> None:
        try:
            if not self._started:
                meter.release(self._ticket)
        finally:
            super().close()


def sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _error(code: ErrorCode, message: str | None = None, details: dict | None = None) -> bytes:
    """The `error` event, with the same fields as a JSON error's envelope."""
    return sse("error", envelope(code, message or ApiError(code).message, details)["error"])


@dataclass
class _Run:
    """What the T5 line reports about one turn."""

    started: float = field(default_factory=time.monotonic)
    # Until the turn ends one way or another: a player who leaves before it is saved abandons it.
    outcome: str = "abandoned"
    # Whether `scene.completed` went out. A turn saved after its player left is `ok` but unsent.
    sent: bool = False
    first_text_ms: int | None = None
    result: TurnResult | None = None
    decided: StepsDecided | None = None
    # A3: this run kept its turn on the story, or plays out the one the story owed.
    owed: bool = False


async def stream(
    prepared: PreparedTurn,
    *,
    ticket: meter.Ticket,
    byok: ByokKey | None,
    request: HttpRequest | None = None,
) -> AsyncIterator[bytes]:
    """The turn as API.md's server-sent events: `turn.started`, the steps the engine decided,
    the narration as it is written, then `scene.completed` once it is saved, or `error` with no
    scene saved and nothing charged. The credit hold is given back whatever happens, including
    the player leaving mid-turn."""
    turn = prepared.input
    telemetry = TurnTelemetry()
    run = _Run(owed=prepared.resumed)
    llm = None
    try:
        started: dict[str, Any] = {"turn": turn.ctx.turn}
        if prepared.resumed:
            # A3: the app sent some turn, and this is the one that plays.
            started |= {"resumed": True, "kind": turn.kind.value, "action": _shown_action(turn)}
        yield sse("turn.started", started)
        # The model SDK and LangGraph load on the first turn (B10), and a player's key gets a
        # client of its own: both off the event loop, so other streams don't stall (S3).
        llm = await asyncio.to_thread(
            build_client, rating=turn.ctx.rating.value, byok=byok, recorder=telemetry
        )
        await asyncio.to_thread(turn_graph)
        async with aclosing(run_turn(turn, llm)) as events:
            async for event in events:
                if isinstance(event, NarrationDelta):
                    if run.first_text_ms is None:
                        run.first_text_ms = int((time.monotonic() - run.started) * 1000)
                    yield sse("narration.delta", {"text": event.text})
                elif isinstance(event, NarrationReset):
                    yield sse("narration.reset", {"reason": event.reason})
                elif isinstance(event, StepsDecided):
                    run.decided = event
                    if not run.owed:
                        # A3: kept before its steps are shown, so the turn is played out.
                        await akeep(prepared, event)
                        run.owed = True
                    yield sse(
                        "steps.decided",
                        {"turn": turn.ctx.turn, "details": event.details.model_dump(mode="json")},
                    )
                else:
                    run.result = event.result
        if run.result is None:
            raise RuntimeError("the turn ended without a result")
        saving = asyncio.ensure_future(
            asave(
                prepared,
                run.result,
                telemetry=telemetry,
                ticket=ticket,
                request=request,
                owed=run.owed,
            )
        )
        try:
            completed = await asyncio.shield(saving)
        except asyncio.CancelledError:
            # The player left while the turn was being saved. The save finishes in its thread
            # either way, so wait for it, for the T5 line to say what happened.
            run.outcome = await _outcome_of(saving)
            raise
        run.outcome = "ok"
        yield sse("scene.completed", completed)
        run.sent = True
    except EndingRefused as refusal:
        # N6: the note asked for an ending the world won't give. Nothing saved or charged; the
        # app offers to play on or to end without it.
        run.outcome = refusal.code
        yield sse(
            "ending.refused",
            {
                "message": refusal.message,
                "refused": [
                    {"text": r.text, "reason": r.reason, "class": r.outcome_class}
                    for r in refusal.refused
                ],
            },
        )
    except UnreadableAction as error:
        # F4: the one block the player sees. The app offers to rephrase or retry.
        run.outcome = error.code
        yield _error(ErrorCode.UNREADABLE_ACTION, error.message, getattr(error, "details", None))
    except BadKey:
        run.outcome = "bad_key"
        yield _error(ErrorCode.BAD_KEY, BadKey.default_message)
    except LLMError:
        # T7: the model failed twice. A provider's own message can carry details, so it's
        # never passed on.
        run.outcome = "llm_unavailable"
        yield _error(ErrorCode.LLM_UNAVAILABLE, LLMUnavailable.default_message)
    except ApiError as error:
        # Another turn was saved first (T10), or the story was deleted mid-turn.
        run.outcome = str(error.code)
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
        run.outcome = "internal_error"
        await _let_go(prepared)
        yield _error(ErrorCode.INTERNAL_ERROR)
    except Exception as error:
        log_failure("A turn failed, so nothing was saved", error)
        run.outcome = "internal_error"
        await _let_go(prepared)
        yield _error(ErrorCode.INTERNAL_ERROR)
    finally:
        try:
            if llm is not None:
                await llm.aclose()
        finally:
            await meter.arelease(ticket)
            _log(prepared, run, telemetry)


def _shown_action(turn: TurnInput) -> str | None:
    """What the player did, as its scene will show it."""
    if turn.kind is TurnKind.STANDING and turn.standing is not None:
        return turn.standing.value
    return turn.action


def keep(prepared: PreparedTurn, decided: StepsDecided) -> None:
    unfinished.keep(
        prepared.story,
        prepared.input,
        decided,
        input_mode=prepared.input_mode,
        version=prepared.read_version,
    )


akeep = sync_to_async(keep)


async def _let_go(prepared: PreparedTurn) -> None:
    """A3. A turn the story owed that broke while it was played out is let go, so the story is
    never stuck behind it: the next turn sent is a fresh one. The first failure keeps it, since
    it may have been a passing fault."""
    if not prepared.resumed:
        return
    try:
        await sync_to_async(unfinished.drop)(prepared.story)
    except Exception as error:
        log_failure("An unfinished turn couldn't be let go", error)


async def _outcome_of(saving: asyncio.Future) -> str:
    try:
        await saving
    except ApiError as error:
        return str(error.code)
    except Exception as error:
        log_failure("A turn failed, so nothing was saved", error)
        return "internal_error"
    return "ok"


def log_failure(message: str, error: BaseException) -> None:
    """Logs an unexpected error with its traceback for Error Reporting. A Pydantic error's text
    quotes the values it rejected, which can be story text, so it is logged without them at
    ERROR and in full only at DEBUG (T6)."""
    if not isinstance(error, ValidationError):
        logger.error(message, exc_info=error)
        return
    problems = "; ".join(
        f"{'.'.join(str(part) for part in problem['loc']) or '(root)'}: {problem['type']}"
        for problem in error.errors(include_input=False, include_url=False)
    )
    safe = ValueError(f"{error.error_count()} validation errors for {error.title}: {problems}")
    logger.error(message, exc_info=(ValueError, safe, error.__traceback__))
    logger.debug("Validation details: %s", error)


def save(
    prepared: PreparedTurn,
    result: TurnResult,
    *,
    telemetry: TurnTelemetry,
    ticket: meter.Ticket,
    request: HttpRequest | None = None,
    owed: bool = False,
) -> dict[str, Any]:
    """Saves the turn in one transaction and returns `scene.completed`'s data. Raises
    `version_conflict` when another turn was saved since this one read the story (T10), or when
    the story owes a turn that isn't this one: `owed` says this is the turn it owes (A3)."""
    story = prepared.story
    state = result.state
    draft = result.scene
    data = state.model_dump(mode="json")
    ending = None
    with transaction.atomic():
        if result.ending is not None:
            # C8: how far back the ending can be rewound, by the difficulty it was played on.
            reach = rewind.reach(
                story, draft.turn, prepared.input.ctx.settings.difficulty, result.ending
            )
            ending = endings.record(result.ending, state, draft.turn, rewind=reach)
        current = Story.objects.filter(pk=story.pk, version=prepared.read_version)
        if not owed:
            # A3: another action was decided and shown while this one played, and that one
            # is played out. Saving this one instead would let what was shown be dodged.
            current = current.filter(unfinished_turn__isnull=True)
        saved = current.update(
            state=data,
            turn=state.turn,
            # A3: the turn is played out, so the story owes none.
            unfinished_turn=None,
            version=F("version") + 1,
            updated_at=timezone.now(),
            **({"ending": ending} if ending is not None else {}),
        )
        if saved != 1:
            version = Story.objects.filter(pk=story.pk).values_list("version", flat=True).first()
            if version is None:
                raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
            raise version_conflict(version)
        lived = draft.personal_elapsed_s
        times = scene_time(
            state.bible.calendar,
            draft.world_start_s,
            draft.world_end_s,
            lived if lived is not None else draft.world_end_s - draft.world_start_s,
            # S10: the time bar in the story's language when the scene was played.
            prepared.input.ctx.settings.language,
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
            # The cover is the story's, not this scene's (M1): Illustrate draws the scene itself.
            image_prompt=draft.picture.prompt
            if draft.picture and draft.picture.kind is not PictureKind.COVER
            else None,
        )
        pending.write_back(story, prepared.input.state, state)
        rewind.keep(story, state.turn, data)
        _plan_picture(story, scene, state, result)
        meter.charge(ticket, telemetry.calls, story_id=story.pk, turn=scene.turn)
    story.version = prepared.read_version + 1
    story.turn = state.turn
    # The turn is saved and charged now, so nothing after this may fail it.
    try:
        shown = responses.scenes_out(story, [scene], request=request, blocked=set())[0]
    except Exception as error:
        log_failure("A saved scene's pictures couldn't be read, so it is sent without", error)
        shown = responses.bare_scene(scene)
    story_part: dict[str, Any] = {
        "version": story.version,
        "clock": clock_view(state, prepared.input.ctx.settings.language).model_dump(mode="json"),
    }
    if ending is not None:
        story.ending = ending
        story_part["ending"] = ending
    return {"scene": shown.model_dump(mode="json"), "story": story_part}


asave = sync_to_async(save)


def cast(state: WorldState) -> list[dict[str, str]]:
    """The other characters there at the scene's end whom the player knows (M4, M5)."""
    return [{"character_id": c.id, "name": c.name} for c in known_cast(state)]


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
                brief=brief(story, state, picture, decision.trigger),
                subject_id=picture.subject_id,
                # M1, M5: a place or face that changed for good is drawn once more, then reused.
                version=decision.version,
            )
    except Exception as error:
        log_failure("A scene's picture couldn't be planned, so the scene has none", error)


def brief(
    story: Story,
    state: WorldState,
    picture: ScenePicture,
    trigger: PictureTrigger | None = None,
) -> Brief:
    """What to draw: the prompt, the world's look (S7), and the subject, or for a scene the people
    in it with the appearance kept in their entries (C9, M5) and what the player character has on
    them (C10), chosen by `media.briefs.scene_figures`, and the scene's turn. A scene picture also
    gets the time of day, to be lit for, and the place the scene ends in, whose picture goes along
    (M5); its description is written again from the finished scene (`media.notes`). The cover,
    the story's poster, is drawn from the premise instead, around the main character, never from
    the scene it is planned in (M1, `media.briefs.cover_brief`)."""
    look = look_for_story(story)
    if picture.kind is PictureKind.COVER:
        return cover_brief(state, look)
    subject_id = picture.subject_id
    if picture.kind is PictureKind.PORTRAIT and subject_id in state.characters:
        character = state.characters[subject_id]
        return Brief(
            description=picture.prompt,
            look=look,
            subject_name=character.name,
            subject_appearance=character.appearance or character.description,
            subject_age=character.age,
        )
    if picture.kind is PictureKind.PLACE and subject_id in state.places:
        place = state.places[subject_id]
        return Brief(
            description=picture.prompt,
            look=look,
            subject_name=place.name,
            subject_appearance=place_looks(place),
        )
    if trigger in THREAD_SUBJECTS:
        subject_id = None
    brief = Brief(
        description=picture.prompt,
        look=look,
        figures=scene_figures(state, picture.prompt, subject_id=subject_id),
        you=state.player.name,
        turn=state.turn,
    )
    if picture.kind is not PictureKind.SCENE:
        return brief  # a portrait or place whose subject is no longer on record
    place_id, place_name, place_look = scene_place(state)
    return replace(
        brief,
        time=time_of_day(state.bible.calendar, state.world_s),
        place_id=place_id,
        place_name=place_name,
        place_look=place_look,
    )


def _log(prepared: PreparedTurn, run: _Run, telemetry: TurnTelemetry) -> None:
    """T5's one line per turn, with how the action was entered (V7). Numbers, names and codes
    only: never the action, the narration or a prompt (T6)."""
    turn = prepared.input
    result = run.result
    throws = run.decided.throws if run.decided is not None else []
    fields: dict[str, Any] = {
        "turn": turn.ctx.turn,
        "kind": turn.kind.value,
        "input_mode": prepared.input_mode,
        "outcome": run.outcome,
        "sent": run.sent,
        # A3: numbers only. How many throws the turn had, how each fell and how many could kill.
        "resumed": prepared.resumed,
        "throws": len(throws),
        "marks": dict(Counter(throw.mark.value for throw in throws)),
        "deadly": sum(1 for throw in throws if throw.deadly),
        "duration_ms": int((time.monotonic() - run.started) * 1000),
        "first_text_ms": run.first_text_ms,
        "narration_mode": result.narration_mode if result else None,
        "issues": [issue.code for issue in result.issues] if result else [],
        "node_ms": dict(result.timings_ms) if result else {},
        # W10: how far the clock moved, and each step's kind and seconds, to tell a clock that
        # drifts from a model's short estimate.
        "world_s": result.scene.world_end_s - result.scene.world_start_s if result else None,
        "steps": [[s.kind.value if s.kind else None, s.duration_s] for s in result.resolution.steps]
        if result
        else [],
    } | telemetry.summary()
    logger.info("Turn %s", run.outcome, extra={"turn": fields})
