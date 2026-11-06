"""The newest build of the app that the deploy published (S12, T13, docs/DEPLOY.md).

The deploy uploads the Android APK to the private releases bucket (`RELEASES_BUCKET`) as
`android/lucid-saga-<build>.apk`, then writes `android/latest.json`, which names it:

    {"build": 12, "version": "1.0.0", "apk": "android/lucid-saga-12.apk", "size": 61234567,
     "sha256": "<64 hex digits>", "published_at": "2026-11-06T10:00:00Z"}

The manifest is written last, so it never names an APK that isn't there yet. Each instance reads
it at most once a minute. The app gets a short-lived signed URL for the APK, signed as the runtime
service account with no key file, like a picture's (M4, B11).

Without a bucket (development and tests) releases are local files under `PICTURE_ROOT/releases/`,
served by `media.views.local_file` behind the same kind of signed URL.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from django.conf import settings

from media.storage import GcsStorage, LocalStorage, PictureStorage, SignedUrl

logger = logging.getLogger("releases")

PLATFORMS = ("android",)
# How long one reading of the manifest is kept. A new build reaches every instance within it.
MANIFEST_CACHE_S = 60.0
# How long a download URL works. Cloud Storage checks it when the download starts, so a slow
# download that started in time finishes.
URL_TTL_S = 30 * 60

_LOCAL_PREFIX = "releases/"
_APK_KEY = re.compile(r"android/lucid-saga-([1-9][0-9]{0,9})\.apk")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,31}")


@dataclass(frozen=True)
class Release:
    platform: str
    # Android's versionCode, which grows with every deploy.
    build: int
    # The version name from pubspec.yaml, such as 1.0.0.
    version: str
    # The APK's key in the releases storage.
    apk: str
    size: int
    sha256: str
    published_at: datetime | None


class InvalidManifest(ValueError):
    pass


@lru_cache(maxsize=4)
def _storage_for(bucket: str, root: str, project: str) -> tuple[PictureStorage, str]:
    if bucket:
        return GcsStorage(bucket, project=project), ""
    return LocalStorage(root), _LOCAL_PREFIX


def get_storage() -> tuple[PictureStorage, str]:
    """The releases storage and the prefix of its keys: the releases bucket when
    `RELEASES_BUCKET` is set, else local files under `PICTURE_ROOT/releases/`."""
    return _storage_for(settings.RELEASES_BUCKET, str(settings.PICTURE_ROOT), settings.GCP_PROJECT)


_manifests: dict[tuple[object, str], tuple[float, Release | None]] = {}
_urls: dict[tuple[object, str], SignedUrl] = {}
_lock = threading.Lock()


def clear_caches() -> None:
    with _lock:
        _manifests.clear()
        _urls.clear()


def latest(platform: str) -> Release | None:
    """The newest published build for `platform`, or None when none is. A manifest that can't
    be read or makes no sense is logged and counts as none, so the app just doesn't offer an
    update. Blocks on the network: call it off the event loop."""
    if platform not in PLATFORMS:
        return None
    storage, prefix = get_storage()
    cache_key = (storage, platform)
    now = time.monotonic()
    with _lock:
        cached = _manifests.get(cache_key)
    if cached is not None and cached[0] > now:
        return cached[1]
    release = _read(storage, prefix, platform)
    with _lock:
        _manifests[cache_key] = (now + MANIFEST_CACHE_S, release)
    return release


def download_url(release: Release) -> SignedUrl:
    """A signed URL for the release's APK, reused while more than half its life remains, since
    signing in Cloud Storage is a call to IAM. Blocks on the network."""
    storage, prefix = get_storage()
    key = prefix + release.apk
    with _lock:
        cached = _urls.get((storage, key))
    if cached is not None and (cached.expires_at - datetime.now(UTC)).total_seconds() > (
        URL_TTL_S / 2
    ):
        return cached
    url = storage.url(key, URL_TTL_S)
    with _lock:
        _urls[(storage, key)] = url
    return url


def parse_manifest(raw: bytes, platform: str) -> Release:
    """Reads `latest.json`, refusing anything the deploy wouldn't write."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidManifest("not JSON") from exc
    if not isinstance(data, dict):
        raise InvalidManifest("not an object")
    build = data.get("build")
    if type(build) is not int or build < 1:
        raise InvalidManifest("build")
    apk = data.get("apk")
    match = _APK_KEY.fullmatch(apk) if isinstance(apk, str) else None
    if match is None or int(match.group(1)) != build or not apk.startswith(f"{platform}/"):
        raise InvalidManifest("apk")
    version = data.get("version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise InvalidManifest("version")
    size = data.get("size")
    if type(size) is not int or size < 1:
        raise InvalidManifest("size")
    sha256 = data.get("sha256")
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256):
        raise InvalidManifest("sha256")
    return Release(
        platform=platform,
        build=build,
        version=version,
        apk=apk,
        size=size,
        sha256=sha256,
        published_at=_timestamp(data.get("published_at")),
    )


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _read(storage: PictureStorage, prefix: str, platform: str) -> Release | None:
    try:
        raw = storage.load(f"{prefix}{platform}/latest.json")
    except Exception as exc:
        if not _is_missing(exc):
            logger.warning(
                "The latest release couldn't be read",
                extra={"release": {"platform": platform, "error": type(exc).__name__}},
            )
        return None
    try:
        return parse_manifest(raw, platform)
    except InvalidManifest as exc:
        logger.warning(
            "The latest release's manifest is invalid",
            extra={"release": {"platform": platform, "field": str(exc)}},
        )
        return None


def _is_missing(exc: Exception) -> bool:
    """Nothing published yet: no local file, or no object in the bucket."""
    if isinstance(exc, FileNotFoundError):
        return True
    from google.api_core.exceptions import NotFound  # loads on first use (B10)

    return isinstance(exc, NotFound)
