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
  rollback REV     Send all traffic back to revision REV.

IMAGE is a full image reference, best pinned by digest. DRY_RUN=1 prints instead of running.
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

describe_service() {
  read_value gcloud run services describe "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --format="$1"
}

# The service's hostnames, comma-separated: the deterministic one, which exists before the first
# deploy, and every URL Cloud Run reports once the service exists.
service_hosts() {
  local urls
  urls="$(describe_service 'value(metadata.annotations["run.googleapis.com/urls"],status.url)')"
  {
    printf '%s\n' "$SERVICE_DETERMINISTIC_HOST"
    printf '%s\n' "$urls" | { grep -oE 'https://[A-Za-z0-9.-]+' || true; } | sed 's#^https://##'
  } | awk 'NF && !seen[$0]++' | paste -sd, -
}

# Writes the env vars file for a deploy: infra/cloudrun/env.yaml plus the values this script owns.
render_env() {
  local hosts="$1" out="$TMP_DIR/env-$RANDOM.yaml" origins
  if grep -Eq '^(GCP_PROJECT|MEDIA_BUCKET|ALLOWED_HOSTS|CSRF_TRUSTED_ORIGINS|DATABASE_URL|DJANGO_SECRET_KEY):' "$ENV_FILE"; then
    die "$ENV_FILE sets a variable that deploy.sh owns; remove it from the file"
  fi
  origins="$(printf '%s' "$hosts" | sed 's#\([^,][^,]*\)#https://\1#g')"
  {
    cat "$ENV_FILE"
    printf '\n# Added by infra/deploy.sh\n'
    printf 'GCP_PROJECT: "%s"\n' "$PROJECT_ID"
    printf 'MEDIA_BUCKET: "%s"\n' "$MEDIA_BUCKET"
    printf 'ALLOWED_HOSTS: "%s"\n' "$hosts"
    printf 'CSRF_TRUSTED_ORIGINS: "%s"\n' "$origins"
  } >"$out"
  if is_dry_run; then
    say "[dry-run] env vars file $out:"
    grep -Ev '^[[:space:]]*(#|$)' "$out" | sed 's/^/[dry-run]   /' >&2
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
  say "Preflight passed: the image repository and the runtime service account are in place."
}

cmd_migrate() {
  local image="$1" env_file
  need_arg "$image" IMAGE
  env_file="$(render_env "$SERVICE_DETERMINISTIC_HOST")"
  step "Migrations: job $MIGRATE_JOB over the direct database URL (T2, B2)"
  run gcloud run jobs deploy "$MIGRATE_JOB" --project="$PROJECT_ID" --region="$REGION" \
    --image="$image" --service-account="$RUNTIME_SA" \
    --command=python --args=manage.py,migrate,--noinput \
    --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=10m --cpu=1 --memory=1Gi \
    --env-vars-file="$env_file" --set-secrets="$MIGRATE_SECRETS" --labels="$(deploy_labels)"
  if ! run gcloud run jobs execute "$MIGRATE_JOB" --project="$PROJECT_ID" --region="$REGION" --wait; then
    say "The migration failed, so the service was not deployed and still runs the old code."
    say "Its logs: $(quote_cmd gcloud logging read \
      "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"$MIGRATE_JOB\"" \
      --project="$PROJECT_ID" --freshness=1h --limit=50)"
    exit 1
  fi
}

cmd_service() {
  local image="$1" previous hosts after env_file url revision
  need_arg "$image" IMAGE
  previous="$(describe_service 'value(status.traffic[0].revisionName)')"
  hosts="$(service_hosts)"
  env_file="$(render_env "$hosts")"
  step "Service $SERVICE in $REGION (T1, B10)"
  # Min 0 and max 3 instances, 300 s for streamed turns, startup CPU boost. No IAM flags: a deploy
  # never makes the API public (docs/DEPLOY.md#going-public).
  run gcloud run deploy "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --image="$image" --service-account="$RUNTIME_SA" \
    --cpu=1 --memory=1Gi --concurrency=80 --min-instances=0 --max-instances=3 \
    --timeout=300 --cpu-boost --port=8080 \
    --env-vars-file="$env_file" --set-secrets="$SERVICE_SECRETS" --update-labels="$(deploy_labels)"
  after="$(service_hosts)"
  if [ "$after" != "$hosts" ]; then
    # Only on the first deploy: Cloud Run has just given the service its other URL.
    say "Allowing the service's new URLs: $after"
    env_file="$(render_env "$after")"
    run gcloud run services update "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
      --env-vars-file="$env_file"
  fi
  # A rollback pins traffic to an old revision; a deploy always moves it to the new one.
  run gcloud run services update-traffic "$SERVICE" --project="$PROJECT_ID" --region="$REGION" \
    --to-latest
  url="$(describe_service 'value(status.url)')"
  revision="$(describe_service 'value(status.latestReadyRevisionName)')"
  set_output previous_revision "$previous"
  set_output url "${url:-https://$SERVICE_DETERMINISTIC_HOST}"
  set_output revision "$revision"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    # shellcheck disable=SC2016 # The backticks are Markdown.
    {
      printf '| | |\n| --- | --- |\n'
      printf '| Image | `%s` |\n' "$image"
      printf '| Revision | `%s` |\n' "${revision:-dry run}"
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
      --max-time 30 --header "@$headers" "$url/health" || true)"
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
    rollback) cmd_rollback "${1:-}" ;;
    -h | --help | help) usage ;;
    *)
      usage >&2
      die "unknown command: ${command:-none}"
      ;;
  esac
}

main "$@"
