"""T17 "Workaround" (A9, G18, W10): a mage three realms up shelters in a hall behind a force field
that keeps out blades, bazooka rounds and air, and the player sets the hall on fire from outside,
over many seeds; once when she has no way out and once when her sheet has a teleport. With no way
out, she dies on every seed once the air runs out, minutes of in-world time later, with no roll and
the chain in the scene details. With the teleport, she escapes and hunts for whoever tried. A
head-on attack on her stays ruled out."""

from engine.base import MINUTE
from engine.contracts import BeatVerdict, ChainLink, Intent, OutcomeClass, StopReason
from engine.state import CharacterStatus, Condition, PassingState, StepResult

from .worlds import (
    SEEDS,
    burn_the_hall,
    facts,
    resolve,
    shielded_mage,
    step,
    strike,
)


def test_with_no_way_out_she_dies_on_every_seed_once_the_air_runs_out():
    state = shielded_mage()
    intent = Intent(steps=[burn_the_hall()])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert settled.outcome_class is OutcomeClass.CERTAIN
        assert settled.result is StepResult.SUCCESS
        assert settled.roll is None
        assert [link.holds for link in settled.chain] == [True] * 4
        assert {link.outcome_class for link in settled.chain} == {OutcomeClass.CERTAIN}
        (dead,) = settled.effects.characters
        assert (dead.id, dead.status) == ("su-yan", CharacterStatus.DEAD)
    # Ten minutes of work, then six while the fire takes the hall and the air runs out (W10).
    assert settled.duration_s == 10 * MINUTE + 6 * MINUTE
    # The chain is in the scene details, with the facts behind each link (A9).
    assert settled.chain[1].reason == ("It follows from Su Yan's Azure Barrier.")
    assert settled.chain[2].reason == (
        "It follows from Su Yan's Azure Barrier; The hall has a single door."
    )
    assert [b.verdict for b in settled.beats] == [BeatVerdict.HOLDS, BeatVerdict.MADE_CANON]


def test_with_a_teleport_she_escapes_on_every_seed_and_the_attempt_is_a_deed():
    state = shielded_mage(teleport=True)
    intent = Intent(steps=[burn_the_hall()])

    for seed in SEEDS:
        (settled,) = resolve(state, intent, seed).steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
        )
        assert settled.roll is None
        assert settled.stopped_at_link == 3
        assert settled.effects.empty
    assert (
        settled.chain[-1].reason == "Su Yan has a way out: Void Step (Teleports her out of danger)."
    )
    assert "breaks at" in settled.reason
    # She knows someone tried to burn her alive; WS10 turns the deed into her hunt (W1, W4).
    (deed,) = settled.deeds
    assert deed.target_ids == ["su-yan"] and deed.victim_ids == []


def test_a_head_on_attack_on_her_stays_ruled_out():
    state = shielded_mage()
    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[strike("su-yan")]), seed).steps
        assert (settled.outcome_class, settled.roll) == (OutcomeClass.RULED_OUT, None)
    assert "Nascent Soul" in settled.reason


def test_a_link_resting_on_something_untrue_breaks_the_chain():
    state = shielded_mage()
    state.facts["no-exit"].is_true = False

    (settled,) = resolve(state, Intent(steps=[burn_the_hall()])).steps

    assert settled.result is StepResult.FAILURE
    assert settled.stopped_at_link == 2
    assert settled.chain[2].outcome_class is OutcomeClass.RULED_OUT
    assert "isn't so" in settled.chain[2].reason


def test_smoke_doesnt_choke_what_doesnt_breathe():
    state = shielded_mage()
    chain = burn_the_hall().chain
    chain[3] = chain[3].model_copy(update={"proposed_class": OutcomeClass.RULED_OUT})

    (settled,) = resolve(state, Intent(steps=[burn_the_hall(chain=chain)])).steps

    assert (settled.result, settled.outcome_class) == (StepResult.FAILURE, OutcomeClass.RULED_OUT)
    assert settled.roll is None


def test_a_link_judged_open_is_rolled_and_can_go_either_way():
    state = shielded_mage()
    chain = burn_the_hall().chain
    chain.insert(
        1,
        ChainLink(
            text="The fire catches before the night rain puts it out.",
            proposed_class=OutcomeClass.CONTESTED,
        ),
    )

    results = [
        resolve(state, Intent(steps=[burn_the_hall(chain=chain)]), seed).steps[0] for seed in SEEDS
    ]

    assert {r.result for r in results} == {StepResult.SUCCESS, StepResult.FAILURE}
    assert {r.outcome_class for r in results} == {OutcomeClass.CONTESTED}
    assert all(r.chain[1].roll is not None for r in results)


def test_a_mage_who_sees_it_coming_can_answer_first():
    state = shielded_mage()
    aware = facts(opposition_ids=["su-yan"], can_respond=True)

    results = [
        resolve(state, Intent(steps=[burn_the_hall(facts=aware)]), seed).steps[0] for seed in SEEDS
    ]

    caught = [r for r in results if r.result is StepResult.FAILURE]
    assert caught and len(caught) < len(results)
    assert all(r.chain == [] and "sees it coming" in r.reason for r in caught)
    assert all(r.roll is not None for r in results)


def test_someone_asleep_in_the_burning_hall_cant_use_their_way_out():
    state = shielded_mage(teleport=True)
    state.characters["su-yan"].sheet.condition = Condition(states=[PassingState(name="asleep")])

    (settled,) = resolve(state, Intent(steps=[burn_the_hall()])).steps

    assert settled.result is StepResult.SUCCESS


def test_a_chained_plan_stops_where_the_workaround_fails():
    state = shielded_mage(teleport=True)
    intent = Intent(
        steps=[burn_the_hall(), step("walk away whistling", duration_s=30, kind="move")]
    )

    resolution = resolve(state, intent)

    # Her way out settles it with no roll, so the plan stops as ruled out.
    assert resolution.stopped_at_step == 0
    assert resolution.stop_reason is StopReason.RULED_OUT
    assert resolution.unplayed == ["walk away whistling"]
