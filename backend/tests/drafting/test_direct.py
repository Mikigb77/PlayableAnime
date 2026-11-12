"""G1, G2: the plain fields of a draft, which code writes in at once, with no model
(`graph.drafting.direct`, Miki 2026-11-10)."""

import json

from graph.drafting import samples
from graph.drafting.direct import Fields, apply, renamed
from graph.drafting.schema import DraftProposal, NpcP


def _texts(proposal) -> str:
    return json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False)


def test_a_new_name_takes_the_old_ones_place_everywhere():
    draft = renamed(samples.naples(), "Marco Esposito")

    assert draft.character.name == "Marco Esposito"
    carmine = next(npc for npc in draft.world.npcs if npc.id == "carmine")
    assert carmine.secrets == [
        "He ordered the killing of Marco's father in the alley behind the club."
    ]
    assert draft.world.opening.positions == ["Carmine in the back booth", "Marco at the door"]
    assert draft.world.summary == "Marco is back in Naples after his father's murder."
    assert "Luca" not in _texts(draft)


def test_a_word_of_the_name_that_others_share_stays_theirs():
    # The family keeps its name whatever its son is called now.
    before = samples.naples()
    draft = renamed(before, "Marco Rossi")

    assert draft.character.name == "Marco Rossi"
    assert [f.name for f in draft.world.factions] == [f.name for f in before.world.factions]
    assert [n.name for n in draft.world.npcs] == [n.name for n in before.world.npcs]
    assert "Esposito" in _texts(draft.world)
    assert draft.character.family_name == "Esposito"


def test_each_word_stands_in_for_the_one_in_its_place():
    draft = renamed(samples.cultivation(), "Zhang Wei")

    elder = next(npc for npc in draft.world.npcs if npc.secrets)
    assert "the night Zhang Wei woke" in " ".join(elder.secrets)
    assert draft.world.opening.positions[0] == "Zhang at the well with a full bucket"
    assert draft.world.summary.startswith("Zhang Wei wakes in the outer court")
    assert draft.character.family_name == "the fallen Zhang clan"


def test_a_name_of_another_length_puts_its_first_word_for_each_own_word():
    draft = renamed(samples.cultivation(), "Kai")

    assert draft.character.name == "Kai"
    assert draft.world.opening.positions[0] == "Kai at the well with a full bucket"
    assert draft.world.summary.startswith("Kai wakes in the outer court")


def test_ids_and_other_peoples_names_are_never_reworded():
    before = samples.cultivation()
    # Someone else is called Lin too, so "Lin" alone is no longer the character's own word.
    cousin = NpcP(id="lin-mei", name="Lin Mei", description="A cousin in the inner court.")
    before = before.model_copy(
        update={"world": before.world.model_copy(update={"npcs": [*before.world.npcs, cousin]})}
    )

    draft = renamed(before, "Zhang Wei")

    assert draft.world.npcs[-1] == cousin
    assert draft.world.opening.positions[0] == "Lin at the well with a full bucket"
    assert draft.world.summary.startswith("Zhang Wei wakes")
    assert [n.id for n in draft.world.npcs] == [n.id for n in before.world.npcs]
    assert draft.world.opening.present_ids == before.world.opening.present_ids


def _called_lin(**world) -> DraftProposal:
    """The outer disciple under a name of one word, in a world with `world` changed."""
    before = samples.cultivation()
    return DraftProposal(
        world=before.world.model_copy(update=world),
        character=before.character.model_copy(update={"name": "Lin", "aliases": ["Little Lin"]}),
    )


def test_what_others_are_called_stays_beside_a_name_of_one_word():
    # Lin Mei and Old Lin are called so themselves, and the story says them by those names.
    base = samples.cultivation().world
    cousin = NpcP(
        id="lin-mei",
        name="Lin Mei",
        aliases=["Old Lin"],
        description="A cousin in the inner court.",
        secrets=["Lin Mei told Old Lin's wife what Lin did at the well."],
    )
    before = _called_lin(
        npcs=[*base.npcs, cousin],
        summary="Lin wakes in the outer court. Lin Mei is already at the well.",
    )

    draft = renamed(before, "Kai")

    assert draft.character.name == "Kai"
    assert draft.character.aliases == ["Little Kai"]
    kept = draft.world.npcs[-1]
    assert (kept.name, kept.aliases) == ("Lin Mei", ["Old Lin"])
    assert kept.secrets == ["Lin Mei told Old Lin's wife what Kai did at the well."]
    assert draft.world.summary == "Kai wakes in the outer court. Lin Mei is already at the well."


def test_a_name_that_leans_on_the_characters_follows_it():
    base = samples.cultivation().world
    mother = NpcP(id="mother", name="Lin's mother", description="She sells tea by the gate.")
    before = _called_lin(npcs=[*base.npcs, mother])

    draft = renamed(before, "Kai")

    assert draft.world.npcs[-1].name == "Kai's mother"
    assert draft.world.npcs[-1].id == "mother"

    # And beside a name of two words, such a name lends the character none of its words.
    mother = mother.model_copy(update={"name": "Lin Feng's mother"})
    world = base.model_copy(update={"npcs": [*base.npcs, mother]})
    whole = DraftProposal(world=world, character=samples.cultivation().character)

    draft = renamed(whole, "Zhang Wei")

    assert draft.world.npcs[-1].name == "Zhang Wei's mother"
    assert draft.world.opening.positions[0] == "Zhang at the well with a full bucket"


def test_a_record_called_just_what_the_character_was_keeps_its_name():
    # A sect called Lotus beside a character who was called Lotus: the sect is still Lotus.
    before = samples.cultivation()
    factions = [f.model_copy(update={"name": "Lotus"}) for f in before.world.factions[:1]]
    before = DraftProposal(
        world=before.world.model_copy(
            update={"factions": factions, "summary": "Lotus wakes in the outer court."}
        ),
        character=before.character.model_copy(update={"name": "Lotus"}),
    )

    draft = renamed(before, "Mei")

    assert draft.character.name == "Mei"
    assert [f.name for f in draft.world.factions] == ["Lotus"]
    assert draft.world.summary == "Mei wakes in the outer court."


def test_the_same_name_or_an_empty_one_changes_nothing():
    draft = samples.naples()

    assert renamed(draft, "  Luca   Esposito ") is draft
    assert renamed(draft, "   ") is draft
    assert apply(draft, Fields(name="  ", title="", looks=" ")) is draft
    assert apply(draft, Fields()) is draft
    assert not Fields()
    assert Fields(age=0)


def test_an_alias_that_is_the_new_name_is_dropped():
    before = samples.naples()
    character = before.character.model_copy(update={"aliases": ["Marco", "the Boss's Son"]})
    before = before.model_copy(update={"character": character})

    draft = renamed(before, "Marco")

    assert draft.character.aliases == ["the Boss's Son"]


def test_a_new_age_takes_the_old_ones_place_in_the_looks():
    before = samples.naples()
    assert before.character.appearance.startswith("24, lean")

    draft = apply(before, Fields(age=31))

    assert draft.character.age == 31
    assert draft.character.appearance.startswith("31, lean")
    assert draft.world == before.world


def test_the_title_the_tone_the_looks_and_the_manner_are_written_word_for_word():
    before = samples.naples()

    draft = apply(
        before,
        Fields(
            title="  The  Long Summer ",
            tone="Dry and tender",
            looks="Tall, a broken nose, a camel coat.",
            manner="Laughs first, counts later.",
            age=30,
        ),
    )

    assert draft.world.title == "The Long Summer"
    assert draft.world.tone == "Dry and tender"
    # What the player wrote in the same change is theirs as written, the old age included.
    assert draft.character.appearance == "Tall, a broken nose, a camel coat."
    assert draft.character.description == "Laughs first, counts later."
    assert draft.character.age == 30
    assert draft.character.name == before.character.name
    assert draft.world.npcs == before.world.npcs
