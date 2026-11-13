"""Lives of their own (W6, W10): what the years bring the people the story knows.

The player character can be gone for years, or live years in one place in a single step. The
people they know don't wait for them. On the world tick, each of them may find a partner,
marry, have a child, part from a partner, make a close friend or fall out with someone for
good, and everyone on record grows older with the world's years.

Nothing here is made to happen (Miki, 2026-11-13: "maybe 10 years go by and the person is
exactly the same"). Each thing has a chance in one year (`engine.world.tuning`), and the chance
over a stretch follows from it, so a month brings next to nothing and ten years a great deal.
Every draw is seeded by whom it is about, so the same years play the same way again (A3).
Where the facts settle it, they do (A2): nobody leaves a marriage that is for life, only
recorded adults pair or have children (F3), close family never pair, and someone marked
`solitary` takes no partner of the world's making. One person in four is settled as they are
(`settled`), by who they are: no partner, friend or foe comes to them alone, however long it
has been.

Whose life it is: the living key people and those the player character has met, beasts aside,
those closest to the story first, up to `LIVES_PEOPLE`. Not whoever is in the scene, and not
for a season after the player character was last with them (`Character.seen_s`,
`LIFE_QUIET_S`): those days are the story's to tell. The player character's own romances are
theirs (G15): the world gives their partner no one else, parts no couple they are one of, and
leaves alone whoever they are courting while they are near. Someone they courted and then
left for years may well find someone, the less likely the more their heart is with the
player character.

What changes is on the records it touches: a romance (`WorldState.bonds`), a child or a partner
the record didn't have, as a minor character with a placeholder name until the story names
them, and how two people feel about each other. The news of it is a `LifeEvent`, known to the
two it came to, and to the player character at once when they know one of the two and live near
them (the same place, or within a day of it). Otherwise it is news of the two (`news_of`): the
narrator is shown it whenever one of them is in the scene or about to be, and the player
character has heard it once a scene told it (`settle`), never before, where a scene has told
what its own words bear out (`borne_out`). News is of someone they had met by then: what came
to a stranger before the two ever met is who that person is (`Character.met_s`), and when
someone else becomes the player character they have been with their own people all along
(`hand_over`). Where someone lives is where the story put them, or where they set out from
while the world has them out on a trip (`_Homes`): a partner or a child the world brings is at
home there, and nobody hears a neighbour's news for being in town the day it happened.

How long the two have been apart (`apart_s`) counts from the last scene they shared or from
when they last lived near each other (`_beside`), so neighbours of ten years are nobody to
meet again, and someone left behind for ten years is, until a scene has the two together.

Nobody dies of old age yet. Until that is built, whoever has outlived their people's span
gets no new partner, friend or foe (`_spent`).
"""

import re
import zlib
from collections.abc import Iterable

from engine import bonds, naming
from engine.base import YEAR
from engine.limits import ADULT_AGE, is_adult
from engine.state.cast import Character, CharacterStatus, DeathCertainty, Prominence
from engine.state.records import (
    Bond,
    BondStage,
    BondStep,
    LifeEvent,
    LifeKind,
    Origin,
    OriginKind,
)
from engine.state.sheet import Attitude
from engine.state.world import WorldState, natural_key
from engine.world.births import NAME_ROOM, is_placeholder, placeholder_name
from engine.world.geography import scene_ids, together, travel_s
from engine.world.knowledge import closeness, shift_attitude
from engine.world.norms import is_beast
from engine.world.scheduling import Kind, World, by_id, pending
from engine.world.tuning import (
    CHILD_GAP_S,
    CHILD_RATE_MARRIED,
    CHILD_RATE_TOGETHER,
    FOE_AT,
    FRIEND_AT,
    LIFE_APART_S,
    LIFE_NEAR_S,
    LIFE_QUIET_S,
    LIFE_SETTLED,
    LIFESPAN_YEARS,
    LIVES_KEPT,
    LIVES_PEOPLE,
    MARRY_RATE,
    MOST_CHILDREN,
    NEWCOMER_AGE_ROOM,
    PAIR_AGE_GAP,
    PAIR_AGE_ROOM,
    PAIR_FROM_CAST,
    PAIR_LATE,
    PAIR_RATE,
    PART_COLD,
    PART_RATE_MARRIED,
    PART_RATE_TOGETHER,
    PRIME,
    TIE_AGE,
    TIE_RATE,
    TIE_ROOM,
    TIE_SOUR,
    TIE_WARM,
)

# A look written with an age at its head, as the drafter writes them: "29, strong arms".
_LEADING_AGE = re.compile(r"^\s*(\d{1,3})\s*,")
# How a child born in the story is described until someone writes more (`engine.world.births`).
_NEWBORN = "A newborn, the child of "
_PARTNER = re.compile(r".*'s partner( \d+)?")

# What came to someone, in the engine's own words, for the narrator.
_SAID = {
    LifeKind.PAIRED: "found a partner",
    LifeKind.MARRIED: "married",
    LifeKind.PARTED: "parted from their partner",
    LifeKind.CHILD: "had a child",
    LifeKind.FRIENDS: "became close friends with someone",
    LifeKind.FELL_OUT: "fell out with someone for good",
}
_LEFT, _WAS_LEFT = "left their partner", "was left by their partner"


# --- growing older (W10) ---------------------------------------------------------------------


def grow_older(state: WorldState, now_s: int, since_s: int | None = None) -> None:
    """Everyone on record is as old as the world's years make them at `now_s`: a year older
    for every whole year since the world first counted (`WorldState.aged_s`, which starts at
    `since_s`, or now), and someone born in the story as old as the years since their birth.
    Whoever died for certain stays the age they died at; a death only presumed may turn out
    false (C1), so those years count. Mutates `state`."""
    first = state.aged_s is None
    if state.aged_s is None:
        state.aged_s = max(0, now_s if since_s is None else min(since_s, now_s))
    was = state.aged_s
    upto = was + max(0, (now_s - was) // YEAR) * YEAR
    for character in state.characters.values():
        known = character.id != state.player_id and state.player_id in character.met_by
        if first and known and character.seen_s is None:
            # A story already under way: whoever they know, they were with until now.
            character.seen_s = was
        if character.age is None:
            continue
        before = character.age
        died = _died_s(character)
        if character.born_s is not None:
            end = now_s if died is None else min(now_s, died)
            character.age = max(0, (end - character.born_s) // YEAR)
        elif died is None:
            character.age += (upto - was) // YEAR
        elif died > was:
            character.age += (min(died, upto) - was) // YEAR
        if character.age != before:
            _in_step(character, before)
    state.aged_s = upto


def _died_s(character: Character) -> int | None:
    """When someone died for certain, as their history has it: at the story's start where it
    doesn't say. None for the living and for a death only presumed."""
    presumed = character.death_certainty is DeathCertainty.PRESUMED
    if character.status is not CharacterStatus.DEAD or presumed:
        return None
    death = next((c for c in reversed(character.status_history) if c.status == "dead"), None)
    return death.world_s if death is not None else 0


def _in_step(character: Character, before: int) -> None:
    """Words that state their age keep the age they are: a look with it at its head ("29,
    strong arms"), and a child the world called a newborn."""
    for field in ("appearance", "description"):
        text = getattr(character, field)
        match = _LEADING_AGE.match(text)
        if match and int(match.group(1)) == before:
            head, tail = text[: match.start(1)], text[match.end(1) :]
            setattr(character, field, f"{head}{character.age}{tail}")
    if character.age >= 1 and character.description.startswith(_NEWBORN):
        character.description = "The child of " + character.description[len(_NEWBORN) :]


# --- whose life it is ------------------------------------------------------------------------


def unnamed(character: Character) -> bool:
    """Whether someone the world brought still goes by the name it gave them: "Mira's child",
    "Mara's partner", until the story names them."""
    if is_placeholder(character):
        return True
    origin = character.origin
    return (
        origin is not None
        and origin.kind is OriginKind.ENGINE
        and _PARTNER.fullmatch(character.name) is not None
    )


def _person(state: WorldState, character: Character) -> bool:
    return (
        character.id != state.player_id
        and character.status is CharacterStatus.ALIVE
        and not is_beast(state, character.id)
    )


def living(state: WorldState) -> list[Character]:
    """Whom the world gives a life of their own now: the living key people and those the
    player character has met, beasts aside, whoever is in the scene aside, those closest to
    the story first, up to `LIVES_PEOPLE`."""
    you = state.player
    here = set(scene_ids(state))
    found = [
        c
        for c in by_id(state.npcs())
        if _person(state, c)
        and c.id not in here
        and (c.prominence is Prominence.KEY or you.id in c.met_by)
    ]

    def rank(character: Character) -> tuple:
        feeling = abs(character.attitude_toward(you.id).affinity)
        key = character.prominence is Prominence.KEY
        return (-closeness(state, you, character.id), not key, -feeling, natural_key(character.id))

    return sorted(found, key=rank)[:LIVES_PEOPLE]


def settled(character: Character) -> bool:
    """Whether someone is settled as they are: nothing of the world's making comes to them
    alone, however long it has been. Theirs by who they are (their id), for the whole
    story, never from a throw."""
    return zlib.crc32(f"life:{character.id}".encode()) % 100 < LIFE_SETTLED


class _Homes:
    """Where everyone lives, as near as the record has it, read once for a pass of the tick:
    where the story put them, or, while the world has them out on a trip of their own, where
    they set out from (`returns.trip_of`). A day in town makes nobody a neighbour there."""

    def __init__(self, state: WorldState) -> None:
        self.state = state
        # The first return on record is the trip someone is on, as `trip_of` has it.
        trips = reversed(pending(state, Kind.RETURN))
        self.out = {trip.payload.get("character_id"): trip.place_id for trip in trips}

    def of(self, person: Character) -> str | None:
        return self.out.get(person.id, person.location_id)

    def same(self, a: Character, b: Character) -> bool:
        at, other = self.of(a), self.of(b)
        if at is None or other is None:
            return False
        return together(self.state, at, other)

    def near(self, a: Character, b: Character) -> bool:
        """Whether two people live near enough for one to hear what comes to the other as
        it happens: in the same place, or within `LIFE_NEAR_S` of it by the map."""
        if self.same(a, b):
            return True
        away = travel_s(self.state, self.of(a), self.of(b))
        return away is not None and away <= LIFE_NEAR_S


def _storys(homes: _Homes, person: Character) -> bool:
    """Whether someone's love is the story's to tell now, never the world's: they are in the
    scene, they are a couple with the player character (G15), or the player character is
    courting them and lives near."""
    state = homes.state
    if person.id in scene_ids(state):
        return True
    bond = bonds.live(state, state.player_id, person.id)
    if bond is None or bond.stage is BondStage.INTEREST:
        return False
    return bond.stage.couple or homes.near(state.player, person)


def _years(person: Character, since_s: int, now_s: int) -> float:
    """How many years of a stretch were someone's own: all of it, less the season after the
    player character was last with them."""
    start = since_s
    if person.seen_s is not None:
        start = max(start, person.seen_s + LIFE_QUIET_S)
    return max(0, now_s - start) / YEAR


def _over(rate: float, years: float) -> float:
    """The chance of something within a stretch, from its chance in one year."""
    return 1 - (1 - min(1.0, max(0.0, rate))) ** max(0.0, years)


def _lifespan(state: WorldState, person: Character) -> int:
    """How long someone's people live (G23), or a human span where the world doesn't say."""
    people = next((p for p in state.bible.peoples if p.id == person.people_id), None)
    return (people.lifespan_years if people is not None else None) or LIFESPAN_YEARS


def _prime(state: WorldState, person: Character) -> bool:
    """Whether someone is in the prime of life, by their people's lifespan."""
    return person.age is not None and person.age < _lifespan(state, person) * PRIME


def _spent(state: WorldState, person: Character) -> bool:
    """Whether someone has outlived their people's span. The world brings them no new
    partner, friend or foe: what a hundred years does to the people left behind is still to
    build (deaths of old age), and until then nobody starts a new life at a hundred and
    thirty."""
    return person.age is not None and person.age >= _lifespan(state, person)


# --- the tick --------------------------------------------------------------------------------


def live_on(w: World, since_s: int) -> None:
    """The world's part in the lives of the people the story knows, for the stretch from
    `since_s` to now: everyone grows older, and then each couple, each single person and each
    pair of neighbours gets what the years bring, one thing of a kind at most per stretch."""
    state = w.state
    grow_older(state, w.at_s, since_s)
    homes = _Homes(state)
    _beside(state, homes, since_s, w.at_s)
    if w.at_s <= since_s:
        return
    people = living(state)
    years = {p.id: _years(p, since_s, w.at_s) for p in people}
    whole = (w.at_s - since_s) / YEAR
    for bond in sorted(state.bonds.values(), key=lambda b: natural_key(b.id)):
        a, b = state.characters.get(bond.a_id), state.characters.get(bond.b_id)
        if a is None or b is None or not bond.stage.couple:
            continue
        if not (_person(state, a) and _person(state, b)):
            continue
        if (a.id not in years and b.id not in years) or _storys(homes, a) or _storys(homes, b):
            continue
        theirs = min(years.get(a.id, whole), years.get(b.id, whole))
        if theirs > 0:
            _couple(w, homes, bond, a, b, theirs)
    for person in people:
        if years[person.id] > 0:
            _pair(w, homes, person, years[person.id])
    known = {p.id for p in people}
    for person in people:
        if years[person.id] > 0:
            _tie(w, homes, person, years[person.id], known)
    _prune(state)


def _beside(state: WorldState, homes: _Homes, since_s: int, now_s: int) -> None:
    """Whoever lives near the player character, and was with or near them when this stretch
    began or within `LIFE_APART_S` before it, has been near them up to now
    (`Character.near_s`): the two haven't been apart, though no scene had them together.
    Someone the player character comes back to after longer than that stays apart from them
    until a scene has the two together."""
    you = state.player
    near: dict[str | None, bool] = {}  # by where someone lives: the map is read once a place
    for person in state.characters.values():
        if person.id == you.id or not person.alive:
            continue
        last = _last_with(person)
        if last is None or last < since_s - LIFE_APART_S:
            continue
        home = homes.of(person)
        if home not in near:
            near[home] = homes.near(you, person)
        if near[home]:
            person.near_s = now_s


def apart_s(state: WorldState, person: Character) -> int | None:
    """How long the player character and someone have been apart: since the two were last in
    a scene together (`seen_s`) or last lived near each other (`near_s`). None when the
    record has them together at neither. A neighbour of ten years is nobody to meet again,
    and someone left behind for ten years is."""
    last = _last_with(person)
    return None if last is None else max(0, state.world_s - last)


def _last_with(person: Character) -> int | None:
    """When the player character and someone were last together: in a scene, or living near
    each other, whichever came later."""
    return max((s for s in (person.seen_s, person.near_s) if s is not None), default=None)


def _news(
    w: World,
    homes: _Homes,
    kind: LifeKind,
    subject_ids: list[str],
    *,
    child_id: str | None = None,
    by_id: str | None = None,
) -> LifeEvent:
    """The news of something that came to one or two people: they know it, and so does the
    player character at once when they know one of the two and live near them. What comes to
    someone they have never heard of is no talk of theirs (C6)."""
    state = w.state
    you = state.player
    known = list(subject_ids)
    theirs = [c for i in subject_ids if you.id in (c := state.characters[i]).known_by]
    if any(homes.near(you, c) for c in theirs):
        known.append(you.id)
    event = LifeEvent(
        id=state.new_id("life"),
        kind=kind,
        subject_ids=list(subject_ids),
        child_id=child_id,
        by_id=by_id,
        turn=w.ctx.turn,
        world_s=w.at_s,
        timeline_id=state.timeline_id,
        known_by=list(dict.fromkeys(known)),
    )
    state.lives[event.id] = event
    return event


def _couple(w: World, homes: _Homes, bond: Bond, a: Character, b: Character, years: float) -> None:
    """What a stretch brings a couple: a parting, by the custom of the world and likelier
    where a heart has gone cold; else a wedding; else a child."""
    state = w.state
    married = bond.stage is BondStage.MARRIED
    hearts = {a.id: bonds.heart_for(state, a, b.id), b.id: bonds.heart_for(state, b, a.id)}
    part = (PART_RATE_MARRIED if married else PART_RATE_TOGETHER)[state.bible.unions]
    if min(hearts.values()) < bonds.LEAVES_UNDER:
        part *= PART_COLD
    if part and w.roll("life", "part", bond.id).chance(_over(part, years)):
        # Whoever's heart is less in it ends it.
        leaver, left = sorted((a, b), key=lambda c: (hearts[c.id], natural_key(c.id)))
        bonds.end(
            bond,
            by_id=leaver.id,
            how=f"{leaver.name} and {left.name} parted.",
            turn=w.ctx.turn,
            world_s=w.at_s,
        )
        shift_attitude(
            left,
            leaver.id,
            affinity=-bonds.PARTED_COUPLE,
            attraction=-bonds.PARTED_HEART_COUPLE,
        )
        _news(w, homes, LifeKind.PARTED, [leaver.id, left.id], by_id=leaver.id)
        return
    if not married:
        if w.roll("life", "marry", bond.id).chance(_over(MARRY_RATE, years)):
            # A wedding keeps a promise: the record has both steps, a stage at a time.
            hows = {
                BondStage.PROMISED: f"{a.name} and {b.name} promised themselves to each other.",
                BondStage.MARRIED: f"{a.name} and {b.name} married.",
            }
            for stage, how in hows.items():
                if bonds.can_move(bond, stage):
                    bond.stage = stage
                    bond.steps.append(
                        BondStep(stage=stage, turn=w.ctx.turn, world_s=w.at_s, by_id=a.id, how=how)
                    )
            _news(w, homes, LifeKind.MARRIED, [a.id, b.id])
            return
    children = [c for c in state.characters.values() if {a.id, b.id} <= set(c.parent_ids)]
    last = max((c.born_s for c in children if c.born_s is not None), default=None)
    if (
        len(children) >= MOST_CHILDREN
        or (last is not None and w.at_s - last < CHILD_GAP_S)
        or a.expecting is not None
        or b.expecting is not None
        or not all(is_adult(c) and _prime(state, c) for c in (a, b))
    ):
        return
    rate = CHILD_RATE_MARRIED if married else CHILD_RATE_TOGETHER
    if w.roll("life", "child", bond.id).chance(_over(rate, years)):
        names = f"{a.name} and {b.name}"
        child = Character(
            id=state.new_id("npc"),
            # A placeholder until the story names them, as for any child born in it.
            name=placeholder_name(state, a),
            prominence=Prominence.MINOR,
            age=0,
            born_s=w.at_s,
            people_id=a.people_id,
            location_id=homes.of(a),
            parent_ids=[a.id, b.id],
            origin=Origin(kind=OriginKind.BIRTH, ref_id=bond.id, text=f"Born to {names}."),
            known_by=[a.id, b.id],
            met_by=[a.id, b.id],
        )
        state.characters[child.id] = child
        _news(w, homes, LifeKind.CHILD, [a.id, b.id], child_id=child.id)


def _pair(w: World, homes: _Homes, person: Character, years: float) -> None:
    """A single adult may find a partner: someone on record who fits, about half the time
    there is one, and otherwise someone the record didn't have."""
    state = w.state
    you = state.player_id
    if person.solitary or not is_adult(person) or bonds.partners(state, person.id):
        return
    if settled(person) or _spent(state, person) or _storys(homes, person):
        return
    # The more their heart is with the player character, the longer they wait.
    waiting = 1 - person.attitude_toward(you).attraction / 100
    rate = PAIR_RATE * waiting * (1 if _prime(state, person) else PAIR_LATE)
    if not w.roll("life", "pair", person.id).chance(_over(rate, years)):
        return
    stream = w.roll("life", "partner", person.id)
    matches = _matches(homes, person)
    if matches and stream.chance(PAIR_FROM_CAST):
        partner = stream.choice(matches)
    else:
        older_by = stream.randint(-NEWCOMER_AGE_ROOM, NEWCOMER_AGE_ROOM)
        partner = _newcomer(w, homes, person, older_by)
    step = BondStep(
        stage=BondStage.TOGETHER,
        turn=w.ctx.turn,
        world_s=w.at_s,
        by_id=person.id,
        how=f"{person.name} and {partner.name} became a couple.",
    )
    bond = bonds.live(state, person.id, partner.id)
    if bond is None:
        bond = Bond(id=state.new_id("bond"), a_id=person.id, b_id=partner.id)
        state.bonds[bond.id] = bond
    bond.stage = BondStage.TOGETHER
    bond.steps.append(step)
    for one, other in ((person, partner), (partner, person)):
        toward = one.sheet.disposition.attitudes.setdefault(other.id, Attitude())
        if toward.attraction == 0:
            toward.attraction = bonds.settled_heart(one.id, other.id)
    _news(w, homes, LifeKind.PAIRED, [person.id, partner.id])


def _matches(homes: _Homes, person: Character) -> list[Character]:
    """Whom on record someone could come to be with: a single adult of the same place who
    isn't close family, isn't far from them in age, bears them no ill will and has no past
    with them, and whose love isn't the story's to tell."""
    state = homes.state
    you = state.player_id
    found = []
    for other in by_id(state.npcs()):
        if other.id == person.id or not _person(state, other) or other.solitary:
            continue
        if settled(other) or _spent(state, other):
            continue
        if not is_adult(other) or bonds.partners(state, other.id) or _storys(homes, other):
            continue
        if bonds.live(state, you, other.id) is not None:
            continue  # someone the player character has an eye on isn't given away
        if bonds.kin(state.characters, person.id, other.id):
            continue
        if not homes.same(person, other):
            continue
        older = max(person.age or 0, other.age or 0)
        apart = abs((person.age or 0) - (other.age or 0))
        if apart > max(PAIR_AGE_ROOM, PAIR_AGE_GAP * older):
            continue
        if bonds.last_over(state, person.id, other.id) is not None:
            continue
        feelings = (person.attitude_toward(other.id), other.attitude_toward(person.id))
        if any(feeling.affinity < 0 for feeling in feelings):
            continue
        found.append(other)
    return found


def _newcomer(w: World, homes: _Homes, person: Character, older_by: int) -> Character:
    """Someone the record didn't have, who came into a person's life: a minor character of
    their people and place, about their age, under a placeholder name until the story names
    them."""
    state = w.state
    base = f"{person.name[:NAME_ROOM]}'s partner"
    taken = {c.name for c in state.characters.values()}
    name, n = base, 2
    while name in taken:
        name, n = f"{base} {n}", n + 1
    newcomer = Character(
        id=state.new_id("npc"),
        name=name,
        prominence=Prominence.MINOR,
        age=max(ADULT_AGE, (person.age or ADULT_AGE) + older_by),
        people_id=person.people_id,
        location_id=homes.of(person),
        origin=Origin(
            kind=OriginKind.ENGINE, ref_id=person.id, text=f"Came into {person.name}'s life."
        ),
        known_by=[person.id],
        met_by=[person.id],
    )
    state.characters[newcomer.id] = newcomer
    return newcomer


def _tie(w: World, homes: _Homes, person: Character, years: float, known: Iterable[str]) -> None:
    """Someone and another the story knows, of the same place, become close friends or fall
    out for good. Close family never fall into friendship, being family already, and may
    well fall out."""
    state = w.state
    if settled(person) or _spent(state, person):
        return
    if person.age is not None and person.age < TIE_AGE:
        return
    if not w.roll("life", "tie", person.id).chance(_over(TIE_RATE, years)):
        return
    others = []
    for other_id in sorted(set(known) - {person.id}, key=natural_key):
        other = state.characters[other_id]
        if settled(other) or _spent(state, other):
            continue
        if other.age is not None and other.age < TIE_AGE:
            continue
        if not homes.same(person, other) or other_id in bonds.partners(state, person.id):
            continue
        mine, theirs = person.attitude_toward(other_id), other.attitude_toward(person.id)
        friends = mine.affinity >= FRIEND_AT and theirs.affinity >= FRIEND_AT
        foes = mine.affinity <= FOE_AT or theirs.affinity <= FOE_AT
        if not (friends or foes):
            others.append(other)
    if not others:
        return
    stream = w.roll("life", "with", person.id)
    other = stream.choice(others)
    mine, theirs = person.attitude_toward(other.id), other.attitude_toward(person.id)
    warm = stream.chance(TIE_WARM if min(mine.affinity, theirs.affinity) >= 0 else TIE_SOUR)
    if warm and bonds.kin(state.characters, person.id, other.id):
        return
    goal = (FRIEND_AT if warm else FOE_AT) + (1 if warm else -1) * stream.randint(0, TIE_ROOM)
    for one, toward in ((person, other.id), (other, person.id)):
        now = one.attitude_toward(toward).affinity
        change = max(0, goal - now) if warm else min(0, goal - now)
        shift_attitude(one, toward, affinity=change, trust=change / 2)
    _news(w, homes, LifeKind.FRIENDS if warm else LifeKind.FELL_OUT, [person.id, other.id])


def _prune(state: WorldState) -> None:
    """Keep the latest news only, so a long story's state stays flat (K8). What it told of
    stays on the records it changed (C1)."""
    if len(state.lives) <= LIVES_KEPT:
        return
    oldest = sorted(state.lives.values(), key=lambda e: (e.world_s, natural_key(e.id)))
    for event in oldest[:-LIVES_KEPT]:
        del state.lives[event.id]


# --- who has heard (C6) ----------------------------------------------------------------------


def of(state: WorldState, character_id: str) -> list[LifeEvent]:
    """What came to someone in their own life, on this timeline, oldest first."""
    found = [
        e
        for e in state.lives.values()
        if character_id in e.subject_ids and e.timeline_id == state.timeline_id
    ]
    return sorted(found, key=lambda e: (e.world_s, natural_key(e.id)))


def unheard(state: WorldState, character_id: str) -> list[LifeEvent]:
    """What came to someone that the player character hasn't heard of yet, oldest first."""
    return [e for e in of(state, character_id) if state.player_id not in e.known_by]


def news_of(state: WorldState, character: Character) -> list[LifeEvent]:
    """What the player character has yet to hear of someone they know: what came to them since
    the two first met (`Character.met_s`, or always, for someone known from before the story)
    that hasn't reached the player character. It stays news until a scene tells it (`settle`).
    What came to a stranger before they ever met is no news, only who they are."""
    if state.player_id not in character.met_by:
        return []
    since = -1 if character.met_s is None else character.met_s
    return [e for e in unheard(state, character.id) if e.world_s > since]


def heard_in(state: WorldState, turn: int) -> list[LifeEvent]:
    """What came to people in turn `turn` that the player character knows of already, being
    where it happened: oldest first."""
    found = [
        e
        for e in state.lives.values()
        if e.turn == turn and e.timeline_id == state.timeline_id and state.player_id in e.known_by
    ]
    return sorted(found, key=lambda e: (e.world_s, natural_key(e.id)))


def said(event: LifeEvent, of_id: str) -> str:
    """What came to someone, in the engine's own words, as it is told of them."""
    if event.kind is LifeKind.PARTED and event.by_id is not None:
        return _LEFT if event.by_id == of_id else _WAS_LEFT
    return _SAID[event.kind]


def hand_over(state: WorldState) -> None:
    """Someone else is the player character now (N6, `engine.succession.carry_on`). Whom they
    have met, they were with until now and grew up knowing the news of; whom the one before
    them was last with is nothing to them. Mutates `state`."""
    you = state.player_id
    met = set()
    for character in state.characters.values():
        theirs = character.id != you and you in character.met_by
        character.seen_s = state.world_s if theirs else None
        character.near_s = None  # the next tick says who lives near them
        character.met_s = None
        if theirs:
            met.add(character.id)
    for event in state.lives.values():
        if you not in event.known_by and met & set(event.subject_ids):
            event.known_by.append(you)


def told_by_naming(before: WorldState, after: WorldState, shown: Iterable[str]) -> list[str]:
    """The news among `shown`, by id, that a scene told by naming whom it brought: someone
    who went by the world's placeholder before the scene (`unnamed`) and has a name of their
    own after it. A scene names a partner or a child when it first tells of them, so the
    news of a partner found, or of a child born, is told with the name, whatever else the
    scene's answer lists."""

    def named(character_id: str | None) -> bool:
        was, now = before.characters.get(character_id), after.characters.get(character_id)
        return was is not None and now is not None and unnamed(was) and not unnamed(now)

    told = []
    for key in dict.fromkeys(shown):
        event = after.lives.get(key)
        if event is None:
            continue
        if event.kind is LifeKind.CHILD and named(event.child_id):
            told.append(key)
        elif event.kind is LifeKind.PAIRED and any(named(i) for i in event.subject_ids):
            told.append(key)
    return told


def borne_out(
    state: WorldState, told: Iterable[str], scene: str, *, there: Iterable[str] | None = None
) -> list[str]:
    """Of the news a scene says it told, by id, what its words bear out (C6): a piece is told
    where the scene names whoever it came with, by a name of their own (`naming.named_in`).
    For a birth that is the child. Otherwise it is whichever of the two wasn't in the scene
    (`there`, or whoever the scene ended with), or either of them where both were. Someone
    still under the name the world gave them can't be named by it: a scene that gives them a
    name of their own has told the news that brought them (`told_by_naming`).

    In the second live story of a homecoming (2026-11-13) the narrator listed all the news it
    was handed under a scene that said none of it, so Memory held what no scene had told."""
    here = set(state.scene.present_ids if there is None else there)
    events = [e for key in dict.fromkeys(told) if (e := state.lives.get(key)) is not None]

    def came_with(event: LifeEvent) -> list[str]:
        if event.kind is LifeKind.CHILD:
            return [event.child_id] if event.child_id else []
        return [i for i in event.subject_ids if i not in here] or list(event.subject_ids)

    people = state.characters
    named = {i for e in events for i in came_with(e) if i in people and not unnamed(people[i])}
    # The people of the scene share the words of their names with whoever the news names.
    among = sorted(named | {i for i in here if i in people}, key=natural_key)
    said = named.intersection(naming.named_in(state, [scene], among, anywhere=True))
    return [e.id for e in events if said.intersection(came_with(e))]


def settle(state: WorldState, told: Iterable[str] = ()) -> tuple[WorldState, list[str]]:
    """A scene ended. Whoever was in it, the player character has now been with
    (`Character.seen_s`). `told` is the news the scene was shown and says it showed or said,
    by the ids of its `LifeEvent`s: what of it is news of someone they know (`news_of`) the
    player character has now heard. News a scene left out stays news, however long the two
    were together (C6: Memory holds only what the story told). The ids of the news now heard
    come back with the state, which is a new one where anything changed."""
    you = state.player_id
    there = [
        c
        for i in dict.fromkeys(state.scene.present_ids)
        if i != you and (c := state.characters.get(i)) is not None and c.alive
    ]
    seen = {c.id: c.model_copy(update={"seen_s": state.world_s}) for c in there}
    heard = {}
    for key in dict.fromkeys(told):
        event = state.lives.get(key)
        if event is None:
            continue
        of_whom = [state.characters[i] for i in event.subject_ids if i in state.characters]
        if any(event in news_of(state, person) for person in of_whom):
            heard[key] = event.model_copy(update={"known_by": [*event.known_by, you]})
    if not seen and not heard:
        return state, []
    update: dict = {"characters": state.characters | seen}
    if heard:
        update["lives"] = state.lives | heard
    return state.model_copy(update=update), sorted(heard, key=natural_key)
