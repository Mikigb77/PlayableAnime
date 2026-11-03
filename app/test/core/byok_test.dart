import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/byok_store.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/core/session/session_controller.dart';

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('each account on the device has its own key, and signed out there is none', () async {
    const ren = ByokStore('user_ren');
    await ren.saveGeminiKey('AIza-ren');
    expect(await ren.readGeminiKey(), 'AIza-ren');
    expect(await const ByokStore('user_mei').readGeminiKey(), isNull);
    expect(await const ByokStore(null).readGeminiKey(), isNull);
    await ren.clearGeminiKey();
    expect(await ren.readGeminiKey(), isNull);
  });

  test('the key follows whoever is signed in', () async {
    final backend = FakeBackend.standard(pace: FakePace.instant);
    final container = ProviderContainer(
      overrides: [
        httpClientProvider.overrideWithValue(backend),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      ],
    );
    addTearDown(container.dispose);
    container.read(sessionProvider);
    await Future<void>.delayed(Duration.zero);

    final json =
        await container.read(authApiClientProvider).post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    await container.read(sessionProvider.notifier).signIn(json);
    await container.read(byokStoreProvider).saveGeminiKey('AIza-demo');
    expect(container.read(byokStoreProvider).userId, FakeAuthState.demoUserId);

    await container.read(sessionProvider.notifier).signOut();
    expect(container.read(byokStoreProvider).userId, isNull);
    expect(await container.read(byokStoreProvider).readGeminiKey(), isNull);
  });
}
