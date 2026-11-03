"""In-world time (W10): how long each kind of action may take.

The interpret step proposes a duration; code bounds it by the kind of action, so a sword exchange
takes seconds and a night's sleep hours, never a fixed amount per turn. A time skip takes whatever
the player asks for, within a generous cap (E7).
"""

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.contracts.intent import ActionKind

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
    ActionKind.TIME_SKIP: (HOUR, 1000 * YEAR),
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
