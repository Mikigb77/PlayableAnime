"""The story endpoints from docs/API.md (Stories, Turns, Memory and status).

Every endpoint needs a signed-in player (T8), and a player sees and plays only their own stories
(S8) within their account's rating limit (F8). A story is made by starting a draft
(`POST /v1/drafts/{id}/start`, WS12) or, in development, by `manage.py seed_story`; its first
turn is `kind: "opening"`. Stories from before the turn graph (`Engine.LEGACY`) are not served.
"""

from asgiref.sync import sync_to_async
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from ninja import Query, Router, Schema
from pydantic import Field

from billing import meter
from engine.context import StorySettings
from engine.state.world import WorldState
from engine.visibility import MemoryView, StatusView
from lucid.errors import field_error, version_conflict
from stories import responses, turns
from stories.access import graph_stories, owned_story
from stories.models import Scene, Story
from stories.schemas import SceneOut, StoryOut, StoryPatch, StorySummaryOut, TurnIn

stories_router = Router(tags=["stories"])

MAX_SCENES = 50


class StoryQuery(Schema):
    scenes: int = Field(default=20, ge=0, le=MAX_SCENES)


class ScenesQuery(Schema):
    before: int | None = Field(default=None, ge=1)
    limit: int = Field(default=20, ge=1, le=MAX_SCENES)


@stories_router.get("", response=list[StorySummaryOut])
async def list_stories(request: HttpRequest) -> list[StorySummaryOut]:
    """The caller's own stories, most recently played first (S8)."""
    stories = responses.with_clock(_stories().filter(owner=request.auth)).order_by("-updated_at")
    rows = [story async for story in stories[: responses.LIBRARY_SIZE]]
    return await sync_to_async(responses.library)(rows, request=request)


@stories_router.get("/{story_id}", response=StoryOut)
async def get_story(request: HttpRequest, story_id: str, query: Query[StoryQuery]) -> StoryOut:
    """The story with its last `scenes` scenes, oldest first."""
    story = await _load(request, story_id)
    return await sync_to_async(_story_out)(story, query.scenes, request)


@stories_router.get("/{story_id}/scenes", response=list[SceneOut])
async def list_scenes(
    request: HttpRequest, story_id: str, query: Query[ScenesQuery]
) -> list[SceneOut]:
    """Older scenes for scrollback: the `limit` scenes before turn `before`, oldest first."""
    story = await _load(request, story_id)
    scenes = Scene.objects.filter(story=story)
    if query.before is not None:
        scenes = scenes.filter(turn__lt=query.before)
    rows = [scene async for scene in scenes.order_by("-turn")[: query.limit]]
    return await sync_to_async(responses.scenes_out)(story, rows[::-1], request=request)


@stories_router.patch("/{story_id}", response=StoryOut)
async def update_story(request: HttpRequest, story_id: str, body: StoryPatch) -> StoryOut:
    """Renames a story or changes its settings (S6). Only what is sent changes. This writes the
    title and settings alone, so it never undoes a turn saved meanwhile (B12, T10)."""
    story = await _load(request, story_id)
    story = await sync_to_async(_patch)(story, body)
    return await sync_to_async(_story_out)(story, StoryQuery().scenes, request)


def _patch(story: Story, body: StoryPatch) -> Story:
    changes = body.settings.model_dump(mode="json", exclude_unset=True) if body.settings else {}
    if body.title is None and not changes:
        return story
    with transaction.atomic():
        # Locked, so two changes sent together both count.
        current = Story.objects.select_for_update().only("settings").get(pk=story.pk)
        fields = []
        if body.title is not None:
            story.title = body.title
            fields.append("title")
        if changes:
            merged = responses.settings_of(current).model_dump(mode="json") | changes
            story.settings = StorySettings.model_validate(merged).model_dump(mode="json")
            fields.append("settings")
        # Not `updated_at`: the Library lists stories by when they were last played.
        story.save(update_fields=fields)
    return story


@stories_router.delete("/{story_id}", response={204: None})
async def delete_story(request: HttpRequest, story_id: str):
    """Deletes the story with its scenes, pending events and pictures."""
    story = await _load(request, story_id)
    await story.adelete()
    return HttpResponse(status=204)


@stories_router.post("/{story_id}/turns")
async def take_turn(request: HttpRequest, story_id: str, body: TurnIn):
    """Plays one turn as server-sent events (B7, S3). See docs/API.md, Turns."""
    story = await _load(request, story_id)
    if body.expected_version != story.version:
        raise version_conflict(story.version)
    byok = _byok(request)
    prepared = await sync_to_async(turns.prepare)(story, body, request.auth)
    ticket = await meter.astart(request.auth, meter.TURN, byok=byok is not None)
    return turns.TurnStream(
        turns.stream(prepared, ticket=ticket, byok=byok, request=request), ticket
    )


@stories_router.get("/{story_id}/memory", response=MemoryView)
async def get_memory(request: HttpRequest, story_id: str) -> MemoryView:
    """What the player character knows, in the world's words (C6)."""
    story = await _load(request, story_id)
    return await sync_to_async(responses.memory_out)(story, request=request)


@stories_router.get("/{story_id}/status", response=StatusView)
async def get_status(request: HttpRequest, story_id: str) -> StatusView:
    """`/status`: the sheet, reputation, the clock and how long ago things happened (A8, G16)."""
    story = await _load(request, story_id)
    return await sync_to_async(responses.status_out)(story, request=request)


def _stories():
    return graph_stories()


async def _load(request: HttpRequest, story_id: str) -> Story:
    return await owned_story(request, story_id, _stories())


def _story_out(story: Story, count: int, request: HttpRequest) -> StoryOut:
    scenes = list(Scene.objects.filter(story=story).order_by("-turn")[:count])[::-1]
    state = WorldState.model_validate(story.state)
    return responses.story_out(story, state, scenes, request=request)


def _byok(request: HttpRequest):
    """The player's own key, for this turn only and never stored or logged (S9, T6)."""
    from graph.llm import UnsupportedProvider, parse_byok

    try:
        return parse_byok(
            request.headers.get("X-LLM-Provider"), request.headers.get("X-LLM-Api-Key")
        )
    except UnsupportedProvider as exc:
        raise field_error(
            "X-LLM-Provider", str(exc), source="header", type="unsupported_provider"
        ) from exc
