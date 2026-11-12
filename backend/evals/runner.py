"""Playing a scenario through the real turn graph (B5) and recording what it found.

    result = await run_scenario(scenario, Mode.DETERMINISTIC)
    result.passed  # every check held

A scenario script gets an `Eval`. It makes stories (`ev.story(world, seed=...)`), plays turns on
them (`await story.act("I farm", interpretation)`), and records checks on what code decided
(`ev.check(name, passed, detail)`). In live mode it also asks the judge about the telling
(`await ev.judge(...)`) and draws pictures (`await ev.draw(...)`).

Each turn is played the way the turn endpoint plays it (`stories.turns`): a `TurnInput` from the
story's state with its pending events, the scenes the next chapter and the narrator read, and the
story's settings, rating and the player's content preferences; then `graph.turn.run_turn`, whose
`TurnResult.state` the next turn starts from. Nothing touches the database: the world state
carries its own pending events (B12), and the endpoint's table only mirrors them.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable, Iterable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from engine.context import (
    ContentPrefs,
    Language,
    NarrationLength,
    Rating,
    StorySettings,
    TurnContext,
)
from engine.contracts import (
    DirectorPlan,
    Intent,
    IntentStep,
    PictureKind,
    PlannedEvent,
    Resolution,
    StandingAction,
    StepResolution,
)
from engine.invariants import check_state
from engine.labels import moment
from engine.state.records import PendingEvent
from engine.state.world import WorldState
from engine.tally import turn_tally
from evals.judge import (
    MILD_PICTURE,
    PICTURE_INSTRUCTIONS,
    Judgement,
    Rubric,
    SceneToJudge,
    judge_lines,
    judge_pictures,
    judge_scenes,
    judge_summary,
)
from evals.pictures import (
    NotDrawn,
    Picture,
    draw,
    ending,
    place_brief,
    portrait_brief,
    scene_brief,
)
from evals.scenario import Mode, Scenario
from evals.scripted import Line, Narration, ScriptedModel
from graph.llm import (
    LLMError,
    ModelClient,
    ModelConfig,
    Node,
    TurnTelemetry,
    build_client,
    get_model_config,
)
from graph.llm.telemetry import CallRecord
from graph.llm.types import Backend
from graph.turn import (
    MAX_CHAPTER_TURNS,
    WORN_SCENES,
    NarrationDelta,
    NarrationReset,
    PastScene,
    SceneDraft,
    StepsDecided,
    TurnCompleted,
    TurnInput,
    TurnKind,
    TurnResult,
    UnreadableAction,
    run_turn,
)
from graph.turn.errors import LimitReached
from graph.turn.nodes import read_action
from media.briefs import THREAD_SUBJECTS
from media.notes import SceneText

if TYPE_CHECKING:
    from graph.drafting.chain import Draft, Target

# How much of a missed criterion a failure line repeats before the judge's reason.
CRITERION_CHARS = 80
# How much of a refused turn's action a failed scenario's line shows.
ACTION_CHARS = 80
# How many failures a check keeps the details of. The count covers them all.
KEPT_DETAILS = 5


# No script plays more turns than this in one story: a loop waiting on something a live model
# never does stops here instead of spending without end.
MAX_TURNS = 400


class RunawayStory(RuntimeError):
    """A story played more than `MAX_TURNS` turns."""


class NotAsScripted(Exception):
    """A turn didn't take the shape the script reads: refused, or fewer steps. In live mode that
    is the model's reading of the player's words, and fails the scenario's run with the reason;
    in deterministic mode it is a bug in the script."""


class LiveUnavailable(RuntimeError):
    """Live mode needs the real models: `LLM_PROVIDER=vertex` with Vertex AI access."""


@dataclass(frozen=True)
class Models:
    """Where live mode's model calls go. `backend` and `judge_backend` stand in for Vertex AI in
    tests, so CI can show that every live scenario runs without spending anything."""

    config: ModelConfig | None = None
    backend: Backend | None = None
    judge_backend: Backend | None = None

    def resolved(self) -> ModelConfig:
        return self.config or get_model_config()

    def require_live(self) -> None:
        if self.backend is None and self.resolved().provider != "vertex":
            raise LiveUnavailable(
                "Live evals call the real models: set LLM_PROVIDER=vertex, GCP_PROJECT and "
                "Application Default Credentials (docs/ARCHITECTURE.md, Evals)."
            )

    def client(self, rating: str, recorder: TurnTelemetry) -> ModelClient:
        return build_client(
            rating=rating,  # type: ignore[arg-type]
            recorder=recorder,
            config=self.resolved(),
            backend=self.backend,
        )

    def judge_client(self, recorder: TurnTelemetry) -> ModelClient:
        # The judge reads Mature scenes, so it gets the Mature safety settings (F5).
        return build_client(
            rating="mature",
            recorder=recorder,
            config=self.resolved(),
            backend=self.judge_backend or self.backend,
        )

    def models_used(self) -> dict[str, str]:
        config = self.resolved()
        return {node.value: config.node(node).model for node in Node}

    def thinking_used(self) -> dict[str, str]:
        """How hard each step that takes the setting is told to think (B6)."""
        config = self.resolved()
        levels = {node.value: config.node(node).options.thinking for node in Node}
        return {node: level for node, level in levels.items() if level}


# --- turns -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Played:
    """One turn as the scenario saw it: the finished turn, or the refusal that ended it (F3, F4)."""

    turn: int
    kind: TurnKind
    action: str | None
    before: WorldState
    result: TurnResult | None
    refused: UnreadableAction | None
    calls: tuple[CallRecord, ...]
    streamed: str
    resets: tuple[str, ...]
    seconds: float
    # A3: what the engine decided, as it went out, and whether any of the telling got out first.
    decided: StepsDecided | None = None
    told_first: bool = False

    @property
    def completed(self) -> bool:
        return self.result is not None

    def _result(self) -> TurnResult:
        if self.result is None:
            raise NotAsScripted(f"turn {self.turn} was refused: {self.refused!r}")
        return self.result

    def step(self, index: int) -> StepResolution:
        """The settled step at `index` (negative counts from the end). A live interpret step
        that read the action as fewer steps than the script needs raises `NotAsScripted`."""
        steps = self.steps
        if not -len(steps) <= index < len(steps):
            raise NotAsScripted(
                f"turn {self.turn} ({self.action!r}) played {len(steps)} steps; the script reads "
                f"step {index}"
            )
        return steps[index]

    @property
    def state(self) -> WorldState:
        return self.result.state if self.result is not None else self.before

    @property
    def plan(self) -> DirectorPlan:
        return self._result().plan

    @property
    def resolution(self) -> Resolution:
        return self._result().resolution

    @property
    def steps(self) -> list[StepResolution]:
        return self._result().resolution.steps

    @property
    def scene(self) -> SceneDraft:
        return self._result().scene

    @property
    def narration(self) -> str:
        return self.result.scene.narration if self.result is not None else ""

    @property
    def event(self) -> PlannedEvent | None:
        return self.result.plan.event if self.result is not None else None

    @property
    def fired(self) -> tuple[PendingEvent, ...]:
        """The pending events that fired during the turn (B12), in time order."""
        return self.result.fired if self.result is not None else ()

    @property
    def issues(self) -> list[str]:
        return [issue.code for issue in self.result.issues] if self.result is not None else []

    @property
    def cost_usd(self) -> Decimal:
        return sum((c.cost_usd for c in self.calls), Decimal(0))

    @property
    def world_seconds(self) -> int:
        return self.state.world_s - self.before.world_s

    @property
    def tally(self) -> dict[str, int]:
        """T5: what the turn's log line counts about the logic of play, for a turn that
        finished."""
        if self.result is None:
            return {}
        result = self.result
        return turn_tally(self.before, result.state, result.resolution, result.plan)

    def outcome(self) -> dict[str, Any]:
        """What code decided, in short, for the judge and the transcript."""
        if self.result is None:
            return {}
        resolution = self.result.resolution
        outcome: dict[str, Any] = {
            "steps": [
                {
                    "step": s.text,
                    "class": s.outcome_class.value,
                    "result": s.result.value,
                    "why": s.reason,
                }
                for s in resolution.steps
            ]
        }
        if resolution.unplayed:
            outcome["unplayed"] = resolution.unplayed
        if self.result.plan.event is not None:
            outcome["event"] = self.result.plan.event.title
        # W10: when the scene began and ended on the world's clock, to the minute whatever the
        # calendar shows, so the telling can be scored against it.
        calendar = self.result.state.bible.calendar
        outcome["clock"] = {
            "from": moment(calendar, self.before.world_s).model_dump(),
            "to": moment(calendar, self.result.state.world_s).model_dump(),
        }
        return outcome

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "turn": self.turn,
            "kind": self.kind.value,
            "action": self.action,
            "seconds": round(self.seconds, 3),
            "cost_usd": float(self.cost_usd),
        }
        if self.refused is not None:
            data["refused"] = {
                "code": self.refused.code,
                "categories": list(self.refused.categories),
                # A hard limit of the engine's, or the model's own filter and where it struck.
                "by": "code" if isinstance(self.refused, LimitReached) else "model",
                "stage": self.refused.stage,
            }
            return data
        result = self._result()
        data |= {
            "narration_mode": result.narration_mode,
            "narration": result.scene.narration,
            "outcome": self.outcome(),
            "event": result.plan.event.title if result.plan.event else None,
            "picture": result.scene.picture.model_dump(mode="json")
            if result.scene.picture
            else None,
            "world_seconds": self.world_seconds,
            "issues": self.issues,
            "tally": self.tally,
        }
        return data


# T5: what a run's report adds up of each turn's counts. The goals still open are where a story
# stands, not something to add up.
LOGIC = (
    "refused",
    "moves_refused",
    "searches",
    "searches_empty",
    "rumors_heard",
    "rumors_unvoiced",
)


def counted(turns: Iterable[Played]) -> dict[str, int]:
    """What the turns that finished counted about the logic of play, added up, with the steps
    the engine settled in them. Empty when none finished."""
    done = [played for played in turns if played.result is not None]
    if not done:
        return {}
    tallies = [played.tally for played in done]
    return {"steps": sum(len(played.steps) for played in done)} | {
        key: sum(tally[key] for tally in tallies) for key in LOGIC
    }


@dataclass(frozen=True)
class Read:
    """One line as the first model read it where a story stands (V3, B5), with no turn played:
    the intent a turn would go on to play, or why there is none (the model's filter stopped it,
    or it didn't answer in time)."""

    action: str
    intent: Intent | None
    failed: str
    calls: tuple[CallRecord, ...]
    seconds: float

    @property
    def steps(self) -> list[IntentStep]:
        return self.intent.steps if self.intent is not None else []


@dataclass(frozen=True)
class Use:
    """What one model step came to over a scenario's stories (T5, K8): how often it was called,
    on which model, and the tokens, the time and the money of it. Tokens out include thinking,
    and cached tokens are part of the tokens in, as the provider counts them."""

    node: str
    model: str
    calls: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    retries: int = 0
    failed: int = 0
    cost_usd: Decimal = Decimal(0)

    @classmethod
    def of(cls, calls: Iterable[CallRecord]) -> list[Use]:
        """The calls by step and model, in the order each first ran."""
        return merged(
            cls(
                node=c.node,
                model=c.model,
                calls=1,
                input_tokens=c.input_tokens,
                cached_tokens=c.cached_tokens,
                output_tokens=c.output_tokens,
                thinking_tokens=c.thinking_tokens,
                latency_ms=c.latency_ms,
                retries=c.retries,
                failed=int(c.outcome != "ok"),
                cost_usd=c.cost_usd,
            )
            for c in calls
        )

    def plus(self, other: Use) -> Use:
        return Use(
            self.node,
            self.model,
            self.calls + other.calls,
            self.input_tokens + other.input_tokens,
            self.cached_tokens + other.cached_tokens,
            self.output_tokens + other.output_tokens,
            self.thinking_tokens + other.thinking_tokens,
            self.latency_ms + other.latency_ms,
            self.retries + other.retries,
            self.failed + other.failed,
            self.cost_usd + other.cost_usd,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "model": self.model,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens,
            "latency_ms": self.latency_ms,
            "retries": self.retries,
            "failed": self.failed,
            "cost_usd": float(self.cost_usd),
        }


def merged(uses: Iterable[Use]) -> list[Use]:
    """One line per step and model, in the order each first appears."""
    by_step: dict[tuple[str, str], Use] = {}
    for use in uses:
        key = (use.node, use.model)
        by_step[key] = by_step[key].plus(use) if key in by_step else use
    return list(by_step.values())


class Story:
    """A story played turn after turn, each from the state the last one left."""

    def __init__(
        self,
        ev: Eval,
        world: WorldState,
        *,
        seed: str,
        rating: Rating,
        settings: StorySettings,
        prefs: ContentPrefs,
        premise: str,
        label: str,
    ) -> None:
        problems = check_state(world)
        if problems:
            raise ValueError(f"The scenario's world breaks C1: {problems}")
        self.ev = ev
        self.state = world
        self.seed = seed
        self.rating = rating
        self.settings = settings
        self.prefs = prefs
        self.premise = premise
        self.label = label
        self.turns: list[Played] = []
        self.scenes: list[PastScene] = []
        self.telemetry = TurnTelemetry()
        self._scripted: ScriptedModel | None = None
        if ev.live:
            self.client = ev.models.client(rating.value, self.telemetry)
        else:
            self._scripted = ScriptedModel(settings.narration_length or NarrationLength.MEDIUM)
            self.client = ModelClient(
                self._scripted.backend,
                ModelConfig(),
                rating=rating.value,
                recorder=self.telemetry,
                retry_delay_s=0,
            )

    @property
    def last(self) -> Played:
        return self.turns[-1]

    def prompt(self, node: Node) -> str:
        """The last prompt `node` was sent (deterministic mode), for checking what code put in
        front of the model; empty in live mode, where checks read the telling instead."""
        return self._scripted.prompts.get(node, "") if self._scripted is not None else ""

    def fired(self, kind: str | None = None, **payload: Any) -> list[PendingEvent]:
        """Every pending event that fired in the story so far, of `kind` and with `payload`."""
        return [
            event
            for played in self.turns
            for event in played.fired
            if (kind is None or event.kind == kind)
            and all(event.payload.get(k) == v for k, v in payload.items())
        ]

    def change(self, edit: Callable[[WorldState], Any]) -> WorldState:
        """Changes the world between turns, as the scenario's setup says (a trap springs, a
        witness is planted). The change must leave a valid world (C1)."""
        state = self.state.model_copy(deep=True)
        edit(state)
        problems = check_state(state)
        if problems:
            raise ValueError(f"The scenario's change breaks C1: {problems}")
        self.state = state
        return state

    async def open(self, *, narration: Narration | Iterable[Narration] | None = None) -> Played:
        """The opening turn, which every story plays before the player acts."""
        return await self._play(TurnKind.OPENING, None, None, narration=narration)

    async def act(
        self,
        action: str,
        interpretation: Intent | None = None,
        *,
        narration: Narration | Iterable[Narration] | None = None,
    ) -> Played:
        """The player's action. Deterministic mode feeds `interpretation` to the interpret node;
        live mode lets the interpret model read `action`."""
        return await self._play(TurnKind.ACTION, action, interpretation, narration=narration)

    async def choose(
        self,
        choice: int = 0,
        interpretation: Intent | None = None,
        *,
        narration: Narration | Iterable[Narration] | None = None,
    ) -> Played:
        """Picks a suggestion from the last scene, by position."""
        label = self.last.scene.choices[choice].label
        return await self._play(TurnKind.CHOICE, label, interpretation, narration=narration)

    async def stand(
        self,
        standing: StandingAction = StandingAction.WAIT,
        *,
        narration: Narration | Iterable[Narration] | None = None,
    ) -> Played:
        """Wait or observe (S2): no model reads it."""
        return await self._play(
            TurnKind.STANDING, None, None, narration=narration, standing=standing
        )

    async def read(self, action: str, interpretation: Intent | None = None) -> Read:
        """Only the first model's step on `action` (V3, B5): the player's words read where the
        story stands and checked as a turn checks them (`graph.turn.nodes.read_action`). No turn
        is played and nothing moves, so a scenario about the reading alone pays for no telling.
        A line the model's filter stops, or doesn't answer in time, is a line it didn't read."""
        if self._scripted is not None:
            self._scripted.line = Line.of(self.state.turn + 1, action, interpretation, None)
        calls_before = len(self.telemetry.calls)
        last_scene = self.scenes[-1].narration if self.scenes else ""
        intent, failed = None, ""
        started = time.perf_counter()
        try:
            checked = await read_action(
                self.client, self.state, action, self.settings.language, last_scene
            )
            intent = checked.intent
        except LLMError as error:
            failed = error.code
        return Read(
            action=action,
            intent=intent,
            failed=failed,
            calls=tuple(self.telemetry.calls[calls_before:]),
            seconds=time.perf_counter() - started,
        )

    def _past_scenes(self) -> tuple[PastScene, ...]:
        """As the endpoint reads them: those the next chapter covers, and the latest dozen."""
        last_chapter = max((c.to_turn for c in self.state.chapters), default=0)
        latest = self.state.turn - WORN_SCENES
        return tuple(
            s
            for s in self.scenes
            if (last_chapter < s.turn <= last_chapter + MAX_CHAPTER_TURNS) or s.turn > latest
        )

    async def _play(
        self,
        kind: TurnKind,
        action: str | None,
        interpretation: Intent | None,
        *,
        narration: Narration | Iterable[Narration] | None = None,
        standing: StandingAction | None = None,
    ) -> Played:
        if len(self.turns) >= MAX_TURNS:
            raise RunawayStory(f"{self.label or self.seed} played {MAX_TURNS} turns")
        before = self.state
        ctx = TurnContext(
            story_id=self.seed,
            turn=before.turn + 1,
            settings=self.settings,
            rating=self.rating,
            content_prefs=self.prefs,
        )
        turn = TurnInput(
            state=before,
            ctx=ctx,
            kind=kind,
            action=action,
            standing=standing,
            premise=self.premise,
            scenes=self._past_scenes(),
        )
        if self._scripted is not None:
            self._scripted.line = Line.of(ctx.turn, action, interpretation, narration)
        calls_before = len(self.telemetry.calls)
        streamed, resets = "", []
        decided: StepsDecided | None = None
        told_first = False
        result: TurnResult | None = None
        refused: UnreadableAction | None = None
        started = time.perf_counter()
        try:
            async with aclosing(run_turn(turn, self.client)) as events:
                async for event in events:
                    if isinstance(event, NarrationDelta):
                        streamed += event.text
                    elif isinstance(event, NarrationReset):
                        streamed = ""
                        resets.append(event.reason)
                    elif isinstance(event, StepsDecided):
                        decided, told_first = event, bool(streamed or resets)
                    elif isinstance(event, TurnCompleted):
                        result = event.result
        except UnreadableAction as error:
            refused = error
        played = Played(
            turn=ctx.turn,
            kind=kind,
            action=action,
            before=before,
            result=result,
            refused=refused,
            calls=tuple(self.telemetry.calls[calls_before:]),
            streamed=streamed,
            resets=tuple(resets),
            seconds=time.perf_counter() - started,
            decided=decided,
            told_first=told_first,
        )
        self.turns.append(played)
        self.ev._turn_played(self, played)
        if result is not None:
            self.state = result.state
            scene = result.scene
            self.scenes.append(PastScene(scene.turn, scene.narration, scene.player_action))
        return played


# --- an eval run -------------------------------------------------------------------------------


@dataclass
class Tally:
    """A check, counted over every time the script made it.

    A check with a `gap` is a requirement the engine is known not to meet yet: it is expected to
    fail, and its failures are reported without failing the run. Once it holds, a deterministic
    run fails until the marker is taken off, so a fixed gap becomes a plain check (as pytest's
    strict xfail does). A live run plays a seed or two of whatever the models write, so a gap that
    happens to hold there proves nothing and fails nothing (`strict` is off)."""

    name: str
    live: bool = True
    gap: str = ""
    strict: bool = True
    passed: int = 0
    failed: int = 0
    details: list[str] = field(default_factory=list)

    @property
    def held(self) -> bool:
        return self.failed == 0 and self.passed > 0

    @property
    def ok(self) -> bool:
        if self.gap:
            return self.failed > 0 or not self.strict
        return self.held

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "passed": self.passed,
            "failed": self.failed,
            "details": self.details,
        }
        if self.gap:
            data["gap"] = self.gap
        return data


@dataclass
class ScenarioResult:
    id: str
    suite: str
    title: str
    mode: Mode
    status: str  # passed, failed, error, pending, skipped
    seconds: float = 0.0
    turns: int = 0
    cost_usd: Decimal = Decimal(0)
    checks: list[Tally] = field(default_factory=list)
    judged: list[Judgement] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    pictures: list[Picture | NotDrawn] = field(default_factory=list)
    transcripts: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    waits_for: str = ""
    # What the stories' own model steps came to, and of that what the turns played cost: the
    # judge and the pictures are the eval's, never a turn's.
    use: list[Use] = field(default_factory=list)
    turn_cost_usd: Decimal = Decimal(0)
    # T5: what the scenario's turns counted about the logic of play (`counted`).
    logic: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def score(self) -> float | None:
        """The share of checks and judged rubrics that held, for tracking over time."""
        total = sum(t.passed + t.failed for t in self.checks) + len(self.judged)
        if not total:
            return None
        held = sum(t.passed for t in self.checks) + sum(1 for j in self.judged if j.passed)
        return round(held / total, 4)

    def failures(self) -> list[str]:
        lines = []
        if self.error:
            lines.append(f"error: {self.error.splitlines()[-1] if self.error else ''}")
        for tally in self.checks:
            if tally.ok:
                continue
            if tally.gap and tally.held:
                lines.append(
                    f"{tally.name}: the known gap is closed ({tally.gap}); make it a plain check"
                )
                continue
            shown = "; ".join(tally.details[:KEPT_DETAILS]) or "never checked"
            total = tally.passed + tally.failed
            lines.append(f"{tally.name}: {tally.failed} failed of {total}: {shown}")
        for judgement in self.judged:
            if judgement.passed:
                continue
            if judgement.error or not judgement.verdicts:
                lines.append(f"judge {judgement.name}: {judgement.error or 'nothing judged'}")
                continue
            # One line per criterion missed, with the judge's own reason, so a run's log says
            # what the judge saw without its artifact (T18).
            for v in judgement.verdicts:
                if not v.passed:
                    lines.append(
                        f"judge {judgement.name}: {v.id} ({_clip(v.criterion, CRITERION_CHARS)}) "
                        f"failed: {' '.join(v.reason.split()) or 'no reason given'}"
                    )
            # The rows a judge of lines read (S10), which the reasons above only point at. Eval
            # stories are made up, so they can be printed.
            rows = judgement.subject.get("lines") or []
            if rows:
                read = " | ".join(f"{was} => {said}" for was, said in rows)
                lines.append(f"judge {judgement.name} read: {read}")
            # And the summary a judge of a draft read, against the premise it was drafted from
            # (G1).
            summary = judgement.subject.get("summary") or []
            if summary:
                premise = judgement.subject.get("premise", "")
                lines.append(f"judge {judgement.name} read: {premise} => {' | '.join(summary)}")
        if lines:
            lines += self._refusals()
        return lines

    def _refusals(self) -> list[str]:
        """The turns of a live run that were refused, with who refused them and why, for a
        scenario that failed: a story whose first action can't be read fails every check after
        it, and the run's log is all that can be read of it afterwards (T18)."""
        lines = []
        for story in self.transcripts:
            for turn in story["turns"]:
                refused = turn.get("refused")
                if refused is None:
                    continue
                where = f" at the {refused['stage']}" if refused.get("stage") else ""
                lines.append(
                    f"refused: {story['seed']} t{turn['turn']} "
                    f"({_clip(turn.get('action') or '', ACTION_CHARS)}): {refused['code']} by "
                    f"{refused.get('by', 'model')}{where}, categories {refused['categories']}"
                )
        return lines

    def gaps(self) -> list[str]:
        """The known gaps this run still found open."""
        return [f"{t.name}: {t.gap}" for t in self.checks if t.gap and not t.held]

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "suite": self.suite,
            "title": self.title,
            "mode": self.mode.value,
            "status": self.status,
            "score": self.score,
            "seconds": round(self.seconds, 3),
            "turns": self.turns,
            "cost_usd": float(self.cost_usd),
            "turn_cost_usd": float(self.turn_cost_usd),
            "use": [u.to_json() for u in self.use],
            "logic": self.logic,
            "checks": [t.to_json() for t in self.checks],
            "judged": [j.to_json() for j in self.judged],
            "metrics": self.metrics,
            "pictures": [
                {"name": p.name, "kind": p.kind, "model": p.model, "bytes": len(p.data)}
                if isinstance(p, Picture)
                else {"name": p.name, "not_drawn": p.reason}
                for p in self.pictures
            ],
        }
        if self.error:
            data["error"] = self.error
        if self.waits_for:
            data["waits_for"] = self.waits_for
        return data


class Eval:
    """One scenario's run: its stories, checks, judgements, pictures and metrics."""

    def __init__(self, scenario: Scenario, mode: Mode, models: Models | None = None) -> None:
        self.scenario = scenario
        self.mode = mode
        self.models = models or Models()
        self.stories: list[Story] = []
        self.tallies: dict[str, Tally] = {}
        self.judged: list[Judgement] = []
        self.pictures: list[Picture | NotDrawn] = []
        self.metrics: dict[str, Any] = {}
        self.judge_telemetry = TurnTelemetry()
        # Live pictures' calls, so their spend counts in the scenario's cost.
        self.picture_telemetry = TurnTelemetry()
        self.turns = 0
        self._judge: ModelClient | None = None

    @property
    def live(self) -> bool:
        return self.mode is Mode.LIVE

    def seeds(self, deterministic: int, live: int = 1) -> list[str]:
        """Story ids for a run over many seeds (A3: the story id seeds every roll). Live mode
        plays fewer, because each costs real model calls."""
        count = live if self.live else deterministic
        return [f"{self.scenario.id}/{n}" for n in range(count)]

    def story(
        self,
        world: WorldState,
        *,
        seed: str | None = None,
        rating: Rating = Rating.TEEN,
        settings: StorySettings | None = None,
        prefs: ContentPrefs | None = None,
        premise: str = "",
        label: str = "",
        under_way: bool = False,
    ) -> Story:
        """A story on `world`. Play its opening first (`await story.open()`), or pass
        `under_way` for a story whose opening was played before the scenario picks it up, as a
        scenario over hundreds of seeds does to halve its turns."""
        if under_way and world.turn == 0:
            world = world.model_copy(update={"turn": 1})
        story = Story(
            self,
            world,
            seed=seed or f"{self.scenario.id}/0",
            rating=rating,
            settings=settings or StorySettings(),
            prefs=prefs or ContentPrefs(),
            premise=premise,
            label=label,
        )
        self.stories.append(story)
        return story

    def check(
        self, name: str, passed: bool, detail: str = "", *, live: bool = True, gap: str = ""
    ) -> bool:
        """Records one check of what code decided. `live=False` keeps a check out of live mode,
        for one whose truth depends on the scripted interpretation or on many seeds. `gap` marks
        a requirement the engine is known not to meet yet, saying what is missing (see
        `Tally`)."""
        tally = self.tallies.setdefault(name, Tally(name, live=live, gap=gap, strict=not self.live))
        if self.live and not tally.live:
            return passed
        if passed:
            tally.passed += 1
        else:
            tally.failed += 1
            if len(tally.details) < KEPT_DETAILS and detail:
                tally.details.append(detail)
        return passed

    def metric(self, name: str, value: Any) -> None:
        self.metrics[name] = value

    def _turn_played(self, story: Story, played: Played) -> None:
        self.turns += 1

    # Live mode: the judge and pictures. In deterministic mode these are no-ops, so one script
    # serves both modes.

    def judge_client(self) -> ModelClient:
        if self._judge is None:
            self._judge = self.models.judge_client(self.judge_telemetry)
        return self._judge

    async def judge(
        self,
        name: str,
        rubric: Rubric,
        scenes: Played | Sequence[Played] | Sequence[tuple[str, Played]],
        *,
        context: str = "",
        rating: Rating | None = None,
    ) -> Judgement | None:
        """Scores the telling of `scenes` against `rubric` (live mode only). Pass `(label,
        played)` pairs to set scenes from different stories side by side."""
        if not self.live:
            return None
        items = [scenes] if isinstance(scenes, Played) else list(scenes)
        to_judge = []
        for item in items:
            label, played = item if isinstance(item, tuple) else ("", item)
            if played.result is None:
                continue
            to_judge.append(SceneToJudge(played.action, played.narration, played.outcome(), label))
        shown_rating = rating or (self.stories[-1].rating if self.stories else Rating.TEEN)
        judgement = await judge_scenes(
            self.judge_client(),
            name,
            rubric,
            to_judge,
            rating=shown_rating.value,
            context=context,
        )
        judgement = Judgement(
            judgement.name,
            judgement.verdicts,
            judgement.error,
            {"turns": [p.turn for _, p in (i if isinstance(i, tuple) else ("", i) for i in items)]},
        )
        self.judged.append(judgement)
        return judgement

    async def judge_lines(
        self, name: str, rubric: Rubric, pairs: Sequence[tuple[str, str]], *, language: str
    ) -> Judgement | None:
        """Scores how the engine's lines were said in a story's language (S10, live mode only).
        `pairs` are (the English line, how it was said)."""
        if not self.live:
            return None
        judgement = await judge_lines(self.judge_client(), name, rubric, pairs, language=language)
        # Kept with the judgement, so a failed run's log shows the lines the judge read.
        judgement = replace(judgement, subject={"lines": [list(pair) for pair in pairs]})
        self.judged.append(judgement)
        return judgement

    async def judge_summary(
        self, name: str, rubric: Rubric, premise: str, lines: Sequence[str]
    ) -> Judgement | None:
        """Scores the summary a draft shows of its world against the premise it was drafted
        from (G1, live mode only)."""
        if not self.live:
            return None
        judgement = await judge_summary(self.judge_client(), name, rubric, premise, lines)
        # Kept with the judgement, so a failed run's log shows the summary the judge read.
        judgement = replace(judgement, subject={"premise": premise, "summary": list(lines)})
        self.judged.append(judgement)
        return judgement

    async def judge_pictures(
        self,
        name: str,
        rubric: Rubric,
        images: Sequence[tuple[str, Picture]],
        *,
        context: str = "",
    ) -> Judgement | None:
        if not self.live:
            return None
        judgement = await judge_pictures(
            self.judge_client(),
            name,
            rubric,
            [(caption, p.data, p.mime_type) for caption, p in images],
            context=context,
        )
        self.judged.append(judgement)
        return judgement

    async def judge_mild(self, name: str, picture: Picture | NotDrawn | None) -> None:
        """M6: a picture shows nothing sexual and no more than mild gore. A picture the model
        refused to draw is mild by definition, and is recorded as such."""
        if not self.live or picture is None:
            return
        if isinstance(picture, NotDrawn):
            self.check("picture drawn or refused by its filter", picture.reason == "blocked")
            return
        rubric = Rubric(must=(MILD_PICTURE,), instructions=PICTURE_INSTRUCTIONS)
        await self.judge_pictures(name, rubric, [("the picture", picture)])

    def picture_model(self, story: Story):
        from media.drawing import GraphPictureModel

        client = self.models.client(story.rating.value, self.picture_telemetry)
        model = self.models.resolved().node(Node.PICTURE).model
        return GraphPictureModel(client, self.picture_telemetry, model)

    async def draw_portrait(
        self, story: Story, character_id: str, name: str = ""
    ) -> Picture | None:
        """A character's portrait (M1, M5), as the picture endpoint draws one. Live mode only."""
        if not self.live:
            return None
        brief = portrait_brief(story.state, character_id)
        drawn = await draw(
            self.picture_model(story), name or f"portrait-{character_id}", "portrait", brief
        )
        self.pictures.append(drawn)
        return drawn if isinstance(drawn, Picture) else None

    async def draw_place(self, story: Story, place_id: str, name: str = "") -> Picture | None:
        """A place's picture (M1), as the picture endpoint draws one. Live mode only."""
        if not self.live:
            return None
        brief = place_brief(story.state, place_id)
        drawn = await draw(self.picture_model(story), name or f"place-{place_id}", "place", brief)
        self.pictures.append(drawn)
        return drawn if isinstance(drawn, Picture) else None

    async def draw_told(
        self,
        story: Story,
        narration: str,
        *,
        name: str,
        references: Sequence[tuple[str, Picture]] = (),
        place: Picture | None = None,
    ) -> Picture | NotDrawn | None:
        """The picture of a scene the eval writes rather than plays, ending in the story's state
        as it is, drawn as the endpoint draws a scene the player illustrates (M2): from the end
        of its narration, rewritten by the note step, with reference portraits and the picture of
        the place it happens in (M5). Live mode only."""
        if not self.live:
            return None
        drawn = await draw(
            self.picture_model(story),
            name,
            "scene",
            scene_brief(story.state, ending(narration)),
            references,
            scene=SceneText(narration),
            place=place,
        )
        self.pictures.append(drawn)
        return drawn

    async def draw_scene(
        self,
        story: Story,
        played: Played,
        *,
        name: str = "",
        people: Sequence[str] = (),
        references: Sequence[tuple[str, Picture]] = (),
    ) -> Picture | NotDrawn | None:
        """The scene's picture, from the narrator's image prompt when code planned one, else
        from the end of its narration, rewritten from the finished scene by the note step, with
        reference portraits (M5). A scene that code planned the story's cover for draws the
        cover, the story's poster, with its premise, as the picture endpoint does (M1). Live mode
        only."""
        if not self.live or played.result is None:
            return None
        picture = played.scene.picture
        description = picture.prompt if picture is not None else ending(played.narration)
        decision = played.plan.picture
        subject = decision.subject_id if decision is not None else None
        if decision is not None and decision.trigger in THREAD_SUBJECTS:
            subject = None  # a thread, not a person, as `stories.turns.brief` leaves it out
        cover = picture is not None and picture.kind is PictureKind.COVER
        brief = scene_brief(
            played.state,
            description,
            people=people,
            subject_id=subject,
            cover=cover,
            premise=story.premise,
        )
        drawn = await draw(
            self.picture_model(story),
            name or f"{'cover' if cover else 'scene'}-{played.turn}",
            "cover" if cover else "scene",
            brief,
            references,
            scene=SceneText(played.narration, played.action or ""),
        )
        self.pictures.append(drawn)
        return drawn

    async def draw_cover(self, story: Story, name: str = "cover") -> Picture | NotDrawn | None:
        """The story's cover, its poster, from its premise around the main character, as the
        picture endpoint draws a planned cover (M1). Live mode only."""
        if not self.live:
            return None
        brief = scene_brief(story.state, "", cover=True, premise=story.premise)
        drawn = await draw(self.picture_model(story), name, "cover", brief)
        self.pictures.append(drawn)
        return drawn

    # Drafting a world from a premise (G1), for a case whose world isn't a sample.

    def _drafter(self, rating: Rating) -> ModelClient:
        from graph.drafting.samples import offline_backend

        if self.live:
            return self.models.client(rating.value, self.judge_telemetry)
        return ModelClient(offline_backend(grounded=False), ModelConfig(), rating=rating.value)

    async def draft(
        self,
        premise: str,
        *,
        rating: Rating = Rating.TEEN,
        premise_id: str | None = None,
        language: Language = Language.EN,
    ) -> Draft:
        """A draft of the world a premise asks for, by the real drafter in live mode and the
        offline one otherwise, which drafts the outer disciple whatever the premise says."""
        from graph.drafting.chain import create

        return await create(
            self._drafter(rating),
            premise,
            rating=rating.value,
            premise_id=premise_id,
            language=language,
        )

    async def revised(self, draft: Draft, target: Target, instruction: str) -> Draft:
        """The draft after a change the player asks for in plain words (G1, G2)."""
        from graph.drafting.chain import revise

        return await revise(self._drafter(Rating(draft.rating)), draft, target, instruction)

    async def drafted(
        self, premise: str, *, rating: Rating = Rating.TEEN, premise_id: str | None = None
    ) -> WorldState:
        return (await self.draft(premise, rating=rating, premise_id=premise_id)).state()

    def result(self, status: str, seconds: float, error: str | None = None) -> ScenarioResult:
        scenario = self.scenario
        calls = [c for s in self.stories for c in s.telemetry.calls]
        cost = (
            sum((c.cost_usd for c in calls), Decimal(0))
            + self.judge_telemetry.cost_usd
            + self.picture_telemetry.cost_usd
        )
        tallies = [t for t in self.tallies.values() if not (self.live and not t.live)]
        return ScenarioResult(
            id=scenario.id,
            suite=scenario.suite,
            title=scenario.title,
            mode=self.mode,
            status=status,
            seconds=seconds,
            turns=self.turns,
            cost_usd=cost,
            checks=tallies,
            judged=self.judged,
            metrics=self.metrics,
            pictures=self.pictures,
            transcripts=[
                {
                    "seed": s.seed,
                    "label": s.label,
                    "rating": s.rating.value,
                    "turns": [p.to_json() for p in s.turns],
                }
                for s in self.stories
            ]
            if self.live
            else [],
            error=error,
            use=Use.of(calls),
            turn_cost_usd=sum((p.cost_usd for s in self.stories for p in s.turns), Decimal(0)),
            logic=counted(p for s in self.stories for p in s.turns),
        )


def _traceback(error: BaseException) -> str:
    """The traceback, ending on the error's own line, which `ScenarioResult.failures()` shows.
    Notes such as LangGraph's "During task with name ..." are printed after that line, so they
    go first instead."""
    shown = traceback.TracebackException.from_exception(error, limit=8)
    notes = shown.__notes__ or []
    shown.__notes__ = None
    return "".join([*(f"{note}\n" for note in notes), *shown.format()])


async def run_scenario(
    scenario: Scenario, mode: Mode, models: Models | None = None
) -> ScenarioResult:
    """Runs one scenario. A scenario that doesn't run in `mode` is skipped, a pending one is
    reported as pending, and a script that raises is an error, never a crash of the whole run."""
    if scenario.pending:
        return ScenarioResult(
            scenario.id,
            scenario.suite,
            scenario.title,
            mode,
            "pending",
            waits_for=scenario.waits_for,
        )
    if not scenario.runs_in(mode):
        return ScenarioResult(scenario.id, scenario.suite, scenario.title, mode, "skipped")
    ev = Eval(scenario, mode, models)
    started = time.perf_counter()
    assert scenario.script is not None
    try:
        if ev.live:
            ev.models.require_live()
        await scenario.script(ev)
    except LiveUnavailable:
        raise
    except NotAsScripted as error:
        if not ev.live:
            return ev.result("error", time.perf_counter() - started, _traceback(error))
        ev.check("the live turns take the shape the script reads", False, str(error))
    except Exception as error:
        return ev.result("error", time.perf_counter() - started, _traceback(error))
    tallies = [t for t in ev.tallies.values() if not (ev.live and not t.live)]
    failed = any(not t.ok for t in tallies) or any(not j.passed for j in ev.judged)
    if not tallies and not ev.judged:
        return ev.result("error", time.perf_counter() - started, "the scenario checked nothing")
    return ev.result("failed" if failed else "passed", time.perf_counter() - started)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
