"""The engine functions the turn graph calls (B5), in the order it calls them.

1. `catch_up`: the world catches up on anything that fell due (W6, W10, B12).
2. (interpret, a model node, produces an `Intent`)
3. `resolve`: logic first, then the odds, step by step (A2, A3, R2, R6).
   `play_out`: the steps happen in order on in-world time; each step's consequences are recorded
   when it ends, and an event that needs the player cuts the plan short (W10, R6).
   `direct`: whether something new comes in, callbacks, suggestions and the picture (W16, M1).
4. to 7. (context, narrate and the narrator's state update are the graph's; the update is applied
   with `engine.apply.apply_delta`, PR 2)

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

from engine.context import ImageSetting, TurnContext
from engine.contracts.direction import (
    DirectorPlan,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    SuggestionPlan,
)
from engine.contracts.intent import ActionKind, Intent, OutcomeClass, StandingAction
from engine.contracts.resolution import Resolution, StepResolution
from engine.rng import SeededRng
from engine.state.records import Deed, EventStatus, PendingEvent, StepResult, Visibility
from engine.state.world import WorldState
from engine.timekeeping import bound_duration, in_time_stop, stop_power_used

STANDING_DURATIONS_S = {StandingAction.WAIT: 60, StandingAction.OBSERVE: 30}


@dataclass(frozen=True)
class TimePassage:
    """In-world time that passed: from `started_s` to `ended_s`, with the pending events that fired
    in time order. `interrupted_by` is the first event that needed the player, if one cut the time
    short (W10)."""

    state: WorldState
    started_s: int
    ended_s: int
    fired: tuple[PendingEvent, ...] = ()
    interrupted_by: PendingEvent | None = None

    @property
    def elapsed_s(self) -> int:
        return self.ended_s - self.started_s


@dataclass(frozen=True)
class PlayOut:
    """The plan after it played out: the new state, the resolution with each step's start and end
    times (and truncated if an event cut it short), and the events that fired along the way."""

    state: WorldState
    resolution: Resolution
    fired: tuple[PendingEvent, ...] = field(default_factory=tuple)
    interrupted_by: PendingEvent | None = None


def catch_up(state: WorldState, until_s: int, ctx: TurnContext, rng: SeededRng) -> TimePassage:
    """Step 1. Apply pending events due by `until_s`, in time order, and run the deterministic
    world tick (W6, W10, B12). The graph passes `until_s=state.world_s`.

    Default: nothing happens off-screen. WS10 replaces it.
    """
    return TimePassage(state=state, started_s=state.world_s, ended_s=state.world_s)


def resolve(state: WorldState, intent: Intent, ctx: TurnContext, rng: SeededRng) -> Resolution:
    """Step 3. Settle each step from the facts and roll only what they leave open (A2, A3).

    Default: every step is certain and succeeds in its proposed duration, bounded by its kind.
    Inside a time stop (one already in effect, or one a step starts), the world clock stands
    still while the actor's runs, for as long as the stop lasts (W10a). WS9 replaces it.
    """
    actor_id = intent.actor_id or state.player_id
    frozen = in_time_stop(state, actor_id)
    stop_left_s: int | None = None
    steps: list[StepResolution] = []
    for i, step in enumerate(intent.steps):
        power = stop_power_used(state, actor_id, step)
        if power is not None:
            frozen = True
            stop_left_s = power.time.lasts_s
        proposed_lived = step.proposed_personal_s
        if frozen and proposed_lived is None:
            proposed_lived = step.proposed_duration_s
        lived = None if proposed_lived is None else bound_duration(step.kind, proposed_lived)
        steps.append(
            StepResolution(
                index=i,
                text=step.text,
                outcome_class=OutcomeClass.CERTAIN,
                reason="Nothing stands in the way.",
                result=StepResult.SUCCESS,
                duration_s=bound_duration(step.kind, step.proposed_duration_s, world_frozen=frozen),
                personal_s=lived,
            )
        )
        if frozen and stop_left_s is not None:
            stop_left_s -= lived or 0
            if stop_left_s <= 0:
                frozen, stop_left_s = False, None
    if not steps and intent.standing is not None:
        kind = ActionKind(intent.standing.value)
        steps = [
            StepResolution(
                index=0,
                text=intent.standing.value,
                outcome_class=OutcomeClass.CERTAIN,
                reason="Nothing stands in the way.",
                result=StepResult.SUCCESS,
                duration_s=bound_duration(kind, STANDING_DURATIONS_S[intent.standing]),
            )
        ]
    return Resolution(actor_id=intent.actor_id, steps=steps)


def apply_event(
    state: WorldState, event: PendingEvent, ctx: TurnContext, rng: SeededRng
) -> WorldState:
    """Apply one pending event that fell due: a witness reaching the guard post, a rumor arriving,
    a faction's answer (W2, W5, W10, W13). It may schedule new events, which fire in turn if they
    fall due within the same stretch of time.

    Default: the event is marked fired and changes nothing else. WS10 replaces it.
    """
    stored = state.pending_events.get(event.id)
    if stored is None or stored.status is not EventStatus.PENDING:
        raise ValueError(f"event {event.id!r} is not a pending event of this state")
    new = state.model_copy(deep=True)
    fired = new.pending_events[event.id]
    fired.status = EventStatus.FIRED
    fired.fired_turn = ctx.turn
    fired.fired_s = new.world_s
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

    For each step the world clock moves by the step's duration and the actor's personal clock by
    their lived time, then the step's consequences are recorded at its end time. Rulings are
    recorded on the actor's sheet once, never flipped (A9).

    PR 1 moves the clocks without firing pending events. PR 2 fires every event due during each
    step in time order through `apply_event`, cuts the plan short at the first one that needs the
    player, and applies each step's `effects` with the C1 invariants.
    """
    # One working copy for the whole plan; the input state is never touched.
    current = state.model_copy(deep=True)
    played: list[StepResolution] = []
    actor_id = resolution.actor_id or state.player_id
    for step in resolution.steps:
        start_s = current.world_s
        current.world_s += step.duration_s
        lived_s = step.duration_s if step.personal_s is None else step.personal_s
        actor = current.characters.get(actor_id)
        if actor is not None:
            actor.personal_offset_s += lived_s - step.duration_s
        timed = step.model_copy(update={"start_s": start_s, "end_s": current.world_s})
        step_rng = rng.child("play_out", "step", step.index)
        current = record_consequences(current, resolution, timed, ctx, step_rng)
        played.append(timed)

    if resolution.rulings and actor_id in current.characters:
        sheet = current.characters[actor_id].sheet
        for ruling in resolution.rulings:
            if sheet.ruling(ruling.topic, ruling.power_id) is None:
                settled = ruling.model_copy(update={"turn": ctx.turn, "world_s": current.world_s})
                sheet.rulings.append(settled)

    return PlayOut(state=current, resolution=resolution.model_copy(update={"steps": played}))


def direct(
    state: WorldState, resolution: Resolution, ctx: TurnContext, rng: SeededRng
) -> DirectorPlan:
    """Decide whether an event comes in, which dormant threads to call back, the suggestions and
    whether the scene gets a picture (W16, E4, N1, S2, M1, M2).

    Default: nothing new comes in, three suggestions (none if the player turned them off), and the
    player character's portrait on the opening turn. WS11 replaces it.
    """
    picture = None
    if ctx.turn <= 1 and ctx.settings.images is not ImageSetting.OFF:
        picture = PictureDecision(
            kind=PictureKind.PORTRAIT,
            trigger=PictureTrigger.STORY_START,
            subject_id=state.player_id,
            reason="The story starts.",
        )
    suggestions = (
        SuggestionPlan() if ctx.settings.suggestions else SuggestionPlan(count=0, kinds=[])
    )
    return DirectorPlan(picture=picture, suggestions=suggestions)
