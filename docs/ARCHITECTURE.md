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
                               │                           │──▶│ Cloud Storage: pictures  │
                               └───────────────────────────┘   │ (private, signed URLs)   │
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
  lowercased), with display name, birth date (F8), role (`player` or `owner`, K7), Google subject
  id, whether the email is verified, and content preferences (F7). Sign-in is described in
  [Accounts and sign-in](#accounts-and-sign-in).
- **Admin (B1).** `/admin/` for staff: users, stories with their scenes, and pending events. A
  story's world state and version are read-only there, and saving a story writes only the fields
  staff changed, so the admin never undoes a turn (B12, T10). Its static files are collected into
  the image and served by ServeStatic.
- **Cold starts (B10, T3).** `/health` never touches the database, and the service refuses to start
  without `DATABASE_URL` and `DJANGO_SECRET_KEY` outside DEBUG. Model SDKs and LangChain are
  imported inside the code that uses them, off the event loop, and a test checks that loading the
  ASGI app and its URLs doesn't import them. The image answers its first `/health` about a second after the container
  starts.

## Accounts and sign-in

Requirements T8, S8, F8, K7 and T12; the endpoints are in [API.md](API.md#auth-and-account-t8-s8-f8-k7-t12).
The code is in `backend/accounts/`.

- **No Firebase (T8).** The app signs in with Google and sends the ID token once.
  `accounts/google.py` checks it with `google-auth` against Google's public certificates (cached
  for as long as Google's `Cache-Control` allows, refetched when a token names a new key, at most
  once a minute): signed with RS256 by Google, issued by `accounts.google.com`, unexpired, and for
  one of the OAuth clients in `GOOGLE_OAUTH_CLIENT_IDS`. Email and password accounts use Django's
  own password hashing and validators.
- **Our tokens (`accounts/tokens.py`).** An access token lives 15 minutes. It is signed with
  `DJANGO_SECRET_KEY` (HMAC-SHA256 through `django.core.signing`, so no extra dependency) and names
  the user and the session. A refresh token is 256 random bits, stored only as a SHA-256 hash, good
  for one refresh within 30 days. Each refresh rotates it inside the same session
  (`AuthSession`); a spent token used again after a 60-second leeway revokes the session, since two
  holders means one stole it. Rotating `DJANGO_SECRET_KEY` signs everyone out within 15 minutes
  unless the old key goes in `SECRET_KEY_FALLBACKS`.
- **Every request (`accounts/auth.py`).** One Ninja auth on the whole API: it checks the access
  token's signature and age without the database, then loads the session with its user in one
  query, so logout, a revoked session, a disabled account and a deleted account all take effect at
  once. It binds `user_id` to the request's log context (T4). Only `/v1/auth/*` opts out, and
  `/health` lives outside Ninja.
- **Ownership (S8, F8).** `stories/access.py` `owned_story()` loads a story for the signed-in
  player: `404` when it doesn't exist, `403` when it is someone else's or its rating is above the
  account's limit. Every story endpoint goes through it.
- **Owner role (K7).** A Google sign-in whose verified email is in `OWNER_EMAILS` gets
  `role = owner` with `is_staff` and `is_superuser`, and loses them at the next Google sign-in if
  it leaves the list. A password never grants it, and the role is read-only in the admin. The
  owner signs in with Google, so to use `/admin/` with a password, set one once with
  `python manage.py changepassword mikigb77@gmail.com` against the target database.
- **Taking over an email.** Email accounts are unverified until an email provider exists. When a
  verified Google sign-in matches an email account, it takes that account over and drops its
  password, because someone may have signed up first with an address they don't own.
- **Brute force (`accounts/throttle.py`).** Fixed-window counters in Postgres, so they hold across
  Cloud Run instances: 10 wrong passwords per email and 100 per address in 15 minutes, and 10
  new accounts per address per hour. Each attempt is counted before it runs, in one atomic
  upsert, so parallel guesses can't all slip under a limit, and a correct password or a sign-up
  that fails validation is handed back. Keys are HMACs, so the table holds no emails or addresses. The
  address is the `X-Forwarded-For` entry `TRUSTED_PROXY_HOPS` from the right (1 on Cloud Run, where
  Google's front end appends the address it saw). Per-user rate limits on the rest of the API are
  T9's, in `billing/`.
- **Delete and export (T12).** `DELETE /v1/me` sends `accounts.signals.account_deleting` and then
  deletes the user through the ORM inside one transaction, so stories, scenes, pending events,
  sessions and anything else with a foreign key to them cascade, and picture files are removed on
  commit. `GET /v1/me/export` collects the account and its stories (`stories/export.py`, without
  the hidden world state) and asks `account_exporting` receivers for more, such as pictures.
- **Sign in with Apple** is left for the App Store launch. Apple's guideline 4.8 requires it on iOS
  once Google sign-in is offered there. It fits the same shape: the app sends Apple's identity
  token to a `POST /v1/auth/apple`, which checks it against Apple's public keys (audience is our
  bundle id or Services ID), keeps Apple's stable `sub` on the user like `google_sub`, and issues
  our own tokens. Apple may hide the email behind a private relay address and sends the name only
  on the first sign-in, so both are saved then. It needs the Apple developer account.

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
| `engine/timekeeping.py` | How long each kind of action may take, and `advance_clock`, which moves the world clock through pending events in time order and stops at the first that needs the player (W10, W10a). |
| `engine/apply.py` | `apply_delta`: a proposed `StateDelta` applied with the C1 invariants, on behalf of the narrator or the engine, returning the new state and what it refused. |
| `engine/invariants.py` | `check_state` and `check_transition`: every C1 invariant on one state or between two, however they were made. |
| `engine/labels.py` | Time in words: dates in the world's calendar, "+8 h", "World: +0 s. You: +40 s.", "2 days ago", and the scene's time bar (W10, W10a). |
| `engine/visibility.py` | The C6 projection: `memory_view` and `status_view` in the shapes of API.md's `MemoryView` and `StatusView`. |
| `engine/pipeline.py` | The functions the turn graph calls, with default bodies that WS9, WS10 and WS11 replace. |
| `engine/samples.py` | Two sample worlds from the requirements, the Naples vendetta and the Azure Cloud Sect, for tests and development. |

**The turn, as the graph calls it** (B5). Every function takes the state as read-only and returns
a new one.

| B5 step | Function | Owner |
| --- | --- | --- |
| 1. Catch up | `catch_up(state, until_s, ctx, rng) -> TimePassage` applies events due by `until_s` (the graph passes `state.world_s`) in time order through `apply_event`, stopping at the first that needs the player. Nothing fires during a time stop | WS10 |
| 3. Resolve | `resolve(state, intent, ctx, rng) -> Resolution` | WS9 |
| 3. Time passes | `play_out(state, resolution, ctx, rng) -> PlayOut` plays the steps in order. The world catches up to each step's end through `catch_up` (one loop for every stretch of time, with the turn's own `rng`, so an event rolls the same however time is split into steps), and the actor's clock moves by their lived time. An event that needs the player cuts the plan short there (the cut step's effects and deeds don't happen, and later steps go to `unplayed`). At each finished step's end its `effects` apply as the engine's, then its consequences are recorded. The graph must not apply `effects` again | WS2 |
| | `record_consequences(state, resolution, step, ctx, rng) -> WorldState`, called by `play_out` for each finished step | WS10 |
| | `apply_event(state, event, ctx, rng) -> WorldState`, called for each pending event that falls due | WS10 |
| 3. Direct | `direct(state, resolution, ctx, rng) -> DirectorPlan` | WS11 |
| 6. Apply the update | `apply_delta(state, delta, ctx, source=DeltaSource.NARRATOR) -> Applied`. Refused changes come back in `Applied.rejected` for the log and the C5 check; the rest applies. Before saving, the graph runs `check_transition(first, last)`, and a violation is an engine bug: log it and don't save | WS2 |

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
  engine only (terminal changes such as deaths, anything that needs a C1 `Cause`, faction
  reputation, rulings, gains, accepted backstory, rule changes) are rejected when the narrator
  proposes them, because resolve records the outcome in code before narration (F4). Resolve puts
  its own changes for each step in `StepResolution.effects`. The narrator can still introduce
  people, places and factions with real names, nudge an attitude by up to 10 points per scene,
  record facts, items and leads, and end the scene. A death, destruction or ruin is undone only by
  a `Cause` that points at a recorded deed or a fired event naming the subject, on this timeline,
  no earlier than the change it undoes, by a mechanism the world bible allows (resurrection, a
  presumed death that was false, a revival with survivors, rebuilding).
- **What the player sees** (C6). `engine.visibility` reads only records whose knowledge lists
  hold the player character: `known_by`, `met_by`, `visited_by`, `Rumor.heard_at`, and the
  `known_by` on each status change, so an off-screen death shows only once the player hears of
  it. A witness the player didn't notice (a hidden watcher, anyone immune to a time stop) is on
  `Deed.unnoticed_witness_ids`, so the deed reads as unseen. People show the attitude they let
  on (`apparent_affinity`), never trust or what they hide.
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

Requirements: M1 to M8 in [REQUIREMENTS.md](REQUIREMENTS.md#images). The pictures backend is
`backend/media/` (WS8), described [below](#how-pictures-work). The legacy narrator still writes
`Scene.image_prompt` every turn; M1 limits it to scenes that get a picture once the turn graph lands.

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

### How pictures work

```text
turn (WS3)            the director decides a scene gets a picture (M1, WS11)
  └─ media.plans.plan_picture(scene, kind, subject_id, trigger, brief)   in the turn's transaction
app                   shows the narration, then asks for the picture in its own request (M3, B8)
  └─ POST /v1/stories/{id}/scenes/{turn}/image  →  media.service.scene_picture
       claim (row lock) → hold credits → draw on graph.llm → store → mark ready + charge (one txn)
```

- **One `Image` per subject (M4).** `media.Image` is keyed by story, kind (portrait, place, scene,
  cover), subject (a character id, a place id, `turn-12`, `cover`) and version. A portrait or place
  is drawn once and every later scene that shows it links to the same row through
  `media.ScenePicture`. A planned subject that was skipped is planned again the next time it comes
  up. `plan_picture(..., redraw=True)` with a new appearance draws a character's portrait again as
  the next version, once per change (M5); the earlier portrait goes along as the reference.
- **What to draw (S7, M5, M6).** The turn stores a `Brief` with the plan: the narrator's image
  prompt, the world's genre, era, tone and setting from the bible, and the known characters in the
  picture with the appearance from their entry (C9). `media/prompts.py` turns it into the prompt:
  one house style for every picture (the app's cinematic, dark-first look), the world's own era,
  the framing and aspect ratio per kind (portraits and covers 3:4, places and scenes 16:9), and the
  mild-in-every-rating rules. Ready portraits of up to three known characters go along as reference
  images. The picture safety settings in `graph.llm.safety` back the rules up in every rating. A
  scene nobody wrote an image prompt for (Illustrate on any scene) is described by the end of its
  narration, which the same rules keep mild.
- **Drawing (M8, B6).** `media.drawing` draws through the model layer's `picture` node
  (`PICTURE_MODEL`, default `gemini-3.1-flash-lite-image` at 1K), with its one retry, typed
  failures and call records. A player's own key draws for free (K6); a key that can't draw, such as
  a free-tier key, which has no image models, falls back to credits (M7).
- **At most once (M3).** The first request to find a picture planned claims it under a row lock
  and draws it inside that request; requests that arrive meanwhile answer `pending`. A claim is a
  lease of 300 seconds, longer than a Cloud Run request can live, so a claim left by a request that
  died is taken over, at most three attempts in all. The first request to finish wins: a late one
  keeps the winner's picture, charges nothing and deletes its own file. A failure, a block or no
  credits marks the picture `skipped`, and a repeat answers `skipped` without drawing again; only
  Illustrate tries a skipped picture again.
- **Paying (M7, K7).** `media/billing.py` is the seam to WS7's credit meter: `start` holds the
  estimated price before drawing on our account (no credits: skipped; a rate limit: the API's
  `rate_limited`, with the picture planned again), `charge` takes the real cost plus margin in the
  transaction that marks the picture ready, and `release` lets a hold go when the picture isn't
  drawn. Until the meter lands, pictures are free and the owner's are recorded as the owner's.
- **Storage (M4, B11).** `MEDIA_BUCKET` names the private Cloud Storage bucket,
  `gs://playable-anime-pictures` in `europe-west3`, made by WS5's bootstrap; files are
  `stories/<story id>/<image id>.png`. The app gets V4 signed URLs that last
  `PICTURE_URL_TTL_S` (an hour by default), signed through IAM's signBlob as the runtime service
  account with Application Default Credentials, so no key file exists. That needs
  `roles/iam.serviceAccountTokenCreator` for the service account on itself and object access on the
  bucket ([DEPLOY.md](DEPLOY.md#signed-urls-without-a-key)). A URL is reused while more than half its life remains, so a list of
  scenes doesn't sign the same picture again. Without a bucket, files go to `PICTURE_ROOT`
  (`backend/media-local/`) and `/media/<key>` serves them behind an HMAC-signed, expiring URL.
- **Deleting and exporting (T12).** Deleting a story or an account cascades to its pictures, and a
  `post_delete` receiver removes each file once the transaction commits, so a delete that rolls
  back keeps them. The account export (WS6's `account_exporting` signal) lists every ready picture
  with a fresh URL.
- **Showing pictures elsewhere.** `media.lookups` gives the story, library and memory endpoints
  `Scene.image`, portrait URLs and covers in one query each, and the export list.
- **Logs (T5, T6).** Each picture drawn or skipped writes one `media.pictures` line with a
  `picture` object: image id, kind, version, status, skip reason, trigger, model, cost, payer, BYOK
  and fallback, references, block categories, latency and size. The prompt and the key never
  appear.

## Google Cloud

| Item | Value |
| --- | --- |
| Project | `playable-anime` (number 528988811295), owned by tech.garbar@gmail.com, billing on |
| gcloud configuration | `playable-anime` (not the active one; use `--configuration=playable-anime`) |
| Region | `europe-west3` (Frankfurt), next to Neon, for Cloud Run, Artifact Registry, Secret Manager and the pictures bucket (T1); Vertex AI on the `global` endpoint |
| APIs enabled | Cloud Run, Artifact Registry, Cloud Build, Secret Manager, Vertex AI, IAM; `infra/bootstrap.sh` enables the rest the deploy needs |
| Runtime service account | `playable-anime-api@playable-anime.iam.gserviceaccount.com` with `aiplatform.user`, `secretmanager.secretAccessor`, `logging.logWriter`; the bootstrap adds access to each secret and to the pictures bucket, and lets it sign URLs as itself |
| Default narrator model | `gemini-3.5-flash` (checked working on 2026-11-03) |
| API service | Cloud Run `playable-anime-api`, 0 to 3 instances, 300 s timeout, startup CPU boost, at `https://playable-anime-api-528988811295.europe-west3.run.app` once deployed |
| Images | Artifact Registry `europe-west3-docker.pkg.dev/playable-anime/playable-anime/api` |
| Secrets | `database-url` (pooled), `database-url-direct` and `django-secret-key` in Secret Manager (T11) |
| Pictures | `gs://playable-anime-pictures`, private (M4) |
| Deploys | `.github/workflows/deploy.yml`, started by hand on `main`, signs in as `github-deployer@playable-anime.iam.gserviceaccount.com` through Workload Identity Federation, with no key (B11) |
| Budget | `playable-anime-monthly`, an email alert on the project's monthly spend (T9) |

Setup, deploys, costs and rollback are in [DEPLOY.md](DEPLOY.md); the scripts are in `infra/`.
**Don't deploy publicly before rate limits and quotas (T9) exist alongside sign-in (T8):** an open
endpoint lets anyone spend our Vertex budget.

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
| `accounts_user` | Players and staff (custom `User`, UUID ids), with `email_verified` and `content_prefs` (F7). |
| `accounts_authsession` | One signed-in device (T8): user, sign-in method, last use, and when and why it was revoked. |
| `accounts_refreshtoken` | Refresh tokens as SHA-256 hashes, per session, with expiry and when each was spent. |
| `accounts_throttle` | Sign-in brute-force counters: an HMAC key, the window start and the hits. |
| `stories_story` | One row per story: owner (S8, required), title, premise, genre, rating, settings (S6), the engine that wrote it, the world state as JSONB (C2), `turn`, and `version` for T10. Only a turn writes it (B12). |
| `stories_scene` | One row per turn, unique per story and turn: kind, action and input mode (V7), narration, choices, details (A2, A9, R6), event (W16), in-world start and end seconds plus the player's own elapsed time (W10, W10a) and their labels, timeline id, and the picture flag, kind and prompt (M1). The picture itself and its state live in `media_image`. |
| `stories_pendingevent` | Off-screen results waiting on in-world time (B12): story, timeline id, due time in in-world seconds, kind, payload, status, and the turns that scheduled and applied it. Indexed for "pending on this timeline, due by now". |
| `media_image` | One picture of one subject (M4): story, kind, subject, version (M5), status (planned, pending, ready, skipped) and skip reason, the trigger, the brief to draw from, model, cost and payer (M7, T5), storage key, and the claim and attempts that keep it to one drawing (M3). Unique per story, kind, subject and version. |
| `media_scenepicture` | Which picture a scene shows, and whether code planned it (M1) or the player asked for it (M2). One per scene; many scenes can show one portrait or place. |

The FastAPI version's `stories` and `schema_migrations` tables are left on Neon untouched. Dropping
them deletes production data, so it waits for Miki.

**Branch-first workflow.** Per feature:
1. Run `neon checkout <feature> --create` (this repoints `.env.local`).
2. Run `uv run python manage.py migrate --database direct` in `backend/`, then test.
3. Run `neon diff` to review schema changes.
4. After merging, don't migrate `production` by hand: the deploy workflow migrates it before each
   deploy ([DEPLOY.md](DEPLOY.md#deploying)).

**Latency.** The database is in Frankfurt, and so is Cloud Run (`europe-west3`), so queries never
cross regions (T1).

**Cloud Run.** `infra/bootstrap.sh` stores the production branch's pooled URL as the secret
`database-url` and its direct URL as `database-url-direct`. The service gets the pooled one and the
migration job the direct one, both as `DATABASE_URL` ([DEPLOY.md](DEPLOY.md#what-the-container-gets)).
