#!/usr/bin/env bash
# One-time setup of Google Cloud for Lucid Saga, safe to run again. See docs/DEPLOY.md.
#
# Miki runs this once, as an owner of the playable-anime project and an administrator of its
# billing account. It needs only a login: on a computer without gcloud it installs it first (apt in
# WSL, Debian or Ubuntu; Homebrew on macOS), and when gcloud isn't signed in to an account that can
# see the project, it opens the browser to sign in. It deploys nothing. It sets up, or brings back
# in line:
#
#   1. the APIs the deploy needs
#   2. the runtime service account's roles (T1, B11)
#   3. an Artifact Registry repository for the API image, with a cleanup policy
#   4. the secrets database-url, database-url-direct and django-secret-key (T11)
#   5. a private bucket in europe-west3 for pictures, with keyless signed URLs (M4, B11)
#   6. a deployer service account for GitHub Actions, with Workload Identity Federation (B11),
#      and a custom role that lets it decide who may call the API
#   6c. a read-only account for the Ops workflow, which lets threads read logs and settings
#   6d. a private bucket for the app's own updates, which the deploy uploads each build to (S12)
#   7. a monthly budget alert on the project (T9)
#
# Run it with --dry-run first to see every command without changing anything.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infra/lib.sh
. "$HERE/lib.sh"
# shellcheck source=infra/config.sh
. "$HERE/config.sh"
# shellcheck source=infra/tools.sh
. "$HERE/tools.sh"

usage() {
  cat <<'EOF'
Usage: infra/bootstrap.sh [--dry-run] [--yes]

  --dry-run   Print every command that would change something, and run none. Needs no credentials.
  --yes       Don't ask for confirmation before making changes.

Installs the gcloud CLI when it is missing, and signs in through the browser when gcloud isn't
signed in to an account that can see the project.

Environment, all optional:
  BUDGET_AMOUNT                        Monthly budget in the billing account's currency (default 25).
  NEON_PRODUCTION_DATABASE_URL         Pooled URL of Neon's production branch.
  NEON_PRODUCTION_DATABASE_URL_DIRECT  Direct URL of Neon's production branch.

The Neon URLs are needed only while their secrets have no value. Without these variables the script
reads them with the Neon CLI (`neonctl`) when it is installed and signed in (`neonctl auth`), and
asks for them otherwise.

Secrets that already have a value are left alone. docs/DEPLOY.md says how to rotate them.
EOF
}

ASSUME_YES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --yes | -y) ASSUME_YES=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $1"
      ;;
  esac
  shift
done

APIS="run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com storage.googleapis.com
cloudresourcemanager.googleapis.com cloudbilling.googleapis.com billingbudgets.googleapis.com
aiplatform.googleapis.com logging.googleapis.com clouderrorreporting.googleapis.com"

# Only the deploy workflow on main of this repository gets in (B11): run by a push to main (a merge
# of dev, docs/DEPLOY.md) or started by hand there.
WIF_ISSUER="https://token.actions.githubusercontent.com"
WIF_ATTRIBUTE_MAPPING="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref"
WIF_CONDITION="assertion.repository_id == '${GITHUB_REPOSITORY_ID}' && assertion.repository_owner_id == '${GITHUB_OWNER_ID}' && assertion.ref == 'refs/heads/main' && (assertion.event_name == 'push' || assertion.event_name == 'workflow_dispatch') && assertion.workflow_ref == '${GITHUB_REPOSITORY_NAME}/${DEPLOY_WORKFLOW}@refs/heads/main'"
WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository_id/${GITHUB_REPOSITORY_ID}"
# Only the Ops workflow on main, started by hand or through the API by someone with write access,
# gets the read-only account. Its pool is its own, so it can never act as the deployer.
OPS_WIF_CONDITION="assertion.repository_id == '${GITHUB_REPOSITORY_ID}' && assertion.repository_owner_id == '${GITHUB_OWNER_ID}' && assertion.ref == 'refs/heads/main' && assertion.event_name == 'workflow_dispatch' && assertion.workflow_ref == '${GITHUB_REPOSITORY_NAME}/${OPS_WORKFLOW}@refs/heads/main'"
OPS_WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${OPS_WIF_POOL}/attribute.repository_id/${GITHUB_REPOSITORY_ID}"
# Only the Evals workflow on main, nightly or started by hand, gets the evals account. Its pool is
# its own too, so it can never act as the deployer or the ops account, nor they as it.
EVALS_WIF_CONDITION="assertion.repository_id == '${GITHUB_REPOSITORY_ID}' && assertion.repository_owner_id == '${GITHUB_OWNER_ID}' && assertion.ref == 'refs/heads/main' && (assertion.event_name == 'schedule' || assertion.event_name == 'workflow_dispatch') && assertion.workflow_ref == '${GITHUB_REPOSITORY_NAME}/${EVALS_WORKFLOW}@refs/heads/main'"
EVALS_WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${EVALS_WIF_POOL}/attribute.repository_id/${GITHUB_REPOSITORY_ID}"

BUDGET_AMOUNT="${BUDGET_AMOUNT:-$BUDGET_DEFAULT_AMOUNT}"
DATABASE_URL_VALUE=""
DATABASE_URL_DIRECT_VALUE=""

# --- helpers -----------------------------------------------------------------------------------

grant_project_role() {
  run_retry gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="$1" --role="$2" --condition=None --format=none
}

grant_service_account_role() {
  run_retry gcloud iam service-accounts add-iam-policy-binding "$1" \
    --project="$PROJECT_ID" --member="$2" --role="$3" --format=none
}

ensure_service_account() {
  local name="$1" display="$2" email="$1@${PROJECT_ID}.iam.gserviceaccount.com"
  if probe gcloud iam service-accounts describe "$email" --project="$PROJECT_ID"; then
    say "Service account $email exists."
  else
    run gcloud iam service-accounts create "$name" --project="$PROJECT_ID" --display-name="$display"
  fi
}

# True when the secret exists and has an enabled version. Once the secret exists, a failed
# listing stops the script: reading it as "no value yet" would replace a working secret, such as
# the Django key, which would sign everyone out.
secret_has_version() {
  local versions
  if ! probe gcloud secrets describe "$1" --project="$PROJECT_ID"; then
    return 1
  fi
  versions="$(gcloud secrets versions list "$1" --project="$PROJECT_ID" --filter='state:ENABLED' \
    --limit=1 --format='value(name)')" || die "can't list the versions of secret $1"
  [ -n "$versions" ]
}

# Sends a secret value through stdin, so it never shows up in arguments, output or logs.
add_secret_version() {
  local name="$1" value="$2" source="$3"
  if is_dry_run; then
    say "[dry-run] gcloud secrets versions add $name --project=$PROJECT_ID --data-file=- <<< ($source)"
    return 0
  fi
  say "+ gcloud secrets versions add $name --project=$PROJECT_ID --data-file=- <<< ($source)"
  printf '%s' "$value" | gcloud secrets versions add "$name" --project="$PROJECT_ID" \
    --data-file=- --format=none
}

# Prints a value from the named environment variable, or asks for it without echoing it.
read_secret_input() {
  local var="$1" prompt="$2" value
  value="${!var:-}"
  if [ -z "$value" ]; then
    if ! { : </dev/tty; } 2>/dev/null; then
      die "$var is not set and there is no terminal to ask for it"
    fi
    IFS= read -r -s -p "$prompt: " value </dev/tty
    printf '\n' >&2
  fi
  [ -n "$value" ] || die "$var is empty"
  printf '%s' "$value"
}

# Prints a production URL of the given kind (pooled or direct) read with the Neon CLI, or fails
# when neonctl isn't installed or signed in. Nothing is printed but the URL.
neonctl_url() {
  local kind="$1" url args
  command -v neonctl >/dev/null 2>&1 || return 1
  args=(connection-string "$NEON_PRODUCTION_BRANCH" --project-id "$NEON_PROJECT_ID")
  if [ "$kind" = pooled ]; then
    args+=(--pooled)
  fi
  url="$(neonctl "${args[@]}" 2>/dev/null | tail -n 1)" || return 1
  case "$url" in
    postgres://* | postgresql://*) printf '%s' "$url" ;;
    *) return 1 ;;
  esac
}

# Prints a production URL: from the environment variable $2, else from neonctl, else asked for.
neon_production_url() {
  local kind="$1" var="$2" prompt="$3" value
  value="${!var:-}"
  if [ -z "$value" ] && value="$(neonctl_url "$kind")"; then
    say "Read the $kind URL of Neon's $NEON_PRODUCTION_BRANCH branch with neonctl."
  fi
  if [ -z "$value" ]; then
    # Command substitutions don't inherit set -e, so stop by hand if there is nothing to ask on.
    value="$(read_secret_input "$var" "$prompt")" || exit 1
  fi
  printf '%s' "$value"
}

# Checks the shape of a Neon URL without printing it. Neon's pooled hosts contain "-pooler".
check_neon_url() {
  local value="$1" kind="$2" label="$3" rest host
  case "$value" in
    postgres://* | postgresql://*) ;;
    *) die "$label must start with postgresql://" ;;
  esac
  rest="${value#*://}"
  rest="${rest%%/*}"
  rest="${rest%%\?*}"
  host="${rest##*@}"
  host="${host%%:*}"
  case "$kind:$host" in
    pooled:*-pooler.*) ;;
    pooled:*) die "$label must be the pooled URL (its host contains -pooler)" ;;
    direct:*-pooler.*) die "$label must be the direct URL (its host has no -pooler)" ;;
    direct:*) ;;
  esac
}

generate_django_key() {
  # 48 random bytes, base64 without padding or symbols that need quoting.
  head -c 48 /dev/urandom | base64 | tr -d '\n=+/'
}

confirm() {
  local answer=""
  if is_dry_run || [ -n "$ASSUME_YES" ]; then
    return 0
  fi
  if ! { : </dev/tty; } 2>/dev/null; then
    die "no terminal to confirm on; pass --yes to run without asking"
  fi
  read -r -p "Set up $PROJECT_ID as described above? [y/N] " answer </dev/tty
  case "$answer" in
    y | Y | yes | YES) ;;
    *) die "stopped, nothing changed" ;;
  esac
}

# --- steps -------------------------------------------------------------------------------------

gcloud_account() { gcloud config get-value account 2>/dev/null || true; }
project_number() { gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'; }

check_access() {
  local account number
  step "Checking access"
  if is_dry_run; then
    say "Dry run: nothing is changed and nothing is read from Google Cloud."
    return 0
  fi
  ensure_gcloud
  use_gcloud_configuration
  account="$(gcloud_account)"
  # Signed out, or signed in as an account that can't see the project: sign in in the browser.
  if [ -z "$account" ] || ! number="$(project_number 2>/dev/null)"; then
    if [ -n "$account" ]; then
      say "$account can't read project $PROJECT_ID."
    fi
    sign_in_gcloud
    account="$(gcloud_account)"
    [ -n "$account" ] || die "gcloud is not signed in; run: gcloud auth login"
    number="$(project_number)" || die "$account can't read project $PROJECT_ID"
  fi
  [ "$number" = "$PROJECT_NUMBER" ] ||
    die "project $PROJECT_ID has number $number, but infra/config.sh expects $PROJECT_NUMBER"
  say "Signed in as $account, project $PROJECT_ID ($PROJECT_NUMBER)."
  # The runtime account already exists, with Vertex AI access (T1, B11). A new one with the same
  # name would be a different principal, so the script stops instead of creating it.
  gcloud iam service-accounts describe "$RUNTIME_SA" --project="$PROJECT_ID" >/dev/null ||
    die "the runtime service account $RUNTIME_SA is missing or not readable by $account"
}

collect_inputs() {
  step "Inputs"
  case "$BUDGET_AMOUNT" in
    '' | *[!0-9.]* | *.*.* | .* | *.) die "BUDGET_AMOUNT must be a number, such as 25 or 40.50" ;;
  esac
  say "Budget: $BUDGET_AMOUNT per month, in the billing account's currency."
  if is_dry_run; then
    say "Dry run: the Neon URLs are not asked for."
    return 0
  fi
  if ! secret_has_version "$SECRET_DATABASE_URL"; then
    DATABASE_URL_VALUE="$(neon_production_url pooled NEON_PRODUCTION_DATABASE_URL \
      'Neon production pooled URL (host has -pooler)')"
    check_neon_url "$DATABASE_URL_VALUE" pooled "The pooled URL"
  else
    say "$SECRET_DATABASE_URL already has a value; leaving it."
  fi
  if ! secret_has_version "$SECRET_DATABASE_URL_DIRECT"; then
    DATABASE_URL_DIRECT_VALUE="$(neon_production_url direct NEON_PRODUCTION_DATABASE_URL_DIRECT \
      'Neon production direct URL (host has no -pooler)')"
    check_neon_url "$DATABASE_URL_DIRECT_VALUE" direct "The direct URL"
  else
    say "$SECRET_DATABASE_URL_DIRECT already has a value; leaving it."
  fi
}

enable_apis() {
  step "1. APIs"
  # shellcheck disable=SC2086 # APIS is a list of words.
  run gcloud services enable $APIS --project="$PROJECT_ID"
}

setup_runtime_account() {
  local role
  step "2. Runtime service account $RUNTIME_SA"
  # Vertex AI through Application Default Credentials, and logs (T4, T7, B11). Secret access is
  # granted per secret below, and bucket access on the bucket.
  for role in roles/aiplatform.user roles/logging.logWriter; do
    grant_project_role "serviceAccount:$RUNTIME_SA" "$role"
  done
}

setup_artifact_registry() {
  step "3. Artifact Registry repository $AR_REPO in $REGION"
  if probe gcloud artifacts repositories describe "$AR_REPO" --project="$PROJECT_ID" \
    --location="$REGION"; then
    say "Repository $AR_REPO exists."
  else
    run gcloud artifacts repositories create "$AR_REPO" --project="$PROJECT_ID" \
      --location="$REGION" --repository-format=docker \
      --description="Lucid Saga API images, built by the deploy workflow"
  fi
  # Keeps the 10 newest images, so the last 10 deploys can be rolled back to, and deletes the rest
  # once they are 30 days old.
  run gcloud artifacts repositories set-cleanup-policies "$AR_REPO" --project="$PROJECT_ID" \
    --location="$REGION" --policy="$HERE/artifact-cleanup.json" --no-dry-run
}

ensure_secret() {
  local name="$1" value="$2" source="$3"
  if probe gcloud secrets describe "$name" --project="$PROJECT_ID"; then
    say "Secret $name exists."
  else
    # Stored only in Frankfurt, for EU users (T12).
    run gcloud secrets create "$name" --project="$PROJECT_ID" \
      --replication-policy=user-managed --locations="$REGION" --labels=app=lucid-saga
  fi
  if secret_has_version "$name"; then
    say "Secret $name already has a value; leaving it."
  elif [ -n "$value" ] || is_dry_run; then
    add_secret_version "$name" "$value" "$source"
  else
    die "secret $name has no value and none was given"
  fi
  run_retry gcloud secrets add-iam-policy-binding "$name" --project="$PROJECT_ID" \
    --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor --format=none
}

setup_secrets() {
  local django_key=""
  step "4. Secrets"
  ensure_secret "$SECRET_DATABASE_URL" "$DATABASE_URL_VALUE" "the pooled Neon URL"
  ensure_secret "$SECRET_DATABASE_URL_DIRECT" "$DATABASE_URL_DIRECT_VALUE" "the direct Neon URL"
  if ! is_dry_run && ! secret_has_version "$SECRET_DJANGO_KEY"; then
    django_key="$(generate_django_key)"
  fi
  ensure_secret "$SECRET_DJANGO_KEY" "$django_key" "a new random key"
}

setup_bucket() {
  step "5. Pictures bucket gs://$MEDIA_BUCKET"
  if probe gcloud storage buckets describe "gs://$MEDIA_BUCKET" --project="$PROJECT_ID"; then
    say "Bucket gs://$MEDIA_BUCKET exists."
  else
    run gcloud storage buckets create "gs://$MEDIA_BUCKET" --project="$PROJECT_ID" \
      --location="$REGION" --default-storage-class=STANDARD --uniform-bucket-level-access \
      --public-access-prevention --soft-delete-duration=0
  fi
  # Private, no soft delete (a deleted account's pictures are gone at once, T12), and readable from
  # the web build through signed URLs.
  run gcloud storage buckets update "gs://$MEDIA_BUCKET" --project="$PROJECT_ID" \
    --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0 \
    --cors-file="$HERE/storage-cors.json"
  run_retry gcloud storage buckets add-iam-policy-binding "gs://$MEDIA_BUCKET" \
    --project="$PROJECT_ID" --member="serviceAccount:$RUNTIME_SA" --role=roles/storage.objectUser \
    --format=none
  # Signed URLs without a key: the API signs as itself through the IAM signBlob call (B11).
  grant_service_account_role "$RUNTIME_SA" "serviceAccount:$RUNTIME_SA" \
    roles/iam.serviceAccountTokenCreator
}

# The app's own updates (S12): the deploy uploads each Android build here, and the API gives the
# app a short-lived signed URL for the newest, as it does for pictures. Private, without CORS (the
# web build never updates itself) and without soft delete, since the deploy deletes old builds.
# After the deployer, which it grants access to.
setup_releases_bucket() {
  step "6d. App releases bucket gs://$RELEASES_BUCKET"
  if probe gcloud storage buckets describe "gs://$RELEASES_BUCKET" --project="$PROJECT_ID"; then
    say "Bucket gs://$RELEASES_BUCKET exists."
  else
    run gcloud storage buckets create "gs://$RELEASES_BUCKET" --project="$PROJECT_ID" \
      --location="$REGION" --default-storage-class=STANDARD --uniform-bucket-level-access \
      --public-access-prevention --soft-delete-duration=0
  fi
  run gcloud storage buckets update "gs://$RELEASES_BUCKET" --project="$PROJECT_ID" \
    --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
  # The deploy writes builds and deletes old ones. The legacy reader role adds only reading the
  # bucket's own settings, which gcloud may do while uploading.
  run_retry gcloud storage buckets add-iam-policy-binding "gs://$RELEASES_BUCKET" \
    --project="$PROJECT_ID" --member="serviceAccount:$DEPLOYER_SA" \
    --role=roles/storage.objectUser --format=none
  run_retry gcloud storage buckets add-iam-policy-binding "gs://$RELEASES_BUCKET" \
    --project="$PROJECT_ID" --member="serviceAccount:$DEPLOYER_SA" \
    --role=roles/storage.legacyBucketReader --format=none
  # The API only reads them, to sign the download URL as itself (B11).
  run_retry gcloud storage buckets add-iam-policy-binding "gs://$RELEASES_BUCKET" \
    --project="$PROJECT_ID" --member="serviceAccount:$RUNTIME_SA" \
    --role=roles/storage.objectViewer --format=none
}

# The custom role the deploy uses to add or remove allUsers as the API's invoker: only the
# permissions to read and set Cloud Run services' IAM policies. Granted on the project, because the
# service may not exist yet. A role deleted in the last 7 days can't be created again, only
# undeleted.
setup_api_access_role() {
  local name deleted
  name="$(read_value gcloud iam roles describe "$API_ACCESS_ROLE_ID" --project="$PROJECT_ID" \
    --format='value(name)')"
  if [ -z "$name" ]; then
    run gcloud iam roles create "$API_ACCESS_ROLE_ID" --project="$PROJECT_ID" \
      --title="Lucid Saga API access" \
      --description="Decide who may call the API: make it public or private again" \
      --permissions="$API_ACCESS_PERMISSIONS" --stage=GA
    return 0
  fi
  deleted="$(read_value gcloud iam roles describe "$API_ACCESS_ROLE_ID" --project="$PROJECT_ID" \
    --format='value(deleted)')"
  case "$deleted" in
    True | true) run gcloud iam roles undelete "$API_ACCESS_ROLE_ID" --project="$PROJECT_ID" ;;
  esac
  # Brings an existing role back to exactly these permissions.
  run gcloud iam roles update "$API_ACCESS_ROLE_ID" --project="$PROJECT_ID" \
    --permissions="$API_ACCESS_PERMISSIONS"
}

setup_deployer() {
  step "6a. Deployer service account $DEPLOYER_SA"
  ensure_service_account "$DEPLOYER_SA_NAME" "GitHub Actions deploy"
  # Deploys services and jobs. Its only IAM rights over them come from the custom role below.
  grant_project_role "serviceAccount:$DEPLOYER_SA" roles/run.developer
  setup_api_access_role
  grant_project_role "serviceAccount:$DEPLOYER_SA" "$API_ACCESS_ROLE"
  # Calls /health on a private service after a deploy.
  grant_project_role "serviceAccount:$DEPLOYER_SA" roles/run.invoker
  # Runs the service and the migration job as the runtime account.
  grant_service_account_role "$RUNTIME_SA" "serviceAccount:$DEPLOYER_SA" \
    roles/iam.serviceAccountUser
  # Prints a failed job's logs in the deploy run, so the reason shows in GitHub.
  grant_project_role "serviceAccount:$DEPLOYER_SA" roles/logging.viewer
  run_retry gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" \
    --project="$PROJECT_ID" --location="$REGION" --member="serviceAccount:$DEPLOYER_SA" \
    --role=roles/artifactregistry.writer --format=none
}

# Creates the pool $1 (display name $2, description $3), or brings back a deleted one.
ensure_wif_pool() {
  local pool="$1" display="$2" description="$3" state
  state="$(read_value gcloud iam workload-identity-pools describe "$pool" \
    --project="$PROJECT_ID" --location=global --format='value(state)')"
  case "$state" in
    '')
      run gcloud iam workload-identity-pools create "$pool" --project="$PROJECT_ID" \
        --location=global --display-name="$display" --description="$description"
      ;;
    DELETED)
      run gcloud iam workload-identity-pools undelete "$pool" --project="$PROJECT_ID" \
        --location=global
      ;;
    *) say "Pool $pool exists." ;;
  esac
}

# Creates GitHub's OIDC provider $2 in pool $1 (display name $3) that admits only tokens passing
# the condition $4, or brings an existing one back to exactly that mapping and condition.
ensure_wif_provider() {
  local pool="$1" provider="$2" display="$3" condition="$4" state
  state="$(read_value gcloud iam workload-identity-pools providers describe "$provider" \
    --project="$PROJECT_ID" --location=global --workload-identity-pool="$pool" \
    --format='value(state)')"
  if [ -z "$state" ]; then
    run_retry gcloud iam workload-identity-pools providers create-oidc "$provider" \
      --project="$PROJECT_ID" --location=global --workload-identity-pool="$pool" \
      --display-name="$display" --issuer-uri="$WIF_ISSUER" \
      --attribute-mapping="$WIF_ATTRIBUTE_MAPPING" --attribute-condition="$condition"
  else
    if [ "$state" = DELETED ]; then
      run gcloud iam workload-identity-pools providers undelete "$provider" \
        --project="$PROJECT_ID" --location=global --workload-identity-pool="$pool"
    fi
    run gcloud iam workload-identity-pools providers update-oidc "$provider" \
      --project="$PROJECT_ID" --location=global --workload-identity-pool="$pool" \
      --issuer-uri="$WIF_ISSUER" --attribute-mapping="$WIF_ATTRIBUTE_MAPPING" \
      --attribute-condition="$condition"
  fi
}

setup_workload_identity() {
  step "6b. Workload Identity Federation for $GITHUB_REPOSITORY_NAME"
  ensure_wif_pool "$WIF_POOL" "GitHub Actions" "Keyless sign-in for GitHub Actions"
  ensure_wif_provider "$WIF_POOL" "$WIF_PROVIDER" "PlayableAnime deploy workflow" "$WIF_CONDITION"
  grant_service_account_role "$DEPLOYER_SA" "$WIF_MEMBER" roles/iam.workloadIdentityUser
}

# Lets threads read Google Cloud through the Ops workflow (docs/DEPLOY.md#reading-google-cloud).
# Viewer reads every setting but no secret's value and no stored picture; logging.viewer reads the
# logs. Neither can change anything.
setup_ops() {
  local role
  step "6c. Read-only access for the Ops workflow: $OPS_SA"
  ensure_service_account "$OPS_SA_NAME" "GitHub Actions read-only ops"
  for role in $OPS_ROLES; do
    grant_project_role "serviceAccount:$OPS_SA" "$role"
  done
  ensure_wif_pool "$OPS_WIF_POOL" "GitHub Actions ops" \
    "Keyless read-only sign-in for the Ops workflow"
  ensure_wif_provider "$OPS_WIF_POOL" "$OPS_WIF_PROVIDER" "PlayableAnime ops workflow" \
    "$OPS_WIF_CONDITION"
  grant_service_account_role "$OPS_SA" "$OPS_WIF_MEMBER" roles/iam.workloadIdentityUser
}

# Lets the Evals workflow play the live story evals on the real models (T15, T17, T18, M8), by hand
# from main. Vertex AI user calls models and nothing else. The nightly run stays off until the
# repository variable EVALS_ENABLED is true, since a full run costs $10 to $20.
setup_evals() {
  local role
  step "6e. Live evals: $EVALS_SA"
  ensure_service_account "$EVALS_SA_NAME" "GitHub Actions live evals"
  for role in $EVALS_ROLES; do
    grant_project_role "serviceAccount:$EVALS_SA" "$role"
  done
  ensure_wif_pool "$EVALS_WIF_POOL" "GitHub Actions evals" \
    "Keyless sign-in for the live evals workflow"
  ensure_wif_provider "$EVALS_WIF_POOL" "$EVALS_WIF_PROVIDER" "PlayableAnime evals workflow" \
    "$EVALS_WIF_CONDITION"
  grant_service_account_role "$EVALS_SA" "$EVALS_WIF_MEMBER" roles/iam.workloadIdentityUser
}

setup_budget() {
  local billing account existing
  step "7. Budget alert $BUDGET_NAME"
  if is_dry_run; then
    account="BILLING_ACCOUNT_ID"
  else
    billing="$(gcloud billing projects describe "$PROJECT_ID" \
      --format='value(billingAccountName)')" || die "can't read the billing account of $PROJECT_ID"
    [ -n "$billing" ] || die "project $PROJECT_ID has no billing account"
    account="${billing#billingAccounts/}"
  fi
  # A failed listing stops the script, so a re-run never adds a second budget.
  existing=""
  if ! is_dry_run; then
    existing="$(gcloud billing budgets list --billing-account="$account" \
      --billing-project="$PROJECT_ID" --filter="displayName=\"$BUDGET_NAME\"" \
      --format='value(name)' --limit=1)" || die "can't list the budgets of billing account $account"
  fi
  if [ -n "$existing" ]; then
    run gcloud billing budgets update "$existing" --billing-project="$PROJECT_ID" \
      --budget-amount="$BUDGET_AMOUNT"
  else
    # Emails the billing account's admins at 50%, 90% and 100% of actual spend, and when the
    # forecast passes 100%. Credits are left out, so free credits don't hide real usage.
    run gcloud billing budgets create --billing-account="$account" \
      --billing-project="$PROJECT_ID" --display-name="$BUDGET_NAME" \
      --budget-amount="$BUDGET_AMOUNT" --calendar-period=month \
      --filter-projects="projects/$PROJECT_ID" --credit-types-treatment=exclude-all-credits \
      --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 \
      --threshold-rule=percent=1.0,basis=forecasted-spend
  fi
}

summary() {
  step "Done"
  if is_dry_run; then
    say "Dry run finished. Nothing was changed. Run without --dry-run to apply."
    return 0
  fi
  cat >&2 <<EOF
Google Cloud is ready for the deploy workflow:

  Workload identity provider  $WIF_PROVIDER_RESOURCE
  Deployer service account    $DEPLOYER_SA
  Ops (read-only) account     $OPS_SA, through $OPS_WIF_PROVIDER_RESOURCE
  Live evals account          $EVALS_SA, through $EVALS_WIF_PROVIDER_RESOURCE
  Image repository            $IMAGE
  Pictures bucket             gs://$MEDIA_BUCKET
  App releases bucket         gs://$RELEASES_BUCKET

Next: in GitHub, run Actions > Deploy on main with "dry run" ticked. It signs in, checks this setup
and builds the image without deploying anything. After that, merging dev into main deploys
(docs/DEPLOY.md).
EOF
}

main() {
  step "Lucid Saga bootstrap for project $PROJECT_ID in $REGION"
  check_access
  collect_inputs
  confirm
  enable_apis
  setup_runtime_account
  setup_artifact_registry
  setup_secrets
  setup_bucket
  setup_deployer
  setup_workload_identity
  setup_ops
  setup_releases_bucket
  setup_evals
  setup_budget
  summary
}

main
