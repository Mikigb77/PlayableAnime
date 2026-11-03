"""F2, F8: a story above the account's rating limit is closed on every story route, now and for
routes added later, so a new endpoint can't forget the check."""

import json
import uuid

import pytest
from django.test import Client

from lucid.api import api
from stories.models import Engine
from tests.conftest import auth_headers
from tests.moderation.conftest import TEEN_BIRTH_DATE

pytestmark = pytest.mark.django_db

# Enough for any story route's body to validate, so the rating check is what answers.
BODY = {
    "action": "look around",
    "kind": "action",
    "input_mode": "typed",
    "expected_version": 0,
    "category": "other",
    "block": False,
}


def story_routes() -> list[tuple[str, str]]:
    routes = []
    for prefix, router in api._routers:
        for path, view in router.path_operations.items():
            if "{story_id}" not in path:
                continue
            for operation in view.operations:
                routes += [(method, f"/v1{prefix}{path}") for method in operation.methods]
    return routes


def test_the_story_routes_are_found():
    assert ("POST", "/v1/stories/{story_id}/scenes/{turn}/report") in story_routes()
    assert len(story_routes()) >= 7


@pytest.mark.parametrize(("method", "path"), story_routes())
def test_a_teen_account_is_refused_a_mature_story_everywhere(make_user, make_story, method, path):
    teen = make_user("teen@example.com", birth_date=TEEN_BIRTH_DATE)
    client = Client(headers=auth_headers(teen))
    statuses = []
    # A route may serve only one engine's stories and answer 404 for the other.
    for engine in (Engine.LEGACY, Engine.GRAPH):
        story = make_story(teen, rating="mature", engine=engine)
        url = (
            path.replace("{story_id}", str(story.id))
            .replace("{turn}", "1")
            .replace("{image_id}", str(uuid.uuid4()))
        )
        response = client.generic(method, url, json.dumps(BODY), content_type="application/json")
        statuses.append(response.status_code)
        if response.status_code == 403:
            assert response.json()["error"]["code"] == "forbidden"
    assert 403 in statuses, statuses
    assert all(status in (403, 404) for status in statuses), statuses


def test_the_same_teen_plays_a_teen_story(make_user, make_story):
    teen = make_user("teen@example.com", birth_date=TEEN_BIRTH_DATE)
    story = make_story(teen, rating="teen")
    client = Client(headers=auth_headers(teen))
    response = client.post(
        f"/v1/stories/{story.id}/scenes/1/report",
        json.dumps({"category": "other"}),
        content_type="application/json",
    )
    assert response.status_code == 204
