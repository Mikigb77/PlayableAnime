"""Every scenario, registered in `evals.scenario.REGISTRY` when its module is imported."""

from evals.scenario import REGISTRY, Scenario
from evals.scenarios import (  # noqa: F401  (registers them)
    t15,
    t17,
    t17_climbing,
    t17_lives,
    t17_old_age,
    t17_play,
    t17_powers,
    t17_romance,
    t17_world,
    t18,
    t18_reading,
)


def all_scenarios() -> list[Scenario]:
    return list(REGISTRY.scenarios.values())
