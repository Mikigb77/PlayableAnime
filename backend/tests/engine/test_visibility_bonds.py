"""W17, C6: Memory shows a romance as the player character knows it."""

import json

import pytest

from engine import visibility
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY
from engine.context import Language, TurnContext
from engine.contracts import BondChange, CharacterChange, StateDelta
from engine.samples import farm_world
from engine.state import (
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Character,
    CharacterStatus,
    DeathCertainty,
    WorldState,
)
from engine.visibility import memory_view

EN, ES, CA = Language.EN, Language.ES, Language.CA
INTEREST, COURTING, TOGETHER, PROMISED, MARRIED, OVER = BondStage


def farm() -> WorldState:
    """Tomas, his wife Ilse, and Mara, a neighbour he knows."""
    state = farm_world()
    state.characters["mara"] = Character(
        id="mara",
        name="Mara Voss",
        age=29,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
    )
    return state


def engine(state: WorldState, day: int = 1, **delta) -> WorldState:
    """The state after the engine's delta, applied on a day of the story."""
    state = state.model_copy(deep=True)
    state.world_s = (day - 1) * DAY
    applied = apply_delta(
        state, StateDelta(**delta), TurnContext(story_id="s1", turn=day), source=DeltaSource.ENGINE
    )
    assert not applied.rejected, applied.rejected
    return applied.state


def moved(state: WorldState, stage: BondStage, day: int, *, by: str = "tomas", other="mara"):
    change = BondChange(a_id=by, b_id=other if by == "tomas" else "tomas", stage=stage, by_id=by)
    return engine(state, day, bonds=[change])


def told(state: WorldState, who: str, language: Language = EN) -> tuple:
    """A person's romance on the Memory screen: its stage, and the line that tells it."""
    person = next(p for p in memory_view(state, language).people if p.id == who)
    return person.bond, person.bond_line


def test_someone_with_no_romance_shows_none():
    state = farm()
    assert told(state, "mara") == (None, None)
    assert told(state, "bram") == (None, None)


def test_a_marriage_from_before_the_story_is_told_as_it_stands_with_no_day():
    state = farm_world()
    assert told(state, "ilse") == (MARRIED, "You are married.")
    assert told(state, "ilse", ES) == (MARRIED, "Sois un matrimonio.")
    assert told(state, "ilse", CA) == (MARRIED, "Sou un matrimoni.")
    # It is a line of its own, beside who they are.
    ilse = memory_view(state).people[0]
    assert ilse.lines == ["Tomas's wife, quick-witted and quicker to laugh."]


STAGES = [
    (
        INTEREST,
        "You made your interest plain, day 3.",
        "Le dejaste claro tu interés, día 3.",
        "Li vas deixar clar el teu interès, dia 3.",
    ),
    (
        COURTING,
        "You began courting, day 3.",
        "Empezó algo entre Mara Voss y tú, día 3.",
        "Va començar alguna cosa entre Mara Voss i tu, dia 3.",
    ),
    (
        TOGETHER,
        "You became a couple, day 3.",
        "Os hicisteis pareja, día 3.",
        "Us vau fer parella, dia 3.",
    ),
    (
        PROMISED,
        "You promised yourselves to each other, day 3.",
        "Os prometisteis, día 3.",
        "Us vau prometre, dia 3.",
    ),
    (MARRIED, "You married, day 3.", "Os casasteis, día 3.", "Us vau casar, dia 3."),
]


def at(stage: BondStage, *, day: int = 3, by: str | None = "tomas") -> WorldState:
    """The farm with Tomas and Mara at a stage they came to on a day, with what came before
    a day earlier."""
    state = farm()
    before = {COURTING: INTEREST, TOGETHER: COURTING, PROMISED: TOGETHER, MARRIED: PROMISED}
    steps = [BondStep(stage=stage, turn=day, world_s=(day - 1) * DAY, by_id=by)]
    if stage in before:
        earlier = BondStep(stage=before[stage], turn=1, world_s=(day - 2) * DAY, by_id="tomas")
        steps.insert(0, earlier)
    state.bonds["bond-9"] = Bond(id="bond-9", a_id="tomas", b_id="mara", stage=stage, steps=steps)
    state.world_s = day * DAY
    return state


@pytest.mark.parametrize(("stage", "en", "es", "ca"), STAGES)
def test_each_stage_tells_how_it_came_there_with_its_day(stage, en, es, ca):
    state = at(stage)
    assert told(state, "mara", EN) == (stage, en)
    assert told(state, "mara", ES) == (stage, es)
    assert told(state, "mara", CA) == (stage, ca)


@pytest.mark.parametrize(
    ("stage", "en", "es", "ca"),
    [
        (
            INTEREST,
            "You have made your interest plain.",
            "Le has dejado claro tu interés.",
            "Li has deixat clar el teu interès.",
        ),
        (
            COURTING,
            "You are courting.",
            "Hay algo entre Mara Voss y tú.",
            "Hi ha alguna cosa entre Mara Voss i tu.",
        ),
        (TOGETHER, "You are a couple.", "Sois pareja.", "Sou parella."),
        (
            PROMISED,
            "You are promised to each other.",
            "Os habéis prometido.",
            "Us heu promès.",
        ),
    ],
)
def test_a_romance_the_premise_set_up_is_told_as_it_stands(stage, en, es, ca):
    state = farm()
    opening = BondStep(stage=stage, how="As the story opens.")
    state.bonds["bond-9"] = Bond(
        id="bond-9", a_id="tomas", b_id="mara", stage=stage, steps=[opening]
    )
    assert [told(state, "mara", language) for language in (EN, ES, CA)] == [
        (stage, en),
        (stage, es),
        (stage, ca),
    ]


def test_an_interest_someone_else_made_plain_names_them():
    state = moved(farm(), INTEREST, 3, by="mara")
    assert told(state, "mara") == (INTEREST, "Mara Voss made their interest in you plain, day 3.")
    assert told(state, "mara", ES)[1] == "Mara Voss te dejó claro su interés, día 3."
    assert told(state, "mara", CA)[1] == "Mara Voss et va deixar clar el seu interès, dia 3."
    # Once it is answered it is the two's, whoever began it.
    courting = moved(state, COURTING, 5, by="tomas")
    assert told(courting, "mara") == (COURTING, "You began courting, day 5.")

    opened = farm()
    opened.bonds["bond-9"] = Bond(
        id="bond-9", a_id="mara", b_id="tomas", steps=[BondStep(stage=INTEREST)]
    )
    assert told(opened, "mara")[1] == "Mara Voss has made their interest in you plain."
    assert told(opened, "mara", ES)[1] == "Mara Voss te ha dejado claro su interés."
    assert told(opened, "mara", CA)[1] == "Mara Voss t'ha deixat clar el seu interès."


def test_an_ending_tells_what_it_had_come_to_and_whose_doing_it_was():
    left = moved(farm_world(), OVER, 5, by="tomas", other="ilse")
    assert told(left, "ilse") == (OVER, "You were married until you ended it, day 5.")
    assert told(left, "ilse", ES) == (OVER, "Fuisteis un matrimonio hasta que lo dejaste, día 5.")
    assert told(left, "ilse", CA) == (OVER, "Vau ser un matrimoni fins que ho vas deixar, dia 5.")

    # Ended with nobody on record as the one who did it: it only says that it ended.
    ended = farm_world()
    ended.bonds["bond-1"].steps.append(BondStep(stage=OVER, turn=5, world_s=4 * DAY))
    ended.bonds["bond-1"].stage, ended.bonds["bond-1"].end = OVER, BondEnd.PARTED
    assert [told(ended, "ilse", language)[1] for language in (EN, ES, CA)] == [
        "You were married until it ended, day 5.",
        "Fuisteis un matrimonio hasta que se acabó, día 5.",
        "Vau ser un matrimoni fins que es va acabar, dia 5.",
    ]

    was_left = moved(farm_world(), OVER, 5, by="ilse")
    assert told(was_left, "ilse")[1] == "You were married until they ended it, day 5."
    assert told(was_left, "ilse", ES)[1] == "Fuisteis un matrimonio hasta que te dejó, día 5."
    assert told(was_left, "ilse", CA)[1] == "Vau ser un matrimoni fins que et va deixar, dia 5."


@pytest.mark.parametrize(
    ("stage", "en", "es", "ca"),
    [
        (
            COURTING,
            "You were courting until you ended it, day 6.",
            "Hubo algo entre Mara Voss y tú hasta que lo dejaste, día 6.",
            "Hi va haver alguna cosa entre Mara Voss i tu fins que ho vas deixar, dia 6.",
        ),
        (
            TOGETHER,
            "You were a couple until you ended it, day 6.",
            "Fuisteis pareja hasta que lo dejaste, día 6.",
            "Vau ser parella fins que ho vas deixar, dia 6.",
        ),
        (
            PROMISED,
            "You were promised to each other until you ended it, day 6.",
            "Tuvisteis un compromiso hasta que lo dejaste, día 6.",
            "Vau tenir un compromís fins que ho vas deixar, dia 6.",
        ),
    ],
)
def test_an_ending_names_the_stage_it_ended_at(stage, en, es, ca):
    over = moved(at(stage), OVER, 6)
    assert [told(over, "mara", language) for language in (EN, ES, CA)] == [
        (OVER, en),
        (OVER, es),
        (OVER, ca),
    ]


def test_an_interest_that_ended_before_anything_began_is_nothing_to_remember():
    over = moved(moved(farm(), INTEREST, 3), OVER, 4)
    assert over.bonds["bond-2"].stage is OVER
    assert told(over, "mara") == (None, None)


def test_a_romance_that_began_again_shows_the_one_that_stands():
    again = moved(moved(at(TOGETHER), OVER, 6), INTEREST, 9)
    assert told(again, "mara") == (INTEREST, "You made your interest plain, day 9.")


def dies(state: WorldState, *, known: bool, presumed: bool = False) -> WorldState:
    change = CharacterChange(
        id="ilse",
        status=CharacterStatus.DEAD,
        death_certainty=DeathCertainty.PRESUMED if presumed else None,
        known_to_player=known,
    )
    return engine(state, 8, characters=[change])


def test_a_death_they_know_of_ended_it_and_one_they_dont_know_of_ended_nothing():
    """C6: the record ends a romance when one of the two dies, and Memory says so only once
    the character knows of the death."""
    away = farm_world()
    away.scene.present_ids = ["tomas"]  # she dies where he isn't
    unknown = dies(away, known=False)
    assert unknown.bonds["bond-1"].stage is OVER
    assert told(unknown, "ilse") == (MARRIED, "You are married.")

    known = dies(farm_world(), known=True)
    assert told(known, "ilse") == (OVER, "You were married until their death.")
    assert told(known, "ilse", ES)[1] == "Fuisteis un matrimonio hasta su muerte."
    assert told(known, "ilse", CA)[1] == "Vau ser un matrimoni fins a la seva mort."

    # A death that is only presumed ends nothing on record, so nothing in Memory either.
    presumed = dies(farm_world(), known=True, presumed=True)
    assert told(presumed, "ilse") == (MARRIED, "You are married.")


def test_how_drawn_they_are_never_shows():
    state = at(COURTING)
    state.characters["mara"].attitude_toward("tomas").attraction = 87
    said = json.dumps(memory_view(state).model_dump(mode="json"))
    assert "attraction" not in said and "87" not in said


def test_two_others_romance_is_not_the_characters_to_see():
    state = farm()
    state.bonds["bond-9"] = Bond(
        id="bond-9", a_id="bram", b_id="mara", stage=TOGETHER, steps=[BondStep(stage=TOGETHER)]
    )
    assert told(state, "mara") == (None, None)
    assert told(state, "bram") == (None, None)


def test_every_language_has_every_word():
    english = visibility._BOND_WORDS[EN]
    for language in (ES, CA):
        words = visibility._BOND_WORDS[language]
        assert set(words) == set(english), language
        for key, value in english.items():
            if isinstance(value, dict):
                assert set(words[key]) == set(value), (language, key)
            else:
                assert words[key] != value, (language, key)
    assert set(english["came"]) == set(english["is"]) == set(BondStage) - {OVER}
    assert set(english["was"]) == set(BondStage) - {OVER, INTEREST}
