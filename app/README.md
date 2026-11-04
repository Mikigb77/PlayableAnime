# Lucid Saga app

The Flutter client: Riverpod for state, go_router for routes, Material 3 with the app's own design
system. The look, the components and their rules are in [DESIGN.md](DESIGN.md). Screens on the fake
API: [play and account](docs/screenshots/screens.jpg), [Discover and creating a
story](docs/screenshots/create.jpg), [changing a draft](docs/screenshots/create-changes.jpg), and
[the library and memory](docs/screenshots/library-memory.jpg).

## Run

```bash
flutter pub get          # also generates the strings in lib/l10n/gen
flutter run --dart-define=API_MODE=fake
```

**`API_MODE=fake`** runs the whole app on an in-app fake of the API (docs/API.md), with no backend:
a demo account, the starter worlds, a story in progress, streamed turns, pictures that arrive a few
seconds after the text, and typed errors. Put a trigger in an action to try the error states:

- before the stream: `[fail:out_of_credits]` (an empty balance, so your own key gets past it),
  `[fail:rate_limited]`, `[fail:quota_exceeded]`, `[fail:version_conflict]`;
- in the stream, as the real interpret and narrate steps send them: `[fail:unreadable_action]`,
  `[fail:limit]` (a hard limit with `details.category`), `[fail:bad_key]`, `[fail:lost_race]`
  (another turn was saved first) and `[fail:llm_unavailable]` (after a few words);
- `[fail:dropped]` (saved, then the connection drops before `scene.completed`), `[reset]` (a
  cut-away, F4) and `[fail:picture]` (a planned picture that is then skipped).

The words of an action shape the scene: "attack" or "duel" is a fight with a roll and a picture,
"then" chains steps that stop where one fails, "stop time" runs the two clocks apart, "leap" is a
long shot and "fly" is ruled out.

A premise or a change asked of a draft takes `[fail:out_of_credits]`, `[fail:rate_limited]`,
`[fail:quota_exceeded]`, `[fail:version_conflict]`, `[fail:llm_unavailable]`,
`[fail:unreadable_action]`, `[fail:bad_key]`, `[fail:picture]` and `[reset]` too, and
`[fail:real_person]` (refused under the field that names one, G12). Drafting takes about three
seconds and is charged like the real thing (3 cents a model call, free on your own key), so the
costs the review shows can be checked against the balance. The fake lives in `lib/core/fake/`, one
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
  package name (`com.lucid.saga`) and signing SHA-1, so add an Android OAuth client with both in
  the Google Cloud console (`./gradlew signingReport` prints the SHA-1 of your debug key). The
  released APK is signed with the release key, whose Android client is registered once
  ([docs/DEPLOY.md](../docs/DEPLOY.md#5-set-up-google-sign-in)).
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

CI runs the same three on Flutter 3.44.5, and builds the release APK with `infra/build-apk.sh`
(debug-signed), as each deploy does with the release key.

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
    names.dart              Names from the world as headings ("The inner court")
    byok_store.dart         The player's own Gemini key (S9)
  features/
    auth/                   Welcome, Google sign-in, email sign-in and sign-up, birth date (T8, F8)
    discover/               Starter worlds: the signature ones first, then a shelf of covers
    create/                 A new story: premise, drafting, the world and character review with
                            what each change costs (draft.dart redraftFor), rating, start
    story/                  Models, repository, the play screen and its controller, scene
                            details, report and block, story settings, status, and the memory
                            page (memory.dart, memory_screen.dart: only what the character knows)
    library/                Your stories, with the turn and in-world time, and delete
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
- **Out of credits:** on a `402 out_of_credits`, call
  `showOutOfCreditsSheet(context, error: error, retriesItself: true)`. It shows the balance, says
  top-ups are coming soon and offers the player's own key; it answers
  `OutOfCreditsOutcome.keyAdded` when a key was saved, so the caller can retry the turn. Its note
  on a saved key says "trying again on it" with `retriesItself`, or "try again to carry on"
  without, so a caller never shows a second one. The create flow's `offerOwnKey(context, error)`
  does both: it opens the sheet only for that error and answers true when the player added a key.
- **The account** is `meProvider` (`GET /v1/me`, refreshed when the Account tab shows) and
  `creditsHistoryProvider`; `formatCredits` writes an amount the way the app shows it (50¢, $1.20).
- **The privacy policy** is `app/assets/legal/privacy_en.md`, everything in `docs/PRIVACY.md` from
  "Who we are" on. A test fails when the two differ, so a change to the policy copies it over.
- **Voice:** put `DictationButton(tracker: InputModeTracker(controller))` next to any text box and
  send `tracker.mode.wire` as the turn's `input_mode` (V7).
- **Your own key** (S9) is `byokStoreProvider`, which holds the signed-in account's key only.
- **Tests** can run any flow on `FakeBackend.standard(pace: FakePace.instant)`; see
  `test/app_test.dart` and `test/helpers.dart`. `AppHarness` in `test/features/harness.dart` signs
  in and opens the whole app at any location, with the requests it sent to check. A test that answers requests by hand makes its
  `Completer`s inside the test body, not in `setUp`, or they never complete under the test clock
  (see `test/features/story_screen_test.dart`). `test/features/play_screen_test.dart` plays a
  story through the fake with a paced stream; give the fake `clock: tester.binding.clock.now` so
  pictures arrive on the test's clock.
- **The play screen** draws what `PlayController` holds (the story, the turn in flight, pictures
  and notices) and keeps its own scroll: it opens at the top of the newest scene, follows a turn as
  it streams but never past its top, and loads older scenes above without moving the page. A
  turn or an Illustrate refused for credits opens `showOutOfCreditsSheet` and goes again once the
  player adds their own key; a saved scene or a drawn picture refreshes `meProvider` if a screen
  has loaded it.
