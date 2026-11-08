"""WS17: every eval in the requirements has a scenario, and every scenario runs.

The whole deterministic suite runs in CI's `evals` job (`python -m evals run`); here a few run
as tests, and every live scenario runs on the offline model with a judge that passes whatever it
sees, so a broken live script fails here and not on the first nightly run.
"""

import asyncio
import re
from pathlib import Path

import pytest

from evals.runner import run_scenario
from evals.scenario import Mode
from evals.scenarios import all_scenarios
from moderation.evals import load_cases

REQUIREMENTS = Path(__file__).resolve().parents[3] / "docs" / "REQUIREMENTS.md"
SCENARIOS = {s.id: s for s in all_scenarios()}


def table_titles(heading: str) -> list[str]:
    """The Eval column of the table under `heading` in the requirements."""
    text = REQUIREMENTS.read_text()
    start = text.index(heading)
    table = text[text.index("\n|", start) :]
    table = table[: table.find("\n\n") if "\n\n" in table else len(table)]
    rows = re.findall(r"^\| ([^|]+?) \| .+ \| .+ \|$", table, re.MULTILINE)
    return [row for row in rows if row not in ("Eval", "---")]


@pytest.mark.parametrize(
    "suite, heading", [("T17", "**T17 Openness evals"), ("T18", "**T18 Narration, voice")]
)
def test_every_eval_in_the_requirements_has_a_scenario(suite, heading):
    titles = table_titles(heading)
    assert len(titles) >= 10
    have = {s.title for s in SCENARIOS.values() if s.suite == suite}
    assert [t for t in titles if t not in have] == []


def test_t15s_examples_and_every_content_line_case_are_scenarios():
    assert {"t15.dead-stays-dead", "t15.massacre", "t15.revisit"} <= SCENARIOS.keys()
    for case in load_cases():
        scenario = SCENARIOS[f"t15.content.{case.id}"]
        assert scenario.runs_in(Mode.LIVE)
        assert scenario.runs_in(Mode.DETERMINISTIC) is case.deterministic


def test_every_scenario_cites_its_suite_and_says_when_it_passes():
    for scenario in SCENARIOS.values():
        assert scenario.id.startswith(scenario.suite.lower() + ".")
        assert scenario.suite in scenario.requirements
        assert scenario.passes_when.strip()


def test_only_whats_waiting_on_other_work_is_pending():
    pending = {s.id: s.waits_for for s in SCENARIOS.values() if s.pending}
    assert pending.keys() == {"t17.time-loop", "t18.name-accuracy"}
    assert all(pending.values())


@pytest.mark.parametrize(
    "scenario_id",
    [
        "t15.dead-stays-dead",
        "t15.content.romance-with-a-minor",
        "t17.time-stop",
        "t17.walk-away",
        "t17.controlled-throw",
        "t18.broken-plan",
        "t18.same-face",
        "t18.out-of-the-temple",
    ],
)
def test_a_deterministic_scenario_passes_through_the_turn_graph(scenario_id):
    result = asyncio.run(run_scenario(SCENARIOS[scenario_id], Mode.DETERMINISTIC))
    assert result.status == "passed", result.failures()
    assert result.turns > 0 and result.checks


@pytest.mark.parametrize(
    "scenario_id",
    [s.id for s in SCENARIOS.values() if not s.pending and s.runs_in(Mode.LIVE)],
)
def test_every_live_scenario_runs_on_the_offline_model(scenario_id, offline_models):
    """The offline model's answers are minimal, so checks may fail; the script must not."""
    result = asyncio.run(run_scenario(SCENARIOS[scenario_id], Mode.LIVE, offline_models))
    assert result.status in ("passed", "failed"), result.error
