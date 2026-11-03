# API contract (v1)

The contract between the Flutter app and the Django backend for the first version. App and backend
threads build to it in parallel, so a thread that changes an endpoint updates this file in the same
PR and tells the orchestrator thread. Django Ninja also serves the live OpenAPI schema at
`/v1/docs`. Requirement ids refer to [REQUIREMENTS.md](REQUIREMENTS.md); the work plan is in
[PLAN.md](PLAN.md).

## Conventions

- Base path `/v1`. JSON in and out, UTF-8, `snake_case` keys. Ids are opaque strings.
- **Auth (T8):** every endpoint except `GET /health` and `POST /v1/auth/*` needs
  `Authorization: Bearer <access_token>`. Access tokens are short-lived (about 15 minutes) and the
  app refreshes them with the refresh token.
- **Bring your own key (S9):** optional `X-LLM-Provider: gemini` and `X-LLM-Api-Key: <key>` headers
  on any request that calls a model. The key is used for that request only and is never stored or
  logged (T6). A BYOK turn uses no credits (K6).
- **In-world time (W10)** is an integer number of seconds since the story's epoch (the moment the
  story opens). The server also sends ready-made labels in the world's own calendar, so the app
  never formats in-world dates itself.
- **Errors (T7)** are never a bare 500. Every error body is:

  ```json
  {"error": {"code": "out_of_credits", "message": "Human-readable text", "details": {}}}
  ```

  | HTTP | `code` | When |
  | --- | --- | --- |
  | 400 | `validation_error` | The body, query or a header is invalid. `details.fields` lists the problems as `{field, source, message, type}`, where `source` is `body`, `query`, `path` or `header`. |
  | 400 | `birth_date_required` | A new Google account signs in without `birth_date` (F8). |
  | 401 | `unauthenticated` | Missing, expired or invalid access token. The app refreshes once, then signs out. |
  | 402 | `out_of_credits` | Not enough credits for a turn or a picture (K2, M7). `details.balance_cents` and `details.available_cents`. |
  | 403 | `forbidden` | The resource belongs to someone else, or the rating is above the account's limit (F8). |
  | 404 | `not_found` | |
  | 405 | `method_not_allowed` | The path exists but not with this method. The `Allow` header lists the ones it takes. |
  | 409 | `version_conflict` | `expected_version` is stale: another turn won (T10). `details.current_version`. |
  | 422 | `unreadable_action` | The interpret step was blocked, so the action can't be read. Offer rephrase or retry (F4). |
  | 422 | `bad_key` | The BYOK key was rejected by the provider. |
  | 429 | `rate_limited` | Per-user rate limit (T9). `details.retry_after_s`. |
  | 429 | `quota_exceeded` | Daily turn quota on our key (T9). `details.resets_at`. |
  | 500 | `internal_error` | A bug on our side. It is logged with its traceback for Error Reporting, and the message never shows internals. |
  | 503 | `llm_unavailable` | The model failed twice (one retry, T7). Nothing was saved. |
  | 503 | `sign_in_unavailable` | Google sign-in can't be checked right now (Google unreachable, or not configured yet). Email sign-in still works. |

- **Request ids (T4):** every response carries an `X-Request-Id` header, the id on the server's log
  lines for that request. The app may send its own (up to 64 letters, digits, `.`, `_` or `-`), and
  the server keeps it.

## Health

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | `{"status": "ok"}`. Never touches the database (T3). |

## Auth and account (T8, S8, F8, K7, T12)

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| POST | `/v1/auth/google` | `{id_token, birth_date?}` | `Session` |
| POST | `/v1/auth/register` | `{email, password, display_name, birth_date}` | `Session` |
| POST | `/v1/auth/login` | `{email, password}` | `Session` |
| POST | `/v1/auth/refresh` | `{refresh_token}` | `Session` (the refresh token rotates) |
| POST | `/v1/auth/logout` | `{refresh_token}` | `204` |
| GET | `/v1/me` | | `User` |
| PATCH | `/v1/me` | `{display_name?, content_prefs?}` | `User` |
| DELETE | `/v1/me` | | `204`. Deletes the account, stories and pictures (T12, M4). |
| GET | `/v1/me/export` | | `{"user": User, "stories": [Story with all scenes], "images": [ExportedPicture]}` (T12, M4) |
| GET | `/v1/me/credits` | `?limit=50` (1 to 200) | `{balance_cents, unlimited, entries: [LedgerEntry]}`, newest first (K1, K2) |

```text
Session      {access_token, refresh_token, expires_in, user: User}
User         {id, email, display_name, role: "player"|"owner", max_rating: "teen"|"mature",
              content_prefs: {gore: "low"|"medium"|"high", romance: bool, dark_themes: bool},
              credits: {balance_cents, unlimited}}
LedgerEntry  {id, kind: "starter"|"turn"|"draft"|"image"|"topup"|"adjustment", amount_cents,
              balance_after_cents, story_id?, turn?, created_at}
ExportedPicture {id, story_id, kind, subject, version, turns: [int], url, expires_at, created_at}
```

`amount_cents` may be fractional (a turn costs about 2 cents), so it is a decimal number, not an
integer. It is positive when credits are added and negative when they are spent, and a balance
never goes below zero. The owner account (K7) has `unlimited: true`; its ledger still records costs
at zero charge so T5's numbers stay honest. A turn, draft or picture on the player's own key (K6)
uses no credits and writes no entry.

**Credits, rate limits and quotas (K2, K6, T9).** Every request that calls a model (a turn, a
draft or revision, a picture) is checked before it starts, in this order:

1. A per-user rate limit per minute, on any key, BYOK included: `429 rate_limited` with
   `details.retry_after_s`. Turns, drafts and pictures each have their own limit.
2. A per-user daily quota on our key, per UTC day: `429 quota_exceeded` with `details.resets_at`
   (ISO 8601, the next midnight UTC). BYOK requests don't count.
3. Credits, on our key: the request needs its estimated cost available (about 5 cents for a turn
   or a draft, 6 for a picture), or it gets `402 out_of_credits` with `details.balance_cents` and
   `details.available_cents` (less than the balance while another request of the same player is
   running). A picture that can't be paid for is `skipped` instead (M7).

A request that is refused counts against nothing. The real cost is charged when the request
completes, in the same transaction as what it saved, so a turn that fails or loses a version race
costs nothing. These checks are wired into each endpoint as it moves to this contract (the turn
endpoint, drafting and pictures); the legacy endpoints described under Stories have no signed-in
user yet, so they aren't metered.

**Signing in.** Every auth endpoint answers `200` with a `Session`, except `logout` (`204`).

- **Google** (`/v1/auth/google`). The app gets an ID token from Google Sign-In for one of our OAuth
  clients and sends it once; the server checks it and from then on only our own tokens are used.
  A first sign-in without `birth_date` gets `400 birth_date_required`, and the app asks for the
  date and sends the same request again with it (an ID token lasts an hour). A Google account whose
  email Google hasn't verified gets `403 forbidden`. When Google can't be reached, or Google
  sign-in isn't configured yet, the answer is `503 sign_in_unavailable`: try again later or use
  email. If an email and password account already has
  that email, the Google sign-in takes it over: Google vouches for the email and nobody verified
  the password, so the password stops working and that account's devices are signed out. An
  account already tied to a different Google account answers `403 forbidden`.
- **Email and password** (`/v1/auth/register`, `/v1/auth/login`). Register answers
  `validation_error` with one entry in `details.fields` per problem: `email` (`invalid_email`,
  `email_taken`), `password` (Django's checks, such as `password_too_short`,
  `password_too_common`, `password_too_similar`), `display_name` (`missing`) or `birth_date`
  (`future`, `implausible`, `too_young`). Login answers `401 unauthenticated` with the same message
  for a wrong password and an unknown email. After 10 failures for one email in 15 minutes, or 100
  from one address, login answers `429 rate_limited` until the window ends; so does register after
  10 new accounts from one address in an hour (attempts that fail validation don't count).
- **Ages (F8).** The youngest age that can sign up is the `MIN_SIGNUP_AGE` setting (13). Under 17,
  `max_rating` is `teen`, and it becomes `mature` on the 17th birthday with nothing to update. A
  story whose rating is above the account's `max_rating` answers `403 forbidden`.
- **Owner (K7).** `role` is `owner` only for a Google sign-in whose verified email is in
  `OWNER_EMAILS`, never through a password, and it follows that list at every Google sign-in.
- **Tokens.** `expires_in` is the access token's lifetime in seconds (900). A refresh token is good
  for one refresh within 30 days and is replaced by the one in the response, so the app keeps only
  the newest. The app should refresh one request at a time: sending a spent refresh token again
  within 60 seconds still works (a retry after a lost response) and spends the token the lost
  response carried, but later it signs that device out, because two holders of one token means one
  of them stole it. `/v1/auth/refresh` answers
  `401 unauthenticated` when the session is over, and the app then signs out. Logout takes the
  refresh token, needs no access token and is safe to repeat.
- **Other people's stories (S8).** A story that exists but belongs to someone else answers
  `403 forbidden`; a story that doesn't exist answers `404 not_found`.
- **`PATCH /v1/me`** changes only the fields sent, and inside `content_prefs` only the keys sent.
  `role`, `email` and `birth_date` can't be changed.
- **`DELETE /v1/me`** deletes the account and everything it owns at once and for good: stories,
  scenes, signed-in devices and pictures. There is no undo, so the app confirms first.
- **`GET /v1/me/export`** is a JSON download (`Content-Disposition: attachment`). Its stories are
  the export shape below, oldest first, and `images` lists every ready picture with a fresh URL,
  and the turns that show it (M4). A scene's own `image` has no URL; use `images`. The world
  state isn't exported, because it holds truths the player hasn't learned (C6, N7).

```text
ExportStory  {id, title, premise, genre, rating, settings, turn, version, created_at, updated_at,
              scenes: [ExportScene]}                       # every scene, in turn order
ExportScene  {turn, kind, player_action?, input_mode?, narration, choices, details, event?,
              time: {world_start_s, world_end_s, label, duration_label, personal_label?},
              image?: {kind, status, url?}, created_at}
```

## Starter premises (S1)

| Method | Path | Response |
| --- | --- | --- |
| GET | `/v1/premises` | `[Premise]` |

```text
Premise {id, title, genre, tagline, premise, flagship: bool, cover_url?}
```

Flagship genres come first (cultivation, knights and aura, many races and monsters, reincarnation),
then at least a grounded modern story, science fiction and a modern world with a hidden
supernatural side.

## Drafting a world and a character (G1, G2, S1, A1)

A draft holds the AI's proposal until the player starts the story. Drafting calls a model, so it
needs credits or a BYOK key like a turn does.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| POST | `/v1/drafts` | `{premise, premise_id?, rating, advanced?: DraftAdvanced}` | `Draft` |
| GET | `/v1/drafts/{id}` | | `Draft` |
| PATCH | `/v1/drafts/{id}` | `{world_lines?, character_lines?, advanced?, rating?}` | `Draft` (direct edits) |
| POST | `/v1/drafts/{id}/revise` | `{target: "world"|"character", instruction}` | `Draft` (plain-words change, such as "add hidden vampires") |
| POST | `/v1/drafts/{id}/start` | `{settings?: StorySettings}` | `{story_id}`. The app then opens the play screen and streams the opening turn. |

```text
Draft          {id, premise, rating, title, genre, tone,
                world_lines: [string],       # the one-screen summary in plain words (G1)
                character_lines: [string],   # the character in the world's words (G2, G16)
                advanced: DraftAdvanced, created_at}
DraftAdvanced  {physics: "fun_first"|"strict",                      # A9
                rules: [{id, text, fixed: bool}],                    # G6, G7
                gift_strength?: "none"|"small"|"rare"|"overpowered", # G22
                difficulty: "story"|"balanced"|"brutal",             # A5, default balanced
                event_frequency: "calm"|"normal"|"dramatic"}         # W16, default normal
```

Hidden parts of the draft (the answer to a major mystery, NPC secrets, N7, C6) never appear in this
response.

## Stories

**Until WS3's turn graph lands,** the backend still serves today's endpoints with today's shapes, so
the current app keeps working: `POST /v1/stories` with `{premise, title?}` returns the whole story
with its opening scene, `POST /v1/stories/{id}/turns` takes `{choice_id}` or `{action}` (plus
optional `input_mode` and `expected_version`) and returns `{scene, state, version}` as plain JSON,
and `GET /v1/stories/{id}/memory` returns the raw world state. Stories and turns already carry
`version` (T10) and errors already use the envelope above. The contract below is the target.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| GET | `/v1/stories` | | `[StorySummary]`, only the caller's own (S8) |
| GET | `/v1/stories/{id}` | `?scenes=20` | `Story` with the last N scenes |
| GET | `/v1/stories/{id}/scenes` | `?before=<turn>&limit=20` | `[Scene]`, older scenes for scrollback |
| PATCH | `/v1/stories/{id}` | `{title?, settings?: StorySettings}` | `Story` (S6) |
| DELETE | `/v1/stories/{id}` | | `204` |
| POST | `/v1/stories/{id}/turns` | `TurnRequest` | `text/event-stream`, see below |
| GET | `/v1/stories/{id}/memory` | | `MemoryView` (C6) |
| GET | `/v1/stories/{id}/status` | | `StatusView` (`/status`, A8, G16, W10) |

```text
StorySummary  {id, title, genre, rating, turn, world_time_label, cover_url?, updated_at}
Story         {id, title, genre, rating, version, settings: StorySettings,
               clock: Clock, scenes: [Scene], cover_url?}
StorySettings {narration_length: "short"|"medium"|"long", tone?: string,
               difficulty: "story"|"balanced"|"brutal",
               event_frequency: "calm"|"normal"|"dramatic",
               images: "off"|"key_moments"|"more",      # M2, default key_moments
               suggestions: bool}                         # S2
Clock         {world_s, label, timeline_id}              # label such as "Day 3, dusk" or "14 May 1974, 23:10"
```

### Turns (B5, B7, S3, T10, V7)

```text
TurnRequest {kind: "action"|"choice"|"standing"|"opening",
             action?: string,            # kind=action, 1 to 2000 characters
             choice_id?: string,         # kind=choice
             standing?: "wait"|"observe",# kind=standing (S2)
             input_mode: "typed"|"voice"|"voice_edited"|"choice",
             expected_version: int}      # the Story.version the app last saw (T10)
```

`kind: "opening"` writes the opening scene of a story that has none yet, right after
`POST /v1/drafts/{id}/start`.

Checks that can fail (auth, ownership, rating, version, credits, rate limit, quota) run before the
stream starts and come back as ordinary JSON errors. Once the server answers `200` with
`Content-Type: text/event-stream`, it sends these events:

| Event | Data | Notes |
| --- | --- | --- |
| `turn.started` | `{turn}` | Sent at once, so the app can show the action and a typing state. |
| `narration.delta` | `{text}` | Narration as it is written. The first one arrives within about 2 s (S3). |
| `narration.reset` | `{reason: "cutaway"|"template"|"retry"}` | The partial narration is being rewritten, so the app clears it: `cutaway` and `template` when it was blocked (F4), `retry` when the model failed partway and is being retried once (T7). |
| `scene.completed` | `{scene: Scene, story: {version, clock}}` | The turn is saved. Always the last event of a successful turn. |
| `error` | `{code, message}` | The turn failed after streaming began (`llm_unavailable`). Nothing was saved and no credits were charged, so the app discards the partial scene and offers a retry. |

A turn is all or nothing: the world state, the scene, the ledger entry and the version bump are saved
together only when the turn completes.

### Scene

```text
Scene {turn, kind: "opening"|"action"|"choice"|"standing",
       player_action?: string, input_mode?: string,
       narration: string,
       choices: [{id, label, kind: "thread"|"personal"|"side"|"wild"}],   # 0 to 4 (S2)
       standing_actions: ["wait", "observe"],
       time: {world_start_s, world_end_s, label, duration_label,   # "+8 h" (W10)
              personal_label?},                                   # "World: +0 s. You: +40 s." (W10a)
       details: SceneDetails,
       event?: {size: "personal"|"local"|"world", title},        # a W16 event arrived
       image?: SceneImage,
       portraits: [{character_id, name, url?}],                  # known characters in the scene (M4, M5)
       created_at}

SceneDetails {steps: [{text,                                    # the step in plain words
                       class: "certain"|"contested"|"long_shot"|"ruled_out",
                       reason,                                   # in the world's words (A8, G14)
                       roll?: {odds_label, result: "success"|"partial"|"failure", seed}}],
              chain?: [{link, class, reason}],                   # a cause-and-effect chain (A9)
              stopped_at_step?: int}                             # a chained plan stopped here (R6)

SceneImage {planned: bool,                  # code planned it (M1); false for Illustrate (M2)
            kind: "portrait"|"place"|"scene"|"cover",
            status: "planned"|"ready"|"skipped", # "planned" until it is drawn: ask for it (M3)
            image_id?, url?, expires_at?}
```

### Pictures (M1 to M8)

The scene says when a picture is planned. The app shows the text first, then asks for the picture in
its own request (M3, B8).

| Method | Path | Response |
| --- | --- | --- |
| POST | `/v1/stories/{id}/scenes/{turn}/image` | `Picture` |
| POST | `/v1/stories/{id}/scenes/{turn}/illustrate` | `Picture`. The player asks and pays for a picture of any scene (M2). |
| GET | `/v1/stories/{id}/images/{image_id}` | `Picture`. Refreshes an expired signed URL; never draws. |

```text
Picture {status: "ready"|"pending"|"skipped",
         image_id?, kind?: "portrait"|"place"|"scene"|"cover",
         url?, expires_at?}        # url and expires_at only when ready
```

- `POST .../image` is safe to repeat: it draws and charges at most once per picture, and a repeat
  while the picture is drawn answers `pending`, so ask again after a couple of seconds. It draws only
  a picture the scene says is planned; any other scene answers `skipped`, and so does a picture not
  drawn yet while the story's `images` setting is `off`.
- `skipped` means the picture failed, was blocked or wasn't affordable. Leave the scene quietly
  without one (M3, M7). A repeat answers `skipped` again without trying; `illustrate` tries it
  again. A portrait or place that failed or wasn't affordable is also planned again the next time
  the story shows that character or place.
- `illustrate` draws the scene's planned picture if it has one, or a picture of the scene itself,
  even with pictures off. On a scene whose picture is ready it returns that picture at no charge.
- Pictures are reused: a character's portrait or a place's picture is drawn once and every scene
  that shows it answers with the same `image_id` (M4). Size the slot by `kind` before the picture
  arrives: portraits and covers are 3:4, places and scenes 16:9.
- `url` is a signed URL that works until `expires_at`, about an hour. After that, ask
  `GET .../images/{image_id}` for a fresh one, and cache the picture by `image_id`, not by URL.
- With the player's own key (`X-LLM-*` headers) the picture is drawn on their key at no charge. A
  key that can't draw pictures (rejected, or a free-tier Gemini key, which has no image models)
  falls back to credits; a server error on their key skips the picture instead (M7).
- Errors: `401 unauthenticated` without a valid access token, `404 not_found` for an unknown
  story, scene or picture, `403 forbidden` for another player's story or one above the account's
  rating limit (F8), `400 validation_error` for an unsupported `X-LLM-Provider`, and `429
  rate_limited` from the credit meter, after which the picture is still planned.

### Memory and status (C6, G16)

Only what the player character knows, in the world's words. Hidden truth never appears.

```text
MemoryView {character: {name, lines: [string], portrait_url?},
            people:   [{id, name, lines: [string], attitude_label?, portrait_url?, status_label}],
            places:   [{id, name, lines: [string], image_url?}],
            factions: [{id, name, lines: [string], standing_label}],    # esteem and fear in words (W3)
            goals:    [{id, text}],
            leads:    [{id, text, expires_label?}],
            rumors:   [{id, text, heard_label, unconfirmed: true}],
            deeds:    [{id, text, when_label, known_label}],
            threads:  [{id, title, status}]}

StatusView {character: {name, lines: [string]},
            reputation: [{name, label}],
            clock: Clock,
            since: [{text, ago_label}]}      # "The bar shooting: 2 days ago" (W10)
```

### Reports (F6)

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| POST | `/v1/stories/{id}/scenes/{turn}/report` | `{category: "sexual"|"minor"|"hate"|"real_person"|"self_harm"|"other", note?, block: bool}` | `204` |

`block: true` hides the scene's text in the app at once. Staff review reports in the Django admin.
