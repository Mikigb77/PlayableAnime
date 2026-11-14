"""What the model nodes read: the interpret prompt and the narrator's brief (B5 step 4)."""

import json

import pytest
from pydantic import ValidationError

from engine import bonds, pipeline
from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import (
    ContentPrefs,
    GoreLevel,
    Language,
    NarrationLength,
    Rating,
    StorySettings,
    TurnContext,
)
from engine.contracts import (
    ActionKind,
    Aim,
    ChoiceKind,
    DirectorPlan,
    EventKind,
    EventSource,
    Harm,
    Intent,
    IntentStep,
    OutcomeClass,
    Peril,
    PictureDecision,
    PictureKind,
    PictureTrigger,
    PlannedEvent,
    PlannedMoment,
    PlannedTalk,
    ProposedDeed,
    Resolution,
    SceneWeight,
    StepResolution,
    StopReason,
    SuggestionPlan,
    Trip,
)
from engine.labels import DAY_PARTS
from engine.rng import SeededRng
from engine.samples import cultivation_world, farm_world, grounded_world
from engine.state.cast import (
    Character,
    CharacterStatus,
    DeathCertainty,
    Faith,
    Place,
    Pregnancy,
    Prominence,
    Route,
)
from engine.state.records import (
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Deed,
    Die,
    DieKind,
    EventStatus,
    Goal,
    GoalStatus,
    LifeEvent,
    LifeKind,
    Mark,
    NumberPart,
    Origin,
    OriginKind,
    PendingEvent,
    RollRecord,
    StepResult,
    Throw,
)
from engine.state.scene import Bout, Encounter, EncounterKind, Terms
from engine.state.sheet import (
    Attitude,
    Power,
    Talent,
    TalentBridge,
    TalentCover,
    TalentFit,
    TalentRuling,
    TalentStrength,
)
from engine.state.world import EventSize, WorldState
from engine.world import returns
from engine.world.scheduling import World
from graph.turn import prompts
from graph.turn.context import (
    _FAITH,
    _PACE,
    LAST_SCENE_CHARS,
    RECENT_SCENES,
    asks,
    chapter_prompt,
    interpret_prompt,
    narration_brief,
    present_characters,
)
from graph.turn.outputs import NarratorOutput, SuggestionOut
from graph.turn.scene import choices, fallback_prompt
from graph.turn.types import Ending, PastScene

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
    assert prompt.system == prompts.interpret_system(asks(state))
    assert "## ACTION\nI throw a stone at Senior Brother Jo" in text
    assert "Zhao grins and draws back his foot" in text  # the last moment (R3)
    assert '"aliases":["Senior Brother Zhao"]' in text  # misheard names map to ids (V3)
    assert '"tournament"' in text  # open threads, for what the action takes up


def test_the_interpret_prompt_names_the_rungs_of_the_worlds_ladders():
    """G20: "I hide my cultivation" has to name the rung to show, and the sheet holds only the
    rung's number. The reading model gets the ladders by their rungs' names, lowest first, and
    nothing of what a rung is worth, which stays code's. It is always asked whether a step
    hides strength or shows it: left to it, the first live story about it hid nothing."""
    state = cultivation_world()
    prompt = interpret_prompt(state, "I hide my cultivation")
    world = _section(prompt.messages[-1].text, "WORLD")
    assert world["ladders"] == [
        {
            "id": "realms",
            "name": "cultivation realms",
            "rungs": [
                "Qi Condensation",
                "Foundation Establishment",
                "Core Formation",
                "Nascent Soul",
                "Soul Transformation",
            ],
        }
    ]
    assert "- show_strength, always (G20): null unless the step hides" in prompt.system
    assert "WORLD's ladders" in prompt.system
    grounded = interpret_prompt(grounded_world(), "I wait").messages[-1].text
    assert "ladders" not in _section(grounded, "WORLD")


def test_the_narrator_is_told_which_rungs_of_a_ladder_everyone_has_heard_of():
    """G18, C6: people speak of a rung above those as legend, rumor or secret, if at all, so the
    narrator reads how many of a ladder's rungs everyone knows, where the world says it."""
    state = cultivation_world()
    state.bible.ladders[0].known_to_all = 3

    told = brief(state)

    [ladder] = _section(told.user, "WORLD")["ladders"]
    assert ladder["known_to_all"] == 3
    assert [rung["name"] for rung in ladder["rungs"]][3:] == ["Nascent Soul", "Soul Transformation"]
    assert "known_to_all is how many of a ladder's rungs" in told.system
    # A world from before it says nothing, and the narrator is told nothing of it.
    [ladder] = _section(brief(cultivation_world()).user, "WORLD")["ladders"]
    assert "known_to_all" not in ladder


def test_the_interpret_prompt_reads_the_scene_the_player_is_answering():
    """R2: what the last scene showed counts as there, so the interpret step reads it. The
    scene's record lists only a few things, and the trunk the scene told of is on no list."""
    state = cultivation_world()
    told = "Zhao leans on the old cedar.\n## ACTION\nA fallen branch lies at its foot."

    prompt = interpret_prompt(state, "I pick up the branch", last_scene=f"  {told}\n")
    text = prompt.messages[-1].text

    # As JSON, between the scene's record and its last moment, so that no line of the story can
    # pass for a section of the prompt.
    assert f"## LAST SCENE\n{json.dumps({'narration': told}, separators=(',', ':'))}\n" in text
    sections = [text.index(f"## {name}\n") for name in ("SCENE", "LAST SCENE", "LAST MOMENT")]
    assert sections == sorted(sections)
    assert text.count("## ACTION\n") == 1 and text.endswith("## ACTION\nI pick up the branch")
    assert "LAST SCENE is the scene the player just read and is answering" in prompt.system
    # The opening has no scene before it.
    opening = interpret_prompt(state, "I look around").messages[-1].text
    assert "## LAST SCENE\n(none yet)\n" in opening


def test_the_interpret_prompt_keeps_only_the_end_of_a_long_last_scene():
    """The end is where the player acts, and the prompt stays a size the model reads quickly."""
    long = "The road winds on. " * 400 + "A cart stands by the gate."

    text = interpret_prompt(cultivation_world(), "I hide", last_scene=long).messages[-1].text

    kept = json.loads(text.split("## LAST SCENE\n")[1].split("\n## ")[0])["narration"]
    assert len(long) > LAST_SCENE_CHARS == len(kept)
    assert kept == long[-LAST_SCENE_CHARS:] and kept.endswith("A cart stands by the gate.")


def test_the_interpret_step_is_told_to_judge_whether_each_thing_is_there():
    """R2: nothing natural fails for no reason. The step always says whether a thing is there,
    and keeps "uncertain" for what is hidden, rare, valuable or decisive."""
    system = prompts.INTERPRET_SYSTEM
    assert "- plausibility, always, for everything a beat uses: whether it is there." in system
    assert "nothing natural fails for no reason" in system
    assert "uncertain only for something that might well not be there and that matters" in system
    assert "Never judge by whether SCENE lists it: SCENE lists only a few things." in system
    assert "an aura blade included: it is no object" in system


def test_both_models_see_the_players_active_goals_by_id():
    """N2: the interpret step names the goals the player drops, and the narrator the goals that
    are over, by id. The narrator sees the goals as the director left them this turn."""
    state = grounded_world()
    state.goals["goal-2"] = Goal(id="goal-2", text="Leave Naples", status=GoalStatus.ABANDONED)
    after = state.model_copy(deep=True)
    after.goals["goal-3"] = Goal(id="goal-3", text="Win back the bar at cards", set_turn=2)
    goal = '{"id":"find-killer","text":"Find out who killed my father."}'
    taken = '{"id":"goal-3","text":"Win back the bar at cards"}'

    text = interpret_prompt(state, "I drink").messages[-1].text
    assert goal in text and "Leave Naples" not in text
    step = IntentStep(text="drink", verb="drink", kind=ActionKind.TASK, proposed_duration_s=60)
    action = Intent(steps=[step])
    text = brief(state, after=after, intent=action).user
    assert goal in text and taken in text and "Leave Naples" not in text


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


def thrown(mark: Mark, *, kind: DieKind = DieKind.PLAIN, deadly: bool = False) -> RollRecord:
    """A throw as the engine records it: 12 against 17, however `mark` says it fell."""
    throw = Throw(
        dice=[Die(kind=kind, face=12)],
        hand=1,
        hand_why="Speed, 1 die",
        number=17,
        made_of=[NumberPart(text="Zhao's swordplay (fair), level 2", points=17)],
        total=12,
        most=20,
        mark=mark,
        against="Zhao can answer.",
        deadly=deadly,
        miss_costs="His blade opens your throat." if deadly else "",
    )
    return RollRecord(
        seed="s", odds=0.45, odds_label="12 against 17", result=StepResult.PARTIAL, throw=throw
    )


def outcome_of(resolution: Resolution) -> dict:
    told = brief(cultivation_world(), intent=Intent(summary="cut"), resolution=resolution)
    return json.loads(told.user.split("## OUTCOME\n", 1)[1].split("\n", 1)[0])


def cut(**kw) -> StepResolution:
    return StepResolution(
        index=0,
        text="cut at Zhao",
        outcome_class=OutcomeClass.CONTESTED,
        reason="Speed, 1 die, against Zhao's swordplay (fair), level 2: 12 against 17, so close.",
        result=StepResult.PARTIAL,
        duration_s=2,
        **kw,
    )


def test_the_narrator_is_told_how_the_dice_fell_and_never_the_dice():
    # A3: how it fell, what it was up against and whether a miss could kill. The dice, the
    # number and the chance stay with the scene's details.
    [step] = outcome_of(Resolution(steps=[cut(roll=thrown(Mark.SO_CLOSE, deadly=True))]))["steps"]
    assert step["throw"] == {"fell": "so_close", "against": "Zhao can answer.", "deadly": True}
    assert "extra" not in step

    [step] = outcome_of(Resolution(steps=[cut(roll=thrown(Mark.PASSED))]))["steps"]
    assert step["throw"] == {"fell": "passed", "against": "Zhao can answer."}


def test_the_narrator_tells_a_throw_by_the_hand_that_threw_it():
    """R4, A3: how the dice fell is what happened, never how skilled the character is. Found in
    a live run on 2026-11-10: a novice whose stroke came off was told as a master's."""
    assert "The result and the throw say how the step turned out, and the hand says how it" in (
        prompts.NARRATOR_SYSTEM
    )
    assert "gets there awkwardly, slowly, with effort or by luck" in prompts.NARRATOR_SYSTEM
    assert "a master who misses is still plainly a master (R4)" in prompts.NARRATOR_SYSTEM


def test_the_narrator_is_told_the_one_extra_effect_of_a_throw_over_the_top():
    extra = "Over the top: Zhao is staggered and has no answer. Those who saw it will remember."
    won = cut(roll=thrown(Mark.OVER_THE_TOP), extra=extra, opening_ids=["zhao"])
    [step] = outcome_of(Resolution(steps=[won]))["steps"]
    assert (step["throw"]["fell"], step["extra"]) == ("over_the_top", extra)
    assert "opening_ids" not in step  # the engine's own bookkeeping
    assert "extra is the one extra" in prompts.NARRATOR_SYSTEM
    assert "never name dice, numbers, levels or chances" in prompts.NARRATOR_SYSTEM


def test_the_worlds_die_and_a_step_with_no_throw_give_the_narrator_no_throw():
    # The world's die is nobody's doing: the step's why already says what it found.
    grey = cut(roll=thrown(Mark.PASSED, kind=DieKind.GREY))
    plain = cut()
    for step in outcome_of(Resolution(steps=[grey, plain]))["steps"]:
        assert "throw" not in step


def test_the_narrator_is_told_how_the_defence_fared_against_what_struck_back():
    blow = Peril(
        by_ids=["zhao"],
        by="Zhao",
        aim=Aim.KILL,
        outcome_class=OutcomeClass.CONTESTED,
        reason="Zhao strikes back. You are badly wounded.",
        roll=thrown(Mark.SO_CLOSE, deadly=True),
        result=StepResult.PARTIAL,
        harm=Harm.BADLY_WOUNDED,
    )
    helpless = blow.model_copy(update={"roll": None, "harm": Harm.DEAD})
    [step] = outcome_of(Resolution(steps=[cut(perils=[blow, helpless])]))["steps"]
    first, second = step["struck"]
    assert first == {
        "by": "Zhao",
        "means": "kill",
        "harm": "badly_wounded",
        "why": "Zhao strikes back. You are badly wounded.",
        "defence": {"fell": "so_close", "against": "Zhao can answer.", "deadly": True},
    }
    assert "defence" not in second  # nothing was thrown: they couldn't fend it off


def test_the_narrator_is_told_a_step_was_fought_in_a_bout_and_when_a_blow_broke_its_terms():
    # W1: a blow inside terms both sides agreed to is told as the fight both wanted.
    lesson = cut(bout=Bout(terms=Terms.NO_HARM, with_ids=["zhao"]))
    breach = cut(broke_terms=True)
    inside, beyond, plain = outcome_of(Resolution(steps=[lesson, breach, cut()]))["steps"]

    assert inside["bout"] == "no_harm" and "broke_terms" not in inside
    assert beyond["broke_terms"] is True and "bout" not in beyond
    assert "bout" not in plain and "broke_terms" not in plain


def test_the_narrator_reads_a_blow_of_a_bout_aimed_as_its_terms_held_it():
    # W1: a sparring blow the interpret step read as a killing one isn't told as one.
    blow = IntentStep(
        text="cut at Zhao",
        verb="cut",
        kind=ActionKind.EXCHANGE,
        proposed_duration_s=2,
        aim=Aim.KILL,
        target_ids=["zhao"],
    )
    intent = Intent(summary="spar with Zhao", steps=[blow, blow])
    first = cut(bout=Bout(terms=Terms.NO_HARM, with_ids=["zhao"]))
    resolution = Resolution(steps=[first, cut().model_copy(update={"index": 1})])

    told = brief(cultivation_world(), intent=intent, resolution=resolution).user
    action = json.loads(told.split("## ACTION\n", 1)[1].split("\n", 1)[0])

    assert [step["aim"] for step in action["steps"]] == ["subdue", "kill"]
    assert intent.steps[0].aim is Aim.KILL  # the plan itself is left as it was read


def test_both_models_see_the_terms_of_the_bout_under_way():
    state = cultivation_world()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["zhao"],
        started_turn=1,
        started_s=0,
        bout=Bout(terms=Terms.NO_HARM, with_ids=["zhao"]),
    )
    shown = '"bout":{"terms":"no_harm","with_ids":["zhao"]}'

    assert shown in brief(state, intent=Intent(summary="spar")).user
    assert shown in interpret_prompt(state, "I spar with Zhao").messages[-1].text


def test_the_interpret_step_is_told_who_someone_meant_but_not_named_is():
    """V3: "him" with nobody named is whoever the last scene had the character dealing with,
    and in a fight or a bout whoever they are fighting. In a live lesson (2026-11-11) a blow at
    "his eyes", meant for the teacher, fell on someone who stood by."""
    state = cultivation_world()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["elder-mo"], started_turn=1, started_s=0
    )
    system = prompts.INTERPRET_SYSTEM

    assert 'Someone the player means without naming them ("him", "her", "them") is' in system
    assert "While a fight or a bout is under way (SCENE's encounter), it is whoever" in system
    assert "unless the player's words point at someone else there." in system
    # Who that is is in the prompt: the encounter names those the character is fighting.
    assert '"opponent_ids":["elder-mo"]' in interpret_prompt(state, "I hit him").messages[-1].text


def test_the_reading_names_a_steps_verb_in_english_whatever_the_story_speaks():
    """S10, B5: code reads a verb, to tell a deed (G16), to know a defence, a threat or what
    a bout allows, so a Spanish or a Catalan story's reading still names it in English. The
    step and its beats are the player's to read, under "How it played out", so they are in the
    story's language like the rest of what the reading notes."""
    system = prompts.INTERPRET_SYSTEM

    assert "in your own words (each step's text and its beats, which the player reads" in system
    assert "outcome claims and the summary) in the language LANGUAGE names (S10)." in system
    assert "Code reads a step's verb, so it is a plain English verb in any language" in system


def test_the_models_are_told_who_saw_what_is_done_and_whose_feelings_a_scene_moves():
    """W2, W4: the interpret step says of every step whether a crowd is around, not for a
    quiet place with a few people about (the real model called a walk along a village lane of
    an evening one) and not for what is done so that nobody notices; the narrator moves only
    the feelings of the scene's people."""
    reading, telling = prompts.INTERPRET_SYSTEM, prompts.NARRATOR_SYSTEM
    reading = " ".join(reading.split())

    assert "- facts.crowd (W2), always: true when many people SCENE doesn't name are" in reading
    assert "in a quiet one with only a few people about (a lane of an evening, a road, a" in reading
    assert "and for what is done so that nobody around notices" in reading
    assert "Code makes public what is done before a crowd." in reading
    assert "Only the people in the scene change how they feel (W4)" in telling
    assert "code moves how they feel once a witness or word reaches them" in telling


def test_the_narrator_is_told_what_someone_has_only_heard_said_and_how_they_carry_it():
    """W4: talk alone makes nobody an accuser. The scene shows what each person has only heard
    said of the player character (`Deed.heard_by`), apart from what they hold against them,
    the gravest first, and the narrator is told that it is no accusation."""
    state = cultivation_world()
    for n, (severity, kind) in enumerate([(2, "theft"), (4, "kill"), (3, "assault")], start=1):
        state.deeds[f"deed-{n}"] = Deed(
            id=f"deed-{n}",
            actor_id="lin",
            kind=kind,
            text=f"Lin did a {kind} on Elder Mo",
            turn=1,
            world_s=0,
            place_id="inner-court",
            victim_ids=["elder-mo"],
            severity=severity,
            heard_by={"zhao": 0.7},
        )
    state.deeds["deed-4"] = state.deeds["deed-1"].model_copy(
        update={"id": "deed-4", "heard_by": {}, "known_by": ["lin", "zhao"]}
    )

    (seen,) = [c for c in _section(brief(state).user, "SCENE")["present"] if c["id"] == "zhao"]

    # The gravest first, in the world's words, and not the one he knows of for himself.
    assert seen["toward_you"]["heard_said"] == [
        "Lin Feng wounded Elder Mo at the inner court.",
        "Lin Feng attacked Elder Mo at the inner court.",
        "Lin Feng robbed Elder Mo at the inner court.",
    ]
    assert "grudges" not in seen["toward_you"]
    telling = prompts.NARRATOR_SYSTEM
    assert "Its heard_said is what they have only heard said of the player character" in telling
    assert "they neither accuse outright nor act as if it were known (W4)" in telling
    assert "puts it to them and hears the answer before anything else" in telling


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
        '"passed":"11 h 30 min","world_seconds_passed":41400,"heading":"Twelve hours later"}'
    )


def scene_time(hours: float, **settings) -> dict:
    """The TIME the narrator is given for a scene that took `hours`, from 07:00 on day 1."""
    state = cultivation_world()
    after = state.model_copy(deep=True)
    after.world_s += int(hours * HOUR)
    action = brief(
        state, after=after, context=ctx(**settings), intent=Intent(summary="pass the time")
    )
    return json.loads(action.user.split("## TIME\n", 1)[1].split("\n", 1)[0])


def test_the_narrator_is_told_the_heading_the_player_reads_over_the_scene():
    """W10: a scene that hours or days passed in is headed with them, in the story's language,
    and the telling never says it again."""
    assert "heading" not in scene_time(1.5)  # a short scene has none: the time bar tells it
    assert scene_time(3)["heading"] == "Three hours later"
    assert scene_time(24)["heading"] == "The next day"
    assert scene_time(72)["heading"] == "Three days later"
    assert scene_time(72, language=Language.ES)["heading"] == "Tres días después"
    assert scene_time(72, language=Language.CA)["heading"] == "Tres dies després"
    assert "never say the heading's words again" in prompts.NARRATOR_SYSTEM
    assert "- Keep to the clock (W10)." in prompts.NARRATOR_SYSTEM
    assert "never skip ahead" in prompts.NARRATOR_SYSTEM
    # What the engine has done is told as done at whatever hour it is (on the real model,
    # 2026-11-13, a wedding the record held at one in the morning was put off to sunrise).
    assert "never put it off to a morning the clock doesn't reach" in " ".join(
        prompts.NARRATOR_SYSTEM.split()
    )


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


def test_a_scenes_length_follows_its_weight_within_the_players_setting():
    """R3: a passing moment is told short and a turning point gets room, each within the
    length the player set (S6). The weight changes from turn to turn, so it stays out of STYLE,
    which is cached, and an ordinary scene has STYLE's length alone."""
    short = ctx(narration_length=NarrationLength.SHORT)
    ordinary = brief(context=short)
    light = brief(context=short, plan=DirectorPlan(weight=SceneWeight.LIGHT))
    heavy = brief(context=short, plan=DirectorPlan(weight=SceneWeight.HEAVY))

    assert "## LENGTH" not in ordinary.user
    assert "## LENGTH\nA passing moment: 40 to 80 words." in light.user
    assert "## LENGTH\nA turning point: 120 to 200 words." in heavy.user
    for told in (ordinary, light, heavy):
        assert prompts.LENGTHS[NarrationLength.SHORT] in told.user
        assert told.stable_chars == ordinary.stable_chars
    long = ctx(narration_length=NarrationLength.LONG)
    assert (
        "A turning point: 450 to 650 words."
        in brief(context=long, plan=DirectorPlan(weight=SceneWeight.HEAVY)).user
    )
    # A story's ending is a turning point, whatever the director weighed.
    chosen = Ending(kind="chosen", character_id="lin")
    ending = brief(plan=DirectorPlan(weight=SceneWeight.LIGHT), ending=chosen)
    assert "A turning point: 250 to 400 words." in ending.user
    assert "unless the brief has a LENGTH (R3)" in prompts.NARRATOR_SYSTEM


def asked() -> dict:
    """A quiet turn in the bar: Luca asks Carmine, whom he knows, about the docks."""
    step = StepResolution(
        index=0,
        text="ask Carmine about the docks",
        outcome_class=OutcomeClass.CERTAIN,
        reason="Carmine answers.",
        result=StepResult.SUCCESS,
        duration_s=60,
    )
    read = IntentStep(
        text=step.text,
        verb="ask",
        kind=ActionKind.CONVERSATION,
        proposed_duration_s=60,
        target_ids=["carmine"],
    )
    return {
        "intent": Intent(steps=[read]),
        "resolution": Resolution(steps=[step]),
        "words": "I ask Carmine about the docks",
    }


def player_record(told) -> dict:
    return json.loads(told.user.split("## PLAYER CHARACTER\n", 1)[1].split("\n\n## ", 1)[0])


def test_the_appearance_is_handed_only_to_a_scene_with_reason_to_show_it():
    """R9: in Miki's long story the narrator had the character's looks on every turn, and
    "deep black eyes" came back in 16 scenes of 187. Code decides when a scene gets them."""
    looks = grounded_world().player.appearance
    quiet = brief(**asked())

    assert looks and not quiet.looks
    assert "appearance" not in player_record(quiet) and looks not in quiet.user
    # Nor the line on how they come across, which says how they look too: in the live check
    # (2026-11-12) "a patched grey robe" came back from it in two plain scenes of six.
    comes_across = grounded_world().player.description
    assert "dark suit" in comes_across
    assert "description" not in player_record(quiet) and comes_across not in quiet.user
    # Who they are and everything on their sheet stay.
    assert player_record(quiet)["name"] and player_record(quiet)["sheet"]["traits"]

    def handed(state=None, **change) -> bool:
        told = brief(state, **(asked() | change))
        assert ("appearance" in player_record(told)) is told.looks
        assert ("description" in player_record(told)) is told.looks
        return told.looks

    # The scene that introduces them, and the one that ends their story.
    assert handed(intent=None, resolution=Resolution(), words=None)
    assert handed(ending=Ending(kind="chosen", character_id="luca"))

    # A picture that shows them is drawn true to their appearance (M5): one of the scene, or
    # their own portrait. Someone else's portrait, a place and the cover don't show them.
    def pictured(kind, trigger, subject=None) -> bool:
        picture = PictureDecision(kind=kind, trigger=trigger, subject_id=subject)
        return handed(plan=DirectorPlan(picture=picture))

    assert pictured(PictureKind.SCENE, PictureTrigger.BIG_DEED, "d1")
    assert pictured(PictureKind.PORTRAIT, PictureTrigger.LOOK_CHANGED, "luca")
    assert not pictured(PictureKind.PORTRAIT, PictureTrigger.FIRST_MEETING, "carmine")
    assert not pictured(PictureKind.PLACE, PictureTrigger.FIRST_VISIT, "bar")
    assert not pictured(PictureKind.COVER, PictureTrigger.COVER)
    # A look that changed this turn.
    scarred = grounded_world()
    scarred.player.appearance += " A fresh cut across the cheek."
    scarred.player.look_version += 1
    assert handed(after=scarred)
    # The player's own words are about how they look.
    assert handed(words="I comb my hair back in the mirror behind the bar")
    assert handed(words="I straighten up and touch the scar on my eyebrow")


def test_meeting_someone_for_the_first_time_shows_the_appearance():
    def stranger(**record) -> WorldState:
        state = grounded_world()
        state.characters["nina"] = Character(
            id="nina", name="Nina", location_id="bar", description="A courier.", **record
        )
        return state

    turn = asked()
    to_nina = turn["intent"].steps[0].model_copy(update={"target_ids": ["nina"]})
    walks_up = turn | {"intent": Intent(steps=[to_nina])}
    assert brief(stranger(), **walks_up).looks
    # Someone they have met, or who was already in the scene, is no first meeting.
    assert not brief(stranger(met_by=["luca"]), **walks_up).looks
    there = stranger()
    there.scene.present_ids.append("nina")
    assert not brief(there, **walks_up).looks
    # A stranger a step made real, and someone an event brings.
    made = turn["resolution"].steps[0].model_copy(update={"strangers": ["nina"]})
    assert brief(stranger(), **(turn | {"resolution": Resolution(steps=[made])})).looks
    arrives = PlannedEvent(
        kind=EventKind.ARRIVAL,
        size=EventSize.PERSONAL,
        source=EventSource.DECK,
        title="A courier at the door",
        brief="A courier asks for Luca.",
        cast_ids=["nina"],
    )
    assert brief(stranger(), **(turn | {"plan": DirectorPlan(event=arrives)})).looks


def test_the_narrator_is_handed_the_wording_the_last_scenes_repeated():
    """R9: code reads the last scenes, and the narrator says those things another way."""
    scene = "Carmine Russo watches you over a thousand lire. Your steady nerves hold."
    told = [PastScene(turn, f"{scene} Scene {turn}.") for turn in range(1, 4)]
    plain = brief(**asked())
    worn = brief(scenes=told, **asked())

    assert "## WORN" not in plain.user and plain.worn == ()
    assert worn.worn == ("steady nerves hold",)
    assert '## WORN\n["steady nerves hold"]' in worn.user
    # Names are no wording, nor is what the world calls its money, and the list stays out of
    # the cached start.
    assert not any(name in " ".join(worn.worn) for name in ("carmine", "russo", "lire"))
    assert worn.stable_chars == plain.stable_chars
    assert "Never use a phrase WORN lists" in prompts.NARRATOR_SYSTEM


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
        # W10. Someone who came for the character to another place and found them gone is
        # there, looking: nothing of it shows here, though it is about them.
        PendingEvent(
            id="e7",
            kind="world.answer",
            title="CAME-ELSEWHERE",
            due_s=0,
            place_id="inner-court",
            subject_ids=["elder-mo", "lin"],
        ),
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
    for title in ("FAR-AWAY", "NOWHERE", "NEVER-BORN", "CAME-ELSEWHERE"):
        assert title not in text
    # And he is not among those the scene may bring in.
    assert "WHO ELSE" not in text


def test_word_of_a_deed_on_its_way_is_nothing_the_player_character_notices():
    """C6, W2: a report, a rumor or the news to a victim's family is about the player character
    when the deed is theirs, and still happens out of their sight. Only being told on the spot,
    or where they are, shows."""
    state = cultivation_world()
    about = {"due_s": 0, "subject_ids": ["lin", "zhao"]}
    events = [
        PendingEvent(id="e1", kind="world.rumor", title="RUMOR-HERE", place_id="well", **about),
        PendingEvent(id="e2", kind="world.word", title="WORD-OUT", **about),
        PendingEvent(id="e3", kind="world.discovery", title="LOOK-HERE", place_id="well", **about),
        PendingEvent(
            id="e4", kind="world.report", title="RAN-OFF", payload={"witness_id": "wei"}, **about
        ),
        PendingEvent(
            id="e5", kind="world.tidings", title="KIN-AWAY", place_id="inner-court", **about
        ),
        PendingEvent(
            id="e6", kind="world.report", title="TOLD-HERE", payload={"witness_id": "zhao"}, **about
        ),
        PendingEvent(id="e7", kind="world.tidings", title="KIN-HERE", place_id="well", **about),
        PendingEvent(
            id="e8", kind="world.report", title="AT-THE-SEAT", place_id="well", payload={}, **about
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
    for title in ("TOLD-HERE", "KIN-HERE", "AT-THE-SEAT"):
        assert title in text
    for title in ("RUMOR-HERE", "WORD-OUT", "LOOK-HERE", "RAN-OFF", "KIN-AWAY"):
        assert title not in text


def test_the_narrator_is_told_who_runs_to_tell_and_the_interpret_step_who_is_leaving():
    """W11: a witness with someone to tell sets off within a couple of minutes. The scene that
    tells the deed shows them going, and the next action can go after them."""
    before = cultivation_world()
    before.places["inner-court"].controller_id = "azure-cloud"
    before.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    before.scene.present_ids.append("wei")
    shove = StepResolution(
        index=0,
        text="shove Zhao into the well",
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=2,
        deeds=[ProposedDeed(kind="assault", text="Lin shoves Zhao", victim_ids=["zhao"])],
    )
    resolution = Resolution(steps=[shove])
    after = pipeline.play_out(before, resolution, ctx(), SeededRng.for_turn("s", "main", 2)).state
    intent = Intent(
        steps=[
            IntentStep(
                text="shove Zhao into the well",
                verb="shove",
                kind=ActionKind.INSTANT,
                proposed_duration_s=2,
            )
        ]
    )

    def witnesses(state, turn=2):
        told = brief(before, after=state, intent=intent, resolution=resolution, context=ctx(turn))
        return _section(told.user, "WITNESSES") if "## WITNESSES" in told.user else None

    sect = "the Azure Cloud Sect"
    assert witnesses(after) == [{"id": "wei", "who": "Wei", "to_tell": sect, "gone": False}]
    # The player's next words can stop him: the interpret step reads that he is leaving.
    scene = _section(interpret_prompt(after, "I grab Wei").messages[-1].text, "SCENE")
    assert scene["leaving"] == [{"id": "wei", "to_tell": sect}]
    assert "leaving" not in _section(interpret_prompt(before, "x").messages[-1].text, "SCENE")
    # The guide says what leaving means only to a turn whose scene shows someone leaving (B5).
    assert "SCENE's leaving" in prompts.INTERPRET_SYSTEM
    assert "SCENE's leaving" in interpret_prompt(after, "I grab Wei").system
    assert "SCENE's leaving" not in interpret_prompt(before, "x").system

    # A scene that ran past the moment he set off shows him go (W10).
    later = after.model_copy(deep=True)
    later.world_s += 5 * MINUTE
    assert witnesses(later, turn=3) == [{"id": "wei", "who": "Wei", "to_tell": sect, "gone": True}]
    # Whom he runs to is told only when the character knows of them (C6).
    after.factions["azure-cloud"].known_by = []
    assert witnesses(after) == [{"id": "wei", "who": "Wei", "gone": False}]
    # Stopped for good, he is going nowhere.
    after.characters["wei"].status = CharacterStatus.DEAD
    after.characters["wei"].death_certainty = DeathCertainty.CONFIRMED
    assert witnesses(after) is None


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
    assert choices(narration, SuggestionPlan(count=0, kinds=[])) == []
    one = SuggestionPlan(count=1, kinds=[ChoiceKind.THREAD])
    assert [c.label for c in choices(narration, one)] == ["Run"]


def test_a_way_to_let_time_pass_is_the_directors_to_offer():
    """S2, W10: the narrator writes the choices and the director says their kinds, so a choice
    marked `time` that the plan didn't ask for is shown as a side matter, and one it asked for
    keeps its mark."""
    narration = NarratorOutput(
        narration="x",
        suggestions=[
            SuggestionOut(label="Ask the smith about the blade", kind=ChoiceKind.THREAD),
            SuggestionOut(label="Sleep until morning", kind=ChoiceKind.TIME),
            SuggestionOut(label="Train for three days", kind=ChoiceKind.TIME),
        ],
    )
    quiet = [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE]

    unasked = choices(narration, SuggestionPlan(count=3, kinds=quiet))
    asked = choices(narration, SuggestionPlan(count=4, kinds=[*quiet, ChoiceKind.TIME]))

    assert [c.kind for c in unasked] == [ChoiceKind.THREAD, ChoiceKind.SIDE, ChoiceKind.SIDE]
    assert [c.kind for c in asked] == [ChoiceKind.THREAD, ChoiceKind.TIME, ChoiceKind.SIDE]
    assert [c.label for c in asked] == [s.label for s in narration.suggestions]


def test_the_narrator_is_asked_for_a_time_choice_only_when_the_plan_lists_one():
    state = cultivation_world()
    kinds = [ChoiceKind.THREAD, ChoiceKind.PERSONAL, ChoiceKind.SIDE, ChoiceKind.TIME]
    plan = DirectorPlan(suggestions=SuggestionPlan(count=4, kinds=kinds, thread_id="tournament"))

    assert '"kinds":["thread","personal","side","time"]' in brief(state, plan=plan).user
    assert '"time"' not in brief(state).user.split("## SUGGESTIONS\n", 1)[1].split("\n", 1)[0]
    # What such a choice is, and that the scene never leans on it.
    assert 'A "time" choice, only when SUGGESTIONS lists one' in prompts.NARRATOR_SYSTEM
    assert "nothing in the narration leans toward it" in prompts.NARRATOR_SYSTEM


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


def test_the_narrator_reads_a_romance_as_the_record_has_it():
    """W17: the bond between someone and the player character, since when, and their own heart
    and pace in words. The number stays the engine's. A partner is family by name."""
    state = farm_world()
    state.world_s = 12 * DAY
    state.scene.present_ids = ["tomas", "ilse", "bram", "mara", "greta"]
    felt = Attitude(affinity=20, attraction=45, heart_moved_s=11 * DAY)
    state.characters["mara"] = Character(id="mara", name="Mara", age=29, location_id="farm")
    state.characters["mara"].sheet.disposition.attitudes["tomas"] = felt
    state.bonds["bond-2"] = Bond(
        id="bond-2",
        a_id="tomas",
        b_id="mara",
        stage=BondStage.COURTING,
        steps=[BondStep(stage=BondStage.COURTING, turn=9, world_s=9 * DAY)],
    )
    ended = [
        BondStep(stage=BondStage.TOGETHER, turn=2, world_s=DAY),
        BondStep(stage=BondStage.OVER, turn=4, world_s=5 * DAY, how="Tomas Weller ended it."),
    ]
    state.characters["greta"] = Character(id="greta", name="Greta", age=31, location_id="farm")
    state.bonds["bond-3"] = Bond(
        id="bond-3",
        a_id="tomas",
        b_id="greta",
        stage=BondStage.OVER,
        end=BondEnd.PARTED,
        steps=ended,
    )

    text = brief(state).user
    present = json.loads(text.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])["present"]
    you = json.loads(text.split("## PLAYER CHARACTER\n", 1)[1].split("\n\n## ", 1)[0])
    ilse, bram, mara, greta = present

    assert ilse["bond_with_you"] == {
        "stage": "married",
        "since": "before the story began",
        "their_heart": "in love with you",
        "their_pace": _PACE[bonds.pace("ilse")],
    }
    assert mara["bond_with_you"] == {
        "stage": "courting",
        "since": "3 days ago",
        "their_heart": "drawn to you",
        "their_pace": _PACE[bonds.pace("mara")],
    }
    assert greta["bond_with_you"] == {
        "stage": "over",
        "ended": "Tomas Weller ended it.",
        "since": "7 days ago",
        "their_heart": "not drawn to you",
        "their_pace": _PACE[bonds.pace("greta")],
    }
    assert "bond_with_you" not in bram
    # A new start doesn't undo what ended before it: the narrator reads both.
    again = state.model_copy(deep=True)
    again.bonds["bond-4"] = Bond(
        id="bond-4",
        a_id="tomas",
        b_id="greta",
        stage=BondStage.INTEREST,
        steps=[BondStep(stage=BondStage.INTEREST, turn=11, world_s=11 * DAY, by_id="tomas")],
    )
    retold = brief(again).user
    present = json.loads(retold.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])["present"]
    assert present[3]["bond_with_you"] == {
        "stage": "interest",
        "since": "a day ago",
        "earlier": {"ended": "Tomas Weller ended it.", "since": "7 days ago"},
        "their_heart": "not drawn to you",
        "their_pace": _PACE[bonds.pace("greta")],
    }
    # The heart is told in words only.
    assert mara["toward_you"] == {"affinity": 20}
    assert '"attraction"' not in text and "heart_moved_s" not in text
    assert you["family"] == {"partners": [{"id": "ilse", "name": "Ilse Weller", "bond": "married"}]}
    assert ilse["family"]["partners"] == [
        {"id": "tomas", "name": "Tomas Weller", "bond": "married"}
    ]
    # The interpret step reads the same people, so "I kiss my wife" finds a wife.
    read = interpret_prompt(state, "I kiss my wife").messages[-1].text
    assert '"bond_with_you":{"stage":"married"' in read


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


def test_bodies_are_as_the_record_says():
    # N6, 2026-11-07: a fight "reopened an old wound" the character never had. The narrator
    # gives nobody an injury their record doesn't hold and never hurts the player character in
    # its update, and the interpret step keeps wounds out of edges and hindrances: code weighs
    # them (A8, `engine.injuries`).
    assert "Bodies are as the record says" in prompts.NARRATOR_SYSTEM
    assert "an old wound included, and never reopen or worsen one" in prompts.NARRATOR_SYSTEM
    assert "Never hurt the player character here" in prompts.NARRATOR_SYSTEM
    assert "never an injury no one's record holds" in prompts.INTERPRET_SYSTEM


def test_the_reading_is_told_what_is_the_places_what_waits_and_what_is_only_dangerous():
    # What the hand plays of 2026-11-14 showed. A glass of brandy poured for a guest at home
    # was a gift of something the character didn't have (C10, R2); "That evening I find the
    # widow" played at half past ten in the morning (W10); and a breakthrough the world calls
    # deadly without a pill was refused as against that rule, where it is the player's to risk
    # (G8, G19). Code backs each of them where it can (`check._props`, `exchanges._of_the_place`,
    # `checks.world_check`).
    guide = " ".join(prompts.INTERPRET_SYSTEM.split())
    assert "everyday things of their own home included: a drink off the shelf" in guide
    assert "Nor does serving an everyday thing of the place" in guide
    assert "begins with the wait: a step of kind wait with until that hour" in guide
    assert "one that only makes it dangerous or costly forbids nothing" in guide


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


def test_the_narrator_gets_the_players_own_words_before_what_they_meant():
    # R1 (Miki, 2026-11-07): the scene tells the gestures and manner the player gave, so the
    # narrator reads their words, not only the interpret step's reading of them.
    said = "I look at him firmly, hold out a gold coin and say: I want this potion."
    intent = Intent(summary="buy the potion with a gold coin")
    action = brief(intent=intent, resolution=stopped_plan(), words=f"  {said}\n").user
    view = json.loads(action.split("## ACTION\n", 1)[1].split("\n## ", 1)[0])
    assert list(view) == ["words", "summary"]
    assert view["words"] == said
    # No words, or blank ones, leave ACTION as the interpret step read it.
    for words in (None, "  "):
        quiet = brief(intent=intent, resolution=stopped_plan(), words=words).user
        assert '"words"' not in quiet.split("## ACTION\n", 1)[1].split("\n## ", 1)[0]


def test_the_narrator_tells_the_action_first_in_its_own_part():
    # R1: the scene opens on the action in `action`, even one the player wrote like a story, and
    # never skips it; "the player's words repeated back" once read as "leave the action out".
    system = prompts.NARRATOR_SYSTEM
    assert "Open on the player's action, in action (R1)" in system
    assert "so does one the player already wrote like a story" in system
    assert "never skip it or start from what it leads to" in system
    assert "never tell the action twice" in system
    assert "repeated back" not in system
    assert "leave action empty" in system
    assert "action still shows the character setting about" in prompts.CUTAWAY_SYSTEM
    assert "- ACTION: the player's own words for this turn (words)" in prompts.BRIEF_GUIDE


def test_the_narrators_answer_asks_for_the_action_first_and_joins_the_scene():
    schema = NarratorOutput.model_json_schema()
    assert list(schema["properties"])[:2] == ["action", "narration"]
    # W2, W6: whether the scene told the talk it was offered, and which news of people's lives
    # it told, is always answered, as `update` is.
    assert schema["required"] == ["action", "narration", "told_talk", "told_news", "update"]
    assert list(schema["properties"])[2:4] == ["told_talk", "told_news"]
    assert NarratorOutput(narration="You wake.").told_news == []
    assert NarratorOutput(narration=" You wake. ").text == "You wake."
    told = NarratorOutput(action=" You hold out the coin. ", narration="\nHe takes it.")
    assert told.text == "You hold out the coin.\n\nHe takes it."
    # A scene written wholly in action is still a scene; only a blank one is refused (T7).
    whole = NarratorOutput.model_validate({"action": "You pay, and he nods.", "narration": ""})
    assert whole.text == "You pay, and he nods."
    for blank in ({"narration": "  "}, {"action": " ", "narration": ""}):
        with pytest.raises(ValidationError):
            NarratorOutput.model_validate(blank)


def _robbed():
    """C10: Milo has taken all twelve of Luca's copper coins (Miki, 2026-11-07)."""
    from engine.apply import DeltaSource, apply_delta
    from engine.contracts import ItemChange, StateDelta

    state = grounded_world()
    purse = state.player.sheet.resources
    purse.money, purse.currency = 12, "copper coins"
    state.characters["milo"] = Character(
        id="milo",
        name="Milo",
        description="A quick-fingered street kid.",
        age=19,
        location_id="bar",
        known_by=["luca"],
        met_by=["luca"],
    )
    state.scene.present_ids.append("milo")
    theft = ItemChange(name="12 copper coins", from_id="luca", to_id="milo", how="stolen")
    applied = apply_delta(state, StateDelta(items=[theft]), ctx(), source=DeltaSource.NARRATOR)
    assert not applied.rejected
    return applied.state


def test_both_models_read_an_empty_purse_and_where_the_coins_went():
    # C10: the narrator once let the player pay Milo with coins Milo had already stolen, since
    # an empty purse never showed and nothing said where the coins went.
    state = _robbed()
    went = (
        '## CHANGED HANDS\n["12 copper coins went from you to Milo (milo), stolen, moments ago."]'
    )

    interpret = interpret_prompt(state, "I tell Milo to keep the coins").messages[-1].text
    narrator = brief(state).user

    for text in (interpret, narrator):
        assert '"money":0,"currency":"copper coins"' in text
        assert went in text
    assert '## CHANGED HANDS\n["(nothing yet)"]' in brief().user
    assert "- CHANGED HANDS: " in prompts.BRIEF_GUIDE
    assert "never count as theirs money or a thing they don't hold" in prompts.INTERPRET_SYSTEM
    assert '("keep the coins as my payment")' in prompts.INTERPRET_SYSTEM
    assert "Never show them paying, handing over or using money" in prompts.NARRATOR_SYSTEM


def test_the_outcome_says_what_a_step_moved_unless_an_event_cut_it_short():
    from engine.contracts import ItemChange, StateDelta

    paid = ItemChange(
        name="5 copper coins", money=True, quantity=5, from_id="luca", to_id="milo", how="pay"
    )

    def outcome(interrupted: bool) -> str:
        step = StepResolution(
            index=0,
            text="pay Milo",
            outcome_class=OutcomeClass.CERTAIN,
            reason="Done.",
            result=StepResult.SUCCESS,
            effects=StateDelta(items=[paid]),
            duration_s=3,
            interrupted=interrupted,
        )
        return brief(_robbed(), resolution=Resolution(steps=[step])).user

    moved = '"changed_hands":[{"what":"5 copper coins","amount":5,"from":"luca","to":"milo"'
    assert moved + ',"money":true}]' in outcome(False)
    assert "changed_hands" not in outcome(True).split("## OUTCOME")[1]


def test_the_outcome_names_the_abilities_a_step_used_so_a_miss_is_the_foes_doing():
    """A3, R1 (Miki, 2026-11-08): an aura blade used several times kept "fizzling" in the
    telling when a fight went against the player. The narrator is told which of the character's
    own powers, techniques and moves worked, and that a miss comes from what stood in the way."""
    missed = StepResolution(
        index=0,
        text="cut the thief's hand with an aura blade",
        outcome_class=OutcomeClass.CONTESTED,
        reason="The thief can push back: even odds.",
        result=StepResult.FAILURE,
        drew_on=["Aura del despertar", "Cuchilla de aura"],
        duration_s=2,
    )
    plain = missed.model_copy(update={"drew_on": []})

    used = brief(resolution=Resolution(steps=[missed])).user.split("## OUTCOME")[1]
    nothing = brief(resolution=Resolution(steps=[plain])).user.split("## OUTCOME")[1]

    assert '"drew_on":["Aura del despertar","Cuchilla de aura"]' in used
    assert "drew_on" not in nothing
    assert "fizzling, faltering, resisting or refusing to come" in prompts.NARRATOR_SYSTEM
    assert "doesn't make it fail again" in prompts.NARRATOR_SYSTEM
    assert "drew_on (their own powers, techniques and moves it used)" in prompts.NARRATOR_SYSTEM
    # The interpret step names a move made with a power, so code can find and record it (A4).
    assert "the move as a technique, by its name as the player calls it" in (
        prompts.INTERPRET_SYSTEM
    )


def test_the_outcome_says_what_a_step_was_done_with_and_how_well():
    """R4 (live run, 2026-11-10): a novice cut a falling leaf with nothing in the way, the
    outcome said only that it worked, and the stroke was told "swift, quiet and perfectly
    clean". Each step now carries the hand it was done with, thrown or not, and the narrator
    tells the doing to match it whatever the result."""
    done = StepResolution(
        index=0,
        text="cut the falling leaf in two",
        outcome_class=OutcomeClass.CERTAIN,
        reason="Nothing stands in the way.",
        result=StepResult.SUCCESS,
        hand="Swordsmanship (novice)",
        duration_s=2,
    )
    raw = done.model_copy(update={"hand": ""})

    told = brief(resolution=Resolution(steps=[done])).user.split("## OUTCOME")[1]
    plain = brief(resolution=Resolution(steps=[raw])).user.split("## OUTCOME")[1]

    assert '"hand":"Swordsmanship (novice)"' in told
    assert '"hand"' not in plain
    system = prompts.NARRATOR_SYSTEM
    assert "hand under a step in OUTCOME is what they did it with and how well" in system
    assert "the hand says how it looks, whatever the result and however easy the thing" in system
    assert "and it looks it, never clean, graceful or effortless" in system
    assert "a master who misses is still plainly a master (R4)" in system
    assert "hand (what they did it with and how well they have it)" in system


def test_a_player_character_with_nothing_on_them_reads_as_carrying_nothing():
    """C10, M5: an empty list of things is shown, not left out, so neither the scene nor its
    picture prompt hands the character a weapon the premise or the genre suggests (Miki,
    2026-11-07: a leap through the trees came out with a dagger the character never had)."""
    state = cultivation_world()  # Lin has nothing on him
    assert not state.player.sheet.resources.items

    text = brief(state).user

    assert '"items":[]' in text
    assert "never give them a weapon or gear they don't have" in prompts.NARRATOR_SYSTEM
    assert "from the world, the premise or earlier" in prompts.NARRATOR_SYSTEM


def test_a_scene_picture_is_asked_for_as_told_and_a_cover_not_at_all():
    """M1, M5: a scene picture shows only its scene. The Library cover is the story's poster,
    drawn from its premise, never from the scene it comes with (Miki, 2026-11-07: "not just a
    random scene"), so the narrator isn't asked to describe it."""
    rules = prompts.NARRATOR_SYSTEM.split("image_prompt (M1, M5):", 1)[1].split("\n\n", 1)[0]

    assert "For a scene, the moment PICTURE's why names, as you told it" in rules
    assert "cover" not in rules
    cover = brief(
        plan=DirectorPlan(
            picture=PictureDecision(kind=PictureKind.COVER, trigger=PictureTrigger.COVER)
        )
    )
    assert "## PICTURE" not in cover.user


def _section(text: str, name: str):
    return json.loads(text.split(f"## {name}\n", 1)[1].split("\n\n## ", 1)[0])


def test_both_models_read_where_the_scene_is_and_what_it_lies_within():
    """R8: the scene's place comes with the places it lies within and whether each is under the
    sky, so a chamber of a buried temple is never told as out in the forest, nor a clearing in
    the forest as still in the temple (Miki, 2026-11-08)."""
    from engine.state.cast import Place, PlaceSetting

    state = cultivation_world()
    state.places["bosque"] = Place(
        id="bosque",
        name="El Bosque de los Susurros",
        kind="wilds",
        setting=PlaceSetting.OUTDOORS,
        parent_id="azure-peak",
        known_by=["lin"],
    )
    state.places["templo"] = Place(
        id="templo",
        name="el Templo Subterráneo",
        kind="building",
        setting=PlaceSetting.UNDERGROUND,
        parent_id="bosque",
        known_by=["lin"],
    )
    state.places["camara"] = Place(
        id="camara", name="la cámara de las runas", kind="room", parent_id="templo"
    )
    state.scene.place_id = "camara"

    for text in (
        brief(state).user,
        interpret_prompt(state, "I climb the stairs").messages[-1].text,
    ):
        place = _section(text, "SCENE")["place"]
        assert (place["id"], place["parent_id"]) == ("camara", "templo")
        assert "setting" not in place  # not told yet
        assert place["within"] == [
            {
                "id": "templo",
                "name": "el Templo Subterráneo",
                "kind": "building",
                "setting": "underground",
            },
            {
                "id": "bosque",
                "name": "El Bosque de los Susurros",
                "kind": "wilds",
                "setting": "outdoors",
            },
            {"id": "azure-peak", "name": "Azure Peak", "kind": "region"},
        ]
        known = {p["id"]: p for p in _section(text, "KNOWN")["places"]}
        assert known["templo"] == {
            "id": "templo",
            "name": "el Templo Subterráneo",
            "within": "bosque",
            "setting": "underground",
        }
        assert known["azure-peak"] == {"id": "azure-peak", "name": "Azure Peak"}

    state.scene.place_id = "azure-peak"  # a place within nothing has no within
    assert "within" not in _section(brief(state).user, "SCENE")["place"]


def test_the_narrator_tells_where_the_character_is_and_records_every_move():
    """R8: the scene keeps to its place, tells a way out as the crossing itself, names places so
    they can't be taken for another kind, and always says where it ends."""
    system = prompts.NARRATOR_SYSTEM
    assert "Keep to where the character is (R8)" in system
    assert "below the ground there is no sky" in system
    assert "leaving a place is told as the crossing itself" in system
    assert "never a word that means a clearing, a square or a field under the sky" in system
    assert "a clearing outside it within the forest, never within the temple" in system
    assert "a setting already given never changes" in system
    assert "a move the scene tells but place_id doesn't name never happened" in system
    assert "- SCENE: the place, with its setting and the places it lies within" in system
    assert "the place each place lies within (within) and its setting" in system


def test_both_models_read_the_talents_and_the_narrator_their_rulings_and_bridges():
    """A4: both models read the talents on the sheet, and the narrator the rulings and the
    bridges there too. The interpret step, which makes a case only for a thing no ruling names
    yet, reads those once, under TALENTS."""
    state = grounded_world()
    sheet = state.player.sheet
    sheet.talents = [
        Talent(id="sword", name="The sword", covers="blades", strength=TalentStrength.ONE_OF_A_KIND)
    ]
    cover = TalentCover(talent_id="sword", fit=TalentFit.RELATED, reason="a draw is half a cut")
    sheet.talent_rulings = [
        TalentRuling(key="technique:quick-draw", what="Quick draw", covers=[cover])
    ]
    sheet.bridges = [
        TalentBridge(
            key="technique:quick-draw",
            what="Quick draw",
            talent_id="sword",
            rests_on="the angle of the holster",
        )
    ]

    def sheet_in(text: str) -> dict:
        you = json.loads(text.split("## PLAYER CHARACTER\n", 1)[1].split("\n\n## ", 1)[0])
        return you["sheet"]

    read, told = interpret_prompt(state, "I practise").messages[-1].text, brief(state).user
    for text in (read, told):
        assert sheet_in(text)["talents"] == [
            {"id": "sword", "name": "The sword", "covers": "blades", "strength": "one_of_a_kind"}
        ]
    assert sheet_in(told)["talent_rulings"] == [
        {
            "key": "technique:quick-draw",
            "what": "Quick draw",
            "covers": [{"talent_id": "sword", "fit": "related", "reason": "a draw is half a cut"}],
        }
    ]
    assert sheet_in(told)["bridges"] == [
        {
            "key": "technique:quick-draw",
            "what": "Quick draw",
            "talent_id": "sword",
            "rests_on": "the angle of the holster",
        }
    ]
    assert not {"talent_rulings", "bridges"} & set(sheet_in(read))
    assert '"ruled":[{"what":"Quick draw","stands":{"sword":"related"}}]' in read


def test_the_interpret_prompt_gathers_what_to_rule_on_under_talents():
    """A4 (live run, 2026-11-10): the real model read the talents on the sheet and never said
    how they stood to what was being learned, so nothing was ruled on. What it has to rule on is
    now a section of its own beside the action: the talents that reach some things and not
    others, what is already ruled with how each stands, and the ground bridges already tried."""
    state = grounded_world()
    sheet = state.player.sheet

    def talents(of=state):
        text = interpret_prompt(of, "I practise the draw").messages[-1].text
        if "## TALENTS\n" not in text:
            return None
        return json.loads(text.split("## TALENTS\n", 1)[1].split("\n\n## ", 1)[0])

    # Nobody without a talent is asked, nor someone whose only talent covers everything.
    assert talents() is None
    sheet.talents = [Talent(id="quick", name="Quick study", general=True)]
    assert talents() is None

    sheet.talents += [
        Talent(id="sword", name="The sword", covers="blades", strength=TalentStrength.GENIUS),
        Talent(id="maths", name="Hopeless at sums", covers="numbers", strength=TalentStrength.SLOW),
    ]
    assert talents() == {
        "talents": [
            {"id": "sword", "name": "The sword", "covers": "blades"},
            {"id": "maths", "name": "Hopeless at sums", "covers": "numbers", "weakness": True},
        ],
        "ruled": [],  # shown empty, so "nothing ruled yet" is said and not left out
    }

    cover = TalentCover(talent_id="sword", fit=TalentFit.RELATED, reason="a draw is half a cut")
    sheet.talent_rulings = [
        TalentRuling(key="technique:quick-draw", what="Quick draw", covers=[cover])
    ]
    sheet.bridges = [
        TalentBridge(
            key="technique:quick-draw",
            what="Quick draw",
            talent_id="sword",
            rests_on="the angle of the holster",
            steps=0,
        )
    ]
    told = talents()
    # A talent the ruling doesn't list is outside, and a bridge that didn't hold shows as tried.
    assert told["ruled"] == [
        {"what": "Quick draw", "stands": {"sword": "related", "maths": "outside"}}
    ]
    assert told["bridges"] == [
        {
            "what": "Quick draw",
            "talent_id": "sword",
            "rests_on": "the angle of the holster",
            "held": False,
        }
    ]
    # It sits next to the action, where the player makes their case, and the narrator, who
    # rules on nothing, isn't given it.
    text = interpret_prompt(state, "I practise the draw").messages[-1].text
    assert [part.split("\n", 1)[0] for part in text.split("\n\n## ")][-3:] == [
        "TALENTS",
        "LANGUAGE",
        "ACTION",
    ]
    assert "## TALENTS" not in brief(state).user


def test_the_interpret_step_is_asked_for_the_case_on_a_talent_and_for_bridges():
    """A4, A9: the model proposes how a talent stands to a new thing and what a bridge rests
    on; code records the ruling once and throws for the bridge. Both are answered on every
    step, with nothing where there is nothing to say."""
    system = prompts.INTERPRET_SYSTEM
    assert "- TALENTS, when it is given, holds PLAYER CHARACTER's talents" in system
    assert "- talent_cases, always: an empty list when TALENTS isn't given." in system
    assert "trains, practises or learns something (a skill, a technique" in system
    assert "or uses a technique or a move of their own, and TALENTS.ruled doesn't name" in system
    assert "one entry for each talent in TALENTS.talents" in system
    assert "Weigh the case the player makes in this action for why a talent applies" in system
    assert "Judge each talent on its own: where several reach the thing, code adds their" in system
    assert "A thing TALENTS.ruled names is settled, whatever the player argues now" in system
    assert "one the player declares now is a backstory claim, not a talent" in system
    assert "- bridge, always: null when TALENTS isn't given" in system
    assert "never ground TALENTS.bridges already lists for that thing" in system
    assert "Only a deed is a bridge: words that restate the case are not" in system
    assert "practising the thing itself is training" in system


def test_the_narrator_tells_a_ruling_or_a_bridge_in_the_storys_own_words():
    system = prompts.NARRATOR_SYSTEM
    assert "never as a pace, a ruling or a bridge by name" in system


def _barn_killing(state, *, heard_by):
    state.deeds["barn"] = Deed(
        id="barn",
        actor_id="tomas",
        kind="kill",
        text="Tomas killed a thief in the barn",
        turn=1,
        world_s=0,
        place_id="farm",
        severity=4,
        heard_by=dict.fromkeys(heard_by, 0.7),
    )
    return state


def _to(*ids: str) -> Intent:
    step = IntentStep(
        text="call on them",
        verb="greet",
        kind=ActionKind.CONVERSATION,
        proposed_duration_s=5 * MINUTE,
        target_ids=list(ids),
    )
    return Intent(steps=[step])


def _arrived(state, place_id: str):
    after = state.model_copy(deep=True)
    after.player.location_id = place_id
    return after


def test_the_narrator_is_told_who_a_turn_may_bring_into_the_scene_as_the_record_has_them():
    """W4, E4: in the first live story about it (2026-11-11) Tomas walked over to Old Bram, who
    had heard talk of a killing, and the scene played Bram as a friend. KNOWN had him by name
    alone, so the narrator met him without how he is toward Tomas. Whoever the action names
    comes as SCENE shows its people, and so does whoever the record has where a trip took the
    character."""
    state = _barn_killing(farm_world(), heard_by=["bram"])

    # A scene at the farm that names nobody: Bram is in the village, and Ilse is under SCENE.
    assert "## WHO ELSE" not in brief(state).user
    # The action names him: how he is toward Tomas, and not where he is (C6).
    (named,) = _section(brief(state, intent=_to("bram", "ilse")).user, "WHO ELSE")
    assert named["id"] == "bram" and named["name"] == "Old Bram"
    assert named["toward_you"]["affinity"] == 30
    (heard,) = named["toward_you"]["heard_said"]
    assert "killed a thief in the barn" in heard
    assert not {"here", "location_id", "stranger"} & named.keys()
    # A trip took Tomas to the village: the record has Bram there.
    (there,) = _section(brief(state, after=_arrived(state, "village")).user, "WHO ELSE")
    assert there["id"] == "bram" and there["here"] is True and there["location_id"] == "village"
    assert there["toward_you"] == named["toward_you"]
    # A trip that stopped on the way: the scene ends on the road, where the record has nobody.
    state.characters["nel"] = Character(
        id="nel", name="Nel", location_id="farm", known_by=["tomas"]
    )
    road = StepResolution(
        index=0,
        text="walk to the village",
        outcome_class=OutcomeClass.CERTAIN,
        reason="Nothing stops it.",
        result=StepResult.SUCCESS,
        duration_s=10 * MINUTE,
        trip=Trip(from_id="farm", to_id="village", arrived=False),
    )
    assert [c["id"] for c in _section(brief(state).user, "WHO ELSE")] == ["nel"]
    assert "## WHO ELSE" not in brief(state, resolution=Resolution(steps=[road])).user

    system = prompts.NARRATOR_SYSTEM
    assert "- Whoever comes into the scene is who the record says (W4, E4)." in system
    assert "never warmer, colder or better informed than it says" in system
    assert "use one of these who fits before making anyone up" in system
    assert "Nobody is in the scene just for being listed" in system


def _outing(state, who: str, to: str, stay_s: int):
    """The world takes `who` to `to` for `stay_s`: a round trip (`engine.world.returns`)."""
    person = state.characters[who]
    was, person.location_id = person.location_id, to
    w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=SeededRng.for_turn("s", "main", 2))
    return returns.left(w, person, was, (stay_s, stay_s))


def test_the_narrator_is_told_a_neighbour_is_away_and_about_when_they_are_back():
    """W6: whoever the world sent somewhere comes back, so the scene has something true to say
    of a neighbour it can't show: that they are gone, about when they are back, and where to
    when the player character knows of that place (C6)."""
    state = farm_world()
    state.characters["mara"] = Character(
        id="mara", name="Mara", location_id="farm", known_by=["tomas"]
    )
    state.places["town"] = Place(id="town", name="Harrow", kind="town")  # news to Tomas
    state.places["village"].routes.append(Route(to_id="town", travel_s=DAY))

    def named(who: str) -> dict:
        (view,) = _section(brief(state, intent=_to(who)).user, "WHO ELSE")
        return view

    # Mara of the farm is in Millbrook for two days, and then the walk home.
    _outing(state, "mara", "village", 2 * DAY)
    mara = named("mara")
    assert mara["away"] == {"back": "in 2 days", "to": "Millbrook"}
    assert not {"here", "location_id"} & mara.keys()
    # She went on to a town Tomas has never heard of: gone, and nothing on where.
    _outing(state, "mara", "town", 2 * DAY)
    assert named("mara")["away"] == {"back": "in 3 days"}
    # Bram is away from Millbrook, which is not where this scene is: he is only elsewhere.
    _outing(state, "bram", "town", 2 * DAY)
    assert "away" not in named("bram")
    # At the farm on an errand of his own he is here, and nobody's absent neighbour.
    state.characters["bram"].location_id = "farm"
    bram = named("bram")
    assert bram["here"] is True and "away" not in bram

    assert "away: they belong here and are off somewhere for now." in prompts.NARRATOR_SYSTEM


def test_who_else_is_those_the_turn_is_about_and_then_whoever_matters_at_the_place():
    state = _barn_killing(cultivation_world(), heard_by=[])
    lin = state.player_id
    crowd = {
        "a-friend": {"known_by": [lin]},
        "b-cook": {},  # nobody to Lin, and nobody at the peak either
        "c-rival": {"heard": True},
        "d-master": {"prominence": Prominence.KEY},
        "e-dead": {
            "known_by": [lin],
            "status": CharacterStatus.DEAD,
            "death_certainty": DeathCertainty.CONFIRMED,
        },
        "f-far": {"known_by": [lin], "location_id": None},
    }
    for cid, extra in crowd.items():
        heard = extra.pop("heard", False)
        fields = {"location_id": "inner-court", "prominence": Prominence.MINOR} | extra
        state.characters[cid] = Character(id=cid, name=cid.title(), **fields)
        if heard:
            state.deeds["barn"].heard_by[cid] = 0.7
    state.deeds["barn"].actor_id = lin
    after = _arrived(state, "inner-court")
    feud = PlannedEvent(
        size=EventSize.LOCAL,
        kind=EventKind.VISITOR,
        source=EventSource.DECK,
        title="Someone comes",
        brief="SOMEONE-COMES",
        cast_ids=["f-far"],
    )

    others = _section(brief(state, after=after, plan=DirectorPlan(event=feud)).user, "WHO ELSE")

    # The event's own first, then who has heard of Lin, who Lin knows, and the key people.
    assert [c["id"] for c in others] == ["f-far", "c-rival", "a-friend", "d-master", "elder-mo"]
    by_id = {c["id"]: c for c in others}
    assert "here" not in by_id["f-far"] and "location_id" not in by_id["f-far"]
    assert all(by_id[i]["here"] is True for i in ("c-rival", "a-friend", "d-master", "elder-mo"))
    # Someone Lin neither knows nor has met is a stranger to him, whatever the record calls them.
    assert {i for i, c in by_id.items() if c.get("stranger")} == {"c-rival", "d-master", "elder-mo"}
    # Zhao was in the scene when it began: SCENE has him, here or not.
    assert "zhao" not in by_id


def test_who_else_leaves_out_whom_a_step_made_real_and_stops_at_a_handful():
    state = cultivation_world()
    lin = state.player_id
    for n in range(12):
        state.characters[f"disciple-{n}"] = Character(
            id=f"disciple-{n}", name=f"Disciple {n}", location_id="well", known_by=[lin]
        )
    made = StepResolution(
        index=0,
        text="shove a passer-by",
        outcome_class=OutcomeClass.CERTAIN,
        reason="Nothing stops it.",
        result=StepResult.SUCCESS,
        duration_s=5,
        strangers=["disciple-0"],
    )

    others = _section(brief(state, resolution=Resolution(steps=[made])).user, "WHO ELSE")

    assert [c["id"] for c in others] == [f"disciple-{n}" for n in range(1, 9)]


def test_the_narrator_is_not_offered_whoever_a_move_wronged_and_who_did_not_see_it():
    """W17, W10. In the first stories about an affair on the real model (2026-11-13) the
    narrator walked the wronged partner into the scene of a move the engine had decided they
    didn't see. Whoever this turn's move wrongs and who wasn't there is not among those the
    scene may bring in, even from the same place, and OUTCOME says of each whether they saw
    it. An event that is about them brings them, as the world's own doing."""
    state = farm_world()
    state.scene.present_ids = ["tomas"]  # Ilse is about the farm, and not at the gate

    (ilse,) = _section(brief(state).user, "WHO ELSE")
    assert ilse["id"] == "ilse" and ilse["here"] is True

    state.deeds["deed-1"] = Deed(
        id="deed-1",
        actor_id="tomas",
        kind="court",
        text="kiss Mara (it worked)",
        turn=2,
        world_s=state.world_s,
        place_id="farm",
        wronged_ids=["ilse"],
    )
    assert "## WHO ELSE" not in brief(state).user
    # An earlier turn's move keeps her out of nothing now.
    assert "## WHO ELSE" in brief(state, context=ctx(turn=3)).user
    # The world brings her: an event of this turn is about her.
    comes = PlannedEvent(
        size=EventSize.PERSONAL,
        kind=EventKind.VISITOR,
        source=EventSource.DECK,
        title="Ilse comes round the barn",
        brief="ILSE-COMES",
        cast_ids=["ilse"],
    )
    (brought,) = _section(brief(state, plan=DirectorPlan(event=comes)).user, "WHO ELSE")
    assert brought["id"] == "ilse"

    system = " ".join(prompts.NARRATOR_SYSTEM.split())
    assert "They are not in this scene and never come into it" in system
    assert "So is anyone under KNOWN who is in neither SCENE nor WHO ELSE" in system
    assert "only the world moves anyone else (W10)" in system


def test_the_narrator_reads_a_heart_that_closed_when_they_ended_it():
    """W17. Whoever ended it has made up their mind, and the narrator is told so in place of
    how drawn they still are: otherwise a wife who left yesterday reads as "starting to be
    drawn to you". Once the while has passed, their heart is told as it stands again."""
    state = farm_world()
    state.world_s = 400 * DAY
    state.characters["ilse"].attitude_toward("tomas").attraction = 35
    bonds.end(
        state.bonds["bond-1"], by_id="ilse", how="Ilse Weller ended it.", turn=1, world_s=399 * DAY
    )

    def heart(of: WorldState) -> str:
        scene = json.loads(brief(of).user.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
        (ilse,) = [p for p in scene["present"] if p["id"] == "ilse"]
        assert ilse["bond_with_you"]["stage"] == "over"
        return ilse["bond_with_you"]["their_heart"]

    assert heart(state) == "closed to you since they ended it"
    state.world_s += bonds.REST_S[bonds.pace("ilse")] * bonds.ENDED_RESTS
    assert heart(state) == "starting to be drawn to you"
    assert "A heart that is closed since they ended it answers nothing of the kind" in " ".join(
        prompts.NARRATOR_SYSTEM.split()
    )


def test_the_narrator_reads_how_someone_holds_to_a_partner_of_their_own():
    """W17. Someone who has a partner weighs it when anyone else courts them, each in their
    own way, and the narrator is told which: otherwise a devoted wife flirts back in the
    telling while the rules turn every advance down."""
    state = farm_world()
    state.scene.present_ids = ["tomas", "ilse", "bram", "mara"]
    state.characters["mara"] = Character(id="mara", name="Mara", age=29, location_id="farm")
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    wed = BondStep(stage=BondStage.MARRIED)
    state.bonds["bond-2"] = Bond(
        id="bond-2", a_id="jorn", b_id="mara", stage=BondStage.MARRIED, steps=[wed]
    )

    def read(of: WorldState) -> tuple[dict, dict]:
        text = brief(of).user
        scene = json.loads(text.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
        you = json.loads(text.split("## PLAYER CHARACTER\n", 1)[1].split("\n\n## ", 1)[0])
        return {p["id"]: p for p in scene["present"]}, you

    present, you = read(state)
    mara = present["mara"]
    assert bonds.faith(state, state.characters["mara"]) is Faith.STEADFAST
    assert mara["family"] == {
        "partners": [{"id": "jorn", "name": "Jorn", "bond": "married"}],
        "faith": "keeps to their partner: nobody else moves them while that bond holds",
    }
    assert "bond_with_you" not in mara  # nothing has been between the two
    # Someone with nobody has nothing to weigh, and the player character's heart is their own.
    assert "family" not in present["bram"] and "faith" not in you["family"]
    assert (
        present["ilse"]["family"]["faith"] == _FAITH[bonds.faith(state, state.characters["ilse"])]
    )

    # Once a move is on record, her heart reads closed, and whom she keeps to.
    made = BondStep(stage=BondStage.INTEREST, turn=3, by_id="tomas")
    state.bonds["bond-3"] = Bond(id="bond-3", a_id="tomas", b_id="mara", steps=[made])
    assert read(state)[0]["mara"]["bond_with_you"]["their_heart"] == (
        "closed to you: they keep to Jorn"
    )
    # Someone torn is told as such, with their heart as it stands.
    state.characters["mara"].faith = Faith.TORN
    mara = read(state)[0]["mara"]
    assert mara["family"]["faith"] == (
        "could be moved by someone else, with their partner standing in the way"
    )
    assert mara["bond_with_you"]["their_heart"] == "not drawn to you"
    state.characters["mara"].faith = Faith.ROVING
    assert read(state)[0]["mara"]["family"]["faith"] == "lets a partner stand in nobody's way"
    # Where several partners are the custom there is nothing of the kind to weigh.
    state.bible.several_partners = True
    assert "faith" not in read(state)[0]["mara"]["family"]

    system = " ".join(prompts.NARRATOR_SYSTEM.split())
    assert "faith under a person who has a partner says how" in system
    assert "never wavers, hints or flirts back" in system
    assert "they have made up their mind and say so" in system


def _ten_years_on() -> WorldState:
    """Tomas is back at the farm after ten years away, and Mara, whom he knew, is in the
    scene. In those years the world gave her a partner the record lacked, the two married
    and had a child (`engine.world.lives`), and nobody has told him."""
    state = farm_world()
    state.world_s = 10 * YEAR
    state.scene.present_ids = ["tomas", "ilse", "mara"]
    state.characters["ilse"].seen_s = state.world_s - DAY
    state.characters["mara"] = Character(
        id="mara", name="Mara", age=39, location_id="farm", met_by=["tomas"], seen_s=0
    )
    state.characters["char-9"] = Character(
        id="char-9",
        name="Mara's partner",
        age=41,
        location_id="farm",
        known_by=["mara"],
        origin=Origin(kind=OriginKind.ENGINE, ref_id="mara", text="Found a life with Mara."),
    )
    state.characters["char-10"] = Character(
        id="char-10",
        name="Mara's child",
        age=4,
        born_s=6 * YEAR,
        location_id="farm",
        parent_ids=["mara", "char-9"],
        known_by=["mara", "char-9"],
        origin=Origin(kind=OriginKind.BIRTH, ref_id="bond-2", text="Born to Mara."),
    )
    wed = BondStep(stage=BondStage.MARRIED, world_s=4 * YEAR)
    state.bonds["bond-2"] = Bond(
        id="bond-2", a_id="mara", b_id="char-9", stage=BondStage.MARRIED, steps=[wed]
    )
    for n, (kind, year, child) in enumerate(
        [(LifeKind.PAIRED, 2, None), (LifeKind.MARRIED, 4, None), (LifeKind.CHILD, 6, "char-10")],
        start=1,
    ):
        state.lives[f"life-{n}"] = LifeEvent(
            id=f"life-{n}",
            kind=kind,
            subject_ids=["mara", "char-9"],
            child_id=child,
            world_s=year * YEAR,
            known_by=["mara", "char-9"],
        )
    return state


def test_the_narrator_reads_what_the_years_brought_someone_met_again():
    """W6, W10 (Miki, 2026-11-13): "if you meet someone again after 10 years of training, you
    cannot expect that someone to stay single", and "a narrator should know". Under someone the
    player character hasn't seen in a long while, the brief says how long it has been and what
    that time brought them, with whom, and marks a partner or a child the world brought who
    still needs a name. Their family reads as it is now, with the child at the age they are."""
    state = _ten_years_on()

    present = {p["id"]: p for p in _section(brief(state).user, "SCENE")["present"]}

    mara = present["mara"]
    partner = {"id": "char-9", "name": "Mara's partner", "unnamed": True}
    assert mara["last_seen"] == "10 years ago"
    assert mara["news"] == [
        {"id": "life-1", "what": "found a partner", "when": "8 years ago", "with": partner},
        {"id": "life-2", "what": "married", "when": "6 years ago", "with": partner},
        {
            "id": "life-3",
            "what": "had a child",
            "when": "4 years ago",
            "with": partner,
            "child": {"id": "char-10", "name": "Mara's child", "unnamed": True},
        },
    ]
    assert mara["family"]["partners"] == [
        {"id": "char-9", "name": "Mara's partner", "bond": "married"}
    ]
    assert mara["family"]["children"] == [{"id": "char-10", "name": "Mara's child", "age": 4}]
    # The engine's own bookkeeping stays out: the brief says it in words.
    assert not {"seen_s", "born_s", "solitary"} & mara.keys()
    # Someone seen a day ago has no such line, and someone the years brought nothing has no
    # news: "maybe 10 years go by and the person is exactly the same".
    assert not {"last_seen", "news"} & present["ilse"].keys()

    # Once the story has named them, they are told by that name like anyone.
    state.characters["char-9"].name = "Edrik"
    mara = _section(brief(state).user, "SCENE")["present"][-1]
    assert mara["news"][0]["with"] == {"id": "char-9", "name": "Edrik"}


def test_the_brief_says_outright_that_the_two_meet_again_after_years():
    """W6: in the second live story of a homecoming (2026-11-13) a man came back to his
    village after nine years, `last_seen` stood under each neighbour, and one of them said
    they hadn't expected him back so soon. So the brief says it on its own: whom this scene
    has the player character meet again after a year or more, how long it has been, and that
    the scene is told as that, with some of their news where the years brought any."""
    state = _ten_years_on()

    again = _section(brief(state).user, "MEETING AGAIN")

    assert again["people"] == [{"who": "Mara", "last_seen": "10 years ago"}]  # not Ilse
    assert "first time the player character is with them since" in again["tell"]
    assert "nobody talks as if it had been days" in again["tell"]
    assert "at least one piece of the news under them" in again["tell"]
    # In the third live story the narration gave a wedding as something he already knew.
    assert "The player character learns it there" in again["tell"]
    assert "never gives it as something they already know" in again["tell"]

    # Someone the years brought nothing is met again all the same, with no news owed.
    state.lives.clear()
    quiet = _section(brief(state).user, "MEETING AGAIN")
    assert quiet["people"] == again["people"] and "news" not in quiet["tell"]
    assert "already know" not in quiet["tell"]

    # Under a year apart is no reunion, and neither is the scene after the one they met in.
    state.characters["mara"].seen_s = state.world_s - 300 * DAY
    assert "## MEETING AGAIN" not in brief(state).user
    met, _ = pipeline.settle_lives(_ten_years_on())
    assert "## MEETING AGAIN" not in brief(met).user

    # The section carries its own instruction, so the rules only say what it is.
    system = " ".join(prompts.NARRATOR_SYSTEM.split())
    assert "- MEETING AGAIN: whom this scene has the player character meet again" in system


def test_someone_far_away_brings_no_news_of_theirs_into_a_scene():
    """W6, C6: the years show, and their news is told, when the two meet. In the second live
    story of a homecoming (2026-11-13) a man heard in a city three days off what had come to
    two of his village. Someone a scene only thinks of, speaks of or has a moment about is
    far away, and so is their news: the brief hands it only of someone who is in the scene,
    who is at its place, or whom an event of the world's brings."""
    state = _ten_years_on()
    state.scene.present_ids = ["tomas", "ilse"]
    state.characters["mara"].location_id = "village"
    asks = Intent(
        steps=[
            IntentStep(
                text="ask Ilse about Mara",
                verb="ask",
                kind=ActionKind.CONVERSATION,
                proposed_duration_s=60,
                target_ids=["ilse", "mara"],
            )
        ]
    )
    thought = DirectorPlan(moment=PlannedMoment(id="m1", brief="A-MEMORY", cast_ids=["mara"]))

    for told in (brief(state, intent=asks), brief(state, plan=thought)):
        (mara,) = _section(told.user, "WHO ELSE")
        assert mara["id"] == "mara" and not {"here", "last_seen", "news"} & mara.keys()
        assert told.news == () and "## MEETING AGAIN" not in told.user

    # An event of the world's brings her: she is met, years and news with her.
    comes = PlannedEvent(
        size=EventSize.PERSONAL,
        kind=EventKind.VISITOR,
        source=EventSource.DECK,
        title="Mara comes up the lane",
        brief="MARA-COMES",
        cast_ids=["mara"],
    )
    told = brief(state, plan=DirectorPlan(event=comes))
    (mara,) = _section(told.user, "WHO ELSE")
    assert mara["last_seen"] == "10 years ago" and len(mara["news"]) == 3
    assert told.news == ("life-1", "life-2", "life-3")
    assert _section(told.user, "MEETING AGAIN")["people"][0]["who"] == "Mara"


def test_news_stays_under_someone_until_a_scene_says_it_told_it():
    """C6: a scene the two share is where the player character can hear it, and has heard
    only what the scene told. After a scene that told none of it the record has them as seen
    and the next brief still carries the news; each piece leaves the brief once a scene told
    it. The brief keeps which news it handed the scene, for code to hold the answer to."""
    state = _ten_years_on()
    assert brief(state).news == ("life-1", "life-2", "life-3")

    silent, heard = pipeline.settle_lives(state)

    assert heard == []
    mara = _section(brief(silent).user, "SCENE")["present"][-1]
    assert "last_seen" not in mara and [n["id"] for n in mara["news"]] == [
        "life-1",
        "life-2",
        "life-3",
    ]

    some, heard = pipeline.settle_lives(silent, ["life-2"])

    assert heard == ["life-2"] and brief(some).news == ("life-1", "life-3")

    after, heard = pipeline.settle_lives(some, ["life-1", "life-3"])

    assert heard == ["life-1", "life-3"] and brief(after).news == ()
    mara = _section(brief(after).user, "SCENE")["present"][-1]
    assert not {"last_seen", "news"} & mara.keys()
    assert mara["family"]["partners"][0]["name"] == "Mara's partner"  # what is, stays told
    # The state the scene began in is untouched (B4).
    assert state.characters["mara"].seen_s == 0 and state.lives["life-1"].known_by[-1] == "char-9"


def test_someone_with_news_in_the_scene_is_what_there_is_to_hear_in_place_of_made_up_talk():
    """W6, W2: in the first live story of a homecoming (2026-11-13) a man asked his neighbours
    how the ten years had been, the brief offered talk of the narrator's own making, and the
    scene told that in place of the news it had under them. With news of someone the scene
    shows, that is the talk on offer; a rumor on record is still the place's own saying."""
    state = _ten_years_on()
    asked = DirectorPlan(talk=PlannedTalk(asked=True))

    assert _section(brief(state, plan=asked).user, "TALK") == {"news": True, "asked": True}
    passing = DirectorPlan(talk=PlannedTalk())
    assert _section(brief(state, plan=passing).user, "TALK") == {"news": True}

    # Mara isn't in the scene, and may come into it: her news is still what there is to hear.
    state.scene.present_ids = ["tomas", "ilse"]
    assert brief(state, plan=asked).news == ("life-1", "life-2", "life-3")
    assert _section(brief(state, plan=asked).user, "TALK") == {"news": True, "asked": True}

    # Once it is told, talk is the narrator's to make up again.
    told, _ = pipeline.settle_lives(state, ["life-1", "life-2", "life-3"])
    assert _section(brief(told, plan=asked).user, "TALK") == {"own": True, "asked": True}


def test_no_more_than_the_latest_news_of_someone_is_read():
    state = _ten_years_on()
    for n in range(4, 12):
        state.lives[f"life-{n}"] = LifeEvent(
            id=f"life-{n}", kind=LifeKind.FRIENDS, subject_ids=["mara", "bram"], world_s=n * DAY
        )

    mara = _section(brief(state).user, "SCENE")["present"][-1]

    assert [told["what"] for told in mara["news"]] == [
        "became close friends with someone",
        "became close friends with someone",
        "found a partner",
        "married",
        "had a child",
    ]


def test_someone_who_comes_into_the_scene_is_read_with_their_years_too():
    """W4: Mara isn't in the scene yet, and the turn may bring her in from the same place. WHO
    ELSE reads her as the record has her now, so the narrator doesn't bring in the Mara of ten
    years ago."""
    state = _ten_years_on()
    state.scene.present_ids = ["tomas", "ilse"]

    others = {p["id"]: p for p in _section(brief(state).user, "WHO ELSE")}

    assert others["mara"]["last_seen"] == "10 years ago"
    assert [told["what"] for told in others["mara"]["news"]] == [
        "found a partner",
        "married",
        "had a child",
    ]


def test_the_narrator_reads_what_the_scenes_own_time_brought_the_people_around():
    """W6, C6. Where the player character lives among them, they see or hear what comes to
    people as it happens, so a scene that covers a year is told it under LIVES. What an
    earlier turn brought, and what nobody told them, stays out, and a scene with no such news
    has no section."""
    before = farm_world()
    before.world_s = 9 * YEAR
    before.characters["mara"] = Character(
        id="mara", name="Mara", age=38, location_id="village", met_by=["tomas"]
    )
    assert "## LIVES" not in brief(before).user

    after = before.model_copy(deep=True)
    after.world_s = 10 * YEAR
    told = {"subject_ids": ["bram", "mara"], "known_by": ["bram", "mara", "tomas"]}
    turn = ctx().turn
    after.lives = {
        "life-1": LifeEvent(
            id="life-1", kind=LifeKind.FELL_OUT, world_s=8 * YEAR, turn=turn - 1, **told
        ),
        "life-2": LifeEvent(
            id="life-2", kind=LifeKind.FRIENDS, world_s=9 * YEAR + 183 * DAY, turn=turn, **told
        ),
        "life-3": LifeEvent(
            id="life-3",
            kind=LifeKind.PARTED,
            subject_ids=["mara", "bram"],
            by_id="bram",
            world_s=9 * YEAR + 300 * DAY,
            turn=turn,
            known_by=["bram", "mara"],
        ),
    }

    text = brief(before, after=after).user

    assert _section(text, "LIVES") == [
        {
            "who": {"id": "bram", "name": "Old Bram"},
            "what": "became close friends with someone",
            "when": "6 months ago",
            "with": {"id": "mara", "name": "Mara"},
        }
    ]


def test_the_scenes_news_is_told_of_whoever_the_player_character_knows():
    """C6: news is told of someone the player character knows, with whoever it was with. An
    event whose first subject they have never heard of is told of the other, and one between
    two people they have never heard of isn't told at all."""
    before = farm_world()
    before.world_s = 9 * YEAR
    for cid, name in (("wen", "Wen"), ("odo", "Odo")):
        before.characters[cid] = Character(id=cid, name=name, age=30, location_id="village")
    after = before.model_copy(deep=True)
    after.world_s = 10 * YEAR
    turn = ctx().turn
    after.lives = {
        "life-1": LifeEvent(
            id="life-1",
            kind=LifeKind.FRIENDS,
            subject_ids=["wen", "bram"],
            world_s=9 * YEAR + 183 * DAY,
            turn=turn,
            known_by=["wen", "bram", "tomas"],
        ),
        "life-2": LifeEvent(
            id="life-2",
            kind=LifeKind.FELL_OUT,
            subject_ids=["wen", "odo"],
            world_s=9 * YEAR + 200 * DAY,
            turn=turn,
            known_by=["wen", "odo", "tomas"],
        ),
    }

    told = _section(brief(before, after=after).user, "LIVES")

    assert [(line["who"]["id"], line["with"]["id"]) for line in told] == [("bram", "wen")]


def test_the_narrator_is_told_people_lead_lives_of_their_own():
    """W6: the rule the brief's lines stand on, and Miki's own limit to it: nothing is made
    to happen, and nobody gets a wedding or a child the record doesn't hold."""
    system = " ".join(prompts.NARRATOR_SYSTEM.split())

    assert "People lead lives of their own while the story is elsewhere (W6, W10)." in system
    assert "after years they are that much older, and it shows on them" in system
    assert "never undo it, and never make up a wedding, a child or a parting" in system
    assert "Someone marked unnamed is a partner or a child the world brought" in system
    assert "Someone with no news is as they were left, a little older" in system
    # What the first live homecoming showed was missing (2026-11-13): the news is told before
    # anything made up, the scene says which of it it told, and the years are counted once.
    assert "shows or says at least one piece of that news before anything of your own" in system
    assert "Under told_news, list the id of every piece of news the scene showed or said" in system
    assert "never list a piece the scene didn't tell, and never leave out one it did" in system
    assert "never set age for someone who has one" in system
    assert (
        "news in place of saying or own: someone in SCENE or WHO ELSE, or WIDER WORLD, has news"
        in system
    )
    assert "so the scene makes up no talk of its own" in system
    assert 'does a partner it gave someone ("Mara\'s partner")' in system
    assert "last_seen and news where time has gone by" in system
