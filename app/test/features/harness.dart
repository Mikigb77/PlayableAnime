import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:playable_anime/app.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/core/session/session_controller.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';

/// The whole app on a fake backend that answers at once, signed in as the demo account, for
/// driving a feature the way a player would.
class AppHarness {
  AppHarness({FakePace pace = FakePace.instant}) : backend = FakeBackend.standard(pace: pace) {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  }

  final FakeBackend backend;
  final store = MemorySessionStore();

  /// The recognizer every mic in the app uses.
  final speech = FakeSpeechEngine();

  /// Makes the demo account an adult's or a teen's (F8), before sign-in: the limit follows the
  /// birth date, as on the server.
  set maxRating(String rating) {
    final now = backend.now();
    final age = rating == 'mature' ? 30 : 14;
    final born = DateTime.utc(now.year - age, now.month, now.day);
    backend.data.auth.users[FakeAuthState.demoUserId]!['birth_date'] = born
        .toIso8601String()
        .substring(0, 10);
  }

  Future<void> signIn() async {
    final api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend);
    final session =
        await api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    store.value = Session.fromApi(session);
  }

  /// Signs in and opens the app at [location].
  Future<void> launch(
    WidgetTester tester, {
    String location = '/discover',
    List<Override> overrides = const [],
    double textScale = 1,
  }) async {
    await signIn();
    usePhone(tester);
    if (textScale != 1) {
      tester.platformDispatcher.textScaleFactorTestValue = textScale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    }
    tester.platformDispatcher.defaultRouteNameTestValue = location;
    addTearDown(tester.platformDispatcher.clearDefaultRouteNameTestValue);
    await tester.pumpWidget(
      ProviderScope(
        retry: retryTransient,
        overrides: [
          httpClientProvider.overrideWithValue(backend),
          apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
          sessionStoreProvider.overrideWithValue(store),
          speechEngineProvider.overrideWithValue(speech),
          ...overrides,
        ],
        child: const App(),
      ),
    );
    await settle(tester, frames: 10);
  }

  /// Where the router is now.
  String location(WidgetTester tester) =>
      GoRouter.of(tester.element(find.byType(Navigator).last)).state.uri.toString();

  /// The requests the app sent to [path] with [method].
  List<FakeRequest> sent(String method, bool Function(String path) path) => [
    for (final r in backend.requests)
      if (r.method == method && path(r.uri.path)) r,
  ];
}
