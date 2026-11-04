#!/usr/bin/env bash
# Builds the Android app: the APK that each deploy publishes as lucid-saga.apk (docs/DEPLOY.md,
# "The Android app"). CI builds it too, with no signing secrets, so a change that breaks the release
# build fails its own PR instead of the deploy.
#
# Usage: infra/build-apk.sh OUT.apk
#
# Environment, all optional:
#   API_BASE_URL               The API the app calls. Default: the service's URL in infra/config.sh.
#   BUILD_NUMBER               Android's versionCode. It must grow with every release, or an update
#                              won't install over the last one. Default: pubspec.yaml's.
#   ANDROID_KEYSTORE_BASE64    The release keystore, base64-encoded. With all four of these set,
#   ANDROID_KEYSTORE_PASSWORD  the APK is signed for release. With none, it is signed with this
#   ANDROID_KEY_ALIAS          machine's debug key, which changes from one CI run to the next.
#   ANDROID_KEY_PASSWORD       With only some, the build stops: one is probably misspelt.
#   APP_DIR                    The Flutter app. Default: app/. For the infra tests.
#
# Writes these step outputs in GitHub Actions, or prints them: signing (release or debug), sha1 and
# sha256 (the signing certificate's, which the Android OAuth client needs), version_name and
# version_code.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
# shellcheck source=infra/lib.sh
. "$HERE/lib.sh"
# shellcheck source=infra/config.sh
. "$HERE/config.sh"

SIGNING_SECRETS="ANDROID_KEYSTORE_BASE64 ANDROID_KEYSTORE_PASSWORD ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD"

out="${1:-}"
[ -n "$out" ] || die "usage: infra/build-apk.sh OUT.apk"
case "$out" in
  /*) ;;
  *) out="$PWD/$out" ;;
esac

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lucid-apk.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

app_dir="${APP_DIR:-$ROOT/app}"
api_url="${API_BASE_URL:-$API_URL}"
case "$api_url" in
  https://* | http://*) ;;
  *) die "API_BASE_URL must be an http or https URL" ;;
esac
# The web OAuth client from infra/config.sh is the app's server client id on Android (T8).
web_client_id="$GOOGLE_WEB_CLIENT_ID"
case "$web_client_id" in
  *[!A-Za-z0-9._-]*) die "infra/config.sh has a Google web client id with odd characters" ;;
esac
build_number="${BUILD_NUMBER:-}"
case "$build_number" in
  *[!0-9]* | 0*) die "BUILD_NUMBER must be a whole number above 0" ;;
esac

# Signing (docs/DEPLOY.md). app/android/app/build.gradle.kts signs for release when
# ANDROID_KEYSTORE_PATH is set, and with the debug key otherwise.
unset ANDROID_KEYSTORE_PATH
given=0
missing=''
for name in $SIGNING_SECRETS; do
  if [ -n "${!name:-}" ]; then
    given=$((given + 1))
  else
    missing="$missing $name"
  fi
done
if [ "$given" -eq 4 ]; then
  signing=release
  printf '%s' "$ANDROID_KEYSTORE_BASE64" | base64 --decode >"$TMP_DIR/release.jks" 2>/dev/null ||
    die "ANDROID_KEYSTORE_BASE64 isn't base64"
  [ -s "$TMP_DIR/release.jks" ] || die "ANDROID_KEYSTORE_BASE64 is empty once decoded"
  export ANDROID_KEYSTORE_PATH="$TMP_DIR/release.jks"
  say "Signing with the release keystore."
elif [ "$given" -eq 0 ]; then
  signing=debug
  warn "no release keystore, so the APK is signed with the debug key: Google sign-in won't work in" \
    "it, and the next build won't install over it. docs/DEPLOY.md says how to add the keystore."
else
  die "only some of the signing secrets are set; missing:$missing. Set all four, or none to sign with the debug key."
fi

args=(build apk --release "--dart-define=API_BASE_URL=$api_url")
if [ -n "$web_client_id" ]; then
  args+=("--dart-define=GOOGLE_WEB_CLIENT_ID=$web_client_id")
else
  warn "infra/config.sh has no Google web client id, so the app offers email sign-in only."
fi
if [ -n "$build_number" ]; then
  args+=("--build-number=$build_number")
fi
step "flutter $(quote_cmd "${args[@]}")"
(cd "$app_dir" && flutter "${args[@]}")
mkdir -p "$(dirname "$out")"
cp "$app_dir/build/app/outputs/flutter-apk/app-release.apk" "$out"

# The signing certificate's fingerprints, as the Google Cloud console writes them (AA:BB:…).
apksigner=''
if [ -n "${ANDROID_HOME:-}" ] && [ -d "$ANDROID_HOME/build-tools" ]; then
  apksigner="$(find "$ANDROID_HOME/build-tools" -mindepth 2 -maxdepth 2 -name apksigner | sort -V | tail -n 1)"
fi
fingerprint() { # algorithm
  local hex
  hex="$(sed -n "s/^Signer #1 certificate $1 digest: *//p" "$TMP_DIR/certs" | head -n 1)"
  printf '%s' "$hex" | tr '[:lower:]' '[:upper:]' | sed 's/../&:/g; s/:$//'
}
sha1=''
sha256=''
if [ -n "$apksigner" ]; then
  "$apksigner" verify --print-certs "$out" >"$TMP_DIR/certs" || die "the APK's signature doesn't verify"
  sha1="$(fingerprint SHA-1)"
  sha256="$(fingerprint SHA-256)"
else
  warn "apksigner was not found under ANDROID_HOME, so the signing certificate isn't shown."
fi

version_name="$(sed -n 's/^version: *\([^+]*\).*/\1/p' "$app_dir/pubspec.yaml")"
version_code="${build_number:-$(sed -n 's/^version: *[^+]*+\([0-9]*\).*/\1/p' "$app_dir/pubspec.yaml")}"

set_output signing "$signing"
set_output sha1 "$sha1"
set_output sha256 "$sha256"
set_output version_name "$version_name"
set_output version_code "$version_code"
say "Built $out: version $version_name ($version_code), $signing-signed${sha1:+, SHA-1 $sha1}."
