# Deploying Lucid Saga

How the API gets to Cloud Run and the Android app to the README's download link: what Miki sets up
once, what each deploy does, what it all costs, and how to roll back. Requirements: T1, T2, T3, T8,
T9, T11, T13, B10, B11 and M4 in [REQUIREMENTS.md](REQUIREMENTS.md). The scripts are in
[`infra/`](../infra/), and the workflow is
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

## How changes reach production

Every PR goes into the `dev` branch. Threads open their PRs against `dev`, review them, wait for
green CI and merge them themselves (CLAUDE.md). **Merging `dev` into `main` is the deploy:** the
push to `main` starts the deploy workflow, which deploys the whole backend and publishes the APK.
A thread deploys its own work once it is in `dev` and ready, without asking Miki (Miki,
2026-11-07): it opens the `dev` to `main` PR, waits for green CI and merges it with **Create a
merge commit**, never squashed, so `dev` and `main` keep one history, then watches the deploy.

```text
feature branch --PR, self-reviewed, green CI--> dev --PR, green CI, merge commit--> main --> deploy
```

CI runs on every PR and on every push to `dev` and `main`. A PR into `main` from any branch but
`dev` fails CI's `into-main` check. `dev` is the default branch, so Dependabot's security updates
([below](#dependabot)) go to it like every other PR; the Workload Identity condition admits only
`main`.

The CI jobs are separate checks of the same commit (backend tests, evals, the image, the app, the
Android build, the deploy scripts), so they run side by side. The deploy's jobs are a chain
instead: the CI gate, then the deploy, then the model checks, the covers and the story pictures,
while the APK builds alongside and is published after the deploy. Every job runs on
`ubuntu-24.04` rather than `ubuntu-latest`, so a new runner image never arrives in the middle of a
deploy; moving to a newer Ubuntu is a PR of its own. Every action is pinned to a commit with its version in a comment.

### Dependabot

Dependabot watches every dependency the repository declares: the API's Python packages
(`backend/uv.lock`), its image (`backend/Dockerfile`), the app's Dart packages (`app/pubspec.lock`),
the workflows' actions and the Neon CLI config (`package-lock.json`). It is free, and stays free if
the repository goes private.

- **Alerts** list each known vulnerability under the repository's Security tab.
- **Security updates** open a PR into `dev`, the default branch, as soon as an advisory affects a
  dependency and a fixed version exists.
- **Version updates** ([`.github/dependabot.yml`](../.github/dependabot.yml)) open PRs into `dev`
  once a week (the Neon config once a month): the minor and patch updates of each ecosystem in one
  PR, each major update in its own. A release waits 7 days before it is offered, so a broken or
  hijacked release is usually pulled first. Security updates never wait.

Alerts and security updates are switched on in the repository's settings, not in the file (since
2026-11-10; `gh api repos/Mikigb77/PlayableAnime/automated-security-fixes` shows whether they still
are). Dependabot checks early on Monday (04:00 Madrid time), and a scheduled Claude pass at 06:09
works through its PRs (Miki, 2026-11-10) and posts a summary in the project by 08:00. A Dependabot
PR is merged like any other: CI must be green, a major update needs a look at its changelog, and it
is squash-merged into `dev`, then reaches production with the next deploy. If CI fails, the fix goes
on the Dependabot branch or the update is closed with the reason.

Some things stay out of Dependabot's hands. The Android build's Gradle plugins follow Flutter's
versions, and so does `intl`, which the Flutter SDK pins through `flutter_localizations`: they move
with a Flutter upgrade. Python moves to a newer minor version in a PR of its own, like the runners'
Ubuntu; the `python:3.13-slim` tag already brings its patch releases.

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
| App releases | Cloud Storage `gs://playable-anime-releases` in `europe-west3` | Private. Each deploy's APK and `android/latest.json`, which the installed app updates itself from through a signed URL (S12). The newest 3 builds are kept. |
| Deploy identity | `github-deployer@playable-anime.iam.gserviceaccount.com` | GitHub Actions signs in as it through Workload Identity Federation. No JSON key (B11). |
| Budget alert | `playable-anime-monthly` on the billing account | Emails at 50%, 90% and 100% of the month's budget, and when the forecast passes 100% (T9). |
| Database | Neon `production` branch | Pooled URL for the service, direct URL for migrations (T2, B2). |

The names live in [`infra/config.sh`](../infra/config.sh). Plain settings for the container are in
[`infra/cloudrun/env.yaml`](../infra/cloudrun/env.yaml).

## One-time setup (Miki)

These steps need Miki: they sign in as the project's owner, read the production database URLs,
create things that are billed and hold the app's signing key. Do them in this order; each one is
safe to repeat. The commands work in a bash shell (WSL on Windows, Linux or macOS) with the
[gcloud CLI](https://cloud.google.com/sdk/docs/install), the [GitHub CLI](https://cli.github.com),
the [Neon CLI](https://neon.com/docs/reference/neon-cli) (`npm i -g neonctl`) and a JDK's
`keytool` (Android Studio ships one under `jbr/bin`). The bootstrap installs gcloud itself when
it is missing and signs it in through the browser, so on [a new laptop](#on-a-new-laptop) it needs
only the repo. **Each step needs only a login in the browser:** the scripts read everything that
follows from it themselves, so nothing is copied from a console or pasted from a terminal.

1. [Sign in](#1-sign-in) to gcloud, GitHub and Neon, each in the browser.
2. [Nothing to copy from Neon](#2-the-production-urls-from-neon): the bootstrap reads the URLs.
3. [Run the bootstrap from `dev`](#3-run-the-bootstrap-from-dev), or run it again if it ran before.
4. [Make the app's signing key and give it to GitHub](#4-make-the-apps-signing-key).
5. [Set up Google sign-in](#5-set-up-google-sign-in): the consent screen, the Web and Android
   clients (both done).
6. [Allow merge commits](#6-allow-merge-commits) in the repository's settings.
7. [Give GitHub the owner email](#7-the-owner-email) as a repository secret.
8. [Dry-run the deploy](#8-dry-run-the-deploy) from `main`.
9. Merge `dev` into `main` ([How changes reach production](#how-changes-reach-production)). That is
   the first deploy.

### 1. Sign in

On a machine with this repo, sign in to the three CLIs. Each opens the browser. gcloud and neonctl
get the result back on a `localhost` callback, so there is nothing to copy; GitHub's CLI has no
such callback, and `--clipboard` puts its one-time code on the clipboard, to paste once on the
page it opens. Use the Google account that owns the `playable-anime` project and administers its
billing account:

```bash
# In WSL only: open links in the Windows browser (wslview comes with `sudo apt install wslu`).
export BROWSER=wslview            # or: export BROWSER=explorer.exe

gcloud config configurations create playable-anime --no-activate 2>/dev/null || true
gcloud --configuration=playable-anime auth login      # not --no-launch-browser
gh auth login --web --clipboard --git-protocol https
neonctl auth
```

WSL 2 forwards `localhost` between Windows and Linux, which is what lets the Windows browser reach
the CLI's callback. The scripts use the `playable-anime` gcloud configuration when it exists,
without making it the active one, and pass `--project=playable-anime` on every command anyway.
The bootstrap does its own gcloud sign-in when it is needed, so for the bootstrap alone this step
can be skipped.
Cloud Shell works too: it is already signed in to gcloud.

### 2. The production URLs from Neon

The bootstrap reads the `production` branch's pooled and direct URLs with `neonctl` (project
`divine-rice-51324513`, in `infra/config.sh`), so nothing is copied from the Neon console. It
needs them only while the `database-url` and `database-url-direct` secrets have no value; a re-run
leaves them alone. They are never printed. Without a signed-in `neonctl` it asks for them without
echoing them, or reads `NEON_PRODUCTION_DATABASE_URL` and `NEON_PRODUCTION_DATABASE_URL_DIRECT`.
Either way it refuses a URL of the wrong kind (the pooled one's host contains `-pooler`) before
changing anything.

### 3. Run the bootstrap, from `dev`

```bash
git fetch origin && git checkout dev && git pull   # this setup is on dev until the first deploy
infra/bootstrap.sh --dry-run       # prints every command, changes nothing, needs no sign-in
BUDGET_AMOUNT=25 infra/bootstrap.sh
```

On a computer without gcloud, the bootstrap installs it first: through Google's apt repository in
WSL, Debian or Ubuntu, or through Homebrew on macOS ([`infra/tools.sh`](../infra/tools.sh)). sudo
asks for the computer's password. In WSL it also installs `wslu`, so the sign-in opens the Windows
browser. When gcloud isn't signed in to an account that can see the project, the bootstrap opens
the browser to sign in, in the `playable-anime` gcloud configuration, and goes on once you have.
The Neon CLI is needed only while the database secrets have no value, which is no longer the case.

#### On a new laptop

The repo is private, so the GitHub CLI fetches it before anything else can. On Windows, WSL comes
first: `wsl --install` in PowerShell, then restart and pick a Linux user name and password. Then,
in the Ubuntu terminal:

```bash
sudo apt-get update && sudo apt-get install -y gh git wslu
gh auth login --web --git-protocol https           # GitHub shows a one-time code to enter on its page
gh repo clone Mikigb77/PlayableAnime ~/PlayableAnime -- --branch dev
~/PlayableAnime/infra/bootstrap.sh                 # installs gcloud, opens the browser to sign in
```

The one-time code is the only thing typed by hand: the GitHub CLI from Ubuntu's own packages is
older than its `--clipboard` flag.

**If the bootstrap already ran from an older `main`, run it again from `dev`.** The older one let
GitHub sign in only for deploys started by hand, so the push to `main` would be refused, and it
lacked the role that makes the API reachable. A re-run fixes both and changes nothing else.

**Run it again once after 2026-11-04's first deploy.** That version adds the read-only account
that lets threads [read Google Cloud](#reading-google-cloud) and lets the deploy print a failed
job's logs. Until then the Ops workflow can't sign in, and a failed job only says where its logs
are.

**Run it again once after 2026-11-06, before the next deploy.** That version adds step 6d, the
bucket the installed app [updates itself](#updates-in-the-app) from. Until then the deploy still
publishes the GitHub release, but its last step, which offers the build to installed apps, fails
and says to run the bootstrap.

`BUDGET_AMOUNT` is the monthly alert threshold in the billing account's currency (25 by default).
The script shows the account and project, reads the two URLs, asks for confirmation, then runs
the steps below. Running it again brings everything back in line and changes nothing that is
already right: secrets that have a value keep it, and the budget's amount is updated.

| Step | What it does | Cost |
| --- | --- | --- |
| 1. APIs | Enables Cloud Run, Artifact Registry, Secret Manager, IAM, IAM Credentials, STS, Cloud Storage, Resource Manager, Billing, Budgets, Vertex AI, Logging and Error Reporting. | Free |
| 2. Runtime account | Makes sure `playable-anime-api` has `aiplatform.user` and `logging.logWriter` (T4, T7, B11). It already exists and is never created here: the script stops before changing anything if it can't see it. | Free |
| 3. Artifact Registry | A Docker repository `playable-anime` in `europe-west3`, with a cleanup policy: keep the 10 newest images, delete the rest once 30 days old ([`artifact-cleanup.json`](../infra/artifact-cleanup.json)). | 0.5 GiB free, then about $0.10 per GiB-month. Expect a few cents a month. |
| 4. Secrets | `database-url` (pooled), `database-url-direct` and `django-secret-key` (generated), each stored in `europe-west3` only, with read access for the runtime account. | 6 versions and 10,000 reads a month are free; these are 3 versions. Free. |
| 5. Pictures bucket | `gs://playable-anime-pictures` in `europe-west3`: uniform access, public access prevention enforced, soft delete off so a deleted account's pictures are gone at once (T12), and CORS that lets the web build read signed URLs ([`storage-cors.json`](../infra/storage-cors.json)). The runtime account gets `storage.objectUser` on the bucket and `iam.serviceAccountTokenCreator` on itself, which is what [signed URLs without a key](#signed-urls-without-a-key) need. | About $0.02 per GB-month (no free tier in Europe), $0.005 per 1,000 uploads, $0.12 per GB downloaded. 1,000 pictures of about 1.5 MB cost about $0.03 a month to keep and $0.18 to view once. |
| 6. Deployer and federation | A `github-deployer` account with `run.developer` (deploy services and jobs), a custom role `lucidSagaApiAccess` with only `run.services.getIamPolicy` and `run.services.setIamPolicy` (so the deploy can [decide who may call the API](#who-may-call-the-api)), `run.invoker` (for the post-deploy health check), `logging.viewer` (to print a failed job's logs in the run), `iam.serviceAccountUser` on the runtime account only, and `artifactregistry.writer` on the repository only. A Workload Identity pool `github` with a provider that admits only `.github/workflows/deploy.yml` on `main` of this repository (by its numeric id), run by a push to `main` or started by hand. | Free |
| 6c. Read-only ops | A `github-ops` account with `viewer` and `logging.viewer`, which read every setting and log but change nothing and read no secret's value or stored picture, and a pool `github-ops` of its own whose provider admits only `.github/workflows/ops.yml` on `main`, started by hand or through the API. Being a separate pool, it can never sign in as the deployer, nor the deploy as it. See [Reading Google Cloud](#reading-google-cloud). | Free |
| 6d. App releases | A private bucket `gs://playable-anime-releases` in `europe-west3`, with no soft delete and no CORS. The deployer gets `storage.objectUser` and `storage.legacyBucketReader` on it (write and delete builds, read the bucket's settings), and the runtime account `storage.objectViewer` (read them, to sign the download URL). The deployer still gets nothing on the pictures bucket. | About $0.02 per GB-month for the newest 3 APKs (a few cents a year), $0.12 per GB downloaded: about $0.01 per phone per update. |
| 6e. Live evals | A `github-evals` account with only `aiplatform.user`, which calls Vertex AI models and nothing else, and a pool `github-evals` of its own whose provider admits only `.github/workflows/evals.yml` on `main`, nightly or started by hand. The nightly run stays off until the repository variable `EVALS_ENABLED` is `true`; by hand, from **Actions > Evals**, it runs whenever it is started. See [Story evals](ARCHITECTURE.md#switching-on-the-nightly-live-run). | Free; each run pays for its model calls: a full run $10 to $20, the picture evals alone about $2 |
| 7. Budget | A monthly budget on the project, measured before credits so free credits can't hide real usage. It alerts by email; it does not stop spending. | Free |

Every command the bootstrap and the deploy run is listed under [Every command](#every-command).

### 4. Make the app's signing key

Android only installs an update signed with the same key as the installed app, and Google sign-in
recognises the app by that key's SHA-1, so the release APK needs one key that never changes. Make
it once, outside the repo, and keep a backup: a lost key means every player has to uninstall the
app to get the next one.

```bash
# A random password; keytool asks for it twice, then for a name (anything will do).
openssl rand -base64 24 | tr -d '/+='
keytool -genkeypair -v -keystore lucid-saga-upload.jks -storetype PKCS12 -keyalg RSA \
  -keysize 4096 -validity 10000 -alias lucid

# The SHA-1 and SHA-256 fingerprints, for step 5.
keytool -list -v -keystore lucid-saga-upload.jks -alias lucid | grep -E 'SHA(1|256):'
```

Done on 2026-11-04: the release key has the alias `lucid` and the SHA-1
`BD:56:41:D0:51:B3:32:78:36:01:93:C7:B6:10:77:3A:F9:A8:FD:88` (SHA-256
`69:24:A9:DB:58:F2:9E:A3:CE:2A:4F:C4:C3:AF:DB:11:EE:E7:03:04:1A:7C:59:CD:F8:5B:DE:33:CD:14:94:3B`).
Fingerprints aren't secret; a release APK's notes show the SHA-1 it was signed with, which must
match this one.

Then the four repository secrets the deploy reads. A PKCS12 keystore has one password, so the key
password is the keystore password. `gh secret set` asks for a value when none is piped in:

```bash
base64 -w0 lucid-saga-upload.jks | gh secret set ANDROID_KEYSTORE_BASE64   # macOS: base64 -i lucid-saga-upload.jks
gh secret set ANDROID_KEYSTORE_PASSWORD
gh secret set ANDROID_KEY_PASSWORD        # the same password
gh secret set ANDROID_KEY_ALIAS --body lucid
```

In PowerShell, the first line is
`[Convert]::ToBase64String([IO.File]::ReadAllBytes("lucid-saga-upload.jks")) | gh secret set ANDROID_KEYSTORE_BASE64`.
Without these secrets the deploy still publishes the APK, signed with a throwaway debug key and
marked so in the release notes; Google sign-in doesn't work in it.

### 5. Set up Google sign-in

In the [Google Cloud console](https://console.cloud.google.com/auth/overview?project=playable-anime),
under **Google Auth Platform**:

1. **Branding and Audience** (the consent screen): app name Lucid Saga, a support email, the
   audience **External**. While it is in **Testing**, only the test users listed there can sign
   in, so add yours (and any tester's), or publish it: the app asks only for `openid`, `email` and
   `profile`, which need no Google review.
2. **Clients > Web application**: done. Its id is `GOOGLE_WEB_CLIENT_ID` in
   [`infra/config.sh`](../infra/config.sh); the deploy gives it to the API and to the APK. Client
   ids aren't secrets. Its client secret is never needed, because the app sends Google's ID token,
   so don't store it anywhere.
3. **Clients > Android**: done, with package name `com.lucid.saga` and the release key's **SHA-1**
   from step 4.
   Its id is `GOOGLE_ANDROID_CLIENT_ID` in `infra/config.sh`, and the API accepts it too. On
   Android the app asks Google for an ID token for the Web client, and Google checks the package
   name and signing key against this client, so a new signing key needs its SHA-1 added here.
   Optional, for Google sign-in in your own `flutter run` debug builds: a second Android client for
   `com.lucid.saga` with your debug key's SHA-1 (`./gradlew signingReport` in `app/android`; on
   Miki's PC it is `2F:0F:8B:06:6C:7F:E0:ED:1E:F4:AA:4F:02:27:45:78:62:0B:82:BD`). Release APKs
   don't need it, and the API doesn't need its id.
4. iOS, later: an iOS client, its id in `GOOGLE_IOS_CLIENT_ID` in `infra/config.sh`.

### 6. Allow merge commits

In the repository's **Settings > General > Pull Requests**, keep **Allow merge commits** on. A
`dev` to `main` PR is merged with a merge commit so the two branches never drift apart; other PRs
can keep squash merging.

### 7. The owner email

The owner role (K7) goes to the Google account whose email is in `OWNER_EMAILS`. The address
isn't a credential, since the role also needs a verified Google sign-in for it, but it stays out of
this public repo: the deploy reads it from a repository secret and hands it to Cloud Run. Several
owners are comma-separated. Set it once, in **Settings > Secrets and variables > Actions > New
repository secret** (it works from a phone), or with:

```bash
gh secret set OWNER_EMAILS --body "the-owner@gmail.com"
```

Without it the deploy stops at its preflight check, before it builds or changes anything. A deploy from a laptop
needs `OWNER_EMAILS` exported in the shell instead. A dry run prints the secret's name in place of
the address, because Actions logs are public while the repository is.

### 8. Dry-run the deploy

```bash
gh workflow run deploy.yml --ref main -f dry_run=true
```

Or **Actions > Deploy > Run workflow** on `main` with **Dry run** ticked. A dry run checks that CI
passed on `main`, signs in through Workload Identity Federation, checks that the bootstrap's
repository and runtime account are visible, builds the image without pushing it, builds the APK
with the signing secrets, and prints the commands it would run. It changes nothing in Google Cloud
and publishes nothing. If it fails at **google-github-actions/auth**, the bootstrap hasn't run or
the provider's condition doesn't match (see [Troubleshooting](#troubleshooting)). Until this setup
reaches `main` with the first deploy, `main`'s older workflow runs instead: it signs in and builds
the image, but not the APK.

## Deploying

Merging `dev` into `main` deploys. To deploy `main` again without a merge, run the workflow by
hand: **Actions > Deploy > Run workflow** on `main`, or `gh workflow run deploy.yml --ref main`. It
only ever deploys `main`. Two deploys never run at once, and a dry run never replaces a deploy
waiting its turn.

1. **CI passed on this commit** ([`require-green-ci.sh`](../infra/require-green-ci.sh)): the CI
   workflow's run for this exact commit of `main` must have succeeded. CI starts on the same push,
   so the deploy waits for it, up to 30 minutes. A red, cancelled or missing run stops the deploy
   (T13).
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
7. **Decide who may call the API** (`infra/deploy.sh access`): anyone, by default, so the app can
   reach it ([below](#who-may-call-the-api)). A failure here fails the run but keeps the new
   revision, which passed its health check.
8. **Check the models** (`infra/deploy.sh models`): the migration job runs
   `manage.py check_models`, which calls each model the app uses once, on the service's settings
   and account ([below](#checking-the-models)). If Vertex AI refuses one, the run fails with its
   reason, and the new revision keeps serving: rolling back wouldn't make the model answer.
9. **Draw the starter covers** (`infra/deploy.sh covers`) that are missing, or drawn in an older
   house style, in a job of its own
   ([below](#drawing-the-starter-covers)). A failure there doesn't fail the deploy.
10. **Redraw story pictures** (`infra/deploy.sh redraw`) drawn in an older house style, in a job
    of its own after the covers ([below](#redrawing-story-pictures)). A failure there doesn't fail
    the deploy either.
11. **Publish the Android app** ([below](#the-android-app)). It is built alongside steps 1 to 7,
    and published only once they pass: first as the latest GitHub release, then to the releases
    bucket (`infra/deploy.sh upload-apk`), where installed apps find it and
    [update themselves](#updates-in-the-app).

The run's summary shows the image, the new and previous revisions, the URL and the APK's link.
When the migration, the model check, the covers or the redraw job fails, the run prints that
job's own log lines, so the reason is in GitHub without opening the Cloud console.

### Checking the models

The first deploy put the API online with every call to Gemini failing, and only players found out:
"The storyteller is unavailable", and no covers. Each deploy now calls each model the app uses
once, before anyone else does. Only the models in use are called, each once whichever nodes share
it, but the voice once for each story language: today the interpret, narrator and checker models, the picture model, the speech model
(Gemini 3.5 Transcribe, sent a second of silence, V6) and the voice model (Gemini 3.8 Flash-Lite
TTS, which reads a short passage in each story language, with its language and accent such as
`es-ES`, that the speech model then writes down: the check fails if Vertex AI won't read a
language or the voice said more than the passage, V9), about 4 cents in all, most of it one small picture. The evals' judge is never called here. Each line of the output says
which model answered, or Vertex AI's reason it didn't, such as a model name that doesn't exist, a
missing permission or no quota:

```text
gemini-3.5-flash (narrator, drafter): ok in 1.4 s
gemini-3.1-flash-lite-image (picture): FAILED (invalid): GoogleModelNotFoundError: ...
```

A model that answers can still refuse a node's response format, its JSON schema, with a bare
`400 INVALID_ARGUMENT`: on 2026-11-04 every draft failed that way while plain calls worked. So the
check then sends each format once, as its node does but thinking at `low` and with room for only a
few words, which adds well under a cent. A format that meets a 429, a 5xx or a timeout is sent again
after 2 s and then 6 s. A schema Gemini refuses goes in the prompt instead
([ARCHITECTURE.md](ARCHITECTURE.md#model-layer), "Response formats"), so its line says so and the check
passes; only a format refused both ways fails it:

```text
gemini-3.5-flash-lite (interpret) Intent format: ok in 0.9 s
gemini-3.5-flash (drafter) DraftProposal format: ok in 1.1 s, though Gemini refused it as a schema, so it goes in the prompt
```

Last, it makes one explicit prompt cache on the narrator's model, as turns do
([ARCHITECTURE.md](ARCHITECTURE.md#model-layer), "Prompt caches"), sends one call that names it,
deletes it, and says how many of the call's prompt tokens Gemini read from it, which bill at a
tenth of the input price. It adds about a cent. A cache that doesn't work never fails the check,
since turns work without one, at the full price; its line says why:

```text
gemini-3.5-flash (narrator) prompt cache: Gemini read 6,012 of 6,040 prompt tokens from it, in 2.1 s
gemini-3.5-flash (narrator) prompt cache: not working (cache_failed), so turns pay the full price: ...
```

To check by hand: `gcloud run jobs execute playable-anime-migrate --project=playable-anime
--region=europe-west3 --args=manage.py,check_models --task-timeout=10m --wait`.

### Drawing the starter covers

Discover's twenty-three starter premises show a cover once the house has drawn it (S1, M4). Each
deploy runs `manage.py draw_premise_covers` as the migration job with other arguments, after the
health check. The job already has the runtime account, the Vertex AI settings, `MEDIA_BUCKET` and
the direct database URL. It skips every cover that exists in today's house style and draws the
missing ones, and those drawn in an older style (`HOUSE_STYLE_VERSION` in `media/prompts.py`,
S7), with `PICTURE_MODEL`, about $0.034 each, paid by the house (the logs show each cover's model
and cost, `Premise cover ready`, and no player's ledger changes). So only a deploy that adds
starter premises or changes the house style draws anything: the first drew the first eleven for
$0.37, the one that added the next twelve drew those for about $0.41, and the grown-up house style
(2026-11-08) draws all twenty-three once more for about $0.80. Our picture quota answered 429 after three quick drawings, so
the covers are drawn 10 s apart, and one that runs out of quota is drawn again after a minute,
twice at most. A cover that still fails, is blocked, or isn't reached before the job's 30 minutes
run out is left out and the covers job is marked failed, without failing the deploy; the covers
already drawn are kept, and the next deploy tries the rest again. Until then, and for a premise
without a cover, Discover shows a glow in the genre's colour. The app shows a new cover the next
time it loads the premises.

To draw now, or draw one again with `--force`:

```bash
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 \
  --args=manage.py,draw_premise_covers --task-timeout=30m --wait
# One cover again:   --args=manage.py,draw_premise_covers,naples-vendetta,--force
# What it would draw and cost, without drawing:   --args=manage.py,draw_premise_covers,--dry-run
```

### Redrawing story pictures

When the house style changes (`HOUSE_STYLE_VERSION`, S7), the pictures already in players' stories
are drawn once more in it too (M4). Each deploy runs `manage.py redraw_pictures` as the migration
job, after the covers, whether or not they all drew. It finds every ready portrait, place, scene
and cover drawn in an older style and draws it again with `PICTURE_MODEL`, about $0.034 each (a
scene picture's note adds a fraction of a cent), paid by the house: the logs show each one's model
and cost (`Redrawn picture ready`), and no player's ledger changes. Portraits and places go first,
so the scenes and covers are drawn with the new faces. The old drawing stays on screen until the
new one is stored, then its file is deleted; the app shows the new one the next time it loads the
story. The grown-up house style (2026-11-08) redraws the 49 pictures drawn so far for about $1.70,
and its higher-detail version (3, the same day) redraws everything drawn before it once more.

The drawings are 10 s apart, and one that runs out of quota is drawn again after a minute, twice
at most. A run spends at most $5 and starts no drawing after 45 minutes (the job has 60), so a big
redraw takes a few deploys. A picture that fails or is blocked keeps its old drawing, and the job
is marked failed without failing the deploy; the next deploy tries again. Once every picture is in
the current style, the job only starts and stops.

To draw now, or count first:

```bash
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 \
  --args=manage.py,redraw_pictures --task-timeout=60m --wait
# What it would draw and cost, without drawing:   --args=manage.py,redraw_pictures,--dry-run
# A bigger run:   --args=manage.py,redraw_pictures,--max-usd=20
```

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
| Who may call it | anyone, unless `API_ACCESS` is `private` | The API checks sign-in itself (T8). See [Who may call the API](#who-may-call-the-api). |

### What the container gets

The image must follow the runtime contract in [PLAN.md](PLAN.md#target-layout): its default command
serves `lucid.asgi:application` on `$PORT`, and `python manage.py migrate` works from its working
directory.

| Variable | From |
| --- | --- |
| `DATABASE_URL` | Secret `database-url` (pooled) for the service, `database-url-direct` for the migrate job |
| `DJANGO_SECRET_KEY` | Secret `django-secret-key` |
| `LLM_PROVIDER`, `VERTEX_LOCATION`, `LOG_LEVEL`, and later `CORS_ORIGINS` and per-node model names | [`infra/cloudrun/env.yaml`](../infra/cloudrun/env.yaml) |
| `GCP_PROJECT`, `MEDIA_BUCKET`, `GOOGLE_OAUTH_CLIENT_IDS` | `infra/config.sh`, added by `deploy.sh`. The client ids are the Web and Android clients' and, later, the iOS client's (T8). |
| `OWNER_EMAILS` | The repository secret of that name ([setup step 7](#7-the-owner-email)), added by `deploy.sh` |
| `ALLOWED_HOSTS` | The service's hostnames, comma-separated, without a scheme, added by `deploy.sh` |
| `CSRF_TRUSTED_ORIGINS` | The same hostnames as `https://` origins, for the Django admin |
| `PORT`, `K_SERVICE`, `K_REVISION` | Cloud Run itself |

Each deploy replaces every plain variable with the file's contents, so a variable removed from
`env.yaml` disappears from the service. Changing a setting is a PR to `env.yaml` and a deploy.
Variables the backend doesn't read yet are ignored until the code that needs them lands.
`LLM_PROVIDER` must be `vertex`: on Cloud Run (where `K_SERVICE` or
`CLOUD_RUN_JOB` is set) the service and its jobs refuse to start with any other value, so the
published app never answers with the offline model (B6). `MEDIA_BUCKET` is required: with
`LLM_PROVIDER=vertex` the service refuses to start without it, because pictures on one instance's
disk would be lost (M4). Cloud Run terminates TLS, and `lucid/settings.py` trusts its
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

## Reading Google Cloud

Threads, and anyone with write access to this repo, read Google Cloud through the **Ops** workflow
([`ops.yml`](../.github/workflows/ops.yml), [`infra/ops.sh`](../infra/ops.sh)), so nobody has to
open the console or bring a laptop to see a log. It runs one gcloud command and prints its output
in the run's log. It signs in as `github-ops` through its own Workload Identity pool, with no key
(B11): that account reads every setting and log, and can change nothing and read no secret's value
or stored picture. The script also refuses `auth` and `config` commands, `--account`,
`--impersonate-service-account`, token printing, service-account keys and secret values, and the
output can't issue GitHub workflow commands.

Start it on `main` with a gcloud command without `gcloud`, starting with its command group and
with flags after it, or with none for the last 3 hours of the API's and its jobs' warnings and
errors:

- In GitHub: **Actions > Ops > Run workflow**, then read the run's log.
- From a thread: dispatch `ops.yml` on `main` with the input `command`, then read the newest run's
  job log (the GitHub tools' workflow run and job log calls, or `POST
  /repos/Mikigb77/PlayableAnime/actions/workflows/ops.yml/dispatches` with
  `{"ref": "main", "inputs": {"command": "..."}}`).

```text
(empty)                                                        recent warnings and errors
logging read 'severity>=ERROR AND jsonPayload.message="Model call rejected"' --freshness=1d --limit=20
run services describe playable-anime-api --region=europe-west3 --format=yaml
run jobs executions list --job=playable-anime-migrate --region=europe-west3
projects get-iam-policy playable-anime --format=yaml
services list --enabled
```

It reads only. Changes still go through `infra/` in a PR and a re-run of the bootstrap, or through
the deploy.

## Who may call the API

T8 (sign-in) and T9 (rate limits, quotas and the budget alert) are merged, and on 2026-11-04 Miki
asked for the app to work from the APK, so each deploy lets anyone call the API: it makes sure
`allUsers` has `roles/run.invoker` on the service. Cloud Run then passes every request on, and the
API itself refuses everything but `/health` and sign-in without a signed-in player (T8), and holds
each player to the rate limits and quotas (T9). The deployer does this through the custom role
`lucidSagaApiAccess`, its only IAM permissions. They cover the IAM policy of every Cloud Run
service in the project (a role can't be granted on a service before it exists), which adds little
to `run.developer`, since deploying code as the runtime account is already more power; the deploy
uses them only to add or remove `allUsers` as an invoker.

To make it private again, in an emergency or otherwise, do both:

```bash
gcloud run services remove-iam-policy-binding playable-anime-api --project=playable-anime \
  --region=europe-west3 --member=allUsers --role=roles/run.invoker
gh variable set API_ACCESS --body private   # so the next deploys keep it private
```

Requests refused this way are not billed. To open it again, `gh variable delete API_ACCESS` (or set
it to `public`) and deploy, or run the command above with `add-iam-policy-binding`.

## The Android app

Each deploy builds the Android app with [`infra/build-apk.sh`](../infra/build-apk.sh) and, once the
API is deployed, publishes it as the asset `lucid-saga.apk` of a new GitHub release tagged
`build-<run number>`, marked as the latest. The README's link,
<https://github.com/Mikigb77/PlayableAnime/releases/latest/download/lucid-saga.apk>, always
downloads the newest. While the repository is private, only people with access to it can download.
A release asset isn't in git and doesn't count against the repository's size.

- **What it talks to:** `API_BASE_URL` is `https://playable-anime-api-528988811295.europe-west3.run.app`
  (`API_URL` in `infra/config.sh`), and `GOOGLE_WEB_CLIENT_ID` is the Web client's id from the same
  file.
- **Signing:** with the release keystore from the four `ANDROID_*` secrets
  ([setup step 4](#4-make-the-apps-signing-key)), read by
  [`app/android/app/build.gradle.kts`](../app/android/app/build.gradle.kts) from
  `ANDROID_KEYSTORE_PATH` and the passwords. Without the secrets, the debug key of that run signs
  it and the release notes say so; with only some of them, the build stops. The run's log and the
  release notes show the signing certificate's SHA-1.
- **Version:** the name comes from `app/pubspec.yaml`; the version code is the deploy workflow's
  run number, so every release installs over the one before.
- **Installing:** open the link on the phone (or drag the file onto an emulator) and allow installs
  from the browser or the Files app when Android asks.
- **Checked in CI:** CI builds the same release APK with the debug key on every PR and every push
  to `dev`, so a change that breaks the build fails its PR, not the deploy. Pushes to `main` skip
  it, because the deploy builds that commit's APK itself.

### Updates in the app

Once installed, the APK updates itself (S12): no new download from the README, and it works while
the repository is private. After publishing the GitHub release, the deploy's last step,
`infra/deploy.sh upload-apk`, uploads the same APK to `gs://playable-anime-releases` as
`android/lucid-saga-<build>.apk`, then writes `android/latest.json` with its build, version, size
and SHA-256 ([`infra/release_manifest.py`](../infra/release_manifest.py)). It keeps the newest 3
builds, and a re-run of an older run leaves a newer build in place. `GET /v1/app/latest` reads
that manifest and gives the app a 30-minute signed URL ([API.md](API.md#app-updates-s12)).

The app checks when its tabs first show and whenever it comes back to the foreground, at most every
half hour, and Account has "Check for updates". Update downloads the APK, checks it, and hands it
to Android, which asks to confirm (the first time, it also asks to allow installs from Lucid Saga
in Settings). As soon as Android starts installing, the app covers every screen with "Updating
Lucid Saga" and stays in front, since Android and Play Protect may still check the build or ask
the player; Android then replaces it, which closes the old app, and the player opens it again on
the new build. The first build with the updater has to be
installed from the README once; every build after it arrives in the app.

**On Google Play** the store updates the app, and Play's policy forbids any other way. A Play build
is built with `SELF_UPDATE=false` (`infra/build-apk.sh` reads it; the default is `true`), and drops
the `REQUEST_INSTALL_PACKAGES` and `UPDATE_PACKAGES_WITHOUT_USER_ACTION` permissions from
`app/android/app/src/main/AndroidManifest.xml`, for example through a `play` product flavor. The
plan for then (Miki, 2026-11-06): a production app through Play, and a staging app that keeps
updating itself from this bucket.

To build a release-signed APK by hand, export `ANDROID_KEYSTORE_BASE64` (or point
`ANDROID_KEYSTORE_PATH` at the keystore for a plain `flutter build apk`) and the three others, then
run `infra/build-apk.sh out/lucid-saga.apk`.

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
| Cloud Storage, app releases | The same prices. The newest 3 APKs stay, and each phone downloads each update once. | A few cents a year to keep, about $0.01 per phone per update. |
| Workload Identity Federation, service accounts, IAM, budgets, enabling APIs | Free | Free |
| Cloud Logging and Error Reporting | First 50 GiB of logs a month free | Free |
| GitHub Actions | This private repo's free plan includes 2,000 minutes a month. An Ops run takes about a minute. The APK build takes roughly 10 minutes, once in each CI run on a PR or `dev` and once in each deploy; the rest of a deploy about 10, and the CI gate waits while CI runs. Release assets are stored free. | Free at a few PRs a day; many PRs a day can use up the minutes. |
| Neon | A deploy wakes the production compute for the migration. | Seconds of compute. |
| Vertex AI (Gemini) | Per token and per picture ([ARCHITECTURE.md](ARCHITECTURE.md#images)) | The real cost, guarded by T9 and the budget alert. Each deploy's model check adds about $0.04. |

Sources: [Cloud Run](https://cloud.google.com/run/pricing),
[Artifact Registry](https://cloud.google.com/artifact-registry/pricing),
[Secret Manager](https://cloud.google.com/secret-manager/pricing) and
[Cloud Storage](https://cloud.google.com/storage/pricing) pricing pages.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `google-github-actions/auth` fails with `unauthorized_client` or `The given credential is rejected by the attribute condition` | The run isn't `deploy.yml` on `main`, or the bootstrap hasn't run, or ran from a version older than this one (it admitted only runs started by hand): run it again from `dev` or `main`. The provider admits only `push` and `workflow_dispatch` runs of `deploy.yml` on `main`. |
| The access step fails with `Permission 'run.services.setIamPolicy' denied` | The deployer lacks the `lucidSagaApiAccess` role; run the bootstrap again. |
| The access step fails with a message about `allUsers` and an organization policy | The project is under an organization whose policy blocks public members (domain-restricted sharing); an organization admin has to allow it for this project. |
| The APK step fails with `only some of the signing secrets are set` | One of the four `ANDROID_*` secrets is missing or misspelt. |
| Google sign-in fails in the app on Android | The APK is debug-signed, or the Android client's SHA-1 isn't the release key's, or your account isn't a test user of the consent screen. |
| A PR fails CI's `into-main` check | It targets `main`. Change its base branch to `dev`. |
| `Permission 'iam.serviceAccounts.getAccessToken' denied` | The `workloadIdentityUser` binding on `github-deployer` is missing; re-run the bootstrap. |
| Preflight can't see the repository or the runtime account | The bootstrap hasn't run, or ran on another project. |
| The deploy fails with `does not have permission to access secret` | The runtime account lost `secretAccessor` on a secret; re-run the bootstrap. |
| `/health` answers 400 | Django rejected the host: the backend must read `ALLOWED_HOSTS`. |
| `/health` answers 401 or 403 | The smoke test's ID token was refused; check that `github-deployer` still has `run.invoker`. |
| The migrate job fails at once | The image lacks `manage.py` in its working directory, or `DATABASE_URL` isn't the direct URL. See the job's logs, which the run prints. |
| "Check the models" fails | The run prints each model's answer and Vertex AI's reason. `NotFound` means the model name in `backend/graph/llm/config.py` (or a `<NODE>_MODEL` setting) doesn't exist in Vertex AI at `VERTEX_LOCATION`; `PermissionDenied` means the runtime account lacks `aiplatform.user`; `transient_429` means no quota for that model. |
| "Check the models" says a response format was refused | Gemini refused that node's JSON schema both as a schema and in the prompt, so the node can't answer players. The line carries Vertex AI's reason. Shrink the Pydantic model in `graph/` (fewer optional fields in a row, smaller enums, fewer `anyOf` branches) and check again. |
| Covers fail with `rate_limited` in their `Premise cover skipped` lines | The picture quota stayed spent through both waits. Run the covers job again later, or raise `RATE_LIMIT_WAIT_S` in `backend/media/premise_covers.py`. |
| A failed job prints `They couldn't be read here` | The deployer lacks `logging.viewer`: re-run the bootstrap. |
| The Ops workflow fails at the sign-in | The bootstrap hasn't run since the Ops workflow was added, or the run isn't on `main`. |
| The bootstrap says it can't install gcloud by itself | The computer has neither apt nor Homebrew. Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install), or on a Mac [Homebrew](https://brew.sh), and run it again. |
| The bootstrap's sign-in prints a command to run on another machine instead of opening a browser | gcloud found no browser. In WSL, `sudo apt-get install -y wslu` and run it again; elsewhere, run it from a terminal on the desktop. |

## Changing or removing the setup

Change a name or a setting in `infra/` in a PR, then re-run `infra/bootstrap.sh`. To change the
budget, re-run it with a new `BUDGET_AMOUNT`.

Removing pieces is Miki's call and can't be undone; each command below deletes its data:
`gcloud run services delete playable-anime-api`, `gcloud run jobs delete playable-anime-migrate`,
`gcloud artifacts repositories delete playable-anime --location=europe-west3`,
`gcloud storage rm --recursive gs://playable-anime-pictures`, `gcloud secrets delete <name>`,
`gcloud iam workload-identity-pools delete github --location=global` (it can be undeleted for 30
days, and the bootstrap does that if it finds it deleted), the same for `github-ops` and `github-evals`, and
`gcloud iam service-accounts delete github-deployer@playable-anime.iam.gserviceaccount.com` (or
`github-ops@…`, `github-evals@…`) and
`gcloud iam roles delete lucidSagaApiAccess` (it can be undeleted for 7 days, and the bootstrap
does that), each with `--project=playable-anime`. Never delete the runtime account. Old releases
can be deleted from the repository's **Releases** page; the latest one is what the README links.

## Every command

Printed from the dry runs by [`infra/tests/print-commands.sh`](../infra/tests/print-commands.sh);
CI fails if this copy falls out of date. A dry run assumes nothing exists yet, so it shows every
create; a real run skips what already exists. On a re-run the bootstrap instead updates the
provider (`update-oidc` with the same flags), the custom role (`iam roles update` with the same
permissions) and the budget (`billing budgets update <budget> --budget-amount=…`), and undeletes a
pool, provider or role that was deleted. On the first deploy,
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
gcloud iam roles create lucidSagaApiAccess --project=playable-anime '--title=Lucid Saga API access' '--description=Decide who may call the API: make it public or private again' --permissions=run.services.getIamPolicy,run.services.setIamPolicy --stage=GA
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=projects/playable-anime/roles/lucidSagaApiAccess --condition=None --format=none
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/run.invoker --condition=None --format=none
gcloud iam service-accounts add-iam-policy-binding playable-anime-api@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser --format=none
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/logging.viewer --condition=None --format=none
gcloud artifacts repositories add-iam-policy-binding playable-anime --project=playable-anime --location=europe-west3 --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/artifactregistry.writer --format=none
gcloud iam workload-identity-pools create github --project=playable-anime --location=global '--display-name=GitHub Actions' '--description=Keyless sign-in for GitHub Actions'
gcloud iam workload-identity-pools providers create-oidc playable-anime-deploy --project=playable-anime --location=global --workload-identity-pool=github '--display-name=PlayableAnime deploy workflow' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref '--attribute-condition=assertion.repository_id == '\''1444213567'\'' && assertion.repository_owner_id == '\''112938189'\'' && assertion.ref == '\''refs/heads/main'\'' && (assertion.event_name == '\''push'\'' || assertion.event_name == '\''workflow_dispatch'\'') && assertion.workflow_ref == '\''Mikigb77/PlayableAnime/.github/workflows/deploy.yml@refs/heads/main'\'''
gcloud iam service-accounts add-iam-policy-binding github-deployer@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser --format=none
gcloud iam service-accounts create github-ops --project=playable-anime '--display-name=GitHub Actions read-only ops'
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-ops@playable-anime.iam.gserviceaccount.com --role=roles/viewer --condition=None --format=none
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-ops@playable-anime.iam.gserviceaccount.com --role=roles/logging.viewer --condition=None --format=none
gcloud iam workload-identity-pools create github-ops --project=playable-anime --location=global '--display-name=GitHub Actions ops' '--description=Keyless read-only sign-in for the Ops workflow'
gcloud iam workload-identity-pools providers create-oidc playable-anime-ops --project=playable-anime --location=global --workload-identity-pool=github-ops '--display-name=PlayableAnime ops workflow' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref '--attribute-condition=assertion.repository_id == '\''1444213567'\'' && assertion.repository_owner_id == '\''112938189'\'' && assertion.ref == '\''refs/heads/main'\'' && assertion.event_name == '\''workflow_dispatch'\'' && assertion.workflow_ref == '\''Mikigb77/PlayableAnime/.github/workflows/ops.yml@refs/heads/main'\'''
gcloud iam service-accounts add-iam-policy-binding github-ops@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github-ops/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser --format=none
gcloud storage buckets create gs://playable-anime-releases --project=playable-anime --location=europe-west3 --default-storage-class=STANDARD --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
gcloud storage buckets update gs://playable-anime-releases --project=playable-anime --uniform-bucket-level-access --public-access-prevention --soft-delete-duration=0
gcloud storage buckets add-iam-policy-binding gs://playable-anime-releases --project=playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectUser --format=none
gcloud storage buckets add-iam-policy-binding gs://playable-anime-releases --project=playable-anime --member=serviceAccount:github-deployer@playable-anime.iam.gserviceaccount.com --role=roles/storage.legacyBucketReader --format=none
gcloud storage buckets add-iam-policy-binding gs://playable-anime-releases --project=playable-anime --member=serviceAccount:playable-anime-api@playable-anime.iam.gserviceaccount.com --role=roles/storage.objectViewer --format=none
gcloud iam service-accounts create github-evals --project=playable-anime '--display-name=GitHub Actions live evals'
gcloud projects add-iam-policy-binding playable-anime --member=serviceAccount:github-evals@playable-anime.iam.gserviceaccount.com --role=roles/aiplatform.user --condition=None --format=none
gcloud iam workload-identity-pools create github-evals --project=playable-anime --location=global '--display-name=GitHub Actions evals' '--description=Keyless sign-in for the live evals workflow'
gcloud iam workload-identity-pools providers create-oidc playable-anime-evals --project=playable-anime --location=global --workload-identity-pool=github-evals '--display-name=PlayableAnime evals workflow' --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping=google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id,attribute.ref=assertion.ref,attribute.event_name=assertion.event_name,attribute.workflow_ref=assertion.workflow_ref '--attribute-condition=assertion.repository_id == '\''1444213567'\'' && assertion.repository_owner_id == '\''112938189'\'' && assertion.ref == '\''refs/heads/main'\'' && (assertion.event_name == '\''schedule'\'' || assertion.event_name == '\''workflow_dispatch'\'') && assertion.workflow_ref == '\''Mikigb77/PlayableAnime/.github/workflows/evals.yml@refs/heads/main'\'''
gcloud iam service-accounts add-iam-policy-binding github-evals@playable-anime.iam.gserviceaccount.com --project=playable-anime --member=principalSet://iam.googleapis.com/projects/528988811295/locations/global/workloadIdentityPools/github-evals/attribute.repository_id/1444213567 --role=roles/iam.workloadIdentityUser --format=none
gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID --billing-project=playable-anime --display-name=playable-anime-monthly --budget-amount=25 --calendar-period=month --filter-projects=projects/playable-anime --credit-types-treatment=exclude-all-credits --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 --threshold-rule=percent=1.0,basis=forecasted-spend

# infra/deploy.sh migrate IMAGE
gcloud run jobs deploy playable-anime-migrate --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:DIGEST --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --command=python --args=manage.py,migrate,--noinput --tasks=1 --parallelism=1 --max-retries=0 --task-timeout=10m --cpu=1 --memory=1Gi --env-vars-file=ENV_FILE --set-secrets=DATABASE_URL=database-url-direct:latest,DJANGO_SECRET_KEY=django-secret-key:latest --labels=deployed-by=github-actions,commit-sha=COMMIT_SHA
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --wait

# infra/deploy.sh service IMAGE
gcloud run deploy playable-anime-api --project=playable-anime --region=europe-west3 --image=europe-west3-docker.pkg.dev/playable-anime/playable-anime/api@sha256:DIGEST --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --cpu=1 --memory=1Gi --concurrency=80 --min-instances=0 --max-instances=3 --timeout=300 --cpu-boost --port=8080 --env-vars-file=ENV_FILE --set-secrets=DATABASE_URL=database-url:latest,DJANGO_SECRET_KEY=django-secret-key:latest --update-labels=deployed-by=github-actions,commit-sha=COMMIT_SHA
gcloud run services update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-latest

# infra/deploy.sh access (API_ACCESS=private removes the same binding instead)
gcloud run services add-iam-policy-binding playable-anime-api --project=playable-anime --region=europe-west3 --member=allUsers --role=roles/run.invoker --format=none

# infra/deploy.sh models
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,check_models --task-timeout=10m --wait

# infra/deploy.sh covers
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,draw_premise_covers --task-timeout=30m --wait

# infra/deploy.sh redraw
gcloud run jobs execute playable-anime-migrate --project=playable-anime --region=europe-west3 --args=manage.py,redraw_pictures --task-timeout=60m --wait

# infra/deploy.sh upload-apk APK (BUILD_NUMBER=42, VERSION_NAME=1.0.0)
gcloud storage cp APK gs://playable-anime-releases/android/lucid-saga-42.apk --content-type=application/vnd.android.package-archive
gcloud storage cp MANIFEST gs://playable-anime-releases/android/latest.json --content-type=application/json --cache-control=no-store

# infra/deploy.sh rollback REVISION
gcloud run services update-traffic playable-anime-api --project=playable-anime --region=europe-west3 --to-revisions=REVISION=100

# ENV_FILE for the service: infra/cloudrun/env.yaml plus what deploy.sh adds
LLM_PROVIDER: "vertex"
VERTEX_LOCATION: "global"
LOG_LEVEL: "INFO"
GCP_PROJECT: "playable-anime"
MEDIA_BUCKET: "playable-anime-pictures"
RELEASES_BUCKET: "playable-anime-releases"
ALLOWED_HOSTS: "playable-anime-api-528988811295.europe-west3.run.app"
CSRF_TRUSTED_ORIGINS: "https://playable-anime-api-528988811295.europe-west3.run.app"
GOOGLE_OAUTH_CLIENT_IDS: "528988811295-lnn9hj7ddlpr84s31ltco5n9eq3i4g18.apps.googleusercontent.com,528988811295-c2t6dchelulruu7hgl4mem4kr733d346.apps.googleusercontent.com"
OWNER_EMAILS: "<the OWNER_EMAILS secret>"
```
<!-- every-command:end -->
