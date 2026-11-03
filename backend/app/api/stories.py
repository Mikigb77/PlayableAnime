import uuid
from typing import Annotated, Self

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import get_narrator, get_repository
from app.domain import Scene, Story, WorldState
from app.engine.narrator import Narrator
from app.storage import StoryRepository

router = APIRouter(prefix="/v1/stories", tags=["stories"])

Repository = Annotated[StoryRepository, Depends(get_repository)]
NarratorDep = Annotated[Narrator, Depends(get_narrator)]


class CreateStoryRequest(BaseModel):
    premise: str = Field(min_length=10, max_length=4000)
    title: str | None = Field(default=None, max_length=120)


class StorySummary(BaseModel):
    id: str
    title: str
    premise: str
    turn: int


class TurnRequest(BaseModel):
    """Either pick one of the offered choices or describe a free action."""

    choice_id: str | None = None
    action: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.choice_id is None) == (self.action is None):
            raise ValueError("Send exactly one of choice_id or action")
        return self


class TurnResponse(BaseModel):
    scene: Scene
    state: WorldState


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_story(body: CreateStoryRequest, repo: Repository, narrator: NarratorDep) -> Story:
    story = Story(
        id=uuid.uuid4().hex,
        title=body.title or _title_from(body.premise),
        premise=body.premise,
    )
    story = await narrator.advance(story)
    await repo.save(story)
    return story


@router.get("")
async def list_stories(repo: Repository) -> list[StorySummary]:
    return [
        StorySummary(id=s.id, title=s.title, premise=s.premise, turn=s.state.turn)
        for s in await repo.list()
    ]


@router.get("/{story_id}")
async def get_story(story_id: str, repo: Repository) -> Story:
    return await _load(repo, story_id)


@router.get("/{story_id}/memory")
async def get_memory(story_id: str, repo: Repository) -> WorldState:
    return (await _load(repo, story_id)).state


@router.post("/{story_id}/turns")
async def take_turn(
    story_id: str, body: TurnRequest, repo: Repository, narrator: NarratorDep
) -> TurnResponse:
    story = await _load(repo, story_id)
    action = body.action or _choice_label(story, body.choice_id)
    story = await narrator.advance(story, action)
    await repo.save(story)
    return TurnResponse(scene=story.scenes[-1], state=story.state)


async def _load(repo: StoryRepository, story_id: str) -> Story:
    story = await repo.get(story_id)
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Story not found")
    return story


def _choice_label(story: Story, choice_id: str | None) -> str:
    choices = story.scenes[-1].choices if story.scenes else []
    for choice in choices:
        if choice.id == choice_id:
            return choice.label
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown choice for the current scene"
    )


def _title_from(premise: str) -> str:
    words = premise.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
