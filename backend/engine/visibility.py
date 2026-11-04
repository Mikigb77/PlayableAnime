"""C6: what the player character knows, in the world's words (G16).

`memory_view` and `status_view` project the world state onto the player character's knowledge,
in the shapes of API.md's `MemoryView` and `StatusView`. They read only records whose knowledge
lists hold the player character (`known_by`, `met_by`, `heard_at`, a status change's `known_by`),
and never read hidden truth: whether a rumor or fact is true, how accurate a rumor is, secrets,
agendas, real attitudes behind an apparent one, trust (W4), faction plans (W6), witnesses the
player didn't notice, or anything on another timeline. A spoiler view after an arc ends is a
separate projection (P1).

URLs for portraits and pictures are left empty here; the API fills them from the scene images.
"""

from typing import Literal

from pydantic import Field

from engine.base import EngineModel
from engine.labels import ago_label, clock_label, in_label
from engine.state.cast import (
    Character,
    CharacterStatus,
    Faction,
    FactionStatus,
    Place,
    PlaceStatus,
    Reputation,
)
from engine.state.records import (
    Deed,
    GoalStatus,
    LeadStatus,
    StatusChange,
    ThreadStatus,
    Visibility,
)
from engine.state.sheet import Health
from engine.state.world import WorldState, natural_key
from engine.world.telling import cap, tell

SINCE_LIMIT = 6


# --- the views, as API.md shapes them ------------------------------------------------------


class CharacterCard(EngineModel):
    name: str
    lines: list[str] = Field(default_factory=list)
    portrait_url: str | None = None


class PersonEntry(EngineModel):
    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    attitude_label: str | None = None
    portrait_url: str | None = None
    status_label: str


class PlaceEntry(EngineModel):
    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    image_url: str | None = None


class FactionEntry(EngineModel):
    id: str
    name: str
    lines: list[str] = Field(default_factory=list)
    standing_label: str


class GoalEntry(EngineModel):
    id: str
    text: str


class LeadEntry(EngineModel):
    id: str
    text: str
    expires_label: str | None = None


class RumorEntry(EngineModel):
    id: str
    text: str
    heard_label: str
    unconfirmed: Literal[True] = True


class DeedEntry(EngineModel):
    id: str
    text: str
    when_label: str
    known_label: str


class ThreadEntry(EngineModel):
    id: str
    title: str
    status: ThreadStatus


class MemoryView(EngineModel):
    character: CharacterCard
    people: list[PersonEntry] = Field(default_factory=list)
    places: list[PlaceEntry] = Field(default_factory=list)
    factions: list[FactionEntry] = Field(default_factory=list)
    goals: list[GoalEntry] = Field(default_factory=list)
    leads: list[LeadEntry] = Field(default_factory=list)
    rumors: list[RumorEntry] = Field(default_factory=list)
    deeds: list[DeedEntry] = Field(default_factory=list)
    threads: list[ThreadEntry] = Field(default_factory=list)


class StatusCharacter(EngineModel):
    name: str
    lines: list[str] = Field(default_factory=list)
    portrait_url: str | None = None


class ReputationEntry(EngineModel):
    name: str
    label: str


class ClockView(EngineModel):
    world_s: int
    label: str
    timeline_id: str


class SinceEntry(EngineModel):
    text: str
    ago_label: str


class StatusView(EngineModel):
    character: StatusCharacter
    reputation: list[ReputationEntry] = Field(default_factory=list)
    clock: ClockView
    since: list[SinceEntry] = Field(default_factory=list)


# --- words --------------------------------------------------------------------------------


def attitude_label(affinity: int) -> str:
    """How someone comes across toward the player character (W4): what they show, not what
    they feel."""
    if affinity >= 60:
        return "Warm"
    if affinity >= 20:
        return "Friendly"
    if affinity > -20:
        return "Neutral"
    if affinity > -60:
        return "Cold"
    return "Hostile"


def standing_label(reputation: Reputation) -> str:
    """Esteem and fear in words (W3): "Respected and feared", "Despised", "Neutral"."""
    esteem = reputation.esteem
    if esteem >= 60:
        words = "Admired"
    elif esteem >= 20:
        words = "Respected"
    elif esteem > -20:
        words = ""
    elif esteem > -60:
        words = "Disliked"
    else:
        words = "Despised"
    fear = "feared" if reputation.fear >= 60 else "wary of you" if reputation.fear >= 20 else ""
    if words and fear:
        return f"{words} and {fear}"
    if fear:
        return fear[0].upper() + fear[1:]
    return words or "Neutral"


_HEALTH_WORDS = {
    Health.UNHURT: "Unhurt",
    Health.HURT: "Hurt",
    Health.WOUNDED: "Wounded",
    Health.BADLY_WOUNDED: "Badly wounded",
    Health.DYING: "Dying",
}


def _status_words(status: str, presumed: bool = False) -> str:
    if status == CharacterStatus.DEAD.value:
        return "Presumed dead" if presumed else "Dead"
    return status.replace("_", " ").capitalize()


def believed_status(
    history: list[StatusChange], current: str, player_id: str, *, initial: str
) -> tuple[str, bool]:
    """The status the player character believes, and whether a death was presumed (C6): the
    latest change they know of. With none, it is the status before the first change (`initial`
    if that wasn't recorded), or the current one if it never changed."""
    known = [h for h in history if player_id in h.known_by]
    if known:
        return known[-1].status, known[-1].presumed
    if history:
        return history[0].from_status or initial, False
    return current, False


class _PlayerTeller:
    """The player character telling a deed (C6): "you" for themselves, only the names they
    know, and a death only where they know the deed caused it."""

    def __init__(self, knowledge: "_Knowledge") -> None:
        self.k = knowledge

    def name(self, record: Character | Place | Faction) -> str | None:
        if record.id == self.k.player_id:
            return "you"
        return record.name if self.k.knows(record) else None

    def believes_dead(self, victim_id: str, deed: Deed) -> bool:
        """A death they know of on this timeline, recorded by the deed's turn: one they learned
        of later, from some other cause, isn't laid at this deed's door."""
        victim = self.k.state.characters.get(victim_id)
        if victim is None:
            return True  # a nameless victim, such as a villager of a massacre, is a death
        dead = CharacterStatus.DEAD.value
        known = [
            h
            for h in victim.status_history
            if self.k.player_id in h.known_by and h.timeline_id == self.k.timeline
        ]
        if known:
            return known[-1].status == dead and known[-1].turn <= deed.turn
        if victim.status_history:
            return False  # changed only in ways they never learned of
        return victim.status.value == dead


# --- the projection ------------------------------------------------------------------------


class _Knowledge:
    """The player character's knowledge of one state."""

    def __init__(self, state: WorldState) -> None:
        self.state = state
        self.player_id = state.player_id
        self.now = state.world_s
        self.timeline = state.timeline_id
        # The facts the player character knows, by subject, in the order they were learned.
        known = sorted(
            (
                f
                for f in state.facts.values()
                if self.player_id in f.known_by and f.timeline_id == self.timeline
            ),
            key=lambda f: (f.world_s, natural_key(f.id)),
        )
        self.facts_by_subject: dict[str, list[str]] = {}
        for fact in known:
            for subject_id in dict.fromkeys(fact.subject_ids):
                self.facts_by_subject.setdefault(subject_id, []).append(fact.text)

    def knows(self, record) -> bool:
        return self.player_id in record.known_by

    def name_of(self, record_id: str) -> str | None:
        for collection in (self.state.characters, self.state.places, self.state.factions):
            record = collection.get(record_id)
            if record is not None and (record_id == self.player_id or self.knows(record)):
                return record.name
        return None

    def facts_about(self, subject_id: str) -> list[str]:
        return list(self.facts_by_subject.get(subject_id, []))

    def deed_text(self, deed: Deed) -> str:
        """A deed in the world's words (G16), naming only whom the player character knows and
        telling a death only where they know of it (C6): "You killed Zhao Kun at the well." A
        deed the world has no words for keeps its own."""
        return tell(self.state, deed, teller=_PlayerTeller(self)) or cap(deed.text)

    def deeds(self) -> list[Deed]:
        deeds = [
            d
            for d in self.state.deeds.values()
            if d.timeline_id == self.timeline
            and (d.actor_id == self.player_id or self.player_id in d.known_by)
        ]
        deeds.sort(key=lambda d: (d.world_s, natural_key(d.id)))
        return deeds

    def known_label(self, deed: Deed) -> str:
        """Who saw it, as far as the player character knows (W2, C6)."""
        if deed.actor_id != self.player_id:
            return "You saw it" if self.player_id in deed.witness_ids else "You heard of it"
        # In stopped time every witness is immune to the stop and unnoticed (W10a), unless the
        # world later reveals them by taking them off `unnoticed_witness_ids`.
        noticed = [
            w
            for w in deed.witness_ids
            if w != self.player_id and w not in deed.unnoticed_witness_ids
        ]
        if noticed:
            names = [n for n in (self.name_of(w) for w in noticed) if n]
            others = len(noticed) - len(names)
            if not names:
                return "You were seen"
            if others:
                plural = "s" if others > 1 else ""
                names.append(f"{others} other{plural}")
            return "Seen by " + _join(names)
        if deed.visibility is Visibility.PUBLIC and not deed.in_stopped_time:
            return "Done in public"
        return "No one saw, as far as you know"

    # --- entries --------------------------------------------------------------------------

    def person(self, c: Character) -> PersonEntry:
        lines = [c.description] if c.description else []
        lines += self.facts_about(c.id)
        attitude = None
        if self.player_id in c.met_by:
            attitude = attitude_label(c.attitude_toward(self.player_id).shown_affinity)
        status, presumed = believed_status(
            c.status_history, c.status.value, self.player_id, initial=CharacterStatus.ALIVE.value
        )
        return PersonEntry(
            id=c.id,
            name=c.name,
            lines=lines,
            attitude_label=attitude,
            status_label=_status_words(status, presumed),
        )

    def place(self, p: Place) -> PlaceEntry:
        lines = [_cap(p.kind)] if p.kind else []
        if p.description:
            lines.append(p.description)
        status, _ = believed_status(
            p.status_history, p.status.value, self.player_id, initial=PlaceStatus.THRIVING.value
        )
        if status != PlaceStatus.THRIVING.value:
            lines.append(_status_words(status))
        if self.player_id not in p.visited_by:
            lines.append("You haven't been there.")
        lines += self.facts_about(p.id)
        return PlaceEntry(id=p.id, name=p.name, lines=lines)

    def faction(self, f: Faction) -> FactionEntry:
        lines = [_cap(f.kind)] if f.kind else []
        if f.description:
            lines.append(f.description)
        status, _ = believed_status(
            f.status_history, f.status.value, self.player_id, initial=FactionStatus.INTACT.value
        )
        if status != FactionStatus.INTACT.value:
            lines.append(_status_words(status))
        lines += self.facts_about(f.id)
        return FactionEntry(
            id=f.id, name=f.name, lines=lines, standing_label=standing_label(f.player_reputation)
        )

    def player_lines(self, player: Character) -> list[str]:
        lines = [player.description] if player.description else []
        resources = player.sheet.resources
        for title in (resources.title, resources.rank):
            if title:
                lines.append(_cap(title))
        lines += self.ladder_lines(player)
        return lines

    def ladder_lines(self, player: Character) -> list[str]:
        lines = []
        for position in player.sheet.ladders:
            ladder = self.state.bible.ladder(position.ladder_id)
            if ladder is None or position.rung >= len(ladder.rungs):
                continue
            rung = ladder.rungs[position.rung].name
            stage = f", {position.stage}" if position.stage else ""
            lines.append(_cap(f"{ladder.name}: {rung}{stage}"))
        return lines

    def condition_lines(self, player: Character) -> list[str]:
        condition = player.sheet.condition
        lines = [_HEALTH_WORDS[condition.health]]
        lines += [_cap(w.text) for w in condition.wounds]
        lines += [_cap(s.name) for s in condition.states]
        lines += [_cap(f"{r.name}: {r.level}%") for r in condition.reserves]
        return lines

    def power_lines(self, player: Character) -> list[str]:
        lived = player.personal_s(self.now)
        lines = []
        for power in player.sheet.powers:
            ready_at = power.ready_at_personal_s
            if ready_at is not None and ready_at > lived:
                lines.append(_cap(f"{power.name}: ready {in_label(ready_at - lived)}"))
            else:
                lines.append(_cap(f"{power.name}: ready"))
        return lines

    def resource_lines(self, player: Character) -> list[str]:
        resources = player.sheet.resources
        lines = []
        if resources.money or resources.currency:
            lines.append(f"{resources.money:,} {resources.currency}".strip())
        for item in sorted(resources.items, key=lambda i: natural_key(i.id)):
            if item.carried:
                count = f" ({item.quantity})" if item.quantity > 1 else ""
                lines.append(_cap(f"{item.name}{count}"))
        return lines


def _cap(text: str) -> str:
    """Capitalises the first letter only, keeping names such as "Qi Condensation" intact."""
    return text[:1].upper() + text[1:]


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _sort_name(name: str) -> str:
    folded = name.casefold()
    for article in ("the ", "a ", "an "):
        if folded.startswith(article):
            return folded[len(article) :]
    return folded


def _by_name(records):
    """Alphabetical, ignoring a leading article: "the Azure Cloud Sect" sorts under A."""
    return sorted(records, key=lambda r: (_sort_name(r.name), natural_key(r.id)))


def memory_view(state: WorldState) -> MemoryView:
    """The Memory screen (C6): only what the player character knows."""
    k = _Knowledge(state)
    player = state.player
    calendar = state.bible.calendar

    people = [k.person(c) for c in _by_name(state.npcs()) if k.knows(c)]
    places = [k.place(p) for p in _by_name(state.places.values()) if k.knows(p)]
    factions = [k.faction(f) for f in _by_name(state.factions.values()) if k.knows(f)]
    goals = [
        GoalEntry(id=g.id, text=g.text)
        for g in sorted(state.goals.values(), key=lambda g: (g.set_turn, natural_key(g.id)))
        if g.status is GoalStatus.ACTIVE
    ]
    leads = []
    for lead in sorted(state.leads.values(), key=lambda le: (le.offered_s, natural_key(le.id))):
        if lead.status is not LeadStatus.OPEN:
            continue
        if lead.expires_s is not None and lead.expires_s <= k.now:
            continue
        expires = None if lead.expires_s is None else f"Ends {in_label(lead.expires_s - k.now)}"
        leads.append(LeadEntry(id=lead.id, text=lead.text, expires_label=expires))
    rumors = []
    heard = [
        r
        for r in state.rumors.values()
        if k.player_id in r.heard_at and r.timeline_id == k.timeline
    ]
    for rumor in sorted(heard, key=lambda r: (r.heard_at[k.player_id], natural_key(r.id))):
        when = ago_label(k.now - rumor.heard_at[k.player_id])
        rumors.append(RumorEntry(id=rumor.id, text=rumor.text, heard_label=f"Heard {when}"))
    deeds = [
        DeedEntry(
            id=d.id,
            text=k.deed_text(d),
            when_label=clock_label(calendar, d.world_s),
            known_label=k.known_label(d),
        )
        for d in k.deeds()
    ]
    threads = [
        ThreadEntry(id=t.id, title=t.title, status=t.status)
        for t in sorted(state.threads.values(), key=lambda t: (t.opened_turn, natural_key(t.id)))
        if k.knows(t)
    ]
    return MemoryView(
        character=CharacterCard(name=player.name, lines=k.player_lines(player)),
        people=people,
        places=places,
        factions=factions,
        goals=goals,
        leads=leads,
        rumors=rumors,
        deeds=deeds,
        threads=threads,
    )


def clock_view(state: WorldState) -> ClockView:
    return ClockView(
        world_s=state.world_s,
        label=clock_label(state.bible.calendar, state.world_s),
        timeline_id=state.timeline_id,
    )


def status_view(state: WorldState) -> StatusView:
    """`/status` (A8, G16, W10): the player character's sheet in the world's words, their
    standing with the factions they know, the clock, and how long ago key events happened."""
    k = _Knowledge(state)
    player = state.player
    lines = (
        k.ladder_lines(player)
        + k.condition_lines(player)
        + k.power_lines(player)
        + k.resource_lines(player)
    )
    reputation = [
        ReputationEntry(name=f.name, label=standing_label(f.player_reputation))
        for f in _by_name(state.factions.values())
        if k.knows(f)
    ]
    moments: list[tuple[int, str, str]] = [
        (d.world_s, d.id, k.deed_text(d))
        for d in k.deeds()
        if d.actor_id == k.player_id or d.severity >= 3
    ]
    moments += [
        (f.world_s, f.id, f.text)
        for f in state.facts.values()
        if k.knows(f) and f.importance >= 4 and f.timeline_id == k.timeline
    ]
    moments.sort(key=lambda m: (m[0], natural_key(m[1])), reverse=True)
    since = [
        SinceEntry(text=text, ago_label=ago_label(k.now - when))
        for when, _, text in moments[:SINCE_LIMIT]
    ]
    return StatusView(
        character=StatusCharacter(name=player.name, lines=lines),
        reputation=reputation,
        clock=clock_view(state),
        since=since,
    )
