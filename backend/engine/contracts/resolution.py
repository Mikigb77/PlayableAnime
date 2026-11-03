"""What resolve decides (B5 step 3): per step, its class, the reason in the world's words, the
roll if there was one, the result, the costs and how long it took.

Resolve is code. It turns an `Intent` into a `Resolution` before anything is narrated, so a blocked
narration never blocks the deed (F4). The narrator writes the result it is given (A3).
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, Severity
from engine.contracts.delta import StateDelta
from engine.contracts.intent import OutcomeClass
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
    traces: list[Trace] = Field(default_factory=list)
    in_stopped_time: bool = False


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
    chain: list[LinkResolution] = Field(default_factory=list)
    stopped_at_link: int | None = None
    effects: StateDelta = Field(default_factory=StateDelta)
    deeds: list[ProposedDeed] = Field(default_factory=list)
    start_s: int | None = Field(default=None, description="Set by `pipeline.play_out`.")
    end_s: int | None = Field(default=None, description="Set by `pipeline.play_out`.")
    interrupted: bool = Field(
        default=False, description="Cut short by an event that needs the player (W10)."
    )

    @property
    def clean_success(self) -> bool:
        return self.result is StepResult.SUCCESS and not self.interrupted


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
    stakes: bool = Field(default=False, description="W16: whether the turn held real stakes.")

    @property
    def duration_s(self) -> int:
        return sum(s.duration_s for s in self.steps)

    @property
    def personal_s(self) -> int:
        return sum(s.duration_s if s.personal_s is None else s.personal_s for s in self.steps)
