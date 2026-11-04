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

# The Neon project and its production branch (docs/ARCHITECTURE.md#neon-postgres). The bootstrap
# reads the branch's URLs with the Neon CLI when it is signed in.
NEON_PROJECT_ID="divine-rice-51324513"
NEON_PRODUCTION_BRANCH="production"

# Secret Manager (T11). The service gets the pooled URL, migrations get the direct one (T2, B2).
SECRET_DATABASE_URL="database-url"
SECRET_DATABASE_URL_DIRECT="database-url-direct"
SECRET_DJANGO_KEY="django-secret-key"

# Pictures (M4): a private bucket in Frankfurt, served through short-lived signed URLs.
MEDIA_BUCKET="playable-anime-pictures"

# GitHub Actions signs in through Workload Identity Federation as this account. No JSON key (B11).
DEPLOYER_SA_NAME="github-deployer"
DEPLOYER_SA="${DEPLOYER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
# A custom role with only the permissions to read and set Cloud Run services' IAM policies, which
# the deploy uses to add or remove allUsers as the API's invoker (docs/DEPLOY.md#who-may-call-the-api).
API_ACCESS_ROLE_ID="lucidSagaApiAccess"
API_ACCESS_ROLE="projects/${PROJECT_ID}/roles/${API_ACCESS_ROLE_ID}"
API_ACCESS_PERMISSIONS="run.services.getIamPolicy,run.services.setIamPolicy"
WIF_POOL="github"
WIF_PROVIDER="playable-anime-deploy"
WIF_PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

# The budget alert on the project (T9). The amount is in the billing account's currency.
BUDGET_NAME="playable-anime-monthly"
BUDGET_DEFAULT_AMOUNT="25"

# The service's deterministic URL, which exists before the first deploy. The Android app calls it.
SERVICE_DETERMINISTIC_HOST="${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
API_URL="https://${SERVICE_DETERMINISTIC_HOST}"

# Google sign-in (T8): the OAuth clients in this project. Client ids aren't secrets. The client
# secret is never needed, because the app sends Google's ID token, so it is never stored anywhere.
# deploy.sh gives the API every id here (GOOGLE_OAUTH_CLIENT_IDS), and build-apk.sh gives the app
# the web one, which is also its server client id on Android.
GOOGLE_WEB_CLIENT_ID="528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com"
# Registered for the package com.lucid.saga and the release key's SHA-1 (docs/DEPLOY.md).
GOOGLE_ANDROID_CLIENT_ID="528988811295-c2t6dchelulruu7hgl4mem4kr733d346.apps.googleusercontent.com"
# The iOS client, once there is one.
GOOGLE_IOS_CLIENT_ID=""

# The Android app: each deploy publishes it as this asset of a GitHub release, which the README
# links through releases/latest/download/.
APK_ASSET="lucid-saga.apk"
