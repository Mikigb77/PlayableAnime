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
    BeatVerdict,
    ChoiceKind,
    DirectorPlan,
    Harm,
    Intent,
    OutcomeClass,
    PictureKind,
    Resolution,
    StandingAction,
)
from engine.pipeline import PlayOut, TimePassage
from engine.state.records import DieKind, Mark, PendingEvent, StepResult
from engine.state.world import EventSize, WorldState

if TYPE_CHECKING:
    from graph.llm import ModelClient

# C3: a chapter summary every this many turns.
CHAPTER_TURNS = 20
# A chapter covers at most this many turns, so summaries that were late for a long time catch up
# a window at a time instead of asking for every scene at once.
MAX_CHAPTER_TURNS = 3 * CHAPTER_TURNS
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
    # N6: the player ends the story with `/end`, with or without a note on how. Its scene is the
    # epilogue.
    END = "end"


@dataclass(frozen=True)
class Reading:
    """A3. How a turn that was decided and shown was read: the interpret step's `Intent` as
    code checked it, and the steps it handed back as too many for one scene (R6). The dice of a
    turn come from its seed, so the same reading on the same world decides the same steps again."""

    intent: Intent
    overflow: tuple[str, ...] = ()


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
    first: every one the next chapter summary covers (C3: those since the last chapter, at most
    `MAX_CHAPTER_TURNS` of them), and never fewer than the last `RECENT_SCENES`, which the
    narrator reads in full.
    """

    state: WorldState
    ctx: TurnContext
    kind: TurnKind
    action: str | None = None
    standing: StandingAction | None = None
    premise: str = ""
    scenes: tuple[PastScene, ...] = ()
    # N6, an end turn only: tell the epilogue without what the world refused of the note,
    # instead of handing the refusal back.
    drop_refused: bool = False
    # A3: this turn was already decided and shown, so it is played out as it was read then.
    reading: Reading | None = None

    def __post_init__(self) -> None:
        if self.ctx.turn != self.state.turn + 1:
            raise ValueError(
                f"turn {self.ctx.turn} doesn't follow the state's last turn {self.state.turn}"
            )
        if self.kind in (TurnKind.ACTION, TurnKind.CHOICE) and not (self.action or "").strip():
            raise ValueError(f"a {self.kind} turn needs the action's text")
        if self.kind is TurnKind.STANDING and self.standing is None:
            raise ValueError("a standing turn needs wait or observe")
        if self.kind is TurnKind.OPENING and not (self.state.turn == 0 or self.state.opening_due):
            # N6: a story carried on by someone new opens again, for them.
            raise ValueError("only a story with no scenes, or someone new, gets an opening turn")
        if self.kind is TurnKind.END and self.state.turn == 0:
            raise ValueError("a story that hasn't opened can't end")
        if self.drop_refused and self.kind is not TurnKind.END:
            raise ValueError("only an end turn drops what the world refused")


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


class DieDetail(_ApiModel):
    """One die of a throw as it fell. `sprung` marks one thrown because the die before it
    showed a 20."""

    kind: DieKind
    face: int
    sprung: bool = False


class NumberPartDetail(_ApiModel):
    text: str
    points: int


class ThrowDetail(_ApiModel):
    """API.md's `Throw`: the dice that decided a step, in the order thrown, with everything the
    app needs to show the throw and replay it (A3). The app never rolls: it shows these."""

    dice: list[DieDetail]
    hand: int
    hand_why: str = ""
    greens: list[str] = Field(default_factory=list)
    number: int
    made_of: list[NumberPartDetail] = Field(default_factory=list)
    total: int
    most: int
    mark: Mark
    against: str = ""
    deadly: bool = False
    miss_costs: str = ""
    insight: bool = False
    # The face of the violet die that shows an insight: 18, or 15 when two talents cover it.
    insight_at: int = 18


class RollDetail(_ApiModel):
    odds_label: str
    result: StepResult
    seed: str
    # The dice, for a step dice decided. A scene saved before the dice travelled has none.
    throw: ThrowDetail | None = None


class BeatDetail(_ApiModel):
    """R2: a beat whose check found something the scene hadn't established, or came up empty
    (nothing there, or a power or item the character doesn't have) and stopped the step there.
    Beats whose check simply held are left out: nothing about them needs explaining."""

    beat: str
    thing: str
    verdict: BeatVerdict
    reason: str
    roll: RollDetail | None = None


class StruckDetail(_ApiModel):
    """N6: what struck back at the player character after a step: the foes still fighting them, or
    a danger the step met, settled like a step, by the facts or by a roll."""

    by: str
    outcome_class: OutcomeClass = Field(alias="class")
    harm: Harm
    reason: str
    roll: RollDetail | None = None


class StepDetail(_ApiModel):
    text: str
    outcome_class: OutcomeClass = Field(alias="class")
    reason: str
    roll: RollDetail | None = None
    beats: list[BeatDetail] | None = None
    struck: list[StruckDetail] | None = None


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
    # For a refused change, what kind it was ("character.item"), the only part logged with the
    # code, since detail and subject can hold story text (T6).
    area: str | None = None


EndingKind = Literal["death", "chosen"]


@dataclass(frozen=True)
class Ending:
    """N6: the turn ended the player character's story. `death` when they died in it, `chosen`
    when the player ended it with `/end` and they lived. `self_inflicted` when the death was
    harm they aimed at their own body."""

    kind: EndingKind
    character_id: str
    self_inflicted: bool = False


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
    ending: Ending | None = None

    @property
    def narration_mode(self) -> NarrationMode:
        return self.scene.narration_mode


@dataclass(frozen=True)
class StepsDecided:
    """`steps.decided`: what the engine decided, before the narrator writes a word (A3, B7).
    `details` is what the finished scene will carry. `reading` is how the turn was read, for the
    endpoint to keep before it shows them, so the turn is played out as it was decided.
    `passage_label` is the heading the scene will carry when hours or days passed in it ("Three
    days later", W10), so the player reads it before the telling starts."""

    details: SceneDetails
    reading: Reading
    passage_label: str | None = None

    @property
    def throws(self) -> list[ThrowDetail]:
        """Every throw of dice among the steps, their beats and what struck back."""
        rolls = []
        for step in self.details.steps:
            rolls.append(step.roll)
            rolls += [beat.roll for beat in step.beats or []]
            rolls += [struck.roll for struck in step.struck or []]
        return [roll.throw for roll in rolls if roll is not None and roll.throw is not None]


@dataclass(frozen=True)
class TurnCompleted:
    """The last event of a turn that finished."""

    result: TurnResult


type TurnEvent = NarrationDelta | NarrationReset | StepsDecided | TurnCompleted


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
    ending: Ending | None  # N6: the player character's story ends in this scene
    left_out: tuple[str, ...]  # N6: what the world refused of an ending's note, ended without
    # S10: the engine's lines of the turn, as far as they are said in the story's language; the
    # model call still saying some of them; and the decided steps still waiting on it to go out.
    lines: Any  # graph.turn.saying.Lines
    wording: Any  # graph.turn.saying.Wording
    decided: StepsDecided | None
    brief: Any  # graph.turn.context.NarrationBrief
    narration: Any  # graph.turn.outputs.NarratorOutput
    narration_mode: NarrationMode
    scene: SceneDraft
    result: TurnResult
    issues: list[Issue]
    timings_ms: dict[str, int]
