"""Private storage with expiring signed URLs: local files in development, Cloud Storage in
production, signed through IAM with no key file (M4, B11)."""

import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client

from media import storage
from media.storage import GcsStorage, LocalStorage, get_storage, signed_url, storage_key


def test_local_files_are_saved_read_and_deleted(picture_files):
    local = LocalStorage(picture_files)

    local.save("stories/s1/a.png", b"png", "image/png")

    assert local.load("stories/s1/a.png") == b"png"
    local.delete("stories/s1/a.png")
    local.delete("stories/s1/a.png")  # already gone: not an error
    assert not local.exists("stories/s1/a.png")


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs.png", "a//b.png", "a/../../b", "", "é.png"])
def test_unsafe_keys_are_refused(picture_files, key):
    with pytest.raises(ValueError):
        LocalStorage(picture_files).save(key, b"x", "image/png")


def test_keys_group_pictures_by_story():
    assert storage_key("s1", "i1", "image/png") == "stories/s1/i1.png"
    assert storage_key("s1", "i1", "image/jpeg") == "stories/s1/i1.jpg"


def test_local_urls_are_signed_and_expire(picture_files, monkeypatch):
    local = LocalStorage(picture_files)
    url = local.url("stories/s1/a.png", 60)
    query = parse_qs(urlsplit(url.url).query)
    expires, signature = query["expires"][0], query["signature"][0]

    assert url.url.startswith("/media/stories/s1/a.png?")
    assert storage.verify_local_signature("stories/s1/a.png", expires, signature)
    assert not storage.verify_local_signature("stories/s1/b.png", expires, signature)
    assert not storage.verify_local_signature("stories/s1/a.png", expires, "0" * 64)
    assert not storage.verify_local_signature("stories/s1/a.png", "soon", signature)
    monkeypatch.setattr(time, "time", lambda: int(expires) + 1)
    assert not storage.verify_local_signature("stories/s1/a.png", expires, signature)


def test_the_local_file_view_serves_only_signed_unexpired_urls(picture_files, settings):
    get_storage().save("stories/s1/a.png", b"\x89PNG", "image/png")
    url = signed_url("stories/s1/a.png").url
    client = Client()

    response = client.get(url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"\x89PNG"
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, max-age=3600"

    assert client.get(url.replace("signature=", "signature=0")).status_code == 404
    assert client.get("/media/stories/s1/a.png").status_code == 404
    get_storage().delete("stories/s1/a.png")
    missing = client.get(url)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_signed_urls_are_reused_until_half_their_life_is_gone(settings, monkeypatch):
    settings.PICTURE_URL_TTL_S = 3600
    signed = []
    local = get_storage()
    real_url = local.url
    monkeypatch.setattr(local, "url", lambda key, ttl: signed.append(key) or real_url(key, ttl))

    first = signed_url("stories/s1/a.png")
    assert signed_url("stories/s1/a.png") is first
    assert len(signed) == 1

    storage._url_cache[(local, "stories/s1/a.png")] = storage.SignedUrl(
        first.url, datetime.now(UTC) + timedelta(minutes=10)
    )
    signed_url("stories/s1/a.png")
    assert len(signed) == 2


def test_a_bucket_setting_picks_cloud_storage_without_loading_its_client(settings):
    settings.MEDIA_BUCKET = "lucid-pictures"
    sys.modules.pop("google.cloud.storage", None)

    chosen = get_storage()

    assert isinstance(chosen, GcsStorage)
    assert chosen.bucket_name == "lucid-pictures"
    assert "google.cloud.storage" not in sys.modules  # loaded on first use (B10)


class FakeCredentials:
    def __init__(self) -> None:
        self.valid = False
        self.token = None
        self.service_account_email = "default"
        self.refreshes = 0

    def refresh(self, request) -> None:
        self.refreshes += 1
        self.valid = True
        self.token = "access-token"
        self.service_account_email = "playable-anime-api@playable-anime.iam.gserviceaccount.com"


class FakeBlob:
    def __init__(self, bucket, name) -> None:
        self.bucket, self.name = bucket, name
        self.cache_control = None

    def upload_from_string(self, data, content_type) -> None:
        self.bucket.files[self.name] = (data, content_type, self.cache_control)

    def download_as_bytes(self) -> bytes:
        return self.bucket.files[self.name][0]

    def delete(self) -> None:
        from google.api_core.exceptions import NotFound

        if self.name not in self.bucket.files:
            raise NotFound("gone")
        del self.bucket.files[self.name]

    def generate_signed_url(self, **kwargs) -> str:
        self.bucket.signed.append(kwargs)
        return f"https://storage.googleapis.com/{self.bucket.name}/{self.name}?X-Goog-Signature=s"


class FakeBucket:
    def __init__(self, name) -> None:
        self.name = name
        self.files: dict = {}
        self.signed: list = []

    def blob(self, name) -> FakeBlob:
        return FakeBlob(self, name)


class FakeClient:
    def __init__(self) -> None:
        self._credentials = FakeCredentials()
        self.buckets: dict = {}

    def bucket(self, name) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket(name))


def test_cloud_storage_keeps_files_private_and_signs_urls_through_iam():
    client = FakeClient()
    gcs = GcsStorage("lucid-pictures", client=client)

    gcs.save("stories/s1/a.png", b"png", "image/png")
    url = gcs.url("stories/s1/a.png", 900)
    gcs.url("stories/s1/a.png", 900)

    bucket = client.buckets["lucid-pictures"]
    assert bucket.files["stories/s1/a.png"] == (b"png", "image/png", "private, max-age=3600")
    assert gcs.load("stories/s1/a.png") == b"png"
    assert url.url.startswith("https://storage.googleapis.com/lucid-pictures/stories/s1/a.png?")
    assert timedelta(seconds=890) < url.expires_at - datetime.now(UTC) <= timedelta(seconds=900)
    signed = bucket.signed[0]
    assert signed["version"] == "v4"
    assert signed["method"] == "GET"
    assert signed["expiration"] == timedelta(seconds=900)
    # No key file: IAM signs as the runtime service account with an ADC token (B11).
    assert signed["service_account_email"].startswith("playable-anime-api@")
    assert signed["access_token"] == "access-token"
    assert client._credentials.refreshes == 1  # refreshed only while the token is invalid

    gcs.delete("stories/s1/a.png")
    gcs.delete("stories/s1/a.png")  # already gone: not an error
    assert bucket.files == {}
