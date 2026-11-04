# shellcheck shell=bash
# Installs what Miki's one-time setup needs when this computer lacks it, so infra/bootstrap.sh runs
# on a laptop that has only bash and this repo (docs/DEPLOY.md#one-time-setup-miki): WSL, Debian or
# Ubuntu through apt, and macOS through Homebrew. Every install prints its commands first; sudo asks
# for this computer's password once. Needs lib.sh.

GCLOUD_APT_KEY_URL="https://packages.cloud.google.com/apt/doc/apt-key.gpg"
GCLOUD_APT_KEYRING="/usr/share/keyrings/cloud.google.gpg"
GCLOUD_APT_LIST="/etc/apt/sources.list.d/google-cloud-sdk.list"
GCLOUD_APT_SOURCE="deb [signed-by=$GCLOUD_APT_KEYRING] https://packages.cloud.google.com/apt cloud-sdk main"

is_wsl() {
  [ -n "${WSL_DISTRO_NAME:-}" ] || grep -qi microsoft /proc/version 2>/dev/null
}

# Runs a command as root, through sudo unless this already is root.
as_root() {
  if [ "$(id -u)" = 0 ]; then
    run "$@"
  else
    run sudo "$@"
  fi
}

APT_UPDATED=""
apt_install() {
  if [ -z "$APT_UPDATED" ]; then
    as_root apt-get update -q
    APT_UPDATED=1
  fi
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q "$@"
}

install_gcloud() {
  local tmp
  if command -v apt-get >/dev/null 2>&1; then
    # Google's own package repository, as https://cloud.google.com/sdk/docs/install says.
    apt_install ca-certificates curl gnupg
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/lucid-tools.XXXXXX")"
    run curl -fsSL "$GCLOUD_APT_KEY_URL" --output "$tmp/apt-key.gpg"
    as_root gpg --dearmor --yes -o "$GCLOUD_APT_KEYRING" "$tmp/apt-key.gpg"
    printf '%s\n' "$GCLOUD_APT_SOURCE" >"$tmp/google-cloud-sdk.list"
    as_root install -m 0644 "$tmp/google-cloud-sdk.list" "$GCLOUD_APT_LIST"
    rm -rf "$tmp"
    APT_UPDATED=""
    apt_install google-cloud-cli
  elif command -v brew >/dev/null 2>&1; then
    run brew install --cask google-cloud-sdk
  else
    die "can't install gcloud on this computer by itself; install it from https://cloud.google.com/sdk/docs/install and run this again"
  fi
}

# Installs the gcloud CLI unless it is already on PATH.
ensure_gcloud() {
  local version
  if command -v gcloud >/dev/null 2>&1; then
    return 0
  fi
  step "Installing the gcloud CLI, which this computer doesn't have yet"
  install_gcloud
  hash -r
  command -v gcloud >/dev/null 2>&1 || die "gcloud isn't on PATH after installing it; open a new terminal and run this again"
  version="$(gcloud --version 2>/dev/null | head -n 1 || true)"
  say "Installed ${version:-the gcloud CLI}."
}

# In WSL, lets a CLI's sign-in open the Windows browser and come back on its localhost callback,
# which WSL 2 forwards (wslview comes with wslu).
use_windows_browser() {
  if ! is_wsl || [ -n "${BROWSER:-}" ]; then
    return 0
  fi
  if ! command -v wslview >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    apt_install wslu || warn "couldn't install wslu; using explorer.exe to open the browser"
  fi
  if command -v wslview >/dev/null 2>&1; then
    export BROWSER=wslview
  else
    export BROWSER=explorer.exe
  fi
  say "Links open in the Windows browser (BROWSER=$BROWSER)."
}

# Signs gcloud in through the browser, in this project's own gcloud configuration so other
# projects on this computer keep theirs. The browser comes back on a localhost callback, so there
# is nothing to copy (never --no-launch-browser).
sign_in_gcloud() {
  say "gcloud isn't signed in here. A browser opens: sign in with the Google account that owns"
  say "$PROJECT_ID and administers its billing account."
  if [ -z "${CLOUDSDK_ACTIVE_CONFIG_NAME:-}" ]; then
    run gcloud config configurations create "$GCLOUD_CONFIGURATION" --no-activate --format=none
    export CLOUDSDK_ACTIVE_CONFIG_NAME="$GCLOUD_CONFIGURATION"
  fi
  use_windows_browser
  if is_wsl && [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    # gcloud opens a browser on Linux only when a display is set. Without WSLg there is none, but
    # the Windows browser still opens through $BROWSER.
    run env DISPLAY=:0 gcloud auth login
  else
    run gcloud auth login
  fi
}
