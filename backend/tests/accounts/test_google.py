"""The real Google ID token check, against a key pair made here instead of Google's (T8)."""

import time
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt
from google.auth import jwt as google_jwt

from accounts import google

CLIENT_ID = "web-client.apps.googleusercontent.com"


def _key_pair(kid: str) -> tuple[crypt.RSASigner, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    signer = crypt.RSASigner.from_string(private_pem, key_id=kid)
    return signer, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture(scope="module")
def keys():
    return {kid: _key_pair(kid) for kid in ("k1", "k2")}


@pytest.fixture
def certs(keys, monkeypatch, settings):
    """Google's certificate endpoint, serving whichever of our test keys `published` names."""
    settings.GOOGLE_OAUTH_CLIENT_IDS = [CLIENT_ID, "android-client"]
    published = {"k1"}
    fetches = []

    def fetch():
        fetches.append(1)
        return {kid: keys[kid][1] for kid in published}, 3600.0

    monkeypatch.setattr(google, "fetch_certs", fetch)
    google._cache.clear()
    yield published, fetches
    google._cache.clear()


def _token(keys, kid="k1", **claims) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234567890",
        "email": "Kaede@Gmail.com",
        "email_verified": True,
        "name": "Kaede Mori",
        "iat": now,
        "exp": now + 3600,
    } | claims
    return google_jwt.encode(keys[kid][0], payload).decode()


def test_a_valid_token_gives_the_identity(keys, certs):
    identity = google.verify_id_token(_token(keys))

    assert identity == google.GoogleIdentity(
        sub="1234567890", email="kaede@gmail.com", email_verified=True, name="Kaede Mori"
    )


def test_any_of_our_clients_is_an_accepted_audience(keys, certs):
    assert google.verify_id_token(_token(keys, aud="android-client")).sub == "1234567890"


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-elses-client"},
        {"iss": "https://evil.example.com"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"sub": ""},
        {"email": None},
    ],
)
def test_tokens_that_arent_for_us_are_refused(keys, certs, claims):
    with pytest.raises(google.GoogleTokenError):
        google.verify_id_token(_token(keys, **claims))


def test_a_token_signed_by_another_key_is_refused(keys, certs):
    forged = _token(keys, kid="k2")
    header, payload, _ = forged.split(".")
    _, _, signature = _token(keys, kid="k1").split(".")

    with pytest.raises(google.GoogleTokenError):
        google.verify_id_token(f"{header}.{payload}.{signature}")


def test_garbage_is_refused(certs):
    with pytest.raises(google.GoogleTokenError):
        google.verify_id_token("not.a.token")


def test_an_unverified_email_is_reported_as_such(keys, certs):
    assert not google.verify_id_token(_token(keys, email_verified=False)).email_verified
    assert google.verify_id_token(_token(keys, email_verified="true")).email_verified


def test_certificates_are_cached_and_refetched_when_google_rotates_keys(keys, certs, monkeypatch):
    published, fetches = certs
    google.verify_id_token(_token(keys))
    google.verify_id_token(_token(keys))
    assert len(fetches) == 1

    published.add("k2")
    monkeypatch.setattr(google, "_MIN_REFETCH_S", 0)
    assert google.verify_id_token(_token(keys, kid="k2")).sub == "1234567890"
    assert len(fetches) == 2


def test_an_unknown_key_refetches_at_most_once_a_minute(keys, certs):
    _, fetches = certs
    google.verify_id_token(_token(keys))

    for _ in range(3):
        with pytest.raises(google.GoogleTokenError):
            google.verify_id_token(_token(keys, kid="k2"))

    assert len(fetches) == 1


def test_google_being_unreachable_is_unavailable_not_invalid(keys, monkeypatch, settings):
    settings.GOOGLE_OAUTH_CLIENT_IDS = [CLIENT_ID]
    google._cache.clear()

    def down():
        raise OSError("network is unreachable")

    monkeypatch.setattr(google, "fetch_certs", down)

    with pytest.raises(google.GoogleUnavailable):
        google.verify_id_token(_token(keys))


def test_sign_in_is_off_without_client_ids(keys, settings):
    settings.GOOGLE_OAUTH_CLIENT_IDS = []

    with pytest.raises(google.GoogleUnavailable):
        google.verify_id_token(_token(keys))
