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
from graph.llm import FakeBackend, ModelClient, ModelConfig, Node, Reply
from graph.llm.fake import TINY_PNG
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
