import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client, override_settings
from django.urls import path
from ninja import NinjaAPI, Schema
from ninja.errors import AuthenticationError, HttpError

from accounts.models import User
from lucid import errors
from lucid.errors import DEFAULT_MESSAGES, STATUS, ApiError, ErrorCode

api = NinjaAPI(urls_namespace="errors-test")
errors.install(api)


class Body(Schema):
    name: str
    count: int


@api.post("/validate")
def validate(request, body: Body):
    return {"ok": True}


@api.get("/api-error")
def api_error(request):
    raise ApiError(ErrorCode.RATE_LIMITED, details={"retry_after_s": 30})


@api.get("/conflict")
def conflict(request):
    raise errors.version_conflict(7)


@api.get("/unauthenticated")
def unauthenticated(request):
    raise AuthenticationError()


@api.get("/http-error")
def http_error(request):
    raise HttpError(503, "down")


@api.get("/missing-row")
def missing_row(request):
    return User.objects.get(email="nobody@example.com")


@api.get("/denied")
def denied(request):
    raise PermissionDenied


@api.get("/boom")
def boom(request):
    raise RuntimeError("secret internals")


urlpatterns = [path("t/", api.urls)]
pytestmark = pytest.mark.urls(__name__)


def _error(response) -> dict:
    assert response["Content-Type"] == "application/json"
    return response.json()["error"]


def test_every_code_in_the_api_table_has_a_status_and_a_message():
    assert set(STATUS) == set(ErrorCode) == set(DEFAULT_MESSAGES)


def test_validation_errors_list_each_field():
    response = Client().post("/t/validate", {"count": "many"}, content_type="application/json")

    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "validation_error"
    assert {(f["field"], f["source"]) for f in error["details"]["fields"]} == {
        ("name", "body"),
        ("count", "body"),
    }


def test_a_body_that_is_not_json_is_a_validation_error():
    response = Client().post("/t/validate", "{nope", content_type="application/json")

    assert response.status_code == 400
    assert _error(response)["code"] == "validation_error"


def test_api_errors_keep_their_code_status_and_details():
    response = Client().get("/t/api-error")

    assert response.status_code == 429
    assert _error(response) == {
        "code": "rate_limited",
        "message": "Slow down a little, then try again.",
        "details": {"retry_after_s": 30},
    }


def test_version_conflict_carries_the_current_version():
    response = Client().get("/t/conflict")

    assert response.status_code == 409
    assert _error(response)["details"] == {"current_version": 7}


def test_ninja_auth_errors_are_unauthenticated():
    response = Client().get("/t/unauthenticated")

    assert response.status_code == 401
    assert _error(response)["code"] == "unauthenticated"


def test_plain_http_errors_keep_their_status():
    response = Client().get("/t/http-error")

    assert response.status_code == 503
    assert _error(response)["code"] == "llm_unavailable"


@pytest.mark.django_db
def test_a_missing_row_is_not_found_and_permission_denied_is_forbidden():
    assert _error(Client().get("/t/missing-row"))["code"] == "not_found"
    assert _error(Client().get("/t/denied"))["code"] == "forbidden"


def test_an_unexpected_error_is_logged_with_its_traceback_and_hidden_from_the_caller(log_lines):
    response = Client().get("/t/boom")

    assert response.status_code == 500
    error = _error(response)
    assert error["code"] == "internal_error"
    assert "secret internals" not in response.content.decode()
    [line] = [line for line in log_lines() if line["logger"] == "lucid.errors"]
    assert line["severity"] == "ERROR"
    assert "RuntimeError: secret internals" in line["stack_trace"]


@override_settings(ROOT_URLCONF="lucid.urls")
def test_unknown_urls_get_the_envelope_too():
    response = Client().get("/no/such/page")

    assert response.status_code == 404
    assert _error(response)["code"] == "not_found"
