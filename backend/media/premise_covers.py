"""The starter premises' covers on Discover (S1, M4, M8): drawn once by the house, shown to all.

`manage.py draw_premise_covers` draws each starter's cover with the configured picture model (M8):
the house style with the lower third calm for the title (S7, `media.prompts`), mild in every
rating (M6), stored in the private picture storage (M4). `GET /v1/premises` then answers each
drawn cover with a fresh signed URL (`media.lookups.premise_cover_urls`).

The house pays, once: every drawing is logged with its model and cost (T5), and no player's
ledger is charged, since the cover belongs to no one's story. A cover is kept until it is drawn
again with `--force`, except a placeholder from the offline model, which a real model replaces.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal

from asgiref.sync import sync_to_async
from django.db import IntegrityError, transaction
from django.utils import timezone

from graph.drafting.catalog import StarterPremise
from media import drawing
from media.drawing import DrawBlocked, DrawError, Drawn, DrawRequest
from media.models import PremiseCover
from media.prompts import Brief, WorldLook, build_prompt
from media.storage import check_key, delete_quietly, extension_for, get_storage
from stories.models import ImageKind

logger = logging.getLogger("media.pictures")

# Every account sees Discover, so a cover is drawn under the Teen rating. Pictures are mild in
# every rating anyway (M6), with the same safety settings.
COVER_RATING = "teen"
TRIGGER = "draw_premise_covers"
# How long a cover's signed URL lasts at least (never less than a story picture's). The app
# fetches the premises once per session, so a URL must outlive one; reused while half its life
# remains, each answer lasts six hours at least.
COVER_URL_TTL_S = 12 * 3600


def cover_url_ttl_s() -> int:
    from django.conf import settings

    return max(COVER_URL_TTL_S, settings.PICTURE_URL_TTL_S)


@dataclass(frozen=True)
class Outcome:
    """What happened to one premise's cover."""

    premise_id: str
    # "drawn", "kept" (it already had one), "failed" or "blocked".
    status: str
    model: str = ""
    cost_usd: Decimal | None = None
    # A kept cover drawn from older premise text, or by the offline model.
    stale: bool = False
    offline: bool = False


def offline_model() -> bool:
    """Whether the configured model is the offline one (`LLM_PROVIDER=fake`, the default), which
    draws plain placeholder pictures."""
    from graph.llm import get_model_config

    return get_model_config().provider != "vertex"


def picture_model_name() -> str:
    from graph.llm import Node, get_model_config

    return get_model_config().node(Node.PICTURE).model


def cover_brief(premise: StarterPremise) -> Brief:
    """What a starter's cover shows: its world and its main character, from the premise's public
    text. The title is left out, since the app sets it over the cover and a picture has no text."""
    return Brief(
        description=f'The premise, which calls the main character "you": {premise.premise}',
        look=WorldLook(genre=premise.genre, setting=premise.tagline),
    )


def cover_request(premise: StarterPremise) -> DrawRequest:
    prompt = build_prompt(ImageKind.COVER, cover_brief(premise))
    return DrawRequest(
        kind=ImageKind.COVER,
        system=prompt.system,
        prompt=prompt.user,
        aspect_ratio=prompt.aspect_ratio,
    )


def cover_key(premise_id: str, mime_type: str) -> str:
    """A new file for every drawing, so a cached signed URL never shows an older cover."""
    name = f"{uuid.uuid4().hex}{extension_for(mime_type)}"
    return check_key(f"premises/{premise_id}/{name}")


def to_draw(
    premises: Iterable[StarterPremise], *, force: bool, offline: bool
) -> tuple[list[StarterPremise], list[Outcome]]:
    """The premises whose cover to draw, and the covers kept as they are.

    A premise without a cover is drawn, and with `force` every one is. A placeholder from the
    offline model counts as no cover once a real model is configured.
    """
    premises = list(premises)
    covers = PremiseCover.objects.in_bulk([premise.id for premise in premises])
    todo: list[StarterPremise] = []
    kept: list[Outcome] = []
    for premise in premises:
        cover = covers.get(premise.id)
        if force or cover is None or (cover.offline and not offline):
            todo.append(premise)
            continue
        kept.append(
            Outcome(
                premise.id,
                "kept",
                model=cover.model,
                cost_usd=cover.cost_usd,
                stale=cover.brief != cover_brief(premise).to_json(),
                offline=cover.offline,
            )
        )
    return todo, kept


async def draw_covers(
    premises: Iterable[StarterPremise],
    *,
    force: bool,
    offline: bool,
    report: Callable[[Outcome], None] = lambda outcome: None,
) -> list[Outcome]:
    """Draws each premise's cover in turn, storing each as soon as it is drawn, and calls
    `report` with each outcome. A cover that fails or is blocked is left as it was."""
    outcomes = []
    for premise in premises:
        outcome = await draw_cover(premise, force=force, offline=offline)
        report(outcome)
        outcomes.append(outcome)
    return outcomes


async def draw_cover(premise: StarterPremise, *, force: bool, offline: bool) -> Outcome:
    started = time.monotonic()
    model = None
    name = picture_model_name()
    try:
        model = drawing.build_picture_model(rating=COVER_RATING, byok_provider=None, byok_key=None)
        name = model.model
        drawn = await model.draw(cover_request(premise))
    except DrawBlocked as exc:
        cost = _spent(model)
        _log(premise.id, "skipped", "blocked", name, cost, offline, started, exc.categories)
        return Outcome(premise.id, "blocked", model=name, cost_usd=cost, offline=offline)
    except DrawError:
        cost = _spent(model)
        _log(premise.id, "skipped", "failed", name, cost, offline, started)
        return Outcome(premise.id, "failed", model=name, cost_usd=cost, offline=offline)
    except Exception:
        logger.exception("Drawing a premise cover failed", extra={"premise_id": premise.id})
        cost = _spent(model)
        _log(premise.id, "skipped", "failed", name, cost, offline, started)
        return Outcome(premise.id, "failed", model=name, cost_usd=cost, offline=offline)
    finally:
        if model is not None:
            await model.aclose()

    key = cover_key(premise.id, drawn.mime_type)
    try:
        await asyncio.to_thread(get_storage().save, key, drawn.data, drawn.mime_type)
        stored = await _store(premise, key, drawn, force=force, offline=offline)
    except Exception:
        logger.exception("Storing a premise cover failed", extra={"premise_id": premise.id})
        await asyncio.to_thread(delete_quietly, key)
        _log(premise.id, "skipped", "failed", drawn.model, drawn.cost_usd, offline, started)
        return Outcome(
            premise.id, "failed", model=drawn.model, cost_usd=drawn.cost_usd, offline=offline
        )
    status = "drawn" if stored else "kept"
    size = len(drawn.data) if stored else None
    # Not stored: another run's cover won meanwhile, and this drawing was paid for and dropped.
    logged = "ready" if stored else "discarded"
    _log(premise.id, logged, "", drawn.model, drawn.cost_usd, offline, started, size=size)
    return Outcome(premise.id, status, model=drawn.model, cost_usd=drawn.cost_usd, offline=offline)


@sync_to_async
def _store(premise: StarterPremise, key: str, drawn: Drawn, *, force: bool, offline: bool) -> bool:
    """Makes the new file the premise's cover and removes the one it replaces once that commits.
    False when another run stored a cover meanwhile that this one doesn't replace (it isn't
    forced, and that cover is no placeholder this real drawing beats): the new file goes."""
    fields = {
        "storage_key": key,
        "mime_type": drawn.mime_type,
        "size_bytes": len(drawn.data),
        "model": drawn.model,
        "cost_usd": drawn.cost_usd,
        "offline": offline,
        "brief": cover_brief(premise).to_json(),
        "drawn_at": timezone.now(),
    }
    for _ in range(2):
        try:
            with transaction.atomic():
                cover = PremiseCover.objects.select_for_update().filter(pk=premise.id).first()
                if cover is None:
                    PremiseCover.objects.create(premise_id=premise.id, **fields)
                    return True
                if not force and not (cover.offline and not offline):
                    transaction.on_commit(functools.partial(delete_quietly, key))
                    return False
                old = cover.storage_key
                for name, value in fields.items():
                    setattr(cover, name, value)
                cover.save()
                if old != key:
                    transaction.on_commit(functools.partial(delete_quietly, old))
                return True
        except IntegrityError:
            # Another run created this premise's cover at the same moment. Its row exists now,
            # so the next pass locks it and decides as above.
            continue
    delete_quietly(key)
    return False


def _spent(model) -> Decimal | None:
    """What a drawing that failed or was blocked still cost, from the model layer's call records
    when the model keeps them (T5)."""
    telemetry = getattr(model, "telemetry", None)
    calls = getattr(telemetry, "calls", None)
    if not calls:
        return None
    return sum((call.cost_usd for call in calls), Decimal(0))


def _log(
    premise_id: str,
    status: str,
    reason: str,
    model: str,
    cost_usd: Decimal | None,
    offline: bool,
    started: float,
    categories: Iterable[str] = (),
    *,
    size: int | None = None,
) -> None:
    """The cover's T5 line, like a story picture's: model, cost and outcome, never the prompt
    (T6). The house paid, so no ledger entry goes with it."""
    fields = {
        "premise_id": premise_id,
        "kind": ImageKind.COVER.value,
        "status": status,
        "skip_reason": reason or None,
        "trigger": TRIGGER,
        "model": model or None,
        "cost_usd": float(cost_usd) if cost_usd is not None else None,
        "payer": "house",
        "byok": False,
        "offline": offline,
        "block_categories": list(categories),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "size_bytes": size,
    }
    logger.info("Premise cover %s", status, extra={"picture": fields})
