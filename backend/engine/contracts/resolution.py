"""What resolve decides (B5 step 3): per step, its class, the reason in the world's words, the
roll if there was one, the result, the costs and how long it took.

Resolve is code. It turns an `Intent` into a `Resolution` before anything is narrated, so a blocked
narration never blocks the deed (F4). The narrator writes the result it is given (A3).
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, Severity
from engine.contracts.delta import StateDelta
from engine.contracts.intent import OutcomeClass, UseSource
from engine.state.records import RollRecord, StepResult, Trace, Visibility
from engine.state.sheet import CostKind, Ruling


class Cost(EngineModel):
    """A cost paid: a power's toll, bullets, money, a favour (G3 step 5)."""

    kind: CostKind
    text: str
    ref: str | None = Field(default=None, description="The power or item it came from.")
    amount: int | None = None


class LinkResolution(EngineModel):
    """A9. How one link of a chain of cause and effect was settled."""

    text: str
    outcome_class: OutcomeClass
    reason: str
    holds: bool
    roll: RollRecord | None = None
    takes_s: int = Field(default=0, ge=0)


class BeatVerdict(StrEnum):
    """R2. How a beat's use was checked."""

    HOLDS = "holds"  # the body, a power, something carried, the scene or this turn's canon
    MADE_CANON = "made_canon"  # something new the place plausibly holds, or a roll found it
    EMPTY = "empty"  # a search that comes up empty or a thing not there: the step goes no further


class BeatResolution(EngineModel):
    """R2. One thing a beat uses, checked against the body, powers, what the character carries,
    the scene and what this turn made canon."""

    text: str = Field(description="The beat.")
    thing: str = Field(description="What it uses, in plain words.")
    source: UseSource
    verdict: BeatVerdict
    reason: str = ""
    roll: RollRecord | None = Field(default=None, description="When the place might hold it.")


class ProposedDeed(EngineModel):
    """W1. A deed that resolve proposes; `record_consequences` turns it into a `Deed` with its
    time, place and witnesses worked out (W2, W12)."""

    kind: str
    text: str
    actor_id: str | None = Field(default=None, description="None means the player character.")
    victim_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    place_id: str | None = None
    severity: Severity = 1
    visibility: Visibility | None = Field(
        default=None, description="None lets the world work it out from who could perceive it."
    )
    witness_ids: list[str] = Field(
        default_factory=list,
        description="Who perceived it. In stopped time, only those immune to the stop (W10a).",
    )
    unnoticed_witness_ids: list[str] = Field(
        default_factory=list,
        description="Witnesses the actor didn't notice (C6). In stopped time, all of them.",
    )
    traces: list[Trace] = Field(default_factory=list)
    in_stopped_time: bool = False


class TrainingSoFar(EngineModel):
    """A4. Where a training step started, so one cut short keeps the effort put in: effort counts
    as `growth.effort_s` of the lived time it ran, times `rate`, on top of `before_s`, and makes
    the gain if it reaches `need_s`."""

    key: str
    what: str
    before_s: float = Field(default=0, ge=0)
    rate: float = Field(default=1.0, gt=0)
    need_s: float = Field(default=0, ge=0)


class StepResolution(EngineModel):
    """One step of the plan, settled. `effects` are the engine's own state changes for the outcome,
    such as a death, applied whether or not the narration is blocked (F4)."""

    index: int = Field(ge=0)
    text: str
    outcome_class: OutcomeClass
    reason: str = Field(description="In the world's words (A8, G14).")
    roll: RollRecord | None = None
    result: StepResult
    costs: list[Cost] = Field(default_factory=list)
    duration_s: int = Field(ge=0, description="World seconds it took (W10).")
    personal_s: int | None = Field(
        default=None, ge=0, description="The actor's lived seconds, when they differ (W10a)."
    )
    beats: list[BeatResolution] = Field(default_factory=list, description="R2's beat check.")
    chain: list[LinkResolution] = Field(default_factory=list)
    stopped_at_link: int | None = None
    effects: StateDelta = Field(default_factory=StateDelta)
    deeds: list[ProposedDeed] = Field(default_factory=list)
    start_s: int | None = Field(default=None, description="Set by `pipeline.play_out`.")
    end_s: int | None = Field(default=None, description="Set by `pipeline.play_out`.")
    interrupted: bool = Field(
        default=False, description="Cut short by an event that needs the player (W10)."
    )
    training: TrainingSoFar | None = Field(
        default=None, description="A4: a training step's effort so far, kept if it is cut short."
    )

    @property
    def clean_success(self) -> bool:
        return self.result is StepResult.SUCCESS and not self.interrupted


class ClaimVerdict(EngineModel):
    """N4. What the engine made of a backstory claim: recorded, or played as something the
    character says or believes, with the reason."""

    text: str
    accepted: bool
    reason: str = ""


class StopReason(StrEnum):
    """R6. Why a chained plan stopped before its last step."""

    FAILED = "failed"
    PARTIAL = "partial"
    RULED_OUT = "ruled_out"
    INTERRUPTED = "interrupted"  # something that needs the player happened (W10)


class Resolution(EngineModel):
    """B5 step 3. The settled plan. `steps` runs up to and including the step where a chained plan
    stopped (R6); `unplayed` lists the steps that never happened, so the narrator hands the scene
    back instead of playing them."""

    actor_id: str | None = Field(default=None, description="None means the player character.")
    steps: list[StepResolution] = Field(default_factory=list)
    stopped_at_step: int | None = None
    stop_reason: StopReason | None = None
    unplayed: list[str] = Field(default_factory=list)
    rulings: list[Ruling] = Field(default_factory=list, description="A9, settled for good.")
    canon: list[str] = Field(
        default_factory=list, description="Details this turn made canon (R2, N7)."
    )
    claims: list[ClaimVerdict] = Field(default_factory=list, description="N4's verdicts.")
    effects: StateDelta = Field(
        default_factory=StateDelta,
        description=(
            "The engine's changes for the plan as a whole, applied after its steps: details of"
            " powers settled (A9) and accepted backstory (N4)."
        ),
    )
    stakes: bool = Field(default=False, description="W16: whether the turn held real stakes.")

    @property
    def duration_s(self) -> int:
        return sum(s.duration_s for s in self.steps)

    @property
    def personal_s(self) -> int:
        return sum(s.duration_s if s.personal_s is None else s.personal_s for s in self.steps)
