"""Children born when they are due (N6, W10).

A pregnancy is `Character.expecting` on whoever carries the child, set by the narrator when a
scene makes it so (`engine.apply`). Its birth is a pending event at the due time, kept pending by
`ensure_births` at the start of every catch-up. When it falls due the child is born into the
world, if the one who carries them is alive then; if they died first, the child never is. A birth
to the player character, or with the player character there as the other parent, stops the clock
for them (W10).
"""

from engine.state.cast import Character, DeathCertainty, Prominence
from engine.state.records import EventStatus, Origin, OriginKind, PendingEvent
from engine.state.world import WorldState
from engine.world.scheduling import Kind, World, by_id, pending, schedule

# How much of the carrier's name a newborn's placeholder name keeps, so it stays a `Name`.
NAME_ROOM = 180


def ensure_births(w: World) -> None:
    """Every living character who carries a child has its birth pending at the due time. A
    birth the world never caught up on applies first, at its own time."""
    for carrier in by_id(w.state.characters.values()):
        expecting = carrier.expecting
        if expecting is None or not carrier.alive:
            continue
        if pending(w.state, Kind.BIRTH, parent_id=carrier.id, due_s=expecting.due_s):
            continue
        other = w.state.characters.get(expecting.other_parent_id or "")
        schedule(
            w,
            Kind.BIRTH,
            expecting.due_s,
            title=f"{carrier.name}'s child is born",
            subject_ids=[carrier.id, *([other.id] if other else [])],
            place_id=carrier.location_id,
            payload={"parent_id": carrier.id, "due_s": expecting.due_s},
            origin=Origin(kind=OriginKind.BIRTH, ref_id=carrier.id),
            overdue=True,
        )


def on_birth(w: World, event: PendingEvent) -> bool:
    """The child is born, if the one who carries them lives. True if it needs the player
    character: they gave birth, or they are the other parent and there. A birth that doesn't
    happen is cancelled, so nobody is told of it."""
    state = w.state
    carrier = state.characters.get(str(event.payload.get("parent_id")))
    expecting = carrier.expecting if carrier is not None else None
    if carrier is None or expecting is None or expecting.due_s != event.payload.get("due_s"):
        # The pregnancy ended, or this is a later one, with its own birth.
        event.status = EventStatus.CANCELLED
        return False
    if not carrier.alive:
        event.status = EventStatus.CANCELLED
        if carrier.death_certainty is DeathCertainty.CONFIRMED:
            carrier.expecting = None  # the child died with them
        # A presumed death can turn out false (C1): if they come back, so does the birth.
        return False
    carrier.expecting = None
    other = state.characters.get(expecting.other_parent_id or "")
    parents = [carrier, *([other] if other is not None else [])]
    names = " and ".join(p.name for p in parents)
    # The parents there meet the child: the one giving birth, and the other if they are alive
    # and in the same place. A parent elsewhere learns of it as the story has them (C6).
    here = carrier.location_id
    there = [p.id for p in parents if p is carrier or (p.alive and here and p.location_id == here)]
    child = Character(
        id=state.new_id("npc"),
        # A placeholder until the story names them; a rename keeps it as an alias.
        name=_placeholder(state, carrier),
        prominence=Prominence.MINOR,
        description=f"A newborn, the child of {names}.",
        age=0,
        people_id=carrier.people_id,
        location_id=carrier.location_id,
        parent_ids=[p.id for p in parents],
        origin=Origin(kind=OriginKind.BIRTH, ref_id=event.id, text=f"Born to {names}."),
        known_by=list(there),
        met_by=there,
    )
    state.characters[child.id] = child
    event.subject_ids = list(dict.fromkeys([*event.subject_ids, child.id]))
    return state.player_id in child.met_by


def _placeholder(state: WorldState, carrier: Character) -> str:
    """ "Mira's child", then "Mira's child 2" for the next one still unnamed, within `Name`'s
    length."""
    base = f"{carrier.name[:NAME_ROOM]}'s child"
    taken = {c.name for c in state.characters.values()}
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    return name
