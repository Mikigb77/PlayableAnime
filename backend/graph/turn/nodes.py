"""The seven nodes of the turn graph (B5), in the order they run.

1. `catch_up` (code): the world catches up on what fell due (W6, W10, B12).
2. `interpret` (model): the player's words become an `Intent`, checked in code (V3, R2, A9).
3. `resolve` (code): resolve, play out and direct, then the plan is checked (A2, R6, W16, M1, C5).
4. `build_context` (code): the narrator's brief (R3, C3).
5. `narrate` (model, streamed): the scene, with F4's cut-away and template fallbacks (S3, B7).
6. `apply_update` (code): the narrator's update applied and checked (C1), the scene built.
7. `after_turn`: the chapter summary every 20 turns (C3), the C1 check on the whole turn, and
   the result.

Steps 1 and 3 call `engine.pipeline`, so WS9, WS10 and WS11 plug in without touching the graph.
Model nodes propose; code nodes decide. Nothing here imports LangGraph at module load (B10): the
runtime is passed in.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any

from engine import limits, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.contracts import Intent, Resolution
from engine.invariants import InvariantError, check_transition
from engine.pipeline import PlayOut
from engine.rng import SeededRng
from engine.state.world import Chapter, WorldState
from graph.llm import (
    Completed,
    LLMBlocked,
    LLMError,
    LLMUnavailable,
    Node,
    StreamRestart,
    TextDelta,
)
from graph.turn import check
from graph.turn.context import chapter_prompt, interpret_prompt, narration_brief
from graph.turn.errors import LimitReached, UnreadableAction
from graph.turn.outputs import ChapterOutput, NarratorOutput
from graph.turn.scene import scene_draft
from graph.turn.types import (
    CHAPTER_TURNS,
    Issue,
    NarrationDelta,
    NarrationReset,
    PastScene,
    TurnDeps,
    TurnInput,
    TurnKind,
    TurnResult,
    TurnState,
)

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

logger = logging.getLogger("graph.turn")

# How long the turn waits, once its scene is written, for a chapter summary still running (C3).
# A late one is dropped and asked for again next turn.
CHAPTER_GRACE_S = 5.0

type NodeFn = Callable[..., Awaitable[dict[str, Any]]]


def timed(name: str) -> Callable[[NodeFn], NodeFn]:
    """Records how long a node took in `timings_ms`, for the turn's T5 log line."""

    def wrap(fn: NodeFn) -> NodeFn:
        @wraps(fn)
        async def node(state: TurnState, *args: Any, **kwargs: Any) -> dict[str, Any]:
            started = time.perf_counter()
            update = await fn(state, *args, **kwargs)
            timings = dict(state.get("timings_ms") or {})
            timings[name] = round((time.perf_counter() - started) * 1000)
            return {**update, "timings_ms": timings}

        return node

    return wrap


def turn_rng(turn: TurnInput) -> SeededRng:
    """One seeded stream per turn and timeline (A3). Each seam derives its own children with
    stable labels, so retrying a turn never rerolls."""
    return SeededRng.for_turn(turn.ctx.story_id, turn.state.timeline_id, turn.ctx.turn)


def _rejected(code: str, rejection: Any) -> Issue:
    return Issue(code, rejection.reason, f"{rejection.subject}: {rejection.change}")


def _issues(state: TurnState, new: list[Issue]) -> list[Issue]:
    """Adds what a check found to the turn's issues and logs it. Details and subjects can hold
    story text, so only the code is logged above DEBUG (T6)."""
    for issue in new:
        logger.info("turn check: %s", issue.code, extra={"turn_issue": {"code": issue.code}})
        logger.debug(
            "turn check detail: %s",
            issue.code,
            extra={
                "turn_issue": {"code": issue.code, "detail": issue.detail, "subject": issue.subject}
            },
        )
    return [*(state.get("issues") or []), *new]


def log_block(node: str, categories: list[str], *, stage: str, source: str, **extra: Any) -> None:
    """One line per block, with its category (F4): a model's safety filter (`source: model`) or
    a hard limit in code (`source: code`, `engine.limits`). Never with story text (T6)."""
    block = {"node": node, "source": source, "categories": categories, "stage": stage, **extra}
    logger.warning("%s blocked", node, extra={"block": block})


def _limit_detail(hits: list[limits.LimitHit]) -> None:
    """What the hits were about: names and words, so DEBUG only (T6)."""
    logger.debug(
        "limit detail",
        extra={
            "limit_hits": [
                {"category": h.category.value, "subject": h.subject, "detail": h.detail}
                for h in hits
            ]
        },
    )


@dataclass(frozen=True)
class PendingChapter:
    """A chapter summary running alongside the turn (C3)."""

    from_turn: int
    to_turn: int
    task: asyncio.Task[ChapterOutput]


def chapter_due(turn: TurnInput) -> tuple[int, int, list[PastScene]] | None:
    """The saved turns a new chapter covers, and their scenes, once `CHAPTER_TURNS` of them have
    passed since the last chapter."""
    last = max((c.to_turn for c in turn.state.chapters), default=0)
    saved = turn.state.turn
    if saved - last < CHAPTER_TURNS:
        return None
    scenes = [s for s in turn.scenes if last < s.turn <= saved]
    return last + 1, saved, scenes


@timed("catch_up")
async def catch_up(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 1: apply pending events due by now, in time order, and the world tick (W10, B12).

    It also starts the chapter summary step 7 waits for, once one is due, so the summary runs
    alongside the turn's other model calls instead of after them (B8).
    """
    turn = state["input"]
    passage = pipeline.catch_up(turn.state, turn.state.world_s, turn.ctx, turn_rng(turn))
    update: dict[str, Any] = {"passage": passage, "world": passage.state}
    issues: list[Issue] = []
    if passage.capped:
        issues.append(Issue("events_capped", "catch-up hit the event cap"))
    due = chapter_due(turn)
    if due is not None:
        first, last, scenes = due
        if scenes:
            llm = runtime.context.llm
            task = asyncio.create_task(
                llm.structured(Node.SUMMARIZER, chapter_prompt(scenes), ChapterOutput)
            )
            runtime.context.tasks.append(task)
            update["chapter"] = PendingChapter(first, last, task)
        else:
            issues.append(Issue("chapter_skipped", "no scenes to summarize"))
    update["issues"] = _issues(state, issues)
    return update


@timed("interpret")
async def interpret(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 2: the player's words become an `Intent` (V3). A standing action needs no model, and
    the opening has no action. A blocked interpret call is the one block the player sees (F4)."""
    turn = state["input"]
    world = state["world"]
    if turn.kind is TurnKind.OPENING:
        return {"intent": None}
    if turn.kind is TurnKind.STANDING:
        return {"intent": Intent(standing=turn.standing, summary=str(turn.standing))}
    action = turn.action or ""
    try:
        intent = await runtime.context.llm.structured(
            Node.INTERPRET, interpret_prompt(world, action), Intent
        )
    except LLMBlocked as block:
        log_block("interpret", list(block.categories), stage=block.stage, source="model")
        raise UnreadableAction(categories=block.categories) from None
    checked = check.check_intent(intent, world, action)
    # F3, G12, F2: a step over a hard limit never plays, so nothing is resolved or narrated.
    hits = limits.check_action(world, checked.intent, turn.ctx.rating)
    gravest = limits.gravest(hits)
    if gravest is not None:
        categories = list(dict.fromkeys(h.category.value for h in hits))
        log_block("interpret", categories, stage="action", source="code")
        _limit_detail(hits)
        raise LimitReached(gravest.category.value, limits.MESSAGES[gravest.category])
    return {
        "intent": checked.intent,
        "overflow": checked.overflow,
        "issues": _issues(state, checked.issues),
    }


@timed("resolve")
async def resolve(state: TurnState) -> dict[str, Any]:
    """Step 3, all in code: resolve the steps, play them out on in-world time, let the director
    pick, and check the plan before anything is narrated (A2, R6, W10, W16, M1, C5)."""
    turn = state["input"]
    world = state["world"]
    intent = state.get("intent")
    rng = turn_rng(turn)
    issues: list[Issue] = []
    if intent is None:
        played = PlayOut(state=world, resolution=Resolution())
    else:
        resolution = pipeline.resolve(world, intent, turn.ctx, rng)
        resolution, found = check.check_resolution(resolution, state.get("overflow"))
        issues += found
        played = pipeline.play_out(world, resolution, turn.ctx, rng)
        issues += [_rejected("engine_rejected", r) for r in played.rejected]
        if played.capped:
            issues.append(Issue("events_capped", "a step hit the event cap"))
    plan = pipeline.direct(played.state, played.resolution, turn.ctx, rng)
    plan, found = check.check_plan(played.state, plan, turn.ctx)
    issues += found
    return {
        "played": played,
        "resolution": played.resolution,
        "plan": plan,
        "world": played.state,
        "issues": _issues(state, issues),
    }


@timed("build_context")
async def build_context(state: TurnState) -> dict[str, Any]:
    """Step 4: the narrator's brief, from where the last scene ended (R3)."""
    turn = state["input"]
    played = state["played"]
    fired = (*state["passage"].fired, *played.fired)
    brief = narration_brief(
        before=state["passage"].state,
        after=played.state,
        ctx=turn.ctx,
        intent=state.get("intent"),
        resolution=state["resolution"],
        plan=state["plan"],
        fired=fired,
        scenes=turn.scenes,
        premise=turn.premise,
    )
    return {"brief": brief}


@timed("narrate")
async def narrate(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 5: the one large call on the critical path (B8), streamed as it is written (S3, B7).

    A blocked narration never blocks the deed (F4): it is retold as a cut-away, and if that is
    blocked or fails too, a neutral template line stands in. A narration that reads as working
    real-world instructions (F3, `engine.limits.harm_instructions`) counts as blocked. A
    narration that fails for any other reason, after the model layer's one retry, ends the turn
    with `llm_unavailable` (T7).
    """
    brief = state["brief"]
    llm = runtime.context.llm
    emit = runtime.stream_writer
    shown = False

    async def tell(cutaway: bool) -> NarratorOutput:
        nonlocal shown
        stream = llm.stream_structured(
            Node.NARRATOR, brief.prompt(cutaway=cutaway), NarratorOutput, field="narration"
        )
        async with aclosing(stream) as events:
            async for event in events:
                if isinstance(event, TextDelta):
                    if event.text:
                        shown = True
                        emit(NarrationDelta(event.text))
                elif isinstance(event, StreamRestart):
                    if shown:
                        emit(NarrationReset("retry"))
                        shown = False
                elif isinstance(event, Completed):
                    if limits.harm_instructions(event.value.narration) is not None:
                        raise LLMBlocked(
                            node=Node.NARRATOR.value,
                            categories=(limits.LimitCategory.HARM_INSTRUCTIONS.value,),
                            streamed=shown,
                        )
                    return event.value
        raise LLMUnavailable(node=Node.NARRATOR.value)

    def blocked(block: LLMBlocked, attempt: str) -> None:
        code = limits.LimitCategory.HARM_INSTRUCTIONS.value in block.categories
        log_block(
            "narrator",
            list(block.categories),
            stage=block.stage,
            source="code" if code else "model",
            attempt=attempt,
        )

    try:
        return {"narration": await tell(cutaway=False), "narration_mode": "full"}
    except LLMBlocked as block:
        blocked(block, "full")
    if shown:
        emit(NarrationReset("cutaway"))
        shown = False
    try:
        return {"narration": await tell(cutaway=True), "narration_mode": "cutaway"}
    except LLMBlocked as block:
        blocked(block, "cutaway")
    except LLMUnavailable:
        logger.warning("cut-away failed; using the template line")
    if shown:
        emit(NarrationReset("template"))
    line = brief.template_line()
    emit(NarrationDelta(line))
    return {"narration": NarratorOutput(narration=line), "narration_mode": "template"}


@timed("apply_update")
async def apply_update(state: TurnState) -> dict[str, Any]:
    """Step 6, code: the narrator's update applied with the C1 invariants by `engine.apply`, the
    turn closed and the scene built. A refused change is logged and the rest still applies (C5
    repairs the next scene). A template line proposes nothing."""
    turn = state["input"]
    narration: NarratorOutput = state["narration"]
    mode = state["narration_mode"]
    world = state["world"]
    issues: list[Issue] = []
    if mode != "template":
        delta, found = check.check_update(narration.update, world)
        if any(issue.code == check.REAL_ENTITY for issue in found):
            log_block(
                "narrator", [limits.LimitCategory.REAL_PERSON.value], stage="update", source="code"
            )
        issues += found
        applied = apply_delta(world, delta, turn.ctx, source=DeltaSource.NARRATOR)
        world = applied.state
        issues += [_rejected("rejected", r) for r in applied.rejected]
    # apply_delta stamps records with ctx.turn but leaves the turn counter to the graph.
    world = world.model_copy(update={"turn": turn.ctx.turn})
    scene = scene_draft(
        turn,
        before=state["passage"].state,
        after=world,
        resolution=state["resolution"],
        plan=state["plan"],
        narration=narration,
        mode=mode,
    )
    return {"world": world, "scene": scene, "issues": _issues(state, issues)}


@timed("after_turn")
async def after_turn(state: TurnState) -> dict[str, Any]:
    """Step 7: the chapter summary started in step 1 (C3), the C1 check on the whole turn, and the
    result.

    Everything finishes before the turn is saved, never after the response ends (B8). A summary
    that failed, or isn't ready `CHAPTER_GRACE_S` after the scene, is dropped and asked for again
    next turn. A turn whose first and last states break C1 is an engine bug: it raises
    `InvariantError` and nothing is saved.
    """
    turn = state["input"]
    world: WorldState = state["world"]
    issues: list[Issue] = []
    pending: PendingChapter | None = state.get("chapter")
    if pending is not None:
        done, _ = await asyncio.wait({pending.task}, timeout=CHAPTER_GRACE_S)
        if not done:
            pending.task.cancel()
            issues.append(Issue("chapter_late", "asked for again next turn"))
        else:
            try:
                chapter = pending.task.result()
            except LLMError as error:
                issues.append(Issue("chapter_skipped", error.code))
            else:
                world = world.model_copy(deep=True)
                world.chapters.append(
                    Chapter(
                        index=len(world.chapters) + 1,
                        from_turn=pending.from_turn,
                        to_turn=pending.to_turn,
                        summary=chapter.summary,
                    )
                )
    issues = _issues(state, issues)

    violations = check_transition(turn.state, world)
    if violations:
        logger.error(
            "turn broke C1",
            extra={"turn_violations": [{"subject": v.subject, "rule": v.rule} for v in violations]},
        )
        raise InvariantError(violations)

    result = TurnResult(
        state=world,
        scene=state["scene"],
        intent=state.get("intent"),
        resolution=state["resolution"],
        plan=state["plan"],
        fired=(*state["passage"].fired, *state["played"].fired),
        issues=tuple(issues),
    )
    return {"world": world, "result": result, "issues": issues}


NODES: tuple[tuple[str, NodeFn], ...] = (
    ("catch_up", catch_up),
    ("interpret", interpret),
    ("resolve", resolve),
    ("build_context", build_context),
    ("narrate", narrate),
    ("apply_update", apply_update),
    ("after_turn", after_turn),
)
