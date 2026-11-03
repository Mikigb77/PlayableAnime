"""C1: no state change without a recorded cause, checked in code.

The dead stay dead, destroyed factions and ruined places stay that way, stats stay within bounds,
nobody is nameless, fixed rules never change (G7) and rulings are never flipped (A9). One of them
can change only through a recorded deed or event whose mechanism the world bible allows:
resurrection magic, a presumed death that turns out false, a faction revival with survivors
(W15a), or rebuilding a ruined place (W7).

`engine.apply.apply_delta` enforces these as it applies a change. `check_transition` checks any
two states, however the second was made, so the turn graph can run it after every seam and catch a
bug in any workstream's code before a state is saved.
"""

from dataclasses import dataclass

from pydantic import ValidationError

from engine.state.bible import Resurrection
from engine.state.cast import (
    Character,
    CharacterStatus,
    DeathCertainty,
    Faction,
    FactionStatus,
    PlaceStatus,
)
from engine.state.records import Cause, CauseMechanism, CauseRef, EventStatus, StatusChange
from engine.state.world import WorldState

# Words a model uses when it has no name for someone (C1: no nameless characters).
PLACEHOLDER_NAMES = frozenset(
    {
        "?",
        "anonymous",
        "n/a",
        "nobody",
        "none",
        "someone",
        "somebody",
        "stranger",
        "the stranger",
        "a stranger",
        "unknown",
        "unnamed",
        "no name",
    }
)


@dataclass(frozen=True)
class Violation:
    """One broken invariant: what it is about, which rule, and how."""

    subject: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.subject}: {self.rule}: {self.detail}"


class InvariantError(ValueError):
    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        super().__init__("; ".join(str(v) for v in violations))


def is_real_name(name: str | None) -> bool:
    return bool(name and name.strip()) and name.strip().casefold() not in PLACEHOLDER_NAMES


def terminal_since(history: list[StatusChange], status: str) -> int:
    """The world second of the latest change into `status`, or 0 if the record started there."""
    times = [h.world_s for h in history if h.status == status]
    return max(times) if times else 0


def cause_problem(
    state: WorldState,
    cause: Cause,
    *,
    subject_id: str | None,
    since_s: int,
    allowed: set[CauseMechanism],
) -> str | None:
    """Why a cause can't justify a change, or None if it can.

    The cause must use an allowed mechanism and point at a deed or a fired event recorded in this
    state, on this timeline, that names the subject and happened no earlier than the change it
    undoes. Only engine code records deeds and fires events, so a narrator can't make one up.
    """
    if cause.mechanism not in allowed:
        names = ", ".join(sorted(m.value for m in allowed)) or "nothing"
        return f"{cause.mechanism.value} can't change this; only {names} can"
    if cause.ref_kind is CauseRef.DEED:
        deed = state.deeds.get(cause.ref_id)
        if deed is None:
            return f"no recorded deed {cause.ref_id!r}"
        when, timeline, named = deed.world_s, deed.timeline_id, [deed.actor_id, *deed.subject_ids]
    else:
        event = state.pending_events.get(cause.ref_id)
        if event is None:
            return f"no recorded event {cause.ref_id!r}"
        if event.status is EventStatus.CANCELLED or (
            event.status is EventStatus.PENDING and event.due_s > state.world_s
        ):
            return f"event {cause.ref_id!r} hasn't happened"
        when = event.applied_s if event.applied_s is not None else event.due_s
        timeline, named = event.timeline_id, event.subject_ids
    if timeline != state.timeline_id:
        return f"{cause.ref_kind.value} {cause.ref_id!r} is on another timeline"
    if subject_id is not None and subject_id not in named:
        return f"{cause.ref_kind.value} {cause.ref_id!r} doesn't involve {subject_id!r}"
    if when < since_s:
        return f"{cause.ref_kind.value} {cause.ref_id!r} came before the change it would undo"
    return None


def death_reversal_problem(state: WorldState, character: Character, cause: Cause) -> str | None:
    """Why a dead character can't come back by this cause, or None if they can (C1)."""
    allowed: set[CauseMechanism] = set()
    if character.death_certainty is DeathCertainty.PRESUMED:
        allowed.add(CauseMechanism.SURVIVED)
    if state.bible.medicine.resurrection is not Resurrection.NONE:
        allowed.add(CauseMechanism.RESURRECTION)
    if cause.mechanism is CauseMechanism.SURVIVED and CauseMechanism.SURVIVED not in allowed:
        return "a confirmed death never turns out false"
    if cause.mechanism is CauseMechanism.RESURRECTION and not allowed & {cause.mechanism}:
        return "nothing in this world brings back the dead"
    since = terminal_since(character.status_history, CharacterStatus.DEAD.value)
    return cause_problem(state, cause, subject_id=character.id, since_s=since, allowed=allowed)


def faction_revival_problem(
    state: WorldState, faction: Faction, cause: Cause, new_status: FactionStatus
) -> str | None:
    """Why a destroyed faction can't return this way, or None if it can (W15a). A revival starts
    weak, as rebuilding, and needs survivors: a living member or something on `survivors`."""
    if new_status is not FactionStatus.REBUILDING:
        return "a destroyed faction comes back only as rebuilding"
    survivors = faction.survivors or [
        c.id for c in state.characters.values() if c.alive and c.member_of(faction.id)
    ]
    if not survivors:
        return "nobody survived to carry it on"
    since = terminal_since(faction.status_history, FactionStatus.DESTROYED.value)
    return cause_problem(
        state, cause, subject_id=faction.id, since_s=since, allowed={CauseMechanism.REVIVAL}
    )


def place_rebuild_problem(state: WorldState, place_id: str, cause: Cause) -> str | None:
    """Why a ruined place can't recover this way, or None if it can (W7, W10a)."""
    place = state.places[place_id]
    since = terminal_since(place.status_history, PlaceStatus.RUINED.value)
    return cause_problem(
        state,
        cause,
        subject_id=place_id,
        since_s=since,
        allowed={CauseMechanism.REBUILD, CauseMechanism.LOCAL_REVERSAL},
    )


def _bounds(state: WorldState) -> list[Violation]:
    try:
        WorldState.model_validate(state.model_dump())
    except ValidationError as error:
        return [
            Violation(".".join(str(p) for p in e["loc"]) or "state", "bounds", e["msg"])
            for e in error.errors()
        ]
    return []


def check_state(state: WorldState) -> list[Violation]:
    """Invariants of one state: every value within bounds (re-validated, since engine code mutates
    copies without validation), no nameless characters, and references that point somewhere."""
    found = _bounds(state)
    for c in state.characters.values():
        if not is_real_name(c.name):
            found.append(Violation(f"character {c.id}", "named", f"{c.name!r} isn't a name"))
        if c.location_id is not None and c.location_id not in state.places:
            found.append(Violation(f"character {c.id}", "reference", "unknown location"))
        for m in c.memberships:
            if m.faction_id not in state.factions:
                found.append(
                    Violation(f"character {c.id}", "reference", f"unknown faction {m.faction_id}")
                )
        for position in c.sheet.ladders:
            ladder = state.bible.ladder(position.ladder_id)
            if ladder is None or position.rung >= len(ladder.rungs):
                found.append(
                    Violation(f"character {c.id}", "reference", f"no rung {position.rung}")
                )
    for f in state.factions.values():
        if f.parent_id is not None and f.parent_id not in state.factions:
            found.append(Violation(f"faction {f.id}", "reference", "unknown parent faction"))
    for p in state.places.values():
        if p.parent_id is not None and p.parent_id not in state.places:
            found.append(Violation(f"place {p.id}", "reference", "unknown parent place"))
    return found


def _reversal(
    subject: str, before_status: str, after_history: list[StatusChange], problem
) -> Violation | None:
    last = after_history[-1] if after_history else None
    if last is None or last.cause is None:
        return Violation(subject, "C1", f"left {before_status} with no recorded cause")
    reason = problem(last.cause)
    return Violation(subject, "C1", reason) if reason else None


def check_transition(before: WorldState, after: WorldState) -> list[Violation]:
    """Every C1 invariant between two states, however `after` was made."""
    found = check_state(after)

    for field in ("characters", "factions", "places", "deeds"):
        gone = set(getattr(before, field)) - set(getattr(after, field))
        found.extend(
            Violation(f"{field} {i}", "C1", "records are archived, never deleted")
            for i in sorted(gone)
        )
    if after.timeline_id != before.timeline_id:
        found.append(Violation("timeline", "W10a", "only a world rewind starts a new timeline"))
    elif after.world_s < before.world_s:
        found.append(Violation("world clock", "W10", "time never runs backwards"))

    for cid, old in before.characters.items():
        new = after.characters.get(cid)
        if new is None or old.status is not CharacterStatus.DEAD:
            continue
        subject = f"character {cid}"
        if new.status is not CharacterStatus.DEAD:
            v = _reversal(
                subject,
                "death",
                new.status_history,
                lambda cause, old=old: death_reversal_problem(after, old, cause),
            )
            if v:
                found.append(v)
        elif (
            old.death_certainty is DeathCertainty.CONFIRMED
            and new.death_certainty is DeathCertainty.PRESUMED
        ):
            found.append(Violation(subject, "C1", "a confirmed death never becomes presumed"))

    for fid, old in before.factions.items():
        new = after.factions.get(fid)
        if new is None or old.status is not FactionStatus.DESTROYED:
            continue
        if new.status is not FactionStatus.DESTROYED:
            v = _reversal(
                f"faction {fid}",
                "destruction",
                new.status_history,
                lambda cause, old=old, new=new: faction_revival_problem(
                    after, old, cause, new.status
                ),
            )
            if v:
                found.append(v)

    for pid, old in before.places.items():
        new = after.places.get(pid)
        if new is None or old.status is not PlaceStatus.RUINED:
            continue
        if new.status is not PlaceStatus.RUINED:
            v = _reversal(
                f"place {pid}",
                "ruin",
                new.status_history,
                lambda cause, pid=pid: place_rebuild_problem(after, pid, cause),
            )
            if v:
                found.append(v)

    fixed_before = {r.id: r for r in before.bible.rules if r.fixed}
    fixed_after = {r.id: r for r in after.bible.rules if r.fixed}
    for rid, rule in fixed_before.items():
        if fixed_after.get(rid) != rule:
            found.append(Violation(f"rule {rid}", "G7", "a fixed rule never changes"))
    for rid in sorted(set(fixed_after) - set(fixed_before)):
        found.append(Violation(f"rule {rid}", "G7", "no fixed rule is added after the start"))

    for cid, old in before.characters.items():
        new = after.characters.get(cid)
        if new is None:
            continue
        kept = {(r.topic, r.power_id): r for r in new.sheet.rulings}
        for ruling in old.sheet.rulings:
            now = kept.get((ruling.topic, ruling.power_id))
            if now is None or (now.answer, now.holds) != (ruling.answer, ruling.holds):
                found.append(
                    Violation(f"character {cid}", "A9", f"ruling {ruling.topic!r} was changed")
                )
    return found


def assert_valid_transition(before: WorldState, after: WorldState) -> None:
    violations = check_transition(before, after)
    if violations:
        raise InvariantError(violations)
