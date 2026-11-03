# CLAUDE.md

Lucid Saga (repo: PlayableAnime, codename "Initial D") is an endless AI story game: a Flutter app plus
a Python backend on Cloud Run, Neon Postgres and Gemini on Vertex AI.

**Read [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) before any change.** It is the single source of
requirements for every agent and thread. Cite its ids (F1, A4, W13, T8, K7…) in PR descriptions.
Architecture and setup are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Current state vs target

- The backend is still **FastAPI** (`backend/app`). The agreed target is **Django + Django Ninja over
  ASGI, with a LangGraph turn graph on Vertex AI** (B1 to B12). Until that migration lands, keep new
  engine logic in plain Python with no web-framework imports (B4), so it moves over unchanged.
- No auth, credits or deploy exist yet. Nothing goes public before T8 (auth) and T9 (rate limits and
  quotas).

## Rules

1. One feature per branch and per PR, and one Neon branch per feature
   (`neon checkout <feature> --create`). Never test against the `production` branch.
2. Engine rules (A2–A8, C1, W1–W16, E2–E7, N1, N2) are enforced in code with unit tests, not
   only in the prompt. Model nodes propose; code nodes decide. Nothing in the world is timed in
   turns: world processes run on in-world time (W10).
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
