"""What the story has yet to tell the player of its own start (G1, C6).

A drafted story begins with people the character already knows, goals of theirs and threads
already running. The draft's screen shows one only when the player's own words name it (G1): the
rest is the story's surprise. It is on the record all the same, the character knows it and the
story is told with it, so nothing here changes what a model is handed. Only the player's
screens hold it back, until the story tells it.

`WorldState.untold` lists what is held back, by key (`key`): a person, a goal or a thread. A key
leaves the list, for good, when what the player reads names what it stands for
(`graph.drafting.openers.told_by`, which reads a scene much as it reads a premise), or when play
reaches it another way (`reached`): the story moves or closes the goal, or the player takes the
thread up. A story that wasn't drafted, or was started before this, holds nothing back.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from engine.state.records import GoalStatus
from engine.state.world import WorldState

PERSON = "person"
GOAL = "goal"
THREAD = "thread"


def key(kind: str, record_id: str) -> str:
    return f"{kind}:{record_id}"


@dataclass(frozen=True)
class Untold:
    """The ids of what is held back, by kind."""

    people: frozenset[str] = frozenset()
    goals: frozenset[str] = frozenset()
    threads: frozenset[str] = frozenset()


def held(state: WorldState) -> Untold:
    """What the player's screens hold back of this state."""
    by_kind: dict[str, set[str]] = {PERSON: set(), GOAL: set(), THREAD: set()}
    for entry in state.untold:
        kind, _, record_id = entry.partition(":")
        if kind in by_kind:
            by_kind[kind].add(record_id)
    return Untold(
        people=frozenset(by_kind[PERSON]),
        goals=frozenset(by_kind[GOAL]),
        threads=frozenset(by_kind[THREAD]),
    )


def reached(state: WorldState) -> list[str]:
    """The keys on the list that play has reached without a word of a scene naming them: a goal
    the story moved or closed, a thread the player took up, and someone who carries the story
    on as its player character (N6). A key whose record is gone counts too, since it holds
    nothing back."""
    found = []
    for entry in state.untold:
        kind, _, record_id = entry.partition(":")
        if kind == PERSON:
            over = record_id not in state.characters or record_id == state.player_id
        elif kind == GOAL:
            goal = state.goals.get(record_id)
            over = (
                goal is None
                or goal.status is not GoalStatus.ACTIVE
                or goal.moved_turn is not None
                or bool(goal.progress)
            )
        elif kind == THREAD:
            thread = state.threads.get(record_id)
            over = thread is None or thread.taken_up_turn is not None
        else:
            over = True
        if over:
            found.append(entry)
    return found


def tell(state: WorldState, keys: Iterable[str]) -> WorldState:
    """The state with `keys` off the list: the same one when none of them is on it."""
    told = set(keys) & set(state.untold)
    if not told:
        return state
    return state.model_copy(update={"untold": [k for k in state.untold if k not in told]})
