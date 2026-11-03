"""The code checks that run before narration (C5): intent, resolution (A2, R6) and plan."""

from engine.context import ContentPrefs, GoreLevel, ImageSetting, Rating, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    DirectorPlan,
    EventKind,
    EventSource,
    Intent,
    IntentStep,
    OutcomeClass,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
    Resolution,
    StepResolution,
    StopReason,
    SuggestionPlan,
    Theme,
)
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import CharacterStatus, DeathCertainty
from engine.state.records import RollRecord, StepResult, ThreadStatus
from engine.state.world import EventSize
from graph.turn.check import MAX_STEPS, check_intent, check_plan, check_resolution


def ctx(**settings) -> TurnContext:
    rating = settings.pop("rating", Rating.TEEN)
    prefs = settings.pop("prefs", ContentPrefs())
    return TurnContext(
        story_id="s", turn=1, settings=StorySettings(**settings), rating=rating, content_prefs=prefs
    )


def step(text: str = "throw", **extra) -> IntentStep:
    return IntentStep(
        text=text, verb="throw", kind=ActionKind.EXCHANGE, proposed_duration_s=2, **extra
    )


def resolved(index: int, result=StepResult.SUCCESS, cls=OutcomeClass.CERTAIN, **extra):
    return StepResolution(
        index=index,
        text=f"step {index}",
        outcome_class=cls,
        reason="because",
        result=result,
        duration_s=2,
        **extra,
    )


def roll(result=StepResult.FAILURE) -> RollRecord:
    return RollRecord(seed="seed", odds=0.4, value=0.7, result=result)


# check_intent


def test_unknown_or_player_actor_becomes_the_player():
    state = cultivation_world()
    intent, issues = check_intent(Intent(actor_id="ghost", steps=[step()]), state, "x")
    assert intent.actor_id is None
    assert [i.code for i in issues] == ["unknown_actor"]
    intent, issues = check_intent(Intent(actor_id="lin", steps=[step()]), state, "x")
    assert intent.actor_id is None and issues == []


def test_unknown_targets_are_kept_as_words():
    state = cultivation_world()
    proposed = Intent(steps=[step(target_ids=["zhao", "senior-brother-jo"], targets=["a bucket"])])
    intent, issues = check_intent(proposed, state, "x")
    assert intent.steps[0].target_ids == ["zhao"]
    assert intent.steps[0].targets == ["a bucket", "senior-brother-jo"]
    assert [i.code for i in issues] == ["unknown_target"]
    assert proposed.steps[0].target_ids == ["zhao", "senior-brother-jo"]  # never mutated


def test_an_action_that_fits_nothing_still_becomes_a_step():
    intent, issues = check_intent(Intent(), cultivation_world(), "  I sing to the moon ")
    assert [s.text for s in intent.steps] == ["I sing to the moon"]
    assert intent.summary == "I sing to the moon"
    assert [i.code for i in issues] == ["no_step"]


def test_a_standing_action_needs_no_step():
    intent, issues = check_intent(Intent(standing="wait"), cultivation_world(), "wait")
    assert intent.steps == [] and issues == []


def test_too_many_steps_are_cut():
    intent, issues = check_intent(
        Intent(steps=[step(f"s{i}") for i in range(MAX_STEPS + 3)]), cultivation_world(), "x"
    )
    assert len(intent.steps) == MAX_STEPS
    assert [i.code for i in issues] == ["too_many_steps"]


# check_resolution


def test_a_clean_plan_passes_untouched():
    resolution = Resolution(steps=[resolved(0), resolved(1)])
    checked, issues = check_resolution(resolution)
    assert checked == resolution and issues == []


def test_the_class_wins_over_a_result_that_contradicts_it():
    """A2: no roll can overturn a certain or ruled-out step."""
    resolution = Resolution(
        steps=[
            resolved(0, StepResult.FAILURE, OutcomeClass.CERTAIN, roll=roll()),
        ]
    )
    checked, issues = check_resolution(resolution)
    assert checked.steps[0].result is StepResult.SUCCESS
    assert checked.steps[0].roll is None
    assert [i.code for i in issues] == ["class_result_mismatch"]

    ruled_out = Resolution(steps=[resolved(0, StepResult.SUCCESS, OutcomeClass.RULED_OUT)])
    checked, _ = check_resolution(ruled_out)
    assert checked.steps[0].result is StepResult.FAILURE


def test_a_chained_plan_stops_at_its_first_step_that_doesnt_cleanly_succeed():
    """R6: the stone misses, so the run for the tunnel never happens."""
    resolution = Resolution(
        steps=[
            resolved(0),
            resolved(1, StepResult.FAILURE, OutcomeClass.CONTESTED, roll=roll()),
            resolved(2),
        ],
        unplayed=["later"],
    )
    checked, issues = check_resolution(resolution)
    assert [s.index for s in checked.steps] == [0, 1]
    assert checked.stopped_at_step == 1
    assert checked.stop_reason is StopReason.FAILED
    assert checked.unplayed == ["step 2", "later"]
    assert [i.code for i in issues] == ["plan_not_stopped"]


def test_stop_reasons_follow_the_step():
    partial = Resolution(
        steps=[resolved(0, StepResult.PARTIAL, OutcomeClass.CONTESTED, roll=roll()), resolved(1)]
    )
    assert check_resolution(partial)[0].stop_reason is StopReason.PARTIAL
    ruled_out = Resolution(
        steps=[resolved(0, StepResult.FAILURE, OutcomeClass.RULED_OUT), resolved(1)]
    )
    assert check_resolution(ruled_out)[0].stop_reason is StopReason.RULED_OUT


def test_a_declared_stop_with_steps_after_it_is_enforced():
    resolution = Resolution(
        steps=[resolved(0), resolved(1)], stopped_at_step=0, stop_reason=StopReason.INTERRUPTED
    )
    checked, issues = check_resolution(resolution)
    assert [s.index for s in checked.steps] == [0]
    assert checked.stop_reason is StopReason.INTERRUPTED
    assert checked.unplayed == ["step 1"]


def test_a_correct_stop_raises_no_issue():
    resolution = Resolution(
        steps=[resolved(0, StepResult.FAILURE, OutcomeClass.CONTESTED, roll=roll())],
        stopped_at_step=0,
        stop_reason=StopReason.FAILED,
        unplayed=["run for the tunnel"],
    )
    checked, issues = check_resolution(resolution)
    assert checked == resolution and issues == []


def test_a_stop_naming_no_step_is_cleared():
    checked, issues = check_resolution(Resolution(steps=[resolved(0)], stopped_at_step=4))
    assert checked.stopped_at_step is None
    assert [i.code for i in issues] == ["bad_stop"]


# check_plan


def portrait(subject: str | None, trigger=PictureTrigger.FIRST_MEETING) -> DirectorPlan:
    return DirectorPlan(
        picture=PictureDecision(kind=PictureKind.PORTRAIT, trigger=trigger, subject_id=subject)
    )


def event(**extra) -> PlannedEvent:
    return PlannedEvent(
        size=EventSize.LOCAL,
        kind=EventKind.ARRIVAL,
        source=EventSource.DECK,
        title="A stranger",
        brief="Someone arrives.",
        **extra,
    )


def test_pictures_switched_off_are_dropped():
    plan, issues = check_plan(cultivation_world(), portrait("zhao"), ctx(images=ImageSetting.OFF))
    assert plan.picture is None
    assert [i.code for i in issues] == ["picture_dropped"]


def test_a_dead_subject_is_drawn_only_for_their_death():
    state = cultivation_world()
    zhao = state.characters["zhao"]
    zhao.status, zhao.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    assert check_plan(state, portrait("zhao"), ctx())[0].picture is None
    death = portrait("zhao", PictureTrigger.DEATH)
    assert check_plan(state, death, ctx())[0].picture is not None


def test_a_picture_of_nothing_is_dropped():
    assert check_plan(cultivation_world(), portrait("nobody"), ctx())[0].picture is None
    assert check_plan(cultivation_world(), portrait("well"), ctx())[0].picture is not None


def test_events_only_start_themes_the_player_allows():
    """F7, F2."""
    state = cultivation_world()
    romance = DirectorPlan(event=event(themes=[Theme.ROMANCE]))
    assert check_plan(state, romance, ctx())[0].event is not None
    off = ctx(prefs=ContentPrefs(romance=False))
    plan, issues = check_plan(state, romance, off)
    assert plan.event is None and [i.code for i in issues] == ["event_dropped"]

    gore = DirectorPlan(event=event(themes=[Theme.GORE]))
    assert check_plan(state, gore, ctx())[0].event is None  # Teen has no gore
    assert check_plan(state, gore, ctx(rating=Rating.MATURE))[0].event is not None
    low = ctx(rating=Rating.MATURE, prefs=ContentPrefs(gore=GoreLevel.LOW))
    assert check_plan(state, gore, low)[0].event is None

    dark = DirectorPlan(event=event(themes=[Theme.DARK]))
    assert check_plan(state, dark, ctx(prefs=ContentPrefs(dark_themes=False)))[0].event is None


def test_an_events_unknown_references_are_cleared():
    plan, issues = check_plan(
        cultivation_world(),
        DirectorPlan(event=event(thread_id="nope", source_id="nope")),
        ctx(),
    )
    assert plan.event.thread_id is None and plan.event.source_id is None
    assert {i.code for i in issues} == {"unknown_thread", "unknown_source"}
    kept, _ = check_plan(
        cultivation_world(), DirectorPlan(event=event(thread_id="tournament")), ctx()
    )
    assert kept.event.thread_id == "tournament"


def test_callbacks_pull_in_only_open_or_dormant_threads():
    state = grounded_world()
    revenge = state.threads["revenge"]
    state.threads["old-debt"] = revenge.model_copy(
        update={"id": "old-debt", "status": ThreadStatus.DORMANT}
    )
    revenge.status = ThreadStatus.RESOLVED
    plan, issues = check_plan(state, DirectorPlan(callbacks=["revenge", "old-debt"]), ctx())
    assert plan.callbacks == ["old-debt"]
    assert [i.subject for i in issues] == ["revenge"]
    plan, issues = check_plan(state, DirectorPlan(callbacks=["nope"]), ctx())
    assert plan.callbacks == [] and [i.subject for i in issues] == ["nope"]


def test_suggestions_follow_the_players_setting():
    plan, _ = check_plan(cultivation_world(), DirectorPlan(), ctx(suggestions=False))
    assert plan.suggestions == SuggestionPlan(count=0, kinds=[])
