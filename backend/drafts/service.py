"""Glue between the drafts API, the drafting chain and the database.

Every model call goes through `model_call`: the player's own key from the headers (S9), the credit
meter (K2, K6, T9), the model client for the draft's rating (F5), typed errors (T7) and one T5 log
line with the call's tokens and cost, never its prompt (T6). Saves are all or nothing and
refuse to overwrite a draft that changed since it was read (T10).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from asgiref.sync import sync_to_async
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone

from accounts import rules
from billing import meter
from drafts.models import Draft
from engine import pipeline
from engine.context import Difficulty, EventFrequency, Language, StorySettings
from engine.state import GiftStrength, PhysicsMode, WorldState
from graph.drafting import chain
from graph.drafting.catalog import starter
from graph.drafting.schema import DraftProposal
from graph.drafting.view import public_text, shown
from lucid.errors import ApiError, ErrorCode, field_error
from stories.models import Engine, Story

logger = logging.getLogger("drafts")

BLOCKED_MESSAGE = "That couldn't be drafted as written. Try rephrasing it."


def to_chain(row: Draft) -> chain.Draft:
    return chain.Draft(
        premise=row.premise,
        proposal=DraftProposal.model_validate(row.proposal),
        rating=row.rating,
        premise_id=row.premise_id or None,
        physics=PhysicsMode(row.physics),
        gift=GiftStrength(row.gift_strength) if row.gift_strength else None,
        released_rules=frozenset(row.released_rules),
        language=Language(row.language),
        told=frozenset(row.told),
    )


def chain_fields(draft: chain.Draft) -> dict[str, Any]:
    """The columns that hold a chain draft's inputs."""
    return {
        "premise": draft.premise,
        "premise_id": draft.premise_id or "",
        "rating": draft.rating,
        "proposal": draft.proposal.model_dump(mode="json"),
        "physics": draft.physics.value,
        "gift_strength": draft.gift.value if draft.gift is not None else None,
        "released_rules": sorted(draft.released_rules),
        "language": draft.language.value,
        "told": sorted(draft.told),
    }


def check_rating(user, rating: str) -> None:
    """F8: an account under 17 drafts and plays Teen only."""
    if not rules.allows_rating(user.birth_date, rating):
        raise ApiError(ErrorCode.FORBIDDEN, "This rating is above your account's limit.")


async def owned_draft(request: HttpRequest, draft_id: str) -> Draft:
    """The signed-in player's draft, within their rating limit (S8, F8)."""
    try:
        pk = uuid.UUID(draft_id)
    except ValueError:
        raise ApiError(ErrorCode.NOT_FOUND, "Draft not found.") from None
    row = await Draft.objects.filter(pk=pk).afirst()
    if row is None:
        raise ApiError(ErrorCode.NOT_FOUND, "Draft not found.")
    if row.owner_id != request.auth.pk:
        raise ApiError(ErrorCode.FORBIDDEN, "This draft belongs to someone else.")
    check_rating(request.auth, row.rating)
    return row


def version_conflict(current_version: int) -> ApiError:
    """T10: the draft changed since the caller read it, in another tab or on another device."""
    return ApiError(
        ErrorCode.VERSION_CONFLICT,
        "This draft changed since you opened it.",
        {"current_version": current_version},
    )


def check_version(row: Draft, expected: int | None) -> None:
    if expected is not None and expected != row.version:
        raise version_conflict(row.version)


def refuse_started(row: Draft) -> None:
    if row.story_id is not None:
        raise ApiError(
            ErrorCode.FORBIDDEN,
            "This draft has already started its story.",
            {"story_id": str(row.story_id)},
        )


# Model calls.


def model_backend(*, grounded: bool, byok: object | None):
    """The backend for a drafting call, or None to let the model layer pick: Vertex AI, or the
    player's own key. With `LLM_PROVIDER=fake` the offline drafter answers with a sample draft,
    so the create flow works without a model. Tests replace this function."""
    from graph.drafting import samples
    from graph.llm import get_model_config

    if byok is None and get_model_config().provider == "fake":
        return samples.offline_backend(grounded=grounded)
    return None


@dataclass
class ModelCall:
    client: Any
    ticket: meter.Ticket
    telemetry: Any
    action: str
    premise_id: str | None
    outcome: str = "ok"
    extra: dict[str, Any] = field(default_factory=dict)

    def charge(self) -> None:
        """Inside the transaction that saves the draft, so the charge lands with it (K2). A
        draft has no story yet, so its ledger entry has none."""
        meter.charge(self.ticket, self.telemetry.calls)


@asynccontextmanager
async def model_call(
    request: HttpRequest, *, rating: str, action: str, premise_id: str | None
) -> AsyncIterator[ModelCall]:
    """One drafting request's model access. The meter refuses it first when the player is over
    the rate limit or the daily quota or out of credits (T9, K2). Model failures leave as the API's
    typed errors, and a hold on credits that wasn't charged is given back."""
    from graph.llm import (
        BadKey,
        LLMBlocked,
        LLMUnavailable,
        TurnTelemetry,
        UnsupportedProvider,
        parse_byok,
    )

    try:
        byok = parse_byok(
            request.headers.get("X-LLM-Provider"), request.headers.get("X-LLM-Api-Key")
        )
    except UnsupportedProvider as exc:
        raise field_error(
            "X-LLM-Provider", str(exc), source="header", type="unsupported_provider"
        ) from exc
    ticket = await meter.astart(request.auth, meter.DRAFT, byok=byok is not None)
    telemetry = TurnTelemetry()
    found = starter(premise_id) if premise_id else None
    grounded = found is not None and found.template.grounded_rule_id is not None
    try:
        client = await sync_to_async(_client, thread_sensitive=False)(
            rating, byok, telemetry, grounded
        )
    except BaseException:
        await meter.arelease(ticket)
        raise
    call = ModelCall(client, ticket, telemetry, action, premise_id)
    try:
        yield call
    except LLMBlocked as exc:
        call.outcome = "blocked"
        call.extra = {"stage": exc.stage, "categories": list(exc.categories)}
        raise ApiError(ErrorCode.UNREADABLE_ACTION, BLOCKED_MESSAGE) from exc
    except BadKey as exc:
        call.outcome = "bad_key"
        raise ApiError(ErrorCode.BAD_KEY, exc.message) from exc
    except LLMUnavailable as exc:
        call.outcome = "unavailable"
        raise ApiError(ErrorCode.LLM_UNAVAILABLE) from exc
    except ApiError as exc:
        call.outcome = str(exc.code)
        raise
    except BaseException:
        call.outcome = "failed"
        raise
    finally:
        # Gives back the hold. After a charge there is none left, unless the save rolled back.
        await meter.arelease(ticket)
        await client.aclose()
        _log(call)


def _client(rating: str, byok, telemetry, grounded: bool):
    """Built off the event loop: the first real client imports the model SDK (B10)."""
    from graph.llm import build_client

    return build_client(
        rating=rating,
        byok=byok,
        recorder=telemetry,
        backend=model_backend(grounded=grounded, byok=byok),
    )


def _log(call: ModelCall) -> None:
    """T5: one line per drafting request, with numbers and names only (T6)."""
    summary = call.telemetry.summary()
    fields = {
        "action": call.action,
        "premise_id": call.premise_id,
        "outcome": call.outcome,
        "calls": summary["calls"],
        "models": summary["models"],
        "input_tokens": summary["input_tokens"],
        "output_tokens": summary["output_tokens"],
        # Gemini counts thinking against the output limit, so this shows how much of it went there.
        "thinking_tokens": summary["thinking_tokens"],
        "cached_tokens": summary["cached_tokens"],
        "latency_ms": summary["latency_ms"],
        "cost_usd": summary["cost_usd"],
        "billable_cost_usd": summary["billable_cost_usd"],
        "retries": summary["retries"],
        "byok": summary["byok"],
        **call.extra,
    }
    level = logging.INFO if call.outcome == "ok" else logging.WARNING
    logger.log(level, "Draft %s %s", call.action, call.outcome, extra={"draft": fields})


# Saving.


@sync_to_async
def create_row(
    owner, draft: chain.Draft, call: ModelCall, *, difficulty: str, event_frequency: str
) -> Draft:
    draft.state()  # never save a draft whose state can't be built
    with transaction.atomic():
        row = Draft.objects.create(
            owner=owner,
            difficulty=difficulty,
            event_frequency=event_frequency,
            **chain_fields(draft),
        )
        call.charge()
    return row


@sync_to_async
def save_row(
    row: Draft, draft: chain.Draft, call: ModelCall | None = None, **settings: str
) -> Draft:
    """Saves a changed draft only if nobody saved it since `row` was read (T10)."""
    draft.state()
    fields = {**chain_fields(draft), **settings}
    with transaction.atomic():
        updated = Draft.objects.filter(pk=row.pk, version=row.version, story__isnull=True).update(
            **fields, version=F("version") + 1, updated_at=timezone.now()
        )
        if updated and call is not None:
            call.charge()
    if not updated:
        if call is not None:
            # The model ran for this request, so it is paid for even though another save won
            # (K2).
            call.charge()
        current = Draft.objects.filter(pk=row.pk).first()
        if current is None:
            raise ApiError(ErrorCode.NOT_FOUND, "Draft not found.")
        refuse_started(current)
        raise version_conflict(current.version)
    return Draft.objects.get(pk=row.pk)


@sync_to_async
def start_story(
    row_id: uuid.UUID, settings: dict[str, Any], *, expected_version: int | None = None
) -> Story:
    """Creates the story with its opening state and marks the draft started, together. Starting
    again returns the same story, so a retry over a flaky network never makes two, whatever
    version it carries (starting bumps the version). A draft not yet started must still be at
    `expected_version`, so a story never starts from a copy the player hasn't seen (T10)."""
    with transaction.atomic():
        row = Draft.objects.select_for_update().get(pk=row_id)
        if row.story_id is not None:
            return Story.objects.get(pk=row.story_id)
        check_version(row, expected_version)
        draft = to_chain(row)
        # G18, C6: what the player read before starting, the character knows from the first
        # moment: a rung their own premise or the draft's screen named is one they have heard of.
        # The draft's own state is never changed, so this gives a copy when it adds anything.
        read = f"{row.premise}\n{shown(draft.state(), Language(row.language), draft.said)}"
        state, _ = pipeline.settle_path(draft.state(), read)
        story = Story.objects.create(
            owner_id=row.owner_id,
            title=_title(state, row.premise),
            premise=row.premise,
            genre=state.bible.genre[:80],
            rating=row.rating,
            settings=story_settings(row, settings),
            engine=Engine.GRAPH,
            state=state.model_dump(mode="json"),
            turn=0,
            # A story exists from version 1, and the opening turn expects this version (T10).
            version=1,
        )
        Draft.objects.filter(pk=row.pk).update(
            story=story, version=F("version") + 1, updated_at=timezone.now()
        )
    logger.info(
        "Story started from a draft",
        extra={"story_id": str(story.id), "draft": {"premise_id": row.premise_id or None}},
    )
    return story


def story_settings(row: Draft, overrides: dict[str, Any]) -> dict[str, Any]:
    """S6: the draft's difficulty, event frequency and language (S10), then whatever the player
    set on start."""
    base = StorySettings(
        difficulty=Difficulty(row.difficulty),
        event_frequency=EventFrequency(row.event_frequency),
        language=Language(row.language),
    )
    return StorySettings.model_validate(base.model_dump() | overrides).model_dump(mode="json")


def _title(state: WorldState, premise: str) -> str:
    if title := public_text(state, state.bible.title):
        return title[:200]
    words = premise.split()
    return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
