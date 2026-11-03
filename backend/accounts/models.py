"""The custom User model, in the first migration so `AUTH_USER_MODEL` never has to change."""

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
