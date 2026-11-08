"""N2: goals belong to the player; leads are what the world offers.

The only ways a goal comes to exist are the player stating it (the intent's `goals`) or the player
taking up a lead the story offered (`responds_to` names an open lead). A goal that says what an
active one already says, give or take case, accents and punctuation, isn't added again.

No goal is ever rewritten, and one closes only once it is over:

- the player drops it, or replaces it with a new one, in their own words (the intent's
  `dropped_goals`): abandoned;
- the thread of the lead it came from closes, or that of a goal merged into it: achieved when the
  player saw it through, failed when it failed or ended without them, abandoned when it was
  abandoned;
- the scene's update says play achieved it or made it impossible, or that it repeats an older goal
  (`engine.apply`, on a turn the player acted).

Leads expire on in-world time (W10) and never overwrite a goal.
"""

from engine.context import TurnContext
from engine.contracts.direction import ThreadChange
from engine.contracts.intent import Intent
from engine.director.ids import IdProbe
from engine.director.turn import TurnFacts
from engine.limits import normalize
from engine.state.records import Goal, GoalStatus, LeadStatus, Thread, ThreadStatus
from engine.state.world import WorldState, natural_key

# What a goal from a lead becomes when the lead's thread closes.
_WITH_THREAD = {
    ThreadStatus.RESOLVED: GoalStatus.ACHIEVED,
    ThreadStatus.FAILED: GoalStatus.FAILED,
    ThreadStatus.RESOLVED_WITHOUT_PLAYER: GoalStatus.FAILED,
    ThreadStatus.ABANDONED: GoalStatus.ABANDONED,
}


def same_goal(a: str, b: str) -> bool:
    """The same words, give or take case, accents and punctuation."""
    return normalize(a) == normalize(b)


def lead_thread(state: WorldState, goal: Goal) -> Thread | None:
    """The thread of the lead the goal came from, if it came from one with a thread."""
    lead = state.leads.get(goal.lead_id) if goal.lead_id else None
    return state.threads.get(lead.thread_id) if lead and lead.thread_id else None


def carried_by(state: WorldState, goal: Goal) -> Goal | None:
    """The active goal that carries this one on: itself, or the goal it was merged into, in
    turn. None when that goal is closed."""
    seen: set[str] = set()
    while goal.status is GoalStatus.MERGED and goal.id not in seen:
        seen.add(goal.id)
        into = state.goals.get(goal.merged_into or "")
        if into is None:
            return None
        goal = into
    return goal if goal.status is GoalStatus.ACTIVE else None


def player_goals(
    state: WorldState,
    ctx: TurnContext,
    intent: Intent | None,
    facts: TurnFacts,
    ids: IdProbe,
) -> tuple[list[Goal], list[str]]:
    """The goals the player stated or accepted this turn, and the leads they took up."""
    if intent is None:
        return [], []
    dropped = set(intent.dropped_goals)
    active = [
        g for g in state.goals.values() if g.status is GoalStatus.ACTIVE and g.id not in dropped
    ]
    new: list[Goal] = []

    def known(text: str) -> bool:
        return any(same_goal(g.text, text) for g in [*active, *new])

    taken: list[str] = []
    for lead_id in sorted(facts.responded_leads, key=natural_key):
        lead = state.leads[lead_id]
        taken.append(lead_id)
        if any(g.lead_id == lead_id for g in state.goals.values()) or known(lead.text):
            continue
        new.append(Goal(id=ids.new("goal"), text=lead.text, set_turn=ctx.turn, lead_id=lead_id))
    for text in intent.goals:
        text = " ".join(text.split())
        if normalize(text) and not known(text):
            new.append(Goal(id=ids.new("goal"), text=text, set_turn=ctx.turn))
    return new, taken


def closed_goals(
    state: WorldState, intent: Intent | None, changes: list[ThreadChange]
) -> dict[str, GoalStatus]:
    """The active goals that are over this turn, by id: the ones the player dropped, and the ones
    whose lead's thread is closed, with this turn's thread `changes` counted. A goal merged into
    another passes its lead's thread on to the goal that carries it (`carried_by`)."""
    after = {c.thread_id: c.status for c in changes if c.status is not None}
    closed: dict[str, GoalStatus] = {}
    for goal_id in intent.dropped_goals if intent is not None else []:
        goal = state.goals.get(goal_id)
        if goal is not None and goal.status is GoalStatus.ACTIVE:
            closed[goal_id] = GoalStatus.ABANDONED
    for goal in sorted(state.goals.values(), key=lambda g: natural_key(g.id)):
        thread = lead_thread(state, goal)
        status = after.get(thread.id, thread.status) if thread is not None else None
        if status is None or not status.closed:
            continue
        carrier = carried_by(state, goal)
        if carrier is not None and carrier.id not in closed:
            closed[carrier.id] = _WITH_THREAD[status]
    return closed


def expired_leads(state: WorldState, taken: list[str]) -> list[str]:
    """Open leads whose in-world expiry has passed and that the player didn't just take up."""
    return sorted(
        (
            lead.id
            for lead in state.leads.values()
            if lead.status is LeadStatus.OPEN
            and lead.expires_s is not None
            and lead.expires_s <= state.world_s
            and lead.id not in taken
        ),
        key=natural_key,
    )
