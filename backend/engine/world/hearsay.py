"""What a place is saying (W2, C6): the rumors someone who comes there later may hear.

Word reaches a place and everyone there hears it (`rumors.on_rumor`). Whoever comes later can
hear it too, since what has reached a place is what its people are saying: what the world did
while they were elsewhere, and what it says of their own deeds ("they say someone burned the
mill"). It reaches them softly (Miki, 2026-11-11: "don't force it ... let the story walk you
through hearing all that ... you might miss some rumors, that's also okay"). Nothing is heard
by arriving. `talk_of` is what a place has to tell someone, the director offers one piece of it
to a quiet scene now and then (`director.talk`), the narrator tells it only if the scene has
room, and `hear` records it once a scene did, so Memory shows only what the story told (C6).
"""

from engine.invariants import ancestry
from engine.state.records import Rumor
from engine.state.world import WorldState, natural_key
from engine.world.knowledge import character_learns
from engine.world.rumors import believes, knows_doer, knows_firsthand, names_actor
from engine.world.scheduling import World
from engine.world.tuning import TALK_FRESH_S


def talk_of(state: WorldState, character_id: str, place_id: str | None, at_s: int) -> list[Rumor]:
    """What a place is saying that the character hasn't heard, in the order they hear it: news
    to them first, then talk of what they already know for themselves, the newest first.

    A rumor is the talk of a place while it is fresh (`TALK_FRESH_S`) and has reached the place
    or one it lies in. A deed is told once, in its most accurate telling there, and never
    again to someone who has heard another telling of it.
    """
    around = set(ancestry(state.places, place_id))
    if not around:
        return []
    rumors = [r for r in state.rumors.values() if r.timeline_id == state.timeline_id]
    old_news = {r.deed_id for r in rumors if character_id in r.heard_at and r.deed_id}
    told: dict[str, Rumor] = {}
    for rumor in rumors:
        if character_id in rumor.heard_at or rumor.deed_id in old_news:
            continue
        if at_s - rumor.started_s > TALK_FRESH_S:
            continue
        if not around.intersection(rumor.reached_place_ids):
            continue
        key = rumor.deed_id or rumor.id
        kept = told.get(key)
        if kept is None or _better(rumor, kept):
            told[key] = rumor
    return sorted(
        told.values(),
        key=lambda r: (knows_firsthand(state, character_id, r), -r.started_s, natural_key(r.id)),
    )


def _better(rumor: Rumor, other: Rumor) -> bool:
    """Whether a telling of a deed is the one to hear, of two: the more accurate, else the
    older record."""
    if rumor.accuracy != other.accuracy:
        return rumor.accuracy > other.accuracy
    return natural_key(rumor.id) < natural_key(other.id)


def hear(w: World, character_id: str, rumor_id: str) -> bool:
    """W2, C6. A scene told someone a rumor, in place: they have heard it, believe it as a
    hearer there would, and learn who did a deed when it rightly names a doer they didn't
    know. False when the record doesn't hold the rumor or they had already heard it."""
    state = w.state
    rumor = state.rumors.get(rumor_id)
    if rumor is None or character_id in rumor.heard_at:
        return False
    deed = state.deeds.get(rumor.deed_id) if rumor.deed_id else None
    names_new_doer = names_actor(rumor, deed) and not knows_doer(state, character_id, deed)
    rumor.heard_at[character_id] = w.at_s
    if believes(state, character_id, rumor, rumor.accuracy):
        if character_id not in rumor.believed_by:
            rumor.believed_by.append(character_id)
        if names_new_doer:
            character_learns(w, character_id, deed, weight=rumor.accuracy / 100)
    return True
