"""Core story models shared by the API, the engine and storage."""

from enum import StrEnum

from pydantic import BaseModel, Field


class CharacterStatus(StrEnum):
    ALIVE = "alive"
    DEAD = "dead"
    MISSING = "missing"


class FactionStance(StrEnum):
    ALLIED = "allied"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"
    DESTROYED = "destroyed"


class Character(BaseModel):
    id: str
    name: str
    description: str = ""
    status: CharacterStatus = CharacterStatus.ALIVE
    # How the character feels about the player, from -100 (hatred) to 100 (devotion).
    affinity: int = 0


class Faction(BaseModel):
    id: str
    name: str
    description: str = ""
    stance: FactionStance = FactionStance.NEUTRAL


class Fact(BaseModel):
    text: str
    turn: int
    # 1 = flavour, 5 = must never be forgotten.
    importance: int = Field(default=3, ge=1, le=5)


class WorldState(BaseModel):
    """Everything the story must remember, beyond the raw scene text."""

    turn: int = 0
    summary: str = ""
    goals: list[str] = []
    characters: list[Character] = []
    factions: list[Faction] = []
    facts: list[Fact] = []


class Choice(BaseModel):
    id: str
    label: str


class Scene(BaseModel):
    turn: int
    player_action: str | None = None
    narration: str
    choices: list[Choice]
    image_prompt: str | None = None
    image_url: str | None = None


class Story(BaseModel):
    id: str
    title: str
    premise: str
    scenes: list[Scene] = []
    state: WorldState = Field(default_factory=WorldState)


class StorySummary(BaseModel):
    id: str
    title: str
    premise: str
    turn: int
