"""Who may open a story: only its owner (S8), and only within the account's rating limit (F8)."""

import uuid

from django.db.models import QuerySet
from django.http import HttpRequest

from accounts import rules
from lucid.errors import ApiError, ErrorCode
from stories.models import Engine, Story


def graph_stories() -> QuerySet[Story]:
    """Stories the turn graph plays: not one from the old narrator, whose world state it would
    misread, nor one whose world state was never filled in."""
    return Story.objects.filter(engine=Engine.GRAPH, state__has_key="player_id")


async def owned_story(
    request: HttpRequest, story_id: str, stories: QuerySet[Story] | None = None
) -> Story:
    """The signed-in player's story `story_id`, from `stories` (all stories by default).

    Raises `not_found` when there is no such story, and `forbidden` when it belongs to someone
    else or its rating is above what the account may play (docs/API.md).
    """
    try:
        pk = uuid.UUID(story_id)
    except ValueError:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.") from None
    queryset = stories if stories is not None else Story.objects.all()
    story = await queryset.filter(pk=pk).afirst()
    if story is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
    user = request.auth
    if story.owner_id != user.pk:
        raise ApiError(ErrorCode.FORBIDDEN, "This story belongs to someone else.")
    if not rules.allows_rating(user.birth_date, story.rating):
        raise ApiError(ErrorCode.FORBIDDEN, "This story's rating is above your account's limit.")
    return story
