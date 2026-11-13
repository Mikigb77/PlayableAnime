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
from engine.state.records import BondStage, RollRecord, StepResult, Trace, Visibility
from engine.state.scene import Bout, EncounterKind, Terms
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
    not_own: bool = Field(
        default=False,
        description="G14: empty because the power it names is on no record of the actor's.",
    )


class Trip(EngineModel):
    """W10, W7. Where a step takes the actor, as code follows it (`engine.world.journeys`). The
    interpret step says only where; the time comes from the map wherever its routes cover the
    way."""

    from_id: str | None = Field(default=None, description="The place it sets out from.")
    to_id: str | None = Field(
        default=None, description="The place it heads for, when the record holds it."
    )
    to: str = Field(
        default="",
        description="The destination in the player's words, when the record doesn't hold it "
        "yet: the narrator's update names the place the scene reached.",
    )
    route_s: int | None = Field(
        default=None,
        ge=1,
        description="What the way still to go takes by the map's routes, as people travel "
        "there. None when no route covers it: then the step takes the time the interpret step "
        "judged, and that time becomes the route once the actor arrives.",
    )
    takes_s: int | None = Field(
        default=None,
        ge=1,
        description="What the whole of that way takes this actor: the route's time, or less "
        "when something of their own carries them faster. None when no route covers it.",
    )
    arrived: bool | None = Field(
        default=False,
        description="The step took them all the way. False for a step that failed, one the "
        "player timed to stop before, and one an event cut short. None when the player timed "
        "it and no route says how long the way is: the scene says how far they got.",
    )
    by_own_means: bool = Field(
        default=False,
        description="Something of the actor's own carried them, a power, a technique or an "
        "item the step used, so the time it took says nothing of the road.",
    )
    first_visit: bool = Field(
        default=False,
        description="W10: the player character arrived somewhere they had never been, so the "
        "scene shows the place for the first time.",
    )


class ProposedDeed(EngineModel):
    """W1. A deed that resolve proposes; `record_consequences` turns it into a `Deed` with its
    time, place and witnesses worked out (W2, W12)."""

    kind: str
    text: str
    actor_id: str | None = Field(default=None, description="None means the player character.")
    victim_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    wronged_ids: list[str] = Field(
        default_factory=list,
        description="W17: whom a move in a romance wrongs (`engine.bonds.wronged`).",
    )
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
    terms: Terms | None = Field(
        default=None,
        description="W1: the terms both sides agreed to that the deed stayed inside. With no "
        "victim it is the bout itself, recorded once however many blows it had.",
    )
    broke_terms: bool = Field(
        default=False,
        description="W1: it went beyond the terms of an agreed bout, so it is an attack that "
        "came under cover of one.",
    )


class TrainingSoFar(EngineModel):
    """A4. Where a training step started, so one cut short keeps the effort put in: effort counts
    as `growth.effort_s` of the lived time it ran, times `rate`, on top of `before_s`, and makes
    the gain if it reaches `need_s`. Practising a technique they already know (`practising`,
    keyed `mastery:<technique id>`) has nothing to reach: the time it ran counts toward the
    technique's mastery."""

    key: str
    what: str
    before_s: float = Field(default=0, ge=0)
    rate: float = Field(default=1.0, gt=0)
    need_s: float = Field(default=0, ge=0)
    practising: bool = False


class WooingSoFar(EngineModel):
    """W17. An advance in a romance that was answered, as the step began: whom it was made to,
    how it came off, and where the romance stood. A step an event cuts short didn't happen, and
    courting that ran for days is no single moment, so one cut short keeps what the time it
    ran earned (`engine.resolve.romance.cut_short`)."""

    other_id: str
    whole: bool = Field(description="It came off whole, not by half.")
    over_the_top: bool = False
    stage: BondStage | None = None
    attraction: int = 0
    moved_s: int | None = None
    said: list[str] = Field(
        default_factory=list,
        description="What the step's reason tells of the romance, as it stands there, so a "
        "step cut short tells only what it kept.",
    )


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
    terms: Terms | None = Field(
        default=None,
        description="W1: the terms of the agreed bout the blow came inside, if it did. Under "
        "no_harm it bruises at most and leaves nobody helpless.",
    )


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
    hand: str = Field(
        default="",
        description="R4: what the actor did the step with and how well they have it, a skill "
        'or a move with its level ("Swordsmanship (novice)"), whether or not anything was '
        "thrown. Empty for a raw feat and for a step that never got that far. The telling "
        "matches it whatever the result.",
    )
    duration_s: int = Field(ge=0, description="World seconds it took (W10).")
    personal_s: int | None = Field(
        default=None, ge=0, description="The actor's lived seconds, when they differ (W10a)."
    )
    beats: list[BeatResolution] = Field(default_factory=list, description="R2's beat check.")
    not_own: bool = Field(
        default=False,
        description="G14: ruled out because a power or technique the step named is on no "
        "record of the actor's. T5 counts these: a move the story let them do is theirs (A4), "
        "so it must not come back here.",
    )
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
    wooing: WooingSoFar | None = Field(
        default=None,
        description="W17: an advance in a romance that was answered, so one cut short keeps "
        "what the time it ran earned.",
    )
    kind: ActionKind | None = Field(default=None, description="W10: the kind of action.")
    trip: Trip | None = Field(
        default=None,
        description="W10: where the step took the actor, for a step that goes somewhere.",
    )
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
    bout: Bout | None = Field(
        default=None,
        description="W1: the bout both sides agreed to that the step was fought in, with its "
        "terms as code reads them (`engine.resolve.bouts`). None for a step outside one, and "
        "for one that broke them.",
    )
    broke_terms: bool = Field(
        default=False,
        description="W1: a blow of this step, the actor's or a foe's, went beyond the terms of "
        "the bout it was in, so the bout is over and what is left is an open fight.",
    )
    extra: str = Field(
        default="",
        description="A3: the one fixed extra effect of a throw over the top, in words, which "
        "code picks by the kind of step: an opening, a notch of trust or fear, half the time.",
    )
    opening_ids: list[str] = Field(
        default_factory=list,
        description="A3: whom this step won the actor an opening on, by a blow or a defence "
        "thrown over the top. Their next step against them throws a green die.",
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
