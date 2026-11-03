"""What every resolution promises the turn graph, over many seeds and every kind of step (A2, A3):
a certain or ruled-out step carries no roll that could have changed it (only one that picked how
long it took), and a contested or long-shot step carries the roll that decided it, with the same
result."""

import pytest

from engine.contracts import (
    ActionKind,
    Beat,
    BeatUse,
    ChainLink,
    Intent,
    MeansVerdict,
    OutcomeClass,
    Plausibility,
    UseSource,
)
from engine.samples import cultivation_world, grounded_world
from engine.state import StepResult

from .worlds import (
    burn_the_hall,
    facts,
    fire_bazooka,
    hidden_city,
    naples_with_sleeping_guard,
    resolve,
    sect,
    shielded_mage,
    step,
    strike,
)

SETTLED = {OutcomeClass.CERTAIN: StepResult.SUCCESS, OutcomeClass.RULED_OUT: StepResult.FAILURE}


def _open_link_chain():
    chain = burn_the_hall().chain
    chain.insert(
        1,
        ChainLink(text="The fire catches before the rain.", proposed_class=OutcomeClass.CONTESTED),
    )
    return chain


CASES = {
    "fight": lambda: (sect(), Intent(steps=[strike("zhao", duration_uncertain=True)])),
    "ruled out head-on": lambda: (sect(), Intent(steps=[strike("elder-mo")])),
    "close call": lambda: (
        hidden_city(),
        Intent(steps=[fire_bazooka("ilya", MeansVerdict.CLOSE_CALL)]),
    ),
    "sure kill": lambda: (naples_with_sleeping_guard(), Intent(steps=[strike("guard")])),
    "uncertain find": lambda: (
        cultivation_world(),
        Intent(
            steps=[
                step(
                    "throw a brick",
                    beats=[
                        Beat(
                            text="find a brick",
                            uses=[
                                BeatUse(
                                    source=UseSource.NEW,
                                    thing="a loose brick",
                                    plausibility=Plausibility.UNCERTAIN,
                                )
                            ],
                        )
                    ],
                )
            ]
        ),
    ),
    "certain with a rolled time": lambda: (
        grounded_world(),
        Intent(
            steps=[
                step(
                    "find Carmine's cousin in the city",
                    ActionKind.TASK,
                    3600,
                    verb="search",
                    duration_uncertain=True,
                )
            ]
        ),
    ),
    "chain, no way out": lambda: (shielded_mage(), Intent(steps=[burn_the_hall()])),
    "chain, a way out": lambda: (shielded_mage(teleport=True), Intent(steps=[burn_the_hall()])),
    "chain, an open link": lambda: (
        shielded_mage(),
        Intent(steps=[burn_the_hall(chain=_open_link_chain())]),
    ),
    "chain, an open link, a rolled time": lambda: (
        shielded_mage(),
        Intent(steps=[burn_the_hall(chain=_open_link_chain(), duration_uncertain=True)]),
    ),
    "chain, seen coming, an open link": lambda: (
        shielded_mage(),
        Intent(
            steps=[
                burn_the_hall(
                    chain=_open_link_chain(),
                    facts=facts(opposition_ids=["su-yan"], can_respond=True),
                )
            ]
        ),
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_each_step_carries_the_roll_that_decided_it_and_no_other(case):
    state, intent = CASES[case]()
    for seed in range(150):
        for settled in resolve(state, intent, seed).steps:
            roll = settled.roll
            if settled.outcome_class in SETTLED:
                assert settled.result is SETTLED[settled.outcome_class]
                if roll is not None:  # only a roll that picked the time
                    assert (roll.odds, roll.result) == (1.0, settled.result)
                    assert roll.duration_s == settled.duration_s
            else:
                assert roll is not None and roll.result is settled.result
