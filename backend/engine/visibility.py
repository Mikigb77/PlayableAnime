"""C6: what the player character knows, in the world's words (G16).

`memory_view` and `status_view` project the world state onto the player character's knowledge,
in the shapes of API.md's `MemoryView` and `StatusView`. They read only records whose knowledge
lists hold the player character (`known_by`, `met_by`, `heard_at`, a status change's `known_by`),
and never read hidden truth: whether a rumor or fact is true, how accurate a rumor is, secrets,
agendas, real attitudes behind an apparent one, trust (W4), faction plans (W6), witnesses the
player didn't notice, or anything on another timeline. The one exception is what the player
character knows for themselves: a rumor of something they did, suffered, saw or were there for is
confirmed, or false, rather than unconfirmed. A spoiler view after an arc ends is a separate
projection (P1).

The same words heard or done more than once show once: a fight of four blows is one rumor and one
deed, not four.

URLs for portraits and pictures are left empty here; the API fills them from the scene images.

The fixed words here (attitudes, standing, health, who saw a deed, "Heard 2 days ago") come in the
story's language (S10). What the world itself wrote, such as a fact or a deed's telling, stays in
the language it was written in.
"""

from functools import cached_property

from pydantic import Field

from engine import possessions
from engine.base import EngineModel
from engine.context import Language
from engine.kin import descendants
from engine.labels import ago_label, clock_label, in_label, number_label
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
    Transfer,
    Visibility,
)
from engine.state.sheet import Health
from engine.state.world import WorldState, natural_key
from engine.world.rumors import Certainty, certainty
from engine.world.telling import cap, tell

SINCE_LIMIT = 6
# C10: how many of the player character's latest gains and losses `/status` weighs among them.
SINCE_TRANSFERS = 3
EN = Language.EN
ES = Language.ES
CA = Language.CA
_DESCENDANT_WORDS = {
    EN: {1: "Your child.", 2: "Your grandchild."},
    ES: {1: "Tu hijo o hija.", 2: "Tu nieto o nieta."},
    CA: {1: "El teu fill o filla.", 2: "El teu nét o néta."},
}


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
    certainty: Certainty = Certainty.UNCONFIRMED
    unconfirmed: bool = True
    """`certainty` is unconfirmed: kept for apps older than `certainty`."""


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


# Spanish and Catalan have no gender-free adjective for most of these, and a character's gender
# isn't recorded, so their words are ones that fit anyone: "Cordial", "Con heridas", "Respeto".
_ATTITUDES = {
    EN: ("Warm", "Friendly", "Neutral", "Cold", "Hostile"),
    ES: ("Cordial", "Afable", "Neutral", "Distante", "Hostil"),
    CA: ("Cordial", "Afable", "Neutral", "Distant", "Hostil"),
}


def attitude_label(affinity: int, language: Language = EN) -> str:
    """How someone comes across toward the player character (W4): what they show, not what
    they feel."""
    warm, friendly, neutral, cold, hostile = _ATTITUDES[language]
    if affinity >= 60:
        return warm
    if affinity >= 20:
        return friendly
    if affinity > -20:
        return neutral
    if affinity > -60:
        return cold
    return hostile


_STANDING = {
    # admired, respected, disliked, despised, feared, wary, "and", neutral
    EN: ("Admired", "Respected", "Disliked", "Despised", "feared", "wary of you", "and", "Neutral"),
    ES: ("Admiración", "Respeto", "Recelo", "Desprecio", "temor", "cautela", "y", "Neutral"),
    CA: ("Admiració", "Respecte", "Recel", "Menyspreu", "temor", "cautela", "i", "Neutral"),
}


def standing_label(reputation: Reputation, language: Language = EN) -> str:
    """Esteem and fear in words (W3): "Respected and feared", "Despised", "Neutral"; in Spanish
    "Respeto y temor", "Desprecio", "Neutral"; in Catalan "Respecte i temor", "Menyspreu"."""
    admired, respected, disliked, despised, feared, wary, and_, neutral = _STANDING[language]
    esteem = reputation.esteem
    if esteem >= 60:
        words = admired
    elif esteem >= 20:
        words = respected
    elif esteem > -20:
        words = ""
    elif esteem > -60:
        words = disliked
    else:
        words = despised
    fear = feared if reputation.fear >= 60 else wary if reputation.fear >= 20 else ""
    if words and fear:
        return f"{words} {and_} {fear}"
    if fear:
        return fear[0].upper() + fear[1:]
    return words or neutral


_HEALTH_WORDS = {
    EN: {
        Health.UNHURT: "Unhurt",
        Health.HURT: "Hurt",
        Health.WOUNDED: "Wounded",
        Health.BADLY_WOUNDED: "Badly wounded",
        Health.DYING: "Dying",
    },
    ES: {
        Health.UNHURT: "Sin heridas",
        Health.HURT: "Con heridas leves",
        Health.WOUNDED: "Con heridas",
        Health.BADLY_WOUNDED: "Con heridas graves",
        Health.DYING: "Al borde de la muerte",
    },
    CA: {
        Health.UNHURT: "Sense ferides",
        Health.HURT: "Amb ferides lleus",
        Health.WOUNDED: "Amb ferides",
        Health.BADLY_WOUNDED: "Amb ferides greus",
        Health.DYING: "A punt de morir",
    },
}

# S10: every status a person, place or faction can show, in Spanish and Catalan, and how a death
# the player character only believes in reads.
_STATUS_WORDS = {
    ES: {
        CharacterStatus.ALIVE.value: "Con vida",
        CharacterStatus.MISSING.value: "En paradero desconocido",
        CharacterStatus.DEAD.value: "Ha muerto",
        PlaceStatus.THRIVING.value: "Próspero",
        PlaceStatus.DAMAGED.value: "Con daños",
        PlaceStatus.RUINED.value: "En ruinas",
        PlaceStatus.OCCUPIED.value: "Bajo ocupación",
        FactionStatus.INTACT.value: "Intacta",
        FactionStatus.WEAKENED.value: "Ha perdido fuerza",
        FactionStatus.REBUILDING.value: "Se está reconstruyendo",
        FactionStatus.DESTROYED.value: "Ya no existe",
        "presumed_dead": "Se cree que ha muerto",
    },
    CA: {
        CharacterStatus.ALIVE.value: "Amb vida",
        CharacterStatus.MISSING.value: "En parador desconegut",
        CharacterStatus.DEAD.value: "Ha mort",
        PlaceStatus.THRIVING.value: "Pròsper",
        PlaceStatus.DAMAGED.value: "Amb danys",
        PlaceStatus.RUINED.value: "En ruïnes",
        PlaceStatus.OCCUPIED.value: "Sota ocupació",
        FactionStatus.INTACT.value: "Intacta",
        FactionStatus.WEAKENED.value: "Ha perdut força",
        FactionStatus.REBUILDING.value: "S'està reconstruint",
        FactionStatus.DESTROYED.value: "Ja no existeix",
        "presumed_dead": "Es creu que ha mort",
    },
}

# S10: the other fixed words of Memory and Status.
_WORDS = {
    EN: {
        "saw": "You saw it",
        "heard_of": "You heard of it",
        "seen": "You were seen",
        "seen_by": "Seen by {names}",
        "other": "{count} other",
        "others": "{count} others",
        "public": "Done in public",
        "unseen": "No one saw, as far as you know",
        "parent": "Your parent.",
        "not_been": "You haven't been there.",
        "expecting": "Expecting a child, due {due}",
        "ready": "ready",
        "cost": "{power}, cost: {costs}",
        "ends": "Ends {when}",
        "heard": "Heard {when}",
        "and": " and ",
        "to": "To {who}: {what}",
        "from": "From {who}: {what}",
        "gained": "Gained: {what}",
        "lost": "Lost: {what}",
        "someone": "someone",
    },
    ES: {
        "saw": "Lo viste",
        "heard_of": "Te enteraste",
        "seen": "Te vieron",
        "seen_by": "Te vieron {names}",
        "other": "{count} persona más",
        "others": "{count} personas más",
        "public": "A la vista de todos",
        "unseen": "Nadie lo vio, que tú sepas",
        "parent": "Tu padre o tu madre.",
        "not_been": "Aún no has estado allí.",
        "expecting": "Esperando un bebé, que nacerá {due}",
        "ready": "disponible",
        "cost": "{power}, coste: {costs}",
        "ends": "Termina {when}",
        "heard": "Lo oíste {when}",
        "and": " y ",
        "to": "Para {who}: {what}",
        "from": "De {who}: {what}",
        "gained": "Ganancia: {what}",
        "lost": "Pérdida: {what}",
        "someone": "alguien",
    },
    CA: {
        "saw": "Ho vas veure",
        "heard_of": "Te'n vas assabentar",
        "seen": "Et van veure",
        "seen_by": "Et van veure {names}",
        "other": "{count} persona més",
        "others": "{count} persones més",
        "public": "A la vista de tothom",
        "unseen": "Ningú no ho va veure, que tu sàpigues",
        "parent": "El teu pare o la teva mare.",
        "not_been": "Encara no hi has estat.",
        "expecting": "Esperant un nadó, que naixerà {due}",
        "ready": "disponible",
        "cost": "{power}, cost: {costs}",
        "ends": "Acaba {when}",
        "heard": "Ho vas sentir {when}",
        "and": " i ",
        "to": "Per a {who}: {what}",
        "from": "De {who}: {what}",
        "gained": "Guany: {what}",
        "lost": "Pèrdua: {what}",
        "someone": "algú",
    },
}


def _status_words(status: str, presumed: bool = False, language: Language = EN) -> str:
    if words := _STATUS_WORDS.get(language):
        if status == CharacterStatus.DEAD.value and presumed:
            return words["presumed_dead"]
        return words.get(status) or status.replace("_", " ").capitalize()
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

    def __init__(self, state: WorldState, language: Language = EN) -> None:
        self.state = state
        self.language = language
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

    def transfer_text(self, transfer: Transfer) -> str:
        """C10. Something the player character gained or lost, in the story's language, naming
        the other side only if they know who it was: "To Milo: 12 copper coins". How it went
        (stolen, paid) is the model's word, in English, so it is left to the models' record."""
        words = _WORDS[self.language]
        what = transfer.name
        if transfer.money or transfer.quantity > 1:
            what = f"{number_label(transfer.quantity, self.language)} {transfer.name}"
        you = self.player_id
        if transfer.from_id == you:
            key, other = ("to", transfer.to_id) if transfer.to_id else ("lost", None)
        else:
            key, other = ("from", transfer.from_id) if transfer.from_id else ("gained", None)
        who = (self.name_of(other) or words["someone"]) if other else ""
        text = words[key].format(who=who, what=what)
        if key == "from" and self.language is CA and who[:1].casefold() in "aeiouhàèéíòóú":
            text = f"D'{who}: {what}"  # Catalan elides "de" before a vowel
        return _cap(text)

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

    def rumors(self) -> list[RumorEntry]:
        """The rumors the player character heard, each said once however many deeds or tellers
        it came from, by when they last heard it (W2, C6). One they know firsthand is confirmed,
        or false, rather than unconfirmed: what they lived needs no confirming."""
        heard = [
            r
            for r in self.state.rumors.values()
            if self.player_id in r.heard_at and r.timeline_id == self.timeline
        ]
        said: dict[str, list] = {}
        for rumor in heard:
            said.setdefault(_said(rumor.text), []).append(rumor)
        entries = []
        for same in said.values():
            same.sort(key=lambda r: (r.heard_at[self.player_id], natural_key(r.id)))
            latest = same[-1]
            known = {certainty(self.state, self.player_id, r) for r in same}
            # What they lived settles it; one telling they can't check keeps it open.
            sure = next(
                (c for c in (Certainty.CONFIRMED, Certainty.UNCONFIRMED) if c in known),
                Certainty.FALSE,
            )
            entries.append((latest.heard_at[self.player_id], latest, sure))
        entries.sort(key=lambda e: (e[0], natural_key(e[1].id)))
        words = _WORDS[self.language]
        return [
            RumorEntry(
                id=rumor.id,
                text=rumor.text,
                heard_label=words["heard"].format(when=ago_label(self.now - when, self.language)),
                certainty=sure,
                unconfirmed=sure is Certainty.UNCONFIRMED,
            )
            for when, rumor, sure in entries
        ]

    def known_label(self, deed: Deed) -> str:
        """Who saw it, as far as the player character knows (W2, C6)."""
        words = _WORDS[self.language]
        if deed.actor_id != self.player_id:
            if self.player_id in deed.witness_ids:
                return words["saw"]
            return words["heard_of"]
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
                return words["seen"]
            if others:
                names.append(words["others" if others > 1 else "other"].format(count=others))
            return words["seen_by"].format(names=_join(names, self.language))
        if deed.visibility is Visibility.PUBLIC and not deed.in_stopped_time:
            return words["public"]
        return words["unseen"]

    # --- entries --------------------------------------------------------------------------

    def person(self, c: Character) -> PersonEntry:
        lines = [c.description] if c.description else []
        if kin := self.kin_line(c):
            lines.insert(0, kin)
        lines += self.facts_about(c.id)
        attitude = None
        if self.player_id in c.met_by:
            attitude = attitude_label(
                c.attitude_toward(self.player_id).shown_affinity, self.language
            )
        status, presumed = believed_status(
            c.status_history, c.status.value, self.player_id, initial=CharacterStatus.ALIVE.value
        )
        return PersonEntry(
            id=c.id,
            name=c.name,
            lines=lines,
            attitude_label=attitude,
            status_label=_status_words(status, presumed, self.language),
        )

    @cached_property
    def descendants(self) -> dict[str, int]:
        return descendants(self.state, self.player_id)

    def kin_line(self, c: Character) -> str | None:
        """N6: how someone is family to the player character, if they are."""
        if c.id in self.state.player.parent_ids:
            return _WORDS[self.language]["parent"]
        return _DESCENDANT_WORDS[self.language].get(self.descendants.get(c.id, 0))

    def place(self, p: Place) -> PlaceEntry:
        lines = [_cap(p.kind)] if p.kind else []
        if p.description:
            lines.append(p.description)
        status, _ = believed_status(
            p.status_history, p.status.value, self.player_id, initial=PlaceStatus.THRIVING.value
        )
        if status != PlaceStatus.THRIVING.value:
            lines.append(_status_words(status, language=self.language))
        if self.player_id not in p.visited_by:
            lines.append(_WORDS[self.language]["not_been"])
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
            lines.append(_status_words(status, language=self.language))
        lines += self.facts_about(f.id)
        return FactionEntry(
            id=f.id,
            name=f.name,
            lines=lines,
            standing_label=standing_label(f.player_reputation, self.language),
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
        lines = [_HEALTH_WORDS[self.language][condition.health]]
        lines += [_cap(w.text) for w in condition.wounds]
        lines += [_cap(s.name) for s in condition.states]
        lines += [_cap(f"{r.name}: {r.level}%") for r in condition.reserves]
        expecting = player.expecting
        if expecting is not None and player.alive:
            # N6: a child on the way, born when it is due.
            due = in_label(max(0, expecting.due_s - self.now), self.language)
            lines.append(_WORDS[self.language]["expecting"].format(due=due))
        return lines

    def power_lines(self, player: Character) -> list[str]:
        lived = player.personal_s(self.now)
        lines = []
        ready = _WORDS[self.language]["ready"]
        for power in player.sheet.powers:
            ready_at = power.ready_at_personal_s
            if ready_at is not None and ready_at > lived:
                when = in_label(ready_at - lived, self.language)
                lines.append(_cap(f"{power.name}: {ready} {when}"))
            else:
                lines.append(_cap(f"{power.name}: {ready}"))
            # G13: what using it costs, as the sheet says, so nothing about it is a surprise.
            costs = power.costs_text
            if costs:
                cost = _WORDS[self.language]["cost"].format(power=power.name, costs=costs)
                lines.append(_cap(cost))
        return lines

    def resource_lines(self, player: Character) -> list[str]:
        resources = player.sheet.resources
        lines = []
        if resources.money or resources.currency:
            money = number_label(resources.money, self.language)
            lines.append(f"{money} {resources.currency}".strip())
        for item in sorted(resources.items, key=lambda i: natural_key(i.id)):
            if item.carried:
                count = f" ({item.quantity})" if item.quantity > 1 else ""
                lines.append(_cap(f"{item.name}{count}"))
        return lines


def _cap(text: str) -> str:
    """Capitalises the first letter only, keeping names such as "Qi Condensation" intact."""
    return text[:1].upper() + text[1:]


def _join(names: list[str], language: Language = EN) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + _WORDS[language]["and"] + names[-1]


def _sort_name(name: str) -> str:
    folded = name.casefold()
    for article in ("the ", "a ", "an "):
        if folded.startswith(article):
            return folded[len(article) :]
    return folded


def _by_name(records):
    """Alphabetical, ignoring a leading article: "the Azure Cloud Sect" sorts under A."""
    return sorted(records, key=lambda r: (_sort_name(r.name), natural_key(r.id)))


def _said(text: str) -> str:
    """Words as said, for telling the same words apart from new ones: case, spacing and the
    closing stop don't count."""
    return " ".join(text.casefold().split()).rstrip(".")


def _once(entries: list, *, key) -> list:
    """Each entry once, where it first comes: the same words at the same time say nothing new."""
    seen: set = set()
    kept = []
    for entry in entries:
        if (mark := key(entry)) not in seen:
            seen.add(mark)
            kept.append(entry)
    return kept


def memory_view(state: WorldState, language: Language = EN) -> MemoryView:
    """The Memory screen (C6): only what the player character knows, with its fixed words in the
    story's language (S10)."""
    k = _Knowledge(state, language)
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
        expires = None
        if lead.expires_s is not None:
            when = in_label(lead.expires_s - k.now, language)
            expires = _WORDS[language]["ends"].format(when=when)
        leads.append(LeadEntry(id=lead.id, text=lead.text, expires_label=expires))
    rumors = k.rumors()
    deeds = _once(
        [
            DeedEntry(
                id=d.id,
                text=k.deed_text(d),
                when_label=clock_label(calendar, d.world_s, language),
                known_label=k.known_label(d),
            )
            for d in k.deeds()
        ],
        key=lambda e: (_said(e.text), e.when_label, e.known_label),
    )
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


# Gemini 3.5 Transcribe takes up to 1,000 terms but works best with about 100 (V6).
SPEECH_VOCABULARY_LIMIT = 100


def speech_vocabulary(state: WorldState, *, limit: int = SPEECH_VOCABULARY_LIMIT) -> list[str]:
    """The names the player character knows, as the speech model's custom vocabulary (V6, C6),
    so a dictated "Senior Brother Jo" comes back as Zhao.

    Most relevant first: the character's own name, the people in the scene, the place it is in,
    then everyone, everywhere and every faction the character knows, without a leading article.
    Never a name the character doesn't know (C6), and each name once.
    """
    k = _Knowledge(state)
    present = [state.characters.get(i) for i in state.scene.present_ids]
    here = state.places.get(state.scene.place_id or state.player.location_id or "")
    known = [
        *(c for c in present if c is not None and c.id != state.player_id and k.knows(c)),
        *([here] if here is not None and k.knows(here) else []),
        *(c for c in _by_name(state.npcs()) if k.knows(c)),
        *(p for p in _by_name(state.places.values()) if k.knows(p)),
        *(f for f in _by_name(state.factions.values()) if k.knows(f)),
    ]
    names: dict[str, str] = {}
    for name in (state.player.name, *(record.name for record in known)):
        name = _without_article(" ".join(name.split()))
        if name and name.casefold() not in names:
            names[name.casefold()] = name
    return list(names.values())[:limit]


def _without_article(name: str) -> str:
    """ "the Azure Cloud Sect" is heard as "Azure Cloud Sect": "the" is a common word. Only
    "the": "A" and "An" start names such as A Qing and An Lushan."""
    if name.casefold().startswith("the ") and len(name) > len("the "):
        return name[len("the ") :]
    return name


def clock_view(state: WorldState, language: Language = EN) -> ClockView:
    return ClockView(
        world_s=state.world_s,
        label=clock_label(state.bible.calendar, state.world_s, language),
        timeline_id=state.timeline_id,
    )


def status_view(state: WorldState, language: Language = EN) -> StatusView:
    """`/status` (A8, G16, W10): the player character's sheet in the world's words, their
    standing with the factions they know, the clock, and how long ago key events happened, with
    the fixed words in the story's language (S10)."""
    k = _Knowledge(state, language)
    player = state.player
    lines = (
        k.ladder_lines(player)
        + k.condition_lines(player)
        + k.power_lines(player)
        + k.resource_lines(player)
    )
    reputation = [
        ReputationEntry(name=f.name, label=standing_label(f.player_reputation, language))
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
    # C10: what the player character gained and lost lately, and to whom.
    mine = possessions.involving(state, k.player_id)[-SINCE_TRANSFERS:]
    moments += [(t.world_s, f"transfer-{n}", k.transfer_text(t)) for n, t in enumerate(mine)]
    moments.sort(key=lambda m: (m[0], natural_key(m[1])), reverse=True)
    since = _once(
        [
            SinceEntry(text=text, ago_label=ago_label(k.now - when, language))
            for when, _, text in moments
        ],
        key=lambda e: (_said(e.text), e.ago_label),
    )[:SINCE_LIMIT]
    return StatusView(
        character=StatusCharacter(name=player.name, lines=lines),
        reputation=reputation,
        clock=clock_view(state, language),
        since=since,
    )
