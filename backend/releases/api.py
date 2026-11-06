"""`GET /v1/app/latest`: the newest build of the app, so the app can update itself (S12).

The Android app from the GitHub release asks for it on start and when it comes back to the
foreground. When the build here is newer than its own, it offers the update, downloads the APK
from `url`, checks its size and SHA-256, and hands it to Android's installer. A build for the Play
Store never asks: Google Play updates it.
"""

import asyncio
from datetime import datetime
from typing import Literal

from django.http import HttpRequest
from ninja import Router, Schema

from lucid.errors import ApiError, ErrorCode
from media.api import absolute_url
from releases import service

app_router = Router(tags=["app"])


class AppReleaseOut(Schema):
    platform: Literal["android"]
    build: int
    version: str
    size: int
    sha256: str
    # Downloads the APK until `expires_at`. Ask again for a fresh one after that.
    url: str
    expires_at: datetime
    published_at: datetime | None = None


@app_router.get("/latest", response=AppReleaseOut)
async def latest_release(
    request: HttpRequest, platform: Literal["android"] = "android"
) -> AppReleaseOut:
    """The newest published build, with a short-lived download URL. 404 until one is published."""
    release = await asyncio.to_thread(service.latest, platform)
    if release is None:
        raise ApiError(ErrorCode.NOT_FOUND, "No build of the app has been published yet.")
    url = await asyncio.to_thread(service.download_url, release)
    return AppReleaseOut(
        platform="android",
        build=release.build,
        version=release.version,
        size=release.size,
        sha256=release.sha256,
        url=absolute_url(request, url.url),
        expires_at=url.expires_at,
        published_at=release.published_at,
    )
