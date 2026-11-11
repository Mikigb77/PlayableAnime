"""W16: where a new event comes from, in order: the world's own state first, then the deck.

1. Due: pending events and clocks that came due (E2). Those are read in `engine.director.due`,
   because they come in whatever the pressure is.
2. Agenda: a key NPC or a faction acting on its plans comes to the player character (W6, E3).
3. Thread: a dormant thread returns (N1).
4. Emergence: a character or faction the world created and the player hasn't met yet (W15).
5. Deck: a fresh, seeded draw (E4).

The model never picks the event type (W16). A source used recently is passed over, so the same NPC
or thread doesn't come knocking every time. Titles are shown to the player, so they only name what
the player character already knows (C6); briefs go to the narrator and never hold secrets.

What comes fits the time that passed (W10): `clock.sizes_in_time` says which sizes of event the
story clock leaves room for since the last ones, and every source keeps to them.
"""

from dataclasses import dataclass, field

from engine.context import TurnContext
from engine.contracts.direction import EventKind, EventSource, PlannedEvent, Theme
from engine.director import deck, rules
from engine.director.clock import ALL_SIZES
from engine.director.deck import Card, CastRole
from engine.director.themes import fits
from engine.limits import is_adult
from engine.rng import SeededRng
from engine.state.cast import Activity, Character, Faction, FactionStatus, Prominence
from engine.state.records import ClockStatus, OriginKind, Thread, ThreadKind, ThreadStatus
from engine.state.world import EventSize, WorldState, natural_key

FRIENDLY = 30  # affinity from which an NPC comes as a friend, and below minus which as a foe
CLOSE_AFFINITY = 20


THREAD_EVENT_KIND: dict[ThreadKind, EventKind] = {
    ThreadKind.MYSTERY: EventKind.DISCOVERY,
    ThreadKind.THREAT: EventKind.ARRIVAL,
    ThreadKind.RIVALRY: EventKind.RIVAL,
    ThreadKind.ROMANCE: EventKind.VISITOR,
    ThreadKind.AMBITION: EventKind.OFFER,
    ThreadKind.DEBT: EventKind.ARRIVAL,
    ThreadKind.QUEST: EventKind.OFFER,
}


@dataclass(frozen=True)
class Pick:
    """An event the director chose, with what recording it needs: the thread it opens when
    `event.thread_id` is None, how long it waits for the player before it plays out, and whether
    its thread lingers as dormant when ignored instead of closing."""

    event: PlannedEvent
    key: str
    window_s: int
    lingers: bool = False
    lead: bool = False
    thread_kind: ThreadKind | None = None
    thread_title: str = ""
    involved_ids: list[str] = field(default_factory=list)


def thread_themes(thread: Thread) -> frozenset[Theme]:
    return frozenset({Theme.ROMANCE}) if thread.kind is ThreadKind.ROMANCE else frozenset()


def here(state: WorldState) -> str | None:
    return state.player.location_id or state.scene.place_id


def _near(state: WorldState) -> set[str]:
    """The player character's place, its parent and its siblings."""
    place_id = here(state)
    if place_id is None:
        return set()
    near = {place_id}
    place = state.places.get(place_id)
    if place is not None and place.parent_id is not None:
        near.add(place.parent_id)
        near.update(p.id for p in state.places.values() if p.parent_id == place.parent_id)
    return near


def _knows(state: WorldState, record: Character | Faction) -> bool:
    player = state.player_id
    return player in record.known_by or (isinstance(record, Character) and player in record.met_by)


def existing_thread(state: WorldState, subject_id: str) -> Thread | None:
    """The live thread that involves someone, open before dormant, most recent first."""
    live = [
        t for t in state.threads.values() if subject_id in t.involved_ids and not t.status.closed
    ]
    live.sort(
        key=lambda t: (t.status is not ThreadStatus.OPEN, -t.last_active_turn, natural_key(t.id))
    )
    return live[0] if live else None


def cast_for(state: WorldState, role: CastRole, rng: SeededRng, *, adults_only: bool) -> list[str]:
    """E4: an existing character the player character knows and who is nearby, to reuse before
    the narrator invents someone. Only adults for a romance event (F3)."""
    if role is CastRole.NONE:
        return []
    player = state.player_id
    near = _near(state)
    present = set(state.scene.present_ids)
    pool: list[Character] = []
    weights: list[float] = []
    for npc in sorted(state.npcs(), key=lambda c: natural_key(c.id)):
        if not npc.alive or npc.activity is not Activity.ACTIVE or player not in npc.met_by:
            continue
        if adults_only and not is_adult(npc):
            continue
        if npc.id not in present and npc.location_id not in near:
            continue
        attitude = npc.attitude_toward(player)
        if role is CastRole.CLOSE:
            weight = attitude.affinity if attitude.affinity >= CLOSE_AFFINITY else 0
        elif role is CastRole.HOSTILE:
            weight = -attitude.affinity if attitude.affinity <= -CLOSE_AFFINITY else 0
            weight = weight or (CLOSE_AFFINITY if attitude.grudges else 0)
        else:
            weight = 1
        if weight > 0:
            pool.append(npc)
            weights.append(float(weight))
    if not pool:
        return []
    return [rng.weighted(pool, weights).id]


def _agenda(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    recent: list[str],
    sizes: frozenset[EventSize],
) -> Pick | None:
    """A key NPC acting on their plans is a personal event, and a faction a local one."""
    player = state.player_id
    options: list[Character | Faction] = []
    npcs = state.npcs() if EventSize.PERSONAL in sizes else []
    factions = state.factions.values() if EventSize.LOCAL in sizes else []
    for npc in sorted(npcs, key=lambda c: natural_key(c.id)):
        if (
            npc.alive
            and npc.activity is Activity.ACTIVE
            and npc.prominence is Prominence.KEY
            and npc.agenda is not None
            and f"npc:{npc.id}" not in recent
            and _knows(state, npc)
        ):
            options.append(npc)
    for faction in sorted(factions, key=lambda f: natural_key(f.id)):
        if (
            faction.activity is not Activity.ACTIVE
            or faction.status is FactionStatus.DESTROYED
            or not faction.goal
            or f"faction:{faction.id}" in recent
        ):
            continue
        planning = any(
            c.owner_id == faction.id and c.status is ClockStatus.RUNNING
            for c in state.clocks.values()
        )
        tied = state.player.member_of(faction.id) or faction.threat > 0 or _knows(state, faction)
        if planning and tied:
            options.append(faction)
    if not options:
        return None
    actor = rng.choice(options)
    window = rules.SOURCE_WINDOW_S
    if isinstance(actor, Character):
        affinity = actor.attitude_toward(player).affinity
        kind = (
            EventKind.OFFER
            if affinity >= FRIENDLY
            else EventKind.RIVAL
            if affinity <= -FRIENDLY
            else EventKind.VISITOR
        )
        thread = existing_thread(state, actor.id)
        goal = actor.agenda.goal if actor.agenda else ""
        return Pick(
            event=PlannedEvent(
                size=EventSize.PERSONAL,
                kind=kind,
                source=EventSource.AGENDA,
                source_id=actor.id,
                title=f"{actor.name} seeks you out",
                brief=(
                    f"{actor.name} acts on their own plans ({goal}) and comes to the character "
                    "to ask, offer, warn or demand, as their temperament and their feelings "
                    "about the character suggest."
                ),
                thread_id=thread.id if thread else None,
                cast_ids=[actor.id],
                place_id=here(state),
                consequence=f"Left without an answer, {actor.name} goes ahead without the "
                "character, and remembers.",
            ),
            key=f"npc:{actor.id}",
            window_s=window[EventSize.PERSONAL.value],
            lingers=True,
            thread_kind=ThreadKind.RIVALRY if affinity <= -FRIENDLY else ThreadKind.QUEST,
            thread_title=f"{actor.name}'s plans",
            involved_ids=[player, actor.id],
        )
    member = state.player.member_of(actor.id)
    kind = (
        EventKind.OFFER if member else EventKind.RIVAL if actor.threat >= 2 else EventKind.ARRIVAL
    )
    known = _knows(state, actor) or member
    leaders = [
        i
        for i in actor.leader_ids
        if i in state.characters and state.characters[i].alive and i != player
    ]
    thread = existing_thread(state, actor.id)
    return Pick(
        event=PlannedEvent(
            size=EventSize.LOCAL,
            kind=kind,
            source=EventSource.AGENDA,
            source_id=actor.id,
            title=f"Word from {actor.name}" if known else "Someone takes an interest in you",
            brief=(
                f"{actor.name} moves on its goal ({actor.goal}), and the move reaches the "
                "character: a summons, a demand, an envoy or a warning, as the faction's nature "
                "and situation suggest (W5)."
            ),
            thread_id=thread.id if thread else None,
            cast_ids=leaders[:1],
            place_id=here(state),
            consequence=f"Unanswered, {actor.name} takes the silence as an answer and acts on it.",
        ),
        key=f"faction:{actor.id}",
        window_s=window[EventSize.LOCAL.value],
        lingers=True,
        thread_kind=(
            ThreadKind.QUEST
            if member
            else ThreadKind.THREAT
            if actor.threat >= 2
            else ThreadKind.MYSTERY
        ),
        thread_title=f"{actor.name}'s designs" if known else "Someone's interest in you",
        involved_ids=[player, actor.id, *leaders[:1]],
    )


def _thread_size(thread: Thread) -> EventSize:
    return EventSize.LOCAL if thread.kind is ThreadKind.THREAT else EventSize.PERSONAL


def _dormant_thread(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    allowed: frozenset[Theme],
    recent: list[str],
    sizes: frozenset[EventSize],
) -> Pick | None:
    candidates = [
        t
        for t in sorted(state.threads.values(), key=lambda t: natural_key(t.id))
        if t.status is ThreadStatus.DORMANT
        and ctx.turn - t.last_active_turn >= rules.RETURN_AFTER_TURNS
        and f"thread:{t.id}" not in recent
        and fits(thread_themes(t), allowed)
        and _thread_size(t) in sizes
    ]
    if not candidates:
        return None
    weights = [1 + min(10, max(0, ctx.turn - t.last_active_turn) / 10) for t in candidates]
    thread = rng.weighted(candidates, weights)
    known = state.player_id in thread.known_by
    size = _thread_size(thread)
    romance = Theme.ROMANCE in thread_themes(thread)
    cast = [
        i
        for i in thread.involved_ids
        if i != state.player_id
        and i in state.characters
        and state.characters[i].alive
        and (not romance or is_adult(state.characters[i]))  # F3
    ][:2]
    return Pick(
        event=PlannedEvent(
            size=size,
            kind=THREAD_EVENT_KIND[thread.kind],
            source=EventSource.THREAD,
            source_id=thread.id,
            title=thread.title if known else "Something from the past returns",
            brief=(
                f"A thread that went quiet comes back into the character's life: {thread.title}. "
                f"{thread.stakes} It returns with something new that needs an answer."
            ).strip(),
            themes=sorted(thread_themes(thread)),
            thread_id=thread.id,
            cast_ids=cast,
            place_id=here(state),
            consequence="Left alone again, it goes on without the character.",
        ),
        key=f"thread:{thread.id}",
        window_s=rules.SOURCE_WINDOW_S[size.value],
        lingers=True,
    )


def _emerging(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    recent: list[str],
    sizes: frozenset[EventSize],
) -> Pick | None:
    """A newcomer in person is a personal event, and word of a new power a local one."""
    player = state.player_id
    npcs = state.npcs() if EventSize.PERSONAL in sizes else []
    factions = state.factions.values() if EventSize.LOCAL in sizes else []
    options: list[Character | Faction] = [
        c
        for c in sorted(npcs, key=lambda c: natural_key(c.id))
        if c.alive
        and c.activity is Activity.ACTIVE
        and c.origin is not None
        and c.origin.kind is OriginKind.EMERGENCE
        and player not in c.met_by
        and f"npc:{c.id}" not in recent
    ]
    options += [
        f
        for f in sorted(factions, key=lambda f: natural_key(f.id))
        if f.origin is not None
        and f.origin.kind in (OriginKind.EMERGENCE, OriginKind.SUCCESSOR)
        and f.status is not FactionStatus.DESTROYED
        and f.activity is Activity.ACTIVE
        and player not in f.known_by
        and f"faction:{f.id}" not in recent
    ]
    if not options:
        return None
    newcomer = rng.choice(options)
    why = newcomer.origin.text if newcomer.origin and newcomer.origin.text else ""
    if isinstance(newcomer, Character):
        hostile = newcomer.attitude_toward(player).affinity <= -FRIENDLY
        return Pick(
            event=PlannedEvent(
                size=EventSize.PERSONAL,
                kind=EventKind.RIVAL if hostile else EventKind.ARRIVAL,
                source=EventSource.EMERGENCE,
                source_id=newcomer.id,
                title="A stranger appears",
                brief=(
                    f"{newcomer.name} enters the character's life"
                    + (f" ({why})" if why else "")
                    + ", with reasons of their own."
                ),
                cast_ids=[newcomer.id],
                place_id=here(state),
                consequence=f"Unmet and unanswered, {newcomer.name} makes their own move.",
            ),
            key=f"npc:{newcomer.id}",
            window_s=rules.SOURCE_WINDOW_S[EventSize.PERSONAL.value],
            lingers=True,
            thread_kind=ThreadKind.THREAT if hostile else ThreadKind.MYSTERY,
            thread_title="A stranger arrives",
            involved_ids=[player, newcomer.id],
        )
    return Pick(
        event=PlannedEvent(
            size=EventSize.LOCAL,
            kind=EventKind.RUMOR,
            source=EventSource.EMERGENCE,
            source_id=newcomer.id,
            title="Word of a new power",
            brief=(
                f"Word reaches the character of {newcomer.name}"
                + (f", which rose from {why}" if why else "")
                + f". {newcomer.description}"
            ).strip(),
            place_id=here(state),
            consequence=f"Unheeded, {newcomer.name} grows without the character in its plans.",
        ),
        key=f"faction:{newcomer.id}",
        window_s=rules.SOURCE_WINDOW_S[EventSize.LOCAL.value],
        lingers=True,
        thread_kind=ThreadKind.MYSTERY,
        thread_title=f"The rise of {newcomer.name}",
        involved_ids=[player, newcomer.id],
    )


def from_card(state: WorldState, card: Card, rng: SeededRng) -> Pick:
    romance = Theme.ROMANCE in card.themes
    return Pick(
        event=PlannedEvent(
            size=card.size,
            kind=card.kind,
            source=EventSource.DECK,
            card_id=card.id,
            title=card.title,
            brief=card.brief,
            themes=sorted(card.themes),
            cast_ids=cast_for(state, card.cast, rng.child("cast"), adults_only=romance),
            place_id=here(state),
            needs_decision=card.needs_decision,
            consequence=card.consequence,
        ),
        key=card.source_key,
        window_s=card.window_s,
        lingers=card.lingers,
        lead=card.lead,
        thread_kind=card.thread_kind if card.needs_decision else None,
        thread_title=card.title,
        involved_ids=[state.player_id],
    )


def pick_event(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    allowed: frozenset[Theme],
    *,
    recent: list[str],
    decision_only: bool = True,
    sizes: frozenset[EventSize] = ALL_SIZES,
) -> Pick | None:
    """The first source in W16's order that has something fitting, after the due events, among
    the `sizes` the time since the last events leaves room for (`clock.sizes_in_time`)."""
    if not sizes:
        return None
    pick = (
        _agenda(state, ctx, rng.child("agenda"), recent, sizes)
        or _dormant_thread(state, ctx, rng.child("thread"), allowed, recent, sizes)
        or _emerging(state, ctx, rng.child("emergence"), recent, sizes)
    )
    if pick is not None:
        return pick
    card = deck.draw(
        state,
        ctx,
        rng.child("deck"),
        allowed,
        recent=recent,
        decision_only=decision_only,
        sizes=sizes,
    )
    return from_card(state, card, rng.child("deck")) if card is not None else None
