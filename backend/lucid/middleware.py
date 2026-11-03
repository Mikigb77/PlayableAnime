"""Request context for logs (T4): ids in, one request line out."""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from inspect import iscoroutinefunction

from asgiref.sync import markcoroutinefunction
from django.http import HttpRequest, HttpResponseBase

from lucid import errors, logs

logger = logging.getLogger("lucid.request")

REQUEST_ID_HEADER = "X-Request-Id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Liveness probes would drown the request lines, so they're logged at DEBUG.
_QUIET_PATHS = frozenset({"/health"})


class RequestContextMiddleware:
    """Opens the log context for each request and logs one line when it ends.

    The request id comes from `X-Request-Id` when the caller sends a safe one, otherwise it is
    new, and it is echoed back in the response. The trace comes from Cloud Run's
    `X-Cloud-Trace-Context`. The story id is bound from the URL (`story_id`), and the auth layer
    binds the user id with `lucid.logs.bind(user_id=...)`. Headers, bodies and query strings are
    never logged (T6).

    A streamed response (a turn's server-sent events) is sent after the view returns, so under
    ASGI the context stays open until the stream ends, and the request line is written then.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)
        else:
            self.process_view = self._process_view_sync  # type: ignore[method-assign]

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self._acall(request)
        # Sync mode (runserver, some tests): a streamed response is logged before it is sent.
        token, started = self._start(request)
        try:
            response = self.get_response(request)
        except BaseException:
            self._end(request, None, started, token)
            raise
        self._finish(request, response, started, token, wrap_stream=False)
        return response

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        token, started = self._start(request)
        try:
            response = await self.get_response(request)
        except BaseException:
            self._end(request, None, started, token)
            raise
        self._finish(request, response, started, token, wrap_stream=True)
        return response

    async def process_view(self, request, view_func, view_args, view_kwargs) -> None:
        _bind_story(view_kwargs)

    def _process_view_sync(self, request, view_func, view_args, view_kwargs) -> None:
        _bind_story(view_kwargs)

    def _start(self, request: HttpRequest) -> tuple[object, float]:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        trace_id, span_id, sampled = logs.parse_trace_header(
            request.headers.get("X-Cloud-Trace-Context")
        )
        request.request_id = request_id  # type: ignore[attr-defined]
        token = logs.start_context(
            request_id=request_id, trace_id=trace_id, span_id=span_id, trace_sampled=sampled
        )
        return token, time.perf_counter()

    def _finish(
        self,
        request: HttpRequest,
        response: HttpResponseBase,
        started: float,
        token: object,
        *,
        wrap_stream: bool,
    ) -> None:
        response[REQUEST_ID_HEADER] = request.request_id  # type: ignore[attr-defined]
        if not (wrap_stream and response.streaming):
            self._end(request, response, started, token)
            return
        content = response.streaming_content  # type: ignore[attr-defined]

        if response.is_async:  # type: ignore[attr-defined]

            async def logged_async() -> AsyncIterator[bytes]:
                try:
                    async for chunk in content:
                        yield chunk
                finally:
                    self._end(request, response, started, token)

            response.streaming_content = logged_async()  # type: ignore[attr-defined]
        else:

            def logged() -> Iterator[bytes]:
                try:
                    yield from content
                finally:
                    self._end(request, response, started, token)

            response.streaming_content = logged()  # type: ignore[attr-defined]

    def _end(
        self,
        request: HttpRequest,
        response: HttpResponseBase | None,
        started: float,
        token: object,
    ) -> None:
        try:
            self._log(request, response, started)
        finally:
            logs.end_context(token)

    def _log(self, request: HttpRequest, response: HttpResponseBase | None, started: float) -> None:
        status = response.status_code if response is not None else 500
        level = logging.DEBUG if request.path in _QUIET_PATHS else logging.INFO
        logger.log(
            level,
            "%s %s %s",
            request.method,
            request.path,
            status,
            extra={
                "method": request.method,
                "path": request.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )


def _bind_story(view_kwargs: dict) -> None:
    story_id = view_kwargs.get("story_id")
    if story_id:
        logs.bind(story_id=str(story_id))


class ErrorEnvelopeMiddleware:
    """The innermost middleware: gives the envelope to error responses that views return instead
    of raising (T7), before the outer middleware adds CORS and request-id headers to them."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response) -> None:
        self.get_response = get_response
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if self.is_async:
            return self._acall(request)
        return errors.with_envelope(self.get_response(request))

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        return errors.with_envelope(await self.get_response(request))
