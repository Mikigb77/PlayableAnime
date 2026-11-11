"""The story endpoints besides turns (API.md: Stories, Memory and status), each scoped to the
signed-in player (S8, F8)."""

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from graph.llm import Node, Reply
from media.models import Image, ImageStatus
from moderation.service import report_scene
from stories.models import Engine, PendingEvent, Scene, Story
from tests.conftest import auth_headers
from tests.stories.conftest import opening, play
from tests.stories.test_turns import AFTER, OPENING, opened

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(player) -> Client:
    return Client(headers=auth_headers(player))


def test_the_library_lists_your_own_stories_most_recently_played_first(
    client, player, make_user, make_story, model
):
    older = make_story(player, title="Older")
    make_story(player, world="grounded", title="Newer")
    make_story(make_user("other@example.com"), title="Not yours")
    Story.objects.create(owner=player, title="Legacy", premise="P", engine=Engine.LEGACY)
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    play(player, older, opening(older))

    library = client.get("/v1/stories").json()

    assert [s["title"] for s in library] == ["Older", "Newer"]
    first = library[0]
    assert set(first) == {
        "id",
        "title",
        "genre",
        "rating",
        "turn",
        "world_time_label",
        "cover_url",
        "ending",
        "accent",
        "updated_at",
    }
    assert (first["id"], first["genre"], first["rating"], first["turn"]) == (
        str(older.pk),
        "cultivation",
        "mature",
        1,
    )
    assert first["world_time_label"]
    assert library[1]["world_time_label"]
    assert first["cover_url"] is None


def test_a_story_comes_with_its_last_scenes_settings_and_clock(client, player, make_story, model):
    story = opened(player, make_story, model)
    for version in (2, 3):
        model.backend.script(Node.NARRATOR, Reply(json=AFTER))
        play(player, story, {"kind": "standing", "standing": "wait", "expected_version": version})

    loaded = client.get(f"/v1/stories/{story.pk}").json()
    last = client.get(f"/v1/stories/{story.pk}?scenes=2").json()
    none = client.get(f"/v1/stories/{story.pk}?scenes=0").json()

    assert (loaded["version"], loaded["turn"]) == (4, 3)
    assert [s["turn"] for s in loaded["scenes"]] == [1, 2, 3]
    assert loaded["scenes"][0]["image"]["kind"] == "portrait"
    assert loaded["settings"] == {
        "narration_length": "medium",
        "tone": None,
        "difficulty": "balanced",
        "event_frequency": "normal",
        "images": "key_moments",
        "suggestions": True,
        "language": "en",
        "accent": None,
    }
    assert set(loaded["clock"]) == {"world_s", "label", "timeline_id"}
    assert [s["turn"] for s in last["scenes"]] == [2, 3]
    assert none["scenes"] == []
    assert client.get(f"/v1/stories/{story.pk}?scenes=51").status_code == 400


def test_a_scene_the_player_blocked_comes_back_blocked(client, player, make_story, model):
    """F6: a blocked scene says so wherever scenes are served, and the others don't."""
    story = opened(player, make_story, model)
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    play(player, story, {"kind": "standing", "standing": "wait", "expected_version": 2})
    report_scene(
        story, Scene.objects.get(story=story, turn=1), player, category="other", note="", block=True
    )
    report_scene(
        story,
        Scene.objects.get(story=story, turn=2),
        player,
        category="other",
        note="",
        block=False,
    )

    loaded = client.get(f"/v1/stories/{story.pk}").json()["scenes"]
    scrolled = client.get(f"/v1/stories/{story.pk}/scenes").json()

    for scenes in (loaded, scrolled):
        assert [(s["turn"], s["blocked"]) for s in scenes] == [(1, True), (2, False)]


def test_older_scenes_come_back_for_scrollback(client, player, make_story, model):
    story = opened(player, make_story, model)
    for version in (2, 3, 4):
        model.backend.script(Node.NARRATOR, Reply(json=AFTER))
        play(player, story, {"kind": "standing", "standing": "wait", "expected_version": version})

    page = client.get(f"/v1/stories/{story.pk}/scenes?before=4&limit=2").json()
    everything = client.get(f"/v1/stories/{story.pk}/scenes").json()

    assert [s["turn"] for s in page] == [2, 3]
    assert [s["turn"] for s in everything] == [1, 2, 3, 4]
    assert client.get(f"/v1/stories/{story.pk}/scenes?limit=0").status_code == 400


def test_a_new_story_has_no_scenes_yet(client, player, make_story):
    story = make_story(player)

    loaded = client.get(f"/v1/stories/{story.pk}").json()

    assert (loaded["turn"], loaded["version"], loaded["scenes"]) == (0, 1, [])
    assert loaded["clock"]["world_s"] == 0


def test_patch_renames_and_changes_only_the_settings_sent(client, player, make_story):
    story = make_story(player)

    response = client.patch(
        f"/v1/stories/{story.pk}",
        {"title": "  A  new name ", "settings": {"images": "off", "narration_length": "long"}},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["title"] == "A new name"
    assert body["settings"]["images"] == "off"
    assert body["settings"]["narration_length"] == "long"
    assert body["settings"]["difficulty"] == "balanced"
    story.refresh_from_db()
    assert story.settings["images"] == "off"
    assert story.version == 1
    for bad in ({"settings": {"images": "always"}}, {"title": ""}, {"title": "   "}):
        response = client.patch(f"/v1/stories/{story.pk}", bad, content_type="application/json")
        assert response.status_code == 400, bad


def test_a_story_keeps_the_language_it_was_set_up_in(client, player, make_story, model):
    # S10 (Miki, 2026-11-06): no switching mid-story. An older app that still sends a language
    # has it ignored, and the story carries on as it began.
    story = opened(player, make_story, model)
    response = client.patch(
        f"/v1/stories/{story.pk}",
        {"settings": {"language": "es", "images": "off"}},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["settings"]["language"] == "en"
    assert response.json()["settings"]["images"] == "off"
    story.refresh_from_db()
    assert story.settings.get("language", "en") == "en"


@pytest.mark.parametrize(
    ("language", "day", "named", "alive"),
    [
        ("es", "Día ", "Spanish from Spain", "Con vida"),
        ("ca", "Dia ", "Catalan, speaking to the player as tu", "Amb vida"),
    ],
)
def test_a_story_set_up_in_spanish_or_catalan_is_told_in_it(
    client, player, make_story, model, language, day, named, alive
):
    # S10: the narrator, the interpret step's notes and every fixed word the server writes.
    story = make_story(player)
    story.settings = {"language": language}
    story.save(update_fields=["settings"])
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    play(player, story, opening(story))
    story.refresh_from_db()
    model.backend.script(Node.NARRATOR, Reply(json=AFTER))
    model.backend.script(Node.INTERPRET, Reply(json={"summary": "Look.", "steps": []}))

    played = play(player, story, {"kind": "action", "action": "Look.", "expected_version": 2})

    completed = played.completed
    assert completed["scene"]["time"]["label"].startswith(day)
    assert completed["story"]["clock"]["label"].startswith(day)
    status = client.get(f"/v1/stories/{story.pk}/status").json()
    assert status["clock"]["label"].startswith(day)
    memory = client.get(f"/v1/stories/{story.pk}/memory").json()
    assert all(p["status_label"] == alive for p in memory["people"])
    [summary] = client.get("/v1/stories").json()
    assert summary["world_time_label"].startswith(day)
    narrator = model.backend.calls(Node.NARRATOR)[-1]
    assert named in narrator.prompt.messages[-1].text.split("## CONTENT")[0]
    [interpret] = model.backend.calls(Node.INTERPRET)
    assert f"## LANGUAGE\n{named}" in interpret.prompt.messages[-1].text


def test_delete_removes_the_story_with_its_scenes_and_events(client, player, make_story, model):
    story = opened(player, make_story, model, world="grounded")
    assert PendingEvent.objects.filter(story=story).exists()

    response = client.delete(f"/v1/stories/{story.pk}")

    assert response.status_code == 204
    assert not Story.objects.filter(pk=story.pk).exists()
    assert not Scene.objects.exists()
    assert not PendingEvent.objects.exists()
    assert client.get(f"/v1/stories/{story.pk}").status_code == 404


def test_memory_shows_only_what_the_character_knows_with_their_pictures(
    client, player, make_story, settings, tmp_path
):
    story = make_story(player)
    Image.objects.create(
        story=story,
        kind="portrait",
        subject="zhao",
        status=ImageStatus.READY,
        storage_key=f"stories/{story.pk}/zhao.png",
    )

    memory = client.get(f"/v1/stories/{story.pk}/memory").json()

    assert memory["character"]["name"] == "Lin Feng"
    assert memory["character"]["portrait_url"] is None
    people = {person["id"]: person for person in memory["people"]}
    assert people["zhao"]["portrait_url"].startswith("http://testserver/")
    text = str(memory)
    state = story.state
    for character in state["characters"].values():
        for secret in character.get("secrets", []):
            assert secret not in text


def test_status_shows_the_sheet_and_the_clock(client, player, make_story):
    story = make_story(player)

    status = client.get(f"/v1/stories/{story.pk}/status").json()

    assert status["character"]["name"] == "Lin Feng"
    assert status["character"]["portrait_url"] is None  # not drawn yet
    assert status["clock"]["world_s"] == 0
    assert status["clock"]["label"]
    # The sheet in sections (G13, G16), with the plain lines still there for an older app.
    sheet = status["sheet"]
    assert sheet["condition"]["health"] == "unhurt" and sheet["condition"]["health_label"]
    assert [path["rungs"][-1]["name"] for path in sheet["paths"]] == ["Qi Condensation"]
    assert [(p["name"], p["ready"]) for p in sheet["powers"]] == [("Time stop", True)]
    assert status["character"]["lines"]


def test_status_shows_the_player_characters_portrait_once_drawn(client, player, make_story):
    story = make_story(player)
    Image.objects.create(
        story=story,
        kind="portrait",
        subject=story.state["player_id"],
        status=ImageStatus.READY,
        storage_key=f"stories/{story.pk}/me.png",
    )

    status = client.get(f"/v1/stories/{story.pk}/status").json()

    assert status["character"]["portrait_url"].startswith("http://testserver/")


def test_stories_from_the_old_narrator_are_not_served(client, player):
    legacy = Story.objects.create(
        owner=player, title="Old", premise="P", engine=Engine.LEGACY, state={"turn": 1}
    )

    for path in ("", "/memory", "/status", "/scenes"):
        assert client.get(f"/v1/stories/{legacy.pk}{path}").status_code == 404
    assert client.delete(f"/v1/stories/{legacy.pk}").status_code == 404


def test_unknown_and_other_players_stories(client, make_user, make_story):
    theirs = make_story(make_user("other@example.com"))

    for story_id in ("missing", "8b2b5a8e-0000-4000-8000-000000000000"):
        response = client.get(f"/v1/stories/{story_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert client.get(f"/v1/stories/{theirs.pk}").status_code == 403
    assert client.delete(f"/v1/stories/{theirs.pk}").status_code == 403
    assert Story.objects.filter(pk=theirs.pk).exists()


def test_stories_are_made_by_drafts_not_by_posting_a_premise(client):
    response = client.post("/v1/stories", {"premise": "x" * 20}, content_type="application/json")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response["Allow"] == "GET"


def test_seed_story_makes_a_story_ready_for_its_opening(player, model, capsys):
    call_command("seed_story", player.email, "--world", "grounded")

    story = Story.objects.get(pk=capsys.readouterr().out.strip())
    assert (story.owner, story.engine, story.turn, story.version) == (
        player,
        Engine.GRAPH,
        0,
        1,
    )
    assert (story.title, story.rating) == ("The Esposito Succession", "mature")
    assert story.settings["images"] == "key_moments"
    model.backend.script(Node.NARRATOR, Reply(json=OPENING))
    assert play(player, story, opening(story)).names[-1] == "scene.completed"
    with pytest.raises(CommandError):
        call_command("seed_story", "nobody@example.com")


def test_every_story_endpoint_needs_a_signed_in_player(player, make_story):
    """T8: no story endpoint answers an anonymous caller."""
    story = make_story(player)
    anonymous = Client()
    calls = [
        ("get", "/v1/stories"),
        ("get", f"/v1/stories/{story.pk}"),
        ("patch", f"/v1/stories/{story.pk}"),
        ("delete", f"/v1/stories/{story.pk}"),
        ("get", f"/v1/stories/{story.pk}/scenes"),
        ("post", f"/v1/stories/{story.pk}/turns"),
        ("get", f"/v1/stories/{story.pk}/memory"),
        ("get", f"/v1/stories/{story.pk}/status"),
        ("get", "/v1/premises"),
    ]
    for method, path in calls:
        response = getattr(anonymous, method)(path, {}, content_type="application/json")
        assert response.status_code == 401, (method, path)
        assert response.json()["error"]["code"] == "unauthenticated"
    assert Story.objects.filter(pk=story.pk).exists()


def test_a_story_takes_the_color_the_player_picks_and_can_go_back_to_its_genres(
    client, player, make_story
):
    # S13 (Miki, 2026-11-07): the player can swap the color a story got from its genre. It is kept
    # with the story, so the Library and every device show it, and null goes back to the genre's.
    story = make_story(player, settings={"tone": "wry"})

    picked = client.patch(
        f"/v1/stories/{story.pk}", {"settings": {"accent": "rose"}}, content_type="application/json"
    )
    listed = client.get("/v1/stories").json()

    assert picked.status_code == 200, picked.content
    assert picked.json()["settings"]["accent"] == "rose"
    assert picked.json()["settings"]["tone"] == "wry"
    assert picked.json()["version"] == story.version
    assert [s["accent"] for s in listed] == ["rose"]

    other = client.patch(
        f"/v1/stories/{story.pk}", {"settings": {"images": "off"}}, content_type="application/json"
    )
    assert other.json()["settings"]["accent"] == "rose"

    automatic = client.patch(
        f"/v1/stories/{story.pk}", {"settings": {"accent": None}}, content_type="application/json"
    )
    assert automatic.status_code == 200, automatic.content
    assert automatic.json()["settings"]["accent"] is None
    assert client.get("/v1/stories").json()[0]["accent"] is None
    story.refresh_from_db()
    assert story.settings["accent"] is None

    unknown = client.patch(
        f"/v1/stories/{story.pk}",
        {"settings": {"accent": "plaid"}},
        content_type="application/json",
    )
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (400, "validation_error")

    # A color stored by a newer server, as after rolling a deploy back, reads as the genre's.
    Story.objects.filter(pk=story.pk).update(settings={"accent": "teal", "tone": "wry"})
    assert client.get(f"/v1/stories/{story.pk}").json()["settings"]["accent"] is None
    assert client.get("/v1/stories").json()[0]["accent"] is None


def test_patch_refuses_null_settings_except_tone(client, player, make_story):
    story = make_story(player, settings={"tone": "wry"})

    refused = client.patch(
        f"/v1/stories/{story.pk}",
        {"settings": {"narration_length": None}},
        content_type="application/json",
    )
    cleared = client.patch(
        f"/v1/stories/{story.pk}", {"settings": {"tone": None}}, content_type="application/json"
    )

    assert (refused.status_code, refused.json()["error"]["code"]) == (400, "validation_error")
    assert cleared.status_code == 200
    assert cleared.json()["settings"]["tone"] is None


def test_a_story_whose_world_was_never_filled_in_is_not_served(client, player):
    empty = Story.objects.create(owner=player, title="Empty", premise="P", engine=Engine.GRAPH)

    assert client.get("/v1/stories").json() == []
    assert client.get(f"/v1/stories/{empty.pk}").status_code == 404
