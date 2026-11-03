# shellcheck shell=bash disable=SC2034 # Sourced: the scripts that source it use these.
# Names and ids shared by bootstrap.sh, deploy.sh and the deploy workflow. See docs/DEPLOY.md.
#
# These are identifiers, not secrets. They are fixed here on purpose: nothing reads them from the
# environment, so a stray PROJECT_ID or REGION in someone's shell can never point a script at the
# wrong project. Change a value here, in a PR, and re-run bootstrap.sh.

# The Google Cloud project (docs/ARCHITECTURE.md#google-cloud).
PROJECT_ID="playable-anime"
PROJECT_NUMBER="528988811295"
# Frankfurt, next to the Neon database (T1). Vertex AI uses the global endpoint.
REGION="europe-west3"
# The gcloud configuration Miki uses for this project. Used when it exists on the machine.
GCLOUD_CONFIGURATION="playable-anime"

# The GitHub repository allowed to deploy, by its numeric ids, which survive a rename (B11).
GITHUB_REPOSITORY_NAME="Mikigb77/PlayableAnime"
GITHUB_REPOSITORY_ID="1444213567"
GITHUB_OWNER_ID="112938189"
DEPLOY_WORKFLOW=".github/workflows/deploy.yml"

# Cloud Run (T1, B10).
SERVICE="playable-anime-api"
MIGRATE_JOB="playable-anime-migrate"
# The runtime service account that already exists, with Vertex AI access (B11).
RUNTIME_SA_NAME="playable-anime-api"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Artifact Registry: one Docker repository, one image.
AR_REPO="playable-anime"
REGISTRY_HOST="${REGION}-docker.pkg.dev"
IMAGE="${REGISTRY_HOST}/${PROJECT_ID}/${AR_REPO}/api"

# Secret Manager (T11). The service gets the pooled URL, migrations get the direct one (T2, B2).
SECRET_DATABASE_URL="database-url"
SECRET_DATABASE_URL_DIRECT="database-url-direct"
SECRET_DJANGO_KEY="django-secret-key"

# Pictures (M4): a private bucket in Frankfurt, served through short-lived signed URLs.
MEDIA_BUCKET="playable-anime-pictures"

# GitHub Actions signs in through Workload Identity Federation as this account. No JSON key (B11).
DEPLOYER_SA_NAME="github-deployer"
DEPLOYER_SA="${DEPLOYER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
WIF_POOL="github"
WIF_PROVIDER="playable-anime-deploy"
WIF_PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

# The budget alert on the project (T9). The amount is in the billing account's currency.
BUDGET_NAME="playable-anime-monthly"
BUDGET_DEFAULT_AMOUNT="25"

# The service's deterministic URL, which exists before the first deploy.
SERVICE_DETERMINISTIC_HOST="${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
