"""`GET /v1/me/credits` (K1, K2, K7), in the shapes from docs/API.md."""

import uuid

import pytest
from django.test import Client

from billing import meter
from tests.billing.conftest import call

pytestmark = pytest.mark.django_db


def test_credits_need_a_signed_in_user():
    response = Client().get("/v1/me/credits")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_a_new_player_sees_the_starter_credit(player, auth_client):
    body = auth_client(player).get("/v1/me/credits").json()

    assert body["balance_cents"] == 50
    assert body["unlimited"] is False
    (entry,) = body["entries"]
    assert entry["kind"] == "starter"
    assert (entry["amount_cents"], entry["balance_after_cents"]) == (50, 50)
    assert (entry["story_id"], entry["turn"]) == (None, None)
    assert set(entry) == {
        "id",
        "kind",
        "amount_cents",
        "balance_after_cents",
        "story_id",
        "turn",
        "created_at",
    }


def test_entries_come_newest_first_with_fractional_cents(player, auth_client):
    story = uuid.uuid4()
    for turn in (1, 2):
        ticket = meter.start(player, meter.TURN)
        meter.charge(ticket, [call("0.0206")], story_id=story, turn=turn)

    body = auth_client(player).get("/v1/me/credits?limit=2").json()

    assert body["balance_cents"] == pytest.approx(50 - 2 * 3.09)
    assert [e["turn"] for e in body["entries"]] == [2, 1]
    assert body["entries"][0]["amount_cents"] == -3.09
    assert body["entries"][0]["story_id"] == str(story)
    assert body["entries"][0]["kind"] == "turn"


def test_the_owner_is_unlimited_and_still_sees_the_costs(owner, auth_client):
    ticket = meter.start(owner, meter.TURN)
    meter.charge(ticket, [call("0.02")], turn=1)

    body = auth_client(owner).get("/v1/me/credits").json()

    assert body["unlimited"] is True
    assert body["entries"][0]["amount_cents"] == 0


def test_the_limit_is_bounded(player, auth_client):
    response = auth_client(player).get("/v1/me/credits?limit=201")

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["field"] == "limit"
