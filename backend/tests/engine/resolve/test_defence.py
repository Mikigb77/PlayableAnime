"""N6, A3: the defence throw. Every die is the player character's own: they throw their defence
against the strongest foe who answers, or against a danger, and how far it falls short says what
the blow does. A throw that can kill is marked Deadly before the dice land, and nothing hidden is
drawn afterwards."""

from collections import Counter

import pytest

from engine.contracts import Aim, Harm, OutcomeClass, SheetPart, SheetUse
from engine.resolve.perils import MAIMS_SHORT_BY, MISS_COSTS
from engine.state import Mark, PowerAxis, Skill, SkillLevel, StepResult, WorldState

from .test_perils import circle, fighting, jump, one
from .worlds import SEEDS, add, disciple, facts, item, sect, step


def in_a_fight() -> WorldState:
    """Lin fighting Wei, a disciple of his own realm."""
    return fighting(add(sect(), disciple("wei", "Wei")), "wei")


def parry(meant: Aim = Aim.KILL):
    return step(
        "parry Wei's cut",
        verb="parry",
        axis=PowerAxis.MIGHT,
        uses=[item("sword")],
        facts=facts(opposition_ids=["wei"], can_respond=True, foes_mean=meant),
    )


# --- Deadly --------------------------------------------------------------------------------------


def test_a_blow_meant_to_kill_is_marked_deadly_before_the_dice_with_what_a_miss_costs():
    state = in_a_fight()
    for seed in range(40):
        [peril] = one(state, circle(Aim.KILL), seed=seed).perils
        thrown = peril.roll.throw
        assert thrown.deadly  # whatever the dice then showed
        assert thrown.miss_costs == "A miss by more than 5 kills. Just short leaves a bad wound."
        assert thrown.against == "Wei strikes back, meaning to kill."


def test_the_interpret_steps_own_words_for_what_a_miss_costs_are_kept():
    told = step(
        "circle",
        verb="circle",
        facts=facts(foes_mean=Aim.KILL, miss_costs="His blade opens your throat."),
    )
    [peril] = one(in_a_fight(), told).perils
    assert peril.roll.throw.miss_costs == "His blade opens your throat."


@pytest.mark.parametrize(
    ("meant", "against"),
    [
        (Aim.WOUND, "Wei strikes back."),
        (Aim.SUBDUE, "Wei strikes back, meaning to take you down."),
    ],
)
def test_a_blow_that_cant_kill_is_not_deadly(meant, against):
    [peril] = one(in_a_fight(), circle(meant)).perils
    thrown = peril.roll.throw
    assert (thrown.deadly, thrown.miss_costs, thrown.against) == (False, "", against)


# --- how far it fell short -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("meant", "just_short", "missed"),
    [
        (Aim.KILL, Harm.BADLY_WOUNDED, Harm.DEAD),
        (Aim.WOUND, Harm.HURT, Harm.WOUNDED),
        (Aim.SUBDUE, Harm.HURT, Harm.SUBDUED),
    ],
)
def test_how_far_the_defence_fell_short_says_what_the_blow_does(meant, just_short, missed):
    state = in_a_fight()
    seen = Counter()
    for seed in SEEDS:
        [peril] = one(state, circle(meant), seed=seed).perils
        thrown = peril.roll.throw
        seen[thrown.mark] += 1
        if thrown.mark.passed:
            assert (peril.harm, peril.result) == (Harm.NONE, StepResult.FAILURE)
        elif thrown.mark is Mark.SO_CLOSE:
            assert 1 <= thrown.short_by <= 5
            # N6. A killing blow that fell short by 4 or 5 leaves a wound that lasts.
            maims = meant is Aim.KILL and thrown.short_by >= MAIMS_SHORT_BY
            assert peril.harm is (Harm.MAIMED if maims else just_short)
            assert peril.result is StepResult.PARTIAL
        else:
            assert thrown.short_by > 5
            assert (peril.harm, peril.result) == (missed, StepResult.SUCCESS)
    assert set(seen) == set(Mark)


def test_the_same_dice_give_the_same_marks_whatever_the_foe_meant():
    # What they mean changes what a miss costs, never the throw itself.
    state = in_a_fight()
    for seed in range(60):
        marks = {
            meant: one(state, circle(meant), seed=seed).perils[0].roll.throw.line
            for meant in (Aim.KILL, Aim.WOUND, Aim.SUBDUE)
        }
        assert len(set(marks.values())) == 1


def test_the_reason_reads_the_throw_and_then_what_it_did():
    state = in_a_fight()
    told = {}
    for seed in SEEDS:
        [peril] = one(state, circle(Aim.KILL), seed=seed).perils
        told.setdefault(peril.roll.throw.mark, peril.reason)
    lead = "Wei strikes back. Speed, 2 dice, against Wei's strength and speed, level 2: "
    assert all(reason.startswith(lead) for reason in told.values())
    assert told[Mark.PASSED].endswith("against 17, passed. It misses you.")
    assert told[Mark.MISSED].endswith("against 17, missed. It kills you.")
    assert told[Mark.SO_CLOSE].endswith(
        (
            "so close. You are badly wounded.",
            "so close. You are maimed, with a wound that will last.",
        )
    )
    assert told[Mark.OVER_THE_TOP].endswith(
        "over the top. You turn the blow, and your next step against them throws a green die."
    )


# --- the hand ------------------------------------------------------------------------------------


def guard_up(level: SkillLevel):
    state = in_a_fight()
    state.player.sheet.skills.append(Skill(name="swordplay", level=level))
    on_guard = step(
        "circle with my sword up",
        verb="circle",
        uses=[item("sword"), SheetUse(part=SheetPart.SKILL, ref="swordplay")],
        facts=facts(foes_mean=Aim.KILL),
    )
    return state, on_guard


def test_the_defence_is_thrown_with_the_skill_the_step_drew_on_when_it_serves_better():
    state, on_guard = guard_up(SkillLevel.SKILLED)
    [peril] = one(state, on_guard).perils
    assert peril.roll.throw.hand_why == "Swordplay (skilled), 3 dice"
    # With no skill in hand it is their speed.
    [peril] = one(in_a_fight(), circle(Aim.KILL)).perils
    assert peril.roll.throw.hand_why == "Speed, 2 dice"


def test_foes_two_levels_under_the_hand_cant_get_past_the_guard():
    state, on_guard = guard_up(SkillLevel.EXPERT)  # four dice against Wei's level 2
    for seed in range(40):
        [peril] = one(state, on_guard, seed=seed).perils
        assert (peril.outcome_class, peril.roll, peril.harm) == ("ruled_out", None, Harm.NONE)
        assert peril.reason == "Wei strikes back, but they can't get past your guard."


def test_each_other_foe_near_the_strongest_adds_five_and_two_at_most():
    numbers = {}
    for count in (1, 2, 3, 4):
        foes = [disciple(f"foe-{n}", f"Foe {n}") for n in range(count)]
        state = fighting(add(sect(), *foes), *(f.id for f in foes))
        [peril] = one(state, circle()).perils
        numbers[count] = peril.roll.throw.number
        extra = [(part.text, part.points) for part in peril.roll.throw.made_of[1:]]
        assert (
            extra
            == {
                1: [],
                2: [("one more at their side", 5)],
                3: [("two more at their side", 10)],
                4: [("two more at their side", 10)],
            }[count]
        )
    assert numbers == {1: 17, 2: 22, 3: 27, 4: 27}


# --- a defence over the top ----------------------------------------------------------------------


def test_a_defence_over_the_top_turns_the_blow_and_wins_an_opening():
    state = in_a_fight()
    turned = 0
    for seed in SEEDS:
        settled = one(state, circle(Aim.KILL), seed=seed)
        [peril] = settled.perils
        if peril.roll.throw.mark is not Mark.OVER_THE_TOP:
            assert settled.opening_ids == []
            continue
        turned += 1
        assert peril.harm is Harm.NONE
        assert settled.opening_ids == ["wei"]
    assert turned


# --- the step that is itself the defence ---------------------------------------------------------


def test_a_parry_is_the_one_throw_and_a_foe_it_held_off_has_no_answer():
    state = in_a_fight()
    seen = Counter()
    for seed in SEEDS:
        settled = one(state, parry(), seed=seed)
        thrown = settled.roll.throw
        # They mean to kill, so the parry itself is the Deadly throw.
        assert thrown.deadly and thrown.miss_costs == MISS_COSTS[Aim.KILL]
        seen[thrown.mark] += 1
        if thrown.mark.passed:
            assert settled.result is StepResult.SUCCESS and settled.perils == []
            continue
        [peril] = settled.perils
        assert peril.roll is None  # no second throw
        assert peril.reason.startswith(
            "Wei strikes back, and your defence fell short, with no second throw: "
        )
        if thrown.mark is Mark.MISSED:
            assert peril.harm is Harm.DEAD
        else:
            maims = thrown.short_by >= MAIMS_SHORT_BY
            assert peril.harm is (Harm.MAIMED if maims else Harm.BADLY_WOUNDED)
    assert set(seen) == set(Mark)


def test_a_parry_over_the_top_leaves_the_foe_staggered():
    state = in_a_fight()
    won = [s for s in SEEDS if one(state, parry(), seed=s).opening_ids]
    assert won
    for seed in won:
        settled = one(state, parry(), seed=seed)
        assert settled.roll.throw.mark is Mark.OVER_THE_TOP
        assert settled.opening_ids == ["wei"] and "Wei is staggered" in settled.extra


def test_a_parry_against_a_foe_who_only_means_to_wound_is_not_deadly():
    thrown = one(in_a_fight(), parry(Aim.WOUND)).roll.throw
    assert (thrown.deadly, thrown.miss_costs) == (False, "")


# --- a danger ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("surely", "level", "number"),
    [(OutcomeClass.LONG_SHOT, 1, 7), (OutcomeClass.CONTESTED, 2, 17)],
)
@pytest.mark.parametrize("does", [Aim.KILL, Aim.WOUND])
def test_a_dangers_level_is_how_surely_it_hurts_an_ordinary_person(surely, level, number, does):
    state = sect()
    for seed in range(60):
        [peril] = one(state, jump(surely, does), seed=seed).perils
        thrown = peril.roll.throw
        assert thrown.hand_why == "Speed, 2 dice"
        assert [(part.text, part.points) for part in thrown.made_of] == [
            (f"the long drop to the river, level {level}", number)
        ]
        assert thrown.against == "The long drop to the river."
        # What it does when it hurts says whether a miss can kill.
        assert thrown.deadly is (does is Aim.KILL)
        assert thrown.miss_costs == (MISS_COSTS[Aim.KILL] if does is Aim.KILL else "")
        if thrown.mark is Mark.MISSED:
            assert peril.harm is (Harm.DEAD if does is Aim.KILL else Harm.WOUNDED)


@pytest.mark.parametrize(("does", "harm"), [(Aim.KILL, Harm.DEAD), (Aim.WOUND, Harm.WOUNDED)])
def test_a_danger_certain_to_hurt_a_person_lands_on_a_persons_body_with_no_throw(does, harm):
    for seed in range(20):
        [peril] = one(sect(), jump(OutcomeClass.CERTAIN, does), seed=seed).perils
        assert (peril.outcome_class, peril.roll, peril.harm) == ("certain", None, harm)
        assert peril.reason.startswith("The long drop to the river, and there's no escaping it: ")


def test_a_danger_that_cant_do_real_harm_does_none():
    for seed in range(20):
        [peril] = one(sect(), jump(OutcomeClass.RULED_OUT), seed=seed).perils
        assert (peril.outcome_class, peril.roll, peril.harm) == ("ruled_out", None, Harm.NONE)
        assert peril.reason == "The long drop to the river, but it can't do real harm."


def test_a_body_a_step_above_a_persons_peak_throws_against_a_certain_danger_one_level_down():
    state = sect()
    state.characters["lin"].sheet.axes.might = 6  # one rung above a person's peak
    [peril] = one(state, jump(OutcomeClass.CERTAIN)).perils
    assert peril.roll is not None
    assert peril.roll.throw.made_of[0].text == "the long drop to the river, level 3"


def test_a_step_that_missed_adds_five_to_the_danger_it_faced():
    state = sect()
    leap = step(
        "leap the gap between the roofs",
        verb="leap",
        facts=facts(
            opposition="the gap between the roofs",
            danger="the fall to the street",
            danger_class=OutcomeClass.CONTESTED,
            danger_harm=Aim.WOUND,
        ),
    )
    exposed = Counter()
    for seed in SEEDS:
        settled = one(state, leap, seed=seed)
        [peril] = settled.perils
        moved = [(part.text, part.points) for part in peril.roll.throw.made_of[1:]]
        missed = settled.result is StepResult.FAILURE
        assert moved == ([("your own step missed", 5)] if missed else [])
        exposed[missed] += 1
    assert set(exposed) == {True, False}
