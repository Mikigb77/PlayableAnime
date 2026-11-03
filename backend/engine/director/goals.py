"""N2: goals belong to the player; leads are what the world offers.

The only ways a goal comes to exist are the player stating it (the intent's `goals`) or the player
taking up a lead the story offered (`responds_to` names an open lead). Nothing else in the director
touches goals: not events, not threads closing, not leads expiring. Leads expire on in-world time
(W10) and never overwrite a goal.
"""

from engine.context import TurnContext
from engine.contracts.intent import Intent
from engine.director.ids import IdProbe
from engine.director.turn import TurnFacts
from engine.state.records import Goal, GoalStatus, LeadStatus
from engine.state.world import WorldState, natural_key


def _same(a: str, b: str) -> bool:
    return " ".join(a.casefold().split()) == " ".join(b.casefold().split())


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
    active = [g for g in state.goals.values() if g.status is GoalStatus.ACTIVE]
    new: list[Goal] = []

    def known(text: str) -> bool:
        return any(_same(g.text, text) for g in [*active, *new])

    taken: list[str] = []
    for lead_id in sorted(facts.responded_leads, key=natural_key):
        lead = state.leads[lead_id]
        taken.append(lead_id)
        if any(g.lead_id == lead_id for g in state.goals.values()) or known(lead.text):
            continue
        new.append(Goal(id=ids.new("goal"), text=lead.text, set_turn=ctx.turn, lead_id=lead_id))
    for text in intent.goals:
        text = " ".join(text.split())
        if text and not known(text):
            new.append(Goal(id=ids.new("goal"), text=text, set_turn=ctx.turn))
    return new, taken


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
