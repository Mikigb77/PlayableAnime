"""Staff views of balances and the ledger (B1), and the billing settings from env (K1, K2, T9)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client
from django.urls import reverse
from pydantic import ValidationError

from accounts.models import User
from billing import meter
from billing.config import StarterPolicy, Use, get_config
from billing.models import CreditAccount, LedgerEntry
from lucid.env import Env
from tests.billing.conftest import call


@pytest.fixture
def staff_client(db) -> Client:
    client = Client()
    client.force_login(User.objects.create_superuser("staff@example.com", "pw"))
    return client


@pytest.mark.django_db
def test_staff_can_read_balances_and_the_ledger_but_not_change_them(staff_client, player):
    ticket = meter.start(player, meter.TURN)
    entry = meter.charge(ticket, [call("0.02")], turn=1)

    for name, query in [("billing_creditaccount", "player"), ("billing_ledgerentry", "player")]:
        listing = staff_client.get(reverse(f"admin:{name}_changelist"), {"q": query})
        assert listing.status_code == 200, name
    detail = staff_client.get(reverse("admin:billing_ledgerentry_change", args=[entry.pk]))
    assert detail.status_code == 200
    assert b'name="_save"' not in detail.content  # read-only

    assert staff_client.get(reverse("admin:billing_ledgerentry_add")).status_code == 403
    delete_url = reverse("admin:billing_ledgerentry_delete", args=[entry.pk])
    assert staff_client.post(delete_url, {"post": "yes"}).status_code == 403
    assert LedgerEntry.objects.filter(pk=entry.pk).exists()
    assert CreditAccount.objects.get(user=player).balance_cents == 47


@pytest.mark.django_db
def test_staff_can_still_delete_a_user_with_their_credits(staff_client, player):
    """T12: the read-only billing admins don't block deleting a user in the admin."""
    response = staff_client.post(
        reverse("admin:accounts_user_delete", args=[player.pk]), {"post": "yes"}
    )

    assert response.status_code == 302
    assert not User.objects.filter(pk=player.pk).exists()
    assert not LedgerEntry.objects.exists()


def test_a_zero_hold_is_refused(billing_settings):
    billing_settings["RESERVE_CENTS"]["image"] = 0

    with pytest.raises(ImproperlyConfigured):
        get_config()


def test_the_billing_settings_come_from_env(monkeypatch):
    monkeypatch.setenv("BILLING_MARGIN", "0.25")
    monkeypatch.setenv("STARTER_CREDIT_CENTS", "75")
    monkeypatch.setenv("STARTER_CREDIT_POLICY", "all")
    monkeypatch.setenv("TURN_RATE_PER_MINUTE", "4")
    monkeypatch.setenv("DAILY_TURN_QUOTA", "0")

    env = Env()

    assert env.billing_margin == Decimal("0.25")
    assert env.starter_credit_cents == 75
    assert env.starter_credit_policy == "all"
    assert (env.turn_rate_per_minute, env.daily_turn_quota) == (4, 0)


@pytest.mark.parametrize(
    "name, value",
    [
        ("BILLING_MARGIN", "-0.1"),
        ("STARTER_CREDIT_CENTS", "-1"),
        ("STARTER_CREDIT_POLICY", "everyone"),
        ("TURN_RATE_PER_MINUTE", "0"),
        ("DAILY_TURN_QUOTA", "-1"),
    ],
)
def test_bad_billing_settings_stop_the_service_from_starting(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Env()


def test_the_default_settings_hold_together(settings):
    from lucid import settings as project_settings

    settings.BILLING = project_settings.BILLING  # not the test values from conftest.py
    config = get_config()

    assert config.starter_policy in StarterPolicy
    assert set(config.reserve_cents) == set(config.per_minute) == set(config.per_day) == set(Use)
    assert config.hold_ttl_s > 300  # longer than Cloud Run's request timeout (T1)
