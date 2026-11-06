"""`GET /v1/app/latest`: the newest build the deploy published, for the app to update (S12)."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from django.test import Client

from releases import service

SHA = "ab" * 32


@pytest.fixture
def release_files(settings, tmp_path):
    """A fresh local releases folder per test, as `PICTURE_ROOT/releases/`, and no cache."""
    settings.RELEASES_BUCKET = ""
    settings.MEDIA_BUCKET = ""
    settings.PICTURE_ROOT = str(tmp_path / "pictures")
    service.clear_caches()
    yield tmp_path / "pictures" / "releases"
    service.clear_caches()


def publish(folder, build=12, *, apk=b"fake apk bytes", manifest=None):
    """Writes what the deploy uploads: the APK, then the manifest that names it, with any of its
    fields replaced by `manifest`."""
    (folder / "android").mkdir(parents=True, exist_ok=True)
    (folder / "android" / f"lucid-saga-{build}.apk").write_bytes(apk)
    manifest = {
        "build": build,
        "version": "1.0.0",
        "apk": f"android/lucid-saga-{build}.apk",
        "size": len(apk),
        "sha256": SHA,
        "published_at": "2026-11-06T10:00:00Z",
    } | (manifest or {})
    (folder / "android" / "latest.json").write_text(json.dumps(manifest))


def test_the_latest_build_comes_with_a_download_url(release_files, player_client):
    publish(release_files, 12)

    response = player_client.get("/v1/app/latest", {"platform": "android"})

    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "android"
    assert body["build"] == 12
    assert body["version"] == "1.0.0"
    assert body["size"] == len(b"fake apk bytes")
    assert body["sha256"] == SHA
    assert body["published_at"].startswith("2026-11-06T10:00:00")
    expires = datetime.fromisoformat(body["expires_at"])
    assert timedelta(minutes=25) < expires - datetime.now(UTC) <= timedelta(minutes=30)
    # Local development serves the file like a picture, behind an expiring signature.
    url = urlsplit(body["url"])
    assert url.scheme == "http" and url.path == "/media/releases/android/lucid-saga-12.apk"
    download = Client().get(f"{url.path}?{url.query}")
    assert download.status_code == 200
    assert b"".join(download.streaming_content) == b"fake apk bytes"


def test_android_is_the_default_platform(release_files, player_client):
    publish(release_files, 3)

    assert player_client.get("/v1/app/latest").json()["build"] == 3


def test_nothing_published_is_a_404(release_files, player_client):
    response = player_client.get("/v1/app/latest", {"platform": "android"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_other_platforms_are_refused(release_files, player_client):
    publish(release_files, 12)

    response = player_client.get("/v1/app/latest", {"platform": "ios"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_it_needs_a_signed_in_player(release_files, db):
    publish(release_files, 12)

    response = Client().get("/v1/app/latest")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_a_new_build_shows_once_the_cache_has_expired(release_files, player_client, monkeypatch):
    publish(release_files, 12)
    assert player_client.get("/v1/app/latest").json()["build"] == 12

    publish(release_files, 13)
    assert player_client.get("/v1/app/latest").json()["build"] == 12  # read once a minute

    now = service.time.monotonic()
    monkeypatch.setattr(service.time, "monotonic", lambda: now + service.MANIFEST_CACHE_S + 1)
    assert player_client.get("/v1/app/latest").json()["build"] == 13


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"build": 0}, "build"),
        ({"build": "12"}, "build"),
        ({"build": True}, "build"),
        ({"apk": "android/lucid-saga-11.apk"}, "apk"),  # not the build it names
        ({"apk": "../stories/s1/a.png"}, "apk"),
        ({"apk": "stories/s1/a.png"}, "apk"),
        ({"version": ""}, "version"),
        ({"version": "1.0.0\n"}, "version"),
        ({"size": 0}, "size"),
        ({"sha256": "AB" * 32}, "sha256"),
        ({"sha256": "ab" * 31}, "sha256"),
    ],
)
def test_a_manifest_the_deploy_wouldnt_write_is_ignored(
    release_files, player_client, log_lines, fields, problem
):
    publish(release_files, 12, manifest=fields)

    response = player_client.get("/v1/app/latest")

    assert response.status_code == 404
    warnings = [line for line in log_lines() if line.get("release")]
    assert warnings[-1]["severity"] == "WARNING"
    assert warnings[-1]["release"] == {"platform": "android", "field": problem}


def test_a_manifest_that_isnt_json_is_ignored(release_files, player_client):
    (release_files / "android").mkdir(parents=True)
    (release_files / "android" / "latest.json").write_text("{not json")

    assert player_client.get("/v1/app/latest").status_code == 404


def test_storage_errors_are_logged_and_offer_no_update(
    release_files, player_client, log_lines, monkeypatch
):
    def unreadable(self, key):
        raise PermissionError("denied")

    monkeypatch.setattr(service.LocalStorage, "load", unreadable)

    assert player_client.get("/v1/app/latest").status_code == 404
    lines = [line for line in log_lines() if line.get("release")]
    assert lines[-1]["release"] == {"platform": "android", "error": "PermissionError"}


def test_a_missing_bucket_object_is_not_an_error(log_lines):
    from google.api_core.exceptions import NotFound

    class Bucket:
        def load(self, key):
            raise NotFound("no such object")

    assert service._read(Bucket(), "", "android") is None
    assert not [line for line in log_lines() if line.get("release")]


def test_download_urls_are_reused_while_fresh(release_files):
    publish(release_files, 12)
    release = service.latest("android")

    first = service.download_url(release)
    assert service.download_url(release) is first


def test_production_reads_the_releases_bucket(settings):
    settings.RELEASES_BUCKET = "playable-anime-releases"
    settings.GCP_PROJECT = "playable-anime"
    service._storage_for.cache_clear()
    try:
        storage, prefix = service.get_storage()
        assert isinstance(storage, service.GcsStorage)
        assert storage.bucket_name == "playable-anime-releases"
        assert prefix == ""
    finally:
        service._storage_for.cache_clear()


def test_the_api_reads_the_manifest_the_deploy_writes(tmp_path):
    """infra/deploy.sh upload-apk writes the manifest with infra/release_manifest.py."""
    script = Path(__file__).resolve().parents[3] / "infra" / "release_manifest.py"
    apk = tmp_path / "lucid-saga.apk"
    apk.write_bytes(b"an apk")
    out = tmp_path / "latest.json"

    subprocess.run(
        [sys.executable, "-I", str(script), str(out), str(apk), "android/lucid-saga-42.apk"]
        + ["42", "1.0.0"],
        check=True,
        timeout=30,
    )

    release = service.parse_manifest(out.read_bytes(), "android")
    assert release.build == 42
    assert release.version == "1.0.0"
    assert release.apk == "android/lucid-saga-42.apk"
    assert release.size == len(b"an apk")
    assert release.sha256 == hashlib.sha256(b"an apk").hexdigest()
    assert abs(release.published_at - datetime.now(UTC)) < timedelta(minutes=1)
