"""Concurrent requests on real, separate database connections, as on several Cloud Run instances.

PLAN.md's bar for WS7: concurrent debits can't overdraw, and the ledger reconciles with the balance.
"""

import threading
from collections.abc import Callable
from decimal import Decimal

import pytest
from django.db import connection

from accounts.models import User
from billing import credits, limits, meter
from billing.models import CreditAccount, EntryKind, LedgerEntry
from lucid.errors import ApiError, ErrorCode
from tests.billing.conftest import call

pytestmark = pytest.mark.django_db(transaction=True)

THREADS = 10


def _run_together(work: Callable[[int], object], n: int = THREADS) -> list[object]:
    """Runs `work(i)` on n threads released at the same moment, each on its own connection.
    Returns each result, or the exception it raised."""
    barrier = threading.Barrier(n)
    results: list[object] = [None] * n

    def run(i: int) -> None:
        try:
            barrier.wait()
            results[i] = work(i)
        except Exception as exc:  # noqa: BLE001 — collected for the test to inspect
            results[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def _balance(user) -> Decimal:
    return CreditAccount.objects.get(user=user).balance_cents


def _assert_reconciles(user) -> None:
    balance, total = credits.reconcile(user.pk)
    assert balance == total
    assert balance >= 0


def test_concurrent_turns_cant_start_on_the_same_credits(player):
    """20 cents and a 5-cent hold: exactly four of ten simultaneous turns may start."""
    credits.credit(player, Decimal(-30))

    results = _run_together(lambda i: meter.start(player, meter.TURN))

    tickets = [r for r in results if isinstance(r, meter.Ticket)]
    refused = [r for r in results if isinstance(r, ApiError)]
    assert len(tickets) == 4
    assert {e.code for e in refused} == {ErrorCode.OUT_OF_CREDITS}
    assert len(refused) == THREADS - 4

    charged = _run_together(
        lambda i: meter.charge(tickets[i], [call("0.02")], turn=i), n=len(tickets)
    )

    assert all(isinstance(e, LedgerEntry) for e in charged)
    assert _balance(player) == 20 - 4 * 3
    _assert_reconciles(player)


def test_concurrent_charges_dearer_than_the_balance_stop_at_zero(player):
    """Each charge is 15 cents against 20: the balance reaches zero and never goes below."""
    credits.credit(player, Decimal(-30))
    tickets = [meter.start(player, meter.TURN) for _ in range(4)]

    results = _run_together(lambda i: meter.charge(tickets[i], [call("0.10")]), n=4)

    assert all(isinstance(e, LedgerEntry) for e in results)
    assert _balance(player) == 0
    spent = sum(-e.amount_cents for e in results)
    assert spent == 20
    uncovered = sum(Decimal(e.detail.get("uncovered_cents", 0)) for e in results)
    assert uncovered == 4 * 15 - 20
    _assert_reconciles(player)


def test_the_same_ticket_charged_at_once_bills_once(player):
    ticket = meter.start(player, meter.TURN)

    results = _run_together(lambda i: meter.charge(ticket, [call("0.02")]), n=5)

    assert len({e.pk for e in results}) == 1
    assert LedgerEntry.objects.filter(kind=EntryKind.TURN).count() == 1
    assert _balance(player) == 47
    _assert_reconciles(player)


def test_the_rate_limit_counts_simultaneous_requests_exactly(
    player, billing_settings, steady_minute
):
    """T9 across instances: of 10 turns at once with a limit of 7, exactly 7 start."""
    billing_settings["PER_MINUTE"]["turn"] = 7

    results = _run_together(lambda i: meter.start(player, meter.TURN, byok=True))

    assert sum(isinstance(r, meter.Ticket) for r in results) == 7
    assert {r.code for r in results if isinstance(r, ApiError)} == {ErrorCode.RATE_LIMITED}


def test_a_counter_counts_every_simultaneous_hit(player):
    from django.utils import timezone

    now = timezone.now()
    results = _run_together(
        lambda i: limits.hit(player.pk, "test:minute", limit=100, window_s=60, now=now)
    )

    assert sorted(r.count for r in results) == list(range(1, THREADS + 1))


def test_an_account_opened_from_many_requests_at_once_gets_one_starter_credit(db):
    (user,) = User.objects.bulk_create([User(email="race@example.com", google_sub="race")])

    results = _run_together(lambda i: credits.open_account(user))

    assert all(isinstance(r, CreditAccount) for r in results)
    assert LedgerEntry.objects.filter(user=user, kind=EntryKind.STARTER).count() == 1
    assert _balance(user) == 50
    _assert_reconciles(user)
