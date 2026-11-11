"""S2: zero to four suggested choices, at least one of them away from the current thread.

Wait and observe are always offered on top (API.md `standing_actions`), and the player can turn
suggestions off. The director decides only how many and of which kinds; the narrator writes them.

- In an encounter: two ways to carry on with it, and one wild idea.
- When an event arrives that needs a decision: two ways to answer it, and one way to get on with
  the character's own life instead, since ignoring it is a choice too (W16).
- In a quiet scene: the current thread, something personal and a side matter, plus a wild idea
  once stall pressure is building. With no thread open, the thread choice gives way to a wild one.
- After a long run of scenes that took next to no time (`clock.clock_is_slow`, W10), a quiet
  scene's suggestions hold one way to let time pass: a fourth choice, or in place of the side
  matter when there are four already. The pace stays the player's: it is one choice among the
  others, never in an encounter or beside an event that needs a decision.
"""

from engine.context import TurnContext
from engine.contracts.direction import ChoiceKind, PlannedEvent, SuggestionPlan
from engine.director.pressure import Pressure

AWAY = (ChoiceKind.PERSONAL, ChoiceKind.SIDE, ChoiceKind.WILD)
MAX_CHOICES = 4


def plan_suggestions(
    ctx: TurnContext,
    *,
    pressure: Pressure,
    event: PlannedEvent | None,
    thread_id: str | None,
    time: bool = False,
) -> SuggestionPlan:
    """`time` is whether this scene may offer a way to let time pass (W10): the caller says so
    after a long run of scenes that took next to no time, where the scene has room for it."""
    if not ctx.settings.suggestions:
        return SuggestionPlan(count=0, kinds=[])
    quiet = False
    if pressure.encounter:
        kinds = [ChoiceKind.THREAD, ChoiceKind.THREAD, ChoiceKind.WILD]
    elif event is not None and event.needs_decision:
        kinds = [ChoiceKind.THREAD, ChoiceKind.THREAD, ChoiceKind.PERSONAL]
    elif thread_id is not None:
        quiet = True
        kinds = [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE]
        if pressure.building:
            kinds.append(ChoiceKind.WILD)
    else:
        quiet = True
        kinds = [ChoiceKind.PERSONAL, ChoiceKind.SIDE, ChoiceKind.WILD]
    if thread_id is None:
        # Nothing for a thread choice to follow, so it becomes something of the player's own.
        kinds = [ChoiceKind.PERSONAL if k is ChoiceKind.THREAD else k for k in kinds]
    if time and quiet:
        if len(kinds) < MAX_CHOICES:
            kinds.append(ChoiceKind.TIME)
        else:
            # Four already: it takes the side matter's place.
            side = kinds.index(ChoiceKind.SIDE) if ChoiceKind.SIDE in kinds else -1
            kinds[side] = ChoiceKind.TIME
    return SuggestionPlan(count=len(kinds), kinds=kinds, thread_id=thread_id)
