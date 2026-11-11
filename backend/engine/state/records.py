"""The records the world keeps: deeds, rumors, facts, goals, leads, threads, clocks, pending
events and rolls (C2).

Every record that happens in time carries a `timeline_id` and an in-world time (W10, W10a). Every
record a character can know carries `known_by`, a list of character ids, so the Memory screen can
show only what the player character knows (C6).
"""

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from engine.base import (
    MAIN_TIMELINE,
    EngineModel,
    Importance,
    Percent,
    Probability,
    Severity,
    WorldSeconds,
)
from engine.context import Difficulty
from engine.state.scene import Terms


class OriginKind(StrEnum):
    """Where something came from (W15, N1, N4, N7)."""

    PREMISE = "premise"
    DEED = "deed"
    EVENT = "event"  # a W16 event or a pending event that fired
    AGENDA = "agenda"  # a faction's or a key NPC's plan (W6, E3)
    CLOCK = "clock"
    EMERGENCE = "emergence"  # W15: born of the world state
    BIRTH = "birth"  # N6: born to someone in the story
    SUCCESSOR = "successor"  # W15a: a new faction derived from a destroyed one
    NARRATOR = "narrator"  # N7: a detail that became canon when first told
    PLAYER = "player"  # N4: a backstory claim, or a goal the player stated
    ENGINE = "engine"


class Origin(EngineModel):
    kind: OriginKind
    ref_id: str | None = None
    text: str = ""


class CauseMechanism(StrEnum):
    """C1. The only ways a death, a destroyed faction, a ruined place or an open rule can change.
    Each needs a recorded deed or event, and the world bible must allow the mechanism."""

    RESURRECTION = "resurrection"  # the bible's medicine allows bringing back the dead
    SURVIVED = "survived"  # a presumed death turned out false; never a confirmed one
    REVIVAL = "revival"  # W15a: a destroyed faction returns, with survivors
    REBUILD = "rebuild"  # W7: time, people and resources rebuilt a ruined place
    LOCAL_REVERSAL = "local_reversal"  # W10a: a time power rewound an object or a building
    DISCOVERY = "discovery"  # G7, A4: a discovery changed an open rule for everyone


class CauseRef(StrEnum):
    DEED = "deed"
    EVENT = "event"


class Cause(EngineModel):
    """C1. The recorded cause behind a change that would otherwise be forbidden."""

    mechanism: CauseMechanism
    ref_kind: CauseRef
    ref_id: str
    text: str = ""


class StatusChange(EngineModel):
    """One entry in the status history of a character, faction or place."""

    status: str
    from_status: str | None = Field(default=None, description="The status it changed from.")
    presumed: bool = Field(
        default=False, description="For a death: presumed, not confirmed, when it was recorded."
    )
    turn: int = Field(ge=0)
    world_s: WorldSeconds
    timeline_id: str = MAIN_TIMELINE
    cause: Cause | None = None
    note: str = ""
    known_by: list[str] = Field(
        default_factory=list, description="Who knows of the change, such as a death (C6)."
    )


class Visibility(StrEnum):
    """W2. Who could know a deed when it happened."""

    SECRET = "secret"
    WITNESSED = "witnessed"
    PUBLIC = "public"


class TraceKind(StrEnum):
    """W13. What a deed with no witnesses leaves behind."""

    TIES = "ties"  # how connected the victims were: family, trade, a lord who misses the taxes
    BODY = "body"
    WOUND = "wound"  # wounds only a power like yours makes
    DAMAGE = "damage"  # a burned town visible from the road
    SURVIVOR = "survivor"  # a hidden survivor
    RECORD = "record"  # scrying, forensics, cameras, phone records (G9)
    NOISE = "noise"  # a blast seen and heard (W10a)


class Trace(EngineModel):
    kind: TraceKind
    text: str
    strength: Percent = Field(default=50, description="How much it raises the odds of discovery.")


# W1. The kind of the deed that is a bout both sides agreed to (`engine.resolve.bouts`).
BOUT = "bout"


class Deed(EngineModel):
    """W1. A significant act, recorded with its turn, place, victims, severity and witnesses.

    The actor is usually the player, but NPCs' deeds use the same record (E5). Deeds done in
    stopped time are secret unless someone was immune, but still leave traces (W10a, W13).
    """

    id: str
    actor_id: str
    kind: str = Field(description="A free-form verb: kill, save, betray, conquer, reveal.")
    text: str
    turn: int = Field(ge=0)
    world_s: WorldSeconds
    timeline_id: str = MAIN_TIMELINE
    place_id: str | None = None
    victim_ids: list[str] = Field(default_factory=list)
    target_ids: list[str] = Field(default_factory=list)
    severity: Severity = 1
    visibility: Visibility = Visibility.SECRET
    witness_ids: list[str] = Field(default_factory=list)
    unnoticed_witness_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Witnesses the actor didn't notice, such as a hidden watcher or someone immune to a"
            " time stop. They spread word as usual (W2), but the actor doesn't know of them (C6)."
        ),
    )
    traces: list[Trace] = Field(default_factory=list)
    in_stopped_time: bool = False
    discovered: bool = False
    known_by: list[str] = Field(default_factory=list)
    known_by_factions: list[str] = Field(
        default_factory=list,
        description=(
            "Factions that know of it and who did it (W3, W5), by id, so the player's reputation"
            " and a faction's answer count each deed once."
        ),
    )
    terms: Terms | None = Field(
        default=None,
        description=(
            "W1: the terms both sides agreed to that the deed stayed inside"
            " (`engine.resolve.bouts`). With no victim it is the bout itself, one deed however"
            " many blows; with one, a death both accepted. Nobody takes either as an attack."
        ),
    )
    broke_terms: bool = Field(
        default=False,
        description="W1: it went beyond the terms of an agreed bout: an attack under cover of one.",
    )

    @property
    def subject_ids(self) -> list[str]:
        return [*self.victim_ids, *self.target_ids]

    @property
    def is_bout(self) -> bool:
        """W1. The bout itself: a fight inside terms both sides agreed to, which hurt nobody
        beyond them."""
        return self.terms is not None and not self.victim_ids

    @property
    def agreed(self) -> bool:
        """W1. Inside terms both sides accepted: the bout itself, or a death in it."""
        return self.terms is not None


# How a retelling that lost the doer's name begins (W2), in the world's words.
GARBLED_LEAD = "A garbled account goes round: "


class Rumor(EngineModel):
    """W2, W13. What people say. It may be wrong; `is_true` is hidden truth (C6): whether what it
    says is so, even where it is vague ("nobody knows who did it"). It spreads over in-world time
    along places' travel times and can lose accuracy as it goes."""

    id: str
    text: str
    is_true: bool
    accuracy: Percent = 100
    deed_id: str | None = None
    about_ids: list[str] = Field(default_factory=list)
    origin_place_id: str | None = None
    reached_place_ids: list[str] = Field(default_factory=list)
    started_s: WorldSeconds = 0
    timeline_id: str = MAIN_TIMELINE
    believed_by: list[str] = Field(default_factory=list)
    heard_at: dict[str, WorldSeconds] = Field(
        default_factory=dict,
        description="Who has heard it, by character id, and the world second they first did.",
    )
    seen_by: list[str] = Field(
        default_factory=list,
        description=(
            "Who was there when what it tells happened, such as a clock's end, so they know it"
            " is so rather than heard it (C6). A rumor of a deed goes by the deed's own"
            " `known_by` instead."
        ),
    )

    @model_validator(mode="after")
    def _garbled_is_vague_not_wrong(self) -> "Rumor":
        """A garbled retelling saved before it kept its truth loads true: it only ever came from a
        true rumor that named the doer, and losing the name makes it vaguer, not wrong (W2)."""
        if not self.is_true and self.deed_id is not None and self.text.startswith(GARBLED_LEAD):
            self.is_true = True
        return self

    @property
    def heard_by(self) -> list[str]:
        """Who has heard it, earliest first."""
        return sorted(self.heard_at, key=lambda c: (self.heard_at[c], c))


class FactKind(StrEnum):
    LORE = "lore"  # about the world
    CANON = "canon"  # N7: a detail that became canon when first told, or R2 made canon
    OBSERVATION = "observation"  # something a character saw or learned
    SECRET = "secret"
    BELIEF = "belief"  # something someone holds true; check `is_true`


class Fact(EngineModel):
    """C2, N3. A fact with its importance, truth value and who knows it."""

    id: str
    text: str
    kind: FactKind = FactKind.OBSERVATION
    importance: Importance = 3
    is_true: bool = True
    subject_ids: list[str] = Field(default_factory=list)
    known_by: list[str] = Field(default_factory=list)
    turn: int = Field(default=0, ge=0)
    world_s: WorldSeconds = 0
    timeline_id: str = MAIN_TIMELINE
    origin: Origin | None = None


class Transfer(EngineModel):
    """C10. One thing that changed hands, or came from the world or left it, with who had it and
    who has it now: the record behind what everyone holds, so a loss is never forgotten. `None`
    on a side is the world: found or made, used up or lost. Money is counted in `currency`."""

    name: str
    quantity: int = Field(ge=1)
    money: bool = False
    currency: str = ""
    item_id: str | None = None
    from_id: str | None = None
    to_id: str | None = None
    how: str = ""
    known_by: list[str] = Field(default_factory=list)
    turn: int = Field(default=0, ge=0)
    world_s: WorldSeconds = 0
    timeline_id: str = MAIN_TIMELINE
    origin: OriginKind = OriginKind.NARRATOR


class GoalStatus(StrEnum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    FAILED = "failed"
    ABANDONED = "abandoned"
    MERGED = "merged"  # it said again what an older goal says (`merged_into`)


class Goal(EngineModel):
    """N2. Goals belong to the player, who states them or accepts one the story offers. The
    narrator never rewrites them. A goal closes once it is over: play achieved it or made it
    impossible, the thread of the lead it came from closed, it repeated an older goal, or the
    player dropped it."""

    id: str
    text: str
    status: GoalStatus = GoalStatus.ACTIVE
    set_turn: int = Field(default=0, ge=0)
    lead_id: str | None = Field(default=None, description="Set when the player accepted a lead.")
    closed_turn: int | None = Field(default=None, ge=0)
    merged_into: str | None = Field(
        default=None, description="For a merged goal: the older goal that says the same."
    )


class Fallen(EngineModel):
    """N6. An earlier player character, whose story ended before someone else carried it on. The
    character stays in `characters`, dead or, after an ending the player chose, alive as anyone
    else in the world, and the people who knew them may remember them."""

    character_id: str
    name: str
    ending: str = Field(description="death or chosen, as the story's ending was.")
    turn: int = Field(ge=0, description="The scene the ending came in.")
    world_s: WorldSeconds
    successor_id: str


class LeadStatus(StrEnum):
    OPEN = "open"
    TAKEN = "taken"
    DECLINED = "declined"
    EXPIRED = "expired"


class Lead(EngineModel):
    """N2. What the world offers: a job, a rumor, a summons. It can expire, on in-world time
    (W10), and never overwrites a goal."""

    id: str
    text: str
    kind: str = ""
    from_id: str | None = None
    place_id: str | None = None
    status: LeadStatus = LeadStatus.OPEN
    offered_turn: int = Field(default=0, ge=0)
    offered_s: WorldSeconds = 0
    expires_s: WorldSeconds | None = None
    thread_id: str | None = None


class ThreadKind(StrEnum):
    MYSTERY = "mystery"
    THREAT = "threat"
    RIVALRY = "rivalry"
    ROMANCE = "romance"
    AMBITION = "ambition"
    DEBT = "debt"
    QUEST = "quest"


class ThreadStatus(StrEnum):
    OPEN = "open"
    DORMANT = "dormant"
    RESOLVED = "resolved"
    FAILED = "failed"
    ABANDONED = "abandoned"
    RESOLVED_WITHOUT_PLAYER = "resolved_without_player"

    @property
    def closed(self) -> bool:
        return self not in (ThreadStatus.OPEN, ThreadStatus.DORMANT)


class Thread(EngineModel):
    """N1. An open plot line. Arcs are named afterwards, never planned."""

    id: str
    title: str
    kind: ThreadKind
    stakes: str = ""
    involved_ids: list[str] = Field(default_factory=list)
    clock_id: str | None = None
    origin: Origin
    status: ThreadStatus = ThreadStatus.OPEN
    opened_turn: int = Field(default=0, ge=0)
    last_active_turn: int = Field(default=0, ge=0)
    taken_up_turn: int | None = Field(
        default=None, ge=0, description="The last turn the player took it up (W16)."
    )
    closed_turn: int | None = None
    arc: str | None = None
    known_by: list[str] = Field(default_factory=list)


class ClockStatus(StrEnum):
    RUNNING = "running"
    ENDED = "ended"
    STOPPED = "stopped"


class Clock(EngineModel):
    """E2. A threat, ambition or scheduled event: a name, a few steps, what happens at each, and
    what advances or reverses it. It runs on in-world time (W10) and with deeds, whether or not
    the player is there. A clock that ends becomes a pending event with a due time."""

    id: str
    name: str
    steps: list[str] = Field(min_length=1, description="What happens at each step.")
    filled: int = Field(default=0, ge=0, description="Steps completed so far.")
    advances_on: list[str] = Field(default_factory=list)
    reverses_on: list[str] = Field(default_factory=list)
    interval_s: int | None = Field(
        default=None, gt=0, description="In-world seconds per step, when time alone advances it."
    )
    next_step_s: WorldSeconds | None = None
    owner_id: str | None = None
    thread_id: str | None = None
    status: ClockStatus = ClockStatus.RUNNING
    known_by: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _filled_within_steps(self) -> "Clock":
        if self.filled > len(self.steps):
            raise ValueError(
                f"clock {self.id!r} has {self.filled} of {len(self.steps)} steps filled"
            )
        return self

    @property
    def remaining(self) -> int:
        return max(0, len(self.steps) - self.filled)


class EventStatus(StrEnum):
    """The same values as the `stories_pendingevent` table's status."""

    PENDING = "pending"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class PendingEvent(EngineModel):
    """W10, B12. Something that will happen at an in-world time, never after a number of turns:
    a witness reaching the guard post, a rumor arriving, a faction's answer, a clock's end.

    `needs_player` events stop a long action at their due time, and the scene starts there.
    `payload` is free JSON that the code which scheduled the event reads back when it fires.
    `seed` is the event's own seed, so a rewound world replays it the same way (W10a).
    """

    id: str
    kind: str
    title: str = ""
    due_s: WorldSeconds
    timeline_id: str = MAIN_TIMELINE
    needs_player: bool = False
    status: EventStatus = EventStatus.PENDING
    subject_ids: list[str] = Field(default_factory=list)
    place_id: str | None = None
    origin: Origin | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    seed: str | None = None
    created_turn: int = Field(default=0, ge=0)
    created_s: WorldSeconds = 0
    applied_turn: int | None = None
    applied_s: WorldSeconds | None = None


class StepResult(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


class DieKind(StrEnum):
    """A3. What a die of a throw is. Every die has twenty sides."""

    PLAIN = "plain"
    GREEN = "green"  # one real advantage that holds
    VIOLET = "violet"  # a move's own die while they are mastering it: 18 or more is an insight
    GOLD = "gold"  # a move's own die from second nature on: it never counts below 10
    GREY = "grey"  # the world's die, for what is nobody's doing


class Die(EngineModel):
    """A3. One die of a throw, as it fell. `sprung` marks a die thrown because the one before it
    showed a 20."""

    kind: DieKind = DieKind.PLAIN
    face: int = Field(ge=1, le=20)
    sprung: bool = False

    @property
    def value(self) -> int:
        """What it counts for: its face, and never below 10 for a gold die."""
        return max(10, self.face) if self.kind is DieKind.GOLD else self.face


class Mark(StrEnum):
    """A3. How a throw came out against its number, best first."""

    OVER_THE_TOP = "over_the_top"  # the total is past 20 for each die in the hand
    PASSED = "passed"  # it reached the number
    SO_CLOSE = "so_close"  # it fell short by 5 or less
    MISSED = "missed"  # it fell short by more than 5

    @property
    def passed(self) -> bool:
        return self in (Mark.OVER_THE_TOP, Mark.PASSED)


class NumberPart(EngineModel):
    """A3, A8. One thing a throw's number is made of: the level it is up against, or something
    that moves it by a step of 5."""

    text: str
    points: int


class Throw(EngineModel):
    """A3. The dice that decided a step, kept so the throw can be shown and replayed exactly:
    `SeededRng(seed).randint(1, 20)` gives each die's face in the order of `dice`.

    The hand is what the character throws: plain dice by how well they have the move or the
    skill, a green die for each real advantage that holds, and the move's own die last. A 20
    throws one more die. The total is set against `number`, which code works out from what the
    step is up against (`engine.resolve.throw`).
    """

    dice: list[Die] = Field(default_factory=list, description="In the order thrown.")
    hand: int = Field(ge=1, description="The dice in the hand, before any sprung from a 20.")
    hand_why: str = Field(default="", description="'Aura blade (skilled), 3 dice'.")
    greens: list[str] = Field(
        default_factory=list, description="Each green die's reason, in the order thrown."
    )
    number: int = Field(ge=0)
    made_of: list[NumberPart] = Field(
        default_factory=list, description="What the number is made of, the level first."
    )
    total: int = Field(ge=0)
    most: int = Field(ge=0, description="The most the hand could make with no 20: 20 a die.")
    mark: Mark
    against: str = Field(default="", description="What it is up against, in a sentence.")
    deadly: bool = Field(default=False, description="A miss can kill, marked before the dice.")
    miss_costs: str = Field(default="", description="What a miss costs, for a deadly throw.")
    insight: bool = Field(
        default=False, description="A4: the violet die showed an insight, worth three uses."
    )
    insight_at: int = Field(
        default=18,
        ge=1,
        le=20,
        description="A4: the face of the violet die that shows an insight: 18, or 15 when two "
        "talents both cover the move.",
    )

    @property
    def short_by(self) -> int:
        """How far the total fell short of the number; 0 when it reached it."""
        return max(0, self.number - self.total)

    @property
    def line(self) -> str:
        """ "31 against 27", as a scene shows a throw in one line."""
        return f"{self.total} against {self.number}"

    @property
    def of_the_world(self) -> bool:
        """The world's one grey die, for what is nobody's doing, and not a character's hand."""
        return bool(self.dice) and self.dice[0].kind is DieKind.GREY


class RollRecord(EngineModel):
    """A3. A seeded roll, recorded on the scene with its seed so it can be replayed exactly.

    A step is decided by a throw of dice (`throw`): `odds` is then the exact chance the hand had
    of reaching the number, and `odds_label` the throw in one line, "31 against 27". A roll made
    before the dice has no throw: its `odds` is the chance of success after difficulty (A5) and
    `value` the draw that decided it. `allowed` lists the results the facts allow, since a close
    call is decided only between outcomes the facts leave open (A2). When the roll also decided
    how long something took (W10), `duration_s` holds it.
    """

    seed: str
    label: str = ""
    odds: Probability
    odds_label: str = ""
    value: Probability = 0.0
    result: StepResult
    allowed: list[StepResult] = Field(
        default_factory=lambda: [StepResult.SUCCESS, StepResult.PARTIAL, StepResult.FAILURE]
    )
    difficulty: Difficulty = Difficulty.BALANCED
    duration_s: int | None = Field(default=None, ge=0)
    throw: Throw | None = Field(default=None, description="A3: the dice, when dice decided it.")
