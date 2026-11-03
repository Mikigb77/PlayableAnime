# Architecture

```
┌──────────────┐  HTTPS/JSON   ┌───────────────────────────┐   ┌──────────────────────────┐
│ Flutter app  │ ────────────▶ │ Story API (Django, ASGI)  │──▶│ Vertex AI: Gemini        │
│ app/         │  X-LLM-* hdrs │ Cloud Run, backend/       │   │ (or the user's own key)  │
│ iOS, Android │ ◀──────────── │ Ninja API, admin, engine  │   └──────────────────────────┘
└──────────────┘               │                           │   ┌──────────────────────────┐
                               │                           │──▶│ Neon Postgres (psycopg 3)│
                               │                           │   └──────────────────────────┘
                               │                           │   ┌──────────────────────────┐
                               │                           │──▶│ Cloud Storage: images    │
                               └───────────────────────────┘   │ (later)                  │
                                                               └──────────────────────────┘
```

## Repo layout

| Path | What |
| --- | --- |
| `app/` | Flutter client: Riverpod, go_router, http, flutter_secure_storage |
| `backend/` | Python 3.13, Django and Django Ninja over ASGI (uvicorn), managed with uv, deployed to Cloud Run. Layout in [backend/README.md](../backend/README.md#layout) and [PLAN.md](PLAN.md#target-layout) |
| `neon.ts`, `package.json` | Neon config as code (`@neon/config`). Node is used only for the Neon CLI and this config. |
| `docs/` | Product and architecture notes |
| `.github/workflows/ci.yml` | Lint and test for both halves on every PR |

## Backend

Django 6 with Django Ninja, served over ASGI by uvicorn (B1). Settings come from environment
variables (`backend/lucid/env.py`), so Cloud Run, local runs and tests differ only in their env.

- **API.** One Ninja API mounted at `/v1`, with its live OpenAPI schema at `/v1/docs`. Each Django
  app adds its own router in `lucid/api.py`. Views are async; database writes that must happen
  together run in a sync function inside `transaction.atomic()` through `sync_to_async`.
- **Errors (T7).** Every error, including a 404 outside the API, a wrong method and an unexpected
  exception, comes back as the [API.md](API.md) envelope `{"error": {"code", "message", "details"}}`. Raise
  `lucid.errors.ApiError(ErrorCode.X, ...)` from any view. An unexpected exception is logged with
  its traceback and answers `internal_error`.
- **Logging (T4 to T6, B3).** JSON lines on stdout with `severity`, `request_id`, `trace_id` (from
  `X-Cloud-Trace-Context`, also linked as `logging.googleapis.com/trace`), `user_id` and
  `story_id`. `lucid.middleware.RequestContextMiddleware` opens a context per request, binds the
  story id from the URL, and writes one line per request when it ends, or when its stream ends for
  a streamed turn. The auth layer binds the user with `lucid.logs.bind(user_id=...)`. uvicorn's own
  lines go through the same formatter, and its plain-text access log is off. Fields named like keys,
  tokens, passwords or prompts are redacted, and headers, bodies and query strings are never logged.
- **Users.** A custom `accounts.User` from the first migration: the email is the login (stored
  lowercased), with display name, birth date (F8), role (`player` or `owner`, K7) and Google
  subject id. Sign-in flows come with WS6.
- **Admin (B1).** `/admin/` for staff: users, stories with their scenes, and pending events. A
  story's world state and version are read-only there, and saving a story writes only the fields
  staff changed, so the admin never undoes a turn (B12, T10). Its static files are collected into
  the image and served by ServeStatic.
- **Cold starts (B10, T3).** `/health` never touches the database, and the service refuses to start
  without `DATABASE_URL` and `DJANGO_SECRET_KEY` outside DEBUG. Model SDKs and LangChain are
  imported inside the code that uses them, off the event loop, and a test checks that loading the
  ASGI app and its URLs doesn't import them. The image answers its first `/health` about a second after the container
  starts.

## Story engine

Today's turn still runs the one-call narrator, moved unchanged from the FastAPI app to
`backend/legacy/` and wired to the Django models by `stories/legacy_bridge.py`. WS3's LangGraph turn
graph (B5) replaces both. The legacy endpoints only serve stories the legacy narrator wrote
(`Story.engine`), so they never overwrite a graph story's state. One turn
(`backend/legacy/engine/narrator.py`):

1. **Build the prompt** from the premise, rolling summary, continuity rules, goals, known characters
   and factions, the last 3 scenes and the player's action.
2. **Call Gemini** with a JSON response schema (`NarratorOutput`): narration, 3 choices, an image
   prompt and a `state_update` describing what changed.
3. **Apply the update** (`backend/legacy/engine/memory.py`). The engine owns the invariants: a dead
   character can't come back, a destroyed faction can't be restored, affinity is clamped to ±100,
   and nameless "new" characters are ignored.
4. **Save** the new state and the scene in one transaction, only if the story's `version` is still
   the one the turn read, and bump it. The losing turn of a race gets `409 version_conflict` (T10).

How the reference app's memory layers map onto ours:

| Layer | Here |
| --- | --- |
| Long-term memory | `facts` (importance 1–5) + `summary` |
| Short-term memory | the last `RECENT_SCENES` scenes in the prompt |
| Relationships | `Character.affinity`, `Faction.stance` |
| Current goals | `goals` |

Facts with importance ≥ 4 and all deaths and destructions are restated as **continuity rules** on
every turn.

**Still to build for endless stories:** chapter summaries every N turns, and retrieval of relevant
facts and scenes with pgvector on Neon, so the prompt stays small however long the story runs.

**Still to build for narration (R1 to R7):** today's prompt asks the narrator to react to the
player's action, but not to play it out step by step from where the last scene ended before telling
the outcome, and nothing yet breaks the action into beats or stops a chained plan where it fails.

**Still to build for outcomes (A2, A9):** today the narrator model decides whether an action works
inside its one call. Nothing yet works out the facts, follows a chain of cause and effect, sorts each
step into certain, contested, long shot or ruled out, or rolls in code.

## Engine package (`backend/engine/`)

The rules engine that replaces the one-call narrator above (WS2 in [PLAN.md](PLAN.md)). It is plain
Python and Pydantic, with no Django, Ninja, LangChain or model SDK imports (B4), and
`tests/engine/test_purity.py` fails if one creeps in. The turn graph (WS3) loads the story, calls
these functions and saves the result.

| Module | What |
| --- | --- |
| `engine/state/` | The world state (C2): `WorldState`, `WorldBible` (G6, G7, G18, W11, N7), `Character` with its `CharacterSheet` (G13, A1, A8, A9), `Faction`, `Place`, `Deed`, `Rumor`, `Fact`, `Goal`, `Lead`, `Thread`, `Clock`, `PendingEvent` and `RollRecord`. |
| `engine/contracts/` | What flows between the turn's steps (B5): `Intent` (interpret), `Resolution` (resolve), `DirectorPlan` (director) and `StateDelta` (what the narrator or the engine proposes to change). |
| `engine/context.py` | `TurnContext`: the story id, the turn number, story settings (S6), rating (F2) and content preferences (F7), which live outside the world state. |
| `engine/rng.py` | `SeededRng`, the seeded random numbers behind every roll (A3). |
| `engine/timekeeping.py` | How long each kind of action may take (W10). |
| `engine/pipeline.py` | The functions the turn graph calls, with trivial default bodies that WS9, WS10 and WS11 replace. |
| `engine/samples.py` | Two sample worlds from the requirements, the Naples vendetta and the Azure Cloud Sect, for tests and development. |

**The turn, as the graph calls it** (B5). Every function takes the state as read-only and returns
a new one.

| B5 step | Function | Owner |
| --- | --- | --- |
| 1. Catch up | `catch_up(state, until_s, ctx, rng) -> TimePassage` applies events due by `until_s` (the graph passes `state.world_s`) | WS10 |
| 3. Resolve | `resolve(state, intent, ctx, rng) -> Resolution` | WS9 |
| 3. Time passes | `play_out(state, resolution, ctx, rng) -> PlayOut` plays the steps in order: the clocks move by each step's duration and the step's consequences are recorded at its end. From WS2's second PR, events due during a step fire in time order and one that needs the player cuts the plan short | WS2 |
| | `record_consequences(state, resolution, step, ctx, rng) -> WorldState`, called by `play_out` for each finished step | WS10 |
| | `apply_event(state, event, ctx, rng) -> WorldState`, called for each pending event that falls due | WS10 |
| 3. Direct | `direct(state, resolution, ctx, rng) -> DirectorPlan` | WS11 |
| 6. Apply the update | `apply_delta` with the C1 invariants (WS2's second PR) | WS2 |

**Decisions the package makes:**

- **Records are keyed by id.** `WorldState.characters`, `factions`, `places`, `deeds` and the rest
  are maps from id to record, and each record's `id` must match its key. The player character is in
  `characters` under `player_id`, so attitudes, witnesses and knowledge treat everyone the same
  way (E5). `state.new_id("deed")` hands out stable ids. Never rely on map order, because Postgres
  JSONB reorders object keys: sort by time or id wherever order matters, as `due_events` does.
- **In-world time is whole seconds since the story's epoch** (W10). Everything that happens in time
  carries a `timeline_id` and a world second (W10a). A character's personal clock is
  `world_s + personal_offset_s`, so it moves with the world for free, and a time stop only adds to
  the user's offset. World processes such as rumor spread, clock steps and faction answers are
  pending events with due times, so they fire in time order wherever time passes, at the start of
  a turn and during a long action alike. The rows live in `stories_pendingevent` (B12): the turn
  graph loads the story's pending rows on its timeline into `state.pending_events` and writes back
  the ones the turn applied, cancelled or scheduled. `EventStatus` uses the table's values
  (`pending`, `applied`, `cancelled`).
- **Knowledge is recorded on the record.** Anything a character can know carries `known_by`, a
  list of character ids, plus `met_by` on characters, `visited_by` on places and `heard_at` on
  rumors. The Memory screen shows only records whose lists hold the player character (C6). Hidden
  truth lives in fields the projection never shows: `is_true` on rumors and facts, secrets, mystery
  answers, real attitudes behind an `apparent_affinity`.
- **Proposals versus decisions.** `StateDelta` serves the narrator and the engine. Fields marked
  engine only (terminal changes such as deaths, anything that needs a C1 `Cause`, rulings, gains,
  accepted backstory, rule changes) are rejected when the narrator proposes them, because resolve
  records the outcome in code before narration (F4). Resolve puts its own changes for each step in
  `StepResolution.effects`.
- **Rolls are replayable.** The graph makes one `SeededRng.for_turn(story_id, timeline_id, turn)` per
  turn, and each seam derives child streams with stable labels, such as
  `rng.child("resolve", "step", 0)`. Draws come from SHA-256, so a seed recorded on a scene replays
  its roll on any machine, and retrying a turn never rerolls.
- **The state is stored as JSONB.** Unknown keys are ignored on load and new fields need defaults,
  so a state saved by an older engine still loads. A state whose `schema_version` is newer than the
  engine's is refused, so an old revision can't drop fields it doesn't know and save the stripped
  state back during a rolling deploy. Bump `SCHEMA_VERSION` when a field is removed or changes
  meaning.

## Model layer

`backend/graph/llm/` is the one way the backend calls a model (B6, T5, T7). It is plain Python with
no Django imports (B4), and importing it loads no model SDK: LangChain and google-genai load on the
first real call (B10). Today's one-call narrator in `backend/legacy/` still serves the legacy
endpoints until the turn graph replaces it (WS3's PR 2 and 3).

```python
telemetry = TurnTelemetry()
llm = build_client(rating=story.rating, byok=parse_byok(provider_header, key_header),
                   recorder=telemetry)
intent = await llm.structured(Node.INTERPRET, Prompt.build(system, action), Intent)
async with aclosing(llm.stream_structured(Node.NARRATOR, prompt, NarratorOutput,
                                          field="narration")) as events:
    async for event in events:  # TextDelta, StreamRestart, then Completed(value)
        ...
picture = await llm.image(Node.PICTURE, Prompt.build(style, scene, images=portraits))
```

**Nodes and models (B6, B8).** Each node has a model and defaults in `graph/llm/config.py`,
overridable with `<NODE>_MODEL` and `<NODE>_THINKING`, read like Django's settings from the
environment, `backend/.env` and the repo-root `.env.local`:

| Node | Default model | Price per 1M tokens in / out | Why |
| --- | --- | --- | --- |
| `narrator` | `gemini-3.5-flash`, thinking `low` | $1.50 / $9.00 | The one large call on the critical path. Low thinking keeps the first words under 2 s (S3). |
| `interpret` | `gemini-3.5-flash-lite`, thinking `low` | $0.30 / $2.50 | Cheap, but it reasons about cause and effect (A9), so the graph can raise its thinking for a turn that rests on a chain. |
| `checker`, `tick`, `summarizer` | `gemini-3.1-flash-lite`, thinking `low` | $0.25 / $1.50 | The cheapest model (B8). |
| `drafter` | `gemini-3.5-flash`, the model's own thinking | $1.50 / $9.00 | World and character drafts (WS12), off the turn path. |
| `picture` | `gemini-3.1-flash-lite-image` | $0.034 a 1K picture (image tokens at $30 per 1M) | The cheapest image model (M8). Bigger sizes bill more tokens. |

Prices are Vertex AI's standard prices on the `global` endpoint, checked 2026-11-03, and live in
`graph/llm/pricing.py`. A model missing from the table is priced like the dearest known model, so
the estimate never undercounts. Gemini 3.6, 3.7 and 3.8 Flash are cheaper than 3.5 Flash until the end of
2026 ($0.75 / $3.75), but stay out of the defaults until T18's narration evals have run on them.

**Providers.** `LLM_PROVIDER=vertex` uses `ChatGoogleGenerativeAI` from `langchain-google-genai`
with `vertexai=True` and Application Default Credentials (B11). `langchain-google-vertexai`'s
`ChatVertexAI` was deprecated in 3.2.0 in favour of this class, so we use it directly. Every node
shares one google-genai client (and its connections) per event loop, or per request for a player's
key. `LLM_PROVIDER=fake` (the default) is the offline model,
which answers any schema with placeholder values. Don't set `GOOGLE_API_KEY` or `LANGSMITH_TRACING`
on the service: the first changes which credentials LangChain picks, the second would send prompts
to LangSmith.

**Calls.** Every call streams from the backend, so blocks and usage look the same everywhere. The
client gives each attempt the node's deadline, counting only time spent waiting on the model and
never the caller's time between chunks, retries a transient failure (timeout, 408, 429, 499, 5xx, a
cut-off or unparseable answer) once, and otherwise raises a typed error with the API's code: `LLMUnavailable`
(`llm_unavailable`), `LLMBlocked` (`blocked`, with the categories and whether the prompt or the
response was blocked) or `BadKey` (`bad_key`, only for a player's key). A safety block is never
retried blindly: the graph retells a blocked narration as a cut-away, then a template line (F4),
and turns a blocked interpret step into `unreadable_action`.

**Streaming the narration (S3, B7).** The narrator returns one JSON object, and
`stream_structured` streams the decoded text of its `narration` field as it is written, with
`graph/llm/jsonstream.py`. The full JSON is still validated at the end. If an attempt fails after
text was shown, the client yields `StreamRestart` before retrying, which the turn endpoint sends as
`narration.reset` with reason `retry` ([API.md](API.md)).

**Safety settings (F5).** `graph/llm/safety.py` holds the table and the reasons behind it:
harassment off in Mature; hate speech, dangerous content and, in Mature, sexual content filtered
only at high probability as backstops for G12, F3 and the fade-out rule; Teen filters sexual
content from medium; pictures filter from medium, and sexual content from low (M6). WS16 tunes it
against T15's content-line evals.

**Telemetry (T5).** Each call leaves one `CallRecord` (node, model, provider, BYOK or not, outcome,
tokens in, out and thinking, pictures, latency, time to first text, attempts, retry reasons,
blocks with categories, estimated cost) with the request's `TurnTelemetry`. The turn endpoint logs
`summary()` as the turn's T5 line. `cost_usd` is always the raw cost, and billing charges the
calls made on our own account (`billable_cost_usd`; BYOK calls are free, K6) plus its margin (K2). Records hold
no prompt or story text, and a `Prompt`'s repr shows only its size (T6).

**Tests** script the fake per node: `FakeBackend().script(Node.NARRATOR, Fail(), Reply(json=...))`
for a failure and its retry, `Block(after_text=...)` for a block mid-stream, `Hang()` for a
timeout. `tests/graph/test_gemini.py` runs the real LangChain model with google-genai's network
call replaced, to check the Gemini translation: messages, safety settings, blocks, usage, errors.

## Bring your own key

- The app keeps the key in `flutter_secure_storage` and sends it per request as `X-LLM-Provider` and
  `X-LLM-Api-Key`.
- `graph.llm.parse_byok` wraps it in a `ByokKey` whose repr is masked and which refuses to be
  pickled, and `build_client` makes a Gemini API client for that request only, never cached. It is
  never persisted or logged, and error details are scrubbed of it.
- The client's base URL is pinned to `generativelanguage.googleapis.com`, so no environment
  variable (such as LangChain's `LANGSMITH_GATEWAY`) can route a player's key anywhere else.
- Only `gemini` is supported for now. A rejected key is `bad_key`, never retried.

## Voice input

Requirements: V1 to V7 in [REQUIREMENTS.md](REQUIREMENTS.md#voice-input).

**P0: the phone's own recognizer.** The app uses a Flutter plugin over the platform recognizers,
such as [`speech_to_text`](https://pub.dev/packages/speech_to_text) (7.5.0, September 2026, for
Android, iOS, macOS and web). Audio never reaches our backend: the app puts the transcript in the
action box, and the player sends it as text.

- **iOS:** add `NSMicrophoneUsageDescription` and `NSSpeechRecognitionUsageDescription` to
  `Info.plist`. Apple stops a recognition task after about a minute.
- **Android:** add the `RECORD_AUDIO` permission and, when targeting SDK 30 or later, a `<queries>`
  entry for the `android.speech.RecognitionService` intent. Recognition stops after a pause of a few
  seconds, and that can't be changed.
- Use on-device recognition where the phone has it for the story's language, so audio stays on the
  phone (V5).
- The plugin is built for short phrases, not long dictation. That fits a single action, and V2 lets
  the player add to the box with another tap.

**P1: Gemini 3.5 Transcribe on Vertex AI.** The streaming version costs about $0.009 per minute of
speech ($3.50 per million audio tokens in, $21 per million text tokens out), and the file version
about $0.005 per minute (Vertex AI pricing page, 2026-11-03). It accepts a custom vocabulary, so we
pass the names the character knows from the scene and the story (C6), most relevant first. The app
streams microphone audio over a WebSocket to our API, which relays it to Vertex AI with Application
Default Credentials (B11) and streams the words back. Audio is never written to disk or logged.
Cloud Run supports WebSockets within its request timeout (T1). Django needs Channels or a small ASGI
WebSocket route for this, to be chosen when the work starts. The Gemini API's free tier covers this
model, which suits BYOK.

**Turn API.** The turn request gains an `input_mode` field, one of `typed`, `voice`, `voice_edited`
or `choice` (V7).

## Images

Requirements: M1 to M8 in [REQUIREMENTS.md](REQUIREMENTS.md#images). Nothing is generated yet.
`Scene.image_prompt` is produced every turn today; M1 limits it to scenes that get a picture.

Gemini image models on Vertex AI, at standard prices on the global endpoint, from the [Vertex AI
pricing page](https://cloud.google.com/vertex-ai/generative-ai/pricing) on 2026-11-03:

| Model | 1K picture | Other sizes | Notes |
| --- | --- | --- | --- |
| Gemini 3.1 Flash-Lite Image ("Nano Banana 2 Lite") | $0.034 | 1K only | Cheapest. Input is $0.25 per million tokens, so a reference portrait (about 1,120 tokens) adds under $0.001. |
| Gemini Nano Banana 2.1 | $0.034 | 2K $0.050, 4K $0.113 | Same price at 1K. Input is $1.50 per million tokens, so a reference portrait adds about $0.002. Google's suggested replacement for Imagen 4. |
| Gemini 3.1 Flash Image ("Nano Banana 2") | $0.067 | 0.5K $0.045, 2K $0.101, 4K $0.15 | |
| Gemini 3 Pro Image ("Nano Banana Pro") | $0.134 | 4K $0.24 | Best quality, too dear for routine pictures. |
| Gemini 2.5 Flash Image | $0.039 | | Being retired. Don't build on it. |

- Batch and Flex prices are half, but a batch can take hours, so they fit only work that can wait.
- Imagen was shut down on 2026-08-17. Google's [migration
  guide](https://firebase.google.com/docs/ai-logic/imagen-models-migration) points to Nano Banana 2.1.
- The Gemini API's free tier has no image models, so a BYOK key on the free tier can't make pictures
  (M7).
- An open model (FLUX, SDXL) on a Cloud Run GPU is cheaper only at high volume, and it would put the
  content lines (M6) on our own filters. It's out for now: everything runs on Gemini (F2).

Plan:

1. The turn response says whether a picture is planned for the scene (M1). The app shows the text
   first, then calls an image endpoint for that scene, which generates the picture, stores it and
   returns its URL (M3). This keeps the work inside a request, as B8 requires.
2. Pictures go to a private Cloud Storage bucket in `europe-west3`, served through short-lived signed
   URLs, keyed by character, place or scene, and reused (M4).
3. A scene with known characters passes their portraits as reference images, so faces stay the same
   (M5).
4. The model is set in config per use (portrait, place, scene, cover), so it can change as prices and
   T18's picture evals change (B6, M8).

## Google Cloud

| Item | Value |
| --- | --- |
| Project | `playable-anime` (number 528988811295), owned by tech.garbar@gmail.com, billing on |
| gcloud configuration | `playable-anime` (not the active one; use `--configuration=playable-anime`) |
| Region | `europe-southwest1` (Madrid) for Cloud Run; Vertex AI on the `global` endpoint |
| APIs enabled | Cloud Run, Artifact Registry, Cloud Build, Secret Manager, Vertex AI, IAM |
| Runtime service account | `playable-anime-api@playable-anime.iam.gserviceaccount.com` with `aiplatform.user`, `secretmanager.secretAccessor`, `logging.logWriter` |
| Default narrator model | `gemini-3.5-flash` (checked working on 2026-11-03) |

Deploying is described in [backend/README.md](../backend/README.md#deploy-to-cloud-run).
**Don't deploy publicly before auth exists:** an open endpoint lets anyone spend our Vertex budget.

## Neon Postgres

| Item | Value |
| --- | --- |
| Project | `divine-rice-51324513` ("PleyableAnime") in org `org-winter-dew-32019906`, `aws-eu-central-1`, Postgres 18 |
| Branches | `production` (default). Feature branches come from `neon checkout <name> --create` and expire after 7 days (see `neon.ts`). |
| Local env | `neon deploy`, `neon checkout` and `neon env pull` write `DATABASE_URL`, `DATABASE_URL_UNPOOLED` and `NEON_BRANCH` to the repo-root `.env.local` (git-ignored). The backend reads that file. |
| Driver | psycopg 3 through Django, on the pooled URL with `CONN_MAX_AGE = 0` and `DISABLE_SERVER_SIDE_CURSORS = True`, because PgBouncer runs in transaction mode (B2). No connection stays open, so the compute can scale to zero. |
| Migrations | Django migrations (`backend/*/migrations/`), run by `python manage.py migrate` over the **direct** URL: `migrate --database direct` locally, where `DATABASE_URL_UNPOOLED` is set, or `DATABASE_URL` set to the direct URL in the deploy's migration step |
| Tests | A local or CI Postgres from `TEST_DATABASE_URL`, never `DATABASE_URL` (see [backend/README.md](../backend/README.md#test-and-lint)) |

**Schema (v2, Django).**

| Table | What |
| --- | --- |
| `accounts_user` | Players and staff (custom `User`, UUID ids). |
| `stories_story` | One row per story: owner (S8; null only until sign-in lands), title, premise, genre, rating, settings (S6), the engine that wrote it, the world state as JSONB (C2), `turn`, and `version` for T10. Only a turn writes it (B12). |
| `stories_scene` | One row per turn, unique per story and turn: kind, action and input mode (V7), narration, choices, details (A2, A9, R6), event (W16), in-world start and end seconds plus the player's own elapsed time (W10, W10a) and their labels, timeline id, and the picture fields (M1 to M3). |
| `stories_pendingevent` | Off-screen results waiting on in-world time (B12): story, timeline id, due time in in-world seconds, kind, payload, status, and the turns that scheduled and applied it. Indexed for "pending on this timeline, due by now". |

The FastAPI version's `stories` and `schema_migrations` tables are left on Neon untouched. Dropping
them deletes production data, so it waits for Miki.

**Branch-first workflow.** Per feature:
1. Run `neon checkout <feature> --create` (this repoints `.env.local`).
2. Run `uv run python manage.py migrate --database direct` in `backend/`, then test.
3. Run `neon diff` to review schema changes.
4. After merging, run `neon checkout production` and migrate again.

**Latency.** The database is in Frankfurt. Deploying Cloud Run to `europe-west3` (Frankfurt) instead
of `europe-southwest1` (Madrid) would avoid a cross-region hop on every query.

**Cloud Run.** Store the pooled URL in Secret Manager and mount it as an env var:

```bash
gcloud secrets create database-url --replication-policy=automatic --data-file=- --configuration=playable-anime
```

Then deploy with `--set-secrets=DATABASE_URL=database-url:latest`.
