"""The story evals' command line (WS17; T15, T17, T18).

    uv run python -m evals list
    uv run python -m evals run                        # deterministic: no model, as CI runs it
    uv run python -m evals run --mode live --out evals-out --history evals-out/history.jsonl
    uv run python -m evals run --only t17.time-stop --only t18.
    uv run python -m evals report --history evals-out/history.jsonl

`run` exits 1 when a scenario fails or errors, and 2 when live mode has no model access. Live
mode needs `LLM_PROVIDER=vertex`, `GCP_PROJECT` and Application Default Credentials, never a key
(B11).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evals.results import Run, finish, git_sha, read_history, trend, write
from evals.runner import LiveUnavailable, Models, ScenarioResult, run_scenario
from evals.scenario import Mode, Scenario
from evals.scenarios import all_scenarios


def chosen(only: Sequence[str], suites: Sequence[str]) -> list[Scenario]:
    picked = []
    for scenario in all_scenarios():
        if suites and scenario.suite not in suites:
            continue
        if only and not any(scenario.id.startswith(o) or o == scenario.id for o in only):
            continue
        picked.append(scenario)
    return picked


async def run(scenarios: Sequence[Scenario], mode: Mode, models: Models) -> list[ScenarioResult]:
    results = []
    for scenario in scenarios:
        result = await run_scenario(scenario, mode, models)
        results.append(result)
        line = f"{result.status:>7}  {scenario.id}  ({result.seconds:.1f}s, {result.turns} turns)"
        print(line, flush=True)
        for failure in result.failures():
            print(f"         {failure[:500]}", flush=True)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list", help="list the scenarios")
    listing.add_argument("--suite", action="append", default=[], choices=["T15", "T17", "T18"])

    running = commands.add_parser("run", help="run scenarios")
    running.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.DETERMINISTIC)
    running.add_argument("--only", action="append", default=[], help="an id or id prefix")
    running.add_argument("--suite", action="append", default=[], choices=["T15", "T17", "T18"])
    running.add_argument("--out", type=Path, help="write run.json, summary.md, transcripts…")
    running.add_argument("--history", type=Path, help="append the run to this JSON lines file")

    report = commands.add_parser("report", help="show the trend from a history file")
    report.add_argument("--history", type=Path, required=True)
    report.add_argument("--mode", choices=[m.value for m in Mode])
    report.add_argument("--last", type=int, default=10)

    args = parser.parse_args(argv)
    # Engine and graph warnings (a blocked step, a rejected update) are expected in a run; keep
    # them out of the scenario lines.
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)

    if args.command == "list":
        for scenario in chosen([], args.suite):
            modes = "pending" if scenario.pending else "+".join(m.value for m in scenario.modes)
            print(f"{scenario.suite}  {scenario.id:<48} {modes:<22} {scenario.title}")
        return 0

    if args.command == "report":
        print(trend(read_history(args.history), mode=args.mode, last=args.last), end="")
        return 0

    mode = Mode(args.mode)
    scenarios = chosen(args.only, args.suite)
    if not scenarios:
        print("No scenario matches.", file=sys.stderr)
        return 1
    models = Models()
    started = Run(mode=mode, started_at=datetime.now(UTC))
    if mode is Mode.LIVE:
        try:
            models.require_live()
        except LiveUnavailable as error:
            print(error, file=sys.stderr)
            return 2
        started.models = models.models_used()
    started.sha = git_sha()
    finished = finish(started, asyncio.run(run(scenarios, mode, models)))
    counts = ", ".join(f"{n} {s}" for s, n in finished.counts.items() if n)
    print(f"\n{counts}. {len(finished.gaps())} known gaps open.")
    if args.out is not None:
        path = write(finished, args.out, history=args.history)
        print(f"Results in {path}")
    elif args.history is not None:
        write(finished, args.history.parent / finished.id, history=args.history)
    return 0 if finished.ok else 1


if __name__ == "__main__":
    sys.exit(main())
