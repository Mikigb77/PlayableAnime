"""What the model nodes read: the interpret prompt and the narrator's brief (B5 step 4)."""

import json

from engine.base import DAY, HOUR, MINUTE
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
from engine.labels import DAY_PARTS
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import Character, CharacterStatus, DeathCertainty, Pregnancy
from engine.state.records import EventStatus, PendingEvent, StepResult
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


def test_the_interpret_prompt_reads_the_clock_and_how_people_travel():
    # W10: what time it is now, on the 24-hour clock, to judge how long the action takes and
    # to count "until nightfall" from.
    state = cultivation_world()  # day count from 07:00
    state.world_s = 12 * HOUR + 15 * MINUTE
    text = interpret_prompt(state, "I wait until nightfall").messages[-1].text
    assert '## NOW\n{"date":"Day 1, evening","clock":"19:15","part_of_day":"evening"}' in text
    assert '"travel":{"description":"On foot, by flying sword for the strong' in text
    system = prompts.INTERPRET_SYSTEM
    assert "walking across a town 10 to 30 minutes" in system
    assert "- until: when the player times a step by the clock" in system
    assert "steps is empty only when the character just waits or watches" in system
    assert "Waiting or watching for a set time or until a time of day is a step" in system
    # "Until dusk" lands where the clock the player sees says dusk starts.
    parts = ", ".join(f"{part} {hour:02d}:00" for hour, part in DAY_PARTS[1:])
    assert f"parts of the day start at {parts}, unless" in system
    assert "dusk 17:00, evening 19:00" in parts


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
    # W10: the opening is told at the hour the story opens.
    assert '## NOW\n{"date":"Day 1, morning","clock":"07:00"' in opening.user


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


def test_the_narrator_is_told_when_the_scene_began_and_what_time_it_is_now():
    # W10: the light, meals and the hour in the telling keep to the clock.
    state = cultivation_world()  # day count from 07:00
    after = state.model_copy(deep=True)
    after.world_s += 11 * HOUR + 30 * MINUTE
    action = brief(state, after=after, intent=Intent(summary="walk to the inn and eat"))
    time = action.user.split("## TIME\n", 1)[1].split("\n", 1)[0]
    assert time == (
        '{"began":{"date":"Day 1, morning","clock":"07:00","part_of_day":"morning"},'
        '"now":{"date":"Day 1, dusk","clock":"18:30","part_of_day":"dusk"},'
        '"passed":"11 h 30 min","world_seconds_passed":41400}'
    )
    assert "- Keep to the clock (W10)." in prompts.NARRATOR_SYSTEM
    assert "never skip ahead" in prompts.NARRATOR_SYSTEM


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


def test_what_stays_the_same_each_turn_starts_the_brief_and_is_marked_for_the_cache():
    # T5: the style, the content rules and the world start the brief, so the backend can keep
    # them cached with the system text; the opening's premise and the story so far come after.
    state = grounded_world()
    opening = brief(state, context=ctx(turn=1), premise="Luca comes home.")
    later = brief(state, scenes=[PastScene(1, "Luca walks in.", "I walk in")])

    for narration in (opening, later):
        stable, rest = narration.prompt().stable_split()
        assert [line for line in stable.splitlines() if line.startswith("## ")] == [
            "## STYLE",
            "## CONTENT",
            "## WORLD",
        ]
        assert narration.user == f"{stable}\n\n{rest}"
    assert opening.prompt().stable_split()[0] == later.prompt().stable_split()[0]
    assert opening.prompt().stable_split()[1].startswith("## PREMISE\nLuca comes home.")
    assert later.prompt().stable_split()[1].startswith("## STORY SO FAR")
    # A cutaway's system text is rare, so it isn't cached.
    assert later.prompt(cutaway=True).stable_split() is None


def test_the_interpret_prompt_starts_with_the_world_marked_for_the_cache():
    stable, rest = interpret_prompt(grounded_world(), "I open the door").stable_split()

    assert stable.startswith("## WORLD\n") and "\n## " not in stable
    assert rest.startswith("## PLAYER CHARACTER")


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
        # A birth that came to nothing, here, is never told (N6).
        PendingEvent(
            id="e6",
            kind="world.birth",
            title="NEVER-BORN",
            due_s=0,
            place_id="well",
            status=EventStatus.CANCELLED,
        ),
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
    for title in ("FAR-AWAY", "NOWHERE", "NEVER-BORN"):
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


def test_the_narrator_reads_family_by_name_and_a_child_on_the_way():
    """N6: parents and children by name, the dead marked, and a pregnancy with when it is due.
    The player character's own family marks kin they haven't learned of (C6)."""
    state = grounded_world()
    state.world_s = 10 * DAY
    state.characters["gennaro"] = Character(id="gennaro", name="Gennaro", parent_ids=["luca"])
    state.characters["nina"] = Character(
        id="nina", name="Nina", parent_ids=["luca"], known_by=["luca"]
    )
    state.characters["bartender"].parent_ids = ["carmine"]
    state.characters["carmine"].expecting = Pregnancy(
        other_parent_id="luca", conceived_s=0, due_s=40 * DAY
    )
    gone = state.characters["nina"]
    gone.status, gone.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED

    text = brief(state).user
    present = json.loads(text.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])["present"]
    you = json.loads(text.split("## PLAYER CHARACTER\n", 1)[1].split("\n\n## ", 1)[0])

    carmine, bartender = present
    assert carmine["family"] == {
        "children": [{"id": "bartender", "name": "Gennaro"}],
        "expecting": {"with": "Luca Esposito", "due": "in 4 weeks"},
    }
    assert bartender["family"] == {"parents": [{"id": "carmine", "name": "Carmine Russo"}]}
    assert "parent_ids" not in bartender and "expecting" not in carmine
    # Luca hasn't learned of his son Gennaro, and knows his daughter Nina.
    assert you["family"] == {
        "children": [
            {"id": "gennaro", "name": "Gennaro", "unknown_to_you": True},
            {"id": "nina", "name": "Nina", "dead": True},
        ]
    }


def test_the_narrators_guide_names_every_section_the_brief_writes():
    # T5: the guide brings the cached start past Vertex AI's 4,096-token minimum, and it must
    # describe the brief as it is.
    import inspect
    import re

    from graph.turn import context

    written = set(re.findall(r'\("([A-Z][A-Z ]+)",', inspect.getsource(context.narration_brief)))
    assert {"STYLE", "WORLD", "OUTCOME", "ENDING", "TASK"} <= written
    missing = [name for name in sorted(written) if f"- {name}: " not in prompts.BRIEF_GUIDE]
    assert missing == []
    assert prompts.NARRATOR_SYSTEM.endswith(prompts.BRIEF_GUIDE)


def test_ability_costs_come_from_the_sheet_and_the_world_never_from_the_narrator():
    # G13, A1: a keen-observation gift once played as a crushing headache nothing called for.
    # The narrator shows only the costs OUTCOME lists, and the drafter gives a power only the
    # costs its world or premise gives it.
    from graph.drafting import prompts as drafting

    assert "a power shows its cost" not in prompts.NARRATOR_SYSTEM
    assert "costs only what OUTCOME's costs say" in prompts.NARRATOR_SYSTEM
    assert "never a drawback of your own" in prompts.NARRATOR_SYSTEM
    assert "Never invent pain, sickness or harm as a cost" in drafting.SYSTEM
    assert "facts.challenge, always" in prompts.INTERPRET_SYSTEM
