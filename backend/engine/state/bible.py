"""The world bible: what is real in a world and which rules never change (G6, G7)."""

from enum import StrEnum

from pydantic import Field

from engine.base import DAY, EngineModel, Name, Tier
from engine.state.sheet import PowerAxis


class Prevalence(StrEnum):
    """How common an extraordinary thing is (G6)."""

    NONE = "none"  # a grounded story
    HIDDEN = "hidden"  # a modern city with secret vampires
    RARE = "rare"
    COMMON = "common"  # everywhere


class PhysicsMode(StrEnum):
    """A9. Fun first bends physics wherever that is more fun; strict is rougher and more
    physically coherent. Fun first is the default."""

    FUN_FIRST = "fun_first"
    STRICT = "strict"


class RuleTopic(StrEnum):
    """Which part of G6 a rule is about."""

    EXISTENCE = "existence"  # whether something extraordinary exists at all
    LIMITS = "limits"  # how far an ability can go (A4)
    NATURE = "nature"  # where physics, chemistry or biology differ (A9)
    TECHNOLOGY = "technology"
    PEOPLES = "peoples"
    TRAVEL = "travel"
    MEDICINE = "medicine"
    LAW = "law"
    OTHER = "other"


class WorldRule(EngineModel):
    """G7. A fixed rule holds for the whole story; an open rule changes only through a discovery
    made in the story, and then for everyone. By default whether something extraordinary exists
    is fixed and how far it can go is open."""

    id: str
    text: str
    fixed: bool
    topic: RuleTopic = RuleTopic.OTHER


class Extraordinary(EngineModel):
    """G6. One kind of extraordinary thing the world holds, such as magic, qi, psychic powers,
    cybernetics or an in-world system with status windows."""

    id: str
    kind: str
    prevalence: Prevalence
    reach: str = Field(default="", description="How far it can go, in plain words (A4).")
    rule_ids: list[str] = Field(default_factory=list)


class People(EngineModel):
    """G23. A race or people: body and gifts, culture, relations and its own path to power."""

    id: str
    name: Name
    description: str = ""
    lifespan_years: int | None = Field(default=None, ge=0)
    gifts: list[str] = Field(default_factory=list)
    culture: str = ""
    relations: list[str] = Field(default_factory=list)
    path: str = Field(default="", description="Its own path on the ladder (G18).")


class Creature(EngineModel):
    """G24. A kind of monster or beast: where it stands, where it lives and what it is worth."""

    id: str
    name: Name
    description: str = ""
    tier: Tier = 1
    habitat: str = ""
    worth: str = Field(default="", description="Cores, hides, blood or bones (G19, G24).")
    can_be_tamed: bool = False


class Rung(EngineModel):
    """A rung on a power ladder, named in the world's words, mapped to an A8 tier."""

    name: Name
    tier: Tier
    description: str = ""


class PowerLadder(EngineModel):
    """G18. Cultivation realms, aura ranks, adventurer ranks or numbered levels. Rungs go from
    lowest to highest."""

    id: str
    name: Name
    axis: PowerAxis = PowerAxis.MIGHT
    rungs: list[Rung] = Field(min_length=1)
    standing_follows: bool = Field(
        default=True, description="Whether a higher rung means a senior's respect (G18)."
    )
    sensing: bool = Field(
        default=False, description="Whether characters sense strength up to their own rung (G20)."
    )


class CalendarStyle(StrEnum):
    """How the world names its dates (W10). Labels are made in `engine.labels` (PR 2)."""

    GREGORIAN = "gregorian"  # "14 May 1974, 23:10"
    DAY_COUNT = "day_count"  # "Day 3, dusk"
    CUSTOM = "custom"  # "3rd day of the Frost Moon, year 412, dusk"


class TimeOfDayStyle(StrEnum):
    CLOCK = "clock"  # 23:10
    PARTS = "parts"  # dawn, morning, midday, afternoon, dusk, evening, night


class Month(EngineModel):
    name: Name
    days: int = Field(ge=1, le=400)


class Calendar(EngineModel):
    """The world's own calendar. The story's epoch (world second 0) is when the story opens.

    - Gregorian: `epoch` is an ISO date and time, such as `1974-05-14T21:00`.
    - Day count: day 1 starts at the epoch, `start_second_of_day` after midnight.
    - Custom: `months`, starting at `start_year`, `start_month` and `start_day`, with `era` after
      the year number.
    """

    style: CalendarStyle = CalendarStyle.DAY_COUNT
    time_of_day: TimeOfDayStyle = TimeOfDayStyle.PARTS
    epoch: str | None = None
    start_second_of_day: int = Field(default=8 * 3600, ge=0, lt=DAY)
    months: list[Month] = Field(default_factory=list)
    start_year: int = 1
    start_month: int = Field(default=1, ge=1)
    start_day: int = Field(default=1, ge=1)
    era: str = ""


class Travel(EngineModel):
    """G6, W10. How people and news travel. Travel times between places sit on `Place.routes`."""

    description: str = ""
    instant_messages: bool = Field(
        default=False, description="Phones or the like: a witness can call within seconds."
    )


class Resurrection(StrEnum):
    """G6, C1. Whether anything can bring back the dead."""

    NONE = "none"
    RARE = "rare"
    POSSIBLE = "possible"


class Medicine(EngineModel):
    """G6. How wounds heal and how long that takes, and whether the dead can come back."""

    healing: str = ""
    resurrection: Resurrection = Resurrection.NONE
    resurrection_means: str = ""


class Zeal(StrEnum):
    """W11. How hard a law's enforcers try."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Law(EngineModel):
    """W11. A law or custom, who enforces it and how hard they try."""

    id: str
    text: str
    enforcer: str = ""
    enforcer_faction_id: str | None = None
    zeal: Zeal = Zeal.MEDIUM
    corruptible: bool = False


class Mystery(EngineModel):
    """N7. A major mystery is decided when it is created, answer and clues, so investigations stay
    fair. The answer is hidden from the player (C6) until the thread closes."""

    id: str
    question: str
    answer: str
    clues: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    solved: bool = False


class WorldBible(EngineModel):
    """G6. What is real in the world, drafted from the premise (G1) and grown in play (N7)."""

    title: str = ""
    genre: str = ""
    tone: str = Field(default="", description="The voice the narration takes (G5).")
    era: str = Field(default="", description="Era and technology (G6).")
    extraordinary: list[Extraordinary] = Field(default_factory=list)
    peoples: list[People] = Field(default_factory=list)
    creatures: list[Creature] = Field(default_factory=list)
    nature: list[str] = Field(
        default_factory=list, description="Where nature works differently from ours (A9)."
    )
    physics: PhysicsMode = PhysicsMode.FUN_FIRST
    ladders: list[PowerLadder] = Field(default_factory=list)
    calendar: Calendar = Field(default_factory=Calendar)
    travel: Travel = Field(default_factory=Travel)
    medicine: Medicine = Field(default_factory=Medicine)
    laws: list[Law] = Field(default_factory=list)
    norms: list[str] = Field(
        default_factory=list, description="What the world finds monstrous or normal (W12)."
    )
    rules: list[WorldRule] = Field(default_factory=list)
    mysteries: list[Mystery] = Field(default_factory=list)

    def rule(self, rule_id: str) -> WorldRule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def ladder(self, ladder_id: str) -> PowerLadder | None:
        return next((ladder for ladder in self.ladders if ladder.id == ladder_id), None)

    @property
    def grounded(self) -> bool:
        """True when nothing extraordinary exists in this world at all (G8)."""
        return all(e.prevalence is Prevalence.NONE for e in self.extraordinary)
