"""Settle a plan step by step: logic first, dice only for real doubt (A2, A3).

For each step, in order:

1. **The world and the sheet** (G8, G14, C10). A step the world's rules forbid, a power the
   character doesn't have or hasn't recovered, a technique they never learned, an item that isn't
   on them, or a payment, gift or use of something they don't hold is settled at once, with no
   roll. A move they make with a power of theirs, such as an aura blade from their aura, is that
   power at work, never a technique they never learned, and the first time it comes off cleanly it
   becomes a technique of their own (A4, G25). What a step pays, gives, spends or takes moves as
   the engine's own change when it works (`engine.resolve.exchanges`).
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
   call is rolled. A blow that lands is rolled between doing harm and doing full harm, never
   bouncing off harmlessly; anything else can simply fail. Where nobody can be measured against
   the actor (only things in the way, a faction, a close call), the challenge the interpret step
   judged for an ordinary person, weighed against the actor's attributes, skills, traits, powers
   and condition, decides: a step they are sure to manage is certain where only things stand in
   the way, one they rarely would is a long shot, and the rest are contested (G14,
   `engine.resolve.capability`). A plan that goes around the strength is settled link by link
   instead (A9).
5. **The roll** (A3, A5), only for contested and long-shot steps and close calls, with odds held
   inside the class's band whatever the edges, skills, the story's difficulty and a run of misses
   do. Each miss in a row since the player character's last clean success makes their next roll
   likelier, so bad luck doesn't pile up on what they're good at.

Powers (`engine.resolve.powers`, WS9b) come into it at each stage. The player's theories about
their powers are ruled on first, once, so every step follows the answer (A9), and backstory
claims are judged (N4). In a time stop (W10a), everyone but its user and those immune to it is
frozen; how each blow, throw or lift lands follows the power's settled hit mode, which code
settles itself the first time it matters and never asks the player; air and friction never get in
the user's way; a relative-speed hit is measured by its own force, not the user's arm, and a throw
that lands that way blasts whatever is near, its thrower too once time restarts. A step that
starts in a stop and outlasts it lives out the stop and then takes world time. A training step
grows the character (A4), a breakthrough is rolled (G19), and hiding or revealing strength
changes what others sense (G20).

A chain's own time is added to the step's world time; inside a time stop the chain plays out once
time restarts, and a link that burns or ruins a place changes it (A9, W7). A chained plan stops at
the first step that doesn't cleanly succeed (R6). What the player claims about outcomes or other
people's reactions plays only as a hope (A6), and nothing in the intent changes the state except
what code settles from it (A7).
"""

from dataclasses import dataclass, field

from engine.context import TurnContext
from engine.contracts.delta import (
    CharacterChange,
    ItemChange,
    PlaceChange,
    PowerChange,
    PowerSetting,
    StateDelta,
)
from engine.contracts.intent import (
    ActionKind,
    Contact,
    GrowthKind,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    PlaceHarm,
    StandingAction,
)
from engine.contracts.resolution import (
    BeatResolution,
    LinkResolution,
    ProposedDeed,
    Resolution,
    StepResolution,
    StopReason,
    TrainingSoFar,
)
from engine.resolve import capability, exchanges
from engine.resolve import odds as odds_mod
from engine.resolve import perils as perils_mod
from engine.resolve import strangers as strangers_mod
from engine.resolve.chain import settle_chain
from engine.resolve.checks import Drawn, Settled, beat_check, sheet_check, world_check
from engine.resolve.durations import lived_estimate, step_timing, until_time
from engine.resolve.effects import aim_effects, power_costs, proposed_deed
from engine.resolve.power import (
    Scale,
    Standing,
    base_tier,
    claims_frozen_in_time,
    helpless_name,
    helpless_state,
    ranked_with_numbers,
    scale,
    standing,
)
from engine.resolve.powers import claims as claims_mod
from engine.resolve.powers import growth, sensing
from engine.resolve.powers import theories as theories_mod
from engine.resolve.powers import time_stop as stop
from engine.resolve.words import cap, is_are, name, names, possessive, stems
from engine.rng import SeededRng
from engine.state.cast import Character, CharacterStatus, PlaceStatus
from engine.state.records import RollRecord, StepResult, Trace, TraceKind
from engine.state.scene import EncounterKind
from engine.state.sheet import (
    Health,
    HitMode,
    Power,
    PowerAxis,
    Ruling,
    RulingSource,
    Technique,
    TimeEffect,
)
from engine.state.world import ActiveTimeEffect, WorldState
from engine.timekeeping import bound_duration, effect_over, in_time_stop

STANDING_DURATIONS_S = {StandingAction.WAIT: 60, StandingAction.OBSERVE: 30}
NOTHING_IN_THE_WAY = "Nothing stands in the way."
FROZEN = "frozen in stopped time"

_MEANS_ORDER = [MeansVerdict.CLEARLY_NOT, MeansVerdict.CLOSE_CALL, MeansVerdict.CLEARLY_ENOUGH]
_HARDER = [OutcomeClass.CERTAIN, OutcomeClass.CONTESTED, OutcomeClass.LONG_SHOT]
_TEMPO = (TimeEffect.HASTE, TimeEffect.SLOW)
_FIRE_STEMS = stems("burn burns fire fires flame flames blaze alight ablaze torch")


@dataclass
class _Tempo:
    """W10a. A haste or slow in effect: the actor's lived seconds per world second."""

    power: Power
    rate: float
    left_s: int | None


@dataclass
class _Frame:
    """What carries from one step of a plan to the next: a time stop or a haste, the actor's own
    clock, what this plan settled about powers, effort toward gains, and this turn's canon."""

    frozen: bool
    stop_left_s: int | None
    canon: list[str] = field(default_factory=list)
    personal_s: int = 0
    world_s: int = 0  # the world clock as this step starts, had the steps before it run in full
    stop_power: Power | None = None  # the actor's stop holding the world, if one does
    tempo: _Tempo | None = None
    ready_at: dict[str, int] = field(default_factory=dict)  # cooldowns on the actor's clock
    training: TrainingSoFar | None = None  # the current step's training so far, if any
    settled: stop.Settlements = field(default_factory=stop.Settlements)
    rulings: list[Ruling] = field(default_factory=list)
    practice: dict[str, float] = field(default_factory=dict)
    gone: str | None = None  # why the actor can't act any more, such as their own blast
    met: list[Character] = field(default_factory=list)  # strangers this plan made real (F1)
    alert: set[str] = field(default_factory=set)  # hidden masters among them, who see it coming
    fighting: list[str] = field(default_factory=list)  # foes this plan fought (N6)
    out: set[str] = field(default_factory=set)  # foes it killed, subdued or got away from (N6)
    # A3: the player character's rolled steps that missed in a row so far, within this plan;
    # `engine.pipeline.play_out` keeps the count from the steps that played, for the next turn.
    misses: int = 0
    moved: list[ItemChange] = field(default_factory=list)  # C10: what this plan moved so far
    learned: list[Technique] = field(default_factory=list)  # A4: moves this plan made theirs


@dataclass
class _Opposition:
    """Who stands in the way of one step, after the facts were checked against the state."""

    responsive: list[Character] = field(default_factory=list)
    helpless: list[tuple[Character, str]] = field(default_factory=list)
    targets: list[Character] = field(default_factory=list)  # whom the aim lands on
    answering: list[Character] = field(default_factory=list)  # who can still answer a chain (A9)
    unmeasured: bool = False  # something that pushes back with no sheet: a faction, a storm
    factions: bool = False  # a faction is named in the way, who could still answer
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
    frame = _frame(state, actor)
    # A9. Theories are ruled on before anything is tried, so every step follows the answer.
    theories = theories_mod.rule_on_theories(state, actor, intent.theories, frame.settled, [])
    frame.rulings.extend(theories.rulings)
    verdicts, effects = claims_mod.judge_claims(state, actor, intent.backstory)
    if theories.powers:
        changes = StateDelta(characters=[CharacterChange(id=actor.id, powers=theories.powers)])
        effects = _merge(effects, changes)

    steps: list[StepResolution] = []
    stopped_at: int | None = None
    stop_reason: StopReason | None = None
    unplayed: list[str] = []
    stakes = False
    for i, step in enumerate(intent.steps):
        settled, step_stakes, own_choice = _settle_step(
            state, actor, step, i, ctx, rng.child("resolve", "step", i), frame
        )
        steps.append(settled)
        stakes = stakes or step_stakes
        later = intent.steps[i + 1 :]
        # G15. A step only the actor's own nature stood in the way of was done, however hard it
        # was, so the plan carries on: the temper never takes the rest of it from the player.
        if not (settled.clean_success or own_choice) and later:
            stopped_at, unplayed = i, [s.text for s in later]
            if settled.outcome_class is OutcomeClass.RULED_OUT:
                stop_reason = StopReason.RULED_OUT
            elif settled.result is StepResult.PARTIAL:
                stop_reason = StopReason.PARTIAL
            else:
                stop_reason = StopReason.FAILED
            break
        if settled.hurt_by_peril and later:
            # N6. Struck, the character reacts before anything else they planned.
            stopped_at, unplayed, stop_reason = i, [s.text for s in later], StopReason.STRUCK
            break

    if not steps and intent.standing is not None:
        steps = [_standing_step(state, actor, intent.standing, ctx, rng, frame)]

    return Resolution(
        actor_id=intent.actor_id if intent.actor_id in state.characters else None,
        steps=steps,
        stopped_at_step=stopped_at,
        stop_reason=stop_reason,
        unplayed=unplayed,
        rulings=theories.rulings,
        canon=frame.canon,
        claims=verdicts,
        effects=effects,
        stakes=stakes,
    )


def _standing_step(
    state: WorldState,
    actor: Character,
    standing_action: StandingAction,
    ctx: TurnContext,
    rng: SeededRng,
    frame: _Frame,
) -> StepResolution:
    """Waiting or watching (S2). In a fight the foes still in it strike all the same (N6)."""
    kind = ActionKind(standing_action.value)
    duration_s = bound_duration(kind, STANDING_DURATIONS_S[standing_action])
    standing = StepResolution(
        index=0,
        text=standing_action.value,
        outcome_class=OutcomeClass.CERTAIN,
        reason=NOTHING_IN_THE_WAY,
        result=StepResult.SUCCESS,
        duration_s=duration_s,
    )
    if actor.id != state.player_id or state.scene.encounter is None:
        return standing
    still = IntentStep(
        text=standing_action.value,
        verb=standing_action.value,
        kind=kind,
        proposed_duration_s=duration_s,
    )
    struck = perils_mod.strike_back(
        state,
        actor,
        still,
        outcome_class=OutcomeClass.CERTAIN,
        result=StepResult.SUCCESS,
        faced=[],
        out=set(),
        fighting=[],
        frozen=frame.frozen,
        health=actor.sheet.condition.health,
        difficulty=ctx.settings.difficulty,
        rng=rng.child("resolve", "step", 0, "peril"),
    )
    return standing.model_copy(
        update={"perils": struck.perils, "effects": struck.effects, "deeds": struck.deeds}
    )


def _frame(state: WorldState, actor: Character) -> _Frame:
    """The plan starts where the state is: in a stop or a haste of the actor's own, or not."""
    lived = actor.personal_s(state.world_s)
    frame = _Frame(
        frozen=in_time_stop(state, actor.id),
        stop_left_s=_stop_left(state, actor),
        personal_s=lived,
        world_s=state.world_s,
        misses=state.misses_in_a_row if actor.id == state.player_id else 0,
    )
    # A1. Cooldowns already running on the actor's clock, so a stop carried over from an earlier
    # turn can't be started afresh once it runs out partway through this plan.
    for power in actor.sheet.powers:
        if power.ready_at_personal_s is not None and power.ready_at_personal_s > lived:
            frame.ready_at[power.id] = power.ready_at_personal_s
    for effect in state.time_effects:
        if effect.character_id != actor.id or effect_over(state, effect):
            continue
        power = actor.sheet.power(effect.power_id)
        if power is None or power.time is None:
            continue
        if effect.effect is TimeEffect.STOP and frame.frozen:
            frame.stop_power = power
        elif effect.effect in _TEMPO and power.time.rate:
            left = None if effect.ends_personal_s is None else effect.ends_personal_s - lived
            frame.tempo = _Tempo(power, power.time.rate, left)
    return frame


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
) -> tuple[StepResolution, bool, bool]:
    """The step settled, whether it held real stakes (W16), and whether only the actor's own
    nature stood in its way, so it was done whatever the roll said (G15)."""
    if frame.met:
        state = _with_people(state, frame.met)
    drawn = Drawn()
    beats: list[BeatResolution] = []
    chain: list[LinkResolution] = []
    stopped_at_link: int | None = None
    chain_s = 0
    opposition: _Opposition | None = None
    new_stop: Power | None = None  # a time stop this step starts
    new_tempo: Power | None = None  # a haste or slow this step starts
    hit: stop.StoppedHit | None = None
    extra = StateDelta()  # the engine's changes besides the aim's
    deeds: list[ProposedDeed] = []
    after: list[str] = []  # what follows from the outcome, in words, after its reason

    gone = frame.gone is not None
    if gone:
        settled = Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, frame.gone)
    else:
        settled = (
            world_check(state, actor, step)
            or sheet_check(state, actor, step, drawn)
            or exchanges.check(state, actor, step, frame.moved)
        )
    attempted = settled is None
    if settled is None:
        found = beat_check(state, actor, step, frame.canon, drawn, ctx, rng)
        beats = found.checks
        frame.canon.extend(found.canon)
        settled = found.settled or _recovered(state, actor, drawn, frame)
    if attempted and not (settled is not None and settled.reason.endswith(_NOT_RECOVERED)):
        # W10a. A time stop the step uses, named on the step or in a beat, freezes the world;
        # the stop already holding it is the same use carrying on.
        new_stop = next(
            (p for p in drawn.powers if stop.stops_time(p) and not _continuing(frame, p)), None
        )
        new_tempo = next(
            (p for p in drawn.powers if _tempo_power(p) and not _continuing(frame, p)), None
        )
    holding = new_stop or (frame.stop_power if frame.frozen else None)
    frozen = frame.frozen or new_stop is not None
    stop_left = None
    if frozen:
        stop_left = stop.lasts_s(new_stop) if new_stop is not None else frame.stop_left_s
    # A step that outlasts the stop finishes once time runs again, so those it acts on can
    # answer by then (W10a).
    outlasts = frozen and stop_left is not None and lived_estimate(step) > stop_left
    frozen_now = frozen and not outlasts
    if frozen and holding is not None:
        step = _in_the_stop(step)

    growing = showing = False
    if settled is None and step.training is not None:
        growing = True
        settled = growth.check(state, actor, step, frame.canon)
        practice = growth.already_known(state, actor, step) if settled is None else None
        if practice is not None:
            # A4. Practising what they already know happens, and teaches nothing new.
            settled, growing = practice, False
        elif settled is None and step.training.kind is GrowthKind.BREAKTHROUGH:
            settled = growth.breakthrough(state, actor, step, rng, ctx.settings.difficulty)
        elif settled is None:
            settled = Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, "")
        else:
            growing = settled.outcome_class is not OutcomeClass.RULED_OUT
    elif settled is None and step.show_strength is not None:
        settled = sensing.check(state, actor, step)
        showing = settled is None
        settled = settled or Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, "")

    met: strangers_mod.Met | None = None
    if settled is None and step.aim.harmful and step.stranger is not None:
        if not any(t in state.characters and t != actor.id for t in step.target_ids):
            # F1, W1. The victim is someone the scene hasn't named: make them real first.
            met = strangers_mod.meet(state, actor, step, index, ctx, rng.child("stranger"))
            beats = [*beats, met.check]
            settled = met.settled
            if met.people:
                frame.met.extend(met.people)
                if met.alert:
                    frame.alert.add(met.people[0].id)
                state = _with_people(state, met.people)
                targeted = [*step.target_ids, met.people[0].id]
                step = step.model_copy(update={"target_ids": targeted})
    if settled is None:
        opposition = _opposition(state, actor, step, frozen_now, frame.alert)
        if holding is not None and frozen_now:
            hit, tested = _stopped_hit(state, actor, step, holding, frame, opposition)
            extra = _merge(extra, tested)
            if hit is not None and hit.blocked:
                settled = Settled(
                    OutcomeClass.RULED_OUT, StepResult.FAILURE, _sentence(hit.blocked)
                )
    own_choice = False
    player = actor.id == state.player_id
    # A3. A run of misses makes the player character's next roll likelier.
    misses = frame.misses if player else 0
    if settled is None:
        assert opposition is not None
        if step.chain:
            settled, outcome = _with_chain(
                state, actor, step, opposition, drawn, ctx, rng, misses=misses
            )
            if outcome is not None:
                chain, stopped_at_link, chain_s = outcome.links, outcome.stopped_at, outcome.takes_s
        elif _inner(state, actor, step, opposition):
            own_choice = True
            settled = _own_choice(state, actor, step, opposition, drawn, ctx, rng, misses=misses)
        elif opposition.can_push_back:
            settled = _contested(
                state, actor, step, opposition, drawn, ctx, rng, hit, misses=misses
            )
        else:
            settled = _unopposed(
                state, actor, step, opposition, drawn, ctx, rng, hit, misses=misses
            )
    if player:
        frame.misses = capability.misses_after(frame.misses, settled.roll, settled.result)

    # W10, A3. An uncertain duration on a rolled step is the second draw of that roll's own seed,
    # so the one recorded seed replays both the outcome and the time; otherwise it has its own.
    roll = settled.roll
    duration_rng = rng.child("duration")
    if roll is not None:
        duration_rng = SeededRng(roll.seed)
        duration_rng.random()  # the outcome's draw
    timed_step = step
    if growing and step.training is not None and step.training.kind is GrowthKind.BREAKTHROUGH:
        timed_step = step.model_copy(update={"duration_uncertain": True})  # G19
    tempo, tempo_left = (None, None) if frozen else _rate(new_tempo, frame)
    timing = None
    if not frozen and tempo is None and settled.outcome_class is not OutcomeClass.RULED_OUT:
        # W10. "Until nightfall" is counted on the world's clock from where this step starts.
        # In a stop or a haste, and for a step that never got going, the proposal stands.
        timing = until_time(step, state.bible.calendar, frame.world_s)
    if timing is None:
        timing = step_timing(
            timed_step,
            frozen=frozen,
            rolls=settled.outcome_class is not OutcomeClass.RULED_OUT,
            rng=duration_rng,
            stop_left_s=stop_left,
            outlasts=outlasts if frozen else None,
            rate=tempo,
            rate_left_s=tempo_left,
        )
    duration = timing.duration_s
    personal = timing.personal_s
    if gone:
        duration, personal = 0, None  # the dead take no time over anything
    if not frozen:
        duration += chain_s
    elif duration > 0 and chain_s:
        # Outlasting the stop, the chain plays out once time runs again, and the actor lives it.
        duration += chain_s
        personal = (personal or 0) + chain_s
    # Set off and left inside the stop, a chain is settled now, like a stopped-time throw, and
    # plays out once time restarts without holding the actor, who can't wait on frozen time.
    if timing.rolled_s is not None:
        if roll is not None:
            roll = roll.model_copy(update={"duration_s": timing.rolled_s})
        else:
            roll = RollRecord(
                seed=duration_rng.seed,
                label="how long it takes",
                odds=1.0,
                odds_label="certain",
                value=timing.rolled_value,
                result=settled.result,
                allowed=[settled.result],
                difficulty=ctx.settings.difficulty,
                duration_s=timing.rolled_s,
            )

    started = frame.personal_s
    if new_stop is not None:
        extra = _merge(extra, _takes_hold(actor, new_stop, started, frame))
        frame.frozen, frame.stop_left_s, frame.stop_power = True, stop.lasts_s(new_stop), new_stop
    if frame.frozen and frame.stop_left_s is not None and not gone:
        frame.stop_left_s -= timing.personal_s or 0
        if frame.stop_left_s <= 0:
            frame.frozen, frame.stop_left_s, frame.stop_power = False, None, None
    if new_tempo is not None:
        extra = _merge(extra, _takes_hold(actor, new_tempo, started, frame))
        lasts = stop.lasts_s(new_tempo)
        frame.tempo = _Tempo(new_tempo, new_tempo.time.rate or 1.0, lasts)
    lived = personal if personal is not None else duration
    if frame.tempo is not None and frame.tempo.left_s is not None:
        frame.tempo.left_s -= lived
        if frame.tempo.left_s <= 0:
            frame.tempo = None
    frame.personal_s += lived
    frame.world_s += duration

    targets = opposition.targets if opposition is not None else []
    effects = StateDelta()
    happened = settled.outcome_class is not OutcomeClass.RULED_OUT
    if happened:
        effects = aim_effects(step, settled.result, targets)
    if met is not None:
        if actor.id == state.player_id:
            # Not in the scene's record yet, but the player saw what they did to them.
            effects = _known_to_player(effects, {p.id for p in met.people})
        effects = _merge(met.effects, effects)  # they're real before anything happens to them
    effects = _merge(effects, extra)
    if attempted:
        # C10. What the step pays, gives, spends or takes moves now, before anything is told.
        moves = exchanges.changes(
            state, actor, step, settled.outcome_class, settled.result, frame.moved
        )
        frame.moved.extend(moves)
        effects = _merge(effects, StateDelta(items=moves))
    reason = settled.reason
    # W10a. A stopped-time hit that was made lands however the target fares: a throw that a
    # target's body takes, or that misses, still lets its blast loose where it strikes.
    released = hit is not None and not hit.blocked
    if released and hit.reason:
        after.append(hit.reason)
    if released and hit.blast is not None:
        blasted = stop.blast_outcome(state, actor, step, hit, targets)
        effects = _merge(effects, blasted.effects)
        after.append(blasted.reason)
        if blasted.deed is not None:
            deeds.append(blasted.deed)
        if blasted.actor_dies:
            frame.gone = f"{cap(name(state, actor.id))} died in the blast of {_own(state, actor)}."
    if frame.gone is None and _kills(effects, actor):
        # F1. Harm turned on themselves that killed them ends the plan: the dead do nothing more.
        frame.gone = f"{cap(name(state, actor.id))} {is_are(state, actor.id)} dead."
    frame.training = None
    if growing and happened:
        why, grown, deed = _grow(state, actor, step, settled, frame, personal, duration)
        reason = f"{reason} {why}".strip()
        effects = _merge(effects, grown)
        if deed is not None:
            deeds.append(deed)
    if showing:
        why, shown, deed = sensing.settle(state, actor, step)
        reason = why
        effects = _merge(effects, shown)
        if deed is not None:
            deeds.append(deed)
    if chain:
        places, deed = _chain_places(state, actor, step, chain)
        effects = _merge(effects, places)
        if deed is not None:
            deeds.append(deed)
    clean = happened and settled.result is StepResult.SUCCESS and frame.gone is None
    if drawn.moves and clean and not (growing or showing):
        # A4, G25. A move made with their own power that came off cleanly is theirs now.
        why, learned, change = growth.proven(state, actor, step, drawn.moves, frame.learned)
        if why:
            after.append(why)
            effects = _merge(effects, change)
            frame.learned.extend(learned)
    reason = " ".join([reason, *(_sentence(a) for a in after)]).strip()

    if actor.id == state.player_id and frame.gone is None:
        # N6. The foes still in the fight answer, and a danger the step faced strikes.
        frame.out |= _taken_out(effects)
        struck = perils_mod.strike_back(
            state,
            actor,
            step,
            outcome_class=settled.outcome_class,
            result=settled.result,
            faced=opposition.responsive if opposition is not None else [],
            out=frame.out,
            fighting=frame.fighting,
            frozen=frozen_now,
            health=_health_now(effects, actor),
            difficulty=ctx.settings.difficulty,
            rng=rng.child("peril"),
        )
        perils, escaped = struck.perils, struck.escaped
        frame.fighting = list(dict.fromkeys([*frame.fighting, *struck.fighting]))
        frame.out |= set(struck.escaped)
        effects = _merge(effects, struck.effects)
        deeds.extend(struck.deeds)
        if struck.dead:
            frame.gone = f"{cap(name(state, actor.id))} {is_are(state, actor.id)} dead."
    else:
        perils, escaped = [], []

    if opposition is not None:
        # Harm to oneself is no deed against anyone (W1): only others are its victims.
        others_hit = [t for t in targets if t.id != actor.id]
        deed = proposed_deed(
            step,
            settled.outcome_class,
            settled.result,
            actor.id if actor.id != state.player_id else None,
            targets=others_hit,
            others=[c for c in opposition.characters if c not in targets],
            in_stopped_time=frozen_now,
        )
        if deed is not None and frozen_now and holding is not None:
            deed = _stopped_deed(state, actor, step, deed, holding, hit, others_hit, settled)
        if deed is not None:
            deeds.insert(0, deed)
    stakes = bool(
        step.aim.harmful
        or roll is not None
        or (opposition is not None and (opposition.characters or opposition.unmeasured))
        or (hit is not None and hit.blast is not None)
    )
    used = [p for p in drawn.powers if p is new_stop or p is new_tempo or not _time_power(p)]
    # R1, A3. What of their own the step used, once past the sheet: it works as they know it
    # to, so a miss comes from what stood in the way. A power not yet recovered didn't work.
    unready = settled.outcome_class is OutcomeClass.RULED_OUT and settled.reason.endswith(
        _NOT_RECOVERED
    )
    drew_on = drawn.names if attempted and not unready else []
    encounter, opponent_ids = _engagement(step, opposition, actor.id)
    resolution = StepResolution(
        index=index,
        text=step.text,
        outcome_class=settled.outcome_class,
        reason=reason,
        roll=roll,
        result=settled.result,
        costs=power_costs(used) if attempted else [],
        drew_on=drew_on,
        duration_s=duration,
        personal_s=personal,
        beats=beats,
        strangers=[p.id for p in met.people] if met is not None else [],
        chain=chain,
        stopped_at_link=stopped_at_link,
        effects=effects,
        deeds=deeds,
        training=frame.training,
        kind=step.kind,
        encounter=encounter,
        opponent_ids=opponent_ids,
        perils=perils,
        escaped=escaped,
    )
    return resolution, stakes, own_choice


def _engagement(
    step: IntentStep, opposition: _Opposition | None, actor_id: str
) -> tuple[EncounterKind | None, list[str]]:
    """W10. The encounter a step starts or carries on, and with whom; `engine.encounters`
    decides what comes of it. A step settled before it was tried, such as reaching for a sword
    that isn't there, met no one. Harm aimed at a living character is a fight with them and with
    whoever pushes back; otherwise the interpret step's proposal stands only when someone who can
    respond faces the step, and only they are in it: nobody chases or bargains with a sleeper.
    Everyone the step faced is still named, so it can carry on an encounter it doesn't start."""
    if opposition is None:
        return None, []
    others = [t for t in opposition.targets if t.id != actor_id]  # nobody fights themselves
    faced = [c.id for c in (*others, *opposition.characters)]
    faced = list(dict.fromkeys(faced))
    if step.aim.harmful and others:
        return EncounterKind.FIGHT, faced
    if step.encounter is not None and opposition.responsive:
        responsive = {c.id for c in opposition.responsive}
        return step.encounter, [i for i in faced if i in responsive]
    return None, faced


_NOT_RECOVERED = "hasn't recovered yet."


def _time_power(power: Power) -> bool:
    return power.time is not None and (stop.stops_time(power) or _tempo_power(power))


def _tempo_power(power: Power) -> bool:
    return power.time is not None and power.time.effect in _TEMPO and bool(power.time.rate)


def _continuing(frame: _Frame, power: Power) -> bool:
    """W10a. Naming a stop or a haste that is already in effect carries it on: it is not a new use,
    with no new cost and no new cooldown."""
    if frame.frozen and frame.stop_power is not None and frame.stop_power.id == power.id:
        return True
    return frame.tempo is not None and frame.tempo.power.id == power.id


def _recovered(state: WorldState, actor: Character, drawn: Drawn, frame: _Frame) -> Settled | None:
    """A1. A power used earlier in this plan is on cooldown until the actor's own clock reaches
    it."""
    for power in drawn.powers:
        ready_at = frame.ready_at.get(power.id)
        if ready_at is not None and frame.personal_s < ready_at and not _continuing(frame, power):
            return Settled(
                OutcomeClass.RULED_OUT,
                StepResult.FAILURE,
                f"{cap(possessive(state, actor.id))} {power.name} {_NOT_RECOVERED}",
            )
    return None


def _rate(new_tempo: Power | None, frame: _Frame) -> tuple[float | None, int | None]:
    """W10a. A haste or slow's rate for this step, and how many lived seconds it has left."""
    if new_tempo is not None and new_tempo.time is not None:
        return new_tempo.time.rate, stop.lasts_s(new_tempo)
    if frame.tempo is not None:
        return frame.tempo.rate, frame.tempo.left_s
    return None, None


def _takes_hold(actor: Character, power: Power, started: int, frame: _Frame) -> StateDelta:
    """W10a, A1. A stop or a haste takes hold on the user's own clock: it lasts its time from the
    step's start, so a stop that outlasts the plan still holds the world next turn, and the power
    is ready again a recharge after it ends."""
    assert power.time is not None
    ends = started + stop.lasts_s(power)
    effect = ActiveTimeEffect(
        character_id=actor.id,
        power_id=power.id,
        effect=power.time.effect,
        started_personal_s=started,
        ends_personal_s=ends,
    )
    ready_at = ends + stop.recharge_s(power, frame.settled)
    frame.ready_at[power.id] = ready_at
    change = CharacterChange(
        id=actor.id, powers=[PowerChange(id=power.id, ready_at_personal_s=ready_at)]
    )
    return StateDelta(characters=[change], time_effects=[effect])


def _in_the_stop(step: IntentStep) -> IntentStep:
    """W10a. The user moves and breathes freely in their own stop: hindrances about air,
    friction or breath never get in the way. When they were all the doubt the interpret step
    saw, the means it doubted are enough."""
    kept = stop.drop_convention_hindrances(step.facts.hindrances)
    if kept == step.facts.hindrances:
        return step
    update: dict = {"hindrances": kept}
    if not any(h.strip() for h in kept) and step.facts.means is not MeansVerdict.CLEARLY_ENOUGH:
        update.update(means=None, proposed_class=None)
    return step.model_copy(update={"facts": step.facts.model_copy(update=update)})


def _ruled(actor: Character, frame: _Frame, topic: str, power: Power) -> bool:
    if actor.sheet.ruling(topic, power.id) is not None:
        return True
    return any((r.topic, r.power_id) == (topic, power.id) for r in frame.rulings)


def _stopped_hit(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    power: Power,
    frame: _Frame,
    opposition: _Opposition,
) -> tuple[stop.StoppedHit | None, StateDelta]:
    """W10a, A9. How a blow, a throw or a lift lands in the actor's own stop. The first time it
    matters, code settles the power's way, never asking the player, and records the ruling."""
    contact = stop.contact_of(step)
    if contact is Contact.NONE:
        return None, StateDelta()
    rulings: list[Ruling] = []
    change = PowerChange(id=power.id)
    known = stop.known_hit_mode(power, frame.settled)
    mode = known or stop.default_hit_mode(power)
    if contact is Contact.LIFT:
        movable = frame.settled.get(power, stop.MOVE_FROZEN)
        if movable is None:
            movable = stop.NO if mode is HitMode.UNTOUCHABLE else stop.YES
            frame.settled.put(power, stop.MOVE_FROZEN, movable)
            change.settings.append(PowerSetting(key=stop.MOVE_FROZEN, value=movable))
            if not _ruled(actor, frame, stop.MOVE_FROZEN, power):
                rulings.append(
                    stop.ruling(
                        power,
                        stop.MOVE_FROZEN,
                        question=step.text,
                        answer=stop.MOVE_FROZEN_ANSWERS[movable],
                        holds=movable == stop.YES,
                        source=RulingSource.TEST,
                    )
                )
        if movable == stop.NO:
            mode = HitMode.UNTOUCHABLE
    elif known is None:
        frame.settled.put(power, stop.HIT_MODE, mode.value)
        change.hit_mode = mode
        if not _ruled(actor, frame, stop.HIT_MODE, power):
            rulings.append(
                stop.ruling(
                    power,
                    stop.HIT_MODE,
                    question=step.text,
                    answer=stop.HIT_MODE_ANSWERS[mode],
                    holds=True,
                    source=RulingSource.TEST,
                )
            )
    frame.rulings.extend(rulings)
    hit = stop.stopped_hit(state, actor, step, power, mode, frame.settled, opposition.targets)
    if not rulings and change == PowerChange(id=power.id):
        return hit, StateDelta()
    powers = [change] if change != PowerChange(id=power.id) else []
    tested = CharacterChange(id=actor.id, rulings=rulings, powers=powers)
    return hit, StateDelta(characters=[tested])


def _stopped_deed(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    deed: ProposedDeed,
    power: Power,
    hit: stop.StoppedHit | None,
    targets: list[Character],
    settled: Settled,
) -> ProposedDeed:
    """W10a, W13. Done in stopped time: only someone immune to the stop saw it, and it leaves
    the traces nobody can miss, such as a guard who drops dead with nobody near."""
    killed = []
    if step.aim.harmful and settled.outcome_class is not OutcomeClass.RULED_OUT:
        if settled.result is StepResult.SUCCESS and step.aim.value == "kill":
            killed = [t for t in targets if t.alive]
    traces = [*deed.traces, *stop.stopped_traces(state, actor, power, hit, killed)]
    return deed.model_copy(
        update={
            "witness_ids": stop.witnesses(state, actor, exclude={k.id for k in killed}),
            "traces": traces,
        }
    )


def _grow(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    settled: Settled,
    frame: _Frame,
    personal: int | None,
    duration: int,
) -> tuple[str, StateDelta, ProposedDeed | None]:
    """A4, G19. What a stretch of training or a breakthrough attempt did."""
    training = step.training
    assert training is not None
    if training.kind is GrowthKind.BREAKTHROUGH:
        assert settled.roll is not None
        return growth.breakthrough_effects(state, actor, step, settled.result, settled.roll)
    key = growth.practice_key(step)
    so_far = frame.practice.get(key)
    if so_far is None:
        recorded = actor.sheet.practiced(key)
        so_far = float(recorded.effort_s) if recorded is not None else 0.0
    lived = personal if personal is not None else duration
    made = growth.progress(state, actor, step, lived, so_far, frame.settled)
    frame.practice[key] = made.effort_s
    rate, need = growth.pace_and_need(state, actor, step)
    frame.training = TrainingSoFar(
        key=key, what=training.what, before_s=so_far, rate=rate, need_s=need
    )
    return made.reason, made.effects, None


def _chain_places(
    state: WorldState, actor: Character, step: IntentStep, links: list[LinkResolution]
) -> tuple[StateDelta, ProposedDeed | None]:
    """A9, W7. A link that held and burns or ruins a place changes it, and the burning is a deed
    of its own that everyone nearby can see (agreed with the living world, WS10)."""
    places: list[PlaceChange] = []
    traces: list[Trace] = []
    worst = PlaceHarm.NONE
    fire = False
    for link, settled in zip(step.chain, links, strict=False):
        if not settled.holds or link.place_harm is PlaceHarm.NONE:
            continue
        place = state.places.get(link.place_id or "")
        if place is None or place.status is PlaceStatus.RUINED:
            continue
        status = PlaceStatus.RUINED if link.place_harm is PlaceHarm.RUINED else PlaceStatus.DAMAGED
        if status is PlaceStatus.DAMAGED and place.status is not PlaceStatus.THRIVING:
            continue
        places.append(PlaceChange(id=place.id, status=status, known_to_player=True))
        fire = fire or bool(stems(f"{step.verb} {link.text}") & _FIRE_STEMS)
        if link.place_harm is PlaceHarm.RUINED:
            worst = PlaceHarm.RUINED
        elif worst is PlaceHarm.NONE:
            worst = PlaceHarm.DAMAGED
        words = "lies in ruins" if status is PlaceStatus.RUINED else "is badly damaged"
        traces.append(
            Trace(kind=TraceKind.DAMAGE, text=f"{cap(place.name)} {words}.", strength=100)
        )
    if not places:
        return StateDelta(), None
    if fire:
        kind = "burn"
    else:
        kind = "raze" if worst is PlaceHarm.RUINED else "destroy"
    severity = 4 if worst is PlaceHarm.RUINED else 2
    deed = ProposedDeed(
        kind=kind,
        text=f"{step.text} ({', '.join(state.places[p.id].name for p in places)})",
        actor_id=actor.id if actor.id != state.player_id else None,
        target_ids=[p.id for p in places],
        place_id=places[0].id,
        severity=severity,
        traces=traces,
    )
    return StateDelta(places=places), deed


def _own(state: WorldState, actor: Character) -> str:
    return "your own throw" if actor.id == state.player_id else "their own throw"


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text.endswith((".", "!", "?")) else f"{text}."


def _with_people(state: WorldState, people: list[Character]) -> WorldState:
    """The state as this plan sees it, with the strangers it made real (F1). The state the
    caller passed stays as it was."""
    characters = {**state.characters, **{p.id: p for p in people}}
    return state.model_copy(update={"characters": characters})


def _known_to_player(effects: StateDelta, ids: set[str]) -> StateDelta:
    changes = [
        c.model_copy(update={"known_to_player": True}) if c.id in ids else c
        for c in effects.characters
    ]
    return effects.model_copy(update={"characters": changes})


def _kills(effects: StateDelta, character: Character) -> bool:
    """Whether these changes leave the character dead."""
    return any(
        change.id == character.id and change.status is CharacterStatus.DEAD
        for change in effects.characters
    )


def _taken_out(effects: StateDelta) -> set[str]:
    """N6. Whom a step's own changes killed or left helpless (dying, subdued, knocked out), so
    they don't strike back."""
    return {
        change.id
        for change in effects.characters
        if change.status is CharacterStatus.DEAD
        or (
            change.condition is not None
            and (
                change.condition.health is Health.DYING
                or any(helpless_name(s) for s in change.condition.states)
            )
        )
    }


def _health_now(effects: StateDelta, character: Character) -> Health:
    """The character's health once a step's own changes are in: the last one it sets."""
    health = character.sheet.condition.health
    for change in effects.characters:
        if change.id == character.id and change.condition and change.condition.health:
            health = change.condition.health
    return health


def _merge(*deltas: StateDelta) -> StateDelta:
    """One delta holding every change of the given ones, in order."""
    merged = StateDelta()
    for delta in deltas:
        if delta.empty:
            continue
        merged = merged.model_copy(
            update={
                name_: [*getattr(merged, name_), *getattr(delta, name_)]
                for name_ in (
                    "characters",
                    "factions",
                    "places",
                    "facts",
                    "items",
                    "leads",
                    "rule_changes",
                    "time_effects",
                )
            }
        )
    return merged


def _opposition(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    frozen: bool,
    alert: set[str] | frozenset[str] = frozenset(),
) -> _Opposition:
    """A2, A8. Who stands in the way, checked against the state.

    The targets of a harmful aim, or of a social step, stand in the way whatever was proposed. The
    dead never do. A time stop freezes everyone but its user and those immune to it (W10a), a
    helpless state on the sheet (asleep, bound, stunned) means they can't respond whatever was
    proposed, and the model's word that they can't respond (unaware, cornered) is taken unless it
    claims a time stop that isn't there, or they are a hidden master who sees it coming (`alert`).
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
    if unmeasured and not factions and step.aim.harmful and actor.id in target_ids:
        # F1, G15. Hesitation before harming yourself ("my fear", "his own nerve") is never
        # something pushing back: only words that name more, such as guards or a storm, are.
        unmeasured = _inner_words(actor, facts.opposition) is None

    says_cannot = facts.can_respond is False
    refuted = says_cannot and claims_frozen_in_time(facts.why_not) and not frozen
    found = _Opposition(factions=factions)
    for person in people:
        on_sheet = helpless_state(person)
        why = FROZEN if frozen and not stop.immune(person) else on_sheet
        if why is None and says_cannot and not refuted and person.id not in alert:
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
        # The aim lands on whom the step names, if they're alive; on whoever stands in the way
        # only when it names no one.
        found.targets = [p for p in people if p.id in target_ids] if step.target_ids else people
        if actor.id in target_ids and actor.alive:
            # F1. Harm the actor aims at their own body (a blade turned on themselves, a jump
            # from the battlements) lands on them like any other target. They never stand in
            # their own way: the choice is theirs, so only the means decide (A2, G15).
            found.targets.append(actor)
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
    hit: stop.StoppedHit | None = None,
    *,
    misses: int = 0,
) -> Settled:
    """Someone or something can push back. The power gap decides the class where both sides can
    be measured, and what each brings to the step tilts the odds (G14). Otherwise the challenge
    the interpret step judged, weighed against what the actor brings, decides it: certain where
    only things stand in the way and the actor is sure to manage, a long shot where they rarely
    would, contested between (`engine.resolve.capability`)."""
    axis = _axis(step)
    difficulty = ctx.settings.difficulty
    # A harmful aim still has to get through the body of each target it doesn't meet head-on:
    # getting the blow in by stealth, or past a guard while the target sleeps, doesn't make it
    # hurt a body far above it.
    unmet = [
        t
        for t in opposition.targets
        if axis is not PowerAxis.MIGHT or t not in opposition.responsive
    ]
    if step.aim.harmful and unmet and hit is not None and hit.force_tier is not None:
        # W10a. A relative-speed hit is measured by its own force, not the user's arm.
        margin, body = stop.force_ceiling_margin(state, unmet, hit.force_tier)
        if margin >= stop.TAKES_IT_MARGIN:
            return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, _takes_it(state, body))
    elif step.aim.harmful and unmet:
        gap, toughest = _body(state, actor, unmet)
        if gap >= odds_mod.RULED_OUT_AT:
            reason = f"{_beyond_harm(state, toughest)}."
            return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)
    if axis is not None and opposition.responsive:
        menace = axis is PowerAxis.INFLUENCE and _backed_by_force(state, actor, step)
        if menace:
            # W5, A8: a threat backed by what the actor can do, as the world knows it, meets
            # the target's own force or standing, whichever stands up to it better.
            measure = scale(state, PowerAxis.MIGHT, actor, *opposition.responsive)
            mine, known_power = _menacing(state, actor, measure)
            ranked = (_withstanding(state, c, measure) for c in opposition.responsive)
        else:
            measure = scale(state, axis, actor, *opposition.responsive)
            mine, known_power = standing(state, actor, axis, measure), False
            ranked = (standing(state, c, axis, measure) for c in opposition.responsive)
        theirs, numbers = ranked_with_numbers(list(ranked), measure)
        strongest = theirs[0]
        gap = (strongest.tier - mine.tier) / measure.step + numbers
        lead = _compare(state, mine, strongest, gap, numbers > 0)
        if known_power:
            lead = f"{lead}, knowing what {name(state, actor.id)} can do"
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
        rivals = [s.character for s in theirs]
        weighed = capability.weigh(
            state, actor, step, drawn, rivals=rivals, axis=axis, measured=True
        ).with_misses(misses)
        detail = weighed.words(state, actor).removeprefix(", ")
    else:
        proposed = step.facts.proposed_class
        what = step.facts.opposition.strip() or "Something"
        if proposed is OutcomeClass.RULED_OUT:
            return Settled(
                OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{cap(what)}: there is no way past."
            )
        weighed = capability.weigh(
            state, actor, step, drawn, rivals=opposition.responsive, axis=axis, measured=False
        )
        # A2. Only things in the way (a lantern, a locked door, the wind), never someone or a
        # faction who could still answer, can leave a step certain. (Here nobody is targeted but
        # the actor, so no body stands to be hurt.)
        things_only = not (opposition.responsive or opposition.factions)
        outcome_class, base = _from_challenge(step, weighed, proposed, may_be_certain=things_only)
        if outcome_class is OutcomeClass.CERTAIN:
            stopper = "Nothing" if what == "Something" else cap(what)
            lead = f"{stopper} can't stop {name(state, actor.id)}"
            return Settled(
                OutcomeClass.CERTAIN,
                StepResult.SUCCESS,
                _said(lead, _detail(step, weighed, state, actor)),
            )
        weighed = weighed.with_misses(misses)
        detail = _detail(step, weighed, state, actor)
        lead = f"{cap(what)} can push back"
        if opposition.responsive:
            lead = f"{cap(names(state, opposition.responsive))} can push back"
    odds = odds_mod.settle(
        base, weighed.shift + weighed.luck, odds_mod.BANDS[outcome_class], difficulty
    )
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
    if detail:
        words = f"{detail}, {words}"
    return Settled(outcome_class, roll.result, f"{lead}: {words}.", roll)


def _from_challenge(
    step: IntentStep,
    weighed: capability.Weighed,
    proposed: OutcomeClass | None,
    *,
    may_be_certain: bool,
) -> tuple[OutcomeClass, float]:
    """A2. The class and base log-odds of a step nobody is measured against. An ordinary
    person's odds at the challenge, shifted by what the actor brings, decide the class, before
    the story's difficulty and any run of misses: at `CERTAIN_ODDS` or more it is certain where
    `may_be_certain`, below `LONG_SHOT_BELOW` a long shot, and contested between."""
    base = capability.base_logit(step.facts.challenge, proposed)
    chance = odds_mod.sigmoid(base + weighed.shift)
    if may_be_certain and chance >= odds_mod.CERTAIN_ODDS:
        return OutcomeClass.CERTAIN, base
    if chance < odds_mod.LONG_SHOT_BELOW:
        return OutcomeClass.LONG_SHOT, base
    return OutcomeClass.CONTESTED, base


def _detail(step: IntentStep, weighed: capability.Weighed, state: WorldState, actor: Character):
    """The challenge and what the actor brings to it, in words: "an easy task, your speed and
    your Agile in your favour", or only what they bring when no challenge was judged (A8)."""
    task = capability.challenge_words(step.facts.challenge)
    factors = weighed.words(state, actor)
    return f"{task}{factors}" if task else factors.removeprefix(", ")


def _said(lead: str, detail: str) -> str:
    """ "Lead: detail.", or "Lead." when there is nothing to add."""
    return f"{lead}: {detail}." if detail else f"{lead}."


def _unopposed(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    hit: stop.StoppedHit | None = None,
    *,
    misses: int = 0,
) -> Settled:
    """A2. When nothing can push back, the only question is whether the means are enough. The
    interpret step proposes the verdict; where the target has a body to measure, code caps it by
    how far that body stands above the actor's might, so no proposal makes a kitchen knife bite an
    ancient dragon. A close call is weighed like any task nobody is measured against: the
    challenge against what the actor brings, so one they are sure to manage is certain after all,
    unless a body tougher than their might caps it (`engine.resolve.capability`).

    A hit that lands at relative speed in stopped time is measured by its own force instead, and
    code decides it alone, whatever the interpret step thought a pebble could do (W10a, A9): it
    is enough unless a body tough enough takes it, and a close call within half a tier of it."""
    facts = step.facts
    means = facts.means or _means_from_class(facts.proposed_class)
    # With no verdict on the means, a step the interpret step called a long shot stays one.
    long_shot = facts.means is None and facts.proposed_class is OutcomeClass.LONG_SHOT
    ceiling: MeansVerdict | None = None
    toughest: Standing | None = None
    takes_it: Character | None = None
    bodies = opposition.targets if step.aim.harmful else [c for c, _ in opposition.helpless]
    if hit is not None and hit.force_tier is not None and bodies:
        margin, body = stop.force_ceiling_margin(state, bodies, hit.force_tier)
        if margin >= stop.TAKES_IT_MARGIN:
            ceiling, takes_it = MeansVerdict.CLEARLY_NOT, body
        elif margin > -stop.TAKES_IT_MARGIN:
            ceiling = MeansVerdict.CLOSE_CALL
        else:
            ceiling = MeansVerdict.CLEARLY_ENOUGH
    elif (step.aim.harmful or step.axis is PowerAxis.MIGHT) and bodies:
        gap, toughest = _body(state, actor, bodies)
        if gap >= odds_mod.RULED_OUT_AT:
            ceiling = MeansVerdict.CLEARLY_NOT
        elif gap >= odds_mod.LONG_SHOT_AT:
            ceiling = MeansVerdict.CLOSE_CALL
        else:
            ceiling = MeansVerdict.CLEARLY_ENOUGH
    if hit is not None and hit.overwhelming:
        # Code follows the force through; the interpret step's word on the means doesn't count.
        verdict = ceiling or MeansVerdict.CLEARLY_ENOUGH
        long_shot = False
    else:
        verdict = means if ceiling is None else min(means, ceiling, key=_MEANS_ORDER.index)

    lead = _helpless_lead(state, opposition)
    if verdict is MeansVerdict.CLEARLY_ENOUGH:
        reason = f"{lead}: no contest." if lead else NOTHING_IN_THE_WAY
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
    if verdict is MeansVerdict.CLEARLY_NOT:
        if takes_it is not None:
            why = _takes_it(state, takes_it).rstrip(".")
        elif ceiling is MeansVerdict.CLEARLY_NOT and toughest is not None:
            why = _beyond_harm(state, toughest)
        else:
            why = "; ".join(h for h in facts.hindrances if h.strip()) or "The means aren't enough"
            why = cap(why)
        reason = f"{lead}, but {why[0].lower()}{why[1:]}." if lead else f"{why}."
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)

    difficulty = ctx.settings.difficulty
    weighed = capability.weigh(
        state, actor, step, drawn, rivals=[], axis=_axis(step), measured=False
    )
    # A2. A blow that lands on someone who can't respond does harm either way; the close call is
    # only how much. Anything else can still simply fail.
    harm_lands = step.aim.harmful and bool(opposition.targets)
    allowed = odds_mod.HARM_DONE if harm_lands else odds_mod.ALL_RESULTS
    proposed = OutcomeClass.LONG_SHOT if long_shot else OutcomeClass.CONTESTED
    may_be_certain = ceiling in (None, MeansVerdict.CLEARLY_ENOUGH)
    outcome_class, base = _from_challenge(step, weighed, proposed, may_be_certain=may_be_certain)
    if outcome_class is OutcomeClass.CERTAIN:
        sure = ", ".join(filter(None, [_detail(step, weighed, state, actor), "no real doubt"]))
        reason = f"{lead}: {sure}." if lead else f"{cap(sure)}."
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
    if outcome_class is OutcomeClass.LONG_SHOT:
        band = odds_mod.LONG_SHOT_BAND
    elif harm_lands or step.facts.challenge is None:
        band = odds_mod.CLOSE_CALL_BAND
    else:
        band = odds_mod.CONTESTED_BAND  # a judged task, weighed in full
    weighed = weighed.with_misses(misses)
    odds = odds_mod.settle(base, weighed.shift + weighed.luck, band, difficulty)
    roll = odds_mod.roll(
        rng.child("outcome"), odds, label=step.text, allowed=allowed, difficulty=difficulty
    )
    if outcome_class is OutcomeClass.LONG_SHOT:
        close = f"a long shot, {roll.odds_label}"
    elif harm_lands:
        close = f"a close call, {roll.odds_label} it goes all the way"
    elif step.facts.challenge is not None:
        close = roll.odds_label
    else:
        close = f"a close call, {roll.odds_label}"
    detail = _detail(step, weighed, state, actor)
    if detail:
        close = f"{detail}, {close}"
    reason = f"{lead}, but it's {close}." if lead else f"{cap(close)}."
    return Settled(outcome_class, roll.result, reason, roll)


# G15: words that name an inner state, so an opposition said as "his temper", "Lin's own pride" or
# "fear and doubt" is only the actor's own nature. Anything else in the words, such as a storm or
# someone else's men, means something more pushes back.
_INNER_WORDS = stems(
    """temper temperament nature pride fear fears anger rage fury nerve nerves doubt doubts
    shame guilt conscience instinct instincts impulse impulses urge urges craving cravings desire
    desires greed cowardice hatred grief panic reluctance hesitation emotion emotions feeling
    feelings heart vanity jealousy envy lust despair dread terror"""
)
_INNER_FILLER = stems("only")


def _inner(state: WorldState, actor: Character, step: IntentStep, opposition: _Opposition) -> bool:
    """G15. Whether only the actor's own temperament, fear or pride stands in the way: no harm
    aimed at anyone, nobody else and no faction pushing back, means that aren't clearly short of
    it, and the interpret step said so, named the actor as the opposition, or described it in
    words that name only an inner state besides the actor's own name. Words that name anything
    else, such as a storm, outweigh the flag: the interpret step proposes, code decides."""
    if step.aim.harmful or opposition.characters:
        return False
    facts = step.facts
    if facts.means is MeansVerdict.CLEARLY_NOT:
        return False
    if any(i in state.factions for i in facts.opposition_ids):
        return False
    words = _inner_words(actor, facts.opposition)
    if words is None:
        return False
    return bool(words) or facts.inner or actor.id in facts.opposition_ids


def _inner_words(actor: Character, opposition: str) -> frozenset[str] | None:
    """G15. The inner-state words an opposition is said in, besides the actor's own name (empty
    when it says nothing else), or None when it names anything more than an inner state."""
    names = stems(" ".join([actor.name, *actor.aliases]))
    words = stems(opposition) - names - _INNER_FILLER
    if words and not words <= _INNER_WORDS:
        return None
    return words


def _own_choice(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    *,
    misses: int = 0,
) -> Settled:
    """G15. Only the actor's own nature stands in the way, so the step happens: the player chose
    it, and temperament never takes the choice away. A step the interpret step judged easy, or
    one the actor's sheet makes sure, is certain. Otherwise it is rolled, with a flaw such as a
    hot temper making it harder, and the roll only decides how hard it was: done cleanly, or done
    with the strain showing. It never fails, and the hardest it gets is a long shot, never ruled
    out."""
    facts = step.facts
    player = actor.id == state.player_id
    what = facts.opposition.strip() or f"{possessive(state, actor.id)} own nature"
    yours = "yours" if player else possessive(state, actor.id)
    who, does = name(state, actor.id), "do" if player else "does"
    lead = f"{cap(what)} pushes back, but the choice is {yours}"
    proposed = facts.proposed_class
    easy = proposed is OutcomeClass.CERTAIN or (
        proposed is None and facts.means is MeansVerdict.CLEARLY_ENOUGH
    )
    weighed = capability.weigh(state, actor, step, drawn, rivals=[], axis=step.axis, measured=False)
    hard = proposed in (OutcomeClass.LONG_SHOT, OutcomeClass.RULED_OUT)
    judged = OutcomeClass.LONG_SHOT if hard else OutcomeClass.CONTESTED
    outcome_class, base = _from_challenge(step, weighed, judged, may_be_certain=True)
    if easy or outcome_class is OutcomeClass.CERTAIN:
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, f"{lead}: {who} {does} it.")
    hard = outcome_class is OutcomeClass.LONG_SHOT
    difficulty = ctx.settings.difficulty
    weighed = weighed.with_misses(misses)
    odds = odds_mod.settle(
        base, weighed.shift + weighed.luck, odds_mod.BANDS[outcome_class], difficulty
    )
    roll = odds_mod.roll(
        rng.child("outcome"),
        odds,
        label=step.text,
        allowed=odds_mod.OWN_CHOICE,
        difficulty=difficulty,
    )
    words = f"very hard, {roll.odds_label}" if hard else roll.odds_label
    done = f"{who} {does} it"
    if roll.result is not StepResult.SUCCESS:
        done = f"{done}, but the strain shows"
    return Settled(outcome_class, roll.result, f"{lead} ({words}): {done}.", roll)


def _with_chain(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    *,
    misses: int = 0,
):
    """A9. A plan that goes around the strength instead of meeting it. Whoever can see it coming
    may answer first, so the setup is rolled against anyone who can respond, at the challenge the
    interpret step judged and with what the actor brings to it (`engine.resolve.capability`);
    then the chain settles link by link against everyone who can still answer."""
    difficulty = ctx.settings.difficulty
    setup: RollRecord | None = None
    setup_class = OutcomeClass.CERTAIN
    if opposition.can_push_back:
        proposed = step.facts.proposed_class
        who = (
            names(state, opposition.responsive)
            if opposition.responsive
            else step.facts.opposition.strip() or "they"
        )
        if proposed is OutcomeClass.RULED_OUT:
            reason = f"{cap(who)} will see it coming and answer first."
            return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason), None
        judged = (
            OutcomeClass.LONG_SHOT if proposed is OutcomeClass.LONG_SHOT else OutcomeClass.CONTESTED
        )
        weighed = capability.weigh(
            state,
            actor,
            step,
            drawn,
            rivals=opposition.responsive,
            axis=step.axis,
            measured=False,
        )
        # Someone or something can answer, so the setup is never certain; the weighed odds
        # decide whether it's a long shot, as for any step nobody is measured against.
        setup_class, base = _from_challenge(step, weighed, judged, may_be_certain=False)
        weighed = weighed.with_misses(misses)
        odds = odds_mod.settle(
            base, weighed.shift + weighed.luck, odds_mod.BANDS[setup_class], difficulty
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
    if not outcome.holds:
        # The link it broke on decides: ruled out with no roll, or the roll that failed (A2, A3).
        return Settled(
            outcome.outcome_class, StepResult.FAILURE, outcome.reason, outcome.roll
        ), outcome
    # Every link held: the step is as hard as the hardest roll it took, which is its roll.
    outcome_class, roll = setup_class, setup
    if _HARDER.index(outcome.outcome_class) > _HARDER.index(setup_class):
        outcome_class, roll = outcome.outcome_class, outcome.roll
    return Settled(outcome_class, StepResult.SUCCESS, outcome.reason, roll), outcome


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


def _takes_it(state: WorldState, body: Character) -> str:
    return f"{cap(name(state, body.id))} {is_are(state, body.id)} tough enough to take it unhurt."


def _means_from_class(proposed: OutcomeClass | None) -> MeansVerdict:
    if proposed is OutcomeClass.RULED_OUT:
        return MeansVerdict.CLEARLY_NOT
    if proposed in (OutcomeClass.CONTESTED, OutcomeClass.LONG_SHOT):
        return MeansVerdict.CLOSE_CALL
    return MeansVerdict.CLEARLY_ENOUGH


def _known_might(state: WorldState, character: Character) -> int:
    """W5, A8: the might the world can measure them by, before their condition: the rung they
    stand on (G18), hidden strength as what it shows (G20), and any power it knows of (a
    light-speed time stop once known)."""
    shown = sensing.apparent_tier(state, character, base_tier(state, character, PowerAxis.MIGHT))
    return max(shown, stop.might_with_powers(state, character))


def _backed_by_force(state: WorldState, actor: Character, step: IntentStep) -> bool:
    """Whether a threat rests on what the actor can do rather than on who they are: an
    intimidation from someone whose known might is above their standing (W5)."""
    if not capability.intimidates(step):
        return False
    return _known_might(state, actor) > base_tier(state, actor, PowerAxis.INFLUENCE)


def _menacing(state: WorldState, actor: Character, measure: Scale) -> tuple[Standing, bool]:
    """A threat's weight: the actor's might as the world knows it, after their condition (A8),
    and whether a power the world knows of lifts it above the rung they stand on. A threat
    frightens by what others believe, so hidden strength counts as what it shows (G20). Where
    the known might isn't the rung's, the rung isn't named."""
    found = standing(state, actor, PowerAxis.MIGHT, measure)
    penalty = max(0.0, base_tier(state, actor, PowerAxis.MIGHT) - found.tier)
    known = max(0.0, _known_might(state, actor) - penalty)
    if known == found.tier:
        return found, False
    return Standing(character=actor, tier=known, rung=None, notes=found.notes), known > found.tier


def _withstanding(state: WorldState, target: Character, measure: Scale) -> Standing:
    """What a target meets a threat of force with: their own might, or their standing and the
    people behind it, whichever is higher (A8)."""
    might = standing(state, target, PowerAxis.MIGHT, measure)
    station = standing(
        state, target, PowerAxis.INFLUENCE, scale(state, PowerAxis.INFLUENCE, target)
    )
    return might if might.tier >= station.tier else station


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
        everyone = names(state, [p for p, _ in opposition.helpless])
        return f"{cap(everyone)} can't respond ({why})"
    if opposition.unmeasured_frozen:
        return "Nothing in the way can respond"
    return ""
