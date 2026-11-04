#!/usr/bin/env bash
# Publishes the Android app as the repository's latest GitHub release, with the APK as its asset
# lucid-saga.apk, so the README's link (releases/latest/download/lucid-saga.apk) always serves the
# newest build. Runs in the deploy workflow once the API is deployed, with GH_TOKEN set.
#
# Usage: infra/publish-apk.sh APK
#
# Environment:
#   GITHUB_REPOSITORY, GITHUB_SHA  Set by GitHub Actions.
#   BUILD_NUMBER                   The APK's versionCode. The release is tagged build-<number>.
#   VERSION_NAME                   The APK's version name, such as 1.0.0.
#   SIGNING                        release or debug, from infra/build-apk.sh.
#   SIGNING_SHA1                   The signing certificate's SHA-1, from infra/build-apk.sh.
#
# Re-running the same workflow run replaces the asset of the release it made. Only the newest build
# is marked as the latest release.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/lib.sh
. "$HERE/lib.sh"
# shellcheck source=infra/config.sh
. "$HERE/config.sh"

apk="${1:-}"
if [ -z "$apk" ] || [ ! -f "$apk" ]; then
  die "usage: infra/publish-apk.sh APK (an existing file)"
fi
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
sha="${GITHUB_SHA:?GITHUB_SHA is not set}"
build_number="${BUILD_NUMBER:?BUILD_NUMBER is not set}"
case "$build_number" in
  '' | *[!0-9]*) die "BUILD_NUMBER must be a whole number" ;;
esac
version_name="${VERSION_NAME:-}"
signing="${SIGNING:?SIGNING is not set}"
sha1="${SIGNING_SHA1:-}"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lucid-release.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

tag="build-$build_number"
title="Lucid Saga ${version_name:+$version_name }(build $build_number)"
# The asset takes the file's name.
asset="$TMP_DIR/$APK_ASSET"
cp "$apk" "$asset"

notes="$TMP_DIR/notes.md"
cat >"$notes" <<EOF
Lucid Saga for Android, build $build_number, from commit $sha.

Download **$APK_ASSET** below and open it on an Android phone or emulator. Android asks once to
allow installs from the browser or the Files app. The app talks to $API_URL.

EOF
if [ "$signing" = release ]; then
  cat >>"$notes" <<EOF
Signed with the release key${sha1:+, SHA-1 $sha1}, so it installs over earlier builds.
EOF
else
  cat >>"$notes" <<EOF
**Signed with a throwaway debug key**, because the repository has no release keystore yet
(docs/DEPLOY.md, "One-time setup"). Google sign-in won't work in it, and the next build won't
install over it: uninstall it first. Email sign-in works.
EOF
fi

# Only the newest build becomes the latest release. Re-running an older run must not point the
# README's link back at an APK that won't install over the newer one.
latest_tag="$(gh release view --repo "$repo" --json tagName --jq .tagName 2>/dev/null || true)"
latest_number="${latest_tag#build-}"
case "$latest_number" in
  '' | *[!0-9]*) latest_number=0 ;;
esac
if [ "$build_number" -ge "$latest_number" ]; then
  latest=--latest
else
  latest=--latest=false
  warn "$latest_tag is newer than $tag, so $latest_tag stays the latest release."
fi

if gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
  say "Release $tag exists (a re-run); replacing its APK."
  gh release upload "$tag" "$asset" --repo "$repo" --clobber
  gh release edit "$tag" --repo "$repo" --title "$title" --notes-file "$notes" --draft=false \
    --prerelease=false "$latest"
else
  gh release create "$tag" "$asset" --repo "$repo" --target "$sha" --title "$title" \
    --notes-file "$notes" "$latest"
fi

url="https://github.com/$repo/releases/latest/download/$APK_ASSET"
say "Published $tag: $url"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    printf '### Android app\n\n'
    printf '[%s](%s), build %s, %s-signed.\n' "$APK_ASSET" "$url" "$build_number" "$signing"
  } >>"$GITHUB_STEP_SUMMARY"
fi
