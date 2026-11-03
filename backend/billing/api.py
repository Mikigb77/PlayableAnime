"""`GET /v1/me/credits`: the caller's balance and latest ledger entries (K1, K2, K7)."""

from datetime import datetime
from typing import Literal

from asgiref.sync import sync_to_async
from ninja import Query, Router, Schema
from pydantic import Field

from billing import credits
from billing.models import LedgerEntry

credits_router = Router(tags=["account"])


class LedgerEntryOut(Schema):
    id: str
    kind: Literal["starter", "turn", "draft", "image", "topup", "adjustment"]
    # Positive adds credits, negative spends them. Fractional: a turn costs about 2 cents.
    amount_cents: float
    balance_after_cents: float
    story_id: str | None = None
    turn: int | None = None
    created_at: datetime


class CreditsOut(Schema):
    balance_cents: float
    unlimited: bool
    entries: list[LedgerEntryOut]


class CreditsQuery(Schema):
    limit: int = Field(default=50, ge=1, le=200)


@credits_router.get("", response=CreditsOut)
async def get_credits(request, query: Query[CreditsQuery]) -> CreditsOut:
    """The signed-in user's own credits: the API's bearer auth puts them in `request.auth`."""
    return await sync_to_async(_credits)(request.auth, query.limit)


def _credits(user, limit: int) -> CreditsOut:
    balance = credits.summary(user)
    entries = LedgerEntry.objects.filter(user_id=user.pk).order_by("-created_at", "-id")[:limit]
    return CreditsOut(
        balance_cents=balance["balance_cents"],
        unlimited=balance["unlimited"],
        entries=[
            LedgerEntryOut(
                id=str(e.id),
                kind=e.kind,
                amount_cents=float(e.amount_cents),
                balance_after_cents=float(e.balance_after_cents),
                story_id=str(e.story_id) if e.story_id else None,
                turn=e.turn,
                created_at=e.created_at,
            )
            for e in entries
        ],
    )
