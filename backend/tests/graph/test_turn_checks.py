"""The code checks that run before narration (C5): intent, resolution (A2, R6) and plan."""

from engine.context import ContentPrefs, GoreLevel, ImageSetting, Rating, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    DirectorPlan,
    EventKind,
    EventSource,
    Harm,
    Intent,
    IntentStep,
    ItemChange,
    OutcomeClass,
    Peril,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
    Resolution,
    SceneEnd,
    ShowStrength,
    StateDelta,
    StepFacts,
    StepResolution,
    StopReason,
    SuggestionPlan,
    Theme,
)
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import CharacterStatus, DeathCertainty
from engine.state.records import (
    Goal,
    GoalStatus,
    Lead,
    LeadStatus,
    RollRecord,
    StepResult,
    ThreadStatus,
    Transfer,
)
from engine.state.sheet import LadderPosition
from engine.state.world import EventSize
from graph.turn.check import (
    ACTION_UNTOLD,
    CLOCK_SCENE_END,
    MAX_STEPS,
    check_intent,
    check_plan,
    check_resolution,
    check_told,
    check_update,
)
from graph.turn.outputs import NarratorOutput


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


def test_the_player_only_ever_plays_their_own_character():
    """A6: whoever the interpret step names as the actor, the player character acts."""
    state = cultivation_world()
    for actor, detail in (
        ("ghost", "the actor is not in the story, so the player character acts"),
        ("zhao", "the player plays only their own character (A6)"),
    ):
        checked = check_intent(Intent(actor_id=actor, steps=[step()]), state, "x")
        assert checked.intent.actor_id is None
        assert [(i.code, i.detail, i.subject) for i in checked.issues] == [
            ("not_the_player", detail, actor)
        ]
    checked = check_intent(Intent(actor_id="lin", steps=[step()]), state, "x")
    assert checked.intent.actor_id is None and checked.issues == []


def test_the_dead_never_act():
    """C1: a dead character can't be the actor, so the player character acts."""
    state = cultivation_world()
    zhao = state.characters["zhao"]
    zhao.status, zhao.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    checked = check_intent(Intent(actor_id="zhao", steps=[step()]), state, "x")
    assert checked.intent.actor_id is None
    assert [i.detail for i in checked.issues] == ["the actor is dead, so the player character acts"]


def test_unknown_targets_are_kept_as_words():
    state = cultivation_world()
    proposed = Intent(steps=[step(target_ids=["zhao", "senior-brother-jo"], targets=["a bucket"])])
    checked = check_intent(proposed, state, "x")
    assert checked.intent.steps[0].target_ids == ["zhao"]
    assert checked.intent.steps[0].targets == ["a bucket", "senior-brother-jo"]
    assert [i.code for i in checked.issues] == ["unknown_target"]
    assert proposed.steps[0].target_ids == ["zhao", "senior-brother-jo"]  # never mutated


def test_unknown_opposition_is_kept_as_words():
    facts = StepFacts(opposition_ids=["zhao", "troll"], opposition="a crowd")
    checked = check_intent(Intent(steps=[step(facts=facts)]), cultivation_world(), "x")
    assert checked.intent.steps[0].facts.opposition_ids == ["zhao"]
    assert checked.intent.steps[0].facts.opposition == "a crowd; troll"
    assert [i.code for i in checked.issues] == ["unknown_opposition"]


def test_a_time_of_day_that_cant_be_read_leaves_the_proposed_seconds():
    # W10: code counts "until" only from a time on the 24-hour clock.
    steps = [
        step(until="19:00"),
        step(until="when the bell rings"),
        step(until="  "),
    ]
    checked = check_intent(Intent(steps=steps), cultivation_world(), "x")
    assert [s.until for s in checked.intent.steps] == ["19:00", None, None]
    assert [i.code for i in checked.issues] == ["bad_until"]


def test_an_action_that_fits_nothing_still_becomes_a_step():
    checked = check_intent(Intent(), cultivation_world(), "  I sing to the moon ")
    assert [s.text for s in checked.intent.steps] == ["I sing to the moon"]
    assert checked.intent.summary == "I sing to the moon"
    assert [i.code for i in checked.issues] == ["no_step"]


def test_a_standing_action_needs_no_step():
    checked = check_intent(Intent(standing="wait"), cultivation_world(), "wait")
    assert checked.intent.steps == [] and checked.issues == []


def test_steps_past_the_limit_are_handed_back():
    """R6: a run-on plan longer than a scene can play keeps its first steps; the rest come back
    unplayed, never silently dropped."""
    steps = [step(f"s{i}") for i in range(MAX_STEPS + 3)]
    checked = check_intent(Intent(steps=steps), cultivation_world(), "x")
    assert len(checked.intent.steps) == MAX_STEPS
    assert checked.overflow == [f"s{i}" for i in range(MAX_STEPS, MAX_STEPS + 3)]
    assert [i.code for i in checked.issues] == ["too_many_steps"]
    resolution, _ = check_resolution(Resolution(steps=[resolved(0)]), checked.overflow)
    assert resolution.unplayed == checked.overflow


def hidden_expert():
    """Lin at Core Formation, passing for Qi Condensation."""
    state = cultivation_world()
    state.player.sheet.ladders = [LadderPosition(ladder_id="realms", rung=2, shown_rung=0)]
    return state


def test_a_blow_that_also_shows_strength_is_two_steps():
    """G20: code settles a show of strength for certain, so one read into a blow would land
    the blow with no throw. The show comes first, as its own step, and the blow is thrown."""
    reveal = ShowStrength(ladder_id="realms")
    blow = step(
        "let my cultivation show and strike Zhao down",
        target_ids=["zhao"],
        aim=Aim.WOUND,
        facts=StepFacts(opposition_ids=["zhao"], crowd=True),
        show_strength=reveal,
    )
    checked = check_intent(Intent(steps=[blow, step("walk off")]), hidden_expert(), "x")
    show, strike, rest = checked.intent.steps
    assert (show.verb, show.kind, show.show_strength) == ("reveal", ActionKind.INSTANT, reveal)
    assert show.aim is Aim.NONE and show.target_ids == [] and show.facts.crowd is True
    assert strike.show_strength is None and strike.aim is Aim.WOUND
    assert strike.target_ids == ["zhao"] and rest.text == "walk off"
    assert [i.code for i in checked.issues] == ["show_apart"]
    # Hiding while they strike is the same: the hiding first.
    hide = blow.model_copy(update={"show_strength": ShowStrength(ladder_id="realms", shown_rung=1)})
    checked = check_intent(Intent(steps=[hide]), hidden_expert(), "x")
    assert [s.verb for s in checked.intent.steps] == ["hide", "throw"]


def test_a_show_with_nothing_to_change_is_left_out_of_a_step_that_does_something_else():
    """G20: a reveal with nothing hidden, or of a strength they don't have, read into a blow
    is no reveal: the blow plays as what it is."""
    blow = step(target_ids=["zhao"], aim=Aim.WOUND, show_strength=ShowStrength(ladder_id="realms"))
    checked = check_intent(Intent(steps=[blow]), cultivation_world(), "x")
    [strike] = checked.intent.steps
    assert strike.show_strength is None and strike.aim is Aim.WOUND
    assert [i.code for i in checked.issues] == ["idle_show"]
    nobody = cultivation_world()
    nobody.player.sheet.ladders = []
    checked = check_intent(Intent(steps=[blow]), nobody, "x")
    assert checked.intent.steps[0].show_strength is None
    assert [i.code for i in checked.issues] == ["idle_show"]


def test_a_show_of_strength_alone_stays_as_read_and_one_on_no_ladder_of_the_world_is_none():
    """G20: a step that only hides or shows strength is code's to settle as before. A ladder
    the world doesn't have is a show of nothing, so the step plays without it."""
    hide = step("hide my cultivation", show_strength=ShowStrength(ladder_id="realms", shown_rung=0))
    checked = check_intent(Intent(steps=[hide]), cultivation_world(), "x")
    assert checked.intent.steps == [hide] and checked.issues == []
    odd = step("walk on", show_strength=ShowStrength(ladder_id="levels"))
    checked = check_intent(Intent(steps=[odd]), cultivation_world(), "x")
    assert checked.intent.steps[0].show_strength is None
    assert [i.code for i in checked.issues] == ["unknown_ladder"]


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


def test_a_certain_step_keeps_the_roll_that_only_picked_how_long_it_took():
    """W10: an uncertain duration is rolled even when the outcome is certain."""
    timed = RollRecord(seed="seed", odds=1.0, value=0.3, result=StepResult.SUCCESS, duration_s=5400)
    resolution = Resolution(steps=[resolved(0, roll=timed)])
    checked, issues = check_resolution(resolution)
    assert checked == resolution and issues == []

    # A roll that could have changed the outcome still goes.
    outcome = Resolution(steps=[resolved(0, roll=roll(StepResult.SUCCESS))])
    checked, issues = check_resolution(outcome)
    assert checked.steps[0].roll is None
    assert [i.code for i in issues] == ["class_result_mismatch"]


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
        steps=[
            resolved(0, StepResult.PARTIAL, OutcomeClass.CONTESTED, roll=roll(StepResult.PARTIAL)),
            resolved(1),
        ]
    )
    assert check_resolution(partial)[0].stop_reason is StopReason.PARTIAL
    ruled_out = Resolution(
        steps=[resolved(0, StepResult.FAILURE, OutcomeClass.RULED_OUT), resolved(1)]
    )
    assert check_resolution(ruled_out)[0].stop_reason is StopReason.RULED_OUT


def test_a_plan_stops_where_something_struck_back_and_hurt_the_character():
    """N6: the throw hit, but Zhao's answer cut Lin, so the run waits for the player."""

    def struck(harm: Harm) -> Peril:
        return Peril(
            by_ids=["zhao"],
            by="Zhao",
            aim=Aim.WOUND,
            outcome_class=OutcomeClass.CONTESTED,
            reason="Zhao strikes back",
            result=StepResult.SUCCESS if harm is not Harm.NONE else StepResult.FAILURE,
            harm=harm,
        )

    hurt = Resolution(steps=[resolved(0, perils=[struck(Harm.WOUNDED)]), resolved(1)])
    checked, issues = check_resolution(hurt)
    assert (checked.stopped_at_step, checked.stop_reason) == (0, StopReason.STRUCK)
    assert [i.code for i in issues] == ["plan_not_stopped"]
    missed = Resolution(steps=[resolved(0, perils=[struck(Harm.NONE)]), resolved(1)])
    assert check_resolution(missed) == (missed, [])


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


def test_only_open_threads_the_player_knows_and_open_leads_can_be_taken_up():
    """W16, N1, N2: what the action takes up is checked against the state."""
    state = grounded_world()
    state.leads["lead-1"] = Lead(id="lead-1", text="A job at the docks")
    state.leads["lead-2"] = Lead(id="lead-2", text="Gone", status=LeadStatus.EXPIRED)
    state.threads["secret"] = state.threads["revenge"].model_copy(
        update={"id": "secret", "known_by": []}
    )
    state.threads["over"] = state.threads["revenge"].model_copy(
        update={"id": "over", "status": ThreadStatus.RESOLVED}
    )
    proposed = Intent(
        steps=[step()],
        responds_to=["revenge", "lead-1", "revenge", "lead-2", "secret", "over", "ghost"],
    )
    checked = check_intent(proposed, state, "x")
    assert checked.intent.responds_to == ["revenge", "lead-1"]
    dropped = [i.subject for i in checked.issues if i.code == "unknown_response"]
    assert dropped == ["lead-2", "secret", "over", "ghost"]


def test_only_the_characters_active_goals_can_be_dropped():
    """N2: the goals the player drops are checked against the state."""
    state = grounded_world()
    state.goals["goal-2"] = Goal(id="goal-2", text="Leave", status=GoalStatus.ACHIEVED)
    proposed = Intent(steps=[step()], dropped_goals=["find-killer", "goal-2", "find-killer", "x"])
    checked = check_intent(proposed, state, "x")
    assert checked.intent.dropped_goals == ["find-killer"]
    assert [i.subject for i in checked.issues if i.code == "unknown_goal"] == ["goal-2", "x"]


# check_plan


def portrait(subject: str | None, trigger=PictureTrigger.FIRST_MEETING) -> DirectorPlan:
    return DirectorPlan(
        picture=PictureDecision(kind=PictureKind.PORTRAIT, trigger=trigger, subject_id=subject)
    )


def event(**extra) -> PlannedEvent:
    extra.setdefault("title", "A stranger")
    return PlannedEvent(
        size=EventSize.LOCAL,
        kind=EventKind.ARRIVAL,
        source=EventSource.DECK,
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


def test_a_fights_decisive_blow_can_picture_the_foe_it_killed():
    state = cultivation_world()
    zhao = state.characters["zhao"]
    zhao.status, zhao.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    blow = DirectorPlan(
        picture=PictureDecision(
            kind=PictureKind.SCENE, trigger=PictureTrigger.DECISIVE_BLOW, subject_id="zhao"
        )
    )
    assert check_plan(state, blow, ctx())[0].picture is not None


def test_an_arc_or_event_picture_can_name_its_thread():
    arc = DirectorPlan(
        picture=PictureDecision(
            kind=PictureKind.SCENE, trigger=PictureTrigger.ARC_END, subject_id="tournament"
        )
    )
    assert check_plan(cultivation_world(), arc, ctx())[0].picture is not None


def test_a_picture_of_nothing_is_dropped():
    assert check_plan(cultivation_world(), portrait("nobody"), ctx())[0].picture is None
    assert check_plan(cultivation_world(), portrait("well"), ctx())[0].picture is not None


def test_events_only_start_themes_the_player_allows():
    """F7, F2, F3."""
    state = grounded_world()  # Luca is 24
    romance = DirectorPlan(event=event(themes=[Theme.ROMANCE]))
    assert check_plan(state, romance, ctx())[0].event is not None
    off = ctx(prefs=ContentPrefs(romance=False))
    plan, issues = check_plan(state, romance, off)
    assert plan.event is None and [i.code for i in issues] == ["event_dropped"]
    # F3: no romance event for a player character who isn't a recorded adult (Lin is 16).
    assert check_plan(cultivation_world(), romance, ctx())[0].event is None
    state = cultivation_world()

    gore = DirectorPlan(event=event(themes=[Theme.GORE]))
    assert check_plan(state, gore, ctx())[0].event is None  # Teen has no gore
    assert check_plan(state, gore, ctx(rating=Rating.MATURE))[0].event is not None
    low = ctx(rating=Rating.MATURE, prefs=ContentPrefs(gore=GoreLevel.LOW))
    assert check_plan(state, gore, low)[0].event is None

    dark = DirectorPlan(event=event(themes=[Theme.DARK]))
    assert check_plan(state, dark, ctx(prefs=ContentPrefs(dark_themes=False)))[0].event is None


def test_happenings_carry_only_themes_the_player_allows():
    dark = event(title="A body in the river", themes=[Theme.DARK])
    plan = DirectorPlan(happenings=[event(title="A good harvest"), dark])
    checked, issues = check_plan(grounded_world(), plan, ctx(prefs=ContentPrefs(dark_themes=False)))
    assert [h.title for h in checked.happenings] == ["A good harvest"]
    assert [i.code for i in issues] == ["happening_dropped"]


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
    # An NPC's or a faction's plans are the source of an agenda event (W16, E3).
    for source in ("zhao", "outer-court"):
        kept, issues = check_plan(
            cultivation_world(), DirectorPlan(event=event(source_id=source)), ctx()
        )
        assert kept.event.source_id == source and issues == []


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


def test_a_rolled_step_is_decided_by_its_roll():
    """A3: a contested step's result is its roll's."""
    step0 = resolved(0, StepResult.SUCCESS, OutcomeClass.CONTESTED, roll=roll(StepResult.FAILURE))
    checked, issues = check_resolution(Resolution(steps=[step0]))
    assert checked.steps[0].result is StepResult.FAILURE
    assert [i.code for i in issues] == ["roll_result_mismatch"]
    unrolled = resolved(0, StepResult.SUCCESS, OutcomeClass.LONG_SHOT)
    checked, issues = check_resolution(Resolution(steps=[unrolled]))
    assert checked.steps[0].result is StepResult.SUCCESS
    assert [i.code for i in issues] == ["unrolled"]


def test_a_moved_stop_takes_the_reason_of_the_step_it_stops_at():
    resolution = Resolution(
        steps=[
            resolved(0, StepResult.FAILURE, OutcomeClass.RULED_OUT),
            resolved(1),
            resolved(2),
        ],
        stopped_at_step=2,
        stop_reason=StopReason.INTERRUPTED,
    )
    checked, _ = check_resolution(resolution)
    assert checked.stopped_at_step == 0
    assert checked.stop_reason is StopReason.RULED_OUT


# check_update


def test_the_scene_end_keeps_its_last_moment_and_leaves_out_the_dead():
    state = grounded_world()
    bartender = state.characters["bartender"]
    bartender.status, bartender.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    delta = StateDelta(
        scene_end=SceneEnd(ended_on="  ", present_ids=["luca", "bartender", "new_guard"]),
        summary="   ",
    )
    checked, issues = check_update(delta, state)
    assert checked.scene_end.ended_on == state.scene.ended_on
    assert checked.scene_end.present_ids == ["luca", "new_guard"]
    assert checked.summary is None
    assert [i.code for i in issues] == ["blank_scene_end", "dead_present"]
    assert delta.scene_end.present_ids == ["luca", "bartender", "new_guard"]  # never mutated


def test_a_scene_end_that_gives_only_the_time_takes_the_scenes_last_sentence():
    """R3: in a live story (2026-11-11) a scene ended on "Day 1, morning, 07:00", so the next
    reading had no last moment to go by and aimed a blow at a bystander."""
    state = grounded_world()
    told = 'You bow. "Again," says the bartender, and he sets the glass down in front of you.'
    for clock in ("Day 1, morning, 07:00", "Día 1, mañana", "19:30"):
        delta = StateDelta(scene_end=SceneEnd(ended_on=clock, present_ids=["luca"]))
        checked, issues = check_update(delta, state, told=told)
        assert checked.scene_end.ended_on == (
            '"Again," says the bartender, and he sets the glass down in front of you.'
        )
        assert [i.code for i in issues] == [CLOCK_SCENE_END]
    # With no scene text to go by, it is as good as blank: the last moment stands.
    delta = StateDelta(scene_end=SceneEnd(ended_on="Day 1, morning, 07:00"))
    checked, issues = check_update(delta, state)
    assert checked.scene_end.ended_on == state.scene.ended_on
    assert [i.code for i in issues] == [CLOCK_SCENE_END, "blank_scene_end"]
    # A moment that says what is happening stands, whatever hour it mentions.
    delta = StateDelta(scene_end=SceneEnd(ended_on="At dusk the bartender locks the door."))
    checked, issues = check_update(delta, state, told=told)
    assert checked.scene_end.ended_on == "At dusk the bartender locks the door."
    assert issues == []


def test_a_scene_the_player_acted_in_must_tell_the_action():
    """R1: reported, never repaired, since the scene has already streamed (S3)."""
    paid = Intent(summary="pay the herbalist")
    skipped = NarratorOutput(narration="Old Hu snatches the coin.")
    told = NarratorOutput(action="You hold out the coin.", narration="Old Hu snatches it.")
    assert [i.code for i in check_told(skipped, paid)] == [ACTION_UNTOLD]
    assert check_told(NarratorOutput(action="  ", narration="x"), paid)[0].code == ACTION_UNTOLD
    assert check_told(told, paid) == []
    # An opening, or an ending told from things as they stand, has no action to tell.
    assert check_told(skipped, None) == []


def test_a_payment_a_step_already_made_is_never_made_again_by_the_scene():
    # C10: the step moved the coins before narration; the narrator telling it again would pay
    # twice. What else changed hands in the scene still applies.
    paid = Transfer(
        name="copper coins",
        quantity=5,
        money=True,
        currency="copper coins",
        from_id="luca",
        to_id="carmine",
        turn=1,
    )
    thrown = Transfer(
        name="flick knife", quantity=1, item_id="knife", from_id="luca", to_id=None, turn=1
    )
    told = ItemChange(name="5 copper coins", from_id="luca", to_id="carmine")
    knife = ItemChange(name="the knife", from_id="luca", to_id="World")
    key = ItemChange(name="a brass key", from_id="carmine", to_id="luca")
    more = ItemChange(name="coins", money=True, quantity=9, from_id="luca", to_id="carmine")
    delta = StateDelta(items=[told, knife, key, more])

    checked, issues = check_update(delta, grounded_world(), [paid, thrown])

    assert checked.items == [key, more]
    assert [i.code for i in issues] == ["move_recorded"]
    assert check_update(delta, grounded_world())[0].items == [told, knife, key, more]
