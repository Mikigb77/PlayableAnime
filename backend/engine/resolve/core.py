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
4. **Whether anything is open** (A2). Only a named fact refuses a step: a rule of the world, a
   missing means, a ruling, a force a body takes unhurt (W10a), or what the world's ladder says a
   rung shrugs off (G18), which stops harm from that far below by ordinary means and nothing
   else. A gap in power never refuses by itself. Whoever or whatever stands two levels or more
   under what the actor throws can't push back, with no throw. When nothing can push back, only
   the means count: clearly enough is done, clearly not names what is missing, and a close call
   is thrown for. A move they know, with nothing resisting, is never thrown for (A4). A plan
   that goes around the strength is settled link by link instead (A9).
5. **The throw** (A3, A5), for every step still open. The actor throws what their sheet gives
   them for it (a technique by its mastery, else the skill, else the attributes: G14) against a
   number code builds (`engine.resolve.capability`, `engine.resolve.throw`): ten for each level
   of whoever answers, or of the thing in the way, less what the story's difficulty takes off;
   ten or twenty more for each rung they stand above the actor where the step meets their power
   head-on (G18); and steps of 5 for numbers, wounds, exhaustion, hindrances, gifts and flaws
   (A8). Each real advantage whose source code finds to hold adds a green die, two at most. A
   blow that lands on someone who can't respond does harm either way, and the throw is only for
   how much. What only the actor's own nature stands in the way of is done, cleanly or with the
   strain showing (G15). A throw over the top brings one fixed extra effect, which code picks.
   A thing keeps the level it was first judged at, on its place.

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

from engine import levels
from engine import talent as talent_mod
from engine.context import Difficulty, TurnContext
from engine.contracts.delta import (
    AttitudeShift,
    CharacterChange,
    ItemChange,
    PlaceChange,
    PowerChange,
    PowerSetting,
    StateDelta,
)
from engine.contracts.intent import (
    ActionKind,
    Aim,
    Challenge,
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
    WooingSoFar,
)
from engine.resolve import bouts, capability, exchanges, romance
from engine.resolve import perils as perils_mod
from engine.resolve import strangers as strangers_mod
from engine.resolve import throw as dice
from engine.resolve.chain import settle_chain
from engine.resolve.checks import Drawn, Settled, beat_check, sheet_check, world_check
from engine.resolve.durations import Timing, lived_estimate, step_timing, until_time
from engine.resolve.effects import aim_effects, power_costs, proposed_deed
from engine.resolve.power import (
    base_tier,
    claims_frozen_in_time,
    helpless_name,
    helpless_state,
    rung,
    rung_levels,
    rung_words,
    rungs_above,
    scale,
    shrugs_off,
    true_tier,
)
from engine.resolve.powers import claims as claims_mod
from engine.resolve.powers import growth, sensing
from engine.resolve.powers import talents as talents_mod
from engine.resolve.powers import theories as theories_mod
from engine.resolve.powers import time_stop as stop
from engine.resolve.words import cap, is_are, name, names, possessive, stems
from engine.rng import SeededRng
from engine.state.cast import Character, CharacterStatus, Judged, PlaceStatus
from engine.state.records import Mark, RollRecord, StepResult, Trace, TraceKind, Visibility
from engine.state.scene import Bout, EncounterKind, Terms
from engine.state.sheet import (
    Health,
    HitMode,
    Mastery,
    Power,
    PowerAxis,
    Ruling,
    RulingSource,
    TalentBridge,
    TalentRuling,
    Technique,
    TimeEffect,
)
from engine.state.world import ActiveTimeEffect, WorldState
from engine.timekeeping import bound_duration, effect_over, in_time_stop
from engine.world import journeys
from engine.world.norms import Nature, assess_severity, nature
from engine.world.tuning import RUMOR_MIN_SEVERITY

STANDING_DURATIONS_S = {StandingAction.WAIT: 60, StandingAction.OBSERVE: 30}
NOTHING_IN_THE_WAY = "Nothing stands in the way."
FROZEN = "frozen in stopped time"

_MEANS_ORDER = [MeansVerdict.CLEARLY_NOT, MeansVerdict.CLOSE_CALL, MeansVerdict.CLEARLY_ENOUGH]
_HARDER = [OutcomeClass.CERTAIN, OutcomeClass.CONTESTED, OutcomeClass.LONG_SHOT]
_CHALLENGE_AT = {level: challenge for challenge, level in levels.CHALLENGE_LEVEL.items()}
# A2. With no verdict on the means, a task judged this hard or harder is a close call.
_OPEN_AT = levels.CHALLENGE_LEVEL[Challenge.MODERATE]
# N6. The verbs of a step that is itself a defence, whose own throw then is the defence.
_DEFENCE_STEMS = stems("parry block dodge evade defend deflect sidestep duck guard ward fend")
# A3. What an over-the-top throw at a task takes off its time, and the kinds of step it shortens.
_QUICKER = 2
_SHORTENED = (ActionKind.TASK, ActionKind.WORK, ActionKind.MOVE)
# A3, W4. One notch of trust or fear, which an over-the-top throw of words moves a listener by.
ATTITUDE_NOTCH = 10
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
    # A3: the steps of this plan that came off cleanly so far, counted from 0, which an
    # advantage may rest on, and the words of the scene the player is answering.
    passed: set[int] = field(default_factory=set)
    scene: str = ""
    # A3: whom the actor has an opening on, so their next step against them throws a green die.
    # `engine.pipeline.play_out` keeps it from the steps that played, for the next turn.
    openings: list[str] = field(default_factory=list)
    moved: list[ItemChange] = field(default_factory=list)  # C10: what this plan moved so far
    learned: list[Technique] = field(default_factory=list)  # A4: moves this plan made theirs
    moves: growth.Moves = field(default_factory=growth.Moves)  # A4: their mastery as it grows
    # G19: what this turn has counted for toward each ladder's rank, at its best step so far.
    rank_counted: dict[str, int] = field(default_factory=dict)
    # A4: what this plan ruled about the actor's talents, and the bridges it tried, which the
    # sheet doesn't hold until the plan is played out.
    talent_rulings: list[TalentRuling] = field(default_factory=list)
    bridges: list[TalentBridge] = field(default_factory=list)
    # W10: where the actor is as this step starts, had the trips before it arrived.
    place_id: str | None = None
    # W1: the bout this plan is fighting under terms both sides agreed to, and whether a fight
    # is on in earnest (someone was harmed outside any terms, or its terms were broken), which
    # no step can make a bout afterwards.
    bout: Bout | None = None
    open_fight: bool = False
    # W17: where the romances this plan moved stand, by the other person's id, which the
    # state doesn't hold until the plan is played out.
    hearts: dict[str, romance.Heart] = field(default_factory=dict)


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
    state: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng, *, scene: str = ""
) -> Resolution:
    """B5 step 3. Turn the interpret step's proposal into the engine's decision. The state is read
    only. Throws come from `rng.child("resolve", "step", i)` and streams under it, so a step
    throws the same dice however the steps around it went. `scene` is the text of the scene the
    player is answering, which an advantage may quote (A3).

    The graph passes the player's own intent with `actor_id` unset or the player's id; an NPC's
    intent names the NPC. An actor id the state doesn't hold falls back to the player.
    """
    actor_id = intent.actor_id if intent.actor_id in state.characters else state.player_id
    actor = state.characters[actor_id]
    frame = _frame(state, actor)
    frame.scene = scene
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
        kind=kind,
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
        drawn=Drawn(),
        difficulty=ctx.settings.difficulty,
        rng=rng.child("resolve", "step", 0, "peril"),
        bout=frame.bout,
    )
    under_terms = any(p.terms is not None for p in struck.perils)
    return standing.model_copy(
        update={
            "perils": struck.perils,
            "effects": struck.effects,
            "deeds": struck.deeds,
            "opening_ids": struck.openings,
            "bout": frame.bout if under_terms else None,  # W1: the blow was one of the bout's
            "broke_terms": struck.broke_terms,
        }
    )


def _frame(state: WorldState, actor: Character) -> _Frame:
    """The plan starts where the state is: in a stop or a haste of the actor's own, or not."""
    lived = actor.personal_s(state.world_s)
    frame = _Frame(
        frozen=in_time_stop(state, actor.id),
        stop_left_s=_stop_left(state, actor),
        personal_s=lived,
        world_s=state.world_s,
        openings=[
            i
            for i in (state.openings if actor.id == state.player_id else [])
            if i in state.characters and state.characters[i].alive
        ],
        place_id=journeys.start_of(state, actor),
    )
    encounter = state.scene.encounter
    if encounter is not None:
        frame.bout = encounter.bout
        frame.open_fight = encounter.in_earnest and encounter.bout is None
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
    began_s = frame.world_s
    actor = talents_mod.with_rulings(actor, frame.talent_rulings, frame.bridges)
    # W1. A blow of a bout both sides agreed to does at most what its terms accept.
    stood = (frame.bout, frame.open_fight)  # the bout as it stood before this step
    step, bout, broke_terms = _under_terms(state, actor, step, frame)
    terms = bout.terms if bout is not None else None
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
    reached = attempted  # whether the step got as far as what it draws on
    if settled is None:
        found = beat_check(state, actor, step, frame.canon, drawn, ctx, rng)
        beats = found.checks
        frame.canon.extend(found.canon)
        reached = found.settled is None  # a reach that came up empty stops the step there (R2)
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
    # W10. Where the step takes them. The map times a trip: its routes say how long the way is,
    # whatever was proposed, and only something of the actor's own that the step uses carries
    # them there sooner, in the time proposed for it.
    trip = None if gone else journeys.heading(state, actor, step, frame.place_id)
    going = step.kind in journeys.GOING  # the step is the trip itself, not something done there
    own_way = bool(drawn.powers or drawn.techniques or drawn.items or drawn.moves)
    route_s = trip.route_s if trip is not None else None
    if route_s is not None and own_way:
        sooner = step.proposed_duration_s
        if frozen and step.proposed_personal_s is not None:
            sooner = step.proposed_personal_s  # in a stop the way is lived, not on the clock
        route_s = max(1, min(route_s, sooner))
    # A step that outlasts the stop finishes once time runs again, so those it acts on can
    # answer by then (W10a). A trip is as long as its way, whatever was proposed for it.
    lived_s = lived_estimate(step)
    if route_s is not None:
        lived_s = route_s if going else max(lived_s, route_s)
    outlasts = frozen and stop_left is not None and lived_s > stop_left
    frozen_now = frozen and not outlasts
    if frozen and holding is not None:
        step = _in_the_stop(step)

    # A4, A9. The first time they set out to learn or use a thing, the engine rules once on
    # how their talents stand to it, and this very step already goes at that pace.
    ruled: list[TalentRuling] = []
    ruled_words: list[str] = []
    if settled is None:
        at_stake = talents_mod.things(state, actor, step, drawn, frame.learned)
        ruled, ruled_words = talents_mod.rule(state, actor, step, at_stake)
        actor = talents_mod.with_rulings(actor, ruled, [])

    growing = showing = False
    breaking = False  # G19: an attempt at the peak of a rank, thrown for
    practising: Technique | None = None  # a technique they know that this step practises
    bridging: talents_mod.Bridging | None = None  # A4: a bridge this step sets out to build
    if settled is None and step.training is not None:
        growing = True
        settled = growth.check(state, actor, step, frame.canon)
        practice = None
        if settled is None:
            practice = growth.already_known(state, actor, step, frame.learned)
        if practice is not None:
            # A4. Practising what they already know happens, and teaches nothing new: it counts
            # toward the technique's mastery.
            (settled, practising), growing = practice, False
        elif settled is None and step.training.kind is GrowthKind.BREAKTHROUGH:
            # G19. An attempt is thrown for once the rank is full. Before that, and for work
            # that sets out to try nothing, the step is training toward the rung.
            rank = growth.rank_for(state, actor, step, frame.practice)
            breaking = step.training.attempt and rank is not None and rank.full
            if breaking:
                settled = growth.breakthrough(
                    state,
                    actor,
                    step,
                    rng,
                    ctx.settings.difficulty,
                    greens=_greens(state, actor, step, drawn, frame, []),
                    canon=frame.canon,
                )
            else:
                settled = Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, "")
        elif settled is None:
            settled = Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, "")
        else:
            growing = settled.outcome_class is not OutcomeClass.RULED_OUT
    elif settled is None and step.show_strength is not None:
        settled = sensing.check(state, actor, step)
        showing = settled is None
        settled = settled or Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, "")
    elif settled is None and step.bridge is not None:
        # A4. Work that connects a talent to something outside it is thrown for, against the
        # reach and nothing else.
        settled, bridging = talents_mod.bridge_check(state, actor, step)
        if bridging is not None:
            step = bridging.step

    wooing: romance.Wooing | None = None
    courted: WooingSoFar | None = None
    affair: ProposedDeed | None = None
    if settled is None and bridging is None:
        # W17. A move in a romance is ruled on by the bond on record and the other's own
        # heart first (A2). What they leave open is thrown for like any step of words.
        wooing = romance.read(
            state,
            actor,
            step,
            ctx.settings.language,
            frame.hearts,
            frame.place_id,
            trip,
            held=frozen or state.scene.encounter is not None,
        )
        if wooing is not None:
            step, settled = wooing.step, wooing.settled
            if wooing.goes is not None:
                # W10. They are elsewhere and not far, so the step goes to them first.
                trip, route_s = wooing.goes, wooing.goes.route_s

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
    told_hand = ""  # R4: what the step is done with, and how well they have it
    defending = False  # N6: the step is itself the defence, so its own throw is
    kept: PlaceChange | None = None  # A3: the level of a thing this step judged, for its place
    if settled is None:
        assert opposition is not None
        own_choice = not step.chain and _inner(state, actor, step, opposition)
        if not own_choice and bridging is None:
            step, kept = _judged(state, actor, step, opposition)
        brought = _hand(state, actor, step, drawn, frame)
        told_hand = brought.told
        if step.chain:
            settled, outcome = _with_chain(
                state, actor, step, opposition, drawn, ctx, rng, frame, brought
            )
            if outcome is not None:
                chain, stopped_at_link, chain_s = outcome.links, outcome.stopped_at, outcome.takes_s
        elif own_choice:
            settled = _own_choice(state, actor, step, opposition, drawn, ctx, rng, frame, brought)
        elif opposition.can_push_back:
            defending = _defending(state, actor, step, opposition, frame)
            settled = _contested(
                state,
                actor,
                step,
                opposition,
                drawn,
                ctx,
                rng,
                frame,
                brought,
                hit,
                defending=defending,
            )
        else:
            settled = _unopposed(
                state, actor, step, opposition, drawn, ctx, rng, frame, brought, hit
            )

    if broke_terms and opposition is None:
        # W1. A blow that met no one, such as one stopped before it was tried because the
        # record holds no such blade, broke nothing: the bout stands as it stood, and whoever
        # answers the step answers inside it.
        frame.bout, frame.open_fight = stood
        bout, broke_terms = frame.bout, False

    # A3. Whether the actor's own dice decided the step, and how they fell: the world's die
    # and a draw of how long something took test nothing of theirs.
    roll = settled.roll
    thrown = roll.throw if roll is not None else None
    by_hand = thrown is not None and not thrown.of_the_world
    over_the_top = by_hand and thrown.mark is Mark.OVER_THE_TOP
    # W10, A3. An uncertain duration on a thrown step is drawn from a stream of the throw's own
    # seed, so the one recorded seed replays both the dice and the time; otherwise it has its
    # own.
    duration_rng = rng.child("duration")
    if roll is not None:
        duration_rng = SeededRng(roll.seed).child("duration")
    timed_step = step
    if breaking:
        timed_step = step.model_copy(update={"duration_uncertain": True})  # G19
    tempo, tempo_left = (None, None) if frozen else _rate(new_tempo, frame)
    # W10. A trip that is made takes what its way takes: all of a step that is the going
    # itself, and the least of one that goes somewhere to do something there.
    # A move in a romance that went somewhere got there whatever came of it (W17): the one it
    # went to turned it down there, or wasn't there to be found.
    made = trip is not None and (
        wooing is not None
        or (
            settled.outcome_class is not OutcomeClass.RULED_OUT
            and settled.result is not StepResult.FAILURE
        )
    )
    way_s = route_s if made else None
    fixed_s = way_s if going else None
    timing = None
    if not frozen and tempo is None and settled.outcome_class is not OutcomeClass.RULED_OUT:
        # W10. "Until nightfall" is counted on the world's clock from where this step starts.
        # In a stop or a haste, and for a step that never got going, the proposal stands.
        timing = until_time(step, state.bible.calendar, frame.world_s)
    counted_to = timing is not None
    # A trip the player timed ("until dusk", "for two hours") stops when that time is up, on
    # the way, unless the way is shorter: then they are there before it. Where no route says
    # how long the way is, nobody can tell whether the time was enough, and the scene says
    # where they got to.
    set_s = timing.duration_s if timing is not None else None
    if set_s is None and made and going and step.timed and not frozen and tempo is None:
        set_s = bound_duration(step.kind, step.proposed_duration_s)
    short = trip is not None and going and set_s is not None
    short = short and (fixed_s is None or set_s < fixed_s)
    if counted_to and fixed_s is not None and not short:
        timing = Timing(duration_s=fixed_s, personal_s=None)
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
            fixed_s=set_s if short else fixed_s,
        )
    duration = timing.duration_s
    personal = timing.personal_s
    rolled_s = timing.rolled_s
    # A3. A task on a thing thrown over the top takes half the time. Time someone holds, a
    # stop, a haste or a wait "until nightfall", is not the task's to shorten, and neither is
    # the map's time for a trip or the time the player set for one.
    quicker = (
        over_the_top
        and step.kind in _SHORTENED
        and not (growing or showing or frozen or counted_to or short or fixed_s is not None)
        and tempo is None
        and not (opposition is not None and opposition.responsive)
    )
    if quicker:
        duration = max(1, duration // _QUICKER)
        rolled_s = max(1, rolled_s // _QUICKER) if rolled_s is not None else None
    if way_s is not None and not going and not frozen and tempo is None and duration < way_s:
        # Sleeping at the inn in the village takes the walk there at the least.
        duration = way_s
        rolled_s = way_s if rolled_s is not None else None
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
    if rolled_s is not None:
        if roll is not None:
            roll = roll.model_copy(update={"duration_s": rolled_s})
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
                duration_s=rolled_s,
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
        effects = aim_effects(step, settled.result, targets, pulled=terms is Terms.NO_HARM)
    if met is not None:
        if actor.id == state.player_id:
            # Not in the scene's record yet, but the player saw what they did to them.
            effects = _known_to_player(effects, {p.id for p in met.people})
        effects = _merge(met.effects, effects)  # they're real before anything happens to them
    effects = _merge(effects, extra)
    if kept is not None and happened:
        effects = _merge(effects, StateDelta(places=[kept]))
    if ruled and happened:
        # A4. Ruled once and kept: the steps that follow, and every later turn, go by it.
        frame.talent_rulings.extend(ruled)
        change = CharacterChange(id=actor.id, talent_rulings=ruled)
        effects = _merge(effects, StateDelta(characters=[change]))
        after.extend(ruled_words)
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
        start = _start(actor, step, drawn, growth.talent_key(state, actor, step))
        why, grown, deed = _grow(state, actor, step, settled, frame, personal, duration, start)
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
    if wooing is not None and frame.gone is None:
        # W17. What the move did to the romance: their heart, and the stage it earned.
        said, moved_on, frame.hearts[wooing.other.id] = romance.settle(
            actor, wooing, settled, over_the_top=over_the_top, now_s=began_s, lasted_s=duration
        )
        after.extend(said)
        effects = _merge(effects, moved_on)
        # One an event cuts short keeps what the time it ran earned (E7).
        courted = romance.so_far(
            wooing, settled, [_sentence(line) for line in said], over_the_top=over_the_top
        )
        # A move that wrongs a partner of either is a deed of its own (W1).
        affair = romance.deed(
            state,
            actor,
            wooing,
            settled,
            frame.hearts[wooing.other.id],
            {k: v for k, v in frame.hearts.items() if k != wooing.other.id},
            in_stopped_time=frozen_now,
        )
    if chain:
        places, deed = _chain_places(state, actor, step, chain)
        effects = _merge(effects, places)
        if deed is not None:
            deeds.append(deed)
    clean = happened and settled.result is StepResult.SUCCESS and frame.gone is None
    if bridging is not None and happened:
        # A4. Held or not, the bridge is kept, so the same ground is never tried twice.
        why, built, change = talents_mod.bridge_made(state, actor, bridging, settled.result)
        frame.bridges.append(built)
        after.append(why)
        effects = _merge(effects, change)
    if drawn.moves and clean and not (growing or showing):
        # A4, G25. A move of their own that came off cleanly is a technique of theirs now,
        # starting where their skill at it puts a new move.
        start = _start(actor, step, drawn)
        why, learned, change = growth.proven(state, actor, step, drawn.moves, frame.learned, start)
        if why:
            after.append(why)
            effects = _merge(effects, change)
            _theirs_now(frame, learned)
    if practising is not None:
        # A4. An hour of practice counts as a use, more with a teacher.
        lived = personal if personal is not None else duration
        why, change, frame.training = growth.practised(
            state, actor, step, practising, lived, frame.moves
        )
        after.append(why)
        effects = _merge(effects, change)
    elif reached and happened and frame.gone is None and not (growing or showing):
        # A4. Using a move is how it grows: once where nothing resisted, twice where their own
        # throw decided the step, and three times for an insight, which the move's violet die
        # shows at 18 or more and any throw over the top brings.
        techniques = growth.used_in(actor, drawn.techniques, drawn.moves, frame.learned)
        count = levels.PLAIN_USE
        if by_hand:
            insight = thrown.insight or over_the_top
            count = levels.INSIGHT_USE if insight else levels.RESISTED_USE
            if insight and techniques:
                after.append(f"An insight into {techniques[0].name}: this use counts as three")
        why, change = growth.used(state, actor, step, techniques, count, frame.moves)
        after.append(why)
        effects = _merge(effects, change)
    if reached and happened and frame.gone is None and not (growing or showing or practising):
        # G19. What the step did with what a ladder measures fills the rank they stand on.
        why, change = growth.rank_used(
            state,
            actor,
            step,
            axis=_axis(step),
            own=bool(drawn.powers or drawn.techniques or drawn.moves),
            by_hand=by_hand,
            insight=by_hand and (thrown.insight or over_the_top),
            counted=frame.rank_counted,
            efforts=frame.practice,
        )
        after.append(why)
        effects = _merge(effects, change)
    # A3. The one fixed extra effect of a throw over the top.
    told_extra = ""
    won: list[str] = []
    if over_the_top and happened and frame.gone is None and not (growing or showing):
        told_extra, more, won = _over_the_top(state, actor, step, opposition, effects, quicker)
        effects = _merge(effects, more)
    reason = " ".join([reason, *(_sentence(a) for a in after if a)]).strip()
    if clean:
        frame.passed.add(index)

    lured = False  # W1: someone fighting them went beyond the terms of their bout
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
            drawn=drawn,
            defence=settled.roll if defending and by_hand else None,
            difficulty=ctx.settings.difficulty,
            rng=rng.child("peril"),
            bout=frame.bout,
        )
        if struck.broke_terms:
            # W1. Someone fighting them went beyond the terms: the bout is over.
            lured = True
            frame.bout, frame.open_fight = None, True
        elif not step.aim.harmful and any(p.terms is not None for p in struck.perils):
            bout = frame.bout  # the step struck nobody, and its answer was a blow of the bout
        won = [*won, *(i for i in struck.openings if i not in won)]
        perils, escaped = struck.perils, struck.escaped
        frame.fighting = list(dict.fromkeys([*frame.fighting, *struck.fighting]))
        frame.out |= set(struck.escaped)
        effects = _merge(effects, struck.effects)
        deeds.extend(struck.deeds)
        if struck.dead:
            frame.gone = f"{cap(name(state, actor.id))} {is_are(state, actor.id)} dead."
    else:
        perils, escaped = [], []

    if affair is not None:
        # W17. The move is the deed, with whom it wrongs, in place of the step's plain one.
        deeds.insert(0, affair)
    elif opposition is not None:
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
            terms=terms,
            broke_terms=broke_terms,
        )
        if deed is not None and frozen_now and holding is not None:
            deed = _stopped_deed(state, actor, step, deed, holding, hit, others_hit, settled)
        if deed is not None:
            deeds.insert(0, deed)
    if any(d.victim_ids and d.terms is None for d in deeds):
        frame.open_fight = True  # W1: someone was harmed outside any terms: a fight in earnest
    real = list(met.people) if met is not None else []  # F1, W2: who this step made real
    if deeds and not frozen_now and strangers_mod.crowded(step):
        # W2. What is done before a crowd is public: everyone there saw it.
        deeds, watcher = _before_a_crowd(state, actor, deeds, frame, ctx.turn, index)
        if watcher is not None:
            person, change = watcher
            real.append(person)
            frame.met.append(person)
            effects = _merge(StateDelta(characters=[change]), effects)
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
    if bout is not None and encounter is None and opponent_ids:
        # W1. A blow of a bout is a blow of a fight, even one that aims no harm at anyone, so
        # the encounter that keeps the bout's terms begins and carries on with it.
        encounter = EncounterKind.FIGHT
    # A3. An opening is used by the next step that faces whom it is on, and those this step won
    # are held from here.
    frame.openings = [o for o in frame.openings if o not in opponent_ids] + won
    if trip is not None:
        # W10. A trip that was made and not stopped short arrives, so the next step of the plan
        # sets out from there. One the player timed over ground no route covers is left open.
        arrived: bool | None = made and frame.gone is None
        if arrived and short:
            arrived = False if fixed_s is not None else None
        trip = trip.model_copy(
            update={
                "takes_s": way_s,
                "arrived": arrived,
                "by_own_means": made and own_way,
            }
        )
        if arrived and trip.to_id is not None:
            frame.place_id = trip.to_id
            if not going or (wooing is not None and wooing.goes is not None):
                # W1, W2. What a step did where it went was done there, before whoever is there.
                deeds = [
                    d if d.place_id else d.model_copy(update={"place_id": trip.to_id})
                    for d in deeds
                ]
    resolution = StepResolution(
        index=index,
        text=step.text,
        outcome_class=settled.outcome_class,
        reason=reason,
        roll=roll,
        result=settled.result,
        costs=power_costs(used) if attempted else [],
        drew_on=drew_on,
        hand=told_hand,
        duration_s=duration,
        personal_s=personal,
        beats=beats,
        not_own=settled.not_own,
        strangers=[p.id for p in real],
        chain=chain,
        stopped_at_link=stopped_at_link,
        effects=effects,
        deeds=deeds,
        training=frame.training,
        wooing=courted,
        kind=step.kind,
        trip=trip,
        encounter=encounter,
        opponent_ids=opponent_ids,
        perils=perils,
        escaped=escaped,
        extra=told_extra,
        opening_ids=won,
        bout=None if lured else bout,
        broke_terms=broke_terms or lured,
    )
    return resolution, stakes, own_choice


def _before_a_crowd(
    state: WorldState,
    actor: Character,
    deeds: list[ProposedDeed],
    frame: _Frame,
    turn: int,
    index: int,
) -> tuple[list[ProposedDeed], tuple[Character, CharacterChange] | None]:
    """W2, W11. The deeds of a step done before a crowd, and someone of the crowd to make real.

    A deed that is news by the world's norms (`_news`) is public, unless something already
    settled who saw it: a crowd talks of a killing, not of an insult or a shove, which stay as
    seen as they would be anywhere. When one of those made public is harm to someone, outside
    any terms both sides agreed to, and nobody the record puts there but the doer and those it
    fell on is awake to see it, one of the crowd is made real, so it has a witness who can go
    to the law."""
    made = [d.visibility is None and _news(state, d) for d in deeds]
    told = [
        d.model_copy(update={"visibility": Visibility.PUBLIC}) if public else d
        for d, public in zip(deeds, made, strict=True)
    ]
    harm = [
        d
        for d, public in zip(told, made, strict=True)
        if public
        and d.terms is None
        and nature(state, d.kind, d.victim_ids, d.target_ids, d.severity) is Nature.HARM
    ]
    if not harm:
        return told, None
    apart = {actor.id}
    for deed in harm:
        apart |= {deed.actor_id or actor.id, *deed.victim_ids, *deed.target_ids}
    place_id = frame.place_id or actor.location_id or state.scene.place_id
    return told, strangers_mod.onlooker(state, place_id, apart, turn, index)


def _news(state: WorldState, deed: ProposedDeed) -> bool:
    """W2. Whether a deed is something people talk about, by the world's norms (W12): as
    serious as what starts a rumor wherever it is seen."""
    severity = assess_severity(state, deed.kind, deed.severity, deed.victim_ids, deed.target_ids)
    return severity >= RUMOR_MIN_SEVERITY


def _under_terms(
    state: WorldState, actor: Character, step: IntentStep, frame: _Frame
) -> tuple[IntentStep, Bout | None, bool]:
    """W1 (`engine.resolve.bouts`). The step as the terms of its bout hold it, that bout, and
    whether it went beyond them. The interpret step proposes terms; code decides whether they
    stand and keeps them for the bout.

    A blow at those the actor is in a bout with comes under its terms whether or not the step
    names them, and they only ever get milder. A blow is any step that fights them
    (`bouts.is_blow`), whether it aims at them or names no target and they stand in its way
    (`bouts.against`). It is held to the worst the terms accept, unless the interpret step says
    the actor means to go beyond them, by its aim or failing one by its verb (`bouts.meant`):
    then it is an attack as proposed, and the bout is over. A step that fights someone
    with no bout on starts one when it proposes terms and everyone in it can agree to them, and
    one that proposes terms with someone new while a bout is on brings them into it. A fight in
    earnest, in which someone was harmed outside any terms or whose terms were broken, stays
    one whatever a later step proposes.

    What is agreed here stands though the step then meets no one, as when it is stopped before
    it is tried (`engine.encounters` begins the bout with those it was agreed with), and a
    blow beyond the terms that met no one broke nothing (`_settle_step`)."""
    target_ids = bouts.against(state, actor.id, step)
    if not target_ids or not bouts.is_blow(step):
        return step, None, False
    proposed = step.facts.terms
    if frame.bout is None:
        people = [actor, *(state.characters[i] for i in target_ids)]
        agreed = proposed is not None and all(bouts.can_agree(state, p) for p in people)
        if frame.open_fight or not agreed:
            return step, None, False
        with_ids = [p.id for p in people if p.id != state.player_id]
        frame.bout = Bout(terms=proposed, with_ids=with_ids)
    elif not bouts.covers(state, frame.bout, actor.id, target_ids):
        joined = _joined(state, actor, frame, target_ids)
        if proposed is None or joined is None:
            # A blow at someone outside the bout is none of its own. One that is also meant to
            # go beyond the terms with someone in it ends the bout.
            beyond = step.facts.breaks_terms and not bouts.allows(
                frame.bout.terms, bouts.meant(step)
            )
            if beyond and any(i in bouts.sides(state, frame.bout) for i in target_ids):
                frame.bout, frame.open_fight = None, True
                return step, None, True
            return step, None, False
        frame.bout = joined
    terms = bouts.milder(frame.bout.terms, proposed)
    frame.bout = frame.bout.model_copy(update={"terms": terms})
    if step.facts.breaks_terms and not bouts.allows(terms, bouts.meant(step)):
        frame.bout, frame.open_fight = None, True
        return step, None, True
    aim = bouts.held(terms, step.aim)
    return (step if aim is step.aim else step.model_copy(update={"aim": aim})), frame.bout, False


def _joined(
    state: WorldState, actor: Character, frame: _Frame, target_ids: list[str]
) -> Bout | None:
    """W1. The bout with those a blow of the player character's newly names in it, as when a
    second partner steps into a sparring ring. None when one of them can't agree, or is already
    fighting the character outside the bout: an open fight with someone never becomes a bout."""
    bout = frame.bout
    if bout is None or actor.id != state.player_id:
        return None
    new = [i for i in target_ids if i not in bout.with_ids]
    encounter = state.scene.encounter
    fighting = {*frame.fighting, *(encounter.opponent_ids if encounter is not None else [])}
    for new_id in new:
        if new_id in fighting or not bouts.can_agree(state, state.characters[new_id]):
            return None
    return bout.model_copy(update={"with_ids": [*bout.with_ids, *new]})


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
        update["means"] = MeansVerdict.CLEARLY_ENOUGH
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


def _start(actor: Character, step: IntentStep, drawn: Drawn, key: str = "") -> Mastery:
    """A4. Where a new move of the actor's starts: two steps under the best skill of theirs the
    step draws on, or higher where a talent of theirs covers the thing `key` names
    (`engine.levels`, `engine.talent`)."""
    skill = capability.best_skill(actor, drawn.skills or capability.skills_for(actor, step))
    level = skill.level if skill is not None else None
    steps = talent_mod.standing(actor, key).steps if key else 0
    return levels.starting_mastery(level, steps)


def _theirs_now(frame: _Frame, learned: list[Technique]) -> None:
    """A4. Techniques a step of the plan made the actor's, which the sheet doesn't hold until
    the plan is played out: the steps that follow find them here."""
    frame.learned.extend(learned)
    frame.moves.now.update({t.id: t for t in learned})


def _grow(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    settled: Settled,
    frame: _Frame,
    personal: int | None,
    duration: int,
    start: Mastery,
) -> tuple[str, StateDelta, ProposedDeed | None]:
    """A4, G19. What a stretch of training or a breakthrough attempt did. `start` is where the
    actor's skill puts a new move (`_start`)."""
    training = step.training
    assert training is not None
    lived = personal if personal is not None else duration
    if training.kind is GrowthKind.BREAKTHROUGH and settled.roll is not None:
        # G19. An attempt at the peak: a new rung, or what is left of the rank after a miss.
        why, effects, deed = growth.breakthrough_effects(state, actor, step, settled.result)
        for change in effects.characters:
            frame.practice.update({p.key: float(p.effort_s) for p in change.practice})
        return why, effects, deed
    if training.kind is GrowthKind.BREAKTHROUGH:
        # G19. Training aimed at the rank fills it, and one cut short keeps the time it ran.
        rank = growth.rank_for(state, actor, step, frame.practice)
        assert rank is not None
        trained, rate = growth.rank_trained(state, actor, step, rank, lived)
        frame.practice[rank.key] = trained.effort_s
        frame.training = TrainingSoFar(
            key=rank.key, what=rank.rung.name, before_s=rank.effort_s, rate=rate, need_s=rank.need_s
        )
        return trained.reason, trained.effects, None
    key = growth.practice_key(step)
    so_far = frame.practice.get(key)
    if so_far is None:
        recorded = actor.sheet.practiced(key)
        so_far = float(recorded.effort_s) if recorded is not None else 0.0
    made = growth.progress(state, actor, step, lived, so_far, frame.settled, start)
    frame.practice[key] = made.effort_s
    # A technique this stretch taught is theirs for the rest of the plan.
    _theirs_now(frame, [t for c in made.effects.characters for t in c.techniques])
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
                    "bonds",
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


@dataclass(frozen=True)
class _Rival:
    """Someone a step is thrown against: their level at what answers it, and the whole rungs
    they stand above the actor where the step meets their power (G18)."""

    character: Character
    level: capability.Level
    rungs: int = 0
    per: int = 1  # the levels one rung counts for
    words: str = ""  # "two rungs above you, met head-on"

    @property
    def total(self) -> int:
        return self.level.level + self.rungs * self.per

    def number(self, difficulty: Difficulty) -> dice.Number:
        """The number they set: their level, then the rungs between them and the actor."""
        base = dice.level_number(self.level.level, self.level.why, difficulty)
        return base.raised(self.rungs * self.per, self.words)


def _hand(
    state: WorldState, actor: Character, step: IntentStep, drawn: Drawn, frame: _Frame
) -> capability.Brought:
    """G14, A4. What the actor throws for the step, with their moves as this plan has them. A
    plan that goes around the strength meets no body, so only an axis it names counts (A9)."""
    used = growth.used_in(actor, drawn.techniques, drawn.moves, frame.learned)
    new = talent_mod.technique_key(drawn.moves[0].name) if drawn.moves else ""
    return capability.hand_for(
        state,
        actor,
        step,
        drawn,
        step.axis if step.chain else _axis(step),
        techniques=[frame.moves.latest(t) for t in used],
        start=_start(actor, step, drawn, new),
    )


def _greens(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    frame: _Frame,
    facing: list[Character],
) -> list[str]:
    """A3. The reasons for a step's green dice: an opening the actor holds on someone it faces,
    then each advantage the interpret step proposed whose source code found to hold."""
    held = [c for c in facing if c.id in frame.openings]
    won = [f"the opening on {names(state, held)}"] if held else []
    return capability.advantages(
        state, actor, step, drawn, passed=frame.passed, scene=frame.scene, openings=won
    )


def _head_on(step: IntentStep) -> bool:
    """A3, G18. Whether the step meets the other side's power or goes around it. A blow always
    meets the body it lands on, so the rungs between them count for harm whatever was proposed.
    Otherwise the interpret step says, and with no word a step measured on an axis meets it."""
    if step.aim.harmful:
        return True
    if step.facts.head_on is not None:
        return step.facts.head_on
    return step.axis is not None


def _rival(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    drawn: Drawn,
    other: Character,
    axis: PowerAxis | None,
    *,
    head_on: bool,
    body: bool = False,
) -> _Rival:
    """A3, G14, G18. What `other` answers the step with, and the rungs they stand above the
    actor where the step meets their power head-on. A gap never refuses: each rung moves the
    number by what the world's ladder says a rung counts for. `body` says a blow lands on them,
    which meets their might whatever axis the step was put on."""
    level = capability.level_of(state, other, step.facts.answers_with, drawn.skills, axis)
    if not head_on or axis is None:
        return _Rival(other, level)
    known_power = False
    named: Character | None = other  # whose rung the words name beside the actor's
    if axis is PowerAxis.INFLUENCE and _backed_by_force(state, actor, step):
        # W5, A8: a threat backed by what the actor can do, as the world knows it, meets the
        # target's own force or standing, whichever stands up to it better.
        measure = scale(state, PowerAxis.MIGHT, actor, other)
        mine = max(0.0, _known_might(state, actor) - actor.sheet.condition.weakened_tiers)
        force = true_tier(state, other, PowerAxis.MIGHT)
        theirs = max(force, true_tier(state, other, PowerAxis.INFLUENCE))
        rungs = int((theirs - mine) / measure.step)
        known_power = mine > true_tier(state, actor, PowerAxis.MIGHT)
        if known_power or theirs > force:
            named = None  # measured by a power the world knows of, or against their standing
    else:
        rungs, measure = rungs_above(state, axis, actor, other)
        if body and axis is not PowerAxis.MIGHT:
            # A stab called a matter of stealth still has to get through the body.
            might, on_might = rungs_above(state, PowerAxis.MIGHT, actor, other)
            if might * rung_levels(on_might) > rungs * rung_levels(measure):
                rungs, measure = might, on_might
    if not rungs:
        return _Rival(other, level)
    words = rung_words(state, actor, named, rungs, measure, met=True)
    if known_power:
        words = f"{words}, knowing what {name(state, actor.id)} can do"
    return _Rival(other, level, rungs, rung_levels(measure), words)


def _strongest(rivals: list[_Rival]) -> tuple[_Rival, int]:
    """A8. The strongest of those who answer, and how many more stand near them."""
    strongest = max(rivals, key=lambda r: (r.total, r.character.id))
    near = sum(
        1
        for r in rivals
        if r is not strongest and strongest.total - r.total <= capability.NEAR_LEVELS
    )
    return strongest, near


def _toughest(state: WorldState, actor: Character, bodies: list[Character]) -> _Rival | None:
    """G18. The body among `bodies` that stands the most rungs above the actor's might, with its
    toughness as its level, or None when none stands a whole rung above."""
    found: _Rival | None = None
    for body in sorted(bodies, key=lambda c: c.id):
        rungs, measure = rungs_above(state, PowerAxis.MIGHT, actor, body)
        per = rung_levels(measure)
        if rungs < 1 or (found is not None and rungs * per <= found.rungs * found.per):
            continue
        level = capability.level_of(state, body, "toughness", [], None)
        words = rung_words(state, actor, body, rungs, measure)
        found = _Rival(body, level, rungs, per, words)
    return found


def _shrugged_off(
    state: WorldState, actor: Character, drawn: Drawn, bodies: list[Character]
) -> str:
    """G18, A2. The one thing a gap alone rules out, and the world's ladder states it: harm from
    that many rungs below can't get through by ordinary means. A power, a technique, a move of
    their own or a weapon with a history is no ordinary means, so it is thrown for like
    anything else. The refusal in the world's words, or nothing."""
    if drawn.powers or drawn.techniques or drawn.moves:
        return ""
    if any(item.history.strip() for item in drawn.items):
        return ""
    for body in sorted(bodies, key=lambda c: c.id):
        if body.id == actor.id:
            continue
        rungs, measure = rungs_above(state, PowerAxis.MIGHT, actor, body)
        if rungs < shrugs_off(measure):
            continue
        on = rung(state, body, PowerAxis.MIGHT)
        who = f"{name(state, body.id)} at {on[0]}" if on else name(state, body.id)
        stands = "stand" if body.id == state.player_id else "stands"
        far = rung_words(state, actor, None, rungs, measure)
        return (
            f"{cap(who)} {stands} {far}, and harm from that far below can't get through by "
            "ordinary means."
        )
    return ""


def _no_throw(brought: capability.Brought, number: dice.Number) -> str:
    """A2, A8. Why there is nothing to throw for, with the hand and what it is up against:
    "Lockpicking (master), 5 dice, against a good lock, a hard task, level 3: no throw"."""
    return f"{brought.hand.why}, against {dice.parts_told(number.parts)}: no throw"


def _defending(
    state: WorldState, actor: Character, step: IntentStep, opposition: _Opposition, frame: _Frame
) -> bool:
    """N6, A3. Whether the step is itself the player character's defence against foes in a
    fight: it harms no one, its verb is a defence (a parry, a block, a dodge), and those it
    faces can answer. Its own throw is then the defence, with no second one."""
    if actor.id != state.player_id or step.aim.harmful or not opposition.responsive:
        return False
    if not stems(step.verb) & _DEFENCE_STEMS:
        return False
    encounter = state.scene.encounter
    fighting = encounter is not None and encounter.kind is EncounterKind.FIGHT
    return fighting or step.encounter is EncounterKind.FIGHT or bool(frame.fighting)


def _contested(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    frame: _Frame,
    brought: capability.Brought,
    hit: stop.StoppedHit | None = None,
    *,
    defending: bool = False,
) -> Settled:
    """A2, A3. Someone or something can push back, so the actor throws against them. Against
    people the number is the level of the strongest at what answers the step, plus the rungs
    they stand above the actor where it meets their power head-on; against a thing or a
    faction, the level the interpret step judged. Whoever stands two levels or more under the
    hand can't push back, with no throw. A gap never refuses: only a named fact does, here a
    force a body takes unhurt (W10a) or what the world's ladder says a rung shrugs off (G18)."""
    axis = _axis(step)
    difficulty = ctx.settings.difficulty
    facts = step.facts
    if step.aim.harmful:
        bodies = [t for t in opposition.targets if t.id != actor.id]
        # W10a. A relative-speed hit is measured by its own force, not the user's arm, against
        # each body it doesn't meet head-on.
        unmet = [b for b in bodies if axis is not PowerAxis.MIGHT or b not in opposition.responsive]
        if unmet and hit is not None and hit.force_tier is not None:
            margin, body = stop.force_ceiling_margin(state, unmet, hit.force_tier)
            if margin >= stop.TAKES_IT_MARGIN:
                return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, _takes_it(state, body))
        else:
            refused = _shrugged_off(state, actor, drawn, bodies)
            if refused:
                return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, refused)
    me = name(state, actor.id)
    deadly = False
    if opposition.responsive:
        head_on = _head_on(step)
        landing = opposition.targets if step.aim.harmful else []
        strongest, near = _strongest(
            [
                _rival(state, actor, step, drawn, c, axis, head_on=head_on, body=c in landing)
                for c in opposition.responsive
            ]
        )
        them = names(state, opposition.responsive)
        against = f"{cap(them)} can answer."
        by_attribute = strongest.level.by_attribute
        # A2, G18. Someone awake beside a body doesn't make the body easier to hurt: where a
        # blow also lands on someone who can't respond and stands rungs above the actor, the
        # harder of the two is the number.
        asleep = [b for b in landing if b not in opposition.responsive and b.id != actor.id]
        tough = _toughest(state, actor, asleep)
        if tough is not None and tough.total > strongest.total:
            strongest, near, by_attribute = tough, 0, True
            whose = cap(possessive(state, tough.character.id))
            against = f"{cap(them)} can answer, and {whose} body is the question."
        number = strongest.number(difficulty)
        if not dice.open_against(brought.hand, number.level):
            reason = f"{_no_throw(brought, number)}, {them} can't push back."
            return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
        number = capability.number_for(
            state,
            actor,
            step,
            drawn,
            number,
            brought,
            axis=axis,
            rival=strongest.character,
            rival_by_attribute=by_attribute,
            extra_foes=near,
        )
        deadly = defending and facts.foes_mean is Aim.KILL
    else:
        what = facts.opposition.strip()
        challenge = facts.challenge
        if opposition.factions and capability.thing_level(challenge) < 1:
            challenge = Challenge.EASY  # A2: a faction that could still answer is never nothing
        number = capability.thing_number(what, challenge, difficulty)
        # A2. Only things in the way (a lantern, a locked door, the wind), never a faction who
        # could still answer, can leave a step with nothing to throw for.
        if not opposition.factions and not dice.open_against(brought.hand, number.level):
            reason = f"{_no_throw(brought, number)}, it can't stop {me}."
            return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
        number = capability.number_for(state, actor, step, drawn, number, brought, axis=axis)
        against = f"{cap(what or 'something')} stands in the way."
    roll = dice.throw(
        rng.child("outcome"),
        brought.hand,
        number,
        label=step.text,
        allowed=dice.ALL_RESULTS,
        difficulty=difficulty,
        greens=_greens(state, actor, step, drawn, frame, opposition.responsive),
        against=facts.up_against.strip() or against,
        deadly=deadly,
        miss_costs=facts.miss_costs.strip() or perils_mod.MISS_COSTS[Aim.KILL],
    )
    return Settled(dice.class_of(roll.odds), roll.result, f"{cap(dice.told(roll))}.", roll)


def _unopposed(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    frame: _Frame,
    brought: capability.Brought,
    hit: stop.StoppedHit | None = None,
) -> Settled:
    """A2. When nothing can push back, the only question is whether the means are enough. The
    interpret step proposes the verdict: clearly enough is done, clearly not names what is
    missing, and a close call is thrown for against the level of the thing (A3). With no
    verdict, a task judged a real effort or harder is a close call. A move they know, with
    nothing resisting, is never thrown for (A4).

    A body is a fact code reads for itself. One that stands a whole rung or more above the
    actor's might is never a sure thing: the throw is against its toughness and the rungs
    between them, and a blow that lands does harm either way, so no proposal makes a kitchen
    knife kill an ancient dragon outright. From as far below as the world's ladder says a rung
    shrugs off, ordinary means can't get through at all (G18).

    A hit that lands at relative speed in stopped time is measured by its own force instead, and
    code decides it alone, whatever the interpret step thought a pebble could do (W10a, A9): it
    is enough unless a body tough enough takes it, and a close call within half a tier of it."""
    facts = step.facts
    difficulty = ctx.settings.difficulty
    bodies = opposition.targets if step.aim.harmful else [c for c, _ in opposition.helpless]
    bodies = [b for b in bodies if b.id != actor.id]
    ceiling: MeansVerdict | None = None
    tough: _Rival | None = None
    takes_it: Character | None = None
    refused = ""
    if hit is not None and hit.force_tier is not None and bodies:
        margin, body = stop.force_ceiling_margin(state, bodies, hit.force_tier)
        if margin >= stop.TAKES_IT_MARGIN:
            ceiling, takes_it = MeansVerdict.CLEARLY_NOT, body
        elif margin > -stop.TAKES_IT_MARGIN:
            ceiling = MeansVerdict.CLOSE_CALL
            tough = _Rival(body, capability.level_of(state, body, "toughness", [], None))
        else:
            ceiling = MeansVerdict.CLEARLY_ENOUGH
    elif (step.aim.harmful or step.axis is PowerAxis.MIGHT) and bodies:
        if step.aim.harmful:
            refused = _shrugged_off(state, actor, drawn, bodies)
        tough = None if refused else _toughest(state, actor, bodies)
        if refused:
            ceiling = MeansVerdict.CLEARLY_NOT
        elif tough is not None:
            ceiling = MeansVerdict.CLOSE_CALL

    means = facts.means
    if means is None:
        # With no verdict, the level of the thing says whether there is anything to throw for.
        hard = facts.challenge is not None and capability.thing_level(facts.challenge) >= _OPEN_AT
        means = MeansVerdict.CLOSE_CALL if hard else MeansVerdict.CLEARLY_ENOUGH
    known = (
        brought.technique is not None and brought.technique.mastery.rank >= Mastery.PRACTICED.rank
    )
    if known and means is MeansVerdict.CLOSE_CALL and not (bodies or facts.opposition.strip()):
        # A2, A4. A move they know, with nothing resisting, works as they know it to.
        means = MeansVerdict.CLEARLY_ENOUGH
    if hit is not None and hit.overwhelming:
        # Code follows the force through; the interpret step's word on the means doesn't count.
        verdict = ceiling or MeansVerdict.CLEARLY_ENOUGH
    else:
        verdict = means if ceiling is None else min(means, ceiling, key=_MEANS_ORDER.index)

    lead = _helpless_lead(state, opposition)
    if verdict is MeansVerdict.CLEARLY_ENOUGH:
        reason = f"{lead}: no contest." if lead else NOTHING_IN_THE_WAY
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, reason)
    if verdict is MeansVerdict.CLEARLY_NOT:
        if takes_it is not None or (refused and ceiling is MeansVerdict.CLEARLY_NOT):
            why = _takes_it(state, takes_it) if takes_it is not None else refused
            return Settled(
                OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{lead}. {why}" if lead else why
            )
        why = "; ".join(h for h in facts.hindrances if h.strip()) or "The means aren't enough"
        why = cap(why)
        reason = f"{lead}, but {why[0].lower()}{why[1:]}." if lead else f"{why}."
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, reason)

    # A2. A blow that lands on someone who can't respond does harm either way; the throw is only
    # for how much. Anything else can still simply fail.
    harm_lands = step.aim.harmful and bool(opposition.targets)
    if tough is not None:
        number = tough.number(difficulty)
        against = f"{cap(possessive(state, tough.character.id))} body is the question."
    else:
        what = facts.opposition.strip()
        number = capability.thing_number(what, facts.challenge, difficulty)
        against = f"{cap(what)} stands in the way." if what else "A close call."
    if not dice.open_against(brought.hand, number.level):
        sure = f"{_no_throw(brought, number)}, there is no real doubt."
        return Settled(
            OutcomeClass.CERTAIN, StepResult.SUCCESS, f"{lead}. {sure}" if lead else sure
        )
    number = capability.number_for(
        state,
        actor,
        step,
        drawn,
        number,
        brought,
        axis=_axis(step),
        rival=tough.character if tough is not None else None,
        rival_by_attribute=True,
    )
    roll = dice.throw(
        rng.child("outcome"),
        brought.hand,
        number,
        label=step.text,
        allowed=dice.HARM_DONE if harm_lands else dice.ALL_RESULTS,
        difficulty=difficulty,
        greens=_greens(state, actor, step, drawn, frame, []),
        against=facts.up_against.strip() or against,
    )
    told = f"{cap(dice.told(roll))}."
    if harm_lands:
        how = "It lands in full" if roll.result is StepResult.SUCCESS else "It lands only in part"
        told = f"The blow lands either way, and the throw is for how much. {told} {how}."
    reason = f"{lead}. {told}" if lead else told
    return Settled(dice.class_of(roll.odds), roll.result, reason, roll)


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
    frame: _Frame,
    brought: capability.Brought,
) -> Settled:
    """G15. Only the actor's own nature stands in the way, so the step happens: the player chose
    it, and temperament never takes the choice away. Where the means are clearly enough, or the
    struggle is two levels or more under what they throw, it is simply done. Otherwise they
    throw against how hard the interpret step judged it, a real effort when it didn't say, with
    a flaw such as a hot temper raising the number, and the throw only decides how hard it was:
    done cleanly, or done with the strain showing. It never fails."""
    facts = step.facts
    player = actor.id == state.player_id
    what = facts.opposition.strip() or f"{possessive(state, actor.id)} own nature"
    yours = "yours" if player else possessive(state, actor.id)
    who, does = name(state, actor.id), "do" if player else "does"
    lead = f"{cap(what)} pushes back, but the choice is {yours}"
    difficulty = ctx.settings.difficulty
    number = capability.thing_number(what, facts.challenge, difficulty)
    easy = facts.means is MeansVerdict.CLEARLY_ENOUGH
    if easy or not dice.open_against(brought.hand, number.level):
        return Settled(OutcomeClass.CERTAIN, StepResult.SUCCESS, f"{lead}: {who} {does} it.")
    number = capability.number_for(state, actor, step, drawn, number, brought, axis=step.axis)
    roll = dice.throw(
        rng.child("outcome"),
        brought.hand,
        number,
        label=step.text,
        allowed=dice.OWN_CHOICE,
        difficulty=difficulty,
        greens=_greens(state, actor, step, drawn, frame, []),
        against=facts.up_against.strip() or f"{cap(what)} pushes back.",
    )
    done = f"{who} {does} it"
    if roll.result is not StepResult.SUCCESS:
        done = f"{done}, but the strain shows"
    reason = f"{lead}. {cap(dice.told(roll))}. {cap(done)}."
    return Settled(dice.class_of(roll.odds), roll.result, reason, roll)


def _with_chain(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition,
    drawn: Drawn,
    ctx: TurnContext,
    rng: SeededRng,
    frame: _Frame,
    brought: capability.Brought,
):
    """A9. A plan that goes around the strength instead of meeting it. Whoever can see it coming
    may answer first, so the actor throws for the setup against the level of whoever can
    respond at what answers it, with no rungs, since the plan goes around their power, or
    against the level of the thing in the way; then the chain settles link by link against
    everyone who can still answer."""
    difficulty = ctx.settings.difficulty
    facts = step.facts
    setup: RollRecord | None = None
    setup_class = OutcomeClass.CERTAIN
    if opposition.can_push_back:
        who = (
            names(state, opposition.responsive)
            if opposition.responsive
            else facts.opposition.strip() or "they"
        )
        rival: _Rival | None = None
        near = 0
        if opposition.responsive:
            rival, near = _strongest(
                [
                    _rival(state, actor, step, drawn, c, step.axis, head_on=False)
                    for c in opposition.responsive
                ]
            )
            number = rival.number(difficulty)
        else:
            challenge = facts.challenge
            if opposition.factions and capability.thing_level(challenge) < 1:
                challenge = Challenge.EASY
            number = capability.thing_number(facts.opposition.strip(), challenge, difficulty)
        # A faction that could still answer is never nothing; anyone else two levels under the
        # hand can't answer in time.
        if opposition.factions or dice.open_against(brought.hand, number.level):
            number = capability.number_for(
                state,
                actor,
                step,
                drawn,
                number,
                brought,
                axis=step.axis,
                rival=rival.character if rival is not None else None,
                rival_by_attribute=rival.level.by_attribute if rival is not None else False,
                extra_foes=near,
            )
            setup = dice.throw(
                rng.child("outcome"),
                brought.hand,
                number,
                label=f"before {who} can answer",
                allowed=dice.YES_OR_NO,
                difficulty=difficulty,
                greens=_greens(state, actor, step, drawn, frame, opposition.responsive),
                against=facts.up_against.strip() or f"{cap(who)} may see it coming.",
            )
            setup_class = dice.class_of(setup.odds)
            if setup.result is not StepResult.SUCCESS:
                single = (
                    len(opposition.responsive) == 1
                    and opposition.responsive[0].id != state.player_id
                )
                sees = "sees" if single or not opposition.responsive else "see"
                reason = f"{cap(who)} {sees} it coming in time. {cap(dice.told(setup))}."
                return Settled(setup_class, StepResult.FAILURE, reason, setup), None
    elif facts.means is MeansVerdict.CLEARLY_NOT:
        why = "; ".join(h for h in facts.hindrances if h.strip()) or "The means aren't enough"
        return Settled(OutcomeClass.RULED_OUT, StepResult.FAILURE, f"{cap(why)}."), None

    outcome = settle_chain(state, step, opposition.answering, ctx, rng)
    if not outcome.holds:
        # The link it broke on decides: ruled out with no roll, or the die that fell short.
        return Settled(
            outcome.outcome_class, StepResult.FAILURE, outcome.reason, outcome.roll
        ), outcome
    # Every link held: the step is as hard as the hardest throw it took, which is its roll.
    outcome_class, roll = setup_class, setup
    if _HARDER.index(outcome.outcome_class) > _HARDER.index(setup_class):
        outcome_class, roll = outcome.outcome_class, outcome.roll
    return Settled(outcome_class, StepResult.SUCCESS, outcome.reason, roll), outcome


def _judged(
    state: WorldState, actor: Character, step: IntentStep, opposition: _Opposition
) -> tuple[IntentStep, PlaceChange | None]:
    """A3. A thing keeps the level it was first judged at, so the same lock is the same lock
    tomorrow. The step with the level its place holds for the thing, when it holds one, and
    otherwise the engine's change that keeps what the interpret step judged now. Only a thing
    of the place is kept: nobody's own level, no faction, and nothing judged trivial."""
    if opposition.characters or opposition.factions or step.aim.harmful:
        return step, None
    place = state.places.get(actor.location_id or state.scene.place_id or "")
    key = capability.thing_key(step)
    if place is None or not key:
        return step, None
    level = place.level_of(key)
    if level is not None:
        challenge = _CHALLENGE_AT[level]
        if challenge is step.facts.challenge:
            return step, None
        facts = step.facts.model_copy(update={"challenge": challenge})
        return step.model_copy(update={"facts": facts}), None
    judged = step.facts.challenge
    if judged is None or levels.CHALLENGE_LEVEL[judged] < 1:
        return step, None
    what = step.facts.opposition.strip() or step.text
    kept = Judged(key=key, what=what, level=levels.CHALLENGE_LEVEL[judged])
    return step, PlaceChange(id=place.id, judged=[kept])


def _over_the_top(
    state: WorldState,
    actor: Character,
    step: IntentStep,
    opposition: _Opposition | None,
    effects: StateDelta,
    quicker: bool,
) -> tuple[str, StateDelta, list[str]]:
    """A3. The one fixed extra effect of a throw over the top, which code picks by the kind of
    step so the telling can't inflate it. A blow or a clash leaves those who answered staggered,
    and the actor's next step against them throws a green die. Words move each listener's trust
    one notch further, or their fear where it was a threat. A task on a thing took half the
    time. And those who saw it will remember. The effect in words, the engine's change, and
    whom the actor now holds an opening on."""
    gone = _taken_out(effects)
    standing = [c for c in (opposition.responsive if opposition else []) if c.id not in gone]
    player = actor.id == state.player_id
    whose = "your" if player else possessive(state, actor.id)
    told: list[str] = []
    change = StateDelta()
    openings: list[str] = []
    if standing and _axis(step) is PowerAxis.INFLUENCE and not step.aim.harmful:
        fear = capability.intimidates(step)
        toward = None if player else actor.id
        shift = (
            AttitudeShift(toward_id=toward, fear=ATTITUDE_NOTCH)
            if fear
            else AttitudeShift(toward_id=toward, trust=ATTITUDE_NOTCH)
        )
        change = StateDelta(
            characters=[CharacterChange(id=c.id, attitudes=[shift]) for c in standing]
        )
        listeners = names(state, standing)
        feeling = "fear of" if fear else "trust in"
        them = "you" if player else actor.name
        told.append(f"{cap(listeners)}: {feeling} {them} goes a notch further")
    elif standing:
        openings = [c.id for c in standing]
        who = names(state, standing)
        single = len(standing) == 1 and standing[0].id != state.player_id
        is_, has = ("is", "has") if single else ("are", "have")
        how = "staggered" if step.aim.harmful or _axis(step) is PowerAxis.MIGHT else "caught out"
        told.append(
            f"{cap(who)} {is_} {how} and {has} no answer, and {whose} next step against them "
            "throws a green die"
        )
    elif quicker:
        told.append("it takes half the time")
    told.append("those who saw it will remember")
    return f"Over the top: {'. '.join(cap(t) for t in told)}.", change, openings


def _takes_it(state: WorldState, body: Character) -> str:
    return f"{cap(name(state, body.id))} {is_are(state, body.id)} tough enough to take it unhurt."


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
