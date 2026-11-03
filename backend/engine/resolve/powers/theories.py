"""The engine rules on the player's theories about their own powers, once (A9).

Nobody asks the player how a power works: it is part of the world, and the player finds out by
using it. When they reason about it ("a rock thrown in stopped time should hit at the speed of
light"), the engine decides whether that holds here, and the answer is set in stone on the sheet.
Asking again gets the same answer, shown in play with no physics debate.

- **Refuse nonsense, never power.** A theory is refused when nothing in the power or the world
  explains it, when it would add a new power, or when it breaks a rule of the world that never
  changes (G7). It is never refused for making the character too strong: a chain that holds works
  however strong it makes them, and the world answers that strength instead (G22, W5).
- **Scale.** A flick of a finger doesn't blow up the planet, because nothing in the power reaches
  that far, unless the world works at that scale (its strongest beings do). What a time stop can
  reach is worked out from the heaviest thing its user can lift, at the speed its hits land.
- **A yes can come with a cost** (G22). A modest power whose theory makes it land at relative
  speed, or reach a city, gets a heavier drain: its stop takes twice as long to recover.
- **Time stop's own details** (W10a) are ruled on by code: how hard stopped-time hits land, and
  whether frozen things can be picked up.
"""

import re
from dataclasses import dataclass, field

from engine.contracts.delta import PowerChange, PowerSetting
from engine.contracts.intent import EffectScale, PowerTheory, TheoryAbout
from engine.resolve.power import base_tier
from engine.resolve.powers import force as force_mod
from engine.resolve.powers import time_stop as stop
from engine.state.cast import Character
from engine.state.sheet import GiftStrength, HitMode, Power, PowerAxis, Ruling, RulingSource
from engine.state.world import WorldState

NO_SUCH_POWER = "There is no such power to work that way."
NEW_POWER = "That would be a new power, not a way of using this one."
NOTHING_BEHIND_IT = "No: nothing in the power makes that happen."
TOO_BIG = "No: nothing in the power reaches that far."
HOLDS = "Yes: it works that way."
# Theories whose effect reaches this scale make a modest power pay a heavier drain (G22).
COSTLY_SCALES = (EffectScale.CITY, EffectScale.REGION, EffectScale.WORLD, EffectScale.STARS)
MODEST = (GiftStrength.SMALL, GiftStrength.RARE, GiftStrength.NONE)


@dataclass
class TheoryOutcome:
    rulings: list[Ruling] = field(default_factory=list)
    powers: list[PowerChange] = field(default_factory=list)


def rule_on_theories(
    state: WorldState,
    actor: Character,
    theories: list[PowerTheory],
    settled: stop.Settlements,
    known: list[Ruling],
) -> TheoryOutcome:
    """A9. Rule on each theory, in order. `known` holds this plan's rulings so far; with the
    sheet's, a topic already ruled on is answered by that ruling, never a new one."""
    outcome = TheoryOutcome()
    for theory in theories:
        power = _power(actor, theory)
        topic = canonical_topic(theory)
        power_id = power.id if power is not None else theory.power_id
        earlier = actor.sheet.ruling(topic, power_id) or next(
            (r for r in [*known, *outcome.rulings] if (r.topic, r.power_id) == (topic, power_id)),
            None,
        )
        if earlier is not None:
            outcome.rulings.append(earlier)
            continue
        found = _rule(state, actor, theory, power, topic, settled)
        outcome.rulings.append(found.ruling)
        if found.change is not None:
            outcome.powers.append(found.change)
    return outcome


def canonical_topic(theory: PowerTheory) -> str:
    if theory.about is TheoryAbout.HIT_FORCE:
        return stop.HIT_MODE
    if theory.about is TheoryAbout.MOVE_FROZEN:
        return stop.MOVE_FROZEN
    slug = re.sub(r"[^a-z0-9]+", "_", theory.topic.casefold()).strip("_")
    return slug or "theory"


def _power(actor: Character, theory: PowerTheory) -> Power | None:
    if theory.power_id:
        return actor.sheet.power(theory.power_id)
    if theory.about in (TheoryAbout.HIT_FORCE, TheoryAbout.MOVE_FROZEN):
        stoppers = [p for p in actor.sheet.powers if stop.stops_time(p)]
        return stoppers[0] if len(stoppers) == 1 else None
    return actor.sheet.powers[0] if len(actor.sheet.powers) == 1 else None


@dataclass(frozen=True)
class _Found:
    ruling: Ruling
    change: PowerChange | None = None


def _refused(theory: PowerTheory, topic: str, power_id: str | None, answer: str) -> _Found:
    return _Found(
        Ruling(
            id=f"ruling-{power_id or 'none'}-{topic}",
            topic=topic,
            power_id=power_id,
            question=theory.claim,
            answer=answer,
            holds=False,
            source=RulingSource.THEORY,
        )
    )


def _rule(
    state: WorldState,
    actor: Character,
    theory: PowerTheory,
    power: Power | None,
    topic: str,
    settled: stop.Settlements,
) -> _Found:
    if power is None:
        return _refused(theory, topic, theory.power_id, NO_SUCH_POWER)
    fixed = [r for r in (state.bible.rule(i) for i in theory.against_rule_ids) if r and r.fixed]
    if fixed:
        return _refused(theory, topic, power.id, _rule_text(fixed[0].text))
    if theory.adds_power:
        return _refused(theory, topic, power.id, NEW_POWER)
    if theory.about is TheoryAbout.HIT_FORCE and stop.stops_time(power):
        return _hit_force(theory, power, settled)
    if theory.about is TheoryAbout.MOVE_FROZEN and stop.stops_time(power):
        return _move_frozen(theory, power, settled)
    return _other(state, actor, theory, power, topic, settled)


def _rule_text(text: str) -> str:
    text = text.strip()
    return f"No: {text if text.endswith(('.', '!', '?')) else text + '.'}"


def _hit_force(theory: PowerTheory, power: Power, settled: stop.Settlements) -> _Found:
    """W10a. How hard stopped-time hits land. Once settled it holds; until then the theory
    settles it, unless it contradicts what the power has already shown."""
    claimed = theory.claims_hit_mode or HitMode.RELATIVE_SPEED
    known = stop.known_hit_mode(power, settled)
    if known is not None:
        lands = known
        if claimed is HitMode.RELATIVE_SPEED:
            lands = stop.throw_mode(power, known, settled)
        holds = lands is claimed
        ruling = stop.ruling(
            power,
            stop.HIT_MODE,
            question=theory.claim,
            answer=stop.HIT_MODE_ANSWERS[known],
            holds=holds,
            source=RulingSource.THEORY,
        )
        return _Found(ruling)
    mode, holds = claimed, True
    if claimed is HitMode.UNTOUCHABLE and settled.get(power, stop.MOVE_FROZEN) == stop.YES:
        # The power has already let its user pick frozen things up.
        mode, holds = stop.default_hit_mode(power), False
    cost = ""
    settings: list[PowerSetting] = []
    if holds and mode is HitMode.RELATIVE_SPEED and _modest(power):
        cost = stop.HEAVY_DRAIN_COST
        settings.append(PowerSetting(key=stop.DRAIN, value=stop.HEAVY))
        settled.put(power, stop.DRAIN, stop.HEAVY)
    settled.put(power, stop.HIT_MODE, mode.value)
    ruling = stop.ruling(
        power,
        stop.HIT_MODE,
        question=theory.claim,
        answer=stop.HIT_MODE_ANSWERS[mode],
        holds=holds,
        source=RulingSource.THEORY,
        cost=cost,
    )
    return _Found(ruling, PowerChange(id=power.id, hit_mode=mode, settings=settings))


def _move_frozen(theory: PowerTheory, power: Power, settled: stop.Settlements) -> _Found:
    """W10a. Whether frozen things can be picked up: not where the power is untouchable, and
    otherwise yes, joining the stop as heavy as ever."""
    mode = stop.known_hit_mode(power, settled)
    answer = stop.NO if mode is HitMode.UNTOUCHABLE else stop.YES
    settled.put(power, stop.MOVE_FROZEN, answer)
    ruling = stop.ruling(
        power,
        stop.MOVE_FROZEN,
        question=theory.claim,
        answer=stop.MOVE_FROZEN_ANSWERS[answer],
        holds=answer == stop.YES,
        source=RulingSource.THEORY,
    )
    return _Found(ruling, PowerChange(id=power.id, settings=[_setting(stop.MOVE_FROZEN, answer)]))


def _other(
    state: WorldState,
    actor: Character,
    theory: PowerTheory,
    power: Power,
    topic: str,
    settled: stop.Settlements,
) -> _Found:
    """A9. Any other detail: it holds when something real stands behind it and its scale is one
    the power or the world can reach. Power alone is never a reason to refuse."""
    world_reach = force_mod.joules_for(strongest_tier(state), state.bible.force)
    needed = force_mod.SCALE_JOULES[theory.scale] if theory.scale is not None else 0.0
    in_scale = needed <= world_reach
    if not _grounded_in(state, actor, theory.rests_on) and not (theory.scale and in_scale):
        return _refused(theory, topic, power.id, NOTHING_BEHIND_IT)
    if needed > reach(state, actor, power, settled) and not in_scale:
        return _refused(theory, topic, power.id, TOO_BIG)
    cost = ""
    settings: list[PowerSetting] = []
    if _modest(power) and theory.scale in COSTLY_SCALES:
        cost = stop.HEAVY_DRAIN_COST
        settings.append(PowerSetting(key=stop.DRAIN, value=stop.HEAVY))
        settled.put(power, stop.DRAIN, stop.HEAVY)
    ruling = Ruling(
        id=f"ruling-{power.id}-{topic}",
        topic=topic,
        power_id=power.id,
        question=theory.claim,
        answer=f"{HOLDS} {theory.claim.strip()}",
        holds=True,
        cost=cost,
        source=RulingSource.THEORY,
    )
    change = PowerChange(id=power.id, settings=settings) if settings else None
    return _Found(ruling, change)


def _setting(key: str, value: str) -> PowerSetting:
    return PowerSetting(key=key, value=value)


def _modest(power: Power) -> bool:
    return power.strength in MODEST


def _grounded_in(state: WorldState, actor: Character, rests_on: list[str]) -> bool:
    """Whether a theory rests on anything: a power, item or technique of the actor's, a rule or
    a true fact of the world, or words. An id the state holds as false or dead doesn't count."""
    for ref in rests_on:
        ref = ref.strip()
        if not ref:
            continue
        fact = state.facts.get(ref)
        if fact is not None:
            if fact.is_true:
                return True
            continue
        character = state.characters.get(ref)
        if character is not None:
            if character.alive:
                return True
            continue
        return True
    return False


def strongest_tier(state: WorldState) -> float:
    """The tier of the strongest being the world holds: its ladders' top rungs, its creatures and
    its characters. A world "works at a scale" when its strongest beings do (A9)."""
    tiers = [r.tier for ladder in state.bible.ladders for r in ladder.rungs]
    tiers += [c.tier for c in state.bible.creatures]
    tiers += [base_tier(state, c, PowerAxis.MIGHT) for c in state.characters.values()]
    return float(max(tiers, default=1))


def reach(state: WorldState, actor: Character, power: Power, settled: stop.Settlements) -> float:
    """About the most energy the power can put into one hit: for a time stop whose hits land at
    relative speed, the heaviest thing its user can lift; otherwise the user's own might."""
    might = force_mod.joules_for(base_tier(state, actor, PowerAxis.MIGHT), state.bible.force)
    if not stop.stops_time(power):
        return might
    mode = stop.known_hit_mode(power, settled) or stop.default_hit_mode(power)
    if stop.throw_mode(power, mode, settled) is not HitMode.RELATIVE_SPEED:
        return might
    heaviest = force_mod.lift_kg(actor.sheet.attributes.strength)
    return max(might, force_mod.relative_speed_joules(heaviest))
