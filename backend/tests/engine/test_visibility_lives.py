"""W6, C6: Memory shows what the player character has heard of other people's lives."""

import json

import pytest

from engine import pipeline, visibility
from engine.base import DAY, YEAR
from engine.context import Language
from engine.samples import farm_world
from engine.state import Character, LifeEvent, LifeKind, Origin, OriginKind, WorldState
from engine.visibility import memory_view

EN, ES, CA = Language.EN, Language.ES, Language.CA
PAIRED, MARRIED, PARTED, CHILD, FRIENDS, FELL_OUT, DIED = LifeKind


def known(cid: str, name: str, **more) -> Character:
    """Someone Tomas knows, and was last with as the story began."""
    return Character(id=cid, name=name, known_by=["tomas"], met_by=["tomas"], seen_s=0, **more)


def years_on() -> WorldState:
    """Tomas's farm ten years on. Mara, a neighbour, found Edrik, married him and had a child
    with him, made a friend of Old Bram and fell out with him, and then she and Edrik parted.
    Tomas lived there through all of it, so he knows."""
    state = farm_world()
    state.world_s = 10 * YEAR
    state.characters["mara"] = known("mara", "Mara Voss", age=39, location_id="farm")
    state.characters["edrik"] = known("edrik", "Edrik", age=41, location_id="farm")
    state.characters["lena"] = known("lena", "Lena", age=4, parent_ids=["mara", "edrik"])
    with_edrik = [(PAIRED, 2, None), (MARRIED, 4, None), (CHILD, 6, "lena"), (PARTED, 9, None)]
    with_bram = [(FRIENDS, 7, None), (FELL_OUT, 8, None)]
    events = [(*e, "edrik") for e in with_edrik] + [(*e, "bram") for e in with_bram]
    for n, (kind, year, child, other) in enumerate(events, start=1):
        state.lives[f"life-{n}"] = LifeEvent(
            id=f"life-{n}",
            kind=kind,
            subject_ids=["mara", other],
            child_id=child,
            world_s=year * YEAR + 3 * DAY,
            known_by=["mara", other, "tomas"],
        )
    return state


def lines(state: WorldState, who: str, language: Language = EN) -> list[str]:
    return next(p for p in memory_view(state, language).people if p.id == who).lines


@pytest.mark.parametrize(
    ("language", "told"),
    [
        (
            EN,
            [
                "Found a partner: Edrik, day 734.",
                "Married Edrik, day 1464.",
                "Had a child: Lena, day 2194.",
                "Became close friends with Old Bram, day 2559.",
                "Fell out with Old Bram, day 2924.",
                "Parted from Edrik, day 3289.",
            ],
        ),
        (
            ES,
            [
                "Encontró pareja: Edrik, día 734.",
                "Se casó con Edrik, día 1464.",
                "Tuvo una criatura: Lena, día 2194.",
                "Trabó una gran amistad con Old Bram, día 2559.",
                "Se enemistó con Old Bram, día 2924.",
                "Rompió con Edrik, día 3289.",
            ],
        ),
        (
            CA,
            [
                "Va trobar parella: Edrik, dia 734.",
                "Es va casar amb Edrik, dia 1464.",
                "Va tenir una criatura: Lena, dia 2194.",
                "Va fer una gran amistat amb Old Bram, dia 2559.",
                "Es va enemistar amb Old Bram, dia 2924.",
                "Va trencar amb Edrik, dia 3289.",
            ],
        ),
    ],
    ids=["en", "es", "ca"],
)
def test_a_persons_entry_tells_what_came_to_them_with_its_day(language, told):
    """The lines come after what the entry already says of them, oldest first, in the story's
    language (S10), and each of the two it came to has it in their own entry."""
    state = years_on()

    assert lines(state, "mara", language) == told
    assert lines(state, "edrik", language)[0] == told[0].replace("Edrik", "Mara Voss")
    assert lines(state, "bram", language)[1:] == [
        line.replace("Old Bram", "Mara Voss") for line in told[3:5]
    ]


def test_what_nobody_told_the_player_character_stays_out():
    """C6: news of someone travels to the player character when they live near, or when a
    scene tells it. Until then Memory holds nothing of it, and nothing of when it happened."""
    state = years_on()
    for event in state.lives.values():
        event.known_by.remove("tomas")

    assert lines(state, "mara") == []
    assert "day 734" not in json.dumps(memory_view(state).model_dump(mode="json"))

    # A scene the two share that tells none of it leaves Memory as it was.
    state.scene.present_ids = ["tomas", "mara"]
    silent, heard = pipeline.settle_lives(state)
    assert heard == [] and lines(silent, "mara") == []

    # What a scene told is heard (`pipeline.settle_lives`), piece by piece.
    some, heard = pipeline.settle_lives(silent, ["life-2", "life-3"])
    assert heard == ["life-2", "life-3"]
    assert lines(some, "mara") == ["Married Edrik, day 1464.", "Had a child: Lena, day 2194."]
    met, heard = pipeline.settle_lives(some, list(state.lives))
    assert len(heard) == 4 and len(lines(met, "mara")) == 6
    assert lines(met, "bram") == lines(years_on(), "bram")  # what he heard was about Bram too


def test_someone_the_player_character_doesnt_know_by_name_is_left_unnamed():
    """A partner the world brought goes by "Mara Voss's partner" until the story names them,
    and a child by "Mara Voss's child": Memory doesn't print the engine's placeholder as a
    name, nor the name of someone the player character has never heard of."""
    state = years_on()
    state.characters["edrik"].name = "Mara Voss's partner"
    state.characters["edrik"].origin = Origin(kind=OriginKind.ENGINE, ref_id="mara", text="-")
    state.characters["lena"].name = "Mara Voss's child"
    state.characters["lena"].origin = Origin(kind=OriginKind.BIRTH, ref_id="bond-2", text="-")
    state.characters["bram"].known_by = []

    assert lines(state, "mara") == [
        "Found a partner, day 734.",
        "Married, day 1464.",
        "Had a child, day 2194.",
        "Made a close friend, day 2559.",
        "Fell out with someone close to them, day 2924.",
        "Parted from their partner, day 3289.",
    ]
    assert lines(state, "mara", ES) == [
        "Encontró pareja, día 734.",
        "Se casó, día 1464.",
        "Tuvo una criatura, día 2194.",
        "Trabó una gran amistad, día 2559.",
        "Se enemistó con alguien de su entorno, día 2924.",
        "Rompió con su pareja, día 3289.",
    ]
    assert lines(state, "mara", CA) == [
        "Va trobar parella, dia 734.",
        "Es va casar, dia 1464.",
        "Va tenir una criatura, dia 2194.",
        "Va fer una gran amistat, dia 2559.",
        "Es va enemistar amb algú del seu entorn, dia 2924.",
        "Va trencar amb la seva parella, dia 3289.",
    ]


def test_an_entry_keeps_to_the_latest_of_a_long_life():
    state = years_on()
    for n in range(7, 12):
        state.lives[f"life-{n}"] = LifeEvent(
            id=f"life-{n}",
            kind=FRIENDS,
            subject_ids=["mara", "ilse"],
            world_s=9 * YEAR + n * DAY,
            known_by=["mara", "ilse", "tomas"],
        )

    told = lines(state, "mara")

    assert len(told) == visibility._LIFE_LINES
    assert told[0] == "Parted from Edrik, day 3289."
    assert told[-1] == "Became close friends with Ilse Weller, day 3297."


def test_another_timeline_keeps_its_own_lives():
    state = years_on()
    for event in state.lives.values():
        event.timeline_id = "elsewhere"

    assert lines(state, "mara") == []


@pytest.mark.parametrize(
    ("language", "died", "lost"),
    [
        (EN, "Died of old age, day 3654.", "Lost their partner: Edrik, day 3654."),
        (ES, "Murió de vejez, día 3654.", "Perdió a su pareja: Edrik, día 3654."),
        (CA, "Va morir de vellesa, dia 3654.", "Va perdre la seva parella: Edrik, dia 3654."),
    ],
    ids=["en", "es", "ca"],
)
def test_a_death_of_old_age_is_told_under_the_dead_and_under_the_partner_they_left(
    language, died, lost
):
    """The one who died has that they died, and the partner they left that they lost them:
    one piece of news, told of each as it came to them."""
    state = years_on()
    state.lives["life-9"] = LifeEvent(
        id="life-9",
        kind=DIED,
        subject_ids=["edrik", "mara"],
        world_s=10 * YEAR + 3 * DAY,
        known_by=["edrik", "mara", "tomas"],
    )

    assert lines(state, "edrik", language)[-1] == died
    assert lines(state, "mara", language)[-1] == lost

    # Someone who left nobody: the one line, under them.
    state.lives["life-9"].subject_ids = ["edrik"]
    assert lines(state, "edrik", language)[-1] == died
    assert lost not in lines(state, "mara", language)

    # A partner the player character doesn't know by name is left unnamed.
    state.lives["life-9"].subject_ids = ["edrik", "mara"]
    state.characters["edrik"].known_by = []
    assert lines(state, "mara", language)[-1] == lost.replace(": Edrik", "")


def test_every_language_has_every_line_and_none_is_left_in_english():
    english = visibility._LIFE_WORDS[EN]
    assert set(english) == set(LifeKind)
    for language in (ES, CA):
        words = visibility._LIFE_WORDS[language]
        assert set(words) == set(LifeKind), language
        for kind, (named, bare) in words.items():
            assert named.count("{who}") == 1 and "{" not in bare, (language, kind)
            assert named != english[kind][0] and bare != english[kind][1], (language, kind)
    for named, bare in english.values():
        assert named.count("{who}") == 1 and "{" not in bare
    died = visibility._OLD_AGE_WORDS
    assert set(died) == {EN, ES, CA} and len(set(died.values())) == 3
