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
uv run python manage.py seed_story you@example.com --world cultivation  # a story to play
DEBUG=1 uv run uvicorn lucid.asgi:application --reload --port 8080
```

- http://localhost:8080/v1/docs is the interactive API (OpenAPI from Django Ninja).
- http://localhost:8080/admin/ is the Django admin, for staff (B1).
- http://localhost:8080/health is the liveness check. It never touches the database (T3).

`seed_story` makes a story for an existing account from one of the example worlds (`grounded` or
`cultivation`), ready for its opening turn, without drafting one first. It prints the story id.

`draw_premise_covers` draws each starter premise's cover for Discover once, and skips the ones
already drawn unless `--force` (name premises to draw only those, and `--dry-run` shows what it
would draw and cost). With the offline model the covers are plain placeholders, which a real model
replaces on its first run; it refuses to put placeholders in a Cloud Storage bucket. Without
covers, Discover shows a glow in each genre's colour. On Cloud Run each deploy draws the missing
ones ([docs/DEPLOY.md](../docs/DEPLOY.md#drawing-the-starter-covers)).

By default `LLM_PROVIDER=fake` answers every model call with a minimal valid reply, and every
picture with a quiet gradient in the picture's shape, so everything works offline. For real
stories, either:

- send your own Gemini key in the `X-LLM-Api-Key` header (the app's Account screen does this), or
- set `LLM_PROVIDER=vertex` and give Application Default Credentials access to the
  `playable-anime` project: `gcloud auth application-default login`, signing in with the
  Google account that owns the project. Note that ADC is machine-wide, so this replaces whatever ADC you use for
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
| `LLM_PROVIDER` | `fake` | `vertex` or `fake`. Must be `vertex` on Cloud Run, or the API refuses to start (B6). |
| `GCP_PROJECT`, `VERTEX_LOCATION` | `playable-anime`, `global` | Vertex AI, and the trace links in logs. |
| `NARRATOR_MODEL` | `gemini-3.5-flash` | The narrator's model. Every graph node has its own `<NODE>_MODEL` and `<NODE>_THINKING`, with defaults in `graph/llm/config.py` (B6). |
| `GOOGLE_OAUTH_CLIENT_IDS` | none | Comma-separated OAuth client ids (web, Android, iOS) a Google ID token may be for. Empty turns Google sign-in off (`503 sign_in_unavailable`). Not secrets. |
| `OWNER_EMAILS` | none | Comma-separated. A verified Google sign-in with one of these gets the owner role and the admin (K7). Set it to your own Google email locally; production gets it from the `OWNER_EMAILS` GitHub secret, so no address is in the repo. |
| `MIN_SIGNUP_AGE` | `16` | The youngest age that can sign up, as the privacy policy says. Under 17 is Teen only (F8). |
| `TRUSTED_PROXY_HOPS` | `1` | Proxies that append to `X-Forwarded-For` (Google's front end on Cloud Run), for sign-in throttling. |
| `PICTURE_MODEL` | `gemini-3.1-flash-lite-image` | The picture model (M8), read by `graph/llm/config.py`. |
| `PICTURE_NOTE_MODEL` | `gemini-3.1-flash-lite` | Writes a scene picture's description from the finished scene (M5). |
| `MEDIA_BUCKET` | none | The private Cloud Storage bucket for pictures (M4). Unset, pictures are stored on local disk. |
| `PICTURE_ROOT` | `backend/media-local/` | Where pictures go without a bucket, served at `/media/` behind signed URLs. |
| `PICTURE_URL_TTL_S` | `3600` | How long a picture's signed URL works. |
| `STARTER_CREDIT_CENTS` | `50` | K1's starter credit, once per account. |
| `STARTER_CREDIT_POLICY` | `verified` | `verified`: Google accounts at once, email accounts once their address is verified. `all`: every account. |
| `HOUSE_PICTURES_CENTS` | `30` | The most the house pays, per account, for the first story's once-only pictures, priced as the player would have paid (K1, M7). `0` turns it off. |
| `BILLING_MARGIN` | `0.5` | Turns, drafts and pictures charge our model cost times 1 + margin (K2). |
| `TURN_RATE_PER_MINUTE` | `10` | Turns per user per minute, on any key (T9, K6). |
| `DAILY_TURN_QUOTA` | `300` | Turns per user per UTC day on our key (T9). `0` stops every turn on our key. |

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

## Story evals

The story evals (T15, T17, T18) play scripted scenarios through the real turn graph. They need no
database. Deterministic mode feeds scripted model answers and runs in CI on every PR; live mode
plays the same scripts on the real models and has a model judge score the scenes.

```bash
uv run python -m evals list                      # every scenario, its suite and its modes
uv run python -m evals run --out evals-out       # deterministic, as CI runs it (about 2 minutes)
uv run python -m evals run --only t17.time-stop  # one scenario, or every id with that prefix
LLM_PROVIDER=vertex GCP_PROJECT=playable-anime \
  uv run python -m evals run --mode live --out evals-out --history evals-out/history.jsonl
uv run python -m evals report --history evals-out/history.jsonl
# The first model's reading alone (T18), on another model, to set beside today's:
LLM_PROVIDER=vertex GCP_PROJECT=playable-anime INTERPRET_MODEL=gemini-3.5-flash \
  uv run python -m evals run --mode live --only t18.first-reading --out evals-out
```

A run's summary lists what each model step came to, a call, and what a turn played cost.

How it works, the known gaps and how to switch on the nightly live run are in
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#story-evals).

## API

The target contract is [docs/API.md](../docs/API.md). Every endpoint except `/health` and
`/v1/auth/*` needs `Authorization: Bearer <access_token>` (T8), and a player sees only their own
stories (S8). Sign-in and the account:

| Method | Path | |
| --- | --- | --- |
| POST | `/v1/auth/google` | `{id_token, birth_date?}` → `Session`. A new account needs `birth_date` (F8). |
| POST | `/v1/auth/register` | `{email, password, display_name, birth_date}` → `Session` |
| POST | `/v1/auth/login` | `{email, password}` → `Session`, throttled against guessing |
| POST | `/v1/auth/refresh` | `{refresh_token}` → `Session` with a new refresh token |
| POST | `/v1/auth/logout` | `{refresh_token}` → `204` |
| GET, PATCH, DELETE | `/v1/me` | The account, its name and content preferences, and deleting it with everything it owns (T12) |
| GET | `/v1/me/export` | Everything the account holds, as a JSON download (T12) |

To try the API locally, register in `/v1/docs` (or with curl) and use the `access_token` from the
answer with the docs page's Authorize button. Make a story by drafting and starting one, or with
`seed_story`, and play it:

| Method | Path | |
| --- | --- | --- |
| GET | `/health` | Liveness, `{"status": "ok"}` |
| GET | `/v1/premises` | Starter premises, flagship genres first, each with its genre's fixed rules (S1, G7) and its cover's signed URL once drawn |
| POST | `/v1/drafts` | `{premise?, premise_id?, rating, advanced?}` → a drafted world and character (G1, G2) |
| GET, PATCH | `/v1/drafts/{id}` | A draft, and direct edits of its summary lines and advanced fields |
| POST | `/v1/drafts/{id}/revise` | `{target, instruction}`: a change in plain words |
| POST | `/v1/drafts/{id}/start` | Creates the story from the draft (engine `graph`) → `{story_id, version}` |
| GET | `/v1/stories` | The Library: your stories, most recently played first |
| GET, PATCH, DELETE | `/v1/stories/{id}` | A story with its last scenes; rename it or change its settings; delete it |
| GET | `/v1/stories/{id}/scenes` | Older scenes, for scrollback |
| POST | `/v1/stories/{id}/turns` | A turn (`{kind, action?, choice_id?, standing?, input_mode?, expected_version}`) as server-sent events: `turn.started`, `narration.delta`, `narration.reset`, then `scene.completed` or `error` |
| GET | `/v1/stories/{id}/memory` | What the player character knows (C6) |
| GET | `/v1/stories/{id}/status` | Sheet, reputation, clock and how long ago things happened |
| POST | `/v1/stories/{id}/scenes/{turn}/image` | The scene's planned picture, drawn at most once (M3) |
| POST | `/v1/stories/{id}/scenes/{turn}/illustrate` | A picture of any scene, which the player pays for (M2) |
| GET | `/v1/stories/{id}/images/{image_id}` | A picture with a fresh signed URL |
| GET | `/v1/me/credits` | Balance and ledger, for the signed-in user (K1, K2) |
| POST | `/v1/transcriptions` | Online dictation: a recording as the body (`Content-Type: audio/wav`), `?story_id=` or `?draft_id=` and `?language=` → `{text}` (V6) |

To watch a turn stream: `curl -N -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"
-d '{"kind": "opening", "expected_version": 1}' localhost:8080/v1/stories/$STORY/turns`.

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
accounts/         Users, sign-in and the account endpoints (T8, F8, K7, T12)
  api.py          /v1/auth/* and /v1/me
  auth.py         The bearer auth on every endpoint
  tokens.py       Access tokens and rotating refresh tokens
  google.py       The Google ID token check
  throttle.py     Brute-force counters in Postgres
  rules.py        Age gate, rating limit, content preferences, owner emails
  services.py     Sign-in, sign-up, profile, delete and export
  signals.py      account_deleting and account_exporting, for other apps
stories/          Story, Scene and PendingEvent models, admin, the story API
  api.py          The story endpoints from API.md, the turn endpoint among them
  turns.py        A turn over HTTP: checks, the event stream, the one-transaction save (B7, T10)
  pending.py      Pending events between the world state and their table (B12)
  responses.py    Scenes, stories, the Library, Memory and status as the endpoints answer them
  schemas.py      The request and response shapes
  access.py       owned_story(): the caller's story, within their rating limit (S8, F8)
  export.py       Stories as plain data for the account export
  management/     seed_story: a story from an example world, for development
graph/            Model calls and the turn graph, with no Django imports (B4)
  llm/            The model layer: per-node models, retries, typed errors, telemetry, the fake
  turn/           The LangGraph turn graph (B5): nodes, prompts, the form a turn's first
                  model fills, checks before narration (C5)
evals/            The story evals (T15, T17, T18): scripted scenarios through the turn graph
  scenario.py     Scenario, the registry, the two modes
  runner.py       run_scenario, Story and Eval: turns, a reading alone, checks, known gaps,
                  the judge's calls, what each model step came to
  scripted.py     The scripted model: interpretations and narrations a scenario gives
  judge.py        The model judge and its rubrics (scenes and pictures)
  pictures.py     Live mode's pictures, drawn as the picture endpoint draws them (M5, M6)
  worlds.py       The worlds the scenarios play in
  scenarios/      One module per suite: t15, t17, t17_powers, t17_play, t18, t18_reading
  results.py      run.json, summary.md, the history file and the trend
media/            Pictures (M1 to M8): Image records, planning, drawing, storage, the picture API
  premise_covers.py  The starter premises' covers on Discover, drawn once by the house (S1)
  management/     draw_premise_covers: draws them, skipping the ones already drawn
moderation/       Reports and blocks on scenes, the review queue (F6, T16): see ARCHITECTURE.md
  api.py          POST /v1/stories/{id}/scenes/{turn}/report
  service.py      Filing a report, blocked_turns() for the scene list, reports in the export
  access.py       Who reads story text in the admin, and the mixin that hides it from others
  evals/          T15's content-line cases as data, for the eval runner (WS17)
speech/           Online dictation (V6): POST /v1/transcriptions, on Gemini 3.5 Transcribe
billing/          Credits, quotas and rate limits (K1, K2, T9): see ARCHITECTURE.md
  meter.py        start, charge, charge_image, release: the guard and charge around model calls
  credits.py      Accounts, the starter credit, the append-only ledger, summary(user)
  limits.py       Per-user fixed-window counters in Postgres
  pricing.py      Cost and charge arithmetic, K8's cost spread (plain Python)
  api.py          GET /v1/me/credits
engine/           The rules engine, plain Python with no web or model imports (B4)
  state/          World state models (C2): bible, cast, sheets, records
  contracts/      Step contracts (B5): Intent, Resolution, DirectorPlan, StateDelta
  context.py      Per-turn inputs: story settings, rating, content preferences
  rng.py          Seeded random numbers for rolls (A3)
  timekeeping.py  Duration bounds and the clock through pending events (W10, W10a)
  apply.py        apply_delta: proposed changes applied with the C1 invariants
  limits.py       The hard limits in code: adults only in romance, Teen's line, real people,
                  real-world instructions (F3, F2, G12)
  real_entities.py  Real people and organisations that never become characters or factions
  invariants.py   C1 checks on one state or between two
  labels.py       Time in words: the world's calendar, "+8 h", "2 days ago"
  visibility.py   What the player character knows (C6): the Memory and status views
  pipeline.py     The functions the turn graph calls
  samples.py      Two sample worlds for tests and development
tests/<area>/     Tests per package (engine tests in tests/engine/)
```

Keep heavy imports (model SDKs, LangChain, LangGraph) inside the code that needs them, not at module
level, so a cold start stays fast (B10, T3). A test checks that loading the app and its URLs doesn't import
them.

How a turn runs, from the request to the saved scene, is in
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md#turn-endpoint).

## Deploy to Cloud Run

Not deployed yet. Nothing goes public before rate limits and quotas (T9) join sign-in (T8). The image serves
`uvicorn lucid.asgi:application --host 0.0.0.0 --port $PORT`; before each deploy, run
`python manage.py migrate` from the same image with `DATABASE_URL` set to Neon's direct URL. The
pipeline that does both, its one-time setup, costs and rollback are in
[docs/DEPLOY.md](../docs/DEPLOY.md).
