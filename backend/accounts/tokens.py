"""Our own tokens (T8). After a sign-in, the app holds two:

- An **access token**, good for `ACCESS_TOKEN_TTL_S` (15 minutes) and sent on every request. It is
  signed with `DJANGO_SECRET_KEY` (HMAC-SHA256 through `django.core.signing`) and names the user
  and the session, so checking it needs one query, which also sees a revoked session at once.
- A **refresh token**, a random 256-bit string stored only as its SHA-256 hash. It is good for one
  refresh within `REFRESH_TOKEN_TTL_S`, which returns a new pair in the same session (rotation).

A refresh token presented again after it rotated means two holders, so the session is revoked
(theft detection), except within `REUSE_LEEWAY_S` of the first use, when a retry whose response
was lost on a mobile network gets a fresh pair instead of a sign-out.

These functions are sync and touch the database; call them through `sync_to_async`.
"""

import hashlib
import logging
import random
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import AuthSession, RefreshToken, SignInMethod, User
from lucid.errors import ApiError, ErrorCode

logger = logging.getLogger("lucid.auth")

ACCESS_TOKEN_TTL_S = 15 * 60
REFRESH_TOKEN_TTL_S = 30 * 24 * 3600
REUSE_LEEWAY_S = 60
# Used refresh tokens are kept this long so a late reuse is still caught, then pruned.
USED_TOKEN_KEEP_S = 7 * 24 * 3600
_ACCESS_SALT = "lucid.auth.access"
# About one sign-in in this many also prunes sessions that can no longer refresh.
_PRUNE_ONE_IN = 50

SESSION_EXPIRED = "Your session ended. Sign in again."


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    session: AuthSession
    access_token: str
    refresh_token: str
    expires_in: int = ACCESS_TOKEN_TTL_S


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def make_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return signing.dumps({"u": str(user_id), "s": str(session_id)}, salt=_ACCESS_SALT)


def read_access_token(token: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    """The user and session ids from a valid, unexpired access token, or None."""
    try:
        payload = signing.loads(token, salt=_ACCESS_SALT, max_age=ACCESS_TOKEN_TTL_S)
        return uuid.UUID(payload["u"]), uuid.UUID(payload["s"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def _new_refresh_token(session: AuthSession) -> str:
    raw = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        session=session,
        token_hash=hash_token(raw),
        expires_at=timezone.now() + timedelta(seconds=REFRESH_TOKEN_TTL_S),
    )
    return raw


def issue(user: User, method: SignInMethod) -> IssuedTokens:
    """Starts a session for a user who just proved who they are."""
    with transaction.atomic():
        session = AuthSession.objects.create(user=user, method=method)
        refresh = _new_refresh_token(session)
    if random.randrange(_PRUNE_ONE_IN) == 0:
        prune()
    return IssuedTokens(user, session, make_access_token(user.pk, session.pk), refresh)


def refresh(raw: str) -> IssuedTokens:
    """Exchanges a refresh token for a new pair in the same session.

    Raises `unauthenticated` for an unknown, expired or revoked token. A reuse after the leeway
    revokes the session before raising, so whoever holds the other copy is signed out too.
    """
    now = timezone.now()
    with transaction.atomic():
        token = (
            RefreshToken.objects.select_for_update(of=("self",))
            .select_related("session__user")
            .filter(token_hash=hash_token(raw))
            .first()
        )
        if token is None or token.expires_at <= now:
            raise ApiError(ErrorCode.UNAUTHENTICATED, SESSION_EXPIRED)
        session = token.session
        if session.is_revoked or not session.user.is_active:
            raise ApiError(ErrorCode.UNAUTHENTICATED, SESSION_EXPIRED)
        reused = token.used_at is not None
        if reused and (now - token.used_at).total_seconds() > REUSE_LEEWAY_S:
            _revoke(session, "refresh_reuse", now)
            stolen = True
        else:
            stolen = False
            if not reused:
                token.used_at = now
                token.save(update_fields=["used_at"])
            new_refresh = _new_refresh_token(session)
            session.last_used_at = now
            session.save(update_fields=["last_used_at"])
            RefreshToken.objects.filter(
                session=session, used_at__lt=now - timedelta(seconds=USED_TOKEN_KEEP_S)
            ).delete()
    if stolen:
        # Raised after the transaction commits, so the revocation sticks.
        logger.warning(
            "A rotated refresh token was used again; the session is revoked",
            extra={"user_id": str(session.user_id), "session_id": str(session.pk)},
        )
        raise ApiError(ErrorCode.UNAUTHENTICATED, SESSION_EXPIRED)
    user = session.user
    return IssuedTokens(user, session, make_access_token(user.pk, session.pk), new_refresh)


def revoke_by_refresh_token(raw: str) -> AuthSession | None:
    """Logout: revokes the session this refresh token belongs to, whether or not the token
    already rotated. Unknown tokens are ignored, so logout is safe to repeat."""
    with transaction.atomic():
        token = (
            RefreshToken.objects.select_related("session")
            .filter(token_hash=hash_token(raw))
            .first()
        )
        if token is None or token.session.is_revoked:
            return None
        _revoke(token.session, "logout", timezone.now())
        return token.session


def revoke_all(user: User, reason: str) -> int:
    """Signs a user out everywhere. Returns how many sessions were open."""
    return AuthSession.objects.filter(user=user, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason=reason
    )


def _revoke(session: AuthSession, reason: str, now) -> None:
    session.revoked_at = now
    session.revoked_reason = reason
    session.save(update_fields=["revoked_at", "revoked_reason"])
    # A revoked session can never refresh again, so its tokens are only clutter.
    session.tokens.all().delete()


def prune() -> int:
    """Deletes sessions that can no longer refresh: revoked, or idle past the refresh lifetime.
    Returns how many went."""
    now = timezone.now()
    idle = Q(last_used_at__lt=now - timedelta(seconds=REFRESH_TOKEN_TTL_S + REUSE_LEEWAY_S))
    # Kept a little while after revocation so staff can see why a device was signed out.
    revoked = Q(revoked_at__lt=now - timedelta(seconds=ACCESS_TOKEN_TTL_S))
    _, deleted = AuthSession.objects.filter(idle | revoked).delete()
    return deleted.get(AuthSession._meta.label, 0)
