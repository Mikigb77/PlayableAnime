# CLAUDE.md

Lucid Saga (repo: PlayableAnime, codename "Initial D") is an endless AI story game: a Flutter app plus
a Python backend on Cloud Run, Neon Postgres and Gemini on Vertex AI.

**Read [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) before any change.** It is the single source of
requirements for every agent and thread. Cite its ids (F1, A4, W13, T8, K7…) in PR descriptions.
Architecture and setup are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). The first-version work
plan, with workstreams, file ownership and the rules for parallel threads, is in
[`docs/PLAN.md`](docs/PLAN.md), and the app to backend contract is in [`docs/API.md`](docs/API.md).

## Current state vs target

- The backend is **Django + Django Ninja over ASGI** (`backend/lucid`, `accounts`, `stories`), on
  Postgres through psycopg 3. Turns run the **LangGraph turn graph on Vertex AI**
  (`backend/graph/turn`, B5 to B9) on the rules engine (`backend/engine`), streamed as server-sent
  events by `backend/stories`. Keep engine logic in plain Python with no Django or LangChain
  imports (B4).
- Errors use the API.md envelope (`lucid.errors.ApiError`), and logs are JSON with request, trace,
  user and story ids (`lucid.logs`). Tests run on Postgres (`TEST_DATABASE_URL`, a local Docker
  Postgres by default), never on Neon.
- Sign-in (T8), credits, quotas and rate limits (K1 to K8, T9), pictures (M1 to M8), ratings and
  reports (F6 to F8) and the deploy pipeline (`infra/`, [docs/DEPLOY.md](docs/DEPLOY.md)) are built.
  Merging `dev` into `main` deploys the whole backend and publishes the Android APK that the
  README links. Miki's one-time setup is in DEPLOY.md.

## Rules

1. One feature per branch and per PR, and one Neon branch per feature
   (`neon checkout <feature> --create`). Never test against the `production` branch. **Every PR
   targets `dev`, never `main`**: merging `dev` into `main` is the deploy (docs/DEPLOY.md), and CI
   fails any PR into `main` that doesn't come from `dev`.
2. Engine rules (A2–A9, C1, C10, W1–W16, E2–E7, N1, N2, G7, G8, G14, G15, G18, R2, R6, M1) are
   enforced in code with unit tests, not only in the prompt. Model nodes propose; code nodes decide.
   Logic comes first: a roll is used only where the facts leave the outcome open (A2). Outcomes
   follow cause and effect in any genre, so a clever workaround can beat a stronger foe, and that
   reasoning serves the fun: physics never blocks what the world allows, and the engine rules once,
   for good, on a player's theory about their own power, without debating physics (A9). Nothing in
   the world is timed in turns: world processes run on in-world time (W10). Nothing in the engine
   assumes a genre (G5).
3. CI must be green before merging: `uv run ruff check .`, `uv run ruff format --check .` and
   `uv run pytest` in `backend/`; `dart format --set-exit-if-changed lib test`, `flutter analyze` and
   `flutter test` in `app/`. Add tests with each change.
4. Schema changes go in a new migration. Never edit an applied one.
5. Logging follows T4–T6: structured JSON to stdout. Never log API keys, auth tokens or full prompts.
6. The published app always runs on Gemini through Vertex AI (B6): on Cloud Run the API refuses to
   start with any other `LLM_PROVIDER`. Local runs and tests may use the offline model
   (`LLM_PROVIDER=fake`). No service-account keys anywhere (B11). Vertex AI uses Application
   Default Credentials.
7. Content follows the ratings table in the requirements (Teen and Mature 17+, no explicit sex, Gemini
   only).
8. A change that alters behavior updates `docs/REQUIREMENTS.md` and the other docs in the same PR.
9. **Each thread owns its PR from start to merge into `dev`, with no review from Miki needed.** Open
   the PR against `dev`, review your own diff as a demanding outsider would (or run the code-review
   skill), fix what you find, wait for green CI, then squash-merge it into `dev` yourself. Never
   merge with red CI or unresolved review comments. A `dev` to `main` PR is the deploy: **when
   your work is in `dev` and ready, deploy it yourself without asking Miki** (Miki, 2026-11-07):
   open the PR into `main`, wait for green CI, merge it with a merge commit, never squashed, and
   watch the deploy land. Ask Miki only for decisions that change the product's goals, or for
   other irreversible production actions (a production migration that drops data, deleting
   data).
10. **Read Google Cloud yourself; never ask Miki for logs or settings.** Dispatch the read-only
    Ops workflow (`.github/workflows/ops.yml` on `main`) with a gcloud command, or none for the
    last 3 hours of the API's warnings and errors, and read its run's log
    ([DEPLOY.md](docs/DEPLOY.md#reading-google-cloud)). It changes nothing; changes go through
    `infra/` and the deploy. To read real play, export Miki's own stories, sealed to a key you
    make, through the Deploy workflow's `export_key` input
    ([DEPLOY.md](docs/DEPLOY.md#reading-the-owners-own-stories)); never print or commit story
    text (T16).
11. **A script Miki runs needs only a login.** Sign-ins open the browser and come back on a
    `localhost` callback (`gcloud auth login`, `neonctl auth`; in WSL, `BROWSER=wslview`), never
    `--no-launch-browser` or a code to copy by hand (`gh auth login --web --clipboard` copies
    GitHub's). Everything that follows from the login, such as ids, URLs and keys the CLIs can
    read, the script reads itself.
