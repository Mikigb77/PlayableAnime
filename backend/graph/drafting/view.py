"""What the player sees of a draft (G1, G2, G16, C6): a one-screen world summary in plain words,
the character in the world's words, and the advanced fields.

The lines are written by code from the state's public parts only, never by the model, so they
always match the structured draft and can't carry hidden truth: mystery answers, secrets, agendas,
faction plans, a body's forgotten past and anyone the character doesn't know stay out (C6, N7).
As a last guard, a line that quotes hidden text, or names someone the character doesn't know, is
dropped.

The few words code adds ("Peoples:", "Wants", "Goal:") come in the draft's language (S10); the
rest is the world's own text, which the drafter wrote in it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import Language
from engine.labels import amount, number_label, of_name
from engine.state import (
    Character,
    GiftStrength,
    GoalStatus,
    RuleTopic,
    SkillLevel,
    TraitKind,
    WorldRule,
    WorldState,
)

WORLD_LINES = 10  # one screen (G1)
CHARACTER_LINES = 10
HIDDEN_MIN_WORDS = 5  # shorter hidden strings, such as a name, are too common to match on

EN = Language.EN
ES = Language.ES
CA = Language.CA

# S10: the words code adds to the lines, by language.
_WORDS = {
    EN: {
        "beyond": " and beyond",
        "peoples": "Peoples: ",
        "stage": "{stage} of {rung}",
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
        "stage": "{stage} de {rung}",
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
        # "{of_rung}" is "de Recluta" or "d'Aprenent", as Catalan joins them.
        "stage": "{stage} {of_rung}",
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
# Nouns, as "Pericia: espada", so they fit a character of any gender.
_SKILL_LEVELS = {
    ES: {
        SkillLevel.UNTRAINED: "Sin formación",
        SkillLevel.NOVICE: "Nociones",
        SkillLevel.FAIR: "Soltura",
        SkillLevel.SKILLED: "Destreza",
        SkillLevel.EXPERT: "Pericia",
        SkillLevel.MASTER: "Maestría",
    },
    CA: {
        SkillLevel.UNTRAINED: "Sense formació",
        SkillLevel.NOVICE: "Nocions",
        SkillLevel.FAIR: "Soltesa",
        SkillLevel.SKILLED: "Destresa",
        SkillLevel.EXPERT: "Perícia",
        SkillLevel.MASTER: "Mestratge",
    },
}


def world_lines(state: WorldState, language: Language = EN) -> list[str]:
    """G1: genre and what never changes, then where and when, the ladder and peoples, then the
    factions, deadlines and questions the character knows, then the key people they know."""
    words = _WORDS[language]
    bible = state.bible
    lines: list[str] = []
    existence = [r for r in bible.rules if r.topic is RuleTopic.EXISTENCE]
    lines += [r.text for r in sorted(existence, key=lambda r: not r.fixed)[:3]]
    if bible.era:
        lines.append(_sentence(bible.era))
    for ladder in bible.ladders[:1]:
        names = [r.name for r in ladder.rungs]
        rungs = ", ".join(names[:5]) + (words["beyond"] if len(names) > 5 else "")
        lines.append(_sentence(f"{_capital(ladder.name)}: {rungs}"))
    if bible.peoples:
        peoples = _join([p.name for p in bible.peoples[:6]], language)
        lines.append(_sentence(words["peoples"] + peoples))
    factions = sorted(
        (f for f in state.factions.values() if _known(state, f.known_by)),
        key=lambda f: (f.parent_id is not None, f.id),
    )
    for faction in factions[:3]:
        lines.append(_entry(faction.name, faction.description))
    for clock in sorted(state.clocks.values(), key=lambda c: c.id):
        if _known(state, clock.known_by) and len(lines) < WORLD_LINES:
            lines.append(_clock_line(clock.name, clock.interval_s, clock.remaining, language))
    threads = state.threads
    for mystery in bible.mysteries:
        thread = threads.get(mystery.thread_id or "")
        if thread is not None and _known(state, thread.known_by):
            lines.append(mystery.question)
    people = [
        c
        for c in state.npcs()
        if _known(state, c.known_by) and c.prominence.value == "key" and c.description
    ]
    for npc in people[:2]:
        lines.append(_entry(npc.name, npc.description))
    return _guard(state, lines)[:WORLD_LINES]


def character_lines(state: WorldState, language: Language = EN) -> list[str]:
    """G2, G16: who the character is, in the world's own words rather than numbers."""
    words = _WORDS[language]
    pc = state.player
    sheet = pc.sheet
    lines = [_who(state, pc)]
    if pc.description:
        lines.append(_sentence(pc.description))
    standing = [
        _join_words(m.rank, state.factions[m.faction_id].name)
        for m in pc.memberships
        if m.faction_id in state.factions
    ]
    if sheet.resources.rank and not standing:
        standing.append(sheet.resources.rank)
    if standing:
        lines.append(_sentence(_capital("; ".join(standing))))
    for position in sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is not None and position.rung < len(ladder.rungs):
            rung = ladder.rungs[position.rung].name
            stage = words["stage"].format(
                stage=_capital(position.stage), rung=rung, of_rung=of_name(rung, language)
            )
            lines.append(_sentence(stage if position.stage else rung))
    if sheet.skills:
        by_level = sorted(sheet.skills, key=lambda s: -s.level.rank)
        groups: dict[SkillLevel, list[str]] = {}
        for skill in by_level:
            groups.setdefault(skill.level, []).append(skill.name)
        lines.append(
            " ".join(
                _sentence(f"{_skill_level(level, language)}: {_join(names, language)}")
                for level, names in groups.items()
            )
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
        lines.append(" ".join(traits))
    temperament = sheet.disposition.temperament
    mood = _capital(_join(temperament.traits, language)) if temperament.traits else ""
    wants = words["wants"] + _join(temperament.wants, language) if temperament.wants else ""
    if mood or wants:
        lines.append(" ".join(_sentence(part) for part in (mood, wants) if part))
    if sheet.powers:
        for power in sheet.powers[:3]:
            detail = power.description or power.name
            limits = f" ({'; '.join(power.limits)})" if power.limits else ""
            # G2, G13: what it costs is shown, so the player can change a cost they don't want.
            costs = "; ".join(c.text.strip().rstrip(".") for c in power.costs if c.text.strip())
            cost = f" {_sentence(words['costs'] + _capital(costs))}" if costs else ""
            secret = words["secret"] if power.secret else ""
            lines.append(
                _sentence(f"{_capital(power.name)}: {detail.rstrip('.')}{limits}") + cost + secret
            )
    elif state.bible.grounded:
        lines.append(words["no_powers"])
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
        lines.append(" ".join(held))
    if resources.connections:
        connections = _join([c.name for c in resources.connections], language)
        lines.append(_sentence(_capital(connections)))
    active = [g for g in state.goals.values() if g.status is GoalStatus.ACTIVE]
    for goal in sorted(active, key=lambda g: g.id)[:2]:
        lines.append(_sentence(words["goal"] + goal.text.rstrip(".")))
    return _guard(state, lines)[:CHARACTER_LINES]


def public_text(state: WorldState, text: str) -> str:
    """A short public field, such as the title or the tone, or "" if it quotes hidden text."""
    return text if _guard(state, [text]) else ""


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


def _skill_level(level: SkillLevel, language: Language) -> str:
    if language in _SKILL_LEVELS:
        return _SKILL_LEVELS[language].get(level, level.value.capitalize())
    return level.value.capitalize()


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
