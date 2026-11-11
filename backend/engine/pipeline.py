"""The engine functions the turn graph calls (B5), in the order it calls them.

1. `catch_up`: the world catches up on anything that fell due (W6, W10, B12).
2. (interpret, a model node, produces an `Intent`)
3. `resolve`: logic first, then the odds, step by step (A2, A3, R2, R6).
   `play_out`: the steps happen in order on in-world time; each step's consequences are recorded
   when it ends, and an event that needs the player cuts the plan short (W10, R6).
   `direct`: whether something new comes in, callbacks, suggestions and the picture (W16, M1).
4. to 7. (context, narrate and the narrator's state update are the graph's. The graph applies the
   update with `engine.apply.apply_delta(state, delta, ctx, source=DeltaSource.NARRATOR)`, then
   `settle_trips` and `settle_picture`, and runs `engine.invariants.check_transition` on the
   turn's first and last states before saving)

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

from engine import director, encounters, world
from engine.apply import DeltaSource, Rejection, apply_in_place
from engine.context import TurnContext
from engine.contracts.delta import CharacterChange, StateDelta
from engine.contracts.direction import (
    DirectorPlan,
)
from engine.contracts.intent import Intent
from engine.contracts.resolution import Resolution, StepResolution, StopReason
from engine.resolve import resolve_intent
from engine.resolve.powers import growth
from engine.rng import SeededRng
from engine.state.records import PendingEvent
from engine.state.sheet import Practice
from engine.state.world import WorldState
from engine.timekeeping import TimePassage, prune_time_effects, world_stopped
from engine.world import journeys

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
    "settle_picture",
    "settle_trips",
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


def catch_up(
    state: WorldState, until_s: int, ctx: TurnContext, rng: SeededRng, *, copy: bool = True
) -> TimePassage:
    """Step 1, and every step of a plan. Move the world clock to `until_s` (the graph passes
    `state.world_s`), applying every pending event due on the way in time order and running the
    deterministic world tick (W6, W10, B12). The first event that needs the player stops the
    clock there. While a time stop is in effect nothing fires (W10a).

    The living world's one loop, `engine.world.catch_up` (WS10). `copy=False` works on the
    caller's own copy instead of a new one, as `play_out` does with its working copy.
    """
    return world.catch_up(state, until_s, ctx, rng, copy=copy)


def resolve(
    state: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng, *, scene: str = ""
) -> Resolution:
    """Step 3. Settle each step from the facts and throw only for what they leave open (A2, A3).

    `engine.resolve` (WS9): the world's rules, the sheet and the beats, who stands in the way and
    whether they can respond at all, then a seeded throw of the actor's dice against the number
    the other side's level sets, only where something is open. A chained plan stops at the
    first step that doesn't cleanly succeed (R6). Inside a time stop the world clock stands
    still while the actor's runs (W10a). `scene` is the text of the scene the player is
    answering, which an advantage may quote.
    """
    return resolve_intent(state, intent, ctx, rng, scene=scene)


def apply_event(
    state: WorldState, event: PendingEvent, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Apply one pending event that fell due: a witness reaching the guard post, a rumor arriving,
    a faction's answer, a clock's step, the world tick (W2, W5, W6, W10, W13). It may schedule new
    events, which fire in turn if they fall due within the same stretch of time. It leaves the
    event applied and records on it whether it needed the player when it happened.

    `engine.world.apply_event` (WS10). Events of other kinds, such as `director.*`, are only
    marked applied.
    """
    return world.apply_event(state, event, ctx, rng)


def record_consequences(
    state: WorldState,
    resolution: Resolution,
    step: StepResolution,
    ctx: TurnContext,
    rng: SeededRng,
) -> WorldState:
    """Record what one finished step did to the world: deeds with their witnesses and severity,
    rumors, reputation, grudges, and the world's answers scheduled as pending events (W1 to W5,
    W11 to W13). Called by `play_out` at the step's end time, after the step's effects, so a
    witness who flees during a long action can arrive during it and a victim is already dead.

    `engine.world.record_consequences` (WS10).
    """
    return world.record_consequences(state, resolution, step, ctx, rng)


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

    A step that starts inside a stop and outlasts it lives out the stop first and then takes
    world time for the rest (W10a).

    Rulings are recorded on the actor's sheet once, never flipped (A9), and then the plan's own
    `effects` apply (settled details of powers, accepted backstory). Time effects that ran out
    on their user's clock are cleared at the end, and the openings the player character holds
    for their next step move on with the steps that played (A3).

    Code starts and ends the scene's encounter as the steps play (W10, `engine.encounters`): a
    long stretch that isn't part of it ends it before the stretch's events are rolled, each step
    that played starts, joins or carries it on, and it ends once nothing keeps it going.

    A step that goes somewhere leaves the actor there once it has played in full, so what they
    do next happens there, and one an event cut short leaves the player character on the way,
    with what is left of it kept (W10, `engine.world.journeys`). A trip of theirs rolls what
    the road brings in place of a long stretch's events (W16, `director.schedule_road`).
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
        # W10. A long stretch that isn't part of the encounter, such as a night's sleep, ends it
        # first, so the stretch rolls its events (E7).
        encounters.before_step(current, step, actor_id)
        start_s = current.world_s
        planned_end = start_s + step.duration_s
        lived_total = step.duration_s if step.personal_s is None else step.personal_s
        frozen_part = 0
        if step.duration_s > 0 and world_stopped(current):
            # W10a. A step that starts inside a stop and outlasts it: the actor lives out the rest
            # of the stop first, which ends it, and then the world's time runs again.
            frozen_part = max(0, lived_total - step.duration_s)
            actor = current.characters.get(actor_id)
            if actor is not None:
                actor.personal_offset_s += frozen_part
        if step.duration_s > 0 and not world_stopped(current):
            # A day or more is a montage: the director rolls its W16 events first, so the first
            # that needs a decision stops the clock there (E7).
            stretch_rng = rng.child("director", "stretch", step.index)
            if journeys.on_the_road(current, actor_id, step):
                # W10. A trip meets what the road brings, so a journey isn't always one scene.
                current = director.schedule_road(current, start_s, planned_end, ctx, stretch_rng)
            else:
                current = director.schedule_stretch(current, start_s, planned_end, ctx, stretch_rng)
            passage = catch_up(current, planned_end, ctx, rng, copy=False)
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
        lived = lived_total - frozen_part
        if cut:
            lived = lived * elapsed // step.duration_s
        actor = current.characters.get(actor_id)
        if actor is not None:
            actor.personal_offset_s += lived - elapsed
        lived += frozen_part
        trip = step.trip
        if cut and trip is not None and journeys.cut_short(step, elapsed):
            trip = trip.model_copy(update={"arrived": False})  # W10: stopped on the way
        timed = step.model_copy(
            update={
                "start_s": start_s,
                "end_s": current.world_s,
                "duration_s": elapsed,
                "personal_s": None if step.personal_s is None and lived == elapsed else lived,
                "interrupted": cut,
                "trip": trip,
            }
        )
        played.append(timed)
        if cut and step.training is not None:
            # A4. Training cut short keeps the effort put in, and makes the gain if that was
            # enough before the interruption.
            rejected.extend(_keep_training(current, actor_id, step, lived - frozen_part, ctx))
        if not cut:
            if not step.effects.empty:
                applied = apply_in_place(current, step.effects, ctx, source=DeltaSource.ENGINE)
                rejected.extend(applied.rejected)
            step_rng = rng.child("play_out", "step", step.index)
            current = record_consequences(current, resolution, timed, ctx, step_rng)
        # W10. Whoever arrived is there, and a trip that stopped on the way keeps what is left.
        journeys.follow(current, actor_id, timed, planned_s=step.duration_s)
        # W10. Code starts and ends encounters from what the step did (`engine.encounters`).
        encounters.follow(current, timed, actor_id, ctx)
        encounters.settle(current)
        if interrupted_by is not None:
            break

    if resolution.rulings and actor_id in current.characters:
        rulings = StateDelta(characters=[CharacterChange(id=actor_id, rulings=resolution.rulings)])
        rejected.extend(apply_in_place(current, rulings, ctx, source=DeltaSource.ENGINE).rejected)
    if not resolution.effects.empty:
        applied = apply_in_place(current, resolution.effects, ctx, source=DeltaSource.ENGINE)
        rejected.extend(applied.rejected)
    prune_time_effects(current)
    encounters.settle(current)
    if actor_id == current.player_id:
        # A3. The openings the player character holds for their next step: each is used by the
        # next step that faced whom it is on, those the steps that played won are added, and
        # none outlasts the encounter. A step an event cut short didn't happen.
        held = list(current.openings)
        for step in played:
            if not step.interrupted:
                held = [o for o in held if o not in step.opponent_ids] + step.opening_ids
        in_it = current.scene.encounter is not None
        current.openings = [
            o
            for o in dict.fromkeys(held)
            if in_it and o in current.characters and current.characters[o].alive
        ]

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


def _keep_training(
    current: WorldState, actor_id: str, step: StepResolution, lived_s: int, ctx: TurnContext
) -> list[Rejection]:
    so_far = step.training
    assert so_far is not None
    actor = current.characters.get(actor_id)
    if so_far.practising:
        # Practising a technique they know: the time it ran counts toward its mastery.
        if actor is None:
            return []
        delta = growth.practice_cut(actor, so_far, lived_s, step.text)
        return list(apply_in_place(current, delta, ctx, source=DeltaSource.ENGINE).rejected)
    effort = so_far.before_s + growth.effort_s(lived_s) * so_far.rate
    if effort >= so_far.need_s:
        delta = step.effects
    else:
        kept = Practice(key=so_far.key, what=so_far.what, effort_s=int(effort))
        delta = StateDelta(characters=[CharacterChange(id=actor_id, practice=[kept])])
    return list(apply_in_place(current, delta, ctx, source=DeltaSource.ENGINE).rejected)


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


def settle_trips(
    played: WorldState, state: WorldState, resolution: Resolution, *, told: bool
) -> tuple[WorldState, list[str]]:
    """After the narrator's update is applied (step 6): the scene ends where this turn's trips
    left the player character, a trip over ground the map didn't cover writes its route, and a
    trip stopped on the way keeps what is left of it (W10, W7, `engine.world.journeys`).

    `played` is the state the steps left, before the update, and `told` says whether the
    narrator said where its scene ends. Returns the state, a new one when anything changed, and
    what had to be put right, for the turn's log.
    """
    return journeys.settle(played, state, resolution, told=told)


def settle_picture(state: WorldState, plan: DirectorPlan) -> tuple[WorldState, DirectorPlan]:
    """After the narrator's update is applied (step 6): the look version a planned portrait or
    place is drawn at, with the director's memory to match, so a scene that changed the look it
    pictures draws the new one, once (M4, M5)."""
    return director.settle_look(state, plan)
