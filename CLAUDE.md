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
- No auth, credits or deploy exist yet. Nothing goes public before T8 (auth) and T9 (rate limits and
  quotas).

## Rules

1. One feature per branch and per PR, and one Neon branch per feature
   (`neon checkout <feature> --create`). Never test against the `production` branch.
2. Engine rules (A2–A9, C1, W1–W16, E2–E7, N1, N2, G7, G8, G14, G15, G18, R2, R6, M1) are
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
6. No service-account keys anywhere (B11). Vertex AI uses Application Default Credentials.
7. Content follows the ratings table in the requirements (Teen and Mature 17+, no explicit sex, Gemini
   only).
8. A change that alters behavior updates `docs/REQUIREMENTS.md` and the other docs in the same PR.
9. **Each thread owns its PR from start to merge, with no review from Miki needed.** Open the PR,
   review your own diff as a demanding outsider would (or run the code-review skill), fix what you
   find, wait for green CI, then squash-merge it yourself. Never merge with red CI or unresolved
   review comments. Ask Miki only for decisions that change the product's goals, or for irreversible
   production actions (a deploy, a production migration that drops data, deleting data).
