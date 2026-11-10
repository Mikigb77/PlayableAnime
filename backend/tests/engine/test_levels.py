"""The one scale of levels (A3, A4, G14, G18): how many dice a move, a skill or a body throws,
what number a level sets, and how a move's mastery grows with use.

Nothing is rolled with it yet: the throw comes on top of this scale. The figures are the ones
agreed with Miki on 2026-11-10.
"""

import pytest

from engine import levels
from engine.contracts import Challenge
from engine.state import Mastery, PowerLadder, Rung, SkillLevel


def test_a_move_throws_by_its_mastery_one_die_to_five():
    dice = [levels.MASTERY_DICE[m] for m in Mastery]

    assert list(Mastery) == [
        Mastery.LEARNING,
        Mastery.PRACTICED,
        Mastery.SKILLED,
        Mastery.SECOND_NATURE,
        Mastery.OWN,
    ]
    assert dice == [1, 2, 3, 4, 5]


def test_a_step_with_no_named_move_throws_by_its_skill():
    dice = {skill.value: levels.SKILL_DICE[skill] for skill in SkillLevel}

    assert dice == {
        "untrained": 1,
        "novice": 1,
        "fair": 2,
        "skilled": 3,
        "expert": 4,
        "master": 5,
    }


def test_a_raw_feat_throws_by_the_attribute_two_dice_for_an_average_adult():
    assert levels.attribute_dice(3) == 2
    assert [levels.attribute_dice(level) for level in (4, 5, 6, 10)] == [3, 4, 5, 9]
    # Below average is one die, and nobody throws none.
    assert [levels.attribute_dice(level) for level in (2, 1, 0)] == [1, 1, 1]


def test_the_six_words_are_levels_and_trivial_is_nothing_to_beat():
    by_word = {challenge.value: levels.CHALLENGE_LEVEL[challenge] for challenge in Challenge}

    assert by_word == {
        "trivial": 0,
        "easy": 1,
        "moderate": 2,
        "hard": 3,
        "very_hard": 4,
        "extreme": 5,
    }
    assert levels.number(levels.CHALLENGE_LEVEL[Challenge.TRIVIAL]) == 0


def test_the_number_is_ten_a_level_less_three():
    assert [levels.number(level) for level in range(1, 8)] == [7, 17, 27, 37, 47, 57, 67]


def test_mastery_takes_six_uses_then_fifteen_then_thirty():
    assert levels.grown(Mastery.LEARNING, 0, 5) == (Mastery.LEARNING, 5)
    assert levels.grown(Mastery.LEARNING, 5, 1) == (Mastery.PRACTICED, 0)
    assert levels.grown(Mastery.PRACTICED, 13, 2) == (Mastery.SKILLED, 0)
    assert levels.grown(Mastery.SKILLED, 29, 1) == (Mastery.SECOND_NATURE, 0)
    # About fifty uses from a new move to second nature.
    assert sum(levels.USES_TO_NEXT.values()) == 51
    assert levels.grown(Mastery.LEARNING, 0, 51) == (Mastery.SECOND_NATURE, 0)


def test_uses_past_a_step_carry_on_toward_the_next():
    assert levels.grown(Mastery.LEARNING, 4, 4) == (Mastery.PRACTICED, 2)
    assert levels.grown(Mastery.LEARNING, 0, 30) == (Mastery.SKILLED, 9)


@pytest.mark.parametrize("mastery", [Mastery.SECOND_NATURE, Mastery.OWN])
def test_no_count_of_uses_makes_a_move_their_own(mastery):
    assert levels.uses_to_next(mastery) is None
    assert levels.grown(mastery, 10, 1_000) == (mastery, 1_010)
    assert levels.grown(Mastery.LEARNING, 0, 10_000)[0] is Mastery.SECOND_NATURE


def test_a_use_a_roll_decided_counts_twice():
    assert (levels.PLAIN_USE, levels.RESISTED_USE) == (1, 2)


def test_a_new_move_starts_two_steps_under_the_skill_it_belongs_to():
    assert levels.starting_mastery(None) is Mastery.LEARNING
    starts = {skill.value: levels.starting_mastery(skill).value for skill in SkillLevel}

    assert starts == {
        "untrained": "learning",
        "novice": "learning",
        "fair": "learning",
        "skilled": "learning",
        "expert": "practiced",
        "master": "skilled",  # a master with a new cut is still a master
    }


def test_talent_sets_the_pace_of_mastery():
    """Fourteen uses for someone who learns four times as fast, and twice as many for a slow
    learner as for an ordinary one."""
    climbing = (Mastery.LEARNING, Mastery.PRACTICED, Mastery.SKILLED)

    assert [levels.uses_to_next(m, 4.0) for m in climbing] == [2, 4, 8]
    assert [levels.uses_to_next(m, 2.0) for m in climbing] == [3, 8, 15]
    assert [levels.uses_to_next(m, 8.0) for m in climbing] == [1, 2, 4]
    assert [levels.uses_to_next(m, 0.5) for m in climbing] == [12, 30, 60]
    assert levels.uses_to_next(Mastery.SECOND_NATURE, 4.0) is None
    assert levels.grown(Mastery.LEARNING, 0, 14, 4.0) == (Mastery.SECOND_NATURE, 0)
    assert levels.grown(Mastery.LEARNING, 0, 13, 4.0) == (Mastery.SKILLED, 7)


def test_a_new_move_a_talent_covers_starts_higher():
    """A genius's new move starts at practiced and one of a kind's at skilled. A knack sets the
    pace and leaves the start to the skill."""
    assert levels.starting_mastery(None, talent_steps=1) is Mastery.LEARNING
    assert levels.starting_mastery(None, talent_steps=2) is Mastery.PRACTICED
    assert levels.starting_mastery(None, talent_steps=3) is Mastery.SKILLED
    assert levels.starting_mastery(SkillLevel.EXPERT, talent_steps=2) is Mastery.PRACTICED
    assert levels.starting_mastery(None, talent_steps=-1) is Mastery.LEARNING
    # Where their skill puts them higher, the skill stands.
    assert levels.starting_mastery(SkillLevel.MASTER, talent_steps=2) is Mastery.SKILLED


def test_a_ladder_states_what_a_rung_counts_for_and_what_it_shrugs_off():
    """G18: by default a rung is one level where a move meets that power head-on, and harm from
    three rungs below doesn't get through by ordinary means. A world can say two levels."""
    ladder = PowerLadder(id="realms", name="Realms", rungs=[Rung(name="Mortal", tier=1)])

    assert (ladder.rung_levels, ladder.shrugs_off) == (1, 3)
    wide = ladder.model_copy(update={"rung_levels": 2})
    assert PowerLadder.model_validate(wide.model_dump()).rung_levels == 2
    with pytest.raises(ValueError):
        PowerLadder.model_validate({**ladder.model_dump(), "rung_levels": 3})
    # A world saved before ladders stated it loads with the defaults.
    old = {k: v for k, v in ladder.model_dump().items() if k not in ("rung_levels", "shrugs_off")}
    assert PowerLadder.model_validate(old) == ladder
