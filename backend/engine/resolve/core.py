"""Settle a plan step by step: logic first, dice only for real doubt (A2, A3).

For each step, in order:

1. **The world and the sheet** (G8, G14). A step the world's rules forbid, a power the character
   doesn't have or hasn't recovered, a technique they never learned or an item that isn't on them
   is settled at once, with no roll.
2. **The beats** (R2). Everything a beat uses must be the body, a power, something carried,
   something the scene holds or something this turn made canon. Something new is canon if the
   place plausibly holds it, rolled for if that's uncertain, and an empty search if it can't.
3. **Who stands in the way, and whether they can respond at all** (A2, A8). The facts the model
   proposed are checked against the state: the targets of a harmful aim always stand in the way,
   the dead never do, a sleeping or bound character can't respond whatever was proposed, a time
   stop freezes everyone but its user (W10a), and a claim that someone is frozen in time with no
   stop in effect is refused.
4. **The class** (A2). Against someone who can respond, the gap on the axis the step uses decides,
   measured in the rungs of the world's ladder (G18) and adjusted for condition and numbers (A8):
   two steps up is ruled out head-on, one is a long shot, closer is contested, and two below is
   certain. When nothing can push back, only the means count, and a code check caps them by how
   tough the target's body is: clearly enough is certain, clearly not is ruled out, and a close
   call is rolled between doing harm and doing full harm, never bouncing off harmlessly. A plan
   that goes around the strength is settled link by link instead (A9).
5. **The roll** (A3, A5), only for contested and long-shot steps and close calls, with odds held
   inside the class's band whatever the edges, skills and difficulty do.

A chain's own time is added to the step's world time; inside a time stop the world stands still
and the chain's time is left to the powers rules (WS9b). A chained plan stops at the first step
that doesn't cleanly succeed (R6). What the player claims
about outcomes or other people's reactions plays only as a hope (A6), and nothing in the intent
changes the state except a settled step's aim on living targets (A7).
"""

from dataclasses import dataclass, field

from engine.context import TurnContext
from engine.contracts.delta import StateDelta
from engine.contracts.intent import (
    ActionKind,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    StandingAction,
)
from engine.contracts.resolution import (
    BeatResolution,
    LinkResolution,
    Resolution,
    StepResolution,
    StopReason,
)
from engine.resolve import odds as odds_mod
from engine.resolve.chain import settle_chain
from engine.resolve.checks import Drawn, Settled, beat_check, sheet_check, world_check
from engine.resolve.durations import step_timing
from engine.resolve.effects import aim_effects, power_costs, proposed_deed
from engine.resolve.power import (
    Standing,
    claims_frozen_in_time,
    helpless_state,
    scale,
    standing,
)
from engine.resolve.words import cap, is_are, mentions, name
from engine.rng import SeededRng
from engine.state.cast import Character
from engine.state.records import RollRecord, StepResult
from engine.state.sheet import PowerAxis, SkillLevel, TimeEffect, TraitKind
from engine.state.world import WorldState
from engine.timekeeping import bound_duration, in_time_stop, stop_power_used

STANDING_DURATIONS_S = {StandingAction.WAIT: 60, StandingAction.OBSERVE: 30}
NOTHING_IN_THE_WAY = "Nothing stands in the way."
FROZEN = "frozen in stopped time"

# Shifts to the log-odds of a rolled step (A2: a clever approach shifts the odds within bounds).
EDGE_SHIFT = 0.35  # each edge or hindrance the interpret step proposed
MAX_EDGES = 3  # how many of each count
SKILL_SHIFT = 0.25  # each rank of skill above or below fair
TECHNIQUE_SHIFT = 0.6  # G25: technique matters most within a gap
TRAIT_SHIFT = 0.3  # a gift used, or a flaw that gets in the way
MAX_TRAITS = 2
ATTITUDE_SHIFT = 1.2  # A3: at full devotion or full hatred, on the influence axis
# A8: allies count. Each other opponent within a step of the strongest adds this, up to the cap.
NUMBERS_STEP = 0.5
MAX_NUMBERS = 1.0
INTIMIDATION = ("intimidate", "threaten", "menace", "scare", "frighten", "coerce", "bully")

_MEANS_ORDER = [MeansVerdict.CLEARLY_NOT, MeansVerdict.CLOSE_CALL, MeansVerdict.CLEARLY_ENOUGH]


@dataclass
class _Frame:
    """What carries from one step of a plan to the next: a time stop and this turn's canon."""

    frozen: bool
    stop_left_s: int | None
    canon: list[str] = field(default_factory=list)


@dataclass
class _Opposition:
    """Who stands in the way of one step, after the facts were checked against the state."""

    responsive: list[Character] = field(default_factory=list)
    helpless: list[tuple[Character, str]] = field(default_factory=list)
    targets: list[Character] = field(default_factory=list)  # whom the aim lands on
    answering: list[Character] = field(default_factory=list)  # who can still answer a chain (A9)
    unmeasured: bool = False  # something that pushes back with no sheet: a faction, a storm
    unmeasured_frozen: bool = False

    @property
    def characters(self) -> list[Character]:
        return [*self.responsive, *(c for c, _ in self.helpless)]

    @property
    def can_push_back(self) -> bool:
        return bool(self.responsive) or self.unmeasured


def resolve_intent(
    state: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng
) -> Resolution:
    """B5 step 3. Turn the interpret step's proposal into the engine's decision. The state is read
    only. Rolls come from `rng.child("resolve", "step", i)` and streams under it, so a step rolls
    the same however the steps around it went.

    The graph passes the player's own intent with `actor_id` unset or the player's id; an NPC's
    intent names the NPC. An actor id the state doesn't hold falls back to the player.
    """
    actor_id = intent.actor_id if intent.actor_id in state.characters else state.player_id
    actor = state.characters[actor_id]
    frame = _Frame(frozen=in_time_stop(state, actor_id), stop_left_s=_stop_left(state, actor))

    steps: list[StepResolution] = []
    stopped_at: int | None = None
    stop_reason: StopReason | None = None
    unplayed: list[str] = []
    stakes = False
    for i, step in enumerate(intent.steps):
        settled, step_stakes = _settle_step(
            state, actor, step, i, ctx, rng.child("resolve", "step", i), frame
        )
        steps.append(settled)
        stakes = stakes or step_stakes
        later = intent.steps[i + 1 :]
        if not settled.clean_success and later:
            stopped_at, unplayed = i, [s.text for s in later]
            if settled.outcome_class is OutcomeClass.RULED_OUT:
                stop_reason = StopReason.RULED_OUT
            elif settled.result is StepResult.PARTIAL:
                stop_reason = StopReason.PARTIAL
            else:
                stop_reason = StopReason.FAILED
            break

    if not steps and intent.standing is not None:
        steps = [_standing_step(intent.standing)]

    return Resolution(
        actor_id=intent.actor_id if intent.actor_id in state.characters else None,
        steps=steps,
        stopped_at_step=stopped_at,
        stop_reason=stop_reason,
        unplayed=unplayed,
        canon=frame.canon,
        stakes=stakes,
    )


def _standing_step(standing_action: StandingAction) -> StepResolution:
    kind = ActionKind(standing_action.value)
    return StepResolution(
        index=0,
        text=standing_action.value,
        outcome_class=OutcomeClass.CERTAIN,
        reason=NOTHING_IN_THE_WAY,
        result=StepResult.SUCCESS,
        duration_s=bound_duration(kind, STANDING_DURATIONS_S[standing_action]),
    )


def _stop_left(state: WorldState, actor: Character) -> int | None:
    """Lived seconds left in a time stop of the actor's already in effect; None if unbounded."""
    lived = actor.personal_s(state.world_s)
    left: list[int] = []
    for effect in state.time_effects:
        if effect.character_id != actor.id or effect.effect is not TimeEffect.STOP:
            continue
        if effect.ends_personal_s is None:
            return None
        if lived < effect.ends_personal_s:
            left.append(effect.ends_personal_s - lived)
    return max(left) if left else None


def _settle_step(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    index: int,
    ctx: TurnContext,
    rng: SeededRng,
    frame: _Frame,
) -> tuple[StepResolution, bool]:
    drawn = Drawn()
    beats: list[BeatResolution] = []
    chain: list[LinkResolution] = []
    stopped_at_link: int | None = None
    chain_s = 0
    opposition: _Opposition | None = None
    stop_power = None

    settled = world_check(state, actor, step) or sheet_check(state, actor, step, drawn)
    attempted = settled is None
    if attempted:
        stop_power = stop_power_used(state, actor.id, step)
    frozen = frame.frozen or stop_power is not None
    if settled is None:
        found = beat_check(state, actor, step, frame.canon, drawn, ctx, rng)
        beats = found.checks
        frame.canon.extend(found.canon)
        settled = found.settled
    if settled is None:
        opposition = _opposition(state, actor, step, frozen)
        if step.chain:
            settled, outcome = _with_chain(state, actor, step, opposition, drawn, ctx, rng)
            if outcome is not None:
                chain, stopped_at_link, chain_s = outcome.links, outcome.stopped_at, outcome.takes_s
        elif opposition.can_push_back:
            settled = _contested(state, actor, step, opposition, drawn, ctx, rng)
        else:
            settled = _unopposed(state, actor, step, opposition, drawn, ctx, rng)

    timing = step_timing(
        step,
        frozen=frozen,
        rolls=settled.outcome_class is not OutcomeClass.RULED_OUT,
        rng=rng.child("duration"),
    )
    duration = timing.duration_s if frozen else timing.duration_s + chain_s
    roll = settled.roll
    if timing.rolled_s is not None:
        if roll is not None:
            roll = roll.model_copy(update={"duration_s": timing.rolled_s})
        else:
            roll = RollRecord(
                seed=rng.child("duration").seed,
                label="how long it takes",
                odds=1.0,
                odds_label="certain",
                value=timing.rolled_value,
                result=settled.result,
                allowed=[settled.result],
                difficulty=ctx.settings.difficulty,
                duration_s=timing.rolled_s,
            )

    if stop_power is not None:
        frame.frozen, frame.stop_left_s = True, stop_power.time.lasts_s
    if frame.frozen and frame.stop_left_s is not None:
        frame.stop_left_s -= timing.personal_s or 0
        if frame.stop_left_s <= 0:
            frame.frozen, frame.stop_left_s = False, None

    targets = opposition.targets if opposition is not None else []
    effects = StateDelta()
    if settled.outcome_class is not OutcomeClass.RULED_OUT:
        effects = aim_effects(step, settled.result, targets)
    deed = None
    if opposition is not None:
        deed = proposed_deed(
            step,
            settled.outcome_class,
            settled.result,
            actor.id if actor.id != state.player_id else None,
            opposition.characters,
            in_stopped_time=frozen,
        )
    stakes = bool(
        step.aim.harmful
        or roll is not None
        or (opposition is not None and (opposition.characters or opposition.unmeasured))
    )
    resolution = StepResolution(
        index=index,
        text=step.text,
        outcome_class=settled.outcome_class,
        reason=settled.reason,
        roll=roll,
        result=settled.result,
        costs=power_costs(drawn.powers) if attempted else [],
        duration_s=duration,
        personal_s=timing.personal_s,
        beats=beats,
        chain=chain,
        stopped_at_link=stopped_at_link,
        effects=effects,
        deeds=[deed] if deed is not None else [],
    )
    return resolution, stakes


def _opposition(state: WorldState, actor: Character, step: IntentStep, frozen: bool) -> _Opposition:
    """A2, A8. Who stands in the way, checked against the state.

    The targets of a harmful aim, or of a social step, stand in the way whatever was proposed. The
    dead never do. A time stop freezes everyone but its user (W10a; immunity is WS9b's), a
    helpless state on the sheet (asleep, bound, stunned) means they can't respond whatever was
    proposed, and the model's word that they can't respond (unaware, cornered) is taken unless it
    claims a time stop that isn't there.
    """
    facts = step.facts
    ids = list(dict.fromkeys(facts.opposition_ids))
    target_ids = [t for t in dict.fromkeys(step.target_ids) if t in state.characters]
    if step.aim.harmful or step.axis is PowerAxis.INFLUENCE:
        ids += [t for t in target_ids if t not in ids]
    people = [
        state.characters[i]
        for i in ids
        if i in state.characters and i != actor.id and state.characters[i].alive
    ]
    factions = any(i in state.factions for i in ids)
    unmeasured = not people and (bool(facts.opposition.strip()) or factions)

    says_cannot = facts.can_respond is False
    refuted = says_cannot and claims_frozen_in_time(facts.why_not) and not frozen
    found = _Opposition()
    for person in people:
        on_sheet = helpless_state(person)
        why = FROZEN if frozen else on_sheet
        if why is None and says_cannot and not refuted:
            why = facts.why_not.strip() or "unable to respond"
        if why is None:
            found.responsive.append(person)
        else:
            found.helpless.append((person, why))
        # A chain's links play out after a stop ends, and someone merely unaware notices the
        # fire; only someone asleep, bound or stunned can't answer them (A9).
        if on_sheet is None:
            found.answering.append(person)
    if unmeasured:
        if frozen or (says_cannot and not refuted):
            found.unmeasured_frozen = True
        else:
            found.unmeasured = True
    if step.aim.harmful:
        aimed = [p for p in people if p.id in target_ids]
        found.targets = aimed or people
    return found


def _axis(step: IntentStep) -> PowerAxis | None:
    """The axis the step is measured on; a harmful aim meets the body, so might."""
    if step.axis is not None:
        return step.axis
    return PowerAxis.MIGHT if step.aim.harmful else None


def _contested(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
) -> Settled:
    """Someone or something can push back. The power gap decides the class where both sides can
    be measured; otherwise it is contested, or harder if the interpret step judged it so."""
    axis = _axis(step)
    difficulty = ctx.settings.difficulty
    if step.aim.harmful and axis is not PowerAxis.MIGHT and opposition.targets:
        # Getting the blow in by stealth or a trick doesn't make it hurt a body far above it.
        gap, toughest = _body(state, actor, opposition.targets)
        if gap >= odds_mod.RULED_OUT_AT:
            reason = f"{_beyond_harm(state, toughest)}."
            return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)
    shift = _shift(state, actor, step, drawn, opposition, axis)
    if axis is not None and opposition.responsive:
        measure = scale(state, axis, actor, *opposition.responsive)
        mine = standing(state, actor, axis, measure)
        theirs = sorted(
            (standing(state, c, axis, measure) for c in opposition.responsive),
            key=lambda s: (-s.tier, s.character.id),
        )
        strongest = theirs[0]
        close = sum(1 for s in theirs[1:] if strongest.tier - s.tier < measure.step)
        numbers = min(MAX_NUMBERS, NUMBERS_STEP * close)
        gap = (strongest.tier - mine.tier) / measure.step + numbers
        lead = _compare(state, mine, strongest, gap, numbers > 0)
        if gap >= odds_mod.RULED_OUT_AT:
            return Settled(
                OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{lead}: head-on, there is no contest."
            )
        if gap <= odds_mod.CERTAIN_AT:
            them = "they" if len(theirs) > 1 else name(state, strongest.character.id)
            return Settled(
                OutcomeClass.CERTAIN, StepResult.SUCCESS, f"{lead}: {them} can't push back."
            )
        outcome_class = (
            OutcomeClass.LONG_SHOT if gap >= odds_mod.LONG_SHOT_AT else OutcomeClass.CONTESTED
        )
        base = odds_mod.gap_logit(gap)
    else:
        proposed = step.facts.proposed_class
        what = step.facts.opposition.strip() or "Something"
        if proposed is OutcomeClass.RULED_OUT:
            return Settled(
                OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{cap(what)}: there is no way past."
            )
        outcome_class = (
            OutcomeClass.LONG_SHOT if proposed is OutcomeClass.LONG_SHOT else OutcomeClass.CONTESTED
        )
        base = odds_mod.logit(odds_mod.UNMEASURED_ODDS[outcome_class])
        lead = f"{cap(what)} can push back"
        if opposition.responsive:
            lead = f"{cap(_names(state, opposition.responsive))} can push back"
    odds = odds_mod.settle(base, shift, odds_mod.BANDS[outcome_class], difficulty)
    roll = odds_mod.roll(
        rng.child("outcome"),
        odds,
        label=step.text,
        allowed=odds_mod.ALL_RESULTS,
        difficulty=difficulty,
    )
    words = roll.odds_label
    if outcome_class is OutcomeClass.LONG_SHOT:
        words = f"a long shot, {words}"
    return Settled(outcome_class, roll.result, f"{lead}: {words}.", roll)


def _unopposed(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
) -> Settled:
    """A2. When nothing can push back, the only question is whether the means are enough. The
    interpret step proposes the verdict; where the target has a body to measure, code caps it by
    how far that body stands above the actor's might, so no proposal makes a kitchen knife bite an
    ancient dragon."""
    facts = step.facts
    means = facts.means or _means_from_class(facts.proposed_class)
    ceiling: MeansVerdict | None = None
    toughest: Standing | None = None
    if (step.aim.harmful or step.axis is PowerAxis.MIGHT) and opposition.helpless:
        gap, toughest = _body(state, actor, [c for c, _ in opposition.helpless])
        if gap >= odds_mod.RULED_OUT_AT:
            ceiling = MeansVerdict.CLEARLY_NOT
        elif gap >= odds_mod.LONG_SHOT_AT:
            ceiling = MeansVerdict.CLOSE_CALL
        else:
            ceiling = MeansVerdict.CLEARLY_ENOUGH
    verdict = means if ceiling is None else min(means, ceiling, key=_MEANS_ORDER.index)

    lead = _helpless_lead(state, opposition)
    if verdict is MeansVerdict.CLEARLY_ENOUGH:
        reason = f"{lead}: no contest." if lead else NOTHING_IN_THE_WAY
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
    if verdict is MeansVerdict.CLEARLY_NOT:
        if ceiling is MeansVerdict.CLEARLY_NOT and toughest is not None:
            why = _beyond_harm(state, toughest)
        else:
            why = "; ".join(h for h in facts.hindrances if h.strip()) or "The means aren't enough"
            why = cap(why)
        reason = f"{lead}, but {why[0].lower()}{why[1:]}." if lead else f"{why}."
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)

    difficulty = ctx.settings.difficulty
    shift = _shift(state, actor, step, drawn, opposition, None)
    odds = odds_mod.settle(0.0, shift, odds_mod.CLOSE_CALL_BAND, difficulty)
    roll = odds_mod.roll(
        rng.child("outcome"),
        odds,
        label=step.text,
        allowed=odds_mod.HARM_DONE,
        difficulty=difficulty,
    )
    close = f"a close call, {roll.odds_label} it goes all the way"
    reason = f"{lead}, but it's {close}." if lead else f"{cap(close)}."
    return Settled(OutcomeClass.CONTESTED, roll.result, reason, roll)


def _with_chain(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
):
    """A9. A plan that goes around the strength instead of meeting it. Whoever can see it coming
    may answer first, so the setup is rolled against anyone who can respond; then the chain
    settles link by link against everyone who can still answer."""
    difficulty = ctx.settings.difficulty
    setup: RollRecord | None = None
    setup_class = OutcomeClass.CERTAIN
    if opposition.can_push_back:
        proposed = step.facts.proposed_class
        who = (
            _names(state, opposition.responsive)
            if opposition.responsive
            else step.facts.opposition.strip() or "they"
        )
        if proposed is OutcomeClass.RULED_OUT:
            reason = f"{cap(who)} will see it coming and answer first."
            return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason), None
        setup_class = (
            OutcomeClass.LONG_SHOT if proposed is OutcomeClass.LONG_SHOT else OutcomeClass.CONTESTED
        )
        odds = odds_mod.settle(
            odds_mod.logit(odds_mod.UNMEASURED_ODDS[setup_class]),
            _shift(state, actor, step, drawn, opposition, None),
            odds_mod.BANDS[setup_class],
            difficulty,
        )
        setup = odds_mod.roll(
            rng.child("outcome"),
            odds,
            label=f"before {who} can answer",
            allowed=odds_mod.YES_OR_NO,
            difficulty=difficulty,
        )
        if setup.result is not StepResult.SUCCESS:
            single = (
                len(opposition.responsive) == 1 and opposition.responsive[0].id != state.player_id
            )
            sees = "sees" if single or not opposition.responsive else "see"
            reason = f"{cap(who)} {sees} it coming in time ({setup.odds_label})."
            return Settled(setup_class, StepResult.FAILURE, reason, setup), None
    elif step.facts.means is MeansVerdict.CLEARLY_NOT:
        why = "; ".join(h for h in step.facts.hindrances if h.strip()) or "The means aren't enough"
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{cap(why)}."), None

    outcome = settle_chain(state, step, opposition.answering, ctx, rng)
    outcome_class = outcome.outcome_class
    if outcome.holds and outcome_class is OutcomeClass.CERTAIN:
        outcome_class = setup_class
    result = StepResult.SUCCESS if outcome.holds else StepResult.FAILURE
    return Settled(outcome_class, result, outcome.reason, setup), outcome


def _body(state: WorldState, actor: Character, people: list[Character]) -> tuple[float, Standing]:
    """A2, G18. How far the toughest body among `people` stands above the actor's might, in steps
    of power: what a harmful aim has to get through, whoever can or can't respond."""
    measure = scale(state, PowerAxis.MIGHT, actor, *people)
    mine = standing(state, actor, PowerAxis.MIGHT, measure)
    toughest = max(
        (standing(state, c, PowerAxis.MIGHT, measure) for c in people),
        key=lambda s: (s.tier, s.character.id),
    )
    return (toughest.tier - mine.tier) / measure.step, toughest


def _beyond_harm(state: WorldState, toughest: Standing) -> str:
    body = name(state, toughest.character.id)
    if toughest.rung:
        body = f"{body} at {toughest.rung}"
    return f"{cap(body)} {is_are(state, toughest.character.id)} far beyond what this can hurt"


def _means_from_class(proposed: OutcomeClass | None) -> MeansVerdict:
    if proposed is OutcomeClass.RULED_OUT:
        return MeansVerdict.CLEARLY_NOT
    if proposed in (OutcomeClass.CONTESTED, OutcomeClass.LONG_SHOT):
        return MeansVerdict.CLOSE_CALL
    return MeansVerdict.CLEARLY_ENOUGH


def _shift(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    opposition: _Opposition,
    axis: PowerAxis | None,
) -> float:
    """The log-odds shifts from what the step brings: edges and hindrances (A2, A8), skill and
    technique (G14, G25), traits used (G13), and the target's attitude for a social step (A3)."""
    facts = step.facts
    edges = sum(1 for e in facts.edges if e.strip())
    hindrances = sum(1 for h in facts.hindrances if h.strip())
    shift = EDGE_SHIFT * (min(MAX_EDGES, edges) - min(MAX_EDGES, hindrances))

    fair = SkillLevel.FAIR.rank
    if drawn.skills:
        mine = [actor.sheet.skill(s) for s in drawn.skills]
        best = max((s.level.rank for s in mine if s is not None), default=0)
        shift += SKILL_SHIFT * (best - fair)
        if opposition.responsive:
            rival = opposition.responsive[0]
            theirs = [rival.sheet.skill(s) for s in drawn.skills]
            known = [s.level.rank for s in theirs if s is not None]
            if known:
                shift -= SKILL_SHIFT * (max(known) - fair)
    if drawn.techniques:
        shift += TECHNIQUE_SHIFT
    traits = [t for t in actor.sheet.traits if any(mentions(t.name, ref) for ref in drawn.traits)]
    gifts = sum(1 for t in traits if t.kind is TraitKind.GIFT)
    flaws = sum(1 for t in traits if t.kind is TraitKind.FLAW)
    shift += TRAIT_SHIFT * (min(MAX_TRAITS, gifts) - min(MAX_TRAITS, flaws))

    if axis is PowerAxis.INFLUENCE and opposition.responsive:
        attitude = opposition.responsive[0].attitude_toward(actor.id)
        if any(mentions(step.verb, word) for word in INTIMIDATION):
            shift += ATTITUDE_SHIFT * attitude.fear / 100
        else:
            shift += ATTITUDE_SHIFT * (attitude.affinity + attitude.trust) / 200
    return shift


def _names(state: WorldState, people: list[Character]) -> str:
    names = [name(state, p.id) for p in people]
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _notes(found: Standing) -> str:
    return f", {', '.join(found.notes)}," if found.notes else ""


def _compare(state: WorldState, mine: Standing, theirs: Standing, gap: float, more: bool) -> str:
    """A8, G16. The gap in the world's words: rung names where the world has a ladder."""
    them = name(state, theirs.character.id)
    me = name(state, mine.character.id)
    others = " with others at their side" if more else ""
    if theirs.rung and mine.rung:
        mine_notes = _notes(mine).rstrip(",")
        lead = f"{cap(them)} at {theirs.rung}{_notes(theirs)}{others}"
        return f"{lead} against {me} at {mine.rung}{mine_notes}"
    if gap >= 2:
        words = "far beyond"
    elif gap >= 1:
        words = "well above"
    elif gap > 0.25:
        words = "above"
    elif gap >= -0.25:
        words = "evenly matched with"
    elif gap > -1:
        words = "below"
    elif gap > -2:
        words = "well below"
    else:
        words = "far below"
    notes = _notes(theirs)
    verb = is_are(state, theirs.character.id)
    return f"{cap(them)}{notes}{others} {verb} {words} {me}"


def _helpless_lead(state: WorldState, opposition: _Opposition) -> str:
    if opposition.helpless:
        person, why = opposition.helpless[0]
        if len(opposition.helpless) == 1:
            who = name(state, person.id)
            return f"{cap(who)} {is_are(state, person.id)} {why} and can't respond"
        everyone = _names(state, [p for p, _ in opposition.helpless])
        return f"{cap(everyone)} can't respond ({why})"
    if opposition.unmeasured_frozen:
        return "Nothing in the way can respond"
    return ""
