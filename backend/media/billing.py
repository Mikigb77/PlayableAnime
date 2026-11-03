"""Where a picture is paid for (M7, K7). WS7's credit meter plugs in here.

The flow, which matches WS7's meter (`billing.meter.astart`, `charge_image`, `arelease`):

1. `start()` before drawing on our account: it holds the picture's estimated cost, or raises
   `NoCredits` when the balance can't cover it, and the picture is skipped (M7). It may also raise
   the API's `rate_limited`, which the endpoint passes on so the app asks again later.
2. `charge()` inside the transaction that marks the picture ready, so the charge and the picture
   land together. Only the request that finishes a picture charges it, and the meter is
   idempotent per ticket, so a picture is paid for at most once however often the app asks (M3).
   It never takes a balance below zero.
3. `release()` when the picture fails, is blocked, or another request finished it first.

A picture drawn with the player's own key on a paid tier needs no ticket (K6, M7). Until WS7
lands, pictures are free, except that the owner's are recorded as the owner's (K7).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from media.models import Payer


class NoCredits(Exception):
    """The balance can't cover a picture (M7). The picture is skipped, never an error."""


@dataclass(frozen=True)
class Ticket:
    payer: Payer
    # WS7's meter ticket, when the meter is wired.
    hold: Any = None


async def start(user, *, story_id: uuid.UUID, image_id: uuid.UUID) -> Ticket:
    """Holds one picture's estimated cost for `user`, before drawing on our account.

    `user` is the signed-in player (None only in tests that call the service directly).
    WS7: `await billing.meter.astart(user, billing.meter.IMAGE, byok=False)`, turning its
    `out_of_credits` into `NoCredits`.
    """
    if user is not None and getattr(user, "is_owner", False):
        return Ticket(Payer.OWNER)
    return Ticket(Payer.FREE)


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
    ready. `calls` are the model layer's call records for the picture (T5). Returns who paid.

    WS7: `billing.meter.charge_image(ticket.hold, calls, story_id=..., turn=..., image_id=...)`.
    """
    return ticket.payer


async def release(ticket: Ticket) -> None:
    """Lets go of a hold for a picture that wasn't drawn. WS7: `billing.meter.arelease`."""
    return None
