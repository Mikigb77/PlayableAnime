"""Checks a Google ID token once, at sign-in (T8). After that the app uses our own tokens.

The token must be signed by one of Google's current keys, issued by Google, unexpired, and meant
for one of our OAuth clients (`GOOGLE_OAUTH_CLIENT_IDS`: the web, Android and iOS clients in the
`playable-anime` project). Google's public certificates are cached for as long as Google says they
stay valid, and fetched again when a token names a key we haven't seen (Google rotates them).

`verify_id_token` is sync and may fetch over the network, so call it off the event loop. Tests
replace it; `google.auth` is imported only when a token is checked, to keep cold starts fast (B10).
"""

import json
import logging
import re
import threading
import time
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger("lucid.auth")

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
# Allowed difference between Google's clock and ours.
CLOCK_SKEW_S = 30
_DEFAULT_CERTS_TTL_S = 3600
# A token naming an unknown key refetches at most this often, so junk tokens can't make us
# hammer Google.
_MIN_REFETCH_S = 60
_MAX_AGE = re.compile(r"max-age=(\d+)")


class GoogleTokenError(Exception):
    """The token isn't a valid Google ID token for one of our clients."""


class GoogleUnavailable(Exception):
    """Google's certificates couldn't be fetched, or Google sign-in isn't configured."""


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


class _CertCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._certs: dict[str, str] = {}
        self._expires_at = 0.0
        self._fetched_at = 0.0

    def get(self, key_id: str | None) -> dict[str, str]:
        with self._lock:
            now = time.monotonic()
            stale = now >= self._expires_at
            unknown_key = key_id is not None and key_id not in self._certs
            may_refetch = now - self._fetched_at >= _MIN_REFETCH_S
            if stale or (unknown_key and may_refetch):
                try:
                    self._certs, ttl = fetch_certs()
                    self._fetched_at = now
                    self._expires_at = now + ttl
                except Exception as exc:
                    if not self._certs:
                        raise GoogleUnavailable("Couldn't fetch Google's certificates") from exc
                    # Keep using the last good set; Google keeps keys valid well past rotation.
                    logger.warning("Couldn't refresh Google's certificates", exc_info=True)
            return dict(self._certs)

    def clear(self) -> None:
        with self._lock:
            self._certs, self._expires_at, self._fetched_at = {}, 0.0, 0.0


_cache = _CertCache()


def fetch_certs() -> tuple[dict[str, str], float]:
    """Google's signing certificates by key id, and how long they stay valid in seconds."""
    with urllib.request.urlopen(CERTS_URL, timeout=5) as response:
        certs = json.load(response)
        match = _MAX_AGE.search(response.headers.get("Cache-Control", ""))
    ttl = float(match.group(1)) if match else _DEFAULT_CERTS_TTL_S
    if not isinstance(certs, dict) or not certs:
        raise ValueError("Google returned no certificates")
    return certs, ttl


def verify_id_token(token: str) -> GoogleIdentity:
    client_ids = settings.GOOGLE_OAUTH_CLIENT_IDS
    if not client_ids:
        logger.error("Google sign-in was attempted, but GOOGLE_OAUTH_CLIENT_IDS is empty")
        raise GoogleUnavailable("Google sign-in isn't configured")

    from google.auth import exceptions as google_exceptions
    from google.auth import jwt as google_jwt

    try:
        header = google_jwt.decode_header(token)
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise GoogleTokenError("Malformed token") from exc
    if header.get("alg") != "RS256":
        raise GoogleTokenError("Unexpected signing algorithm")
    certs = _cache.get(header.get("kid"))
    try:
        claims = google_jwt.decode(
            token, certs=certs, audience=client_ids, clock_skew_in_seconds=CLOCK_SKEW_S
        )
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise GoogleTokenError(str(exc)) from exc

    if claims.get("iss") not in ISSUERS:
        raise GoogleTokenError("Not issued by Google")
    sub, email = claims.get("sub"), claims.get("email")
    if not sub or not email:
        raise GoogleTokenError("The token has no subject or email")
    verified = claims.get("email_verified")
    return GoogleIdentity(
        sub=str(sub),
        email=str(email).strip().lower(),
        # Older tokens send the string "true".
        email_verified=verified is True or verified == "true",
        name=str(claims.get("name") or "").strip(),
    )
