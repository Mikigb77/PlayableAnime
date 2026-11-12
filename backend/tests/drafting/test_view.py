"""What the player reads of a draft (G1, G2, G16) and what they never read (C6, N7)."""

import pytest

from engine.context import Language
from engine.state import GiftStrength
from graph.drafting import samples
from graph.drafting.assemble import DraftOptions, assemble
from graph.drafting.catalog import starter
from graph.drafting.openers import Said
from graph.drafting.schema import FactionP, NpcP, RuleP, RungP, TalentP
from graph.drafting.view import (
    CHARACTER_LINES,
    WORLD_LINES,
    PartKind,
    character_lines,
    character_parts,
    duration,
    gift_strength,
    hidden_texts,
    identity,
    kept,
    ladder_view,
    public_rules,
    public_text,
    shown,
    unknown_names,
    world_lines,
    world_parts,
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


def test_the_summary_keeps_how_the_story_starts_a_surprise():
    # G1 (Miki, 2026-11-10): the first event, the first people and the first goal are shown
    # only when the player's own words name them. Neither premise names a deadline or anyone.
    naples = world_lines(_naples(), said=Said(samples.NAPLES_PREMISE))
    assert "The council picks the next boss: in 10 days." not in naples
    assert not any(line.startswith(("Carmine Russo:", "Gennaro:")) for line in naples)
    # What the premise speaks of is there: the killing, and the family it happened in.
    assert "Who inside the family ordered the killing of my father?" in naples
    assert any(line.startswith("The Esposito family:") for line in naples)
    # What the character is after is theirs to say: the killing is in the premise, and the
    # goal the drafter made of it shows once their words say it as an aim.
    luca = character_lines(_naples(), said=Said(samples.NAPLES_PREMISE))
    assert not any(line.startswith("Goal:") for line in luca)
    assert "Three loyal soldiers." not in luca
    sworn = Said(f"{samples.NAPLES_PREMISE} I will find out who.")
    assert "Goal: Find out who killed my father." in character_lines(_naples(), said=sworn)

    cultivation = world_lines(_cultivation(), said=Said(samples.CULTIVATION_PREMISE))
    assert not any("tournament" in line for line in cultivation)
    assert not any(line.startswith(("Zhao Kun:", "Elder Mo:")) for line in cultivation)
    lin = character_lines(_cultivation(), said=Said(samples.CULTIVATION_PREMISE))
    assert not any(line.startswith("Goal:") for line in lin)
    # Who the character is stays whole.
    assert lin[0] == "Lin Feng, 16." and any(line.startswith("Time stop:") for line in lin)


def test_what_the_players_words_name_is_in_the_summary():
    # A deadline the premise sets a time for is there, and it gives no goal: "the ranking
    # tournament starts in two days" says what is coming, not what the character is after.
    said = Said(starter("outer-disciple").premise)
    assert "The ranking tournament: in 2 days." in world_lines(_cultivation(), said=said)
    assert not any(line.startswith("Goal:") for line in character_lines(_cultivation(), said=said))
    said = Said(samples.CULTIVATION_PREMISE + " I must survive the ranking tournament.")
    assert "Goal: Survive the ranking tournament." in character_lines(_cultivation(), said=said)
    # A person is named by their name.
    said = Said(samples.CULTIVATION_PREMISE + " Zhao Kun has hated me since the day I arrived.")
    people = world_lines(_cultivation(), said=said)
    assert any(line.startswith("Zhao Kun:") for line in people)
    assert not any(line.startswith("Elder Mo:") for line in people)
    # What a change they asked for later named is kept by its key, and shows like the rest.
    said = Said(samples.CULTIVATION_PREMISE, frozenset({"clock:tournament", "person:elder-mo"}))
    told = world_lines(_cultivation(), said=said)
    assert "The ranking tournament: in 2 days." in told
    assert any(line.startswith("Elder Mo:") for line in told)
    assert not any(line.startswith("Zhao Kun:") for line in told)
    # A family the premise speaks of names nobody in it: Carmine Esposito is still a surprise.
    world = samples.naples_world()
    carmine = next(npc for npc in world.npcs if npc.id == "carmine")
    carmine.name = "Carmine Esposito"
    premise = starter("naples-vendetta").premise
    assert "Esposito family" in premise
    shown = world_lines(_naples(world), said=Said(premise))
    assert not any(line.startswith("Carmine Esposito:") for line in shown)


def test_what_the_character_wants_is_a_surprise_until_the_players_words_say_it():
    # G1: "Wants revenge for his father" gives the character a goal the premise never spoke of.
    state = _naples()
    nature = "Hot-headed and loyal."
    assert f"{nature} Wants revenge for his father." in character_lines(state)

    kept_back = character_lines(state, said=Said(samples.NAPLES_PREMISE))
    assert nature in kept_back and not any("Wants" in line for line in kept_back)
    # Their own words say it, in the premise or in a change they asked for later.
    said = Said(samples.NAPLES_PREMISE + " I want revenge for my father.")
    assert f"{nature} Wants revenge for his father." in character_lines(state, said=said)
    told = Said(samples.NAPLES_PREMISE, frozenset({"want:revenge for his father"}))
    assert f"{nature} Wants revenge for his father." in character_lines(state, said=told)
    # With nothing else to say of their nature, the line is gone, not left empty.
    state.player.sheet.disposition.temperament.traits = []
    bare = character_parts(state, Language.EN, Said(samples.NAPLES_PREMISE))
    assert PartKind.NATURE not in {part.kind for part in bare}


def test_everyone_the_players_words_name_is_in_the_summary():
    # Without the player's say, the summary names the first two key people with a line on who
    # they are. With it, it names whoever their words name, with or without that line.
    world = samples.cultivation_world()
    world.npcs.append(NpcP(id="wei", name="Wei Shan", location_id="well"))
    world.npcs.append(NpcP(id="old-hu", name="Old Hu", description="The well keeper."))
    state = _cultivation(world)
    assert [line for line in world_lines(state) if line.startswith(("Wei", "Old Hu"))] == []

    premise = samples.CULTIVATION_PREMISE + " Zhao Kun, Elder Mo and Wei Shan all know my name."
    people = [
        part.text
        for part in world_parts(state, Language.EN, Said(premise))
        if part.kind is PartKind.PERSON
    ]
    assert [text.partition(":")[0] for text in people] == ["Zhao Kun", "Elder Mo", "Wei Shan."]
    # Old Hu is still the story's to introduce.
    assert not any("Old Hu" in text for text in people)


def test_the_world_summary_names_the_ladder_and_the_known_people():
    lines = world_lines(_cultivation())

    assert any(line.startswith("Cultivation realms: Qi Condensation") for line in lines)
    assert any(line.startswith("Zhao Kun:") for line in lines)


def test_the_world_summary_names_only_the_rungs_everyone_has_heard_of():
    # G18, C6: the summary names what the character's path starts with, and the rungs above
    # are the story's to name.
    assert (
        "Cultivation realms: Qi Condensation, Foundation Establishment, Core Formation, "
        "Nascent Soul and beyond."
    ) in world_lines(_cultivation())

    few = samples.cultivation_world()
    few.ladders[0].known_to_all = 2
    lines = world_lines(_cultivation(few))
    assert "Cultivation realms: Qi Condensation, Foundation Establishment and beyond." in lines
    assert "Core Formation" not in "\n".join(lines)

    # A ladder everyone knows whole has nothing beyond, and a long one names its first five.
    whole = samples.cultivation_world()
    whole.ladders[0].known_to_all = 5
    assert any(
        line.endswith("Nascent Soul, Soul Transformation.")
        for line in world_lines(_cultivation(whole))
    )
    long = samples.cultivation_world()
    long.ladders[0].rungs += [RungP(name="Void Refinement"), RungP(name="Immortal Ascension")]
    long.ladders[0].known_to_all = 7
    assert any(
        line.endswith("Nascent Soul, Soul Transformation and beyond.")
        for line in world_lines(_cultivation(long))
    )

    # A ladder drafted before the world said which rungs everyone knows names its first ones.
    old = _cultivation()
    old.bible.ladders[0].known_to_all = 0
    assert any(line.endswith("Nascent Soul, Soul Transformation.") for line in world_lines(old))


def test_everything_the_draft_shows_reads_as_one_text():
    # What the player read before starting, the character knows (`engine.path`).
    state = _cultivation()

    text = shown(state)

    for line in world_lines(state) + character_lines(state):
        assert line in text
    assert all(rule.text in text for rule in public_rules(state))
    assert state.bible.title in text and state.bible.genre in text
    for hidden in hidden_texts(state):
        assert hidden not in text


def test_the_character_reads_in_the_worlds_words():
    lines = character_lines(_cultivation())

    assert 3 <= len(lines) <= CHARACTER_LINES
    assert lines[0] == "Lin Feng, 16."
    assert "Qi Condensation, early stage." in lines
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
    assert "Qi Condensation, etapa inicial." in character
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
    assert "Qi Condensation, etapa inicial." in character
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


def _with_talents():
    character = samples.cultivation_character().model_copy(
        update={
            "talents": [
                TalentP(name="Hopeless at haggling", strength="slow"),
                TalentP(name="Architecture", covers="Structure and geometry.", strength="genius"),
                TalentP(
                    name="Extreme perception",
                    covers="any move he can watch someone do",
                    strength="one_of_a_kind",
                ),
                TalentP(name="The sword", strength="one_of_a_kind"),
                TalentP(name="Quick hands", covers="sleight and knots", strength="knack"),
            ]
        }
    )
    return _cultivation(character=character)


def test_the_summary_says_what_each_talent_covers_so_the_player_can_check_it():
    # A4, G2: strongest first, each with what it covers, in words the player can change.
    lines = character_lines(_with_talents())

    assert (
        "One of a kind: Extreme perception (any move he can watch someone do); The sword."
        " Genius: Architecture (Structure and geometry). A knack: Quick hands (sleight and"
        " knots). Weakness: Hopeless at haggling." in lines
    )
    assert len(lines) <= CHARACTER_LINES


def test_the_talent_line_comes_in_spanish_and_catalan():
    state = _with_talents()

    assert (
        "Talento único: Extreme perception (any move he can watch someone do); The sword."
        " Genio: Architecture (Structure and geometry). Facilidad: Quick hands (sleight and"
        " knots). Punto débil: Hopeless at haggling." in character_lines(state, Language.ES)
    )
    assert (
        "Talent únic: Extreme perception (any move he can watch someone do); The sword."
        " Geni: Architecture (Structure and geometry). Facilitat: Quick hands (sleight and"
        " knots). Punt feble: Hopeless at haggling." in character_lines(state, Language.CA)
    )


def test_a_character_with_no_talents_has_no_talent_line():
    lines = character_lines(_cultivation())

    assert not any(
        line.startswith(("One of a kind", "Genius:", "A knack", "Weakness")) for line in lines
    )


# The summary part by part (G1, G2): what the app labels, groups and points a change at.


def test_every_line_of_the_summary_is_a_part_with_its_kind():
    state = _naples()
    world = world_parts(state)
    character = character_parts(state)

    assert [part.text for part in world][:WORLD_LINES] == world_lines(state)
    assert [part.text for part in character][:CHARACTER_LINES] == character_lines(state)
    kinds = [part.kind for part in world]
    assert kinds[:2] == [PartKind.RULE, PartKind.ERA]
    assert {PartKind.FACTION, PartKind.DEADLINE, PartKind.QUESTION} <= set(kinds)
    assert character[0].kind is PartKind.WHO
    assert {PartKind.MANNER, PartKind.SKILLS, PartKind.POWER, PartKind.GOAL} <= {
        part.kind for part in character
    }
    by_kind = {part.kind: part.text for part in character}
    assert by_kind[PartKind.POWER] == "No powers, since this world has none."


def test_the_parts_keep_how_the_story_starts_a_surprise():
    # G1: the parts are the lines, so what the player's words don't name is in neither. The
    # premise asks who killed the father, and names no deadline and nobody.
    state = _naples()
    said = Said(samples.NAPLES_PREMISE)
    kinds = {part.kind for part in world_parts(state, Language.EN, said)}

    assert PartKind.QUESTION in kinds
    assert not {PartKind.DEADLINE, PartKind.PERSON} & kinds
    told = Said(samples.NAPLES_PREMISE, frozenset({"clock:council"}))
    shown_now = world_parts(state, Language.EN, told)
    assert [part.text for part in shown_now if part.kind is PartKind.DEADLINE] == [
        "The council picks the next boss: in 10 days."
    ]


def test_the_story_counts_what_it_keeps_and_tells_none_of_it():
    state = _naples()
    people, clocks = len(list(state.npcs())), len(state.clocks)
    questions = len(state.bible.mysteries)
    assert people and clocks and questions

    # The premise asks who killed the father, so that question is shown, not kept.
    by_premise = kept(state, Language.EN, Said(samples.NAPLES_PREMISE))
    assert by_premise == {"people": people, "events": clocks, "questions": questions - 1}
    # What a change of theirs names is shown from then on, so it is no longer kept either.
    one_more = kept(state, Language.EN, Said(samples.NAPLES_PREMISE, frozenset({"clock:council"})))
    assert one_more == {"people": people, "events": clocks - 1, "questions": questions - 1}
    assert kept(state, Language.EN, Said("A story.")) == {
        "people": people,
        "events": clocks,
        "questions": questions,
    }
    # Read with no say of the player's, the summary keeps nothing back.
    assert kept(state) == {"people": 0, "events": 0, "questions": 0}


def test_the_characters_plain_fields_are_given_as_values():
    who = identity(_naples())

    assert who == {
        "name": "Luca Esposito",
        "age": 24,
        "people": "",
        "standing": who["standing"],
        "looks": "24, lean, dark hair combed back, a scar through one eyebrow.",
        "manner": who["manner"],
    }
    assert who["manner"] and who["manner"] == _naples().player.description
    cultivation = identity(_cultivation())
    assert cultivation["name"] == "Lin Feng"
    assert "outer disciple" in cultivation["standing"].casefold()


def test_the_ladder_is_given_rung_by_rung_with_the_characters_place():
    state = _cultivation()
    ladder = ladder_view(state)
    position = state.player.sheet.ladders[0]

    assert ladder["name"] == "Cultivation realms"
    assert ladder["rungs"][0] == "Qi Condensation"
    assert len(ladder["rungs"]) <= 5
    assert ladder["more"] is (len(state.bible.ladders[0].rungs) > len(ladder["rungs"]))
    assert ladder["at"] == position.rung
    # A world with no ladder has none to show.
    assert ladder_view(_naples()) is None


def test_a_place_above_the_rungs_everyone_knows_is_not_marked_on_them():
    world = samples.cultivation_world()
    ladder = world.ladders[0].model_copy(update={"known_to_all": 2})
    world = world.model_copy(update={"ladders": [ladder]})
    character = samples.cultivation_character()
    top = ladder.rungs[2].name
    position = character.ladders[0].model_copy(update={"rung": top})
    character = character.model_copy(update={"ladders": [position]})

    seen = ladder_view(_cultivation(world, character))

    assert seen["rungs"] == [rung.name for rung in ladder.rungs[:2]]
    assert seen["more"] is True
    assert (seen["at"], seen["stage"]) == (None, "")
