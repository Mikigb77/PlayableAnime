"""Chains of cause and effect, settled link by link (A9).

A plan that goes around someone's strength instead of meeting it isn't judged by the power gap. Each
link is settled the way A2 settles a step: it holds if the facts say so, it is rolled only if the
model judged it genuinely open, and it breaks if what it rests on isn't so or if the target has an
answer to it and can still use it: a way to teleport out, to breathe without air, to put out the
fire. The chain stops at the first link that breaks, and each link takes the in-world time it
really takes (W10).
"""

from dataclasses import dataclass

from engine.context import TurnContext
from engine.contracts.intent import ChainLink, IntentStep, OutcomeClass
from engine.contracts.resolution import LinkResolution
from engine.resolve import odds as odds_mod
from engine.resolve.durations import CHAIN_MAX_S
from engine.resolve.words import cap, is_are, mentions, name, possessive
from engine.rng import SeededRng
from engine.state.cast import Character
from engine.state.records import StepResult
from engine.state.world import WorldState


@dataclass(frozen=True)
class ChainOutcome:
    links: list[LinkResolution]
    holds: bool
    stopped_at: int | None
    outcome_class: OutcomeClass
    takes_s: int
    reason: str


def settle_chain(
    state: WorldState,
    step: IntentStep,
    targets: list[Character],
    ctx: TurnContext,
    rng: SeededRng,
) -> ChainOutcome:
    """Settle `step.chain` against `targets`, the characters who can still answer it."""
    links: list[LinkResolution] = []
    takes = 0
    rolled: set[OutcomeClass] = set()
    for j, link in enumerate(step.chain):
        settled = _settle_link(state, link, targets, ctx, rng.child("link", j))
        takes = min(CHAIN_MAX_S, takes + settled.takes_s)
        links.append(settled)
        if settled.roll is not None:
            rolled.add(settled.outcome_class)
        if not settled.holds:
            reason = f"It breaks at “{link.text}”. {settled.reason}"
            return ChainOutcome(links, False, j, settled.outcome_class, takes, reason)
    if OutcomeClass.LONG_SHOT in rolled:
        outcome_class = OutcomeClass.LONG_SHOT
    elif rolled:
        outcome_class = OutcomeClass.CONTESTED
    else:
        outcome_class = OutcomeClass.CERTAIN
    last = step.chain[-1].text if step.chain else ""
    reason = f"Every link holds: {last}" if last else "Every link holds."
    return ChainOutcome(links, True, None, outcome_class, takes, reason)


def _settle_link(
    state: WorldState,
    link: ChainLink,
    targets: list[Character],
    ctx: TurnContext,
    rng: SeededRng,
) -> LinkResolution:
    takes = min(CHAIN_MAX_S, link.takes_s or 0)

    def settled(outcome_class: OutcomeClass, holds: bool, reason: str, roll=None):
        return LinkResolution(
            text=link.text,
            outcome_class=outcome_class,
            reason=reason,
            holds=holds,
            roll=roll,
            takes_s=takes,
        )

    broken = _broken_basis(state, link)
    if broken:
        return settled(OutcomeClass.RULED_OUT, False, broken)
    for target in targets:
        for answer in link.answers:
            way_out = find_answer(state, target, answer)
            if way_out:
                who = cap(name(state, target.id))
                has = "have" if target.id == state.player_id else "has"
                return settled(OutcomeClass.RULED_OUT, False, f"{who} {has} a way out: {way_out}.")
    proposed = link.proposed_class
    if proposed is OutcomeClass.RULED_OUT:
        return settled(OutcomeClass.RULED_OUT, False, "It doesn't hold here.")
    if proposed in (OutcomeClass.CONTESTED, OutcomeClass.LONG_SHOT):
        difficulty = ctx.settings.difficulty
        odds = odds_mod.settle(
            odds_mod.logit(odds_mod.UNMEASURED_ODDS[proposed]),
            0.0,
            odds_mod.BANDS[proposed],
            difficulty,
        )
        roll = odds_mod.roll(
            rng, odds, label=link.text, allowed=odds_mod.YES_OR_NO, difficulty=difficulty
        )
        holds = roll.result is StepResult.SUCCESS
        reason = f"It could go either way: {roll.odds_label}."
        return settled(proposed, holds, reason, roll)
    return settled(OutcomeClass.CERTAIN, True, _basis_reason(state, link))


def _broken_basis(state: WorldState, link: ChainLink) -> str:
    """Why a link can't rest on what it claims to: a fact that isn't true, or someone dead."""
    for ref in link.rests_on:
        fact = state.facts.get(ref)
        if fact is not None and not fact.is_true:
            return f"It rests on something that isn't so ({fact.text.rstrip('.')})."
        character = state.characters.get(ref)
        if character is not None and not character.alive:
            return f"{cap(name(state, character.id))} {is_are(state, character.id)} dead."
    return ""


def _basis_reason(state: WorldState, link: ChainLink) -> str:
    words: list[str] = []
    for ref in link.rests_on:
        if ref in state.facts:
            words.append(state.facts[ref].text.rstrip("."))
        elif ref in state.characters:
            words.append(state.characters[ref].name)
        elif state.bible.rule(ref) is not None:
            words.append(state.bible.rule(ref).text.rstrip("."))
        else:
            power = _any_power(state, ref)
            words.append(power or ref)
    return f"It follows from {'; '.join(words)}." if words else "It follows."


def _any_power(state: WorldState, power_id: str) -> str | None:
    for character in state.characters.values():
        power = character.sheet.power(power_id)
        if power is not None:
            return f"{possessive(state, character.id)} {power.name}"
    return None


def find_answer(state: WorldState, target: Character, answer: str) -> str | None:
    """A9. Something on the target's sheet that answers the link: a ready power, a technique, a
    carried item or a trait whose name or description says it does what the answer needs."""
    sheet = target.sheet
    lived = target.personal_s(state.world_s)
    for power in sheet.powers:
        if power.ready_at_personal_s is not None and lived < power.ready_at_personal_s:
            continue
        if mentions(f"{power.name} {power.description}", answer):
            return _named(power.name, power.description)
    for technique in sheet.techniques:
        if mentions(f"{technique.name} {technique.effect}", answer):
            return _named(technique.name, technique.effect)
    for item in sheet.resources.items:
        usable = item.carried and item.quantity > 0
        if usable and mentions(f"{item.name} {item.description}", answer):
            return _named(item.name, item.description)
    for trait in sheet.traits:
        if mentions(f"{trait.name} {trait.description}", answer):
            return _named(trait.name, trait.description)
    return None


def _named(title: str, description: str) -> str:
    description = description.strip().rstrip(".")
    return f"{title} ({description})" if description else title
