"""T17's living-world scenarios, played through `pipeline.play_out` turn after turn the way the
turn loop does: the fleeing witness, the interrupted sleep, the phone witness, the idle world and
the ignored hook (W2, W5, W6, W10, W11, E2, K8)."""

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.context import StorySettings, TurnContext
from engine.contracts import (
    CharacterChange,
    OutcomeClass,
    ProposedDeed,
    Resolution,
    StateDelta,
    StepResolution,
)
from engine.invariants import check_transition
from engine.pipeline import PlayOut
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Activity,
    Character,
    CharacterStatus,
    ClockStatus,
    EventStatus,
    FactionStatus,
    Membership,
    OriginKind,
    PendingEvent,
    Prominence,
    StepResult,
    ThreadStatus,
    WorldState,
)
from engine.world import Kind
from engine.world.tuning import MAX_TICKS_PER_PASSAGE, UNKNOWN_TRIP_S


def ctx(turn: int) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings())


def rng(turn: int) -> SeededRng:
    return SeededRng.for_turn("s1", "main", turn)


def step(duration_s: int, text: str, **kwargs) -> StepResolution:
    return StepResolution(
        index=0,
        text=text,
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=duration_s,
        **kwargs,
    )


def kill(victim_id: str, text: str) -> StepResolution:
    death = StateDelta(characters=[CharacterChange(id=victim_id, status=CharacterStatus.DEAD)])
    deed = ProposedDeed(kind="kill", text=text, victim_ids=[victim_id])
    return step(2, text, effects=death, deeds=[deed])


class Story:
    """Turns played one after another, each from the state the last one left."""

    def __init__(self, state: WorldState) -> None:
        self.state = state
        self.turn = 1
        self.fired: list[PendingEvent] = []

    def play(self, *steps: StepResolution) -> PlayOut:
        self.turn += 1
        resolution = Resolution(
            steps=[s.model_copy(update={"index": i}) for i, s in enumerate(steps)]
        )
        before = self.state
        played = pipeline.play_out(before, resolution, ctx(self.turn), rng(self.turn))
        assert check_transition(before, played.state) == []
        self.state = played.state
        self.fired.extend(played.fired)
        return played

    def applied(self, kind: Kind, **payload) -> list[PendingEvent]:
        return [
            e
            for e in self.fired
            if e.kind == kind and all(e.payload.get(k) == v for k, v in payload.items())
        ]


# --- Fleeing witness and interrupted sleep (W10, W11) ----------------------------------------


def sect_with_a_witness() -> WorldState:
    """The cultivation sample, with a timid outer disciple drawing water at the well. The sect
    has no phones, and the map doesn't say where its Law Enforcement Hall sits."""
    state = cultivation_world()
    state.characters["wei"] = Character(
        id="wei",
        name="Wei",
        description="A timid outer disciple with a bucket.",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple", loyalty=40)],
    )
    return state


def kill_then_brew() -> Story:
    story = Story(sect_with_a_witness())
    story.play(kill("zhao", "Lin kills Zhao Kun at the well"))
    for _ in range(10):
        played = story.play(step(18, "stir the potion"))
        assert played.interrupted_by is None
    return story


def test_fleeing_witness_no_guards_arrive_before_a_report_and_the_trip_back():
    story = kill_then_brew()

    (deed,) = story.state.deeds.values()
    assert deed.witness_ids == ["wei"]
    assert story.state.world_s == 2 + 10 * 18  # about three minutes
    # Wei is on the way to tell the sect, on foot: nobody has heard yet, nobody has come.
    assert story.applied(Kind.REPORT) == []
    assert story.applied(Kind.ANSWER) == []
    reports = [
        e
        for e in story.state.pending_events.values()
        if e.kind == Kind.REPORT and e.status is EventStatus.PENDING
    ]
    assert {r.payload["faction_id"] for r in reports} == {"azure-cloud", "outer-court"}
    assert all(r.due_s >= deed.world_s + UNKNOWN_TRIP_S for r in reports)


def test_interrupted_sleep_the_guards_wake_the_player_the_moment_they_arrive():
    story = kill_then_brew()
    asleep_at = story.state.world_s

    played = story.play(step(8 * HOUR, "sleep"))

    guards = played.interrupted_by
    assert guards is not None and guards.kind == Kind.ANSWER
    assert guards.payload["target_id"] == "lin"
    assert (guards.payload["faction_id"], guards.payload["answer"]) == ("azure-cloud", "arrest")
    # The night was played in time order up to them, and the scene starts when they arrive.
    assert story.state.world_s == guards.due_s == guards.applied_s < asleep_at + 8 * HOUR
    times = [e.applied_s for e in played.fired]
    assert times == sorted(times)
    assert played.fired[-1].id == guards.id
    assert played.resolution.steps[0].interrupted
    assert played.resolution.steps[0].duration_s == guards.due_s - asleep_at
    # They came only once Wei's report reached them and they had made the trip.
    (report,) = story.applied(Kind.REPORT, faction_id="azure-cloud")
    assert guards.due_s - report.applied_s >= UNKNOWN_TRIP_S
    assert story.state.characters["lin"].location_id == "well"


# --- Phone witness (G6, W10) -----------------------------------------------------------------


def test_phone_witness_the_police_are_called_within_minutes_and_arrive_after_the_drive():
    story = Story(grounded_world())
    story.play(kill("carmine", "Luca shoots Carmine in the back booth"))
    shot_at = story.state.world_s
    (deed,) = story.state.deeds.values()
    assert deed.witness_ids == ["bartender"]

    # Luca waits at the bar; whatever comes for him on the way just starts a scene.
    while not story.applied(Kind.ANSWER, faction_id="police"):
        assert story.state.world_s < shot_at + 2 * HOUR, "the police never came"
        story.play(step(5 * MINUTE, "wait at the bar"))

    (report,) = story.applied(Kind.REPORT, faction_id="police")
    assert report.payload["witness_id"] == "bartender"
    assert report.applied_s - shot_at <= 3 * MINUTE  # got clear, then called
    (police,) = story.applied(Kind.ANSWER, faction_id="police")
    assert police.payload["answer"] == "arrest"
    drive = 12 * MINUTE
    assert police.applied_s == police.due_s >= report.applied_s + 3 * MINUTE + drive
    assert police.needs_player  # Luca was still there


# --- Idle world (W6, E2, K8) -----------------------------------------------------------------


def test_idle_world_every_faction_and_key_npc_does_something_in_100_days():
    state = grounded_world()
    after, turn, fired = state, 1, []
    # Luca idles at the bar; when something needs him, he lets it pass and idles on.
    while after.world_s < 100 * DAY:
        turn += 1
        passage = pipeline.catch_up(after, 100 * DAY, ctx(turn), rng(turn))
        ticks = [e for e in passage.fired if e.kind == Kind.TICK]
        assert len(ticks) <= MAX_TICKS_PER_PASSAGE  # a long skip costs a bounded number of ticks
        assert check_transition(after, passage.state) == []
        after = passage.state
        fired.extend(passage.fired)
    assert turn <= 4
    movers = {
        f.origin.ref_id
        for f in after.facts.values()
        if f.origin is not None and f.origin.kind is OriginKind.AGENDA
    }
    active_factions = {
        f.id
        for f in after.factions.values()
        if f.activity is Activity.ACTIVE and f.status is not FactionStatus.DESTROYED
    }
    key_npcs = {
        c.id
        for c in after.npcs()
        if c.alive and c.prominence is Prominence.KEY and c.activity is Activity.ACTIVE
    }
    assert active_factions == {"esposito", "carmine-crew", "police"}
    assert key_npcs == {"carmine"}
    assert active_factions | key_npcs <= movers
    # The council met on its own time, at Carmine's bar where Luca was idling, so it was a
    # scene; the mystery it belongs to stays open.
    assert after.clocks["council"].status is ClockStatus.ENDED
    council = after.pending_events["council-meets"]
    assert council.applied_s == 10 * DAY and council.needs_player
    assert not after.threads["revenge"].status.closed


# --- Ignored hook (E2, N5) -------------------------------------------------------------------


def test_ignored_hook_the_tournament_happens_without_the_player():
    story = Story(cultivation_world())

    for _ in range(20):
        story.play(step(3 * HOUR, "cultivate in seclusion"))

    clock = story.state.clocks["tournament"]
    assert clock.status is ClockStatus.ENDED and clock.filled == 3
    thread = story.state.threads["tournament"]
    assert thread.status is ThreadStatus.RESOLVED_WITHOUT_PLAYER
    steps = sorted(
        (f for f in story.state.facts.values() if f.origin and f.origin.ref_id == "tournament"),
        key=lambda f: f.world_s,
    )
    assert [(f.world_s, f.text.split(": ")[1]) for f in steps] == [
        (16 * HOUR, "Names are posted."),
        (32 * HOUR, "The brackets are drawn."),
        (48 * HOUR, "The tournament begins."),
    ]
    assert all("lin" in f.known_by for f in steps)
    (end,) = story.applied(Kind.CLOCK_END)
    assert end.applied_s == 48 * HOUR and not end.needs_player
    # Word of it goes round.
    assert any(r.text.endswith("The tournament begins.") for r in story.state.rumors.values())
