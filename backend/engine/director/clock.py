"""W16, W10: what comes in fits the time that passed on the story's clock.

Stall pressure counts the player's quiet turns: it says when a scene needs something (W16). What
that may be is the clock's to say, never the turn count's, so a player who plays a hundred short
scenes inside one hour gets what fits an hour (Miki, 2026-11-11: "100 scenes in the same hour
should get events that make sense for this time lap"):

- one of life's events needs hours since the last, a local one days and a world one weeks
  (`sizes_in_time`, `rules.EVENT_GAP_S`);
- a small thing, a moment or some talk of the place, needs minutes (`small_thing_fits`,
  `rules.SMALL_GAP_S`);
- and sooner than that, nothing new comes in: the scene is the player's own.

Events that came due (E2), what a time skip or the road rolls (E7, W10) and what an encounter
brings come when they come; the clock only spaces what the director adds.

The pace is the player's to choose, so nothing here moves the clock on. After a long run of
scenes that took next to no time, the suggestions may hold one way to let time pass
(`clock_is_slow`, S2): an offer, never a push.
"""

from engine.director import rules
from engine.state.world import DirectorState, EventSize

ALL_SIZES = frozenset(EventSize)
_SMALLEST_FIRST = list(EventSize)


def _within(now_s: int, at_s: int, gap_s: int) -> bool:
    """Whether `at_s` is less than `gap_s` behind the clock. A time ahead of the clock, after a
    return to an earlier time (W10a), is behind nothing."""
    return 0 <= now_s - at_s < gap_s


def sizes_in_time(memory: DirectorState, now_s: int) -> frozenset[EventSize]:
    """The sizes of event the story clock leaves room for, from when the last event of each
    size came in (`DirectorState.last_event_s`).

    Two events are never closer together than the smaller of them needs: hours for a personal
    one, days for a local one, weeks for a world one. So a hundred scenes inside one hour hold
    one of life's events at most, and a flood isn't followed by bandits the same afternoon. A
    story with no event yet has room for any.
    """
    fitting = set()
    for size in EventSize:
        for last, at_s in memory.last_event_s.items():
            smaller = min(size, last, key=_SMALLEST_FIRST.index)
            if _within(now_s, at_s, rules.EVENT_GAP_S[smaller.value]):
                break
        else:
            fitting.add(size)
    return frozenset(fitting)


def small_thing_fits(memory: DirectorState, now_s: int) -> bool:
    """Whether the clock leaves room for a small thing of the moment: minutes since the last
    one, and since the last event (`rules.SMALL_GAP_S`), so a talk of ten minutes is not broken
    into by something at every other line."""
    latest = list(memory.last_event_s.values())
    if memory.last_small_s is not None:
        latest.append(memory.last_small_s)
    return not any(_within(now_s, at_s, rules.SMALL_GAP_S) for at_s in latest)


def clock_after(memory: DirectorState, now_s: int) -> list[int]:
    """The story's clock at the end of each of the last scenes, this one last
    (`rules.SLOW_CLOCK_SCENES` of them at most)."""
    return [*memory.recent_clock, now_s][-rules.SLOW_CLOCK_SCENES :]


def clock_is_slow(ends: list[int]) -> bool:
    """S2, W10. Whether a long run of scenes took next to no time: `rules.SLOW_CLOCK_SCENES` in
    a row that all ended within `rules.SLOW_CLOCK_S` of each other. A clock that jumped in that
    run, on or back (W10a), is not a slow one."""
    if len(ends) < rules.SLOW_CLOCK_SCENES:
        return False
    return max(ends) - min(ends) < rules.SLOW_CLOCK_S
