"""The turn graph end to end on the scripted fake model (B5, B7, F4, T7, C3).

The fake sits under the real model client, so these turns go through the same streaming, retry,
block and telemetry code a live turn does.
"""

import subprocess
import sys

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
from engine.samples import cultivation_world, grounded_world
from engine.state.records import StepResult
from engine.state.world import Chapter
from graph.llm import Block, Fail, LLMUnavailable, Node, Reply
from graph.turn import (
    CHAPTER_TURNS,
    NarrationDelta,
    NarrationReset,
    PastScene,
    TurnCompleted,
    TurnInput,
    TurnKind,
    UnreadableAction,
    prompts,
    run_turn,
)
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


def test_a_turn_runs_end_to_end(fake, make_client, telemetry):
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    turn = turn_input()
    before = turn.state.model_dump(mode="json")

    events, result = play(make_client(), turn)

    assert all(isinstance(e, NarrationDelta) for e in events)
    assert len(events) > 1  # streamed in pieces (S3)
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

    # The narrator's update: the scene end and the summary apply; the rest waits for
    # engine.apply, and a dead or unknown person is never placed in the scene (C1).
    assert result.state.scene.ended_on == "Zhao wipes the blood from his brow and laughs."
    assert result.state.scene.present_ids == ["lin", "zhao"]
    assert result.state.summary == "Lin struck back at Zhao."
    assert "elder_mo" not in result.state.characters
    codes = [i.code for i in result.issues]
    assert codes.count("rejected") == 2  # the unknown person, and the new character

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
    assert request.prompt.system == prompts.INTERPRET_SYSTEM
    assert request.json_schema is not None
    assert request.prompt.messages[-1].text.endswith(
        "## ACTION\nI throw a stone at Zhao, then run for the gate"
    )
    [narration] = fake.calls(Node.NARRATOR)
    assert "## OUTCOME" in narration.prompt.messages[-1].text


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

    def careless_resolve(state, intent, ctx, rng):
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


def test_an_action_that_fits_nothing_still_plays(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json={"summary": ""}))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    _, result = play(make_client(), turn_input(action="I sing to the moon"))
    assert [s.text for s in result.resolution.steps] == ["I sing to the moon"]
    assert result.intent.steps[0].kind is ActionKind.INSTANT


def test_a_chapter_summary_every_twenty_turns(fake, make_client, telemetry):
    """C3: chapter summaries keep older scenes without keeping them in the prompt."""
    state = cultivation_world()
    state.turn = CHAPTER_TURNS - 1
    scenes = tuple(PastScene(t, f"scene {t}") for t in range(1, CHAPTER_TURNS))
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Reply(json={"summary": " Lin endured Zhao for weeks. "}))
    _, result = play(make_client(), turn_input(state, scenes=scenes))
    assert result.state.chapters == [
        Chapter(index=1, from_turn=1, to_turn=CHAPTER_TURNS, summary="Lin endured Zhao for weeks.")
    ]
    [request] = fake.calls(Node.SUMMARIZER)
    text = request.prompt.messages[-1].text
    assert '"narration":"scene 1"' in text
    assert SCENE["narration"] in text  # this turn's scene too
    assert [c.node for c in telemetry.calls] == ["interpret", "narrator", "summarizer"]


def test_no_chapter_before_twenty_turns_have_passed(fake, make_client):
    state = cultivation_world()
    state.turn = CHAPTER_TURNS + 3
    state.chapters = [Chapter(index=1, from_turn=1, to_turn=CHAPTER_TURNS, summary="Before.")]
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    _, result = play(make_client(), turn_input(state))
    assert fake.calls(Node.SUMMARIZER) == []
    assert len(result.state.chapters) == 1


def test_a_failed_chapter_summary_is_tried_again_next_turn(fake, make_client):
    state = cultivation_world()
    state.turn = CHAPTER_TURNS - 1
    fake.script(Node.INTERPRET, Reply(json=STONE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.SUMMARIZER, Fail(), Fail())
    _, result = play(make_client(), turn_input(state))
    assert result.state.chapters == []
    assert "chapter_skipped" in [i.code for i in result.issues]


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
