"""What the player sees of a draft (G1, G2, G16, C6): a one-screen world summary in plain words,
the character in the world's words, and the advanced fields.

The lines are written by code from the state's public parts only, never by the model, so they
always match the structured draft and can't carry hidden truth: mystery answers, secrets, agendas,
faction plans, a body's forgotten past and anyone the character doesn't know stay out (C6, N7).
As a last guard, a line that quotes hidden text, or names someone the character doesn't know, is
dropped.

The few words code adds ("Peoples:", "Wants", "Goal:") come in the draft's language (S10); the
rest is the world's own text, which the drafter wrote in it.

The summary never gives away how the story starts (G1, Miki 2026-11-10): given the player's say
(`said`: the premise, and what a change they asked for later named), a deadline, an open
question, a goal, a person and a connection are shown only when their own words name them
(`graph.drafting.openers`). The rest is the story's surprise, drafted and kept out of sight;
of it the screen gets a count and nothing more (`kept`).

Each line is a part with its kind (`world_parts`, `character_parts`), so the app can label it,
group it and point a change in plain words at it. The plain fields the player changes themselves
are given as values (`identity`, `graph.drafting.direct`), and the ladder as its rungs with the
character's place on it (`ladder_view`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from functools import partial

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import Language
from engine.labels import amount, number_label
from engine.state import (
    Character,
    GiftStrength,
    GoalStatus,
    RuleTopic,
    SkillLevel,
    Talent,
    TraitKind,
    WorldRule,
    WorldState,
    stage_named,
)
from engine.visibility import TALENT_STRENGTH_WORDS, rank_stage_label, skill_level_label
from graph.drafting.openers import (
    Opener,
    Said,
    of_clock,
    of_connection,
    of_goal,
    of_person,
    of_question,
)


class PartKind(StrEnum):
    """What a line of the summary tells of. The app labels a line by it (S10)."""

    # The world.
    RULE = "rule"  # what is real in it, first what never changes
    ERA = "era"
    LADDER = "ladder"
    PEOPLES = "peoples"
    FACTION = "faction"
    # How the story starts, shown only when the player's own words name it (G1).
    DEADLINE = "deadline"
    QUESTION = "question"
    PERSON = "person"
    CONNECTIONS = "connections"
    GOAL = "goal"
    # The character.
    WHO = "who"
    MANNER = "manner"
    STANDING = "standing"
    RANK = "rank"
    SKILLS = "skills"
    TALENTS = "talents"
    TRAITS = "traits"
    NATURE = "nature"
    POWER = "power"
    BELONGINGS = "belongings"


@dataclass(frozen=True)
class Part:
    """One line of the summary, with what it tells of."""

    kind: PartKind
    text: str


WORLD_LINES = 10  # one screen (G1)
CHARACTER_LINES = 10
# The most rungs of a ladder the world's summary names. It names the ones everyone has heard
# of (G18, C6), so this is also how many those are where the drafter doesn't say.
SUMMARY_RUNGS = 5
HIDDEN_MIN_WORDS = 5  # shorter hidden strings, such as a name, are too common to match on

EN = Language.EN
ES = Language.ES
CA = Language.CA

# S10: the words code adds to the lines, by language.
_WORDS = {
    EN: {
        "beyond": " and beyond",
        "peoples": "Peoples: ",
        "gifts": "Gifts",
        "flaws": "Flaws",
        "quirks": "Quirks",
        "wants": "Wants ",
        "secret": " Nobody knows.",
        "costs": "Cost: ",
        "no_powers": "No powers, since this world has none.",
        "carries": "Carries ",
        "owns": "Owns ",
        "goal": "Goal: ",
        "in": "in",
        "and": " and ",
        "moments": "moments",
    },
    ES: {
        "beyond": " y más allá",
        "peoples": "Pueblos: ",
        "gifts": "Dones",
        "flaws": "Defectos",
        "quirks": "Manías",
        "wants": "Quiere ",
        "secret": " Nadie lo sabe.",
        "costs": "Coste: ",
        "no_powers": "Sin poderes, porque en este mundo no existen.",
        "carries": "Lleva ",
        "owns": "Posee ",
        "goal": "Objetivo: ",
        "in": "en",
        "and": " y ",
        "moments": "un momento",
    },
    CA: {
        "beyond": " i més enllà",
        "peoples": "Pobles: ",
        "gifts": "Dons",
        "flaws": "Defectes",
        "quirks": "Manies",
        "wants": "Vol ",
        "secret": " Ningú no ho sap.",
        "costs": "Cost: ",
        "no_powers": "Sense poders, perquè en aquest món no n'hi ha.",
        "carries": "Porta ",
        "owns": "Té ",
        "goal": "Objectiu: ",
        "in": "d'aquí a",
        "and": " i ",
        "moments": "un moment",
    },
}


def world_lines(state: WorldState, language: Language = EN, said: Said | None = None) -> list[str]:
    """G1: the world's summary as plain lines, one screen of them (`world_parts`)."""
    return [part.text for part in world_parts(state, language, said)][:WORLD_LINES]


def world_parts(state: WorldState, language: Language = EN, said: Said | None = None) -> list[Part]:
    """G1: genre and what never changes, then where and when, the ladder and peoples, then the
    factions, deadlines and questions the character knows, then the key people they know.
    With `said`, the player's say, a deadline, a question and a person are in it only when
    their own words name them; without, everything the character knows is."""

    spoken = partial(_spoken, said, language)

    words = _WORDS[language]
    bible = state.bible
    parts: list[Part] = []

    def add(kind: PartKind, text: str) -> None:
        parts.append(Part(kind, text))

    existence = [r for r in bible.rules if r.topic is RuleTopic.EXISTENCE]
    for rule in sorted(existence, key=lambda r: not r.fixed)[:3]:
        add(PartKind.RULE, rule.text)
    if bible.era:
        add(PartKind.ERA, _sentence(bible.era))
    for ladder in bible.ladders[:1]:
        # G18, C6: only the rungs everyone has heard of, which the character's path starts
        # with (`engine.path`). A ladder drafted before the world said which those are names
        # its first ones, as it did then.
        names = [r.name for r in ladder.rungs]
        told = names[: _told_rungs(ladder.known_to_all)]
        rungs = ", ".join(told) + (words["beyond"] if len(names) > len(told) else "")
        add(PartKind.LADDER, _sentence(f"{_capital(ladder.name)}: {rungs}"))
    if bible.peoples:
        peoples = _join([p.name for p in bible.peoples[:6]], language)
        add(PartKind.PEOPLES, _sentence(words["peoples"] + peoples))
    factions = sorted(
        (f for f in state.factions.values() if _known(state, f.known_by)),
        key=lambda f: (f.parent_id is not None, f.id),
    )
    for faction in factions[:3]:
        add(PartKind.FACTION, _entry(faction.name, faction.description))
    for clock in sorted(state.clocks.values(), key=lambda c: c.id):
        if _known(state, clock.known_by) and spoken(of_clock(state, clock)):
            line = _clock_line(clock.name, clock.interval_s, clock.remaining, language)
            add(PartKind.DEADLINE, line)
    threads = state.threads
    for mystery in bible.mysteries:
        thread = threads.get(mystery.thread_id or "")
        known = thread is not None and _known(state, thread.known_by)
        if known and spoken(of_question(state, mystery)):
            add(PartKind.QUESTION, mystery.question)
    people = [
        c
        for c in state.npcs()
        if _known(state, c.known_by)
        and c.prominence.value == "key"
        and c.description
        and spoken(of_person(state, c))
    ]
    for npc in people[:2]:
        add(PartKind.PERSON, _entry(npc.name, npc.description))
    return _guarded(state, parts)


def character_lines(
    state: WorldState, language: Language = EN, said: Said | None = None
) -> list[str]:
    """G2, G16: the character's summary as plain lines, one screen of them
    (`character_parts`)."""
    return [part.text for part in character_parts(state, language, said)][:CHARACTER_LINES]


def character_parts(
    state: WorldState, language: Language = EN, said: Said | None = None
) -> list[Part]:
    """G2, G16: who the character is, in the world's own words rather than numbers. With
    `said`, the player's say, a connection and a goal are in it only when their own words name
    them."""

    spoken = partial(_spoken, said, language)

    words = _WORDS[language]
    pc = state.player
    sheet = pc.sheet
    parts = [Part(PartKind.WHO, _who(state, pc))]

    def add(kind: PartKind, text: str) -> None:
        parts.append(Part(kind, text))

    if pc.description:
        add(PartKind.MANNER, _sentence(pc.description))
    if standing := _standing(state, pc):
        add(PartKind.STANDING, _sentence(_capital(standing)))
    for position in sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is not None and position.rung < len(ladder.rungs):
            rung = ladder.rungs[position.rung].name
            # G19: the stage the story starts them at, in the words their sheet will use.
            if stage := _stage_words(position.stage, language):
                rung = f"{rung}, {stage}"
            add(PartKind.RANK, _sentence(rung))
    if sheet.skills:
        by_level = sorted(sheet.skills, key=lambda s: -s.level.rank)
        groups: dict[SkillLevel, list[str]] = {}
        for skill in by_level:
            groups.setdefault(skill.level, []).append(skill.name)
        add(
            PartKind.SKILLS,
            " ".join(
                _sentence(f"{skill_level_label(level, language)}: {_join(names, language)}")
                for level, names in groups.items()
            ),
        )
    if sheet.talents:
        # A4: how fast they learn each thing, so the player can check it and change it in
        # plain words: "One of a kind: The sword (anything fought with a blade)."
        add(
            PartKind.TALENTS,
            " ".join(
                _sentence(f"{label}: {'; '.join(named)}")
                for strength, label in TALENT_STRENGTH_WORDS[language].items()
                if (named := [_talent(t) for t in sheet.talents if t.strength is strength])
            ),
        )
    gifts = [t.name for t in sheet.traits if t.kind is TraitKind.GIFT]
    flaws = [t.name for t in sheet.traits if t.kind is TraitKind.FLAW]
    quirks = [t.name for t in sheet.traits if t.kind is TraitKind.QUIRK]
    traits = [
        _sentence(f"{words[label]}: {_join(names, language)}")
        for label, names in (("gifts", gifts), ("flaws", flaws), ("quirks", quirks))
        if names
    ]
    if traits:
        add(PartKind.TRAITS, " ".join(traits))
    temperament = sheet.disposition.temperament
    mood = _capital(_join(temperament.traits, language)) if temperament.traits else ""
    wants = words["wants"] + _join(temperament.wants, language) if temperament.wants else ""
    if mood or wants:
        add(PartKind.NATURE, " ".join(_sentence(part) for part in (mood, wants) if part))
    if sheet.powers:
        for power in sheet.powers[:3]:
            detail = power.description or power.name
            limits = f" ({'; '.join(power.limits)})" if power.limits else ""
            # G2, G13: what it costs is shown, so the player can change a cost they don't want.
            costs = power.costs_text
            cost = f" {_sentence(words['costs'] + _capital(costs))}" if costs else ""
            secret = words["secret"] if power.secret else ""
            add(
                PartKind.POWER,
                _sentence(f"{_capital(power.name)}: {detail.rstrip('.')}{limits}") + cost + secret,
            )
    elif state.bible.grounded:
        add(PartKind.POWER, words["no_powers"])
    resources = sheet.resources
    carried = [i.name for i in resources.items if i.carried]
    owned = [i.name for i in resources.items if not i.carried]
    held = []
    if carried:
        held.append(_sentence(words["carries"] + _join(carried, language)))
    if owned:
        held.append(_sentence(words["owns"] + _join(owned, language)))
    if resources.money:
        money = number_label(resources.money, language)
        held.append(_sentence(f"{money} {resources.currency}".strip()))
    if held:
        add(PartKind.BELONGINGS, " ".join(held))
    known = [c.name for c in resources.connections if spoken(of_connection(state, c))]
    if known:
        add(PartKind.CONNECTIONS, _sentence(_capital(_join(known, language))))
    active = [
        g
        for g in state.goals.values()
        if g.status is GoalStatus.ACTIVE and spoken(of_goal(state, g))
    ]
    for goal in sorted(active, key=lambda g: g.id)[:2]:
        add(PartKind.GOAL, _sentence(words["goal"] + goal.text.rstrip(".")))
    return _guarded(state, parts)


def identity(state: WorldState) -> dict[str, object]:
    """G2: the plain fields of the character, which the player changes themselves
    (`graph.drafting.direct`): their name, their age, their looks and how they come across,
    with their people and their standing to tell them by."""
    pc = state.player
    people = next((p for p in state.bible.peoples if p.id == pc.people_id), None)
    return {
        "name": pc.name,
        "age": pc.age,
        "people": people.name if people is not None else "",
        "standing": public_text(state, _capital(_standing(state, pc))),
        "looks": public_text(state, pc.appearance),
        "manner": public_text(state, pc.description),
    }


def ladder_view(state: WorldState, language: Language = EN) -> dict[str, object] | None:
    """G18, G19: the world's first ladder as the summary tells it, rung by rung: the rungs
    everyone has heard of, whether it goes on above them, and where the character stands when
    that is one of them. None in a world with no ladder."""
    for ladder in state.bible.ladders[:1]:
        names = [r.name for r in ladder.rungs]
        told = names[: _told_rungs(ladder.known_to_all)]
        if not _guard(state, [", ".join([ladder.name, *told])]):
            return None
        at = next((p for p in state.player.sheet.ladders if p.ladder_id == ladder.id), None)
        here = at is not None and at.rung < len(told)
        return {
            "name": _capital(ladder.name),
            "rungs": told,
            "more": len(names) > len(told),
            "at": at.rung if here else None,
            "stage": _stage_words(at.stage, language) if here else "",
        }
    return None


def kept(state: WorldState, language: Language = EN, said: Said | None = None) -> dict[str, int]:
    """G1: how much of the story's start the summary keeps out of sight, as counts and nothing
    more: the people, the things already in motion and the open questions the player's own
    words don't name. With no `said`, nothing is kept."""
    if said is None:
        return {"people": 0, "events": 0, "questions": 0}

    def unsaid(openers: Iterable[Opener]) -> int:
        return sum(not said.names(opener, language) for opener in openers)

    return {
        "people": unsaid(of_person(state, c) for c in state.npcs()),
        "events": unsaid(of_clock(state, c) for c in state.clocks.values()),
        "questions": unsaid(of_question(state, m) for m in state.bible.mysteries),
    }


def public_text(state: WorldState, text: str) -> str:
    """A short public field, such as the title or the tone, or "" if it quotes hidden text."""
    return text if _guard(state, [text]) else ""


def shown(state: WorldState, language: Language = EN, said: Said | None = None) -> str:
    """Everything the draft's screen says of the world and the character: the title, the genre
    and the tone, the two summaries and the rules of the advanced fields. What the player read
    there, the character knows from the story's first moment (`engine.path`). `said` is the
    player's say, as the summaries take it."""
    bible = state.bible
    lines = [public_text(state, text) for text in (bible.title, bible.genre, bible.tone)]
    lines += world_lines(state, language, said) + character_lines(state, language, said)
    lines += [rule.text for rule in public_rules(state)]
    return "\n".join(line for line in lines if line)


def public_rules(state: WorldState) -> list[WorldRule]:
    """G6, G7: the world's rules for the advanced fields, minus any that quotes hidden text."""
    kept = set(_guard(state, (r.text for r in state.bible.rules)))
    return [r for r in state.bible.rules if r.text in kept]


def gift_strength(state: WorldState) -> GiftStrength:
    """G22: the strongest gift the character holds, or `none`."""
    order = list(GiftStrength)
    gifts = [p.strength for p in state.player.sheet.powers if p.strength is not None]
    return max(gifts, key=order.index) if gifts else GiftStrength.NONE


# The guard (C6, N7).


def hidden_texts(state: WorldState) -> list[str]:
    """Everything the player must not read in a draft: mystery answers and clues, secrets,
    agendas, faction plans, and facts the character doesn't know."""
    texts: list[str] = []
    for mystery in state.bible.mysteries:
        texts += [mystery.answer, *mystery.clues]
    for character in state.characters.values():
        texts += character.secrets
        if character.agenda is not None:
            texts += [character.agenda.goal, character.agenda.method, character.agenda.secret]
    for faction in state.factions.values():
        texts += [*faction.secrets, faction.goal, faction.methods]
    texts += [f.text for f in state.facts.values() if state.player_id not in f.known_by]
    return [t for t in texts if t]


def unknown_names(state: WorldState) -> list[str]:
    """Names of people, factions and places the character doesn't know exist."""
    pc = state.player_id
    names = [c.name for c in state.npcs() if pc not in c.known_by]
    names += [f.name for f in state.factions.values() if pc not in f.known_by]
    names += [p.name for p in state.places.values() if pc not in p.known_by]
    return names


def _guarded(state: WorldState, parts: list[Part]) -> list[Part]:
    """The parts whose lines pass the guard, each line once."""
    kept_lines = set(_guard(state, (part.text for part in parts)))
    seen: set[str] = set()
    passed = []
    for part in parts:
        if part.text in kept_lines and part.text not in seen:
            seen.add(part.text)
            passed.append(part)
    return passed


def _guard(state: WorldState, lines: Iterable[str]) -> list[str]:
    hidden = [h for h in map(_words, hidden_texts(state)) if len(h.split()) >= HIDDEN_MIN_WORDS]
    names = [n for n in map(_words, unknown_names(state)) if len(n) >= 4]
    kept = []
    for line in lines:
        words = f" {_words(line)} "
        if any(f" {h} " in words for h in hidden) or any(f" {n} " in words for n in names):
            continue
        kept.append(line)
    return list(dict.fromkeys(kept))


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


# Wording.


def _known(state: WorldState, known_by: list[str]) -> bool:
    return state.player_id in known_by


def _spoken(said: Said | None, language: Language, opener: Opener) -> bool:
    """Whether the player's own words name this opener, or True when the lines aren't read
    against them (G1)."""
    return said is None or said.names(opener, language)


def _told_rungs(known_to_all: int | None) -> int:
    """How many rungs of a ladder the summary names: the ones everyone has heard of, five at
    most."""
    return min(known_to_all or SUMMARY_RUNGS, SUMMARY_RUNGS)


def _standing(state: WorldState, pc: Character) -> str:
    """Where the character stands: their rank in each faction they belong to, or failing that
    their rank in the world."""
    standing = [
        _join_words(m.rank, state.factions[m.faction_id].name)
        for m in pc.memberships
        if m.faction_id in state.factions
    ]
    if pc.sheet.resources.rank and not standing:
        standing.append(pc.sheet.resources.rank)
    return "; ".join(standing)


def _stage_words(stage: str, language: Language) -> str:
    """G19: a stage of a rung in the words the sheet uses, in lower case, or ""."""
    found = stage_named(stage)
    if found is None:
        return ""
    label = rank_stage_label(found, language)
    return f"{label[:1].lower()}{label[1:]}"


def _who(state: WorldState, pc: Character) -> str:
    parts = [pc.name]
    if pc.age is not None:
        parts.append(str(pc.age))
    people = next((p for p in state.bible.peoples if p.id == pc.people_id), None)
    if people is not None:
        parts.append(people.name)
    return _sentence(", ".join(parts))


def _clock_line(name: str, interval_s: int | None, steps: int, language: Language = EN) -> str:
    if not interval_s:
        return _sentence(name)
    when = duration(interval_s * steps, language)
    return _sentence(f"{name.rstrip('.')}: {_WORDS[language]['in']} {when}")


# S10: each unit in Spanish and Catalan, as one (with its article) and as many.
def duration(seconds: int, language: Language = EN) -> str:
    """A rough span in words: '10 days', 'an hour', 'a year' (in Spanish '10 días', 'una
    hora'; in Catalan '10 dies', 'una hora')."""
    for size, unit in ((YEAR, "year"), (DAY, "day"), (HOUR, "hour"), (MINUTE, "minute")):
        if seconds >= size:
            return amount(round(seconds / size), unit, language)
    return _WORDS[language]["moments"]


def _talent(talent: Talent) -> str:
    """A talent by its name, with what it covers: "The sword (anything fought with a blade)"."""
    covers = talent.covers.strip().rstrip(".")
    return f"{talent.name} ({covers})" if covers else talent.name


def _entry(name: str, description: str) -> str:
    if not description:
        return _sentence(_capital(name))
    return _sentence(f"{_capital(name)}: {description.rstrip('.')}")


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".!?…" else text + "."


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _join(items: list[str], language: Language = EN) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + _WORDS[language]["and"] + items[-1]


def _join_words(rank: str, faction: str) -> str:
    return f"{rank}, {faction}" if rank else faction
