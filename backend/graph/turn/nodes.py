"""The seven nodes of the turn graph (B5), in the order they run.

1. `catch_up` (code): the world catches up on what fell due (W6, W10, B12).
2. `interpret` (model): the player's words become an `Intent`, checked in code (V3, R2, A9). A
   reading that would do what can't be taken back is read once more by the larger model (B8).
3. `resolve` (code): resolve, play out, direct and record the director's plan, then the plan is
   checked (A2, R6, W16, M1, C5). The decided steps go out at once, before the telling (A3).
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
from dataclasses import dataclass, replace
from functools import wraps
from typing import TYPE_CHECKING, Any

from engine import injuries, limits, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.context import Language
from engine.contracts import Intent, Resolution, SuggestionPlan
from engine.invariants import InvariantError, check_transition
from engine.labels import passage_label
from engine.pipeline import PlayOut
from engine.rng import SeededRng
from engine.state.records import OriginKind
from engine.state.world import Chapter, WorldState
from graph.llm import (
    Completed,
    LLMBlocked,
    LLMError,
    LLMUnavailable,
    ModelClient,
    Node,
    StreamRestart,
    TextDelta,
)
from graph.turn import check
from graph.turn import ending as ending_mod
from graph.turn.context import asks, chapter_prompt, interpret_prompt, narration_brief
from graph.turn.errors import EndingRefused, LimitReached, UnreadableAction
from graph.turn.form import intent_form
from graph.turn.outputs import ChapterOutput, NarratorOutput
from graph.turn.scene import details, scene_draft
from graph.turn.types import (
    CHAPTER_TURNS,
    MAX_CHAPTER_TURNS,
    Issue,
    NarrationDelta,
    NarrationReset,
    PastScene,
    Reading,
    StepsDecided,
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
    # What kind of change it was, such as "character.item", which holds no story text (T6).
    area = ".".join(part.split()[0] for part in (rejection.subject, rejection.change) if part)
    return Issue(code, rejection.reason, f"{rejection.subject}: {rejection.change}", area)


def _issues(state: TurnState, new: list[Issue]) -> list[Issue]:
    """Adds what a check found to the turn's issues and logs it. Details and subjects can hold
    story text, so only the code, and for a refused change its kind, is logged above DEBUG
    (T6)."""
    for issue in new:
        logged = {"code": issue.code} | ({"area": issue.area} if issue.area else {})
        logger.info("turn check: %s", issue.code, extra={"turn_issue": logged})
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
    passed since the last chapter: all of them, up to `MAX_CHAPTER_TURNS`."""
    last = max((c.to_turn for c in turn.state.chapters), default=0)
    saved = turn.state.turn
    if saved - last < CHAPTER_TURNS:
        return None
    to_turn = min(saved, last + MAX_CHAPTER_TURNS)
    scenes = [s for s in turn.scenes if last < s.turn <= to_turn]
    return last + 1, to_turn, scenes


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
                llm.structured(
                    Node.SUMMARIZER,
                    chapter_prompt(scenes, turn.ctx.settings.language),
                    ChapterOutput,
                )
            )
            runtime.context.tasks.append(task)
            update["chapter"] = PendingChapter(first, last, task)
        else:
            issues.append(Issue("chapter_skipped", "no scenes to summarize"))
    update["issues"] = _issues(state, issues)
    return update


async def read_action(
    llm: ModelClient, world: WorldState, action: str, language: Language, last_scene: str = ""
) -> check.CheckedIntent:
    """The player's words as the first model reads them where the story stands, checked in code
    (V3, B5). The form asks only what can apply to this turn, and the guide explains only that
    (`graph.turn.form`). A reading the model's filter stops raises `LLMBlocked`.

    A reading that would do something that can't be taken back on the model's word alone
    (`check.doubtful`) is read once more, by the larger model and from the same prompt, and that
    second reading stands (B8, W1). When it can't be had, the first one does: the player's turn
    never fails for the lack of it."""
    asked = asks(world)
    prompt = interpret_prompt(world, action, language, last_scene, asked)
    form = intent_form(asked)
    intent = await llm.structured(Node.INTERPRET, prompt, Intent, form=form)
    checked = check.check_intent(intent, world, action)
    doubt = check.doubtful(checked.intent, world)
    if doubt is None:
        return checked
    try:
        # A call this rare isn't worth a prompt cache of its own on the larger model.
        again = await llm.structured(
            Node.SECOND_READING, replace(prompt, stable_chars=0), Intent, form=form
        )
    except LLMError:
        checked.issues.append(_read_again(doubt, "unread", "the first reading stands"))
        return checked
    second = check.check_intent(again, world, action)
    if check.doubtful(second.intent, world) == doubt:
        second.issues.insert(0, _read_again(doubt, "confirmed", "both readings say so"))
    else:
        second.issues.insert(0, _read_again(doubt, "overturned", "the second reading stands"))
    return second


def _read_again(doubt: str, verdict: str, detail: str) -> Issue:
    # The doubt and what became of it hold no story text, so they are logged with the code (T6).
    return Issue(check.READ_AGAIN, detail, area=f"{doubt}.{verdict}")


@timed("interpret")
async def interpret(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 2: the player's words become an `Intent` (V3). A standing action needs no model, and
    the opening has no action. A blocked interpret call is the one block the player sees (F4)."""
    turn = state["input"]
    world = state["world"]
    if turn.reading is not None:
        # A3: this turn was decided and shown, so it is played out as it was read then. No
        # model reads the action again, since another reading could decide otherwise.
        return {"intent": turn.reading.intent, "overflow": list(turn.reading.overflow)}
    if turn.kind is TurnKind.OPENING or (turn.kind is TurnKind.END and not turn.action):
        # N6: an ending with no note is told from things as they stand.
        return {"intent": None}
    if turn.kind is TurnKind.STANDING:
        return {"intent": Intent(standing=turn.standing, summary=str(turn.standing))}
    action = turn.action or ""
    # R2: the scene the player is answering, so that what it showed counts as there.
    last_scene = turn.scenes[-1].narration if turn.scenes else ""
    try:
        checked = await read_action(
            runtime.context.llm, world, action, turn.ctx.settings.language, last_scene
        )
    except LLMBlocked as block:
        log_block("interpret", list(block.categories), stage=block.stage, source="model")
        raise UnreadableAction(categories=block.categories, stage=block.stage) from None
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
async def resolve(state: TurnState, runtime: Runtime[TurnDeps]) -> dict[str, Any]:
    """Step 3, all in code: resolve the steps, play them out on in-world time, let the director
    pick, and check the plan before anything is narrated (A2, R6, W10, W16, M1, C5). What it
    decided goes out at once, ahead of the story text (`StepsDecided`, A3)."""
    turn = state["input"]
    world = state["world"]
    intent = state.get("intent")
    read = intent  # as the interpret step read it, before an ending keeps only what it may
    rng = turn_rng(turn)
    issues: list[Issue] = []
    left_out: tuple[str, ...] = ()
    if turn.kind is TurnKind.END and intent is not None:
        # N6: an ending keeps only what the world allows of the note.
        kept, refused = ending_mod.earned(world, intent, turn.ctx, turn_rng(turn))
        if refused and not turn.drop_refused:
            raise EndingRefused(refused)
        intent = kept
        left_out = tuple(r.text for r in refused)
    if intent is None:
        played = PlayOut(state=world, resolution=Resolution())
    else:
        # A3: the scene the player is answering, which an advantage may quote.
        last_scene = turn.scenes[-1].narration if turn.scenes else ""
        resolution = pipeline.resolve(world, intent, turn.ctx, rng, scene=last_scene)
        resolution, found = check.check_resolution(resolution, state.get("overflow"))
        issues += found
        played = pipeline.play_out(world, resolution, turn.ctx, rng)
        issues += [_rejected("engine_rejected", r) for r in played.rejected]
        if played.capped:
            issues.append(Issue("events_capped", "a step hit the event cap"))
    # The director decides, then its records go in before anything is narrated, so the plan's
    # new threads and leads are in the state the check and the narrator see (W16, N1, N2).
    plan = pipeline.direct(played.state, played.resolution, turn.ctx, rng, intent=intent)
    ending = ending_mod.ending_of(turn.state, played.state, intent, played.resolution, turn.kind)
    if ending is not None:
        # N6: the protagonist's last scene ends on them, with no new event, picture or
        # suggestion to act on, no small thing of the moment and no talk of the place.
        plan = plan.model_copy(
            update={
                "event": None,
                "moment": None,
                "picture": None,
                "suggestions": SuggestionPlan(count=0),
                "talk": None,
            }
        )
    played = replace(played, state=pipeline.record_direction(played.state, plan, turn.ctx))
    plan, found = check.check_plan(played.state, plan, turn.ctx)
    issues += found
    if read is not None and played.resolution.steps:
        # A3, B7: the steps are decided, so the player can watch them before the telling.
        reading = Reading(intent=read, overflow=tuple(state.get("overflow") or ()))
        # W10: with the heading over a scene that hours or days passed in, as it will be saved.
        heading = passage_label(
            world.bible.calendar, world.world_s, played.state.world_s, turn.ctx.settings.language
        )
        runtime.stream_writer(StepsDecided(details(played.resolution), reading, heading))
    return {
        "intent": intent,
        "played": played,
        "resolution": played.resolution,
        "plan": plan,
        "ending": ending,
        "left_out": left_out,
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
        # R1: the player's own words, so the scene tells the action as they gave it. An ending's
        # note goes as its wish instead, and only when the world kept all of it (N6).
        words=turn.action if turn.kind in (TurnKind.ACTION, TurnKind.CHOICE) else None,
        ending=state.get("ending"),
        # The player's own words on how it ends, unless the world refused some of them: then the
        # narrator gets only what was kept, and what was left out, so it is never granted (N6).
        wish=turn.action if turn.kind is TurnKind.END and not state.get("left_out") else None,
        left_out=state.get("left_out", ()),
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

    def recipe(text: str) -> LLMBlocked | None:
        if limits.harm_instructions(text) is None:
            return None
        return LLMBlocked(
            node=Node.NARRATOR.value,
            categories=(limits.LimitCategory.HARM_INSTRUCTIONS.value,),
            streamed=shown,
        )

    async def tell(cutaway: bool) -> NarratorOutput:
        nonlocal shown
        # R1: the action, then what comes of it, streamed as one text (`NarratorOutput.text`).
        stream = llm.stream_structured(
            Node.NARRATOR,
            brief.prompt(cutaway=cutaway),
            NarratorOutput,
            field=("action", "narration"),
        )
        told = ""
        async with aclosing(stream) as events:
            async for event in events:
                if isinstance(event, TextDelta):
                    if event.text:
                        # Checked before each piece is sent, so a recipe stops at the piece
                        # that completes it and never reaches the player whole (F3).
                        told += event.text
                        if block := recipe(told):
                            raise block
                        shown = True
                        emit(NarrationDelta(event.text))
                elif isinstance(event, StreamRestart):
                    told = ""
                    if shown:
                        emit(NarrationReset("retry"))
                        shown = False
                elif isinstance(event, Completed):
                    if block := recipe(event.value.text):
                        raise block
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
    planned picture settled on the look the scene left (M5), the turn closed and the scene built.
    A refused change is logged and the rest still applies (C5 repairs the next scene). A template
    line proposes nothing."""
    turn = state["input"]
    narration: NarratorOutput = state["narration"]
    mode = state["narration_mode"]
    world = state["world"]
    issues: list[Issue] = []
    ended = False  # whether the narrator said where its scene ends
    scene_text = ""
    if mode != "template":
        issues += check.check_told(narration, state.get("intent"))
        # C10: what the engine moved this turn, so the scene doesn't move it again.
        moved = [
            t for t in world.transfers if t.turn == turn.ctx.turn and t.origin is OriginKind.ENGINE
        ]
        scene_text = f"{narration.action} {narration.narration}"
        delta, found = check.check_update(narration.update, world, moved, scene_text)
        if any(issue.code == check.REAL_ENTITY for issue in found):
            log_block(
                "narrator", [limits.LimitCategory.REAL_PERSON.value], stage="update", source="code"
            )
        issues += found
        # N6: the narrator records harm to the player character only where something recorded
        # this turn caused it: a power's toll in health or blood, or the first opening's premise.
        first_opening = turn.kind is TurnKind.OPENING and not turn.state.opening_due
        hurts = first_opening or injuries.pays_in_body(state["resolution"])
        applied = apply_delta(
            world,
            delta,
            turn.ctx,
            source=DeltaSource.NARRATOR,
            may_hurt_player=hurts,
            # N2: a goal closes only on a turn the player acted, never on an opening.
            player_acted=state.get("intent") is not None,
            # R2, R3: what the turn found stays on the scene's record.
            found=state["resolution"].found,
            # W4: the scene moves only the feelings of its own people and of whom the turn
            # reached; anyone else hears of it through the world.
            reached=pipeline.reached(world, state["resolution"], state["plan"]),
        )
        world = applied.state
        issues += [_rejected("rejected", r) for r in applied.rejected]
        ended = delta.scene_end is not None
        if narration.told_talk:
            # W2, C6: only talk a scene told is heard, so Memory never lists what no scene said.
            world = pipeline.hear_talk(world, state["plan"], turn.ctx, turn_rng(turn))
    # W10: the scene ends where the turn's trips left the character, and a trip over ground the
    # map didn't cover writes its route.
    world, moved_scene = pipeline.settle_trips(
        state["world"], world, state["resolution"], told=ended
    )
    issues += [Issue("trip_place", note) for note in moved_scene]
    # W11: code decides who runs, whatever the scene's end listed. Whoever set off to tell what
    # they saw has left the scene, and whoever hasn't yet is still in it.
    world, left, kept = pipeline.settle_witnesses(state["world"], world, turn.ctx.turn)
    issues += [Issue("witness_left", "set off to tell what they saw", subject=who) for who in left]
    issues += [
        Issue("witness_kept", "hasn't got away: still in the scene", subject=who) for who in kept
    ]
    # W10: code ends a fight, a chase or talks, never the telling: whoever is still in the
    # scene's encounter is still in the scene.
    world, stayed = pipeline.settle_encounter(state["world"], world)
    issues += [
        Issue("encounter_kept", "still in the encounter: still in the scene", subject=who)
        for who in stayed
    ]
    # G18, C6: what the scene told of a ladder is what the character knows of it. A rung it
    # named is heard of from now on, and one they had heard of is known once someone who shows
    # it has stood before them.
    world, rungs = pipeline.settle_path(world, scene_text)
    issues += [
        Issue("rung_known" if r.known else "rung_heard", "the scene told it", subject=r.ladder_id)
        for r in rungs
    ]
    # apply_delta stamps records with ctx.turn but leaves the turn counter to the graph.
    # N6: once told, a successor's opening is done.
    world = world.model_copy(update={"turn": turn.ctx.turn, "opening_due": False})
    # M4, M5: a scene that changed the look it pictures draws the new look.
    world, plan = pipeline.settle_picture(world, state["plan"])
    scene = scene_draft(
        turn,
        before=state["passage"].state,
        after=world,
        resolution=state["resolution"],
        plan=plan,
        narration=narration,
        mode=mode,
    )
    return {"world": world, "plan": plan, "scene": scene, "issues": _issues(state, issues)}


def _checked_chapter(chapter: ChapterOutput, issues: list[Issue]) -> ChapterOutput | None:
    """F3: a summary that reads as real-world working instructions is dropped, never kept. The
    summarizer runs with dangerous content off (C3), so code holds this line instead."""
    domain = limits.harm_instructions(chapter.summary)
    if domain is None:
        return chapter
    log_block(
        "summarizer",
        [limits.LimitCategory.HARM_INSTRUCTIONS.value],
        stage="response",
        source="code",
        domain=domain,
    )
    issues.append(Issue("chapter_skipped", limits.LimitCategory.HARM_INSTRUCTIONS.value))
    return None


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
            chapter: ChapterOutput | None = None
            try:
                chapter = pending.task.result()
            except LLMError as error:
                issues.append(Issue("chapter_skipped", error.code))
            else:
                chapter = _checked_chapter(chapter, issues)
            if chapter is not None:
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
        ending=state.get("ending"),
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
