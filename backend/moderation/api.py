"""`POST /v1/stories/{id}/scenes/{turn}/report` from docs/API.md (F6).

Every scene can be reported, and blocked so its text is hidden in the app at once. Only the
story's owner can report its scenes, within their account's rating limit like every story
endpoint (S8, F8).
"""

from typing import Literal

from django.http import HttpRequest
from ninja import Field, Router, Schema, Status

from lucid.errors import ApiError, ErrorCode
from moderation.service import areport_scene
from stories.access import owned_story
from stories.models import Scene

reports_router = Router(tags=["reports"])

MAX_NOTE_CHARS = 1000


class ReportIn(Schema):
    category: Literal["sexual", "minor", "hate", "real_person", "self_harm", "other"]
    note: str | None = Field(default=None, max_length=MAX_NOTE_CHARS)
    # True hides the scene's text in the app at once (F6).
    block: bool = False


@reports_router.post("/{story_id}/scenes/{turn}/report", response={204: None})
async def report_scene(request: HttpRequest, story_id: str, turn: int, body: ReportIn):
    story = await owned_story(request, story_id)
    scene = await Scene.objects.filter(story=story, turn=turn).afirst()
    if scene is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Scene not found.")
    await areport_scene(
        story,
        scene,
        request.auth,
        category=body.category,
        note=(body.note or "").strip(),
        block=body.block,
    )
    return Status(204, None)
