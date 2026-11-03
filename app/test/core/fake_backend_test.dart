import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/turn_events.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

import '../helpers.dart';

/// The fake backend speaks docs/API.md, so the app's flows run end to end without a server.
void main() {
  late ApiClient api;
  late FakeBackend backend;
  late TestTokens tokens;
  late StoryRepository stories;

  Future<JsonMap> signIn() async {
    final session =
        await api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    tokens
      ..accessToken = session['access_token'] as String
      ..refreshToken = session['refresh_token'] as String;
    return session;
  }

  Future<num> balance() async =>
      (await api.get('/v1/me/credits') as JsonMap)['balance_cents'] as num;

  setUp(() {
    final fake = fakeApi();
    api = fake.api;
    backend = fake.backend;
    tokens = fake.tokens;
    stories = StoryRepository(api);
  });

  group('auth', () {
    test('signs in the demo account and reads it back', () async {
      final session = await signIn();
      expect((session['user'] as JsonMap)['email'], FakeAuthState.demoEmail);
      final me = await api.get('/v1/me') as JsonMap;
      expect(me['id'], FakeAuthState.demoUserId);
    });

    test('a wrong password is unauthenticated', () async {
      await expectLater(
        api.post('/v1/auth/login', {
          'email': FakeAuthState.demoEmail,
          'password': 'nope',
        }, authenticated: false),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthenticated)),
      );
    });

    test('a private route without a token is refused', () async {
      await expectLater(
        api.get('/v1/stories'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthenticated)),
      );
    });

    test('an expired token is refreshed once, and the refresh token rotates', () async {
      await signIn();
      final oldRefresh = tokens.refreshToken!;
      tokens.onRefresh = () async {
        final next =
            await api.post('/v1/auth/refresh', {
                  'refresh_token': tokens.refreshToken,
                }, authenticated: false)
                as JsonMap;
        tokens
          ..accessToken = next['access_token'] as String
          ..refreshToken = next['refresh_token'] as String;
        return true;
      };
      backend.data.auth.expireAccessTokens();
      expect(await api.get('/v1/stories'), isA<List<Object?>>());
      expect(tokens.refreshToken, isNot(oldRefresh));

      // The old refresh token no longer works.
      await expectLater(
        api.post('/v1/auth/refresh', {'refresh_token': oldRefresh}, authenticated: false),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthenticated)),
      );
    });
  });

  group('stories', () {
    setUp(signIn);

    test('lists premises with the flagship worlds first', () async {
      final premises = await stories.premises();
      expect(premises, hasLength(greaterThanOrEqualTo(4)));
      expect(premises.take(4).every((p) => p.flagship), isTrue);
      expect(premises.first.coverUrl, startsWith('asset:'));
    });

    test('the demo account starts with a story in progress', () async {
      final list = await stories.stories();
      final story = await stories.get(list.single.id);
      expect(story.scenes, hasLength(story.scenes.last.turn));
      expect(story.scenes.last.choices, isNotEmpty);
      final memory = await stories.memory(story.id);
      expect(memory.sections, isNotEmpty);
    });

    test('a turn streams words, then saves the scene and charges for it', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final before = await balance();
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('I wait by the window', inputMode: 'voice'),
          expectedVersion: story.version,
        ),
      );
      expect(events.first, isA<TurnStarted>());
      final words = events.whereType<NarrationDelta>().map((e) => e.text).join();
      final done = events.last as SceneCompleted;
      expect(done.version, story.version + 1);
      final scene = Scene.fromJson(done.scene);
      expect(words, scene.narration);
      expect(scene.playerAction, 'I wait by the window');
      expect(scene.spoken, isTrue);
      expect(scene.durationLabel, isNotNull);
      expect(await balance(), before - 2);

      final saved = await stories.get(story.id);
      expect(saved.version, story.version + 1);
      expect(saved.scenes.last.turn, scene.turn);
    });

    test('a stale version is a conflict that names the current one', () async {
      final story = await stories.get((await stories.stories()).single.id);
      await expectLater(
        stories.takeTurn(story.id, const TurnInput.standing('wait'), expectedVersion: 0),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.versionConflict)
              .having((e) => e.currentVersion, 'current', story.version),
        ),
      );
    });

    test('a choice that is not offered is a validation error', () async {
      final story = await stories.get((await stories.stories()).single.id);
      await expectLater(
        stories.takeTurn(story.id, const TurnInput.choice('nope'), expectedVersion: story.version),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );
    });

    test('out of credits stops the turn before it starts', () async {
      final story = await stories.get((await stories.stories()).single.id);
      await expectLater(
        stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:out_of_credits] Go', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.outOfCredits)
              .having((e) => e.balanceCents, 'balance', isNotNull),
        ),
      );
    });

    test('a storyteller failure mid-stream saves nothing', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:llm_unavailable] Go', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      expect(events.whereType<NarrationDelta>(), isNotEmpty);
      final failed = events.last as TurnFailed;
      expect(failed.error.code, ApiErrorCode.llmUnavailable);
      expect((await stories.get(story.id)).version, story.version);
    });

    test('a reset clears the words and the scene still completes', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[reset] Go', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      expect(events.whereType<NarrationReset>(), hasLength(1));
      expect(events.last, isA<SceneCompleted>());
    });

    test('your own key is sent with turns and spends no credits', () async {
      final fake = fakeApi();
      final own = ApiClient(
        baseUrl: FakeBackend.baseUrl,
        httpClient: fake.backend,
        tokens: tokens,
        byok: _Key('AIza-test'),
      );
      backend = fake.backend;
      api = own;
      stories = StoryRepository(own);
      await signIn();
      final story = await stories.get((await stories.stories()).single.id);
      final before = await balance();
      await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.standing('observe'),
          expectedVersion: story.version,
        ),
      );
      expect(await balance(), before);
      final turn = backend.requests.lastWhere((r) => r.uri.path.endsWith('/turns'));
      expect(turn.usesOwnKey, isTrue);
      final read = backend.requests.lastWhere((r) => r.method == 'GET');
      expect(read.usesOwnKey, isFalse);
    });
  });

  group('pictures', () {
    late DateTime now;

    setUp(() async {
      now = DateTime.utc(2026, 11, 3, 12);
      backend = FakeBackend.standard(
        pace: const FakePace(
          latency: Duration.zero,
          firstWords: Duration.zero,
          perChunk: Duration.zero,
          picture: Duration(seconds: 3),
        ),
        clock: () => now,
      );
      tokens = TestTokens();
      api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend, tokens: tokens);
      stories = StoryRepository(api);
      await signIn();
    });

    test('a fight plans a picture that is painted after the text and charged once', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('I draw my blade and attack', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      final scene = Scene.fromJson((events.last as SceneCompleted).scene);
      expect(scene.image?.status, 'planned');

      final afterTurn = await balance();
      expect((await stories.picture(story.id, scene.turn)).status, 'planned');
      now = now.add(const Duration(seconds: 4));
      final ready = await stories.picture(story.id, scene.turn);
      expect(ready.status, 'ready');
      expect(ready.url, startsWith('asset:'));
      expect(ready.imageId, isNotNull);
      final again = await api.get('/v1/stories/${story.id}/images/${ready.imageId}') as JsonMap;
      expect(again['url'], ready.url);
      expect(await balance(), closeTo(afterTurn - 3.4, 0.001));

      // Asking again is free.
      await stories.picture(story.id, scene.turn);
      expect(await balance(), closeTo(afterTurn - 3.4, 0.001));
    });

    test('a scene without a planned picture is skipped', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.standing('wait'),
          expectedVersion: story.version,
        ),
      );
      // Turn 4 of the demo story: no fight and not a third turn, so no picture is planned.
      final scene = Scene.fromJson((events.last as SceneCompleted).scene);
      expect(scene.turn, 4);
      expect(scene.image, isNull);
      expect((await stories.picture(story.id, scene.turn)).status, 'skipped');
    });

    test('[fail:picture] plans a picture that is then skipped, free of charge', () async {
      final story = await stories.get((await stories.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:picture] I look at the sky', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      final scene = Scene.fromJson((events.last as SceneCompleted).scene);
      expect(scene.playerAction, 'I look at the sky');
      expect(scene.image?.status, 'planned');

      final afterTurn = await balance();
      now = now.add(const Duration(seconds: 4));
      expect((await stories.picture(story.id, scene.turn)).status, 'skipped');
      expect(await balance(), afterTurn);
    });
  });

  test('a draft starts a story that opens with its first scene', () async {
    await signIn();
    final draft =
        await api.post('/v1/drafts', {
              'premise': 'A lighthouse keeper finds a door in the sea.',
              'rating': 'teen',
            })
            as JsonMap;
    expect(draft['world_lines'], isNotEmpty);
    expect(draft['version'], 1);
    final path = '/v1/drafts/${draft['id']}';
    final edited =
        await api.patch(path, {
              'advanced': {'difficulty': 'brutal'},
              'expected_version': 1,
            })
            as JsonMap;
    expect(edited['version'], 2);
    await expectLater(
      api.post('$path/revise', {
        'target': 'world',
        'instruction': 'Add hidden vampires',
        'expected_version': 1,
      }),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.versionConflict)),
    );

    final started =
        await api.post('$path/start', {
              'settings': {'pictures': 'key_scenes'},
            })
            as JsonMap;
    final id = started['story_id'] as String;
    expect(started['version'], 1);
    // Starting again returns the same story, and a started draft can't change.
    expect((await api.post('$path/start', {}) as JsonMap)['story_id'], id);
    await expectLater(
      api.patch(path, {'rating': 'mature'}),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.forbidden)),
    );
    final fresh = await stories.get(id);
    expect(fresh.scenes, isEmpty);

    final opening = await api.turn(id, {'kind': 'opening', 'expected_version': fresh.version});
    final events = await collect(opening);
    final scene = Scene.fromJson((events.last as SceneCompleted).scene);
    expect(scene.turn, 1);
    expect(scene.choices, isNotEmpty);
    expect((await stories.stories()).map((s) => s.id), contains(id));
  });

  test('an unknown route is not found', () async {
    await signIn();
    await expectLater(
      api.get('/v1/nothing'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.notFound)),
    );
  });
}

class _Key implements ByokSource {
  _Key(this.key);

  final String key;

  @override
  Future<String?> readGeminiKey() async => key;
}
