"""G12 in drafting: a real person in the player's words is refused, and real people and
organisations never become characters or factions in what the model drafts."""

import asyncio

import pytest

from engine.invariants import check_state
from graph.drafting import chain, samples
from graph.drafting.assemble import PLAYER_FALLBACK_NAME, DraftOptions, assemble
from graph.drafting.catalog import STARTER_PREMISES
from graph.drafting.real_names import real_person_in, without_real_names
from graph.drafting.schema import ConnectionP, FactionP, NpcP
from graph.llm import FakeBackend, ModelClient, ModelConfig, Node, Reply, TurnTelemetry


def blocks(log_lines) -> list[dict]:
    return [line["block"] for line in log_lines() if "block" in line]


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("I'm Taylor Swift's bodyguard on her last tour.", "Taylor Swift"),
        ("A rookie agent hunting Putin's money in Naples.", "Putin"),
        ("The Google boss Sundar Pichai is my rival.", "Sundar Pichai"),
    ],
)
def test_a_real_person_in_the_players_words_is_found(text, name, log_lines):
    found = real_person_in([("title", "A quiet start"), ("premise", text)])

    assert (found.field, found.name) == ("premise", name)
    assert name in found.message and "fictional" in found.message
    assert blocks(log_lines) == [
        {
            "node": "drafter",
            "source": "code",
            "categories": ["real_person"],
            "stage": "prompt",
            "count": 1,
        }
    ]
    assert name not in str(log_lines()[0])  # names never reach the log at WARNING (T6)


@pytest.mark.parametrize(
    "text",
    [
        "A rookie FBI agent in Naples, 1974.",  # a real organisation is a backdrop
        "I serve the Esposito family after my father's murder.",
        "Napoleon's last campaign, seen by a drummer boy.",  # long dead (G12)
        "",
    ],
)
def test_fiction_and_backdrops_pass(text):
    assert real_person_in([("premise", text)]) is None


@pytest.mark.parametrize("premise", STARTER_PREMISES, ids=lambda p: p.id)
def test_no_starter_premise_names_a_real_person(premise):
    assert real_person_in([("premise", premise.premise)]) is None


def _naples_with_real_names():
    proposal = samples.naples()
    world, character = proposal.world, proposal.character
    world.npcs += [
        NpcP(id="musk", name="Elon Musk", age=55, location_id="bar"),
        NpcP(id="lia", name="Lia Conte", aliases=["Rihanna", "the Rose"], age=30),
    ]
    world.factions += [FactionP(id="gambino", name="the Gambino family", leader_ids=["musk"])]
    world.factions[0].leader_ids = ["carmine", "musk"]
    world.opening.present_ids += ["musk"]
    world.clocks[0].owner_id = "gambino"
    character.aliases = ["Kim Kardashian", "Lucky"]
    character.connections += [ConnectionP(name="Taylor Swift"), ConnectionP(name="the Gambinos")]
    return proposal


def test_real_people_and_organisations_never_become_characters_or_factions(log_lines):
    cleaned = without_real_names(_naples_with_real_names())

    assert {n.id for n in cleaned.world.npcs} == {"carmine", "bartender", "lia"}
    assert next(n for n in cleaned.world.npcs if n.id == "lia").aliases == ["the Rose"]
    assert "gambino" not in {f.id for f in cleaned.world.factions}
    assert cleaned.character.aliases == ["Lucky"]
    assert [c.name for c in cleaned.character.connections][-1] == "the Gambinos"
    assert "Taylor Swift" not in [c.name for c in cleaned.character.connections]
    [block] = blocks(log_lines)
    assert block["stage"] == "update" and block["count"] == 5

    # References to who was left out resolve to nothing, and the world still holds together.
    state = assemble(cleaned.world, cleaned.character, DraftOptions())
    assert check_state(state) == []
    names = {c.name for c in state.characters.values()}
    assert "Elon Musk" not in names and "Lia Conte" in names
    assert all("musk" not in f.leader_ids for f in state.factions.values())


def test_a_player_character_given_a_real_name_gets_the_default_name():
    proposal = samples.naples()
    proposal.character.name = "Cristiano Ronaldo"
    proposal.character.family_name = "Ronaldo"

    cleaned = without_real_names(proposal.character)
    state = assemble(proposal.world, cleaned, DraftOptions())

    assert cleaned.name == ""
    assert state.characters[state.player_id].name == PLAYER_FALLBACK_NAME


def test_a_clean_proposal_comes_back_unchanged(log_lines):
    proposal = samples.naples()
    assert without_real_names(proposal) is proposal
    assert without_real_names(proposal.world) is proposal.world
    assert blocks(log_lines) == []


def test_every_drafting_call_is_cleaned():
    fake = FakeBackend()
    llm = ModelClient(fake, ModelConfig(), rating="teen", recorder=TurnTelemetry(), retry_delay_s=0)
    dirty = _naples_with_real_names()
    fake.script(
        Node.DRAFTER, Reply(json=dirty), Reply(json=dirty.world), Reply(json=dirty.character)
    )

    async def go():
        draft = await chain.create(llm, samples.NAPLES_PREMISE, rating="teen")
        drafted = draft.proposal
        draft = await chain.revise(llm, draft, "world", "add a rival crew")
        draft = await chain.revise(llm, draft, "character", "make me older")
        return drafted, draft.proposal

    drafted, revised = asyncio.run(go())
    for proposal in (drafted, revised):
        assert "musk" not in {n.id for n in proposal.world.npcs}
        assert "gambino" not in {f.id for f in proposal.world.factions}
        assert "Kim Kardashian" not in proposal.character.aliases
