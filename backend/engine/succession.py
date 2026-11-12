"""N6: someone else carries the story on after its ending, in the same world.

After a death, or an ending the player chose, the player can carry on as a random person of the
world. Code draws who that person is by the world's own population odds (rule 2: model nodes
propose, code decides), and the drafting model only fills in someone who fits the draw:

- **Where**: a place where people live, likelier a city than a village, never a ruin or the wilds.
- **Station**, by population: most people are common folk, about 1 in 5 has a trade or a craft,
  about 1 in 40 is a notable (a rich merchant, an official, an elder), about 1 in 1,000 belongs to
  a noble house, and about 1 in 50,000 to a ruling family, never as its ruler (Miki, 2026-11-05:
  royalty is 1 in 10,000 to 1 in 100,000). Nobody is drawn as a king or a god.
- **Might**, as a stranger's (W1): most are ordinary, about 1 in 15 knows how to fight, and a
  hidden master is rare, rarer where nothing is extraordinary (`strangers.master_odds`).
- **Age**: an adult of working age.
- **People** (G23): the world's peoples, likelier the ones the story has met more of.

`carry_on` makes the drawn person the player character. The old one stays in the world, dead or,
after an ending the player chose, alive like anyone else, and is recorded in `fallen`, so the people
who knew them can remember them (N6). What was the old player character's alone stays theirs:
their goals, the leads offered to them, their reputation with factions and places (W3) and what
they knew (C6). The new one starts as a stranger to the world, with their first scene still to
tell (`opening_due`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import Field

from engine.base import EngineModel, Tier
from engine.kin import ancestors
from engine.resolve.strangers import (
    ORDINARY_TIER,
    PEAK_PERSON_TIER,
    TOUGH_ODDS,
    master_odds,
    strongest,
)
from engine.rng import SeededRng
from engine.state.cast import Activity, Character, PlaceStatus, Prominence, Reputation
from engine.state.records import Fallen, GoalStatus, LeadStatus
from engine.state.scene import SceneFrame
from engine.state.world import WorldState


class Station(StrEnum):
    """Where someone stands among the world's people, by population."""

    COMMON = "common"  # labourers, farmers, servants, the poor
    SKILLED = "skilled"  # a trade or a craft: smiths, traders, soldiers, clerks
    NOTABLE = "notable"  # a rich merchant, a local official, an officer, an elder
    NOBLE = "noble"  # a noble house or a high office
    ROYAL = "royal"  # a ruling family, never its ruler


# How likely each station is; common folk are everyone else.
STATION_ODDS: dict[Station, float] = {
    Station.ROYAL: 1 / 50_000,
    Station.NOBLE: 1 / 1_000,
    Station.NOTABLE: 1 / 40,
    Station.SKILLED: 1 / 5,
}
STATION_ODDS[Station.COMMON] = 1 - sum(STATION_ODDS.values())

# Influence and wealth for each station, as A8 tiers (1 is an ordinary person's).
STANDING: dict[Station, tuple[int, int]] = {
    Station.COMMON: (1, 1),
    Station.SKILLED: (1, 2),
    Station.NOTABLE: (2, 3),
    Station.NOBLE: (4, 4),
    Station.ROYAL: (5, 5),
}

# Where people live, by the words in a place's kind: likelier a city than a village. Kinds that
# match none count once; kinds nobody lives in never come up.
PLACE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("capital", 12),
    ("city", 10),
    ("port", 6),
    ("town", 5),
    ("district", 4),
    ("quarter", 4),
    ("market", 3),
    ("village", 2),
)
# Kinds of place nobody makes a home in, as whole words, unless the kind also names a settlement
# ("a seaport", "a city in the underworld").
EMPTY_KINDS = frozenset(
    (
        "wild wilds wilderness wasteland waste ruin ruins region realm continent world sea ocean "
        "lake river desert forest woods jungle swamp marsh mountain mountains peak pass cave "
        "cavern dungeon battlefield road"
    ).split()
)

# An adult of working age.
AGES = (16, 60)


class Lot(EngineModel):
    """Who the next player character is, as drawn: the drafting model fills in a person who fits
    it, and code holds the result to it."""

    place_id: str | None = None
    station: Station = Station.COMMON
    might: Tier = ORDINARY_TIER
    master: bool = Field(default=False, description="A hidden master (W1).")
    age: int = Field(ge=0)
    people_id: str | None = None
    one_in: int = Field(ge=1, description="How rare a person like this is: one in this many.")


def draw(state: WorldState, rng: SeededRng) -> Lot:
    """A random person of the world, by its population odds."""
    station = _pick(
        [(s, STATION_ODDS[s]) for s in Station], rng.child("station"), default=Station.COMMON
    )
    might, master, might_odds = _might(state, rng.child("might"))
    low, high = AGES
    return Lot(
        place_id=_place(state, rng.child("place")),
        station=station,
        might=might,
        master=master,
        age=rng.child("age").randint(low, high),
        people_id=_people(state, rng.child("people")),
        one_in=max(1, round(1 / (STATION_ODDS[station] * might_odds))),
    )


def carry_on(
    state: WorldState,
    successor: Character,
    situation: str,
    *,
    ending: str,
    turn: int,
    ended_s: int | None = None,
) -> WorldState:
    """`successor` becomes the player character, after the story's ending in scene `turn`, at
    `ended_s` (now, unless the world ran on since, for an heir). The old player character stays
    in the world and is remembered in `fallen`; the new one's first scene opens on `situation`.
    `successor` is someone new, or an heir the story has (`engine.heirs`), as they are now.
    Returns a new state."""
    heir = successor.id in state.characters
    if successor.id == state.player_id:
        raise ValueError(f"{successor.id!r} is the player character already")
    new = state.model_copy(deep=True)
    old = new.player
    new.fallen.append(
        Fallen(
            character_id=old.id,
            name=old.name,
            ending=ending,
            turn=turn,
            world_s=new.world_s if ended_s is None else ended_s,
            successor_id=successor.id,
        )
    )
    if old.alive:
        # W15: one more character in the world, kept and moved on by their clocks.
        old.activity = Activity.DORMANT
    else:
        # Whoever was there when they died saw how it ended (C6), and an heir of theirs grew up
        # knowing it.
        death = next((s for s in reversed(old.status_history) if s.status == "dead"), None)
        if death is not None:
            knowers = [*new.scene.present_ids]
            if heir and old.id in ancestors(new.characters, successor.id):
                knowers.append(successor.id)
            for cid in knowers:
                witness = new.characters.get(cid)
                if witness is not None and witness.alive and cid != old.id:
                    if cid not in death.known_by:
                        death.known_by.append(cid)
    if heir:
        # An heir keeps who knows them, and knows their own family (C6).
        new.characters[successor.id] = successor.model_copy(
            update={
                "known_by": list(dict.fromkeys([*successor.known_by, successor.id])),
                "met_by": list(dict.fromkeys([*successor.met_by, successor.id])),
                "activity": Activity.ACTIVE,
                "prominence": Prominence.KEY,
            }
        )
        _knows_family(new, successor.id)
    else:
        new.characters[successor.id] = successor.model_copy(
            update={"known_by": [successor.id], "met_by": [successor.id]}
        )
    new.player_id = successor.id
    new.openings = []  # A3: the openings were the old character's, not theirs
    # C6: they know where they live, and the places around it.
    place = new.places.get(successor.location_id or "")
    seen: set[str] = set()
    while place is not None and place.id not in seen:
        seen.add(place.id)
        if successor.id not in place.known_by:
            place.known_by.append(successor.id)
        place = new.places.get(place.parent_id or "")
    for goal in new.goals.values():
        if goal.status is GoalStatus.ACTIVE:
            goal.status = GoalStatus.ABANDONED
            goal.closed_turn = turn
            goal.closed_s = new.world_s
    for lead in new.leads.values():
        if lead.status is LeadStatus.OPEN:
            lead.status = LeadStatus.EXPIRED
    for record in (*new.factions.values(), *new.places.values()):
        record.player_reputation = Reputation()
    new.time_effects = [e for e in new.time_effects if e.character_id != old.id]
    new.scene = SceneFrame(
        place_id=successor.location_id, present_ids=[successor.id], ended_on=situation
    )
    new.opening_due = True
    return new


def _knows_family(state: WorldState, heir_id: str) -> None:
    """An heir knows their parents, brothers and sisters, and children, and has met those alive,
    as they have them. They know of their grandparents and those before them too."""
    heir = state.characters[heir_id]
    parents = set(heir.parent_ids)
    for ancestor_id in ancestors(state.characters, heir_id) - parents:
        if heir_id not in state.characters[ancestor_id].known_by:
            state.characters[ancestor_id].known_by.append(heir_id)
    kin = [
        c
        for c in state.characters.values()
        if c.id != heir_id
        and (c.id in parents or heir_id in c.parent_ids or parents & set(c.parent_ids))
    ]
    for relative in kin:
        if heir_id not in relative.known_by:
            relative.known_by.append(heir_id)
        if relative.alive:
            for record, other in ((relative, heir_id), (heir, relative.id)):
                if other not in record.met_by:
                    record.met_by.append(other)
                if other not in record.known_by:
                    record.known_by.append(other)


def _might(state: WorldState, rng: SeededRng) -> tuple[int, bool, float]:
    """Their might, whether they are a hidden master, and how likely that was."""
    master = master_odds(state)
    roll = rng.random()
    if roll < master:
        # Halfway to the strongest the world holds, and never less than the best a real person
        # can be (A9).
        return max(PEAK_PERSON_TIER, (ORDINARY_TIER + strongest(state)) // 2), True, master
    if roll < master + TOUGH_ODDS:
        return ORDINARY_TIER + 1, False, TOUGH_ODDS
    return ORDINARY_TIER, False, 1 - master - TOUGH_ODDS


def _place(state: WorldState, rng: SeededRng) -> str | None:
    places = [
        (place.id, _lived_in(place.kind))
        for place in sorted(state.places.values(), key=lambda p: p.id)
        if place.status is not PlaceStatus.RUINED
    ]
    return _pick(places, rng, default=None)


def _lived_in(kind: str) -> int:
    text = kind.casefold()
    settled = next((weight for word, weight in PLACE_WEIGHTS if word in text), None)
    if settled is not None:
        return settled
    if EMPTY_KINDS.intersection(re.findall(r"[^\W\d_]+", text)):
        return 0
    # A house, a sect, a farm, an inn: someone may live there.
    return 1


def _people(state: WorldState, rng: SeededRng) -> str | None:
    met: dict[str, int] = {}
    for character in state.characters.values():
        if character.people_id:
            met[character.people_id] = met.get(character.people_id, 0) + 1
    peoples = [
        (p.id, 1 + met.get(p.id, 0)) for p in sorted(state.bible.peoples, key=lambda p: p.id)
    ]
    return _pick(peoples, rng, default=None)


def _pick[T](weighted: Sequence[tuple[T, float]], rng: SeededRng, *, default: T) -> T:
    total = sum(weight for _, weight in weighted if weight > 0)
    if total <= 0:
        return default
    point = rng.random() * total
    for item, weight in weighted:
        if weight <= 0:
            continue
        point -= weight
        if point < 0:
            return item
    return next(item for item, weight in reversed(weighted) if weight > 0)
