"""A new player's first pictures on the house (K1, M7), at the credit meter.

A picture started with `house=True` is held against the account's house allowance instead of its
balance, for the accounts that get the starter credit, while the allowance has room. It is
charged at zero, the entry keeps what it would have cost, and that counts against the allowance.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from billing import credits, meter
from billing.models import CreditAccount, CreditHold, EntryKind
from billing.pricing import house_has_room
from lucid.errors import ApiError, ErrorCode
from tests.billing.conftest import call

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)
PICTURE = call("0.034", model="gemini-3.1-flash-lite-image", images=1)  # 5.1 cents to a player


def _account(user) -> CreditAccount:
    return CreditAccount.objects.get(user=user)


def _house_picture(user, *, now=NOW):
    """Starts and charges one first picture, as `media.billing` does."""
    ticket = meter.start(user, meter.IMAGE, house=True, now=now)
    return ticket, meter.charge_image(ticket, [PICTURE], image_id="img", now=now)


def test_the_house_pays_for_a_first_picture(player):
    ticket = meter.start(player, meter.IMAGE, house=True, now=NOW)

    assert (ticket.house, ticket.held_cents) == (True, 6)
    assert CreditHold.objects.get(pk=ticket.id).house is True
    entry = meter.charge_image(ticket, [PICTURE], story_id=None, turn=1, image_id="img-1", now=NOW)

    assert entry.kind == EntryKind.IMAGE
    assert (entry.amount_cents, entry.balance_after_cents) == (0, 50)
    assert (entry.house, entry.unlimited) == (True, False)
    assert entry.cost_usd == Decimal("0.034")
    assert entry.detail["list_cents"] == "5.1000"
    account = _account(player)
    assert (account.balance_cents, account.house_pictures_cents) == (50, Decimal("5.1"))
    assert not CreditHold.objects.exists()
    assert credits.reconcile(player.pk) == (50, 50)


def test_a_house_picture_needs_no_credits(player):
    credits.credit(player, Decimal(-50))

    ticket, entry = _house_picture(player)

    assert ticket.house and entry.amount_cents == 0
    with pytest.raises(ApiError) as caught:
        meter.start(player, meter.IMAGE, now=NOW)  # a key scene is still the player's
    assert caught.value.code == ErrorCode.OUT_OF_CREDITS


def test_a_house_hold_leaves_the_players_credits_free(player):
    """Drawing a first picture never holds the credits a turn needs at the same time."""
    credits.credit(player, Decimal(-45))  # 5 cents: one turn's hold
    meter.start(player, meter.IMAGE, house=True, now=NOW)

    assert meter.start(player, meter.TURN, now=NOW).held_cents == 5


def test_the_house_pays_until_its_allowance_is_crossed(player, billing_settings):
    """The picture that crosses the allowance is still the house's; the next is the player's."""
    billing_settings["HOUSE_PICTURES_CENTS"] = Decimal(10)

    paid = [_house_picture(player)[0].house for _ in range(3)]

    assert paid == [True, True, False]
    account = _account(player)
    assert account.house_pictures_cents == Decimal("10.2")
    assert account.balance_cents == Decimal("44.9")


def test_pictures_started_at_once_share_the_allowance(player, billing_settings):
    """Holds count against the allowance, so two pictures can't both take its last cents."""
    billing_settings["HOUSE_PICTURES_CENTS"] = Decimal(10)
    first = meter.start(player, meter.IMAGE, house=True, now=NOW)
    second = meter.start(player, meter.IMAGE, house=True, now=NOW)
    third = meter.start(player, meter.IMAGE, house=True, now=NOW)

    assert [first.house, second.house, third.house] == [True, True, False]


def test_a_released_or_expired_house_hold_gives_its_room_back(player, billing_settings):
    billing_settings["HOUSE_PICTURES_CENTS"] = Decimal(6)
    meter.release(meter.start(player, meter.IMAGE, house=True, now=NOW))
    assert meter.start(player, meter.IMAGE, house=True, now=NOW).house

    later = NOW + timedelta(seconds=billing_settings["HOLD_TTL_S"] + 1)
    assert meter.start(player, meter.IMAGE, house=True, now=later).house


def test_charging_twice_counts_once(player):
    ticket, entry = _house_picture(player)

    assert meter.charge_image(ticket, [PICTURE], image_id="img", now=NOW) == entry
    assert _account(player).house_pictures_cents == Decimal("5.1")


def test_an_unverified_account_pays_like_for_the_starter_credit(make_user):
    """The same accounts as the starter credit: an unverified email account gets neither."""
    user = make_user(google=False)

    with pytest.raises(ApiError) as caught:
        meter.start(user, meter.IMAGE, house=True, now=NOW)
    assert caught.value.code == ErrorCode.OUT_OF_CREDITS


def test_every_account_qualifies_when_the_starter_policy_says_all(make_user, billing_settings):
    billing_settings["STARTER_POLICY"] = "all"
    user = make_user(google=False)

    assert meter.start(user, meter.IMAGE, house=True, now=NOW).house


def test_no_allowance_turns_it_off(player, billing_settings):
    billing_settings["HOUSE_PICTURES_CENTS"] = Decimal(0)

    ticket, entry = _house_picture(player)

    assert not ticket.house and not entry.house
    assert entry.amount_cents == Decimal("-5.1")


def test_the_owner_and_the_players_own_key_are_unchanged(owner, player):
    """K7: the owner's picture is the owner's, at no charge. K6: their own key holds nothing."""
    ticket, entry = _house_picture(owner)
    assert (ticket.house, entry.unlimited, entry.house) == (False, True, False)
    assert _account(owner).house_pictures_cents == 0

    byok = meter.start(player, meter.IMAGE, byok=True, house=True, now=NOW)
    assert (byok.house, byok.held_cents) == (False, 0)
    assert meter.charge_image(byok, [call("0.034", byok=True, images=1)]) is None


def test_only_a_picture_can_be_on_the_house(player):
    with pytest.raises(ValueError):
        meter.start(player, meter.TURN, house=True, now=NOW)


@pytest.mark.parametrize(
    "paid, held, allowance, room",
    [
        (0, 0, 30, True),
        ("25.5", 0, 30, True),  # the sixth 5.1-cent picture crosses 30 and is still free
        ("30.6", 0, 30, False),
        ("25.5", 6, 30, False),  # a picture being drawn holds its share
        (0, 0, 0, False),
    ],
)
def test_house_has_room(paid, held, allowance, room):
    assert house_has_room(Decimal(paid), Decimal(held), Decimal(allowance)) is room
