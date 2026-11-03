import io
import json
import logging
from datetime import date

import pytest
from django.test import Client

from lucid import logs
from lucid.logs import JsonFormatter


@pytest.fixture
def log_lines():
    """The JSON lines logged during the test, parsed, as Cloud Logging would receive them."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(project="test-project"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture(autouse=True)
def fresh_log_context():
    """A response a test never reads to the end (a file, a stream) keeps its request's log
    context open, as it would until the stream ends in production. Start each test clean."""
    logs._context.set(None)


# Signed-in players. Every endpoint except /health and /v1/auth/* needs an access token (T8).

ADULT_BIRTH_DATE = date(1995, 5, 17)
PASSWORD = "correct horse battery staple"


def auth_headers(user) -> dict[str, str]:
    """An `Authorization` header with a fresh access token for `user`."""
    from accounts.models import SignInMethod
    from accounts.tokens import issue

    return {"Authorization": f"Bearer {issue(user, SignInMethod.PASSWORD).access_token}"}


@pytest.fixture
def make_user(db):
    """Creates a player: an adult with a password, unless told otherwise."""
    from accounts.models import User

    def make(email: str = "player@example.com", **fields):
        fields.setdefault("birth_date", ADULT_BIRTH_DATE)
        fields.setdefault("display_name", email.split("@")[0])
        return User.objects.create_user(email, fields.pop("password", PASSWORD), **fields)

    return make


@pytest.fixture
def player(make_user):
    return make_user()


@pytest.fixture
def player_client(player) -> Client:
    """A test client signed in as `player`."""
    return Client(headers=auth_headers(player))
