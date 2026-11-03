"""Accounts, the starter credit and the append-only ledger (K1, K2, T12)."""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.db import DatabaseError, IntegrityError, transaction

from accounts.models import User
from billing import credits
from billing.models import CreditAccount, CreditHold, EntryKind, LedgerEntry, UsageCounter

pytestmark = pytest.mark.django_db


def _balance(user) -> Decimal:
    return CreditAccount.objects.get(user=user).balance_cents


def test_a_new_google_account_gets_the_starter_credit_once(player):
    """K1: $0.50, recorded as a starter entry."""
    entry = LedgerEntry.objects.get(user=player)

    assert _balance(player) == 50
    assert (entry.kind, entry.amount_cents, entry.balance_after_cents) == ("starter", 50, 50)
    player.display_name = "Kaede"
    player.save()
    credits.open_account(player)
    assert LedgerEntry.objects.filter(user=player).count() == 1


def test_an_unverified_email_account_waits_for_the_starter_credit(make_user):
    """Throwaway emails can't farm it: an email account gets it once it is verified."""
    user = make_user(google=False)

    assert _balance(user) == 0
    assert not LedgerEntry.objects.filter(user=user).exists()

    # Linking a Google sign-in verifies the email, so the starter credit arrives then, once.
    user.google_sub = "google-linked"
    user.save(update_fields=["google_sub"])
    user.save()
    assert _balance(user) == 50
    assert LedgerEntry.objects.filter(user=user, kind=EntryKind.STARTER).count() == 1


def test_ws6s_email_verified_flag_grants_it_once_it_is_set(make_user, monkeypatch):
    """WS6 adds `User.email_verified`; billing reads it when it is there."""
    monkeypatch.setattr(User, "email_verified", False, raising=False)
    user = make_user(google=False)
    assert not credits.qualifies_for_starter(user)
    assert _balance(user) == 0

    user.email_verified = True
    user.save()

    assert _balance(user) == 50


def test_a_google_account_counts_as_verified_whatever_the_flag_says(make_user, monkeypatch):
    monkeypatch.setattr(User, "email_verified", False, raising=False)

    assert _balance(make_user(google=True)) == 50


def test_saves_that_cant_verify_an_account_skip_the_check(make_user, django_assert_num_queries):
    user = make_user(google=False)

    with django_assert_num_queries(1):  # the UPDATE itself
        user.save(update_fields=["last_login"])


def test_every_account_gets_it_when_the_policy_says_all(make_user, billing_settings):
    billing_settings["STARTER_POLICY"] = "all"

    assert _balance(make_user(google=False)) == 50


def test_a_user_without_an_account_gets_one_on_first_use(db):
    """Users created before billing existed, or without the signal (bulk_create), aren't left
    without an account or their starter credit."""
    (user,) = User.objects.bulk_create([User(email="early@example.com", google_sub="early")])
    assert not CreditAccount.objects.filter(user=user).exists()

    assert credits.summary(user) == {"balance_cents": 50.0, "unlimited": False}
    assert LedgerEntry.objects.filter(user=user).count() == 1


def test_the_owner_is_unlimited(owner, player):
    """K7: from the role stored on the user."""
    assert credits.summary(owner)["unlimited"] is True
    assert credits.summary(player)["unlimited"] is False


def test_staff_adjustments_add_or_take_credits_but_never_below_zero(player):
    credits.credit(player, Decimal("12.5"), detail={"note": "support refund"})
    credits.credit(player, Decimal("-2.5"))

    assert _balance(player) == 60
    with pytest.raises(ValueError):
        credits.credit(player, Decimal("-60.0001"))
    assert _balance(player) == 60


def test_the_database_refuses_a_negative_balance(player):
    with pytest.raises(IntegrityError), transaction.atomic():
        CreditAccount.objects.filter(user=player).update(balance_cents=Decimal("-0.0001"))


def test_ledger_entries_cant_be_changed_or_deleted_one_by_one(player):
    """K2: append-only, in the model and in the database."""
    entry = LedgerEntry.objects.get(user=player)

    entry.amount_cents = 500
    with pytest.raises(ValueError):
        entry.save()
    with pytest.raises(ValueError):
        entry.delete()
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        LedgerEntry.objects.filter(pk=entry.pk).update(amount_cents=500)
    assert LedgerEntry.objects.get(pk=entry.pk).amount_cents == 50


def test_the_balance_reconciles_with_the_ledger(player):
    credits.credit(player, Decimal("7.25"))
    credits.credit(player, Decimal("-3"))

    balance, total = credits.reconcile(player.pk)

    assert balance == total == Decimal("54.25")


def test_check_ledger_reports_balances_that_dont_match(player, make_user):
    make_user()
    out = StringIO()
    call_command("check_ledger", stdout=out)
    assert "All 2 balances match" in out.getvalue()

    CreditAccount.objects.filter(user=player).update(balance_cents=49)
    err = StringIO()
    with pytest.raises(CommandError, match="1 of 2"):
        call_command("check_ledger", stdout=StringIO(), stderr=err)
    assert str(player.pk) in err.getvalue()


def test_deleting_the_account_deletes_its_credits_ledger_holds_and_counters(player):
    """T12: nothing billing keeps outlives the account."""
    from billing import meter

    meter.start(player, meter.TURN)
    assert CreditHold.objects.filter(user=player).exists()
    assert UsageCounter.objects.filter(user=player).exists()

    player.delete()

    for model in (CreditAccount, LedgerEntry, CreditHold, UsageCounter):
        assert not model.objects.exists()
