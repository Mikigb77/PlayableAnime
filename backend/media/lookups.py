"""Picture URLs for the endpoints that show scenes, portraits, covers and the export.

The story, library, memory and export endpoints (WS3, WS6, WS15) call these instead of reading
the media tables themselves. They query in bulk, one query per call. URLs are signed, so call
them off the event loop (`sync_to_async`), and pass the request to make local URLs absolute.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.http import HttpRequest

from media.api import absolute_url
from media.models import Image, ImageStatus, ScenePicture
from media.storage import SignedUrl, signed_url
from stories.models import ImageKind, Scene, Story


def scene_images(
    scenes: Iterable[Scene], *, request: HttpRequest | None = None
) -> dict[int, dict[str, Any]]:
    """`Scene.image` from docs/API.md for each scene that has or will have a picture, by turn:
    `{planned, kind, status, image_id?, url?, expires_at?}`. `status` is `planned` until the
    picture is ready or skipped; the app then asks for it (M3)."""
    scenes = list(scenes)
    links = {
        link.scene_id: link
        for link in ScenePicture.objects.select_related("image").filter(scene__in=scenes)
    }
    images: dict[int, dict[str, Any]] = {}
    for scene in scenes:
        link = links.get(scene.pk)
        if link is not None:
            image = link.image
            status = image.status if image.status in _FINAL else ImageStatus.PLANNED
            images[scene.turn] = {
                "planned": link.planned,
                "kind": image.kind,
                "status": str(status),
                "image_id": str(image.id),
                **_url_fields(image, request),
            }
        elif scene.image_planned:
            images[scene.turn] = {
                "planned": True,
                "kind": scene.image_kind or ImageKind.SCENE,
                "status": ImageStatus.PLANNED,
            }
    return images


def portrait_urls(
    story: Story | Any, character_ids: Iterable[str], *, request: HttpRequest | None = None
) -> dict[str, SignedUrl]:
    """The current portrait of each character that has one ready (M4, M5), by character id."""
    ids = list(dict.fromkeys(character_ids))
    latest: dict[str, Image] = {}
    portraits = Image.objects.filter(
        story=story, kind=ImageKind.PORTRAIT, subject__in=ids, status=ImageStatus.READY
    ).order_by("subject", "-version")
    for portrait in portraits:
        latest.setdefault(portrait.subject, portrait)
    return {subject: _signed(image, request) for subject, image in latest.items()}


def cover_urls(
    story_ids: Iterable[Any], *, request: HttpRequest | None = None
) -> dict[str, SignedUrl]:
    """Each story's Library cover, when it has one ready (M1), by story id."""
    covers = Image.objects.filter(
        story_id__in=list(story_ids), kind=ImageKind.COVER, status=ImageStatus.READY
    ).order_by("story_id", "-version")
    latest: dict[str, Image] = {}
    for cover in covers:
        latest.setdefault(str(cover.story_id), cover)
    return {story_id: _signed(image, request) for story_id, image in latest.items()}


def export_pictures(user, *, request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """Every ready picture of the user's stories, with fresh URLs, for the export (T12, M4)."""
    images = (
        Image.objects.filter(story__owner=user, status=ImageStatus.READY)
        .prefetch_related("scene_links__scene")
        .order_by("story_id", "created_at")
    )
    exported = []
    for image in images:
        url = _signed(image, request)
        exported.append(
            {
                "id": str(image.id),
                "story_id": str(image.story_id),
                "kind": image.kind,
                "subject": image.subject,
                "version": image.version,
                "turns": sorted(link.scene.turn for link in image.scene_links.all()),
                "url": url.url,
                "expires_at": url.expires_at.isoformat(),
                "created_at": image.created_at.isoformat(),
            }
        )
    return exported


_FINAL = (ImageStatus.READY, ImageStatus.SKIPPED)


def _url_fields(image: Image, request: HttpRequest | None) -> dict[str, Any]:
    if image.status != ImageStatus.READY or not image.storage_key:
        return {}
    url = _signed(image, request)
    return {"url": url.url, "expires_at": url.expires_at}


def _signed(image: Image, request: HttpRequest | None) -> SignedUrl:
    url = signed_url(image.storage_key)
    return SignedUrl(absolute_url(request, url.url), url.expires_at)
