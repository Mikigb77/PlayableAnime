"""Getting a scene's picture, drawn and paid for at most once (M3, M7).

The app asks for a scene's picture in its own request after the narration is shown, and may ask
again as often as it likes. The first request to find the picture planned **claims** it, under a
row lock, and draws it inside that request (nothing runs after a response ends on Cloud Run, B8).
Any request that arrives meanwhile answers `pending` at once. A claim older than `LEASE`, left by
a request that died, can be taken over, at most `MAX_ATTEMPTS` times in all.

Paying (`media.billing`): a picture drawn with the player's own key costs no credits (K6, M7).
Otherwise the credit meter holds its price before drawing, and the request that marks it ready
charges it in the same transaction. Without credits it is skipped (M7). A failed or blocked
picture is skipped too, its hold released, and the scene is complete without it (M3).

Each picture drawn or skipped writes one T5 log line with its model, cost and outcome, and never
its prompt (T6).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from lucid.errors import ApiError
from media import billing, drawing
from media.drawing import DrawBlocked, DrawError, Drawn, DrawRequest, KeyCannotDraw, Reference
from media.models import Image, ImageStatus, Payer, ScenePicture, SkipReason
from media.plans import ILLUSTRATE, SCENE_FLAG, brief_for_scene, plan_picture, replan
from media.prompts import MAX_REFERENCES, Brief, build_prompt
from media.storage import SignedUrl, get_storage, signed_url, storage_key
from stories.models import ImageKind, Scene, Story

logger = logging.getLogger("media.pictures")

# Longer than a Cloud Run request can live (T1), so a live request never loses its claim.
LEASE = timedelta(seconds=300)
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class PictureResult:
    """What the picture endpoints answer: `ready` with a URL, `pending` or `skipped`."""

    status: str
    image: Image | None = None
    url: SignedUrl | None = None


@dataclass
class _Attempt:
    """What one drawing attempt did, for its T5 line."""

    started: float = field(default_factory=time.monotonic)
    payer: str = ""
    model: str = ""
    cost_usd: Decimal | None = None
    byok: bool = False
    byok_fell_back: bool = False
    references: int = 0
    categories: tuple[str, ...] = ()


def pictures_off(story: Story) -> bool:
    """The player turned automatic pictures off for this story (S6, M2)."""
    settings_ = story.settings if isinstance(story.settings, dict) else {}
    return settings_.get("images") == "off"


async def scene_picture(
    story: Story,
    scene: Scene,
    *,
    user,
    illustrate: bool = False,
    byok_provider: str | None = None,
    byok_key: str | None = None,
) -> PictureResult:
    """The picture `scene` shows, drawn now if nobody has drawn it yet.

    Without `illustrate`, only a picture code planned (M1) is drawn, and not while the story's
    pictures are off. With `illustrate`, the player asked for one (M2): a scene with no picture
    gets one of its own, and a skipped one is tried again. `user` pays (None for a story from
    before sign-in). May raise the API's `rate_limited` from the credit meter.
    """
    link = await _link(story, scene, illustrate)
    if link is None:
        return PictureResult("skipped")
    image = link.image
    if not illustrate and image.status != ImageStatus.READY and pictures_off(story):
        return PictureResult("skipped", image)
    image, token = await _claim(image.pk)
    if token is None:
        return await result_for(image)
    trigger = ILLUSTRATE if illustrate else (link.trigger or image.trigger)
    return await _draw(
        story,
        scene,
        image,
        token,
        user=user,
        trigger=trigger,
        byok_provider=byok_provider,
        byok_key=byok_key,
    )


async def result_for(image: Image) -> PictureResult:
    """The picture's state as the endpoints answer it, with a fresh signed URL when ready."""
    if image.status == ImageStatus.READY and image.storage_key:
        url = await asyncio.to_thread(signed_url, image.storage_key)
        return PictureResult("ready", image, url)
    if image.status == ImageStatus.SKIPPED:
        return PictureResult("skipped", image)
    return PictureResult("pending", image)


@sync_to_async
def _link(story: Story, scene: Scene, illustrate: bool) -> ScenePicture | None:
    link = ScenePicture.objects.select_related("image").filter(scene=scene).first()
    if link is None:
        if scene.image_planned:
            # Marked planned without a plan: draw the scene itself, or the cover.
            kind = scene.image_kind if scene.image_kind == ImageKind.COVER else ImageKind.SCENE
            link = plan_picture(
                scene, kind=kind, trigger=SCENE_FLAG, brief=brief_for_scene(story, scene)
            )
        elif illustrate:
            link = plan_picture(
                scene,
                kind=ImageKind.SCENE,
                trigger=ILLUSTRATE,
                brief=brief_for_scene(story, scene),
                planned=False,
            )
        else:
            return None
    if illustrate and link.image.status == ImageStatus.SKIPPED:
        link.image = replan(link.image, trigger=ILLUSTRATE)
    return link


@sync_to_async
def _claim(image_id: uuid.UUID) -> tuple[Image, uuid.UUID | None]:
    """Claims the picture for drawing if it is planned, or its claim has run out. Returns the
    picture and the claim token, or no token when it is ready, skipped or being drawn."""
    with transaction.atomic():
        image = Image.objects.select_for_update().get(pk=image_id)
        now = timezone.now()
        stale = image.status == ImageStatus.PENDING and (
            image.claimed_at is None or image.claimed_at < now - LEASE
        )
        if image.status != ImageStatus.PLANNED and not stale:
            return image, None
        if image.attempts >= MAX_ATTEMPTS:
            _mark_skipped(image, SkipReason.FAILED)
            image.save()
            logger.warning(
                "Picture skipped after %s attempts",
                image.attempts,
                extra={"picture": _fields(image, "skipped", SkipReason.FAILED)},
            )
            return image, None
        image.status = ImageStatus.PENDING
        image.claim = uuid.uuid4()
        image.claimed_at = now
        image.attempts += 1
        image.save(update_fields=["status", "claim", "claimed_at", "attempts", "updated_at"])
        return image, image.claim


async def _draw(
    story: Story,
    scene: Scene,
    image: Image,
    token: uuid.UUID,
    *,
    user,
    trigger: str,
    byok_provider: str | None,
    byok_key: str | None,
) -> PictureResult:
    attempt = _Attempt()
    ticket: billing.Ticket | None = None
    try:
        request = await _draw_request(story, image)
        attempt.references = len(request.references)
        drawn: Drawn | None = None
        if byok_key:
            attempt.byok = True
            drawn = await _draw_once(story, request, attempt, byok_provider, byok_key)
            if drawn is None:
                attempt.byok_fell_back = True
        if drawn is None:
            try:
                ticket = await billing.start(user, story_id=story.id, image_id=image.id)
            except billing.NoCredits:
                return await _skip(image, token, SkipReason.NO_CREDITS, attempt, trigger)
            attempt.payer = ticket.payer
            drawn = await _draw_once(story, request, attempt, None, None)
            if drawn is None:
                raise drawing.DrawFailed("no picture")
        else:
            attempt.payer = Payer.BYOK
    except ApiError:
        # The meter's rate limit: put the picture back, and let the app ask again later.
        await _unclaim(image.pk, token)
        raise
    except DrawBlocked as exc:
        attempt.categories = exc.categories
        return await _skip(image, token, SkipReason.BLOCKED, attempt, trigger, ticket)
    except DrawError:
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger, ticket)
    except Exception:
        logger.exception("Drawing a picture failed", extra={"image_id": str(image.id)})
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger, ticket)

    attempt.model, attempt.cost_usd = drawn.model, drawn.cost_usd
    key = storage_key(story.id, image.id, drawn.mime_type)
    try:
        await asyncio.to_thread(get_storage().save, key, drawn.data, drawn.mime_type)
        finished, won = await _finish(image.pk, key, drawn, ticket, scene.turn, attempt)
    except Exception:
        logger.exception("Storing a picture failed", extra={"image_id": str(image.id)})
        await asyncio.to_thread(_delete_quietly, key)
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger, ticket)
    if not won:
        # Another request finished it first (after our claim ran out), or the story is gone.
        if ticket is not None:
            await billing.release(ticket)
        await asyncio.to_thread(_delete_quietly, key)
        if finished is None:
            return PictureResult("skipped")
        return await result_for(finished)
    _log(finished, "ready", "", attempt, trigger)
    return await result_for(finished)


async def _draw_once(
    story: Story,
    request: DrawRequest,
    attempt: _Attempt,
    byok_provider: str | None,
    byok_key: str | None,
) -> Drawn | None:
    """One drawing, on the player's key or ours. None when the player's key can't draw (M7)."""
    model = drawing.build_picture_model(
        rating=story.rating, byok_provider=byok_provider, byok_key=byok_key
    )
    attempt.model = model.model
    try:
        return await model.draw(request)
    except KeyCannotDraw:
        return None
    finally:
        await model.aclose()


@sync_to_async
def _references(story: Story, image: Image) -> tuple[list[tuple[str, Image]], bool]:
    """The portraits to send with a picture (M5): the earlier portrait of a character being
    redrawn, or the ready portraits of the known characters in a scene or cover."""
    brief = Brief.from_json(image.brief)
    portraits = Image.objects.filter(
        story=story, kind=ImageKind.PORTRAIT, status=ImageStatus.READY
    ).exclude(storage_key="")
    if image.kind == ImageKind.PORTRAIT:
        earlier = (
            portraits.filter(subject=image.subject, version__lt=image.version)
            .order_by("-version")
            .first()
        )
        if earlier is None:
            return [], False
        return [(brief.subject_name or image.subject, earlier)], True
    if image.kind not in (ImageKind.SCENE, ImageKind.COVER):
        return [], False
    ids = [figure.id for figure in brief.figures if figure.id]
    latest: dict[str, Image] = {}
    for portrait in portraits.filter(subject__in=ids).order_by("subject", "-version"):
        latest.setdefault(portrait.subject, portrait)
    chosen = [(f.name or f.id, latest[f.id]) for f in brief.figures if f.id in latest]
    return chosen[:MAX_REFERENCES], False


async def _draw_request(story: Story, image: Image) -> DrawRequest:
    chosen, redraw = await _references(story, image)
    references = []
    for name, portrait in chosen:
        try:
            data = await asyncio.to_thread(get_storage().load, portrait.storage_key)
        except Exception:
            logger.warning("A reference portrait couldn't be read", exc_info=True)
            continue
        references.append(Reference(name, data, portrait.mime_type or "image/png"))
    prompt = build_prompt(
        image.kind,
        Brief.from_json(image.brief),
        references=[ref.name for ref in references],
        redraw=redraw and bool(references),
    )
    return DrawRequest(
        kind=image.kind,
        system=prompt.system,
        prompt=prompt.user,
        aspect_ratio=prompt.aspect_ratio,
        references=tuple(references),
    )


@sync_to_async
def _finish(
    image_id: uuid.UUID,
    key: str,
    drawn: Drawn,
    ticket: billing.Ticket | None,
    turn: int,
    attempt: _Attempt,
) -> tuple[Image | None, bool]:
    """Marks the picture ready and charges it, together. The first request to finish a picture
    wins; a later one (whose claim ran out) gets the winner's picture and charges nothing."""
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        if image is None or image.status != ImageStatus.PENDING:
            return image, False
        payer = Payer.BYOK
        if ticket is not None:
            payer = billing.charge(
                ticket,
                calls=drawn.calls,
                cost_usd=drawn.cost_usd,
                story_id=image.story_id,
                turn=turn,
                image_id=image.id,
            )
        attempt.payer = payer
        image.status = ImageStatus.READY
        image.skip_reason = ""
        image.storage_key = key
        image.mime_type = drawn.mime_type
        image.size_bytes = len(drawn.data)
        image.model = drawn.model
        image.cost_usd = drawn.cost_usd
        image.payer = payer
        image.claim = None
        image.ready_at = timezone.now()
        image.save()
        return image, True


async def _skip(
    image: Image,
    token: uuid.UUID,
    reason: str,
    attempt: _Attempt,
    trigger: str,
    ticket: billing.Ticket | None = None,
) -> PictureResult:
    if ticket is not None:
        await billing.release(ticket)
    current = await _mark_skipped_if_claimed(image.pk, token, reason)
    if current is None:
        return PictureResult("skipped")
    if current.status == ImageStatus.SKIPPED:
        _log(current, "skipped", reason, attempt, trigger)
    return await result_for(current)


@sync_to_async
def _mark_skipped_if_claimed(image_id: uuid.UUID, token: uuid.UUID, reason: str) -> Image | None:
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        if image is not None and image.claim == token:
            _mark_skipped(image, reason)
            image.save()
        return image


def _mark_skipped(image: Image, reason: str) -> None:
    image.status = ImageStatus.SKIPPED
    image.skip_reason = reason
    image.claim = None


@sync_to_async
def _unclaim(image_id: uuid.UUID, token: uuid.UUID) -> None:
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        if image is not None and image.claim == token:
            image.status = ImageStatus.PLANNED
            image.claim = None
            image.claimed_at = None
            image.attempts = max(0, image.attempts - 1)
            image.save()


def _delete_quietly(key: str) -> None:
    try:
        get_storage().delete(key)
    except Exception:
        logger.warning("A picture file couldn't be deleted", exc_info=True)


def _fields(image: Image, status: str, reason: str) -> dict:
    return {
        "image_id": str(image.id),
        "kind": image.kind,
        "version": image.version,
        "status": status,
        "skip_reason": reason or None,
        "attempts": image.attempts,
    }


def _log(image: Image, status: str, reason: str, attempt: _Attempt, trigger: str) -> None:
    """The picture's T5 line: model, cost and outcome, never the prompt (T6)."""
    fields = _fields(image, status, reason) | {
        "trigger": trigger,
        "model": attempt.model or None,
        "cost_usd": float(attempt.cost_usd) if attempt.cost_usd is not None else None,
        "payer": str(attempt.payer) or None,
        "byok": attempt.byok,
        "byok_fell_back": attempt.byok_fell_back,
        "references": attempt.references,
        "block_categories": list(attempt.categories),
        "latency_ms": int((time.monotonic() - attempt.started) * 1000),
        "size_bytes": image.size_bytes if status == "ready" else None,
    }
    logger.info("Picture %s", status, extra={"picture": fields})
