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
  contains "$out" "(assertion.event_name == '\\''push'\\'' || assertion.event_name == '\\''workflow_dispatch'\\'')"
  contains "$out" "Mikigb77/PlayableAnime/.github/workflows/deploy.yml@refs/heads/main"
  contains "$out" "[dry-run] gcloud iam roles create lucidSagaApiAccess --project=playable-anime"
  contains "$out" "--permissions=run.services.getIamPolicy,run.services.setIamPolicy --stage=GA"
  contains "$out" "--member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=projects/playable-anime/roles/lucidSagaApiAccess"
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
  contains "$out" "gcloud logging read"
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
  contains "$state/flutter.log" "flutter build apk --release --dart-define=API_BASE_URL=https://playable-anime-api-528988811295.europe-west3.run.app --dart-define=GOOGLE_WEB_CLIENT_ID=528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com --build-number=42"
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

test_workflow_matches_scripts() {
  local wf="$ROOT/.github/workflows/deploy.yml" cmd
  start "deploy.yml uses only commands deploy.sh has"
  if [ -f "$wf" ]; then ok; else bad "missing $wf"; fi
  grep -oE 'infra/deploy\.sh [a-z-]+' "$wf" | awk '{print $2}' | sort -u >"$WORK/workflow-commands"
  while read -r cmd; do
    if "$INFRA/deploy.sh" --help | grep -qE "^  $cmd( |$)"; then ok; else bad "deploy.sh has no '$cmd'"; fi
  done <"$WORK/workflow-commands"
  contains "$wf" "infra/require-green-ci.sh"
  contains "$wf" "infra/build-apk.sh"
  contains "$wf" "infra/publish-apk.sh"
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
test_deploy_dry_run
test_deploy_settings
test_deploy_service
test_access
test_covers
test_migration_failure
test_smoke
test_rollback
test_ci_gate
test_build_apk
test_publish_apk
test_workflow_matches_scripts
test_docs_list_every_command

printf '\n%d checks passed, %d failed\n' "$passed" "$failed"
[ "$failed" -eq 0 ]
