import asyncio
import logging

from asgiref.sync import async_to_sync
from django.http import StreamingHttpResponse
from django.test import Client, RequestFactory

from lucid import logs
from lucid.middleware import RequestContextMiddleware

TRACE = "0123456789abcdef0123456789abcdef"


def _request_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line["logger"] == "lucid.request"]


def test_a_request_id_is_made_and_echoed_and_the_request_is_logged(log_lines):
    response = Client().get("/v1/nowhere")

    request_id = response.headers["X-Request-Id"]
    assert len(request_id) == 32
    [line] = _request_lines(log_lines())
    assert line["message"] == "GET /v1/nowhere 404"
    assert (line["request_id"], line["status"], line["path"]) == (request_id, 404, "/v1/nowhere")
    assert line["duration_ms"] >= 0


def test_a_safe_incoming_request_id_and_the_cloud_trace_are_kept(log_lines):
    response = Client().get(
        "/v1/nowhere",
        headers={"X-Request-Id": "app-42", "X-Cloud-Trace-Context": f"{TRACE}/123;o=1"},
    )

    assert response.headers["X-Request-Id"] == "app-42"
    [line] = _request_lines(log_lines())
    assert line["trace_id"] == TRACE
    assert line["logging.googleapis.com/trace"] == f"projects/test-project/traces/{TRACE}"


def test_an_unsafe_incoming_request_id_is_replaced():
    response = Client().get("/v1/nowhere", headers={"X-Request-Id": 'x"\n{"severity":"ERROR"}'})

    assert response.headers["X-Request-Id"] != 'x"\n{"severity":"ERROR"}'


def test_health_is_logged_at_debug(log_lines):
    Client().get("/health")

    [line] = _request_lines(log_lines())
    assert line["severity"] == "DEBUG"


def test_the_context_closes_after_a_sync_request():
    Client().get("/health")

    assert logs.current_context() == {}


def test_a_streamed_response_keeps_its_context_and_is_logged_when_the_stream_ends(log_lines):
    """WS3's turn streams server-sent events after the view returns: lines written while it
    streams still carry the request's ids."""

    async def events():
        logs.bind(story_id="s1")
        yield b"event: turn.started\n\n"
        await asyncio.sleep(0)
        logging.getLogger("lucid.test").info("mid-stream")
        yield b"event: scene.completed\n\n"

    async def view(request):
        return StreamingHttpResponse(events(), content_type="text/event-stream")

    async def run() -> tuple[list[bytes], list[dict]]:
        middleware = RequestContextMiddleware(view)
        response = await middleware(RequestFactory().get("/v1/stories/s1/turns"))
        assert _request_lines(log_lines()) == []
        chunks = [chunk async for chunk in response]
        return chunks, log_lines()

    chunks, lines = async_to_sync(run)()

    assert len(chunks) == 2
    mid, done = [line for line in lines if line["logger"] in ("lucid.test", "lucid.request")]
    assert mid["message"] == "mid-stream"
    assert done["message"] == "GET /v1/stories/s1/turns 200"
    assert mid["request_id"] == done["request_id"] is not None
    assert mid["story_id"] == done["story_id"] == "s1"


def test_the_sync_path_logs_and_closes_its_context(log_lines):
    def view(request):
        logs.bind(user_id="u1")
        return StreamingHttpResponse(iter([b"a"]))

    middleware = RequestContextMiddleware(view)
    response = middleware(RequestFactory().get("/v1/sync"))

    assert response.headers["X-Request-Id"]
    [line] = _request_lines(log_lines())
    assert (line["status"], line["user_id"]) == (200, "u1")
    assert logs.current_context() == {}


def test_the_story_id_is_bound_from_the_url(log_lines):
    Client().get("/v1/stories/not-a-story")

    [line] = _request_lines(log_lines())
    assert line["story_id"] == "not-a-story"
