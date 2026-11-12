"""The checks a step passes before anyone pushes back: the world's rules (G8), what the character
draws on from their sheet (G14), and every beat's means (R2).

Each check either lets the step go on or settles it on the spot with no roll: the world rules it
out, the character has no such power, or the thing they reach for isn't there. An uncertain find
is the one roll here (R2, A3).

Nothing natural fails for no reason (decided 2026-11-10, Miki). What a place of that kind would
hold is there with no roll: a thing the engine has no record of exists unless the interpret step
says it is uncertain, which is kept for what is hidden, rare, valuable or decisive, or absent.
What the scene's own record holds is there whatever source the interpret step gave it.

A power is found by its id or its name, and a technique by its id or its name, said in fewer
words or in more (`same_way`). A move the character makes with a power of theirs, such as an
aura blade from their aura, is that power at work, not a technique they never learned (`Move`):
the power must be ready, and the contest decides, never the sheet check. Pulled off cleanly, the
move becomes a technique of their own (A4, `engine.resolve.core`).

"You have no power like that" is said only of something no record of theirs holds (`on_record`).
A move made of the world's energy they hold, in a power, a technique, a reserve or a ladder they
stand on, is theirs to try (`energy_move`), and so is one that names a technique they know or are
still learning, whole or in part. It is tried on their own attributes and skills, and the contest
decides. One shared word is never enough, so a power they lack is still one they lack.
Such a move is a `Move` too, so the first time it comes off it is a technique of theirs: the
technique they were learning, under its own name, or the move made of the energy, in the
interpret step's words. The energy alone is no move, and a new way to use a power is earned by
its own ruling (A9), never by doing it.
The interpret step files the same move under different sources from turn to turn, so each source
is checked against every record: a technique named as a power is that technique, and an aura
blade filed as something carried is a move, not an object they lack.
"""

import re
from dataclasses import dataclass, field

from engine.context import TurnContext
from engine.contracts.intent import (
    BeatUse,
    IntentStep,
    OutcomeClass,
    Plausibility,
    SheetPart,
    UseSource,
)
from engine.contracts.resolution import BeatResolution, BeatVerdict
from engine.possessions import gone_to, is_money
from engine.resolve import throw as dice
from engine.resolve.words import any_mentions, cap, is_are, mentions, name, possessive, stems
from engine.rng import SeededRng
from engine.state.bible import Prevalence
from engine.state.cast import Character
from engine.state.records import RollRecord, StepResult
from engine.state.sheet import CharacterSheet, Item, Power, Practice, Technique
from engine.state.world import WorldState
from engine.timekeeping import effect_over


def find_roll(label: str, ctx: TurnContext, rng: SeededRng) -> RollRecord:
    """R2, A3. Whether a place holds something it only might is nobody's doing, so the world's
    die decides it in the open: one grey die, 11 or more. The story's difficulty never moves
    it."""
    return dice.world_die(rng, label=label, difficulty=ctx.settings.difficulty)


@dataclass(frozen=True)
class Settled:
    """A check that settled the step: its class, result and reason, with the roll that decided it
    if one did. `not_own` marks the one refusal T5 counts: a power or technique the step named
    is on no record of the actor's (G14)."""

    outcome_class: OutcomeClass
    result: StepResult
    reason: str
    roll: RollRecord | None = None
    not_own: bool = False


@dataclass(frozen=True)
class Move:
    """A4, G14. A move of the character's own that isn't a technique on their sheet: one they
    make with a power of theirs, such as an aura blade made with their aura (that power at work,
    named in the interpret step's words), or one their records make theirs to try
    (`on_record`): a technique they are still learning, or a move made of the world's energy
    they hold. Pulled off cleanly, it becomes a technique of theirs (A4)."""

    name: str
    power: Power | None = None
    style: str = ""  # the power's name, or the world's energy it is made of
    practice: Practice | None = None  # the effort toward it so far, for one still being learned


@dataclass
class Drawn:
    """What the step draws on from the sheet, once checked: the powers, techniques and items it
    really has, the moves it makes with those powers, and the skills and traits it names."""

    powers: list[Power] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        """The powers, techniques and moves it draws on, by name (R1, A3)."""
        found = [p.name for p in self.powers] + [t.name for t in self.techniques]
        found += [m.name for m in self.moves]
        return list(dict.fromkeys(found))


def world_check(state: WorldState, actor: Character, step: IntentStep) -> Settled | None:
    """G8, G7. What the world rules out, nobody can do. A step against one of the world's rules
    plays as what it really is, and the reason names the rule. In a world with nothing
    extraordinary, using a power is ruled out whatever the interpret step proposed."""
    if not actor.alive:
        return Settled(
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
            f"{cap(name(state, actor.id))} {is_are(state, actor.id)} dead.",
        )
    rules = [r for r in (state.bible.rule(i) for i in step.facts.against_rule_ids) if r]
    uses_power = any(u.part is SheetPart.POWER for u in step.uses) or any(
        use.source is UseSource.POWER for beat in step.beats for use in beat.uses
    )
    if rules:
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, _rule_reason(rules[0].text))
    if uses_power and state.bible.grounded:
        grounded = [r for r in state.bible.rules if r.fixed]
        reason = _rule_reason(grounded[0].text) if grounded else "Nothing like that exists here."
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)
    if not step.facts.world_allows:
        return Settled(
            OutcomeClass.RULED_OUT, StepResult.FAILURE, "The world doesn't work that way."
        )
    return None


def _rule_reason(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def sheet_check(
    state: WorldState, actor: Character, step: IntentStep, drawn: Drawn
) -> Settled | None:
    """G14, A1. A power or technique the step names must be the actor's own, and ready; an item
    must be theirs and on them, unless it is a vehicle or a property, used where it stands, and
    money must be in their purse (C10). Skills and traits the actor lacks simply don't help."""
    sheet = actor.sheet
    who = name(state, actor.id)
    # The powers the step names outright, so a move it makes is made with one of them.
    named = [
        p
        for p in (find_power(sheet, u.ref) for u in step.uses if u.part is SheetPart.POWER)
        if p is not None
    ]
    for use in step.uses:
        if use.part is SheetPart.POWER:
            # A power named by a word of its own name, such as "aura_blade" for their Aura, is
            # that power; nothing looser, so a power they lack is still one they lack.
            power = find_power(sheet, use.ref) or named_by_word(sheet, use.ref)
            if power is None:
                # A technique of theirs named as a power is that technique, and what else their
                # sheet records makes the move theirs to try (A4).
                technique = known_technique(sheet, use.ref)
                if technique is not None:
                    not_ready = _draw_technique(state, actor, technique, drawn)
                    if not_ready:
                        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, not_ready)
                    continue
                if on_record(state, actor, use.ref):
                    _add_own_move(state, actor, drawn, use.ref)
                    continue
                return Settled(
                    OutcomeClass.RULED_OUT,
                    StepResult.FAILURE,
                    f"{cap(who)} {_have(state, actor)} no power like that.",
                    not_own=True,
                )
            if not _ready(state, actor, power):
                return Settled(
                    OutcomeClass.RULED_OUT, StepResult.FAILURE, _not_recovered(state, actor, power)
                )
            _add(drawn.powers, power)
            # A move filed as a power ("aura_blade" for their Aura) is a move all the same.
            _add_move(drawn, use.ref, power)
        elif use.part is SheetPart.TECHNIQUE:
            technique = known_technique(sheet, use.ref)
            if technique is not None:
                not_ready = _draw_technique(state, actor, technique, drawn)
                if not_ready:
                    return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, not_ready)
                continue
            # A4, G14. No technique they learned: a move made with a power of theirs is that
            # power at work.
            power = find_power(sheet, use.ref) or made_with(sheet, use.ref, named)
            if power is None:
                if on_record(state, actor, use.ref):
                    # Something they are still learning, or made with the world's energy they
                    # hold: theirs to try, with nothing of the sheet added to it.
                    _add_own_move(state, actor, drawn, use.ref)
                    continue
                return Settled(
                    OutcomeClass.RULED_OUT,
                    StepResult.FAILURE,
                    f"{cap(who)} never learned that technique.",
                    not_own=True,
                )
            if not _ready(state, actor, power):
                return Settled(
                    OutcomeClass.RULED_OUT, StepResult.FAILURE, _not_recovered(state, actor, power)
                )
            _add(drawn.powers, power)
            _add_move(drawn, use.ref, power)
        elif use.part is SheetPart.ITEM:
            item = sheet.item(use.ref) or _owned_item(actor, use.ref)
            if item is None and is_money(use.ref, sheet.resources.currency):
                # C10. Money is the purse, not an item.
                if sheet.resources.money > 0:
                    continue
                reason = _no_money(state, actor, use.ref)
                return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)
            if item is None and _at_hand(state, actor, use.ref):
                continue
            missing = _item_missing(state, actor, item, use.ref)
            if missing:
                return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, missing)
            _add(drawn.items, item)
        elif use.part is SheetPart.SKILL:
            drawn.skills.append(use.ref)
        elif use.part is SheetPart.TRAIT:
            drawn.traits.append(use.ref)
    return None


def same_way(way: str, words: str) -> bool:
    """A4, G25. Whether `words` name the way called `way`: every word of theirs is in its name
    ("the palm" for a Rising Palm), or its whole name is in them and is more than one word, so
    "the rising palm, with all my weight" is the Rising Palm, and an "aura strike" is still no
    plain Strike."""
    name, said = stems(way), stems(words)
    if not name or not said:
        return False
    return said <= name or (len(name) > 1 and name <= said)


def known_technique(sheet: CharacterSheet, ref: str) -> Technique | None:
    """G25. The technique of theirs a use names: by its id, else by its name, said in fewer
    words or in more (`same_way`). One named in full comes first."""
    if not ref.strip():
        return None
    by_id = sheet.technique(ref)
    if by_id is not None:
        return by_id
    return next((t for t in sheet.techniques if mentions(t.name, ref)), None) or next(
        (t for t in sheet.techniques if same_way(t.name, ref)), None
    )


def _draw_technique(state: WorldState, actor: Character, technique: Technique, drawn: Drawn) -> str:
    """G25. A technique the step draws on. A technique of a power is that power at work: it must
    be ready, and it counts and costs like the power. A power over time starts only where named.
    Why it can't be used right now, or an empty string."""
    _add(drawn.techniques, technique)
    power = actor.sheet.power(technique.power_id) if technique.power_id else None
    if power is not None and power.time is None:
        if not _ready(state, actor, power):
            return _not_recovered(state, actor, power)
        _add(drawn.powers, power)
    return ""


def _own_ways(actor: Character) -> list[str]:
    """What the character's sheet records of their ways besides their powers: the techniques
    they know, the techniques and new uses they have put effort into (A4), and the world's
    energy they hold (G25)."""
    sheet = actor.sheet
    texts = [t.name for t in sheet.techniques]
    texts += [p.what for p in sheet.practice if p.key.startswith(("technique:", "power:"))]
    texts += [r.name for r in sheet.condition.reserves]
    return texts


def _held_words(state: WorldState, actor: Character) -> frozenset[str]:
    """Every word that says which of the world's energies the character holds: their ways, the
    ladders they stand on with the rungs they have reached (G18), and their powers. A power over
    time is found only where named (W10a), so it lends no word."""
    sheet = actor.sheet
    texts = _own_ways(actor) + [p.name for p in sheet.powers if p.time is None]
    for position in sheet.ladders:
        ladder = state.bible.ladder(position.ladder_id)
        if ladder is not None:
            texts.append(ladder.name)
            texts += [rung.name for rung in ladder.rungs[: position.rung + 1]]
    return frozenset().union(*(stems(text) for text in texts))


def energy_move(state: WorldState, actor: Character, words: str) -> bool:
    """G6, G25. Whether the words are a move made of the world's energy that the character
    holds: they name one of the world's extraordinary kinds ("aura" in "an aura blade", where
    the world has combat aura), and the character's sheet holds that same kind, in a power, a
    technique known or practised, a reserve or a ladder they stand on. A sword stays a sword,
    since no kind of the world names it, and so does a kind they never touched."""
    return _energy_named(state, actor, words) is not None


def _energy_named(state: WorldState, actor: Character, words: str) -> str | None:
    """The world's energy the words name that the character holds, in the world's own words
    ("combat aura"), or None (`energy_move`)."""
    said, held = stems(words), _held_words(state, actor)
    for kind in state.bible.extraordinary:
        if kind.prevalence is not Prevalence.NONE and said & stems(kind.kind) & held:
            return kind.kind
    return None


def _energy_words(state: WorldState, actor: Character) -> frozenset[str]:
    """Every word that names an energy alone and no move made of it: the world's extraordinary
    kinds, and the reserves the character holds."""
    texts = [k.kind for k in state.bible.extraordinary]
    texts += [r.name for r in actor.sheet.condition.reserves]
    return frozenset().union(*(stems(text) for text in texts))


def on_record(state: WorldState, actor: Character, words: str) -> bool:
    """A4, G14 (decided 2026-11-10, Miki). Whether a power or technique that isn't on the sheet
    by name is still the character's own to try. It is when it is made of the world's energy
    they hold (`energy_move`), so "aura to my feet" is theirs once they have trained with aura.
    And it is when it names one of their ways, whole or in part: "the rising palm, with all my
    weight" for a Rising Palm they are still learning. One shared word is never enough, so
    knowing an aura slash makes no one a void slasher, and "call down lightning" stays refused.
    Nothing of the sheet is added to such a move, and the contest decides how it goes. A power
    over time is found only where named (W10a): this never starts one."""
    if energy_move(state, actor, words):
        return True
    said = stems(words)
    ways = (stems(text) for text in _own_ways(actor))
    return bool(said) and any(way and (way <= said or said <= way) for way in ways)


def find_power(sheet: CharacterSheet, ref: str) -> Power | None:
    """G14. The power a use names: by its id, else by its name ("aura" finds "Aura")."""
    if not ref.strip():
        return None
    return sheet.power(ref) or next((p for p in sheet.powers if mentions(p.name, ref)), None)


def named_by_word(sheet: CharacterSheet, words: str) -> Power | None:
    """G14. A power whose own name shares a word with `words` ("aura_blade" and their Aura), the
    one sharing most. A power over time is found only by its id or its whole name, so "travel
    back in time" never stops the world (W10a)."""
    return _sharing([p for p in sheet.powers if p.time is None], words, description=False)


def made_with(sheet: CharacterSheet, words: str, named: list[Power]) -> Power | None:
    """A4, G14. The power of the character's that a move is made with ("an aura blade" and their
    aura): the one whose name and description share the most words with the move, among those
    the step names, else among all of theirs but powers over time, which are found only where
    named (W10a); else the one power the step names, if it names just one. None when no power of
    theirs makes it."""
    return (
        _sharing(named, words, description=True)
        or _sharing([p for p in sheet.powers if p.time is None], words, description=True)
        or (named[0] if len(named) == 1 else None)
    )


def _sharing(powers: list[Power], words: str, *, description: bool) -> Power | None:
    """The power whose name, and description when asked, shares the most words with `words`,
    if any shares one."""
    wanted = stems(words)
    scored = [
        (len(wanted & stems(f"{p.name} {p.description}" if description else p.name)), p)
        for p in powers
    ]
    best = max(scored, key=lambda pair: pair[0], default=None)
    return best[1] if best is not None and best[0] > 0 else None


# A move's name is a name, not a description: longer than this, it plays as the power at work and
# is never recorded (`Technique.name` holds 200 characters).
MAX_MOVE_NAME = 80


def _add_move(drawn: Drawn, ref: str, power: Power) -> None:
    """A move made with `power` that can become a technique of the actor's own (A4): one whose
    words share something with the power, so "an aura blade" with their aura, but neither a move
    that only says what the power is or does ("teleport" for a power that teleports), which is
    the power itself, nor one that has nothing to do with it, which plays as the power but isn't
    learned from it. A power over time grows its own ways instead (A4, W10a)."""
    words = move_name(ref)
    if not words or len(words) > MAX_MOVE_NAME or power.time is not None:
        return
    if power.id == ref or stems(ref) == stems(power.id):
        return  # the power by its id, however the id's words are joined
    what = f"{power.name} {power.description}"
    if mentions(what, words) or not stems(words) & stems(what):
        return
    if all(m.name.casefold() != words.casefold() for m in drawn.moves):
        drawn.moves.append(Move(name=words, power=power, style=power.name))


def _add_own_move(state: WorldState, actor: Character, drawn: Drawn, ref: str) -> None:
    """A4. A move the character's records make theirs to try (`on_record`), which can become a
    technique of theirs once it comes off: a technique they are still learning, under its own
    name, or a move made of the world's energy they hold, in the interpret step's words. The
    energy alone is no move ("aura to my feet" is one, "aura" is not), and a new way to use a
    power is earned by its own ruling (A9), never by doing it."""
    words = move_name(ref)
    if not stems(words) - _energy_words(state, actor):
        return
    learning = next(
        (
            p
            for p in actor.sheet.practice
            if p.key.startswith("technique:") and same_way(p.what, words)
        ),
        None,
    )
    if learning is not None:
        move = Move(name=cap(learning.what.strip()), practice=learning)
    else:
        kind = _energy_named(state, actor, words)
        if kind is None or len(words) > MAX_MOVE_NAME:
            return
        move = Move(name=words, style=kind)
    if all(m.name.casefold() != move.name.casefold() for m in drawn.moves):
        drawn.moves.append(move)


# What a move's name starts with that isn't its name: an article or a possessive, in English,
# Spanish or Catalan (S10), or the word technique.
_LEADING = re.compile(
    r"^(?:(?:a|an|the|my|your|his|her|their|el|la|los|las|un|una|mi|tu|su|els|les|"
    r"technique|t[eé]cnica|t[eè]cnica)\s+|l')+",
    re.IGNORECASE,
)


def move_name(ref: str) -> str:
    """A move's name from the interpret step's words: "the aura_blade" is "Aura blade", and "la
    cuchilla de aura" is "Cuchilla de aura"."""
    words = re.sub(r"[\s_\-]+", " ", ref).strip()
    return cap(_LEADING.sub("", words).strip())


def _have(state: WorldState, actor: Character) -> str:
    return "have" if actor.id == state.player_id else "has"


def _ready(state: WorldState, actor: Character, power: Power) -> bool:
    """A1. A power on cooldown can't be used until the character's own clock reaches it. A power
    still in effect, such as a stop that holds the world, is in use, not recovering (W10a)."""
    ready_at = power.ready_at_personal_s
    if ready_at is None or actor.personal_s(state.world_s) >= ready_at:
        return True
    return any(
        e.character_id == actor.id and e.power_id == power.id and not effect_over(state, e)
        for e in state.time_effects
    )


def _not_recovered(state: WorldState, actor: Character, power: Power) -> str:
    return f"{cap(possessive(state, actor.id))} {power.name} hasn't recovered yet."


def _add(items: list, item) -> None:
    if all(existing is not item for existing in items):
        items.append(item)


def _owned_item(actor: Character, words: str) -> Item | None:
    carried = [i for i in actor.sheet.resources.items if i.carried and i.quantity > 0]
    others = [i for i in actor.sheet.resources.items if i not in carried]
    for pool in (carried, others):
        for item in pool:
            if mentions(item.name, words) or mentions(item.description, words):
                return item
    return None


def _at_hand(state: WorldState, actor: Character, words: str, ref: str | None = None) -> bool:
    """C10, R3. Something filed as carried that the sheet doesn't list is still at hand when it
    is no object at all but a move of their own (an aura blade), when the scene's record holds
    it, such as the branch they picked up last turn, or when they wear it, as their looks say
    (C9). Looks are written once and go stale: what the record says left them is gone, whatever
    they say."""
    if energy_move(state, actor, words) or _in_scene(state, words, ref):
        return True
    return mentions(actor.appearance, words) and not gone_to(state, actor, words, money=False)


def _item_missing(state: WorldState, actor: Character, item: Item | None, words: str) -> str:
    """Why an item can't be used here and now, or an empty string if it can."""
    who = name(state, actor.id)
    if item is None:
        return f"{cap(who)} {_have(state, actor)} no {_bare(words)} on {_them(state, actor)}."
    if item.quantity <= 0:
        return f"{cap(possessive(state, actor.id))} {item.name} is used up."
    if not item.carried and item.kind.value not in ("vehicle", "property"):
        return f"{cap(possessive(state, actor.id))} {item.name} isn't on {_them(state, actor)}."
    return ""


def _no_money(state: WorldState, actor: Character, thing: str) -> str:
    currency = actor.sheet.resources.currency or _bare(thing)
    who = f"{cap(name(state, actor.id))} {_have(state, actor)}"
    went = gone_to(state, actor, thing, money=True)
    return " ".join(filter(None, [f"{who} no {currency} left.", went]))


def _them(state: WorldState, actor: Character) -> str:
    return "you" if actor.id == state.player_id else "them"


@dataclass
class BeatOutcome:
    checks: list[BeatResolution]
    canon: list[str]
    settled: Settled | None = None


def beat_check(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    canon_so_far: list[str],
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
) -> BeatOutcome:
    """R2. Whatever a beat uses has to be the character's own body or powers, something they
    carry, something the scene holds, or something this turn made canon. Something the engine
    has no record of is there, and becomes canon, unless the interpret step says otherwise: if
    it is uncertain a roll decides, and if the place can't hold it, the beat is a search that
    comes up empty and the step goes no further. A claim that the scene or this turn holds
    something the record doesn't show is judged the same way."""
    checks: list[BeatResolution] = []
    canon: list[str] = []
    for b, beat in enumerate(step.beats):
        for u, use in enumerate(beat.uses):
            if use.source is UseSource.BODY:
                continue
            check = _check_use(
                state,
                actor,
                beat.text,
                use,
                [*canon_so_far, *canon],
                drawn,
                ctx,
                rng.child("beat", b, u),
            )
            checks.append(check)
            if check.verdict is BeatVerdict.MADE_CANON:
                canon.append(use.thing)
            if check.verdict is BeatVerdict.EMPTY:
                rolled = check.roll is not None
                settled = Settled(
                    OutcomeClass.CONTESTED if rolled else OutcomeClass.RULED_OUT,
                    StepResult.FAILURE,
                    check.reason,
                    check.roll,
                    not_own=check.not_own,
                )
                return BeatOutcome(checks, canon, settled)
    return BeatOutcome(checks, canon)


def _check_use(
    state: WorldState,
    actor: Character,
    beat: str,
    use: BeatUse,
    canon: list[str],
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
) -> BeatResolution:
    def verdict(
        v: BeatVerdict, reason: str = "", roll: RollRecord | None = None, *, not_own: bool = False
    ):
        return BeatResolution(
            text=beat,
            thing=use.thing,
            source=use.source,
            verdict=v,
            reason=reason,
            roll=roll,
            not_own=not_own,
        )

    if use.source is UseSource.POWER:
        # A move made with a power the step draws on, such as an aura blade, is that power.
        words = f"{use.ref or ''} {use.thing}"
        power = (
            find_power(actor.sheet, use.ref or "")
            or find_power(actor.sheet, use.thing)
            or _sharing(drawn.powers, words, description=True)
            or named_by_word(actor.sheet, words)
        )
        if power is None:
            # A technique of theirs named as a power is that technique, and what else their
            # sheet records makes the move theirs to try (A4).
            technique = known_technique(actor.sheet, use.ref or "") or known_technique(
                actor.sheet, use.thing
            )
            if technique is not None:
                not_ready = _draw_technique(state, actor, technique, drawn)
                return verdict(BeatVerdict.EMPTY if not_ready else BeatVerdict.HOLDS, not_ready)
            if on_record(state, actor, words):
                return verdict(BeatVerdict.HOLDS)
            return verdict(
                BeatVerdict.EMPTY,
                f"{cap(name(state, actor.id))} {_have(state, actor)} no power like that.",
                not_own=True,
            )
        if not _ready(state, actor, power):
            return verdict(BeatVerdict.EMPTY, _not_recovered(state, actor, power))
        _add(drawn.powers, power)
        return verdict(BeatVerdict.HOLDS)
    if use.source is UseSource.CARRIED:
        item = (actor.sheet.item(use.ref) if use.ref else None) or _owned_item(actor, use.thing)
        if item is None and is_money(use.thing, actor.sheet.resources.currency):
            # C10. Money is the purse, not an item: there is some, or there is none left.
            if actor.sheet.resources.money > 0:
                return verdict(BeatVerdict.HOLDS)
            return verdict(BeatVerdict.EMPTY, _no_money(state, actor, use.thing))
        if item is None and _at_hand(state, actor, use.thing, use.ref):
            return verdict(BeatVerdict.HOLDS)
        missing = _item_missing(state, actor, item, use.thing)
        if missing:
            return verdict(BeatVerdict.EMPTY, missing)
        _add(drawn.items, item)
        return verdict(BeatVerdict.HOLDS)
    # R2, R3. What the scene's record or this turn's canon holds is there, whatever source the
    # interpret step gave it, so nothing on record is ever rolled for. Only a plain "absent" for
    # something filed as new stands against it: words match loosely, and a rim of worn stone is
    # no stone to pick up.
    ruled_absent = use.source is UseSource.NEW and use.plausibility is Plausibility.ABSENT
    held = _in_scene(state, use.thing, use.ref) or any_mentions(canon, use.thing)
    if held and not ruled_absent:
        return verdict(BeatVerdict.HOLDS)

    # Something the engine has no record of (R2, N7). The record is never the whole scene: the
    # ground of a forest and the trunk the last scene told of are on no list. So it is there
    # unless the interpret step says otherwise, and a judgement left out never fails a step.
    plausibility = use.plausibility or Plausibility.PLAUSIBLE
    if plausibility is Plausibility.PLAUSIBLE:
        return verdict(BeatVerdict.MADE_CANON, _is_here(use.thing))
    if plausibility is Plausibility.ABSENT:
        return verdict(BeatVerdict.EMPTY, f"There is no {_bare(use.thing)} to be found here.")
    found = find_roll(f"find {use.thing}", ctx, rng)
    if found.result is StepResult.SUCCESS:
        return verdict(BeatVerdict.MADE_CANON, _is_here(use.thing, after_all=True), found)
    return verdict(BeatVerdict.EMPTY, f"The search turns up no {_bare(use.thing)}.", found)


def _in_scene(state: WorldState, thing: str, ref: str | None = None) -> bool:
    """R2, R3. Whether the scene's record holds it: a prop, someone present or the place."""
    scene = state.scene
    if ref and (ref in scene.present_ids or ref == scene.place_id):
        return True
    names = list(scene.props)
    names += [state.characters[i].name for i in scene.present_ids if i in state.characters]
    if scene.place_id in state.places:
        names.append(state.places[scene.place_id].name)
    return any_mentions(names, thing) is not None


# The small words a thing is named with. A Spanish or a Catalan story names its things in its
# own language (S10), so the thing brings its own: "una piedra suelta", "l'espasa".
_OWN_ARTICLES = (
    *("un ", "una ", "unos ", "unas ", "uns ", "unes ", "el ", "la ", "lo ", "los ", "las "),
    *("els ", "les ", "l'", "mi ", "mis ", "tu ", "tus ", "su ", "sus ", "algún ", "alguna "),
    *("algun ", "el meu ", "la meva ", "el teu ", "la teva ", "el seu ", "la seva "),
)
_ARTICLES = tuple(
    sorted(
        ("a ", "an ", "the ", "some ", "my ", "your ", "his ", "her ", "their ", *_OWN_ARTICLES),
        key=len,
        reverse=True,
    )
)


# A thing the story names as the one it is, and those that name several of them.
_THE_ONE = tuple(a for a in _OWN_ARTICLES if not a.startswith(("un", "algu")))
_SEVERAL = ("los ", "las ", "els ", "les ", "mis ", "tus ", "sus ")


def _opening(text: str) -> str:
    """A thing's name as its article is looked for: in lower case, with a plain apostrophe."""
    return text.casefold().replace("\u2019", "'")


def _is_here(thing: str, *, after_all: bool = False) -> str:
    """That the thing a step reaches for is there. One the story names as the one it is ("la
    pedra del pati", "el meu sarró") is here; any other is one of its kind ("There is a loose
    stone here.")."""
    text = thing.strip()
    tail = " after all" if after_all else ""
    lowered = _opening(text)
    if lowered.startswith(_THE_ONE):
        return f"{cap(text)} {'are' if lowered.startswith(_SEVERAL) else 'is'} here{tail}."
    return f"There is {_a(text)} here{tail}."


def _bare(thing: str) -> str:
    text = thing.strip()
    lowered = _opening(text)
    for article in _ARTICLES:
        if lowered.startswith(article):
            return text[len(article) :]
    return text


def _a(thing: str) -> str:
    """The thing as one of its kind: "a loose stone", "an old rope". One that is named with an
    article of its own, in any of the story's languages, keeps it ("una piedra suelta")."""
    text = thing.strip()
    if _opening(text).startswith(("a ", "an ", "some ", *_OWN_ARTICLES)):
        return text
    bare = _bare(text)
    return f"{'an' if bare[:1].casefold() in 'aeiou' else 'a'} {bare}"
