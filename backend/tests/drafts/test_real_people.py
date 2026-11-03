"""G12 at the drafting API: the player's words never bring a real person into a story, and the
refusal comes before any model call, so it costs nothing (docs/API.md)."""

from billing.models import EntryKind, LedgerEntry
from drafts.models import Draft
from graph.drafting import samples
from graph.drafting.schema import NpcP
from graph.llm import Node, Reply
from tests.drafts.test_api import _create, _draft, _error, _patch, _revise, _state


def _refused(response, field: str) -> dict:
    assert response.status_code == 400, response.content
    error = _error(response)
    assert error["code"] == "validation_error"
    [problem] = error["details"]["fields"]
    assert (problem["field"], problem["type"]) == (field, "real_person")
    assert problem["message"] == error["message"]
    return error


def test_a_premise_with_a_real_person_is_refused_before_any_model_call(player_client, model):
    premise = "I'm Taylor Swift's bodyguard on her last world tour."

    error = _refused(_create(player_client, {"premise": premise, "rating": "teen"}), "premise")

    assert "Taylor Swift" in error["message"]
    assert model.requests == [] and not Draft.objects.exists()
    assert not LedgerEntry.objects.filter(kind=EntryKind.DRAFT).exists()


def test_a_real_organisation_in_a_premise_is_a_backdrop(player_client, model):
    draft = _draft(
        player_client,
        {"premise": "A rookie FBI agent sent undercover in Naples.", "rating": "mature"},
    )
    assert draft["title"]


def test_a_rule_with_a_real_person_is_refused(player_client, model):
    body = {
        "premise": "A port town where the tide brings strange things.",
        "rating": "teen",
        "advanced": {
            "rules": [
                {"text": "Magic is rare.", "fixed": True},
                {"text": "Elon Musk owns the tide.", "fixed": False},
            ]
        },
    }
    _refused(_create(player_client, body), "advanced.rules.1.text")
    assert model.requests == []


def test_a_revision_with_a_real_person_is_refused(player_client, model):
    draft = _draft(player_client)
    calls = len(model.requests)

    response = _revise(
        player_client, draft["id"], {"target": "world", "instruction": "Add Elon Musk as a rival."}
    )

    _refused(response, "instruction")
    assert len(model.requests) == calls
    assert Draft.objects.get(pk=draft["id"]).version == 0


def test_an_edited_line_with_a_real_person_is_refused_at_that_line(player_client, model):
    draft = _draft(player_client)
    lines = [*draft["world_lines"], "Jeff Bezos owns the docks."]
    calls = len(model.requests)

    _refused(
        _patch(player_client, draft["id"], {"world_lines": lines}), f"world_lines.{len(lines) - 1}"
    )

    assert len(model.requests) == calls


def test_lines_the_drafter_wrote_are_not_held_against_the_player(player_client, model):
    # The drafter's free text can name someone real as a backdrop; sending its line back
    # unchanged is not the player naming them.
    proposal = samples.naples()
    proposal.character.description = "Grew up on Rihanna's songs and his father's stories."
    model.script(Node.DRAFTER, Reply(json=proposal), Reply(json=proposal.character))
    draft = _draft(player_client)
    lines = [*draft["character_lines"]]
    assert any("Rihanna" in line for line in lines)
    lines[0] = lines[0] + " Quick with a knife."

    response = _patch(player_client, draft["id"], {"character_lines": lines})

    assert response.status_code == 200, response.content


def test_a_drafted_real_person_never_reaches_the_story(player_client, model):
    world = samples.naples_world()
    world.npcs.append(NpcP(id="musk", name="Elon Musk", age=55, location_id="bar"))
    proposal = samples.naples()
    proposal.world = world
    model.script(Node.DRAFTER, Reply(json=proposal))

    draft = _draft(player_client)

    names = {c.name for c in _state(draft["id"]).characters.values()}
    assert "Elon Musk" not in names
    assert not any("Elon Musk" in line for line in draft["world_lines"])
