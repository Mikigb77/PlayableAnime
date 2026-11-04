#!/usr/bin/env bash
# Runs every gcloud command the scripts can issue against the real gcloud, offline and signed out,
# to prove that the installed gcloud accepts every command and flag. The commands come from the
# dry runs and from the calls the scripts make against the fake gcloud on first runs, re-runs and
# recoveries, which a dry run can't show (update-oidc, undelete, a role or budget update, the
# first deploy's second revision, making the API private, every read, a failed job's logs, the
# Ops workflow's default command). Each must fail on the network, never on its arguments.
# Nothing reaches Google Cloud: gcloud gets an empty configuration and a proxy that refuses every
# connection.
#
# Usage: infra/tests/check-gcloud-flags.sh   (skips when gcloud isn't installed)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA="$ROOT/infra"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is not installed; skipping."
  exit 0
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/gcloud-flags.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export CLOUDSDK_CONFIG="$WORK/config"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1
export CLOUDSDK_CORE_DISABLE_USAGE_REPORTING=1
export CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK=1
export CLOUDSDK_PROXY_TYPE=http
export CLOUDSDK_PROXY_ADDRESS=127.0.0.1
export CLOUDSDK_PROXY_PORT=9
mkdir -p "$CLOUDSDK_CONFIG"

image="europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:0000"
{
  DRY_RUN=1 "$INFRA/bootstrap.sh" --dry-run
  DRY_RUN=1 "$INFRA/deploy.sh" migrate "$image"
  DRY_RUN=1 "$INFRA/deploy.sh" service "$image"
  DRY_RUN=1 "$INFRA/deploy.sh" access
  DRY_RUN=1 "$INFRA/deploy.sh" models
  DRY_RUN=1 "$INFRA/deploy.sh" covers
  DRY_RUN=1 "$INFRA/deploy.sh" rollback playable-anime-api-00001-abc
} 2>&1 | sed -n 's/^\[dry-run\] \(gcloud .*\)$/\1/p' >"$WORK/dry-run-commands"

state="$WORK/fake-state"
mkdir -p "$state/res"
touch "$state/res/iam_service-accounts_playable-anime-api"
fake() {
  env PATH="$INFRA/tests/fakes:$PATH" FAKE_STATE="$state" RETRY_SLEEP_SECONDS=0 LOGS_WAIT_SECONDS=0 \
    NEON_PRODUCTION_DATABASE_URL="postgresql://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/db" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/db" \
    "$@" >/dev/null 2>&1
}
fake "$INFRA/bootstrap.sh" --yes
fake "$INFRA/bootstrap.sh" --yes
fake env FAKE_DELETED=1 "$INFRA/bootstrap.sh" --yes
fake "$INFRA/deploy.sh" preflight
fake "$INFRA/deploy.sh" migrate "$image"
fake "$INFRA/deploy.sh" service "$image"
fake "$INFRA/deploy.sh" service "$image"
fake "$INFRA/deploy.sh" access
fake env API_ACCESS=private "$INFRA/deploy.sh" access
fake "$INFRA/deploy.sh" covers
fake env FAKE_FAIL_COVERS=1 "$INFRA/deploy.sh" covers || true # its logs are read
fake "$INFRA/deploy.sh" models
fake env OPS_COMMAND="" "$INFRA/ops.sh" run
fake env OPS_COMMAND="run jobs executions list --job=playable-anime-migrate --region=europe-west3" \
  "$INFRA/ops.sh" run
fake "$INFRA/deploy.sh" rollback playable-anime-api-00001-abc
cat "$WORK/dry-run-commands" "$state/calls.log" | sort -u >"$WORK/commands"

# The env vars file of a dry run is deleted when it ends; the committed one has the same shape.
sed -i.bak "s#--env-vars-file=[^ ]*#--env-vars-file=$INFRA/cloudrun/env.yaml#" "$WORK/commands"
# The secret commands show where their value comes from after "<<<"; the value goes in on stdin.
sed -i.bak 's# <<< (.*)$##' "$WORK/commands"

# Signed out and offline, each command fails after gcloud's network retries, so run them together.
count=0
while IFS= read -r command; do
  count=$((count + 1))
  (eval "$command" </dev/null >"$WORK/out-$count" 2>&1 || true) &
done <"$WORK/commands"
wait

failed=0
i=0
while IFS= read -r command; do
  i=$((i + 1))
  if grep -qiE 'unrecognized arguments|argument --|invalid value for|invalid choice|is not a valid|must be specified|expected one argument|bad syntax|failed to parse|no such file' "$WORK/out-$i"; then
    failed=$((failed + 1))
    printf 'FAIL: %s\n%s\n\n' "$command" "$(head -n 8 "$WORK/out-$i")"
  fi
done <"$WORK/commands"

[ "$count" -gt 30 ] || {
  echo "Only $count commands were checked; the dry runs printed less than expected."
  exit 1
}
echo "$count gcloud commands checked against $(gcloud --version 2>/dev/null | head -n 1), $failed rejected."
[ "$failed" -eq 0 ]
