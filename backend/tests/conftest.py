import io
import json
import logging

import pytest

from lucid import logs
from lucid.logs import JsonFormatter


@pytest.fixture
def log_lines():
    """The JSON lines logged during the test, parsed, as Cloud Logging would receive them."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(project="test-project"))
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture(autouse=True)
def fresh_log_context():
    """A response a test never reads to the end (a file, a stream) keeps its request's log
    context open, as it would until the stream ends in production. Start each test clean."""
    logs._context.set(None)
