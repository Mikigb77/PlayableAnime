# Lucid Saga app

The Flutter client: Riverpod for state, go_router for routes, Material 3 with the app's own design
system. The look, the components and their rules are in [DESIGN.md](DESIGN.md).

## Run

```bash
flutter pub get          # also generates the strings in lib/l10n/gen
flutter run --dart-define=API_MODE=fake
```

**`API_MODE=fake`** runs the whole app on an in-app fake of the API (docs/API.md), with no backend:
a demo account, the starter worlds, a story in progress, streamed turns, pictures that arrive a few
seconds after the text, and typed errors. Put a trigger in an action to try the error states:
`[fail:out_of_credits]`, `[fail:rate_limited]`, `[fail:llm_unavailable]` (fails mid-stream),
`[fail:version_conflict]`, `[fail:picture]` (a planned picture that is then skipped) or `[reset]`.
The fake lives in `lib/core/fake/`, one
file per area of the API, so each feature thread extends its own.

Sign-in works offline too. **Try the demo account** on the welcome screen, or sign in with
`demo@lucid.test` and the password `lucid-demo`. **Continue with Google** opens a picker that stands
in for Google: the demo player, a new player (who is asked for a birth date) and the owner (unlimited
credits). Email sign-up checks what the backend checks and, like the backend, grants the 50¢
starter credit only once an address is verified, so a new email account starts at 0.

Against a real backend, set its URL (the default is `http://localhost:8080`):

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

(`10.0.2.2` is how an Android emulator reaches your machine.) Email sign-in and sign-up work against
any backend. Google sign-in needs the OAuth client ids (T8), passed at build time:

```bash
flutter run --dart-define=API_BASE_URL=… \
  --dart-define=GOOGLE_WEB_CLIENT_ID=….apps.googleusercontent.com \
  --dart-define=GOOGLE_IOS_CLIENT_ID=….apps.googleusercontent.com
```

- **Web:** the web client id. The page shows Google's own button, and the web client lists the
  app's origins (`http://localhost:<port>` for `flutter run -d chrome --web-port <port>`).
- **Android:** the web client id again, as the server client id. Google matches the app by its
  package name and signing SHA-1, so add an Android OAuth client with both in the Google Cloud
  console (`./gradlew signingReport` prints the SHA-1).
- **iOS:** the iOS client id, and its reversed form (`com.googleusercontent.apps.…`) as a URL scheme
  under `CFBundleURLTypes` in `ios/Runner/Info.plist`.
- The backend's `GOOGLE_OAUTH_CLIENT_IDS` lists every one of these ids, or it refuses the tokens.

Without an id, the Google button is hidden on that platform and email still works.

### Web

```bash
flutter run -d chrome --dart-define=API_MODE=fake --no-web-resources-cdn
```

`--no-web-resources-cdn` serves the Flutter engine from the app itself instead of Google's CDN, so
nothing loads from elsewhere at runtime (the fonts are bundled too).

### Widget gallery

`/gallery` shows every component in its states, with switches for the theme, the genre accent and
the text size. It exists in debug builds and with the fake API. On the web, open
`/#/gallery?theme=light&accent=jade&scale=2` to set the switches from the URL.

## Check

```bash
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
```

CI runs the same three on Flutter 3.44.5.

## Layout

```
lib/
  main.dart, app.dart       Entry point, MaterialApp, themes and strings
  router.dart               Routes: welcome, the tabs (Discover, Library, Account), create, story
  home_shell.dart           Bottom bar on phones, side rail from 840 px
  design/                   Tokens, themes, genre accents, type, motion, components, gallery
  core/
    api/                    ApiClient (bearer token, one refresh on 401, own-key headers),
                            SSE parser, turn events, typed errors and their copy
    session/                Session, secure storage, SessionController (sign in, refresh, sign out)
    fake/                   The fake API, one file per area: auth, account, premises, drafts,
                            stories, turns, pictures, reports
    l10n.dart               context.l10n
    byok_store.dart         The player's own Gemini key (S9)
  features/
    auth/                   Welcome, Google sign-in, email sign-in and sign-up, birth date (T8, F8)
    discover/               Starter worlds
    create/                 New story from a premise
    story/                  Models, repository, play screen, memory, status
    library/                Your stories
    account/                Profile, credits and history, own key, content preferences (F7),
                            privacy policy, export, delete, the out-of-credits sheet, sign out
    voice/                  Dictation: speech engine, controller, button, input mode (V1–V7)
  l10n/app_en.arb           Every string the player sees (S10)
assets/
  fonts/                    Literata and Inter, SIL Open Font License
  fake/                     Placeholder pictures for the fake API
  legal/                    The privacy policy the app shows, a copy of docs/PRIVACY.md (T12)
```

## Building on it

- **Screens** use the components in `design/` and the strings in `l10n/app_en.arb`; see DESIGN.md.
- **API calls** go through `apiClientProvider`. Errors arrive as `ApiException` with a typed `code`;
  `describeError` turns one into the player's words (T7). A turn is `StoryRepository.takeTurn`, a
  stream of `TurnEvent`s that always ends in `SceneCompleted` or `TurnFailed`.
- **Sign-in** goes through `authRepositoryProvider` (`signInWithGoogle`, `logIn`, `register`,
  `signOut`), which posts to `/v1/auth/*` and hands the `Session` to the `SessionController`. The
  router follows the session. `fieldErrors` turns a `validation_error` into a message per field.
- **Out of credits:** on a `402 out_of_credits`, call `showOutOfCreditsSheet(context, error)`. It
  shows the balance, says top-ups are coming soon and offers the player's own key; it answers
  `OutOfCreditsOutcome.keyAdded` when a key was saved, so the caller can retry the turn.
- **The account** is `meProvider` (`GET /v1/me`, refreshed when the Account tab shows) and
  `creditsHistoryProvider`; `formatCredits` writes an amount the way the app shows it (50¢, $1.20).
- **The privacy policy** is `app/assets/legal/privacy_en.md`, everything in `docs/PRIVACY.md` from
  "Who we are" on. A test fails when the two differ, so a change to the policy copies it over.
- **Voice:** put `DictationButton(tracker: InputModeTracker(controller))` next to any text box and
  send `tracker.mode.wire` as the turn's `input_mode` (V7).
- **Your own key** (S9) is `byokStoreProvider`, which holds the signed-in account's key only.
- **Tests** can run any flow on `FakeBackend.standard(pace: FakePace.instant)`; see
  `test/app_test.dart` and `test/helpers.dart`. A test that answers requests by hand makes its
  `Completer`s inside the test body, not in `setUp`, or they never complete under the test clock
  (see `test/features/story_screen_test.dart`).
