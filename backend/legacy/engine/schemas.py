"""Structured output the narrator model must return each turn."""

from pydantic import BaseModel, Field

from legacy.domain import CharacterStatus, FactionStance


class CharacterChange(BaseModel):
    id: str
    # Required when introducing a new character, optional otherwise.
    name: str | None = None
    description: str | None = None
    status: CharacterStatus | None = None
    affinity_delta: int = 0


class FactionChange(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    stance: FactionStance | None = None


class NewFact(BaseModel):
    text: str
    importance: int = Field(default=3, ge=1, le=5)


class StateUpdate(BaseModel):
    characters: list[CharacterChange] = []
    factions: list[FactionChange] = []
    new_facts: list[NewFact] = []
    # None means the goals did not change this turn.
    goals: list[str] | None = None
    summary: str = ""


class NarratorOutput(BaseModel):
    narration: str
    choices: list[str]
    image_prompt: str | None = None
    state_update: StateUpdate
