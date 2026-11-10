#!/usr/bin/env bash
# The steps of .github/workflows/deploy.yml, one subcommand each. See docs/DEPLOY.md.
#
# The workflow runs these as the deployer service account. They also run from a laptop signed in to
# gcloud, as a fallback. DRY_RUN=1 prints every command that would change something and runs none.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/lib.sh
. "$HERE/lib.sh"
# shellcheck source=infra/config.sh
. "$HERE/config.sh"

ENV_FILE="$HERE/cloudrun/env.yaml"
SERVICE_SECRETS="DATABASE_URL=${SECRET_DATABASE_URL}:latest,DJANGO_SECRET_KEY=${SECRET_DJANGO_KEY}:latest"
MIGRATE_SECRETS="DATABASE_URL=${SECRET_DATABASE_URL_DIRECT}:latest,DJANGO_SECRET_KEY=${SECRET_DJANGO_KEY}:latest"

usage() {
  cat <<'EOF'
Usage: infra/deploy.sh <command> [argument]

  github-outputs   Write the names from infra/config.sh as step outputs.
  preflight        Check, read-only, that bootstrap.sh has run and this account can deploy.
  migrate IMAGE    Run `python manage.py migrate` as a Cloud Run job over the direct database URL.
  service IMAGE    Deploy IMAGE to the API service and send all traffic to it.
  smoke URL        Check that URL/health answers 200. Uses SMOKE_ID_TOKEN when the service is private.
  access           Make the API public, or private with API_ACCESS=private.
  models           Call each model the app uses once, as the migration job (check_models).
  covers           Draw the starter premises' missing covers, as the migration job.
  redraw           Draw story pictures from an older house style again, as the migration job.
  export           Seal the owner's own stories to EXPORT_KEY, as the migration job, and print a
                   short-lived link to the sealed file, or delete it with EXPORT_KEY=forget
                   (docs/DEPLOY.md#reading-the-owners-own-stories).
  upload-apk APK   Upload the Android app for its own updater and point android/latest.json at it.
  rollback REV     Send all traffic back to revision REV.

IMAGE is a full image reference, best pinned by digest. DRY_RUN=1 prints instead of running.
API_ACCESS=private keeps the API private (docs/DEPLOY.md#who-may-call-the-api).
upload-apk reads BUILD_NUMBER and VERSION_NAME, as infra/build-apk.sh reports them.
EOF
}

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lucid-deploy.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

commit_sha() {
  if [ -n "${GITHUB_SHA:-}" ]; then
    printf '%s' "$GITHUB_SHA"
  else
    git -C "$HERE" rev-parse HEAD 2>/dev/null || printf 'unknown'
  fi
}

deploy_labels() {
  local by=manual
  if [ "${GITHUB_ACTIONS:-}" = true ]; then
    by=github-actions
  fi
  printf 'deployed-by=%s,commit-sha=%s' "$by" "$(commit_sha)"
}

# Saves the service's description as JSON to the file $1: {} if it doesn't exist yet, or in a
# dry run. One call serves every field the deploy needs.
describe_service() {
  read_value gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --format=json >"$1"
  if [ ! -s "$1" ]; then
    printf '{}' >"$1"
  fi
}

# Reads one field from a saved description:
#   serving  the revision with the largest share of traffic, so a rollback returns to it
#   hosts    the deterministic hostname, which exists before the first deploy, then every URL
#            Cloud Run reports, comma-separated
#   url      the service's URL
service_field() {
  python3 -I - "$1" "$2" "$SERVICE_DETERMINISTIC_HOST" <<'EOF'
import json
import sys

path, field, deterministic_host = sys.argv[1:4]
try:
    with open(path) as file:
        service = json.load(file)
except ValueError:
    service = {}
status = service.get("status") or {}
if field == "serving":
    routes = [r for r in status.get("traffic") or [] if r.get("revisionName") and r.get("percent")]
    print(max(routes, key=lambda r: r["percent"])["revisionName"] if routes else "")
elif field == "hosts":
    annotations = (service.get("metadata") or {}).get("annotations") or {}
    urls = json.loads(annotations.get("run.googleapis.com/urls") or "[]") + [status.get("url") or ""]
    hosts = [deterministic_host]
    for url in urls:
        host = url.removeprefix("https://").split("/")[0]
        if host and host not in hosts:
            hosts.append(host)
    print(",".join(hosts))
elif field == "url":
    print(status.get("url") or "")
else:
    sys.exit(f"unknown field {field}")
EOF
}

# Prints the OAuth client ids from infra/config.sh that the API accepts Google ID tokens for (T8),
# comma-separated, and stops on anything that isn't a client id.
google_client_ids() {
  local id ids=''
  for id in "$GOOGLE_WEB_CLIENT_ID" "$GOOGLE_ANDROID_CLIENT_ID" "$GOOGLE_IOS_CLIENT_ID"; do
    check_client_id "$id"
    if [ -n "$id" ]; then
      ids="${ids:+$ids,}$id"
    fi
  done
  printf '%s' "$ids"
}

# Prints the owner's emails (K7) from the OWNER_EMAILS environment variable, which the deploy
# workflow fills from the repository secret of that name, and stops when it is empty or isn't a
# comma-separated list of plain addresses. They come from a secret only to keep them out of the
# public repo: they aren't credentials, since the owner role also needs that Google account.
owner_emails() {
  local list="${OWNER_EMAILS:-}" email
  local -a emails
  list="${list//[[:space:]]/}"
  if [ -z "$list" ]; then
    die "OWNER_EMAILS is empty: add the OWNER_EMAILS repository secret (docs/DEPLOY.md#7-the-owner-email), or export it for a deploy from a laptop"
  fi
  IFS=, read -r -a emails <<<"$list"
  for email in "${emails[@]}"; do
    if ! [[ "$email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
      die "OWNER_EMAILS holds something that isn't an email address"
    fi
  done
  printf '%s' "$list"
}

# Writes the env vars file for a deploy: infra/cloudrun/env.yaml plus the values this script owns.
render_env() {
  local hosts="$1" out="$TMP_DIR/env-$RANDOM.yaml" origins client_ids owners
  if grep -Eq '^(GCP_PROJECT|MEDIA_BUCKET|RELEASES_BUCKET|ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|GOOGLE_OAUTH_CLIENT_IDS|OWNER_EMAILS|DATABASE_URL|DJANGO_SECRET_KEY):' "$ENV_FILE"; then
    die "$ENV_FILE sets a variable that deploy.sh owns; remove it from the file"
  fi
  origins="$(printf '%s' "$hosts" | sed 's#\([^,][^,]*\)#https://\1#g')"
  # Command substitutions don't inherit set -e, so a bad id must stop this one by hand.
  client_ids="$(google_client_ids)" || exit 1
  owners="$(owner_emails)" || exit 1
  {
    cat "$ENV_FILE"
    printf '\n# Added by infra/deploy.sh\n'
    printf 'GCP_PROJECT: "%s"\n' "$PROJECT_ID"
    printf 'MEDIA_BUCKET: "%s"\n' "$MEDIA_BUCKET"
    printf 'RELEASES_BUCKET: "%s"\n' "$RELEASES_BUCKET"
    printf 'ALLOWED_HOSTS: "%s"\n' "$hosts"
    printf 'CSRF_TRUSTED_ORIGINS: "%s"\n' "$origins"
    if [ -n "$client_ids" ]; then
      printf 'GOOGLE_OAUTH_CLIENT_IDS: "%s"\n' "$client_ids"
    fi
    printf 'OWNER_EMAILS: "%s"\n' "$owners"
  } >"$out"
  if is_dry_run; then
    # The owner's emails stay out of the output, which is public in the Actions log.
    say "[dry-run] env vars file $out:"
    grep -Ev '^[[:space:]]*(#|$)' "$out" |
      sed -e 's/^OWNER_EMAILS: .*/OWNER_EMAILS: "<the OWNER_EMAILS secret>"/' -e 's/^/[dry-run]   /' >&2
  fi
  printf '%s' "$out"
}

need_arg() {
  [ -n "${1:-}" ] || {
    usage >&2
    die "$2 is missing"
  }
}

cmd_github_outputs() {
  set_output project_id "$PROJECT_ID"
  set_output region "$REGION"
  set_output wif_provider "$WIF_PROVIDER_RESOURCE"
  set_output deployer_sa "$DEPLOYER_SA"
  set_output registry_host "$REGISTRY_HOST"
  set_output image "$IMAGE"
  set_output service "$SERVICE"
  set_output api_url "$API_URL"
  set_output apk_asset "$APK_ASSET"
}

# Read-only, so it also runs in a dry run: it proves the workflow can sign in and see the setup.
cmd_preflight() {
  local account
  account="$(gcloud config get-value account 2>/dev/null || true)"
  say "Signed in as ${account:-an unknown account}."
  gcloud artifacts repositories describe "$AR_REPO" --project="$PROJECT_ID" --location="$REGION" \
    --format='value(name)' >/dev/null ||
    die "can't see the Artifact Registry repository $AR_REPO; has infra/bootstrap.sh run?"
  gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID" \
    --format='value(email)' >/dev/null ||
    die "can't see the runtime service account $RUNTIME_SA; has infra/bootstrap.sh run?"
  owner_emails >/dev/null
  say "Preflight passed: the image repository, the runtime service account and OWNER_EMAILS are in place."
}

# The migration job's log lines since $1 (an RFC 3339 time), oldest first, for a run that failed.
# Needs roles/logging.viewer, which the bootstrap gives the deployer; without it, says how to read
# them instead. Lines are the job's output and its JSON logs, which never hold a secret (T6).
job_logs() {
  local since="$1" filter
  filter="resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$MIGRATE_JOB\" AND timestamp>=\"$since\""
  # Cloud Logging takes a few seconds to show a line.
  sleep "${LOGS_WAIT_SECONDS:-20}"
  say "The job's logs:"
  if ! gcloud logging read "$filter" --project="$PROJECT_ID" --order=asc --limit=200 \
    --format='value(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.llm,jsonPayload.stack_trace)' >&2; then
    say "They couldn't be read here (the deployer needs roles/logging.viewer; re-run the bootstrap)."
    say "Read them with: $(quote_cmd gcloud logging read "$filter" --project="$PROJECT_ID" --order=asc --limit=200)"
  fi
}

# Runs the migration job once with other arguments ($1, comma-separated) and waits for it.
execute_job() {
  run gcloud run jobs execute "$MIGRATE_JOB" --project="$PROJECT_ID" --region="$REGION" \
    --args="$1" --task-timeout="$2" --wait
}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

cmd_migrate() {
  local image="$1" env_file since
  need_arg "$image" IMAGE
  env_file="$(render_env "$SERVICE_DETERMINISTIC_HOST")"
  step "Migrations: job $MIGRATE_JOB over the direct database URL (T2, B2)"
  run gcloud run jobs deploy "$MIGRATE_JOB" --project="$PROJECT_ID" --region="$REGION" \
    --image="$image" --service-account="$RUNTIME_SA" \
    --command=python --args=manage.py,migrate,--noinput \
    --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=10m --cpu=1 --memory=1Gi \
    --env-vars-file="$env_file" --set-secrets="$MIGRATE_SECRETS" --labels="$(deploy_labels)"
  since="$(now_utc)"
  if ! run gcloud run jobs execute "$MIGRATE_JOB" --project="$PROJECT_ID" --region="$REGION" --wait; then
    say "The migration failed, so the service was not deployed and still runs the old code."
    job_logs "$since"
    exit 1
  fi
}

cmd_service() {
  local image="$1" before="$TMP_DIR/before.json" after="$TMP_DIR/after.json" previous hosts
  local new_hosts env_file url
  need_arg "$image" IMAGE
  describe_service "$before"
  previous="$(service_field "$before" serving)"
  hosts="$(service_field "$before" hosts)"
  # Written first, so the workflow can roll back if anything fails once traffic may have moved.
  set_output previous_revision "$previous"
  env_file="$(render_env "$hosts")"
  step "Service $SERVICE in $REGION (T1, B10)"
  # Min 0 and max 3 instances, 300 s for streamed turns, startup CPU boost. No IAM flags: who may
  # call the API is the access step's job (docs/DEPLOY.md#who-may-call-the-api).
  run gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --image="$image" --service-account="$RUNTIME_SA" \
    --cpu=1 --memory=1Gi --concurrency=80 --min-instances=0 --max-instances=3 \
    --timeout=300 --cpu-boost --port=8080 \
    --env-vars-file="$env_file" --set-secrets="$SERVICE_SECRETS" --update-labels="$(deploy_labels)"
  describe_service "$after"
  new_hosts="$(service_field "$after" hosts)"
  if [ "$new_hosts" != "$hosts" ]; then
    # Only on the first deploy: Cloud Run has just given the service its other URL.
    say "Allowing the service's new URLs: $new_hosts"
    env_file="$(render_env "$new_hosts")"
    run gcloud run services update "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
      --env-vars-file="$env_file"
  fi
  # A rollback pins traffic to an old revision; a deploy always moves it to the new one.
  run gcloud run services update-traffic "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --to-latest
  url="$(service_field "$after" url)"
  set_output url "${url:-https://$SERVICE_DETERMINISTIC_HOST}"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    # shellcheck disable=SC2016 # The backticks are Markdown.
    {
      printf '| | |\n| --- | --- |\n'
      printf '| Image | `%s` |\n' "$image"
      printf '| Previous revision | `%s` |\n' "${previous:-none}"
      printf '| URL | %s |\n' "${url:-dry run}"
    } >>"$GITHUB_STEP_SUMMARY"
  fi
}

cmd_smoke() {
  local url="$1" attempt=1 code headers="$TMP_DIR/headers" body="$TMP_DIR/body"
  need_arg "$url" URL
  : >"$headers"
  if [ -n "${SMOKE_ID_TOKEN:-}" ]; then
    printf 'Authorization: Bearer %s\n' "$SMOKE_ID_TOKEN" >"$headers"
  fi
  step "Smoke test: GET $url/health"
  if is_dry_run; then
    say "[dry-run] curl $url/health"
    return 0
  fi
  while :; do
    code="$(curl --silent --show-error --output "$body" --write-out '%{http_code}' \
      --max-time 10 --header "@$headers" "$url/health" || true)"
    if [ "$code" = 200 ]; then
      say "/health answered 200."
      return 0
    fi
    say "/health answered ${code:-nothing} (attempt $attempt of ${SMOKE_ATTEMPTS:-6})."
    if [ "$attempt" -ge "${SMOKE_ATTEMPTS:-6}" ]; then
      head -c 500 "$body" >&2 2>/dev/null || true
      printf '\n' >&2
      case "$code" in
        400) say "A 400 here usually means Django rejected the host: check ALLOWED_HOSTS." ;;
        401 | 403) say "A $code means the smoke test's ID token was refused." ;;
      esac
      return 1
    fi
    attempt=$((attempt + 1))
    sleep "${SMOKE_SLEEP_SECONDS:-5}"
  done
}

# Whether allUsers may call the service now, from its IAM policy. Stops when the policy can't be
# read: taking that as "private" would leave a public API open while saying it is closed.
public_now() {
  local policy="$TMP_DIR/policy.json"
  if is_dry_run; then
    say "[dry-run] $(quote_cmd gcloud run services get-iam-policy "$SERVICE" \
      --project="$PROJECT_ID" --region="$REGION" --format=json)"
    return 0
  fi
  gcloud run services get-iam-policy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --format=json >"$policy" || die "can't read who may call $SERVICE, so it may still be public"
  python3 -I - "$policy" <<'EOF'
import json
import sys

with open(sys.argv[1]) as file:
    policy = json.load(file)
bindings = policy.get("bindings") or []
public = any(
    b.get("role") == "roles/run.invoker" and "allUsers" in (b.get("members") or []) for b in bindings
)
sys.exit(0 if public else 1)
EOF
}

# Who may call the API (docs/DEPLOY.md#who-may-call-the-api). Public by default, so the app can
# reach it; every request still needs a signed-in player except /health and sign-in (T8).
cmd_access() {
  local access="${API_ACCESS:-public}"
  case "$access" in
    public)
      step "Access: anyone may call $SERVICE; the API checks who is signed in (T8)"
      run_retry gcloud run services add-iam-policy-binding "$SERVICE" --project="$PROJECT_ID" \
        --region="$REGION" --member=allUsers --role=roles/run.invoker --format=none
      ;;
    private)
      step "Access: only callers with IAM access may call $SERVICE (API_ACCESS=private)"
      if public_now; then
        run gcloud run services remove-iam-policy-binding "$SERVICE" --project="$PROJECT_ID" \
          --region="$REGION" --member=allUsers --role=roles/run.invoker --format=none
      else
        say "The service is already private."
      fi
      ;;
    *) die "API_ACCESS must be public or private, not '$access'" ;;
  esac
}

# Draws the starter premises' covers that are missing, as the migration job with other arguments
# (S1, M4). Covers that exist are skipped, so after the first run this costs only the job's start.
cmd_covers() {
  local since
  step "Starter covers: job $MIGRATE_JOB runs draw_premise_covers"
  since="$(now_utc)"
  if ! execute_job manage.py,draw_premise_covers 30m; then
    say "Some covers weren't drawn; Discover shows the genre's glow for them until the next deploy."
    job_logs "$since"
    exit 1
  fi
}

# Draws the story pictures drawn in an older house style again in the current one (S7, M4), as the
# migration job with other arguments. Once all are current, this costs only the job's start. A run
# spends at most $5 and starts no drawing after 45 minutes; the next deploy draws the rest.
cmd_redraw() {
  local since
  step "Story pictures: job $MIGRATE_JOB runs redraw_pictures"
  since="$(now_utc)"
  if ! execute_job manage.py,redraw_pictures 60m; then
    say "Some pictures weren't drawn again; they keep their old drawing until the next deploy."
    job_logs "$since"
    exit 1
  fi
}

# Calls each model the app uses once, on the service's settings and account (B6, T13), so a model
# Vertex AI refuses fails the deploy run with its reason instead of failing players' turns.
cmd_models() {
  local since
  step "Models: job $MIGRATE_JOB runs check_models"
  since="$(now_utc)"
  if ! execute_job manage.py,check_models 10m; then
    say "A model the app uses didn't answer, so players see \"The storyteller is unavailable\"."
    job_logs "$since"
    exit 1
  fi
}

# Hands the owner's own stories (K7) to whoever holds the private key of EXPORT_KEY, as the
# migration job with other arguments (T16). The job seals them and stores the file in the private
# pictures bucket; its log, printed here, ends with a signed link that works for 30 minutes. The
# link and this log are public, and the file opens only with the reader's private key. The key
# goes to the job as one argument, so only its exact alphabet is let through. EXPORT_KEY=forget
# deletes the stored file instead, once the reader has it.
cmd_export() {
  local key="${EXPORT_KEY:-}" args since
  if [ "$key" = forget ]; then
    args=manage.py,export_owner_stories,--forget
    step "The owner's own stories: job $MIGRATE_JOB deletes the stored sealed file"
  elif [[ "$key" =~ ^[A-Za-z0-9_-]{43}$ ]]; then
    args="manage.py,export_owner_stories,--key=$key"
    step "The owner's own stories, sealed for one reader: job $MIGRATE_JOB runs export_owner_stories"
  else
    die "EXPORT_KEY must be the reader's public key, as 'python -m stories.sealed keygen' prints it, or 'forget'"
  fi
  since="$(now_utc)"
  if ! execute_job "$args" 10m; then
    say "The export job failed."
    job_logs "$since"
    exit 1
  fi
  # The job's own lines: how much it sealed and the link, or that the file is deleted.
  if ! is_dry_run; then
    job_logs "$since"
  fi
}

# Prints the build number in the release manifest on stdin, or 0 when there is none to read.
manifest_build() {
  python3 -I -c '
import json
import sys

try:
    build = json.load(sys.stdin).get("build")
except (ValueError, AttributeError):
    build = None
print(build if type(build) is int and build > 0 else 0)
'
}

# Prints the URLs of the builds in a listing of the bucket's android/ folder (stdin) that go: all
# but the newest $1, and never build $2, the one just published.
old_builds() {
  python3 -I -c '
import re
import sys

keep, newest = int(sys.argv[1]), int(sys.argv[2])
builds = {}
for line in sys.stdin:
    match = re.fullmatch(r"gs://[^/]+/android/lucid-saga-([1-9][0-9]*)\.apk", line.strip())
    if match:
        builds[int(match.group(1))] = line.strip()
kept = sorted(builds, reverse=True)[:keep]
for build in sorted(builds):
    if build not in kept and build != newest:
        print(builds[build])
' "$1" "$2"
}

# The Android app for its own updater (S12): uploads the APK to the releases bucket as
# android/lucid-saga-<build>.apk, then points android/latest.json at it, last, so the manifest
# never names a missing APK. The API then offers it to every installed app that is older. A
# re-run of an older run leaves a newer build in place, since phones can't install an older build
# over it. Keeps the newest RELEASES_KEEP builds.
cmd_upload_apk() {
  local apk="$1" build="${BUILD_NUMBER:-}" version="${VERSION_NAME:-}" bucket="gs://$RELEASES_BUCKET"
  local key current manifest="$TMP_DIR/latest.json" old
  need_arg "$apk" APK
  [ -f "$apk" ] || die "no APK at $apk"
  case "$build" in
    '' | *[!0-9]* | 0*) die "BUILD_NUMBER must be a whole number above 0" ;;
  esac
  [[ "$version" =~ ^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$ ]] ||
    die "VERSION_NAME must be a version name such as 1.0.0"
  key="android/lucid-saga-$build.apk"
  step "App updates: $bucket/$key (S12)"
  current="$(read_value gcloud storage cat "$bucket/android/latest.json" | manifest_build)"
  if [ "${current:-0}" -gt "$build" ]; then
    warn "the bucket already offers build $current, newer than $build, so it stays the app's update."
    return 0
  fi
  # A single upload: a parallel composite one would need more than the deployer's object rights.
  if ! CLOUDSDK_STORAGE_PARALLEL_COMPOSITE_UPLOAD_ENABLED=False run gcloud storage cp "$apk" \
    "$bucket/$key" --content-type=application/vnd.android.package-archive; then
    die "the APK couldn't be uploaded to $bucket. Has infra/bootstrap.sh run since it gained" \
      "step 6d? (docs/DEPLOY.md#3-run-the-bootstrap-from-dev)"
  fi
  python3 -I "$HERE/release_manifest.py" "$manifest" "$apk" "$key" "$build" "$version"
  run gcloud storage cp "$manifest" "$bucket/android/latest.json" --content-type=application/json \
    --cache-control=no-store
  say "The app's updater now offers build $build ($version)."
  # The listing is a read, so a dry run lists nothing and deletes nothing.
  old="$(read_value gcloud storage ls "$bucket/android/" | old_builds "$RELEASES_KEEP" "$build")"
  # shellcheck disable=SC2086 # One URL per line, none with spaces.
  if [ -n "$old" ] && ! run gcloud storage rm $old; then
    warn "older builds couldn't be deleted from $bucket; the next deploy tries again."
  fi
}

cmd_rollback() {
  local revision="$1"
  need_arg "$revision" REVISION
  step "Rollback: all traffic to $revision"
  run gcloud run services update-traffic "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --to-revisions="$revision=100"
}

main() {
  local command="${1:-}"
  if [ $# -gt 0 ]; then
    shift
  fi
  # From a laptop, use Miki's configuration for this project; Actions signs in on its own.
  if [ "${GITHUB_ACTIONS:-}" != true ]; then
    use_gcloud_configuration
  fi
  case "$command" in
    github-outputs) cmd_github_outputs ;;
    preflight) cmd_preflight ;;
    migrate) cmd_migrate "${1:-}" ;;
    service) cmd_service "${1:-}" ;;
    smoke) cmd_smoke "${1:-}" ;;
    access) cmd_access ;;
    models) cmd_models ;;
    covers) cmd_covers ;;
    redraw) cmd_redraw ;;
    export) cmd_export ;;
    upload-apk) cmd_upload_apk "${1:-}" ;;
    rollback) cmd_rollback "${1:-}" ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      die "unknown command: ${command:-none}"
      ;;
  esac
}

main "$@"
