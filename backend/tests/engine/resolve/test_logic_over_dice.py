"""T17 "Logic over dice": cutting the throat of a sleeping guard the player is standing over,
killing a troll frozen by time stop, and stabbing a sleeping ancient dragon with a kitchen knife,
over many seeds and on every difficulty. The first two succeed every time and the dragon is never
hurt, with no roll recorded and the reason in the scene details (A2, A5). The dragon is refused
by a fact the world's ladder states, never by the gap alone (G18)."""

import pytest

from engine.context import Difficulty
from engine.contracts import Aim, Intent, MeansVerdict, OutcomeClass
from engine.resolve import throw as dice
from engine.state import CharacterStatus, Condition, PassingState, PowerAxis, StepResult

from .worlds import (
    SEEDS,
    add,
    disciple,
    facts,
    item,
    naples_with_sleeping_guard,
    resolve,
    sect,
    step,
    stop_time,
    with_dragon,
    with_troll,
)


def cut_throat(target: str, weapon: str, **kw):
    return step(
        f"cut {target}'s throat",
        verb="kill",
        aim=Aim.KILL,
        target_ids=[target],
        uses=[item(weapon)],
        **kw,
    )


def killed(resolution, character_id: str) -> bool:
    return any(
        c.id == character_id and c.status is CharacterStatus.DEAD
        for s in resolution.steps
        for c in s.effects.characters
    )


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_sleeping_guard_dies_every_time_with_no_roll(difficulty):
    state = naples_with_sleeping_guard()
    # The interpret step forgot he was asleep; the sheet says so.
    intent = Intent(steps=[cut_throat("guard", "knife", facts=facts(can_respond=True))])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed, difficulty).steps
        assert settled.outcome_class is OutcomeClass.CERTAIN
        assert settled.result is StepResult.SUCCESS
        assert settled.roll is None
        assert "asleep" in settled.reason
        assert killed(resolve(state, intent, seed, difficulty), "guard")


def test_the_interpret_steps_word_that_he_sleeps_is_enough_when_the_sheet_is_silent():
    state = naples_with_sleeping_guard(asleep_on_sheet=False)
    intent = Intent(
        steps=[cut_throat("guard", "knife", facts=facts(can_respond=False, why_not="asleep"))]
    )

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert (settled.outcome_class, settled.roll) == (OutcomeClass.CERTAIN, None)
        assert settled.reason == "Tonino is asleep and can't respond: no contest."


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_troll_frozen_by_time_stop_dies_every_time_with_no_roll(difficulty):
    state = with_troll(sect())
    intent = Intent(steps=[stop_time(), cut_throat("troll", "sword", proposed_personal_s=2)])

    for seed in SEEDS:
        resolution = resolve(state, intent, seed, difficulty)
        stop, kill = resolution.steps
        assert stop.outcome_class is OutcomeClass.CERTAIN
        assert kill.outcome_class is OutcomeClass.CERTAIN
        assert kill.result is StepResult.SUCCESS
        assert kill.roll is None
        assert "frozen in stopped time" in kill.reason
        assert (kill.duration_s, kill.personal_s) == (0, 2)  # the world stands still (W10a)
        assert kill.deeds[0].in_stopped_time
        assert killed(resolution, "troll")


@pytest.mark.parametrize("difficulty", list(Difficulty))
@pytest.mark.parametrize("proposed", [None, MeansVerdict.CLEARLY_ENOUGH, MeansVerdict.CLOSE_CALL])
def test_a_kitchen_knife_never_hurts_a_sleeping_ancient_dragon(difficulty, proposed):
    state = with_dragon(sect())
    # However generous the interpret step was about the knife, the dragon's body decides.
    intent = Intent(
        steps=[
            cut_throat(
                "dragon",
                "kitchen-knife",
                axis=PowerAxis.MIGHT,
                facts=facts(can_respond=False, why_not="asleep", means=proposed),
            )
        ]
    )

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed, difficulty).steps
        assert settled.outcome_class is OutcomeClass.RULED_OUT
        assert settled.result is StepResult.FAILURE
        assert settled.roll is None
        assert settled.effects.empty
        # The world's ladder names the fact that refuses it (G18).
        assert settled.reason.endswith(
            "The ancient dragon stands six rungs above you, and harm from that far below can't "
            "get through by ordinary means."
        )
        # The attempt is still a deed: the dragon may notice (A8, W1).
        assert settled.deeds[0].target_ids == ["dragon"]


@pytest.mark.parametrize("asleep", [True, False])
def test_calling_the_stab_a_matter_of_stealth_doesnt_get_a_knife_through_dragon_scales(asleep):
    state = with_dragon(sect())
    if not asleep:
        state.characters["dragon"].sheet.condition.states.clear()
    sneaky = cut_throat(
        "dragon",
        "kitchen-knife",
        axis=PowerAxis.STEALTH,
        facts=facts(means=MeansVerdict.CLEARLY_ENOUGH, can_respond=not asleep),
    )

    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[sneaky]), seed).steps
        assert (settled.outcome_class, settled.roll) == (OutcomeClass.RULED_OUT, None)
        assert not any(c.id == "dragon" for c in settled.effects.characters)
        # Awake, the dragon answers the knife, and nothing Lin has can stop it (N6).
        assert [a.by_ids for a in settled.perils] == ([] if asleep else [["dragon"]])


def test_a_guard_awake_beside_a_sleeping_elder_doesnt_make_the_elder_easier_to_hurt():
    # Elder Mo sleeps two realms up while a disciple of Lin's own realm keeps watch. Getting past
    # the disciple would be an even throw, but the blow lands on the elder's body, which is the
    # harder of the two, so that is the number (A2, G18).
    state = add(sect(), disciple("wei", "Wei"))
    state.characters["elder-mo"].sheet.condition = Condition(states=[PassingState(name="asleep")])
    attack = cut_throat(
        "elder-mo",
        "sword",
        axis=PowerAxis.MIGHT,
        facts=facts(opposition_ids=["elder-mo", "wei"], can_respond=True),
    )

    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[attack]), seed).steps
        thrown = settled.roll.throw
        assert settled.outcome_class is OutcomeClass.LONG_SHOT
        assert [(part.text, part.points) for part in thrown.made_of] == [
            ("Elder Mo's toughness, level 2", 17),
            ("two rungs above you, Core Formation over Qi Condensation", 20),
        ]
        assert thrown.against == "Wei can answer, and Elder Mo's body is the question."
    # Alone with the disciple, the same sword is an even throw.
    spar = cut_throat("wei", "sword", facts=facts(opposition_ids=["wei"], can_respond=True))
    (settled,) = resolve(state, Intent(steps=[spar])).steps
    assert settled.roll.throw.number == 17


def test_a_sleeping_body_a_rung_or_two_above_is_thrown_for_and_the_blow_lands_either_way():
    # No proposal makes a sword kill a sleeping elder outright: the body is a fact code reads.
    state = sect()
    state.characters["elder-mo"].sheet.condition = Condition(states=[PassingState(name="asleep")])
    for means in (None, MeansVerdict.CLEARLY_ENOUGH, MeansVerdict.CLOSE_CALL):
        attack = cut_throat("elder-mo", "sword", facts=facts(means=means))
        results = [resolve(state, Intent(steps=[attack]), seed).steps[0] for seed in SEEDS]
        assert all(r.roll is not None and r.roll.allowed == dice.HARM_DONE for r in results)
        assert {r.result for r in results} == {StepResult.SUCCESS, StepResult.PARTIAL}
        assert {r.roll.throw.number for r in results} == {37}
        assert results[0].reason.startswith(
            "Elder Mo is asleep and can't respond. The blow lands either way, and the throw is "
            "for how much. Strength and speed, 2 dice, against Elder Mo's toughness, level 2; "
            "two rungs above you, Core Formation over Qi Condensation (+20): "
        )


@pytest.mark.parametrize(
    ("state_name", "helpless"),
    [
        ("asleep", True),
        ("fast asleep", True),
        ("tied up", True),
        ("bound", True),
        ("chained to the wall", True),
        ("half asleep", False),
        ("sleepless", False),
        ("bound by an oath", False),
        ("no longer bound", False),
    ],
)
def test_only_a_state_that_really_leaves_someone_helpless_stops_them_responding(
    state_name, helpless
):
    state = naples_with_sleeping_guard(asleep_on_sheet=False)
    state.characters["guard"].sheet.condition = Condition(states=[PassingState(name=state_name)])
    attack = cut_throat("guard", "knife", facts=facts(opposition_ids=["guard"], can_respond=True))

    (settled,) = resolve(state, Intent(steps=[attack])).steps

    assert (settled.roll is None) is helpless
