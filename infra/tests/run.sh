#!/usr/bin/env bash
# Tests for the infra scripts, run in CI (the infra job) and locally: infra/tests/run.sh
#
# Fake gcloud, gh and curl (infra/tests/fakes) log every call, so these tests show what the scripts
# would run, that a dry run touches nothing, that bootstrap.sh is safe to re-run, and that no secret
# value ever reaches arguments or output. Nothing here talks to Google Cloud or GitHub.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INFRA="$ROOT/infra"
FAKES="$INFRA/tests/fakes"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/infra-tests.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

passed=0
failed=0
current=''

start() {
  current="$1"
  printf '%s\n' "- $current"
}
ok() { passed=$((passed + 1)); }
bad() {
  failed=$((failed + 1))
  printf '  FAIL (%s): %s\n' "$current" "$*"
}
contains() { # file pattern [message]
  if grep -qF -- "$2" "$1"; then ok; else bad "${3:-expected to find: $2}"; fi
}
lacks() { # file pattern [message]
  if grep -qF -- "$2" "$1"; then bad "${3:-expected not to find: $2}"; else ok; fi
}
equals() { # actual expected message
  if [ "$1" = "$2" ]; then ok; else bad "$3 (got '$1', expected '$2')"; fi
}

new_state() {
  local dir="$WORK/$1"
  rm -rf "$dir"
  mkdir -p "$dir/res"
  # The runtime service account exists already (T1).
  touch "$dir/res/iam_service-accounts_playable-anime-api"
  printf '%s' "$dir"
}

# Runs a script with the fakes first on PATH; stdout and stderr go to $out.
with_fakes() {
  local out="$1"
  shift
  set +e
  env PATH="$FAKES:$PATH" RETRY_SLEEP_SECONDS=0 SMOKE_SLEEP_SECONDS=0 "$@" >"$out" 2>&1
  status=$?
  set -e
}

POOLED="postgresql://app:SENTINEL-POOLED-PASSWORD@ep-quiet-cat-123456-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
DIRECT="postgresql://app:SENTINEL-DIRECT-PASSWORD@ep-quiet-cat-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require"

test_bootstrap_dry_run() {
  local state out
  start "bootstrap.sh --dry-run prints the plan and calls nothing"
  state="$(new_state bootstrap-dry)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/bootstrap.sh" --dry-run
  equals "$status" 0 "exit status"
  if [ -e "$state/calls.log" ]; then bad "a dry run called gcloud"; else ok; fi
  contains "$out" "[dry-run] gcloud services enable run.googleapis.com"
  contains "$out" "[dry-run] gcloud artifacts repositories create playable-anime --project=playable-anime --location=europe-west3 --repository-format=docker"
  contains "$out" "set-cleanup-policies playable-anime"
  contains "$out" "[dry-run] gcloud secrets create database-url --project=playable-anime --replication-policy=user-managed --locations=europe-west3"
  contains "$out" "[dry-run] gcloud secrets create database-url-direct"
  contains "$out" "[dry-run] gcloud secrets create django-secret-key"
  contains "$out" "[dry-run] gcloud storage buckets create gs://playable-anime-pictures --project=playable-anime --location=europe-west3"
  contains "$out" "--public-access-prevention --soft-delete-duration=0"
  contains "$out" "--member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectUser"
  contains "$out" "--role=roles/iam.serviceAccountTokenCreator"
  contains "$out" "[dry-run] gcloud iam service-accounts create github-deployer"
  contains "$out" "--role=roles/run.developer"
  contains "$out" "--role=roles/iam.serviceAccountUser"
  contains "$out" "--role=roles/artifactregistry.writer"
  contains "$out" "providers create-oidc playable-anime-deploy"
  contains "$out" "assertion.repository_id == '\\''1444213567'\\''"
  contains "$out" "assertion.repository_owner_id == '\\''112938189'\\''"
  contains "$out" "assertion.ref == '\\''refs/heads/main'\\''"
  contains "$out" "assertion.event_name == '\\''workflow_dispatch'\\''"
  contains "$out" "Mikigb77/PlayableAnime/.github/workflows/deploy.yml@refs/heads/main"
  contains "$out" "--member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser"
  contains "$out" "[dry-run] gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID"
  contains "$out" "--budget-amount=25"
  lacks "$out" "allUsers" "bootstrap must never make anything public"
  lacks "$out" "roles/run.admin" "the deployer must not get IAM rights over services"
  lacks "$out" "keys create" "no service-account keys (B11)"
}

test_bootstrap_first_and_second_run() {
  local state out calls_before key
  start "bootstrap.sh creates everything once, keeps secrets out of output, and re-runs cleanly"
  state="$(new_state bootstrap-real)"
  out="$state/out-1"
  with_fakes "$out" env FAKE_STATE="$state" BUDGET_AMOUNT=30 \
    NEON_PRODUCTION_DATABASE_URL="$POOLED" NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" \
    "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "first run exit status"
  contains "$state/calls.log" "gcloud artifacts repositories create playable-anime"
  contains "$state/calls.log" "gcloud secrets create database-url "
  contains "$state/calls.log" "gcloud secrets create database-url-direct "
  contains "$state/calls.log" "gcloud secrets create django-secret-key "
  contains "$state/calls.log" "gcloud storage buckets create gs://playable-anime-pictures"
  contains "$state/calls.log" "gcloud iam service-accounts create github-deployer"
  lacks "$state/calls.log" "gcloud iam service-accounts create playable-anime-api" \
    "the existing runtime account must not be created again"
  contains "$state/calls.log" "gcloud iam workload-identity-pools create github"
  contains "$state/calls.log" "gcloud iam workload-identity-pools providers create-oidc playable-anime-deploy"
  contains "$state/calls.log" "gcloud billing budgets create --billing-account=000000-AAAAAA-BBBBBB"
  contains "$state/calls.log" "--budget-amount=30"
  equals "$(cat "$state/secret-database-url")" "$POOLED" "pooled URL stored in database-url"
  equals "$(cat "$state/secret-database-url-direct")" "$DIRECT" "direct URL stored in database-url-direct"
  key="$(cat "$state/secret-django-secret-key")"
  if [ "${#key}" -ge 50 ]; then ok; else bad "the Django key has only ${#key} characters"; fi
  for log in "$out" "$state/calls.log"; do
    lacks "$log" "SENTINEL-POOLED-PASSWORD" "the pooled URL leaked into $(basename "$log")"
    lacks "$log" "SENTINEL-DIRECT-PASSWORD" "the direct URL leaked into $(basename "$log")"
    lacks "$log" "$key" "the Django key leaked into $(basename "$log")"
  done

  calls_before="$(wc -l <"$state/calls.log")"
  out="$state/out-2"
  # No URLs this time: secrets that have a value must not be asked for again.
  with_fakes "$out" env FAKE_STATE="$state" BUDGET_AMOUNT=40 "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "second run exit status"
  tail -n +"$((calls_before + 1))" "$state/calls.log" >"$state/calls-2.log"
  lacks "$state/calls-2.log" " create " "a re-run must not create anything"
  lacks "$state/calls-2.log" "create-oidc" "a re-run must not create the provider again"
  lacks "$state/calls-2.log" "secrets versions add" "a re-run must not overwrite a secret"
  contains "$state/calls-2.log" "providers update-oidc playable-anime-deploy"
  contains "$state/calls-2.log" "gcloud billing budgets update billingAccounts/000000-AAAAAA-BBBBBB/budgets/budget-1"
  contains "$state/calls-2.log" "--budget-amount=40"
  equals "$(cat "$state/secret-django-secret-key")" "$key" "the Django key must survive a re-run"
}

test_bootstrap_rejects_bad_input() {
  local state out
  start "bootstrap.sh rejects swapped URLs and a bad budget before changing anything"
  state="$(new_state bootstrap-swapped)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" NEON_PRODUCTION_DATABASE_URL="$DIRECT" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" "$INFRA/bootstrap.sh" --yes
  if [ "$status" -ne 0 ]; then ok; else bad "accepted a direct URL as the pooled one"; fi
  contains "$out" "must be the pooled URL"
  lacks "$out" "SENTINEL-DIRECT-PASSWORD" "an error message printed the URL"
  lacks "$state/calls.log" " create " "changed something before validating input"

  state="$(new_state bootstrap-swapped-direct)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" NEON_PRODUCTION_DATABASE_URL="$POOLED" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="$POOLED" "$INFRA/bootstrap.sh" --yes
  if [ "$status" -ne 0 ]; then ok; else bad "accepted a pooled URL as the direct one"; fi
  contains "$out" "must be the direct URL"

  state="$(new_state bootstrap-budget)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" BUDGET_AMOUNT=lots "$INFRA/bootstrap.sh" --dry-run
  if [ "$status" -ne 0 ]; then ok; else bad "accepted BUDGET_AMOUNT=lots"; fi
  contains "$out" "BUDGET_AMOUNT must be a number"

  # Only where there is no terminal to ask on, as in CI; elsewhere this would wait for input.
  if ! { : </dev/tty; } 2>/dev/null; then
    state="$(new_state bootstrap-no-tty)"
    out="$state/out"
    with_fakes "$out" env FAKE_STATE="$state" "$INFRA/bootstrap.sh" --yes
    if [ "$status" -ne 0 ]; then ok; else bad "ran without the URLs and without a terminal"; fi
    contains "$out" "NEON_PRODUCTION_DATABASE_URL is not set"
  fi
}

test_deploy_dry_run() {
  local state out
  start "deploy.sh in a dry run prints the migrate job and the service deploy, and calls nothing"
  state="$(new_state deploy-dry)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" DRY_RUN=1 "$INFRA/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  equals "$status" 0 "migrate exit status"
  contains "$out" "[dry-run] gcloud run jobs deploy playable-anime-migrate --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --command=python --args=manage.py,migrate,--noinput"
  contains "$out" "--set-secrets=DATABASE_URL=database-url-direct:latest,DJANGO_SECRET_KEY=django-secret-key:latest"
  contains "$out" "[dry-run] gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --wait"

  out="$state/out-service"
  with_fakes "$out" env FAKE_STATE="$state" DRY_RUN=1 "$INFRA/deploy.sh" service \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  equals "$status" 0 "service exit status"
  contains "$out" "[dry-run] gcloud run deploy playable-anime-api --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com"
  contains "$out" "--min-instances=0 --max-instances=3 --timeout=300 --cpu-boost"
  contains "$out" "--set-secrets=DATABASE_URL=database-url:latest,DJANGO_SECRET_KEY=django-secret-key:latest"
  contains "$out" 'ALLOWED_HOSTS: "playable-anime-api-528988811295.europe-west3.run.app"'
  contains "$out" 'MEDIA_BUCKET: "playable-anime-pictures"'
  contains "$out" 'LLM_PROVIDER: "vertex"'
  contains "$out" "update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-latest"
  lacks "$out" "allow-unauthenticated" "a deploy must never change who can call the API"
  lacks "$out" "invoker-iam-check" "a deploy must never change who can call the API"
  if [ -e "$state/calls.log" ]; then bad "a dry run called gcloud"; else ok; fi
}

test_deploy_service() {
  local state out
  start "deploy.sh service allows both URLs after the first deploy and records the previous revision"
  state="$(new_state deploy-service)"
  out="$state/out-1"
  with_fakes "$out" env FAKE_STATE="$state" GITHUB_OUTPUT="$state/outputs-1" \
    "$INFRA/deploy.sh" service europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:one
  equals "$status" 0 "first deploy exit status"
  contains "$state/calls.log" "gcloud run deploy playable-anime-api"
  contains "$state/calls.log" "gcloud run services update playable-anime-api"
  contains "$state/last-env.yaml" 'ALLOWED_HOSTS: "playable-anime-api-528988811295.europe-west3.run.app,playable-anime-api-abc123xyz-ey.a.run.app"'
  contains "$state/last-env.yaml" 'CSRF_TRUSTED_ORIGINS: "https://playable-anime-api-528988811295.europe-west3.run.app,https://playable-anime-api-abc123xyz-ey.a.run.app"'
  contains "$state/outputs-1" "previous_revision="
  lacks "$state/outputs-1" "previous_revision=playable" "a first deploy has no previous revision"
  contains "$state/outputs-1" "url=https://playable-anime-api-abc123xyz-ey.a.run.app"

  : >"$state/calls.log"
  out="$state/out-2"
  with_fakes "$out" env FAKE_STATE="$state" GITHUB_OUTPUT="$state/outputs-2" \
    "$INFRA/deploy.sh" service europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:two
  equals "$status" 0 "second deploy exit status"
  lacks "$state/calls.log" "gcloud run services update playable-anime-api" \
    "a later deploy must not need a second revision for its hosts"
  contains "$state/last-env.yaml" "playable-anime-api-abc123xyz-ey.a.run.app"
  contains "$state/outputs-2" "previous_revision=playable-anime-api-00001-abc"
}

test_migration_failure() {
  local state out
  start "deploy.sh migrate fails loudly and points at the logs when the job fails"
  state="$(new_state deploy-migrate-fail)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_MIGRATION=1 "$INFRA/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "a failed migration passed"; fi
  contains "$out" "gcloud logging read"
}

test_smoke() {
  local state out
  start "deploy.sh smoke passes on 200, fails on anything else, and keeps the token out of arguments"
  state="$(new_state smoke)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" SMOKE_ID_TOKEN=token-SENTINEL \
    "$INFRA/deploy.sh" smoke https://example.a.run.app
  equals "$status" 0 "smoke on 200"
  contains "$state/curl.log" "https://example.a.run.app/health"
  lacks "$state/curl.log" "token-SENTINEL" "the ID token must not be a curl argument"
  contains "$state/curl-headers" "Authorization: Bearer token-SENTINEL"
  lacks "$out" "token-SENTINEL" "the ID token must not be printed"

  out="$state/out-400"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_HTTP_CODE=400 SMOKE_ATTEMPTS=2 \
    "$INFRA/deploy.sh" smoke https://example.a.run.app
  if [ "$status" -ne 0 ]; then ok; else bad "smoke passed on a 400"; fi
  contains "$out" "ALLOWED_HOSTS"
}

test_rollback() {
  local state out
  start "deploy.sh rollback sends all traffic to the given revision"
  state="$(new_state rollback)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" rollback playable-anime-api-00007-xyz
  equals "$status" 0 "rollback exit status"
  contains "$state/calls.log" "update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-revisions=playable-anime-api-00007-xyz=100"
}

gate() { # responses... ; sets status
  local responses="$WORK/gh-responses"
  printf '%s\n' "$@" >"$responses"
  rm -f "$responses.calls"
  with_fakes "$WORK/gate-out" env FAKE_GH_RESPONSES="$responses" GITHUB_REPOSITORY=Mikigb77/PlayableAnime \
    GITHUB_SHA=0123abc GITHUB_REF="${GATE_REF:-refs/heads/main}" CI_POLL_SECONDS=1 \
    CI_MISSING_GRACE_SECONDS=0 CI_WAIT_SECONDS=2 "$INFRA/require-green-ci.sh"
}

test_ci_gate() {
  start "require-green-ci.sh deploys only a commit whose CI passed on main"
  gate "completed success https://github.com/run/1"
  equals "$status" 0 "green CI"
  contains "$WORK/gh-responses.calls" "head_sha=0123abc"
  contains "$WORK/gh-responses.calls" "event=push"
  gate "completed failure https://github.com/run/2"
  if [ "$status" -ne 0 ]; then ok; else bad "red CI passed"; fi
  gate "completed cancelled https://github.com/run/3"
  if [ "$status" -ne 0 ]; then ok; else bad "cancelled CI passed"; fi
  gate ""
  if [ "$status" -ne 0 ]; then ok; else bad "a commit with no CI run passed"; fi
  gate "in_progress none https://github.com/run/4" "completed success https://github.com/run/4"
  equals "$status" 0 "CI that finishes green while waiting"
  gate "in_progress none https://github.com/run/5"
  if [ "$status" -ne 0 ]; then ok; else bad "CI that never finishes passed"; fi
  GATE_REF=refs/heads/feature gate "completed success https://github.com/run/6"
  if [ "$status" -ne 0 ]; then ok; else bad "a run from another branch passed"; fi
}

test_workflow_matches_scripts() {
  local wf="$ROOT/.github/workflows/deploy.yml" cmd
  start "deploy.yml uses only commands deploy.sh has"
  if [ -f "$wf" ]; then ok; else bad "missing $wf"; fi
  grep -oE 'infra/deploy\.sh [a-z-]+' "$wf" | awk '{print $2}' | sort -u >"$WORK/workflow-commands"
  while read -r cmd; do
    if "$INFRA/deploy.sh" --help | grep -qE "^  $cmd( |$)"; then ok; else bad "deploy.sh has no '$cmd'"; fi
  done <"$WORK/workflow-commands"
  contains "$wf" "infra/require-green-ci.sh"
}

test_docs_list_every_command() {
  start "docs/DEPLOY.md lists exactly the commands the scripts run"
  "$INFRA/tests/print-commands.sh" >"$WORK/commands-now"
  sed -n '/<!-- every-command:start -->/,/<!-- every-command:end -->/p' "$ROOT/docs/DEPLOY.md" |
    sed -e '1,2d' -e '$d' | sed '$d' >"$WORK/commands-documented"
  if diff -u "$WORK/commands-documented" "$WORK/commands-now" >"$WORK/commands-diff"; then
    ok
  else
    bad "out of date; paste the output of infra/tests/print-commands.sh into docs/DEPLOY.md"
    head -n 20 "$WORK/commands-diff"
  fi
}

test_bootstrap_dry_run
test_bootstrap_first_and_second_run
test_bootstrap_rejects_bad_input
test_deploy_dry_run
test_deploy_service
test_migration_failure
test_smoke
test_rollback
test_ci_gate
test_workflow_matches_scripts
test_docs_list_every_command

printf '\n%d checks passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
