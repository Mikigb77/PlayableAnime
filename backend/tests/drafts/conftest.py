import pytest
from django.test import Client

from drafts import service
from graph.drafting import samples
from graph.drafting.schema import CharacterChange, WorldChange
from graph.llm import FakeBackend, Reply
from graph.llm.types import Request
from tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def funded_players(settings):
    """Every test account gets the starter credit, and the rate limit stays out of the way
    unless a test sets it (K1, T9)."""
    settings.BILLING = {
        **settings.BILLING,
        "STARTER_POLICY": "all",
        "PER_MINUTE": {**settings.BILLING["PER_MINUTE"], "draft": 1000},
        "PER_DAY": {**settings.BILLING["PER_DAY"], "draft": 1000},
    }


def _sample_reply(request: Request) -> Reply:
    """The Naples draft, or for a revision a change that changes nothing."""
    title = (request.json_schema or {}).get("title")
    if title == "WorldChange":
        return Reply(json=WorldChange())
    if title == "CharacterChange":
        return Reply(json=CharacterChange())
    return Reply(json=samples.naples())


@pytest.fixture
def model(monkeypatch) -> FakeBackend:
    """The drafting model for every request in the test: answers with the Naples sample unless
    a test scripts other replies. It also stands in for the player's own key."""
    fake = FakeBackend(default=_sample_reply)
    monkeypatch.setattr(service, "model_backend", lambda *, grounded, byok: fake)
    return fake


@pytest.fixture
def other_client(make_user) -> Client:
    return Client(headers=auth_headers(make_user("other@example.com")))
