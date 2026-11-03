"""`/v1/auth/*` and the bearer auth on every other endpoint (T8, F8, K7), with Google's token
check replaced by a stub that maps test tokens to identities."""

from datetime import date, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from accounts import google, throttle, tokens
from accounts.google import GoogleIdentity, GoogleTokenError
from accounts.models import AuthSession, Role, Throttle, User
from lucid.errors import ApiError
from tests.conftest import ADULT_BIRTH_DATE, PASSWORD, auth_headers

pytestmark = pytest.mark.django_db

OWNER = "mikigb77@gmail.com"


@pytest.fixture(autouse=True)
def owner_setting(settings):
    settings.OWNER_EMAILS = [OWNER]
    settings.MIN_SIGNUP_AGE = 13


@pytest.fixture
def google_tokens(monkeypatch):
    """Stands in for Google: `add(...)` makes a test token for an identity."""
    identities: dict[str, GoogleIdentity] = {}

    def verify(token: str) -> GoogleIdentity:
        if token not in identities:
            raise GoogleTokenError("unknown test token")
        return identities[token]

    monkeypatch.setattr(google, "verify_id_token", verify)

    def add(sub="g-1", email="kaede@gmail.com", verified=True, name="Kaede Mori") -> str:
        token = f"token-{len(identities)}"
        identities[token] = GoogleIdentity(sub, email, verified, name)
        return token

    return add


def _post(path: str, body: dict, client: Client | None = None, **headers):
    return (client or Client()).post(
        f"/v1/auth/{path}", body, content_type="application/json", headers=headers
    )


def _google(token: str, birth_date: date | None = None):
    body = {"id_token": token}
    if birth_date:
        body["birth_date"] = birth_date.isoformat()
    return _post("google", body)


def _register(email="ren@example.com", password=PASSWORD, **fields):
    body = {
        "email": email,
        "password": password,
        "display_name": "Ren",
        "birth_date": ADULT_BIRTH_DATE.isoformat(),
    } | fields
    return _post("register", body)


def _me(access_token: str):
    return Client().get("/v1/me", headers={"Authorization": f"Bearer {access_token}"})


def _error(response) -> dict:
    return response.json()["error"]


# Google


def test_a_new_google_account_needs_a_birth_date_first(google_tokens):
    response = _google(google_tokens())

    assert response.status_code == 400
    assert _error(response)["code"] == "birth_date_required"
    assert not User.objects.exists()


def test_a_new_google_account_is_created_verified_and_signed_in(google_tokens):
    response = _google(google_tokens(), ADULT_BIRTH_DATE)

    assert response.status_code == 200, response.content
    session = response.json()
    assert session["expires_in"] == 900
    assert session["user"] == {
        "id": session["user"]["id"],
        "email": "kaede@gmail.com",
        "display_name": "Kaede Mori",
        "role": "player",
        "max_rating": "mature",
        "content_prefs": {"gore": "medium", "romance": True, "dark_themes": True},
        "credits": {"balance_cents": 0, "unlimited": False},
    }
    user = User.objects.get()
    assert (user.google_sub, user.email_verified, user.birth_date) == (
        "g-1",
        True,
        ADULT_BIRTH_DATE,
    )
    assert not user.has_usable_password()
    assert _me(session["access_token"]).json()["id"] == str(user.pk)


def test_a_returning_google_account_signs_in_without_a_birth_date(google_tokens):
    token = google_tokens()
    first = _google(token, ADULT_BIRTH_DATE).json()

    again = _google(token)

    assert again.status_code == 200
    assert again.json()["user"]["id"] == first["user"]["id"]
    assert User.objects.count() == 1
    assert AuthSession.objects.count() == 2


def test_an_account_without_a_birth_date_is_asked_for_one_at_google_sign_in(google_tokens):
    User.objects.create_user("kaede@gmail.com", google_sub="g-1", email_verified=True)
    token = google_tokens()

    assert _error(_google(token))["code"] == "birth_date_required"
    assert _google(token, ADULT_BIRTH_DATE).status_code == 200
    assert User.objects.get().birth_date == ADULT_BIRTH_DATE


def test_a_young_teen_gets_teen_only_and_a_child_cant_sign_up(google_tokens):
    today = date.today()
    fifteen = today.replace(year=today.year - 15)
    ten = today.replace(year=today.year - 10)

    child = _google(google_tokens(sub="g-child", email="child@gmail.com"), ten)
    teen = _google(google_tokens(sub="g-teen", email="teen@gmail.com"), fifteen)

    assert child.status_code == 400
    assert _error(child)["details"]["fields"][0]["type"] == "too_young"
    assert teen.json()["user"]["max_rating"] == "teen"
    assert list(User.objects.values_list("email", flat=True)) == ["teen@gmail.com"]


def test_an_unverified_google_email_cant_create_or_claim_an_account(google_tokens, make_user):
    make_user("kaede@gmail.com")

    response = _google(google_tokens(verified=False), ADULT_BIRTH_DATE)

    assert response.status_code == 403
    assert User.objects.get().google_sub is None


def test_a_bad_google_token_is_unauthenticated(google_tokens):
    response = _google("forged")

    assert response.status_code == 401
    assert _error(response)["code"] == "unauthenticated"


def test_google_sign_in_off_or_down_is_a_retryable_503(settings, log_lines):
    """Not a 401: the app tells "try again soon" apart from a rejected sign-in."""
    settings.GOOGLE_OAUTH_CLIENT_IDS = []

    response = _google("anything", ADULT_BIRTH_DATE)

    assert response.status_code == 503
    assert _error(response)["code"] == "sign_in_unavailable"
    assert any(line["severity"] == "ERROR" for line in log_lines())


def test_google_takes_over_an_unverified_email_account_and_drops_its_password(
    google_tokens, make_user
):
    """Someone may have signed up with this email before its owner did. Google vouches for the
    owner, so the password (which nobody verified) stops working and its devices are signed out."""
    squatter = make_user("kaede@gmail.com")
    squatter_headers = auth_headers(squatter)

    response = _google(google_tokens(), ADULT_BIRTH_DATE)

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(squatter.pk)
    user = User.objects.get()
    assert (user.google_sub, user.email_verified) == ("g-1", True)
    assert not user.has_usable_password()
    assert Client().get("/v1/me", headers=squatter_headers).status_code == 401
    login = _post("login", {"email": "kaede@gmail.com", "password": PASSWORD})
    assert login.status_code == 401


def test_an_account_tied_to_another_google_account_is_never_moved(google_tokens):
    _google(google_tokens(sub="g-old"), ADULT_BIRTH_DATE)

    response = _google(google_tokens(sub="g-new"), ADULT_BIRTH_DATE)

    assert response.status_code == 403
    assert User.objects.get().google_sub == "g-old"


# The owner role (K7)


def test_the_owner_email_gets_the_owner_role_and_admin_access_through_google(google_tokens):
    response = _google(google_tokens(email=OWNER), ADULT_BIRTH_DATE)

    user = response.json()["user"]
    assert (user["role"], user["credits"]["unlimited"]) == ("owner", True)
    owner = User.objects.get()
    assert owner.is_owner and owner.is_staff and owner.is_superuser


def test_the_owner_email_gets_no_owner_role_through_a_password():
    response = _register(email=OWNER)

    assert response.json()["user"]["role"] == "player"
    assert not User.objects.get().is_staff


def test_an_owner_no_longer_listed_loses_the_role_at_the_next_google_sign_in(
    google_tokens, settings
):
    token = google_tokens(email=OWNER)
    _google(token, ADULT_BIRTH_DATE)
    settings.OWNER_EMAILS = []

    response = _google(token)

    assert response.json()["user"]["role"] == "player"
    user = User.objects.get()
    assert (user.role, user.is_staff, user.is_superuser) == (Role.PLAYER, False, False)


def test_a_disabled_account_cant_sign_in_with_google(google_tokens):
    token = google_tokens()
    _google(token, ADULT_BIRTH_DATE)
    User.objects.update(is_active=False)

    assert _google(token).status_code == 403


# Email and password


def test_register_creates_an_unverified_player_and_signs_in():
    response = _register(email=" Ren@Example.COM ")

    assert response.status_code == 200, response.content
    session = response.json()
    assert session["user"]["email"] == "ren@example.com"
    assert session["user"]["display_name"] == "Ren"
    user = User.objects.get()
    assert (user.email_verified, user.role, user.birth_date) == (False, "player", ADULT_BIRTH_DATE)
    assert user.check_password(PASSWORD)
    assert _me(session["access_token"]).status_code == 200


@pytest.mark.parametrize(
    ("fields", "field", "error_type"),
    [
        ({"email": "not-an-email"}, "email", "invalid_email"),
        ({"password": "short"}, "password", "password_too_short"),
        ({"password": "ren@example.com"}, "password", "password_too_similar"),
        ({"password": "12345678901"}, "password", "password_entirely_numeric"),
        ({"display_name": "   "}, "display_name", "missing"),
        ({"birth_date": "2030-01-01"}, "birth_date", "future"),
        ({"birth_date": None}, "birth_date", None),
    ],
)
def test_register_explains_what_is_wrong(fields, field, error_type):
    response = _register(**fields)

    assert response.status_code == 400
    error = _error(response)
    assert error["code"] == "validation_error"
    assert field in [f["field"] for f in error["details"]["fields"]]
    if error_type:
        assert error_type in [f["type"] for f in error["details"]["fields"]]
    assert not User.objects.exists()


def test_register_refuses_an_email_that_is_taken_whatever_its_case(make_user):
    make_user("ren@example.com")

    response = _register(email="REN@example.com")

    assert response.status_code == 400
    assert _error(response)["details"]["fields"][0]["type"] == "email_taken"


def test_register_is_limited_per_address():
    for i in range(throttle.REGISTRATIONS_PER_IP.max_hits):
        assert _register(email=f"p{i}@example.com").status_code == 200

    response = _register(email="one-more@example.com")

    assert response.status_code == 429
    assert _error(response)["code"] == "rate_limited"
    assert 0 < _error(response)["details"]["retry_after_s"] <= 3600


def test_sign_ups_that_fail_validation_dont_use_up_the_limit():
    """Many players can share one carrier address, so only accounts made count."""
    for _ in range(throttle.REGISTRATIONS_PER_IP.max_hits + 5):
        assert _register(password="short").status_code == 400

    assert _register().status_code == 200


def test_login_with_the_right_password(make_user):
    user = make_user("ren@example.com")

    response = _post("login", {"email": "REN@example.com", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.pk)
    user.refresh_from_db()
    assert user.last_login is not None


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(make_user):
    make_user("ren@example.com")

    wrong = _post("login", {"email": "ren@example.com", "password": "wrong password"})
    unknown = _post("login", {"email": "nobody@example.com", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert _error(wrong) == _error(unknown)
    assert _error(wrong)["message"] == "Wrong email or password."


def test_a_google_only_account_cant_log_in_with_a_password(google_tokens):
    _google(google_tokens(), ADULT_BIRTH_DATE)

    assert _post("login", {"email": "kaede@gmail.com", "password": ""}).status_code == 400
    assert _post("login", {"email": "kaede@gmail.com", "password": "x"}).status_code == 401


def test_repeated_wrong_passwords_lock_the_email_for_a_while(make_user):
    make_user("ren@example.com")
    wrong = {"email": "ren@example.com", "password": "wrong password"}
    for _ in range(throttle.LOGIN_FAILURES_PER_EMAIL.max_hits):
        assert _post("login", wrong).status_code == 401

    locked = _post("login", {"email": "ren@example.com", "password": PASSWORD})

    assert locked.status_code == 429
    assert 0 < _error(locked)["details"]["retry_after_s"] <= 15 * 60
    # The window passes.
    Throttle.objects.update(window_started_at=timezone.now() - timedelta(hours=1))
    assert _post("login", {"email": "ren@example.com", "password": PASSWORD}).status_code == 200


def test_a_successful_login_clears_the_emails_failures(make_user):
    make_user("ren@example.com")
    limit = throttle.LOGIN_FAILURES_PER_EMAIL
    for _ in range(limit.max_hits - 1):
        _post("login", {"email": "ren@example.com", "password": "wrong password"})

    assert _post("login", {"email": "ren@example.com", "password": PASSWORD}).status_code == 200
    assert not Throttle.objects.filter(hits__gte=limit.max_hits).exists()
    assert _post("login", {"email": "ren@example.com", "password": "nope"}).status_code == 401


def test_a_burst_of_parallel_guesses_is_cut_off_at_the_limit():
    """Each attempt is counted before its password is checked, so attempts racing each other
    can't all see a count under the limit."""
    limit = throttle.LOGIN_FAILURES_PER_EMAIL
    for _ in range(limit.max_hits):
        throttle.take((limit, "ren@example.com"))

    with pytest.raises(ApiError) as raised:
        throttle.take((limit, "ren@example.com"))
    assert raised.value.code == "rate_limited"


def test_a_right_password_doesnt_count_against_a_shared_address(make_user):
    make_user("ren@example.com")
    for _ in range(throttle.LOGIN_FAILURES_PER_IP.max_hits + 5):
        assert _post("login", {"email": "ren@example.com", "password": PASSWORD}).status_code == 200


def test_every_login_runs_the_hasher_once_whatever_the_case(make_user, google_tokens, monkeypatch):
    """No timing tells an unknown email, a Google-only account and a wrong password apart."""
    from django.contrib.auth.hashers import check_password as real_check
    from django.contrib.auth.hashers import make_password as real_make

    from accounts import services

    runs = []
    monkeypatch.setattr(services, "make_password", lambda p: runs.append(1) or real_make(p))
    monkeypatch.setattr(
        "django.contrib.auth.base_user.check_password",
        lambda *a, **k: runs.append(1) or real_check(*a, **k),
    )
    make_user("ren@example.com")
    _google(google_tokens(), ADULT_BIRTH_DATE)

    for email in ("nobody@example.com", "kaede@gmail.com", "ren@example.com"):
        runs.clear()
        _post("login", {"email": email, "password": "wrong password"})
        assert runs == [1], email


def test_one_address_guessing_across_many_emails_is_limited(settings):
    settings.TRUSTED_PROXY_HOPS = 1
    limit = throttle.LOGIN_FAILURES_PER_IP
    for _ in range(limit.max_hits):
        throttle.take((limit, "203.0.113.9"))

    response = _post(
        "login",
        {"email": "fresh@example.com", "password": "x"},
        # Whatever the caller puts first, Google's front end appends the address it saw.
        **{"X-Forwarded-For": "198.51.100.1, 203.0.113.9"},
    )

    assert response.status_code == 429


def test_the_client_address_is_the_one_the_trusted_proxy_saw(rf, settings):
    settings.TRUSTED_PROXY_HOPS = 1
    request = rf.get("/", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})
    assert throttle.client_ip(request) == "203.0.113.9"
    settings.TRUSTED_PROXY_HOPS = 2
    assert throttle.client_ip(request) == "6.6.6.6"
    assert throttle.client_ip(rf.get("/")) == "127.0.0.1"


def test_throttle_keys_never_hold_the_email_or_address():
    throttle.take((throttle.LOGIN_FAILURES_PER_EMAIL, "ren@example.com"))

    [row] = Throttle.objects.all()
    assert "ren" not in row.key and len(row.key) == 64


# Refresh and logout


def test_refresh_rotates_and_returns_a_working_access_token(make_user):
    make_user("ren@example.com")
    first = _post("login", {"email": "ren@example.com", "password": PASSWORD}).json()

    second = _post("refresh", {"refresh_token": first["refresh_token"]})

    assert second.status_code == 200
    assert second.json()["refresh_token"] != first["refresh_token"]
    assert _me(second.json()["access_token"]).status_code == 200


def test_refresh_with_an_unknown_token_is_unauthenticated():
    response = _post("refresh", {"refresh_token": "nope"})

    assert response.status_code == 401
    assert _error(response)["code"] == "unauthenticated"


def test_logout_signs_the_device_out_at_once(make_user):
    make_user("ren@example.com")
    session = _post("login", {"email": "ren@example.com", "password": PASSWORD}).json()

    response = _post("logout", {"refresh_token": session["refresh_token"]})

    assert response.status_code == 204
    assert _me(session["access_token"]).status_code == 401
    assert _post("refresh", {"refresh_token": session["refresh_token"]}).status_code == 401
    assert _post("logout", {"refresh_token": session["refresh_token"]}).status_code == 204


# The bearer auth on every other endpoint


@pytest.mark.parametrize(
    "header",
    [None, "Bearer", "Bearer not-a-token", "Basic dXNlcjpwYXNz", "Token abc"],
)
def test_requests_without_a_valid_access_token_are_unauthenticated(header):
    headers = {"Authorization": header} if header else {}

    response = Client().get("/v1/me", headers=headers)

    assert response.status_code == 401
    assert _error(response) == {
        "code": "unauthenticated",
        "message": "Sign in to continue.",
        "details": {},
    }


def test_an_expired_access_token_is_unauthenticated(player, monkeypatch):
    headers = auth_headers(player)
    monkeypatch.setattr(tokens, "ACCESS_TOKEN_TTL_S", -1)

    assert Client().get("/v1/me", headers=headers).status_code == 401


def test_a_disabled_or_deleted_account_is_signed_out_at_once(player, make_user):
    headers = auth_headers(player)
    other = make_user("other@example.com")
    other_headers = auth_headers(other)
    User.objects.filter(pk=player.pk).update(is_active=False)
    other.delete()

    assert Client().get("/v1/me", headers=headers).status_code == 401
    assert Client().get("/v1/me", headers=other_headers).status_code == 401


def test_health_and_the_auth_endpoints_need_no_token():
    assert Client().get("/health").status_code == 200
    assert _post("refresh", {"refresh_token": "x"}).status_code == 401  # reached the view
    assert _post("logout", {"refresh_token": "x"}).status_code == 204


def test_signed_in_requests_log_the_user_id_and_never_a_token(player, log_lines):
    headers = auth_headers(player)

    Client().get("/v1/me", headers=headers)

    [line] = [line for line in log_lines() if line["logger"] == "lucid.request"]
    assert line["user_id"] == str(player.pk)
    assert headers["Authorization"].split()[1] not in str(log_lines())


def test_sign_in_logs_the_user_id_and_never_the_tokens(make_user, log_lines):
    user = make_user("ren@example.com")

    session = _post("login", {"email": "ren@example.com", "password": PASSWORD}).json()

    [line] = [line for line in log_lines() if line["logger"] == "lucid.request"]
    assert line["user_id"] == str(user.pk)
    text = str(log_lines())
    assert session["access_token"] not in text
    assert session["refresh_token"] not in text
    assert PASSWORD not in text
    assert "ren@example.com" not in text
