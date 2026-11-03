"""Our access and refresh tokens (T8): signed short-lived access, rotating hashed refresh."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts import tokens
from accounts.models import AuthSession, RefreshToken, SignInMethod
from lucid.errors import ApiError

pytestmark = pytest.mark.django_db


def test_an_access_token_names_its_user_and_session(player):
    issued = tokens.issue(player, SignInMethod.PASSWORD)

    assert tokens.read_access_token(issued.access_token) == (player.pk, issued.session.pk)
    assert issued.expires_in == 15 * 60


def test_a_tampered_or_foreign_access_token_is_refused(player):
    issued = tokens.issue(player, SignInMethod.PASSWORD)
    payload, _, signature = issued.access_token.rpartition(":")

    assert tokens.read_access_token(payload + ":" + signature[::-1]) is None
    assert tokens.read_access_token("not-a-token") is None
    assert tokens.read_access_token(issued.refresh_token) is None


def test_an_access_token_expires(player, monkeypatch):
    issued = tokens.issue(player, SignInMethod.PASSWORD)
    monkeypatch.setattr(tokens, "ACCESS_TOKEN_TTL_S", -1)

    assert tokens.read_access_token(issued.access_token) is None


def test_refresh_tokens_are_stored_only_as_hashes(player):
    issued = tokens.issue(player, SignInMethod.PASSWORD)

    stored = RefreshToken.objects.get()
    assert stored.token_hash == tokens.hash_token(issued.refresh_token)
    assert issued.refresh_token not in stored.token_hash
    assert len(issued.refresh_token) >= 43


def test_a_refresh_rotates_the_token_in_the_same_session(player):
    first = tokens.issue(player, SignInMethod.PASSWORD)

    second = tokens.refresh(first.refresh_token)

    assert second.session == first.session
    assert second.refresh_token != first.refresh_token
    assert tokens.read_access_token(second.access_token) == (player.pk, first.session.pk)
    assert RefreshToken.objects.get(token_hash=tokens.hash_token(first.refresh_token)).used_at


def test_a_retry_within_the_leeway_gets_a_fresh_pair_instead_of_a_sign_out(player):
    """The first refresh's response was lost on a mobile network, so the app sends it again."""
    first = tokens.issue(player, SignInMethod.PASSWORD)
    tokens.refresh(first.refresh_token)

    again = tokens.refresh(first.refresh_token)

    assert again.session == first.session
    assert not AuthSession.objects.get().is_revoked


def test_a_rotated_token_used_again_later_revokes_the_session(player, log_lines):
    """Two holders of one refresh token means one stole it: both are signed out."""
    first = tokens.issue(player, SignInMethod.PASSWORD)
    second = tokens.refresh(first.refresh_token)
    RefreshToken.objects.filter(token_hash=tokens.hash_token(first.refresh_token)).update(
        used_at=timezone.now() - timedelta(seconds=tokens.REUSE_LEEWAY_S + 1)
    )

    with pytest.raises(ApiError) as raised:
        tokens.refresh(first.refresh_token)

    assert raised.value.code == "unauthenticated"
    session = AuthSession.objects.get()
    assert (session.is_revoked, session.revoked_reason) == (True, "refresh_reuse")
    with pytest.raises(ApiError):
        tokens.refresh(second.refresh_token)
    [warning] = [line for line in log_lines() if line["severity"] == "WARNING"]
    assert warning["user_id"] == str(player.pk)
    assert first.refresh_token not in str(log_lines())


@pytest.mark.parametrize("token", ["unknown", ""])
def test_an_unknown_refresh_token_is_unauthenticated(token):
    with pytest.raises(ApiError) as raised:
        tokens.refresh(token)

    assert raised.value.code == "unauthenticated"


def test_an_expired_refresh_token_is_refused(player):
    issued = tokens.issue(player, SignInMethod.PASSWORD)
    RefreshToken.objects.update(expires_at=timezone.now())

    with pytest.raises(ApiError):
        tokens.refresh(issued.refresh_token)


def test_a_disabled_account_cant_refresh(player):
    issued = tokens.issue(player, SignInMethod.PASSWORD)
    player.is_active = False
    player.save()

    with pytest.raises(ApiError):
        tokens.refresh(issued.refresh_token)


def test_logout_revokes_the_session_even_with_a_rotated_token(player):
    first = tokens.issue(player, SignInMethod.PASSWORD)
    tokens.refresh(first.refresh_token)

    assert tokens.revoke_by_refresh_token(first.refresh_token) == first.session
    assert AuthSession.objects.get().revoked_reason == "logout"
    assert not RefreshToken.objects.exists()
    assert tokens.revoke_by_refresh_token(first.refresh_token) is None


def test_revoke_all_signs_a_user_out_everywhere(player, make_user):
    tokens.issue(player, SignInMethod.PASSWORD)
    tokens.issue(player, SignInMethod.GOOGLE)
    other = tokens.issue(make_user("other@example.com"), SignInMethod.PASSWORD)

    assert tokens.revoke_all(player, "test") == 2
    assert not AuthSession.objects.get(pk=other.session.pk).is_revoked


def test_prune_drops_sessions_that_can_no_longer_refresh(player):
    idle = tokens.issue(player, SignInMethod.PASSWORD).session
    revoked = tokens.issue(player, SignInMethod.PASSWORD).session
    live = tokens.issue(player, SignInMethod.PASSWORD).session
    long_ago = timezone.now() - timedelta(seconds=tokens.REFRESH_TOKEN_TTL_S * 2)
    AuthSession.objects.filter(pk=idle.pk).update(last_used_at=long_ago)
    AuthSession.objects.filter(pk=revoked.pk).update(revoked_at=long_ago)

    assert tokens.prune() == 2
    assert list(AuthSession.objects.all()) == [live]
