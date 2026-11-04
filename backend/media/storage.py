"""Where picture files live (M4): behind one small interface.

- **Production:** a private Cloud Storage bucket in Frankfurt (`MEDIA_BUCKET`, made by WS5's
  bootstrap). Nothing in it is public: the app gets short-lived V4 signed URLs. They are signed
  through the IAM signBlob API as the runtime service account, with Application Default
  Credentials, so no key file exists anywhere (B11). The service account needs
  `roles/iam.serviceAccountTokenCreator` on itself and object access on the bucket.
- **Development and tests:** files under `PICTURE_ROOT`, served by `media.views.local_file` with
  URLs signed by an HMAC of the Django secret, so they expire the same way.

The Cloud Storage client loads on first use, never at import (B10).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from django.conf import settings
from django.utils.crypto import constant_time_compare, salted_hmac

logger = logging.getLogger("media.pictures")

_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.-]{0,511}$")
_LOCAL_SALT = "media.storage.local"
LOCAL_URL_PREFIX = "/media/"


@dataclass(frozen=True)
class SignedUrl:
    url: str
    expires_at: datetime


class PictureStorage(Protocol):
    def save(self, key: str, data: bytes, mime_type: str) -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None:
        """Removes the file. A missing file is not an error."""
        ...

    def url(self, key: str, ttl_s: int) -> SignedUrl:
        """A URL that reads the file until it expires."""
        ...


def check_key(key: str) -> str:
    if not _SAFE_KEY.match(key) or ".." in key or "//" in key:
        raise ValueError("Unsafe storage key")
    return key


class LocalStorage:
    """Files on disk, for development and tests. URLs point at `media.views.local_file` and are
    relative to the API's base URL; the views make them absolute."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Unsafe storage key")
        return path

    def save(self, key: str, data: bytes, mime_type: str) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.partial")
        partial.write_bytes(data)
        partial.replace(path)

    def load(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def url(self, key: str, ttl_s: int) -> SignedUrl:
        expires = int(time.time()) + ttl_s
        query = urlencode({"expires": expires, "signature": local_signature(key, expires)})
        return SignedUrl(
            f"{LOCAL_URL_PREFIX}{check_key(key)}?{query}", datetime.fromtimestamp(expires, UTC)
        )


def local_signature(key: str, expires: int) -> str:
    return salted_hmac(_LOCAL_SALT, f"{key}\n{expires}", algorithm="sha256").hexdigest()


def verify_local_signature(key: str, expires: str, signature: str) -> bool:
    """Whether a local URL is genuine and not expired."""
    if not expires.isdigit() or int(expires) < time.time():
        return False
    return constant_time_compare(local_signature(key, int(expires)), signature)


class GcsStorage:
    """A private Cloud Storage bucket. Pass `client` to test without Google Cloud."""

    def __init__(
        self, bucket: str, *, project: str = "", client: Any = None, credentials: Any = None
    ) -> None:
        self.bucket_name = bucket
        self.project = project
        self._client = client
        self._credentials = credentials
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        with self._lock:
            if self._client is None:
                import google.auth  # loads on first use (B10)
                from google.cloud import storage

                # Application Default Credentials: the runtime service account on Cloud Run.
                credentials, _ = google.auth.default(scopes=[_CLOUD_PLATFORM])
                self._credentials = credentials
                self._client = storage.Client(project=self.project or None, credentials=credentials)
            return self._client

    def _blob(self, key: str) -> Any:
        return self._get_client().bucket(self.bucket_name).blob(check_key(key))

    def save(self, key: str, data: bytes, mime_type: str) -> None:
        blob = self._blob(key)
        # Signed URLs are per viewer and short-lived, so no shared cache may keep the file.
        blob.cache_control = "private, max-age=3600"
        blob.upload_from_string(data, content_type=mime_type)

    def load(self, key: str) -> bytes:
        return self._blob(key).download_as_bytes()

    def delete(self, key: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self._blob(key).delete()
        except NotFound:
            pass

    def url(self, key: str, ttl_s: int) -> SignedUrl:
        blob = self._blob(key)
        email, token = self._signing_identity()
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_s)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=ttl_s),
            method="GET",
            service_account_email=email,
            access_token=token,
        )
        return SignedUrl(url, expires_at)

    def _signing_identity(self) -> tuple[str, str]:
        """The service account and a fresh access token, for signing through IAM (B11). On Cloud
        Run the account's email is only known after a refresh."""
        self._get_client()
        credentials = self._credentials
        with self._lock:
            email = getattr(credentials, "service_account_email", "") or ""
            if not credentials.valid or email in ("", "default"):
                from google.auth.transport.requests import Request

                credentials.refresh(Request())
            return credentials.service_account_email, credentials.token


@lru_cache(maxsize=4)
def _storage_for(bucket: str, root: str, project: str) -> PictureStorage:
    if bucket:
        return GcsStorage(bucket, project=project)
    return LocalStorage(root)


def get_storage() -> PictureStorage:
    """The storage the settings name: Cloud Storage when `MEDIA_BUCKET` is set, else local."""
    return _storage_for(settings.MEDIA_BUCKET, str(settings.PICTURE_ROOT), settings.GCP_PROJECT)


_url_cache: dict[tuple[object, str], SignedUrl] = {}
_url_lock = threading.Lock()
_URL_CACHE_SIZE = 4096


def signed_url(key: str, ttl_s: int | None = None) -> SignedUrl:
    """A signed URL for a stored picture, valid for `ttl_s`, by default `PICTURE_URL_TTL_S`.

    A URL is reused while more than half its life remains, so a list of scenes doesn't sign the
    same picture again on every load (signing in Cloud Storage is a call to IAM). Can block on
    the network: call it off the event loop.
    """
    storage = get_storage()
    ttl = settings.PICTURE_URL_TTL_S if ttl_s is None else ttl_s
    # One key is always signed for the same life (covers longer than story pictures), and a
    # cached URL is checked against the life asked for, so the TTL needn't be in the cache key.
    cache_key = (storage, key)
    with _url_lock:
        cached = _url_cache.get(cache_key)
    if cached is not None and (cached.expires_at - datetime.now(UTC)).total_seconds() > ttl / 2:
        return cached
    url = storage.url(key, ttl)
    with _url_lock:
        if len(_url_cache) >= _URL_CACHE_SIZE:
            _url_cache.clear()
        _url_cache[cache_key] = url
    return url


def signed_urls(keys: Iterable[str], ttl_s: int | None = None) -> dict[str, SignedUrl]:
    """Signed URLs for many pictures, signing the ones not cached at the same time, so a story
    with many pictures costs one round of IAM calls, not one after another."""
    keys = list(dict.fromkeys(keys))
    if len(keys) <= 1:
        return {key: signed_url(key, ttl_s) for key in keys}
    with ThreadPoolExecutor(max_workers=min(_SIGNING_THREADS, len(keys))) as pool:
        urls = pool.map(lambda key: signed_url(key, ttl_s), keys)
        return dict(zip(keys, urls, strict=True))


_SIGNING_THREADS = 8


def storage_key(story_id: object, image_id: object, mime_type: str) -> str:
    """Files are grouped by story, so a story's pictures can be found and deleted together."""
    return f"stories/{story_id}/{image_id}{extension_for(mime_type)}"


def extension_for(mime_type: str) -> str:
    return _EXTENSIONS.get(mime_type, ".bin")


_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def delete_quietly(key: str) -> None:
    """Removes a file that is no longer any picture's, logging instead of raising: left behind,
    it is still private and unreachable without a signed URL."""
    try:
        get_storage().delete(key)
    except Exception:
        logger.warning("A picture file couldn't be deleted", exc_info=True)
