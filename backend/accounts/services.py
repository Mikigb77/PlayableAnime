"""Sign-in, sign-up, profile, delete and export (T8, F8, K7, T12).

Sync functions that touch the database; the async views call them through `sync_to_async`.
"""

import logging
from datetime import date
from typing import Any

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts import rules, tokens
from accounts.google import GoogleIdentity
from accounts.models import Role, User
from accounts.signals import account_deleting, account_exporting
from lucid.errors import ApiError, ErrorCode, field_error

logger = logging.getLogger("lucid.auth")

DISPLAY_NAME_MAX = 80


def sign_in_with_google(identity: GoogleIdentity, birth_date: date | None) -> User:
    """Finds or creates the account for a verified Google identity.

    - A known Google account signs in.
    - Otherwise an email and password account with the same email takes on the Google identity,
      but only when Google vouches for the email. Its password was never verified, so whoever set
      it may not own the email (an attacker can sign up first with someone else's address): the
      password is dropped and its devices are signed out, and the email's owner signs in with
      Google from then on. An account already tied to another Google account is never moved.
    - Otherwise a new account is created, which needs a birth date (F8).

    The owner role follows `OWNER_EMAILS` on every Google sign-in (K7).
    """
    try:
        return _sign_in_with_google(identity, birth_date)
    except IntegrityError:
        # Two first sign-ins raced and the other created the account; this one now finds it.
        return _sign_in_with_google(identity, birth_date)


def _sign_in_with_google(identity: GoogleIdentity, birth_date: date | None) -> User:
    with transaction.atomic():
        user = User.objects.select_for_update().filter(google_sub=identity.sub).first()
        if user is None:
            if not identity.email_verified:
                raise ApiError(
                    ErrorCode.FORBIDDEN,
                    "Verify the email on your Google account, then try again.",
                )
            user = User.objects.select_for_update().filter(email=identity.email).first()
            if user is not None and user.google_sub and user.google_sub != identity.sub:
                # The email's account belongs to another Google account. Moving it silently would
                # hand it to whoever now holds the address (a recycled work email, say).
                raise ApiError(
                    ErrorCode.FORBIDDEN,
                    "This email is already used by another Google account. Sign in with that one.",
                )
            if user is not None and not user.google_sub:
                _take_over_with_google(user, identity)
        if user is not None and not user.is_active:
            raise ApiError(ErrorCode.FORBIDDEN, "This account is disabled.")
        if user is None or user.birth_date is None:
            if birth_date is None:
                raise ApiError(ErrorCode.BIRTH_DATE_REQUIRED)
            rules.check_birth_date(birth_date)
        if user is None:
            user = User.objects.create_user(
                identity.email,
                None,
                google_sub=identity.sub,
                email_verified=True,
                display_name=_display_name(identity.name) or identity.email.split("@")[0],
                birth_date=birth_date,
            )
            logger.info("Account created", extra={"user_id": str(user.pk), "method": "google"})
        elif user.birth_date is None:
            user.birth_date = birth_date
        _sync_owner_role(user, identity)
        user.last_login = timezone.now()
        user.save()
    return user


def _take_over_with_google(user: User, identity: GoogleIdentity) -> None:
    user.google_sub = identity.sub
    user.email_verified = True
    if user.has_usable_password():
        user.set_unusable_password()
        closed = tokens.revoke_all(user, "google_takeover")
        logger.warning(
            "A Google sign-in took over an email account; its password was dropped",
            extra={"user_id": str(user.pk), "sessions_closed": closed},
        )


def _sync_owner_role(user: User, identity: GoogleIdentity) -> None:
    """The owner role, with admin access, for a verified Google email in `OWNER_EMAILS` (K7).
    An owner who is no longer listed loses it at their next Google sign-in."""
    listed = identity.email_verified and rules.is_owner_email(identity.email)
    if listed and not user.is_owner:
        user.role = Role.OWNER
        user.is_staff = user.is_superuser = True
        logger.info("Owner role granted", extra={"user_id": str(user.pk)})
    elif not listed and user.is_owner:
        user.role = Role.PLAYER
        user.is_staff = user.is_superuser = False
        logger.warning("Owner role removed", extra={"user_id": str(user.pk)})


def register(email: str, password: str, display_name: str, birth_date: date) -> User:
    """A new email and password account. It never gets the owner role, whatever the email (K7),
    and stays unverified until an email provider exists."""
    email = email.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise field_error("email", "Enter a valid email address.", type="invalid_email") from None
    name = _display_name(display_name)
    if not name:
        raise field_error("display_name", "Enter a name.", type="missing")
    rules.check_birth_date(birth_date)
    _check_password(password, User(email=email, display_name=name))
    taken = field_error(
        "email", "An account with this email already exists. Sign in instead.", type="email_taken"
    )
    if User.objects.filter(email=email).exists():
        raise taken
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email, password, display_name=name, birth_date=birth_date, last_login=timezone.now()
            )
    except IntegrityError:
        # Another sign-up for the same email won the race.
        raise taken from None
    logger.info("Account created", extra={"user_id": str(user.pk), "method": "password"})
    return user


def _check_password(password: str, user: User) -> None:
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ApiError(
            ErrorCode.VALIDATION_ERROR,
            exc.messages[0],
            {
                "fields": [
                    {
                        "field": "password",
                        "source": "body",
                        "message": message,
                        "type": error.code or "invalid",
                    }
                    for error, message in zip(exc.error_list, exc.messages, strict=True)
                ]
            },
        ) from None


def log_in(email: str, password: str) -> User | None:
    """The account for these credentials, or None. The password hasher runs once whatever the
    case (unknown email, Google-only account, wrong password), so timing reveals nothing."""
    user = User.objects.filter(email=email.strip().lower()).first()
    if user is None or not user.has_usable_password():
        make_password(password)
        return None
    if not user.check_password(password) or not user.is_active:
        return None
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    return user


def update_profile(user: User, display_name: str | None, prefs: dict[str, Any] | None) -> User:
    fields = []
    if display_name is not None:
        name = _display_name(display_name)
        if not name:
            raise field_error("display_name", "Enter a name.", type="missing")
        user.display_name = name
        fields.append("display_name")
    if prefs:
        current = rules.content_prefs(user.content_prefs)
        user.content_prefs = rules.content_prefs({**current, **prefs})
        fields.append("content_prefs")
    if fields:
        user.save(update_fields=fields)
    return user


def delete_account(user: User) -> None:
    """Deletes the account and everything it owns: stories, scenes, sessions, and through
    `account_deleting` whatever lives elsewhere, such as pictures (T12, M4)."""
    user_id = str(user.pk)
    with transaction.atomic():
        account_deleting.send(sender=User, user=user)
        user.delete()
    logger.info("Account deleted", extra={"user_id": user_id})


def export_account(user: User, user_data: dict[str, Any]) -> dict[str, Any]:
    """`{"user": ..., "stories": [...]}` plus whatever `account_exporting` receivers add (T12)."""
    from stories.export import export_stories

    data: dict[str, Any] = {"user": user_data, "stories": export_stories(user.pk)}
    for receiver, extra in account_exporting.send(sender=User, user=user):
        if not isinstance(extra, dict):
            continue
        for key, value in extra.items():
            if key in data:
                logger.error("Export key %s is taken; %r's value is dropped", key, receiver)
                continue
            data[key] = value
    return data


def _display_name(name: str) -> str:
    return " ".join(name.split())[:DISPLAY_NAME_MAX]
