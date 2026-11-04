"""`manage.py check_models`: each deploy calls each model the app uses once (B6, T13)."""

from dataclasses import replace

import pytest
from django.core.management import CommandError, call_command

from graph.llm import Fail, FakeBackend, ModelClient, ModelConfig, Node, Reply
from graph.llm.config import DEFAULT_NODES
from stories.management.commands import check_models

VERTEX = ModelConfig(provider="vertex")


@pytest.fixture
def backend(monkeypatch) -> FakeBackend:
    """Vertex AI is configured, and every call goes to this fake backend instead."""
    fake = FakeBackend()
    monkeypatch.setattr(check_models, "get_model_config", lambda: VERTEX)

    def build(*, rating, recorder=None, config=None, **kwargs):
        return ModelClient(
            fake, config or VERTEX, rating=rating, recorder=recorder, retry_delay_s=0
        )

    monkeypatch.setattr(check_models, "build_client", build)
    return fake


def models_called(backend: FakeBackend) -> list[str]:
    return [request.model for request in backend.requests]


def test_each_model_in_use_is_called_once_and_the_judge_never(backend, capsys):
    backend.script(Node.INTERPRET, Reply(text="ok"))
    backend.script(Node.NARRATOR, Reply(text="ok"))
    backend.script(Node.CHECKER, Reply(text="ok"))
    backend.script(Node.PICTURE, Reply(images=(b"png",)))

    call_command("check_models")

    in_use = {DEFAULT_NODES[node].model for node in (*check_models.TEXT_NODES, Node.PICTURE)}
    assert sorted(models_called(backend)) == sorted(in_use)
    assert DEFAULT_NODES[Node.JUDGE].model not in models_called(backend)
    [picture] = [request for request in backend.requests if request.image is not None]
    assert picture.node is Node.PICTURE
    out = capsys.readouterr().out
    assert f"{DEFAULT_NODES[Node.NARRATOR].model} (narrator, drafter): ok in" in out
    assert f"All {len(in_use)} models answered." in out


def test_no_picture_checks_only_the_text_models(backend):
    for node in (Node.INTERPRET, Node.NARRATOR, Node.CHECKER):
        backend.script(node, Reply(text="ok"))

    call_command("check_models", "--no-picture")

    assert DEFAULT_NODES[Node.PICTURE].model not in models_called(backend)
    assert all(request.image is None for request in backend.requests)


def test_a_model_vertex_refuses_fails_with_vertex_ais_reason(backend, capsys):
    backend.script(Node.INTERPRET, Reply(text="ok"))
    backend.script(Node.NARRATOR, Fail(kind="invalid", status=404))
    backend.script(Node.CHECKER, Reply(text="ok"))
    backend.script(Node.PICTURE, Fail(), Fail())  # a 503, then the same on the retry

    with pytest.raises(CommandError) as failed:
        call_command("check_models")

    narrator = DEFAULT_NODES[Node.NARRATOR].model
    picture = DEFAULT_NODES[Node.PICTURE].model
    assert str(failed.value).startswith("2 of 4 models didn't answer")
    assert narrator in str(failed.value) and picture in str(failed.value)
    out = capsys.readouterr().out
    assert f"{narrator} (narrator, drafter): FAILED (invalid): fake invalid failure" in out
    assert f"{picture} (picture): FAILED (transient_503): fake transient failure" in out
    # Every model is still checked after the first failure.
    assert len(set(models_called(backend))) == 4


def test_a_node_moved_to_another_model_is_checked_through_it(backend, monkeypatch):
    nodes = {**DEFAULT_NODES, Node.TICK: replace(DEFAULT_NODES[Node.TICK], model="other-model")}
    config = ModelConfig(provider="vertex", nodes=nodes)
    monkeypatch.setattr(check_models, "get_model_config", lambda: config)
    for node in (Node.INTERPRET, Node.NARRATOR, Node.CHECKER, Node.TICK):
        backend.script(node, Reply(text="ok"))

    call_command("check_models", "--no-picture")

    assert "other-model" in models_called(backend)
    assert [r.node for r in backend.requests if r.model == "other-model"] == [Node.TICK]


def test_the_offline_model_has_nothing_to_check(monkeypatch, capsys):
    monkeypatch.setattr(check_models, "get_model_config", lambda: ModelConfig(provider="fake"))

    call_command("check_models")

    assert "nothing to check" in capsys.readouterr().out
