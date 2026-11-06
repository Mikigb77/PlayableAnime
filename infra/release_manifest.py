"""Writes the release manifest, android/latest.json, that the API reads to offer the installed
app its update (S12, backend/releases/service.py). infra/deploy.sh upload-apk runs it, then
uploads the manifest after the APK, so it never names an APK that isn't there.

Usage: python3 -I infra/release_manifest.py OUT APK KEY BUILD VERSION
"""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime


def manifest(apk: str, key: str, build: int, version: str) -> dict[str, object]:
    digest = hashlib.sha256()
    with open(apk, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "build": build,
        "version": version,
        "apk": key,
        "size": os.path.getsize(apk),
        "sha256": digest.hexdigest(),
        "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main(argv: list[str]) -> None:
    if len(argv) != 5:
        sys.exit(__doc__)
    out, apk, key, build, version = argv
    with open(out, "w") as file:
        json.dump(manifest(apk, key, int(build), version), file)


if __name__ == "__main__":
    main(sys.argv[1:])
