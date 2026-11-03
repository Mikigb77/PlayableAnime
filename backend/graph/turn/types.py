"""What goes into a turn, what flows between its nodes, and what comes out (B5).

The turn endpoint (WS3's PR 3) loads the story, builds a `TurnInput`, runs `run_turn` and saves the
`TurnResult` it ends with. Nothing here imports Django or LangGraph (B4, B10).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from engine.context import TurnContext
from engine.contracts import (
    ChoiceKind,
    DirectorPlan,
    Intent,
    OutcomeClass,
    PictureKind,
    Resolution,
    StandingAction,
)
from engine.pipeline import PlayOut, TimePassage
from engine.state.records import PendingEvent, StepResult
from engine.state.world import EventSize, WorldState

if TYPE_CHECKING:
    from graph.llm import ModelClient

# C3: a chapter summary every this many turns.
CHAPTER_TURNS = 20
# The narrator reads this many of the latest scenes in full.
RECENT_SCENES = 3

NarrationMode = Literal["full", "cutaway", "template"]
ResetReason = Literal["cutaway", "template", "retry"]


class TurnKind(StrEnum):
    """API.md's `TurnRequest.kind`, and the Scene's `kind`."""

    OPENING = "opening"
    ACTION = "action"
    CHOICE = "choice"
    STANDING = "standing"


@dataclass(frozen=True)
class PastScene:
    """A saved scene, as the narrator and the summarizer read it."""

    turn: int
    narration: str
    player_action: str | None = None


@dataclass(frozen=True)
class TurnInput:
    """One turn to play.

    `state` is the story's world state as loaded, with its pending events on the current timeline
    (B12). `ctx.turn` is the turn being played, one more than `state.turn`. `action` is the
    player's text, or the label of the suggestion they picked. `scenes` are saved scenes, oldest
    first: every one since the last chapter summary (C3), and never fewer than the last
    `RECENT_SCENES`, which the narrator reads in full.
    """

    state: WorldState
    ctx: TurnContext
    kind: TurnKind
    action: str | None = None
    standing: StandingAction | None = None
    premise: str = ""
    scenes: tuple[PastScene, ...] = ()

    def __post_init__(self) -> None:
        if self.ctx.turn != self.state.turn + 1:
            raise ValueError(
                f"turn {self.ctx.turn} doesn't follow the state's last turn {self.state.turn}"
            )
        if self.kind in (TurnKind.ACTION, TurnKind.CHOICE) and not (self.action or "").strip():
            raise ValueError(f"a {self.kind} turn needs the action's text")
        if self.kind is TurnKind.STANDING and self.standing is None:
            raise ValueError("a standing turn needs wait or observe")
        if self.kind is TurnKind.OPENING and self.state.turn != 0:
            raise ValueError("only a story with no scenes gets an opening turn")


@dataclass(frozen=True)
class TurnDeps:
    """What the nodes use but don't keep: the request's model client (S9: a BYOK client lives
    only as long as its request), and the model calls running alongside the turn, which the
    runner cancels if the turn ends first (B8)."""

    llm: ModelClient
    tasks: list[asyncio.Task[Any]] = field(default_factory=list)


# Events `run_turn` yields while the turn runs. The endpoint sends them as API.md's SSE events.


@dataclass(frozen=True)
class NarrationDelta:
    """`narration.delta`: narration as it is written (S3)."""

    text: str


@dataclass(frozen=True)
class NarrationReset:
    """`narration.reset`: the app clears the narration shown so far. `cutaway` and `template`
    when the narration was blocked (F4), `retry` when a model call failed partway (T7)."""

    reason: ResetReason


# The Scene the endpoint saves, in API.md's shapes.


class _ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class Choice(_ApiModel):
    id: str
    label: str
    kind: ChoiceKind


class RollDetail(_ApiModel):
    odds_label: str
    result: StepResult
    seed: str


class StepDetail(_ApiModel):
    text: str
    outcome_class: OutcomeClass = Field(alias="class")
    reason: str
    roll: RollDetail | None = None


class LinkDetail(_ApiModel):
    link: str
    outcome_class: OutcomeClass = Field(alias="class")
    reason: str


class SceneDetails(_ApiModel):
    """API.md's `SceneDetails`: why the action went the way it did (A2, A8, A9, R6)."""

    steps: list[StepDetail] = Field(default_factory=list)
    chain: list[LinkDetail] | None = None
    stopped_at_step: int | None = None


class SceneEvent(_ApiModel):
    size: EventSize
    title: str


class ScenePicture(_ApiModel):
    """A picture code planned for the scene (M1). The picture endpoint (WS8) draws it later."""

    kind: PictureKind
    prompt: str
    subject_id: str | None = None


class SceneDraft(_ApiModel):
    """One scene, ready to save: the `stories.Scene` row and API.md's `Scene`."""

    turn: int
    kind: TurnKind
    player_action: str | None = None
    narration: str
    choices: list[Choice] = Field(default_factory=list)
    standing_actions: list[StandingAction] = Field(
        default_factory=lambda: [StandingAction.WAIT, StandingAction.OBSERVE]
    )
    details: SceneDetails = Field(default_factory=SceneDetails)
    event: SceneEvent | None = None
    picture: ScenePicture | None = None
    timeline_id: str
    world_start_s: int
    world_end_s: int
    personal_elapsed_s: int | None = None
    narration_mode: NarrationMode = "full"


@dataclass(frozen=True)
class Issue:
    """Something code found wrong with a proposal or the plan, and how it was handled (C5). Logged,
    and kept on the result so the after-turn check and evals can see it."""

    code: str
    detail: str
    subject: str | None = None


@dataclass(frozen=True)
class TurnResult:
    """The finished turn. `state` is the world state to save, with `turn` bumped. `fired` lists
    the pending events that fired during the turn, which the endpoint writes back (B12)."""

    state: WorldState
    scene: SceneDraft
    intent: Intent | None
    resolution: Resolution
    plan: DirectorPlan
    fired: tuple[PendingEvent, ...]
    issues: tuple[Issue, ...]
    timings_ms: dict[str, int] = field(default_factory=dict)

    @property
    def narration_mode(self) -> NarrationMode:
        return self.scene.narration_mode


@dataclass(frozen=True)
class TurnCompleted:
    """The last event of a turn that finished."""

    result: TurnResult


type TurnEvent = NarrationDelta | NarrationReset | TurnCompleted


class TurnState(TypedDict, total=False):
    """The graph's state. Each node returns the keys it sets; nothing is persisted (B9)."""

    input: TurnInput
    seed: str
    world: WorldState  # the state after the latest code step
    passage: TimePassage
    chapter: Any  # graph.turn.nodes.PendingChapter, a summary running alongside the turn
    intent: Intent | None
    overflow: list[str]  # steps past the most one scene plays, handed back (R6)
    resolution: Resolution
    played: PlayOut
    plan: DirectorPlan
    brief: Any  # graph.turn.context.NarrationBrief
    narration: Any  # graph.turn.outputs.NarratorOutput
    narration_mode: NarrationMode
    scene: SceneDraft
    result: TurnResult
    issues: list[Issue]
    timings_ms: dict[str, int]
