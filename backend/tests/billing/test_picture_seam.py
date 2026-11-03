"""Pictures pay through the meter (M7, K7): `media.billing` wired to `billing.meter`."""

import uuid
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync

from billing import credits
from billing.models import CreditAccount, CreditHold, EntryKind, LedgerEntry
from billing.pricing import ModelCall
from lucid.errors import ApiError, ErrorCode
from media import billing as picture_billing
from media.models import Payer

pytestmark = pytest.mark.django_db

STORY, IMAGE = uuid.uuid4(), uuid.uuid4()
PICTURE = ModelCall(model="gemini-3.1-flash-lite-image", images=1, cost_usd=Decimal("0.0343"))


def _start(user):
    return async_to_sync(picture_billing.start)(user, story_id=STORY, image_id=IMAGE)


def _charge(ticket, calls=(PICTURE,), cost="0.0343"):
    return picture_billing.charge(
        ticket, calls=calls, cost_usd=Decimal(cost), story_id=STORY, turn=4, image_id=IMAGE
    )


def test_a_players_picture_is_held_then_charged_to_their_credits(player):
    ticket = _start(player)
    assert ticket.payer == Payer.CREDITS
    assert CreditHold.objects.get().amount_cents == 6

    assert _charge(ticket) == Payer.CREDITS

    entry = LedgerEntry.objects.get(kind=EntryKind.IMAGE)
    assert (entry.amount_cents, entry.image_id, entry.turn) == (Decimal("-5.145"), str(IMAGE), 4)
    assert entry.story_id == STORY
    assert not CreditHold.objects.exists()


def test_a_picture_without_credits_is_skipped(player):
    credits.credit(player, Decimal(-45))  # 5 cents left, a picture holds 6

    with pytest.raises(picture_billing.NoCredits):
        _start(player)


def test_a_rate_limited_picture_is_passed_on(player, billing_settings):
    billing_settings["PER_MINUTE"]["image"] = 0

    with pytest.raises(ApiError) as caught:
        _start(player)
    assert caught.value.code == ErrorCode.RATE_LIMITED


def test_the_owners_picture_is_recorded_at_no_charge(owner):
    ticket = _start(owner)

    assert _charge(ticket) == Payer.OWNER
    entry = LedgerEntry.objects.get(kind=EntryKind.IMAGE)
    assert (entry.amount_cents, entry.unlimited) == (0, True)


def test_a_picture_with_no_call_records_is_charged_its_estimate(player):
    _charge(_start(player), calls=(), cost="0.034")

    assert LedgerEntry.objects.get(kind=EntryKind.IMAGE).amount_cents == Decimal("-5.1")


def test_a_released_picture_costs_nothing(player):
    ticket = _start(player)

    async_to_sync(picture_billing.release)(ticket)

    assert not CreditHold.objects.exists()
    assert CreditAccount.objects.get(user=player).balance_cents == 50


def test_a_story_from_before_sign_in_draws_free():
    ticket = _start(None)

    assert (ticket.payer, ticket.hold) == (Payer.FREE, None)
    assert _charge(ticket) == Payer.FREE
    async_to_sync(picture_billing.release)(ticket)
    assert not LedgerEntry.objects.exists()
