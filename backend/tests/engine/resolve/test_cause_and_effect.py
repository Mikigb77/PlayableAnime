"""T17 "Cause and effect" (A2, A9): in a modern city with hidden mages, the player fires a bazooka
at an unshielded thug, then at a mage whose force field is stated to stop it, then at one whose
field is about as strong as the round, over many seeds. The thug dies and the strong field holds
on every seed, with no roll. Only the evenly matched field is a close call, rolled between outcomes
the facts allow."""

from engine.contracts import Intent, MeansVerdict, OutcomeClass
from engine.resolve import odds as odds_mod
from engine.state import CharacterStatus, Health, StepResult

from .worlds import SEEDS, fire_bazooka, hidden_city, resolve


def test_the_unshielded_thug_dies_on_every_seed_with_no_roll():
    state = hidden_city()
    intent = Intent(steps=[fire_bazooka("thug", MeansVerdict.CLEARLY_ENOUGH)])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
        )
        assert settled.roll is None
        (dead,) = settled.effects.characters
        assert (dead.id, dead.status) == ("thug", CharacterStatus.DEAD)


def test_a_field_stated_to_stop_the_round_holds_on_every_seed_with_no_roll():
    state = hidden_city()
    for means in (MeansVerdict.CLEARLY_NOT, MeansVerdict.CLEARLY_ENOUGH):
        # Even a generous proposal can't push a rocket through a body that far above it.
        intent = Intent(steps=[fire_bazooka("vesna", means)])
        for seed in SEEDS:
            (settled,) = resolve(state, intent, seed).steps
            assert (settled.outcome_class, settled.result) == (
                OutcomeClass.RULED_OUT,
                StepResult.FAILURE,
            )
            assert settled.roll is None
            assert settled.effects.empty


def test_an_evenly_matched_field_is_a_close_call_between_outcomes_the_facts_allow():
    state = hidden_city()
    # A proposal that it's clearly enough is capped to a close call by the gap.
    for means in (MeansVerdict.CLOSE_CALL, MeansVerdict.CLEARLY_ENOUGH):
        intent = Intent(steps=[fire_bazooka("ilya", means)])
        results = [resolve(state, intent, seed).steps[0] for seed in SEEDS]

        assert {r.outcome_class for r in results} == {OutcomeClass.CONTESTED}
        assert {r.result for r in results} == {StepResult.SUCCESS, StepResult.PARTIAL}
        assert all(r.roll.allowed == odds_mod.HARM_DONE for r in results)
        for r in results:
            (change,) = r.effects.characters
            if r.result is StepResult.SUCCESS:
                assert change.status is CharacterStatus.DEAD
            else:
                assert change.condition.health is Health.BADLY_WOUNDED
        assert "close call" in results[0].reason
