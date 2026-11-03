"""Structured JSON logging for Cloud Logging (T4 to T6, B3).

Each request gets a context (request id, trace, user id, story id) that every log line written
while it runs carries, whichever logger wrote it. `RequestContextMiddleware` opens the context;
code that learns more during the request, such as the auth layer finding the user, calls `bind()`.

This module imports nothing from Django, so uvicorn and plain Python code can use it too.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# The fields every line carries, null when unknown (T4).
CONTEXT_FIELDS = ("request_id", "trace_id", "span_id", "trace_sampled", "user_id", "story_id")

_context: ContextVar[dict[str, Any] | None] = ContextVar("lucid_log_context", default=None)

# LogRecord's own attributes, so only what callers pass in `extra` is added to the line.
_RECORD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}
# Never written to a log line: Django's request object (its repr carries the query string).
# uvicorn's `color_message` repeats the message with terminal colours.
_SKIPPED_EXTRAS = frozenset({"request", "color_message"})
# Anything a caller passes by mistake that holds a secret or a prompt is redacted (T6).
_SECRET_NAMES = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "prompt",
        "secret",
        "system_prompt",
        "token",
        "x-llm-api-key",
    }
)
_SECRET_SUFFIXES = ("_key", "_token", "_secret", "_password", "_prompt")
REDACTED = "[redacted]"

_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}
_ERROR_EVENT_TYPE = (
    "type.googleapis.com/google.devtools.clouderrorreporting.v1beta1.ReportedErrorEvent"
)

_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


def start_context(**fields: Any) -> object:
    """Opens a fresh context for one request and returns a token for `end_context`."""
    return _context.set({name: None for name in CONTEXT_FIELDS} | fields)


def end_context(token: object) -> None:
    try:
        _context.reset(token)  # type: ignore[arg-type]
    except ValueError:
        # The token belongs to another context, as when a stream is finished elsewhere.
        _context.set(None)


def bind(**fields: Any) -> None:
    """Adds fields, such as `user_id` or `story_id`, to every later line of this request.

    The context is one shared dict per request, so a field bound in a worker thread
    (`sync_to_async`) is seen by the async code too, and the other way round.
    """
    context = _context.get()
    if context is None:
        _context.set(dict(fields))
    else:
        context.update(fields)


def current_context() -> dict[str, Any]:
    return dict(_context.get() or {})


def parse_trace_header(header: str | None) -> tuple[str | None, str | None, bool | None]:
    """Reads Cloud Run's `X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=1`.

    Returns the trace id, the span id as 16 hex digits (the header has it in decimal, Cloud
    Logging wants hex) and whether the trace is sampled. Anything malformed is ignored.
    """
    if not header:
        return None, None, None
    trace_part, _, options = header.partition(";")
    trace_id, _, span = trace_part.partition("/")
    trace_id = trace_id.strip().lower()
    if not _TRACE_ID.match(trace_id):
        return None, None, None
    span_id = None
    if span.strip().isdigit():
        span_value = int(span.strip())
        if 0 < span_value < 2**64:
            span_id = f"{span_value:016x}"
    sampled = None
    if options.strip().startswith("o="):
        sampled = options.strip()[2:] == "1"
    return trace_id, span_id, sampled


def redact(value: Any) -> Any:
    """Replaces values under secret-looking keys, at any depth, with `[redacted]` (T6)."""
    if isinstance(value, dict):
        return {k: REDACTED if _is_secret(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def _is_secret(key: object) -> bool:
    name = str(key).lower()
    return name in _SECRET_NAMES or name.endswith(_SECRET_SUFFIXES)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, in the shape Cloud Logging and Error Reporting read."""

    def __init__(self, project: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.project = project

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "severity": _SEVERITY.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "logger": record.name,
        }
        context = {name: None for name in CONTEXT_FIELDS} | (_context.get() or {})
        extras = {
            key: value
            for key, value in vars(record).items()
            if key not in _RECORD_ATTRS and key not in _SKIPPED_EXTRAS
        }
        # A field passed explicitly in `extra` wins over the request context.
        for name in CONTEXT_FIELDS:
            if name in extras:
                context[name] = extras.pop(name)
        entry.update(redact(context))
        entry.update(redact(extras))

        if context["trace_id"] and self.project:
            entry["logging.googleapis.com/trace"] = (
                f"projects/{self.project}/traces/{context['trace_id']}"
            )
            if context["span_id"]:
                entry["logging.googleapis.com/spanId"] = context["span_id"]
            if context["trace_sampled"] is not None:
                entry["logging.googleapis.com/trace_sampled"] = context["trace_sampled"]

        if record.exc_info:
            # Error Reporting groups entries whose `stack_trace` holds a Python traceback (T7).
            entry["stack_trace"] = self.formatException(record.exc_info)
            if record.levelno >= logging.ERROR:
                entry["@type"] = _ERROR_EVENT_TYPE
        elif record.stack_info:
            entry["stack_trace"] = self.formatStack(record.stack_info)

        return json.dumps(entry, ensure_ascii=False, default=str)
