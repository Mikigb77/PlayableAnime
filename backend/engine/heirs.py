"""N6: heirs who can carry a story on after its ending.

An heir is a living child or grandchild of the player character whose story ended, or a child of
theirs (or of one of their children) still on the way. An unborn child counts only if the one who
carries them lives, and logic decides that first: alive and well, they are an heir; dead, never.
Only a carrier who is dying leaves it open, and a seeded roll settles it once per ending
(`unborn_lost`), so asking again gives the same answer (Miki, 2026-11-05). The roll is the world's
from then on: carrying the story on ends a pregnancy it lost (`settled`), so the world never has a
child born that was never offered.

An heir too young to act is played from the day they reach `AGE_OF_ACTION`. The world runs on to
that day first (`time_jump`): every pending event and the world's own processes apply on the way,
a child on the way is born when it is due, and everyone grows older by the years they lived
through. Nothing is told of those years but what the world recorded. The old player character's
time effects end before it, as they do when the story is carried on.
"""

from __future__ import annotations

from pydantic import Field

from engine.base import YEAR, EngineModel
from engine.context import TurnContext
from engine.kin import descendants
from engine.rng import SeededRng
from engine.state.cast import Character, CharacterStatus
from engine.state.records import EventStatus, OriginKind
from engine.state.sheet import Health
from engine.state.world import WorldState, natural_key
from engine.world import Kind, catch_up

# The age from which an heir is played: younger ones are played from that birthday on.
AGE_OF_ACTION = 16
# How likely a carrier at death's door brings their child into the world.
DYING_CARRIER_ODDS = 0.5
# How many stretches a time jump may take: each one ends where the world stopped its clock for an
# event the old player character would have played. More than this, and the jump ends anyway.
MAX_JUMP_PASSAGES = 400
UNBORN = "unborn:"
RELATIONS = {1: "child", 2: "grandchild", 3: "great-grandchild"}


class Heir(EngineModel):
    """Someone who can carry the story on, as the ending card offers them."""

    id: str = Field(description="Their character id, or `unborn:` and the carrier's id.")
    name: str
    generation: int = Field(ge=1, description="1 for a child, 2 for a grandchild.")
    age: int | None = Field(default=None, description="Now; None for a child not born yet.")
    unborn: bool = False
    carrier_id: str | None = Field(default=None, description="Who carries an unborn child.")
    due_s: int | None = Field(default=None, description="When an unborn child is due.")
    jump_s: int = Field(default=0, ge=0, description="The years to skip before they can act.")

    @property
    def relation(self) -> str:
        return RELATIONS.get(self.generation, "descendant")

    @property
    def years(self) -> int:
        """The time skipped before they can act, in whole years, rounded up."""
        return -(-self.jump_s // YEAR)


def heirs(state: WorldState, rng: SeededRng) -> list[Heir]:
    """The player character's heirs at their ending: children first, then grandchildren, then
    any child on the way, each in a stable order. `rng` settles a dying carrier's child once."""
    fallen = state.player_id
    lineage = descendants(state, fallen)
    found = []
    for heir_id, generation in sorted(lineage.items(), key=lambda i: (i[1], natural_key(i[0]))):
        heir = state.characters[heir_id]
        if heir.status is not CharacterStatus.ALIVE:
            continue
        # An age nobody recorded is taken as an adult's (F3 asks every adult for one).
        young = max(0, AGE_OF_ACTION - heir.age) if heir.age is not None else 0
        found.append(
            Heir(
                id=heir.id, name=heir.name, generation=generation, age=heir.age, jump_s=young * YEAR
            )
        )
    family = {fallen: 0, **lineage}
    lost = unborn_lost(state, rng)
    for carrier in sorted(state.characters.values(), key=lambda c: natural_key(c.id)):
        expecting = carrier.expecting
        if expecting is None or carrier.status is not CharacterStatus.ALIVE or carrier.id in lost:
            continue
        parents = [p for p in (carrier.id, expecting.other_parent_id) if p in family]
        if not parents:
            continue
        found.append(
            Heir(
                id=UNBORN + carrier.id,
                name=f"{carrier.name}'s child, not yet born",
                generation=min(family[p] for p in parents) + 1,
                unborn=True,
                carrier_id=carrier.id,
                due_s=expecting.due_s,
                jump_s=max(0, expecting.due_s - state.world_s) + AGE_OF_ACTION * YEAR,
            )
        )
    return found


def unborn_lost(state: WorldState, rng: SeededRng) -> set[str]:
    """The carriers whose child won't be born, of those the facts leave open: alive, but dying.
    A seeded roll, the same however often it is asked (A2)."""
    return {
        carrier.id
        for carrier in state.characters.values()
        if carrier.expecting is not None
        and carrier.status is CharacterStatus.ALIVE
        and carrier.sheet.condition.health is Health.DYING
        and not rng.child("unborn", carrier.id).chance(DYING_CARRIER_ODDS)
    }


def find(state: WorldState, heir_id: str, rng: SeededRng) -> Heir | None:
    return next((h for h in heirs(state, rng) if h.id == heir_id), None)


def settled(state: WorldState, rng: SeededRng) -> WorldState:
    """The world with each dying carrier's child as the ending's roll had it (`unborn_lost`, the
    same `rng`): a child the roll lost won't be born. The same state when the roll lost none, and a
    new one otherwise."""
    lost = unborn_lost(state, rng)
    if not lost:
        return state
    new = state.model_copy(deep=True)
    for carrier_id in lost:
        new.characters[carrier_id].expecting = None
    return new


def jump_for(state: WorldState, heir: Heir, ctx: TurnContext, rng: SeededRng) -> WorldState:
    """The world on the day `heir` can act: `state` itself when they can already, otherwise run on
    (`time_jump`). A child on the way born later than due, because the world held the birth, is
    run on to their own sixteenth birthday."""
    if not heir.jump_s:
        return state
    later = time_jump(state, state.world_s + heir.jump_s, ctx, rng)
    if heir.unborn:
        child = born_of(later, heir.carrier_id or "", heir.due_s or 0)
        born = _born_s(later, child) if child is not None else None
        if born is not None and later.world_s < born + AGE_OF_ACTION * YEAR:
            later = time_jump(later, born + AGE_OF_ACTION * YEAR, ctx, rng.child("birthday"))
    return later


def time_jump(state: WorldState, until_s: int, ctx: TurnContext, rng: SeededRng) -> WorldState:
    """The world run on to `until_s`, applying everything due on the way, whatever it would have
    stopped for, and everyone grown older by the years they lived through. Returns a new state."""
    start = state.world_s
    current = state.model_copy(deep=True)
    # The old player character's story ended: a time stop of theirs doesn't hold the world (W10a).
    current.time_effects = [e for e in current.time_effects if e.character_id != state.player_id]
    for _ in range(MAX_JUMP_PASSAGES):
        if current.world_s >= until_s:
            break
        passage = catch_up(current, until_s, ctx, rng, copy=False)
        if passage.ended_s <= passage.started_s and not passage.fired:
            break  # time stands still (W10a), or nothing moves it
    # Whatever the world didn't get to on the way still lies ahead of it.
    current.world_s = max(current.world_s, until_s)
    for character in current.characters.values():
        before = state.characters.get(character.id)
        if character.age is None or (before is not None and not before.alive):
            continue  # the dead stay the age they died at
        # Up to now, or to their death on the way.
        end = current.world_s if character.alive else _died_s(character, start)
        born = _born_s(current, character)
        if born is not None:
            character.age = max(0, (end - born) // YEAR)
        elif before is not None:
            character.age += (end - start) // YEAR
    return current


def born_of(state: WorldState, carrier_id: str, due_s: int) -> Character | None:
    """The child a carrier's pregnancy, due at `due_s`, brought into the world, if it did."""
    for event in state.pending_events.values():
        if (
            event.kind == Kind.BIRTH
            and event.status is EventStatus.APPLIED
            and event.payload.get("parent_id") == carrier_id
            and event.payload.get("due_s") == due_s
        ):
            return next(
                (
                    c
                    for c in state.characters.values()
                    if c.origin is not None
                    and c.origin.kind is OriginKind.BIRTH
                    and c.origin.ref_id == event.id
                ),
                None,
            )
    return None


def _died_s(character: Character, start: int) -> int:
    """When someone who died since `start` died, as their status history has it."""
    death = next((c for c in reversed(character.status_history) if c.status == "dead"), None)
    return max(start, death.world_s) if death is not None else start


def _born_s(state: WorldState, character: Character) -> int | None:
    """When someone born in the story was born."""
    origin = character.origin
    if origin is None or origin.kind is not OriginKind.BIRTH or origin.ref_id is None:
        return None
    event = state.pending_events.get(origin.ref_id)
    return event.applied_s if event is not None else None
