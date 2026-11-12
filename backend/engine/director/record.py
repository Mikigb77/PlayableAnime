"""`record`: write a director plan's updates into the state (`pipeline.record_direction`).

Mechanical on purpose: every decision was made in `direct`. Call it once per turn, right after
`direct` and before anything else changes the state (the turn graph does), so the plan's
provisional ids are still free and the plan the narrator sees names the records as saved. If one
was taken anyway, it gets a fresh id and the references inside the updates follow it, so a plan
never overwrites a record; the plan's own fields (its event's thread, say) keep the old id.
"""

import re

from engine.context import TurnContext
from engine.contracts.direction import DirectorPlan
from engine.director.due import is_director_event
from engine.state.records import EventStatus, GoalStatus, LeadStatus, ThreadStatus
from engine.state.world import _KEYED_COLLECTIONS, WorldState

_NUMBERED = re.compile(r"^(?P<prefix>.+)-(?P<number>\d+)$")


def _taken(state: WorldState, record_id: str) -> bool:
    return any(record_id in getattr(state, f) for f in _KEYED_COLLECTIONS)


def _claim(state: WorldState, record_id: str, remap: dict[str, str]) -> str:
    """The provisional id if it is still free, else a fresh one with the same prefix."""
    match = _NUMBERED.match(record_id)
    prefix = match["prefix"] if match else record_id
    if _taken(state, record_id):
        fresh = state.new_id(prefix)
        remap[record_id] = fresh
        return fresh
    if match:
        state.id_counters[prefix] = max(state.id_counters.get(prefix, 0), int(match["number"]))
    return record_id


def record(state: WorldState, plan: DirectorPlan, ctx: TurnContext) -> WorldState:
    updates = plan.updates
    new = state.model_copy(deep=True)
    new.director = updates.memory.model_copy(deep=True)
    remap: dict[str, str] = {}

    def follow(record_id: str | None) -> str | None:
        return remap.get(record_id, record_id) if record_id is not None else None

    for thread in updates.new_threads:
        thread = thread.model_copy(deep=True)
        thread.id = _claim(new, thread.id, remap)
        new.threads[thread.id] = thread

    for scheduled in updates.schedule:
        event = scheduled.model_copy(deep=True)
        event.id = _claim(new, event.id, remap)
        if "thread_id" in event.payload:
            event.payload["thread_id"] = follow(event.payload["thread_id"])
        inner = event.payload.get("event")
        if isinstance(inner, dict) and "thread_id" in inner:
            inner["thread_id"] = follow(inner["thread_id"])
        if event.origin is not None:
            event.origin.ref_id = follow(event.origin.ref_id)
        new.pending_events[event.id] = event

    for lead in updates.new_leads:
        lead = lead.model_copy(deep=True)
        lead.id = _claim(new, lead.id, remap)
        lead.thread_id = follow(lead.thread_id)
        new.leads[lead.id] = lead

    for change in updates.thread_changes:
        thread = new.threads.get(follow(change.thread_id) or "")
        if thread is None:
            continue
        if change.status is not None and change.status is not thread.status:
            thread.status = change.status
            if change.status.closed:
                thread.closed_turn = ctx.turn
            elif change.status is ThreadStatus.OPEN:
                thread.last_active_turn = ctx.turn
        if change.active:
            thread.last_active_turn = ctx.turn
        if change.taken_up:
            thread.taken_up_turn = ctx.turn

    for event_id in updates.cancel_ids:
        event = new.pending_events.get(event_id)
        if event is None:
            continue
        # A director event the clock applied during this very turn changed nothing by itself
        # (director events only mark themselves applied), so the player's action can still
        # overtake it.
        overtaken = (
            is_director_event(event)
            and event.status is EventStatus.APPLIED
            and event.applied_turn == ctx.turn
        )
        if event.status is EventStatus.PENDING or overtaken:
            event.status = EventStatus.CANCELLED
            event.applied_turn = None
            event.applied_s = None
    for event_id in updates.applied_ids:
        event = new.pending_events.get(event_id)
        if event is not None and event.status is EventStatus.PENDING:
            event.status = EventStatus.APPLIED
            event.applied_turn = ctx.turn
            event.applied_s = new.world_s

    for lead_id in updates.expired_lead_ids:
        lead = new.leads.get(lead_id)
        if lead is not None and lead.status is LeadStatus.OPEN:
            lead.status = LeadStatus.EXPIRED
    for lead_id in updates.taken_lead_ids:
        lead = new.leads.get(lead_id)
        if lead is not None and lead.status is LeadStatus.OPEN:
            lead.status = LeadStatus.TAKEN

    for goal_id, status in updates.closed_goals.items():
        goal = new.goals.get(goal_id)
        if goal is not None and goal.status is GoalStatus.ACTIVE:
            goal.status = status
            goal.closed_turn = ctx.turn
            goal.closed_s = new.world_s
    for goal in updates.new_goals:
        goal = goal.model_copy(deep=True)
        goal.id = _claim(new, goal.id, remap)
        new.goals[goal.id] = goal

    return new
