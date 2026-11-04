import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/turn_events.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/discover/premises.dart';
import 'package:playable_anime/features/library/library.dart';
import 'package:playable_anime/features/story/memory.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

import '../helpers.dart';

/// The fake backend speaks docs/API.md, so the app's flows run end to end without a server.
void main() {
  late ApiClient api;
  late FakeBackend backend;
  late TestTokens tokens;
  late StoryRepository stories;
  late LibraryRepository library;

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
    library = LibraryRepository(api);
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
      final premises = [
        for (final p in await api.get('/v1/premises') as List) Premise.fromJson(p as JsonMap),
      ];
      expect(premises, hasLength(11));
      expect(premises.take(4).every((p) => p.flagship), isTrue);
      expect(premises.first.coverUrl, startsWith('asset:'));
    });

    test('the demo account starts with a story in progress', () async {
      final list = await library.stories();
      final story = await stories.get(list.single.id);
      expect(story.scenes, hasLength(story.scenes.last.turn));
      expect(story.scenes.last.choices, isNotEmpty);
      final memory = MemoryView.fromJson(
        await api.get('/v1/stories/${story.id}/memory') as JsonMap,
      );
      expect(memory.sections, isNotEmpty);
    });

    test('a turn streams words, then saves the scene and charges for it', () async {
      final story = await stories.get((await library.stories()).single.id);
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
      final story = await stories.get((await library.stories()).single.id);
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
      final story = await stories.get((await library.stories()).single.id);
      await expectLater(
        stories.takeTurn(story.id, const TurnInput.choice('nope'), expectedVersion: story.version),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );
    });

    test('out of credits stops the turn before it starts', () async {
      final story = await stories.get((await library.stories()).single.id);
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
      final story = await stories.get((await library.stories()).single.id);
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

    test('the interpret step\'s errors arrive in the stream, and save nothing', () async {
      final story = await stories.get((await library.stories()).single.id);
      Future<TurnFailed> fail(String action) async {
        final events = await collect(
          await stories.takeTurn(
            story.id,
            TurnInput.action(action, inputMode: 'typed'),
            expectedVersion: story.version,
          ),
        );
        expect(events.first, isA<TurnStarted>());
        return events.last as TurnFailed;
      }

      expect((await fail('[fail:unreadable_action] Hm')).error.code, ApiErrorCode.unreadableAction);
      expect((await fail('[fail:bad_key] Go')).error.code, ApiErrorCode.badKey);
      final limit = (await fail('[fail:limit] Someone famous')).error;
      expect(limit.code, ApiErrorCode.unreadableAction);
      expect(limit.details['category'], 'real_person');
      final race = (await fail('[fail:lost_race] Go')).error;
      expect(race.code, ApiErrorCode.versionConflict);
      expect(race.currentVersion, story.version);
      expect((await stories.get(story.id)).version, story.version);
    });

    test('a dropped connection after saving ends the stream as a network error', () async {
      final story = await stories.get((await library.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:dropped] I look', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      expect(events.whereType<SceneCompleted>(), isEmpty);
      expect((events.last as TurnFailed).error.code, ApiErrorCode.network);
      expect((await stories.get(story.id)).version, story.version + 1);
    });

    test('each turn kind takes only its own field, and the opening comes first, once', () async {
      final story = await stories.get((await library.stories()).single.id);
      Future<void> refused(Map<String, Object?> body) => expectLater(
        api.turn(story.id, {...body, 'expected_version': story.version}),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );

      await refused({'kind': 'opening'});
      await refused({'kind': 'action', 'action': 'Go', 'choice_id': 'c1'});
      await refused({'kind': 'action', 'action': 'Go', 'input_mode': 'choice'});
      await refused({'kind': 'action', 'action': ''});
      await refused({'kind': 'standing', 'standing': 'dance'});
      await refused({'kind': 'teleport'});
    });

    test('settings change without moving the version, and the server checks them', () async {
      final story = await stories.get((await library.stories()).single.id);
      final saved = await stories.update(
        story.id,
        title: '  The Tenth Peak ',
        settings: story.settings
            .copyWith(difficulty: 'brutal', tone: 'Wry and quiet')
            .changesFrom(story.settings),
      );
      expect(saved.title, 'The Tenth Peak');
      expect(saved.settings.difficulty, 'brutal');
      expect(saved.settings.tone, 'Wry and quiet');
      expect(saved.version, story.version);

      final cleared = await stories.update(
        story.id,
        settings: saved.settings.copyWith(tone: '').changesFrom(saved.settings),
      );
      // Only the tone was sent, so the rest stays as it was.
      expect(cleared.settings.difficulty, 'brutal');
      expect(cleared.settings.tone, isNull);

      for (final body in [
        {'title': ''},
        {'title': 'x' * 121},
        {
          'settings': {'difficulty': 'nightmare'},
        },
        {
          'settings': {'tone': 'x' * 201},
        },
      ]) {
        await expectLater(
          api.patch('/v1/stories/${story.id}', body),
          throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
        );
      }
    });

    test('a report with a block hides the scene from then on', () async {
      final story = await stories.get((await library.stories()).single.id);
      await stories.report(story.id, 2, category: 'other', note: 'Not for me', block: false);
      await stories.report(story.id, 3, category: 'hate', block: true);
      final again = await stories.get(story.id);
      expect(again.scenes.map((s) => s.blocked), [false, false, true]);
      expect(backend.data.reports.map((r) => r['block']), [false, true]);

      // Reporting again updates the one report, and the block stays.
      await stories.report(story.id, 3, category: 'other', block: false);
      expect(backend.data.reports, hasLength(2));
      expect(backend.data.reports.last, containsPair('category', 'other'));
      expect((await stories.get(story.id)).scenes.last.blocked, isTrue);
      await expectLater(
        stories.report(story.id, 3, category: 'boring', block: false),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );
    });

    test('scrollback pages older scenes, oldest first', () async {
      final story = await stories.get((await library.stories()).single.id, scenes: 1);
      expect(story.scenes.single.turn, 3);
      final older = await stories.olderScenes(story.id, before: 3, limit: 1);
      expect(older.single.turn, 2);
      final rest = await stories.olderScenes(story.id, before: 3);
      expect(rest.map((s) => s.turn), [1, 2]);
    });

    test('a reset clears the words and the scene still completes', () async {
      final story = await stories.get((await library.stories()).single.id);
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
      library = LibraryRepository(own);
      await signIn();
      final story = await stories.get((await library.stories()).single.id);
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
      library = LibraryRepository(api);
      await signIn();
    });

    test('a fight plans a picture that is painted after the text and charged once', () async {
      final story = await stories.get((await library.stories()).single.id);
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

    test('meeting Senior Sister Lan plans her portrait, once', () async {
      final story = await stories.get((await library.stories()).single.id);
      Future<Scene> wait(int version) async {
        final events = await collect(
          await stories.takeTurn(
            story.id,
            const TurnInput.standing('wait'),
            expectedVersion: version,
          ),
        );
        return Scene.fromJson((events.last as SceneCompleted).scene);
      }

      final met = await wait(story.version);
      expect(met.turn, 4);
      expect(met.portraits.map((p) => p.characterId), contains('lan'));
      expect(met.image?.kind, 'portrait');
      now = now.add(const Duration(seconds: 4));
      await stories.picture(story.id, 4, kind: 'portrait');
      now = now.add(const Duration(seconds: 4));
      final portrait = await stories.picture(story.id, 4, kind: 'portrait');
      expect(portrait.status, 'ready');
      expect(portrait.kind, 'portrait');

      // Turn 5: no fight, not a third turn and Lan already met, so no picture is planned.
      final quiet = await wait(story.version + 1);
      expect(quiet.image, isNull);
      expect((await stories.picture(story.id, quiet.turn)).status, 'skipped');
    });

    test('illustrating plans a picture, also for a scene whose picture was skipped', () async {
      final story = await stories.get((await library.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:picture] I look at the sky', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      final turn = Scene.fromJson((events.last as SceneCompleted).scene).turn;
      expect((await stories.picture(story.id, turn)).status, 'skipped');

      expect((await stories.illustrate(story.id, turn)).status, 'planned');
      now = now.add(const Duration(seconds: 4));
      final ready = await stories.illustrate(story.id, turn);
      expect(ready.status, 'ready');

      // A fresh URL by the picture's id lasts a while, and never draws.
      backend.data.pictures.ttl = const Duration(minutes: 10);
      final fresh = await stories.refreshPicture(story.id, ready.imageId!);
      expect(fresh.url, ready.url);
      expect(fresh.expiresAt, now.add(const Duration(minutes: 10)));
    });

    test('illustrating on credits that cannot pay for it is a 402 that changes nothing', () async {
      final story = await stories.get((await library.stories()).single.id);
      final turn = story.scenes.last.turn;
      final before = story.scenes.last.image?.status;
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'adjustment',
        cents: await balance(),
        now: now,
      );

      await expectLater(
        stories.illustrate(story.id, turn),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.outOfCredits)
              .having((e) => e.balanceCents, 'balance', 0),
        ),
      );
      expect((await stories.get(story.id)).scenes.last.image?.status, before);
    });

    test('[fail:picture] plans a picture that is then skipped, free of charge', () async {
      final story = await stories.get((await library.stories()).single.id);
      final events = await collect(
        await stories.takeTurn(
          story.id,
          const TurnInput.action('[fail:picture] I look at the sky', inputMode: 'typed'),
          expectedVersion: story.version,
        ),
      );
      final scene = Scene.fromJson((events.last as SceneCompleted).scene);
      expect(scene.playerAction, '[fail:picture] I look at the sky');
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
    expect((await library.stories()).map((s) => s.id), contains(id));
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
