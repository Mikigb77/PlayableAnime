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
  | 402 | `out_of_credits` | Not enough credits for a turn or a picture (K2, M7). `details.balance_cents`. |
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
| GET | `/v1/me/export` | | `{"user": User, "stories": [Story with all scenes]}` (T12) |
| GET | `/v1/me/credits` | `?limit=50` | `{balance_cents, unlimited, entries: [LedgerEntry]}` (K1, K2) |

```text
Session      {access_token, refresh_token, expires_in, user: User}
User         {id, email, display_name, role: "player"|"owner", max_rating: "teen"|"mature",
              content_prefs: {gore: "low"|"medium"|"high", romance: bool, dark_themes: bool},
              credits: {balance_cents, unlimited}}
LedgerEntry  {id, kind: "starter"|"turn"|"image"|"topup"|"adjustment", amount_cents,
              balance_after_cents, story_id?, turn?, created_at}
```

`amount_cents` may be fractional (a turn costs about 2 cents), so it is a decimal number, not an
integer. The owner account (K7) has `unlimited: true`; its ledger still records costs at zero
charge so T5's numbers stay honest.

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

SceneImage {planned: bool, kind: "portrait"|"place"|"scene"|"cover",
            status: "planned"|"ready"|"skipped", url?, expires_at?}
```

### Pictures (M1 to M8)

The scene says when a picture is planned. The app shows the text first, then asks for the picture in
its own request (M3, B8).

| Method | Path | Response |
| --- | --- | --- |
| POST | `/v1/stories/{id}/scenes/{turn}/image` | `{status: "ready"|"pending"|"skipped", url?, expires_at?}` |
| POST | `/v1/stories/{id}/scenes/{turn}/illustrate` | Same. The player paid for an extra picture of any scene (M2). |
| GET | `/v1/stories/{id}/images/{image_id}` | `{status, url?, expires_at?}`. Refreshes an expired signed URL. |

`POST .../image` is safe to repeat: it generates and charges at most once per scene, and a repeat
while generation runs returns `pending`. `skipped` means the picture failed, was blocked or wasn't
affordable, and the app quietly leaves the scene without one (M3, M7).

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
