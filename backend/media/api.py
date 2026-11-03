"""The picture endpoints from docs/API.md (M1 to M8).

The scene says when a picture is planned. The app shows the text first, then asks for the picture
here in its own request (M3, B8). Asking again is always safe: a picture is drawn and charged at
most once, a repeat while it is drawn answers `pending`, and a picture that failed, was blocked or
couldn't be paid for answers `skipped`, which the app shows as no picture at all.
"""

import uuid
from datetime import datetime
from typing import Literal

from django.http import HttpRequest
from ninja import Router, Schema

from lucid.errors import ApiError, ErrorCode, field_error
from media.models import Image
from media.service import PictureResult, result_for, scene_picture
from stories.models import Scene, Story

media_router = Router(tags=["pictures"])


class PictureOut(Schema):
    status: Literal["ready", "pending", "skipped"]
    # Ask `GET /v1/stories/{id}/images/{image_id}` for a fresh URL once `expires_at` passes.
    image_id: str | None = None
    kind: Literal["portrait", "place", "scene", "cover"] | None = None
    url: str | None = None
    expires_at: datetime | None = None


@media_router.post("/{story_id}/scenes/{turn}/image", response=PictureOut)
async def scene_image(request: HttpRequest, story_id: str, turn: int) -> PictureOut:
    """The picture code planned for this scene (M1), drawn now if it isn't yet."""
    return await _scene_picture(request, story_id, turn, illustrate=False)


@media_router.post("/{story_id}/scenes/{turn}/illustrate", response=PictureOut)
async def illustrate_scene(request: HttpRequest, story_id: str, turn: int) -> PictureOut:
    """A picture of any scene, which the player asked and pays for (M2)."""
    return await _scene_picture(request, story_id, turn, illustrate=True)


@media_router.get("/{story_id}/images/{image_id}", response=PictureOut)
async def get_image(request: HttpRequest, story_id: str, image_id: str) -> PictureOut:
    """A picture's state, with a fresh signed URL when it is ready."""
    story = await owned_story(request, story_id)
    image = await Image.objects.filter(pk=_uuid(image_id, "Picture"), story=story).afirst()
    if image is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Picture not found.")
    return _out(request, await result_for(image))


async def _scene_picture(
    request: HttpRequest, story_id: str, turn: int, *, illustrate: bool
) -> PictureOut:
    story = await owned_story(request, story_id)
    provider, key = _byok(request)
    scene = await Scene.objects.filter(story=story, turn=turn).afirst()
    if scene is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Scene not found.")
    result = await scene_picture(
        story,
        scene,
        user=caller(request),
        illustrate=illustrate,
        byok_provider=provider,
        byok_key=key,
    )
    return _out(request, result)


def caller(request: HttpRequest):
    """The signed-in user (WS6 sets `request.auth`), or None before sign-in exists."""
    from accounts.models import User

    user = getattr(request, "auth", None)
    return user if isinstance(user, User) else None


async def owned_story(request: HttpRequest, story_id: str) -> Story:
    """The story, if the caller may see it: 404 when it doesn't exist, 403 when it belongs to
    someone else (S8). A story from before sign-in has no owner."""
    story = await Story.objects.filter(pk=_uuid(story_id)).afirst()
    if story is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Story not found.")
    user = caller(request)
    if story.owner_id is not None and (user is None or user.pk != story.owner_id):
        raise ApiError(ErrorCode.FORBIDDEN)
    return story


def _byok(request: HttpRequest) -> tuple[str | None, str | None]:
    """The player's own key, used for this picture only and never stored or logged (S9, T6)."""
    from graph.llm import UnsupportedProvider, parse_byok

    provider = request.headers.get("X-LLM-Provider")
    key = request.headers.get("X-LLM-Api-Key")
    try:
        parse_byok(provider, key)
    except UnsupportedProvider as exc:
        raise field_error(
            "X-LLM-Provider", str(exc), source="header", type="unsupported_provider"
        ) from exc
    return provider, (key or "").strip() or None


def _uuid(value: str, what: str = "Story") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ApiError(ErrorCode.NOT_FOUND, f"{what} not found.") from None


def _out(request: HttpRequest, result: PictureResult) -> PictureOut:
    image = result.image
    url = result.url
    return PictureOut(
        status=result.status,
        image_id=str(image.id) if image is not None else None,
        kind=image.kind if image is not None else None,
        url=absolute_url(request, url.url) if url is not None else None,
        expires_at=url.expires_at if url is not None else None,
    )


def absolute_url(request: HttpRequest | None, url: str) -> str:
    """Local development's picture URLs are paths on this server; the app needs them whole."""
    if request is not None and url.startswith("/"):
        return request.build_absolute_uri(url)
    return url
