import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/core/session/session_controller.dart';

void main() {
  late FakeBackend backend;
  late MemorySessionStore store;
  late ProviderContainer container;

  ProviderContainer make() {
    final c = ProviderContainer(
      overrides: [
        httpClientProvider.overrideWithValue(backend),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(store),
      ],
    );
    addTearDown(c.dispose);
    return c;
  }

  Future<SessionState> restored(ProviderContainer c) async {
    c.read(sessionProvider);
    for (var i = 0; i < 10 && c.read(sessionProvider).status == SessionStatus.restoring; i++) {
      await Future<void>.delayed(Duration.zero);
    }
    return c.read(sessionProvider);
  }

  Future<JsonMap> login() async =>
      await container.read(apiClientProvider).post('/v1/auth/login', {
            'email': FakeAuthState.demoEmail,
            'password': FakeAuthState.demoPassword,
          }, authenticated: false)
          as JsonMap;

  setUp(() {
    backend = FakeBackend.standard(pace: FakePace.instant);
    store = MemorySessionStore();
    container = make();
  });

  test('starts signed out with nothing stored', () async {
    expect((await restored(container)).status, SessionStatus.signedOut);
  });

  test('signs in, stores the session and restores it next launch', () async {
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    final state = container.read(sessionProvider);
    expect(state.status, SessionStatus.signedIn);
    expect(state.session!.displayName, 'Demo player');
    expect(store.value, isA<Session>());

    final next = make();
    final again = await restored(next);
    expect(again.status, SessionStatus.signedIn);
    expect(again.session!.accessToken, state.session!.accessToken);
  });

  test('a session never prints its tokens', () async {
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    final session = container.read(sessionProvider).session!;
    expect(session.toString(), isNot(contains(session.accessToken)));
    expect(session.toString(), isNot(contains(session.refreshToken)));
  });

  test('an expired access token is refreshed once for concurrent requests', () async {
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    final before = container.read(sessionProvider).session!;
    backend.data.auth.expireAccessTokens();

    final api = container.read(apiClientProvider);
    await Future.wait([api.get('/v1/stories'), api.get('/v1/me'), api.get('/v1/premises')]);
    final after = container.read(sessionProvider).session!;
    expect(after.accessToken, isNot(before.accessToken));
    expect(after.refreshToken, isNot(before.refreshToken));
    final refreshes = backend.requests.where((r) => r.uri.path == '/v1/auth/refresh');
    expect(refreshes, hasLength(1));
    expect(store.value!.accessToken, after.accessToken);
  });

  test('a refresh the server refuses signs the player out', () async {
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    final session = container.read(sessionProvider).session!;
    // Another device used the refresh token first.
    await container.read(apiClientProvider).post('/v1/auth/refresh', {
      'refresh_token': session.refreshToken,
    }, authenticated: false);
    backend.data.auth.expireAccessTokens();

    await expectLater(
      container.read(apiClientProvider).get('/v1/stories'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthenticated)),
    );
    expect(container.read(sessionProvider).status, SessionStatus.signedOut);
    expect(store.value, isNull);
  });

  test('signing out revokes the refresh token and forgets the session', () async {
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    final session = container.read(sessionProvider).session!;
    await container.read(sessionProvider.notifier).signOut();
    expect(container.read(sessionProvider).status, SessionStatus.signedOut);
    expect(store.value, isNull);
    await expectLater(
      container.read(apiClientProvider).post('/v1/auth/refresh', {
        'refresh_token': session.refreshToken,
      }, authenticated: false),
      throwsA(isA<ApiException>()),
    );
  });

  test('a server failure during a refresh keeps the session', () async {
    container = ProviderContainer(
      overrides: [
        httpClientProvider.overrideWithValue(
          MockClient((request) async {
            if (request.url.path == '/v1/auth/refresh') {
              return http.Response(
                jsonEncode({
                  'error': {'code': 'internal_error', 'message': 'Database hiccup'},
                }),
                500,
              );
            }
            return http.Response.fromStream(await backend.send(request));
          }),
        ),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(store),
      ],
    );
    addTearDown(container.dispose);
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    backend.data.auth.expireAccessTokens();

    await expectLater(
      container.read(apiClientProvider).get('/v1/stories'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.internalError)),
    );
    expect(container.read(sessionProvider).status, SessionStatus.signedIn);
    expect(store.value, isNotNull);
  });

  test('a refresh that cannot be saved still uses the new tokens', () async {
    final broken = _BrokenStore();
    store = broken;
    container = make();
    await restored(container);
    await container.read(sessionProvider.notifier).signIn(await login());
    broken.failWrites = true;
    final api = container.read(apiClientProvider);

    // Two refreshes in a row: the second only works with the token the first one got.
    backend.data.auth.expireAccessTokens();
    await api.get('/v1/stories');
    backend.data.auth.expireAccessTokens();
    await api.get('/v1/stories');

    expect(container.read(sessionProvider).status, SessionStatus.signedIn);
    // The stored session would hold a spent refresh token, so it is dropped.
    expect(broken.value, isNull);
  });

  test('a session expires when the API says, and survives storage', () {
    final now = DateTime.utc(2026, 11, 3, 12);
    final session = Session.fromApi(const {
      'access_token': 'a',
      'refresh_token': 'r',
      'expires_in': 900,
      'user': {'display_name': 'Ren'},
    }, now: now);
    expect(session.expiresAt, now.add(const Duration(minutes: 15)));
    final back = Session.fromStorage(session.toStorage());
    expect(back.expiresAt, session.expiresAt);
    expect(back.displayName, 'Ren');
  });
}

class _BrokenStore extends MemorySessionStore {
  bool failWrites = false;

  @override
  Future<void> write(Session session) async {
    if (failWrites) throw Exception('The keychain is locked');
    await super.write(session);
  }
}
