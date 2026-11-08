"""Story pictures drawn again in the current house style (S7, M4, Miki 2026-11-08).

When the house style changes (`media.prompts.HOUSE_STYLE_VERSION`), `manage.py redraw_pictures`
draws every ready picture of every story again in it, once, so the stories played so far show the
app's current look too. On Cloud Run it runs on each deploy, after the starter covers, and finds
nothing to do until the style changes again.

Each picture is drawn the way `media.service` first drew it: from its brief, a scene picture from
a note on its finished scene with the portraits of the people it shows and the picture of its
place, and a portrait or place drawn again for a changed look from its earlier version (M5). So
the portraits and places go first, oldest version first, and the scenes and covers that use them
after. The old drawing stays on screen until the new one is stored in a file of its own; then the
old file goes.

The house pays, on our account: each drawing is logged with its model and cost (T5), and no
player's ledger is charged. A picture a rewind took out of the story (C8), and the pictures of the
legacy stories no endpoint serves, are left as they are. A picture that fails or is blocked keeps
its old drawing, and the next run tries it again. One run spends at most `max_usd` and starts no
drawing after `minutes`, leaving the rest to the next run.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When

from media import drawing
from media.drawing import DrawBlocked, DrawError, Drawn, DrawRateLimited
from media.models import Image, ImageStatus
from media.plans import RETIRED
from media.premise_covers import (
    COVER_PAUSE_S,
    RATE_LIMIT_RETRIES,
    RATE_LIMIT_WAIT_S,
    picture_model_name,
    spent_by,
)
from media.prompts import HOUSE_STYLE_VERSION
from media.service import plan_drawing, write_note
from media.storage import delete_quietly, get_storage, storage_key
from stories.models import Engine, ImageKind, Scene

logger = logging.getLogger("media.pictures")

TRIGGER = "redraw_pictures"
# A real model draws them a little apart, like the starter covers, for our picture quota.
PAUSE_S = COVER_PAUSE_S
# What one run spends at most, and how long it goes on starting drawings: about 140 pictures,
# and within the deploy job's hour. What is left is drawn by the next run.
MAX_USD = Decimal(5)
MINUTES = 45.0


@dataclass(frozen=True)
class Outcome:
    """What happened to one picture."""

    image_id: str
    kind: str
    # "redrawn", "kept" (it changed meanwhile, so the new drawing went), "failed" or "blocked".
    status: str
    model: str = ""
    cost_usd: Decimal | None = None
    # A failed drawing that ran out of quota (429), which a wait may fix.
    rate_limited: bool = False


@dataclass
class Run:
    """What one run did: an outcome per picture it tried, and how many it left to the next run
    because it reached its budget or its time."""

    outcomes: list[Outcome] = field(default_factory=list)
    # Every try's cost, a try refused for quota and drawn again included.
    spent: Decimal = Decimal(0)
    left: int = 0
    # "budget" or "time" when it stopped before the end.
    stopped_by: str = ""


def to_redraw(story_ids: Iterable[str] = ()) -> list[Image]:
    """The ready pictures drawn in an older house style, in the order they are drawn again:
    portraits and places first, each subject's oldest version first, since a newer version and
    every scene and cover are drawn with them (M5), then the scenes and covers, oldest first.
    Only `story_ids` when given."""
    pictures = (
        Image.objects.filter(
            status=ImageStatus.READY,
            style__lt=HOUSE_STYLE_VERSION,
            story__engine=Engine.GRAPH,
        )
        .exclude(storage_key="")
        .exclude(subject__contains=RETIRED)
        .select_related("story")
    )
    story_ids = list(story_ids)
    if story_ids:
        pictures = pictures.filter(story_id__in=story_ids)
    looks_first = Case(
        When(kind__in=(ImageKind.PORTRAIT, ImageKind.PLACE), then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return list(pictures.order_by(looks_first, "version", "created_at", "id"))


async def redraw_all(
    images: Iterable[Image],
    *,
    offline: bool,
    max_usd: Decimal = MAX_USD,
    minutes: float = MINUTES,
    report: Callable[[Outcome], None] = lambda outcome: None,
) -> Run:
    """Draws each picture again in turn, storing each as soon as it is drawn, and calls `report`
    with each outcome. A real model draws them `PAUSE_S` apart, and draws one that ran out of
    quota again after `RATE_LIMIT_WAIT_S`, up to `RATE_LIMIT_RETRIES` times. Stops starting
    drawings once `max_usd` is spent or `minutes` have passed."""
    images = list(images)
    run = Run()
    started = _clock()
    for index, image in enumerate(images):
        if run.spent >= max_usd:
            run.stopped_by = "budget"
        elif _clock() - started >= minutes * 60:
            run.stopped_by = "time"
        if run.stopped_by:
            run.left = len(images) - index
            break
        if index and not offline:
            await _wait(PAUSE_S)
        outcome = await redraw(image)
        run.spent += outcome.cost_usd or Decimal(0)
        for attempt in range(1, RATE_LIMIT_RETRIES + 1):
            if not outcome.rate_limited:
                break
            logger.info(
                "Redrawing a picture ran out of picture quota; drawing it again after %.0f s",
                RATE_LIMIT_WAIT_S,
                extra={"image_id": str(image.id), "retry": attempt, "of": RATE_LIMIT_RETRIES},
            )
            await _wait(RATE_LIMIT_WAIT_S)
            outcome = await redraw(image)
            run.spent += outcome.cost_usd or Decimal(0)
        run.outcomes.append(outcome)
        report(outcome)
    return run


async def _wait(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _clock() -> float:
    return time.monotonic()


async def redraw(image: Image) -> Outcome:
    """Draws `image` again in the current house style, on our account, and makes the new drawing
    the picture once it is stored. Keeps the old one if the drawing fails or is blocked, or if
    the picture changed meanwhile."""
    started = time.monotonic()
    story = image.story
    model = None
    name = picture_model_name()
    shown = _Shown()
    try:
        plan = await plan_drawing(story, await _scene_for(image), image)
        model = drawing.build_picture_model(rating=story.rating, byok_provider=None, byok_key=None)
        name = model.model
        shown.noted = await write_note(plan, model)
        request = plan.request()
        shown.references = len(request.references)
        shown.place = plan.with_place
        drawn = await model.draw(request)
    except DrawBlocked as exc:
        shown.categories = exc.categories
        return _missed(image, "blocked", "blocked", name, spent_by(model), started, shown)
    except DrawRateLimited:
        cost = spent_by(model)
        _log(image, "skipped", "rate_limited", name, cost, started, shown)
        return Outcome(str(image.id), image.kind, "failed", name, cost, rate_limited=True)
    except DrawError:
        return _missed(image, "failed", "failed", name, spent_by(model), started, shown)
    except Exception:
        logger.exception("Redrawing a picture failed", extra={"image_id": str(image.id)})
        return _missed(image, "failed", "failed", name, spent_by(model), started, shown)
    finally:
        if model is not None:
            await model.aclose()

    key = storage_key(story.id, image.id, drawn.mime_type, fresh=True)
    try:
        await asyncio.to_thread(get_storage().save, key, drawn.data, drawn.mime_type)
        swapped = await _swap(image.pk, image.storage_key, key, drawn)
    except Exception:
        logger.exception("Storing a redrawn picture failed", extra={"image_id": str(image.id)})
        await asyncio.to_thread(delete_quietly, key)
        return _missed(image, "failed", "failed", drawn.model, drawn.cost_usd, started, shown)
    if not swapped:
        # Deleted, rewound or drawn again by another run meanwhile: this drawing was paid for
        # and dropped.
        _log(image, "discarded", "", drawn.model, drawn.cost_usd, started, shown)
        return Outcome(str(image.id), image.kind, "kept", drawn.model, drawn.cost_usd)
    size = len(drawn.data)
    _log(image, "ready", "", drawn.model, drawn.cost_usd, started, shown, size=size)
    return Outcome(str(image.id), image.kind, "redrawn", drawn.model, drawn.cost_usd)


@dataclass
class _Shown:
    """What a drawing went with, for its T5 line."""

    references: int = 0
    place: bool = False
    noted: bool = False
    categories: tuple[str, ...] = ()


@sync_to_async
def _scene_for(image: Image) -> Scene | None:
    """A scene that shows the picture, its first still in the story, for a scene picture's note
    (`media.service`). A portrait, place or cover is drawn without one."""
    if image.kind != ImageKind.SCENE:
        return None
    return (
        Scene.objects.live()
        .filter(picture__image=image)
        .only("id", "turn", "narration", "player_action")
        .order_by("turn")
        .first()
    )


@sync_to_async
def _swap(image_id, old_key: str, key: str, drawn: Drawn) -> bool:
    """Makes the new file the picture's, if it is still the ready picture whose file was `old_key`,
    and removes the old file once that commits. Otherwise the new file goes."""
    with transaction.atomic():
        image = Image.objects.select_for_update().filter(pk=image_id).first()
        current = (
            image is not None
            and image.status == ImageStatus.READY
            and image.storage_key == old_key
            and image.style < HOUSE_STYLE_VERSION
            and RETIRED not in image.subject
        )
        if not current:
            transaction.on_commit(functools.partial(delete_quietly, key))
            return False
        image.storage_key = key
        image.mime_type = drawn.mime_type
        image.size_bytes = len(drawn.data)
        image.model = drawn.model
        image.style = HOUSE_STYLE_VERSION
        image.save(
            update_fields=["storage_key", "mime_type", "size_bytes", "model", "style", "updated_at"]
        )
        transaction.on_commit(functools.partial(delete_quietly, old_key))
        return True


def _missed(
    image: Image,
    status: str,
    reason: str,
    model: str,
    cost_usd: Decimal | None,
    started: float,
    shown: _Shown,
) -> Outcome:
    _log(image, "skipped", reason, model, cost_usd, started, shown)
    return Outcome(str(image.id), image.kind, status, model, cost_usd)


def _log(
    image: Image,
    status: str,
    reason: str,
    model: str,
    cost_usd: Decimal | None,
    started: float,
    shown: _Shown,
    *,
    size: int | None = None,
) -> None:
    """The drawing's T5 line, like a story picture's: model, cost and outcome, never the prompt
    (T6). The house paid, so no ledger entry goes with it."""
    fields = {
        "image_id": str(image.id),
        "story_id": str(image.story_id),
        "kind": image.kind,
        "version": image.version,
        "status": status,
        "skip_reason": reason or None,
        "trigger": TRIGGER,
        "style": HOUSE_STYLE_VERSION,
        "model": model or None,
        "cost_usd": float(cost_usd) if cost_usd is not None else None,
        "payer": "house",
        "byok": False,
        "references": shown.references,
        "place_reference": shown.place,
        "noted": shown.noted,
        "block_categories": list(shown.categories),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "size_bytes": size,
    }
    logger.info("Redrawn picture %s", status, extra={"picture": fields})
