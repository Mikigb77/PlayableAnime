"""The shapes of the story endpoints, as docs/API.md writes them (Stories, Turns, Scene)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from engine.context import (
    Difficulty,
    EventFrequency,
    ImageSetting,
    NarrationLength,
    StorySettings,
)
from engine.contracts import StandingAction
from engine.visibility import ClockView
from graph.turn import TurnKind

ACTION_CHARS = 2000
TITLE_CHARS = 120


class TurnIn(BaseModel):
    """API.md's `TurnRequest`. Each kind takes its own field and no other: `action` for an
    action, `choice_id` for a choice, `standing` for a standing action, and none for the opening.
    """

    kind: TurnKind
    action: str | None = Field(default=None, max_length=ACTION_CHARS)
    choice_id: str | None = Field(default=None, min_length=1, max_length=32)
    standing: StandingAction | None = None
    # How the action was entered (V7). Optional: an action defaults to typed, and a choice or a
    # standing action is always `choice`.
    input_mode: Literal["typed", "voice", "voice_edited", "choice"] | None = None
    # The story version the app last saw (T10).
    expected_version: int = Field(ge=0)

    @field_validator("action")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("The action is blank.")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _fields_for_kind(self) -> Self:
        wanted = {
            TurnKind.ACTION: "action",
            TurnKind.CHOICE: "choice_id",
            TurnKind.STANDING: "standing",
            TurnKind.OPENING: None,
        }[self.kind]
        for name in ("action", "choice_id", "standing"):
            given = getattr(self, name) is not None
            if name == wanted and not given:
                raise ValueError(f"A {self.kind} turn needs {name}.")
            if name != wanted and given:
                raise ValueError(f"A {self.kind} turn takes no {name}.")
        if self.kind is TurnKind.ACTION and self.input_mode == "choice":
            raise ValueError("An action is typed or spoken: input_mode can't be choice.")
        return self

    @property
    def mode(self) -> str | None:
        """The input mode saved on the scene."""
        if self.kind is TurnKind.OPENING:
            return None
        if self.kind is TurnKind.ACTION:
            return self.input_mode or "typed"
        return "choice"


class SettingsPatch(BaseModel):
    """Part of `StorySettings`: only the fields sent change (S6)."""

    narration_length: NarrationLength | None = None
    tone: str | None = Field(default=None, max_length=200)
    difficulty: Difficulty | None = None
    event_frequency: EventFrequency | None = None
    images: ImageSetting | None = None
    suggestions: bool | None = None


class StoryPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_CHARS)
    settings: SettingsPatch | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("The title is blank.")
        return " ".join(value.split()) if value is not None else None


class ChoiceOut(BaseModel):
    id: str
    label: str
    kind: str


class SceneTimeOut(BaseModel):
    world_start_s: int
    world_end_s: int
    label: str
    duration_label: str
    personal_label: str | None = None


class SceneImageOut(BaseModel):
    """`SceneImage`: `planned` until the picture is drawn, so the app asks for it (M3)."""

    planned: bool
    kind: Literal["portrait", "place", "scene", "cover"]
    status: Literal["planned", "ready", "skipped"]
    image_id: str | None = None
    url: str | None = None
    expires_at: datetime | None = None


class PortraitOut(BaseModel):
    character_id: str
    name: str
    url: str | None = None


class SceneOut(BaseModel):
    """API.md's `Scene`."""

    turn: int
    kind: TurnKind
    player_action: str | None = None
    input_mode: str | None = None
    narration: str
    choices: list[ChoiceOut] = Field(default_factory=list)
    standing_actions: list[StandingAction] = Field(
        default_factory=lambda: [StandingAction.WAIT, StandingAction.OBSERVE]
    )
    time: SceneTimeOut
    # `SceneDetails`, saved in API.md's shape: steps with class, reason and roll, the chain, and
    # where a chained plan stopped (A2, A8, A9, R6).
    details: dict[str, Any] = Field(default_factory=dict)
    event: dict[str, Any] | None = None
    image: SceneImageOut | None = None
    portraits: list[PortraitOut] = Field(default_factory=list)
    created_at: datetime


class StorySummaryOut(BaseModel):
    id: str
    title: str
    genre: str
    rating: str
    turn: int
    world_time_label: str
    cover_url: str | None = None
    updated_at: datetime


class StoryOut(BaseModel):
    """API.md's `Story`, with the last scenes. `turn` is 0 until the opening is played."""

    id: str
    title: str
    genre: str
    rating: str
    version: int
    turn: int
    settings: StorySettings
    clock: ClockView
    scenes: list[SceneOut] = Field(default_factory=list)
    cover_url: str | None = None
