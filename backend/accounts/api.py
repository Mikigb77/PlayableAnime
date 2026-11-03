"""The auth and account endpoints from docs/API.md (T8, S8, F8, K7, T12).

`/v1/auth/*` is open (it is how a player gets a token); `/v1/me` needs one like everything else.
"""

import logging
from datetime import date
from typing import Any, Literal

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from ninja import Field, Router, Schema, Status

from accounts import google, rules, services, throttle, tokens
from accounts.models import SignInMethod, User
from lucid import logs
from lucid.errors import ApiError, ErrorCode

logger = logging.getLogger("lucid.auth")

auth_router = Router(tags=["auth"], auth=None)
me_router = Router(tags=["account"])


class ContentPrefs(Schema):
    gore: Literal["low", "medium", "high"]
    romance: bool
    dark_themes: bool


class ContentPrefsPatch(Schema):
    gore: Literal["low", "medium", "high"] | None = None
    romance: bool | None = None
    dark_themes: bool | None = None


class Credits(Schema):
    balance_cents: float
    unlimited: bool


class UserOut(Schema):
    id: str
    email: str
    display_name: str
    role: Literal["player", "owner"]
    max_rating: Literal["teen", "mature"]
    content_prefs: ContentPrefs
    credits: Credits


class SessionOut(Schema):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserOut


class GoogleIn(Schema):
    id_token: str = Field(min_length=1, max_length=8192)
    birth_date: date | None = None


class RegisterIn(Schema):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=80)
    birth_date: date


class LoginIn(Schema):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(Schema):
    refresh_token: str = Field(min_length=1, max_length=256)


class MePatch(Schema):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    content_prefs: ContentPrefsPatch | None = None


def credits_for(user: User) -> dict[str, Any]:
    """The `credits` part of `User` (K1, K7). Billing (WS7) wires the ledger balance in here."""
    return {"balance_cents": 0, "unlimited": user.is_owner}


def user_data(user: User) -> dict[str, Any]:
    return {
        "id": str(user.pk),
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "max_rating": rules.max_rating(user.birth_date),
        "content_prefs": rules.content_prefs(user.content_prefs),
        "credits": credits_for(user),
    }


def _session(issued: tokens.IssuedTokens) -> dict[str, Any]:
    logs.bind(user_id=str(issued.user.pk))
    return {
        "access_token": issued.access_token,
        "refresh_token": issued.refresh_token,
        "expires_in": issued.expires_in,
        "user": user_data(issued.user),
    }


# Sign-in


def _google(id_token: str, birth_date: date | None) -> tokens.IssuedTokens:
    try:
        identity = google.verify_id_token(id_token)
    except google.GoogleTokenError as exc:
        logger.info("A Google ID token was refused: %s", exc)
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Google sign-in failed. Try again.") from None
    except google.GoogleUnavailable:
        logger.exception("Google sign-in is unavailable")
        raise ApiError(
            ErrorCode.UNAUTHENTICATED, "Google sign-in isn't available right now. Try again soon."
        ) from None
    user = services.sign_in_with_google(identity, birth_date)
    return tokens.issue(user, SignInMethod.GOOGLE)


@auth_router.post("/google", response=SessionOut)
async def sign_in_with_google(request: HttpRequest, body: GoogleIn) -> dict[str, Any]:
    """Signs in with a Google ID token, creating the account on first use. A new account needs
    `birth_date` (F8), or the answer is `birth_date_required` and the app asks for it."""
    issued = await sync_to_async(_google)(body.id_token, body.birth_date)
    return _session(issued)


def _register(body: RegisterIn, ip: str) -> tokens.IssuedTokens:
    throttle.check((throttle.REGISTRATIONS_PER_IP, ip))
    throttle.hit(throttle.REGISTRATIONS_PER_IP, ip)
    user = services.register(body.email, body.password, body.display_name, body.birth_date)
    return tokens.issue(user, SignInMethod.PASSWORD)


@auth_router.post("/register", response=SessionOut)
async def register(request: HttpRequest, body: RegisterIn) -> dict[str, Any]:
    issued = await sync_to_async(_register)(body, throttle.client_ip(request))
    return _session(issued)


def _log_in(email: str, password: str, ip: str) -> tokens.IssuedTokens:
    email = email.strip().lower()
    throttle.check((throttle.LOGIN_FAILURES_PER_EMAIL, email), (throttle.LOGIN_FAILURES_PER_IP, ip))
    user = services.log_in(email, password)
    if user is None:
        throttle.hit(throttle.LOGIN_FAILURES_PER_EMAIL, email)
        throttle.hit(throttle.LOGIN_FAILURES_PER_IP, ip)
        raise ApiError(ErrorCode.UNAUTHENTICATED, "Wrong email or password.")
    throttle.reset(throttle.LOGIN_FAILURES_PER_EMAIL, email)
    return tokens.issue(user, SignInMethod.PASSWORD)


@auth_router.post("/login", response=SessionOut)
async def log_in(request: HttpRequest, body: LoginIn) -> dict[str, Any]:
    """A wrong email or password is `unauthenticated`. Repeated failures for one email or from
    one address are `rate_limited` for a while."""
    issued = await sync_to_async(_log_in)(body.email, body.password, throttle.client_ip(request))
    return _session(issued)


@auth_router.post("/refresh", response=SessionOut)
async def refresh(request: HttpRequest, body: RefreshIn) -> dict[str, Any]:
    """A new access token and a new refresh token; the old refresh token is spent."""
    issued = await sync_to_async(tokens.refresh)(body.refresh_token)
    return _session(issued)


@auth_router.post("/logout", response={204: None})
async def log_out(request: HttpRequest, body: RefreshIn) -> Status:
    """Signs this device out. Safe to repeat."""
    session = await sync_to_async(tokens.revoke_by_refresh_token)(body.refresh_token)
    if session is not None:
        logs.bind(user_id=str(session.user_id))
    return Status(204, None)


# The signed-in account


@me_router.get("", response=UserOut)
async def get_me(request: HttpRequest) -> dict[str, Any]:
    return user_data(request.auth)


@me_router.patch("", response=UserOut)
async def update_me(request: HttpRequest, body: MePatch) -> dict[str, Any]:
    prefs = body.content_prefs.model_dump(exclude_none=True) if body.content_prefs else None
    user = await sync_to_async(services.update_profile)(request.auth, body.display_name, prefs)
    return user_data(user)


@me_router.delete("", response={204: None})
async def delete_me(request: HttpRequest) -> Status:
    """Deletes the account, its stories and its pictures, at once and for good (T12)."""
    await sync_to_async(services.delete_account)(request.auth)
    return Status(204, None)


@me_router.get("/export")
async def export_me(request: HttpRequest) -> JsonResponse:
    """Everything the account holds, as one JSON download (T12)."""
    user = request.auth
    data = await sync_to_async(services.export_account)(user, user_data(user))
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    response["Content-Disposition"] = 'attachment; filename="lucid-saga-export.json"'
    return response
