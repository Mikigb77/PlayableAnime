import 'package:flutter/foundation.dart';

/// Where API calls go: the real backend, or the in-app fake in `lib/core/fake/`.
enum ApiMode { real, fake }

/// Compile-time configuration, set with `--dart-define`.
abstract final class AppConfig {
  /// The backend's base URL. Android emulators reach the host machine at http://10.0.2.2:8080.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8080',
  );

  /// `--dart-define=API_MODE=fake` runs the whole app against the in-app fake API, so app work
  /// never waits on the backend.
  static const apiMode = String.fromEnvironment('API_MODE') == 'fake' ? ApiMode.fake : ApiMode.real;

  static const isFake = apiMode == ApiMode.fake;

  /// Until sign-in lands on the backend (T8), the real-mode app offers "Continue without an
  /// account" so it still works against today's backend. The accounts work (WS13) removes this
  /// together with the backend's own auth. `--dart-define=ALLOW_GUEST=false` hides it.
  static const allowGuest = !isFake && bool.fromEnvironment('ALLOW_GUEST', defaultValue: true);

  /// The widget gallery at /gallery, for development: debug builds and the fake API only.
  static const showGallery = kDebugMode || isFake;
}
