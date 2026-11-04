# shellcheck shell=bash
# Helpers shared by the infra scripts. Written for bash 3.2 too, the version macOS ships.

# DRY_RUN=1 (or --dry-run) prints every command that would change something, runs none of them,
# and reads nothing from Google Cloud, so a dry run needs no credentials.
DRY_RUN="${DRY_RUN:-}"

is_dry_run() {
  case "$DRY_RUN" in
    '' | 0 | false) return 1 ;;
    *) return 0 ;;
  esac
}

say() { printf '%s\n' "$*" >&2; }
step() { printf '\n== %s\n' "$*" >&2; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

# Prints a command so it can be copied and run as is, quoting only the arguments that need it.
quote_cmd() {
  local out='' arg q="'"
  for arg in "$@"; do
    case "$arg" in
      '' | *[!A-Za-z0-9_./:=@,+%^-]*) arg="$q${arg//$q/$q\\$q$q}$q" ;;
    esac
    out="$out $arg"
  done
  printf '%s' "${out# }"
}

# Runs a command that changes something, after printing it. In a dry run, only prints it.
# Never pass a secret as an argument: secrets go through stdin (see add_secret_version).
run() {
  if is_dry_run; then
    say "[dry-run] $(quote_cmd "$@")"
    return 0
  fi
  say "+ $(quote_cmd "$@")"
  "$@"
}

# Like run, but retries a few times. IAM is eventually consistent: a binding on an account created
# seconds ago can fail with "does not exist" before it succeeds.
run_retry() {
  local attempt=1
  if is_dry_run; then
    run "$@"
    return 0
  fi
  until run "$@"; do
    if [ "$attempt" -ge 5 ]; then
      return 1
    fi
    attempt=$((attempt + 1))
    say "retrying in 10 s (attempt $attempt of 5)"
    sleep "${RETRY_SLEEP_SECONDS:-10}"
  done
}

# Runs a read-only command and reports only whether it succeeded. In a dry run it runs nothing and
# fails, so callers take the dry-run path of "this does not exist yet".
probe() {
  if is_dry_run; then
    return 1
  fi
  "$@" >/dev/null 2>&1
}

# Prints the output of a read-only command, or nothing if it fails or in a dry run.
read_value() {
  if is_dry_run; then
    return 0
  fi
  "$@" 2>/dev/null || true
}

# Stops unless $1 looks like an OAuth client id (empty is allowed), so a value from infra/config.sh
# can never break out of the env vars file or a --dart-define.
check_client_id() {
  case "$1" in
    *[!A-Za-z0-9._-]*) die "infra/config.sh has a Google client id with odd characters: $1" ;;
  esac
}

# Writes key=value to the step outputs inside GitHub Actions, or to stdout elsewhere.
set_output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    printf '%s=%s\n' "$1" "$2" >>"$GITHUB_OUTPUT"
  else
    printf '%s=%s\n' "$1" "$2"
  fi
}

# Uses Miki's gcloud configuration for this project when it exists on this machine, without
# changing which configuration is active elsewhere. Every command also passes --project.
use_gcloud_configuration() {
  if is_dry_run || [ -n "${CLOUDSDK_ACTIVE_CONFIG_NAME:-}" ]; then
    return 0
  fi
  if gcloud config configurations describe "$GCLOUD_CONFIGURATION" >/dev/null 2>&1; then
    export CLOUDSDK_ACTIVE_CONFIG_NAME="$GCLOUD_CONFIGURATION"
    say "Using the gcloud configuration '$GCLOUD_CONFIGURATION'."
  fi
}

export CLOUDSDK_CORE_DISABLE_PROMPTS=1
