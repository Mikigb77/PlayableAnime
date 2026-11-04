# Deploying Lucid Saga

How the API gets to Cloud Run: what Miki sets up once, what each deploy does, what it all costs, and
how to roll back. Requirements: T1, T2, T3, T9, T11, T13, B10, B11 and M4 in
[REQUIREMENTS.md](REQUIREMENTS.md). The scripts are in [`infra/`](../infra/), and the workflow is
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

**Nothing is deployed yet.** The Django backend already follows the image's runtime contract
([below](#what-the-container-gets)), and nothing goes public before sign-in (T8) and rate limits and
quotas (T9) are merged.

## What runs where

| Piece | Name | Notes |
| --- | --- | --- |
| Google Cloud project | `playable-anime` (528988811295) | Everything below is in it. |
| API service | Cloud Run `playable-anime-api` in `europe-west3` (Frankfurt) | Next to Neon (T1). 0 to 3 instances, 300 s timeout, startup CPU boost. |
| Migrations | Cloud Run job `playable-anime-migrate` | Runs `python manage.py migrate` over the direct URL before each deploy (T2). |
| Runtime identity | `playable-anime-api@playable-anime.iam.gserviceaccount.com` | Already exists. Calls Vertex AI with Application Default Credentials (B11). |
| Images | Artifact Registry `europe-west3-docker.pkg.dev/playable-anime/playable-anime/api` | The 10 newest are kept, so the last 10 deploys can be rolled back to. |
| Secrets | Secret Manager `database-url`, `database-url-direct`, `django-secret-key` | Stored in `europe-west3` only, mounted as env vars (T11). |
| Pictures | Cloud Storage `gs://playable-anime-pictures` in `europe-west3` | Private, served through short-lived signed URLs, no soft delete (M4, T12). |
| Deploy identity | `github-deployer@playable-anime.iam.gserviceaccount.com` | GitHub Actions signs in as it through Workload Identity Federation. No JSON key (B11). |
| Budget alert | `playable-anime-monthly` on the billing account | Emails at 50%, 90% and 100% of the month's budget, and when the forecast passes 100% (T9). |
| Database | Neon `production` branch | Pooled URL for the service, direct URL for migrations (T2, B2). |

The names live in [`infra/config.sh`](../infra/config.sh). Plain settings for the container are in
[`infra/cloudrun/env.yaml`](../infra/cloudrun/env.yaml).

## One-time setup (Miki)

These steps need Miki: they sign in as the project's owner, read the production database URLs and
create things that are billed. Each one is safe to repeat.

### 1. Sign in

On a machine with this repo and the [gcloud CLI](https://cloud.google.com/sdk/docs/install), sign in
with the Google account that owns the `playable-anime` project and administers its billing account:

```bash
gcloud --configuration=playable-anime auth login
```

The scripts use the `playable-anime` gcloud configuration when it exists, without making it the
active one, and pass `--project=playable-anime` on every command anyway. Cloud Shell works too:
it is already signed in, so skip this step there.

### 2. Get the two production URLs from Neon

In the [Neon console](https://console.neon.tech), open the project, press **Connect**, pick the
`production` branch, and copy the connection string twice:

- with **Connection pooling** on: the **pooled** URL, whose host contains `-pooler`;
- with it off: the **direct** URL.

Don't paste them anywhere else. The script asks for them without echoing them, or reads them from
`NEON_PRODUCTION_DATABASE_URL` and `NEON_PRODUCTION_DATABASE_URL_DIRECT`, and refuses a URL of the
wrong kind before changing anything.

### 3. Run the bootstrap

```bash
infra/bootstrap.sh --dry-run       # prints every command, changes nothing, needs no sign-in
BUDGET_AMOUNT=25 infra/bootstrap.sh
```

`BUDGET_AMOUNT` is the monthly alert threshold in the billing account's currency (25 by default).
The script shows the account and project, asks for the two URLs, asks for confirmation, then runs
the steps below. Running it again brings everything back in line and changes nothing that is
already right: secrets that have a value keep it, and the budget's amount is updated.

| Step | What it does | Cost |
| --- | --- | --- |
| 1. APIs | Enables Cloud Run, Artifact Registry, Secret Manager, IAM, IAM Credentials, STS, Cloud Storage, Resource Manager, Billing, Budgets, Vertex AI, Logging and Error Reporting. | Free |
| 2. Runtime account | Makes sure `playable-anime-api` has `aiplatform.user` and `logging.logWriter` (T4, T7, B11). It already exists and is never created here: the script stops before changing anything if it can't see it. | Free |
| 3. Artifact Registry | A Docker repository `playable-anime` in `europe-west3`, with a cleanup policy: keep the 10 newest images, delete the rest once 30 days old ([`artifact-cleanup.json`](../infra/artifact-cleanup.json)). | 0.5 GiB free, then about $0.10 per GiB-month. Expect a few cents a month. |
| 4. Secrets | `database-url` (pooled), `database-url-direct` and `django-secret-key` (generated), each stored in `europe-west3` only, with read access for the runtime account. | 6 versions and 10,000 reads a month are free; these are 3 versions. Free. |
| 5. Pictures bucket | `gs://playable-anime-pictures` in `europe-west3`: uniform access, public access prevention enforced, soft delete off so a deleted account's pictures are gone at once (T12), and CORS that lets the web build read signed URLs ([`storage-cors.json`](../infra/storage-cors.json)). The runtime account gets `storage.objectUser` on the bucket and `iam.serviceAccountTokenCreator` on itself, which is what [signed URLs without a key](#signed-urls-without-a-key) need. | About $0.02 per GB-month (no free tier in Europe), $0.005 per 1,000 uploads, $0.12 per GB downloaded. 1,000 pictures of about 1.5 MB cost about $0.03 a month to keep and $0.18 to view once. |
| 6. Deployer and federation | A `github-deployer` account with `run.developer` (deploy services and jobs, but not change who may call them), `run.invoker` (for the post-deploy health check), `iam.serviceAccountUser` on the runtime account only, and `artifactregistry.writer` on the repository only. A Workload Identity pool `github` with a provider that admits only `.github/workflows/deploy.yml` on `main` of this repository (by its numeric id), started by hand. | Free |
| 7. Budget | A monthly budget on the project, measured before credits so free credits can't hide real usage. It alerts by email; it does not stop spending. | Free |

Every command the bootstrap and the deploy run is listed under [Every command](#every-command).

### 4. Test the pipeline without deploying

In GitHub, open **Actions > Deploy > Run workflow**, keep the branch on `main`, tick **Dry run** and
run it. From a terminal: `gh workflow run deploy.yml --ref main -f dry_run=true`.

A dry run checks that CI passed on `main`, signs in through Workload Identity Federation, checks
that the bootstrap's repository and runtime account are visible, builds the image without pushing
it, and prints the migrate and deploy commands. It changes nothing in Google Cloud. If it fails at
**google-github-actions/auth**, the bootstrap hasn't run or the provider's condition doesn't match
(see [Troubleshooting](#troubleshooting)).

## Deploying

A deploy is the same run without **Dry run**: **Actions > Deploy > Run workflow** on `main`, or
`gh workflow run deploy.yml --ref main`. Only Miki starts one (CLAUDE.md), and only from `main`.
Two deploys never run at once.

1. **CI passed on this commit** ([`require-green-ci.sh`](../infra/require-green-ci.sh)): the CI
   workflow's run for this exact commit of `main` must have succeeded. If it is still running, the
   deploy waits for it, up to 30 minutes. A red, cancelled or missing run stops the deploy (T13).
2. **Sign in** as `github-deployer` through Workload Identity Federation. There is no key to leak
   (B11).
3. **Build** `backend/` into one image, tag it with the commit, push it to Artifact Registry and pin
   it by digest, so the job and the service run exactly the same bytes.
4. **Migrate** (`infra/deploy.sh migrate`): deploy the `playable-anime-migrate` job with the image
   and `DATABASE_URL` from `database-url-direct`, then run it and wait. If it fails, the deploy
   stops and the old service keeps running.
5. **Deploy the service** (`infra/deploy.sh service`). Cloud Run starts one instance of the new
   revision and moves traffic to it only once it is listening, so a container that can't start
   never takes traffic. On the very first deploy the service also learns its second URL, and one
   more revision adds it to `ALLOWED_HOSTS`. Traffic then goes to the newest revision, even if an
   earlier rollback had pinned it.
6. **Check `/health`** with an ID token for `github-deployer`, so it works while the service is
   still private. It tries 6 times, 5 seconds apart, each with a 10-second limit. If it never gets
   a 200, or any step fails once the deploy has started, traffic goes back to the revision that
   had the most traffic before this deploy, and the run fails. `/health` never touches the
   database (T3).

The run's summary shows the image, the new and previous revisions and the URL.

### Drawing the starter covers

Discover's eleven starter premises show a cover once the house has drawn it (S1, M4). Nothing
draws them during a deploy: after the first deploy that has `draw_premise_covers`, and once Vertex
AI answers for the runtime account, Miki runs it once as the migration job with other arguments.
The job already has the runtime account, the Vertex AI settings, `MEDIA_BUCKET` and the direct
database URL, so nothing else is needed:

```bash
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 \
  --args=manage.py,draw_premise_covers --task-timeout=30m --wait
```

It draws each cover once with `PICTURE_MODEL`, about $0.034 each and $0.37 for all eleven, paid by
the house: the logs show each cover's model and cost (`Premise cover ready`), and no player's ledger
changes. A cover that fails or is blocked is left out, and the job ends failed and names it; running
the same command again draws only the missing ones. To draw one again, pass its id and `--force`:
`--args=manage.py,draw_premise_covers,naples-vendetta,--force`. `--dry-run` lists what would be
drawn and its cost without drawing. The app shows a cover the next time it loads the premises;
until then, and for a premise without one, Discover shows a glow in the genre's colour.

### Service settings

| Setting | Value | Why |
| --- | --- | --- |
| Region | `europe-west3` | Next to Neon in Frankfurt (T1). |
| Instances | min 0, max 3 | Scales to zero; the cap is a cost guard (T1). |
| Request timeout | 300 s | Streamed turns can be long (T1, S3). |
| Startup CPU boost | on | Faster cold starts (B10, T3). |
| CPU, memory, concurrency | 1 vCPU, 1 GiB, 80 | Django, LangGraph and the Google libraries need more than 512 MiB; the API is async. |
| Billing | request-based | CPU is throttled after a response, so nothing may run after it (B8). |
| Service account | `playable-anime-api` | Vertex AI through Application Default Credentials (B11). |
| Who may call it | unchanged by deploys | A new service is private. See [Going public](#going-public). |

### What the container gets

The image must follow the runtime contract in [PLAN.md](PLAN.md#target-layout): its default command
serves `lucid.asgi:application` on `$PORT`, and `python manage.py migrate` works from its working
directory.

| Variable | From |
| --- | --- |
| `DATABASE_URL` | Secret `database-url` (pooled) for the service, `database-url-direct` for the migrate job |
| `DJANGO_SECRET_KEY` | Secret `django-secret-key` |
| `LLM_PROVIDER`, `VERTEX_LOCATION`, `LOG_LEVEL`, `OWNER_EMAILS`, and later `GOOGLE_OAUTH_CLIENT_IDS`, `CORS_ORIGINS` and per-node model names | [`infra/cloudrun/env.yaml`](../infra/cloudrun/env.yaml) |
| `GCP_PROJECT`, `MEDIA_BUCKET` | `infra/config.sh`, added by `deploy.sh` |
| `ALLOWED_HOSTS` | The service's hostnames, comma-separated, without a scheme, added by `deploy.sh` |
| `CSRF_TRUSTED_ORIGINS` | The same hostnames as `https://` origins, for the Django admin |
| `PORT`, `K_SERVICE`, `K_REVISION` | Cloud Run itself |

Each deploy replaces every plain variable with the file's contents, so a variable removed from
`env.yaml` disappears from the service. Changing a setting is a PR to `env.yaml` and a deploy.
Variables the backend doesn't read yet, such as `OWNER_EMAILS`, are ignored until the code that
needs them lands. `MEDIA_BUCKET` is required: with `LLM_PROVIDER=vertex` the service refuses to start
without it, because pictures on one instance's disk would be lost (M4). Cloud Run terminates TLS, and `lucid/settings.py` trusts its
`X-Forwarded-Proto` header.

The service has two URLs, `https://playable-anime-api-528988811295.europe-west3.run.app` (known
before the first deploy) and a `…-ey.a.run.app` one that Cloud Run picks. Both are allowed. The
app's `API_BASE_URL` should use the first.

### Signed URLs without a key

Pictures are private objects. The API hands out short-lived V4 signed URLs, signed by the runtime
account through the IAM Credentials `signBlob` call instead of a private key (B11). With
`google-cloud-storage`, refresh the default credentials and pass them in:

```python
credentials, _ = google.auth.default()
credentials.refresh(google.auth.transport.requests.Request())
url = blob.generate_signed_url(
    version="v4",
    expiration=datetime.timedelta(minutes=15),
    service_account_email=credentials.service_account_email,
    access_token=credentials.token,
)
```

## Going public

A deploy never changes who may call the API, and a new service accepts only callers with IAM
access. Once T8 (sign-in) and T9 (rate limits, quotas and this budget) are merged and deployed, and
Miki agrees, this one command lets the app reach it:

```bash
gcloud run services add-iam-policy-binding playable-anime-api --project=playable-anime \
  --region=europe-west3 --member=allUsers --role=roles/run.invoker
```

To make it private again, in an emergency or otherwise, run the same with
`remove-iam-policy-binding`. Requests refused this way are not billed.

## Rolling back

| What went wrong | What to do |
| --- | --- |
| The new revision fails `/health`, or a step after the deploy began fails | Nothing: the workflow already sent traffic back to the previous revision. |
| The new code misbehaves | List revisions with `gcloud run revisions list --service=playable-anime-api --project=playable-anime --region=europe-west3`, then `infra/deploy.sh rollback <revision>`, or the `update-traffic` command under [Every command](#every-command). The next deploy moves traffic to the newest revision again. Images of the last 10 deploys are kept. |
| A migration failed | Nothing to roll back in the service, which kept the old code. Read the job's logs (below), fix it in a PR and deploy again. |
| A migration ran but must be undone | Migrations must stay backward compatible for one deploy (add before you drop), so old code keeps working on the new schema. To reverse one: `gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,migrate,<app>,<migration> --wait`. A migration that drops data needs Miki first (CLAUDE.md). |
| Data is damaged | Neon's point-in-time restore of the `production` branch (T12), from the Neon console. Only Miki does this. |
| A secret is wrong | Add the right value as a new version: `printf '%s' "$VALUE" \| gcloud secrets versions add database-url --project=playable-anime --data-file=-`, then deploy, so new instances read it. |
| Costs climb | Make the service private (above), then look at the budget and Vertex AI usage. |

Migration logs:

```bash
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="playable-anime-migrate"' \
  --project=playable-anime --freshness=1h --limit=50
```

## What it costs

Prices are Google's list prices checked on 2026-11-03, in USD, before the free tiers that apply per
billing account. While the app is used only for testing, everything but Vertex AI stays within the
free tiers or a few cents a month.

| Item | Price | Expected |
| --- | --- | --- |
| Cloud Run service, request-based | $0.000024 per vCPU-second, $0.0000025 per GiB-second and $0.40 per million requests at Tier 1 prices; `europe-west3` is a Tier 2 region and costs more. Free each month: 180,000 vCPU-seconds, 360,000 GiB-seconds, 2 million requests. Idle instances cost nothing with min 0. | Free while testing: the free tier is about 50 hours of busy instance a month. |
| Migration job | $0.000018 per vCPU-second and $0.000002 per GiB-second, with a 1-minute minimum. Free each month: 240,000 vCPU-seconds, 450,000 GiB-seconds. | Under $0.01 per deploy, so free. |
| Artifact Registry | 0.5 GiB free, then about $0.10 per GiB-month. Pulls by Cloud Run in the same region are free. | A few cents a month with the cleanup policy. |
| Secret Manager | $0.06 per active version a month after 6 free, $0.03 per 10,000 reads after 10,000 free. | Free. |
| Cloud Storage, pictures | About $0.02 per GB-month, $0.005 per 1,000 writes, $0.0004 per 1,000 reads, $0.12 per GB served to the internet. | Cents until there are many players. |
| Workload Identity Federation, service accounts, IAM, budgets, enabling APIs | Free | Free |
| Cloud Logging and Error Reporting | First 50 GiB of logs a month free | Free |
| GitHub Actions | This private repo's free plan includes 2,000 minutes a month; a deploy takes about 5 to 10, the CI infra job about 2. | Free |
| Neon | A deploy wakes the production compute for the migration. | Seconds of compute. |
| Vertex AI (Gemini) | Per token and per picture ([ARCHITECTURE.md](ARCHITECTURE.md#images)) | The real cost, guarded by T9 and the budget alert. |

Sources: [Cloud Run](https://cloud.google.com/run/pricing),
[Artifact Registry](https://cloud.google.com/artifact-registry/pricing),
[Secret Manager](https://cloud.google.com/secret-manager/pricing) and
[Cloud Storage](https://cloud.google.com/storage/pricing) pricing pages.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `google-github-actions/auth` fails with `unauthorized_client` or `The given credential is rejected by the attribute condition` | The run wasn't started by hand from `main`, or the bootstrap hasn't run. The provider admits only `workflow_dispatch` runs of `deploy.yml` on `main`. |
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | The `workloadIdentityUser` binding on `github-deployer` is missing; re-run the bootstrap. |
| Preflight can't see the repository or the runtime account | The bootstrap hasn't run, or ran on another project. |
| The deploy fails with `does not have permission to access secret` | The runtime account lost `secretAccessor` on a secret; re-run the bootstrap. |
| `/health` answers 400 | Django rejected the host: the backend must read `ALLOWED_HOSTS`. |
| `/health` answers 401 or 403 | The smoke test's ID token was refused; check that `github-deployer` still has `run.invoker`. |
| The migrate job fails at once | The image lacks `manage.py` in its working directory, or `DATABASE_URL` isn't the direct URL. See the job's logs. |

## Changing or removing the setup

Change a name or a setting in `infra/` in a PR, then re-run `infra/bootstrap.sh`. To change the
budget, re-run it with a new `BUDGET_AMOUNT`.

Removing pieces is Miki's call and can't be undone; each command below deletes its data:
`gcloud run services delete playable-anime-api`, `gcloud run jobs delete playable-anime-migrate`,
`gcloud artifacts repositories delete playable-anime --location=europe-west3`,
`gcloud storage rm --recursive gs://playable-anime-pictures`, `gcloud secrets delete <name>`,
`gcloud iam workload-identity-pools delete github --location=global` (it can be undeleted for 30
days, and the bootstrap does that if it finds it deleted) and
`gcloud iam service-accounts delete github-deployer@playable-anime.iam.gserviceaccount.com`, each
with `--project=playable-anime`. Never delete the runtime account.

## Every command

Printed from the dry runs by [`infra/tests/print-commands.sh`](../infra/tests/print-commands.sh);
CI fails if this copy falls out of date. A dry run assumes nothing exists yet, so it shows every
create; a real run skips what already exists. On a re-run the bootstrap instead updates the
provider (`update-oidc` with the same flags) and the budget (`billing budgets update <budget>
--budget-amount=…`), and undeletes a pool or provider that was deleted. On the first deploy,
`gcloud run services update … --env-vars-file=ENV_FILE` adds the service's second URL. CI checks
all of these against the real gcloud too. Secret values go in on standard input, never as
arguments, shown here as `<<< (where it comes from)`.

<!-- every-command:start -->
```text
# infra/bootstrap.sh
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com storage.googleapis.com cloudresourcemanager.googleapis.com cloudbilling.googleapis.com billingbudgets.googleapis.com aiplatform.googleapis.com logging.googleapis.com clouderrorreporting.googleapis.com --project=playable-anime
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/aiplatform.user --condition=None --format=none
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/logging.logWriter --condition=None --format=none
gcloud artifacts repositories create playable-anime --project=playable-anime --location=europe-west3 --repository-format=docker '--description=Lucid Saga API images, built by the deploy workflow'
gcloud artifacts repositories set-cleanup-policies playable-anime --project=playable-anime --location=europe-west3 --policy=infra/artifact-cleanup.json --no-dry-run
gcloud secrets create database-url --project=playable-anime --replication-policy=user-managed --locations=europe-west3 --labels=app=lucid-saga
gcloud secrets versions add database-url --project=playable-anime --data-file=- <<< (the pooled Neon URL)
gcloud secrets add-iam-policy-binding database-url --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --format=none
gcloud secrets create database-url-direct --project=playable-anime --replication-policy=user-managed --locations=europe-west3 --labels=app=lucid-saga
gcloud secrets versions add database-url-direct --project=playable-anime --data-file=- <<< (the direct Neon URL)
gcloud secrets add-iam-policy-binding database-url-direct --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --format=none
gcloud secrets create django-secret-key --project=playable-anime --replication-policy=user-managed --locations=europe-west3 --labels=app=lucid-saga
gcloud secrets versions add django-secret-key --project=playable-anime --data-file=- <<< (a new random key)
gcloud secrets add-iam-policy-binding django-secret-key --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --format=none
gcloud storage buckets create gs://playable-anime-pictures --project=playable-anime --location=europe-west3 --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
gcloud storage buckets update gs://playable-anime-pictures --project=playable-anime --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0 --cors-file=infra/storage-cors.json
gcloud storage buckets add-iam-policy-binding gs://playable-anime-pictures --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectUser --format=none
gcloud iam service-accounts add-iam-policy-binding playable-anime-api@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/iam.serviceAccountTokenCreator --format=none
gcloud iam service-accounts create github-deployer --project=playable-anime '--display-name=GitHub Actions deploy'
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/run.developer --condition=None --format=none
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/run.invoker --condition=None --format=none
gcloud iam service-accounts add-iam-policy-binding playable-anime-api@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser --format=none
gcloud artifacts repositories add-iam-policy-binding playable-anime --project=playable-anime --location=europe-west3 --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/artifactregistry.writer --format=none
gcloud iam workload-identity-pools create github --project=playable-anime --location=global '--display-name=GitHub Actions' '--description=Keyless sign-in for GitHub Actions'
gcloud iam workload-identity-pools providers create-oidc playable-anime-deploy --project=playable-anime --location=global --workload-identity-pool=github '--display-name=PlayableAnime deploy workflow' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref '--attribute-condition=assertion.repository_id == '\''1444213567'\'' && assertion.repository_owner_id == '\''112938189'\'' && assertion.ref == '\''refs/heads/main'\'' && assertion.event_name == '\''workflow_dispatch'\'' && assertion.workflow_ref == '\''Mikigb77/PlayableAnime/.github/workflows/deploy.yml@refs/heads/main'\'''
gcloud iam service-accounts add-iam-policy-binding github-deployer@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser --format=none
gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID --billing-project=playable-anime --display-name=playable-anime-monthly --budget-amount=25 --calendar-period=month --filter-projects=projects/playable-anime --credit-types-treatment=exclude-all-credits --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 --threshold-rule=percent=1.0,basis=forecasted-spend

# infra/deploy.sh migrate IMAGE
gcloud run jobs deploy playable-anime-migrate --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:DIGEST --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --command=python --args=manage.py,migrate,--noinput --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=10m --cpu=1 --memory=1Gi --env-vars-file=ENV_FILE --set-secrets=DATABASE_URL=database-url-direct:latest,DJANGO_SECRET_KEY=django-secret-key:latest --labels=deployed-by=github-actions,commit-sha=COMMIT_SHA
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --wait

# infra/deploy.sh service IMAGE
gcloud run deploy playable-anime-api --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:DIGEST --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --cpu=1 --memory=1Gi --concurrency=80 --min-instances=0 --max-instances=3 --timeout=300 --cpu-boost --port=8080 --env-vars-file=ENV_FILE --set-secrets=DATABASE_URL=database-url:latest,DJANGO_SECRET_KEY=django-secret-key:latest --update-labels=deployed-by=github-actions,commit-sha=COMMIT_SHA
gcloud run services update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-latest

# infra/deploy.sh rollback REVISION
gcloud run services update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-revisions=REVISION=100

# ENV_FILE for the service: infra/cloudrun/env.yaml plus what deploy.sh adds
LLM_PROVIDER: "vertex"
VERTEX_LOCATION: "global"
LOG_LEVEL: "INFO"
OWNER_EMAILS: "mikigb77@gmail.com"
GCP_PROJECT: "playable-anime"
MEDIA_BUCKET: "playable-anime-pictures"
ALLOWED_HOSTS: "playable-anime-api-528988811295.europe-west3.run.app"
CSRF_TRUSTED_ORIGINS: "https://playable-anime-api-528988811295.europe-west3.run.app"
```
<!-- every-command:end -->
