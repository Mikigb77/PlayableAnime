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
from stories.endings import EndingOut
from stories.succession import HeirOut, SuccessorOut

ACTION_CHARS = 2000
TITLE_CHARS = 120


class TurnIn(BaseModel):
    """API.md's `TurnRequest`. Each kind takes its own field and no other: `action` for an
    action, `choice_id` for a choice, `standing` for a standing action, and none for the opening.
    An end turn (N6) takes an optional `action`, the note on how the story should end, and
    `drop_refused` to end without what the world refused of it.
    """

    kind: TurnKind
    action: str | None = Field(default=None, max_length=ACTION_CHARS)
    choice_id: str | None = Field(default=None, min_length=1, max_length=32)
    standing: StandingAction | None = None
    # How the action was entered (V7). Optional: an action defaults to typed, and a choice or a
    # standing action is always `choice`.
    input_mode: Literal["typed", "voice", "voice_edited", "choice"] | None = None
    # N6, an end turn only: tell the epilogue without the parts of the note the world refused.
    drop_refused: bool = False
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
            TurnKind.END: "action",
        }[self.kind]
        optional = self.kind is TurnKind.END  # an ending's note is optional
        for name in ("action", "choice_id", "standing"):
            given = getattr(self, name) is not None
            if name == wanted and not given and not optional:
                raise ValueError(f"A {self.kind} turn needs {name}.")
            if name != wanted and given:
                raise ValueError(f"A {self.kind} turn takes no {name}.")
        if self.kind in (TurnKind.ACTION, TurnKind.END) and self.input_mode == "choice":
            raise ValueError(f"A {self.kind} turn is typed or spoken: input_mode can't be choice.")
        if self.drop_refused and self.kind is not TurnKind.END:
            raise ValueError("Only an end turn takes drop_refused.")
        return self

    @property
    def mode(self) -> str | None:
        """The input mode saved on the scene."""
        if self.kind is TurnKind.OPENING or (self.kind is TurnKind.END and self.action is None):
            return None
        if self.kind in (TurnKind.ACTION, TurnKind.END):
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

    @model_validator(mode="after")
    def _no_nulls(self) -> Self:
        """Leave a field out to keep it. Only `tone` can be cleared, with null."""
        cleared = [
            name for name in self.model_fields_set if name != "tone" and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(sorted(cleared))} can't be null: leave it out instead.")
        return self


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
    # The player blocked this scene (F6), so the app shows a placeholder instead of its text.
    blocked: bool = False
    created_at: datetime


class StorySummaryOut(BaseModel):
    id: str
    title: str
    genre: str
    rating: str
    turn: int
    world_time_label: str
    cover_url: str | None = None
    # N6: set once the story has reached its ending.
    ending: EndingOut | None = None
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
    # What the story started from, so the app can start again from it (N6).
    premise: str = ""
    # N6: set once the story has reached its ending. Then it takes no more turns.
    ending: EndingOut | None = None
    # N6: the person last drawn to carry the story on from its ending, if any.
    successor: SuccessorOut | None = None
    # N6: who of the player character's family can carry the story on from its ending.
    heirs: list[HeirOut] = Field(default_factory=list)
    # N6: someone new carries the story on, and their opening is the next turn.
    opening_due: bool = False
