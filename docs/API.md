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
  | 402 | `out_of_credits` | Not enough credits for a turn, a draft, an Illustrate, a dictation or a part read aloud (K2, M2, V6, V10). `details.balance_cents` and `details.available_cents`. A planned picture is never refused: it is `skipped` (M7). |
  | 403 | `forbidden` | The resource belongs to someone else, or the rating is above the account's limit (F8). |
  | 404 | `not_found` | |
  | 405 | `method_not_allowed` | The path exists but not with this method. The `Allow` header lists the ones it takes. |
  | 409 | `version_conflict` | `expected_version` is stale: another turn won (T10). `details.current_version`. |
  | 409 | `story_ended` | A turn on a story at its ending (N6). `details.ending` is its `Ending`. Show the ending instead of the action box. |
  | 422 | `unreadable_action` | The interpret step was blocked, so the action can't be read. Offer rephrase or retry (F4). When the action crosses a hard limit, `details.category` names it (`minor`, `sexual`, `sexual_violence` or `real_person`, F2, F3, G12) and `message` says which line it is, so show the message as it is. On a turn it arrives as the stream's `error` event. |
  | 422 | `bad_key` | The BYOK key was rejected by the provider. |
  | 429 | `rate_limited` | Per-user rate limit (T9). `details.retry_after_s`. |
  | 429 | `quota_exceeded` | Daily turn quota on our key (T9). `details.resets_at`. |
  | 500 | `internal_error` | A bug on our side. It is logged with its traceback for Error Reporting, and the message never shows internals. |
  | 503 | `llm_unavailable` | The model failed twice (one retry, T7). Nothing was saved. On a turn it arrives as the stream's `error` event. |
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
| GET | `/v1/me/export` | | `{"user": User, "stories": [Story with all scenes], "images": [ExportedPicture], "reports": [ExportedReport]}` (T12, M4, F6) |
| GET | `/v1/me/credits` | `?limit=50` (1 to 200) | `{balance_cents, unlimited, entries: [LedgerEntry]}`, newest first (K1, K2) |

```text
Session      {access_token, refresh_token, expires_in, user: User}
User         {id, email, display_name, role: "player"|"owner", max_rating: "teen"|"mature",
              content_prefs: {gore: "low"|"medium"|"high", romance: bool, dark_themes: bool},
              credits: {balance_cents, unlimited}}
LedgerEntry  {id, kind: "starter"|"turn"|"draft"|"image"|"speech"|"topup"|"adjustment", amount_cents,
              balance_after_cents, story_id?, turn?, created_at}
ExportedPicture {id, story_id, kind, subject, version, turns: [int], url, expires_at, created_at}
ExportedReport  {story_id, turn, category, note, block, status: "open"|"actioned"|"dismissed",
                 created_at}                                # the player's own reports, oldest first
```

`amount_cents` may be fractional (a turn costs about 2 cents, a dictation a fraction of one), so
it is a decimal number, not an integer. It is positive when credits are added and negative when they are spent, and a balance
never goes below zero. The owner account (K7) has `unlimited: true`; its ledger still records costs
at zero charge so T5's numbers stay honest. A new player's first pictures in their first story
(the player character's portrait, the cover, first meetings and first visits) are on the house
while its allowance lasts (K1, M7): each is an `image` entry with `amount_cents: 0`, which the app
shows as free. A turn, draft or picture on the player's own key (K6) uses no credits and writes no
entry.

**Credits, rate limits and quotas (K2, K6, T9).** Every request that calls a model (a turn, a
draft or revision, a picture, a dictation, a part read aloud) is checked before it starts, in this order:

1. A per-user rate limit per minute, on any key, BYOK and the owner included: `429 rate_limited`
   with `details.retry_after_s`. Turns, drafts, pictures, dictations and parts read aloud each have
   their own limit.
2. A per-user daily quota on our key, per UTC day: `429 quota_exceeded` with `details.resets_at`
   (ISO 8601, the next midnight UTC). BYOK requests don't count, and the owner (K7) has none.
3. Credits, on our key: the request needs its estimated cost available (about 5 cents for a turn
   or a draft, 6 for a picture, 1 for a dictation, 3 for a part read aloud), or it gets `402 out_of_credits` with `details.balance_cents` and
   `details.available_cents` (less than the balance while another request of the same player is
   running). A planned picture that can't be paid for is `skipped` instead (M7); Illustrate, which
   the player asks for, answers the `402`. A first picture the house pays for (K1) needs no
   credits.

A request that is refused counts against nothing. The real cost is charged when the request
completes, in the same transaction as what it saved, so a turn that fails or loses a version race
costs nothing. The turn endpoint and pictures run these checks, and drafting does when it lands.

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
- **Ages (F8).** The youngest age that can sign up is the `MIN_SIGNUP_AGE` setting (16). Under 17,
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
              scenes: [ExportScene]}                       # every scene, in turn order; one a
                                                           # rewind took back comes before the
                                                           # scene played anew in its turn (C8)
ExportScene  {turn, kind, player_action?, input_mode?, narration, choices, details, event?,
              time: {world_start_s, world_end_s, label, duration_label, personal_label?,
                     passage_label?},
              image?: {kind, status, url?},
              rewound: bool,                               # a rewind took it back (C8)
              created_at}
```

## Dictation (V1, V2, V5, V6)

| Method | Path | Query | Body | Response |
| --- | --- | --- | --- | --- |
| POST | `/v1/transcriptions` | `story_id?`, `draft_id?`, `language?` | The recording, with its audio type as `Content-Type` | `{text}` |

Online dictation: the app records while the mic is on and sends the clip; Gemini 3.5 Transcribe on
Vertex AI writes it down, and the app puts `text` in the box for the player to check (V2). Nothing is
sent as an action from here.

- **The body** is the raw audio, at most 2 MiB (the app sends at most a minute of 16 kHz 16-bit mono
  WAV, 1.92 MB, and a longer dictation in parts). `Content-Type` is one of `audio/wav` (or `audio/x-wav`, `audio/wave`),
  `audio/mpeg` (`audio/mp3`), `audio/aac`, `audio/m4a` (`audio/mp4`), `audio/ogg`, `audio/opus`,
  `audio/webm`, `audio/flac` or `audio/aiff`. Anything else, an empty body or a longer one is
  `400 validation_error` with the field `Content-Type` (`unsupported_audio`) or `body` (`missing`,
  `too_long`).
- **`story_id` or `draft_id`** (at most one: both is `validation_error`, `conflict`) says where the
  words go, so the model listens for the names the player character knows there, up to 100 (C6:
  never a hidden one). Someone else's story or draft answers `403`, an unknown one `404`, and a
  story or draft above the account's rating limit `403` (F8). With neither, no names are sent.
- **`language`** is a BCP-47 tag such as `en-US` (V4). Left out, the model detects the language.
- **`text`** is empty when the recording held no speech. It has no trailing spaces.
- **Billing (K2, T9).** Always on our key, even with `X-LLM-Api-Key` (the Gemini API offers this
  model only through its Interactions API), so a BYOK player pays for dictation in credits. The
  checks above apply, with their own rate limit and daily quota, and a dictation needs 1 cent
  available. The real cost, a fraction of a cent, is charged as a `speech` ledger entry, with
  `story_id` when one was sent. A failed dictation costs nothing.
- **Errors:** `422 unreadable_action` when the model refuses to write the clip down (rare: the
  player's words are never filtered), and `503 llm_unavailable` after one retry. The app says it
  couldn't reach the server, and typing always works.
- **Privacy (V5).** The audio is held in memory for the request only (a body within the limit
  never touches the disk), never stored, and never logged. The log line has the audio's size and type, the number of names sent,
  the outcome, the transcript's length, tokens and cost, never the words (T6).

## App updates (S12)

| Method | Path | Query | Response |
| --- | --- | --- | --- |
| GET | `/v1/app/latest` | `platform=android` (the default; anything else is `400 validation_error`) | `AppRelease`, or `404 not_found` until a build is published |

```text
AppRelease  {platform: "android", build, version, size, sha256, url, expires_at, published_at?}
```

The newest build the deploy published, for the APK from the GitHub release to update itself. Only a
build with `SELF_UPDATE=true` asks (never a store build, which its store updates): when its tabs
first show, when it comes back to the foreground (at most every half hour) and from Account's
"Check for updates".

- **`build`** is Android's versionCode, which grows with every deploy; the app offers the update
  when it is above its own. **`version`** is the version name, such as `1.0.0`.
- **`url`** downloads the APK until `expires_at` (30 minutes, a Cloud Storage signed URL in
  production, no `Authorization` header). On Wi-Fi the app downloads it right after the check; on
  mobile data it asks again right before downloading, when the player taps Update, so the URL is
  fresh. The download must be exactly **`size`** bytes with this **`sha256`** (lowercase hex),
  or the app doesn't install it.
- The server reads the deploy's manifest at most once a minute per instance, so a new build is
  offered within a minute of the deploy. A manifest it can't read counts as none (logged as a
  warning), so the app just offers nothing.

## Starter premises (S1)

| Method | Path | Response |
| --- | --- | --- |
| GET | `/v1/premises?language=` | `[Premise]` |

```text
Premise {id, title, genre, tagline, premise, flagship: bool, cover_url?}
```

`language` is the app's language, `en` (the default), `es` or `ca` (S10): the title, genre, tagline
and premise come in it. Any other value is a `validation_error`. The ids, order and covers are the same
in every language.

Flagship genres come first (cultivation, knights and aura, many races and monsters, reincarnation),
then a grounded modern story (the Naples vendetta), science fiction, a modern world with a hidden
supernatural side and a few more. Each starter's genre fixes some rules (G7), which every draft
from it keeps until the player changes them.

`cover_url` is the starter's 3:4 cover, drawn once for everyone (S1, M4), as a signed URL that
works for at least 6 hours; it is null until the cover is drawn. Load the premises again for fresh
URLs. The cover keeps its lower third calm for the genre and title set over it, and a premise
without one shows the app's own fallback.

## Drafting a world and a character (G1, G2, S1, A1)

A draft holds the AI's proposal until the player starts the story. Drafting calls a model, so it
needs credits or a BYOK key like a turn does: the credit meter checks the rate limit, the daily
draft quota and the balance first (`429 rate_limited`, `429 quota_exceeded`, `402 out_of_credits`),
and each create, revise or edit that calls the model is charged as a `draft` ledger entry (K2). A
BYOK request is free (K6).

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| POST | `/v1/drafts` | `{premise?, premise_id?, rating, language?, advanced?: DraftAdvancedIn}` | `201 Draft` |
| GET | `/v1/drafts/{id}` | | `Draft` |
| PATCH | `/v1/drafts/{id}` | `{title?, tone?, character?: DraftCharacterIn, world_lines?, character_lines?, advanced?: DraftAdvancedIn, rating?, expected_version?}` | `Draft` (direct edits) |
| POST | `/v1/drafts/{id}/revise` | `{target: "world"|"character", instruction, about?: DraftPartKind, expected_version?}` | `Draft` (plain-words change, such as "add hidden vampires"; the rest stays as it was) |
| POST | `/v1/drafts/{id}/start` | `{settings?: StorySettings, expected_version?}` | `{story_id, version}`. The app then opens the play screen and asks for the opening turn (`kind: "opening"`). |

```text
Draft            {id, premise, premise_id?, rating, title, genre, tone,
                  language: "en"|"es"|"ca",  # S10: what it is written in, and its story stays in
                  world_lines: [string],       # the one-screen summary in plain words (G1)
                  character_lines: [string],   # the character in the world's words (G2, G16)
                  world_parts: [DraftPart],    # the same lines, each with what it tells of
                  character_parts: [DraftPart],
                  character: DraftCharacter,   # the plain fields the player changes themselves
                  ladder?: DraftLadder,        # the world's ladder rung by rung; null with none
                  kept: {people: int, events: int, questions: int},  # G1, see below
                  advanced: DraftAdvanced,
                  version: int,                # bumped by every saved change (T10)
                  story_id?: string,           # set once started
                  created_at, updated_at}
DraftAdvanced    {physics: "fun_first"|"strict",                     # A9
                  rules: [{id, text, fixed: bool}],                   # G6, G7
                  gift_strength: "none"|"small"|"rare"|"overpowered", # G22, the strongest gift held
                  difficulty: "story"|"balanced"|"brutal",            # A5, default balanced
                  event_frequency: "calm"|"normal"|"dramatic"}        # W16, default normal
DraftAdvancedIn  the same fields, each optional; a rule without an id is a new rule
DraftPart        {kind: DraftPartKind, text}
DraftPartKind    "rule"|"era"|"ladder"|"peoples"|"faction"            # the world
                 |"deadline"|"question"|"person"|"connections"|"goal"  # how the story starts (G1)
                 |"who"|"manner"|"standing"|"rank"|"skills"|"talents"  # the character
                 |"traits"|"nature"|"power"|"belongings"
DraftCharacter   {name, age?: int, people, standing, looks, manner}
DraftCharacterIn {name?, age?: int, looks?, manner?}                  # each one optional
DraftLadder      {name, rungs: [string], more: bool,   # the rungs everyone has heard of (G18)
                  at?: int, stage}                      # the character's rung among them (G19)
```

- **Creating.** `premise` is 10 to 4000 characters. With `premise_id` alone the starter's own text
  is the premise; with both, the player's text is the premise and the starter's genre still holds.
  An unknown `premise_id` is a `validation_error` on that field. A teen account can't ask for
  `mature` (`403 forbidden`, F8). Rules sent in `advanced.rules` join the drafted ones word for
  word, in the same model call; one with the id of a drafted rule replaces it. `language` is the
  app's language, `en` (the default), `es` or `ca` (S10): the drafter writes every text the player
  reads in it, a starter sent by `premise_id` alone takes its premise in that language, and revisions
  keep it.
- **The summary is written by code** from the world's public parts, never by the model, so it always
  matches the draft. `world_lines` lead with what never changes, then the era, the power ladder and
  peoples and the factions the character knows. Of how the story starts they show only what the
  player's own words name (G1): a deadline, an open question or a key person is a line only when
  the premise, or a change the player asked for, names it (a person by their name), and so are
  a connection, a goal and what the character wants in `character_lines`. The rest is drafted
  and kept for the story to tell. A deadline their words give an amount of time ("in 3 days")
  comes at exactly that time (E2).
  At most 10 lines each. Of the ladder they name the rungs everyone in the world has heard of, five
  at most, with "and beyond" when it goes on (G18, C6): the character's path starts with those.
- **The summary part by part.** `world_parts` and `character_parts` are the same lines, not cut to
  10, each with its `kind`, so the app can label a line, group it and point a change at it. The
  app's own words for a kind are fixed text, in its language (S10). The parts of how the story
  starts (`deadline`, `question`, `person`, `connections`, `goal`) are there only when the
  player's own words name them, as in the lines, and `nature` says what the character wants
  only then. `kept` counts what the story keeps back of its
  start, and tells none of it: the people, the things already in motion and the open questions
  the player's words don't name. `ladder` gives the first ladder as `rungs` (the ones the lines
  name), `more` when it goes on above them, and the character's place: `at`, an index into
  `rungs`, with its `stage` in words, or null when they stand above the rungs everyone knows.
  `character` holds the plain fields: `name`, `age`, `looks` (face, build, hair and usual
  clothes, which every picture of them is drawn from) and `manner` (how they come across), with
  their `people` and `standing` to tell them by. A text is "" when the draft has none.
- **Direct edits.** Fields left out stay as they are. The plain fields are the player's to change
  themselves (G1, G2): `title`, `tone` and `character.name` (1 to 80 characters), `character.age`
  (0 to 100,000) and `character.looks` and `character.manner` (1 to 300 characters) are written
  in by code at once, with no model call, and cost nothing. A new name takes the old one's place
  wherever the draft says it, hidden parts included: the whole name, and each word of it that
  nobody and nothing else in the draft is called by. A new age takes the old one's place where
  the looks give it as a number. One left empty or all spaces is a `validation_error` on its
  field with `type: "empty"`, and one sent back as it is changes nothing; `world_lines` and
  `character_lines` sent in the same edit as they were read before it change nothing either,
  so a screen sent back whole with a new name calls no model. Changing `physics`, a
  rule's `fixed` flag,
  `gift_strength: "none"`, `difficulty`, `event_frequency`, or raising `rating` to `mature` needs no
  model call and costs nothing either. Rewriting `world_lines` or `character_lines` (each line up to 300
  characters), rewriting or adding rules, or choosing a different gift strength redrafts the world
  or the character to match, in one model call each; lowering `rating` to `teen` redrafts both
  within Teen (F2). `advanced.rules` is the whole list the player sees, kept word for word.
  Removing, rewriting or opening up one of a starter's fixed rules lets the genre's rule go for
  this story (G7), and so does a revision that asks for it; putting it back word for word, still
  fixed, holds it again.
- **Versions (T10).** Send `expected_version` with the `version` last seen; a stale one answers
  `409 version_conflict` with `details.current_version`, before any model call. Two saves at once
  can't overwrite each other either way: the later one answers `409` too, and its model call is
  still charged, since it ran.
- **Starting** creates the story with the drafted world state (`turn` 0, `version` 1, no scenes) and
  the settings: the draft's `difficulty` and `event_frequency`, then whatever `settings` sends, and
  the draft's `language`, which `settings` can't change (S10: an older app's is ignored). A
  started draft can't change (`403 forbidden` with `details.story_id`), and starting it again
  returns the same story. The app sends `expected_version` here as with every change; the server
  refuses a stale one with `409 version_conflict` like any other change, so a story never starts
  from a copy the player hasn't seen. Starting bumps the version, so a retried start that carries
  the old version still returns the same story.
- **A change in plain words** (`revise`) may say which part of the summary it was asked at:
  `about`, the `kind` of a part of that `target`. The drafter is then given that part as the
  player read it, so "make me better at this" says what "this" is. An unknown `about` is a
  `validation_error`.
- **Real people (G12).** A premise, a revision's `instruction`, an edited summary line, a plain
  field or a rule that names a real living person is refused before any model call, at no cost,
  with `400 validation_error`: `details.fields` has the field (`premise`, `instruction`,
  `world_lines.3`, `character.name`, `advanced.rules.1.text`) with `type: "real_person"`, and the message names who, to show as it
  is. Real organisations are fine as a backdrop ("a rookie FBI agent"). A line sent back unchanged
  is never refused. Real people and organisations the model drafts are left out of the world.
- **Model failures** are the usual codes: `422 unreadable_action` when the safety filter blocked the
  request (offer a rephrase), `422 bad_key`, `503 llm_unavailable`. Nothing is saved or charged.

Hidden parts of the draft (the answer to a major mystery and its clues, NPC secrets and agendas,
faction plans, what others remember of the character's body that the character doesn't, and anyone
the character doesn't know of, N7, C6) never appear in these responses.

## Stories

A story is made by starting a draft (`POST /v1/drafts/{id}/start`), and its first turn is
`kind: "opening"`; there is no `POST /v1/stories`. In development, `manage.py seed_story <email>`
makes one from an example world.

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| GET | `/v1/stories` | | `[StorySummary]`, only the caller's own (S8) |
| GET | `/v1/stories/{id}` | `?scenes=20` (0 to 50) | `Story` with the last N scenes, oldest first |
| GET | `/v1/stories/{id}/scenes` | `?before=<turn>&limit=20` (1 to 50) | `[Scene]`, the `limit` scenes before turn `before`, oldest first, for scrollback |
| PATCH | `/v1/stories/{id}` | `{title?, settings?: StorySettings}` | `Story` with the last 20 scenes (S6). Only the fields sent change, settings included, and the version doesn't move. A story keeps its `language` (S10): one sent is ignored. |
| DELETE | `/v1/stories/{id}` | | `204` |
| POST | `/v1/stories/{id}/turns` | `TurnRequest` | `text/event-stream`, see below |
| POST | `/v1/stories/{id}/close` | | `Story` with the last 20 scenes, its `ending.closed` true (N6). Only a story at its ending; any other is a `validation_error` of type `not_ended`. Closing a closed story changes nothing, and the version doesn't move. |
| POST | `/v1/stories/{id}/successor?heir_id=` | | `Successor` (N6): draws a random person of the world to carry the story on, by its population odds, or with `heir_id` (an `Heir.id` from the story's `heirs`) takes that heir, as they will be once the world has run on to the day they can act. Either replaces anyone drawn before. One drafting call, metered and charged like a draft (K2, so `402 out_of_credits` and the draft rate limits apply). Only a story at an ending the player hasn't closed; any other is a `validation_error` of type `not_ended` or `closed`. An `heir_id` that isn't one of the heirs is a `validation_error` of type `unknown_heir`, and an heir who doesn't live to that day one of type `heir_lost` (both with `source: "query"`): choose someone else. The version doesn't move. |
| POST | `/v1/stories/{id}/carry-on` | `{expected_version}` | `Story` with the last 20 scenes (N6): the person drawn becomes the player character, the ending is lifted, `opening_due` is true and the version moves on. For an heir the world first runs on to the day they can act, so the clock jumps ahead. A `validation_error` of type `no_successor` when nobody was drawn, `not_ended` or `closed` as above, and `409 version_conflict` when the story moved on. |
| POST | `/v1/stories/{id}/rewind` | `{expected_version, scenes}` | `Story` with the last 20 scenes (C8, N6): takes the story back `scenes` scenes (1 to 5) from a death, to the world exactly as it was when the scene it goes back to ended. `scenes: 1` goes back to just before the scene the death came in. The later scenes are gone from the story (and from `/scenes`), the ending and anyone drawn to carry it on are lifted, `turn` is the scene it went back to, and the version moves on. Nobody in the story remembers, and nothing is refunded. At most `Ending.rewind` scenes; more is a `validation_error` of type `too_far` on `scenes`. `not_ended` or `closed` as for `/successor`, and `409 version_conflict` when the story moved on. |
| GET | `/v1/stories/{id}/memory` | | `MemoryView` (C6) |
| GET | `/v1/stories/{id}/status` | | `StatusView` (`/status`, A8, G16, W10) |

```text
StorySummary  {id, title, genre, rating, turn, world_time_label, cover_url?,
               ending?: Ending, accent?: Accent, updated_at}  # accent: the story's color (S13)
Story         {id, title, genre, rating, version, turn,      # turn 0: play the opening
               settings: StorySettings, clock: Clock, scenes: [Scene], cover_url?,
               premise: string,                          # what it started from, to start again (N6)
               ending?: Ending,                          # set once it reached its ending (N6)
               successor?: Successor,                    # who was drawn to carry it on, at its ending
               heirs: [Heir],                            # who of the family can carry it on, at an
                                                         # ending not closed; empty otherwise (N6)
               opening_due: bool,                        # someone new carries it on: the next turn
                                                         # is their opening (N6)
               unfinished_turn?: {turn,                  # A3: the turn that was decided and shown
                                  kind,                  # and whose scene isn't saved yet. Show
                                  action?}}              # its action and send kind=resume (Turns)
Ending        {kind: "death"|"chosen",                    # the character died, or the player used /end
               character_id, character,                  # who, and their name as the story last knew it
               self_inflicted: bool,                     # harm they aimed at themselves killed them (F1)
               turn?: int,                               # the scene it came in; null for an older story
               closed: bool,                             # the player closed it (POST .../close)
               rewind: int}                              # how many scenes back it can be rewound
                                                         # (C8): up to 5 on Story, 1 on Balanced, 0 on
                                                         # Brutal, by the difficulty the death was
                                                         # played on; 0 for a death by the
                                                         # character's own hand, a chosen ending or a
                                                         # closed story
Successor     {name, age?: int, place?: string, people?: string,
               station: "common"|"skilled"|"notable"|"noble"|"royal",
               one_in: int,                              # how rare: one in this many (1 for the commonest)
               master: bool,                             # a hidden master: the player knows, the world doesn't
               lines: [string],                          # who they are, in the world's words (G2, G16)
               situation: string,                        # the moment their first scene opens on
               draws: int,                               # how many were drawn for this ending so far
               heir?: Heir}                              # the heir they are, rather than a random draw
Heir          {id, name,                                 # a child not born yet: "Mira's child, not yet born"
               relation: "child"|"grandchild"|"great-grandchild"|"descendant",
               age?: int,                                # now; null for a child not born yet
               unborn: bool,
               years: int}                               # years the story skips before they can act
                                                         # (until they are 16); 0 for none
StorySettings {narration_length: "short"|"medium"|"long", tone?: string,
               difficulty: "story"|"balanced"|"brutal",
               event_frequency: "calm"|"normal"|"dramatic",
               images: "off"|"key_moments"|"more",      # M2, default key_moments
               suggestions: bool,                         # S2
               accent?: Accent,                           # S13: the color the player picked;
                                                         # null (the default) for the genre's.
                                                         # PATCH null to go back to it
               language: "en"|"es"|"ca"}                  # S10, default en: the language the story
                                                         # started in, for good. Read only: PATCH
                                                         # and start ignore it.
                                                         # The labels the server writes follow it:
                                                         # the clock, a new scene's time bar, and
                                                         # Memory's and Status's fixed words
Clock         {world_s, label, timeline_id}              # label such as "Day 3, dusk" or "14 May 1974, 23:10"
                                                         # ("Día 3, atardecer" in a Spanish story,
                                                         # "Dia 3, capvespre" in a Catalan one, S10)
Accent        "lucid"|"jade"|"azure"|"ember"|"violet"|"crimson"|"cyan"|"orchid"|"lime"|"rose"|"silver"
                                                         # the app's accents by name (S13); only
                                                         # the app reads it, never a prompt (G5).
                                                         # PATCH refuses another name; one stored
                                                         # before a rollback reads as null
```

### Turns (B5, B7, S3, T10, V7)

```text
TurnRequest {kind: "action"|"choice"|"standing"|"opening"|"end"|"resume",
             action?: string,            # kind=action, 1 to 2000 characters, trimmed; or kind=end's
                                         # optional note on how the story ends (N6)
             choice_id?: string,         # kind=choice only: an id from the last scene's choices
             standing?: "wait"|"observe",# kind=standing only (S2)
             input_mode?: "typed"|"voice"|"voice_edited"|"choice",  # V7, see below
             drop_refused?: bool,        # kind=end only: end without what the world refused
             expected_version: int}      # the Story.version the app last saw (T10)
```

`kind: "opening"` writes the opening scene of a story that has none yet, right after
`POST /v1/drafts/{id}/start`, or of someone new who carries the story on (`Story.opening_due`, N6);
any other kind on such a story is a `validation_error` of type `not_opened`, and an opening on a
story that has opened is one of type `already_opened`. Each kind takes only its own field. `input_mode` is how an action
was entered (V7), `typed` when left out; a choice and a standing action are always saved as
`choice`, and the opening has none.

`kind: "end"` is `/end` (N6): the scene is the story's epilogue, told from things as they stand, or
from `action`, the player's note on how it should end, which the world checks like any action. When
the world rules out a part of the note or leaves it to a long shot, the stream ends with
`ending.refused` and nothing is saved or charged; the same turn sent again with `drop_refused: true`
ends the story without those parts. An end turn with no note has no `input_mode`, and one with a note
is typed or spoken, never `choice`. A turn whose character dies (`Ending.kind` `death`) or an end turn
brings the story to its ending: its scene has no choices, picture or event, and `scene.completed`
carries `story.ending`. From then on every turn is `409 story_ended`.

**Once a turn is decided and shown, that turn is played out (A3).** The server sends the steps it
decided, dice and all, before the story text (`steps.decided`). So that a throw, or a fall that
kills, can't be looked at and then swapped for another action, the turn is kept on the story from
that moment until its scene is saved (`Story.unfinished_turn`). While a story owes a turn, every
turn request plays that one, whatever kind or action it carries: the same action, read the same way,
on the same dice, at the difficulty and event frequency it was decided under. `turn.started` then
says so, with `resumed` and the kind and action that are playing. `kind: "resume"` is the request
for exactly this: it takes no field of its own, and on a story that owes no turn it is a
`validation_error` of type `nothing_unfinished` (reload the story: the turn was saved meanwhile, or
let go). An app that lost the stream after `steps.decided`, or that opens a story with
`unfinished_turn` set, shows that action and sends `resume`. An older app that sends its action
again gets the same turn.

Checks that can fail (auth, ownership, rating, version, the request itself, then credits, rate
limit and quota) run before the stream starts and come back as ordinary JSON errors. Once the
server answers `200` with `Content-Type: text/event-stream`, it sends these events, each as
`event: <name>`, then `data: <JSON>`, then a blank line:

| Event | Data | Notes |
| --- | --- | --- |
| `turn.started` | `{turn, resumed?: true, kind?, action?}` | Sent at once, so the app can show the action and a typing state. `resumed`, `kind` and `action` are there only when the story owed a turn and this request plays it out (A3): the app shows that action, not the one it sent. |
| `steps.decided` | `{turn, details: SceneDetails, passage_label?}` | What the engine decided, before the narrator writes a word (A3): each step with its class, its reason and the dice that decided it, exactly as the scene in `scene.completed` will carry them. Sent once, right after `turn.started`, on every turn with steps; an opening and an end turn with no note have none. The app can show the throws while the story is written. `passage_label` is the scene's heading when hours or days passed in it (W10), the same words as the scene's `time.passage_label`, so the app can show it over the story before its first words. |
| `narration.delta` | `{text}` | Narration as it is written. The first one arrives within about 2 s (S3). |
| `narration.reset` | `{reason: "cutaway"|"template"|"retry"}` | The partial narration is being rewritten, so the app clears it: `cutaway` and `template` when it was blocked (F4), `retry` when the model failed partway and is being retried once (T7). |
| `scene.completed` | `{scene: Scene, story: {version, clock, ending?: Ending}}` | The turn is saved. Always the last event of a successful turn. `story.ending` is there when this turn brought the story to its ending (N6). |
| `ending.refused` | `{message, refused: [{text, reason, class}]}` | An end turn's note asked for what the world won't give (N6). The last event: nothing was saved or charged. Each refused part comes with its reason in the world's words, and `class` is `ruled_out` or `long_shot`. Offer to play on, or to send the turn again with `drop_refused: true`. |
| `error` | `{code, message, details}` | The turn failed after streaming began. Nothing was saved and no credits were charged, so the app discards the partial scene. `code` is `unreadable_action` (the interpret step runs after `turn.started`, so this is where it arrives: offer to rephrase or retry, F4, and for a hard limit show `message` as it is, with `details.category` as in the JSON error), `llm_unavailable` or `bad_key` (offer a retry or a look at the key), `version_conflict` (another turn was saved first, or another action sent at the same time was decided first: reload, `details.current_version`) or `internal_error`. `details` is `{}` when there are none. |

A turn is all or nothing: the world state, the scene, the ledger entry and the version bump are saved
together only when the turn completes. The one thing kept earlier is the turn itself, from the
moment its steps are shown (`Story.unfinished_turn`, A3): what was sent and how it was read, never
an outcome, and it goes when the scene is saved. After `llm_unavailable`, `bad_key`, a lost
connection or an `internal_error` the story still owes that turn, and the next request plays it
out. A story is never stuck behind one: a kept turn that ends in `internal_error` again while it is
being played out is let go, and so is one that was decided for another moment of the story. Of two
actions sent at once, only the first to be decided is ever shown: the other ends with
`version_conflict`. A turn with no steps to show, such as an opening, is never kept.

### Scene

```text
Scene {turn, kind: "opening"|"action"|"choice"|"standing"|"end",
       player_action?: string,       # the words sent, a choice's label, "wait" or "observe", or
                                     # an end turn's note
       input_mode?: string,
       narration: string,
       choices: [{id, label,                                     # 0 to 4 (S2)
                  kind: "thread"|"personal"|"side"|"wild"|"time"}],   # time: a way to let hours
                                                                      # or days pass (W10); show
                                                                      # an unknown kind as thread
       standing_actions: ["wait", "observe"],
       time: {world_start_s, world_end_s, label, duration_label,   # "+8 h" (W10)
              personal_label?,                                    # "World: +0 s. You: +40 s." (W10a)
              passage_label?},                                    # "Three days later" (W10)
       details: SceneDetails,
       event?: {size: "personal"|"local"|"world", title},        # a W16 event arrived
       image?: SceneImage,
       portraits: [{character_id, name, url?}],                  # known characters in the scene (M4, M5)
       blocked: bool,                                            # the player blocked this scene (F6)
       created_at}

SceneDetails {steps: [{text,                                    # the step in plain words
                       class: "certain"|"contested"|"long_shot"|"ruled_out",
                       reason,                                   # in the world's words (A8, G14);
                                                                 # see "The story's language"
                       roll?: {odds_label,                       # A3: the throw in one line,
                               result: "success"|"partial"|"failure",   # "31 against 27"; the
                               seed,                             # reason names the dice
                               throw?: Throw},                   # the dice; none on a scene
                                                                 # saved before they travelled
                       beats?: [{beat, thing,                    # R2: only beats that found
                                 verdict: "made_canon"|"empty",  # something new or came up
                                 reason, roll?}],                # empty; empty stopped the step
                       struck?: [{by,                            # N6: what struck back after
                                  class, reason, roll?,          # the step, foes then a danger
                                  harm: "none"|"hurt"|"wounded"|"subdued"|"badly_wounded"
                                        |"maimed"|"dying"|"dead"}]}],
              chain?: [{link, class, reason}],                   # a cause-and-effect chain (A9)
              stopped_at_step?: int}                             # a chained plan stopped here (R6),
                                                                 # or something struck and hurt
                                                                 # the player character (N6)

# The story's language (S10). In an English story the engine's lines are its own, and a rolled
# step's `reason` tells the throw in words ("Speed, 2 dice, against a hard task, level 3: 36
# against 27, passed."), which the app leaves out because it shows the dice. In a Spanish or a
# Catalan story `reason` (of a step, a beat, what struck back and a link), `by`, a roll's
# `odds_label` when it kept no dice, a throw's `hand_why`, `greens`, `made_of[].text`, `against`
# and `miss_costs`, and the scene's `event.title` come in the story's language, and a `reason`
# comes without the sentence that tells its throw, so it may be empty. A line the wording model
# couldn't say in time stays in English. Scenes saved before 2026-11-12 keep their English lines.

Throw {dice: [{kind: "plain"|"green"|"violet"|"gold"|"grey",    # A3: every die as it fell, in
              face,                                             # the order thrown, 1 to 20;
              sprung: bool}],                                   # sprung: thrown because the die
                                                                # before it showed a 20
       hand, hand_why,                    # the dice in the hand before any sprung, and why:
                                          # "Aura blade (skilled), 3 dice"
       greens: [string],                  # each green die's reason, in the order thrown
       number,                            # what the total had to reach
       made_of: [{text, points}],         # what the number is made of, the level first; the
                                          # points add up to it
       total, most,                       # the dice added up (a gold die never under 10), and the
                                          # most the hand could make with no 20
       mark: "over_the_top"|"passed"|"so_close"|"missed",
       against,                           # what it was up against, in a sentence
       deadly: bool, miss_costs,          # a miss could kill, and what it costs (N6)
       insight: bool, insight_at}         # the violet die showed an insight (A4), and the face
                                          # that shows one: 18, or 15 when two talents cover it
                                          # The app never rolls: it shows these dice.

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
- `illustrate` is a picture the player asked and pays for (M2), so without credits it answers `402
  out_of_credits` (with `details.balance_cents` and `details.available_cents`) instead of
  `skipped`, and the scene keeps the picture state it had: offer the player's own key, then ask
  again. `.../image` never answers `402`.
- `illustrate` draws the scene's planned picture if it has one, or a picture of the scene itself,
  even with pictures off. On a scene whose picture is ready it returns that picture at no charge.
- Pictures are reused: a character's portrait or a place's picture is drawn once and every scene
  that shows it answers with the same `image_id` (M4). When a place or a character changes for
  good (ruined, occupied, a lost eye, old age), a later scene plans a new picture of it, with a new
  `image_id`, and scenes from then on show that one; earlier scenes keep theirs (M1, M5). Size the
  slot by `kind` before the picture arrives: portraits and covers are 3:4, places and scenes 16:9.
- `url` is a signed URL that works until `expires_at`, about an hour. After that, ask
  `GET .../images/{image_id}` for a fresh one, and cache the picture by `image_id`, not by URL.
- With the player's own key (`X-LLM-*` headers) the picture is drawn on their key at no charge. A
  key that can't draw pictures (rejected, or a free-tier Gemini key, which has no image models)
  falls back to credits; a server error on their key skips the picture instead (M7).
- Errors: `401 unauthenticated` without a valid access token, `404 not_found` for an unknown
  story, scene or picture, `403 forbidden` for another player's story or one above the account's
  rating limit (F8), `400 validation_error` for an unsupported `X-LLM-Provider`, `429
  rate_limited` from the credit meter, and, for `illustrate` only, `402 out_of_credits`. After
  either, a picture the scene already had is as it was: a planned one still planned, a skipped
  one still skipped. On a scene that had none, the picture Illustrate planned stays: `skipped`
  after a `402`, so nothing draws it until the player asks again, and planned after a `429`, for
  the app to ask again.

### Reading aloud (V8 to V10)

| Method | Path | Query | Response |
| --- | --- | --- | --- |
| POST | `/v1/stories/{id}/scenes/{turn}/audio` | `part` (0 to 99, default 0), `voice` (default `Sulafat`) | `SceneAudio` |

```text
SceneAudio {status: "ready"|"pending"|"blocked", part, parts, text,
            url?, expires_at?, duration_ms?}   # url, expires_at and duration_ms only when ready
```

One part of the scene read aloud in the studio voice (Gemini 3.8 Flash-Lite TTS, V9), in the story's
language and accent: Spanish from Spain (`es-ES`), English (`en-US`) or Catalan (`ca-ES`), from
the story's settings, so the app never sends one. Ask for part 0, play it as soon as it comes, and
ask for the next part while it plays, until `parts`.

- **`voice`** is one of `Sulafat` (warm), `Gacrux` (mature), `Charon` (deep) or `Algieba`
  (smooth). Anything else is `400 validation_error` with the field `voice` (`unknown_voice`), and a
  part past the end is one with the field `part` (`out_of_range`), both with `source: "query"`.
- **`text`** is the words the part reads: the narration without emphasis marks, with its
  whitespace collapsed and a blank line between paragraphs. The parts depend only on the
  narration, so they never change for a scene.
- **Safe to repeat.** Each part is read and charged at most once per voice and kept, so asking again
  answers the same file at no charge (V10). A repeat while the part is being read answers
  `pending`: ask again after a second. `blocked` means the voice model refused the part, for good
  and at no charge: read `text` in the device's own voice.
- `url` is a signed URL to an MP3 (48 kbps mono) that works until `expires_at`, about an hour.
- **Billing (K2, T9).** Always on our key, even with `X-LLM-Api-Key`, which the app doesn't send
  here. The checks above apply, with their own rate limit (30 parts a minute) and daily quota
  (1,000 parts), and a part needs 3 cents available. The real cost, up to about 2 cents for a long
  part, is charged as a `voice` ledger entry with the story and turn. A part that fails costs
  nothing.
- **Errors:** `404 not_found` for an unknown story or scene, or a scene the player blocked (F6),
  `403 forbidden` for another player's story or one above the account's rating limit (F8), `402
  out_of_credits`, `429 rate_limited` or `429 quota_exceeded` from the meter, and `503
  llm_unavailable` after one retry. After any of them the app reads the rest of the scene in the
  device's voice.

### Memory and status (C6, G16)

Only what the player character knows, in the world's words. Hidden truth never appears.

```text
MemoryView {character: {name, lines: [string], portrait_url?},
            people:   [{id, name, lines: [string], portrait_url?,
                        attitude?, attitude_label?,   # how they come across (W4), for someone the
                                          # character met: "warm" | "friendly" | "neutral" |
                                          # "cold" | "hostile", and the same in words
                        status, presumed, status_label}],
                                          # whether they live as far as the character knows
                                          # (C1, C6): "alive" | "missing" | "dead", a death only
                                          # presumed, and the same in words. Family comes
                                          # first: "Your child." (N6)
            places:   [{id, name, lines: [string], image_url?}],
            factions: [{id, name, lines: [string],
                        esteem, dread, standing_label}],
                                          # their regard (W3): "admired" | "respected" |
                                          # "neutral" | "disliked" | "despised"; their fear:
                                          # "none" | "wary" | "feared"; and both in words
            goals:    [{id, text, kind, origin, origin_label, progress?}],
                                          # the open goals (N2), the thread the character
                                          # follows first. kind is where the goal shows:
                                          # "followed" (the one the story last moved, one at
                                          # most) | "own" (the player set it) | "side" (a
                                          # lead they took up). origin is where it came
                                          # from: "start" | "stated" | "asked" | "taken";
                                          # origin_label says it in words: "Asked of you by
                                          # Master Wen, day 3". progress is where it stands
                                          # as far as the character knows, when a scene
                                          # said. An app that doesn't know a kind shows the
                                          # goal as the player's own.
            goals_done: [{id, text, how, when_label?}],
                                          # the goals that are over, in the order they
                                          # closed: how is "achieved" | "failed" |
                                          # "abandoned", when_label the day it closed
                                          # ("Day 3"), none on a record from before the
                                          # day was kept
            leads:    [{id, text, expires_label?}],
            rumors:   [{id, text, heard_label, certainty, unconfirmed}],
                                          # certainty: "unconfirmed", or "confirmed" / "false"
                                          # where the character knows for themselves (they did
                                          # or saw it, or were there); unconfirmed is
                                          # certainty == "unconfirmed", for older apps. The
                                          # same words show once per certainty, by when last
                                          # heard.
            deeds:    [{id, text, when_label, seen, known_label,
                        trail: [{kind, text}], open_label?}],
                                          # in time order. seen is who saw it as far as the
                                          # character knows (W2, C6): their own deed is
                                          # "seen" | "public" | "unseen", someone else's is
                                          # "watched" | "heard_of"; known_label says it in
                                          # words: "Seen by Carmine Russo and 1 other".
                                          # trail is what they know became of their own
                                          # deed since, in the order it happened: kind is
                                          # "went" (someone who saw it, whom they saw go off
                                          # to tell) | "dead" (someone who saw it is dead, as
                                          # far as they know) | "heard" (talk of it a scene
                                          # told them) | "came" (someone came to them over
                                          # it); text says it in words: "Wei went to tell
                                          # the Azure Cloud Sect". open_label, where who
                                          # else knows is an open question, says that they
                                          # can't tell. An app shows a kind it doesn't know
                                          # by its text alone.
            threads:  [{id, title, status}]}  # status: "open" | "dormant" | "resolved" |
                                          # "failed" | "abandoned" | "resolved_without_player"

# Every *_label is in the story's language (S10) and comes with the value it says, so the app
# marks and tints an entry by the value and never reads the words. An app from before the
# values shows the labels alone.
#
# What code words of the world's record is in the story's language too (S10): a deed's `text`
# ("Mataste a Zhao Kun en el pozo."), a rumor's `text` and a thread's `title` or a lead's `text`
# when the director wrote it ("Una vieja amistad en apuros"), and on the sheet a wound the engine
# named. Rumors and titles are kept as first told, so a story started before 2026-11-12 keeps
# the English ones it has.

StatusView {character: {name, lines: [string], portrait_url?},   # portrait once drawn (M4);
                                          # lines are the sheet as plain text, kept for apps
                                          # from before `sheet`; an app that reads `sheet`
                                          # doesn't show them. They
                                          # include a child on the way (N6), and each
                                          # technique with its mastery and its count toward
                                          # the next: "Aura blade (technique, learning, 2 of
                                          # 6 uses)" (A4), then each talent, each thing ruled
                                          # on and the bridges that hold: "The sword (talent,
                                          # one of a kind, eight times as fast): anything
                                          # fought with a blade", "Aura blade: grows eight
                                          # times as fast, inside your talent (The sword)",
                                          # or with every talent that reaches it, since their
                                          # paces add: "Aura blade: grows 16 times as fast,
                                          # inside your talents (The sword and Aura sense)",
                                          # "Bridge: the load formula", "Outside your
                                          # talents: Herb lore; Rope trick" (A4)
            sheet: Sheet,                 # the same sheet in parts, which the app lays out (G16)
            reputation: [{name, label}],
            clock: Clock,
            since: [{text, ago_label}]}      # "The bar shooting: 2 days ago" (W10), and the
                                          # latest gains and losses: "To Milo: 12 copper coins" (C10)

Sheet {about: [string],                   # who they are, a few words each: "Outer disciple,
                                          # the Azure Sky Sect" (only a faction they know,
                                          # C6), a title, "17 years old"
       description,                       # how they come across
       condition: {health: "unhurt"|"hurt"|"wounded"|"badly_wounded"|"dying", health_label,
                   wounds: [{text, lasting}],          # lasting: one that stays, a lost eye
                   states: [{name, effect, ends_label?}],   # "Passes in 2 hours" (W10)
                   reserves: [{name, level}],          # what is left, 0 to 100
                   expecting_label?},                  # a child on the way and when (N6)
       paths: [{name, rungs: [{name, stage, filled?, description, note}],
                above: [{name, known, note, said: [string], gap_below}], higher}],
                                          # each ladder as far as they know it (G18, C6).
                                          # rungs: from its first rung up to their own, lowest
                                          # first: the last is theirs and carries its
                                          # description, the stage of their rank ("Late
                                          # stage", or "At its peak: you can try to break
                                          # through") and filled, how full the rank is from 0
                                          # to 1 (G19), absent on a ladder's last rung; empty
                                          # for a ladder they don't stand on. note: "Reached,
                                          # day 9", "Left behind, day 9".
                                          # above: the rungs over their own that they have
                                          # heard of, lowest first: the ones everyone in the
                                          # world knows and the ones the story named to them.
                                          # known: confirmed, or only heard of. note:
                                          # "Everyone has heard of it", "Heard of, day 14",
                                          # "Confirmed before Elder Han, day 15". said: what
                                          # they learned or heard about it. gap_below: rungs
                                          # nobody named to them lie under it. higher: "" or
                                          # who they have seen stand above all of those
                                          # ("Elder Mo stands somewhere up here."), with no
                                          # rung named. Nothing else of what lies higher is
                                          # sent, and never what a rung is or what reaching
                                          # it takes.
       money_label?,                      # "12 silver taels"
       items: [{name, kind, kind_label, description, history, quantity, carried}],
                                          # kind: weapon | armour | gear | treasure |
                                          # consumable | vehicle | property | document |
                                          # other (no kind_label). What they carry comes
                                          # first, then what they keep elsewhere (C10).
       skills: [{name, level, level_label, dice, notes}],
                                          # best first; level is the skill ladder's value
                                          # (untrained to master) and dice what it throws (A3)
       powers: [{name, description, limits: [string], cost, ready, ready_label, secret}],
                                          # ready_label: "Ready", or "Ready in 2 hours" while
                                          # it recovers (W10a); secret: nobody knows of it
       techniques: [{name, style, effect, cost, source_label, mastery, mastery_label, dice,
                     uses, need?}],       # mastery: learning | practiced | skilled |
                                          # second_nature | own, and dice what it throws
                                          # (A3). need: the uses that reach the next mastery
                                          # at their own pace (A4), left out where use alone
                                          # takes it no further. source_label: "Your own", or
                                          # "Learned from Zhao Kun" for someone they know
                                          # (C6), and empty where the record names nobody.
       traits: [{name, kind: "gift"|"flaw"|"quirk", kind_label, description}],
       temperament: [string],
       talents: [{name, strength, strength_label, pace_label, covers}],
                                          # strength: slow | knack | genius | one_of_a_kind;
                                          # "Genius", "Four times as fast" (A4)
       talent_notes: [string],            # each thing ruled on, the bridges that hold and
                                          # what lies outside, as in `lines` (A4)
       grew: [{kind, when, text, how}]}   # how they grew (A4, G17), latest first, at most 30.
                                          # kind: breakthrough | stage | skill | learned |
                                          # mastery | new_use. when: the day, "Day 9". text:
                                          # "Broke through to Qi Condensation", "Qi
                                          # Condensation: Late stage" (a rank filling, G19),
                                          # "Swordsmanship: Skilled", "Learned Falling Leaf
                                          # Palm". how: "With a
                                          # master", "By doing it", or empty where the record
                                          # doesn't say
```

Every `*_label`, and every word the engine adds, comes in the story's language (S10) next to the
value it says, so the app picks a color or draws a meter from the value and never reads the words.
An app shows a value it doesn't know by its label alone.

### Reports (F6)

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| POST | `/v1/stories/{id}/scenes/{turn}/report` | `{category: "sexual"|"minor"|"hate"|"real_person"|"self_harm"|"other", note?, block?: bool}` (block defaults to false) | `204` |

- **One report per scene and player.** Reporting a scene again updates the category (and the note,
  when one is sent) and puts the report back in the review queue. Both answer `204`.
- **`block: true` hides the scene's text** in the app at once, and from then on the scene comes
  back with `blocked: true`, so the app shows a placeholder in its place. A block is never undone,
  even by a later report with `block: false`. The story itself goes on as before.
- `note` is up to 1000 characters. It is kept with the report, read only by staff handling
  reports, and never logged.
- **Errors:** `401`, `403 forbidden` for someone else's story or a rating above the account's
  limit (F8), `404 not_found` for an unknown story or a turn with no scene, `400
  validation_error` for an unknown category or a note that is too long.
- Staff review reports in the Django admin's queue
  (T16, [ARCHITECTURE.md](ARCHITECTURE.md#safety-ratings-and-reports)).
