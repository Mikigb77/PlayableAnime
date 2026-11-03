"""The endpoints ported from FastAPI, with today's shapes, on Django and Postgres."""

import pytest
from asgiref.sync import async_to_sync
from django.test import AsyncClient, Client

from legacy.llm.fake import FakeNarratorProvider
from lucid.errors import ApiError
from stories import legacy_bridge
from stories.models import Engine, InputMode, Scene, SceneKind, Story

pytestmark = pytest.mark.django_db

PREMISE = "A courier finds a strange package."


@pytest.fixture
def client() -> Client:
    return Client()


def _create_story(client: Client, **headers) -> dict:
    response = client.post(
        "/v1/stories", {"premise": PREMISE}, content_type="application/json", headers=headers
    )
    assert response.status_code == 201, response.content
    return response.json()


def _turn(client: Client, story_id: str, body: dict, **headers):
    return client.post(
        f"/v1/stories/{story_id}/turns", body, content_type="application/json", headers=headers
    )


def test_premises_are_listed(client):
    premises = client.get("/v1/premises").json()

    assert len(premises) >= 1
    assert {"id", "title", "genre", "premise"} <= premises[0].keys()


def test_creating_a_story_generates_and_saves_the_opening_scene(client):
    story = _create_story(client)

    assert story["title"] == PREMISE
    assert story["version"] == 1
    assert len(story["scenes"]) == 1
    assert story["scenes"][0]["player_action"] is None
    assert [c["id"] for c in story["scenes"][0]["choices"]] == ["c1", "c2", "c3"]
    assert story["state"]["turn"] == 1
    row = Story.objects.get(pk=story["id"])
    assert (row.engine, row.version, row.turn) == (Engine.LEGACY, 1, 1)
    assert row.scenes.get().kind == SceneKind.OPENING


def test_turns_advance_the_story_and_its_memory(client):
    story = _create_story(client)

    by_choice = _turn(client, story["id"], {"choice_id": "c1"}).json()
    by_action = _turn(client, story["id"], {"action": "I climb.", "input_mode": "voice"}).json()

    assert by_choice["scene"]["player_action"] == "Follow the sound of the bell"
    assert by_action["scene"]["player_action"] == "I climb."
    assert (by_choice["version"], by_action["version"]) == (2, 3)
    memory = client.get(f"/v1/stories/{story['id']}/memory").json()
    assert memory["turn"] == 3
    assert [(c["id"], c["affinity"]) for c in memory["characters"]] == [("ren", 3)]
    scenes = Scene.objects.filter(story_id=story["id"]).order_by("turn")
    assert [(s.kind, s.input_mode) for s in scenes] == [
        (SceneKind.OPENING, None),
        (SceneKind.CHOICE, InputMode.CHOICE),
        (SceneKind.ACTION, InputMode.VOICE),
    ]


def test_a_story_reloads_with_every_scene(client):
    story = _create_story(client)
    _turn(client, story["id"], {"choice_id": "c2"})

    loaded = client.get(f"/v1/stories/{story['id']}").json()

    assert [s["player_action"] for s in loaded["scenes"]] == [None, "Search for allies"]
    assert (loaded["version"], loaded["state"]["turn"]) == (2, 2)


def test_library_lists_the_most_recently_played_story_first(client):
    older = _create_story(client)
    newer = _create_story(client)
    _turn(client, older["id"], {"choice_id": "c1"})

    summaries = client.get("/v1/stories").json()

    assert [s["id"] for s in summaries[:2]] == [older["id"], newer["id"]]
    assert summaries[0] == {"id": older["id"], "title": PREMISE, "premise": PREMISE, "turn": 2}


def test_turn_needs_exactly_one_of_choice_or_action(client):
    story = _create_story(client)

    for body in ({}, {"choice_id": "c1", "action": "Both"}):
        response = _turn(client, story["id"], body)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "validation_error"


def test_unknown_choice_is_rejected(client):
    story = _create_story(client)

    response = _turn(client, story["id"], {"choice_id": "c9"})

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"][0]["field"] == "choice_id"


def test_unknown_story_is_404(client):
    for story_id in ("missing", "8b2b5a8e-0000-4000-8000-000000000000"):
        response = client.get(f"/v1/stories/{story_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_the_legacy_endpoints_never_touch_a_turn_graph_story(client):
    graph = Story.objects.create(title="Graph", premise="P", state={"clock": {"world_s": 0}})

    assert client.get(f"/v1/stories/{graph.pk}").status_code == 404
    assert _turn(client, str(graph.pk), {"action": "I wait."}).status_code == 404
    assert client.get("/v1/stories").json() == []
    graph.refresh_from_db()
    assert (graph.state, graph.version) == ({"clock": {"world_s": 0}}, 0)


def test_a_wrong_method_gets_the_envelope_and_the_allow_header(client):
    response = client.put("/v1/stories", {}, content_type="application/json")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert set(response["Allow"].split(", ")) == {"GET", "POST"}
    assert response["X-Request-Id"]


def test_unsupported_byok_provider_is_rejected(client):
    response = client.post(
        "/v1/stories",
        {"premise": PREMISE},
        content_type="application/json",
        headers={"X-LLM-Provider": "nope", "X-LLM-Api-Key": "test-key"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_a_stale_expected_version_is_a_conflict_before_any_model_call(client, monkeypatch):
    story = _create_story(client)
    _turn(client, story["id"], {"choice_id": "c1"})
    calls = []
    monkeypatch.setattr(FakeNarratorProvider, "generate", lambda *a, **k: calls.append(1))

    response = _turn(client, story["id"], {"choice_id": "c1", "expected_version": 1})

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "version_conflict",
        "message": "Another turn was saved first.",
        "details": {"current_version": 2},
    }
    assert calls == []


def test_the_loser_of_two_concurrent_turns_saves_nothing(client):
    """T10: both turns read version 1; the first to save wins, the second gets a 409 and its
    scene is rolled back."""
    created = _create_story(client)
    stale = Story.objects.get(pk=created["id"])
    _turn(client, created["id"], {"choice_id": "c1"})
    current = legacy_bridge.to_legacy(stale, list(stale.scenes.all()))
    advanced = current.model_copy(
        update={"scenes": [*current.scenes, current.scenes[-1].model_copy(update={"turn": 2})]}
    )

    with pytest.raises(ApiError) as raised:
        async_to_sync(legacy_bridge.save_turn)(stale, advanced, SceneKind.CHOICE, InputMode.CHOICE)

    assert raised.value.code == "version_conflict"
    assert raised.value.details == {"current_version": 2}
    assert Scene.objects.filter(story_id=created["id"]).count() == 2
    assert Story.objects.get(pk=created["id"]).version == 2


def test_a_model_failure_is_llm_unavailable_and_saves_nothing(client, monkeypatch, log_lines):
    story = _create_story(client)

    async def fail(*args, **kwargs):
        raise TimeoutError("vertex timed out")

    monkeypatch.setattr(FakeNarratorProvider, "generate", fail)

    response = _turn(client, story["id"], {"action": "I run."})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
    assert Story.objects.get(pk=story["id"]).version == 1
    [line] = [line for line in log_lines() if line["message"] == "Narration failed"]
    assert line["story_id"] == story["id"]
    assert "TimeoutError" in line["stack_trace"]


def test_a_rejected_byok_key_is_bad_key_and_the_key_is_never_logged(client, monkeypatch, log_lines):
    from google.genai.errors import ClientError

    from legacy.llm import gemini

    async def reject(*args, **kwargs):
        raise ClientError(400, {"error": {"message": "API key not valid.", "status": "INVALID"}})

    monkeypatch.setattr(gemini.GeminiProvider, "generate", reject)
    key = "AIza-very-secret-key"

    response = client.post(
        "/v1/stories",
        {"premise": PREMISE},
        content_type="application/json",
        headers={"X-LLM-Provider": "gemini", "X-LLM-Api-Key": key},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "bad_key"
    assert not Story.objects.exists()
    assert key not in str(log_lines())


def test_the_ported_endpoints_run_over_asgi():
    async def play() -> tuple[int, int]:
        client = AsyncClient()
        created = await client.post(
            "/v1/stories", {"premise": PREMISE}, content_type="application/json"
        )
        story_id = created.json()["id"]
        turn = await client.post(
            f"/v1/stories/{story_id}/turns",
            {"choice_id": "c3", "expected_version": 1},
            content_type="application/json",
        )
        return created.status_code, turn.json()["version"]

    assert async_to_sync(play)() == (201, 2)
