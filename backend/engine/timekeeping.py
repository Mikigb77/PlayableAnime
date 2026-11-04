"""In-world time (W10, W10a): how long actions take, and the clock moving through pending events.

The interpret step proposes a duration; code bounds it by the kind of action, so a sword exchange
takes seconds and a night's sleep hours, never a fixed amount per turn. A time skip takes whatever
the player asks for, within a generous cap (E7).

When time passes, `advance_clock` applies every pending event due on the way in time order, and
the first that needs the player stops the clock at its due time, so the scene starts there.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.contracts.intent import ActionKind, IntentStep, SheetPart
from engine.state.records import EventStatus, PendingEvent
from engine.state.sheet import Power, TimeEffect
from engine.state.world import ActiveTimeEffect, WorldState

# A guard against a handler that keeps scheduling events due at once. A real stretch of time,
# even a decade's time skip, applies far fewer.
MAX_EVENTS_PER_PASSAGE = 500

DURATION_BOUNDS: dict[ActionKind, tuple[int, int]] = {
    ActionKind.INSTANT: (0, 10),
    ActionKind.EXCHANGE: (1, 2 * MINUTE),
    ActionKind.MOVE: (1, 30 * MINUTE),
    ActionKind.CONVERSATION: (10, 4 * HOUR),
    ActionKind.TASK: (MINUTE, 3 * DAY),
    ActionKind.REST: (10 * MINUTE, 2 * DAY),
    ActionKind.WORK: (30 * MINUTE, 18 * HOUR),
    ActionKind.TRAVEL: (MINUTE, YEAR),
    ActionKind.WAIT: (1, DAY),
    ActionKind.OBSERVE: (1, HOUR),
    ActionKind.TIME_SKIP: (MINUTE, 1000 * YEAR),
}


def bound_duration(kind: ActionKind, proposed_s: int, *, world_frozen: bool = False) -> int:
    """The proposed duration, held within what that kind of action can take (W10).

    With `world_frozen`, as for an action inside a time stop, the world clock doesn't move at all
    (W10a), so the world duration is 0 whatever was proposed. Bound the actor's lived time with
    this function as usual.
    """
    if world_frozen:
        return 0
    low, high = DURATION_BOUNDS[kind]
    return max(low, min(high, int(proposed_s)))


def in_time_stop(state: WorldState, actor_id: str) -> bool:
    """W10a. Whether a time stop of the actor's own is in effect, so the world clock stands still
    while theirs runs. A stop ends with its user's death."""
    actor = state.characters.get(actor_id)
    if actor is None or not actor.alive:
        return False
    lived = actor.personal_s(state.world_s)
    return any(
        e.character_id == actor_id
        and e.effect is TimeEffect.STOP
        and (e.ends_personal_s is None or lived < e.ends_personal_s)
        for e in state.time_effects
    )


def effect_over(state: WorldState, effect: ActiveTimeEffect) -> bool:
    """W10a. Whether a time effect has run out on its user's own clock, or its user is dead."""
    user = state.characters.get(effect.character_id)
    if user is None or not user.alive:
        return True
    return effect.ends_personal_s is not None and user.personal_s(state.world_s) >= (
        effect.ends_personal_s
    )


def prune_time_effects(state: WorldState) -> None:
    """Drop the time effects that have run out, in place."""
    state.time_effects = [e for e in state.time_effects if not effect_over(state, e)]


def tempo_effect(state: WorldState, actor_id: str) -> ActiveTimeEffect | None:
    """W10a. A haste or slow of the actor's own still in effect, if any."""
    for effect in state.time_effects:
        if (
            effect.character_id == actor_id
            and effect.effect in (TimeEffect.HASTE, TimeEffect.SLOW)
            and not effect_over(state, effect)
        ):
            return effect
    return None


def stop_power_used(state: WorldState, actor_id: str, step: IntentStep) -> Power | None:
    """W10a. The time-stop power a step uses, if it uses one of the actor's own."""
    actor = state.characters.get(actor_id)
    if actor is None:
        return None
    for use in step.uses:
        if use.part is not SheetPart.POWER:
            continue
        power = actor.sheet.power(use.ref)
        if power is not None and power.time is not None and power.time.effect is TimeEffect.STOP:
            return power
    return None


def world_stopped(state: WorldState) -> bool:
    """W10a. Whether anyone's time stop is in effect, so no pending event may fire."""
    return any(
        in_time_stop(state, e.character_id)
        for e in state.time_effects
        if e.effect is TimeEffect.STOP
    )


EventHandler = Callable[[WorldState, PendingEvent], WorldState]
NeedsPlayer = Callable[[WorldState, PendingEvent], bool]


def _flagged(state: WorldState, event: PendingEvent) -> bool:
    return event.needs_player


@dataclass(frozen=True)
class TimePassage:
    """In-world time that passed: from `started_s` to `ended_s`, with the pending events applied
    on the way, in time order. `interrupted_by` is the event that needed the player and stopped
    the clock at its due time (W10). `capped` means `MAX_EVENTS_PER_PASSAGE` events were applied
    and the clock stopped there, which only a runaway handler causes."""

    state: WorldState
    started_s: int
    ended_s: int
    fired: tuple[PendingEvent, ...] = field(default_factory=tuple)
    interrupted_by: PendingEvent | None = None
    capped: bool = False

    @property
    def elapsed_s(self) -> int:
        return self.ended_s - self.started_s


def advance_clock(
    state: WorldState,
    until_s: int,
    apply: EventHandler,
    *,
    needs_player: NeedsPlayer = _flagged,
    max_events: int = MAX_EVENTS_PER_PASSAGE,
    copy: bool = True,
) -> TimePassage:
    """Move the world clock to `until_s`, applying each pending event due on the way (W10).

    Events apply in time order (`WorldState.due_events`), each with the clock at its due time, or
    at the current time for one already overdue. An event an earlier one schedules inside the
    stretch applies in its turn. The first event that needs the player is applied and the clock
    stops at its due time: the action is cut short there and the scene starts there. Events due
    at the same second after it wait for the next stretch.

    `apply(state, event)` returns the new state with the event no longer pending, and must not
    move the clock or change the timeline. `needs_player(state, event)` decides, once the event
    has applied, whether it stops the clock; by default it reads `event.needs_player`, and the
    living world can decide from the state instead (guards arriving where the player no longer
    is aren't an interruption). The input state is never changed, unless the caller passes its
    own private copy with `copy=False`: copying a long story's state is most of a turn's own time.
    """
    if until_s < state.world_s:
        raise ValueError(f"time never runs backwards: {until_s} is before {state.world_s}")
    started = state.world_s
    timeline = state.timeline_id
    current = state.model_copy(deep=True) if copy else state
    fired: list[PendingEvent] = []
    while due := current.due_events(until_s):
        if len(fired) >= max_events:
            return TimePassage(current, started, current.world_s, tuple(fired), capped=True)
        event = due[0]
        at = max(current.world_s, event.due_s)
        current.world_s = at
        current = apply(current, event)
        if current.world_s != at or current.timeline_id != timeline:
            raise RuntimeError(f"applying event {event.id!r} moved the clock or the timeline")
        stored = current.pending_events.get(event.id)
        if stored is None or stored.status is EventStatus.PENDING:
            raise RuntimeError(f"applying event {event.id!r} left it pending")
        fired.append(stored)
        if needs_player(current, stored):
            return TimePassage(current, started, at, tuple(fired), interrupted_by=stored)
    current.world_s = until_s
    return TimePassage(current, started, until_s, tuple(fired))
