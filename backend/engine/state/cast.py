"""Characters, factions and places: the world's cast and map (C2, W3, W4, W7, W15)."""

from enum import StrEnum

from pydantic import Field, model_validator

from engine.base import Affinity, EngineModel, Esteem, Fear, Name, Percent, Seconds
from engine.state.records import Origin, StatusChange
from engine.state.sheet import Attitude, CharacterSheet


class Activity(StrEnum):
    """W15. Active characters and factions are simulated each tick and eligible for scenes;
    dormant ones are kept and advanced only by their clocks; archived ones are kept, untouched.
    The active cast is capped (8 key NPCs and 4 factions to start, K8)."""

    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"


class Reputation(EngineModel):
    """W3. Two separate axes: a feared tyrant has high fear and low esteem."""

    esteem: Esteem = 0
    fear: Fear = 0


class CharacterStatus(StrEnum):
    ALIVE = "alive"
    MISSING = "missing"  # whereabouts unknown, not presumed dead
    DEAD = "dead"


class DeathCertainty(StrEnum):
    """C1. Only a presumed death can later turn out false."""

    CONFIRMED = "confirmed"  # the body was seen destroyed or buried
    PRESUMED = "presumed"  # a fall with no body found


class Prominence(StrEnum):
    """W15. Key NPCs get the full sheet; minor ones a line or two."""

    KEY = "key"
    MINOR = "minor"


class Membership(EngineModel):
    """G10, N9. A place in a faction, with its rank and the member's loyalty (W14)."""

    faction_id: str
    rank: str = ""
    loyalty: Percent = 50


class Agenda(EngineModel):
    """E3 (P1). A key NPC's goal, method and secret, and the clock for their plan."""

    goal: str
    method: str = ""
    secret: str = ""
    clock_id: str | None = None


class Character(EngineModel):
    """Anyone in the world, the player character included: the same parts in every genre (G13).

    The personal clock (W10a) is `world_s + personal_offset_s`. It moves with the world clock
    unless a time power changes the offset: time stop adds the user's lived seconds while the
    world stands still, and travel to the future subtracts the world's seconds the traveller
    skipped.
    """

    id: str
    name: Name
    aliases: list[str] = Field(default_factory=list)
    prominence: Prominence = Prominence.MINOR
    description: str = Field(default="", description="How they come across to anyone who meets.")
    appearance: str = Field(default="", description="Kept for portraits (C9, M5).")
    look_version: int = Field(
        default=1,
        ge=1,
        description="M5: moves on each time the look changes for good (`engine.looks`), so the "
        "portrait is drawn once more.",
    )
    age: int | None = Field(default=None, ge=0, description="Years; adults need one (F3).")
    people_id: str | None = Field(default=None, description="Their race, from the bible (G23).")
    status: CharacterStatus = CharacterStatus.ALIVE
    death_certainty: DeathCertainty | None = None
    status_history: list[StatusChange] = Field(default_factory=list)
    activity: Activity = Activity.ACTIVE
    location_id: str | None = None
    personal_offset_s: int = 0
    memberships: list[Membership] = Field(default_factory=list)
    sheet: CharacterSheet = Field(default_factory=CharacterSheet)
    agenda: Agenda | None = None
    secrets: list[str] = Field(default_factory=list)
    origin: Origin | None = None
    known_by: list[str] = Field(default_factory=list)
    met_by: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _death_has_certainty(self) -> "Character":
        if (self.status is CharacterStatus.DEAD) != (self.death_certainty is not None):
            raise ValueError("a dead character needs a death certainty, and only a dead one")
        return self

    @property
    def alive(self) -> bool:
        return self.status is not CharacterStatus.DEAD

    def personal_s(self, world_s: int) -> int:
        """Seconds this character has lived since the story's epoch (W10a)."""
        return world_s + self.personal_offset_s

    def attitude_toward(self, character_id: str) -> Attitude:
        """The attitude toward another character, or a neutral one if none is recorded yet."""
        return self.sheet.disposition.attitudes.get(character_id) or Attitude()

    def member_of(self, faction_id: str) -> bool:
        return any(m.faction_id == faction_id for m in self.memberships)


class FactionStatus(StrEnum):
    INTACT = "intact"
    WEAKENED = "weakened"
    REBUILDING = "rebuilding"  # W15a: a revival starts weak, with its old grudges intact
    DESTROYED = "destroyed"


class Faction(EngineModel):
    """A family, sect, kingdom, crew, fleet or company. Factions can sit inside larger ones (G10).

    `player_reputation` is the player's esteem and fear with this faction (W3). `threat` is how
    much of a threat the faction thinks the player is (W5), an input to its own agenda.
    `survivors` lists what could carry it on if it is destroyed (W15a), beyond living members.
    """

    id: str
    name: Name
    kind: str = ""
    description: str = ""
    parent_id: str | None = None
    status: FactionStatus = FactionStatus.INTACT
    status_history: list[StatusChange] = Field(default_factory=list)
    activity: Activity = Activity.ACTIVE
    leader_ids: list[str] = Field(default_factory=list)
    goal: str = ""
    methods: str = ""
    strength: str = Field(default="", description="What it really has to answer with (W5, A9).")
    player_reputation: Reputation = Field(default_factory=Reputation)
    threat: int = Field(default=0, ge=0, le=5)
    relations: dict[str, Affinity] = Field(
        default_factory=dict, description="Stance toward other factions by id, -100 to 100."
    )
    survivors: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    origin: Origin | None = None
    known_by: list[str] = Field(default_factory=list)


class PlaceStatus(StrEnum):
    """W7. A ruined place stays ruined unless someone rebuilds it (C1)."""

    THRIVING = "thriving"
    DAMAGED = "damaged"
    RUINED = "ruined"
    OCCUPIED = "occupied"


class Route(EngineModel):
    """W7, W10. A rough travel time to a neighbouring place."""

    to_id: str
    travel_s: Seconds
    mode: str = ""


class Place(EngineModel):
    """W7. Places have a status, a controller, a mood, a stability and travel times to their
    neighbours. Regions carry the player's reputation there (W3)."""

    id: str
    name: Name
    kind: str = Field(default="", description="region, city, village, building, room, wilds")
    description: str = ""
    parent_id: str | None = None
    status: PlaceStatus = PlaceStatus.THRIVING
    status_history: list[StatusChange] = Field(default_factory=list)
    controller_id: str | None = None
    mood: str = ""
    stability: Percent = 70
    routes: list[Route] = Field(default_factory=list)
    player_reputation: Reputation = Field(default_factory=Reputation)
    known_by: list[str] = Field(default_factory=list)
    visited_by: list[str] = Field(default_factory=list)

    def travel_s_to(self, place_id: str) -> int | None:
        return next((r.travel_s for r in self.routes if r.to_id == place_id), None)
