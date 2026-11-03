from decimal import Decimal

import pytest
from django.test import Client

from accounts.models import Role, User
from billing.pricing import ModelCall

# Known numbers for every billing test, whatever the env says.
BILLING = {
    "STARTER_CENTS": Decimal(50),
    "STARTER_POLICY": "verified",
    "MARGIN": Decimal("0.5"),
    "RESERVE_CENTS": {"turn": 5, "draft": 5, "image": 6},
    "HOLD_TTL_S": 600,
    "PER_MINUTE": {"turn": 1000, "draft": 1000, "image": 1000},
    "PER_DAY": {"turn": 1000, "draft": 1000, "image": 1000},
}


@pytest.fixture(autouse=True)
def billing_settings(settings):
    """The billing settings; a test changes them with `billing_settings["KEY"] = ...`."""
    settings.BILLING = {k: (dict(v) if isinstance(v, dict) else v) for k, v in BILLING.items()}
    return settings.BILLING


_counter = iter(range(1, 1_000_000))


@pytest.fixture
def make_user(db):
    """A user as WS6 creates them: verified when signed up with Google."""

    def make(*, google: bool = True, owner: bool = False, email: str | None = None) -> User:
        n = next(_counter)
        return User.objects.create_user(
            email or f"player{n}@example.com",
            google_sub=f"google-{n}" if google else None,
            role=Role.OWNER if owner else Role.PLAYER,
        )

    return make


@pytest.fixture
def player(make_user) -> User:
    """A normal, verified account with the $0.50 starter credit (K1)."""
    return make_user()


@pytest.fixture
def owner(make_user) -> User:
    return make_user(owner=True)


@pytest.fixture
def auth_client():
    """A client signed in as `user`. Uses the Django session until WS6's bearer tokens land."""

    def signed_in(user: User) -> Client:
        client = Client()
        client.force_login(user)
        return client

    return signed_in


def call(
    cost_usd: str, *, byok: bool = False, model: str = "gemini-3.5-flash", **usage
) -> ModelCall:
    """A model call that cost us `cost_usd` dollars."""
    return ModelCall(model=model, cost_usd=Decimal(cost_usd), byok=byok, **usage)
