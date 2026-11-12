"""`/v1/premises` and `/v1/drafts` on the fake model (docs/API.md, G1, G2, S1, S6, G7, G22, N7,
C6, F8, K2, K6, T6, T7, T9, T10)."""

import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from asgiref.sync import async_to_sync
from django.test import Client

from billing import meter
from billing.models import CreditHold, EntryKind, LedgerEntry
from billing.pricing import ModelCall
from drafts import service
from drafts.models import Draft
from engine import real_entities
from engine.state import WorldState
from graph.drafting import samples
from graph.drafting.catalog import STARTER_PREMISES, starter
from graph.drafting.catalog_ca import CATALAN
from graph.drafting.catalog_es import SPANISH
from graph.drafting.schema import ExtraordinaryP, PeopleP, RemovalP, WorldChange
from graph.drafting.view import hidden_texts
from graph.llm import Block, Fail, Node, Reply, TurnTelemetry
from stories.models import Engine, Story
from tests.conftest import auth_headers

MY_PREMISE = "I run a small bakery in a port town where the tide brings in strange things."


def _create(client: Client, body: dict | None = None, **headers):
    body = body if body is not None else {"premise_id": "naples-vendetta", "rating": "mature"}
    return client.post("/v1/drafts", body, content_type="application/json", headers=headers)


def _draft(client: Client, body: dict | None = None) -> dict:
    response = _create(client, body)
    assert response.status_code == 201, response.content
    return response.json()


def _patch(client: Client, draft_id: str, body: dict):
    return client.patch(f"/v1/drafts/{draft_id}", body, content_type="application/json")


def _revise(client: Client, draft_id: str, body: dict, **headers):
    return client.post(
        f"/v1/drafts/{draft_id}/revise", body, content_type="application/json", headers=headers
    )


def _start(client: Client, draft_id: str, body: dict | None = None):
    return client.post(f"/v1/drafts/{draft_id}/start", body or {}, content_type="application/json")


def _error(response) -> dict:
    return response.json()["error"]


def _state(draft_id: str) -> WorldState:
    return service.to_chain(Draft.objects.get(pk=draft_id)).state()


def _assert_nothing_hidden(response, state: WorldState) -> None:
    body = json.dumps(response.json(), ensure_ascii=False).casefold()
    for text in hidden_texts(state):
        assert text.casefold().rstrip(".") not in body, text


# Starter premises (S1).


def test_starter_premises_lead_with_the_flagship_genres(player_client):
    premises = player_client.get("/v1/premises").json()

    assert [p["id"] for p in premises] == [p.id for p in STARTER_PREMISES]
    assert premises[0]["flagship"] is True
    assert set(premises[0]) == {
        "id",
        "title",
        "genre",
        "tagline",
        "premise",
        "flagship",
        "cover_url",
    }
    genres = {p["genre"] for p in premises}
    assert {"Cultivation", "Grounded crime", "Science fiction", "Hidden supernatural"} <= genres


def test_starter_premises_come_in_the_apps_language(player_client):
    english = player_client.get("/v1/premises").json()
    spanish = player_client.get("/v1/premises", {"language": "es"}).json()

    assert [p["id"] for p in spanish] == [p["id"] for p in english]
    first = spanish[0]
    assert first["title"] == SPANISH[first["id"]].title
    assert first["premise"] == SPANISH[first["id"]].premise
    assert first["flagship"] == english[0]["flagship"]
    assert first["cover_url"] == english[0]["cover_url"]
    assert player_client.get("/v1/premises", {"language": "en"}).json() == english
    catalan = player_client.get("/v1/premises", {"language": "ca"}).json()
    assert [p["title"] for p in catalan] == [CATALAN[p["id"]].title for p in english]


def test_a_language_the_app_doesnt_speak_is_refused(player_client):
    response = player_client.get("/v1/premises", {"language": "fr"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


# Creating a draft (G1, G2, S1).


def test_a_starter_premise_drafts_a_world_and_a_character(player_client, model, player):
    response = _create(player_client)

    assert response.status_code == 201, response.content
    draft = response.json()
    naples = starter("naples-vendetta")
    assert draft["premise"] == naples.premise
    assert draft["premise_id"] == "naples-vendetta"
    assert (draft["rating"], draft["version"], draft["story_id"]) == ("mature", 0, None)
    assert (draft["title"], draft["genre"], draft["tone"]) == (
        "The Esposito Succession",
        "grounded crime",
        "noir",
    )
    assert draft["world_lines"][0].startswith("Grounded: no magic")
    assert draft["character_lines"][0] == "Luca Esposito, 24."
    advanced = draft["advanced"]
    assert advanced["physics"] == "fun_first"
    assert advanced["gift_strength"] == "none"
    assert (advanced["difficulty"], advanced["event_frequency"]) == ("balanced", "normal")
    rules = {r["id"]: r for r in advanced["rules"]}
    for rule in naples.template.rules:
        assert rules[rule.id] == {"id": rule.id, "text": rule.text, "fixed": True}
    [request] = model.calls(Node.DRAFTER)
    assert naples.premise in request.prompt.messages[0].text
    row = Draft.objects.get(pk=draft["id"])
    assert row.owner_id == player.pk and row.story_id is None


def test_a_players_own_premise_drafts_with_their_choices(player_client, model):
    model.script(Node.DRAFTER, Reply(json=samples.cultivation()))

    draft = _draft(
        player_client,
        {
            "premise": MY_PREMISE,
            "rating": "teen",
            "advanced": {
                "physics": "strict",
                "gift_strength": "small",
                "difficulty": "brutal",
                "event_frequency": "dramatic",
            },
        },
    )

    assert (draft["premise"], draft["premise_id"], draft["rating"]) == (MY_PREMISE, None, "teen")
    assert draft["advanced"] | {"rules": None} == {
        "physics": "strict",
        "rules": None,
        "gift_strength": "small",
        "difficulty": "brutal",
        "event_frequency": "dramatic",
    }
    assert "special gift is small" in model.requests[0].prompt.messages[0].text


def test_rules_sent_with_the_premise_join_the_first_draft(player_client, model):
    draft = _draft(
        player_client,
        {
            "premise_id": "naples-vendetta",
            "rating": "teen",
            "advanced": {"rules": [{"text": "Every street has a saint."}]},
        },
    )

    [request] = model.calls(Node.DRAFTER)
    assert "- Every street has a saint." in request.prompt.messages[0].text
    rules = {r["id"]: r for r in draft["advanced"]["rules"]}
    assert rules["every-street-has-a-saint"]["fixed"] is True
    # The starter's own rules still hold (G7).
    assert {"no-supernatural", "human-limits", "omerta"} <= set(rules)
    assert Draft.objects.get().released_rules == []


def test_summary_lines_have_a_length_limit(player_client, model):
    draft_id = _draft(player_client)["id"]

    response = _patch(player_client, draft_id, {"world_lines": ["x" * 301]})

    assert response.status_code == 400
    assert _error(response)["code"] == "validation_error"


def test_lowering_the_rating_redrafts_within_teen(player_client, model):
    draft_id = _draft(player_client)["id"]
    calls = len(model.requests)

    response = _patch(player_client, draft_id, {"rating": "teen"})

    assert response.status_code == 200, response.content
    assert response.json()["rating"] == "teen"
    redrafts = model.requests[calls:]
    assert [r.json_schema["title"] for r in redrafts] == ["WorldChange", "CharacterProposal"]
    assert all("Rating: Teen" in r.prompt.system for r in redrafts)

    raised = _patch(player_client, draft_id, {"rating": "mature"})
    assert raised.json()["rating"] == "mature"
    assert len(model.requests) == calls + 2  # raising the rating changes nothing drafted


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"rating": "teen"}, None),
        ({"premise_id": "no-such-premise", "rating": "teen"}, "premise_id"),
        ({"premise": "too short", "rating": "teen"}, "premise"),
        ({"premise": MY_PREMISE, "rating": "adult"}, "rating"),
        ({"premise": MY_PREMISE}, "rating"),
        ({"premise": MY_PREMISE, "rating": "teen", "advanced": {"physics": "loose"}}, None),
    ],
)
def test_an_invalid_draft_request_is_refused_before_any_model_call(
    player_client, model, body, field
):
    response = _create(player_client, body)

    assert response.status_code == 400, response.content
    error = _error(response)
    assert error["code"] == "validation_error"
    if field is not None:
        assert field in [f["field"] for f in error["details"]["fields"]]
    assert model.requests == []
    assert not Draft.objects.exists()


# Hidden parts (N7, C6).


def test_no_response_ever_carries_the_drafts_hidden_parts(player_client, model):
    created = _create(player_client)
    draft_id = created.json()["id"]
    state = _state(draft_id)
    assert hidden_texts(state)

    for response in (
        created,
        player_client.get(f"/v1/drafts/{draft_id}"),
        _revise(player_client, draft_id, {"target": "world", "instruction": "More rain."}),
        _revise(player_client, draft_id, {"target": "character", "instruction": "Older."}),
        _patch(player_client, draft_id, {"advanced": {"physics": "strict"}}),
    ):
        assert response.status_code in (200, 201), response.content
        _assert_nothing_hidden(response, state)


# Who may see a draft (T8, S8, F8).


def test_every_draft_endpoint_needs_a_signed_in_player(player_client, model):
    draft_id = _draft(player_client)["id"]
    anonymous = Client()

    for method, path in [
        ("get", "/v1/premises"),
        ("post", "/v1/drafts"),
        ("get", f"/v1/drafts/{draft_id}"),
        ("patch", f"/v1/drafts/{draft_id}"),
        ("post", f"/v1/drafts/{draft_id}/revise"),
        ("post", f"/v1/drafts/{draft_id}/start"),
    ]:
        response = getattr(anonymous, method)(path, {}, content_type="application/json")
        assert response.status_code == 401, path
        assert _error(response)["code"] == "unauthenticated"


def test_a_player_never_sees_or_changes_someone_elses_draft(player_client, other_client, model):
    draft_id = _draft(player_client)["id"]
    calls = len(model.requests)

    for response in (
        other_client.get(f"/v1/drafts/{draft_id}"),
        _patch(other_client, draft_id, {"advanced": {"physics": "strict"}}),
        _revise(other_client, draft_id, {"target": "world", "instruction": "Mine now."}),
        _start(other_client, draft_id),
    ):
        assert response.status_code == 403, response.content
        assert _error(response)["code"] == "forbidden"
    assert len(model.requests) == calls
    assert not Story.objects.exists()


@pytest.mark.parametrize("draft_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_a_missing_draft_is_not_found(player_client, draft_id):
    response = player_client.get(f"/v1/drafts/{draft_id}")

    assert response.status_code == 404
    assert _error(response)["code"] == "not_found"


@pytest.fixture
def teen_client(make_user) -> Client:
    today = date.today()
    teen = make_user("teen@example.com", birth_date=today.replace(year=today.year - 15))
    return Client(headers=auth_headers(teen))


def test_a_teen_account_drafts_teen_stories_only(teen_client, model):
    refused = _create(teen_client, {"premise": MY_PREMISE, "rating": "mature"})

    assert refused.status_code == 403
    assert _error(refused)["code"] == "forbidden"
    assert model.requests == []

    draft_id = _draft(teen_client, {"premise": MY_PREMISE, "rating": "teen"})["id"]
    raised = _patch(teen_client, draft_id, {"rating": "mature"})
    assert raised.status_code == 403
    assert Draft.objects.get(pk=draft_id).rating == "teen"


# Revising in plain words (G1, G2).


def test_the_draft_shows_of_the_story_s_start_only_what_the_player_named(player_client, model):
    # G1 (Miki, 2026-11-10): the first event and the first people are the story's surprise.
    model.script(Node.DRAFTER, Reply(json=samples.naples()))
    draft = _draft(player_client, {"premise": samples.NAPLES_PREMISE, "rating": "mature"})
    council = "The council picks the next boss: in 10 days."
    assert council not in draft["world_lines"]
    assert not any(line.startswith("Carmine Russo:") for line in draft["world_lines"])
    assert "Who inside the family ordered the killing of my father?" in draft["world_lines"]
    assert "Goal: Find out who killed my father." in draft["character_lines"]
    # The council is drafted all the same, for the story to tell.
    assert any(
        clock.name.startswith("The council") for clock in _state(draft["id"]).clocks.values()
    )

    # Asking for it in plain words is the player's say: it shows from then on, and stays.
    model.script(Node.DRAFTER, Reply(json=WorldChange()))
    asked = "The council picks the next boss in ten days."
    revised = _revise(player_client, draft["id"], {"target": "world", "instruction": asked})

    assert council in revised.json()["world_lines"]
    # The draft keeps which deadline they named, not what they wrote.
    assert Draft.objects.get(pk=draft["id"]).told == ["clock:council"]
    assert council in player_client.get(f"/v1/drafts/{draft['id']}").json()["world_lines"]


def test_a_world_revision_redrafts_the_world(player_client, model):
    draft = _draft(player_client)
    model.script(Node.DRAFTER, Reply(json=WorldChange(title="Blood on the Bay")))

    response = _revise(
        player_client,
        draft["id"],
        {"target": "world", "instruction": "Call it Blood on the Bay.", "expected_version": 0},
    )

    assert response.status_code == 200, response.content
    revised = response.json()
    assert (revised["title"], revised["version"]) == ("Blood on the Bay", 1)
    assert revised["character_lines"] == draft["character_lines"]
    assert "Call it Blood on the Bay." in model.requests[-1].prompt.messages[0].text


def test_races_asked_for_in_plain_words_join_the_world_and_nothing_else_changes(
    player_client, model, player
):
    """On 2026-11-04 every world revision failed with `llm_unavailable`: the model had to write
    the whole world back, and ran past its output limit twice. Now it sends only the change."""
    draft = _draft(player_client)
    before = _state(draft["id"])
    character = Draft.objects.get(pk=draft["id"]).proposal["character"]
    model.script(
        Node.DRAFTER,
        Reply(
            json=WorldChange(
                extraordinary=[
                    ExtraordinaryP(id="vampires", kind="vampires", prevalence="hidden"),
                    ExtraordinaryP(id="demons", kind="demons", prevalence="rare"),
                ],
                peoples=[
                    PeopleP(id="vampires", name="Vampires"),
                    PeopleP(id="orcs", name="Orcs"),
                    PeopleP(id="demons", name="Demons"),
                ],
                removed=[RemovalP(section="extraordinary", id="supernatural")],
                # G7: the starter's fixed rules go only because the change names them.
                dropped_rule_ids=["no-supernatural", "human-limits"],
            )
        ),
    )

    response = _revise(
        player_client,
        draft["id"],
        {
            "target": "world",
            "instruction": "Add more races to the world, like vampires, orcs and demons.",
            "expected_version": 0,
        },
    )

    assert response.status_code == 200, response.content
    revised = response.json()
    assert "Peoples: Vampires, Orcs and Demons." in revised["world_lines"]
    assert not any(line.startswith("Grounded") for line in revised["world_lines"])
    # The character stays as drafted; only "no powers, since this world has none" goes.
    assert Draft.objects.get(pk=draft["id"]).proposal["character"] == character
    assert "No powers, since this world has none." not in revised["character_lines"]
    after = _state(draft["id"])
    assert not after.bible.grounded
    assert {r.id for r in after.bible.rules} >= {"omerta"}
    assert (after.places, after.factions, after.clocks) == (
        before.places,
        before.factions,
        before.clocks,
    )
    assert LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT).count() == 2


def test_a_character_revision_redrafts_the_character(player_client, model):
    draft = _draft(player_client)
    character = samples.naples_character()
    character.age = 31
    model.script(Node.DRAFTER, Reply(json=character))

    response = _revise(player_client, draft["id"], {"target": "character", "instruction": "Older"})

    assert response.json()["character_lines"][0] == "Luca Esposito, 31."
    assert response.json()["world_lines"] == draft["world_lines"]


@pytest.mark.parametrize(
    "body",
    [
        {"target": "plot", "instruction": "More twists."},
        {"target": "world", "instruction": ""},
        {"target": "world", "instruction": "x" * 1001},
    ],
)
def test_an_invalid_revision_is_refused(player_client, model, body):
    draft_id = _draft(player_client)["id"]

    response = _revise(player_client, draft_id, body)

    assert response.status_code == 400
    assert _error(response)["code"] == "validation_error"


# Direct edits (G1, G2, G7, G22, A9, S6).


def test_edits_code_can_make_alone_call_no_model(player_client, model):
    draft = _draft(player_client)
    calls = len(model.requests)

    response = _patch(
        player_client,
        draft["id"],
        {
            "world_lines": draft["world_lines"],
            "advanced": {
                "physics": "strict",
                "difficulty": "story",
                "event_frequency": "calm",
                "gift_strength": "none",
            },
            "expected_version": 0,
        },
    )

    assert response.status_code == 200, response.content
    edited = response.json()
    assert edited["version"] == 1
    assert edited["advanced"] | {"rules": None} == {
        "physics": "strict",
        "rules": None,
        "gift_strength": "none",
        "difficulty": "story",
        "event_frequency": "calm",
    }
    assert len(model.requests) == calls


def test_rewritten_summary_lines_redraft_the_world_to_match(player_client, model):
    draft = _draft(player_client)
    model.script(Node.DRAFTER, Reply(json=WorldChange(era="Naples, 1975: the heat of summer")))
    lines = list(draft["world_lines"])
    lines[1] = "Naples, 1975: the heat of summer."

    response = _patch(player_client, draft["id"], {"world_lines": lines})

    assert response.status_code == 200, response.content
    assert "Naples, 1975: the heat of summer." in response.json()["world_lines"]
    assert "The player rewrote the world summary" in model.requests[-1].prompt.messages[0].text


def test_a_line_the_player_writes_names_what_it_speaks_of(player_client, model):
    # G1: a line of their own is their own words, so the deadline it names shows from then on,
    # and the draft keeps which one it was, not the line.
    model.script(Node.DRAFTER, Reply(json=samples.naples()))
    draft = _draft(player_client, {"premise": samples.NAPLES_PREMISE, "rating": "mature"})
    council = "The council picks the next boss: in 10 days."
    assert council not in draft["world_lines"]
    model.script(Node.DRAFTER, Reply(json=WorldChange()))
    lines = [*draft["world_lines"], "The council picks the next boss in ten days."]

    response = _patch(player_client, draft["id"], {"world_lines": lines})

    assert response.status_code == 200, response.content
    assert council in response.json()["world_lines"]
    assert Draft.objects.get(pk=draft["id"]).told == ["clock:council"]


def test_the_players_rules_are_kept_word_for_word(player_client, model):
    draft = _draft(player_client)
    rules = [
        {"id": r["id"], "text": r["text"], "fixed": r["fixed"]}
        for r in draft["advanced"]["rules"]
        if r["id"] != "omerta"
    ] + [{"text": "Every street has a saint.", "fixed": False}]

    response = _patch(player_client, draft["id"], {"advanced": {"rules": rules}})

    assert response.status_code == 200, response.content
    assert [r["text"] for r in response.json()["advanced"]["rules"]] == [r["text"] for r in rules]


def test_a_stale_edit_is_refused_with_the_current_version(player_client, model):
    draft_id = _draft(player_client)["id"]
    _patch(player_client, draft_id, {"advanced": {"physics": "strict"}})
    calls = len(model.requests)

    for response in (
        _patch(
            player_client, draft_id, {"advanced": {"difficulty": "story"}, "expected_version": 0}
        ),
        _revise(
            player_client,
            draft_id,
            {"target": "world", "instruction": "More rain.", "expected_version": 0},
        ),
    ):
        assert response.status_code == 409
        error = _error(response)
        assert error["code"] == "version_conflict"
        assert error["details"] == {"current_version": 1}
    assert len(model.requests) == calls
    assert Draft.objects.get(pk=draft_id).difficulty == "balanced"


def test_a_save_that_loses_a_race_still_pays_for_its_model_call(player_client, model, player):
    draft_id = _draft(player_client)["id"]
    row = Draft.objects.get(pk=draft_id)
    Draft.objects.filter(pk=draft_id).update(version=3)
    telemetry = TurnTelemetry()
    telemetry.calls.append(ModelCall(model="gemini-3.5-flash", cost_usd=Decimal("0.01")))
    call = service.ModelCall(
        client=None,
        ticket=meter.start(player, meter.DRAFT),
        telemetry=telemetry,
        action="revise",
        premise_id=None,
    )

    with pytest.raises(service.ApiError) as raised:
        async_to_sync(service.save_row)(row, service.to_chain(row), call)

    assert raised.value.code == "version_conflict"
    assert LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT).count() == 2
    assert not CreditHold.objects.exists()


def test_a_save_over_a_newer_draft_is_refused(player_client, model):
    draft_id = _draft(player_client)["id"]
    row = Draft.objects.get(pk=draft_id)
    Draft.objects.filter(pk=draft_id).update(version=5)

    with pytest.raises(service.ApiError) as raised:
        async_to_sync(service.save_row)(row, service.to_chain(row), difficulty="story")

    assert raised.value.code == "version_conflict"
    assert raised.value.details == {"current_version": 5}
    assert Draft.objects.get(pk=draft_id).difficulty == "balanced"


# Starting the story (S6, A1).


def test_starting_creates_the_story_with_its_opening_state(player_client, model, player):
    draft = _draft(player_client)
    _patch(player_client, draft["id"], {"advanced": {"difficulty": "brutal"}})
    state = _state(draft["id"])

    response = _start(
        player_client, draft["id"], {"settings": {"narration_length": "short", "images": "off"}}
    )

    assert response.status_code == 200, response.content
    started = response.json()
    assert started["version"] == 1
    story = Story.objects.get(pk=started["story_id"])
    assert (story.owner_id, story.engine, story.turn, story.version) == (
        player.pk,
        Engine.GRAPH,
        0,
        1,
    )
    assert (story.title, story.genre, story.rating) == (
        "The Esposito Succession",
        "grounded crime",
        "mature",
    )
    assert story.premise == starter("naples-vendetta").premise
    # The draft's state, with the goal and the people its screen kept a surprise held back
    # from Memory (G1).
    held = ["goal:goal-1", "person:bartender", "person:carmine"]
    assert story.state["untold"] == held
    assert WorldState.model_validate(story.state | {"untold": []}) == state
    assert story.settings | {} == {
        "narration_length": "short",
        "tone": None,
        "difficulty": "brutal",
        "event_frequency": "normal",
        "images": "off",
        "suggestions": True,
        "language": "en",
        "accent": None,
    }
    assert not story.scenes.exists()
    assert Draft.objects.get(pk=draft["id"]).story_id == story.id


def test_a_story_starts_knowing_the_rungs_its_draft_named(player_client, model):
    # G18, C6: what the player read before starting, the character knows from the first
    # moment. The draft's rules name Soul Transformation, above the rungs everyone has heard
    # of, and the player's own premise names nothing more.
    model.script(Node.DRAFTER, Reply(json=samples.cultivation()))
    draft = _draft(player_client, {"premise": samples.CULTIVATION_PREMISE, "rating": "teen"})
    before = _state(draft["id"])
    assert before.bible.ladders[0].known_to_all == 4
    assert before.player.sheet.rungs_heard == []
    assert any("Soul Transformation" in rule["text"] for rule in draft["advanced"]["rules"])

    story = Story.objects.get(pk=_start(player_client, draft["id"]).json()["story_id"])

    state = WorldState.model_validate(story.state)
    heard = {(h.ladder_id, h.rung): h for h in state.player.sheet.rungs_heard}
    top = heard[("realms", 4)]
    assert (top.heard_s, top.known_s) == (state.world_s, None)
    # Nothing else of the story's first state moved, but for what Memory holds back (G1).
    state.player.sheet.rungs_heard = []
    assert state.untold == ["goal:goal-1", "person:elder-mo", "person:zhao", "thread:tournament"]
    state.untold = []
    assert state == before


def test_a_draft_in_spanish_is_written_and_started_in_spanish(player_client, model):
    # S10: the drafter writes in the app's language, a starter alone is drafted from its own
    # Spanish words, and the story starts in the draft's language.
    draft = _draft(
        player_client, {"premise_id": "naples-vendetta", "rating": "mature", "language": "es"}
    )

    assert draft["language"] == "es"
    assert draft["premise"] == SPANISH["naples-vendetta"].premise
    # The words code adds to the summary come in Spanish too.
    assert "Sin poderes, porque en este mundo no existen." in draft["character_lines"]
    [request] = model.calls(Node.DRAFTER)
    assert "Spanish from Spain" in request.prompt.system
    assert SPANISH["naples-vendetta"].premise in request.prompt.messages[0].text

    _revise(player_client, draft["id"], {"target": "world", "instruction": "Más lluvia"})
    assert "Spanish from Spain" in model.calls(Node.DRAFTER)[-1].prompt.system

    story = Story.objects.get(pk=_start(player_client, draft["id"]).json()["story_id"])
    assert story.settings["language"] == "es"


def test_a_draft_in_catalan_is_written_and_started_in_catalan(player_client, model):
    # S10: like Spanish, and the story's settings can't switch it later.
    draft = _draft(
        player_client, {"premise_id": "naples-vendetta", "rating": "mature", "language": "ca"}
    )

    assert draft["language"] == "ca"
    assert draft["premise"] == CATALAN["naples-vendetta"].premise
    assert "Sense poders, perquè en aquest món no n'hi ha." in draft["character_lines"]
    assert "Catalan, speaking to the player as tu" in model.calls(Node.DRAFTER)[0].prompt.system

    started = _start(player_client, draft["id"], {"settings": {"language": "en"}})
    story = Story.objects.get(pk=started.json()["story_id"])
    assert story.settings["language"] == "ca"


def test_a_draft_is_in_english_unless_the_app_says_otherwise(player_client, model):
    draft = _draft(player_client)

    assert draft["language"] == "en"
    [request] = model.calls(Node.DRAFTER)
    assert "in English, even where" in request.prompt.system
    refused = _create(player_client, {"premise": MY_PREMISE, "rating": "teen", "language": "fr"})
    assert refused.status_code == 400


def test_starting_twice_returns_the_same_story(player_client, model):
    draft_id = _draft(player_client)["id"]

    first = _start(player_client, draft_id).json()
    again = _start(player_client, draft_id).json()

    assert first == again
    assert Story.objects.count() == 1


def test_starting_from_a_stale_copy_is_refused_and_starts_nothing(player_client, model):
    draft = _draft(player_client)
    _patch(player_client, draft["id"], {"advanced": {"difficulty": "brutal"}})  # now version 2

    stale = _start(player_client, draft["id"], {"expected_version": draft["version"]})

    assert stale.status_code == 409
    assert _error(stale)["code"] == "version_conflict"
    assert _error(stale)["details"] == {"current_version": draft["version"] + 1}
    assert not Story.objects.exists()
    assert Draft.objects.get(pk=draft["id"]).story_id is None

    current = _start(player_client, draft["id"], {"expected_version": draft["version"] + 1})
    assert current.status_code == 200, current.content


def test_a_retried_start_returns_the_story_whatever_version_it_sends(player_client, model):
    """Starting bumps the draft's version, so a retry after a lost answer carries a version that
    is stale by then: it still gets the same story instead of a conflict."""
    draft = _draft(player_client)
    body = {"expected_version": draft["version"]}

    first = _start(player_client, draft["id"], body)
    again = _start(player_client, draft["id"], body)

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert player_client.get(f"/v1/drafts/{draft['id']}").json()["version"] == draft["version"] + 1


def test_a_started_draft_cant_change(player_client, model):
    draft_id = _draft(player_client)["id"]
    story_id = _start(player_client, draft_id).json()["story_id"]
    calls = len(model.requests)

    for response in (
        _patch(player_client, draft_id, {"advanced": {"physics": "strict"}}),
        _revise(player_client, draft_id, {"target": "world", "instruction": "More rain."}),
    ):
        assert response.status_code == 403
        assert _error(response)["details"] == {"story_id": story_id}
    assert len(model.requests) == calls
    assert player_client.get(f"/v1/drafts/{draft_id}").json()["story_id"] == story_id


def test_a_started_story_is_in_the_library_ready_for_its_opening(player_client, model):
    draft_id = _draft(player_client)["id"]
    story_id = _start(player_client, draft_id).json()["story_id"]

    [listed] = player_client.get("/v1/stories").json()
    story = player_client.get(f"/v1/stories/{story_id}").json()

    assert listed["id"] == story_id
    assert (story["turn"], story["version"], story["scenes"]) == (0, 1, [])


# Model failures (T7, S9).


def test_a_blocked_draft_asks_for_a_rephrase_and_saves_nothing(player_client, model):
    model.script(Node.DRAFTER, Block(stage="prompt"))

    response = _create(player_client)

    assert response.status_code == 422
    assert _error(response)["code"] == "unreadable_action"
    assert not Draft.objects.exists()
    assert not CreditHold.objects.exists()


def test_a_model_that_fails_twice_is_unavailable(player_client, model):
    draft_id = _draft(player_client)["id"]
    model.script(Node.DRAFTER, Fail(), Fail())

    response = _revise(player_client, draft_id, {"target": "world", "instruction": "Rain."})

    assert response.status_code == 503
    assert _error(response)["code"] == "llm_unavailable"
    assert Draft.objects.get(pk=draft_id).version == 0
    assert not CreditHold.objects.exists()


def test_a_rejected_key_is_a_bad_key(player_client, model):
    model.script(Node.DRAFTER, Fail(kind="auth", status=401))

    response = _create(player_client, None, **{"X-LLM-Api-Key": "not-a-real-key"})

    assert response.status_code == 422
    assert _error(response)["code"] == "bad_key"


def test_an_unsupported_provider_is_a_header_error(player_client, model):
    response = _create(
        player_client, None, **{"X-LLM-Provider": "other", "X-LLM-Api-Key": "some-key"}
    )

    assert response.status_code == 400
    [field] = _error(response)["details"]["fields"]
    assert (field["field"], field["source"]) == ("X-LLM-Provider", "header")
    assert model.requests == []


# Credits and limits (K2, K6, T9).


def test_a_draft_is_charged_to_the_players_credits(player_client, model, player):
    _draft(player_client)
    _revise(player_client, Draft.objects.get().pk.hex, {"target": "world", "instruction": "Rain."})

    entries = LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT)
    assert entries.count() == 2
    assert all(entry.amount_cents < 0 and entry.story_id is None for entry in entries)
    assert not CreditHold.objects.exists()


def test_a_draft_on_the_players_own_key_is_free(player_client, model, player):
    response = _create(player_client, None, **{"X-LLM-Api-Key": "my-own-key"})

    assert response.status_code == 201
    assert not LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT).exists()


def test_out_of_credits_drafts_nothing(make_user, model, settings):
    settings.BILLING = {**settings.BILLING, "STARTER_POLICY": "verified"}
    client = Client(headers=auth_headers(make_user("broke@example.com")))

    response = _create(client)

    assert response.status_code == 402
    assert _error(response)["code"] == "out_of_credits"
    assert model.requests == []


def test_too_many_drafts_a_minute_are_rate_limited(player_client, model, settings):
    settings.BILLING = {**settings.BILLING, "PER_MINUTE": {"turn": 100, "draft": 1, "image": 100}}
    _draft(player_client)

    response = _create(player_client)

    assert response.status_code == 429
    assert _error(response)["code"] == "rate_limited"
    assert len(model.requests) == 1


# Logs (T5, T6).


def test_each_drafting_request_logs_its_cost_but_never_its_words(player_client, model, log_lines):
    _create(player_client, {"premise": MY_PREMISE, "rating": "teen"})

    lines = log_lines()
    [line] = [entry for entry in lines if entry["logger"] == "drafts"]
    fields = line["draft"]
    assert (fields["action"], fields["outcome"], fields["calls"]) == ("create", "ok", 1)
    assert fields["input_tokens"] > 0 and fields["output_tokens"] > 0
    assert "thinking_tokens" in fields
    assert "cached_tokens" in fields
    everything = json.dumps(lines)
    assert "bakery" not in everything
    assert "Luca" not in everything


# The plain fields (G1, G2): the player changes them at once, with no model call.


def test_the_draft_gives_its_summary_part_by_part(player_client, model):
    model.script(Node.DRAFTER, Reply(json=samples.naples()))
    draft = _draft(player_client, {"premise": samples.NAPLES_PREMISE, "rating": "mature"})

    assert [part["text"] for part in draft["world_parts"]][:10] == draft["world_lines"]
    assert [part["text"] for part in draft["character_parts"]][:10] == draft["character_lines"]
    assert draft["world_parts"][0]["kind"] == "rule"
    assert draft["character_parts"][0] == {"kind": "who", "text": "Luca Esposito, 24."}
    assert draft["character"] | {"standing": "", "manner": ""} == {
        "name": "Luca Esposito",
        "age": 24,
        "people": "",
        "standing": "",
        "looks": "24, lean, dark hair combed back, a scar through one eyebrow.",
        "manner": "",
    }
    assert draft["character"]["manner"]
    assert draft["ladder"] is None
    # G1: of how the story starts, a count and nothing more.
    state = _state(draft["id"])
    kept = draft["kept"]
    assert kept["people"] == len(list(state.npcs()))
    assert kept["events"] == len(state.clocks)
    _assert_nothing_hidden(player_client.get(f"/v1/drafts/{draft['id']}"), state)


def test_a_cultivation_draft_gives_its_ladder_rung_by_rung(player_client, model):
    model.script(Node.DRAFTER, Reply(json=samples.cultivation()))
    draft = _draft(player_client, {"premise": samples.CULTIVATION_PREMISE, "rating": "teen"})

    ladder = draft["ladder"]
    assert ladder["name"] == "Cultivation realms"
    assert ladder["rungs"][0] == "Qi Condensation"
    assert ladder["at"] == 0
    assert set(ladder) == {"name", "rungs", "more", "at", "stage"}


def test_a_name_an_age_and_a_look_change_at_once_and_cost_nothing(player_client, model, player):
    draft = _draft(player_client)
    calls = len(model.requests)
    charged = LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT).count()

    response = _patch(
        player_client,
        draft["id"],
        {
            "title": "The Long Summer",
            "tone": "Dry and tender",
            "character": {
                "name": "Marco Esposito",
                "age": 31,
                "looks": "Tall, a broken nose, a camel coat.",
                "manner": "Laughs first, counts later.",
            },
            "expected_version": draft["version"],
        },
    )

    assert response.status_code == 200, response.content
    edited = response.json()
    assert edited["version"] == draft["version"] + 1
    assert (edited["title"], edited["tone"]) == ("The Long Summer", "Dry and tender")
    assert edited["character"] | {"standing": ""} == {
        "name": "Marco Esposito",
        "age": 31,
        "people": "",
        "standing": "",
        "looks": "Tall, a broken nose, a camel coat.",
        "manner": "Laughs first, counts later.",
    }
    assert edited["character_lines"][0] == "Marco Esposito, 31."
    assert edited["world_lines"] == draft["world_lines"]
    assert len(model.requests) == calls
    assert LedgerEntry.objects.filter(user=player, kind=EntryKind.DRAFT).count() == charged
    # The new name is the character's wherever the draft said the old one, hidden parts too.
    state = _state(draft["id"])
    assert state.player.name == "Marco Esposito"
    assert "Luca" not in json.dumps(Draft.objects.get(pk=draft["id"]).proposal)
    # And the story starts with it.
    started = _start(player_client, draft["id"]).json()
    story = Story.objects.get(pk=started["story_id"])
    assert story.title == "The Long Summer"


def test_a_plain_field_sent_back_as_it_is_changes_nothing(player_client, model):
    draft = _draft(player_client)
    proposal = Draft.objects.get(pk=draft["id"]).proposal

    response = _patch(
        player_client,
        draft["id"],
        {"title": draft["title"], "character": {"name": "Luca Esposito", "age": 24}},
    )

    assert response.status_code == 200, response.content
    assert Draft.objects.get(pk=draft["id"]).proposal == proposal

    # Nor does the whole screen sent back as it was read, with one name changed in it: the
    # lines that still say the old name are no rewriting, so no model is called.
    calls = len(model.requests)
    whole = {key: draft[key] for key in ("title", "tone", "world_lines", "character_lines")}
    character = {key: draft["character"][key] for key in ("age", "looks", "manner")}

    response = _patch(
        player_client, draft["id"], whole | {"character": character | {"name": "Marco Rossi"}}
    )

    assert response.status_code == 200, response.content
    assert response.json()["character"]["name"] == "Marco Rossi"
    assert response.json()["character"]["looks"] == draft["character"]["looks"]
    assert len(model.requests) == calls


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"character": {"name": "   "}}, "character.name"),
        ({"title": "  "}, "title"),
        ({"character": {"name": "x" * 81}}, "character.name"),
        ({"character": {"looks": "x" * 301}}, "character.looks"),
        ({"character": {"age": -1}}, "character.age"),
        ({"tone": ""}, "tone"),
    ],
)
def test_an_empty_or_overlong_plain_field_is_refused(player_client, model, body, field):
    draft = _draft(player_client)

    response = _patch(player_client, draft["id"], body)

    assert response.status_code == 400, response.content
    error = _error(response)
    assert error["code"] == "validation_error"
    assert field in json.dumps(error["details"])
    assert _state(draft["id"]).player.name == "Luca Esposito"


def test_a_real_persons_name_is_no_name_for_a_character(player_client, model):
    # G12: refused at its field before anything is saved, as in a premise.
    draft = _draft(player_client)
    real = real_entities.REAL_PEOPLE[0]

    response = _patch(player_client, draft["id"], {"character": {"name": real}})

    assert response.status_code == 400, response.content
    fields = _error(response)["details"]["fields"]
    assert fields[0]["field"] == "character.name"
    assert fields[0]["type"] == "real_person"
    assert _state(draft["id"]).player.name == "Luca Esposito"


def test_a_change_asked_at_a_part_tells_the_drafter_which(player_client, model):
    draft = _draft(player_client)
    skills = next(p["text"] for p in draft["character_parts"] if p["kind"] == "skills")

    response = _revise(
        player_client,
        draft["id"],
        {"target": "character", "instruction": "Better at this.", "about": "skills"},
    )

    assert response.status_code == 200, response.content
    asked = model.requests[-1].prompt.messages[0].text
    assert f"They ask it about this part of the summary they read:\n{skills}" in asked
    # A part that isn't one is refused before any model call.
    calls = len(model.requests)
    bad = _revise(
        player_client,
        draft["id"],
        {"target": "character", "instruction": "Better at this.", "about": "everything"},
    )
    assert bad.status_code == 400
    assert len(model.requests) == calls
