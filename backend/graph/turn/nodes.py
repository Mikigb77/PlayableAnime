"""The seven nodes of the turn graph (B5), in the order they run.

1. `catch_up` (code): the world catches up on what fell due (W6, W10, B12).
2. `interpret` (model): the player's words become an `Intent`, checked in code (V3, R2, A9).
3. `resolve` (code): resolve, play out and direct, then the plan is checked (A2, R6, W16, M1, C5).
4. `build_context` (code): the narrator's brief (R3, C3).
5. `narrate` (model, streamed): the scene, with F4's cut-away and template fallbacks (S3, B7).
6. `apply_update` (code): the narrator's update applied and checked (C1), the scene built.
7. `after_turn`: a chapter summary every 20 turns (C3), then the result.

Steps 1 and 3 call `engine.pipeline`, so WS9, WS10 and WS11 plug in without touching the graph.
Model nodes propose; code nodes decide. Nothing here imports LangGraph at module load (B10): the
runtime is passed in.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from functools import wraps
from typing import TYPE_CHECKING, Any

from engine import pipeline
from engine.contracts import Intent, Resolution
from engine.pipeline import PlayOut
from engine.rng import SeededRng
from engine.state.world import Chapter, WorldState
from graph.llm import Completed, LLMBlocked, LLMUnavailable, Node, StreamRestart, TextDelta
from graph.turn import check
from graph.turn.context import chapter_prompt, interpret_prompt, narration_brief
from graph.turn.errors import UnreadableAction
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
from graph.turn.update import apply_narration, close_turn

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

logger = logging.getLogger("graph.turn")

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


def _issues(state: TurnState, new: list[Issue]) -> list[Issue]:
    for issue in new:
        logger.info(
            "turn check: %s",
            issue.code,
            extra={
                "turn_issue": {"code": issue.code, "detail": issue.detail, "subject": issue.subject}
            },
        )
    return [*(state.get("issues") or []), *new]


@timed("catch_up")
async def catch_up(state: TurnState) -> dict[str, Any]:
    """Step 1: apply pending events due by now, in time order, and the world tick (W10, B12)."""
    turn = state["input"]
    passage = pipeline.catch_up(turn.state, turn.state.world_s, turn.ctx, turn_rng(turn))
    return {"passage": passage, "world": passage.state}


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
        logger.warning(
            "interpret blocked",
            extra={
                "block": {
                    "node": "interpret",
                    "categories": list(block.categories),
                    "stage": block.stage,
                }
            },
        )
        raise UnreadableAction(categories=block.categories) from None
    intent, issues = check.check_intent(intent, world, action)
    return {"intent": intent, "issues": _issues(state, issues)}


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
        resolution, found = check.check_resolution(resolution)
        issues += found
        played = pipeline.play_out(world, resolution, turn.ctx, rng)
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
    blocked or fails too, a neutral template line stands in. A narration that fails for any other
    reason, after the model layer's one retry, ends the turn with `llm_unavailable` (T7).
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
                    return event.value
        raise LLMUnavailable(node=Node.NARRATOR.value)

    def blocked(block: LLMBlocked, attempt: str) -> None:
        logger.warning(
            "narration blocked",
            extra={
                "block": {
                    "node": "narrator",
                    "attempt": attempt,
                    "categories": list(block.categories),
                    "stage": block.stage,
                }
            },
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
    """Step 6, code: the narrator's update applied with the invariants (C1), the turn closed and
    the scene built. A template line proposes nothing."""
    turn = state["input"]
    narration: NarratorOutput = state["narration"]
    mode = state["narration_mode"]
    world = state["world"]
    issues: list[Issue] = []
    if mode != "template":
        applied = apply_narration(world, narration.update, turn.ctx)
        world = applied.state
        issues += [
            Issue("rejected", r.reason, f"{r.subject}: {r.change}") for r in applied.rejected
        ]
    world = close_turn(world, turn.ctx)
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
async def after_turn(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 7: a chapter summary every 20 turns (C3), on the cheapest model (B8).

    It runs before the turn is saved, never after the response ends (B8), but after the whole
    narration has reached the player. A failed summary is skipped and tried again next turn.
    """
    turn = state["input"]
    world: WorldState = state["world"]
    scene = state["scene"]
    issues: list[Issue] = []
    last = max((c.to_turn for c in world.chapters), default=0)
    if turn.ctx.turn - last >= CHAPTER_TURNS:
        scenes = [s for s in turn.scenes if s.turn > last]
        scenes.append(PastScene(turn.ctx.turn, scene.narration, scene.player_action))
        try:
            chapter = await runtime.context.llm.structured(
                Node.SUMMARIZER, chapter_prompt(scenes), ChapterOutput
            )
        except (LLMBlocked, LLMUnavailable) as error:
            issues.append(Issue("chapter_skipped", type(error).__name__))
        else:
            world = world.model_copy(deep=True)
            world.chapters.append(
                Chapter(
                    index=len(world.chapters) + 1,
                    from_turn=last + 1,
                    to_turn=turn.ctx.turn,
                    summary=chapter.summary.strip(),
                )
            )
    issues = _issues(state, issues)
    result = TurnResult(
        state=world,
        scene=scene,
        intent=state.get("intent"),
        resolution=state["resolution"],
        plan=state["plan"],
        fired=(*state["passage"].fired, *state["played"].fired),
        issues=tuple(issues),
        timings_ms=dict(state.get("timings_ms") or {}),
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
