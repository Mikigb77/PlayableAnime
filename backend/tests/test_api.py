import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app(Settings(llm_provider="fake", database_url=None))
    with TestClient(app) as client:
        yield client


def _create_story(client: TestClient) -> dict:
    response = client.post("/v1/stories", json={"premise": "A courier finds a strange package."})
    assert response.status_code == 201
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "storage": "memory"}


def test_premises_are_listed(client):
    premises = client.get("/v1/premises").json()

    assert len(premises) >= 1
    assert {"id", "title", "genre", "premise"} <= premises[0].keys()


def test_creating_a_story_generates_the_opening_scene(client):
    story = _create_story(client)

    assert story["title"] == "A courier finds a strange package."
    assert len(story["scenes"]) == 1
    assert story["scenes"][0]["player_action"] is None
    assert [c["id"] for c in story["scenes"][0]["choices"]] == ["c1", "c2", "c3"]
    assert story["state"]["turn"] == 1


def test_turns_advance_the_story_and_its_memory(client):
    story = _create_story(client)
    url = f"/v1/stories/{story['id']}/turns"

    by_choice = client.post(url, json={"choice_id": "c1"}).json()
    by_action = client.post(url, json={"action": "I climb."}).json()

    assert by_choice["scene"]["player_action"] == "Follow the sound of the bell"
    assert by_action["scene"]["player_action"] == "I climb."
    memory = client.get(f"/v1/stories/{story['id']}/memory").json()
    assert memory["turn"] == 3
    assert [(c["id"], c["affinity"]) for c in memory["characters"]] == [("ren", 3)]


def test_library_lists_the_most_recently_played_story_first(client):
    older = _create_story(client)
    newer = _create_story(client)
    client.post(f"/v1/stories/{older['id']}/turns", json={"choice_id": "c1"})

    summaries = client.get("/v1/stories").json()

    assert [s["id"] for s in summaries[:2]] == [older["id"], newer["id"]]
    assert summaries[0]["turn"] == 2


def test_turn_needs_exactly_one_of_choice_or_action(client):
    story = _create_story(client)
    url = f"/v1/stories/{story['id']}/turns"

    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"choice_id": "c1", "action": "Both"}).status_code == 422


def test_unknown_choice_is_rejected(client):
    story = _create_story(client)

    response = client.post(f"/v1/stories/{story['id']}/turns", json={"choice_id": "c9"})

    assert response.status_code == 422


def test_unknown_story_is_404(client):
    assert client.get("/v1/stories/missing").status_code == 404


def test_unsupported_byok_provider_is_rejected(client):
    response = client.post(
        "/v1/stories",
        json={"premise": "A courier finds a strange package."},
        headers={"X-LLM-Provider": "nope", "X-LLM-Api-Key": "test-key"},
    )

    assert response.status_code == 400
