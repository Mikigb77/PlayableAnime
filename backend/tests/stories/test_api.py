"""The endpoints ported from FastAPI, with today's shapes, on Django and Postgres, each scoped to
the signed-in player (S8)."""

from datetime import date

import pytest
from asgiref.sync import async_to_sync
from django.test import AsyncClient, Client

from legacy.llm.fake import FakeNarratorProvider
from lucid.errors import ApiError
from stories import legacy_bridge
from stories.models import Engine, InputMode, Rating, Scene, SceneKind, Story
from tests.conftest import auth_headers

pytestmark = pytest.mark.django_db

PREMISE = "A courier finds a strange package."


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


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


def test_creating_a_story_generates_and_saves_the_opening_scene(client, player):
    story = _create_story(client)

    assert story["title"] == PREMISE
    assert story["version"] == 1
    assert len(story["scenes"]) == 1
    assert story["scenes"][0]["player_action"] is None
    assert [c["id"] for c in story["scenes"][0]["choices"]] == ["c1", "c2", "c3"]
    assert story["state"]["turn"] == 1
    row = Story.objects.get(pk=story["id"])
    assert (row.engine, row.version, row.turn) == (Engine.LEGACY, 1, 1)
    assert row.owner == player
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


def test_turns_take_the_apps_turn_request(client):
    """The app already sends the streamed endpoint's TurnRequest; the extra fields are ignored."""
    story = _create_story(client)

    by_choice = _turn(
        client,
        story["id"],
        {"kind": "choice", "choice_id": "c1", "input_mode": "choice", "expected_version": 1},
    )
    long_action = "I climb, " * 222  # 1998 characters
    by_action = _turn(
        client,
        story["id"],
        {"kind": "action", "action": long_action, "input_mode": "typed", "expected_version": 2},
    )

    assert (by_choice.status_code, by_action.status_code) == (200, 200), by_action.content
    assert by_action.json()["version"] == 3
    kinds = (
        Scene.objects.filter(story_id=story["id"])
        .order_by("turn")
        .values_list("kind", "input_mode")
    )
    assert list(kinds)[1:] == [
        (SceneKind.CHOICE, InputMode.CHOICE),
        (SceneKind.ACTION, InputMode.TYPED),
    ]


def test_a_turn_request_out_of_bounds_is_rejected(client):
    story = _create_story(client)

    for body in (
        {"action": "x" * 2001},
        {"action": "I climb.", "input_mode": "choice"},
        {"choice_id": "c1", "input_mode": "telepathy"},
    ):
        response = _turn(client, story["id"], body)
        assert response.status_code == 400, body
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


def test_the_legacy_endpoints_never_touch_a_turn_graph_story(client, player):
    graph = Story.objects.create(
        owner=player, title="Graph", premise="P", state={"clock": {"world_s": 0}}
    )

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


def test_the_ported_endpoints_run_over_asgi(player):
    headers = auth_headers(player)

    async def play() -> tuple[int, int]:
        # Headers go on each request: AsyncClient(headers=...) sends them under WSGI names.
        client = AsyncClient()
        created = await client.post(
            "/v1/stories", {"premise": PREMISE}, content_type="application/json", headers=headers
        )
        story_id = created.json()["id"]
        turn = await client.post(
            f"/v1/stories/{story_id}/turns",
            {"choice_id": "c3", "expected_version": 1},
            content_type="application/json",
            headers=headers,
        )
        return created.status_code, turn.json()["version"]

    assert async_to_sync(play)() == (201, 2)


# Ownership and the rating limit (S8, F8)


def test_every_story_endpoint_needs_a_signed_in_player(client):
    story = _create_story(client)
    anonymous = Client()

    for method, path in [
        ("get", "/v1/premises"),
        ("get", "/v1/stories"),
        ("post", "/v1/stories"),
        ("get", f"/v1/stories/{story['id']}"),
        ("get", f"/v1/stories/{story['id']}/memory"),
        ("post", f"/v1/stories/{story['id']}/turns"),
    ]:
        response = getattr(anonymous, method)(path, {}, content_type="application/json")
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthenticated"


def test_a_player_never_sees_or_plays_someone_elses_story(client, make_user):
    story = _create_story(client)
    other = Client(headers=auth_headers(make_user("other@example.com")))

    assert other.get("/v1/stories").json() == []
    for response in (
        other.get(f"/v1/stories/{story['id']}"),
        other.get(f"/v1/stories/{story['id']}/memory"),
        _turn(other, story["id"], {"choice_id": "c1"}),
    ):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    assert Story.objects.get(pk=story["id"]).version == 1


def test_a_teen_account_cant_open_a_mature_story(make_user):
    """F8: under 17, Teen only. The limit lifts on the 17th birthday with nothing to update."""
    today = date.today()
    teen = make_user("teen@example.com", birth_date=today.replace(year=today.year - 15))
    mature = Story.objects.create(
        owner=teen, title="M", premise="P", engine=Engine.LEGACY, rating=Rating.MATURE
    )

    response = Client(headers=auth_headers(teen)).get(f"/v1/stories/{mature.pk}")

    assert response.status_code == 403
    assert "rating" in response.json()["error"]["message"]
