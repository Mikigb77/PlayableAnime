"""The engine functions the turn graph calls (B5), in the order it calls them.

1. `catch_up`: the world catches up on anything that fell due (W6, W10, B12).
2. (interpret, a model node, produces an `Intent`)
3. `resolve`: logic first, then the odds, step by step (A2, A3, R2, R6).
   `play_out`: the steps happen in order on in-world time; each step's consequences are recorded
   when it ends, and an event that needs the player cuts the plan short (W10, R6).
   `direct`: whether something new comes in, callbacks, suggestions and the picture (W16, M1).
4. to 7. (context, narrate and the narrator's state update are the graph's. The graph applies the
   update with `engine.apply.apply_delta(state, delta, ctx, source=DeltaSource.NARRATOR)` and
   runs `engine.invariants.check_transition` on the turn's first and last states before saving)

Each seam has a trivial default body here. Other workstreams replace a body by calling into their
own package, without changing the signature: resolve is `engine.resolve` (WS9), `catch_up`,
`apply_event` and `record_consequences` are `engine.world` (WS10), and `direct` is
`engine.director` (WS11). `play_out` is WS2's. A signature change goes through the orchestrator,
since the graph (WS3) and three workstreams depend on it.

Rules every seam follows:

- Take the state as read-only and return a new one (`state.model_copy(deep=True)`).
- Derive random streams from the turn's `rng` with stable labels, such as
  `rng.child("resolve", "step", 0)`, never from call order across seams.
- Never import Django or a model SDK (B4). World-moving processes (rumor spread, clocks, faction
  answers) are pending events with in-world due times, so they fire in time order wherever time
  passes (W10).
"""

from dataclasses import dataclass, field

from engine import director
from engine.apply import DeltaSource, Rejection, apply_in_place
from engine.context import TurnContext
from engine.contracts.delta import CharacterChange, StateDelta
from engine.contracts.direction import (
    DirectorPlan,
)
from engine.contracts.intent import Intent
from engine.contracts.resolution import Resolution, StepResolution, StopReason
from engine.resolve import resolve_intent
from engine.rng import SeededRng
from engine.state.records import Deed, EventStatus, PendingEvent, Visibility
from engine.state.world import WorldState
from engine.timekeeping import TimePassage, advance_clock, world_stopped

__all__ = [
    "PlayOut",
    "TimePassage",
    "apply_event",
    "catch_up",
    "direct",
    "play_out",
    "record_consequences",
    "record_direction",
    "resolve",
]


@dataclass(frozen=True)
class PlayOut:
    """The plan after it played out: the new state, the resolution with each step's start and end
    times (truncated where an event cut it short), the events applied along the way in time
    order, the event that needed the player if one stopped the plan, and any of the steps' own
    changes that the C1 invariants refused (a bug in resolve if it ever happens). `capped` means
    a step hit the cap on events per stretch, which only a runaway handler causes; log it."""

    state: WorldState
    resolution: Resolution
    fired: tuple[PendingEvent, ...] = field(default_factory=tuple)
    interrupted_by: PendingEvent | None = None
    rejected: tuple[Rejection, ...] = field(default_factory=tuple)
    capped: bool = False


def _event_handler(ctx: TurnContext, rng: SeededRng):
    """Applies events through the `apply_event` seam, each with its own stream keyed by its id,
    so an event rolls the same however the time around it was split into steps."""
    return lambda state, event: apply_event(state, event, ctx, rng.child("event", event.id))


def catch_up(state: WorldState, until_s: int, ctx: TurnContext, rng: SeededRng) -> TimePassage:
    """Step 1. Apply pending events due by `until_s`, in time order, and run the deterministic
    world tick (W6, W10, B12). The graph passes `until_s=state.world_s`. While a time stop is in
    effect nothing fires (W10a).

    Default: the due events go through `apply_event` with `engine.timekeeping.advance_clock`, and
    there is no world tick. WS10 replaces it.
    """
    if world_stopped(state):
        return TimePassage(state=state, started_s=state.world_s, ended_s=state.world_s)
    return advance_clock(state, until_s, _event_handler(ctx, rng))


def resolve(state: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng) -> Resolution:
    """Step 3. Settle each step from the facts and roll only what they leave open (A2, A3).

    `engine.resolve` (WS9): the world's rules, the sheet and the beats, who stands in the way and
    whether they can respond at all, the power gap, then a seeded roll only for contested and
    long-shot steps and close calls. A chained plan stops at the first step that doesn't cleanly
    succeed (R6). Inside a time stop the world clock stands still while the actor's runs (W10a).
    """
    return resolve_intent(state, intent, ctx, rng)


def apply_event(
    state: WorldState, event: PendingEvent, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Apply one pending event that fell due: a witness reaching the guard post, a rumor arriving,
    a faction's answer (W2, W5, W10, W13). It may schedule new events, which fire in turn if they
    fall due within the same stretch of time.

    Default: the event is marked applied and changes nothing else. WS10 replaces it.
    """
    stored = state.pending_events.get(event.id)
    if stored is None or stored.status is not EventStatus.PENDING:
        raise ValueError(f"event {event.id!r} is not a pending event of this state")
    new = state.model_copy(deep=True)
    fired = new.pending_events[event.id]
    fired.status = EventStatus.APPLIED
    fired.applied_turn = ctx.turn
    fired.applied_s = new.world_s
    return new


def record_consequences(
    state: WorldState,
    resolution: Resolution,
    step: StepResolution,
    ctx: TurnContext,
    rng: SeededRng,
) -> WorldState:
    """Record what one finished step did to the world: deeds with their witnesses and severity,
    rumors, reputation, grudges, and the world's answers scheduled as pending events (W1 to W5,
    W11 to W13). Called by `play_out` at the step's end time, so a witness who flees during a long
    action can arrive during it.

    Default: the step's proposed deeds are recorded as given. WS10 replaces it.
    """
    if not step.deeds:
        return state
    new = state.model_copy(deep=True)
    for proposed in step.deeds:
        actor_id = proposed.actor_id or resolution.actor_id or new.player_id
        actor = new.characters.get(actor_id)
        visibility = proposed.visibility or (
            Visibility.WITNESSED if proposed.witness_ids else Visibility.SECRET
        )
        unnoticed = proposed.unnoticed_witness_ids
        if proposed.in_stopped_time:
            # The user sees a frozen world; whoever was immune to the stop goes unnoticed (W10a).
            unnoticed = proposed.witness_ids
        deed = Deed(
            id=new.new_id("deed"),
            actor_id=actor_id,
            kind=proposed.kind,
            text=proposed.text,
            turn=ctx.turn,
            world_s=new.world_s,
            timeline_id=new.timeline_id,
            place_id=proposed.place_id or (actor.location_id if actor else None),
            victim_ids=proposed.victim_ids,
            target_ids=proposed.target_ids,
            severity=proposed.severity,
            visibility=visibility,
            witness_ids=proposed.witness_ids,
            unnoticed_witness_ids=[w for w in unnoticed if w in proposed.witness_ids],
            traces=proposed.traces,
            in_stopped_time=proposed.in_stopped_time,
            known_by=list(dict.fromkeys([actor_id, *proposed.witness_ids])),
        )
        new.deeds[deed.id] = deed
    return new


def play_out(
    state: WorldState, resolution: Resolution, ctx: TurnContext, rng: SeededRng
) -> PlayOut:
    """Play the resolved steps in order on in-world time (W10, W10a, R6).

    For each step that takes world time, the world catches up to the step's end through
    `catch_up`, so every pending event due on the way applies in time order, from the one loop
    the living world owns. It gets the turn's own `rng`, so an event rolls the same however the
    time around it is split into steps. The actor's personal clock moves by their lived time. At
    the step's end its `effects` apply as the engine's, with the C1 invariants, and then its
    consequences are recorded, so a victim is already dead when witnesses are worked out.

    The first event that needs the player stops the plan at its time. A step it cuts short gets
    only the time it ran for (lived time in proportion) and is marked `interrupted`; its effects
    and deeds don't happen, since resolve settled them for the whole step. The steps after it go
    to `unplayed`, so the narrator hands the scene back there. A step in a time stop takes no
    world time (resolve gives it none), and while a stop holds the world, the world clock never
    moves (W10a).

    Rulings are recorded on the actor's sheet once, never flipped (A9).
    """
    # One working copy for the whole plan; the input state is never touched.
    current = state.model_copy(deep=True)
    actor_id = resolution.actor_id or state.player_id
    played: list[StepResolution] = []
    fired: list[PendingEvent] = []
    rejected: list[Rejection] = []
    interrupted_by: PendingEvent | None = None
    capped = False
    for step in resolution.steps:
        start_s = current.world_s
        planned_end = start_s + step.duration_s
        if step.duration_s > 0 and not world_stopped(current):
            # A day or more is a montage: the director rolls its W16 events first, so the first
            # that needs a decision stops the clock there (E7).
            stretch_rng = rng.child("director", "stretch", step.index)
            current = director.schedule_stretch(current, start_s, planned_end, ctx, stretch_rng)
            passage = catch_up(current, planned_end, ctx, rng)
            current = passage.state
            fired.extend(passage.fired)
            interrupted_by = passage.interrupted_by
            if interrupted_by is None and current.world_s < planned_end:
                # The cap stopped the clock early. The step still takes its time; what is left
                # pending is overdue and applies at the next catch-up.
                capped = True
                current.world_s = planned_end
        elapsed = current.world_s - start_s
        cut = interrupted_by is not None and elapsed < step.duration_s
        lived = step.duration_s if step.personal_s is None else step.personal_s
        if cut:
            lived = lived * elapsed // step.duration_s
        actor = current.characters.get(actor_id)
        if actor is not None:
            actor.personal_offset_s += lived - elapsed
        timed = step.model_copy(
            update={
                "start_s": start_s,
                "end_s": current.world_s,
                "duration_s": elapsed,
                "personal_s": None if step.personal_s is None and lived == elapsed else lived,
                "interrupted": cut,
            }
        )
        played.append(timed)
        if not cut:
            if not step.effects.empty:
                applied = apply_in_place(current, step.effects, ctx, source=DeltaSource.ENGINE)
                rejected.extend(applied.rejected)
            step_rng = rng.child("play_out", "step", step.index)
            current = record_consequences(current, resolution, timed, ctx, step_rng)
        if interrupted_by is not None:
            break

    if resolution.rulings and actor_id in current.characters:
        rulings = StateDelta(characters=[CharacterChange(id=actor_id, rulings=resolution.rulings)])
        rejected.extend(apply_in_place(current, rulings, ctx, source=DeltaSource.ENGINE).rejected)

    update: dict = {"steps": played}
    later = resolution.steps[len(played) :]
    if interrupted_by is not None and (later or played[-1].interrupted):
        update.update(
            stopped_at_step=played[-1].index,
            stop_reason=StopReason.INTERRUPTED,
            unplayed=[s.text for s in later] + resolution.unplayed,
        )
    return PlayOut(
        state=current,
        resolution=resolution.model_copy(update=update),
        fired=tuple(fired),
        interrupted_by=interrupted_by,
        rejected=tuple(rejected),
        capped=capped,
    )


def direct(
    state: WorldState,
    resolution: Resolution,
    ctx: TurnContext,
    rng: SeededRng,
    intent: Intent | None = None,
) -> DirectorPlan:
    """Decide whether an event comes in, which dormant threads to call back, the suggestions and
    whether the scene gets a picture (W16, E4, N1, S2, M1, M2), in `engine.director` (WS11).

    Call it after `play_out`, with the played-out state and resolution. Pass the turn's `intent`
    so the director sees the goals the player stated, what they took up (`responds_to`) and
    repeated low-stakes actions; without it the director reads the resolution alone. It never
    changes the state: `record_direction` writes the plan's updates.
    """
    return director.direct(state, resolution, ctx, rng, intent)


def record_direction(state: WorldState, plan: DirectorPlan, ctx: TurnContext) -> WorldState:
    """Write a director plan's updates into the state, once per turn after `direct` and before
    saving: the director's memory, the event's thread and its play-out, thread changes, leads that
    expired and goals the player stated (W16, N1, N2, M2)."""
    return director.record(state, plan, ctx)
