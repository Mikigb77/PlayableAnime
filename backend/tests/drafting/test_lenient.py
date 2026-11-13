"""Reading the drafter's answer leniently (G1, G2, `graph.drafting.lenient`).

With the draft's schema in the prompt, nothing holds Gemini to it, and from 2026-11-05 most drafts
failed validation twice and answered 503. A value of the wrong shape in the model's answer is
fitted where its meaning is clear, and one that still fails costs only itself, never the draft.
What code builds stays strict.
"""

import asyncio
import json
import logging

import pytest
from pydantic import ValidationError

from graph.drafting import chain, lenient, samples
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
from graph.llm.types import REPAIRS

SECRET_NAME = "Rosa Bianchi"


def _read(model, data, context=None):
    """`data` read as the client reads a model's answer."""
    return model.model_validate(data, context=context or lenient.model_output())


def _npc(**fields) -> NpcP:
    return _read(NpcP, {"id": "rosa", "name": SECRET_NAME, **fields})


def test_a_couple_written_loosely_is_still_read():
    """W17: the partner as a record or a list, the stage in any case, and a custom left null."""
    wife = _npc(partner_id={"id": "carmine", "name": "Carmine Russo"}, partner_bond="Married")
    assert (wife.partner_id, wife.partner_bond) == ("carmine", "married")
    lover = _npc(partner_id=["carmine"], partner_bond="engaged to be wed")
    assert (lover.partner_id, lover.partner_bond) == ("carmine", "together")  # the default
    assert _npc(partner_id=None, partner_bond=None).partner_id == ""
    world = samples.naples().world.model_dump(mode="json") | {"several_partners": None}
    assert _read(WorldProposal, world).several_partners is False


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


def _drafting_client() -> tuple[FakeBackend, ModelClient]:
    fake = FakeBackend()
    return fake, ModelClient(fake, ModelConfig(), rating="teen", recorder=TurnTelemetry())


def test_a_draft_written_loosely_still_drafts():
    fake, llm = _drafting_client()
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


def test_the_repairs_are_logged_once_per_answer_with_no_value(log_lines):
    fake, llm = _drafting_client()
    draft = _sloppy_naples()
    draft["world"]["npcs"][1]["parent_ids"] = {"id": SECRET_NAME}
    draft["world"]["npcs"].append({"id": "nameless", "description": SECRET_NAME})
    fake.script(Node.DRAFTER, Reply(text=json.dumps(draft)))

    asyncio.run(chain.create(llm, samples.NAPLES_PREMISE, rating="teen"))

    [line] = [line for line in log_lines() if line["message"] == "Model answer repaired"]
    fields = line["llm"]
    assert fields["node"] == "drafter" and fields["repair_count"] == len(fields["repairs"])
    assert "NpcP.parent_ids: fitted (list_type)" in fields["repairs"]
    assert "NpcP.temperament: null (model_type)" in fields["repairs"]
    assert "WorldProposal.npcs: dropped 1 (missing)" in fields["repairs"]
    assert len(set(fields["repairs"])) == len(fields["repairs"])
    assert SECRET_NAME not in json.dumps(log_lines())


def test_a_valid_proposal_reads_exactly_as_before(caplog):
    for proposal in (samples.naples(), samples.cultivation()):
        context = lenient.model_output()
        with caplog.at_level(logging.DEBUG):
            read = DraftProposal.model_validate_json(proposal.model_dump_json(), context=context)
        assert read == proposal
        assert context[REPAIRS] == []
    assert not caplog.records


def test_a_proposal_code_builds_stays_strict():
    with pytest.raises(ValidationError):
        NpcP.model_validate({"id": "rosa", "name": "Rosa", "parent_ids": None})
    with pytest.raises(ValidationError):
        NpcP(id="rosa", name="Rosa", skills=["knives"])
    with pytest.raises(ValidationError):
        DraftProposal.model_validate_json(json.dumps(_sloppy_naples()))


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
        ({"age": "40.5"}, {"age": 41}),
        ({"location_id": {"id": "bar", "name": "Bar Sport"}}, {"location_id": "bar"}),
        ({"location_id": ["bar", "club"]}, {"location_id": "bar"}),
        ({"description": ["Tall.", "Scarred."]}, {"description": "Tall. Scarred."}),
        ({"appearance": ["tall", "scarred"]}, {"appearance": "tall, scarred"}),
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


def test_records_written_as_a_map_by_id_or_name_become_a_list():
    world = _read(
        WorldProposal,
        {
            "title": "t",
            "genre": "g",
            "tone": "noir",
            "era": "now",
            "npcs": {"rosa": {"name": SECRET_NAME}, "ugo": {"id": "ugo-2", "name": "Ugo"}},
        },
    )
    by_name = _npc(skills={"knives": {"level": "skilled"}}, traits={"a limp": "flaw"})

    assert [(npc.id, npc.name) for npc in world.npcs] == [("rosa", SECRET_NAME), ("ugo-2", "Ugo")]
    assert [(s.name, s.level) for s in by_name.skills] == [("knives", "skilled")]
    assert [t.name for t in by_name.traits] == ["a limp"]


def test_a_reference_written_as_a_list_is_its_first_id():
    power = _read(PowerP, {"id": "ward", "name": "Ward", "kind_id": ["magic", "qi"]})

    assert power.kind_id == "magic"


def test_what_still_fails_costs_only_itself():
    world = samples.naples_world().model_dump(mode="json")
    world["npcs"].append({"id": "nameless"})  # no name: this one is dropped
    world["npcs"].append({"id": "blank", "name": ["", " "]})  # a blank name is no name
    world["npcs"][0]["skills"].append({"name": "luck", "level": "legendary"})
    world["threads"].append({"id": "plot", "title": "A plot", "kind": "conspiracy"})
    world["calendar"] = "the old calendar"
    world["places"][0]["routes"] = [{"to_id": "club", "travel_hours": "a while"}]

    proposal = _read(WorldProposal, world)

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
        _read(DraftProposal, {"character": character})
    with pytest.raises(ValidationError):
        _read(DraftProposal, {"world": None, "character": character})
    with pytest.raises(ValidationError):
        _read(PowerP, {"id": "ward", "name": "Ward"})  # no kind


def test_every_proposal_reads_leniently():
    character = _read(CharacterProposal, {"name": "Luca", "goals": "Find the killer."})
    successor = _read(
        SuccessorProposal, {"name": "Ada", "situation": "Ada mends a net.", "traits": None}
    )

    assert character.goals == ["Find the killer."]
    assert successor.traits == []


def test_each_repair_is_noted_with_where_and_what_but_never_the_value():
    context = lenient.model_output()

    _read(
        NpcP,
        {
            "id": "rosa",
            "name": SECRET_NAME,
            "parent_ids": {"id": SECRET_NAME},
            "skills": [{"name": SECRET_NAME, "level": SECRET_NAME}, {"level": "master"}, 3],
        },
        context,
    )

    assert set(context[REPAIRS]) == {
        "NpcP.parent_ids: fitted (list_type)",
        "SkillP.level: default (enum)",
        "NpcP.skills: dropped 2 (missing, model_type)",
    }
