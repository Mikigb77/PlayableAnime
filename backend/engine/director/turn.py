"""What this turn did, read once from the state after `play_out` and from the player's intent.

The director runs after the steps played out (B5 step 3), so deeds, deaths and place changes are
already in the state with this turn's number on them. Everything here only reads.
"""

from dataclasses import dataclass

from engine.context import TurnContext
from engine.contracts.intent import Intent
from engine.contracts.resolution import Resolution
from engine.looks import LASTING_PLACE_STATUSES
from engine.state.cast import CharacterStatus, PlaceStatus
from engine.state.records import Deed, LeadStatus
from engine.state.sheet import Gain, Health
from engine.state.world import WorldState

GRAVE_HEALTH = (Health.BADLY_WOUNDED, Health.DYING)


@dataclass(frozen=True)
class TurnFacts:
    """This turn, as the director needs it.

    - `deeds`: deeds recorded this turn on this timeline, by anyone (W1, E5).
    - `died`: characters whose death was recorded this turn.
    - `gravely_hurt`: characters this turn's steps left badly wounded or dying.
    - `changed_places`: places that were ruined or occupied this turn, with the new status.
    - `gains`: growth recorded this turn, by character (A4, G19).
    - `responded_threads`, `responded_leads`: what the player's action took up, from the
      intent's `responds_to`, checked against the state (W16, N2).
    - `touched`: characters the player's deeds or the current encounter involve.
    """

    turn: int
    deeds: tuple[Deed, ...]
    died: frozenset[str]
    gravely_hurt: frozenset[str]
    changed_places: tuple[tuple[str, PlaceStatus], ...]
    gains: tuple[tuple[str, Gain], ...]
    responded_threads: frozenset[str]
    responded_leads: frozenset[str]
    touched: frozenset[str]

    @property
    def player_responded(self) -> bool:
        return bool(self.responded_threads or self.responded_leads)


def read_turn(
    state: WorldState, resolution: Resolution, ctx: TurnContext, intent: Intent | None
) -> TurnFacts:
    timeline = state.timeline_id
    deeds = tuple(
        sorted(
            (d for d in state.deeds.values() if d.turn == ctx.turn and d.timeline_id == timeline),
            key=lambda d: (d.world_s, d.id),
        )
    )
    died = frozenset(
        c.id
        for c in state.characters.values()
        if c.status is CharacterStatus.DEAD
        and any(
            h.status == CharacterStatus.DEAD.value
            and h.turn == ctx.turn
            and h.timeline_id == timeline
            for h in c.status_history
        )
    )
    gravely_hurt = frozenset(
        change.id
        for step in resolution.steps
        if not step.interrupted
        for change in step.effects.characters
        if change.condition is not None and change.condition.health in GRAVE_HEALTH
    )
    changed_places = tuple(
        (place.id, place.status)
        for place in sorted(state.places.values(), key=lambda p: p.id)
        if place.status in LASTING_PLACE_STATUSES
        and any(
            h.status == place.status.value and h.turn == ctx.turn and h.timeline_id == timeline
            for h in place.status_history
        )
    )
    gains = tuple(
        (c.id, gain)
        for c in sorted(state.characters.values(), key=lambda c: c.id)
        for gain in c.sheet.growth
        if gain.turn == ctx.turn and not gain.loss
    )

    responded = list(intent.responds_to) if intent is not None else []
    responded_leads = frozenset(
        i for i in responded if i in state.leads and state.leads[i].status is LeadStatus.OPEN
    )
    # Taking up a lead takes up the thread it belongs to.
    responded += [state.leads[i].thread_id for i in responded_leads if state.leads[i].thread_id]
    responded_threads = frozenset(
        i for i in responded if i in state.threads and not state.threads[i].status.closed
    )

    player_id = state.player_id
    touched: set[str] = set()
    for deed in deeds:
        if deed.actor_id == player_id:
            touched.update(deed.subject_ids)
    encounter = state.scene.encounter
    if encounter is not None:
        touched.update(encounter.opponent_ids)
    touched.discard(player_id)

    return TurnFacts(
        turn=ctx.turn,
        deeds=deeds,
        died=died,
        gravely_hurt=gravely_hurt,
        changed_places=changed_places,
        gains=gains,
        responded_threads=responded_threads,
        responded_leads=responded_leads,
        touched=frozenset(touched),
    )


def player_deeds(state: WorldState, facts: TurnFacts) -> list[Deed]:
    return [d for d in facts.deeds if d.actor_id == state.player_id]
