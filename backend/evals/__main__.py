"""The story evals' command line (WS17; T15, T17, T18).

    uv run python -m evals list
    uv run python -m evals run                        # deterministic: no model, as CI runs it
    uv run python -m evals run --mode live --out evals-out --history evals-out/history.jsonl
    uv run python -m evals run --only t17.time-stop --only t18.
    uv run python -m evals report --history evals-out/history.jsonl
    uv run python -m evals styles --out evals-out     # one scene in each candidate house style
    uv run python -m evals play --root plays --plays '{"farmer": [{"create": {"premise": "…"}}]}'

`run` exits 1 when a scenario fails or errors, and 2 when live mode has no model access.
`play` plays stories by hand, a few steps at a time, on the real models where there are any
(`evals.play`), and exits 1 when a step failed and 2 when what it was given can't be read.
`styles` draws each scene of `evals.styles` in each candidate house style for Miki to pick from
(S7), and exits 1 when it drew nothing. Live mode and `styles` need `LLM_PROVIDER=vertex`,
`GCP_PROJECT` and Application Default Credentials, never a key (B11).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evals.results import Run, finish, git_sha, read_history, trend, write
from evals.runner import LiveUnavailable, Models, ScenarioResult, run_scenario
from evals.scenario import Mode, Scenario
from evals.scenarios import all_scenarios

# How much of a failed check's line a run prints. A check's detail may say how each step of a
# lesson was read, and a live run's log is all that can be read of the run afterwards.
FAILURE_CHARS = 4000
METRICS_CHARS = 1000


class CallFormatter(logging.Formatter):
    """The plain log line, with what a failed model call says of itself (`graph.llm`): its node,
    model, attempt, reason and the provider's own words, such as which quota ran out, so a live
    run's log shows why. Never its prompt (T6)."""

    FIELDS = ("node", "model", "attempt", "reason", "detail")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        call = getattr(record, "llm", None)
        if not isinstance(call, dict):
            return line
        said = ", ".join(f"{k}={call[k]}" for k in self.FIELDS if call.get(k) not in (None, ""))
        return f"{line} ({said[:500]})" if said else line


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
            print(f"         {failure[:FAILURE_CHARS]}", flush=True)
        if mode is Mode.LIVE and result.metrics:
            # What a live run counted, such as how its stories ended: its log is all that can
            # be read of it afterwards.
            print(f"         metrics: {str(result.metrics)[:METRICS_CHARS]}", flush=True)
    return results


def draw_styles(
    out: Path,
    scene_ids: Sequence[str],
    style_ids: Sequence[str],
    models: Models,
    candidates: str = "",
) -> int:
    """`styles`: each chosen scene in each chosen candidate house style (S7, `evals.styles`):
    the built-in candidates, or today's style and the ones `candidates` lists as JSON."""
    from evals import styles
    from graph.llm import Node, TurnTelemetry
    from media.drawing import GraphPictureModel

    try:
        scenes = styles.pick(styles.SCENES, scene_ids)
        catalog = styles.candidates(candidates) if candidates.strip() else styles.STYLES
        chosen_styles = styles.pick(catalog, style_ids)
        models.require_live()
    except (ValueError, LiveUnavailable) as error:
        print(error, file=sys.stderr)
        return 2
    model_name = models.resolved().node(Node.PICTURE).model

    def new_model() -> GraphPictureModel:
        telemetry = TurnTelemetry()
        return GraphPictureModel(models.client("teen", telemetry), telemetry, model_name)

    samples = asyncio.run(styles.draw_all(new_model, out, scenes, chosen_styles))
    total = styles.write(samples, out, scenes, chosen_styles)
    drawn = sum(sample.status == "drawn" for sample in samples)
    print(f"\n{drawn} of {len(samples)} pictures drawn for ${total:.2f}. Results in {out}")
    return 0 if drawn else 1


def play_by_hand(root: Path, given: str, models: Models) -> int:
    """`play`: the steps given for each play, on the plays kept under `root` (`evals.play`)."""
    from evals import play

    try:
        plays = json.loads(given)
        if not isinstance(plays, dict) or not plays:
            raise ValueError("--plays is a JSON object: each play's name and its list of steps.")
        played = asyncio.run(play.play_all(root, plays, models))
    except ValueError as error:  # JSON that can't be read, or a name that is no play's name
        print(error, file=sys.stderr)
        return 2
    for name, whole in played.items():
        print(f"{'played' if whole else 'stopped':>7}  {name}", flush=True)
    return 0 if all(played.values()) else 1


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

    styling = commands.add_parser("styles", help="draw one scene in each candidate house style")
    styling.add_argument("--out", type=Path, required=True, help="write the pictures here")
    styling.add_argument("--scene", action="append", default=[], help="a scene id (all if none)")
    styling.add_argument("--style", action="append", default=[], help="a style id (all if none)")
    styling.add_argument(
        "--candidates", default="", help="a JSON list of candidates to draw next to today's style"
    )

    playing = commands.add_parser("play", help="play stories by hand, a few steps at a time")
    playing.add_argument("--root", type=Path, required=True, help="where each play's folder is")
    playing.add_argument("--plays", required=True, help="JSON: each play's name and its steps")

    args = parser.parse_args(argv)
    # Engine and graph warnings (a blocked step, a rejected update) are expected in a run; keep
    # them out of the scenario lines.
    errors = logging.StreamHandler(sys.stderr)
    errors.setFormatter(CallFormatter(logging.BASIC_FORMAT))
    logging.basicConfig(level=logging.ERROR, handlers=[errors])
    # A form the provider refused is worth its one line: the model then reads the form from
    # the prompt, which changes how well it fills it in.
    logging.getLogger("graph.llm.gemini").setLevel(logging.WARNING)

    if args.command == "list":
        for scenario in chosen([], args.suite):
            modes = "pending" if scenario.pending else "+".join(m.value for m in scenario.modes)
            print(f"{scenario.suite}  {scenario.id:<48} {modes:<22} {scenario.title}")
        return 0

    if args.command == "report":
        print(trend(read_history(args.history), mode=args.mode, last=args.last), end="")
        return 0

    if args.command == "styles":
        return draw_styles(args.out, args.scene, args.style, Models(), args.candidates)

    if args.command == "play":
        return play_by_hand(args.root, args.plays, Models())

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
        started.thinking = models.thinking_used()
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
