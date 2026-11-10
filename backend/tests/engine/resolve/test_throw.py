"""The throw (A3, A5): the dice that decide an open step, and the exact chances the agreed plan
states, worked out from the code by listing every way the dice can fall."""

import pytest

from engine import levels
from engine.context import Difficulty
from engine.contracts import OutcomeClass
from engine.resolve import throw as dice
from engine.resolve.throw import Hand, Number, Shares, chance, shares
from engine.rng import SeededRng
from engine.state import Die, DieKind, Mark, Mastery, RollRecord, StepResult

BALANCED = Difficulty.BALANCED
SEEDS = range(400)


def hand(dice_: int, last: DieKind | None = None) -> Hand:
    return Hand(dice_, f"{dice_} dice", last)


def own_level(dice_: int, difficulty: Difficulty = BALANCED) -> int:
    return levels.number(dice_, difficulty)


def at_own_level(dice_: int, last: DieKind | None = None, greens: int = 0) -> Shares:
    return shares(hand(dice_, last), greens, own_level(dice_))


def pct(share: float) -> float:
    return round(100 * share, 1)


# --- the agreed table ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dice_", "last", "so_close", "missed", "over"),
    [
        (1, DieKind.VIOLET, 25.0, 5.0, 5.0),  # learning
        (2, DieKind.VIOLET, 16.25, 13.75, 5.0),  # practiced: the table shows 16.2 and 13.8
        (3, DieKind.VIOLET, 14.6, 16.6, 3.0),  # skilled
        (4, DieKind.GOLD, 11.7, 11.8, 1.9),  # second nature
        (5, DieKind.GOLD, 10.5, 13.7, 1.1),  # made their own
    ],
)
def test_the_chances_of_a_move_at_its_own_level_match_the_agreed_table(
    dice_, last, so_close, missed, over
):
    found = at_own_level(dice_, last)
    assert 100 * found.so_close == pytest.approx(so_close, abs=0.06)
    assert 100 * found.missed == pytest.approx(missed, abs=0.06)
    assert 100 * found.over_the_top == pytest.approx(over, abs=0.06)
    assert found.passed + found.so_close + found.missed == pytest.approx(1.0)


def test_a_green_die_is_worth_about_one_level():
    skilled = hand(3, DieKind.VIOLET)
    assert round(100 * chance(skilled, 0, own_level(3))) == 69
    assert round(100 * chance(skilled, 1, own_level(3))) == 91
    assert round(100 * chance(skilled, 1, own_level(4))) == 69
    assert round(100 * chance(skilled, 2, own_level(3))) == 98
    assert round(100 * chance(skilled, 2, own_level(4))) == 89


def test_no_gap_reaches_zero():
    # Three levels up, a skilled move still passes about one time in twenty.
    assert chance(hand(3, DieKind.VIOLET), 0, own_level(6)) == pytest.approx(0.046, abs=0.005)
    assert chance(hand(1, DieKind.VIOLET), 0, own_level(5)) > 0


@pytest.mark.parametrize(
    ("difficulty", "low", "high"),
    [(Difficulty.STORY, 78, 85), (Difficulty.BALANCED, 69, 77), (Difficulty.BRUTAL, 55, 68)],
)
def test_the_difficulty_sets_what_comes_off_every_number(difficulty, low, high):
    hands = [(d, DieKind.VIOLET if d < 4 else DieKind.GOLD) for d in range(1, 6)]
    passes = [round(100 * chance(hand(d, last), 0, own_level(d, difficulty))) for d, last in hands]
    assert min(passes) == low and max(passes) == high


def test_a_deadly_throw_against_an_equal_kills_between_5_and_17_times_in_100():
    hands = [(d, DieKind.VIOLET if d < 4 else DieKind.GOLD) for d in range(1, 6)]
    missed = [pct(at_own_level(d, last).missed) for d, last in hands]
    assert 5.0 <= min(missed) and max(missed) <= 17.0
    # Right after a step of theirs that missed, which adds 5 to the number: 23.5 to 31.2.
    exposed = [pct(shares(hand(d, last), 0, own_level(d) + 5).missed) for d, last in hands]
    assert exposed == [30.0, 30.0, 31.2, 23.5, 24.2]


# --- the dice ------------------------------------------------------------------------------------


def thrown(seed: int, hand_: Hand, number: int, **kw) -> RollRecord:
    target = Number(0, (dice.NumberPart(text="a test", points=number),))
    kw.setdefault("allowed", dice.ALL_RESULTS)
    return dice.throw(
        SeededRng(f"throw-{seed}"), hand_, target, label="a throw", difficulty=BALANCED, **kw
    )


def test_a_throw_replays_exactly_from_its_seed():
    for seed in SEEDS:
        roll = thrown(seed, hand(3, DieKind.VIOLET), 27, greens=["from behind"])
        stream = SeededRng(roll.seed)
        assert [d.face for d in roll.throw.dice] == [stream.randint(1, 20) for _ in roll.throw.dice]
        assert thrown(seed, hand(3, DieKind.VIOLET), 27, greens=["from behind"]) == roll


def test_the_plain_dice_fall_first_then_the_green_ones_then_the_moves_own():
    roll = thrown(1, hand(3, DieKind.VIOLET), 27, greens=["from behind", "caught mid-turn"])
    kinds = [d.kind for d in roll.throw.dice if not d.sprung]
    assert kinds == [DieKind.PLAIN, DieKind.PLAIN, DieKind.GREEN, DieKind.GREEN, DieKind.VIOLET]
    assert roll.throw.hand == 5 and roll.throw.most == 100
    assert roll.throw.greens == ["from behind", "caught mid-turn"]


def test_two_green_dice_at_most_count():
    roll = thrown(1, hand(2), 17, greens=["one", "two", "three", ""])
    assert roll.throw.greens == ["one", "two"] and roll.throw.hand == 4


def test_a_20_throws_one_more_plain_die_and_that_one_can_throw_another():
    sprung = 0
    for seed in SEEDS:
        dice_ = thrown(seed, hand(4, DieKind.GOLD), 37, greens=["high ground"]).throw.dice
        for before, after in zip(dice_, dice_[1:], strict=False):
            assert after.sprung == (before.face == 20)
            if after.sprung:
                sprung += 1
                assert after.kind is DieKind.PLAIN
    assert sprung > 0


def test_a_gold_die_never_counts_below_10():
    assert Die(kind=DieKind.GOLD, face=3).value == 10
    assert Die(kind=DieKind.GOLD, face=14).value == 14
    assert Die(kind=DieKind.VIOLET, face=3).value == 3
    for seed in SEEDS:
        roll = thrown(seed, hand(4, DieKind.GOLD), 37)
        assert roll.throw.total == sum(d.value for d in roll.throw.dice)


def test_the_violet_die_shows_an_insight_at_18_or_more():
    seen = set()
    for seed in SEEDS:
        roll = thrown(seed, hand(2, DieKind.VIOLET), 17)
        violet = next(d for d in roll.throw.dice if d.kind is DieKind.VIOLET)
        assert roll.throw.insight == (violet.face >= 18)
        seen.add(roll.throw.insight)
        assert not thrown(seed, hand(4, DieKind.GOLD), 37).throw.insight
    assert seen == {True, False}


def test_a_moves_own_die_is_violet_while_they_master_it_and_gold_from_second_nature():
    violet = [Mastery.LEARNING, Mastery.PRACTICED, Mastery.SKILLED]
    assert all(dice.own_die(m) is DieKind.VIOLET for m in violet)
    assert dice.own_die(Mastery.SECOND_NATURE) is DieKind.GOLD
    assert dice.own_die(Mastery.OWN) is DieKind.GOLD


# --- the mark and the result ---------------------------------------------------------------------


def test_the_mark_is_how_the_total_stands_against_the_number():
    assert dice.mark_of(27, 27, 3) is Mark.PASSED
    assert dice.mark_of(60, 27, 3) is Mark.PASSED
    assert dice.mark_of(61, 27, 3) is Mark.OVER_THE_TOP  # past 20 for each die in the hand
    assert dice.mark_of(26, 27, 3) is Mark.SO_CLOSE
    assert dice.mark_of(22, 27, 3) is Mark.SO_CLOSE  # short by 5
    assert dice.mark_of(21, 27, 3) is Mark.MISSED
    # Over the top is a pass first: a huge total that still falls short of the number is none.
    assert dice.mark_of(45, 47, 2) is Mark.SO_CLOSE


def test_so_close_is_a_partial_success_only_where_a_half_result_exists():
    assert dice.result_of(Mark.PASSED, dice.ALL_RESULTS) is StepResult.SUCCESS
    assert dice.result_of(Mark.OVER_THE_TOP, dice.YES_OR_NO) is StepResult.SUCCESS
    assert dice.result_of(Mark.SO_CLOSE, dice.ALL_RESULTS) is StepResult.PARTIAL
    assert dice.result_of(Mark.MISSED, dice.ALL_RESULTS) is StepResult.FAILURE
    # Yes or no: so close is a miss with nothing worse attached.
    assert dice.result_of(Mark.SO_CLOSE, dice.YES_OR_NO) is StepResult.FAILURE
    # A step that can't simply fail is partly done on any miss.
    assert dice.result_of(Mark.MISSED, dice.HARM_DONE) is StepResult.PARTIAL
    assert dice.result_of(Mark.MISSED, dice.OWN_CHOICE) is StepResult.PARTIAL


def test_a_throw_records_what_it_was_made_of_and_the_exact_chance():
    number = dice.level_number(3, "A skilled guard, level 3", BALANCED).plus("the dark", 5)
    roll = dice.throw(
        SeededRng("recorded"),
        Hand(3, "Aura blade, skilled: 3 dice", DieKind.VIOLET),
        number,
        label="cut at the guard",
        allowed=dice.ALL_RESULTS,
        difficulty=BALANCED,
        greens=["from behind"],
        against="A skilled guard, awake.",
    )
    assert roll.throw.number == 32
    assert [(p.text, p.points) for p in roll.throw.made_of] == [
        ("A skilled guard, level 3", 27),
        ("the dark", 5),
    ]
    assert roll.odds_label == roll.throw.line == f"{roll.throw.total} against 32"
    assert roll.odds == pytest.approx(chance(Hand(3, "", DieKind.VIOLET), 1, 32), abs=1e-4)
    assert roll.throw.against == "A skilled guard, awake."
    assert roll.result is dice.result_of(roll.throw.mark, dice.ALL_RESULTS)
    words = dice.told(roll)
    assert words.startswith("Aura blade, skilled: 3 dice, and a green die for from behind, against")
    assert words.endswith(f"{roll.throw.line}, {dice.MARK_WORDS[roll.throw.mark]}")


def test_a_number_moves_in_named_steps_and_whole_levels():
    number = dice.level_number(2, "The lock, level 2", BALANCED)
    assert (number.level, number.value) == (2, 17)
    raised = number.raised(2, "two rungs above you, met head-on")
    assert (raised.level, raised.value) == (4, 37)
    assert raised.parts[-1].points == 20
    lowered = number.raised(-3, "three rungs below you, met head-on")
    assert (lowered.level, lowered.value) == (-1, 0)  # never below nothing
    assert number.plus("nothing", 0) is number and number.raised(0, "") is number
    assert dice.level_number(0, "Nothing", BALANCED).value == 0


def test_nothing_at_level_0_or_two_levels_under_the_hand_is_thrown_for():
    assert not dice.open_against(hand(1), 0)
    assert dice.open_against(hand(1), 1)
    assert dice.open_against(hand(3), 2) and not dice.open_against(hand(3), 1)
    assert dice.open_against(hand(5), 4) and not dice.open_against(hand(5), 3)
    assert dice.open_against(hand(1), 5)  # however far above: a gap never refuses


def test_a_throw_that_rarely_passes_is_a_long_shot():
    assert dice.class_of(0.149) is OutcomeClass.LONG_SHOT
    assert dice.class_of(0.15) is OutcomeClass.CONTESTED
    assert dice.class_of(0.98) is OutcomeClass.CONTESTED


# --- the world's die -----------------------------------------------------------------------------


def test_the_worlds_die_is_one_grey_die_that_the_difficulty_never_moves():
    even, long = [], []
    for seed in range(2000):
        for difficulty in Difficulty:
            roll = dice.world_die(SeededRng(f"w-{seed}"), label="a herb", difficulty=difficulty)
            (die,) = roll.throw.dice
            assert die.kind is DieKind.GREY and roll.throw.of_the_world
            assert roll.result is (StepResult.SUCCESS if die.face >= 11 else StepResult.FAILURE)
            assert roll.odds == 0.5 and roll.allowed == dice.YES_OR_NO
        even.append(roll.result is StepResult.SUCCESS)
        rare = dice.world_die(
            SeededRng(f"w-{seed}"), label="a relic", difficulty=BALANCED, long_shot=True
        )
        assert rare.throw.number == 19 and rare.odds == pytest.approx(0.1)
        long.append(rare.result is StepResult.SUCCESS)
    assert 0.46 < sum(even) / len(even) < 0.54
    assert 0.07 < sum(long) / len(long) < 0.13
    assert not thrown(1, hand(1), 7).throw.of_the_world


def test_a_hand_holds_at_least_one_die_and_only_a_move_has_a_last_die():
    with pytest.raises(ValueError):
        Hand(0)
    with pytest.raises(ValueError):
        Hand(2, "", DieKind.GREEN)
