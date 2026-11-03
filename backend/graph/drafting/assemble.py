"""Turns the drafter's proposal into a `WorldState` (G1, G2, A1). The model proposes; this module
decides, and every rule here has a unit test.

- **Clean ids.** Every record gets a unique slug id, and references resolve by id or by name.
  References to nothing are dropped. The player character is always `player`.
- **G7.** A starter premise's fixed rules hold, and the extraordinary kinds its genre fixes keep
  their prevalence, unless the player let that rule go while setting up the story. Every kind of
  extraordinary thing has a rule saying whether it exists, fixed by default, and a world with no
  extraordinary kinds at all says so with a fixed rule. A proposal that calls the world grounded
  when its genre has something extraordinary loses that claim and the rules tied to it.
- **G8.** Nobody has a power the world doesn't have: in a world where nothing extraordinary exists,
  or from a kind that doesn't exist, a power is dropped. In such a world nobody goes past what a
  real person could do (A4, G6), so attributes stop at 5. When a starter premise grounds the
  world, the model's own kinds, the rules tied only to them and any power ladder go too.
- **G18.** Ladder rungs map to A8 tiers two apart, lowest first, and a character's rung sets their
  tier on the ladder's axis.
- **G22.** The gift strength the player picked wins over the premise's and the model's, and `none`
  removes the gift. Time stop lasts three heartbeats and recharges in a breath unless the draft
  says otherwise, and hits at relative speed when overpowered and with normal force when not.
- **C6.** Who knows what: `known_by`, `met_by` and `visited_by` start from what the player
  character knows, and secrets, agendas, mystery answers and a body's forgotten past are recorded
  where only code and the narrator see them.
- **W15, K8.** At most 8 key characters and 4 factions start active; the rest start dormant.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from engine.base import HOUR, MINUTE, TIER_MAX, YEAR
from engine.invariants import InvariantError, check_state, is_real_name
from engine.state import (
    Activity,
    Agenda,
    Attitude,
    Attributes,
    BackstoryClaim,
    Calendar,
    CalendarStyle,
    Character,
    CharacterSheet,
    Clock,
    Condition,
    Connection,
    Creature,
    Disposition,
    Extraordinary,
    Fact,
    Faction,
    FactKind,
    GiftStrength,
    Goal,
    HitMode,
    Item,
    LadderPosition,
    Law,
    Medicine,
    Membership,
    Month,
    Mystery,
    Origin,
    OriginKind,
    People,
    PhysicsMode,
    Place,
    Power,
    PowerAxes,
    PowerCost,
    PowerLadder,
    Prevalence,
    Prominence,
    Reserve,
    Resources,
    Route,
    RuleTopic,
    Rung,
    SceneFrame,
    Skill,
    Technique,
    Temperament,
    Thread,
    ThreadKind,
    TimeEffect,
    TimeOfDayStyle,
    TimePower,
    Trait,
    Travel,
    WorldBible,
    WorldRule,
    WorldState,
)
from graph.drafting.catalog import PremiseTemplate
from graph.drafting.schema import (
    PLAYER_ID,
    AttributesP,
    AxesP,
    CalendarP,
    CharacterProposal,
    LadderPositionP,
    MembershipP,
    NpcP,
    PowerP,
    TemperamentP,
    TimeP,
    WorldProposal,
)

ACTIVE_NPCS = 8  # W15, K8: the active cast to start
ACTIVE_FACTIONS = 4
HUMAN_PEAK = 5  # G13: the peak of what a person can be
STOP_LASTS_S = 3  # G22: three heartbeats
STOP_RECHARGE_S = 5  # G22: a breath
DEFAULT_GIFT = GiftStrength.RARE

# How much of each list is kept. The prompt asks for less; this only bounds a runaway answer.
MAX = {
    "kinds": 12,
    "rules": 20,
    "peoples": 12,
    "creatures": 16,
    "ladders": 4,
    "rungs": 12,
    "places": 20,
    "factions": 10,
    "npcs": 12,
    "clocks": 6,
    "threads": 10,
    "mysteries": 4,
    "laws": 10,
    "lines": 12,
    "items": 24,
    "sheet": 12,
    "facts": 12,
}
TEXT_LIMIT = 600
NAME_LIMIT = 120

GROUNDED_KIND = Extraordinary(
    id="supernatural",
    kind="magic or anything supernatural",
    prevalence=Prevalence.NONE,
)
PLAYER_FALLBACK_NAME = "Wanderer"
GROUNDED_RULE_TEXT = "Grounded: no magic and nothing supernatural, and that won't change."


@dataclass(frozen=True)
class DraftOptions:
    """What the player set up, plus the starter premise's template (G7, G22, A9)."""

    premise: str = ""
    physics: PhysicsMode = PhysicsMode.FUN_FIRST
    gift: GiftStrength | None = None  # None: the premise's own, then the model's
    template: PremiseTemplate | None = None
    released_rules: frozenset[str] = frozenset()

    def holds(self, rule_id: str) -> bool:
        """Whether a template rule still binds the draft (G7)."""
        return self.template is not None and rule_id not in self.released_rules


def assemble(
    world: WorldProposal, character: CharacterProposal, options: DraftOptions | None = None
) -> WorldState:
    """The opening world state for a drafted world and character. Pure and deterministic.

    Raises `engine.invariants.InvariantError` if the state breaks a C1 invariant, which would be
    a bug here: a broken state is never handed on to be saved.
    """
    state = _Assembler(world, character, options or DraftOptions()).build()
    if violations := check_state(state):
        raise InvariantError(violations)
    return state


# Ids.

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """A short lowercase id: "Café Nero" is "cafe-nero"."""
    plain = unicodedata.normalize("NFKD", (text or "").casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return _NON_SLUG.sub("-", plain).strip("-")[:48].strip("-")


class _Ids:
    """Maps the model's ids in one collection to clean unique ones. A reference resolves by the
    id the model gave, by its slug, or by the record's name."""

    def __init__(self, prefix: str, reserved: Iterable[str] = ()):
        self._prefix = prefix
        self._used = set(reserved)
        self._map: dict[str, str] = {}

    def add(self, raw: str, name: str = "") -> str:
        base = slug(raw) or slug(name) or self._prefix
        candidate, n = base, 2
        while candidate in self._used:
            candidate, n = f"{base}-{n}", n + 1
        self._used.add(candidate)
        for key in (raw, slug(raw), slug(name)):
            self.alias(key, candidate)
        return candidate

    def claim(self, record_id: str) -> str:
        """Takes a fixed id, such as a template rule's, so no other record gets it."""
        self._used.add(record_id)
        self._map[record_id] = record_id
        return record_id

    def alias(self, key: str, target: str) -> None:
        if key and key not in self._map:
            self._map[key] = target

    def get(self, raw: str | None) -> str | None:
        if not raw:
            return None
        return self._map.get(raw) or self._map.get(slug(raw))

    def all(self, raws: Iterable[str]) -> list[str]:
        return _unique(i for i in (self.get(r) for r in raws) if i)


# Small helpers.


def _text(value: str | None, limit: int = TEXT_LIMIT) -> str:
    return " ".join((value or "").split())[:limit].strip()


def _name(value: str | None) -> str:
    return _text(value, NAME_LIMIT)


def _texts(values: Iterable[str], limit: int, size: int = TEXT_LIMIT) -> list[str]:
    return _unique(t for t in (_text(v, size) for v in values) if t)[:limit]


def _unique[T](items: Iterable[T]) -> list[T]:
    return list(dict.fromkeys(items))


def _clamp(value: float | int | None, low: int, high: int, default: int) -> int:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return default
    return max(low, min(high, round(value)))


def _seconds(hours: float | None, *, low: int = MINUTE, high: int = 10 * YEAR) -> int | None:
    if hours is None or not math.isfinite(hours) or hours <= 0:
        return None
    return max(low, min(high, round(hours * HOUR)))


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


@dataclass
class _Ladders:
    by_id: dict[str, PowerLadder] = field(default_factory=dict)
    ids: _Ids = field(default_factory=lambda: _Ids("ladder"))

    def find(self, raw: str) -> PowerLadder | None:
        ladder_id = self.ids.get(raw)
        return self.by_id.get(ladder_id) if ladder_id else None


def _rung_index(ladder: PowerLadder, rung: str) -> int | None:
    wanted = " ".join(rung.casefold().split())
    if not wanted:
        return None
    names = [r.name.casefold() for r in ladder.rungs]
    if wanted in names:
        return names.index(wanted)
    if wanted.isdigit():
        index = int(wanted)
        return index if index < len(names) else None
    # "Foundation Establishment (peak)" or "peak of Foundation Establishment"
    matches = [i for i, name in enumerate(names) if name in wanted or wanted in name]
    return max(matches, key=lambda i: len(names[i])) if matches else None


class _Assembler:
    def __init__(self, world: WorldProposal, character: CharacterProposal, options: DraftOptions):
        self.world = world
        self.character = character
        self.options = options
        self.kinds = _Ids("kind")
        self.rules = _Ids("rule")
        self.peoples = _Ids("people")
        self.places = _Ids("place")
        self.factions = _Ids("faction")
        self.chars = _Ids("character", reserved=[PLAYER_ID])
        self.clocks = _Ids("clock")
        self.threads = _Ids("thread")
        self.ladders = _Ladders()

    # The whole state.

    def build(self) -> WorldState:
        self._reserve_ids()
        bible = self._bible()
        self.bible = bible
        self.possible_kinds = {
            e.id for e in bible.extraordinary if e.prevalence is not Prevalence.NONE
        }
        self.grounded = not self.possible_kinds

        places = self._places()
        factions = self._factions()
        npcs = self._npcs()
        player = self._player()
        characters = {PLAYER_ID: player, **{c.id: c for c in npcs}}
        clocks = self._clocks()
        threads = self._threads()
        self._link_threads(clocks, threads, bible.mysteries)
        scene = self._scene(places, characters)
        self._spread_knowledge(places, factions, player)
        facts = self._facts()
        goals = {
            f"goal-{i}": Goal(id=f"goal-{i}", text=text)
            for i, text in enumerate(_texts(self.character.goals, 6, 300), start=1)
        }
        return WorldState(
            bible=bible,
            player_id=PLAYER_ID,
            characters=characters,
            factions={f.id: f for f in factions},
            places={p.id: p for p in places},
            facts=facts,
            goals=goals,
            threads={t.id: t for t in threads},
            clocks={c.id: c for c in clocks},
            scene=scene,
            summary=_text(self.world.summary, 1200) or _text(self.options.premise, 1200),
            id_counters={"fact": len(facts), "goal": len(goals)},
        )

    def _reserve_ids(self) -> None:
        """Gives every record that will be built its id first, so references can resolve in any
        order. Records too empty to build (C1: no nameless characters) get none."""
        w = self.world
        self.kind_list = list(
            zip(
                [self.kinds.add(k.id, k.kind) for k in w.extraordinary[: MAX["kinds"]]],
                w.extraordinary[: MAX["kinds"]],
                strict=True,
            )
        )
        self.people_list = _with_ids(
            self.peoples, [p for p in w.peoples[: MAX["peoples"]] if _name(p.name)], "name"
        )
        self.place_list = _with_ids(
            self.places, [p for p in w.places[: MAX["places"]] if _name(p.name)], "name"
        )
        self.faction_list = _with_ids(
            self.factions, [f for f in w.factions[: MAX["factions"]] if _name(f.name)], "name"
        )
        self.npc_list = _with_ids(
            self.chars, [n for n in w.npcs[: MAX["npcs"]] if is_real_name(_name(n.name))], "name"
        )
        # After the NPCs, so an NPC's own id always wins over the player's name.
        for key in (self.character.name, "pc", "you", "me"):
            self.chars.alias(key, PLAYER_ID)
            self.chars.alias(slug(key), PLAYER_ID)
        self.clock_list = _with_ids(
            self.clocks,
            [c for c in w.clocks[: MAX["clocks"]] if _texts(c.steps, 1)],
            "name",
        )
        self.thread_list = _with_ids(
            self.threads, [t for t in w.threads[: MAX["threads"]] if _text(t.title)], "title"
        )

    # The bible (G6, G7, G18, G23, G24, W11, N7).

    def _bible(self) -> WorldBible:
        w, options = self.world, self.options
        template = options.template
        kinds: dict[str, Extraordinary] = {}
        for kind_id, proposed in self.kind_list:
            kinds[kind_id] = Extraordinary(
                id=kind_id,
                kind=_name(proposed.kind) or kind_id,
                prevalence=proposed.prevalence,
                reach=_text(proposed.reach),
            )

        rules: dict[str, WorldRule] = {}
        links: dict[str, list[str]] = {}
        for proposed in w.rules[: MAX["rules"]]:
            text = _text(proposed.text, 300)
            if not text:
                continue
            rule_id = self.rules.add(proposed.id, text)
            rules[rule_id] = WorldRule(
                id=rule_id, text=text, fixed=proposed.fixed, topic=proposed.topic
            )
            for kind_id in self.kinds.all(proposed.about):
                links.setdefault(kind_id, []).append(rule_id)

        peoples = {}
        for people_id, proposed in self.people_list:
            peoples[people_id] = People(
                id=people_id,
                name=_name(proposed.name),
                description=_text(proposed.description),
                lifespan_years=None
                if proposed.lifespan_years is None
                else _clamp(proposed.lifespan_years, 0, 1_000_000, 0),
                gifts=_texts(proposed.gifts, 8, 200),
                culture=_text(proposed.culture),
                relations=_texts(proposed.relations, 8, 300),
                path=_text(proposed.path),
            )

        ladders = self._power_ladders()

        if template is not None:
            self._apply_template(template, kinds, rules, links, peoples, ladders)

        self._existence_rules(kinds, rules, links)
        for kind_id, rule_ids in links.items():
            if kind_id in kinds:
                kinds[kind_id].rule_ids = _unique(r for r in rule_ids if r in rules)

        return WorldBible(
            title=_text(w.title, 120),
            genre=_text(w.genre, 80),
            tone=_text(w.tone, 200),
            era=_text(w.era, 300),
            extraordinary=list(kinds.values()),
            peoples=list(peoples.values()),
            creatures=self._creatures(),
            nature=_texts(w.nature, 8, 300),
            physics=options.physics,
            ladders=list(self.ladders.by_id.values()),
            calendar=_calendar(w.calendar),
            travel=Travel(
                description=_text(w.travel.description),
                instant_messages=w.travel.instant_messages,
            ),
            medicine=Medicine(
                healing=_text(w.medicine.healing),
                resurrection=w.medicine.resurrection,
                resurrection_means=_text(w.medicine.resurrection_means),
            ),
            laws=self._laws(),
            norms=_texts(w.norms, 8, 300),
            rules=list(rules.values()),
            mysteries=self._mysteries(),
        )

    def _apply_template(
        self,
        template: PremiseTemplate,
        kinds: dict[str, Extraordinary],
        rules: dict[str, WorldRule],
        links: dict[str, list[str]],
        peoples: dict[str, People],
        ladders: dict[str, PowerLadder],
    ) -> None:
        """G7: a starter premise's fixed rules hold until the player lets them go."""
        holds = self.options.holds
        for rule in template.rules:
            if holds(rule.id):
                rules[self.rules.claim(rule.id)] = rule.model_copy()
        required_ids: set[str] = set()
        for required in template.extraordinary:
            if not all(holds(rule_id) for rule_id in required.rule_ids):
                continue
            kind_id = self.kinds.get(required.id)
            if kind_id not in kinds:
                kind_id = self.kinds.add(required.id, required.kind)
                kinds[kind_id] = required.model_copy(update={"id": kind_id, "rule_ids": []})
            kinds[kind_id].prevalence = required.prevalence
            links.setdefault(kind_id, []).extend(required.rule_ids)
            required_ids.add(kind_id)
        if template.grounded_rule_id and holds(template.grounded_rule_id):
            # G8: nothing extraordinary exists, so neither do the model's kinds, their rules or a
            # power ladder.
            dropped = {k for k in kinds if k not in required_ids}
            for kind in kinds.values():
                kind.prevalence = Prevalence.NONE
            self.ladders.by_id.clear()
        elif any(kinds[k].prevalence is not Prevalence.NONE for k in required_ids):
            # The genre has something extraordinary, so a proposal that called the world
            # grounded is wrong about it.
            dropped = {
                k
                for k, kind in kinds.items()
                if k not in required_ids
                and kind.prevalence is Prevalence.NONE
                and _is_grounded_kind(kind)
            }
        else:
            dropped = set()
        if dropped:
            template_rules = {rule.id for rule in template.rules}
            for rule_id in list(rules):
                linked = [k for k, rule_ids in links.items() if rule_id in rule_ids]
                if rule_id not in template_rules and linked and set(linked) <= dropped:
                    del rules[rule_id]
            for kind_id in dropped:
                del kinds[kind_id]
                links.pop(kind_id, None)
        existence_held = all(
            holds(rule.id) for rule in template.rules if rule.topic is RuleTopic.EXISTENCE
        )
        if template.ladder is not None and existence_held and not ladders:
            ladder = template.ladder.model_copy(deep=True)
            self.ladders.by_id[ladder.id] = ladder
            self.ladders.ids.add(ladder.id, ladder.name)
        peoples_held = all(
            holds(rule.id) for rule in template.rules if rule.topic is RuleTopic.PEOPLES
        )
        if peoples_held:
            for people in template.peoples:
                known = self.peoples.get(people.id) or self.peoples.get(people.name)
                if known is None or known not in peoples:
                    people_id = self.peoples.add(people.id, people.name)
                    peoples[people_id] = people.model_copy(update={"id": people_id})

    def _existence_rules(
        self,
        kinds: dict[str, Extraordinary],
        rules: dict[str, WorldRule],
        links: dict[str, list[str]],
    ) -> None:
        """G7: every kind says whether it exists, fixed by default, and a world with no kinds at
        all says it is grounded."""
        existence = [r for r in rules.values() if r.topic is RuleTopic.EXISTENCE]
        if not kinds:
            kind_id = self.kinds.add(GROUNDED_KIND.id, GROUNDED_KIND.kind)
            kinds[kind_id] = GROUNDED_KIND.model_copy(update={"id": kind_id})
            if existence:
                links.setdefault(kind_id, []).extend(r.id for r in existence)
        for kind_id, kind in kinds.items():
            existence_ids = {r.id for r in existence}
            if any(r in existence_ids for r in links.get(kind_id, [])):
                continue
            mentioned = [r.id for r in existence if _mentions(r.text, kind.kind)]
            if mentioned:
                links.setdefault(kind_id, []).extend(mentioned)
                continue
            if kind.prevalence is Prevalence.NONE and len(kinds) == 1:
                text, rule_id = GROUNDED_RULE_TEXT, self.rules.add("no-supernatural")
            else:
                text, rule_id = _existence_text(kind), self.rules.add(f"{kind_id}-exists")
            rule = WorldRule(id=rule_id, text=text, fixed=True, topic=RuleTopic.EXISTENCE)
            rules[rule_id] = rule
            existence.append(rule)
            links.setdefault(kind_id, []).append(rule_id)

    def _power_ladders(self) -> dict[str, PowerLadder]:
        for proposed in self.world.ladders[: MAX["ladders"]]:
            rungs = [r for r in proposed.rungs if _name(r.name)][: MAX["rungs"]]
            if not rungs:
                continue
            ladder_id = self.ladders.ids.add(proposed.id, proposed.name)
            # G18: rungs map to tiers two apart, lowest first, so a weakened or wounded character
            # can stand between two rungs (A8).
            self.ladders.by_id[ladder_id] = PowerLadder(
                id=ladder_id,
                name=_name(proposed.name) or ladder_id,
                axis=proposed.axis,
                rungs=[
                    Rung(
                        name=_name(r.name),
                        tier=min(TIER_MAX, 2 * (i + 1)),
                        description=_text(r.description, 300),
                    )
                    for i, r in enumerate(rungs)
                ],
                standing_follows=proposed.standing_follows,
                sensing=proposed.sensing,
            )
        return self.ladders.by_id

    def _creatures(self) -> list[Creature]:
        creatures = []
        ids = _Ids("creature")
        for proposed in self.world.creatures[: MAX["creatures"]]:
            name = _name(proposed.name)
            if not name:
                continue
            tier = 1
            for ladder in self.ladders.by_id.values():
                index = _rung_index(ladder, proposed.rung)
                if index is not None:
                    tier = ladder.rungs[index].tier
                    break
            creatures.append(
                Creature(
                    id=ids.add(proposed.id, name),
                    name=name,
                    description=_text(proposed.description),
                    tier=tier,
                    habitat=_text(proposed.habitat, 200),
                    worth=_text(proposed.worth, 200),
                    can_be_tamed=proposed.can_be_tamed,
                )
            )
        return creatures

    def _laws(self) -> list[Law]:
        laws = []
        ids = _Ids("law")
        for proposed in self.world.laws[: MAX["laws"]]:
            text = _text(proposed.text, 300)
            if not text:
                continue
            laws.append(
                Law(
                    id=ids.add(proposed.id, text),
                    text=text,
                    enforcer=_text(proposed.enforcer, 200),
                    enforcer_faction_id=self.factions.get(proposed.enforcer_faction_id),
                    zeal=proposed.zeal,
                    corruptible=proposed.corruptible,
                )
            )
        return laws

    def _mysteries(self) -> list[Mystery]:
        mysteries = []
        ids = _Ids("mystery")
        self.mystery_threads: dict[str, bool] = {}
        for proposed in self.world.mysteries[: MAX["mysteries"]]:
            question, answer = _text(proposed.question, 300), _text(proposed.answer)
            if not question or not answer:
                continue
            mystery_id = ids.add(proposed.id, question)
            thread_id = self.threads.get(proposed.thread_id)
            if thread_id is None:
                # N1: every major mystery is an open thread.
                thread_id = self.threads.add(mystery_id, question)
                self.mystery_threads[thread_id] = proposed.known_to_player
            mysteries.append(
                Mystery(
                    id=mystery_id,
                    question=question,
                    answer=answer,
                    clues=_texts(proposed.clues, 8, 300),
                    thread_id=thread_id,
                )
            )
        return mysteries

    # The map and the cast (G10, G13, W3, W7, W15).

    def _places(self) -> list[Place]:
        places: dict[str, Place] = {}
        for place_id, proposed in self.place_list:
            routes = {}
            for route in proposed.routes:
                to_id = self.places.get(route.to_id)
                travel_s = _seconds(route.travel_hours, low=1)
                if to_id and to_id != place_id and travel_s is not None:
                    routes.setdefault(
                        to_id, Route(to_id=to_id, travel_s=travel_s, mode=_text(route.mode, 80))
                    )
            places[place_id] = Place(
                id=place_id,
                name=_name(proposed.name),
                kind=_text(proposed.kind, 80),
                description=_text(proposed.description),
                parent_id=self.places.get(proposed.parent_id),
                controller_id=self.factions.get(proposed.controller_id)
                or self.chars.get(proposed.controller_id),
                mood=_text(proposed.mood, 200),
                routes=list(routes.values()),
                known_by=[PLAYER_ID] if proposed.known_to_player else [],
            )
        for place in places.values():
            if place.parent_id not in places or place.parent_id == place.id:
                place.parent_id = None
            # W7: a road runs both ways.
            for route in place.routes:
                if route.to_id not in places:
                    continue
                back = places[route.to_id]
                if back.travel_s_to(place.id) is None:
                    back.routes.append(route.model_copy(update={"to_id": place.id}))
            place.routes = [r for r in place.routes if r.to_id in places]
        _break_cycles(places)
        return list(places.values())

    def _factions(self) -> list[Faction]:
        factions: dict[str, Faction] = {}
        for faction_id, proposed in self.faction_list:
            relations = {}
            for relation in proposed.relations:
                other = self.factions.get(relation.faction_id)
                if other and other != faction_id:
                    relations[other] = _clamp(relation.stance, -100, 100, 0)
            factions[faction_id] = Faction(
                id=faction_id,
                name=_name(proposed.name),
                kind=_text(proposed.kind, 80),
                description=_text(proposed.description),
                parent_id=self.factions.get(proposed.parent_id),
                activity=Activity.ACTIVE if len(factions) < ACTIVE_FACTIONS else Activity.DORMANT,
                leader_ids=self.chars.all(proposed.leader_ids),
                goal=_text(proposed.goal),
                methods=_text(proposed.methods),
                strength=_text(proposed.strength),
                relations=relations,
                secrets=_texts(proposed.secrets, 6),
                origin=Origin(kind=OriginKind.PREMISE),
                known_by=[PLAYER_ID] if proposed.known_to_player else [],
            )
        for faction in factions.values():
            if faction.parent_id not in factions or faction.parent_id == faction.id:
                faction.parent_id = None
            faction.relations = {k: v for k, v in faction.relations.items() if k in factions}
        _break_cycles(factions)
        return list(factions.values())

    def _npcs(self) -> list[Character]:
        npcs = []
        for index, (npc_id, proposed) in enumerate(self.npc_list):
            sheet = self._sheet(proposed, player=False)
            attitude = proposed.attitude_to_player
            sheet.disposition.attitudes[PLAYER_ID] = Attitude(
                affinity=_clamp(attitude.affinity, -100, 100, 0),
                fear=_clamp(attitude.fear, 0, 100, 0),
                trust=_clamp(attitude.trust, -100, 100, 0),
                apparent_affinity=None
                if attitude.shown_affinity is None
                else _clamp(attitude.shown_affinity, -100, 100, 0),
            )
            agenda = None
            if proposed.agenda is not None and _text(proposed.agenda.goal):
                agenda = Agenda(
                    goal=_text(proposed.agenda.goal),
                    method=_text(proposed.agenda.method),
                    secret=_text(proposed.agenda.secret),
                    clock_id=self.clocks.get(proposed.agenda.clock_id),
                )
            knows = proposed.player_knows
            npcs.append(
                Character(
                    id=npc_id,
                    name=_name(proposed.name),
                    aliases=_texts(proposed.aliases, 4, NAME_LIMIT),
                    prominence=Prominence.KEY,
                    description=_text(proposed.description),
                    appearance=_text(proposed.appearance),
                    age=_age(proposed.age),
                    people_id=self.peoples.get(proposed.people_id),
                    location_id=self.places.get(proposed.location_id),
                    memberships=self._memberships(proposed.memberships),
                    sheet=sheet,
                    agenda=agenda,
                    secrets=_texts(proposed.secrets, 6),
                    activity=Activity.ACTIVE if index < ACTIVE_NPCS else Activity.DORMANT,
                    origin=Origin(kind=OriginKind.PREMISE),
                    known_by=[PLAYER_ID] if knows in ("met", "heard_of") else [],
                    met_by=[PLAYER_ID] if knows == "met" else [],
                )
            )
        return npcs

    def _player(self) -> Character:
        c = self.character
        sheet = self._sheet(c, player=True)
        item_ids = _Ids("item")
        sheet.resources = Resources(
            items=[
                Item(
                    id=item_ids.add("", item.name),
                    name=_name(item.name),
                    kind=item.kind,
                    description=_text(item.description, 300),
                    quantity=_clamp(item.quantity, 0, 1_000_000, 1),
                    carried=item.carried,
                )
                for item in c.items[: MAX["items"]]
                if _name(item.name)
            ],
            money=_clamp(c.money, 0, 10**15, 0),
            currency=_text(c.currency, 40),
            title=_text(c.title, 120),
            rank=_text(c.rank, 120),
            family_name=_text(c.family_name, 120),
            connections=[
                Connection(
                    name=_name(link.name),
                    kind=link.kind,
                    character_id=_not_player(self.chars.get(link.character_id)),
                    note=_text(link.note, 300),
                )
                for link in c.connections[: MAX["sheet"]]
                if _name(link.name)
            ],
        )
        if not self.grounded:
            sheet.condition = Condition(
                reserves=[
                    Reserve(name=_name(r.name), level=_clamp(r.level, 0, 100, 100))
                    for r in c.reserves[:4]
                    if _name(r.name)
                ]
            )
        sheet.backstory = [BackstoryClaim(text=t) for t in _texts(c.backstory, 8)]
        return Character(
            id=PLAYER_ID,
            # C1: no nameless characters, the player's included.
            name=_name(c.name) if is_real_name(_name(c.name)) else PLAYER_FALLBACK_NAME,
            aliases=_texts(c.aliases, 4, NAME_LIMIT),
            prominence=Prominence.KEY,
            description=_text(c.description),
            appearance=_text(c.appearance),
            age=_age(c.age),
            people_id=self.peoples.get(c.people_id),
            location_id=self.places.get(c.location_id),
            memberships=self._memberships(c.memberships),
            sheet=sheet,
            origin=Origin(kind=OriginKind.PREMISE),
            known_by=[PLAYER_ID],
            met_by=[PLAYER_ID],
        )

    def _sheet(self, proposed: NpcP | CharacterProposal, *, player: bool) -> CharacterSheet:
        ladders = self._positions(proposed.ladders)
        return CharacterSheet(
            attributes=self._attributes(proposed.attributes),
            skills=_skills(proposed.skills),
            traits=[
                Trait(name=_name(t.name), kind=t.kind, description=_text(t.description, 300))
                for t in proposed.traits[: MAX["sheet"]]
                if _name(t.name)
            ],
            powers=self._powers(proposed.powers, player=player),
            techniques=_techniques(proposed.techniques),
            disposition=Disposition(temperament=_temperament(proposed.temperament)),
            axes=self._axes(proposed.axes, ladders),
            ladders=ladders,
        )

    def _attributes(self, proposed: AttributesP) -> Attributes:
        # G6, A4: past human limits only where the world has something extraordinary.
        peak = HUMAN_PEAK if self.grounded else 10
        return Attributes(
            **{name: _clamp(value, 0, peak, 3) for name, value in proposed.model_dump().items()}
        )

    def _powers(self, proposals: list[PowerP], *, player: bool) -> list[Power]:
        powers = []
        ids = _Ids("power")
        for proposed in proposals[: MAX["sheet"]]:
            name = _name(proposed.name)
            if not name:
                continue
            # G8: nobody has a power the world doesn't have, or from a kind it doesn't list.
            kind_id = self.kinds.get(proposed.kind_id)
            if self.grounded or kind_id not in self.possible_kinds:
                continue
            strength = None
            if proposed.gift:
                strength = self._gift_strength(proposed) if player else proposed.strength
                strength = strength or DEFAULT_GIFT
                if strength is GiftStrength.NONE:
                    continue  # G22: the player chose no gift
            powers.append(
                Power(
                    id=ids.add(proposed.id, name),
                    name=name,
                    description=_text(proposed.description),
                    strength=strength,
                    limits=_texts(proposed.limits, 6, 200),
                    costs=[
                        PowerCost(kind=cost.kind, text=_text(cost.text, 200))
                        for cost in proposed.costs[:4]
                        if _text(cost.text)
                    ],
                    secret=proposed.secret,
                    time=_time_power(proposed.time, strength),
                )
            )
        return powers

    def _gift_strength(self, proposed: PowerP) -> GiftStrength | None:
        """G22: the player's pick, then the premise's, then what the model judged."""
        template = self.options.template
        return (
            self.options.gift
            or (template.gift if template is not None else None)
            or proposed.strength
        )

    def _positions(self, proposals: list[LadderPositionP]) -> list[LadderPosition]:
        positions: dict[str, LadderPosition] = {}
        for proposed in proposals:
            ladder = self.ladders.find(proposed.ladder_id)
            if ladder is None or ladder.id in positions:
                continue
            index = _rung_index(ladder, proposed.rung)
            if index is None:
                continue
            positions[ladder.id] = LadderPosition(
                ladder_id=ladder.id, rung=index, stage=_text(proposed.stage, 80)
            )
        return list(positions.values())

    def _axes(self, proposed: AxesP, ladders: list[LadderPosition]) -> PowerAxes:
        axes = PowerAxes(
            **{name: _clamp(value, 0, TIER_MAX, 1) for name, value in proposed.model_dump().items()}
        )
        # G18: a rung is the world's name for a tier on its axis.
        by_axis: dict[str, int] = {}
        for position in ladders:
            ladder = self.ladders.by_id[position.ladder_id]
            tier = ladder.rungs[position.rung].tier
            by_axis[ladder.axis.value] = max(by_axis.get(ladder.axis.value, 0), tier)
        for axis, tier in by_axis.items():
            setattr(axes, axis, tier)
        return axes

    def _memberships(self, proposals: list[MembershipP]) -> list[Membership]:
        memberships: dict[str, Membership] = {}
        for proposed in proposals:
            faction_id = self.factions.get(proposed.faction_id)
            if faction_id and faction_id not in memberships:
                memberships[faction_id] = Membership(
                    faction_id=faction_id,
                    rank=_text(proposed.rank, 120),
                    loyalty=_clamp(proposed.loyalty, 0, 100, 50),
                )
        return list(memberships.values())

    # The plot (E2, N1, N7).

    def _clocks(self) -> list[Clock]:
        clocks: dict[str, Clock] = {}
        for clock_id, proposed in self.clock_list:
            steps = _texts(proposed.steps, 8, 300)
            # E2, W10: a clock runs on in-world time, never on turns.
            interval_s = _seconds(proposed.step_every_hours)
            clocks[clock_id] = Clock(
                id=clock_id,
                name=_text(proposed.name, 200) or steps[-1],
                steps=steps,
                interval_s=interval_s,
                next_step_s=interval_s,
                owner_id=self.factions.get(proposed.owner_id) or self.chars.get(proposed.owner_id),
                thread_id=self.threads.get(proposed.thread_id),
                known_by=[PLAYER_ID] if proposed.known_to_player else [],
            )
        return list(clocks.values())

    def _threads(self) -> list[Thread]:
        threads: dict[str, Thread] = {}
        for thread_id, proposed in self.thread_list:
            involved = [
                self.chars.get(i) or self.factions.get(i) or self.places.get(i)
                for i in proposed.involved_ids
            ]
            threads[thread_id] = Thread(
                id=thread_id,
                title=_text(proposed.title, 200),
                kind=proposed.kind,
                stakes=_text(proposed.stakes),
                involved_ids=_unique(i for i in involved if i),
                clock_id=self.clocks.get(proposed.clock_id),
                origin=Origin(kind=OriginKind.PREMISE),
                known_by=[PLAYER_ID] if proposed.known_to_player else [],
            )
        for mystery in self.bible.mysteries:
            if mystery.thread_id and mystery.thread_id not in threads:
                known = self.mystery_threads.get(mystery.thread_id, True)
                threads[mystery.thread_id] = Thread(
                    id=mystery.thread_id,
                    title=mystery.question,
                    kind=ThreadKind.MYSTERY,
                    involved_ids=[PLAYER_ID],
                    origin=Origin(kind=OriginKind.PREMISE),
                    known_by=[PLAYER_ID] if known else [],
                )
        return list(threads.values())

    def _link_threads(
        self, clocks: list[Clock], threads: list[Thread], mysteries: list[Mystery]
    ) -> None:
        by_clock = {c.id: c for c in clocks}
        by_thread = {t.id: t for t in threads}
        for clock in clocks:
            if clock.thread_id not in by_thread:
                clock.thread_id = None
            elif by_thread[clock.thread_id].clock_id is None:
                by_thread[clock.thread_id].clock_id = clock.id
        for thread in threads:
            if thread.clock_id not in by_clock:
                thread.clock_id = None
            elif by_clock[thread.clock_id].thread_id is None:
                by_clock[thread.clock_id].thread_id = thread.id
        for mystery in mysteries:
            if mystery.thread_id not in by_thread:
                mystery.thread_id = None

    # Where the story opens (R3, N5) and who knows what (C6).

    def _scene(self, places: list[Place], characters: dict[str, Character]) -> SceneFrame:
        opening = self.world.opening
        player = characters[PLAYER_ID]
        place_ids = {p.id for p in places}
        place_id = self.places.get(opening.place_id)
        if place_id not in place_ids:
            place_id = player.location_id if player.location_id in place_ids else None
        if place_id is None and places:
            place_id = places[0].id
        present = _unique([PLAYER_ID, *self.chars.all(opening.present_ids)])
        present = [c for c in present if c in characters]
        for character_id in present:
            # Everyone in the opening scene is where the scene is.
            characters[character_id].location_id = place_id
            if character_id != PLAYER_ID and PLAYER_ID not in characters[character_id].met_by:
                characters[character_id].met_by.append(PLAYER_ID)
                characters[character_id].known_by = _unique(
                    [*characters[character_id].known_by, PLAYER_ID]
                )
        for character in characters.values():
            if character.location_id not in place_ids:
                character.location_id = None
        self.scene_place_id = place_id
        return SceneFrame(
            place_id=place_id,
            present_ids=present,
            positions=_texts(opening.positions, 8, 200),
            props=_texts(opening.props, 8, 200),
            ended_on=_text(opening.situation)
            or _text(self.world.summary)
            or _text(self.options.premise),
        )

    def _spread_knowledge(
        self, places: list[Place], factions: list[Faction], player: Character
    ) -> None:
        """C6: the player character knows the factions they belong to and the place they stand
        in, and knowing a part means knowing the whole it sits in."""
        by_place = {p.id: p for p in places}
        by_faction = {f.id: f for f in factions}
        for membership in player.memberships:
            by_faction[membership.faction_id].known_by = [PLAYER_ID]
        if self.scene_place_id in by_place:
            here = by_place[self.scene_place_id]
            here.known_by = [PLAYER_ID]
            here.visited_by = [PLAYER_ID]
        for records in (by_place, by_faction):
            for record in list(records.values()):
                parent = records.get(record.parent_id) if record.known_by else None
                while parent is not None and not parent.known_by:
                    parent.known_by = [PLAYER_ID]
                    parent = records.get(parent.parent_id)

    def _facts(self) -> dict[str, Fact]:
        facts: dict[str, Fact] = {}
        origin = Origin(kind=OriginKind.PREMISE)
        for text in _texts(self.world.known_facts, MAX["facts"]):
            fact_id = f"fact-{len(facts) + 1}"
            facts[fact_id] = Fact(
                id=fact_id, text=text, importance=4, known_by=[PLAYER_ID], origin=origin
            )
        for text in _texts(self.character.hidden_past, MAX["facts"]):
            # G21: others remember this body's past; the character doesn't (C6).
            fact_id = f"fact-{len(facts) + 1}"
            facts[fact_id] = Fact(
                id=fact_id,
                text=text,
                kind=FactKind.SECRET,
                importance=4,
                subject_ids=[PLAYER_ID],
                origin=origin,
            )
        return facts


# Pieces with no state of their own.


def _with_ids(ids: _Ids, records: list, name_field: str) -> list:
    return [(ids.add(r.id, getattr(r, name_field)), r) for r in records]


def _not_player(character_id: str | None) -> str | None:
    return None if character_id == PLAYER_ID else character_id


def _break_cycles(records: dict[str, Place] | dict[str, Faction]) -> None:
    """A place or faction can't sit inside itself, however far up (G10)."""
    for record in records.values():
        seen = {record.id}
        parent_id = record.parent_id
        while parent_id is not None:
            if parent_id in seen:
                record.parent_id = None
                break
            seen.add(parent_id)
            parent_id = records[parent_id].parent_id


def _mentions(text: str, kind: str) -> bool:
    words = {w for w in re.findall(r"[a-z]+", kind.casefold()) if len(w) >= 4}
    words -= {"anything", "things", "powers", "over", "with", "from", "that", "this"}
    found = set(re.findall(r"[a-z]+", text.casefold()))
    return bool(words & found)


_PREVALENCE_WORDS = {
    Prevalence.NONE: "none, and that won't change",
    Prevalence.HIDDEN: "real, and hidden from most people",
    Prevalence.RARE: "real, and rare",
    Prevalence.COMMON: "real, and everywhere",
}


def _is_grounded_kind(kind: Extraordinary) -> bool:
    """The kind a grounded world lists to say nothing extraordinary exists (the prompt's
    "magic or anything supernatural")."""
    return " ".join(kind.kind.casefold().split()) == GROUNDED_KIND.kind


def _existence_text(kind: Extraordinary) -> str:
    return f"{_capital(kind.kind)}: {_PREVALENCE_WORDS[kind.prevalence]}."


def _age(age: int | None) -> int | None:
    return None if age is None else _clamp(age, 0, 1_000_000, 0)


def _skills(proposals) -> list[Skill]:
    skills: dict[str, Skill] = {}
    for proposed in proposals[: MAX["sheet"]]:
        name = _name(proposed.name)
        if name and name.casefold() not in skills:
            skills[name.casefold()] = Skill(
                name=name, level=proposed.level, notes=_text(proposed.notes, 200)
            )
    return list(skills.values())


def _techniques(proposals) -> list[Technique]:
    ids = _Ids("technique")
    return [
        Technique(
            id=ids.add("", t.name),
            name=_name(t.name),
            style=_text(t.style, 120),
            effect=_text(t.effect, 300),
            cost=_text(t.cost, 200),
            requirements=_text(t.requirements, 200),
        )
        for t in proposals[: MAX["sheet"]]
        if _name(t.name)
    ]


def _temperament(proposed: TemperamentP) -> Temperament:
    return Temperament(
        traits=_texts(proposed.traits, 6, 80),
        values=_texts(proposed.values, 6, 120),
        loves=_texts(proposed.loves, 6, 120),
        fears=_texts(proposed.fears, 6, 120),
        wants=_texts(proposed.wants, 6, 200),
        voice=_text(proposed.voice, 300),
    )


def _time_power(proposed: TimeP | None, strength: GiftStrength | None) -> TimePower | None:
    if proposed is None:
        return None
    lasts = proposed.lasts_seconds
    recharge = proposed.recharge_seconds
    hit_mode = None
    if proposed.effect is TimeEffect.STOP:
        # G22: three heartbeats and a breath to recharge, unless the draft says otherwise.
        lasts = STOP_LASTS_S if lasts is None or lasts <= 0 else lasts
        recharge = STOP_RECHARGE_S if recharge is None or recharge < 0 else recharge
        # G22, W10a: an overpowered stop hits at relative speed with no cap, a modest one with
        # normal force. The engine never asks the player how it works (A9).
        overpowered = strength is GiftStrength.OVERPOWERED
        hit_mode = HitMode.RELATIVE_SPEED if overpowered else HitMode.NORMAL_FORCE
    rate = proposed.rate
    if proposed.effect not in (TimeEffect.HASTE, TimeEffect.SLOW) or not rate or rate <= 0:
        rate = None
    return TimePower(
        effect=proposed.effect,
        hit_mode=hit_mode,
        lasts_s=None if lasts is None else _clamp(lasts, 0, 10 * YEAR, 0),
        recharge_s=None if recharge is None else _clamp(recharge, 0, 10 * YEAR, 0),
        rate=rate,
    )


def _calendar(proposed: CalendarP) -> Calendar:
    time_of_day = TimeOfDayStyle.CLOCK if proposed.clock_time else TimeOfDayStyle.PARTS
    start_s = _clamp(proposed.start_hour, 0, 23, 8) * HOUR
    if proposed.style is CalendarStyle.GREGORIAN:
        try:
            when = datetime.fromisoformat(proposed.epoch.strip())
        except ValueError:
            when = None
        if when is not None:
            return Calendar(
                style=CalendarStyle.GREGORIAN,
                time_of_day=time_of_day,
                epoch=when.strftime("%Y-%m-%dT%H:%M"),
                start_second_of_day=when.hour * HOUR + when.minute * MINUTE,
            )
    months = [
        Month(name=_name(m.name), days=_clamp(m.days, 1, 400, 30))
        for m in proposed.months[:24]
        if _name(m.name)
    ]
    if proposed.style is CalendarStyle.CUSTOM and months:
        month = _clamp(proposed.start_month, 1, len(months), 1)
        return Calendar(
            style=CalendarStyle.CUSTOM,
            time_of_day=time_of_day,
            start_second_of_day=start_s,
            months=months,
            start_year=_clamp(proposed.start_year, -1_000_000, 1_000_000, 1),
            start_month=month,
            start_day=_clamp(proposed.start_day, 1, months[month - 1].days, 1),
            era=_text(proposed.era, 40),
        )
    return Calendar(
        style=CalendarStyle.DAY_COUNT, time_of_day=time_of_day, start_second_of_day=start_s
    )
