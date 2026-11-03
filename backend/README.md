# Story API

FastAPI service that runs the story engine. Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

## Run locally

```bash
uv sync
cp .env.example .env    # optional
uv run uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080/docs for the interactive API.

By default `LLM_PROVIDER=fake` returns a canned scene, so everything works offline. For real
stories, either:

- send your own Gemini key in the `X-LLM-Api-Key` header (the app's Settings screen does this), or
- set `LLM_PROVIDER=vertex` and give Application Default Credentials access to the
  `playable-anime` project: `gcloud auth application-default login`, signing in as
  tech.garbar@gmail.com. Note that ADC is machine-wide, so this replaces whatever ADC you use for
  other projects.

## Database (Neon Postgres)

Stories are stored in Neon when `DATABASE_URL` is set; otherwise they are kept in memory. From the
repo root, the Neon CLI writes the linked branch's URLs to `.env.local`, which this service reads:

```bash
npm i -g neon            # once
neon login               # once per machine
neon env pull            # or: neon checkout <branch> --create
```

Apply migrations (`migrations/*.sql`) over the direct URL:

```bash
uv run python -m app.migrate
```

Work on a Neon branch per feature, never directly on `production`. The details are in
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#neon-postgres).

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

`tests/test_postgres.py` runs only when `TEST_DATABASE_URL` is set, and optionally
`TEST_DATABASE_URL_UNPOOLED`. Point them at a dev branch or a local Postgres, never at production:
the tests write and delete rows.

## API

| Method | Path | |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/v1/premises` | Starter premises |
| POST | `/v1/stories` | `{premise, title?}` → story with its opening scene |
| GET | `/v1/stories` | Story summaries |
| GET | `/v1/stories/{id}` | Full story |
| POST | `/v1/stories/{id}/turns` | `{choice_id}` or `{action}` → next scene and state |
| GET | `/v1/stories/{id}/memory` | World state |

Optional headers: `X-LLM-Provider: gemini` and `X-LLM-Api-Key: <key>` (bring your own key).

## Layout

```
app/
  main.py            FastAPI app and routers
  config.py          Settings from env, .env and the repo-root .env.local
  domain.py          Story, Scene, WorldState, Character, Faction, Fact
  premises.py        Starter premises
  db.py              asyncpg pool and the migration runner
  migrate.py         `python -m app.migrate`
  storage.py         StoryRepository protocol: Postgres and in-memory implementations
  api/               HTTP routes and dependencies
  engine/
    narrator.py      Prompt building and one story turn
    memory.py        Applies model-proposed state changes and enforces continuity
    schemas.py       Structured output the model must return
  llm/
    base.py          LLMProvider protocol
    gemini.py        Gemini via Vertex AI or an API key
    fake.py          Offline narrator for dev and tests
    factory.py       Picks a provider per request (BYOK first)
migrations/          SQL migrations, applied in name order
```

## Deploy to Cloud Run

Not deployed yet. Add auth first: an open endpoint lets anyone spend the Vertex budget. When ready:

```bash
gcloud run deploy playable-anime-api --source . --configuration=playable-anime --region=europe-west3 --service-account=playable-anime-api@playable-anime.iam.gserviceaccount.com --set-env-vars=LLM_PROVIDER=vertex --set-secrets=DATABASE_URL=database-url:latest
```

`europe-west3` (Frankfurt) is the same region as the Neon database. Create the `database-url`
secret first (see [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#neon-postgres)), and run
`uv run python -m app.migrate` against production before deploying a schema change.
