"""Today's endpoints, ported from FastAPI on the same paths and with the same shapes, so the
current app keeps working (WS1). They still run the legacy one-call narrator. WS3 replaces the
turn endpoint with the streamed turn graph from docs/API.md, and the others move to that contract
as the app does.

Stories aren't scoped to their owner yet: sign-in comes with WS6, which adds auth to every
endpoint and filters stories by `owner` (S8).
"""

import uuid
from typing import Literal, Self

from ninja import Field, Router, Schema, Status
from pydantic import BaseModel, model_validator

from legacy.domain import Scene as LegacyScene
from legacy.domain import Story as LegacyStory
from legacy.domain import StorySummary, WorldState
from legacy.premises import SEED_PREMISES, Premise
from lucid import logs
from lucid.errors import ApiError, ErrorCode, version_conflict
from stories import legacy_bridge
from stories.models import InputMode, Scene, SceneKind, Story

premises_router = Router(tags=["premises"])
stories_router = Router(tags=["stories"])

# The legacy narrator reads only the last few scenes (and the turn's choice comes from the last).
RECENT_SCENES = 3
LIBRARY_SIZE = 50


class CreateStoryIn(Schema):
    premise: str = Field(min_length=10, max_length=4000)
    title: str | None = Field(default=None, max_length=120)


class TurnIn(Schema):
    """Either pick one of the offered choices or describe a free action."""

    choice_id: str | None = None
    action: str | None = Field(default=None, min_length=1, max_length=1000)
    # How a free action was entered (V7). A choice is always "choice".
    input_mode: Literal["typed", "voice", "voice_edited"] | None = None
    # The story version the app last saw (T10). Optional here: today's app doesn't send it,
    # and a concurrent turn is refused at save time either way.
    expected_version: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.choice_id is None) == (self.action is None):
            raise ValueError("Send exactly one of choice_id or action")
        return self


class StoryOut(LegacyStory):
    version: int


class TurnOut(BaseModel):
    scene: LegacyScene
    state: WorldState
    version: int


@premises_router.get("", response=list[Premise])
async def list_premises(request) -> list[Premise]:
    return SEED_PREMISES


@stories_router.post("", response={201: StoryOut})
async def create_story(request, body: CreateStoryIn):
    story_id = uuid.uuid4()
    logs.bind(story_id=str(story_id))
    draft = LegacyStory(
        id=str(story_id), title=body.title or _title_from(body.premise), premise=body.premise
    )
    opened = await legacy_bridge.advance(request, draft)
    await legacy_bridge.create_story(story_id, opened)
    return Status(201, StoryOut(**opened.model_dump(), version=1))


@stories_router.get("", response=list[StorySummary])
async def list_stories(request) -> list[StorySummary]:
    """Most recently played first."""
    return [
        StorySummary(id=str(s.id), title=s.title, premise=s.premise, turn=s.turn)
        async for s in Story.objects.order_by("-updated_at")[:LIBRARY_SIZE]
    ]


@stories_router.get("/{story_id}", response=StoryOut)
async def get_story(request, story_id: str) -> StoryOut:
    story = await _load(story_id)
    scenes = [s async for s in Scene.objects.filter(story=story).order_by("turn")]
    return StoryOut(**legacy_bridge.to_legacy(story, scenes).model_dump(), version=story.version)


@stories_router.get("/{story_id}/memory", response=WorldState)
async def get_memory(request, story_id: str) -> WorldState:
    story = await _load(story_id)
    return WorldState.model_validate(story.state or {})


@stories_router.post("/{story_id}/turns", response=TurnOut)
async def take_turn(request, story_id: str, body: TurnIn) -> TurnOut:
    story = await _load(story_id)
    if body.expected_version is not None and body.expected_version != story.version:
        raise version_conflict(story.version)
    recent = [s async for s in Scene.objects.filter(story=story).order_by("-turn")[:RECENT_SCENES]]
    current = legacy_bridge.to_legacy(story, recent[::-1])

    if body.action is not None:
        action = body.action
        kind, input_mode = SceneKind.ACTION, InputMode(body.input_mode or InputMode.TYPED)
    else:
        action = _choice_label(current, body.choice_id)
        kind, input_mode = SceneKind.CHOICE, InputMode.CHOICE

    advanced = await legacy_bridge.advance(request, current, action)
    version = await legacy_bridge.save_turn(story, advanced, kind, input_mode)
    return TurnOut(scene=advanced.scenes[-1], state=advanced.state, version=version)


async def _load(story_id: str) -> Story:
    try:
        pk = uuid.UUID(story_id)
    except ValueError:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.") from None
    story = await Story.objects.filter(pk=pk).afirst()
    if story is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
    return story


def _choice_label(story: LegacyStory, choice_id: str | None) -> str:
    choices = story.scenes[-1].choices if story.scenes else []
    for choice in choices:
        if choice.id == choice_id:
            return choice.label
    raise ApiError(
        ErrorCode.VALIDATION_ERROR,
        "Unknown choice for the current scene.",
        {
            "fields": [
                {
                    "field": "choice_id",
                    "source": "body",
                    "message": "Unknown choice for the current scene",
                    "type": "unknown_choice",
                }
            ]
        },
    )


def _title_from(premise: str) -> str:
    words = premise.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
