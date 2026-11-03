# PlayableAnime app

Flutter client. State management with Riverpod, routing with go_router.

## Run

```bash
flutter pub get
flutter run
```

The API URL is set at compile time and defaults to `http://localhost:8080`:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

(`10.0.2.2` is how an Android emulator reaches your machine.)

## Check

```bash
dart format lib test
flutter analyze
flutter test
```

## Layout

```
lib/
  main.dart, app.dart     Entry point, MaterialApp
  router.dart             Routes: tabs (Discover, Library, Settings), create, story, memory
  home_shell.dart         Bottom navigation
  core/                   Config, theme, API client, BYOK key store, async helpers
  features/
    discover/             Starter premises
    create/               New story from a premise
    story/                Models, repository, play screen, memory screen
    library/              Your stories
    settings/             Bring-your-own-key
```
