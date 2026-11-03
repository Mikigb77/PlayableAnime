"""The living world (WS10): deeds, rumors, reputation, attitudes, faction answers, discovery,
emerging characters and factions, clocks and the world tick (W1 to W8, W11 to W13, W15, W15a, E2,
E5, K8). Plain Python with no model call (W6's deterministic part, B4).

The pipeline seams call in here:

- `catch_up(state, until_s, ctx, rng)`: the one loop that moves the clock through pending events,
  at a turn's start and during every step (`passage`).
- `apply_event(state, event, ctx, rng)`: one due event (`events`).
- `record_consequences(state, resolution, step, ctx, rng)`: a finished step's deeds (`deeds`).

Everything the world does later is a pending event at an in-world time (`scheduling.Kind`):
reports, answers, rumors, tidings, discovery, clock steps and ends, emergence, revivals and the
tick. The numbers live in `tuning`.
"""

from engine.context import TurnContext
from engine.rng import SeededRng
from engine.state.records import PendingEvent
from engine.state.world import WorldState
from engine.world.deeds import record_consequences
from engine.world.events import apply_in_place, needs_player
from engine.world.passage import catch_up
from engine.world.scheduling import Kind


def apply_event(
    state: WorldState, event: PendingEvent, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Apply one due event to a copy of the state, at its clock's current time (W10)."""
    return apply_in_place(state.model_copy(deep=True), event, ctx, rng)


__all__ = ["Kind", "apply_event", "catch_up", "needs_player", "record_consequences"]
