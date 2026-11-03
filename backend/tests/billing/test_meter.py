"""The guard and the charge around model calls (K2, K6, K7, M7, T9)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from django.db import transaction

from billing import credits, meter
from billing.models import CreditAccount, CreditHold, EntryKind, LedgerEntry
from lucid import logs
from lucid.errors import ApiError, ErrorCode
from tests.billing.conftest import call

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 3, 21, 30, 15, tzinfo=UTC)
STORY = uuid.uuid4()


def _balance(user) -> Decimal:
    return CreditAccount.objects.get(user=user).balance_cents


def _set_balance(user, cents) -> None:
    credits.credit(user, Decimal(cents) - _balance(user))


def _error(fn, *args, **kwargs) -> ApiError:
    with pytest.raises(ApiError) as caught:
        fn(*args, **kwargs)
    return caught.value


# Credits


def test_a_turn_holds_its_estimate_then_charges_its_real_cost(player):
    """K2: the cost on our key plus the margin, in an entry tied to the story and turn."""
    ticket = meter.start(player, meter.TURN, now=NOW)

    assert ticket.held_cents == 5
    assert CreditHold.objects.get(pk=ticket.id).amount_cents == 5
    assert _balance(player) == 50  # held, not spent

    entry = meter.charge(
        ticket,
        [
            call("0.0014", model="gemini-3.5-flash-lite", input_tokens=2500, output_tokens=250),
            call("0.0192", input_tokens=8000, output_tokens=800),
        ],
        story_id=STORY,
        turn=7,
    )

    assert entry.kind == EntryKind.TURN
    assert (entry.amount_cents, entry.balance_after_cents) == (Decimal("-3.09"), Decimal("46.91"))
    assert entry.cost_usd == Decimal("0.0206")
    assert (entry.story_id, entry.turn, entry.unlimited) == (STORY, 7, False)
    assert entry.detail["input_tokens"] == 10500
    assert entry.detail["models"] == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
    assert not CreditHold.objects.exists()
    assert credits.reconcile(player.pk) == (Decimal("46.91"), Decimal("46.91"))


def test_a_turn_cant_start_without_the_held_amount_available(player):
    """K2: out_of_credits before anything streams, with the balance for the upsell."""
    _set_balance(player, "4.99")

    error = _error(meter.start, player, meter.TURN, now=NOW)

    assert error.code == ErrorCode.OUT_OF_CREDITS
    assert error.status == 402
    assert error.details == {"balance_cents": 4.99}
    assert not CreditHold.objects.exists()


def test_a_refused_turn_counts_nothing(player, billing_settings):
    billing_settings["PER_MINUTE"]["turn"] = 1
    _set_balance(player, 1)
    _error(meter.start, player, meter.TURN, now=NOW)
    _set_balance(player, 50)

    meter.start(player, meter.TURN, now=NOW)  # the refused one didn't use the minute's turn


def test_holds_keep_concurrent_requests_from_spending_the_same_credits(player):
    _set_balance(player, 12)
    first = meter.start(player, meter.TURN, now=NOW)
    meter.start(player, meter.TURN, now=NOW)

    assert _error(meter.start, player, meter.TURN, now=NOW).code == ErrorCode.OUT_OF_CREDITS

    meter.release(first)
    meter.start(player, meter.TURN, now=NOW)


def test_a_hold_left_by_a_request_that_died_expires(player):
    _set_balance(player, 5)
    meter.start(player, meter.TURN, now=NOW)  # never charged or released

    assert _error(meter.start, player, meter.TURN, now=NOW).code == ErrorCode.OUT_OF_CREDITS
    later = NOW + timedelta(seconds=600)
    meter.start(player, meter.TURN, now=later)
    assert CreditHold.objects.count() == 1  # the expired one is cleared


def test_a_charge_never_takes_the_balance_below_zero(player):
    """K2, M7: the balance stops at zero and the shortfall is recorded."""
    _set_balance(player, 6)
    ticket = meter.start(player, meter.TURN, now=NOW)

    entry = meter.charge(ticket, [call("0.06")])  # 9 cents with the margin

    assert (entry.amount_cents, entry.balance_after_cents) == (-6, 0)
    assert entry.detail["uncovered_cents"] == "3.0000"
    assert _balance(player) == 0
    assert _error(meter.start, player, meter.TURN, now=NOW).code == ErrorCode.OUT_OF_CREDITS


def test_charging_a_ticket_twice_bills_once(player):
    ticket = meter.start(player, meter.TURN, now=NOW)

    first = meter.charge(ticket, [call("0.02")])
    again = meter.charge(ticket, [call("0.02")])

    assert again.pk == first.pk
    assert _balance(player) == 47
    assert LedgerEntry.objects.filter(kind=EntryKind.TURN).count() == 1


def test_release_is_safe_to_repeat_and_does_nothing_after_a_charge(player):
    ticket = meter.start(player, meter.TURN, now=NOW)
    meter.charge(ticket, [call("0.02")])

    meter.release(ticket)
    meter.release(ticket)

    assert _balance(player) == 47


def test_a_turn_that_isnt_saved_isnt_charged(player):
    """API.md: the state, the scene, the ledger entry and the version bump land together."""
    ticket = meter.start(player, meter.TURN, now=NOW)

    with pytest.raises(RuntimeError), transaction.atomic():
        meter.charge(ticket, [call("0.02")], story_id=STORY, turn=3)
        raise RuntimeError("the version check failed")  # the turn's save rolls back

    assert _balance(player) == 50
    assert not LedgerEntry.objects.filter(kind=EntryKind.TURN).exists()
    meter.release(ticket)
    assert not CreditHold.objects.exists()


def test_the_entry_carries_the_request_id(player):
    logs.start_context(request_id="req-123")
    ticket = meter.start(player, meter.TURN, now=NOW)

    assert meter.charge(ticket, [call("0.02")]).request_id == "req-123"


def test_the_charge_is_logged_with_numbers_only(player, log_lines):
    ticket = meter.start(player, meter.TURN, now=NOW)
    meter.charge(ticket, [call("0.02")], story_id=STORY, turn=2)

    (line,) = [line for line in log_lines() if line["message"] == "Credits spent"]
    assert line["billing"] == {
        "kind": "turn",
        "amount_cents": -3.0,
        "balance_after_cents": 47.0,
        "cost_usd": 0.02,
        "unlimited": False,
        "turn": 2,
    }


# The owner (K7) and the player's own key (K6)


def test_the_owner_plays_free_but_every_cost_is_recorded(owner):
    """K7: unlimited even with nothing left, and the entry keeps what it would have cost."""
    _set_balance(owner, 0)
    ticket = meter.start(owner, meter.TURN, now=NOW)

    entry = meter.charge(ticket, [call("0.02")], story_id=STORY, turn=1)

    assert (ticket.unlimited, ticket.held_cents) == (True, 0)
    assert (entry.amount_cents, entry.balance_after_cents, entry.unlimited) == (0, 0, True)
    assert entry.cost_usd == Decimal("0.02")
    assert entry.detail["list_cents"] == "3.0000"


def test_a_turn_on_the_players_own_key_uses_no_credits(player):
    """K6: nothing held, nothing charged, no entry."""
    _set_balance(player, 0)
    ticket = meter.start(player, meter.TURN, byok=True, now=NOW)

    assert meter.charge(ticket, [call("0.02", byok=True)]) is None
    assert ticket.held_cents == 0
    assert _balance(player) == 0
    assert not LedgerEntry.objects.filter(kind=EntryKind.TURN).exists()


def test_a_call_that_fell_back_to_our_key_is_charged(player):
    """M7: a BYOK key on the free tier can't draw, so the picture falls back to credits."""
    ticket = meter.start(player, meter.IMAGE, byok=True, now=NOW)

    entry = meter.charge_image(
        ticket, [call("0.001", byok=True), call("0.034", images=1)], image_id="img-1"
    )

    assert entry.amount_cents == Decimal("-5.1")
    assert entry.cost_usd == Decimal("0.034")


# Pictures and drafts


def test_a_picture_is_charged_with_its_own_kind_and_hold(player):
    ticket = meter.start(player, meter.IMAGE, now=NOW)
    assert ticket.held_cents == 6

    entry = meter.charge_image(
        ticket,
        [call("0.0343", model="gemini-3.1-flash-lite-image", images=1)],
        story_id=STORY,
        turn=4,
        image_id="img-9",
    )

    assert (entry.kind, entry.image_id, entry.turn) == (EntryKind.IMAGE, "img-9", 4)
    assert entry.amount_cents == Decimal("-5.145")


def test_a_picture_without_credits_is_refused_before_drawing(player):
    """M7: the caller skips the picture quietly."""
    _set_balance(player, "5.99")

    assert _error(meter.start, player, meter.IMAGE, now=NOW).code == ErrorCode.OUT_OF_CREDITS


def test_charge_image_takes_only_a_picture_ticket(player):
    ticket = meter.start(player, meter.TURN, now=NOW)

    with pytest.raises(ValueError):
        meter.charge_image(ticket, [call("0.034")])


def test_a_draft_is_charged_as_a_draft(player):
    ticket = meter.start(player, meter.DRAFT, now=NOW)

    assert meter.charge(ticket, [call("0.01")]).kind == EntryKind.DRAFT


# Rate limits and the daily quota (T9)


def test_the_rate_limit_refuses_the_turn_after_the_limit_until_the_minute_ends(
    player, billing_settings
):
    billing_settings["PER_MINUTE"]["turn"] = 3
    for _ in range(3):
        meter.start(player, meter.TURN, now=NOW)

    error = _error(meter.start, player, meter.TURN, now=NOW)

    assert error.code == ErrorCode.RATE_LIMITED
    assert error.status == 429
    assert error.details == {"retry_after_s": 45}  # 21:30:15 → 21:31:00
    meter.start(player, meter.TURN, now=NOW.replace(minute=31, second=0))


def test_the_rate_limit_holds_for_the_players_own_key_too(player, billing_settings):
    """K6: BYOK turns are free but still rate-limited."""
    billing_settings["PER_MINUTE"]["turn"] = 1
    meter.start(player, meter.TURN, byok=True, now=NOW)

    assert _error(meter.start, player, meter.TURN, byok=True, now=NOW).code == "rate_limited"


def test_the_daily_quota_counts_turns_on_our_key_until_midnight_utc(player, billing_settings):
    billing_settings["PER_DAY"]["turn"] = 2
    meter.start(player, meter.TURN, now=NOW)
    meter.start(player, meter.TURN, now=NOW)
    meter.start(player, meter.TURN, byok=True, now=NOW)  # the player's own key: not counted

    error = _error(meter.start, player, meter.TURN, now=NOW)

    assert error.code == ErrorCode.QUOTA_EXCEEDED
    assert error.status == 429
    assert error.details == {"resets_at": "2026-11-04T00:00:00+00:00"}
    meter.start(player, meter.TURN, now=datetime(2026, 11, 4, 0, 0, 1, tzinfo=UTC))


def test_the_owner_has_the_daily_quota_too(owner, billing_settings):
    """A cost guard on our key (T9): it bounds even an owner token that leaked."""
    billing_settings["PER_DAY"]["turn"] = 1
    meter.start(owner, meter.TURN, now=NOW)

    assert _error(meter.start, owner, meter.TURN, now=NOW).code == ErrorCode.QUOTA_EXCEEDED


def test_turns_drafts_and_pictures_have_their_own_limits(player, billing_settings):
    billing_settings["PER_MINUTE"] = {"turn": 1, "draft": 1, "image": 1}
    meter.start(player, meter.TURN, now=NOW)
    meter.start(player, meter.DRAFT, now=NOW)
    meter.start(player, meter.IMAGE, now=NOW)

    for use in (meter.TURN, meter.DRAFT, meter.IMAGE):
        assert _error(meter.start, player, use, now=NOW).code == ErrorCode.RATE_LIMITED


def test_limits_are_per_user(make_user, billing_settings):
    billing_settings["PER_MINUTE"]["turn"] = 1
    meter.start(make_user(), meter.TURN, now=NOW)

    meter.start(make_user(), meter.TURN, now=NOW)


# The async twins the views call


def test_the_async_functions_work_like_the_sync_ones(player):
    ticket = async_to_sync(meter.astart)(player, meter.TURN, now=NOW)
    entry = async_to_sync(meter.acharge)(ticket, [call("0.02")])
    async_to_sync(meter.arelease)(ticket)

    assert entry.amount_cents == -3
    assert async_to_sync(credits.asummary)(player) == {"balance_cents": 47.0, "unlimited": False}
