"""The checks a step passes before anyone pushes back: the world's rules (G8), what the character
draws on from their sheet (G14), and every beat's means (R2).

Each check either lets the step go on or settles it on the spot with no roll: the world rules it
out, the character has no such power, or the thing they reach for isn't there. An uncertain find
is the one roll here (R2, A3).
"""

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
from engine.resolve import odds as odds_mod
from engine.resolve.words import any_mentions, cap, is_are, mentions, name, possessive
from engine.rng import SeededRng
from engine.state.cast import Character
from engine.state.records import RollRecord, StepResult
from engine.state.sheet import Item, Power, Technique
from engine.state.world import WorldState
from engine.timekeeping import effect_over

# The odds that a place holds something it plausibly might, before difficulty (R2, A5).
FIND_ODDS = 0.5


@dataclass(frozen=True)
class Settled:
    """A check that settled the step: its class, result and reason, with the roll that decided it
    if one did."""

    outcome_class: OutcomeClass
    result: StepResult
    reason: str
    roll: RollRecord | None = None


@dataclass
class Drawn:
    """What the step draws on from the sheet, once checked: the powers, techniques and items it
    really has, and the skills and traits it names."""

    powers: list[Power] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)


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
    must be theirs and on them, unless it is a vehicle or a property, used where it stands. Skills
    and traits the actor lacks simply don't help."""
    sheet = actor.sheet
    who = name(state, actor.id)
    for use in step.uses:
        if use.part is SheetPart.POWER:
            power = sheet.power(use.ref)
            if power is None:
                return Settled(
                    OutcomeClass.RULED_OUT,
                    StepResult.FAILURE,
                    f"{cap(who)} {_have(state, actor)} no power like that.",
                )
            if not _ready(state, actor, power):
                return Settled(
                    OutcomeClass.RULED_OUT, StepResult.FAILURE, _not_recovered(state, actor, power)
                )
            _add(drawn.powers, power)
        elif use.part is SheetPart.TECHNIQUE:
            technique = next(
                (t for t in sheet.techniques if t.id == use.ref or mentions(t.name, use.ref)),
                None,
            )
            if technique is None:
                return Settled(
                    OutcomeClass.RULED_OUT,
                    StepResult.FAILURE,
                    f"{cap(who)} never learned that technique.",
                )
            _add(drawn.techniques, technique)
        elif use.part is SheetPart.ITEM:
            item = sheet.item(use.ref) or _owned_item(actor, use.ref)
            missing = _item_missing(state, actor, item, use.ref)
            if missing:
                return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, missing)
            _add(drawn.items, item)
        elif use.part is SheetPart.SKILL:
            drawn.skills.append(use.ref)
        elif use.part is SheetPart.TRAIT:
            drawn.traits.append(use.ref)
    return None


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
    carry, something the scene holds, or something this turn made canon. Something new that the
    place plausibly holds becomes canon; if that's uncertain a roll decides; if the place can't
    hold it, the beat is a search that comes up empty and the step goes no further. A claim that
    the scene or this turn holds something it doesn't is judged as something new."""
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
    def verdict(v: BeatVerdict, reason: str = "", roll: RollRecord | None = None):
        return BeatResolution(
            text=beat, thing=use.thing, source=use.source, verdict=v, reason=reason, roll=roll
        )

    if use.source is UseSource.POWER:
        power = (actor.sheet.power(use.ref) if use.ref else None) or next(
            (p for p in actor.sheet.powers if mentions(p.name, use.thing)), None
        )
        if power is None:
            return verdict(
                BeatVerdict.EMPTY,
                f"{cap(name(state, actor.id))} {_have(state, actor)} no power like that.",
            )
        if not _ready(state, actor, power):
            return verdict(BeatVerdict.EMPTY, _not_recovered(state, actor, power))
        _add(drawn.powers, power)
        return verdict(BeatVerdict.HOLDS)
    if use.source is UseSource.CARRIED:
        item = (actor.sheet.item(use.ref) if use.ref else None) or _owned_item(actor, use.thing)
        missing = _item_missing(state, actor, item, use.thing)
        if missing:
            return verdict(BeatVerdict.EMPTY, missing)
        _add(drawn.items, item)
        return verdict(BeatVerdict.HOLDS)
    if use.source is UseSource.SCENE and _in_scene(state, use):
        return verdict(BeatVerdict.HOLDS)
    if use.source is UseSource.CANON and any_mentions(canon, use.thing):
        return verdict(BeatVerdict.HOLDS)

    # Something the scene hasn't established (R2, N7).
    plausibility = use.plausibility or Plausibility.UNCERTAIN
    if plausibility is Plausibility.PLAUSIBLE:
        return verdict(BeatVerdict.MADE_CANON, f"There is {_a(use.thing)} here.")
    if plausibility is Plausibility.ABSENT:
        return verdict(BeatVerdict.EMPTY, f"There is no {_bare(use.thing)} to be found here.")
    odds = odds_mod.settle(
        odds_mod.logit(FIND_ODDS), 0.0, odds_mod.FIND_BAND, ctx.settings.difficulty
    )
    found = odds_mod.roll(
        rng,
        odds,
        label=f"find {use.thing}",
        allowed=odds_mod.YES_OR_NO,
        difficulty=ctx.settings.difficulty,
    )
    if found.result is StepResult.SUCCESS:
        return verdict(BeatVerdict.MADE_CANON, f"There is {_a(use.thing)} here after all.", found)
    return verdict(BeatVerdict.EMPTY, f"The search turns up no {_bare(use.thing)}.", found)


def _in_scene(state: WorldState, use: BeatUse) -> bool:
    scene = state.scene
    if use.ref and (use.ref in scene.present_ids or use.ref == scene.place_id):
        return True
    names = list(scene.props)
    names += [state.characters[i].name for i in scene.present_ids if i in state.characters]
    if scene.place_id in state.places:
        names.append(state.places[scene.place_id].name)
    return any_mentions(names, use.thing) is not None


_ARTICLES = ("a ", "an ", "the ", "some ", "my ", "your ", "his ", "her ", "their ")


def _bare(thing: str) -> str:
    text = thing.strip()
    lowered = text.casefold()
    for article in _ARTICLES:
        if lowered.startswith(article):
            return text[len(article) :]
    return text


def _a(thing: str) -> str:
    text = thing.strip()
    if text.casefold().startswith(("a ", "an ", "some ")):
        return text
    bare = _bare(text)
    return f"{'an' if bare[:1].casefold() in 'aeiou' else 'a'} {bare}"
