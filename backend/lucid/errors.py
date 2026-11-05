"""The error envelope from docs/API.md (T7): every error body is

    {"error": {"code": "...", "message": "...", "details": {}}}

Raise `ApiError` anywhere in a view, or let Ninja's own errors and Django's 404 reach the handlers
below. Nothing returns a bare 500: an unexpected exception is logged with its traceback, which
sends it to Error Reporting, and answers `internal_error`.
"""

import logging
from enum import StrEnum
from typing import Any

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseNotAllowed,
    JsonResponse,
)
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, AuthorizationError, HttpError, ValidationError

logger = logging.getLogger("lucid.errors")


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    BIRTH_DATE_REQUIRED = "birth_date_required"
    UNAUTHENTICATED = "unauthenticated"
    OUT_OF_CREDITS = "out_of_credits"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    VERSION_CONFLICT = "version_conflict"
    STORY_ENDED = "story_ended"
    UNREADABLE_ACTION = "unreadable_action"
    BAD_KEY = "bad_key"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    INTERNAL_ERROR = "internal_error"
    LLM_UNAVAILABLE = "llm_unavailable"
    SIGN_IN_UNAVAILABLE = "sign_in_unavailable"


# The HTTP status for each code, as in API.md's table.
STATUS = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.BIRTH_DATE_REQUIRED: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.OUT_OF_CREDITS: 402,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.STORY_ENDED: 409,
    ErrorCode.UNREADABLE_ACTION: 422,
    ErrorCode.BAD_KEY: 422,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.QUOTA_EXCEEDED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.LLM_UNAVAILABLE: 503,
    ErrorCode.SIGN_IN_UNAVAILABLE: 503,
}

# What the app can show when a view gives no message of its own.
DEFAULT_MESSAGES = {
    ErrorCode.VALIDATION_ERROR: "The request is invalid.",
    ErrorCode.BIRTH_DATE_REQUIRED: "Your birth date is needed to continue.",
    ErrorCode.UNAUTHENTICATED: "Sign in to continue.",
    ErrorCode.OUT_OF_CREDITS: "You're out of credits.",
    ErrorCode.FORBIDDEN: "You can't do that.",
    ErrorCode.NOT_FOUND: "Not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "Method not allowed.",
    ErrorCode.VERSION_CONFLICT: "The story moved on. Reload it and try again.",
    ErrorCode.STORY_ENDED: "This story has reached its ending.",
    ErrorCode.UNREADABLE_ACTION: "That action couldn't be read. Try rephrasing it.",
    ErrorCode.BAD_KEY: "Your API key was rejected.",
    ErrorCode.RATE_LIMITED: "Slow down a little, then try again.",
    ErrorCode.QUOTA_EXCEEDED: "Today's turns are used up.",
    ErrorCode.INTERNAL_ERROR: "Something went wrong on our side.",
    ErrorCode.LLM_UNAVAILABLE: "The storyteller is unavailable. Try again in a moment.",
    ErrorCode.SIGN_IN_UNAVAILABLE: "Google sign-in isn't available right now. Try again soon.",
}

# Ninja raises plain HttpErrors for some statuses (a body that isn't JSON is a 400).
_CODE_FOR_STATUS = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.VERSION_CONFLICT,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.LLM_UNAVAILABLE,
}


class ApiError(Exception):
    """An error the app can act on. `details` carries the extra fields API.md lists per code,
    such as `current_version` for `version_conflict` or `retry_after_s` for `rate_limited`."""

    def __init__(
        self, code: ErrorCode, message: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        self.code = ErrorCode(code)
        self.status = STATUS[self.code]
        self.message = message or DEFAULT_MESSAGES[self.code]
        self.details = details or {}
        super().__init__(f"{self.code}: {self.message}")


def version_conflict(current_version: int) -> ApiError:
    """Another turn was saved since the caller read the story (T10)."""
    return ApiError(
        ErrorCode.VERSION_CONFLICT,
        "Another turn was saved first.",
        {"current_version": current_version},
    )


def field_error(
    field: str, message: str, *, source: str = "body", type: str = "invalid"
) -> ApiError:
    """A `validation_error` about one field, in the `details.fields` shape from API.md."""
    return ApiError(
        ErrorCode.VALIDATION_ERROR,
        message,
        {"fields": [{"field": field, "source": source, "message": message, "type": type}]},
    )


def envelope(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": str(code), "message": message, "details": details or {}}}


def error_response(error: ApiError) -> JsonResponse:
    return JsonResponse(envelope(error.code, error.message, error.details), status=error.status)


def validation_details(errors: list[dict[str, Any]]) -> dict[str, Any]:
    """Turns Ninja's pydantic-style errors into `details.fields`: one entry per problem, with
    the dotted field path inside its source (`body`, `query`, `path`, `header`)."""
    fields = []
    for error in errors:
        loc = [str(part) for part in error.get("loc", ())]
        source = loc[0] if loc else "body"
        # Ninja puts the view's parameter name after the source when the body is one schema.
        path = loc[2:] if len(loc) > 2 and source == "body" else loc[1:]
        fields.append(
            {
                "field": ".".join(path) or source,
                "source": source,
                "message": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "invalid")),
            }
        )
    return {"fields": fields}


def install(api: NinjaAPI) -> None:
    """Registers the envelope handlers on the Ninja API, replacing Ninja's defaults."""

    def on_api_error(request: HttpRequest, exc: ApiError) -> HttpResponse:
        return error_response(exc)

    def on_validation(request: HttpRequest, exc: ValidationError) -> HttpResponse:
        return error_response(
            ApiError(ErrorCode.VALIDATION_ERROR, details=validation_details(exc.errors))
        )

    def on_unauthenticated(request: HttpRequest, exc: AuthenticationError) -> HttpResponse:
        return error_response(ApiError(ErrorCode.UNAUTHENTICATED))

    def on_forbidden(request: HttpRequest, exc: AuthorizationError) -> HttpResponse:
        return error_response(ApiError(ErrorCode.FORBIDDEN))

    def on_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
        code = _CODE_FOR_STATUS.get(exc.status_code)
        if code is None:
            code = ErrorCode.VALIDATION_ERROR if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR
        error = ApiError(code, str(exc) or None)
        response = error_response(error)
        response.status_code = exc.status_code
        return response

    def on_not_found(request: HttpRequest, exc: Exception) -> HttpResponse:
        return error_response(ApiError(ErrorCode.NOT_FOUND))

    def on_permission_denied(request: HttpRequest, exc: PermissionDenied) -> HttpResponse:
        return error_response(ApiError(ErrorCode.FORBIDDEN))

    def on_unexpected(request: HttpRequest, exc: Exception) -> HttpResponse:
        logger.exception("Unhandled error in %s %s", request.method, request.path)
        return error_response(ApiError(ErrorCode.INTERNAL_ERROR))

    api.add_exception_handler(ApiError, on_api_error)
    api.add_exception_handler(ValidationError, on_validation)
    api.add_exception_handler(AuthenticationError, on_unauthenticated)
    api.add_exception_handler(AuthorizationError, on_forbidden)
    api.add_exception_handler(HttpError, on_http_error)
    api.add_exception_handler(Http404, on_not_found)
    # `Model.DoesNotExist` from an `aget()` that found nothing.
    api.add_exception_handler(ObjectDoesNotExist, on_not_found)
    api.add_exception_handler(PermissionDenied, on_permission_denied)
    api.add_exception_handler(Exception, on_unexpected)


# Django-level handlers, for URLs outside the Ninja API and errors before a view runs.


def handler404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return error_response(ApiError(ErrorCode.NOT_FOUND))


def handler500(request: HttpRequest) -> HttpResponse:
    # Django has already logged the exception with its traceback (`django.request`).
    return error_response(ApiError(ErrorCode.INTERNAL_ERROR))


def handler400(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return error_response(ApiError(ErrorCode.VALIDATION_ERROR, "Bad request."))


def handler403(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return error_response(ApiError(ErrorCode.FORBIDDEN))


def with_envelope(response: HttpResponseBase) -> HttpResponseBase:
    """Ninja answers a wrong method with a plain-text 405 instead of raising, so the handlers
    above never see it. This gives that response the envelope and keeps its Allow header."""
    if not isinstance(response, HttpResponseNotAllowed):
        return response
    replacement = error_response(ApiError(ErrorCode.METHOD_NOT_ALLOWED))
    replacement["Allow"] = response["Allow"]
    return replacement
