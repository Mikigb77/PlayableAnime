import io
import json
import logging
import sys
import time
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


@pytest.fixture
def steady_minute():
    """For a test that makes real requests against a per-minute limit: the limit counts in
    fixed windows on the clock (`billing.limits`), so the requests must fall in one minute.
    A test that starts in a minute's last seconds waits for the next one. On CI one draft went
    out at 07:54:59.99 and the next at 07:55:00.02, and both were let through (2026-11-13)."""
    left = 60 - time.time() % 60
    if left < 5:
        time.sleep(left + 0.05)


@pytest.fixture(autouse=True)
def fresh_log_context():
    """A response a test never reads to the end (a file, a stream) keeps its request's log
    context open, as it would until the stream ends in production. Start each test clean."""
    logs._context.set(None)


@pytest.fixture(autouse=True)
def nothing_said_yet():
    """S10: how the model said a line is remembered while the process lives
    (`graph.turn.saying`). Start each test with nothing said, without loading the turn graph for
    tests that never play a turn."""
    saying = sys.modules.get("graph.turn.saying")
    if saying is not None:
        saying.forget()


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
