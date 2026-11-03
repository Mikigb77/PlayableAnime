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
`[fail:version_conflict]`, `[fail:picture]` or `[reset]`. The fake lives in `lib/core/fake/`, one
file per area of the API, so each feature thread extends its own.

Against a real backend, set its URL (the default is `http://localhost:8080`):

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

(`10.0.2.2` is how an Android emulator reaches your machine.) Until sign-in ships (T8), a real-mode
build also offers **Continue without an account** for today's backend; `--dart-define=ALLOW_GUEST=false`
turns it off.

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
    auth/                   Welcome (sign-in screens come with WS13)
    discover/               Starter worlds
    create/                 New story from a premise
    story/                  Models, repository, play screen, memory, status
    library/                Your stories
    account/                Appearance, own key, sign out
    voice/                  Dictation: speech engine, controller, button, input mode (V1–V7)
  l10n/app_en.arb           Every string the player sees (S10)
assets/
  fonts/                    Literata and Inter, SIL Open Font License
  fake/                     Placeholder pictures for the fake API
```

## Building on it

- **Screens** use the components in `design/` and the strings in `l10n/app_en.arb`; see DESIGN.md.
- **API calls** go through `apiClientProvider`. Errors arrive as `ApiException` with a typed `code`;
  `describeError` turns one into the player's words (T7). A turn is `StoryRepository.takeTurn`, a
  stream of `TurnEvent`s that always ends in `SceneCompleted` or `TurnFailed`.
- **Sign-in** screens post to `/v1/auth/*` through `authApiClientProvider` and hand the `Session`
  JSON to `ref.read(sessionProvider.notifier).signIn(...)`. The router follows the session.
- **Voice:** put `DictationButton(tracker: InputModeTracker(controller))` next to any text box and
  send `tracker.mode.wire` as the turn's `input_mode` (V7).
- **Tests** can run any flow on `FakeBackend.standard(pace: FakePace.instant)`; see
  `test/app_test.dart` and `test/helpers.dart`.
