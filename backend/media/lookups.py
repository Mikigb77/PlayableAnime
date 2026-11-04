"""Picture URLs for the endpoints that show scenes, portraits, places, covers and the export, and
the starter premises' covers on Discover.

The story, library, memory, status and export endpoints (WS3, WS6, WS15) and the views that leave
picture URLs empty for the API to fill (`engine.visibility`, `Scene.portraits`) call these instead
of reading
the media tables themselves. Each call is one query, and the URLs it needs are signed together
(`media.storage.signed_urls`). Signing can call IAM, so call these off the event loop
(`sync_to_async`), and pass the request to make local development's URLs absolute.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.http import HttpRequest

from media.api import absolute_url
from media.models import Image, ImageStatus, PremiseCover, ScenePicture
from media.premise_covers import COVER_URL_TTL_S
from media.storage import SignedUrl, signed_urls
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
    urls = _urls([link.image for link in links.values()], request)
    images: dict[int, dict[str, Any]] = {}
    for scene in scenes:
        link = links.get(scene.pk)
        if link is not None:
            image = link.image
            images[scene.turn] = {
                "planned": link.planned,
                "kind": image.kind,
                "status": str(image.scene_status),
                "image_id": str(image.id),
            }
            if image.pk in urls:
                url = urls[image.pk]
                images[scene.turn] |= {"url": url.url, "expires_at": url.expires_at}
        elif scene.image_planned:
            images[scene.turn] = {
                "planned": True,
                "kind": scene.image_kind or ImageKind.SCENE,
                "status": str(ImageStatus.PLANNED),
            }
    return images


def portrait_urls(
    story: Story | Any, character_ids: Iterable[str], *, request: HttpRequest | None = None
) -> dict[str, SignedUrl]:
    """The current portrait of each character that has one ready (M4, M5), by character id.
    A character with none is left out."""
    return _subject_urls(story, ImageKind.PORTRAIT, character_ids, request)


def place_urls(
    story: Story | Any, place_ids: Iterable[str], *, request: HttpRequest | None = None
) -> dict[str, SignedUrl]:
    """The current picture of each place that has one ready (M4, M5), by place id. A place with
    none is left out."""
    return _subject_urls(story, ImageKind.PLACE, place_ids, request)


def place_url(
    story: Story | Any, place_id: str, *, request: HttpRequest | None = None
) -> SignedUrl | None:
    """One place's current picture, or None when it has none ready."""
    return place_urls(story, [place_id], request=request).get(place_id)


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
    urls = _urls(latest.values(), request)
    return {story_id: urls[image.pk] for story_id, image in latest.items() if image.pk in urls}


def premise_cover_urls(
    premise_ids: Iterable[str], *, request: HttpRequest | None = None
) -> dict[str, SignedUrl]:
    """Each starter premise's cover, when the house has drawn one (S1), by premise id. They are
    signed for `COVER_URL_TTL_S`, longer than a story's pictures, because the app fetches the
    premises once per session and a cover is the same for every player."""
    covers = list(PremiseCover.objects.filter(premise_id__in=list(premise_ids)))
    signed = signed_urls((cover.storage_key for cover in covers), COVER_URL_TTL_S)
    return {
        cover.premise_id: SignedUrl(
            absolute_url(request, signed[cover.storage_key].url),
            signed[cover.storage_key].expires_at,
        )
        for cover in covers
    }


def export_pictures(user, *, request: HttpRequest | None = None) -> list[dict[str, Any]]:
    """Every ready picture of the user's stories, with fresh URLs, for the export (T12, M4)."""
    images = list(
        Image.objects.filter(story__owner=user, status=ImageStatus.READY)
        .prefetch_related("scene_links__scene")
        .order_by("story_id", "created_at")
    )
    urls = _urls(images, request)
    return [
        {
            "id": str(image.id),
            "story_id": str(image.story_id),
            "kind": image.kind,
            "subject": image.subject,
            "version": image.version,
            "turns": sorted(link.scene.turn for link in image.scene_links.all()),
            "url": urls[image.pk].url,
            "expires_at": urls[image.pk].expires_at.isoformat(),
            "created_at": image.created_at.isoformat(),
        }
        for image in images
        if image.pk in urls
    ]


def _subject_urls(
    story: Story | Any, kind: str, subject_ids: Iterable[str], request: HttpRequest | None
) -> dict[str, SignedUrl]:
    """The latest ready version of each subject's picture of `kind`, signed, by subject id."""
    pictures = Image.objects.filter(
        story=story,
        kind=kind,
        subject__in=list(dict.fromkeys(subject_ids)),
        status=ImageStatus.READY,
    ).order_by("subject", "-version")
    latest: dict[str, Image] = {}
    for picture in pictures:
        latest.setdefault(picture.subject, picture)
    urls = _urls(latest.values(), request)
    return {subject: urls[image.pk] for subject, image in latest.items() if image.pk in urls}


def _urls(images: Iterable[Image], request: HttpRequest | None) -> dict[Any, SignedUrl]:
    """Signed URLs for the ready pictures among `images`, by image id."""
    ready = [i for i in images if i.status == ImageStatus.READY and i.storage_key]
    signed = signed_urls(image.storage_key for image in ready)
    return {
        image.pk: SignedUrl(
            absolute_url(request, signed[image.storage_key].url),
            signed[image.storage_key].expires_at,
        )
        for image in ready
    }
