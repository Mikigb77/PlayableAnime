#!/usr/bin/env bash
# Tests for the infra scripts, run in CI (the infra job) and locally: infra/tests/run.sh
#
# Fake gcloud, gh, curl, sudo, apt-get and brew (infra/tests/fakes) log every call and install or
# change nothing, so these tests show what the scripts would run, that a dry run touches nothing,
# that bootstrap.sh is safe to re-run, and that no secret value ever reaches arguments or output.
# Nothing here talks to Google Cloud or GitHub.

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
  env PATH="$FAKES:$PATH" RETRY_SLEEP_SECONDS=0 SMOKE_SLEEP_SECONDS=0 LOGS_WAIT_SECONDS=0 \
    OWNER_EMAILS="$TEST_OWNER" "$@" >"$out" 2>&1
  status=$?
  set -e
}

# The deploy workflow passes the OWNER_EMAILS secret; tests use this address unless they set it.
TEST_OWNER="owner@example.com"

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
  contains "$out" "[dry-run] gcloud storage buckets create gs://playable-anime-releases --project=playable-anime --location=europe-west3"
  contains "$out" "[dry-run] gcloud storage buckets add-iam-policy-binding gs://playable-anime-releases --project=playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectUser"
  contains "$out" "[dry-run] gcloud storage buckets add-iam-policy-binding gs://playable-anime-releases --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectViewer"
  if grep -E "gs://playable-anime-pictures .*github-deployer" "$out" >/dev/null; then
    bad "the deployer must never reach the players' pictures"
  else
    ok
  fi
  contains "$out" "[dry-run] gcloud iam service-accounts create github-deployer"
  contains "$out" "--role=roles/run.developer"
  contains "$out" "--role=roles/iam.serviceAccountUser"
  contains "$out" "--role=roles/artifactregistry.writer"
  contains "$out" "providers create-oidc playable-anime-deploy"
  contains "$out" "assertion.repository_id == '\\''1444213567'\\''"
  contains "$out" "assertion.repository_owner_id == '\\''112938189'\\''"
  contains "$out" "assertion.ref == '\\''refs/heads/main'\\''"
  contains "$out" "(assertion.event_name == '\\''push'\\'' || assertion.event_name == '\\''workflow_dispatch'\\'')"
  contains "$out" "Mikigb77/PlayableAnime/.github/workflows/deploy.yml@refs/heads/main"
  contains "$out" "[dry-run] gcloud iam roles create lucidSagaApiAccess --project=playable-anime"
  contains "$out" "--permissions=run.services.getIamPolicy,run.services.setIamPolicy --stage=GA"
  contains "$out" "--member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=projects/playable-anime/roles/lucidSagaApiAccess"
  contains "$out" "--member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser"
  contains "$out" "--member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/logging.viewer"
  contains "$out" "[dry-run] gcloud iam service-accounts create github-ops"
  contains "$out" "--member=serviceAccount:github-ops@playable-anime.iam.gserviceaccount.com --role=roles/viewer"
  contains "$out" "--member=serviceAccount:github-ops@playable-anime.iam.gserviceaccount.com --role=roles/logging.viewer"
  contains "$out" "[dry-run] gcloud iam workload-identity-pools create github-ops"
  contains "$out" "providers create-oidc playable-anime-ops --project=playable-anime --location=global --workload-identity-pool=github-ops"
  contains "$out" "assertion.event_name == '\\''workflow_dispatch'\\'' && assertion.workflow_ref == '\\''Mikigb77/PlayableAnime/.github/workflows/ops.yml@refs/heads/main'\\''"
  contains "$out" "--member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github-ops/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser"
  if grep -E -e "--member=serviceAccount:github-ops@.*--role=roles/(owner|editor|secretmanager|storage|run\.developer|iam\.)" "$out" >/dev/null; then
    bad "the ops account must stay read-only"
  else
    ok
  fi
  if grep -E "workloadIdentityPools/github/.* github-ops@|iam service-accounts add-iam-policy-binding github-ops@.*workloadIdentityPools/github/" "$out" >/dev/null; then
    bad "the deploy pool must never reach the ops account"
  else
    ok
  fi
  if grep -E "add-iam-policy-binding github-deployer@.*workloadIdentityPools/github-ops/" "$out" >/dev/null; then
    bad "the ops pool must never reach the deployer"
  else
    ok
  fi
  contains "$out" "[dry-run] gcloud iam service-accounts create github-evals"
  contains "$out" "--member=serviceAccount:github-evals@playable-anime.iam.gserviceaccount.com --role=roles/aiplatform.user"
  contains "$out" "[dry-run] gcloud iam workload-identity-pools create github-evals"
  contains "$out" "providers create-oidc playable-anime-evals --project=playable-anime --location=global --workload-identity-pool=github-evals"
  contains "$out" "(assertion.event_name == '\\''schedule'\\'' || assertion.event_name == '\\''workflow_dispatch'\\'') && assertion.workflow_ref == '\\''Mikigb77/PlayableAnime/.github/workflows/evals.yml@refs/heads/main'\\''"
  contains "$out" "--member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github-evals/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser"
  if grep -E -e "--member=serviceAccount:github-evals@" "$out" | grep -v -e "--role=roles/aiplatform.user" >/dev/null; then
    bad "the evals account may only call Vertex AI"
  else
    ok
  fi
  if grep -E "add-iam-policy-binding github-(deployer|ops)@.*workloadIdentityPools/github-evals/|add-iam-policy-binding github-evals@.*workloadIdentityPools/github(-ops)?/" "$out" >/dev/null; then
    bad "the evals pool and the others must never reach each other's accounts"
  else
    ok
  fi
  lacks "$out" "EVALS_ENABLED" "the nightly run's cost stays Miki's call"
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
  contains "$state/calls.log" "gcloud storage buckets create gs://playable-anime-releases"
  contains "$state/calls.log" "gcloud iam service-accounts create github-deployer"
  lacks "$state/calls.log" "gcloud iam service-accounts create playable-anime-api" \
    "the existing runtime account must not be created again"
  contains "$state/calls.log" "gcloud iam workload-identity-pools create github"
  contains "$state/calls.log" "gcloud iam workload-identity-pools providers create-oidc playable-anime-deploy"
  contains "$state/calls.log" "gcloud iam service-accounts create github-ops"
  contains "$state/calls.log" "gcloud iam workload-identity-pools create github-ops"
  contains "$state/calls.log" "gcloud iam workload-identity-pools providers create-oidc playable-anime-ops"
  contains "$state/calls.log" "gcloud iam roles create lucidSagaApiAccess"
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
  contains "$state/calls-2.log" "providers update-oidc playable-anime-ops"
  # The fake logs arguments as printf %q does, which escapes commas.
  contains "$state/calls-2.log" "gcloud iam roles update lucidSagaApiAccess --project=playable-anime --permissions=run.services.getIamPolicy\\,run.services.setIamPolicy"
  lacks "$state/calls-2.log" "iam roles undelete" "a re-run must not undelete a role that is there"
  contains "$state/calls-2.log" "gcloud billing budgets update billingAccounts/000000-AAAAAA-BBBBBB/budgets/budget-1"
  contains "$state/calls-2.log" "--budget-amount=40"
  equals "$(cat "$state/secret-django-secret-key")" "$key" "the Django key must survive a re-run"

  calls_before="$(wc -l <"$state/calls.log")"
  out="$state/out-3"
  # A failed read of the secrets must stop the run, never be taken as "no value yet".
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_SECRET_LIST=1 "$INFRA/bootstrap.sh" --yes
  if [ "$status" -ne 0 ]; then ok; else bad "went on after failing to list a secret's versions"; fi
  tail -n +"$((calls_before + 1))" "$state/calls.log" >"$state/calls-3.log"
  lacks "$state/calls-3.log" "secrets versions add" "replaced a secret after a failed read"
  equals "$(cat "$state/secret-django-secret-key")" "$key" "the Django key must survive a failed read"

  calls_before="$(wc -l <"$state/calls.log")"
  out="$state/out-4"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_DELETED=1 "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "re-run with a deleted pool exit status"
  tail -n +"$((calls_before + 1))" "$state/calls.log" >"$state/calls-4.log"
  contains "$state/calls-4.log" "gcloud iam workload-identity-pools undelete github"
  contains "$state/calls-4.log" "gcloud iam workload-identity-pools providers undelete playable-anime-deploy"
  contains "$state/calls-4.log" "providers update-oidc playable-anime-deploy"
  contains "$state/calls-4.log" "gcloud iam workload-identity-pools undelete github-ops"
  contains "$state/calls-4.log" "gcloud iam workload-identity-pools providers undelete playable-anime-ops"
  contains "$state/calls-4.log" "gcloud iam roles undelete lucidSagaApiAccess --project=playable-anime"
  lacks "$state/calls-4.log" "iam roles create" "a deleted role can only be undeleted"
}

test_bootstrap_reads_neon_urls() {
  local state out
  start "bootstrap.sh reads the Neon URLs with neonctl after a login, and keeps them out of output"
  state="$(new_state bootstrap-neonctl)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_NEON_POOLED="$POOLED" FAKE_NEON_DIRECT="$DIRECT" \
    "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "exit status"
  equals "$(cat "$state/secret-database-url" 2>/dev/null)" "$POOLED" "pooled URL read with neonctl"
  equals "$(cat "$state/secret-database-url-direct" 2>/dev/null)" "$DIRECT" "direct URL read with neonctl"
  contains "$state/neonctl.log" "neonctl connection-string production --project-id divine-rice-51324513 --pooled"
  contains "$out" "Read the pooled URL of Neon's production branch with neonctl."
  for log in "$out" "$state/calls.log"; do
    lacks "$log" "SENTINEL-POOLED-PASSWORD" "the pooled URL leaked into $(basename "$log")"
    lacks "$log" "SENTINEL-DIRECT-PASSWORD" "the direct URL leaked into $(basename "$log")"
  done

  # neonctl answering with the wrong kind of URL is still refused before anything changes.
  state="$(new_state bootstrap-neonctl-swapped)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_NEON_POOLED="$DIRECT" FAKE_NEON_DIRECT="$DIRECT" \
    "$INFRA/bootstrap.sh" --yes
  if [ "$status" -ne 0 ]; then ok; else bad "accepted a direct URL from neonctl as the pooled one"; fi
  lacks "$state/calls.log" " create " "changed something before validating neonctl's URLs"
}

test_bootstrap_signs_in() {
  local state out
  start "bootstrap.sh signs in through the browser when gcloud is signed out or can't see the project"
  state="$(new_state bootstrap-signed-out)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_SIGNED_OUT=1 BROWSER=fake-browser \
    NEON_PRODUCTION_DATABASE_URL="$POOLED" NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" \
    "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "exit status"
  contains "$state/calls.log" "gcloud config configurations create playable-anime --no-activate --format=none"
  contains "$state/calls.log" "gcloud auth login"
  lacks "$state/calls.log" "--no-launch-browser" "the sign-in must open the browser"
  contains "$out" "Signed in as miki@example.com, project playable-anime (528988811295)."
  contains "$state/calls.log" "gcloud services enable"

  # Signed in elsewhere as an account that can't see the project: sign in again, in the project's
  # own configuration when it exists.
  state="$(new_state bootstrap-wrong-account)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_WRONG_ACCOUNT=1 FAKE_HAS_CONFIGURATION=1 \
    BROWSER=fake-browser NEON_PRODUCTION_DATABASE_URL="$POOLED" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "exit status"
  contains "$out" "miki@example.com can't read project playable-anime."
  contains "$state/calls.log" "gcloud auth login"
  lacks "$state/calls.log" "configurations create" "the project's configuration exists already"

  # Already signed in: no sign-in.
  state="$(new_state bootstrap-signed-in)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" NEON_PRODUCTION_DATABASE_URL="$POOLED" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" "$INFRA/bootstrap.sh" --yes
  equals "$status" 0 "exit status"
  lacks "$state/calls.log" "auth login" "signed in already"
}

# Runs a function of tools.sh with only $FAKE_BIN on PATH: the fakes of sudo, curl and $3 (apt-get
# or brew) and the few commands the scripts use, and no gcloud. Output goes to $out.
with_tools() {
  local state="$1" fn="$2" manager="$3" bin="$1/bin" tool
  shift 3
  mkdir -p "$bin"
  for tool in bash cat cp dirname basename grep head ln mkdir mktemp readlink rm tr; do
    ln -sf "$(command -v "$tool")" "$bin/$tool"
  done
  ln -sf "$FAKES/sudo" "$bin/sudo"
  ln -sf "$FAKES/curl" "$bin/curl"
  if [ -n "$manager" ]; then ln -sf "$FAKES/$manager" "$bin/$manager"; fi
  # Not root, so installs go through sudo.
  printf '#!/bin/sh\necho 1000\n' >"$bin/id"
  chmod +x "$bin/id"
  set +e
  # shellcheck disable=SC2016 # The inner bash expands these.
  /usr/bin/env -i PATH="$bin" HOME="$state" TMPDIR="$state" FAKE_STATE="$state" FAKE_BIN="$bin" \
    "$@" bash -c '. "$1/lib.sh"; . "$1/config.sh"; . "$1/tools.sh"; '"$fn"'; echo "BROWSER=${BROWSER:-}"' \
    _ "$INFRA" >"$state/out" 2>&1
  status=$?
  set -e
}

test_tools_install() {
  local state
  start "tools.sh installs gcloud through apt or Homebrew when it is missing, and nothing else"
  state="$(new_state tools-apt)"
  with_tools "$state" ensure_gcloud apt-get
  equals "$status" 0 "exit status"
  contains "$state/sudo.log" "sudo apt-get update -q"
  contains "$state/sudo.log" "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q ca-certificates curl gnupg"
  contains "$state/curl.log" "-fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg --output"
  contains "$state/sudo.log" "sudo gpg --dearmor --yes -o /usr/share/keyrings/cloud.google.gpg"
  contains "$state/sudo.log" "/etc/apt/sources.list.d/google-cloud-sdk.list"
  contains "$state/installed-google-cloud-sdk.list" "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main"
  contains "$state/sudo.log" "apt-get install -y -q google-cloud-cli"
  # The package list is read again once Google's repository is added, before installing from it.
  equals "$(grep -c 'apt-get update' "$state/sudo.log")" 2 "apt-get update runs before each install round"
  equals "$(tail -n 1 "$state/sudo.log")" "sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -q google-cloud-cli" "gcloud is installed last"

  state="$(new_state tools-brew)"
  with_tools "$state" ensure_gcloud brew
  equals "$status" 0 "exit status"
  contains "$state/brew.log" "brew install --cask google-cloud-sdk"
  if [ -e "$state/sudo.log" ]; then bad "Homebrew needs no sudo"; else ok; fi

  state="$(new_state tools-none)"
  with_tools "$state" ensure_gcloud ""
  if [ "$status" -ne 0 ]; then ok; else bad "claimed to install gcloud without apt or Homebrew"; fi
  contains "$state/out" "https://cloud.google.com/sdk/docs/install"

  # Present already: nothing is installed.
  state="$(new_state tools-present)"
  mkdir -p "$state/bin"
  ln -sf "$FAKES/gcloud" "$state/bin/gcloud"
  with_tools "$state" ensure_gcloud apt-get
  equals "$status" 0 "exit status"
  if [ -e "$state/sudo.log" ]; then bad "installed something although gcloud is there"; else ok; fi

  # In WSL, sign-ins open the Windows browser through wslview, installed when missing.
  state="$(new_state tools-wsl)"
  with_tools "$state" use_windows_browser apt-get WSL_DISTRO_NAME=Ubuntu
  equals "$status" 0 "exit status"
  contains "$state/sudo.log" "apt-get install -y -q wslu"
  contains "$state/out" "BROWSER=wslview"

  # Outside WSL, BROWSER is left alone (checked only where these tests don't run in WSL).
  if ! grep -qi microsoft /proc/version 2>/dev/null; then
    state="$(new_state tools-not-wsl)"
    with_tools "$state" use_windows_browser apt-get
    equals "$status" 0 "exit status"
    if [ -e "$state/sudo.log" ]; then bad "installed wslu outside WSL"; else ok; fi
  fi
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

  state="$(new_state bootstrap-no-runtime-account)"
  rm "$state/res/iam_service-accounts_playable-anime-api"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" NEON_PRODUCTION_DATABASE_URL="$POOLED" \
    NEON_PRODUCTION_DATABASE_URL_DIRECT="$DIRECT" "$INFRA/bootstrap.sh" --yes
  if [ "$status" -ne 0 ]; then ok; else bad "went on without the runtime account"; fi
  contains "$out" "runtime service account playable-anime-api@playable-anime.iam.gserviceaccount.com is missing"
  lacks "$state/calls.log" " create " "created something without the runtime account"

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
  lacks "$out" "allow-unauthenticated" "the service deploy leaves access to the access step"
  lacks "$out" "invoker-iam-check" "the service deploy leaves access to the access step"
  contains "$out" 'GOOGLE_OAUTH_CLIENT_IDS: "528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com,528988811295-c2t6dchelulruu7hgl4mem4kr733d346.apps.googleusercontent.com"'
  # The dry run's output is public in the Actions log, so it names the secret, not the emails.
  contains "$out" 'OWNER_EMAILS: "<the OWNER_EMAILS secret>"'
  lacks "$out" "owner@example.com" "a dry run printed the owner's email"

  out="$state/out-access"
  with_fakes "$out" env FAKE_STATE="$state" DRY_RUN=1 "$INFRA/deploy.sh" access
  equals "$status" 0 "access exit status"
  contains "$out" "[dry-run] gcloud run services add-iam-policy-binding playable-anime-api --project=playable-anime --region=europe-west3 --member=allUsers --role=roles/run.invoker"

  out="$state/out-covers"
  with_fakes "$out" env FAKE_STATE="$state" DRY_RUN=1 "$INFRA/deploy.sh" covers
  equals "$status" 0 "covers exit status"
  contains "$out" "[dry-run] gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,draw_premise_covers --task-timeout=30m --wait"
  if [ -e "$state/calls.log" ]; then bad "a dry run called gcloud"; else ok; fi
}

test_deploy_settings() {
  local state out
  start "deploy.sh gives the API the Google client ids, keeps them out of env.yaml, names the API"
  state="$(new_state deploy-settings)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  equals "$status" 0 "migrate exit status"
  contains "$state/last-env.yaml" 'GOOGLE_OAUTH_CLIENT_IDS: "528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com,528988811295-c2t6dchelulruu7hgl4mem4kr733d346.apps.googleusercontent.com"'
  lacks "$INFRA/config.sh" "GOCSPX" "an OAuth client secret must never be committed"
  # The owner's emails (K7) come from the OWNER_EMAILS secret, never from the public repo.
  contains "$state/last-env.yaml" 'OWNER_EMAILS: "owner@example.com"'
  contains "$state/last-env.yaml" 'RELEASES_BUCKET: "playable-anime-releases"'
  if grep -q '^OWNER_EMAILS:' "$INFRA/cloudrun/env.yaml"; then
    bad "env.yaml sets OWNER_EMAILS; the owner's emails belong in the OWNER_EMAILS secret"
  else ok; fi
  lacks "$INFRA/cloudrun/env.yaml" "@" "no email address belongs in env.yaml"

  # Without the secret, or with something that isn't a list of addresses, nothing is deployed.
  : >"$state/calls.log"
  out="$state/out-no-owner"
  with_fakes "$out" env FAKE_STATE="$state" OWNER_EMAILS= "$INFRA/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "deployed without OWNER_EMAILS"; fi
  contains "$out" "OWNER_EMAILS is empty"
  lacks "$state/calls.log" "run jobs deploy" "the job was deployed without OWNER_EMAILS"
  out="$state/out-bad-owner"
  with_fakes "$out" env FAKE_STATE="$state" OWNER_EMAILS='owner@example.com: x' \
    "$INFRA/deploy.sh" service europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "accepted an OWNER_EMAILS that could break out of the env vars file"; fi
  contains "$out" "isn't an email address"
  lacks "$state/calls.log" "run deploy" "the service was deployed with a bad OWNER_EMAILS"
  out="$state/out-two-owners"
  with_fakes "$out" env FAKE_STATE="$state" OWNER_EMAILS=' a@example.com, b.c+d@example.org ' \
    "$INFRA/deploy.sh" migrate europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  equals "$status" 0 "migrate with two owners"
  contains "$state/last-env.yaml" 'OWNER_EMAILS: "a@example.com,b.c+d@example.org"'

  # A copy of infra/ whose env.yaml sets a variable deploy.sh owns.
  cp -R "$INFRA" "$state/infra"
  printf 'GOOGLE_OAUTH_CLIENT_IDS: "x"\n' >>"$state/infra/cloudrun/env.yaml"
  out="$state/out-owned"
  with_fakes "$out" env FAKE_STATE="$state" "$state/infra/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "env.yaml was allowed to set GOOGLE_OAUTH_CLIENT_IDS"; fi
  contains "$out" "sets a variable that deploy.sh owns"

  # And one whose config has a client id that could break out of the env vars file.
  sed -i.bak 's/^GOOGLE_IOS_CLIENT_ID=""/GOOGLE_IOS_CLIENT_ID="abc: x"/' "$state/infra/config.sh"
  sed -i.bak '/^GOOGLE_OAUTH_CLIENT_IDS/d' "$state/infra/cloudrun/env.yaml"
  : >"$state/calls.log"
  out="$state/out-bad"
  with_fakes "$out" env FAKE_STATE="$state" "$state/infra/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "accepted a client id with a colon and a space in it"; fi
  contains "$out" "Google client id with odd characters"
  lacks "$state/calls.log" "jobs deploy" "deployed with a bad client id"

  out="$state/out-outputs"
  with_fakes "$out" env FAKE_STATE="$state" GITHUB_OUTPUT="$state/outputs" "$INFRA/deploy.sh" github-outputs
  contains "$state/outputs" "api_url=https://playable-anime-api-528988811295.europe-west3.run.app"
  contains "$state/outputs" "apk_asset=lucid-saga.apk"
}

test_access() {
  local state out
  start "deploy.sh access makes the API public by default, private on request, and stops on typos"
  state="$(new_state access)"
  with_fakes "$state/out-0" env FAKE_STATE="$state" "$INFRA/deploy.sh" service \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:one
  equals "$status" 0 "first deploy exit status"
  out="$state/out-1"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" access
  equals "$status" 0 "public exit status"
  contains "$state/calls.log" "gcloud run services add-iam-policy-binding playable-anime-api --project=playable-anime --region=europe-west3 --member=allUsers --role=roles/run.invoker"
  if [ -e "$state/public" ]; then ok; else bad "the API is not public"; fi

  out="$state/out-2"
  with_fakes "$out" env FAKE_STATE="$state" API_ACCESS=private "$INFRA/deploy.sh" access
  equals "$status" 0 "private exit status"
  contains "$state/calls.log" "gcloud run services remove-iam-policy-binding playable-anime-api --project=playable-anime --region=europe-west3 --member=allUsers --role=roles/run.invoker"
  if [ -e "$state/public" ]; then bad "the API is still public"; else ok; fi

  : >"$state/calls.log"
  out="$state/out-3"
  with_fakes "$out" env FAKE_STATE="$state" API_ACCESS=private "$INFRA/deploy.sh" access
  equals "$status" 0 "private again exit status"
  lacks "$state/calls.log" "remove-iam-policy-binding" "removed a binding that wasn't there"
  contains "$out" "already private"

  out="$state/out-4"
  with_fakes "$out" env FAKE_STATE="$state" API_ACCESS=Public "$INFRA/deploy.sh" access
  if [ "$status" -ne 0 ]; then ok; else bad "accepted API_ACCESS=Public"; fi
  contains "$out" "API_ACCESS must be public or private"

  out="$state/out-5"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_ACCESS=1 "$INFRA/deploy.sh" access
  if [ "$status" -ne 0 ]; then ok; else bad "a refused binding passed"; fi

  # The policy can't be read (here: no service): private must fail, never assume it is closed.
  state="$(new_state access-unreadable)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" API_ACCESS=private "$INFRA/deploy.sh" access
  if [ "$status" -ne 0 ]; then ok; else bad "passed without reading who may call the API"; fi
  contains "$out" "can't read who may call playable-anime-api"
  lacks "$out" "already private" "claimed the API is private without knowing"

  out="$state/out-dry"
  with_fakes "$out" env FAKE_STATE="$state" API_ACCESS=private DRY_RUN=1 "$INFRA/deploy.sh" access
  equals "$status" 0 "private dry run exit status"
  contains "$out" "[dry-run] gcloud run services remove-iam-policy-binding playable-anime-api"
}

test_covers() {
  local state out
  start "deploy.sh covers runs draw_premise_covers as the migration job and fails loudly"
  state="$(new_state covers)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" covers
  equals "$status" 0 "covers exit status"
  contains "$state/calls.log" "gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py\\,draw_premise_covers --task-timeout=30m --wait"
  out="$state/out-fail"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_COVERS=1 "$INFRA/deploy.sh" covers
  if [ "$status" -ne 0 ]; then ok; else bad "failed covers passed"; fi
  contains "$state/calls.log" "gcloud logging read resource.type=\\\"cloud_run_job\\\"\\ AND\\ resource.labels.job_name=\\\"playable-anime-migrate\\\"\\ AND\\ timestamp\\>=\\\"20"
  contains "$out" "fake-log-line Model call rejected" "a failed job prints its own logs"

  # Without roles/logging.viewer, it says how to read them instead.
  out="$state/out-no-logs"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_COVERS=1 FAKE_FAIL_LOGS=1 \
    "$INFRA/deploy.sh" covers
  if [ "$status" -ne 0 ]; then ok; else bad "failed covers passed"; fi
  contains "$out" "the deployer needs roles/logging.viewer"
  contains "$out" "Read them with: gcloud logging read"
}

test_models() {
  local state out
  start "deploy.sh models calls each model as the migration job and prints the job's logs on failure"
  state="$(new_state models)"
  out="$state/out-dry"
  with_fakes "$out" env FAKE_STATE="$state" DRY_RUN=1 "$INFRA/deploy.sh" models
  equals "$status" 0 "dry-run models exit status"
  contains "$out" "[dry-run] gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,check_models --task-timeout=10m --wait"
  if [ -e "$state/calls.log" ]; then bad "a dry run called gcloud"; else ok; fi

  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" models
  equals "$status" 0 "models exit status"
  contains "$state/calls.log" "gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py\\,check_models --task-timeout=10m --wait"
  lacks "$state/calls.log" "gcloud logging read" "logs are read only after a failure"

  out="$state/out-fail"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_MODELS=1 "$INFRA/deploy.sh" models
  if [ "$status" -ne 0 ]; then ok; else bad "a failed model check passed"; fi
  contains "$out" "The storyteller is unavailable"
  contains "$out" "fake-log-line Model call rejected" "a failed check prints the job's logs"
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

  out="$state/out-3"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_TRAFFIC_SPLIT=1 GITHUB_OUTPUT="$state/outputs-3" \
    "$INFRA/deploy.sh" service europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:three
  equals "$status" 0 "split-traffic deploy exit status"
  contains "$state/outputs-3" "previous_revision=major-rev" \
    "the rollback target must be the revision with the most traffic"

  out="$state/out-4"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_DEPLOY=1 GITHUB_OUTPUT="$state/outputs-4" \
    "$INFRA/deploy.sh" service europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:four
  if [ "$status" -ne 0 ]; then ok; else bad "a failed deploy passed"; fi
  contains "$state/outputs-4" "previous_revision=playable-anime-api-00003-abc" \
    "a failed deploy must still leave the rollback target for the workflow"
}

test_migration_failure() {
  local state out
  start "deploy.sh migrate fails loudly and points at the logs when the job fails"
  state="$(new_state deploy-migrate-fail)"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_MIGRATION=1 "$INFRA/deploy.sh" migrate \
    europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:abc
  if [ "$status" -ne 0 ]; then ok; else bad "a failed migration passed"; fi
  contains "$state/calls.log" "gcloud logging read"
  contains "$out" "fake-log-line Model call rejected" "a failed migration prints the job's logs"
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
  gate "!fail" "completed success https://github.com/run/7"
  equals "$status" 0 "a failed GitHub call is retried, not taken as an answer"
  gate "in_progress none https://github.com/run/5"
  if [ "$status" -ne 0 ]; then ok; else bad "CI that never finishes passed"; fi
  GATE_REF=refs/heads/feature gate "completed success https://github.com/run/6"
  if [ "$status" -ne 0 ]; then ok; else bad "a run from another branch passed"; fi
}

# A Flutter app with pubspec.yaml's version and an Android SDK whose apksigner is the fake one.
new_app() { # state
  mkdir -p "$1/app" "$1/sdk/build-tools/36.0.0"
  printf 'name: playable_anime\nversion: 1.2.3+4\n' >"$1/app/pubspec.yaml"
  ln -sf "$FAKES/apksigner" "$1/sdk/build-tools/36.0.0/apksigner"
}

build_apk() { # state out [env...]
  local state="$1" out="$2"
  shift 2
  mkdir -p "$state/tmp"
  with_fakes "$out" env FAKE_STATE="$state" APP_DIR="$state/app" ANDROID_HOME="$state/sdk" \
    TMPDIR="$state/tmp" \
    GITHUB_OUTPUT="$state/outputs" ANDROID_KEYSTORE_BASE64='' ANDROID_KEYSTORE_PASSWORD='' \
    ANDROID_KEY_ALIAS='' ANDROID_KEY_PASSWORD='' ANDROID_KEYSTORE_PATH='' "$@" \
    "$INFRA/build-apk.sh" "$state/dist/lucid-saga.apk"
}

test_build_apk() {
  local state out keystore
  start "build-apk.sh builds for the API, signs with the keystore or the debug key, and reports it"
  state="$(new_state build-apk-debug)"
  new_app "$state"
  out="$state/out"
  build_apk "$state" "$out" BUILD_NUMBER=42
  equals "$status" 0 "debug build exit status"
  contains "$state/flutter.log" "flutter build apk --release --dart-define=API_BASE_URL=https://playable-anime-api-528988811295.europe-west3.run.app --dart-define=GOOGLE_WEB_CLIENT_ID=528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com --dart-define=SELF_UPDATE=true --build-number=42"
  contains "$state/flutter.log" "ANDROID_KEYSTORE_PATH="
  lacks "$state/flutter.log" "ANDROID_KEYSTORE_PATH=/" "a debug build must not be given a keystore"
  if [ -f "$state/dist/lucid-saga.apk" ]; then ok; else bad "no APK at the given path"; fi
  contains "$state/outputs" "signing=debug"
  contains "$state/outputs" "sha1=DA:39:A3:EE:5E:6B:4B:0D:32:55:BF:EF:95:60:18:90:AF:D8:07:09"
  contains "$state/outputs" "version_name=1.2.3"
  contains "$state/outputs" "version_code=42"
  contains "$out" "signed with the debug key"

  state="$(new_state build-apk-release)"
  new_app "$state"
  out="$state/out"
  keystore="$(printf 'KEYSTORE-BYTES' | base64)"
  build_apk "$state" "$out" ANDROID_KEYSTORE_BASE64="$keystore" \
    ANDROID_KEYSTORE_PASSWORD=store-SENTINEL ANDROID_KEY_ALIAS=upload ANDROID_KEY_PASSWORD=key-SENTINEL
  equals "$status" 0 "release build exit status"
  contains "$state/flutter.log" "ANDROID_KEYSTORE_PATH=/"
  equals "$(cat "$state/keystore-seen" 2>/dev/null)" "KEYSTORE-BYTES" "the keystore Gradle is given"
  contains "$state/outputs" "signing=release"
  contains "$state/outputs" "version_code=4"
  lacks "$state/flutter.log" "--build-number" "no BUILD_NUMBER, so pubspec.yaml's"
  lacks "$out" "SENTINEL" "a signing password was printed"
  lacks "$state/flutter.log" "SENTINEL" "a signing password reached flutter's arguments"
  if [ -e "$state/keystore-seen" ] && [ -z "$(ls -A "$state/tmp")" ]; then
    ok
  else
    bad "the decoded keystore was left behind in TMPDIR, or never made"
  fi

  state="$(new_state build-apk-partial)"
  new_app "$state"
  out="$state/out"
  build_apk "$state" "$out" ANDROID_KEYSTORE_BASE64="$keystore" ANDROID_KEYSTORE_PASSWORD=x
  if [ "$status" -ne 0 ]; then ok; else bad "built with only some of the signing secrets"; fi
  contains "$out" "missing: ANDROID_KEY_ALIAS ANDROID_KEY_PASSWORD"
  if [ -e "$state/flutter.log" ]; then bad "ran flutter with half the signing secrets"; else ok; fi

  state="$(new_state build-apk-bad-number)"
  new_app "$state"
  build_apk "$state" "$state/out" BUILD_NUMBER=07
  if [ "$status" -ne 0 ]; then ok; else bad "accepted BUILD_NUMBER=07"; fi

  state="$(new_state build-apk-bad-signature)"
  new_app "$state"
  build_apk "$state" "$state/out" FAKE_BAD_SIGNATURE=1
  if [ "$status" -ne 0 ]; then ok; else bad "passed an APK whose signature doesn't verify"; fi

  state="$(new_state build-apk-flutter-fails)"
  new_app "$state"
  build_apk "$state" "$state/out" FAKE_FAIL_FLUTTER=1
  if [ "$status" -ne 0 ]; then ok; else bad "passed a failed flutter build"; fi
}

publish() { # responses... ; sets status
  local responses="$WORK/publish-responses"
  printf '%s\n' "$@" >"$responses"
  rm -f "$responses.calls" "$responses.notes"
  printf 'fake apk\n' >"$WORK/app-release.apk"
  with_fakes "$WORK/publish-out" env FAKE_GH_RESPONSES="$responses" \
    GITHUB_REPOSITORY=Mikigb77/PlayableAnime GITHUB_SHA=0123abc BUILD_NUMBER=42 VERSION_NAME=1.0.0 \
    SIGNING="${PUBLISH_SIGNING:-release}" SIGNING_SHA1=AA:BB GITHUB_STEP_SUMMARY="$WORK/summary" \
    "$INFRA/publish-apk.sh" "$WORK/app-release.apk"
}

test_publish_apk() {
  local calls="$WORK/publish-responses.calls" notes="$WORK/publish-responses.notes"
  start "publish-apk.sh makes the newest APK the latest release's lucid-saga.apk, once per run"
  # gh answers: the latest release's tag, then whether build-42 exists, then each change.
  publish "build-41" "!fail" "https://github.com/Mikigb77/PlayableAnime/releases/tag/build-42"
  equals "$status" 0 "first publish exit status"
  contains "$calls" "release view --repo Mikigb77/PlayableAnime --json tagName --jq .tagName"
  contains "$calls" "release view build-42 --repo Mikigb77/PlayableAnime"
  contains "$calls" "release create build-42 "
  contains "$calls" "/lucid-saga.apk --repo Mikigb77/PlayableAnime --target 0123abc --title Lucid Saga 1.0.0 (build 42)"
  contains "$calls" "--notes-file"
  if grep -q -- "--latest$" "$calls"; then ok; else bad "the newest build must be the latest release"; fi
  contains "$notes" "Signed with the release key, SHA-1 AA:BB"
  contains "$notes" "https://playable-anime-api-528988811295.europe-west3.run.app"
  contains "$WORK/summary" "https://github.com/Mikigb77/PlayableAnime/releases/latest/download/lucid-saga.apk"

  publish "!fail" "!fail" "ok"
  equals "$status" 0 "first release ever exit status"
  if grep -q -- "--latest$" "$calls"; then ok; else bad "the first release must be the latest"; fi

  publish "build-42" "{}" "ok" "ok"
  equals "$status" 0 "re-run publish exit status"
  contains "$calls" "release upload build-42 "
  contains "$calls" "--clobber"
  contains "$calls" "release edit build-42 --repo Mikigb77/PlayableAnime"
  if grep -q -- "--prerelease=false --latest$" "$calls"; then ok; else bad "a re-run of the newest must stay latest"; fi
  lacks "$calls" "release create" "a re-run must not create a second release"

  publish "build-43" "!fail" "ok"
  equals "$status" 0 "older run publish exit status"
  contains "$calls" "--latest=false"
  contains "$WORK/publish-out" "build-43 is newer than build-42"

  PUBLISH_SIGNING=debug publish "build-41" "!fail" "ok"
  equals "$status" 0 "debug publish exit status"
  contains "$notes" "Signed with a throwaway debug key"

  publish "build-41" "!fail" "!fail"
  if [ "$status" -ne 0 ]; then ok; else bad "a failed release passed"; fi
}

upload_apk() { # state out build [env...]
  local state="$1" out="$2" build="$3"
  shift 3
  printf 'fake apk %s\n' "$build" >"$state/app-$build.apk"
  with_fakes "$out" env FAKE_STATE="$state" BUILD_NUMBER="$build" VERSION_NAME=1.0.0 "$@" \
    "$INFRA/deploy.sh" upload-apk "$state/app-$build.apk"
}

manifest_field() { # state field
  python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' \
    "$1/gcs/playable-anime-releases/android/latest.json" "$2"
}

test_upload_apk() {
  local state out folder sha
  start "deploy.sh upload-apk offers the newest build to the installed apps and keeps three"
  state="$(new_state upload-apk)"
  folder="$state/gcs/playable-anime-releases/android"
  out="$state/out-12"
  upload_apk "$state" "$out" 12
  equals "$status" 0 "first upload exit status"
  contains "$state/calls.log" "gcloud storage cp $state/app-12.apk gs://playable-anime-releases/android/lucid-saga-12.apk --content-type=application/vnd.android.package-archive"
  contains "$state/composite.log" "gs://playable-anime-releases/android/lucid-saga-12.apk False" \
    "the APK must go up in one piece"
  equals "$(cat "$folder/lucid-saga-12.apk")" "fake apk 12" "the APK in the bucket"
  equals "$(manifest_field "$state" build)" 12 "the manifest's build"
  equals "$(manifest_field "$state" version)" 1.0.0 "the manifest's version"
  equals "$(manifest_field "$state" apk)" android/lucid-saga-12.apk "the manifest's APK"
  equals "$(manifest_field "$state" size)" "$(wc -c <"$state/app-12.apk" | tr -d ' ')" "the manifest's size"
  sha="$(python3 -I -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$state/app-12.apk")"
  equals "$(manifest_field "$state" sha256)" "$sha" "the manifest's SHA-256"
  contains "$state/calls.log" "--content-type=application/json --cache-control=no-store"
  lacks "$state/calls.log" "storage rm" "deleted a build with only one in the bucket"

  for build in 13 14 15; do upload_apk "$state" "$state/out-$build" "$build"; done
  equals "$status" 0 "fourth upload exit status"
  equals "$(manifest_field "$state" build)" 15 "the manifest names the newest build"
  if [ -e "$folder/lucid-saga-12.apk" ]; then bad "kept a fourth build"; else ok; fi
  for build in 13 14 15; do
    if [ -e "$folder/lucid-saga-$build.apk" ]; then ok; else bad "deleted build $build"; fi
  done

  # A re-run of an older run must not send phones back to an older build.
  : >"$state/calls.log"
  out="$state/out-older"
  upload_apk "$state" "$out" 14
  equals "$status" 0 "older upload exit status"
  contains "$out" "already offers build 15, newer than 14"
  lacks "$state/calls.log" "storage cp" "uploaded an older build"
  equals "$(manifest_field "$state" build)" 15 "the manifest after an older run"

  # Re-running the same run replaces its APK and its manifest.
  out="$state/out-same"
  upload_apk "$state" "$out" 15
  equals "$status" 0 "same-build upload exit status"
  contains "$state/calls.log" "android/lucid-saga-15.apk"

  # Before the bootstrap has made the bucket, the run fails and says why, with no manifest.
  state="$(new_state upload-apk-denied)"
  out="$state/out"
  upload_apk "$state" "$out" 16 FAKE_FAIL_UPLOAD=1
  if [ "$status" -ne 0 ]; then ok; else bad "went on after the upload was refused"; fi
  contains "$out" "Has infra/bootstrap.sh run since it gained step 6d?"
  if [ -e "$state/gcs/playable-anime-releases/android/latest.json" ]; then
    bad "wrote a manifest for an APK that isn't there"
  else ok; fi

  state="$(new_state upload-apk-bad)"
  upload_apk "$state" "$state/out-zero" 07
  if [ "$status" -ne 0 ]; then ok; else bad "accepted BUILD_NUMBER=07"; fi
  upload_apk "$state" "$state/out-version" 12 VERSION_NAME='1.0 "x"'
  if [ "$status" -ne 0 ]; then ok; else bad "accepted a version name with a quote in it"; fi
  if [ -e "$state/calls.log" ]; then
    lacks "$state/calls.log" "gcloud storage" "called gcloud storage with bad input"
  else ok; fi

  # A dry run uploads nothing and reads nothing.
  state="$(new_state upload-apk-dry)"
  out="$state/out"
  upload_apk "$state" "$out" 12 DRY_RUN=1
  equals "$status" 0 "dry-run upload exit status"
  contains "$out" "[dry-run] gcloud storage cp $state/app-12.apk gs://playable-anime-releases/android/lucid-saga-12.apk"
  if [ -e "$state/calls.log" ]; then bad "a dry run called gcloud"; else ok; fi
}

test_ops() {
  local state out
  start "ops.sh runs one gcloud command as written, refuses credentials, and keeps logs inert"
  state="$(new_state ops)"
  out="$state/out-outputs"
  with_fakes "$out" env FAKE_STATE="$state" GITHUB_OUTPUT="$state/outputs" "$INFRA/ops.sh" github-outputs
  equals "$status" 0 "github-outputs exit status"
  contains "$state/outputs" "wif_provider=projects/528988811295/locations/global/workloadIdentityPools/github-ops/providers/playable-anime-ops"
  contains "$state/outputs" "ops_sa=github-ops@playable-anime.iam.gserviceaccount.com"

  out="$state/out-default"
  with_fakes "$out" env FAKE_STATE="$state" OPS_COMMAND="" "$INFRA/ops.sh" run
  equals "$status" 0 "default command exit status"
  contains "$state/calls.log" "gcloud logging read severity\\>=WARNING\\ AND\\ \\(resource.type=\\\"cloud_run_revision\\\"\\ OR\\ resource.type=\\\"cloud_run_job\\\"\\) --freshness=3h --order=asc --limit=200"
  contains "$out" "::stop-commands::ops-"
  contains "$out" "fake-log-line Model call rejected"

  : >"$state/calls.log"
  out="$state/out-quoted"
  with_fakes "$out" env FAKE_STATE="$state" \
    OPS_COMMAND="gcloud logging read 'severity>=ERROR AND textPayload:\"a b\"' --limit=5; touch $state/pwned" \
    "$INFRA/ops.sh" run
  equals "$status" 0 "quoted command exit status"
  contains "$state/calls.log" "gcloud logging read severity\\>=ERROR\\ AND\\ textPayload:\\\"a\\ b\\\" --limit=5\\; touch"
  if [ -e "$state/pwned" ]; then bad "ops.sh ran shell syntax from the command"; else ok; fi

  : >"$state/calls.log"
  for refused in "auth print-access-token" "config set account x" \
    "run services describe x --impersonate-service-account=a@b" "projects list --account=x" \
    "secrets versions access latest --secret=django-secret-key" \
    "iam service-accounts keys create k.json --iam-account=x" "logging read 'unbalanced" \
    "projects list --log-http" "projects list --verbosity=debug" "beta auth print-identity-token" \
    "--quiet auth list" "beta --project=x config list"; do
    out="$state/out-refused"
    with_fakes "$out" env FAKE_STATE="$state" OPS_COMMAND="$refused" "$INFRA/ops.sh" run
    if [ "$status" -ne 0 ]; then ok; else bad "ops.sh ran: $refused"; fi
  done
  if [ -s "$state/calls.log" ]; then bad "a refused command reached gcloud"; else ok; fi

  out="$state/out-fail"
  with_fakes "$out" env FAKE_STATE="$state" FAKE_FAIL_LOGS=1 OPS_COMMAND="" "$INFRA/ops.sh" run
  if [ "$status" -ne 0 ]; then ok; else bad "a failed gcloud command passed"; fi
}

test_preflight() {
  local state out
  start "deploy.sh preflight checks the bootstrap and that OWNER_EMAILS is set"
  state="$(new_state preflight)"
  touch "$state/res/artifacts_repositories_playable-anime"
  out="$state/out"
  with_fakes "$out" env FAKE_STATE="$state" "$INFRA/deploy.sh" preflight
  equals "$status" 0 "preflight exit status"
  contains "$out" "Preflight passed"
  lacks "$out" "owner@example.com" "preflight printed the owner's email"
  out="$state/out-no-owner"
  with_fakes "$out" env FAKE_STATE="$state" OWNER_EMAILS= "$INFRA/deploy.sh" preflight
  if [ "$status" -ne 0 ]; then ok; else bad "preflight passed without OWNER_EMAILS"; fi
  contains "$out" "add the OWNER_EMAILS repository secret"
}

test_workflow_matches_scripts() {
  local wf="$ROOT/.github/workflows/deploy.yml" cmd
  start "deploy.yml uses only commands deploy.sh has"
  if [ -f "$wf" ]; then ok; else bad "missing $wf"; fi
  grep -oE 'infra/deploy\.sh [a-z-]+' "$wf" | awk '{print $2}' | sort -u >"$WORK/workflow-commands"
  while read -r cmd; do
    if "$INFRA/deploy.sh" --help | grep -qE "^  $cmd( |$)"; then ok; else bad "deploy.sh has no '$cmd'"; fi
  done <"$WORK/workflow-commands"
  wf="$ROOT/.github/workflows/ops.yml"
  if [ -f "$wf" ]; then ok; else bad "missing $wf"; fi
  grep -oE 'infra/ops\.sh [a-z-]+' "$wf" | awk '{print $2}' | sort -u >"$WORK/ops-commands"
  while read -r cmd; do
    if "$INFRA/ops.sh" --help | grep -qE "^  $cmd( |$)"; then ok; else bad "ops.sh has no '$cmd'"; fi
  done <"$WORK/ops-commands"
  contains "$wf" "OPS_COMMAND: \${{ inputs.command }}" "the command reaches ops.sh only through the environment"
  wf="$ROOT/.github/workflows/deploy.yml"
  contains "$wf" "infra/require-green-ci.sh"
  if [ "$(grep -cF "OWNER_EMAILS: \${{ secrets.OWNER_EMAILS }}" "$wf")" -eq 3 ]; then ok; else
    bad "deploy.yml must pass the OWNER_EMAILS secret to preflight, migrate and service"
  fi
  contains "$wf" "infra/build-apk.sh"
  contains "$wf" "infra/publish-apk.sh"
  contains "$wf" "infra/deploy.sh upload-apk"
  contains "$ROOT/.github/workflows/ci.yml" "infra/build-apk.sh"
  contains "$ROOT/README.md" "https://github.com/Mikigb77/PlayableAnime/releases/latest/download/lucid-saga.apk"
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
test_bootstrap_reads_neon_urls
test_bootstrap_rejects_bad_input
test_bootstrap_signs_in
test_tools_install
test_deploy_dry_run
test_deploy_settings
test_preflight
test_deploy_service
test_access
test_covers
test_models
test_ops
test_migration_failure
test_smoke
test_rollback
test_ci_gate
test_build_apk
test_publish_apk
test_upload_apk
test_workflow_matches_scripts
test_docs_list_every_command

printf '\n%d checks passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
