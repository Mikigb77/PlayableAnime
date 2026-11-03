import logging

from lucid import logs
from lucid.logs import CONTEXT_FIELDS, JsonFormatter, parse_trace_header, redact

TRACE = "0123456789abcdef0123456789abcdef"


def _format(record_kwargs: dict | None = None, **extra) -> dict:
    import json

    record = logging.makeLogRecord(
        {"name": "lucid.test", "levelno": logging.INFO, "levelname": "INFO", "msg": "hello"}
        | (record_kwargs or {})
        | extra
    )
    return json.loads(JsonFormatter(project="playable-anime").format(record))


def test_a_line_has_severity_message_and_every_context_field_even_outside_a_request():
    line = _format()

    assert line["severity"] == "INFO"
    assert line["message"] == "hello"
    assert line["logger"] == "lucid.test"
    assert {name: line[name] for name in CONTEXT_FIELDS} == dict.fromkeys(CONTEXT_FIELDS)


def test_a_line_carries_the_request_context_and_the_cloud_logging_trace():
    token = logs.start_context(request_id="r1", trace_id=TRACE, span_id="000000000000007b")
    try:
        logs.bind(user_id="u1", story_id="s1")
        line = _format()
    finally:
        logs.end_context(token)

    assert (line["request_id"], line["user_id"], line["story_id"]) == ("r1", "u1", "s1")
    assert line["logging.googleapis.com/trace"] == f"projects/playable-anime/traces/{TRACE}"
    assert line["logging.googleapis.com/spanId"] == "000000000000007b"
    assert logs.current_context() == {}


def test_extras_are_added_and_an_explicit_context_field_wins():
    token = logs.start_context(story_id="from-context")
    try:
        line = _format(story_id="explicit", status=200, duration_ms=1.5)
    finally:
        logs.end_context(token)

    assert (line["story_id"], line["status"], line["duration_ms"]) == ("explicit", 200, 1.5)


def test_secrets_and_prompts_are_redacted_at_any_depth_but_token_counts_are_kept():
    line = _format(
        api_key="AIza-secret",
        llm={"x-llm-api-key": "AIza-secret", "prompt": "the whole prompt", "input_tokens": 812},
        refresh_token="rt",
        headers=[{"authorization": "Bearer abc"}],
    )

    assert line["api_key"] == "[redacted]"
    assert line["refresh_token"] == "[redacted]"
    assert line["llm"] == {
        "x-llm-api-key": "[redacted]",
        "prompt": "[redacted]",
        "input_tokens": 812,
    }
    assert line["headers"] == [{"authorization": "[redacted]"}]


def test_django_request_objects_are_never_written():
    line = _format(request=object(), status_code=500)

    assert "request" not in line
    assert line["status_code"] == 500


def test_an_error_with_a_traceback_is_shaped_for_error_reporting():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        exc_info = sys.exc_info()
    line = _format({"levelno": logging.ERROR, "levelname": "ERROR", "exc_info": exc_info})

    assert line["severity"] == "ERROR"
    assert "RuntimeError: boom" in line["stack_trace"]
    assert line["@type"].endswith("ReportedErrorEvent")


def test_bind_outside_a_request_starts_a_context():
    token = logs.start_context()
    logs.end_context(token)
    logs.bind(story_id="s1")
    try:
        assert logs.current_context() == {"story_id": "s1"}
    finally:
        logs._context.set(None)


def test_trace_header_parsing():
    assert parse_trace_header(f"{TRACE}/123;o=1") == (TRACE, "000000000000007b", True)
    assert parse_trace_header(f"{TRACE.upper()}/0;o=0") == (TRACE, None, False)
    assert parse_trace_header(TRACE) == (TRACE, None, None)
    assert parse_trace_header("not-a-trace/1;o=1") == (None, None, None)
    assert parse_trace_header(None) == (None, None, None)


def test_redact_leaves_ordinary_values_alone():
    assert redact({"story_id": "s1", "turn": 3, "tags": ["a"]}) == {
        "story_id": "s1",
        "turn": 3,
        "tags": ["a"],
    }
