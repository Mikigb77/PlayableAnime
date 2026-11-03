"""Brute-force guards for sign-in (T8): fixed-window counters kept in Postgres, so they hold
across Cloud Run instances. Per-user rate limits on the rest of the API are T9's (billing).

Keys are HMACs of what is counted, so the table never holds an email or an IP address.
"""

import math
import random
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from django.utils import timezone
from django.utils.crypto import salted_hmac

from accounts.models import Throttle
from lucid.errors import ApiError, ErrorCode

# About one hit in this many also deletes counters whose window ended long ago.
_PRUNE_ONE_IN = 100
_PRUNE_AFTER = timedelta(days=1)


@dataclass(frozen=True)
class Limit:
    name: str
    max_hits: int
    window_s: int


# Wrong passwords for one email: slows guessing to a crawl without locking a real player out
# for long.
LOGIN_FAILURES_PER_EMAIL = Limit("login-email", 10, 15 * 60)
# Wrong passwords from one address. Generous, because mobile carriers put many players behind
# one address.
LOGIN_FAILURES_PER_IP = Limit("login-ip", 100, 15 * 60)
# New email accounts from one address, against farming starter credit (K1).
REGISTRATIONS_PER_IP = Limit("register-ip", 10, 60 * 60)
# Google sign-ins from one address, against hammering the token check.
GOOGLE_SIGN_INS_PER_IP = Limit("google-ip", 60, 15 * 60)


def _key(limit: Limit, value: str) -> str:
    return salted_hmac("lucid.throttle", f"{limit.name}:{value}", algorithm="sha256").hexdigest()


def retry_after(limit: Limit, value: str) -> int | None:
    """Seconds until `value` may try again, or None if it isn't blocked."""
    row = Throttle.objects.filter(key=_key(limit, value)).first()
    if row is None or row.hits < limit.max_hits:
        return None
    ends = row.window_started_at + timedelta(seconds=limit.window_s)
    remaining = (ends - timezone.now()).total_seconds()
    return math.ceil(remaining) if remaining > 0 else None


def check(*checks: tuple[Limit, str]) -> None:
    """Raises `rate_limited` with `details.retry_after_s` if any of the limits is used up."""
    waits = [wait for limit, value in checks if (wait := retry_after(limit, value))]
    if waits:
        raise ApiError(
            ErrorCode.RATE_LIMITED,
            "Too many attempts. Wait a little, then try again.",
            {"retry_after_s": max(waits)},
        )


def hit(limit: Limit, value: str) -> int:
    """Counts one attempt in the current window, atomically, and returns the count."""
    now = timezone.now()
    window_cutoff = now - timedelta(seconds=limit.window_s)
    table = Throttle._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {table} AS t (key, window_started_at, hits) VALUES (%s, %s, 1)
            ON CONFLICT (key) DO UPDATE SET
                hits = CASE WHEN t.window_started_at <= %s THEN 1 ELSE t.hits + 1 END,
                window_started_at = CASE WHEN t.window_started_at <= %s
                    THEN EXCLUDED.window_started_at ELSE t.window_started_at END
            RETURNING hits
            """,
            [_key(limit, value), now, window_cutoff, window_cutoff],
        )
        (hits,) = cursor.fetchone()
    if random.randrange(_PRUNE_ONE_IN) == 0:
        Throttle.objects.filter(window_started_at__lt=now - _PRUNE_AFTER).delete()
    return hits


def reset(limit: Limit, value: str) -> None:
    Throttle.objects.filter(key=_key(limit, value)).delete()


def client_ip(request: HttpRequest) -> str:
    """The caller's address. On Cloud Run, Google's front end appends the address it saw to
    `X-Forwarded-For`, so the entry `TRUSTED_PROXY_HOPS` from the right is the real one; anything
    to its left came from the caller and can't be trusted."""
    forwarded = [part.strip() for part in request.headers.get("X-Forwarded-For", "").split(",")]
    forwarded = [part for part in forwarded if part]
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0 and len(forwarded) >= hops:
        return forwarded[-hops]
    return request.META.get("REMOTE_ADDR") or "unknown"
