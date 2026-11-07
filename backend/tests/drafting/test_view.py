"""What the player reads of a draft (G1, G2, G16) and what they never read (C6, N7)."""

import pytest

from engine.context import Language
from engine.state import GiftStrength
from graph.drafting import samples
from graph.drafting.assemble import DraftOptions, assemble
from graph.drafting.catalog import starter
from graph.drafting.schema import FactionP, NpcP, RuleP
from graph.drafting.view import (
    CHARACTER_LINES,
    WORLD_LINES,
    character_lines,
    duration,
    gift_strength,
    hidden_texts,
    public_rules,
    public_text,
    unknown_names,
    world_lines,
)


def _naples(world=None, character=None):
    return assemble(
        world or samples.naples_world(),
        character or samples.naples_character(),
        DraftOptions(premise=samples.NAPLES_PREMISE, template=starter("naples-vendetta").template),
    )


def _cultivation(world=None, character=None, **options):
    return assemble(
        world or samples.cultivation_world(),
        character or samples.cultivation_character(),
        DraftOptions(premise=samples.CULTIVATION_PREMISE, **options),
    )


def _everything_shown(state) -> str:
    lines = world_lines(state) + character_lines(state) + [r.text for r in public_rules(state)]
    return "\n".join(lines).casefold()


def test_the_world_summary_fits_one_screen_in_plain_words():
    lines = world_lines(_naples())

    assert 3 <= len(lines) <= WORLD_LINES
    assert lines[0] == "Grounded: no magic and nothing supernatural, and that won't change."
    assert "Naples, 1974: pistols, cars, telephones and the morning papers." in lines
    assert "The council picks the next boss: in 10 days." in lines
    assert "Who inside the family ordered the killing of my father?" in lines


def test_the_world_summary_names_the_ladder_and_the_known_people():
    lines = world_lines(_cultivation())

    assert any(line.startswith("Cultivation realms: Qi Condensation") for line in lines)
    assert any(line.startswith("Zhao Kun:") for line in lines)


def test_the_character_reads_in_the_worlds_words():
    lines = character_lines(_cultivation())

    assert 3 <= len(lines) <= CHARACTER_LINES
    assert lines[0] == "Lin Feng, 16."
    assert "Third stage of Qi Condensation." in lines
    assert any(line.startswith("Time stop:") for line in lines)
    assert "Goal: Survive the ranking tournament." in lines


def test_a_grounded_character_has_no_powers_in_plain_words():
    lines = character_lines(_naples())

    assert "No powers, since this world has none." in lines
    assert "Skilled: pistol and knife work. Fair: driving." in lines


def test_the_words_code_adds_come_in_the_draft_s_language():
    # S10: the world's own text is whatever the drafter wrote; the words around it are Spanish.
    es = Language.ES
    world = world_lines(_cultivation(), es)
    character = character_lines(_cultivation(), es)
    naples = character_lines(_naples(), es)

    assert "The ranking tournament: en 2 días." in world
    assert "Third stage de Qi Condensation." in character
    assert "Objetivo: Survive the ranking tournament." in character
    assert any(line.endswith("Nadie lo sabe.") for line in character)
    assert "Sin poderes, porque en este mundo no existen." in naples
    assert "Destreza: pistol y knife work. Soltura: driving." in naples
    assert any(line.startswith("Lleva Beretta pistol y flick knife.") for line in naples)
    assert any("200.000 lire" in line for line in naples)
    assert duration(10 * 86400, es) == "10 días" and duration(30, es) == "un momento"


def test_the_words_code_adds_come_in_catalan_too():
    ca = Language.CA
    world = world_lines(_cultivation(), ca)
    character = character_lines(_cultivation(), ca)
    naples = character_lines(_naples(), ca)

    assert "The ranking tournament: d'aquí a 2 dies." in world
    assert "Third stage de Qi Condensation." in character
    assert "Objectiu: Survive the ranking tournament." in character
    assert any(line.endswith("Ningú no ho sap.") for line in character)
    assert "Sense poders, perquè en aquest món no n'hi ha." in naples
    assert "Destresa: pistol i knife work. Soltesa: driving." in naples
    assert any(line.startswith("Porta Beretta pistol i flick knife.") for line in naples)
    assert duration(10 * 86400, ca) == "10 dies" and duration(30, ca) == "un moment"


@pytest.mark.parametrize("make", [_naples, _cultivation])
def test_nothing_hidden_is_ever_shown(make):
    state = make()
    shown = _everything_shown(state)

    hidden = hidden_texts(state)
    assert hidden  # each sample hides something
    for text in hidden:
        assert text.casefold().rstrip(".") not in shown


def test_hidden_texts_cover_every_kind_of_secret():
    state = _naples()

    hidden = hidden_texts(state)
    assert "Carmine Russo, the underboss, paid two soldiers from his own crew." in hidden
    assert "Carmine's driver was seen near the club that night." in hidden
    assert "He ordered the killing of the boss himself." in hidden
    assert "The crew was paid to look away the night the boss died." in hidden
    assert "Pick a new boss before the other families smell weakness." in hidden
    assert "The boy whose body this was owed Zhao Kun twenty spirit stones." in hidden_texts(
        _cultivation()
    )


def test_a_description_that_quotes_a_secret_is_dropped():
    world = samples.naples_world()
    secret = world.npcs[0].secrets[0]
    world.factions.append(
        FactionP(id="leak", name="The Leaky Crew", kind="crew", description=secret)
    )

    lines = world_lines(_naples(world=world))

    assert all("alley behind the club" not in line for line in lines)


def test_someone_the_character_doesnt_know_is_never_named():
    world = samples.naples_world()
    world.npcs.append(
        NpcP(
            id="ghost",
            name="Salvatore Ferro",
            description="A hitman from Palermo.",
            player_knows="unknown",
        )
    )
    world.factions[0].description = "Three crews, a council, and Salvatore Ferro in the shadows."
    state = _naples(world=world)

    assert "Salvatore Ferro" in unknown_names(state)
    assert "salvatore" not in _everything_shown(state)


def test_a_rule_that_quotes_a_secret_is_not_shown():
    world = samples.naples_world()
    secret = world.mysteries[0].answer
    world.rules.append(RuleP(id="leak", text=secret, fixed=False))
    state = _naples(world=world)

    assert "leak" in {r.id for r in state.bible.rules}
    assert "leak" not in {r.id for r in public_rules(state)}
    assert {"no-supernatural", "human-limits", "omerta"} <= {r.id for r in public_rules(state)}


def test_gift_strength_is_the_strongest_gift_held():
    assert gift_strength(_naples()) is GiftStrength.NONE
    assert gift_strength(_cultivation()) is GiftStrength.OVERPOWERED
    assert gift_strength(_cultivation(gift=GiftStrength.SMALL)) is GiftStrength.SMALL


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (30, "moments"),
        (60, "a minute"),
        (3600, "an hour"),
        (5 * 3600, "5 hours"),
        (10 * 86400, "10 days"),
        (365 * 86400, "a year"),
    ],
)
def test_durations_read_as_rough_words(seconds, words):
    assert duration(seconds) == words


def test_a_title_that_quotes_a_secret_is_not_shown():
    world = samples.naples_world()
    world.title = world.mysteries[0].answer
    state = _naples(world=world)

    assert public_text(state, state.bible.title) == ""
    assert public_text(state, state.bible.tone) == "noir"


def test_a_powers_cost_is_shown_so_the_player_can_change_it():
    # G2, G13: a drafted cost the review never showed was a drawback the player first met in
    # play, such as a perception gift that suddenly hurt.
    lines = character_lines(_cultivation())

    stop = next(line for line in lines if line.startswith("Time stop:"))
    assert "(three heartbeats per use; a breath to recharge). Cost: Leaves him drained." in stop


def test_a_power_with_no_cost_shows_none():
    character = samples.cultivation_character()
    for power in character.powers:
        power.costs = []
    lines = character_lines(_cultivation(character=character))

    assert not any("Cost:" in line for line in lines)
