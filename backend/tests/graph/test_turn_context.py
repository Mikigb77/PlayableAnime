"""What the model nodes read: the interpret prompt and the narrator's brief (B5 step 4)."""

from engine.context import (
    ContentPrefs,
    GoreLevel,
    NarrationLength,
    Rating,
    StorySettings,
    TurnContext,
)
from engine.contracts import (
    ChoiceKind,
    DirectorPlan,
    EventKind,
    EventSource,
    Intent,
    OutcomeClass,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
    Resolution,
    StepResolution,
    StopReason,
    SuggestionPlan,
)
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import CharacterStatus, DeathCertainty
from engine.state.records import PendingEvent, StepResult
from engine.state.sheet import Power
from engine.state.world import EventSize
from graph.turn import prompts
from graph.turn.context import (
    RECENT_SCENES,
    chapter_prompt,
    interpret_prompt,
    narration_brief,
    present_characters,
)
from graph.turn.outputs import NarratorOutput, SuggestionOut
from graph.turn.scene import choices, fallback_prompt
from graph.turn.types import PastScene

SECRET = "He ordered the killing of Luca's father."
MYSTERY_ANSWER = "Carmine Russo, the underboss."


def ctx(turn=2, rating=Rating.TEEN, **settings) -> TurnContext:
    prefs = settings.pop("prefs", ContentPrefs())
    return TurnContext(
        story_id="s",
        turn=turn,
        rating=rating,
        content_prefs=prefs,
        settings=StorySettings(**settings),
    )


def brief(state=None, *, intent=None, resolution=None, plan=None, scenes=(), **kwargs):
    state = state or grounded_world()
    return narration_brief(
        before=state,
        after=kwargs.pop("after", state),
        ctx=kwargs.pop("context", ctx()),
        intent=intent,
        resolution=resolution or Resolution(),
        plan=plan or DirectorPlan(),
        fired=(),
        scenes=scenes,
        **kwargs,
    )


def stopped_plan() -> Resolution:
    return Resolution(
        steps=[
            StepResolution(
                index=0,
                text="throw the stone",
                outcome_class=OutcomeClass.CONTESTED,
                reason="The troll's hide is thick.",
                result=StepResult.FAILURE,
                duration_s=2,
            )
        ],
        stopped_at_step=0,
        stop_reason=StopReason.FAILED,
        unplayed=["run for the tunnel"],
    )


def test_present_characters_are_living_and_known():
    state = grounded_world()
    assert [c.id for c in present_characters(state)] == ["carmine", "bartender"]
    bartender = state.characters["bartender"]
    bartender.status, bartender.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    state.scene.present_ids.append("nobody")
    assert [c.id for c in present_characters(state)] == ["carmine"]


def test_the_interpret_prompt_reads_the_scene_and_the_known_names():
    state = cultivation_world()
    prompt = interpret_prompt(state, "  I throw a stone at Senior Brother Jo ")
    text = prompt.messages[-1].text
    assert prompt.system == prompts.INTERPRET_SYSTEM
    assert "## ACTION\nI throw a stone at Senior Brother Jo" in text
    assert "Zhao grins and draws back his foot" in text  # the last moment (R3)
    assert '"aliases":["Senior Brother Zhao"]' in text  # misheard names map to ids (V3)
    assert '"tournament"' in text  # open threads, for what the action takes up


def test_the_interpret_step_is_asked_for_the_aim_the_answers_and_no_other_actor():
    """F4, A9, A6: what code relies on is asked for by name, since the interpret step fills it."""
    system = prompts.INTERPRET_SYSTEM
    assert "- aim: what the step does to the characters it targets" in system
    assert "list in answers what would let the target escape or" in system
    assert "Leave actor_id empty: the player plays only their own character (A6)" in system


def test_hidden_truth_never_reaches_a_prompt():
    """Secrets, an agenda's secret and a mystery's answer stay out (C6)."""
    state = grounded_world()
    texts = [
        interpret_prompt(state, "I ask Carmine about my father").messages[-1].text,
        brief(state).user,
    ]
    for text in texts:
        assert SECRET not in text
        assert MYSTERY_ANSWER not in text


def test_the_opening_brief_asks_for_an_opening():
    state = cultivation_world()
    opening = brief(state, context=ctx(turn=1), premise="A weak disciple remembers a past life.")
    assert "## TASK\n" + prompts.OPENING_TASK in opening.user
    assert "## PREMISE\nA weak disciple remembers a past life." in opening.user
    assert "## OUTCOME" not in opening.user


def test_an_action_brief_carries_the_outcome_and_where_the_plan_stopped():
    state = grounded_world()
    after = state.model_copy(deep=True)
    after.world_s += 2
    action = brief(
        state, after=after, intent=Intent(summary="throw, then run"), resolution=stopped_plan()
    )
    assert '"stopped_at_step":0' in action.user
    assert '"unplayed":["run for the tunnel"]' in action.user
    assert '"why":"The troll\'s hide is thick."' in action.user
    assert '"world_seconds_passed":2' in action.user
    assert "## TASK" not in action.user


def test_the_brief_follows_the_rating_and_the_players_preferences():
    teen = brief(context=ctx(rating=Rating.TEEN)).user
    assert "Rating: Teen." in teen and "no gore" in teen
    mature = brief(
        context=ctx(rating=Rating.MATURE, prefs=ContentPrefs(gore=GoreLevel.HIGH, romance=False))
    ).user
    assert "Rating: Mature (17+)." in mature
    assert "graphic, cinematic gore is in" in mature
    assert "never start romance" in mature
    assert "fades out once sex begins" in mature


def test_the_brief_carries_length_tone_and_the_story_so_far():
    scenes = [PastScene(turn=t, narration=f"scene {t}") for t in range(1, 6)]
    text = brief(
        scenes=scenes, context=ctx(narration_length=NarrationLength.SHORT, tone="grim")
    ).user
    assert prompts.LENGTHS[NarrationLength.SHORT] in text
    assert "the player asked for: grim" in text
    shown = [t for t in range(1, 6) if f'"narration":"scene {t}"' in text]
    assert shown == list(range(6 - RECENT_SCENES, 6))


def test_suggestions_and_pictures_are_asked_for_only_when_planned():
    plain = brief(plan=DirectorPlan(suggestions=SuggestionPlan(count=0, kinds=[])))
    assert plain.suggestions == 0
    assert '"count":0' in plain.user
    assert "## PICTURE" not in plain.user
    planned = brief(
        plan=DirectorPlan(
            picture=PictureDecision(
                kind=PictureKind.PORTRAIT,
                trigger=PictureTrigger.FIRST_MEETING,
                subject_id="carmine",
            )
        )
    )
    assert "## PICTURE" in planned.user and "Carmine" in planned.user


def test_the_continuity_section_names_the_dead():
    state = grounded_world()
    bartender = state.characters["bartender"]
    bartender.status, bartender.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED
    assert f"{bartender.name} (bartender) is dead." in brief(state).user


def test_the_cutaway_prompt_and_the_template_line():
    narration = brief(cultivation_world())
    assert narration.prompt().system == prompts.NARRATOR_SYSTEM
    assert narration.prompt(cutaway=True).system.endswith(prompts.CUTAWAY_SYSTEM)
    assert narration.template_line() == (
        "What happened in the outer-court well stays off the page. Its consequences won't."
    )


def test_the_chapter_prompt_holds_the_scenes():
    prompt = chapter_prompt([PastScene(3, "Zhao falls.", "I stop time")])
    assert prompt.system == prompts.SUMMARIZER_SYSTEM
    assert '"narration":"Zhao falls."' in prompt.messages[-1].text


def test_a_present_characters_secret_power_stays_hidden():
    """G20: hidden strength shows when it is used, never in the prompt beforehand."""
    state = cultivation_world()
    zhao = state.characters["zhao"]
    zhao.sheet.powers = [
        Power(id="iron-palm", name="iron palm", description="KNOWN-POWER"),
        Power(id="hidden-blade", name="hidden blade", description="SECRET-POWER", secret=True),
    ]
    for text in (interpret_prompt(state, "x").messages[-1].text, brief(state).user):
        assert "KNOWN-POWER" in text
        assert "SECRET-POWER" not in text
    zhao.sheet.powers = zhao.sheet.powers[1:]
    assert '"hidden-blade"' not in brief(state).user


def test_world_settings_show_even_at_their_defaults():
    """A model can't assume fun-first physics or no resurrection (A9, C1)."""
    state = cultivation_world()
    assert state.bible.physics.value == "fun_first"
    for text in (interpret_prompt(state, "x").messages[-1].text, brief(state).user):
        assert '"physics":"fun_first"' in text
        assert '"resurrection":"none"' in text


def test_only_events_the_player_could_notice_reach_the_narrator():
    """C6: an event far away stays off-screen until word of it arrives."""
    state = cultivation_world()
    events = [
        PendingEvent(id="e1", kind="arrival", title="NEEDS-YOU", due_s=0, needs_player=True),
        PendingEvent(id="e2", kind="rumor", title="ABOUT-YOU", due_s=0, subject_ids=["lin"]),
        PendingEvent(id="e3", kind="visit", title="RIGHT-HERE", due_s=0, place_id="well"),
        PendingEvent(id="e4", kind="plot", title="FAR-AWAY", due_s=0, place_id="inner-court"),
        PendingEvent(id="e5", kind="plot", title="NOWHERE", due_s=0),
    ]
    text = narration_brief(
        before=state,
        after=state,
        ctx=ctx(),
        intent=None,
        resolution=Resolution(),
        plan=DirectorPlan(),
        fired=events,
        scenes=(),
    ).user
    for title in ("NEEDS-YOU", "ABOUT-YOU", "RIGHT-HERE"):
        assert title in text
    for title in ("FAR-AWAY", "NOWHERE"):
        assert title not in text


def test_the_directors_own_events_reach_the_narrator_as_the_event_and_happenings():
    """W16, E7: an ignored event playing out, or a festival inside a time skip, is told from the
    director's plan, never twice from the raw pending event."""
    state = cultivation_world()
    raw = PendingEvent(
        id="director-event-1", kind="director.plays_out", title="RAW", due_s=0, needs_player=True
    )
    happened = PlannedEvent(
        size=EventSize.LOCAL,
        kind=EventKind.CELEBRATION,
        source=EventSource.DUE,
        source_id="director-event-1",
        card_id="good-season",
        title="A good season",
        brief="HARVEST-FESTIVAL",
        needs_decision=False,
        plays_out_s=40,
    )
    text = narration_brief(
        before=state,
        after=state,
        ctx=ctx(),
        intent=None,
        resolution=Resolution(),
        plan=DirectorPlan(happenings=[happened]),
        fired=[raw],
        scenes=(),
    ).user
    assert "HAPPENINGS" in text and "HARVEST-FESTIVAL" in text
    assert "RAW" not in text and "FIRED" not in text
    assert "good-season" not in text and "plays_out_s" not in text


def test_a_world_event_the_director_made_the_scenes_event_is_told_once():
    state = cultivation_world()
    raw = PendingEvent(id="e1", kind="arrival", title="GUARDS", due_s=0, needs_player=True)
    planned = PlannedEvent(
        size=EventSize.PERSONAL,
        kind=EventKind.ARRIVAL,
        source=EventSource.DUE,
        source_id="e1",
        title="GUARDS",
        brief="The guards are at the door.",
    )
    text = narration_brief(
        before=state,
        after=state,
        ctx=ctx(),
        intent=None,
        resolution=Resolution(),
        plan=DirectorPlan(event=planned),
        fired=[raw],
        scenes=(),
    ).user
    assert text.count("GUARDS") == 1 and "FIRED" not in text


def test_thread_choices_name_the_thread_they_follow():
    state = cultivation_world()
    plan = DirectorPlan(
        suggestions=SuggestionPlan(
            count=3,
            kinds=[ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE],
            thread_id="tournament",
        )
    )
    text = brief(state, plan=plan).user
    assert '"thread":{"id":"tournament","title":"The ranking tournament"}' in text
    off = plan.model_copy(update={"suggestions": SuggestionPlan(count=0, kinds=[])})
    assert '"thread":{' not in brief(state, plan=off).user


def test_no_suggestions_when_none_were_asked_for():
    narration = NarratorOutput(
        narration="x", suggestions=[SuggestionOut(label="Run", kind=ChoiceKind.THREAD)]
    )
    assert choices(narration, 0) == []
    assert [c.label for c in choices(narration, 1)] == ["Run"]


def test_a_deed_s_fallback_picture_is_told_in_the_world_s_words():
    """G16: with no prompt from the narrator, a big deed's picture is drawn from what happened,
    not from the player's step and resolve's outcome note."""
    from engine.contracts import PictureDecision, PictureKind, PictureTrigger
    from engine.state import Deed

    state = cultivation_world()
    state.characters["zhao"].status = CharacterStatus.DEAD
    state.deeds["d1"] = Deed(
        id="d1",
        actor_id="lin",
        kind="kill",
        text="cut Zhao down by the well (it worked)",
        victim_ids=["zhao"],
        place_id="well",
        severity=4,
        turn=3,
        world_s=0,
    )
    decision = PictureDecision(
        kind=PictureKind.SCENE, trigger=PictureTrigger.BIG_DEED, subject_id="d1"
    )

    assert fallback_prompt(state, decision) == "Lin Feng killed Zhao Kun at the outer-court well."
