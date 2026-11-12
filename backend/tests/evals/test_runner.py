"""WS17's runner: checks, known gaps, statuses, the judge, the results files and the command
line."""

import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest

from engine.base import HOUR
from engine.contracts import ActionKind
from evals import worlds
from evals.__main__ import CallFormatter, main
from evals.judge import (
    JudgeOutput,
    Rubric,
    SceneToJudge,
    judge_pictures,
    judge_scenes,
    scene_prompt,
)
from evals.results import Run, read_history, summary, trend, write
from evals.runner import MAX_TURNS, Eval, LiveUnavailable, Models, RunawayStory, run_scenario
from evals.scenario import BOTH, LIVE_ONLY, Mode, Registry, Scenario
from evals.scenarios.common import act
from evals.scripted import MissingInterpretation
from graph.llm import Block, Fail, FakeBackend, ModelClient, ModelConfig, Node, Reply
from graph.llm.fake import TINY_PNG, offline_reply
from graph.llm.types import Request
from tests.evals.conftest import passing_judge


def play(script, *, modes=BOTH, mode=Mode.DETERMINISTIC, models=None):
    registry = Registry()
    registry.scenario(
        "t17.test",
        suite="T17",
        title="Test",
        requirements=("T17",),
        passes_when="it does",
        modes=modes,
    )(script)
    return asyncio.run(run_scenario(registry.scenarios["t17.test"], mode, models))


# --- scenarios and statuses --------------------------------------------------------------------


def test_a_scenario_has_a_script_or_waits_for_something():
    with pytest.raises(ValueError):
        Scenario("t17.x", "T17", "X", ("T17",), "it does", None)
    waiting = Scenario("t17.x", "T17", "X", ("T17",), "it does", None, waits_for="WS99")
    assert waiting.pending and not waiting.runs_in(Mode.DETERMINISTIC)


def test_two_scenarios_cant_share_an_id():
    registry = Registry()
    registry.pending(
        "t17.x", suite="T17", title="X", requirements=(), passes_when="", waits_for="y"
    )
    with pytest.raises(ValueError):
        registry.pending(
            "t17.x", suite="T17", title="X", requirements=(), passes_when="", waits_for="y"
        )


def test_checks_count_every_time_and_keep_a_few_details():
    async def script(ev: Eval) -> None:
        for n in range(10):
            ev.check("even", n % 2 == 0, f"seed {n}")

    result = play(script)
    assert result.status == "failed"
    (tally,) = result.checks
    assert (tally.passed, tally.failed) == (5, 5)
    assert result.failures()[0].startswith("even: 5 failed of 10: seed 1; seed 3")
    assert result.score == 0.5


def test_a_script_that_checks_nothing_or_raises_is_an_error_not_a_pass():
    async def nothing(ev: Eval) -> None:
        return None

    async def raises(ev: Eval) -> None:
        raise KeyError("oops")

    assert play(nothing).status == "error"
    broken = play(raises)
    assert broken.status == "error" and "KeyError" in broken.error


def test_an_error_shows_its_own_line_not_the_task_it_came_from():
    async def raises(ev: Eval) -> None:
        error = RuntimeError("the model is unavailable")
        error.add_note("During task with name 'narrate' and id 'x'")
        raise error

    broken = play(raises)
    assert broken.failures() == ["error: RuntimeError: the model is unavailable"]
    assert "During task with name 'narrate'" in broken.error


def test_a_failed_model_call_is_logged_with_why():
    def line(**extra):
        record = logging.makeLogRecord(
            {"name": "graph.llm", "levelname": "ERROR", "msg": "Model call failed", **extra}
        )
        return CallFormatter(logging.BASIC_FORMAT).format(record)

    call = {
        "node": "picture",
        "model": "gemini-3.1-flash-lite-image",
        "attempt": 3,
        "reason": "transient_429",
        "detail": "429 RESOURCE_EXHAUSTED",
        "byok": False,
    }
    assert line(llm=call) == (
        "ERROR:graph.llm:Model call failed (node=picture, model=gemini-3.1-flash-lite-image,"
        " attempt=3, reason=transient_429, detail=429 RESOURCE_EXHAUSTED)"
    )
    assert line() == "ERROR:graph.llm:Model call failed"


def test_a_live_only_scenario_is_skipped_in_deterministic_mode():
    async def script(ev: Eval) -> None:
        ev.check("ran", True)

    assert play(script, modes=LIVE_ONLY).status == "skipped"


def test_live_mode_without_model_access_stops_the_run():
    async def script(ev: Eval) -> None:
        ev.check("ran", True)

    with pytest.raises(LiveUnavailable):
        play(script, mode=Mode.LIVE, models=Models(config=ModelConfig(provider="fake")))


def test_live_only_checks_stay_out_of_live_mode(offline_models):
    async def script(ev: Eval) -> None:
        ev.check("many seeds", False, live=False)
        ev.check("ran", True)

    assert play(script).status == "failed"
    live = play(script, mode=Mode.LIVE, models=offline_models)
    assert live.status == "passed" and [t.name for t in live.checks] == ["ran"]


# --- known gaps --------------------------------------------------------------------------------


def test_an_open_gap_is_reported_without_failing_the_run():
    async def script(ev: Eval) -> None:
        ev.check("works", True)
        ev.check("the engine does it", False, "seed 0", gap="nothing does it yet (W99)")

    result = play(script)
    assert result.status == "passed"
    assert result.gaps() == ["the engine does it: nothing does it yet (W99)"]
    assert result.to_json()["checks"][1]["gap"] == "nothing does it yet (W99)"


def test_a_gap_that_holds_in_a_live_run_fails_nothing(offline_models):
    async def script(ev: Eval) -> None:
        ev.check("works", True)
        ev.check("the engine does it", True, gap="nothing does it yet (W99)")

    result = play(script, mode=Mode.LIVE, models=offline_models)
    assert result.status == "passed" and result.gaps() == []


def test_a_closed_gap_fails_until_its_marker_comes_off():
    async def script(ev: Eval) -> None:
        ev.check("the engine does it", True, gap="nothing does it yet (W99)")

    result = play(script)
    assert result.status == "failed"
    assert "the known gap is closed" in result.failures()[0]
    assert result.gaps() == []


# --- stories -----------------------------------------------------------------------------------


def test_deterministic_mode_needs_every_line_interpreted():
    async def script(ev: Eval) -> None:
        story = ev.story(worlds.farm(), seed="s", under_way=True)
        await story.act("I farm")

    result = play(script)
    assert result.status == "error" and MissingInterpretation.__name__ in result.error


def test_a_story_can_never_run_away():
    async def script(ev: Eval) -> None:
        story = ev.story(worlds.farm(), seed="s", under_way=True)
        for _ in range(MAX_TURNS + 1):
            await story.stand()

    result = play(script)
    assert result.status == "error" and RunawayStory.__name__ in result.error


def test_a_change_that_breaks_c1_is_refused():
    async def script(ev: Eval) -> None:
        story = ev.story(worlds.farm(), seed="s", under_way=True)
        story.change(lambda s: setattr(s.characters[s.player_id], "name", " "))

    result = play(script)
    assert result.status == "error" and "C1" in result.error


def test_the_scripted_model_shows_what_the_narrator_was_sent():
    async def script(ev: Eval) -> None:
        story = ev.story(worlds.farm(), seed="s", under_way=True)
        played = await story.act(
            "I mend the fence", act("mend the fence", "mend", ActionKind.TASK, HOUR)
        )
        ev.check("played", played.completed and played.world_seconds == HOUR)
        ev.check("prompt", "mend the fence" in story.prompt(Node.NARRATOR))
        ev.check("priced", played.cost_usd > 0)

    assert play(script).status == "passed"


# --- a reading alone, and what each model step came to ------------------------------------------


def test_a_reading_alone_plays_no_turn():
    """T18: a scenario about the first model's reading runs that step only, checked as a turn
    checks it, and nothing of the story moves."""
    seen = {}

    async def script(ev: Eval) -> None:
        story = ev.story(worlds.sect(), seed="s", under_way=True)
        before = story.state.model_dump_json()
        scripted = act("bow to Zhao", "bow", ActionKind.INSTANT, 5)
        scripted.steps[0].target_ids = ["zhao", "nobody-here"]
        read = await story.read("I bow to Zhao", scripted)
        seen["read"] = read
        ev.check("read", read.intent is not None and read.failed == "")
        # V3: an id the state doesn't hold is kept as words, as on any turn.
        ev.check("checked", read.steps[0].target_ids == ["zhao"])
        ev.check("nothing moved", story.state.model_dump_json() == before and not story.turns)

    result = play(script)

    assert result.status == "passed", result.failures()
    assert result.turns == 0 and result.turn_cost_usd == 0
    (use,) = result.use
    assert (use.node, use.calls) == ("interpret", 1) and use.cost_usd == result.cost_usd > 0
    assert [call.node for call in seen["read"].calls] == ["interpret"]


def test_a_line_the_model_cant_read_is_no_reading(offline_models):
    """A line the filter stops, or the model never answers, is a line read wrong, not a broken
    run: on a larger model a deadline missed is part of what the reading costs."""
    read = {}

    def answers(request: Request):
        if request.node is not Node.INTERPRET:
            return offline_reply(request)
        said = request.prompt.messages[-1].text
        return Block(categories=("violence",)) if "I stab Zhao" in said else Fail()

    async def script(ev: Eval) -> None:
        story = ev.story(worlds.sect(), seed="s", under_way=True)
        read["blocked"] = await story.read("I stab Zhao")
        read["late"] = await story.read("I bow to Zhao")
        ev.check("ran", True)

    models = Models(backend=FakeBackend(default=answers, keep_requests=False))
    result = play(script, mode=Mode.LIVE, models=models)

    assert result.status == "passed", result.error
    assert (read["blocked"].intent, read["blocked"].failed) == (None, "blocked")
    assert (read["late"].intent, read["late"].failed) == (None, "llm_unavailable")
    assert read["late"].steps == []
    (use,) = result.use
    assert use.failed == use.calls > 0


def test_the_summary_says_what_each_model_step_came_to():
    """B6, B8, K8: a run says what each model step of its stories took a call, and what a turn
    played cost, so the same scenarios on another model can be set beside it."""

    async def script(ev: Eval) -> None:
        story = ev.story(worlds.farm(), seed="s", under_way=True)
        mend = act("mend the fence", "mend", ActionKind.TASK, HOUR)
        await story.act("I mend the fence", mend)
        await story.act("I mend the gate", mend)
        await story.read("I mend the barn", mend)
        ev.check("played", len(story.turns) == 2)

    result = play(script)
    run = Run(mode=Mode.DETERMINISTIC, started_at=datetime(2026, 11, 12, tzinfo=UTC))
    run.results = [result, play(script)]

    by_step = {use.node: use for use in run.use()}
    assert (by_step["interpret"].calls, by_step["narrator"].calls) == (6, 4)
    assert run.turns == 4 and 0 < run.turn_cost_usd < run.cost_usd  # the readings aren't turns
    text = summary(run)
    assert "### What each model step would come to" in text
    assert "| interpret | gemini-3.5-flash-lite | 6 |" in text
    assert f"A turn played would cost ${run.turn_cost_usd / 4:.4f} on average (4 turns)." in text

    run.mode = Mode.LIVE
    run.thinking = {"interpret": "medium"}
    text = summary(run)
    assert "### What each model step came to" in text
    assert "| interpret | gemini-3.5-flash-lite (medium) | 6 |" in text
    assert "A turn played cost $" in text
    data = run.to_json()
    assert data["thinking"] == {"interpret": "medium"} and data["turns"] == 4
    assert [use["node"] for use in data["use"]] == ["interpret", "narrator"]
    assert data["scenarios"][0]["use"][0]["calls"] == 3


def test_a_run_with_no_model_call_lists_no_step():
    assert "What each model step" not in summary(a_run(None))


def test_a_live_run_says_how_hard_each_step_thinks(monkeypatch):
    monkeypatch.setenv("INTERPRET_THINKING", "high")
    monkeypatch.setenv("INTERPRET_MODEL", "gemini-3.5-flash")
    models = Models(config=ModelConfig.from_env())
    assert models.models_used()["interpret"] == "gemini-3.5-flash"
    thinking = models.thinking_used()
    assert thinking["interpret"] == "high" and thinking["narrator"] == "low"
    assert "picture" not in thinking  # a picture model takes no such setting


# --- the judge ---------------------------------------------------------------------------------


def judge_client(answer) -> ModelClient:
    return ModelClient(FakeBackend(default=answer), ModelConfig(), rating="mature", retry_delay_s=0)


SCENE = SceneToJudge("I wave", "Lin waves at Wei.", {"steps": []}, "first")
RUBRIC = Rubric(must=("Lin waves",), must_not=("Lin attacks",))


def test_the_judge_sees_the_rubric_and_scores_every_criterion():
    prompt = scene_prompt(RUBRIC, [SCENE], rating="teen")
    text = "\n".join(m.text for m in prompt.messages)
    assert "M1: Lin waves" in text and "N1: Lin attacks" in text and "SCENE 1 (first)" in text

    judgement = asyncio.run(
        judge_scenes(judge_client(passing_judge), "waves", RUBRIC, [SCENE], rating="teen")
    )
    assert judgement.passed and [v.id for v in judgement.verdicts] == ["M1", "N1"]


def test_a_criterion_the_judge_skips_fails():
    def half(request):
        return Reply(json=JudgeOutput(answers=[{"id": "M1", "verdict": "pass", "reason": "ok"}]))

    judgement = asyncio.run(judge_scenes(judge_client(half), "w", RUBRIC, [SCENE], rating="teen"))
    assert not judgement.passed
    assert [(v.id, v.passed) for v in judgement.verdicts] == [("M1", True), ("N1", False)]


def test_a_judge_that_fails_or_has_nothing_to_judge_never_passes():
    def broken(request):
        return Reply(text="not json")

    failed = asyncio.run(judge_scenes(judge_client(broken), "w", RUBRIC, [SCENE], rating="teen"))
    assert not failed.passed and failed.error
    empty = asyncio.run(judge_pictures(judge_client(passing_judge), "p", RUBRIC, []))
    assert not empty.passed and empty.error == "no_pictures"


def test_pictures_go_to_the_judge_as_images():
    seen = []

    def look(request):
        seen.append(len(request.prompt.images))
        return passing_judge(request)

    images = [("portrait", TINY_PNG, "image/png"), ("scene 1", TINY_PNG, "image/png")]
    judgement = asyncio.run(judge_pictures(judge_client(look), "face", RUBRIC, images))
    assert judgement.passed and seen == [2]


def test_a_scene_is_described_as_the_picture_endpoint_describes_it():
    from evals.pictures import ending, scene_brief
    from media import briefs
    from media.plans import _ending

    long = "It begins. " + "The rain falls on the court. " * 60 + "Lin draws. The mage turns!"
    for text in ("Short.", long, "x" * 1500, "  spaced   out.  "):
        assert ending(text) == _ending(text)
    # The narrator's image prompt goes in as written, however long.
    assert scene_brief(worlds.farm(), long).description == long
    # Who is in it, who "you" is and the hour, as `stories.turns.brief` has them.
    state = worlds.farm()
    brief = scene_brief(state, "You lift the bucket.")
    assert brief.figures == briefs.scene_figures(state, "You lift the bucket.")
    assert brief.you == state.player.name
    assert brief.time == briefs.time_of_day(state.bible.calendar, state.world_s)
    assert (brief.turn, brief.place_id) == (state.turn, briefs.scene_place(state)[0])


def test_a_scene_picture_is_drawn_from_its_note_as_the_endpoint_draws_it():
    """M5: the eval's pictures go through the note step, with the portraits of only the people
    it keeps."""
    from decimal import Decimal

    from evals.pictures import Picture, draw, scene_brief
    from media.drawing import Drawn
    from media.notes import PictureNote, SceneText

    state = worlds.farm()
    player = state.player.name

    class Painter:
        model, byok = "fake-image", False

        def __init__(self):
            self.notes, self.drawn = [], []

        async def note(self, prompt):
            self.notes.append(prompt)
            return PictureNote(description=f"{player} lifts the bucket.", people=[player])

        async def draw(self, request):
            self.drawn.append(request)
            return Drawn(TINY_PNG, "image/png", self.model, Decimal("0.034"))

    painter = Painter()
    brief = scene_brief(state, "You lift the bucket.")
    portrait = Picture("p", "portrait", TINY_PNG, "image/png", "fake-image", Decimal(0))
    others = [("Someone Else", portrait), (player, portrait)]

    drawn = asyncio.run(
        draw(painter, "s", "scene", brief, others, scene=SceneText("You lift it.", "lift"))
    )

    assert isinstance(drawn, Picture)
    assert painter.notes[0].user.endswith("SCENE:\nYou lift it.")
    [request] = painter.drawn
    assert f"What it shows: {player} lifts the bucket." in request.prompt
    assert [ref.name for ref in request.references] == [player]
    # A portrait gets no note.
    asyncio.run(draw(painter, "p", "portrait", brief, scene=SceneText("x")))
    assert len(painter.notes) == 1


def test_a_scene_picture_gets_the_places_picture_last_as_the_endpoint_sends_it():
    """M5: an eval that drew the place hands its picture to a scene drawn there, labelled as the
    place, after the portraits; a cover gets none. The place is described as the turn describes a
    planned one."""
    from decimal import Decimal

    from engine.looks import place_looks
    from evals.pictures import Picture, draw, place_brief, scene_brief
    from media.drawing import Drawn
    from media.prompts import GROUNDED

    state = worlds.above_the_camp()

    class Painter:
        model, byok = "fake-image", False

        def __init__(self):
            self.drawn = []

        async def draw(self, request):
            self.drawn.append(request)
            return Drawn(TINY_PNG, "image/png", self.model, Decimal("0.034"))

    painter = Painter()
    brief = scene_brief(state, "You and Zhao Kun stand on the wall.")
    portrait = Picture("p", "portrait", TINY_PNG, "image/png", "fake-image", Decimal(0))
    place = Picture("place-arches", "place", TINY_PNG, "image/png", "fake-image", Decimal(0))

    asyncio.run(draw(painter, "s", "scene", brief, [("Lin Feng", portrait)], place=place))
    asyncio.run(draw(painter, "c", "cover", brief, [("Lin Feng", portrait)], place=place))

    scene, cover = painter.drawn
    assert [ref.label for ref in scene.references] == [
        "Image 1: the portrait of Lin Feng.",
        "Image 2: the Broken Arches, the place where this happens, to draw again around the "
        "people.",
    ]
    assert "Draw it again around the people" in scene.prompt and GROUNDED in scene.prompt
    assert [ref.name for ref in cover.references] == ["Lin Feng"]
    assert brief.time == "dusk"
    described = place_brief(state, "arches")
    assert (described.subject_name, described.subject_appearance) == (
        "the Broken Arches",
        place_looks(state.places["arches"]),
    )
    assert described.description == "A wide view of the Broken Arches."


# --- results -----------------------------------------------------------------------------------


def a_run(tmp_path):
    async def script(ev: Eval) -> None:
        ev.check("works", True)
        ev.check("gap", False, gap="not yet (W99)")
        ev.metric("rate", 0.5)

    result = play(script)
    return Run(
        mode=Mode.DETERMINISTIC, started_at=datetime(2026, 11, 4, tzinfo=UTC), results=[result]
    )


def test_a_run_is_written_and_tracked_over_time(tmp_path):
    run = a_run(tmp_path)
    history = tmp_path / "history.jsonl"
    path = write(run, tmp_path / "out", history=history)
    write(run, tmp_path / "out2", history=history)

    data = json.loads(path.read_text())
    assert data["counts"]["passed"] == 1 and data["gaps"][0]["gap"] == "gap: not yet (W99)"
    assert data["scenarios"][0]["metrics"] == {"rate": 0.5}
    assert "Known gaps still open" in (tmp_path / "out" / "summary.md").read_text()
    runs = read_history(history)
    assert len(runs) == 2 and runs[0]["scenarios"]["t17.test"]["status"] == "passed"
    shown = trend(runs)
    assert "t17.test" in shown and "✓" in shown


def test_the_summary_leaves_out_skipped_scenarios(tmp_path):
    run = a_run(tmp_path)
    run.results.append(
        asyncio.run(
            run_scenario(
                Scenario("t18.x", "T18", "X", ("T18",), "y", None, waits_for="z"),
                Mode.DETERMINISTIC,
            )
        )
    )
    text = summary(run)
    assert "| t18.x | pending |" in text and "no model spend" in text


def test_a_live_summary_says_what_its_pictures_came_to(tmp_path):
    """M8, T18: two runs of the picture evals, one per picture model, are weighed side by side."""
    from decimal import Decimal

    from evals.pictures import NotDrawn, Picture

    run = a_run(tmp_path)
    run.mode = Mode.LIVE
    run.models = {"picture": "gemini-nano-banana-2.1"}
    run.results[0].pictures = [
        Picture("a", "scene", b"x", "image/png", "gemini-nano-banana-2.1", Decimal("0.0340")),
        Picture("b", "cover", b"x", "image/png", "gemini-nano-banana-2.1", Decimal("0.0372")),
        NotDrawn("c", "blocked"),
    ]

    text = summary(run)

    assert "Pictures by gemini-nano-banana-2.1: 2 drawn for $0.07, 1 not drawn (1 blocked)." in text
    assert "Pictures by" not in summary(a_run(tmp_path))  # a run with none says nothing


# --- the command line --------------------------------------------------------------------------


def test_the_command_line_lists_runs_and_reports(tmp_path, capsys):
    assert main(["list", "--suite", "T18"]) == 0
    assert "t18.same-face" in capsys.readouterr().out

    out = tmp_path / "out"
    code = main(
        [
            "run",
            "--only",
            "t15.content.romance-with-a-minor",
            "--out",
            str(out),
            "--history",
            str(tmp_path / "h.jsonl"),
        ]
    )
    assert code == 0 and (out / "run.json").exists()
    assert main(["report", "--history", str(tmp_path / "h.jsonl")]) == 0
    assert "t15.content.romance-with-a-minor" in capsys.readouterr().out


def test_live_mode_without_vertex_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert main(["run", "--mode", "live", "--only", "t18.same-face"]) == 2
    assert "LLM_PROVIDER=vertex" in capsys.readouterr().err


def test_a_missed_criterion_is_reported_with_the_judges_reason():
    """T18: a live run's log says what the judge saw for each criterion it failed, since the run's
    artifact can be out of reach."""
    from evals.judge import Judgement, Verdict

    async def script(ev: Eval) -> None:
        ev.check("drawn", True)
        ev.judged.append(
            Judgement(
                "the look",
                (
                    Verdict("M1", "must", "Every picture looks made for grown-ups " * 5, True),
                    Verdict(
                        "M2",
                        "must",
                        "No picture looks like a children's book",
                        False,
                        reason="The cover has  pastel colours\nand big round eyes.",
                    ),
                    Verdict("M3", "must", "Each person looks their age", False),
                ),
            )
        )
        ev.judged.append(Judgement("broken", error="the judge answered nothing"))

    result = play(script)

    assert result.status == "failed"
    assert result.failures() == [
        "judge the look: M2 (No picture looks like a children's book) failed: The cover has "
        "pastel colours and big round eyes.",
        "judge the look: M3 (Each person looks their age) failed: no reason given",
        "judge broken: the judge answered nothing",
    ]


def test_a_failed_live_scenario_says_which_turns_were_refused_and_why():
    """T18: a story whose first action can't be read fails every check after it, and the run's
    log is all that can be read of it afterwards. So a failed scenario lists the turns that
    were refused, with who refused them and why."""

    def filtered(request: Request) -> Reply | Block:
        if request.node is Node.INTERPRET:
            return Block(categories=("harassment",), stage="prompt")
        return offline_reply(request)

    models = Models(
        backend=FakeBackend(default=filtered, keep_requests=False),
        judge_backend=FakeBackend(default=passing_judge, keep_requests=False),
    )
    verdicts = {}

    async def script(ev: Eval) -> None:
        story = ev.story(worlds.cultivation_world(), seed="s/0", under_way=True)
        played = await story.act("I cut Zhao down where he stands")
        ev.check("the blow is read", verdicts.get("read", played.completed), "it never played")

    result = play(script, mode=Mode.LIVE, models=models)

    assert result.status == "failed"
    assert result.failures() == [
        "the blow is read: 1 failed of 1: it never played",
        "refused: s/0 t2 (I cut Zhao down where he stands): unreadable_action by model at the "
        "prompt, categories ['harassment']",
    ]
    # A refusal a passing scenario expected is not worth a line.
    verdicts["read"] = True
    assert play(script, mode=Mode.LIVE, models=models).failures() == []
