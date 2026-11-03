/// Compile-time configuration. Override with `--dart-define=API_BASE_URL=...`.
abstract final class AppConfig {
  /// Android emulators reach the host machine at http://10.0.2.2:8080, not localhost.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8080',
  );
}
