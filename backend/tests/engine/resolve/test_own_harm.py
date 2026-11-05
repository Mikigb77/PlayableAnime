"""F1, A2. Harm the player character turns on themselves: a knife to their own heart or a jump from
the battlements. It lands on their own body like any other aim, with only the means deciding,
since they never stand in their own way. It is no deed against anyone and starts no fight, and
once it kills them, the rest of the plan doesn't happen."""

import pytest

from engine.context import Difficulty
from engine.contracts import ActionKind, Aim, Intent, MeansVerdict, OutcomeClass
from engine.state import CharacterStatus, Health, StepResult

from .worlds import SEEDS, facts, item, naples_with_sleeping_guard, resolve, sect, step


def stab_myself(means: MeansVerdict = MeansVerdict.CLEARLY_ENOUGH, **kw):
    return step(
        "drive the knife into my own heart",
        verb="stab",
        aim=Aim.KILL,
        target_ids=["luca"],
        uses=[item("knife")],
        facts=facts(means=means),
        **kw,
    )


def jump(target: str, means: MeansVerdict):
    return step(
        "jump from the top of the tower",
        verb="jump",
        aim=Aim.KILL,
        target_ids=[target],
        facts=facts(means=means),
    )


def died(resolution, character_id: str) -> bool:
    return any(
        c.id == character_id and c.status is CharacterStatus.DEAD
        for s in resolution.steps
        for c in s.effects.characters
    )


def health(resolution, character_id: str) -> Health | None:
    for s in resolution.steps:
        for c in s.effects.characters:
            if c.id == character_id and c.condition is not None and c.condition.health:
                return c.condition.health
    return None


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_a_knife_to_your_own_heart_kills_you_with_no_roll(difficulty):
    state = naples_with_sleeping_guard()

    for seed in SEEDS[:50]:
        resolution = resolve(state, Intent(steps=[stab_myself()]), seed, difficulty)
        (settled,) = resolution.steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
        )
        assert settled.roll is None
        assert died(resolution, "luca")
        # Nobody else was harmed, so it is no deed (W1), and nobody fights themselves (W10).
        assert settled.deeds == []
        assert settled.encounter is None
        assert "luca" not in settled.opponent_ids


def test_a_close_call_on_your_own_body_always_does_harm():
    state = naples_with_sleeping_guard()
    intent = Intent(steps=[stab_myself(MeansVerdict.CLOSE_CALL)])

    outcomes = set()
    for seed in SEEDS:
        resolution = resolve(state, intent, seed)
        (settled,) = resolution.steps
        assert settled.roll is not None
        assert settled.result is not StepResult.FAILURE
        if died(resolution, "luca"):
            outcomes.add("dead")
        else:
            assert health(resolution, "luca") is Health.BADLY_WOUNDED
            outcomes.add("badly wounded")
    assert outcomes == {"dead", "badly wounded"}


def test_the_rest_of_the_plan_never_happens_once_you_are_dead():
    state = naples_with_sleeping_guard()
    walk_out = step("walk out of the bar", ActionKind.MOVE, 30)
    resolution = resolve(state, Intent(steps=[stab_myself(), walk_out]))

    first, second = resolution.steps
    assert died(resolution, "luca")
    assert (second.outcome_class, second.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert second.reason == "You are dead."
    assert second.duration_s == 0


def test_a_jump_a_strong_body_shrugs_off_never_kills():
    # The interpret step judged that the fall can't hurt a body like Lin Feng's.
    state = sect()
    resolution = resolve(state, Intent(steps=[jump("lin", MeansVerdict.CLEARLY_NOT)]))

    (settled,) = resolution.steps
    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert not died(resolution, "lin")


def test_a_jump_from_the_battlements_kills_whoever_makes_it():
    state = sect()
    resolution = resolve(state, Intent(steps=[jump("lin", MeansVerdict.CLEARLY_ENOUGH)]))

    (settled,) = resolution.steps
    assert settled.result is StepResult.SUCCESS
    assert died(resolution, "lin")
    assert settled.deeds == []


def test_harm_aimed_at_yourself_and_someone_else_is_a_deed_against_them_only():
    state = naples_with_sleeping_guard()
    both = step(
        "grab Tonino and throw us both off the roof",
        verb="kill",
        aim=Aim.KILL,
        target_ids=["guard", "luca"],
        facts=facts(means=MeansVerdict.CLEARLY_ENOUGH),
    )

    resolution = resolve(state, Intent(steps=[both]))
    (settled,) = resolution.steps
    assert died(resolution, "guard") and died(resolution, "luca")
    (deed,) = settled.deeds
    assert deed.victim_ids == ["guard"]
    assert "luca" not in deed.target_ids
    assert settled.opponent_ids == ["guard"]
