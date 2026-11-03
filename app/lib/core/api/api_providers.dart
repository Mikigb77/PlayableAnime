import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../byok_store.dart';
import '../config.dart';
import '../fake/fake_backend.dart';
import '../session/session_controller.dart';
import 'api_client.dart';
import 'api_error.dart';

/// The transport: the network, or the in-app fake backend with `API_MODE=fake`. Tests override
/// this with their own [FakeBackend].
final httpClientProvider = Provider<http.Client>((ref) {
  final client = AppConfig.isFake ? FakeBackend.standard() : http.Client();
  ref.onDispose(client.close);
  return client;
});

final apiBaseUrlProvider = Provider<String>(
  (ref) => AppConfig.isFake ? FakeBackend.baseUrl : AppConfig.apiBaseUrl,
);

/// The client for the app's API: the session's bearer token (refreshed on a 401) and the player's
/// own key on storyteller calls.
final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(
    baseUrl: ref.watch(apiBaseUrlProvider),
    httpClient: ref.watch(httpClientProvider),
    byok: ref.watch(byokStoreProvider),
    tokens: ref.watch(sessionProvider.notifier),
  ),
);

/// A client without the session, for the auth endpoints, which take no bearer token. The session
/// signs in, refreshes and signs out through it, so the session never depends on the client that
/// depends on the session.
final authApiClientProvider = Provider<ApiClient>(
  (ref) =>
      ApiClient(baseUrl: ref.watch(apiBaseUrlProvider), httpClient: ref.watch(httpClientProvider)),
);

/// How a failed provider retries on its own (Riverpod retries every failure by default): only a
/// failure that may pass by itself, at most three times, after 0.5, 1 and 2 seconds. A missing or
/// forbidden story or a limit is final, and the screen offers a retry where one can help (T9).
Duration? retryTransient(int retryCount, Object error) {
  if (retryCount >= 3 || error is! ApiException || !error.code.isTransient) return null;
  return Duration(milliseconds: 500 << retryCount);
}
