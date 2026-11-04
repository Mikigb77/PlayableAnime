"""`manage.py check_models`: each deploy calls each model the app uses once (B6, T13)."""

import io
import logging
import wave
from dataclasses import replace

import pytest
from django.core.management import CommandError, call_command

from graph.llm import Fail, FakeBackend, ModelClient, ModelConfig, Node, Reply, fill_schema
from graph.llm.config import DEFAULT_NODES
from stories.management.commands import check_models

VERTEX = ModelConfig(provider="vertex")


def _format_reply(request):
    """Response formats answer by default; a plain call must be scripted."""
    if request.json_schema is None:
        raise AssertionError(f"unscripted plain call for {request.node.value}")
    return Reply(json=fill_schema(request.json_schema))


class InPromptBackend(FakeBackend):
    """Logs what the Gemini backend logs when it sends a refused schema in the prompt."""

    def stream(self, request):
        if request.json_schema is not None and request.json_schema["title"] == "DraftProposal":
            logging.getLogger("graph.llm.gemini").warning(
                "Gemini refused the response schema; sending it in the prompt instead",
                extra={"llm": {"reason": "schema_refused"}},
            )
        return super().stream(request)


@pytest.fixture
def backend(monkeypatch) -> FakeBackend:
    """Vertex AI is configured, and every call goes to this fake backend instead."""
    fake = FakeBackend(default=_format_reply)
    monkeypatch.setattr(check_models, "get_model_config", lambda: VERTEX)

    def build(*, rating, recorder=None, config=None, **kwargs):
        return ModelClient(
            fake, config or VERTEX, rating=rating, recorder=recorder, retry_delay_s=0
        )

    monkeypatch.setattr(check_models, "build_client", build)
    return fake


def models_called(backend: FakeBackend) -> list[str]:
    return [request.model for request in backend.requests if request.json_schema is None]


def formats_sent(backend: FakeBackend) -> list[tuple[Node, str]]:
    return [(r.node, r.json_schema["title"]) for r in backend.requests if r.json_schema]


def script_models(backend: FakeBackend, *, speech: Reply | Fail | None = None) -> None:
    for node in (Node.INTERPRET, Node.NARRATOR, Node.CHECKER):
        backend.script(node, Reply(text="ok"))
    backend.script(Node.SPEECH, speech or Reply(text=""))  # silence has no words
    backend.script(Node.PICTURE, Reply(images=(b"png",)))


def test_each_model_in_use_is_called_once_and_the_judge_never(backend, capsys):
    backend.script(Node.INTERPRET, Reply(text="ok"))
    backend.script(Node.NARRATOR, Reply(text="ok"))
    backend.script(Node.CHECKER, Reply(text="ok"))
    backend.script(Node.SPEECH, Reply(text=""))
    backend.script(Node.PICTURE, Reply(images=(b"png",)))

    call_command("check_models")

    nodes = (*check_models.TEXT_NODES, Node.SPEECH, Node.PICTURE)
    in_use = {DEFAULT_NODES[node].model for node in nodes}
    assert sorted(models_called(backend)) == sorted(in_use)
    assert DEFAULT_NODES[Node.JUDGE].model not in models_called(backend)
    [picture] = [request for request in backend.requests if request.image is not None]
    assert picture.node is Node.PICTURE
    out = capsys.readouterr().out
    assert f"{DEFAULT_NODES[Node.NARRATOR].model} (narrator, drafter): ok in" in out
    assert f"{DEFAULT_NODES[Node.SPEECH].model} (speech): ok in" in out
    assert f"All {len(in_use)} models answered, and Gemini took all 6 response formats." in out


def test_the_speech_model_gets_a_recording_with_dictations_settings(backend):
    script_models(backend)

    call_command("check_models")

    [speech] = backend.calls(Node.SPEECH)
    assert speech.model == DEFAULT_NODES[Node.SPEECH].model == "gemini-3.5-transcribe-preview"
    assert speech.audio is not None and speech.audio.mime_type == "audio/wav"
    with wave.open(io.BytesIO(speech.audio.data)) as clip:  # a real WAV, as the app sends
        assert (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == (16000, 1, 2)
        assert clip.getnframes() == 16000
    assert speech.transcription == check_models.SPEECH_SPEC
    assert speech.transcription.smart and speech.transcription.language_codes == ("en-US",)
    assert speech.safety == {}  # the player's own words are never filtered here


def test_a_speech_model_vertex_refuses_fails_the_check(backend, capsys):
    script_models(backend, speech=Fail(kind="invalid", status=404))

    with pytest.raises(CommandError, match="1 of 5 models didn't answer"):
        call_command("check_models")

    speech = DEFAULT_NODES[Node.SPEECH].model
    assert f"{speech} (speech): FAILED (invalid): fake invalid failure" in capsys.readouterr().out


def test_each_response_format_is_sent_as_its_node_asks_for_it(backend, capsys):
    script_models(backend)

    call_command("check_models")

    assert formats_sent(backend) == [
        (node, schema.__name__) for node, schema in check_models.response_formats()
    ]
    assert formats_sent(backend) == [
        (Node.INTERPRET, "Intent"),
        (Node.NARRATOR, "NarratorOutput"),
        (Node.SUMMARIZER, "ChapterOutput"),
        (Node.DRAFTER, "DraftProposal"),
        (Node.DRAFTER, "WorldChange"),
        (Node.DRAFTER, "CharacterProposal"),
    ]
    for request in backend.requests:
        if request.json_schema is not None:
            assert request.model == DEFAULT_NODES[request.node].model
            assert request.options.max_output_tokens == 64  # cut off on purpose: cheap
            assert request.options.thinking == "low"  # and quick, whatever the node thinks
    drafter = DEFAULT_NODES[Node.DRAFTER].model
    assert f"{drafter} (drafter) DraftProposal format: ok in" in capsys.readouterr().out


def test_a_format_refused_even_in_the_prompt_fails_the_check(backend, capsys):
    script_models(backend)
    backend.script(Node.DRAFTER, Fail(kind="invalid", status=400))

    with pytest.raises(CommandError) as failed:
        call_command("check_models")

    assert str(failed.value).startswith(
        "1 of 6 response formats were refused (drafter DraftProposal)"
    )
    out = capsys.readouterr().out
    assert "(drafter) DraftProposal format: FAILED (invalid_400): fake invalid failure" in out
    # The other formats are still sent.
    assert len(formats_sent(backend)) == 6


def test_a_format_that_fails_for_a_moment_is_sent_again(backend, monkeypatch, capsys):
    monkeypatch.setattr(check_models, "SCHEMA_RETRY_DELAYS_S", (0, 0))
    script_models(backend)
    backend.script(Node.DRAFTER, Fail(status=429), Fail(status=429))

    call_command("check_models")

    assert formats_sent(backend).count((Node.DRAFTER, "DraftProposal")) == 3
    assert "DraftProposal format: ok in" in capsys.readouterr().out


def test_a_format_still_failing_after_the_waits_fails_the_check(backend, monkeypatch, capsys):
    monkeypatch.setattr(check_models, "SCHEMA_RETRY_DELAYS_S", (0, 0))
    script_models(backend)
    backend.script(Node.NARRATOR, *(Fail(status=429) for _ in range(3)))

    with pytest.raises(CommandError, match="narrator NarratorOutput"):
        call_command("check_models")

    assert formats_sent(backend).count((Node.NARRATOR, "NarratorOutput")) == 3
    assert "NarratorOutput format: FAILED (transient_429)" in capsys.readouterr().out


def test_a_format_gemini_takes_only_in_the_prompt_passes_and_says_so(monkeypatch, capsys):
    fake = InPromptBackend(default=_format_reply)
    monkeypatch.setattr(check_models, "get_model_config", lambda: VERTEX)
    monkeypatch.setattr(
        check_models,
        "build_client",
        lambda *, rating, recorder=None, config=None, **kwargs: ModelClient(
            fake, VERTEX, rating=rating, recorder=recorder, retry_delay_s=0
        ),
    )
    script_models(fake)

    call_command("check_models")

    out = capsys.readouterr().out
    assert "DraftProposal format: ok in" in out
    assert "though Gemini refused it as a schema, so it goes in the prompt" in out
    assert out.count("goes in the prompt") == 1


def test_no_picture_leaves_out_only_the_picture_model(backend):
    for node in (Node.INTERPRET, Node.NARRATOR, Node.CHECKER):
        backend.script(node, Reply(text="ok"))
    backend.script(Node.SPEECH, Reply(text=""))

    call_command("check_models", "--no-picture")

    assert DEFAULT_NODES[Node.PICTURE].model not in models_called(backend)
    assert DEFAULT_NODES[Node.SPEECH].model in models_called(backend)
    assert all(request.image is None for request in backend.requests)


def test_a_model_vertex_refuses_fails_with_vertex_ais_reason(backend, capsys):
    backend.script(Node.INTERPRET, Reply(text="ok"))
    backend.script(Node.NARRATOR, Fail(kind="invalid", status=404))
    backend.script(Node.CHECKER, Reply(text="ok"))
    backend.script(Node.SPEECH, Reply(text=""))
    backend.script(Node.PICTURE, Fail(), Fail())  # a 503, then the same on the retry

    with pytest.raises(CommandError) as failed:
        call_command("check_models")

    narrator = DEFAULT_NODES[Node.NARRATOR].model
    picture = DEFAULT_NODES[Node.PICTURE].model
    assert str(failed.value).startswith("2 of 5 models didn't answer")
    assert "response formats" not in str(failed.value)
    assert narrator in str(failed.value) and picture in str(failed.value)
    out = capsys.readouterr().out
    assert f"{narrator} (narrator, drafter): FAILED (invalid): fake invalid failure" in out
    assert f"{picture} (picture): FAILED (transient_503): fake transient failure" in out
    # Every model is still checked after the first failure.
    assert len(set(models_called(backend))) == 5


def test_a_node_moved_to_another_model_is_checked_through_it(backend, monkeypatch):
    nodes = {**DEFAULT_NODES, Node.TICK: replace(DEFAULT_NODES[Node.TICK], model="other-model")}
    config = ModelConfig(provider="vertex", nodes=nodes)
    monkeypatch.setattr(check_models, "get_model_config", lambda: config)
    for node in (Node.INTERPRET, Node.NARRATOR, Node.CHECKER, Node.TICK):
        backend.script(node, Reply(text="ok"))
    backend.script(Node.SPEECH, Reply(text=""))

    call_command("check_models", "--no-picture")

    assert "other-model" in models_called(backend)
    assert [r.node for r in backend.requests if r.model == "other-model"] == [Node.TICK]


def test_the_offline_model_has_nothing_to_check(monkeypatch, capsys):
    monkeypatch.setattr(check_models, "get_model_config", lambda: ModelConfig(provider="fake"))

    call_command("check_models")

    assert "nothing to check" in capsys.readouterr().out
