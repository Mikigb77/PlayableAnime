"""Eval results, kept over time (T15, T17, T18: "results are tracked over time").

A run writes, under its output directory:

- `run.json`: the run and every scenario's result: status, score, checks, judged rubrics,
  metrics, cost and the known gaps still open.
- `summary.md`: the same as a table, for a CI job summary.
- `transcripts/<scenario>.json` (live): each story's turns, for staff to spot-check the judge.
- `pictures/<scenario>/<name>.<ext>` (live): every picture drawn.

and appends one line per run to a history file (JSON lines), which `report` reads back as a trend:
each scenario's status and score run after run. Nothing written here holds a prompt, a key or a
token (T6); transcripts hold the player's actions and the narration, which are the story itself.
"""

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from evals.pictures import NotDrawn, Picture
from evals.runner import ScenarioResult
from evals.scenario import Mode

STATUSES = ("passed", "failed", "error", "pending", "skipped")


def git_sha() -> str:
    sha = os.environ.get("GITHUB_SHA", "")
    if sha:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False
        )
    except OSError:
        return ""
    return out.stdout.strip()


@dataclass
class Run:
    mode: Mode
    started_at: datetime
    finished_at: datetime | None = None
    sha: str = ""
    models: dict[str, str] = field(default_factory=dict)
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.started_at:%Y%m%dT%H%M%SZ}-{self.mode.value}"

    @property
    def counts(self) -> dict[str, int]:
        return {s: sum(1 for r in self.results if r.status == s) for s in STATUSES}

    @property
    def ok(self) -> bool:
        return not any(r.status in ("failed", "error") for r in self.results)

    @property
    def cost_usd(self) -> Decimal:
        return sum((r.cost_usd for r in self.results), Decimal(0))

    @property
    def score(self) -> float | None:
        scores = [r.score for r in self.results if r.score is not None]
        return round(sum(scores) / len(scores), 4) if scores else None

    def gaps(self) -> list[tuple[str, str]]:
        return [(r.id, gap) for r in self.results for gap in r.gaps()]

    def to_json(self) -> dict[str, Any]:
        return {
            "run": self.id,
            "mode": self.mode.value,
            "sha": self.sha,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "models": self.models,
            "counts": self.counts,
            "score": self.score,
            "cost_usd": float(self.cost_usd),
            "gaps": [{"scenario": s, "gap": g} for s, g in self.gaps()],
            "scenarios": [r.to_json() for r in self.results],
        }

    def history_line(self) -> dict[str, Any]:
        """One compact line for the history file."""
        return {
            "run": self.id,
            "mode": self.mode.value,
            "sha": self.sha,
            "at": self.started_at.isoformat(),
            "score": self.score,
            "cost_usd": float(self.cost_usd),
            "counts": self.counts,
            "scenarios": {
                r.id: {
                    "status": r.status,
                    "score": r.score,
                    "cost_usd": float(r.cost_usd),
                    "gaps": len(r.gaps()),
                }
                for r in self.results
            },
        }


def write(run: Run, out: Path, *, history: Path | None = None) -> Path:
    """Writes the run's files under `out` and appends it to `history`. Returns `run.json`."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "run.json"
    path.write_text(json.dumps(run.to_json(), indent=2, default=str) + "\n")
    (out / "summary.md").write_text(summary(run))
    for result in run.results:
        if result.transcripts:
            folder = out / "transcripts"
            folder.mkdir(exist_ok=True)
            (folder / f"{result.id}.json").write_text(
                json.dumps(result.transcripts, indent=2, default=str) + "\n"
            )
        drawn = [p for p in result.pictures if isinstance(p, Picture)]
        if drawn:
            folder = out / "pictures" / result.id
            folder.mkdir(parents=True, exist_ok=True)
            for picture in drawn:
                ext = mimetypes.guess_extension(picture.mime_type) or ".bin"
                (folder / f"{_safe(picture.name)}{ext}").write_bytes(picture.data)
    if history is not None:
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a") as lines:
            lines.write(json.dumps(run.history_line(), default=str) + "\n")
    return path


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)[:80] or "picture"


def summary(run: Run) -> str:
    counts = run.counts
    head = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    if run.mode is Mode.LIVE:
        cost = f"${run.cost_usd:.2f} spent on models"
    else:
        # Scripted answers of fixed sizes to the real prompts, priced as the models would be:
        # no money spent, but prompt growth shows here run after run (K8).
        cost = f"no model spend (the real prompts would have cost ${run.cost_usd:.2f})"
    lines = [
        f"## Story evals: {run.mode.value} run {run.id}",
        "",
        f"{head}. Average score {_pct(run.score)}, {cost}.",
        *_pictures(run),
        "",
        "| Scenario | Status | Score | Turns | Seconds | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    skipped = [r.id for r in run.results if r.status == "skipped"]
    for r in run.results:
        if r.status == "skipped":
            continue
        notes = "; ".join(r.failures())[:300] if r.status in ("failed", "error") else r.waits_for
        lines.append(
            f"| {r.id} | {r.status} | {_pct(r.score)} | {r.turns} | {r.seconds:.1f} | "
            f"{_cell(notes)} |"
        )
    if skipped:
        lines += ["", f"Skipped in {run.mode.value} mode: {', '.join(skipped)}."]
    gaps = run.gaps()
    if gaps:
        lines += ["", "### Known gaps still open", ""]
        lines += [f"- **{scenario}**: {_cell(gap)}" for scenario, gap in gaps]
    return "\n".join(lines) + "\n"


def _pictures(run: Run) -> list[str]:
    """What a live run's pictures came to: by which model, how many, for how much, and how many
    weren't drawn and why, so two runs of the picture evals with different picture models can be
    weighed side by side (M8, T18)."""
    pictures = [p for r in run.results for p in r.pictures]
    if not pictures:
        return []
    drawn = [p for p in pictures if isinstance(p, Picture)]
    missed = Counter(p.reason for p in pictures if isinstance(p, NotDrawn))
    models = sorted({p.model for p in drawn}) or [run.models.get("picture") or "the picture model"]
    cost = sum((p.cost_usd for p in drawn), Decimal(0))
    line = f"Pictures by {', '.join(models)}: {len(drawn)} drawn for ${cost:.2f}"
    if missed:
        reasons = ", ".join(f"{n} {reason}" for reason, n in missed.most_common())
        line += f", {missed.total()} not drawn ({reasons})"
    return ["", f"{line}."]


def _pct(score: float | None) -> str:
    return "–" if score is None else f"{score:.0%}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


# --- the trend over time -----------------------------------------------------------------------


def read_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    runs = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            runs.append(json.loads(line))
    return runs


def trend(runs: Sequence[dict[str, Any]], *, mode: str | None = None, last: int = 10) -> str:
    """Each scenario's status and score over the last `last` runs, oldest first, with each run's
    average score and cost listed above by its column number: what changed after a model or
    prompt change shows here."""
    chosen = [r for r in runs if mode is None or r.get("mode") == mode][-last:]
    if not chosen:
        return "No runs in the history yet.\n"
    marks = {"passed": "✓", "failed": "✗", "error": "!", "pending": "…", "skipped": "-"}
    lines = ["Runs:"]
    for n, r in enumerate(chosen, 1):
        # A deterministic run's cost is what its real prompts would have cost (marked ~).
        spent = "" if r.get("mode") == Mode.LIVE.value else "~"
        lines.append(
            f"{n:>4}  {r['run']}  score {_pct(r.get('score'))}  "
            f"cost {spent}${r.get('cost_usd', 0):.2f}  {(r.get('sha') or '')[:7]}".rstrip()
        )
    names = sorted({s for r in chosen for s in r.get("scenarios", {})})
    width = max((len(n) for n in names), default=8)
    cell = 6
    lines += [
        "",
        "Scenario".ljust(width + 1) + "".join(f"{n:>{cell}}" for n in range(1, len(chosen) + 1)),
    ]
    for name in names:
        cells = []
        for r in chosen:
            s = r.get("scenarios", {}).get(name)
            if s is None:
                cells.append("")
            elif s["status"] in ("passed", "failed", "error"):
                cells.append(f"{marks[s['status']]}{_pct(s['score'])}")
            else:
                cells.append(marks.get(s["status"], "?"))
        lines.append(name.ljust(width + 1) + "".join(c.rjust(cell) for c in cells))
    return "\n".join(lines) + "\n"


def finish(run: Run, results: Iterable[ScenarioResult]) -> Run:
    run.results = list(results)
    run.finished_at = datetime.now(UTC)
    return run
