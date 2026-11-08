"""Getting a scene's picture, drawn and paid for at most once (M3, M7).

The app asks for a scene's picture in its own request after the narration is shown, and may ask
again as often as it likes. The first request to find the picture planned **claims** it, under a
row lock, and draws it inside that request (nothing runs after a response ends on Cloud Run, B8).
Any request that arrives meanwhile answers `pending` at once. A claim older than `LEASE`, left by
a request that died, can be taken over, at most `MAX_ATTEMPTS` times in all.

Paying (`media.billing`): a picture drawn with the player's own key costs no credits (K6, M7).
Otherwise the credit meter holds its price before drawing, and the request that marks it ready
charges it in the same transaction. In an account's first story, a subject's first picture is on
the house while its allowance lasts (K1, M7). Without credits a planned picture is skipped (M7),
while Illustrate, which the player asked and pays for, answers `402 out_of_credits` and leaves the
scene as it was (M2). A failed or blocked picture is skipped too, its hold released, and the
scene is complete without it (M3).

A scene picture is drawn from a description written from the finished scene first
(`media.notes`), on the account that draws it, and goes with the portraits of the people it shows
and the picture of the place it happens in (M5). When the note fails, the narrator's description
stands. A story's cover, its poster (M1), goes with the portraits of the people it shows.

Each picture drawn or skipped writes one T5 log line with its model, cost and outcome, and never
its prompt (T6).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.utils import timezone

from lucid.errors import ApiError
from media import billing, drawing
from media.drawing import (
    DrawBlocked,
    DrawError,
    Drawn,
    DrawRequest,
    KeyCannotDraw,
    NoteFailed,
    PictureModel,
    Reference,
)
from media.models import Image, ImageStatus, Payer, ScenePicture, SkipReason
from media.notes import NOTED, SceneText, apply_note, note_prompt
from media.plans import (
    ILLUSTRATE,
    SCENE_FLAG,
    brief_for_cover,
    brief_for_scene,
    plan_again,
    plan_picture,
)
from media.prompts import HOUSE_STYLE_VERSION, MAX_REFERENCES, Brief, build_prompt
from media.storage import SignedUrl, delete_quietly, get_storage, signed_url, storage_key
from stories.models import ImageKind, Scene, Story

logger = logging.getLogger("media.pictures")

# Longer than a Cloud Run request can live (T1), so a live request never loses its claim.
LEASE = timedelta(seconds=300)
MAX_ATTEMPTS = 3
# Where a ready picture's brief keeps what it was drawn from (`drawn_from`), for staff (T16).
DRAWN_FROM = "drawn_from"


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
    # Whether the place's picture went along, and whether the description came from a note.
    place_reference: bool = False
    noted: bool = False
    categories: tuple[str, ...] = ()
    # What the picture was drawn from, kept with it for staff (T16), never logged (T6).
    drawn_from: dict[str, Any] | None = None
    # The credit hold until it is charged or released, and a stored file not yet the picture's.
    ticket: billing.Ticket | None = None
    saved_key: str | None = None


@dataclass(frozen=True)
class _Before:
    """How a picture stood when Illustrate claimed it, to put it back as it was when the player
    can't pay for it or the request ends without drawing it (M2, M3)."""

    status: str
    skip_reason: str
    trigger: str
    attempts: int
    # Illustrate gave the scene this picture just now, so unpaid the scene goes without one.
    asked_now: bool


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
    before sign-in). May raise the API's `rate_limited` from the credit meter, and with
    `illustrate` its `out_of_credits`, leaving the scene's picture as it was.
    """
    found = await _link(story, scene, illustrate)
    if found is None:
        return PictureResult("skipped")
    link, asked_now = found
    image = link.image
    if not illustrate and image.status != ImageStatus.READY and pictures_off(story):
        return PictureResult("skipped", image)
    image, token, before = await _claim(image.pk, illustrate=illustrate, asked_now=asked_now)
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
        put_back=before,
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
def _link(story: Story, scene: Scene, illustrate: bool) -> tuple[ScenePicture, bool] | None:
    """The scene's picture, planned now when it has none yet, and whether Illustrate gave the
    scene its picture just now. None when there is no picture and none was asked for."""
    link = ScenePicture.objects.select_related("image").filter(scene=scene).first()
    if link is not None:
        return link, False
    if scene.image_planned and scene.image_kind == ImageKind.COVER:
        # Marked for the cover without a plan: the story's poster, from its premise (M1).
        cover = brief_for_cover(story)
        return plan_picture(scene, kind=ImageKind.COVER, trigger=SCENE_FLAG, brief=cover), False
    brief = brief_for_scene(story, scene)
    if scene.image_planned:
        # Marked planned without a plan: draw the scene itself.
        return plan_picture(scene, kind=ImageKind.SCENE, trigger=SCENE_FLAG, brief=brief), False
    if illustrate:
        link = plan_picture(
            scene, kind=ImageKind.SCENE, trigger=ILLUSTRATE, brief=brief, planned=False
        )
        return link, True
    return None


@sync_to_async
def _claim(
    image_id: uuid.UUID, *, illustrate: bool = False, asked_now: bool = False
) -> tuple[Image, uuid.UUID | None, _Before | None]:
    """Claims the picture for drawing if it is planned, or its claim has run out; Illustrate
    also plans a skipped one again and claims it (M2). Returns the picture and the claim token,
    or no token when it is ready, skipped or being drawn. For Illustrate it also returns how the
    picture stood before, read under the claim's lock, so a second request at the same moment
    can never take a picture this one planned again for how it was."""
    with transaction.atomic():
        image = Image.objects.select_for_update().get(pk=image_id)
        before = None
        if illustrate:
            before = _Before(
                image.status, image.skip_reason, image.trigger, image.attempts, asked_now
            )
            plan_again(image, trigger=ILLUSTRATE)
        now = timezone.now()
        stale = image.status == ImageStatus.PENDING and (
            image.claimed_at is None or image.claimed_at < now - LEASE
        )
        if image.status != ImageStatus.PLANNED and not stale:
            return image, None, None
        if image.attempts >= MAX_ATTEMPTS:
            _mark_skipped(image, SkipReason.FAILED)
            image.save()
            image.sync_scenes()
            logger.warning(
                "Picture skipped after %s attempts",
                image.attempts,
                extra={"picture": _fields(image, "skipped", SkipReason.FAILED)},
            )
            return image, None, None
        image.status = ImageStatus.PENDING
        image.claim = uuid.uuid4()
        image.claimed_at = now
        image.attempts += 1
        if before is not None and before.status == ImageStatus.SKIPPED:
            image.save()
            image.sync_scenes()
        else:
            image.save(update_fields=["status", "claim", "claimed_at", "attempts", "updated_at"])
        return image, image.claim, before


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
    put_back: _Before | None = None,
) -> PictureResult:
    attempt = _Attempt()
    try:
        return await _draw_claimed(
            story,
            scene,
            image,
            token,
            attempt,
            user,
            trigger,
            byok_provider,
            byok_key,
            put_back,
        )
    except asyncio.CancelledError:
        # The player left and Django cancelled the request. Nothing may run after it ends (B8),
        # so let the hold go and put the picture back as it was, for the next request.
        await asyncio.shield(_abandon(image.pk, token, attempt, put_back))
        raise


async def _draw_claimed(
    story: Story,
    scene: Scene,
    image: Image,
    token: uuid.UUID,
    attempt: _Attempt,
    user,
    trigger: str,
    byok_provider: str | None,
    byok_key: str | None,
    put_back: _Before | None,
) -> PictureResult:
    """Draws a claimed picture. `put_back` is Illustrate's: how the picture stood before, for
    when the player can't pay for it (M2). Without it a picture the credits can't cover is
    skipped, and the turn goes on (M7)."""
    try:
        plan = await plan_drawing(story, scene, image)
        drawn: Drawn | None = None
        if byok_key:
            attempt.byok = True
            drawn = await _draw_once(story, plan, attempt, byok_provider, byok_key)
            if drawn is None:
                attempt.byok_fell_back = True
        if drawn is None:
            attempt.ticket = await billing.start(
                user,
                story_id=story.id,
                image_id=image.id,
                # K1, M7: a subject's first picture, however it is asked for now. A picture
                # Illustrate adds is a scene of its own, never one.
                first_picture=image.first_picture,
            )
            attempt.payer = attempt.ticket.payer
            drawn = await _draw_once(story, plan, attempt, None, None)
            if drawn is None:
                raise drawing.DrawFailed("no picture")
        else:
            attempt.payer = Payer.BYOK
    except billing.NoCredits as exc:
        if put_back is None:
            return await _skip(image, token, SkipReason.NO_CREDITS, attempt, trigger)
        # Illustrate: the player asked and can't pay, so they hear why (M2), and the picture goes
        # back to how it was before they asked.
        await _put_back(image.pk, token, put_back, unpaid=True)
        _log(image, "refused", SkipReason.NO_CREDITS, attempt, trigger)
        raise exc.error from None
    except ApiError:
        # The meter's rate limit: put the picture back as it was, and let the app ask again.
        await _put_back(image.pk, token, put_back)
        raise
    except DrawBlocked as exc:
        attempt.categories = exc.categories
        return await _skip(image, token, SkipReason.BLOCKED, attempt, trigger)
    except DrawError:
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger)
    except Exception:
        logger.exception("Drawing a picture failed", extra={"image_id": str(image.id)})
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger)

    attempt.model, attempt.cost_usd = drawn.model, drawn.cost_usd
    key = storage_key(story.id, image.id, drawn.mime_type)
    try:
        attempt.saved_key = key
        await asyncio.to_thread(get_storage().save, key, drawn.data, drawn.mime_type)
        finished, won = await _finish(image.pk, key, drawn, attempt.ticket, scene.turn, attempt)
    except Exception:
        logger.exception("Storing a picture failed", extra={"image_id": str(image.id)})
        await asyncio.to_thread(delete_quietly, key)
        attempt.saved_key = None
        return await _skip(image, token, SkipReason.FAILED, attempt, trigger)
    if not won:
        # Another request finished it first (after our claim ran out), or the story is gone.
        await _release(attempt)
        await asyncio.to_thread(delete_quietly, key)
        attempt.saved_key = None
        if finished is None:
            return PictureResult("skipped")
        return await result_for(finished)
    attempt.saved_key = None  # it is the picture now
    attempt.ticket = None  # charged with it
    _log(finished, "ready", "", attempt, trigger)
    return await result_for(finished)


async def _release(attempt: _Attempt) -> None:
    ticket, attempt.ticket = attempt.ticket, None
    if ticket is not None:
        await billing.release(ticket)


async def _abandon(
    image_id: uuid.UUID, token: uuid.UUID, attempt: _Attempt, put_back: _Before | None
) -> None:
    try:
        await _release(attempt)
        if attempt.saved_key is not None:
            await asyncio.to_thread(delete_quietly, attempt.saved_key)
        await _put_back(image_id, token, put_back)
    except Exception:
        logger.exception(
            "Cleaning up a cancelled picture failed", extra={"image_id": str(image_id)}
        )


async def _draw_once(
    story: Story,
    plan: _Plan,
    attempt: _Attempt,
    byok_provider: str | None,
    byok_key: str | None,
) -> Drawn | None:
    """One drawing, on the player's key or ours, its note first. None when the player's key
    can't draw (M7)."""
    model = drawing.build_picture_model(
        rating=story.rating, byok_provider=byok_provider, byok_key=byok_key
    )
    attempt.model = model.model
    try:
        if await write_note(plan, model):
            # Kept when the player's key wrote the note and ours draws the picture.
            attempt.noted = True
        request = plan.request()
        attempt.references = len(request.references)
        attempt.place_reference = plan.with_place
        attempt.drawn_from = drawn_from(plan.brief, request, noted=attempt.noted)
        return await model.draw(request)
    except KeyCannotDraw:
        return None
    finally:
        await model.aclose()


def drawn_from(brief: Brief, request: DrawRequest, *, noted: bool) -> dict[str, Any]:
    """What a picture was drawn from, kept with it so a picture that looks wrong can be traced
    (Miki, 2026-11-08): the description, written by the note or as planned, the people it
    shows and the images that went along, by their labels."""
    return {
        "description": brief.description,
        "people": [f.name for f in brief.figures if f.name],
        "references": [ref.label for ref in request.references],
        "noted": noted,
    }


@dataclass
class _Plan:
    """What one picture is drawn from: its brief, which its note may rewrite, and the reference
    images read for it. A scene picture's `portraits` are those of everyone its brief may show,
    so the people its note keeps still have theirs (M5)."""

    kind: str
    brief: Brief
    portraits: list[tuple[str, Reference]] = field(default_factory=list)
    place: Reference | None = None
    redraw: bool = False
    # The finished scene a scene picture shows, for its note, until one is written.
    scene: SceneText | None = None

    @property
    def with_place(self) -> bool:
        return self.place is not None and not self.redraw

    def request(self) -> DrawRequest:
        if self.redraw:
            references = [ref for _, ref in self.portraits]
        else:
            shown = {f.id for f in self.brief.figures if f.id}
            references = [ref for i, ref in self.portraits if i in shown][:MAX_REFERENCES]
        prompt = build_prompt(
            self.kind,
            self.brief,
            references=[ref.name for ref in references],
            redraw=self.redraw and bool(references),
            place=self.with_place,
        )
        if self.place is not None and self.with_place:
            references.append(self.place)
        return DrawRequest(
            kind=self.kind,
            system=prompt.system,
            prompt=prompt.user,
            aspect_ratio=prompt.aspect_ratio,
            references=tuple(
                replace(ref, label=label)
                for ref, label in zip(references, prompt.labels, strict=True)
            ),
        )


async def write_note(plan: _Plan, model: PictureModel) -> bool:
    """Writes the picture's description from the finished scene, once (`media.notes`), and says
    whether it did. A note that fails on the player's key is tried again on ours, if ours draws
    the picture; one that fails on ours leaves the narrator's description."""
    if plan.scene is None:
        return False
    try:
        note = await model.note(note_prompt(plan.kind, plan.brief, plan.scene))
    except Exception as error:
        reason = str(error) if isinstance(error, NoteFailed) else "error"
        logger.warning(
            "A picture's note failed, so the narrator's description stands",
            exc_info=not isinstance(error, NoteFailed),
            extra={"note": {"reason": reason, "byok": model.byok}},
        )
        if not model.byok:
            plan.scene = None
        return False
    plan.scene = None
    if note is None:
        return False
    plan.brief = apply_note(plan.brief, note)
    return True


async def plan_drawing(story: Story, scene: Scene | None, image: Image) -> _Plan:
    """What `image` is drawn from (M5): its brief and the reference pictures it goes with, and
    for a scene picture the finished scene for its note. `scene` is the scene asking for it; a
    portrait, place or cover needs none."""
    brief = Brief.from_json(image.brief)
    chosen, place, redraw, told = await _sources(story, scene, image, brief)
    portraits = []
    for key, name, picture in chosen:
        reference = await _load(name, picture)
        if reference is not None:
            portraits.append((key, reference))
    place_reference = None
    if place is not None:
        place_reference = await _load(brief.place_name or place.subject, place)
    return _Plan(image.kind, brief, portraits, place_reference, redraw, told)


async def _load(name: str, picture: Image) -> Reference | None:
    try:
        data = await asyncio.to_thread(get_storage().load, picture.storage_key)
    except Exception:
        logger.warning("A reference picture couldn't be read", exc_info=True)
        return None
    return Reference(name, data, picture.mime_type or "image/png")


@sync_to_async
def _sources(
    story: Story, scene: Scene | None, image: Image, brief: Brief
) -> tuple[list[tuple[str, str, Image]], Image | None, bool, SceneText | None]:
    """What a picture is drawn from besides its brief (M5): for a character or place drawn again
    because it changed for good, its earlier picture; for a scene or cover, the ready portraits
    of the people its brief may show, and for a scene picture also the ready picture of the place
    it happens in and the finished scene, for its note. Returns the portraits as (figure id, name,
    picture), the place's picture, whether this is a redraw, and the scene."""
    ready = Image.objects.filter(story=story, status=ImageStatus.READY).exclude(storage_key="")
    if image.kind in (ImageKind.PORTRAIT, ImageKind.PLACE):
        earlier = (
            ready.filter(kind=image.kind, subject=image.subject, version__lt=image.version)
            .order_by("-version")
            .first()
        )
        if earlier is None:
            return [], None, False, None
        return [("", brief.subject_name or image.subject, earlier)], None, True, None
    if image.kind not in (ImageKind.SCENE, ImageKind.COVER):
        return [], None, False, None
    ids = [figure.id for figure in brief.figures if figure.id]
    latest: dict[str, Image] = {}
    portraits = ready.filter(kind=ImageKind.PORTRAIT, subject__in=ids)
    for portrait in portraits.order_by("subject", "-version"):
        latest.setdefault(portrait.subject, portrait)
    chosen = [(f.id, f.name or f.id, latest[f.id]) for f in brief.figures if f.id in latest]
    if image.kind not in NOTED:
        # A cover is the story's poster (M1): no one scene's place or text.
        return chosen, None, False, None
    place = None
    if brief.place_id:
        place = (
            ready.filter(kind=ImageKind.PLACE, subject=brief.place_id).order_by("-version").first()
        )
    return chosen, place, False, _told(story, scene, brief)


def _told(story: Story, scene: Scene | None, brief: Brief) -> SceneText | None:
    """The finished scene the picture shows: the one its brief was planned in, else the scene
    asking for it."""
    if brief.turn and (scene is None or brief.turn != scene.turn):
        found = (
            Scene.objects.live()
            .filter(story=story, turn=brief.turn)
            .only("narration", "player_action")
            .first()
        )
        if found is not None:
            scene = found
    if scene is None or not (scene.narration or "").strip():
        return None
    return SceneText(scene.narration, scene.player_action or "")


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
    wins, even one whose claim ran out meanwhile: a finished drawing is never thrown away for one
    still in progress. A later finisher gets the winner's picture and charges nothing."""
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        if image is None or image.status == ImageStatus.READY:
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
        image.style = HOUSE_STYLE_VERSION
        image.ready_at = timezone.now()
        if attempt.drawn_from is not None:
            image.brief = {**(image.brief or {}), DRAWN_FROM: attempt.drawn_from}
        image.save()
        image.sync_scenes()
        return image, True


async def _skip(
    image: Image, token: uuid.UUID, reason: str, attempt: _Attempt, trigger: str
) -> PictureResult:
    await _release(attempt)
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
            image.sync_scenes()
        return image


def _mark_skipped(image: Image, reason: str) -> None:
    image.status = ImageStatus.SKIPPED
    image.skip_reason = reason
    image.claim = None


@sync_to_async
def _put_back(
    image_id: uuid.UUID, token: uuid.UUID, before: _Before | None, *, unpaid: bool = False
) -> None:
    """Lets go of a claim that drew nothing. A picture code planned is planned again for the next
    request; one Illustrate claimed goes back to how it stood (`before`), so a skipped one keeps
    its old reason and a blocked picture still comes back only through Illustrate (M3).
    `unpaid`: the player couldn't pay for a picture Illustrate gave the scene just now, so it is
    skipped, and the scene goes without one until they ask again."""
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        if image is None or image.claim != token:
            return
        if before is not None and before.status == ImageStatus.SKIPPED:
            _mark_skipped(image, before.skip_reason)
            image.trigger = before.trigger
            image.attempts = before.attempts
        elif unpaid and before is not None and before.asked_now:
            _mark_skipped(image, SkipReason.NO_CREDITS)
        else:
            image.status = ImageStatus.PLANNED
            image.claim = None
            image.attempts = before.attempts if before else max(0, image.attempts - 1)
        image.claimed_at = None
        image.save()
        image.sync_scenes()


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
        "place_reference": attempt.place_reference,
        "noted": attempt.noted,
        "block_categories": list(attempt.categories),
        "latency_ms": int((time.monotonic() - attempt.started) * 1000),
        "size_bytes": image.size_bytes if status == "ready" else None,
    }
    logger.info("Picture %s", status, extra={"picture": fields})
