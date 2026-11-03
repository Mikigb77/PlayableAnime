"""`/v1/me`: the profile, content preferences, deleting the account and exporting it (F7, T12)."""

import json
from datetime import date

import pytest
from django.db import connection
from django.test import Client

from accounts.models import AuthSession, RefreshToken, User
from accounts.signals import account_deleting, account_exporting
from stories.models import PendingEvent, Scene, Story
from tests.conftest import auth_headers

pytestmark = pytest.mark.django_db


def _story(owner, title="The Drowned Capital", turns=2, **fields) -> Story:
    story = Story.objects.create(
        owner=owner,
        title=title,
        premise="A ronin wakes in a flooded city.",
        state={"secret": "The magistrate is the killer."},
        turn=turns,
        **fields,
    )
    for turn in range(1, turns + 1):
        Scene.objects.create(
            story=story,
            turn=turn,
            kind="opening" if turn == 1 else "action",
            player_action=None if turn == 1 else f"Action {turn}",
            input_mode=None if turn == 1 else "typed",
            narration=f"Scene {turn}.",
            choices=[{"id": "c1", "label": "Wait", "kind": "thread"}],
            time_label=f"Day {turn}, dusk",
        )
    return story


def test_me_returns_the_account(player_client, player):
    response = player_client.get("/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(player.pk),
        "email": "player@example.com",
        "display_name": "player",
        "role": "player",
        "max_rating": "mature",
        "content_prefs": {"gore": "medium", "romance": True, "dark_themes": True},
        # An email account gets K1's starter credit once its address is verified.
        "credits": {"balance_cents": 0, "unlimited": False},
    }


def test_a_teen_account_shows_its_teen_limit(make_user):
    today = date.today()
    teen = make_user("teen@example.com", birth_date=today.replace(year=today.year - 16))

    response = Client(headers=auth_headers(teen)).get("/v1/me")

    assert response.json()["max_rating"] == "teen"


def test_patch_changes_the_name_and_only_the_preferences_sent(player_client, player):
    response = player_client.patch(
        "/v1/me",
        {"display_name": "  Kaede   Mori ", "content_prefs": {"gore": "high"}},
        content_type="application/json",
    )
    response = player_client.patch(
        "/v1/me", {"content_prefs": {"romance": False}}, content_type="application/json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Kaede Mori"
    assert body["content_prefs"] == {"gore": "high", "romance": False, "dark_themes": True}
    player.refresh_from_db()
    assert player.content_prefs == {"gore": "high", "romance": False, "dark_themes": True}


def test_an_empty_patch_changes_nothing(player_client):
    response = player_client.patch("/v1/me", {}, content_type="application/json")

    assert response.status_code == 200
    assert response.json()["display_name"] == "player"


@pytest.mark.parametrize(
    "body",
    [
        {"content_prefs": {"gore": "extreme"}},
        {"content_prefs": {"romance": "maybe"}},
        {"display_name": ""},
        {"display_name": "   "},
        {"display_name": "x" * 81},
    ],
)
def test_patch_refuses_bad_values(player_client, body):
    response = player_client.patch("/v1/me", body, content_type="application/json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_the_role_and_birth_date_cant_be_patched(player_client, player):
    player_client.patch(
        "/v1/me",
        {"role": "owner", "birth_date": "2015-01-01", "email": "x@example.com"},
        content_type="application/json",
    )

    player.refresh_from_db()
    assert (player.role, player.email) == ("player", "player@example.com")
    assert player.birth_date.year == 1995


def test_delete_removes_the_account_and_everything_it_owns(player_client, player, make_user):
    story = _story(player)
    PendingEvent.objects.create(story=story, due_world_s=60, kind="arrival")
    other = make_user("other@example.com")
    kept = _story(other, title="Someone else's")
    calls = []

    def on_delete(sender, user, **kwargs):
        calls.append((user.pk, connection.in_atomic_block))

    account_deleting.connect(on_delete)
    try:
        response = player_client.delete("/v1/me")
    finally:
        account_deleting.disconnect(on_delete)

    assert response.status_code == 204
    assert calls == [(player.pk, True)]
    assert list(User.objects.all()) == [other]
    assert list(Story.objects.all()) == [kept]
    assert Scene.objects.filter(story=kept).count() == Scene.objects.count()
    assert not PendingEvent.objects.exists()
    assert not AuthSession.objects.filter(user_id=player.pk).exists()
    assert not RefreshToken.objects.exists()
    assert player_client.get("/v1/me").status_code == 401


def test_a_failing_delete_hook_deletes_nothing(player_client, player):
    _story(player)

    def fail(sender, user, **kwargs):
        raise RuntimeError("storage is down")

    account_deleting.connect(fail)
    try:
        response = player_client.delete("/v1/me")
    finally:
        account_deleting.disconnect(fail)

    assert response.status_code == 500
    assert User.objects.filter(pk=player.pk).exists()
    assert Story.objects.filter(owner=player).exists()


def test_export_has_the_account_and_every_story_with_all_its_scenes(
    player_client, player, make_user
):
    first = _story(player, title="First", turns=3)
    second = _story(player, title="Second", turns=1)
    _story(make_user("other@example.com"), title="Not mine")

    response = player_client.get("/v1/me/export")

    assert response.status_code == 200
    assert "attachment" in response["Content-Disposition"]
    data = json.loads(response.content)
    assert data["user"] == player_client.get("/v1/me").json()
    assert [s["id"] for s in data["stories"]] == [str(first.pk), str(second.pk)]
    story = data["stories"][0]
    assert story["premise"] == "A ronin wakes in a flooded city."
    assert [scene["turn"] for scene in story["scenes"]] == [1, 2, 3]
    assert story["scenes"][1]["player_action"] == "Action 2"
    assert story["scenes"][1]["time"]["label"] == "Day 2, dusk"
    assert story["scenes"][1]["choices"] == [{"id": "c1", "label": "Wait", "kind": "thread"}]
    # Hidden truths stay hidden (C6, N7).
    assert "state" not in story
    assert "magistrate" not in response.content.decode()


def test_export_includes_what_other_apps_add_but_never_replaces_the_core(player_client, player):
    # `images` is taken by the pictures app's own receiver, so this one adds something else.
    def badges(sender, user, **kwargs):
        return {"badges": [{"id": "badge-1"}], "user": "overwritten?"}

    account_exporting.connect(badges)
    try:
        data = player_client.get("/v1/me/export").json()
    finally:
        account_exporting.disconnect(badges)

    assert data["badges"] == [{"id": "badge-1"}]
    assert data["images"] == []
    assert data["user"]["id"] == str(player.pk)


def test_me_needs_a_signed_in_player():
    for method in ("get", "patch", "delete"):
        assert getattr(Client(), method)("/v1/me").status_code == 401
    assert Client().get("/v1/me/export").status_code == 401
