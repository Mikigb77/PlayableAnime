"""The world state (C2): everything the story must remember, beyond the scene text."""

import re
from enum import StrEnum

from pydantic import Field, model_validator

from engine.base import MAIN_TIMELINE, EngineModel, WorldSeconds
from engine.state.bible import WorldBible
from engine.state.cast import Character, Faction, Place
from engine.state.records import (
    Clock,
    Deed,
    EventStatus,
    Fact,
    Goal,
    Lead,
    PendingEvent,
    Rumor,
    Thread,
)
from engine.state.scene import SceneFrame
from engine.state.sheet import TimeEffect

SCHEMA_VERSION = 1


class ActiveTimeEffect(EngineModel):
    """W10a. A time power in effect right now, such as a stop that spans more than one turn. While
    a stop is on, the world clock stands still and no pending event fires."""

    character_id: str
    power_id: str
    effect: TimeEffect
    started_personal_s: int
    ends_personal_s: int | None = None


class EventSize(StrEnum):
    """W16, E4."""

    PERSONAL = "personal"
    LOCAL = "local"
    WORLD = "world"


class KeyFight(EngineModel):
    """M1. A fight with a key NPC or a strong monster that the director is following, so it
    pictures the fight's start and its decisive blow once each, even after the encounter ends."""

    opponent_ids: list[str] = Field(default_factory=list)
    started_turn: int = Field(ge=0)
    start_pictured: bool = False
    blow_pictured: bool = False


class DirectorState(EngineModel):
    """W16, E6, M2. What the director remembers between turns. Turns count only the player's
    attention and cost (W10), so these are the only turn counters in the state.

    `engine.director` reads it and `record_direction` writes it back from the plan."""

    turns_without_stakes: int = Field(default=0, ge=0)
    low_stakes_streak: int = Field(default=0, ge=0)
    last_action_key: str | None = Field(
        default=None, description="The last low-stakes action, to spot repeats (W16)."
    )
    last_event_turn: int | None = None
    last_event_size: EventSize | None = None
    frequency_drift: float = Field(default=0.0, ge=-1.0, le=1.0)
    recent_sources: list[str] = Field(
        default_factory=list,
        description="The last few event sources (deck cards, NPCs, threads), newest last, so the "
        "same one isn't drawn again straight away.",
    )
    auto_pictures: int = Field(default=0, ge=0, description="Automatic pictures so far (M2).")
    picture_credit: float = Field(
        default=1.0,
        ge=-3.0,
        le=5.0,
        description="M2: the key-scene budget, refilled a little each turn. Fights may borrow.",
    )
    pictured: list[str] = Field(
        default_factory=list,
        description="Subjects that already got their automatic picture: 'portrait:<id>', "
        "'place:<id>', 'place:<id>:<status>', 'cover' (M1, M4).",
    )
    fight: KeyFight | None = None
    deck_draws: int = Field(default=0, ge=0)


class Chapter(EngineModel):
    """C3. A summary every N turns (about 20), so older scenes leave the prompt but aren't lost.
    Chapters are named afterwards (N1)."""

    index: int = Field(ge=1)
    from_turn: int = Field(ge=0)
    to_turn: int = Field(ge=0)
    summary: str
    title: str | None = None


class WorldState(EngineModel):
    """C2. Characters, factions, places, the player sheet, deeds, rumors, facts, goals and leads,
    threads, clocks and pending events, the world clock and timeline, and a rolling summary.

    Collections are keyed by id, and each record's `id` must match its key. Never rely on their
    order: Postgres JSONB reorders object keys, so sort by id or time where order matters. The
    player character is in `characters` under `player_id`. Rolls are recorded on each scene's
    resolution with their seeds (A3), so they are not repeated here. The summary is flavour only;
    anything that must not be lost lives in the structured records.
    """

    schema_version: int = SCHEMA_VERSION
    turn: int = Field(default=0, ge=0, description="The last completed turn.")
    timeline_id: str = MAIN_TIMELINE
    world_s: WorldSeconds = 0
    bible: WorldBible = Field(default_factory=WorldBible)
    player_id: str
    characters: dict[str, Character]
    factions: dict[str, Faction] = Field(default_factory=dict)
    places: dict[str, Place] = Field(default_factory=dict)
    deeds: dict[str, Deed] = Field(default_factory=dict)
    rumors: dict[str, Rumor] = Field(default_factory=dict)
    facts: dict[str, Fact] = Field(default_factory=dict)
    goals: dict[str, Goal] = Field(default_factory=dict)
    leads: dict[str, Lead] = Field(default_factory=dict)
    threads: dict[str, Thread] = Field(default_factory=dict)
    clocks: dict[str, Clock] = Field(default_factory=dict)
    pending_events: dict[str, PendingEvent] = Field(default_factory=dict)
    time_effects: list[ActiveTimeEffect] = Field(default_factory=list)
    scene: SceneFrame = Field(default_factory=SceneFrame)
    director: DirectorState = Field(default_factory=DirectorState)
    summary: str = ""
    chapters: list[Chapter] = Field(default_factory=list)
    id_counters: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _keys_match_ids(self) -> "WorldState":
        if self.schema_version > SCHEMA_VERSION:
            # An older engine would drop the fields it doesn't know and save the stripped state
            # back, for instance during a rolling deploy. Refuse instead.
            raise ValueError(
                f"state schema {self.schema_version} is newer than this engine's {SCHEMA_VERSION}"
            )
        for field in _KEYED_COLLECTIONS:
            for key, record in getattr(self, field).items():
                if key != record.id:
                    raise ValueError(f"{field}[{key!r}] holds a record with id {record.id!r}")
        if self.player_id not in self.characters:
            raise ValueError(f"the player character {self.player_id!r} is not in characters")
        return self

    @property
    def player(self) -> Character:
        return self.characters[self.player_id]

    def npcs(self) -> list[Character]:
        """Every character except the player's."""
        return [c for c in self.characters.values() if c.id != self.player_id]

    def new_id(self, prefix: str) -> str:
        """A fresh id such as `deed-3`, unique within this story and stable on replay.

        It mutates `id_counters`, so call it on the copy being built, never on a saved state.
        """
        number = self.id_counters.get(prefix, 0) + 1
        self.id_counters[prefix] = number
        record_id = f"{prefix}-{number}"
        while any(record_id in getattr(self, f) for f in _KEYED_COLLECTIONS):
            number += 1
            self.id_counters[prefix] = number
            record_id = f"{prefix}-{number}"
        return record_id

    def due_events(self, until_s: int) -> list[PendingEvent]:
        """Pending events on the current timeline due at or before `until_s`, in time order.

        Ties go to the event scheduled first, then by id. Map order is never used, because
        Postgres JSONB doesn't keep the order of object keys.
        """
        due = [
            e
            for e in self.pending_events.values()
            if e.status is EventStatus.PENDING
            and e.timeline_id == self.timeline_id
            and e.due_s <= until_s
        ]
        return sorted(due, key=lambda e: (e.due_s, e.created_turn, e.created_s, natural_key(e.id)))


def natural_key(record_id: str) -> tuple:
    """Sorts `deed-9` before `deed-10`."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", record_id))


_KEYED_COLLECTIONS = (
    "characters",
    "factions",
    "places",
    "deeds",
    "rumors",
    "facts",
    "goals",
    "leads",
    "threads",
    "clocks",
    "pending_events",
)
