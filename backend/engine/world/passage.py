"""The world catching up on in-world time (W6, W10, B12, K8).

`catch_up` is the one loop that moves the world clock through pending events, at the start of a
turn and during every step of a plan (`engine.pipeline.play_out` calls it per step). It makes
sure the world's own processes are pending (the tick, the clocks' next steps), spaces the tick so
a stretch of any length takes a bounded number of steps, then runs WS2's `advance_clock` with this
package's handler: every event due on the way applies in time order, each at its due time, events
scheduled inside the stretch apply in their turn, and the first that needs the player stops the
clock there. Nothing fires while a time stop holds the world (W10a).
"""

from engine.context import TurnContext
from engine.rng import SeededRng
from engine.state.world import WorldState
from engine.timekeeping import TimePassage, advance_clock, world_stopped
from engine.world.clocks import ensure_clock_events
from engine.world.events import apply_in_place, needs_player
from engine.world.scheduling import World
from engine.world.tick import plan_ticks


def catch_up(state: WorldState, until_s: int, ctx: TurnContext, rng: SeededRng) -> TimePassage:
    """Move the world to `until_s` (never backwards), applying everything due on the way.

    The input state is never changed. The tick and the clocks are keyed by their own in-world
    times and every event rolls from its own seed, so splitting the same stretch into steps
    plays it the same way, except that a stretch longer than `MAX_TICKS_PER_PASSAGE` days spaces
    its ticks by its own length.
    """
    if world_stopped(state):
        return TimePassage(state=state, started_s=state.world_s, ended_s=state.world_s)
    until_s = max(until_s, state.world_s)
    prepared = state.model_copy(deep=True)
    w = World(state=prepared, ctx=ctx, at_s=prepared.world_s, rng=rng.child("world"))
    ensure_clock_events(w)
    plan_ticks(w, until_s)
    passage = advance_clock(
        prepared,
        until_s,
        lambda current, event: apply_in_place(current, event, ctx, rng),
        needs_player=needs_player,
    )
    return passage
