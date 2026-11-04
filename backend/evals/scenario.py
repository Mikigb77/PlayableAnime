"""What an eval is: a scripted scenario from T15, T17 or T18, and the registry that holds them.

A scenario is an async script that plays stories through the real turn graph and checks what
code decided. It is written once and runs in two modes:

- **deterministic** (`Mode.DETERMINISTIC`): each line's scripted interpretation is fed to the
  interpret node in place of the model, and a stock narrator answers, so no model is needed and
  the run is the same every time. It runs in CI on every pull request.
- **live** (`Mode.LIVE`): the real models read the player's words and tell the scenes, and a
  model judge scores the narration and pictures against the scenario's rubric. It runs nightly.

A scenario that can't run yet, because the engine work it tests hasn't landed, is registered as
pending with what it waits for, so the reports still show the gap.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from evals.runner import Eval

Suite = Literal["T15", "T17", "T18"]


class Mode(StrEnum):
    DETERMINISTIC = "deterministic"
    LIVE = "live"


BOTH = (Mode.DETERMINISTIC, Mode.LIVE)
LIVE_ONLY = (Mode.LIVE,)

type Script = Callable[[Eval], Awaitable[None]]


@dataclass(frozen=True)
class Scenario:
    """One eval. `title` is the eval's name in its requirements table (docs/REQUIREMENTS.md), so
    the coverage test can match them; `passes_when` is the table's pass condition."""

    id: str
    suite: Suite
    title: str
    requirements: tuple[str, ...]
    passes_when: str
    script: Script | None
    modes: tuple[Mode, ...] = BOTH
    waits_for: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if (self.script is None) == (not self.waits_for):
            raise ValueError(f"{self.id}: a scenario has a script, or says what it waits for")
        if not self.modes:
            raise ValueError(f"{self.id}: a scenario runs in at least one mode")

    @property
    def pending(self) -> bool:
        return self.script is None

    def runs_in(self, mode: Mode) -> bool:
        return not self.pending and mode in self.modes


@dataclass
class Registry:
    scenarios: dict[str, Scenario] = field(default_factory=dict)

    def add(self, scenario: Scenario) -> Scenario:
        if scenario.id in self.scenarios:
            raise ValueError(f"Two scenarios share the id {scenario.id!r}")
        self.scenarios[scenario.id] = scenario
        return scenario

    def scenario(
        self,
        id: str,
        *,
        suite: Suite,
        title: str,
        requirements: tuple[str, ...],
        passes_when: str,
        modes: tuple[Mode, ...] = BOTH,
        notes: str = "",
    ) -> Callable[[Script], Script]:
        """Registers the decorated script as a scenario."""

        def register(script: Script) -> Script:
            self.add(
                Scenario(
                    id=id,
                    suite=suite,
                    title=title,
                    requirements=requirements,
                    passes_when=passes_when,
                    script=script,
                    modes=modes,
                    notes=notes,
                )
            )
            return script

        return register

    def pending(
        self,
        id: str,
        *,
        suite: Suite,
        title: str,
        requirements: tuple[str, ...],
        passes_when: str,
        waits_for: str,
    ) -> None:
        """Registers a scenario that can't run yet, and what it waits for."""
        self.add(
            Scenario(
                id=id,
                suite=suite,
                title=title,
                requirements=requirements,
                passes_when=passes_when,
                script=None,
                waits_for=waits_for,
            )
        )


REGISTRY = Registry()
