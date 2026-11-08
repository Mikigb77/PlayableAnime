"""The house style candidates (S7): the same scene in each style, for Miki to pick the look."""

import asyncio
import json
from decimal import Decimal

import pytest

from evals import styles
from evals.__main__ import draw_styles, main
from evals.runner import Models
from graph.llm import FakeBackend, Node
from graph.llm.fake import offline_reply
from media.drawing import DrawBlocked, DrawFailed, Drawn, DrawRateLimited
from media.prompts import HOUSE_STYLE, MILD_RULES

TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


def test_todays_house_style_is_one_of_the_candidates_word_for_word():
    current = styles.STYLES[0]
    assert current.id == "current"
    assert current.text() == HOUSE_STYLE


def test_every_candidate_is_grown_up_and_keeps_the_composition_the_app_needs():
    """S7: never a children's storybook; app/DESIGN.md: a calm bottom edge that fades into the
    page, no border and no writing, in every style."""
    ids = [style.id for style in styles.STYLES]
    assert len(ids) == len(set(ids)) == 8
    composition = styles.composition()
    assert "fades into a dark page" in composition and "no writing" in composition
    for style in styles.STYLES[1:]:
        text = style.text()
        assert text.startswith(style.look)
        assert text.endswith(composition)
        assert styles.GROWN_UP in text
        assert "storybook" in text and "chibi" in text


def test_a_candidate_swaps_only_the_house_style():
    """The same scene in every style: the picture's own lines and the rules are the product's."""
    scene = styles.SCENES[0]
    current = styles.request(scene, styles.STYLES[0])
    for style in styles.STYLES[1:]:
        candidate = styles.request(scene, style)
        assert candidate.prompt == current.prompt
        assert candidate.aspect_ratio == current.aspect_ratio == "16:9"
        assert candidate.references == ()
        assert f"House style: {style.text()}" in candidate.system
        assert HOUSE_STYLE not in candidate.system
        assert MILD_RULES in candidate.system
        assert candidate.system.replace(style.text(), HOUSE_STYLE) == current.system


def test_the_scenes_are_told_as_the_picture_endpoint_tells_them():
    """M5, S7: who "you" is, each person with their age, what the player character carries,
    and the time of day on the story's clock."""
    well = styles.request(styles.SCENES[0], styles.STYLES[0]).prompt
    assert '"You" in the description is Lin Feng.' in well
    assert "Lin Feng, aged 16" in well and "the grey mage, aged 60" in well
    assert "Lin Feng carries no weapon" in well
    assert "Time of day: dusk." in well
    booth = styles.request(styles.SCENES[1], styles.STYLES[0]).prompt
    assert "Luca Esposito, aged 24" in booth and "Carmine Russo, aged 54" in booth
    assert "Luca Esposito carries only this: Beretta pistol, flick knife." in booth


class ScriptedModel:
    model = "fake-image"
    byok = False

    def __init__(self, outcomes: list, closed: list) -> None:
        self.outcomes = outcomes
        self.closed = closed

    async def note(self, prompt):
        return None

    async def draw(self, request):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Drawn(TINY_PNG, "image/png", self.model, outcome)

    async def aclose(self) -> None:
        self.closed.append(True)


def test_each_picture_is_written_with_its_cost_and_a_spent_quota_is_waited_out(tmp_path):
    outcomes = [
        Decimal("0.034"),
        DrawRateLimited("transient_429"),
        Decimal("0.035"),
        DrawBlocked(("sexual",)),
        DrawFailed("timeout"),
        RuntimeError("anything else"),
    ]
    closed: list = []
    waits: list[float] = []

    async def wait(seconds: float) -> None:
        waits.append(seconds)

    scene = styles.SCENES[0]
    chosen = styles.STYLES[:5]
    samples = asyncio.run(
        styles.draw_all(
            lambda: ScriptedModel(outcomes, closed),
            tmp_path,
            [scene],
            chosen,
            wait=wait,
            say=lambda line: None,
        )
    )
    assert [s.status for s in samples] == ["drawn", "drawn", "blocked", "failed", "failed"]
    pause, spent = styles.PAUSE_S, styles.RATE_LIMIT_WAIT_S
    assert waits == [pause, spent, pause, pause, pause]
    assert len(closed) == 6  # every model is closed, the spent one included
    assert samples[1].file == "styles/well-at-dusk/02-anime-film.png"
    assert (tmp_path / samples[1].file).read_bytes() == TINY_PNG

    total = styles.write(samples, tmp_path, [scene], chosen)
    assert total == Decimal("0.069")
    manifest = json.loads((tmp_path / "styles.json").read_text())
    assert manifest["total_cost_usd"] == "0.069"
    assert manifest["models"] == ["fake-image"]
    assert [s["text"] for s in manifest["styles"]] == [s.text() for s in chosen]
    assert manifest["pictures"][2] == {
        "scene": "well-at-dusk",
        "style": "retro-anime",
        "status": "blocked",
        "file": "",
        "model": "fake-image",
        "cost_usd": "0",
    }
    summary = (tmp_path / "summary.md").read_text()
    assert "2 of 5 pictures drawn by fake-image, for $0.07." in summary
    assert "| Black-and-white seinen manga | failed | $0.0000 |" in summary


def test_a_quota_that_stays_spent_gives_the_picture_up(tmp_path):
    outcomes = [DrawRateLimited("transient_429")] * (styles.RATE_LIMIT_RETRIES + 1)

    async def wait(seconds: float) -> None:
        return None

    samples = asyncio.run(
        styles.draw_all(
            lambda: ScriptedModel(outcomes, []),
            tmp_path,
            styles.SCENES[:1],
            styles.STYLES[:1],
            wait=wait,
            say=lambda line: None,
        )
    )
    assert [s.status for s in samples] == ["failed"]
    assert outcomes == []


def test_a_model_that_cannot_even_start_loses_only_its_picture(tmp_path):
    async def wait(seconds: float) -> None:
        return None

    made: list = []

    def new_model():
        made.append(True)
        if len(made) == 1:
            raise RuntimeError("no client")
        return ScriptedModel([Decimal("0.034")], [])

    samples = asyncio.run(
        styles.draw_all(
            new_model,
            tmp_path,
            styles.SCENES[:1],
            styles.STYLES[:2],
            wait=wait,
            say=lambda line: None,
        )
    )
    assert [(s.status, s.cost_usd) for s in samples] == [
        ("failed", Decimal(0)),
        ("drawn", Decimal("0.034")),
    ]


def test_a_spent_quota_is_drawn_again_through_the_picture_model(tmp_path, monkeypatch):
    """Two 429s in a row (the model's own retry included) end the attempt, and the picture is
    drawn again after the wait."""
    from graph.llm import Fail

    monkeypatch.setattr(styles, "PAUSE_S", 0)
    monkeypatch.setattr(styles, "RATE_LIMIT_WAIT_S", 0)
    backend = FakeBackend(default=offline_reply).script(
        Node.PICTURE, *[Fail("transient_429", status=429)] * 2
    )
    code = draw_styles(tmp_path, ["well-at-dusk"], ["current"], Models(backend=backend))
    assert code == 0
    (picture,) = json.loads((tmp_path / "styles.json").read_text())["pictures"]
    assert picture["status"] == "drawn"
    assert len(backend.calls(Node.PICTURE)) >= 3


def test_the_command_draws_every_scene_in_every_style_through_the_picture_model(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(styles, "PAUSE_S", 0)
    backend = FakeBackend(default=offline_reply)
    pictures = len(styles.SCENES) * len(styles.STYLES)
    assert draw_styles(tmp_path, [], [], Models(backend=backend)) == 0
    assert len(backend.calls(Node.PICTURE)) == pictures
    manifest = json.loads((tmp_path / "styles.json").read_text())
    assert len(manifest["pictures"]) == pictures
    assert all(p["status"] == "drawn" for p in manifest["pictures"])
    assert len(list((tmp_path / "styles").glob("*/*.png"))) == pictures


def test_the_command_picks_scenes_and_styles_by_id(tmp_path):
    backend = FakeBackend(default=offline_reply)
    code = draw_styles(tmp_path, ["back-booth"], ["noir-graphic-novel"], Models(backend=backend))
    assert code == 0
    assert [p.name for p in (tmp_path / "styles").glob("*/*")] == ["07-noir-graphic-novel.png"]
    assert draw_styles(tmp_path, ["nowhere"], [], Models(backend=backend)) == 2


def test_the_command_needs_the_real_models(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    assert main(["styles", "--out", str(tmp_path)]) == 2
    assert "LLM_PROVIDER=vertex" in capsys.readouterr().err
    assert not (tmp_path / "styles.json").exists()


@pytest.mark.parametrize("catalog", [styles.SCENES, styles.STYLES])
def test_picking_none_means_all(catalog):
    assert styles.pick(catalog, []) == list(catalog)
    with pytest.raises(ValueError, match="Unknown: nope"):
        styles.pick(catalog, ["nope"])


def test_a_blocked_picture_still_counts_what_it_cost(tmp_path, monkeypatch):
    """T5: a picture the filter stopped after it was drawn is paid for all the same."""
    from graph.llm import Block

    monkeypatch.setattr(styles, "PAUSE_S", 0)
    backend = FakeBackend(default=offline_reply).script(
        Node.PICTURE, Block(("sexual",), stage="response")
    )
    assert (
        draw_styles(tmp_path, ["well-at-dusk"], ["current", "ink-wash"], Models(backend=backend))
        == 0
    )
    manifest = json.loads((tmp_path / "styles.json").read_text())
    blocked, drawn = manifest["pictures"]
    assert blocked["status"] == "blocked" and Decimal(blocked["cost_usd"]) > 0
    assert drawn["status"] == "drawn" and Decimal(drawn["cost_usd"]) > 0
    assert Decimal(manifest["total_cost_usd"]) == Decimal(blocked["cost_usd"]) + Decimal(
        drawn["cost_usd"]
    )


def test_a_tweak_changes_todays_look_and_keeps_the_rest():
    """A later round can fine-tune today's style (Miki, 2026-11-08)."""
    (current, warmer) = styles.candidates(
        '[{"id": "warmer", "name": "Warmer light", "tweak": "Light it warmer."}]'
    )
    assert current == styles.STYLES[0]
    assert warmer.text() == f"{styles.todays_look()} Light it warmer. {styles.composition()}"
    assert styles.todays_look() + " " + styles.composition() == HOUSE_STYLE
    assert styles.GROWN_UP not in warmer.text()  # today's look keeps its own grown-up lines


def test_a_new_look_from_json_is_kept_grown_up():
    (_, woodblock) = styles.candidates(
        '[{"id": "woodblock", "name": "Woodblock print", "look": "A Japanese woodblock print."}]'
    )
    assert woodblock.text() == (
        f"A Japanese woodblock print. {styles.GROWN_UP} {styles.composition()}"
    )


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        "[]",
        '[{"id": "a", "name": "A"}]',
        '[{"id": "a", "name": "A", "look": "x", "tweak": "y"}]',
        '[{"id": "Bad Id", "name": "A", "look": "x"}]',
        '[{"id": "current", "name": "A", "look": "x"}]',
        '[{"id": "a", "name": "A", "look": "x"}, {"id": "a", "name": "B", "look": "y"}]',
        '[{"id": "a", "name": "", "look": "x"}]',
        '[{"id": "a", "name": "A", "look": "x", "extra": 1}]',
        '[{"id": "a", "name": "A", "look": "' + "x" * 1501 + '"}]',
        json.dumps([{"id": f"s{i}", "name": "S", "look": "x"} for i in range(12)]),
    ],
)
def test_candidates_that_cannot_be_drawn_are_refused(text):
    with pytest.raises(ValueError):
        styles.candidates(text)


def test_the_command_draws_todays_style_next_to_the_candidates_it_is_given(tmp_path, monkeypatch):
    monkeypatch.setattr(styles, "PAUSE_S", 0)
    backend = FakeBackend(default=offline_reply)
    candidates = json.dumps(
        [
            {"id": "warmer", "name": "Warmer light", "tweak": "Light it warmer."},
            {"id": "woodblock", "name": "Woodblock print", "look": "A woodblock print."},
        ]
    )
    code = main_styles(tmp_path, ["back-booth"], backend, candidates)
    assert code == 0
    files = sorted(p.name for p in (tmp_path / "styles" / "back-booth").iterdir())
    assert files == ["01-current.png", "02-warmer.png", "03-woodblock.png"]
    manifest = json.loads((tmp_path / "styles.json").read_text())
    assert [s["id"] for s in manifest["styles"]] == ["current", "warmer", "woodblock"]
    systems = [r.prompt.system for r in backend.calls(Node.PICTURE)]
    assert "Light it warmer." in systems[1] and "A woodblock print." in systems[2]
    assert main_styles(tmp_path, [], backend, "[]") == 2


def main_styles(out, scenes, backend, candidates):
    return draw_styles(out, scenes, [], Models(backend=backend), candidates)
