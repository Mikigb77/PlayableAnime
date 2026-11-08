"""What the director decides (B5 step 3): whether an event comes in, which dormant threads to
call back, the suggestions' shape, and whether the scene gets a picture. All of it is code.

The director decides that something happens and what it is, never how it ends (W16).
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, WorldSeconds
from engine.state.records import Goal, GoalStatus, Lead, PendingEvent, Thread, ThreadStatus
from engine.state.world import DirectorState, EventSize


class EventKind(StrEnum):
    """E4. The deck's kinds, good things included (W16). The narrator dresses each one in the
    world's own form (G9): a disaster is a police raid in a mafia story and a hull breach in
    space."""

    ARRIVAL = "arrival"
    LOSS = "loss"
    WINDFALL = "windfall"
    DISASTER = "disaster"
    TEMPTATION = "temptation"
    BETRAYAL = "betrayal"
    DISCOVERY = "discovery"
    RIVAL = "rival"
    RUMOR = "rumor"  # a rumor about the player
    OFFER = "offer"
    VISITOR = "visitor"
    CELEBRATION = "celebration"


class EventSource(StrEnum):
    """W16. Where an event comes from, in the order the director looks."""

    DUE = "due"  # pending events and clocks that came due (E2)
    AGENDA = "agenda"  # plans of factions and key NPCs (W6, E3)
    THREAD = "thread"  # a dormant thread (N1)
    EMERGENCE = "emergence"  # an emerging character or faction (W15)
    DECK = "deck"  # a fresh, seeded draw (E4)


class Theme(StrEnum):
    """F7. Events only use themes the player switched on, within the rating."""

    ROMANCE = "romance"
    DARK = "dark"
    GORE = "gore"


class PlannedEvent(EngineModel):
    """W16, E4. Something new that enters the scene. A deck draw is generic on purpose: the
    narrator dresses it in the world's own form (G9) and reuses `cast_ids` before inventing anyone.
    `title` is shown to the player (API.md `Scene.event`), so it never names hidden things (C6)."""

    size: EventSize
    kind: EventKind
    source: EventSource
    source_id: str | None = Field(
        default=None,
        description="The clock, thread, pending event, character or faction behind it.",
    )
    card_id: str | None = Field(default=None, description="The deck card, for a deck draw.")
    title: str
    brief: str = Field(description="What happens, for the narrator to tell in the world's form.")
    themes: list[Theme] = Field(default_factory=list)
    thread_id: str | None = Field(default=None, description="The thread it opens or continues.")
    cast_ids: list[str] = Field(
        default_factory=list, description="Existing characters the narrator should use (E4)."
    )
    place_id: str | None = None
    needs_decision: bool = True
    consequence: str = Field(
        default="", description="What happens if the player ignores it (W16), for foreshadowing."
    )
    plays_out_s: WorldSeconds | None = Field(
        default=None, description="When it plays out if nobody takes it up (W10, W16)."
    )


class PictureKind(StrEnum):
    PORTRAIT = "portrait"
    PLACE = "place"
    SCENE = "scene"
    COVER = "cover"


class PictureTrigger(StrEnum):
    """M1. Code decides when a picture appears, from things the engine already records."""

    STORY_START = "story_start"  # the player character's portrait (G2)
    FIRST_MEETING = "first_meeting"  # a key NPC met for the first time (W15)
    FIRST_VISIT = "first_visit"  # a place on the first visit (W7)
    PLACE_CHANGED = "place_changed"  # a place changed for good, such as ruined or occupied
    LOOK_CHANGED = "look_changed"  # a character changed for good, such as a lost eye (M5, G17)
    BIG_DEED = "big_deed"  # a deed of severity 4 or 5 (W1)
    EVENT = "event"  # a local or world event arriving (W16)
    BREAKTHROUGH = "breakthrough"  # G19
    STRENGTH_REVEALED = "strength_revealed"  # G20
    DEATH = "death"  # a key character's death (N1)
    ARC_END = "arc_end"  # N1
    FIGHT_START = "fight_start"  # a fight with a key NPC or a strong monster (Miki, 2026-11-03)
    DECISIVE_BLOW = "decisive_blow"  # that fight's decisive blow
    COVER = "cover"  # the Library cover


# M1: each subject's first picture, drawn once per story and outside the key-scene budget (M2):
# the player character's portrait, a key NPC's at the first meeting, a place on the first visit
# and the Library cover. A redraw of a changed place or face (M5) is not one of them.
FIRST_PICTURES = frozenset(
    {
        PictureTrigger.STORY_START,
        PictureTrigger.FIRST_MEETING,
        PictureTrigger.FIRST_VISIT,
        PictureTrigger.COVER,
    }
)


class PictureDecision(EngineModel):
    """M1, M2. Within the story's budget and its picture setting. The narrator writes an image
    prompt only when this is set."""

    kind: PictureKind
    trigger: PictureTrigger
    subject_id: str | None = Field(default=None, description="The character, place or deed.")
    version: int | None = Field(
        default=None,
        ge=1,
        description="M4, M5: the look version of a portrait or place (`engine.looks`). Each "
        "version is drawn once and reused until the look changes for good.",
    )
    reason: str = ""


class ChoiceKind(StrEnum):
    """S2. Suggestions, at least one of them away from the current thread."""

    THREAD = "thread"
    PERSONAL = "personal"
    SIDE = "side"
    WILD = "wild"


class SuggestionPlan(EngineModel):
    """S2. How many suggestions the narrator writes (0 to 4) and of which kinds. Wait and observe
    are always offered on top. `thread_id` is the current thread that `thread` choices follow."""

    count: int = Field(default=3, ge=0, le=4)
    kinds: list[ChoiceKind] = Field(
        default_factory=lambda: [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE]
    )
    thread_id: str | None = None


class ThreadChange(EngineModel):
    """N1. A change the director makes to a thread: it wakes, goes dormant or closes. `active`
    marks it moving this turn, with the player or through an ignored event playing out;
    `taken_up` marks that the player took it up (W16)."""

    thread_id: str
    status: ThreadStatus | None = None
    active: bool = False
    taken_up: bool = False
    reason: str = ""


class DirectorUpdates(EngineModel):
    """What `pipeline.record_direction` writes into the state for this plan. `direct` decides and
    never changes the state; recording is mechanical. Ids of new records are provisional: one
    already taken by the time the plan is recorded gets a fresh id, and references follow it."""

    memory: DirectorState = Field(default_factory=DirectorState)
    new_threads: list[Thread] = Field(default_factory=list)
    thread_changes: list[ThreadChange] = Field(default_factory=list)
    schedule: list[PendingEvent] = Field(
        default_factory=list, description="Play-outs of events nobody takes up yet (W16)."
    )
    cancel_ids: list[str] = Field(
        default_factory=list, description="The director's pending events that were taken up."
    )
    applied_ids: list[str] = Field(
        default_factory=list,
        description="The director's pending events that came due and this plan handled.",
    )
    new_leads: list[Lead] = Field(default_factory=list, description="N2: offers the world makes.")
    expired_lead_ids: list[str] = Field(default_factory=list)
    taken_lead_ids: list[str] = Field(default_factory=list)
    new_goals: list[Goal] = Field(
        default_factory=list, description="N2: only goals the player stated or accepted."
    )
    closed_goals: dict[str, GoalStatus] = Field(
        default_factory=dict,
        description=(
            "N2: goals that are over, by id: the ones the player dropped (abandoned) and the ones "
            "whose lead's thread closed."
        ),
    )


class DirectorPlan(EngineModel):
    event: PlannedEvent | None = None
    happenings: list[PlannedEvent] = Field(
        default_factory=list,
        description="Other things that came due during the turn, such as a festival in a time "
        "skip or an ignored event playing out, for the narrator to mention (W10, E7).",
    )
    callbacks: list[str] = Field(
        default_factory=list, max_length=2, description="Dormant thread ids pulled in (N1)."
    )
    picture: PictureDecision | None = None
    suggestions: SuggestionPlan = Field(default_factory=SuggestionPlan)
    stall_pressure: float = Field(default=0.0, ge=0.0, description="W16, for logs and tuning.")
    updates: DirectorUpdates = Field(default_factory=DirectorUpdates)
