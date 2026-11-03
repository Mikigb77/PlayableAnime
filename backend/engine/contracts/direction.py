"""What the director decides (B5 step 3): whether an event comes in, which dormant threads to
call back, the suggestions' shape, and whether the scene gets a picture. All of it is code.

The director decides that something happens and what it is, never how it ends (W16).
"""

from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel
from engine.state.world import EventSize


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
    size: EventSize
    kind: EventKind
    source: EventSource
    source_id: str | None = Field(default=None, description="The clock, thread or event behind it.")
    title: str
    brief: str = Field(description="What happens, for the narrator to tell in the world's form.")
    themes: list[Theme] = Field(default_factory=list)
    thread_id: str | None = Field(default=None, description="The thread it opens or continues.")
    needs_decision: bool = True


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
    BIG_DEED = "big_deed"  # a deed of severity 4 or 5 (W1)
    EVENT = "event"  # a local or world event arriving (W16)
    BREAKTHROUGH = "breakthrough"  # G19
    STRENGTH_REVEALED = "strength_revealed"  # G20
    DEATH = "death"  # a key character's death (N1)
    ARC_END = "arc_end"  # N1
    FIGHT_START = "fight_start"  # a fight with a key NPC or a strong monster (Miki, 2026-11-03)
    DECISIVE_BLOW = "decisive_blow"  # that fight's decisive blow
    COVER = "cover"  # the Library cover


class PictureDecision(EngineModel):
    """M1, M2. Within the story's budget and its picture setting. The narrator writes an image
    prompt only when this is set."""

    kind: PictureKind
    trigger: PictureTrigger
    subject_id: str | None = Field(default=None, description="The character, place or deed.")
    reason: str = ""


class ChoiceKind(StrEnum):
    """S2. Suggestions, at least one of them away from the current thread."""

    THREAD = "thread"
    PERSONAL = "personal"
    SIDE = "side"
    WILD = "wild"


class SuggestionPlan(EngineModel):
    """S2. How many suggestions the narrator writes (0 to 4) and of which kinds. Wait and observe
    are always offered on top."""

    count: int = Field(default=3, ge=0, le=4)
    kinds: list[ChoiceKind] = Field(
        default_factory=lambda: [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE]
    )


class DirectorPlan(EngineModel):
    event: PlannedEvent | None = None
    callbacks: list[str] = Field(
        default_factory=list, max_length=2, description="Dormant thread ids pulled in (N1)."
    )
    picture: PictureDecision | None = None
    suggestions: SuggestionPlan = Field(default_factory=SuggestionPlan)
    stall_pressure: float = Field(default=0.0, ge=0.0, description="W16, for logs and tuning.")
