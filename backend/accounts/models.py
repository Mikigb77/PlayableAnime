"""The custom User model, in the first migration so `AUTH_USER_MODEL` never has to change, and the
records sign-in keeps: signed-in devices with their rotating refresh tokens, and throttle counters.
"""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    PLAYER = "player", "Player"
    # Unlimited credits and admin access, granted only through a verified Google sign-in (K7).
    OWNER = "owner", "Owner"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **fields) -> "User":
        if not email:
            raise ValueError("A user needs an email address.")
        user = self.model(email=self.normalize_email(email).lower(), **fields)
        user.set_password(password)  # None stores an unusable password (Google-only accounts).
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **fields) -> "User":
        fields.setdefault("is_staff", False)
        fields.setdefault("is_superuser", False)
        return self._create(email, password, **fields)

    def create_superuser(self, email: str, password: str | None = None, **fields) -> "User":
        fields["is_staff"] = True
        fields["is_superuser"] = True
        return self._create(email, password, **fields)

    def get_by_natural_key(self, username: str | None) -> "User":
        return self.get(email__iexact=username)


class User(AbstractBaseUser, PermissionsMixin):
    """A player, signed in with Google or with an email and password (T8).

    The email is the login. It is stored lowercased, so it is unique regardless of case.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    # Asked at sign-up: Teen only under 17 (F8). Null until a new Google account gives it.
    birth_date = models.DateField(null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PLAYER)
    # Google's stable subject id (`sub`) from a verified ID token. Null for email-only accounts.
    google_sub = models.CharField(max_length=255, null=True, blank=True, unique=True)
    # Whether someone proved they own the email: true once Google vouches for it. Email and
    # password accounts stay unverified until an email provider exists.
    email_verified = models.BooleanField(default=False)
    # ContentPrefs from docs/API.md (F7): {gore, romance, dark_themes}. Missing keys take the
    # defaults in `accounts.rules.CONTENT_PREF_DEFAULTS`.
    content_prefs = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    # Staff can use the Django admin (B1).
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = self.email.lower()

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER


class SignInMethod(models.TextChoices):
    GOOGLE = "google", "Google"
    PASSWORD = "password", "Email and password"


class AuthSession(models.Model):
    """One signed-in device (T8): the family of refresh tokens that rotate from one sign-in.

    Access tokens name their session, so revoking it signs that device out at once: on logout,
    when a refresh token is reused after it rotated (a sign of theft), when a Google sign-in takes
    over an account that had an unverified password, and when the account is deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_sessions")
    method = models.CharField(max_length=16, choices=SignInMethod.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [models.Index(fields=["last_used_at"], name="auth_session_last_used_idx")]

    def __str__(self) -> str:
        return f"{self.user_id} via {self.method}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class RefreshToken(models.Model):
    """A refresh token, stored only as its SHA-256 hash. Each is good for one refresh, which
    returns a new one in the same session (rotation)."""

    token_hash = models.CharField(max_length=64, unique=True)
    session = models.ForeignKey(AuthSession, on_delete=models.CASCADE, related_name="tokens")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    # Set when the token is exchanged. A second exchange after the leeway revokes the session.
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"refresh token for session {self.session_id}"


class Throttle(models.Model):
    """A fixed-window counter in Postgres, so a limit holds across Cloud Run instances. The key
    is an HMAC of what is counted (an email or an IP address), never the value itself."""

    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField()
    hits = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.key[:12]}: {self.hits}"
