"""Reading the drafter's answer leniently (G1, G2, `graph.drafting.lenient`).

With the draft's schema in the prompt, nothing holds Gemini to it, and from 2026-11-05 most drafts
failed validation twice and answered 503. A value of the wrong shape is fitted where its meaning
is clear, and one that still fails costs only itself, never the draft.
"""

import asyncio
import json
import logging

import pytest
from pydantic import ValidationError

from graph.drafting import chain, samples
from graph.drafting.schema import (
    CalendarP,
    CharacterProposal,
    DraftProposal,
    NpcP,
    PowerP,
    WorldProposal,
)
from graph.drafting.successor import SuccessorProposal
from graph.llm import FakeBackend, ModelClient, ModelConfig, Node, Reply, TurnTelemetry

SECRET_NAME = "Rosa Bianchi"


def _npc(**fields) -> NpcP:
    return NpcP.model_validate({"id": "rosa", "name": SECRET_NAME, **fields})


def _sloppy_naples() -> dict:
    """The Naples sample as Gemini writes it with the schema in the prompt: every property
    written out, nulls for what it has nothing for, and family the way people say it."""
    draft = samples.naples().model_dump(mode="json")
    carmine, bartender = draft["world"]["npcs"]
    carmine["parent_ids"] = [None, None]
    carmine["agenda"]["clock_id"] = None
    bartender["parent_ids"] = {"father": "carmine", "mother": None}
    bartender["aliases"] = None
    bartender["temperament"] = None
    bartender["player_knows"] = "Heard of"
    draft["character"]["parent_ids"] = None
    draft["character"]["age"] = 24.0
    draft["character"]["skills"].append("card tricks")
    draft["world"]["calendar"]["style"] = "Day Count"
    draft["world"]["places"][0]["routes"] = None
    return draft


def test_a_draft_written_loosely_still_drafts():
    fake = FakeBackend()
    llm = ModelClient(fake, ModelConfig(), rating="teen", recorder=TurnTelemetry())
    fake.script(Node.DRAFTER, Reply(text=json.dumps(_sloppy_naples())))

    draft = asyncio.run(
        chain.create(llm, samples.NAPLES_PREMISE, rating="teen", premise_id="naples-vendetta")
    )

    assert len(fake.calls(Node.DRAFTER)) == 1  # no retry
    world, character = draft.proposal.world, draft.proposal.character
    carmine, bartender = world.npcs
    assert carmine.parent_ids == [] and carmine.agenda.clock_id == ""
    assert bartender.parent_ids == ["carmine"]
    assert bartender.aliases == [] and bartender.player_knows == "heard_of"
    assert character.parent_ids == [] and character.age == 24
    assert character.skills[-1].name == "card tricks"
    assert world.calendar.style == "day_count"
    state = draft.state()
    assert state.characters["bartender"].parent_ids == ["carmine"]


def test_a_valid_proposal_reads_exactly_as_before(caplog):
    for proposal in (samples.naples(), samples.cultivation()):
        with caplog.at_level(logging.DEBUG, logger="graph.drafting"):
            assert DraftProposal.model_validate_json(proposal.model_dump_json()) == proposal
    assert not caplog.records


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"parent_ids": None}, {"parent_ids": []}),
        ({"parent_ids": "carmine"}, {"parent_ids": ["carmine"]}),
        ({"parent_ids": ["carmine", None]}, {"parent_ids": ["carmine"]}),
        ({"parent_ids": {"mother": "carmine", "father": None}}, {"parent_ids": ["carmine"]}),
        ({"parent_ids": [{"id": "carmine", "role": "father"}]}, {"parent_ids": ["carmine"]}),
        ({"parent_ids": {"id": "carmine", "role": "father"}}, {"parent_ids": ["carmine"]}),
        ({"description": None, "age": None}, {"description": "", "age": None}),
        ({"age": 41.6}, {"age": 42}),
        ({"age": "41.6"}, {"age": 42}),
        ({"location_id": {"id": "bar", "name": "Bar Sport"}}, {"location_id": "bar"}),
        ({"description": ["Tall.", "Scarred."]}, {"description": "Tall. Scarred."}),
        ({"aliases": "the Widow"}, {"aliases": ["the Widow"]}),
        ({"people_id": 7}, {"people_id": "7"}),
        ({"player_knows": "Heard-of"}, {"player_knows": "heard_of"}),
        ({"temperament": None}, {}),
        ({"agenda": [{"goal": "Run the docks"}]}, {}),
    ],
)
def test_a_value_of_the_wrong_shape_is_fitted_where_its_meaning_is_clear(fields, expected):
    npc = _npc(**fields)

    for name, value in expected.items():
        assert getattr(npc, name) == value
    if "agenda" in fields:
        assert npc.agenda is not None and npc.agenda.goal == "Run the docks"


def test_a_name_stands_for_a_record_that_needs_only_a_name():
    npc = _npc(
        skills=["knives", {"name": "lying", "level": "Expert"}],
        traits="a limp",
        powers=[{"id": "ward", "name": "Ward", "kind_id": "magic", "costs": ["a night's sleep"]}],
    )

    assert [(s.name, s.level) for s in npc.skills] == [("knives", "fair"), ("lying", "expert")]
    assert [t.name for t in npc.traits] == ["a limp"]
    assert [c.text for c in npc.powers[0].costs] == ["a night's sleep"]


def test_records_written_as_a_map_by_id_become_a_list():
    world = WorldProposal.model_validate(
        {
            "title": "t",
            "genre": "g",
            "tone": "noir",
            "era": "now",
            "npcs": {"rosa": {"name": SECRET_NAME}, "ugo": {"id": "ugo-2", "name": "Ugo"}},
        }
    )

    assert [(npc.id, npc.name) for npc in world.npcs] == [("rosa", SECRET_NAME), ("ugo-2", "Ugo")]


def test_what_still_fails_costs_only_itself():
    world = samples.naples_world().model_dump(mode="json")
    world["npcs"].append({"id": "nameless"})  # no name: this one is dropped
    world["npcs"][0]["skills"].append({"name": "luck", "level": "legendary"})
    world["threads"].append({"id": "plot", "title": "A plot", "kind": "conspiracy"})
    world["calendar"] = "the old calendar"
    world["places"][0]["routes"] = [{"to_id": "club", "travel_hours": "a while"}]

    proposal = WorldProposal.model_validate(world)

    assert [npc.id for npc in proposal.npcs] == ["carmine", "bartender"]
    assert proposal.npcs[0].skills[-1].level == "fair"  # the field's default
    assert [thread.id for thread in proposal.threads] == ["revenge"]
    assert proposal.calendar == CalendarP()
    assert proposal.places[0].routes == []


@pytest.mark.parametrize(
    "fields",
    [
        {"description": [1, 2]},
        {"temperament": [{"voice": "low"}, {"voice": "loud"}]},
        {"age": "Infinity"},
        {"age": float("nan")},
        {"age": [40]},
    ],
)
def test_a_value_that_cant_be_fitted_takes_its_fields_default(fields):
    [(name, _)] = fields.items()

    npc = _npc(**fields)

    assert getattr(npc, name) == NpcP.model_fields[name].get_default(call_default_factory=True)


def test_a_required_part_that_fails_still_fails_the_answer():
    character = samples.naples_character().model_dump(mode="json")

    with pytest.raises(ValidationError):
        DraftProposal.model_validate({"character": character})
    with pytest.raises(ValidationError):
        DraftProposal.model_validate({"world": None, "character": character})
    with pytest.raises(ValidationError):
        PowerP.model_validate({"id": "ward", "name": "Ward"})  # no kind


def test_every_proposal_reads_leniently():
    character = CharacterProposal.model_validate({"name": "Luca", "goals": "Find the killer."})
    successor = SuccessorProposal.model_validate(
        {"name": "Ada", "situation": "Ada mends a net.", "traits": None}
    )

    assert character.goals == ["Find the killer."]
    assert successor.traits == []


def test_a_repair_is_logged_with_where_and_what_but_never_the_value(log_lines):
    _npc(parent_ids={"id": SECRET_NAME}, skills=[{"name": SECRET_NAME, "level": SECRET_NAME}])

    repairs = [line["proposal"] for line in log_lines() if "proposal" in line]
    assert {"record": "NpcP", "field": "parent_ids", "repair": "fitted"} | {
        "errors": ["list_type"]
    } in repairs
    assert {"record": "SkillP", "field": "level", "repair": "default"} | {
        "errors": ["enum"]
    } in repairs
    assert SECRET_NAME not in json.dumps(log_lines())


def test_dropped_items_are_counted(log_lines):
    _npc(skills=[{"name": "knives"}, {"level": "master"}, 3])

    [repair] = [line["proposal"] for line in log_lines() if "proposal" in line]
    assert repair["field"] == "skills" and repair["repair"] == "dropped_items"
    assert repair["dropped"] == 2
