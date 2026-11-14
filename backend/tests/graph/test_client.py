import asyncio
import json
import logging
from contextlib import aclosing
from decimal import Decimal

import pytest
from pydantic import BaseModel

from graph.llm import (
    BadKey,
    Block,
    CallOptions,
    Completed,
    Fail,
    Hang,
    ImagePart,
    LLMBlocked,
    LLMUnavailable,
    ModelClient,
    ModelConfig,
    Node,
    Prompt,
    Reply,
    StreamRestart,
    TextDelta,
    TextEnded,
)
from graph.llm.config import DEFAULT_NODES
from graph.llm.safety import safety_settings
from tests.graph.conftest import Narration, collect, run

PROMPT = Prompt.build("You are the narrator.", "I grab a stone and throw it at the troll.")
SCENE = Narration(title="Cave", narration="You drop to a crouch. The stone flies.", choices=["Run"])


def test_a_structured_call_returns_the_validated_result(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    result = run(make_client().structured(Node.NARRATOR, PROMPT, Narration))

    assert result == SCENE
    [record] = telemetry.calls
    assert record.outcome == "ok"
    assert (record.node, record.model, record.provider) == ("narrator", "gemini-3.5-flash", "fake")
    assert record.attempts == 1 and record.retries == 0
    assert record.input_tokens > 0 and record.output_tokens > 0
    assert record.cost_usd > 0 and record.price_known


def test_a_call_can_ask_for_less_than_its_schema_holds(fake, make_client):
    """B5: a caller's own form goes to the model in place of the class's schema, and the answer
    is still read as the class, with its defaults for what the form left out."""
    whole = Narration.model_json_schema()
    form = {**whole, "properties": {k: v for k, v in whole["properties"].items() if k != "title"}}
    form["required"] = [name for name in whole.get("required", []) if name != "title"]
    fake.script(Node.NARRATOR, Reply(json={"narration": "The stone flies.", "choices": ["Run"]}))

    result = run(make_client().structured(Node.NARRATOR, PROMPT, Narration, form=form))

    [request] = fake.requests
    assert request.json_schema == form and request.json_schema is not form
    assert "title" not in request.json_schema["properties"]
    assert result == Narration(narration="The stone flies.", choices=["Run"])
    # Without one, the class's own schema is sent.
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    run(make_client().structured(Node.NARRATOR, PROMPT, Narration))
    assert fake.requests[-1].json_schema == whole


def test_the_request_carries_the_nodes_model_settings_and_the_ratings_safety(fake, make_client):
    fake.script(Node.INTERPRET, Reply(json=SCENE))

    run(
        make_client(rating="teen").structured(
            Node.INTERPRET, PROMPT, Narration, options=CallOptions(thinking="high")
        )
    )

    [request] = fake.requests
    assert request.model == DEFAULT_NODES[Node.INTERPRET].model
    assert request.options.thinking == "high"
    assert request.options.timeout_s == DEFAULT_NODES[Node.INTERPRET].options.timeout_s
    assert request.safety == safety_settings("teen", node=Node.INTERPRET)
    assert request.json_schema == Narration.model_json_schema()
    assert request.image is None


def test_each_node_gets_its_own_safety_settings(fake, make_client):
    # F5, F4: Mature interpret reads the action with the text filters off.
    fake.script(Node.INTERPRET, Reply(json=SCENE))
    fake.script(Node.NARRATOR, Reply(json=SCENE))
    client = make_client(rating="mature")

    run(client.structured(Node.INTERPRET, PROMPT, Narration))
    run(client.structured(Node.NARRATOR, PROMPT, Narration))

    interpret, narrator = fake.requests
    assert interpret.safety == safety_settings("mature", node=Node.INTERPRET)
    assert narrator.safety == safety_settings("mature", node=Node.NARRATOR)
    assert interpret.safety != narrator.safety


def test_a_transient_failure_is_retried_once(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Fail(status=503), Reply(json=SCENE))

    assert run(make_client().structured(Node.NARRATOR, PROMPT, Narration)) == SCENE

    [record] = telemetry.calls
    assert record.outcome == "ok"
    assert record.attempts == 2 and record.retries == 1
    assert record.retry_reasons == ("transient_503",)
    assert len(fake.requests) == 2


def test_a_second_failure_becomes_llm_unavailable(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Fail(status=429), Fail(status=500))

    with pytest.raises(LLMUnavailable) as raised:
        run(make_client().structured(Node.NARRATOR, PROMPT, Narration))

    assert raised.value.code == "llm_unavailable"
    [record] = telemetry.calls
    assert record.outcome == "unavailable"
    assert record.retries == 1 and record.attempts == 2
    assert record.error_kind == "transient_500"
    assert fake.pending() == 0


def test_our_quota_running_out_is_retried_twice_after_longer_waits(
    fake, make_client, telemetry, monkeypatch
):
    """Vertex AI's shared quota answers 429 in bursts that pass within seconds."""
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("graph.llm.client.asyncio.sleep", sleep)
    fake.script(Node.NARRATOR, Fail(status=429), Fail(status=429), Reply(json=SCENE))
    client = ModelClient(fake, ModelConfig(), rating="mature", recorder=telemetry)

    assert run(client.structured(Node.NARRATOR, PROMPT, Narration)) == SCENE

    [record] = telemetry.calls
    assert record.outcome == "ok" and record.attempts == 3
    assert record.retry_reasons == ("transient_429", "transient_429")
    assert waits == [2.0, 6.0]


def test_our_quota_still_out_after_the_waits_is_unavailable(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, *(Fail(status=429) for _ in range(3)), Reply(json=SCENE))

    with pytest.raises(LLMUnavailable):
        run(make_client().structured(Node.NARRATOR, PROMPT, Narration))

    assert telemetry.calls[0].attempts == 3
    assert fake.pending(Node.NARRATOR) == 1


def test_a_players_key_out_of_quota_is_retried_only_once(fake, make_client, telemetry):
    """A player's key isn't shared: its 429 is its own limit, often a free tier's zero."""
    fake.script(Node.NARRATOR, Fail(status=429), Fail(status=429), Reply(json=SCENE))

    with pytest.raises(LLMUnavailable):
        run(make_client(byok=True).structured(Node.NARRATOR, PROMPT, Narration))

    assert telemetry.calls[0].attempts == 2


@pytest.mark.parametrize(
    "bad",
    [
        Reply(text='{"narration": "You drop'),  # cut off
        Reply(text='{"title": "no narration"}'),  # fails validation
        Reply(text="   "),  # empty
        Reply(json=SCENE, finish="max_tokens"),
        Reply(json=SCENE, finish="recitation"),
    ],
)
def test_an_unusable_answer_is_retried(fake, make_client, telemetry, bad):
    fake.script(Node.NARRATOR, bad, Reply(json=SCENE))

    assert run(make_client().structured(Node.NARRATOR, PROMPT, Narration)) == SCENE
    assert telemetry.calls[0].retries == 1


class Scores(BaseModel):
    by_name: dict[str, int] = {}


def _failures(lines: list[dict]) -> list[dict]:
    return [line["llm"] for line in lines if line["message"].startswith("Model call failed")]


def test_an_answer_that_fails_validation_logs_where_and_how_but_no_value(
    fake, make_client, log_lines
):
    # On 2026-11-05 most drafts failed validation twice, and the log said only "invalid_output".
    bad = '{"title": "Rosa Bianchi", "narration": 5, "choices": "Rosa Bianchi"}'
    fake.script(Node.NARRATOR, Reply(text=bad), Reply(text=bad))

    with pytest.raises(LLMUnavailable):
        run(make_client().structured(Node.NARRATOR, PROMPT, Narration))

    retry, failed = _failures(log_lines())
    for fields in (retry, failed):
        assert fields["reason"] == "invalid_output"
        assert fields["errors"] == ["narration: string_type", "choices: list_type"]
        assert fields["error_count"] == 2 and fields["output_chars"] == len(bad)
    assert "Rosa Bianchi" not in json.dumps(log_lines())


def test_unparseable_json_and_keys_the_model_wrote_are_logged_without_values(
    fake, make_client, log_lines
):
    fake.script(
        Node.CHECKER,
        Reply(text='{"by_name": {"Rosa Bianchi": "many"}}'),
        Reply(text='{"by_name": {"Rosa'),
    )

    with pytest.raises(LLMUnavailable):
        run(make_client().structured(Node.CHECKER, PROMPT, Scores))

    retry, failed = _failures(log_lines())
    assert retry["errors"] == ["by_name.*: int_parsing"]
    assert failed["errors"] == ["(answer): json_invalid"]
    assert "Rosa" not in json.dumps(log_lines())


def test_an_answer_cut_off_logs_no_validation_errors(fake, make_client, log_lines):
    fake.script(Node.NARRATOR, Reply(json=SCENE, finish="max_tokens"), Reply(json=SCENE))

    run(make_client().structured(Node.NARRATOR, PROMPT, Narration))

    [retry] = _failures(log_lines())
    assert retry["reason"] == "max_tokens" and "errors" not in retry


def test_a_fenced_answer_still_parses(fake, make_client):
    fake.script(Node.NARRATOR, Reply(text=f"```json\n{SCENE.model_dump_json()}\n```"))

    assert run(make_client().structured(Node.NARRATOR, PROMPT, Narration)) == SCENE


def test_a_rejected_player_key_is_bad_key_with_no_retry(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Fail(kind="auth", status=400), Reply(json=SCENE))

    with pytest.raises(BadKey) as raised:
        run(make_client(byok=True).structured(Node.NARRATOR, PROMPT, Narration))

    assert raised.value.code == "bad_key"
    assert telemetry.calls[0].outcome == "bad_key"
    assert telemetry.calls[0].byok
    assert fake.pending() == 1


@pytest.mark.parametrize("kind", ["auth", "invalid"])
def test_our_own_rejected_requests_are_unavailable_with_no_retry(fake, make_client, kind):
    fake.script(Node.NARRATOR, Fail(kind=kind, status=403), Reply(json=SCENE))

    with pytest.raises(LLMUnavailable):
        run(make_client().structured(Node.NARRATOR, PROMPT, Narration))
    assert fake.pending() == 1


@pytest.mark.parametrize("stage", ["prompt", "response"])
def test_a_block_is_raised_at_once_with_its_categories(fake, make_client, telemetry, stage):
    fake.script(Node.INTERPRET, Block(categories=("sexually_explicit",), stage=stage))

    with pytest.raises(LLMBlocked) as raised:
        run(make_client().structured(Node.INTERPRET, PROMPT, Narration))

    blocked = raised.value
    assert blocked.code == "blocked"
    assert blocked.categories == ("sexually_explicit",)
    assert blocked.stage == stage
    assert not blocked.streamed
    [record] = telemetry.calls
    assert record.outcome == "blocked" and record.blocked
    assert record.block_categories == ("sexually_explicit",) and record.block_stage == stage
    assert record.retries == 0


def test_a_call_that_hangs_past_its_deadline_is_retried_then_unavailable(fake, make_client):
    fake.script(Node.CHECKER, Hang(), Hang())

    with pytest.raises(LLMUnavailable):
        run(
            make_client().structured(
                Node.CHECKER, PROMPT, Narration, options=CallOptions(timeout_s=0.01)
            )
        )


def test_an_unexpected_backend_error_is_unavailable_with_no_retry(make_client, telemetry):
    class Broken:
        provider = "fake"
        calls = 0

        async def stream(self, request):
            Broken.calls += 1
            raise KeyError("bug")
            yield  # pragma: no cover

        async def aclose(self):
            return None

    with pytest.raises(LLMUnavailable):
        run(make_client(backend=Broken()).text(Node.SUMMARIZER, PROMPT))
    assert Broken.calls == 1
    assert telemetry.calls[0].error_kind == "invalid"


def test_plain_text(fake, make_client):
    fake.script(Node.SUMMARIZER, Reply(text="Chapter one: the cave."))

    assert run(make_client().text(Node.SUMMARIZER, PROMPT)) == "Chapter one: the cave."


def test_streaming_shows_the_field_as_it_is_written_then_completes(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events = run(
        collect(
            make_client().stream_structured(Node.NARRATOR, PROMPT, Narration, field="narration")
        )
    )

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    assert len(deltas) > 1
    assert "".join(deltas) == SCENE.narration
    assert events[-1] == Completed(SCENE)
    [record] = telemetry.calls
    assert record.outcome == "ok"
    assert record.first_token_ms is not None


def test_streaming_says_when_the_text_is_whole_before_the_answer_is(fake, make_client):
    """S4: the fields that stream are written first, and the rest of the answer takes seconds
    more, so the stream says once when they are whole (`graph.turn.last_lines`)."""
    whole = '{"title": "Cave", "narration": "You drop to a crouch.", "choices": ["Ru'
    fake.script(Node.NARRATOR, Fail(after_text=whole), Reply(json=SCENE))

    events = run(
        collect(
            make_client().stream_structured(Node.NARRATOR, PROMPT, Narration, field="narration")
        )
    )

    restart = events.index(StreamRestart())
    assert events[:restart].count(TextEnded()) == 1
    assert events[restart - 1] == TextEnded()
    # Again for the retry, after its last text and before its result.
    assert events[restart:].count(TextEnded()) == 1
    last_text = max(i for i, e in enumerate(events) if isinstance(e, TextDelta))
    assert last_text < events.index(TextEnded(), restart) < len(events) - 1


def test_a_stream_that_fails_after_text_restarts_and_retries(fake, make_client, telemetry):
    fake.script(
        Node.NARRATOR,
        Fail(after_text='{"title": "Cave", "narration": "You drop to a cr'),
        Reply(json=SCENE),
    )

    events = run(
        collect(
            make_client().stream_structured(Node.NARRATOR, PROMPT, Narration, field="narration")
        )
    )

    restart = events.index(StreamRestart())
    before = "".join(e.text for e in events[:restart] if isinstance(e, TextDelta))
    after = "".join(e.text for e in events[restart:] if isinstance(e, TextDelta))
    assert before == "You drop to a cr"
    assert after == SCENE.narration
    assert events[-1] == Completed(SCENE)
    assert telemetry.calls[0].retries == 1


def test_a_stream_that_fails_before_any_text_retries_without_a_restart(fake, make_client):
    fake.script(Node.NARRATOR, Fail(after_text='{"title": "Ca'), Reply(json=SCENE))

    events = run(
        collect(
            make_client().stream_structured(Node.NARRATOR, PROMPT, Narration, field="narration")
        )
    )

    assert StreamRestart() not in events
    assert events[-1] == Completed(SCENE)


def test_a_stream_blocked_midway_says_text_was_shown(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Block(after_text='{"narration": "You drag her into the'))
    shown: list[str] = []

    async def consume():
        stream = make_client().stream_structured(
            Node.NARRATOR, PROMPT, Narration, field="narration"
        )
        async for event in stream:
            shown.append(event.text)

    with pytest.raises(LLMBlocked) as raised:
        run(consume())

    assert "".join(shown) == "You drag her into the"
    assert raised.value.streamed
    assert telemetry.calls[0].outcome == "blocked"


def test_a_stream_the_caller_abandons_is_still_recorded(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    async def first_delta_only():
        events = make_client().stream_structured(
            Node.NARRATOR, PROMPT, Narration, field="narration"
        )
        async with aclosing(events) as stream:
            async for _ in stream:
                break

    run(first_delta_only())

    [record] = telemetry.calls
    assert record.outcome == "cancelled"
    assert record.attempts == 1


def test_streaming_two_fields_shows_one_then_the_other(fake, make_client):
    """R1: the narrator's action and narration stream as one scene, a paragraph apart."""
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    events = run(
        collect(
            make_client().stream_structured(
                Node.NARRATOR, PROMPT, Narration, field=("title", "narration")
            )
        )
    )

    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == (
        f"{SCENE.title}\n\n{SCENE.narration}"
    )
    assert events[-1] == Completed(SCENE)


@pytest.mark.parametrize("field", ["prose", ("narration", "prose")])
def test_streaming_an_unknown_field_is_a_programming_error(make_client, field):
    with pytest.raises(ValueError):
        make_client().stream_structured(Node.NARRATOR, PROMPT, Narration, field=field)


def test_a_picture_call_returns_the_image_and_bills_per_image(fake, make_client, telemetry):
    fake.script(Node.PICTURE, Reply(images=(b"\x89PNG fake",)))
    prompt = Prompt.build("House style.", "A troll in a cave.", images=[ImagePart(b"ref")])

    image = run(make_client().image(Node.PICTURE, prompt))

    assert image.data == b"\x89PNG fake"
    [request] = fake.requests
    assert request.image is not None and request.image.size == "1K"
    assert request.safety == safety_settings("mature", picture=True)
    [record] = telemetry.calls
    assert record.images == 1
    assert record.cost_usd >= Decimal("0.0336")


def test_a_picture_call_with_no_image_is_retried(fake, make_client):
    fake.script(Node.PICTURE, Reply(text="I can't draw that."), Reply(images=(b"png",)))

    assert run(make_client().image(Node.PICTURE, PROMPT)).data == b"png"


def test_logs_never_carry_the_prompt(fake, make_client, caplog):
    secret = "the-secret-player-text"
    prompt = Prompt.build(f"system {secret}", f"user {secret}")
    fake.script(Node.NARRATOR, Fail(), Fail(), Block())

    caplog.set_level(logging.DEBUG, logger="graph.llm")
    with pytest.raises(LLMUnavailable):
        run(make_client().structured(Node.NARRATOR, prompt, Narration))
    with pytest.raises(LLMBlocked):
        run(make_client().structured(Node.NARRATOR, prompt, Narration))

    assert caplog.records
    for record in caplog.records:
        assert secret not in record.getMessage()
        assert secret not in repr(record.__dict__)
    assert secret not in repr(prompt)


def test_turn_telemetry_sums_the_calls(fake, make_client, telemetry):
    fake.script(Node.INTERPRET, Reply(json=SCENE))
    fake.script(Node.NARRATOR, Fail(), Reply(json=SCENE))
    client = make_client()

    async def turn():
        await client.structured(Node.INTERPRET, PROMPT, Narration)
        await client.structured(Node.NARRATOR, PROMPT, Narration)

    run(turn())
    summary = telemetry.summary()

    assert summary["calls"] == 2
    assert summary["retries"] == 1
    assert summary["blocks"] == 0
    assert summary["cost_usd"] == pytest.approx(float(telemetry.cost_usd))
    assert set(summary["by_node"]) == {"interpret", "narrator"}
    assert summary["input_tokens"] == sum(c.input_tokens for c in telemetry.calls)


def test_a_slow_reader_never_times_out_a_healthy_stream(fake, make_client, telemetry):
    fake.chunk_size = 3
    fake.script(Node.NARRATOR, Reply(json=SCENE))

    async def slow_reader():
        stream = make_client().stream_structured(
            Node.NARRATOR, PROMPT, Narration, field="narration", options=CallOptions(timeout_s=0.05)
        )
        async with aclosing(stream) as events:
            async for event in events:
                await asyncio.sleep(0.01)  # 10+ deltas: far longer than the deadline in total
                if isinstance(event, Completed):
                    return event.value

    assert run(slow_reader()) == SCENE
    assert telemetry.calls[0].retries == 0


def test_time_to_first_text_comes_from_the_attempt_the_player_keeps(fake, make_client, telemetry):
    fake.script(Node.NARRATOR, Fail(after_text='{"narration": "You drop'), Reply(json=SCENE))

    async def reader_that_pauses_on_restart():
        stream = make_client().stream_structured(
            Node.NARRATOR, PROMPT, Narration, field="narration"
        )
        async with aclosing(stream) as events:
            async for event in events:
                if isinstance(event, StreamRestart):
                    await asyncio.sleep(0.05)  # the retry's first text comes after this

    run(reader_that_pauses_on_restart())

    assert telemetry.calls[0].first_token_ms >= 50


def test_only_calls_on_our_own_account_are_billable(fake, telemetry):
    from graph.llm import ModelClient, ModelConfig

    fake.script(Node.NARRATOR, Reply(json=SCENE))
    fake.script(Node.PICTURE, Reply(images=(b"png",)))
    player_key = ModelClient(fake, ModelConfig(), rating="mature", recorder=telemetry, byok=True)
    our_key = ModelClient(fake, ModelConfig(), rating="mature", recorder=telemetry)

    async def calls():
        await player_key.structured(Node.NARRATOR, PROMPT, Narration)
        await our_key.image(Node.PICTURE, PROMPT)

    run(calls())

    narration, picture = telemetry.calls
    assert telemetry.cost_usd == narration.cost_usd + picture.cost_usd
    assert telemetry.billable_cost_usd == picture.cost_usd
    assert telemetry.summary()["billable_cost_usd"] == float(picture.cost_usd)
