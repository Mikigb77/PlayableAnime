# Story API

Django and Django Ninja over ASGI (uvicorn) that runs the story engine, on Neon Postgres through
psycopg 3. Python 3.13, managed with [uv](https://docs.astral.sh/uv/). Requirements B1 to B12 and
T1 to T13 in [docs/REQUIREMENTS.md](../docs/REQUIREMENTS.md); the app contract is
[docs/API.md](../docs/API.md).

## Run locally

You need a Postgres. The quickest is a throwaway one in Docker:

```bash
docker run -d --name lucid-pg -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:18
docker exec lucid-pg createdb -U postgres lucid
```

Then:

```bash
uv sync
cp .env.example .env                      # optional; DEBUG=1 is the easy start
uv run python manage.py migrate
uv run python manage.py createsuperuser   # for the admin
DEBUG=1 uv run uvicorn lucid.asgi:application --reload --port 8080
```

- http://localhost:8080/v1/docs is the interactive API (OpenAPI from Django Ninja).
- http://localhost:8080/admin/ is the Django admin, for staff (B1).
- http://localhost:8080/health is the liveness check. It never touches the database (T3).

By default `LLM_PROVIDER=fake` returns a canned scene, so everything works offline. For real
stories, either:

- send your own Gemini key in the `X-LLM-Api-Key` header (the app's Settings screen does this), or
- set `LLM_PROVIDER=vertex` and give Application Default Credentials access to the
  `playable-anime` project: `gcloud auth application-default login`, signing in as
  tech.garbar@gmail.com. Note that ADC is machine-wide, so this replaces whatever ADC you use for
  other projects. No service-account keys anywhere (B11).

## Settings

Every setting comes from an environment variable, then `backend/.env`, then the repo-root
`.env.local` that the Neon CLI writes (`lucid/env.py`).

| Variable | Default | |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | none | Required unless `DEBUG=1`. From Secret Manager on Cloud Run (T11). |
| `DEBUG` | `0` | Never on in production. |
| `DATABASE_URL` | none; with `DEBUG=1`, the local Docker Postgres, database `lucid` | Required outside DEBUG. Neon's pooled URL for the service, its direct URL for `migrate` (B2). |
| `DATABASE_URL_UNPOOLED` | none | Neon's direct URL. When set, `migrate --database direct` uses it. |
| `ALLOWED_HOSTS` | `*` | Comma-separated. Cloud Run only routes the service's own hosts to it. |
| `CORS_ORIGINS` | `*` | Comma-separated origins for the Flutter web build. |
| `CSRF_TRUSTED_ORIGINS` | none | Comma-separated, for the admin behind a custom domain. |
| `LOG_LEVEL` | `INFO` | `DEBUG` logs story text and SQL, so never in production (T6). |
| `LLM_PROVIDER` | `fake` | `vertex` or `fake`. |
| `GCP_PROJECT`, `VERTEX_LOCATION` | `playable-anime`, `global` | Vertex AI, and the trace links in logs. |
| `NARRATOR_MODEL` | `gemini-3.5-flash` | The narrator's model. Every graph node has its own `<NODE>_MODEL` and `<NODE>_THINKING`, with defaults in `graph/llm/config.py` (B6). |

## Database (Neon Postgres)

Django migrations (`*/migrations/`) define the schema. The pooled Neon URL serves the app, with no
persistent connections and no server-side cursors because PgBouncer runs in transaction mode (B2).
Migrations run over the **direct** URL.

From the repo root, the Neon CLI writes the linked branch's URLs to `.env.local`, which this service
reads:

```bash
npm i -g neon            # once
neon login               # once per machine
neon checkout <feature> --create
cd backend && uv run python manage.py migrate --database direct
```

Work on a Neon branch per feature, never directly on `production`. The details are in
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#neon-postgres). The old FastAPI `stories` and
`schema_migrations` tables stay on Neon untouched: dropping production data needs Miki.

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Tests run on Postgres. They use `TEST_DATABASE_URL` (default
`postgresql://postgres:postgres@localhost:5432/postgres`, the Docker container above) and never
`DATABASE_URL`, so a `.env.local` pointing at Neon is never touched. pytest-django creates and drops
its own `test_*` database there. CI runs the same against a Postgres 18 service container, then
builds the image and smoke-tests it.

## API

The target contract is [docs/API.md](../docs/API.md). Until WS3's turn graph lands, these are today's
endpoints, ported from FastAPI with the same paths and shapes so the current app keeps working:

| Method | Path | |
| --- | --- | --- |
| GET | `/health` | Liveness, `{"status": "ok"}` |
| GET | `/v1/premises` | Starter premises |
| POST | `/v1/stories` | `{premise, title?}` → story with its opening scene and `version` |
| GET | `/v1/stories` | Story summaries, most recently played first |
| GET | `/v1/stories/{id}` | Full story with `version` |
| POST | `/v1/stories/{id}/turns` | `{choice_id}` or `{action, input_mode?}`, plus optional `expected_version` → `{scene, state, version}` |
| GET | `/v1/stories/{id}/memory` | World state |

Errors use the envelope from API.md: `{"error": {"code", "message", "details"}}`. A turn saves only
if no other turn was saved since it read the story, so the loser of a race gets `409
version_conflict` (T10). Optional headers: `X-LLM-Provider: gemini` and `X-LLM-Api-Key: <key>` (bring
your own key, never stored or logged), and `X-Request-Id`.

## Logging

JSON lines on stdout (`lucid/logs.py`), which Cloud Run sends to Cloud Logging. Every line has
`severity`, `message`, `request_id`, `trace_id` (from `X-Cloud-Trace-Context`, also linked as
`logging.googleapis.com/trace`), `user_id` and `story_id` (T4). `RequestContextMiddleware` opens the
context and writes one line per request with its status and duration; it binds `story_id` from the
URL, and the auth layer binds the user with `lucid.logs.bind(user_id=...)`. A streamed response keeps
its context until the stream ends. Errors carry `stack_trace` for Error Reporting (T7). Headers,
bodies and query strings are never logged, and fields named like keys, tokens, passwords or prompts
are redacted (T6).

## Layout

```
manage.py
lucid/            Django project
  settings.py     Settings from env (env.py), Neon database (B2), JSON LOGGING (B3)
  asgi.py         `lucid.asgi:application`, the ASGI app uvicorn serves
  urls.py         /health, /v1/ (Ninja), /admin/
  api.py          The Ninja API root; each app adds its router here
  errors.py       The API.md error envelope, ApiError and the error codes (T7)
  logs.py         JSON formatter and the per-request log context (T4 to T6)
  middleware.py   Request ids, trace, story id, one log line per request
  views.py        /health
accounts/         The custom User model (email login, display name, birth date, role, Google id)
stories/          Story, Scene and PendingEvent models, admin, the story API
  legacy_bridge.py  Glue between the models and the legacy narrator, removed with it by WS3
graph/            Model calls and the turn graph, with no Django imports (B4)
  llm/            The model layer: per-node models, retries, typed errors, telemetry, the fake
legacy/           Today's one-call narrator, moved unchanged from FastAPI; WS3 deletes it
engine/           The rules engine, plain Python with no web or model imports (B4)
  state/          World state models (C2): bible, cast, sheets, records
  contracts/      Step contracts (B5): Intent, Resolution, DirectorPlan, StateDelta
  context.py      Per-turn inputs: story settings, rating, content preferences
  rng.py          Seeded random numbers for rolls (A3)
  timekeeping.py  Duration bounds per kind of action (W10)
  pipeline.py     The functions the turn graph calls
  samples.py      Two sample worlds for tests and development
tests/<area>/     Tests per package (engine tests in tests/engine/)
```

Keep heavy imports (model SDKs, LangChain) inside the code that needs them, not at module level, so
a cold start stays fast (B10, T3). A test checks that loading the app and its URLs doesn't import
them.

`legacy/` is today's one-call narrator. `engine/` replaces it once the turn graph lands; see
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#engine-package-backendengine).

## Deploy to Cloud Run

Not deployed yet. Nothing goes public before auth (T8) and rate limits (T9). The image serves
`uvicorn lucid.asgi:application --host 0.0.0.0 --port $PORT`; before each deploy, run
`python manage.py migrate` from the same image with `DATABASE_URL` set to Neon's direct URL. The
pipeline that does both, its one-time setup, costs and rollback are in
[docs/DEPLOY.md](../docs/DEPLOY.md).
