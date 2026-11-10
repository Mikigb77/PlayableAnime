"""What resolve decides (B5 step 3): per step, its class, the reason in the world's words, the
roll if there was one, the result, the costs and how long it took.

Resolve is code. It turns an `Intent` into a `Resolution` before anything is narrated, so a blocked
narration never blocks the deed (F4). The narrator writes the result it is given (A3).
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, Severity
from engine.contracts.delta import StateDelta
from engine.contracts.intent import ActionKind, Aim, OutcomeClass, UseSource
from engine.state.records import RollRecord, StepResult, Trace, Visibility
from engine.state.scene import EncounterKind
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


class Harm(StrEnum):
    """N6. What a peril did to the player character, worst last."""

    NONE = "none"  # it missed, or couldn't hurt them
    HURT = "hurt"
    WOUNDED = "wounded"
    SUBDUED = "subdued"  # knocked down, pinned or taken
    BADLY_WOUNDED = "badly_wounded"
    MAIMED = "maimed"  # badly wounded, with a wound that lasts: a lost hand, an eye
    DYING = "dying"
    DEAD = "dead"


class Peril(EngineModel):
    """N6, A2. What struck back at the player character in a step: the foes fighting them, or a
    danger the step faced, such as a long drop. Settled like any step, logic first and the dice only
    where the facts leave it open, and recorded before anything is narrated (F4)."""

    by_ids: list[str] = Field(
        default_factory=list, description="The foes who struck; empty for a danger."
    )
    by: str = Field(description="Who or what struck, in words.")
    aim: Aim = Field(description="What they were out to do, or what the danger does.")
    outcome_class: OutcomeClass
    reason: str = Field(description="In the world's words (A8).")
    roll: RollRecord | None = None
    result: StepResult
    harm: Harm = Harm.NONE


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
    drew_on: list[str] = Field(
        default_factory=list,
        description="R1, A3: the actor's own powers, techniques and moves the step used, by "
        "name, once past the sheet check. They work as the actor knows them to: a step that "
        "fails meets what stood in the way, unless its reason names the ability.",
    )
    duration_s: int = Field(ge=0, description="World seconds it took (W10).")
    personal_s: int | None = Field(
        default=None, ge=0, description="The actor's lived seconds, when they differ (W10a)."
    )
    beats: list[BeatResolution] = Field(default_factory=list, description="R2's beat check.")
    strangers: list[str] = Field(
        default_factory=list,
        description="F1, W2: the ids of people this step made real, the stranger it aimed at "
        "first and any onlooker after; `effects` creates them.",
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
    training: TrainingSoFar | None = Field(
        default=None, description="A4: a training step's effort so far, kept if it is cut short."
    )
    kind: ActionKind | None = Field(default=None, description="W10: the kind of action.")
    encounter: EncounterKind | None = Field(
        default=None,
        description="W10: the encounter this step starts or carries on with `opponent_ids`, as "
        "code reads it: a fight when it aims harm at someone, otherwise the kind the interpret "
        "step proposed when someone who can respond faces it. `engine.encounters` decides.",
    )
    opponent_ids: list[str] = Field(
        default_factory=list,
        description="W10: the living characters besides the actor that the step fought or faced: "
        "the aim's targets and whoever stood in the way.",
    )
    perils: list[Peril] = Field(
        default_factory=list,
        description="N6: what struck back at the player character in this step, foes first, "
        "then a danger; their harm is in `effects`.",
    )
    escaped: list[str] = Field(
        default_factory=list,
        description="N6: the foes this step got cleanly away from. `engine.encounters` ends the "
        "fight once the player character has left everyone still in it behind.",
    )

    @property
    def hurt_by_peril(self) -> bool:
        """A peril did the player character harm, so the plan stops for them to react."""
        return any(a.harm is not Harm.NONE for a in self.perils)

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
    STRUCK = "struck"  # a foe or a danger hurt the player character (N6)


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

    @property
    def found(self) -> list[str]:
        """R2, R3. What the steps that played made canon, in order, such as the branch a beat
        picked up: the scene's record keeps them (`engine.apply`). A step an event cut short
        found nothing."""
        return [
            beat.thing
            for step in self.steps
            if not step.interrupted
            for beat in step.beats
            if beat.verdict is BeatVerdict.MADE_CANON
        ]
