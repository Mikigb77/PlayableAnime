"""Talent (A4): how fast a character learns each thing, read from their sheet.

Agreed with Miki on 2026-11-10: talent is a list on the sheet, written from the player's own
words, on one scale where every step doubles the pace. Whether a talent covers a thing is ruled
once (inside, related or outside), a bridge built in the story lifts a thing toward a talent, and
the paces of the talents that reach one thing add.
"""

import pytest

from engine import talent
from engine.contracts import GrowthKind, Training
from engine.samples import cultivation_world
from engine.state import (
    Character,
    Talent,
    TalentBridge,
    TalentCover,
    TalentFit,
    TalentRuling,
    TalentStrength,
    Trait,
    TraitKind,
)

BLADE = "technique:aura-blade"
SLOW, KNACK, GENIUS, UNIQUE = (
    TalentStrength.SLOW,
    TalentStrength.KNACK,
    TalentStrength.GENIUS,
    TalentStrength.ONE_OF_A_KIND,
)


def gift(talent_id: str, strength: TalentStrength = GENIUS, **kw) -> Talent:
    return Talent(id=talent_id, name=talent_id.capitalize(), strength=strength, **kw)


def lin(*talents: Talent) -> Character:
    character = cultivation_world().player
    character.sheet.talents = list(talents)
    return character


def ruled(character: Character, key: str = BLADE, **fits: TalentFit) -> Character:
    covers = [TalentCover(talent_id=i, fit=fit) for i, fit in fits.items()]
    character.sheet.talent_rulings.append(TalentRuling(key=key, what="Aura blade", covers=covers))
    return character


def bridged(character: Character, talent_id: str, steps: int = 1, key: str = BLADE) -> Character:
    bridge = TalentBridge(key=key, talent_id=talent_id, rests_on=f"ground {steps}", steps=steps)
    character.sheet.bridges.append(bridge)
    return character


# --- the scale -------------------------------------------------------------------------------


def reaching(stands: talent.Standing) -> list[tuple[str, TalentFit]]:
    return [(reach.talent.id, reach.fit) for reach in stands.reaches]


def test_every_step_of_talent_doubles_the_pace():
    paces = [
        talent.standing(ruled(lin(gift("sword", strength)), sword=TalentFit.INSIDE), BLADE).pace
        for strength in (SLOW, KNACK, GENIUS, UNIQUE)
    ]

    assert paces == [0.5, 2, 4, 8]
    assert talent.standing(lin(), BLADE).pace == 1
    assert [s.steps for s in (SLOW, KNACK, GENIUS, UNIQUE)] == [-1, 1, 2, 3]


def test_a_pace_is_said_in_words_up_to_ten():
    said = [talent.pace_words(pace) for pace in (0.5, 1, 2, 3, 4, 8, 10, 12, 16)]

    assert said == [
        "at half the pace",
        "at the ordinary pace",
        "twice as fast",
        "three times as fast",
        "four times as fast",
        "eight times as fast",
        "ten times as fast",
        "12 times as fast",
        "16 times as fast",
    ]


def test_a_name_is_one_key_in_any_language():
    assert talent.technique_key("Aura Blade") == talent.technique_key("aura-blade") == BLADE
    assert talent.technique_key("Puño de Fuego") == "technique:puno-de-fuego"
    assert talent.skill_key("Swordplay") == "skill:swordplay"


def test_what_a_training_step_learns_is_the_thing_they_use_later():
    """A new way to use a power goes on the sheet as a technique, so it is one from the start."""
    technique = Training(kind=GrowthKind.TECHNIQUE, what="Aura blade")
    power = Training(kind=GrowthKind.POWER, what="Aura blade", power_id="aura")
    rung = Training(kind=GrowthKind.BREAKTHROUGH, what="the next realm", ladder_id="realms")

    assert talent.training_key(technique) == talent.training_key(power) == BLADE
    assert talent.training_key(Training(kind=GrowthKind.SKILL, what="Herb lore")) == (
        "skill:herb-lore"
    )
    assert talent.training_key(rung) == "ladder:realms"


# --- how the sheet's talents read ------------------------------------------------------------


def test_one_of_a_kind_at_everything_reads_as_a_general_genius():
    everything = gift("everything", UNIQUE, general=True)

    (read,) = talent.talents_of(lin(everything))

    assert (read.strength, read.general) == (GENIUS, True)


def test_a_character_holds_three_one_of_a_kind_talents_and_a_fourth_reads_as_genius():
    four = [gift(name, UNIQUE) for name in ("sword", "sight", "body", "fire")]

    read = talent.talents_of(lin(*four))

    assert [t.strength for t in read] == [UNIQUE, UNIQUE, UNIQUE, GENIUS]


def test_a_sheet_with_no_talents_reads_its_traits_words_as_before():
    """A story saved before talent was a record keeps its genius: one general talent."""
    character = lin()
    character.sheet.traits = [
        Trait(name="Prodigio", kind=TraitKind.GIFT),
        Trait(name="Slow learner", kind=TraitKind.FLAW),
    ]

    genius, slow = talent.talents_of(character)

    assert (genius.strength, genius.general) == (GENIUS, True)
    assert (slow.strength, slow.general) == (SLOW, True)
    assert talent.standing(character, BLADE).steps == 1  # four times as fast, less a step


def test_recorded_talents_replace_the_reading_of_traits():
    character = lin(gift("sword", KNACK))
    character.sheet.traits = [Trait(name="Genius", kind=TraitKind.GIFT)]

    assert [t.id for t in talent.talents_of(character)] == ["sword"]
    assert not talent.copies_on_sight(character)


def test_an_old_copycat_still_takes_a_move_on_sight():
    character = lin()
    character.sheet.traits = [Trait(name="Copycat eye", kind=TraitKind.GIFT)]

    assert talent.copies_on_sight(character)


# --- the ruling ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fit", "steps"),
    [(TalentFit.INSIDE, 3), (TalentFit.RELATED, 2), (TalentFit.OUTSIDE, 0)],
)
def test_inside_is_the_talents_pace_related_one_step_under_and_outside_ordinary(fit, steps):
    character = ruled(lin(gift("sword", UNIQUE)), sword=fit)

    assert talent.standing(character, BLADE).steps == steps


def test_a_thing_never_ruled_on_grows_at_the_ordinary_pace():
    character = lin(gift("sword", UNIQUE))

    stands = talent.standing(character, BLADE)

    assert (stands.pace, stands.reaches, stands.words) == (1, (), "at the ordinary pace")
    assert talent.unruled(character, BLADE)


def test_a_talent_the_ruling_doesnt_list_is_outside():
    character = ruled(lin(gift("sword", UNIQUE), gift("architect")), architect=TalentFit.INSIDE)

    stands = talent.standing(character, BLADE)

    assert (stands.pace, reaching(stands)) == (4, [("architect", TalentFit.INSIDE)])
    assert not talent.unruled(character, BLADE)


def test_a_general_talent_covers_everything_with_no_ruling():
    character = lin(gift("prodigy", GENIUS, general=True))

    stands = talent.standing(character, "skill:anything-at-all")

    assert (stands.pace, reaching(stands)) == (4, [("prodigy", TalentFit.INSIDE)])
    assert not talent.unruled(character, BLADE)  # nothing to rule on


def test_a_knack_that_is_only_related_gives_nothing():
    character = ruled(lin(gift("sword", KNACK)), sword=TalentFit.RELATED)

    assert talent.standing(character, BLADE).steps == 0


# --- several talents on one thing ------------------------------------------------------------


def test_two_one_of_a_kind_talents_that_both_cover_a_thing_learn_it_sixteen_times_as_fast():
    """Miki's case: two talents behind one technique learn it faster than either alone."""
    character = ruled(
        lin(gift("sword", UNIQUE), gift("aura", UNIQUE)),
        sword=TalentFit.INSIDE,
        aura=TalentFit.INSIDE,
    )

    stands = talent.standing(character, BLADE)

    assert (stands.pace, stands.words) == (16, "16 times as fast")
    assert reaching(stands) == [("sword", TalentFit.INSIDE), ("aura", TalentFit.INSIDE)]


@pytest.mark.parametrize(
    ("second", "fit", "pace"),
    [
        (GENIUS, TalentFit.INSIDE, 12),
        (GENIUS, TalentFit.RELATED, 10),
        (KNACK, TalentFit.INSIDE, 10),
        (KNACK, TalentFit.RELATED, 8),  # a knack that is only related gives nothing
        (GENIUS, TalentFit.OUTSIDE, 8),
    ],
)
def test_each_talent_that_reaches_a_thing_adds_the_pace_it_gives(second, fit, pace):
    character = ruled(
        lin(gift("sword", UNIQUE), gift("architect", second)),
        sword=TalentFit.INSIDE,
        architect=fit,
    )

    assert talent.standing(character, BLADE).pace == pace


def test_talents_add_and_never_multiply():
    three = [gift(name, UNIQUE) for name in ("sword", "aura", "sight")]
    character = ruled(lin(*three), **{t.id: TalentFit.INSIDE for t in three})

    assert talent.standing(character, BLADE).pace == 24


def test_two_talents_together_can_reach_a_stronger_talents_pace():
    """What a pace unlocks is read from the pace, however it adds up."""
    character = ruled(
        lin(gift("sword"), gift("aura")), sword=TalentFit.INSIDE, aura=TalentFit.INSIDE
    )

    stands = talent.standing(character, BLADE)

    assert (stands.pace, stands.steps) == (8, talent.ONE_OF_A_KIND_STEPS)


def test_the_strongest_reach_is_named_first():
    character = ruled(
        lin(gift("architect"), gift("sword", UNIQUE)),
        architect=TalentFit.INSIDE,
        sword=TalentFit.RELATED,
    )

    assert reaching(talent.standing(character, BLADE)) == [
        ("architect", TalentFit.INSIDE),
        ("sword", TalentFit.RELATED),
    ]
    character.sheet.talent_rulings[0].covers[1].fit = TalentFit.INSIDE
    assert [who for who, _ in reaching(talent.standing(character, BLADE))] == ["sword", "architect"]


def test_of_the_talents_that_cover_everything_only_the_strongest_counts():
    """Said twice about everything, a gift is still one gift."""
    twice = lin(gift("prodigy", GENIUS, general=True), gift("quick", KNACK, general=True))
    beside = ruled(
        lin(gift("prodigy", GENIUS, general=True), gift("sword", UNIQUE)),
        sword=TalentFit.INSIDE,
    )

    assert (talent.standing(twice, BLADE).pace, reaching(talent.standing(twice, BLADE))) == (
        4,
        [("prodigy", TalentFit.INSIDE)],
    )
    assert talent.standing(beside, BLADE).pace == 12  # a talent for one thing adds to it


def test_a_weakness_that_covers_the_thing_halves_what_the_others_give():
    alone = ruled(lin(gift("clumsy", SLOW)), clumsy=TalentFit.INSIDE)
    beside = ruled(
        lin(gift("sword", UNIQUE), gift("clumsy", SLOW)),
        sword=TalentFit.INSIDE,
        clumsy=TalentFit.INSIDE,
    )
    only_near = ruled(lin(gift("clumsy", SLOW)), clumsy=TalentFit.RELATED)

    two = ruled(
        lin(gift("sword", UNIQUE), gift("architect"), gift("clumsy", SLOW)),
        sword=TalentFit.INSIDE,
        architect=TalentFit.INSIDE,
        clumsy=TalentFit.INSIDE,
    )

    assert talent.standing(alone, BLADE).words == "at half the pace"
    assert (talent.standing(beside, BLADE).pace, talent.standing(beside, BLADE).slowed_by.id) == (
        4,
        "clumsy",
    )
    assert talent.standing(two, BLADE).words == "six times as fast"
    assert talent.standing(only_near, BLADE).pace == 1


# --- insight when two talents cover a move ---------------------------------------------------


def test_two_talents_that_both_cover_a_move_fully_show_an_insight_on_15():
    both = ruled(
        lin(gift("sword", UNIQUE), gift("architect", KNACK)),
        sword=TalentFit.INSIDE,
        architect=TalentFit.INSIDE,
    )

    assert talent.standing(both, BLADE).insight_at == 15


def test_a_talent_that_is_only_related_doesnt_bring_the_easier_insight():
    near = ruled(
        lin(gift("sword", UNIQUE), gift("architect")),
        sword=TalentFit.INSIDE,
        architect=TalentFit.RELATED,
    )
    slow = ruled(
        lin(gift("sword", UNIQUE), gift("clumsy", SLOW)),
        sword=TalentFit.INSIDE,
        clumsy=TalentFit.INSIDE,
    )

    assert talent.standing(near, BLADE).insight_at == 18
    assert talent.standing(slow, BLADE).insight_at == 18
    assert talent.standing(lin(), BLADE).insight_at == 18


def test_a_bridge_all_the_way_makes_the_second_talent_cover_it_fully():
    character = ruled(
        lin(gift("sword", UNIQUE), gift("architect")),
        sword=TalentFit.INSIDE,
        architect=TalentFit.RELATED,
    )

    before = talent.standing(character, BLADE).pace
    stands = talent.standing(bridged(character, "architect"), BLADE)

    assert (before, stands.pace, stands.insight_at) == (10, 12, 15)


# --- bridges ---------------------------------------------------------------------------------


def test_each_bridge_that_held_lifts_the_thing_a_step_toward_the_talent():
    character = ruled(lin(gift("architect")), architect=TalentFit.OUTSIDE)

    steps = [talent.standing(character, BLADE).steps]
    for _ in range(3):
        bridged(character, "architect")
        steps.append(talent.standing(character, BLADE).steps)

    assert steps == [0, 1, 2, 2]  # never past the talent it starts from


def test_a_bridge_over_the_heart_of_the_thing_lifts_two_steps():
    character = bridged(lin(gift("sight", UNIQUE)), "sight", steps=2)

    stands = talent.standing(character, BLADE)

    assert (stands.pace, reaching(stands)) == (4, [("sight", TalentFit.RELATED)])


def test_one_of_a_kind_carries_a_second_thing_all_the_way_in_three_bridges():
    character = lin(gift("sight", UNIQUE))
    for _ in range(3):
        bridged(character, "sight")

    stands = talent.standing(character, BLADE)

    assert (stands.pace, reaching(stands)) == (8, [("sight", TalentFit.INSIDE)])


def test_a_bridge_that_didnt_hold_lifts_nothing():
    character = bridged(lin(gift("architect")), "architect", steps=0)

    assert talent.standing(character, BLADE).steps == 0


def test_a_bridge_lifts_only_its_own_thing_and_its_own_talent():
    character = bridged(lin(gift("architect"), gift("sword", UNIQUE)), "architect")

    assert reaching(talent.standing(character, BLADE)) == [("architect", TalentFit.RELATED)]
    assert talent.standing(character, "technique:aura-step").steps == 0
    assert talent.reach(character.sheet, character.sheet.talent("sword"), BLADE) == 0
