"""Where a picture is paid for (M7, K7), through WS7's credit meter (`billing.meter`).

1. `start()` before drawing on our account: it holds the picture's estimated cost, or raises
   `NoCredits` when the balance can't cover it. A picture code planned is then skipped (M7); one
   the player asked for with Illustrate answers the meter's `402 out_of_credits` (M2). It may also
   raise the API's `rate_limited`, which the endpoint passes on so the app asks again later.
2. `charge()` inside the transaction that marks the picture ready, so the charge and the picture
   land together. Only the request that finishes a picture charges it, and the meter is
   idempotent per ticket, so a picture is paid for at most once however often the app asks (M3).
   It never takes a balance below zero.
3. `release()` when the picture fails, is blocked, or another request finished it first. A hold
   left by a request that died expires on its own, after longer than the claim's lease.

A picture drawn with the player's own key on a paid tier needs no ticket (K6, M7). The owner's
pictures are recorded at no charge (K7).

A new player's first pictures are on the house (K1, M7): in an account's first story, the
once-only pictures (`engine.contracts.FIRST_PICTURES`: the player character's portrait, the
cover, a key NPC's first-meeting portrait and a place's first visit) are held against the house's
allowance instead of the player's credits, for the accounts that get the starter credit, until
the allowance (`HOUSE_PICTURES_CENTS`) is spent. Key scenes, fights, redraws (M5) and what
Illustrate adds or tries again are always the player's.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async

from billing import meter
from billing.pricing import ModelCall
from lucid.errors import ApiError, ErrorCode
from media.models import Payer
from stories.models import Story


class NoCredits(Exception):
    """The balance can't cover a picture (M7). A planned picture is skipped, never an error;
    Illustrate answers `error`, the meter's `402 out_of_credits` with the balance (M2)."""

    def __init__(self, error: ApiError | None = None):
        super().__init__("out of credits")
        self.error = error or ApiError(
            ErrorCode.OUT_OF_CREDITS,
            "You're out of credits.",
            {"balance_cents": 0, "available_cents": 0},
        )


@dataclass(frozen=True)
class Ticket:
    payer: Payer
    # The meter's ticket; None when there is no ledger to charge.
    hold: meter.Ticket | None = None


async def start(
    user, *, story_id: uuid.UUID, image_id: uuid.UUID, first_picture: bool = False
) -> Ticket:
    """Holds one picture's estimated cost for `user`, before drawing on our account.

    `user` is the signed-in player, or None for a story from before sign-in, which has no ledger
    to charge. `first_picture`: the picture is a subject's first, which code planned (M1), so
    the house pays for it if this is the account's first story and its allowance has room.
    """
    if user is None:
        return Ticket(Payer.FREE)
    house = first_picture and await first_story(user, story_id)
    try:
        hold = await meter.astart(user, meter.IMAGE, byok=False, house=house)
    except ApiError as exc:
        if exc.code == ErrorCode.OUT_OF_CREDITS:
            raise NoCredits(exc) from exc
        raise
    if hold.unlimited:
        return Ticket(Payer.OWNER, hold=hold)
    return Ticket(Payer.HOUSE if hold.house else Payer.CREDITS, hold=hold)


@sync_to_async
def first_story(user, story_id: uuid.UUID) -> bool:
    """Whether `story_id` is the account's first story: the oldest of its stories (K1, M7).
    When that one is deleted, the next oldest takes its place, with only what is left of the
    account's house allowance, which is kept on the account."""
    first = (
        Story.objects.filter(owner_id=user.pk)
        .order_by("created_at", "id")
        .values_list("id", flat=True)
        .first()
    )
    return first is not None and str(first) == str(story_id)


def charge(
    ticket: Ticket,
    *,
    calls: Sequence[Any],
    cost_usd: Decimal,
    story_id: uuid.UUID,
    turn: int | None,
    image_id: uuid.UUID,
) -> Payer:
    """Charges the picture's real cost plus the margin (K2), inside the transaction that marks it
    ready. `calls` are the model layer's call records for the picture (T5); without them, the
    drawing's own cost estimate is charged. Returns who paid."""
    if ticket.hold is not None:
        billable = list(calls) or [ModelCall(model="", images=1, cost_usd=cost_usd)]
        meter.charge_image(
            ticket.hold, billable, story_id=story_id, turn=turn, image_id=str(image_id)
        )
    return ticket.payer


async def release(ticket: Ticket) -> None:
    """Lets go of the hold for a picture that wasn't drawn."""
    if ticket.hold is not None:
        await meter.arelease(ticket.hold)
