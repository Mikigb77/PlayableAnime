"""The turn graph end to end on the scripted fake model (B5, B7, F4, T7, C3).

The fake sits under the real model client, so these turns go through the same streaming, retry,
block and telemetry code a live turn does.
"""

import json
import subprocess
import sys
from contextlib import aclosing

import pytest

from engine import pipeline
from engine.context import ImageSetting, Rating, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    OutcomeClass,
    PictureKind,
    Resolution,
    StandingAction,
    StepResolution,
)
from engine.invariants import InvariantError
from engine.pipeline import TimePassage
from engine.samples import cultivation_world, grounded_world
from engine.state.cast import CharacterStatus
from engine.state.records import Goal, GoalStatus, StepResult
from engine.state.scene import Bout, Encounter, EncounterKind, Terms
from engine.state.sheet import Health
from engine.state.world import Chapter
from engine.visibility import status_view
from graph.llm import Block, Fail, Hang, LLMUnavailable, Node, Reply
from graph.turn import (
    CHAPTER_TURNS,
    MAX_CHAPTER_TURNS,
    RECENT_SCENES,
    NarrationDelta,
    NarrationReset,
    PastScene,
    Reading,
    StepsDecided,
    TurnCompleted,
    TurnInput,
    TurnKind,
    UnreadableAction,
    prompts,
    run_turn,
)
from graph.turn.context import asks
from graph.turn.form import intent_form
from tests.graph.conftest import collect, run

STONE = {
    "summary": "Lin throws a stone at Zhao, then runs for the gate.",
    "steps": [
        {
            "text": "throw a stone at Zhao",
            "verb": "throw",
            "target_ids": ["zhao"],
            "kind": "exchange",
            "proposed_duration_s": 2,
        },
        {
            "text": "run for the gate",
            "verb": "run",
            "kind": "move",
            "proposed_duration_s": 40,
        },
    ],
}

SCENE = {
    "narration": "You stoop, close your fingers on a stone and let it fly.",
    "suggestions": [
        {"label": "Taunt Zhao", "kind": "thread"},
        {"label": "Wait", "kind": "side"},
        {"label": "Taunt Zhao", "kind": "personal"},
        {"label": "Visit the herb garden", "kind": "side"},
        {"label": "Head to the archives", "kind": "wild"},
        {"label": "Pray", "kind": "personal"},
    ],
    "image_prompt": "Lin Feng mid-throw at the well, Zhao recoiling.",
    "update": {
        "characters": [{"id": "elder_mo", "name": "Elder Mo"}],
        "scene_end": {
            "ended_on": "Zhao wipes the blood from his brow and laughs.",
            "place_id": "well",
            "present_ids": ["lin", "zhao", "nobody"],
            "positions": ["Zhao by the bucket"],
        },
        "summary": "Lin struck back at Zhao.",
    },
}


def turn_input(state=None, kind=TurnKind.ACTION, **extra) -> TurnInput:
    state = state or cultivation_world()
    settings = extra.pop("settings", StorySettings())
    ctx = TurnContext(
        story_id="story-1",
        turn=state.turn + 1,
        settings=settings,
        rating=extra.pop("rating", Rating.TEEN),
    )
    if kind in (TurnKind.ACTION, TurnKind.CHOICE):
        extra.setdefault("action", "I throw a stone at Zhao, then run for the gate")
    return TurnInput(state=state, ctx=ctx, kind=kind, **extra)


def play(client, turn: TurnInput) -> tuple[list, object]:
    events = run(collect(run_turn(turn, client)))
    assert isinstance(events[-1], TurnCompleted)
    return events[:-1], events[-1].result


def streamed(events) -> str:
    text = ""
    for event in events:
        if isinstance(event, NarrationReset):
            text = ""
        elif isinstance(event, NarrationDelta):
            text += event.text
    return text


# A step the dice settle (A2): a hard task with no move behind it.
CLIMB = {
    "summary": "Lin climbs the wall of the well.",
    "steps": [
        {
            "text": "climb the wet wall of the well",
            "verb": "climb",
            "kind": "task",
            "proposed_duration_s": 30,
            "facts": {"challenge": "hard"},
        },
        # More steps than one scene takes: the last two are handed back (R6).
        *(
            {
                "text": f"take step {n} along the lane",
                "verb": "walk",
                "kind": "move",
                "proposed_duration_s": 5,
            }
            for n in range(1, 10)
        ),
    ],
}
HANDED_BACK = ("take step 8 along the lane", "take step 9 along the lane")


def test_the_decided_steps_go_out_before_the_telling_with_their_dice(fake, make_client):
    """A3, B7: the dice a step was decided by travel with it, exactly as the engine threw them,
    and the player has them before the narrator writes a word."""
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events, result = play(make_client(), turn_input(action="I climb the wall and get away"))

    decided, *told = events
    assert isinstance(decided, StepsDecided)
    assert told and all(isinstance(e, NarrationDelta) for e in told)
    assert decided.details == result.scene.details
    [thrown] = decided.throws
    engine_throw = result.resolution.steps[0].roll.throw
    assert [(d.kind, d.face, d.sprung) for d in thrown.dice] == [
        (d.kind, d.face, d.sprung) for d in engine_throw.dice
    ]
    assert (thrown.hand, thrown.number, thrown.total, thrown.most, thrown.mark) == (
        engine_throw.hand,
        engine_throw.number,
        engine_throw.total,
        engine_throw.most,
        engine_throw.mark,
    )
    assert [(p.text, p.points) for p in thrown.made_of] == [
        (p.text, p.points) for p in engine_throw.made_of
    ]
    dumped = result.scene.model_dump(mode="json")["details"]["steps"][0]["roll"]["throw"]
    assert dumped["mark"] == engine_throw.mark.value
    assert dumped["dice"][0] == {
        "kind": engine_throw.dice[0].kind.value,
        "face": engine_throw.dice[0].face,
        "sprung": engine_throw.dice[0].sprung,
    }
    # How the turn was read goes with it, for the endpoint to keep, with the steps handed back.
    assert decided.reading.intent.steps[0].text == "climb the wet wall of the well"
    assert decided.reading.overflow == HANDED_BACK
    assert tuple(result.resolution.unplayed[-2:]) == HANDED_BACK


def test_a_turn_with_its_reading_is_played_out_without_reading_the_action_again(
    fake, make_client, telemetry
):
    """A3: the dice come from the turn's seed, so the same reading on the same world decides the
    same steps, whatever action comes with it."""
    fake.script(Node.INTERPRET, Reply(json=CLIMB))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    first, result = play(make_client(), turn_input(action="I climb the wall and get away"))
    reading = first[0].reading
    # What the endpoint keeps is JSON: the reading comes back from it as it went in.
    kept = type(reading.intent).model_validate(reading.intent.model_dump(mode="json"))
    assert kept == reading.intent
    telemetry.calls.clear()

    fake.script(Node.NARRATOR, Reply(json=SCENE))
    again, replayed = play(
        make_client(),
        turn_input(action="I climb the wall and get away", reading=Reading(kept, reading.overflow)),
    )

    assert [c.node for c in telemetry.calls] == ["narrator"]
    assert again[0].details == first[0].details
    assert again[0].reading == reading
    assert replayed.scene.details == result.scene.details
    assert replayed.resolution.unplayed == result.resolution.unplayed
    assert replayed.state.world_s == result.state.world_s


def test_an_opening_decides_no_steps(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events, result = play(make_client(), turn_input(kind=TurnKind.OPENING))

    assert not any(isinstance(e, StepsDecided) for e in events)
    assert result.scene.details.steps == []


def test_a_turn_runs_end_to_end(fake, make_client, telemetry):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input()
    before = turn.state.model_dump(mode="json")

    events, result = play(make_client(), turn)

    # A3: what the engine decided comes first, and it is what the scene carries.
    decided, *told = events
    assert isinstance(decided, StepsDecided)
    assert decided.details == result.scene.details
    assert decided.throws == []  # both steps are certain, so no dice were thrown
    assert all(isinstance(e, NarrationDelta) for e in told)
    assert len(told) > 1  # streamed in pieces (S3)
    assert streamed(events) == SCENE["narration"]
    assert result.narration_mode == "full"
    assert [c.node for c in telemetry.calls] == ["interpret", "narrator"]

    # The seeded default resolve plays both steps (W10).
    assert [s.text for s in result.resolution.steps] == [
        "throw a stone at Zhao",
        "run for the gate",
    ]
    assert result.state.world_s == turn.state.world_s + 42
    assert result.state.turn == 1

    scene = result.scene
    assert scene.turn == 1 and scene.kind is TurnKind.ACTION
    assert scene.player_action == "I throw a stone at Zhao, then run for the gate"
    assert scene.narration == SCENE["narration"]
    assert [(c.id, c.label) for c in scene.choices] == [
        ("c1", "Taunt Zhao"),
        ("c2", "Visit the herb garden"),
        ("c3", "Head to the archives"),
    ]
    assert [s.outcome_class for s in scene.details.steps] == [OutcomeClass.CERTAIN] * 2
    assert scene.world_start_s == turn.state.world_s
    assert scene.world_end_s == result.state.world_s
    dumped = scene.model_dump(mode="json")
    assert dumped["details"]["steps"][0]["class"] == "certain"
    assert dumped["standing_actions"] == ["wait", "observe"]

    # The narrator's update goes through engine.apply with the C1 invariants: the new character
    # joins, the scene ends where it said, and a person who doesn't exist is never placed in it.
    assert result.state.scene.ended_on == "Zhao wipes the blood from his brow and laughs."
    assert result.state.scene.present_ids == ["lin", "zhao"]
    assert result.state.summary == "Lin struck back at Zhao."
    assert result.state.characters["elder_mo"].name == "Elder Mo"

    # The input state is never touched.
    assert turn.state.model_dump(mode="json") == before
    assert set(result.timings_ms) == {
        "catch_up",
        "interpret",
        "resolve",
        "build_context",
        "narrate",
        "apply_update",
        "after_turn",
    }


def test_a_turn_replays_the_same_way(fake, make_client):
    """A3: the turn's rolls come from a seed, so the same turn plays the same way."""
    fake.script(Node.INTERPRET, Reply(json=STONE), Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE), Reply(json=SCENE))
    turn = turn_input()
    _, first = play(make_client(), turn)
    _, second = play(make_client(), turn)
    assert first.state == second.state
    assert first.scene == second.scene


def test_the_interpret_step_reads_the_players_words(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    play(make_client(), turn_input())
    [request] = fake.calls(Node.INTERPRET)
    # B5: the form asks what can apply to this turn, and the guide explains only that.
    asked = asks(cultivation_world())
    assert request.prompt.system == prompts.interpret_system(asked)
    assert request.json_schema == intent_form(asked)
    assert request.prompt.messages[-1].text.endswith(
        "## ACTION\nI throw a stone at Zhao, then run for the gate"
    )
    [narration] = fake.calls(Node.NARRATOR)
    assert "## OUTCOME" in narration.prompt.messages[-1].text
    # B8: a plain turn is read once, by the small model.
    assert fake.calls(Node.SECOND_READING) == []


def test_the_interpret_step_reads_the_scene_the_player_is_answering(fake, make_client):
    """R2: the last saved scene reaches the interpret step, so what it showed counts as there.
    A first scene has none before it."""
    scenes = (PastScene(1, "The gate stands shut."), PastScene(2, "A cart rolls up to the well."))
    state = cultivation_world()
    state.turn = 2
    for turn in (turn_input(state, scenes=scenes), turn_input()):
        fake.script(Node.INTERPRET, Reply(json=STONE))
        fake.script(Node.NARRATOR, Reply(json=SCENE))
        play(make_client(), turn)

    answered, first = (call.prompt.messages[-1].text for call in fake.calls(Node.INTERPRET))
    assert '## LAST SCENE\n{"narration":"A cart rolls up to the well."}\n' in answered
    assert "The gate stands shut." not in answered
    assert "## LAST SCENE\n(none yet)\n" in first


# R1: the scene with the player's action told in its own part, before what came of it.
ACTED = (
    {"action": "You meet Zhao's sneer, stoop and close your fingers on a stone. You let it fly."}
    | SCENE
    | {"narration": "It cracks against his brow, and you are already running for the gate."}
)


def section(text: str, name: str) -> str:
    return text.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]


def test_the_scene_opens_on_the_players_action(fake, make_client):
    """R1: the action, then what came of it, streamed and saved as one scene, a paragraph apart."""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=ACTED))
    turn = turn_input()

    events, result = play(make_client(), turn)

    told = f"{ACTED['action']}\n\n{ACTED['narration']}"
    assert streamed(events) == told
    assert result.scene.narration == told
    assert "action_untold" not in [i.code for i in result.issues]
    # The narrator is always asked for the action first, with the player's own words in the
    # brief, so it can tell their gestures and manner before anything comes of them.
    [request] = fake.calls(Node.NARRATOR)
    assert list(request.json_schema["properties"])[:2] == ["action", "narration"]
    assert request.json_schema["required"][0] == "action"
    action = json.loads(section(request.prompt.messages[-1].text, "ACTION"))
    assert next(iter(action)) == "words"
    assert action["words"] == turn.action
    assert action["summary"] == STONE["summary"]


def test_a_scene_told_wholly_in_its_action_is_kept(fake, make_client):
    """A complete scene is never thrown away for where the model split it (T7)."""
    whole = {"action": "You throw the stone, and Zhao reels.", "narration": ""} | SCENE
    whole["narration"] = ""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=whole))
    events, result = play(make_client(), turn_input())
    assert streamed(events) == result.scene.narration == "You throw the stone, and Zhao reels."
    assert len(fake.calls(Node.NARRATOR)) == 1


def test_a_scene_that_skips_the_action_is_reported(fake, make_client, log_lines):
    """R1: a scene can't be taken back once it has streamed, so code reports it (T5)."""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    _, result = play(make_client(), turn_input())
    assert "action_untold" in [i.code for i in result.issues]
    assert result.scene.narration == SCENE["narration"]
    assert any(line.get("turn_issue") == {"code": "action_untold"} for line in log_lines())


def test_a_picked_suggestion_reaches_the_narrator_as_the_players_words(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=ACTED))
    play(make_client(), turn_input(kind=TurnKind.CHOICE, action="Taunt Zhao"))
    [request] = fake.calls(Node.NARRATOR)
    assert json.loads(section(request.prompt.messages[-1].text, "ACTION"))["words"] == "Taunt Zhao"


def test_scenes_with_no_action_have_none_to_tell(fake, make_client):
    """An opening has no ACTION, so its whole scene is narration, and nothing is missing."""
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"image_prompt": None}))
    _, result = play(make_client(), turn_input(kind=TurnKind.OPENING))
    assert "action_untold" not in [i.code for i in result.issues]
    [request] = fake.calls(Node.NARRATOR)
    assert "## ACTION" not in request.prompt.messages[-1].text


def test_a_standing_action_is_told_but_has_no_words(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json={"action": "You lean on the well and wait."} | SCENE))
    turn = turn_input(kind=TurnKind.STANDING, standing=StandingAction.WAIT)
    _, result = play(make_client(), turn)
    assert result.scene.narration.startswith("You lean on the well and wait.\n\n")
    [request] = fake.calls(Node.NARRATOR)
    assert "words" not in json.loads(section(request.prompt.messages[-1].text, "ACTION"))


def test_a_standing_action_needs_no_interpret_call(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input(kind=TurnKind.STANDING, standing=StandingAction.WAIT)
    _, result = play(make_client(), turn)
    assert [c.node for c in telemetry.calls] == ["narrator"]
    assert result.scene.player_action == "wait"
    assert result.scene.kind is TurnKind.STANDING
    assert result.state.world_s == turn.state.world_s + 60


def test_the_opening_scene(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"image_prompt": None}))
    turn = turn_input(kind=TurnKind.OPENING, premise="A weak disciple remembers a past life.")
    _, result = play(make_client(), turn)
    assert [c.node for c in telemetry.calls] == ["narrator"]
    [request] = fake.calls(Node.NARRATOR)
    assert "## TASK" in request.prompt.messages[-1].text
    assert "## PREMISE" in request.prompt.messages[-1].text
    assert result.intent is None and result.resolution.steps == []
    assert result.scene.kind is TurnKind.OPENING and result.scene.player_action is None
    # M1: the player character's portrait opens the story. The narrator wrote no prompt, so one
    # comes from the character's record.
    picture = result.scene.picture
    assert picture.kind is PictureKind.PORTRAIT and picture.subject_id == "lin"
    assert picture.prompt.startswith("Portrait of Lin Feng.")


def test_no_picture_when_pictures_are_off(fake, make_client):
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input(kind=TurnKind.OPENING, settings=StorySettings(images=ImageSetting.OFF))
    _, result = play(make_client(), turn)
    assert result.scene.picture is None
    assert "## PICTURE" not in fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text


def test_a_blocked_interpret_step_is_an_unreadable_action(fake, make_client, telemetry):
    """F4: only a blocked interpret step reaches the player, as a rephrase prompt."""
    fake.script(Node.INTERPRET, Block(categories=("harassment",), stage="prompt"))
    with pytest.raises(UnreadableAction) as raised:
        play(make_client(), turn_input())
    assert raised.value.code == "unreadable_action"
    assert raised.value.categories == ("harassment",)
    assert raised.value.stage == "prompt"  # for the logs and the evals, never the app
    assert raised.value.details == {}
    assert fake.calls(Node.NARRATOR) == []


def test_a_blocked_narration_is_retold_as_a_cutaway(fake, make_client, telemetry):
    """F4: the deed stands; only the telling changes."""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    cutaway = SCENE | {"narration": "Later, the courtyard is quiet."}
    fake.script(
        Node.NARRATOR,
        Block(after_text='{"narration": "You stoop and'),
        Reply(json=cutaway),
    )
    events, result = play(make_client(), turn_input())
    assert NarrationReset("cutaway") in events
    assert streamed(events) == cutaway["narration"]
    assert result.narration_mode == "cutaway"
    assert result.scene.narration == cutaway["narration"]
    assert len(result.resolution.steps) == 2  # the deed was resolved before narration
    retold = fake.calls(Node.NARRATOR)[1]
    assert retold.prompt.system.endswith(prompts.CUTAWAY_SYSTEM)
    assert [c.blocked for c in telemetry.calls if c.node == "narrator"] == [True, False]


def test_a_cutaway_that_is_blocked_too_falls_back_to_the_template(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(
        Node.NARRATOR,
        Block(after_text='{"narration": "You'),
        Block(after_text='{"narration": "Later'),
    )
    turn = turn_input()
    events, result = play(make_client(), turn)
    resets = [e.reason for e in events if isinstance(e, NarrationReset)]
    assert resets == ["cutaway", "template"]
    line = "What happened in the outer-court well stays off the page. Its consequences won't."
    assert streamed(events) == line
    assert result.narration_mode == "template"
    assert result.scene.narration == line
    assert result.scene.choices == []
    # A template proposes nothing, so the scene frame stays as the engine left it.
    assert result.state.scene == turn.state.scene
    assert result.state.turn == 1 and result.state.world_s == turn.state.world_s + 42


def test_a_cutaway_that_fails_falls_back_to_the_template(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Block(), Fail(), Fail())
    events, result = play(make_client(), turn_input())
    assert result.narration_mode == "template"
    # Nothing was shown before the block, so there was nothing to clear.
    assert [e for e in events if isinstance(e, NarrationReset)] == []


def test_a_template_turn_keeps_a_portrait_but_drops_a_scene_picture(fake, make_client):
    fake.script(Node.NARRATOR, Block(), Block())
    _, result = play(make_client(), turn_input(kind=TurnKind.OPENING))
    assert result.scene.picture.kind is PictureKind.PORTRAIT
    assert result.scene.picture.prompt.startswith("Portrait of Lin Feng.")


def test_a_narration_that_fails_twice_ends_the_turn(fake, make_client):
    """T7: one retry, then `llm_unavailable`; the endpoint saves nothing."""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Fail(after_text='{"narration": "You st'), Fail())
    seen = []

    async def go():
        async for event in run_turn(turn_input(), make_client()):
            seen.append(event)

    with pytest.raises(LLMUnavailable):
        run(go())
    assert NarrationReset("retry") in seen
    assert not any(isinstance(e, TurnCompleted) for e in seen)


def test_a_retry_after_text_was_shown_resets_it(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Fail(after_text='{"narration": "You st'), Reply(json=SCENE))
    events, result = play(make_client(), turn_input())
    assert NarrationReset("retry") in events
    assert streamed(events) == SCENE["narration"]
    assert result.narration_mode == "full"


def test_the_plan_is_checked_before_narration(fake, make_client, monkeypatch):
    """C5 and R6: a plan that runs past a failed step is cut there before anything is told."""

    def careless_resolve(state, intent, ctx, rng, **_):
        return Resolution(
            steps=[
                StepResolution(
                    index=i,
                    text=step.text,
                    outcome_class=OutcomeClass.CONTESTED,
                    reason="Zhao ducks." if i == 0 else "",
                    result=StepResult.FAILURE if i == 0 else StepResult.SUCCESS,
                    duration_s=2,
                )
                for i, step in enumerate(intent.steps)
            ]
        )

    monkeypatch.setattr(pipeline, "resolve", careless_resolve)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input()
    _, result = play(make_client(), turn)
    assert [s.text for s in result.resolution.steps] == ["throw a stone at Zhao"]
    assert result.resolution.unplayed == ["run for the gate"]
    assert result.scene.details.stopped_at_step == 0
    assert result.state.world_s == turn.state.world_s + 2  # the run never happened
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert '"unplayed":["run for the gate"]' in told
    assert "plan_not_stopped" in [i.code for i in result.issues]


SEARCH = {
    "actor_id": "zhao",
    "summary": "Lin feels for a stone to throw at Zhao.",
    "steps": [
        {
            "text": "find a stone and throw it at Zhao",
            "verb": "throw",
            "target_ids": ["zhao"],
            "aim": "wound",
            "kind": "exchange",
            "proposed_duration_s": 3,
            "beats": [
                {"text": "crouch", "uses": [{"source": "body", "thing": "legs"}]},
                {
                    "text": "feel along the floor for a stone",
                    "uses": [{"source": "new", "thing": "a stone", "plausibility": "absent"}],
                },
                {"text": "throw it", "uses": [{"source": "canon", "thing": "the stone"}]},
            ],
        }
    ],
}


def test_an_empty_search_stops_the_step_and_the_scene_says_why(fake, make_client):
    """R2: the beats as checked reach the narrator, up to the one that came up empty, and the
    scene's details say why. A6: the player's words never make someone else the actor."""
    fake.script(Node.INTERPRET, Reply(json=SEARCH))
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    _, result = play(make_client(), turn_input(action="I feel for a stone and throw it at Zhao"))

    [step] = result.resolution.steps
    assert (step.outcome_class, step.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert result.resolution.actor_id is None
    assert "not_the_player" in [i.code for i in result.issues]
    details = result.scene.model_dump(mode="json")["details"]
    assert details["steps"][0]["beats"] == [
        {
            "beat": "feel along the floor for a stone",
            "thing": "a stone",
            "verdict": "empty",
            "reason": "There is no stone to be found here.",
            "roll": None,
        }
    ]
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    # The body needs no check, and the throw comes after the beat that came up empty.
    assert (
        '"beats":[{"beat":"feel along the floor for a stone","uses":"a stone","check":"empty",'
        '"why":"There is no stone to be found here."}]'
    ) in told


def test_only_beats_that_found_something_new_are_explained(fake, make_client):
    """R2: a thing the place plausibly holds becomes canon and is explained; beats that only used
    the body add nothing to the scene's details or the narrator's outcome."""
    found = {
        "steps": [
            {
                "text": "crouch",
                "verb": "crouch",
                "kind": "instant",
                "proposed_duration_s": 1,
                "beats": [SEARCH["steps"][0]["beats"][0]],
            },
            {
                "text": "pick up a stick",
                "verb": "pick up",
                "kind": "instant",
                "proposed_duration_s": 2,
                "beats": [
                    {
                        "text": "pick up a stick",
                        "uses": [
                            {"source": "new", "thing": "a stick", "plausibility": "plausible"}
                        ],
                    }
                ],
            },
        ]
    }
    fake.script(Node.INTERPRET, Reply(json=found))
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    _, result = play(make_client(), turn_input())

    steps = result.scene.model_dump(mode="json")["details"]["steps"]
    assert [step["class"] for step in steps] == ["certain", "certain"]
    assert steps[0]["beats"] is None
    assert steps[1]["beats"] == [
        {
            "beat": "pick up a stick",
            "thing": "a stick",
            "verdict": "made_canon",
            "reason": "There is a stick here.",
            "roll": None,
        }
    ]
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    outcome = told.split("## OUTCOME\n")[1].split("\n## ")[0]
    assert outcome.count('"beats":') == 1
    assert '{"beat":"pick up a stick","uses":"a stick","check":"made_canon"' in outcome
    # R2, R3: the narrator's scene end lists no stick, and the scene's record keeps it all the
    # same, so the next turn's check finds it there.
    assert result.resolution.found == ["a stick"]
    assert result.state.scene.props == ["a stick"]


def test_what_strikes_back_is_settled_before_it_is_told_and_the_scene_says_why(fake, make_client):
    """N6: the falling rocks wound Lin for certain, so the plan stops there; the narrator plays
    the wound as OUTCOME says, and the scene's details explain it."""
    rockfall = {
        "steps": [
            {
                "text": "run under the crumbling arch",
                "verb": "run",
                "kind": "move",
                "proposed_duration_s": 5,
                "facts": {
                    "danger": "the falling rocks",
                    "danger_class": "certain",
                    "danger_harm": "wound",
                },
            },
            STONE["steps"][1],
        ]
    }
    fake.script(Node.INTERPRET, Reply(json=rockfall))
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    _, result = play(make_client(), turn_input(action="I run under the arch and on to the gate"))

    assert result.state.player.sheet.condition.health.value == "wounded"
    details = result.scene.model_dump(mode="json")["details"]
    assert details["stopped_at_step"] == 0
    assert details["steps"][0]["struck"] == [
        {
            "by": "the falling rocks",
            "class": "certain",
            "harm": "wounded",
            "reason": "The falling rocks, and there's no escaping it: you are wounded.",
            "roll": None,
        }
    ]
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert (
        '"struck":[{"by":"the falling rocks","means":"wound","harm":"wounded",'
        '"why":"The falling rocks, and there\'s no escaping it: you are wounded."}]'
    ) in told
    assert '"stop_reason":"struck"' in told


def test_an_action_that_fits_nothing_still_plays(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json={"summary": ""}))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    _, result = play(make_client(), turn_input(action="I sing to the moon"))
    assert [s.text for s in result.resolution.steps] == ["I sing to the moon"]
    assert result.intent.steps[0].kind is ActionKind.INSTANT


def test_a_killing_the_reading_aimed_at_nobody_still_has_its_victim(fake, make_client):
    """V3, W1: on the real model "I cut Han's throat" was read as a killing with no target
    (2026-11-11): nobody died on record while the scene told a death. The step's words name
    its victim, so the deed is theirs, whatever the reading left out."""
    reading = {
        "summary": "Lin kills Zhao.",
        "steps": [
            {
                "text": "cut Zhao's throat while he dozes",
                "verb": "attack",
                "kind": "instant",
                "aim": "kill",
                "target_ids": [],
                "proposed_duration_s": 3,
                "facts": {"can_respond": False, "why_not": "asleep"},
            }
        ],
    }
    fake.script(Node.INTERPRET, Reply(json=reading))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": {}}))
    action = "I cut Zhao's throat while he dozes against the well"
    _, result = play(make_client(), turn_input(action=action))

    assert result.intent.steps[0].target_ids == ["zhao"]
    assert "target_found" in [i.code for i in result.issues]
    # He is asleep, so the blow lands, and the throw is only for how much.
    zhao = result.state.characters["zhao"]
    assert zhao.status is CharacterStatus.DEAD or zhao.sheet.condition.health is not Health.UNHURT
    (deed,) = result.state.deeds.values()
    assert "zhao" in (*deed.victim_ids, *deed.target_ids)


def lesson():
    """Lin in a lesson with Zhao, agreed on an earlier turn: a bout nobody is to be hurt in."""
    state = cultivation_world()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["zhao"],
        started_turn=state.turn,
        started_s=state.world_s,
        bout=Bout(terms=Terms.NO_HARM, with_ids=["zhao"]),
    )
    return state


def lesson_blow(aim: str, *, beyond: bool) -> dict:
    """A blow of the lesson as a model reads it: inside the terms, or meant to go beyond them."""
    return {
        "summary": "Lin comes at Zhao with the practice sword.",
        "steps": [
            {
                "text": "come at Zhao again with the practice sword",
                "verb": "strike",
                "kind": "exchange",
                "aim": aim,
                "target_ids": ["zhao"],
                "proposed_duration_s": 3,
                "facts": {
                    "opposition_ids": ["zhao"],
                    "can_respond": True,
                    "terms": "no_harm",
                    "breaks_terms": beyond,
                },
            }
        ],
    }


LESSON_ACTION = "I come at Zhao again with the practice sword"


def read_again(result) -> list[str | None]:
    return [i.area for i in result.issues if i.code == "read_again"]


def test_a_lessons_blow_read_as_an_attack_is_read_again_by_the_larger_model(
    fake, make_client, telemetry, log_lines
):
    """B8, W1: on the real model one plain lesson blow in 36 came back as a wounding meant to go
    beyond the terms (2026-11-12), and from then on every blow of that story was an attack on
    the teacher. Such a reading is read once more by the larger model, whose reading stands."""
    fake.script(Node.INTERPRET, Reply(json=lesson_blow("wound", beyond=True)))
    fake.script(Node.SECOND_READING, Reply(json=lesson_blow("subdue", beyond=False)))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": {}}))

    _, result = play(make_client(), turn_input(lesson(), action=LESSON_ACTION))

    [first] = fake.calls(Node.INTERPRET)
    [second] = fake.calls(Node.SECOND_READING)
    # The same words, guide, form and filters, on the larger model.
    assert (first.model, second.model) == ("gemini-3.5-flash-lite", "gemini-3.5-flash")
    assert second.prompt.system == first.prompt.system
    assert second.prompt.messages == first.prompt.messages
    assert second.json_schema == first.json_schema
    assert second.safety == first.safety
    # A call this rare keeps no prompt cache of its own.
    assert first.prompt.stable_chars > 0
    assert second.prompt.stable_chars == 0

    # The second reading stands: the blow is one of the lesson's, and the lesson goes on.
    blow = result.intent.steps[0]
    assert (blow.aim.value, blow.facts.breaks_terms) == ("subdue", False)
    encounter = result.state.scene.encounter
    assert encounter.bout is not None and not encounter.in_earnest
    assert result.resolution.steps[0].bout is not None
    # So it is no attack on record: the lesson is the one deed, and nobody was wronged in it.
    assert [(deed.kind, deed.victim_ids) for deed in result.state.deeds.values()] == [("bout", [])]

    assert read_again(result) == ["beyond_terms.overturned"]
    logged = [line.get("turn_issue") for line in log_lines() if line["severity"] != "DEBUG"]
    assert {"code": "read_again", "area": "beyond_terms.overturned"} in logged
    # T5, K2: the turn's calls and cost count the second reading.
    assert [call.node for call in telemetry.calls] == ["interpret", "second_reading", "narrator"]


def test_a_blow_both_readings_put_beyond_the_terms_ends_the_bout(fake, make_client):
    # W1: the player did mean it. The blow is an attack and the lesson is over.
    for node in (Node.INTERPRET, Node.SECOND_READING):
        fake.script(node, Reply(json=lesson_blow("wound", beyond=True)))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": {}}))

    _, result = play(make_client(), turn_input(lesson(), action="I drive the point at his eye"))

    assert read_again(result) == ["beyond_terms.confirmed"]
    encounter = result.state.scene.encounter
    assert encounter.bout is None and encounter.in_earnest
    assert result.resolution.steps[0].bout is None
    assert any(deed.broke_terms for deed in result.state.deeds.values())


@pytest.mark.parametrize(
    "failure", [(Fail(), Fail()), (Block(categories=("harassment",), stage="prompt"),)]
)
def test_a_second_reading_that_cant_be_had_leaves_the_first_to_stand(fake, make_client, failure):
    # B8, T7: the turn never fails for the lack of it, and a block there never reaches the player.
    fake.script(Node.INTERPRET, Reply(json=lesson_blow("wound", beyond=True)))
    fake.script(Node.SECOND_READING, *failure)
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": {}}))

    _, result = play(make_client(), turn_input(lesson(), action=LESSON_ACTION))

    assert read_again(result) == ["beyond_terms.unread"]
    assert result.intent.steps[0].facts.breaks_terms
    assert result.resolution.steps[0].bout is None


def saved_turns(count: int):
    """A story with `count` saved turns, and their scenes."""
    state = cultivation_world()
    state.turn = count
    return state, tuple(PastScene(t, f"scene {t}", f"action {t}") for t in range(1, count + 1))


def test_a_chapter_summary_every_twenty_turns(fake, make_client, telemetry):
    """C3: once 20 turns are saved, the next turn summarizes them as a chapter, so older scenes
    leave the prompt without being lost. The summary runs alongside the turn's other calls."""
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Reply(json={"summary": " Lin endured Zhao for weeks. "}))
    _, result = play(make_client(), turn_input(state, scenes=scenes))
    assert result.state.chapters == [
        Chapter(index=1, from_turn=1, to_turn=CHAPTER_TURNS, summary="Lin endured Zhao for weeks.")
    ]
    [request] = fake.calls(Node.SUMMARIZER)
    text = request.prompt.messages[-1].text
    assert '"narration":"scene 1"' in text and f'"narration":"scene {CHAPTER_TURNS}"' in text
    assert SCENE["narration"] not in text  # this turn goes into the next chapter
    assert sorted(c.node for c in telemetry.calls) == ["interpret", "narrator", "summarizer"]
    # The narrator still reads the latest scenes in full.
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert f'"narration":"scene {CHAPTER_TURNS}"' in told


def test_no_chapter_before_twenty_turns_have_passed(fake, make_client):
    state, scenes = saved_turns(CHAPTER_TURNS + 3)
    state.chapters = [Chapter(index=1, from_turn=1, to_turn=CHAPTER_TURNS, summary="Before.")]
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    _, result = play(make_client(), turn_input(state, scenes=scenes[-3:]))
    assert fake.calls(Node.SUMMARIZER) == []
    assert len(result.state.chapters) == 1
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert f'"narration":"scene {CHAPTER_TURNS + 3}"' in told


def test_a_failed_chapter_summary_is_tried_again_next_turn(fake, make_client):
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Fail(), Fail())
    _, result = play(make_client(), turn_input(state, scenes=scenes))
    assert result.state.chapters == []
    assert "chapter_skipped" in [i.code for i in result.issues]
    assert result.narration_mode == "full"  # the turn itself stands


def test_a_chapter_that_reads_as_instructions_is_dropped(fake, make_client, caplog):
    """F3: the summarizer runs with dangerous content off (C3), so code drops a summary that
    gives real-world working instructions, and the chapter is asked for again next turn."""
    state, scenes = saved_turns(CHAPTER_TURNS)
    recipe = "1. Get ammonium nitrate\n2. Mix it with fuel oil\n3. Pack it into a pipe"
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Reply(json={"summary": recipe}))
    with caplog.at_level("WARNING"):
        _, result = play(make_client(), turn_input(state, scenes=scenes))
    assert result.state.chapters == []
    assert ("chapter_skipped", "harm_instructions") in [(i.code, i.detail) for i in result.issues]
    [block] = [r.block for r in caplog.records if hasattr(r, "block")]
    assert block["node"] == "summarizer" and block["source"] == "code"
    assert "ammonium" not in caplog.text  # never the story text (T6)


def test_summaries_late_for_long_catch_up_a_window_at_a_time(fake, make_client):
    """C3: after many failed summaries, a chapter covers at most `MAX_CHAPTER_TURNS` turns, the
    oldest first, so no scene is left out of every chapter."""
    state, scenes = saved_turns(MAX_CHAPTER_TURNS + 10)
    first_window = tuple(s for s in scenes if s.turn <= MAX_CHAPTER_TURNS)
    recent = scenes[-RECENT_SCENES:]
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Reply(json={"summary": "The first weeks."}))
    _, result = play(make_client(), turn_input(state, scenes=first_window + recent))
    [chapter] = result.state.chapters
    assert (chapter.from_turn, chapter.to_turn) == (1, MAX_CHAPTER_TURNS)
    text = fake.calls(Node.SUMMARIZER)[0].prompt.messages[-1].text
    assert f'"narration":"scene {MAX_CHAPTER_TURNS}"' in text
    assert f'"narration":"scene {MAX_CHAPTER_TURNS + 1}"' not in text


def test_a_rejected_key_on_the_summary_doesnt_fail_the_turn(fake, make_client):
    """A BYOK key the summarizer's model refuses must not stop the story at turn 20."""
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Fail(kind="auth", status=403))
    _, result = play(make_client(byok=True), turn_input(state, scenes=scenes))
    assert result.state.chapters == []
    assert "chapter_skipped" in [i.code for i in result.issues]


def test_a_late_chapter_summary_is_dropped(fake, make_client, monkeypatch):
    """B8: the turn waits a little for the summary, then saves without it."""
    from graph.turn import nodes

    monkeypatch.setattr(nodes, "CHAPTER_GRACE_S", 0.01)
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Hang())
    _, result = play(make_client(), turn_input(state, scenes=scenes))
    assert result.state.chapters == []
    assert "chapter_late" in [i.code for i in result.issues]


def test_a_chapter_summary_is_cancelled_when_the_turn_fails(fake, make_client, telemetry):
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Block())
    fake.script(Node.SUMMARIZER, Hang())
    with pytest.raises(UnreadableAction):
        play(make_client(), turn_input(state, scenes=scenes))
    assert len(fake.calls(Node.SUMMARIZER)) == 1  # it started alongside the turn
    summaries = [c.outcome for c in telemetry.calls if c.node == "summarizer"]
    assert summaries == ["cancelled"]  # and nothing outlived the turn (B8)


def test_a_player_who_leaves_mid_scene_stops_everything(fake, make_client, telemetry):
    """B8: when the app drops the stream, the turn's model calls are cancelled with it."""
    state, scenes = saved_turns(CHAPTER_TURNS)
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Hang())

    async def leave_after_the_first_words():
        stream = run_turn(turn_input(state, scenes=scenes), make_client())
        async with aclosing(stream) as events:
            async for event in events:
                if isinstance(event, NarrationDelta):
                    return

    run(leave_after_the_first_words())
    assert [c.outcome for c in telemetry.calls if c.node == "summarizer"] == ["cancelled"]


def test_a_turn_that_breaks_c1_is_never_returned(fake, make_client, monkeypatch):
    """The C1 check on the turn's first and last states: an engine bug is caught, not saved."""

    def rewinding_catch_up(state, until_s, ctx, rng, **options):
        broken = state.model_copy(update={"world_s": state.world_s - 50})
        return TimePassage(state=broken, started_s=state.world_s, ended_s=broken.world_s)

    monkeypatch.setattr(pipeline, "catch_up", rewinding_catch_up)
    state = cultivation_world()
    state.world_s = 1000
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    with pytest.raises(InvariantError, match="time never runs backwards"):
        play(make_client(), turn_input(state))


def test_a_blank_narration_is_retried(fake, make_client):
    """A blank answer counts as a failed one, so the model layer asks once more (T7)."""
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"narration": "  "}), Reply(json=SCENE))
    _, result = play(make_client(), turn_input())
    assert result.scene.narration == SCENE["narration"]
    assert len(fake.calls(Node.NARRATOR)) == 2


def test_a_blank_scene_end_keeps_the_last_moment(fake, make_client):
    """R3: the next scene must start somewhere, so a blank ending keeps the previous one."""
    update = SCENE["update"] | {"scene_end": {"ended_on": "   ", "present_ids": ["lin"]}}
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": update}))
    turn = turn_input()
    _, result = play(make_client(), turn)
    assert result.state.scene.ended_on == turn.state.scene.ended_on
    assert "blank_scene_end" in [i.code for i in result.issues]


def test_a_scene_end_that_gives_only_the_time_takes_the_scenes_last_sentence(fake, make_client):
    """R3: the next scene starts from what was happening, never from an hour on the clock."""
    told = "You stoop for a stone. Zhao laughs, and you let it fly at his brow."
    end = {"ended_on": "Day 1, morning, 07:00", "place_id": "well", "present_ids": ["lin"]}
    scene = SCENE | {"narration": told, "update": SCENE["update"] | {"scene_end": end}}
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=scene))
    _, result = play(make_client(), turn_input())
    assert result.state.scene.ended_on == "Zhao laughs, and you let it fly at his brow."
    assert "clock_scene_end" in [i.code for i in result.issues]


def test_a_scene_moves_only_the_feelings_of_its_people_and_of_whom_the_turn_reached(
    fake, make_client
):
    """W4: Zhao, struck at in the scene, can come out of it angrier. Elder Mo is in the inner
    court and saw none of it, so the scene can't turn him against Lin: that change is refused,
    and code moves how he feels once word reaches him (W2)."""
    feelings = [
        {"id": "zhao", "attitudes": [{"affinity": -5}]},
        {"id": "elder-mo", "attitudes": [{"affinity": -5, "grudge": "Lin struck Zhao"}]},
    ]
    update = SCENE["update"] | {"characters": feelings}
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": update}))
    turn = turn_input()
    before = turn.state.characters["elder-mo"].sheet.disposition.attitudes.get("lin")

    _, result = play(make_client(), turn)

    refused = [(i.subject, i.area) for i in result.issues if i.code == "rejected"]
    assert refused == [("character elder-mo: attitude", "character.attitude")]
    assert result.state.characters["elder-mo"].sheet.disposition.attitudes.get("lin") == before

    # In a scene that ends with him there, he is one of its people.
    with_him = update | {"scene_end": SCENE["update"]["scene_end"] | {"present_ids": ["elder-mo"]}}
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": with_him}))
    _, result = play(make_client(), turn_input())
    assert "rejected" not in [i.code for i in result.issues]
    assert result.state.characters["elder-mo"].sheet.disposition.attitudes["lin"].grudges


def two_goals():
    state = cultivation_world()
    state.goals = {
        "goal-1": Goal(id="goal-1", text="Pass the outer-sect exam"),
        "goal-2": Goal(id="goal-2", text="Make Zhao pay", set_turn=1),
    }
    return state


def test_a_scene_closes_the_goals_it_is_over_for_but_never_an_opening(fake, make_client):
    """N2: the narrator names goals that are over; code closes them only when the player acted."""
    over = [{"goal_id": "goal-2", "how": "achieved"}, {"goal_id": "goal-1", "how": "failed"}]
    told = SCENE | {"update": SCENE["update"] | {"goals_over": over}}
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=told))
    _, result = play(make_client(), turn_input(two_goals()))
    statuses = {g.id: g.status for g in result.state.goals.values()}
    assert statuses == {"goal-1": GoalStatus.FAILED, "goal-2": GoalStatus.ACHIEVED}

    fake.script(Node.NARRATOR, Reply(json=told | {"image_prompt": None}))
    turn = turn_input(two_goals(), kind=TurnKind.OPENING, premise="A weak disciple.")
    _, result = play(make_client(), turn)
    assert {g.status for g in result.state.goals.values()} == {GoalStatus.ACTIVE}
    refused = [i.detail for i in result.issues if i.code == "rejected"]
    assert refused.count("the player didn't act this turn") == 2


def test_a_scene_notes_how_a_goal_stands_and_the_next_scene_is_told(fake, make_client):
    """N2, C6: where a goal stands is kept beside it, never in its words, and the models of the
    next scene read it with the goal."""
    moved = [{"goal_id": "goal-2", "progress": "Zhao trains alone behind the kitchens at dusk."}]
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(
        Node.NARRATOR, Reply(json=SCENE | {"update": SCENE["update"] | {"goals_moved": moved}})
    )
    _, result = play(make_client(), turn_input(two_goals()))

    goal = result.state.goals["goal-2"]
    assert (goal.text, goal.progress) == ("Make Zhao pay", moved[0]["progress"])
    assert goal.moved_turn == result.state.turn
    assert "rejected" not in [i.code for i in result.issues]

    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    play(make_client(), turn_input(result.state))
    for node in (Node.INTERPRET, Node.NARRATOR):
        brief = fake.calls(node)[-1].prompt.messages[-1].text
        assert json.loads(section(brief, "GOALS AND THREADS"))["goals"] == [
            {"id": "goal-1", "text": "Pass the outer-sect exam"},
            {"id": "goal-2", "text": "Make Zhao pay", "progress": moved[0]["progress"]},
        ]


def test_a_rung_a_scene_names_is_heard_of_and_known_once_the_story_confirms_it(
    fake, make_client, log_lines
):
    """G18, C6: code reads the scene's own words for the rungs the character doesn't know yet,
    so the path grows by itself. Zhao, who stands on Foundation Establishment, is before Lin, so
    that one is known at once; Core Formation is only heard of."""
    said = "“Foundation Establishment first,” Zhao sneers. “Core Formation is for elders.”"
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"narration": said}))
    _, result = play(make_client(), turn_input())

    heard = result.state.player.sheet.rungs_heard
    assert [(h.ladder_id, h.rung, h.known_from) for h in heard] == [
        ("realms", 1, "zhao"),
        ("realms", 2, None),
    ]
    codes = [(i.code, i.subject) for i in result.issues if i.code.startswith("rung_")]
    assert codes == [("rung_heard", "realms"), ("rung_known", "realms"), ("rung_heard", "realms")]
    (path,) = status_view(result.state).sheet.paths
    assert [(r.name, r.known) for r in path.above] == [
        ("Foundation Establishment", True),
        ("Core Formation", False),
    ]
    # T6: the log says a rung was told, never the scene's words.
    assert not any("Core Formation" in str(line) for line in log_lines())

    # A scene that names nothing new adds nothing.
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"narration": said}))
    _, again = play(make_client(), turn_input(result.state))
    assert again.state.player.sheet.rungs_heard == heard
    assert not [i for i in again.issues if i.code.startswith("rung_")]


def test_issue_details_stay_out_of_production_logs(fake, make_client, log_lines):
    """T6: story text only at DEBUG. An issue's subject can be the player's own words."""
    fake.script(
        Node.INTERPRET,
        Reply(json={"steps": [STONE["steps"][0] | {"target_ids": ["the-hidden-killer"]}]}),
    )
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    play(make_client(), turn_input())
    above_debug = [line for line in log_lines() if line["severity"] != "DEBUG"]
    assert any(line.get("turn_issue") == {"code": "unknown_target"} for line in above_debug)
    assert not any("the-hidden-killer" in str(line) for line in above_debug)


def test_a_payment_is_made_once_and_only_with_what_the_purse_holds(fake, make_client, log_lines):
    """C10: the step moves the coins before the scene is told, the scene telling the payment
    again moves nothing, and a scene that hands over something the player character doesn't
    hold is refused. The log says only what kind of change was refused (T6)."""
    state = cultivation_world()
    purse = state.player.sheet.resources
    purse.money, purse.currency = 12, "copper coins"
    pay = {
        "text": "pay Zhao five copper coins",
        "verb": "pay",
        "kind": "instant",
        "proposed_duration_s": 3,
        "exchanges": [
            {
                "kind": "give",
                "thing": "5 copper coins",
                "money": True,
                "amount": 5,
                "with_id": "zhao",
            }
        ],
    }
    told = [
        {"name": "copper coins", "money": True, "quantity": 5, "from_id": "lin", "to_id": "zhao"},
        {"name": "a jade token", "from_id": "lin", "to_id": "zhao"},
    ]
    fake.script(Node.INTERPRET, Reply(json={"summary": "Lin pays Zhao.", "steps": [pay]}))
    fake.script(Node.NARRATOR, Reply(json=SCENE | {"update": SCENE["update"] | {"items": told}}))

    _, result = play(make_client(), turn_input(state, action="I pay Zhao five copper coins"))

    assert result.state.player.sheet.resources.money == 7
    assert result.state.characters["zhao"].sheet.resources.money == 5
    assert [t.how for t in result.state.transfers] == ["pay"]
    codes = [i.code for i in result.issues]
    assert "move_recorded" in codes and "rejected" in codes
    above_debug = [line for line in log_lines() if line["severity"] != "DEBUG"]
    assert {"code": "rejected", "area": "character.item"} in [
        line.get("turn_issue") for line in above_debug
    ]
    assert not any("jade token" in str(line) for line in above_debug)


def test_turn_inputs_are_checked():
    state = grounded_world()
    good = TurnContext(story_id="s", turn=1)
    with pytest.raises(ValueError, match="doesn't follow"):
        TurnInput(
            state=state, ctx=TurnContext(story_id="s", turn=3), kind=TurnKind.ACTION, action="x"
        )
    with pytest.raises(ValueError, match="needs the action"):
        TurnInput(state=state, ctx=good, kind=TurnKind.ACTION, action="  ")
    with pytest.raises(ValueError, match="wait or observe"):
        TurnInput(state=state, ctx=good, kind=TurnKind.STANDING)
    later = state.model_copy(update={"turn": 4})
    with pytest.raises(ValueError, match="no scenes"):
        TurnInput(state=later, ctx=TurnContext(story_id="s", turn=5), kind=TurnKind.OPENING)


def test_the_offline_model_plays_a_turn(make_client):
    """LLM_PROVIDER=fake: the default backend answers any schema, so a turn runs with no model."""
    from graph.llm import FakeBackend, offline_reply

    client = make_client(backend=FakeBackend(default=offline_reply))
    _, result = play(client, turn_input(grounded_world()))
    assert result.narration_mode == "full"
    assert result.scene.narration
    assert result.state.turn == 1


def test_importing_the_turn_package_loads_no_langgraph():
    """B10: LangGraph loads with the first turn, not at startup."""
    code = (
        "import sys, graph.turn; "
        "print(any(m == 'langgraph' or m.startswith('langgraph.') for m in sys.modules))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert out.strip() == "False"


FARMING = {
    "summary": "Tomas works the fields.",
    "steps": [
        {"text": "work the fields", "verb": "farm", "kind": "work", "proposed_duration_s": 3600}
    ],
}
QUIET_SCENE = {"narration": "The furrows run straight and the day goes by.", "suggestions": []}


def quiet_farm(turn: int = 3):
    from engine.samples import farm_world

    state = farm_world()
    state.turn = turn - 1
    state.director.turns_without_stakes = 9  # W16: the story has been quiet too long
    state.director.pictured = ["portrait:tomas", "portrait:ilse", "cover", "place:farm"]
    return state


def test_the_directors_event_and_its_records_are_in_place_before_narration(fake, make_client):
    """W16, N1: the event's thread and its play-out are recorded in the turn's state, and the
    narrator is told the event."""
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))
    _, result = play(make_client(), turn_input(quiet_farm(), action="I work the fields"))

    event = result.plan.event
    assert event is not None and event.needs_decision
    assert event.thread_id in result.state.threads
    assert result.state.threads[event.thread_id].known_by == ["tomas"]
    waiting = [
        e
        for e in result.state.pending_events.values()
        if e.kind == "director.plays_out" and e.payload["thread_id"] == event.thread_id
    ]
    assert len(waiting) == 1 and waiting[0].due_s == event.plays_out_s
    assert result.state.director.turns_without_stakes == 0
    assert result.scene.event is not None and result.scene.event.title == event.title
    told = fake.calls(Node.NARRATOR)[0].prompt.messages[-1].text
    assert "EVENT" in told and event.title in told
    assert "plays_out_s" not in told  # bookkeeping stays out of the brief
    assert not [i for i in result.issues if i.code in ("unknown_thread", "unknown_source")]


def test_an_action_that_takes_up_the_event_stops_it_from_playing_out(fake, make_client):
    """W16: the interpret step names the thread the action takes up, code checks it, and the
    event's play-out is cancelled."""
    fake.script(Node.INTERPRET, Reply(json=FARMING))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))
    _, first = play(make_client(), turn_input(quiet_farm(), action="I work the fields"))
    thread_id = first.plan.event.thread_id

    answer = {**FARMING, "summary": "Tomas deals with it.", "responds_to": [thread_id, "ghost"]}
    fake.script(Node.INTERPRET, Reply(json=answer))
    fake.script(Node.NARRATOR, Reply(json=QUIET_SCENE))
    _, second = play(make_client(), turn_input(first.state, action="I deal with it"))

    assert second.intent.responds_to == [thread_id]
    assert "unknown_response" in [i.code for i in second.issues]
    waiting = [
        e
        for e in second.state.pending_events.values()
        if e.kind == "director.plays_out" and e.payload["thread_id"] == thread_id
    ]
    assert [e.status.value for e in waiting] == ["cancelled"]
    assert second.state.threads[thread_id].taken_up_turn == second.state.turn
    interpret = fake.calls(Node.INTERPRET)[-1].prompt.messages[-1].text
    assert thread_id in interpret  # the interpret step sees the ids it can take up
