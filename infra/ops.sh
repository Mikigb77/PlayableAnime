#!/usr/bin/env bash
# The steps of .github/workflows/ops.yml: read-only Google Cloud for threads and anyone with write
# access to the repo, without a laptop (docs/DEPLOY.md#reading-google-cloud).
#
# The workflow signs in as the read-only ops account, which reads settings and logs but can't
# change anything or read a secret's value. This script also refuses the few commands that would
# print a credential or switch accounts, so nothing usable ever lands in the run's log.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/lib.sh
. "$HERE/lib.sh"
# shellcheck source=infra/config.sh
. "$HERE/config.sh"

usage() {
  cat <<'EOF'
Usage: infra/ops.sh <command>

  github-outputs   Write the Ops workflow's names from infra/config.sh as step outputs.
  run              Run OPS_COMMAND, a gcloud command line without "gcloud", and print its output.
                   Empty runs the default: the API's and its jobs' warnings and errors of the
                   last 3 hours, oldest first.

Examples of OPS_COMMAND:
  logging read 'resource.type="cloud_run_job" AND severity>=ERROR' --freshness=1d --limit=50
  run services describe playable-anime-api --region=europe-west3
  run jobs executions list --job=playable-anime-migrate --region=europe-west3
  projects get-iam-policy playable-anime
EOF
}

# The API's and its jobs' warnings and errors, with each line's message, model fields and traceback.
DEFAULT_COMMAND=(
  logging read
  'severity>=WARNING AND (resource.type="cloud_run_revision" OR resource.type="cloud_run_job")'
  --freshness=3h --order=asc --limit=200
  '--format=value(timestamp,severity,resource.labels.service_name,resource.labels.job_name,textPayload,jsonPayload.message,jsonPayload.llm,jsonPayload.stack_trace)'
)

cmd_github_outputs() {
  set_output project_id "$PROJECT_ID"
  set_output wif_provider "$OPS_WIF_PROVIDER_RESOURCE"
  set_output ops_sa "$OPS_SA"
}

# Splits $1 the way a shell would, without running anything in it, one argument per line of the
# file $2 (NUL-separated). Fails on unbalanced quotes.
split_command() {
  python3 -I -c '
import shlex
import sys

sys.stdout.write("".join(arg + "\0" for arg in shlex.split(sys.argv[1])))
' "$1" >"$2"
}

# Stops on a command that could print a credential, switch accounts or change gcloud's own setup.
# The account can't change Google Cloud anyway; this keeps tokens out of the log.
check_allowed() {
  local arg group="${1:-}"
  case "$group" in
    alpha | beta) group="${2:-}" ;;
  esac
  case "$group" in
    auth | config | init | components)
      die "'gcloud $group' isn't allowed here: it could print or change credentials"
      ;;
  esac
  for arg in "$@"; do
    case "$arg" in
      *print-access-token* | *print-identity-token* | *access-token-file* | \
        *impersonate-service-account* | --account | --account=* | *credential-file* | \
        --configuration | --configuration=* | --flags-file | --flags-file=* | --log-http* | \
        --verbosity | --verbosity=*)
        die "'$arg' isn't allowed here: it could print or switch credentials"
        ;;
    esac
  done
  case " $* " in
    *" secrets versions access "*) die "secret values are never read here (T11)" ;;
    *" service-accounts keys "*) die "service-account keys are never touched here (B11)" ;;
  esac
}

cmd_run() {
  local command="${OPS_COMMAND:-}" args=() arg token status
  if [ -z "${command//[[:space:]]/}" ]; then
    args=("${DEFAULT_COMMAND[@]}")
  else
    split_command "$command" "$TMP_DIR/args" || die "can't read the command: check its quotes"
    while IFS= read -r -d '' arg; do
      args+=("$arg")
    done <"$TMP_DIR/args"
    if [ "${args[0]:-}" = gcloud ]; then
      args=("${args[@]:1}")
    fi
    [ "${#args[@]}" -gt 0 ] || die "the command is empty"
  fi
  check_allowed "${args[@]}"
  # The command and its output are data: GitHub must not read a "::" line in them as a workflow
  # command.
  token="ops-$(date +%s)-$$-$RANDOM"
  printf '::stop-commands::%s\n' "$token"
  say "+ $(quote_cmd gcloud "${args[@]}")"
  set +e
  gcloud "${args[@]}"
  status=$?
  set -e
  printf '::%s::\n' "$token"
  return "$status"
}

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lucid-ops.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

main() {
  case "${1:-}" in
    github-outputs) cmd_github_outputs ;;
    run) cmd_run ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      die "unknown command: ${1:-none}"
      ;;
  esac
}

main "$@"
