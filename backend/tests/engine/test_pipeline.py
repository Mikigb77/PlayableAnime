from engine import pipeline
from engine.base import HOUR
from engine.context import ImageSetting, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Intent,
    IntentStep,
    OutcomeClass,
    PictureTrigger,
    ProposedDeed,
    Resolution,
    StandingAction,
    StepResolution,
)
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import EventStatus, PendingEvent, Ruling, StepResult, Visibility
from engine.timekeeping import DURATION_BOUNDS, bound_duration


def ctx(turn: int = 2, **settings) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings(**settings))


def rng() -> SeededRng:
    return SeededRng.for_turn("s1", "main", 2)


def step(text: str, kind: ActionKind, duration_s: int, **kwargs) -> IntentStep:
    return IntentStep(text=text, verb=text, kind=kind, proposed_duration_s=duration_s, **kwargs)


def settled(index: int, duration_s: int, **kwargs) -> StepResolution:
    return StepResolution(
        index=index,
        text=f"step {index}",
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=duration_s,
        **kwargs,
    )


def test_duration_bounds_cover_every_kind_and_hold():
    assert set(DURATION_BOUNDS) == set(ActionKind)
    assert bound_duration(ActionKind.EXCHANGE, 3 * HOUR) == 120
    assert bound_duration(ActionKind.REST, 8 * HOUR) == 8 * HOUR
    assert bound_duration(ActionKind.CONVERSATION, 0) == 10
    assert bound_duration(ActionKind.EXCHANGE, 5, world_frozen=True) == 0


def test_default_resolve_succeeds_every_step_within_its_bounds():
    intent = Intent(
        steps=[
            step("throw the stone", ActionKind.EXCHANGE, 2),
            step("sleep", ActionKind.REST, 400 * HOUR),
        ]
    )

    resolution = pipeline.resolve(cultivation_world(), intent, ctx(), rng())

    assert [s.outcome_class for s in resolution.steps] == [OutcomeClass.CERTAIN] * 2
    assert [s.result for s in resolution.steps] == [StepResult.SUCCESS] * 2
    assert [s.duration_s for s in resolution.steps] == [2, 48 * HOUR]


def test_default_resolve_turns_a_standing_action_into_a_step():
    resolution = pipeline.resolve(
        grounded_world(), Intent(standing=StandingAction.WAIT), ctx(), rng()
    )

    assert len(resolution.steps) == 1
    assert resolution.steps[0].duration_s == 60


def test_play_out_moves_the_world_clock_and_times_each_step():
    state = grounded_world()
    resolution = Resolution(steps=[settled(0, 5), settled(1, 8 * HOUR)])

    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert played.state.world_s == 5 + 8 * HOUR
    assert [(s.start_s, s.end_s) for s in played.resolution.steps] == [(0, 5), (5, 5 + 8 * HOUR)]
    assert played.state.player.personal_s(played.state.world_s) == played.state.world_s
    assert state.world_s == 0  # the input state is never changed


def test_in_a_time_stop_only_the_users_clock_runs():
    # "World: +0 s. Lin Feng: +3 heartbeats." (G3, W10a)
    resolution = Resolution(steps=[settled(0, 0, personal_s=1), settled(1, 0, personal_s=2)])

    played = pipeline.play_out(cultivation_world(), resolution, ctx(), rng())

    assert played.state.world_s == 0
    assert played.state.player.personal_s(played.state.world_s) == 3
    assert played.state.characters["zhao"].personal_s(played.state.world_s) == 0


def test_play_out_records_each_steps_deeds_at_its_end_time():
    resolution = Resolution(
        steps=[
            settled(0, 30),
            settled(
                1,
                5,
                deeds=[
                    ProposedDeed(
                        kind="shoot",
                        text="Shot Carmine in the shoulder.",
                        victim_ids=["carmine"],
                        severity=4,
                        witness_ids=["bartender"],
                    )
                ],
            ),
        ]
    )

    played = pipeline.play_out(grounded_world(), resolution, ctx(turn=7), rng())

    (deed,) = played.state.deeds.values()
    assert (deed.id, deed.actor_id, deed.turn, deed.world_s) == ("deed-1", "luca", 7, 35)
    assert deed.place_id == "bar"
    assert deed.visibility is Visibility.WITNESSED
    assert deed.known_by == ["luca", "bartender"]


def test_play_out_records_a_ruling_once_and_never_flips_it():
    def ruling(answer: str, holds: bool) -> Ruling:
        return Ruling(
            id=answer,
            topic="throw_speed",
            power_id="time-stop",
            question="Does a stopped-time throw land at light speed?",
            answer=answer,
            holds=holds,
        )

    first = pipeline.play_out(
        cultivation_world(), Resolution(rulings=[ruling("No.", False)]), ctx(), rng()
    )
    again = pipeline.play_out(first.state, Resolution(rulings=[ruling("Yes.", True)]), ctx(), rng())

    assert [r.answer for r in again.state.player.sheet.rulings] == ["No."]


def test_default_catch_up_and_apply_event():
    state = grounded_world()

    passage = pipeline.catch_up(state, state.world_s, ctx(), rng())
    fired = pipeline.apply_event(state, state.pending_events["council-meets"], ctx(), rng())

    assert passage.state is state and passage.elapsed_s == 0 and passage.fired == ()
    assert fired.pending_events["council-meets"].status is EventStatus.FIRED
    assert fired.pending_events["council-meets"].fired_turn == 2
    assert state.pending_events["council-meets"].status is EventStatus.PENDING


def test_default_director_plans_the_opening_portrait_and_suggestions():
    state = cultivation_world()
    nothing = Resolution()

    opening = pipeline.direct(state, nothing, ctx(turn=1), rng())
    later = pipeline.direct(state, nothing, ctx(turn=5), rng())
    quiet = pipeline.direct(
        state, nothing, ctx(turn=1, images=ImageSetting.OFF, suggestions=False), rng()
    )

    assert opening.picture.trigger is PictureTrigger.STORY_START
    assert opening.picture.subject_id == "lin"
    assert later.picture is None and later.event is None
    assert opening.suggestions.count == 3
    assert quiet.picture is None
    assert quiet.suggestions.count == 0 and quiet.suggestions.kinds == []


def test_seams_never_change_their_input_state():
    state = grounded_world()
    before = state.model_dump()
    resolution = Resolution(
        steps=[settled(0, 5, deeds=[ProposedDeed(kind="threaten", text="Threatened Gennaro.")])]
    )

    pipeline.play_out(state, resolution, ctx(), rng())
    pipeline.apply_event(state, PendingEvent(id="council-meets", kind="x", due_s=0), ctx(), rng())

    assert state.model_dump() == before
