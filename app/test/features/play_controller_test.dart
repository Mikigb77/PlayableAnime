import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/turn_events.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/story/play_controller.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

import '../helpers.dart';

const _demo = 'story_ninth_peak';

/// A repository whose next turns can be scripted, and otherwise plays on the fake backend.
class _Scripted extends StoryRepository {
  _Scripted(super.api);

  final script = <Stream<TurnEvent>>[];

  /// The next Illustrate fails with this, once.
  ApiException? illustrateError;

  @override
  Future<Stream<TurnEvent>> takeTurn(String id, TurnInput input, {required int expectedVersion}) {
    if (script.isNotEmpty) return Future.value(script.removeAt(0));
    return super.takeTurn(id, input, expectedVersion: expectedVersion);
  }

  @override
  Future<SceneImage> illustrate(String id, int turn, {String kind = 'scene'}) {
    if (illustrateError case final error?) {
      illustrateError = null;
      throw error;
    }
    return super.illustrate(id, turn, kind: kind);
  }
}

/// The player's own key, once they add one (S9).
class _Keys implements ByokSource {
  String? key;

  @override
  Future<String?> readGeminiKey() async => key;
}

/// The play controller on the fake backend: every turn, error and picture as the app sees them.
void main() {
  late FakeBackend backend;
  late ApiClient api;
  late _Scripted repository;
  late _Keys keys;
  late DateTime now;

  setUp(() async {
    now = DateTime.utc(2026, 11, 3, 12);
    backend = FakeBackend.standard(pace: FakePace.instant, clock: () => now);
    final tokens = TestTokens();
    keys = _Keys();
    api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend, tokens: tokens, byok: keys);
    final session =
        await api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    tokens.accessToken = session['access_token'] as String;
    repository = _Scripted(api);
  });

  /// A controller, with every notice it sends and every streamed text it held.
  ({PlayController play, List<PlayNotice> notices, List<String> texts}) control({
    String id = _demo,
    int pageSize = 20,
  }) {
    final play = PlayController(
      repository: repository,
      storyId: id,
      clock: () => now,
      pageSize: pageSize,
      pictureInterval: const Duration(milliseconds: 5),
    );
    final notices = <PlayNotice>[];
    final texts = <String>[];
    final sub = play.notices.listen(notices.add);
    play.addListener(() {
      if (play.pending case final pending?) texts.add(pending.text);
    });
    addTearDown(() async {
      await sub.cancel();
      play.dispose();
    });
    return (play: play, notices: notices, texts: texts);
  }

  Future<void> until(ChangeNotifier notifier, bool Function() done) async {
    if (done()) return;
    final reached = Completer<void>();
    void check() {
      if (done() && !reached.isCompleted) reached.complete();
    }

    notifier.addListener(check);
    try {
      await reached.future.timeout(const Duration(seconds: 5));
    } finally {
      notifier.removeListener(check);
    }
  }

  Iterable<FakeRequest> turnRequests() =>
      backend.requests.where((r) => r.method == 'POST' && r.uri.path.endsWith('/turns'));

  group('loading', () {
    test('opens at the newest scenes and paints a picture still planned', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      expect(play.story!.scenes.map((s) => s.turn), [1, 2, 3]);
      expect(play.reachedStart, isTrue);
      expect(play.canAct, isTrue);

      // Turn 3's picture was planned when the story was closed: it is asked for again.
      await until(play, () => play.story!.scenes.last.image?.isReady ?? false);
      final picture = play.imageOf(play.story!.scenes.last)!;
      expect(picture.url, startsWith('asset:'));
      expect(picture.imageId, isNotNull);
    });

    test('older scenes load above the first page without a gap', () async {
      final (:play, notices: _, texts: _) = control(pageSize: 2);
      await play.start();
      expect(play.story!.scenes.map((s) => s.turn), [2, 3]);
      expect(play.anchorTurn, 2);
      expect(play.reachedStart, isFalse);

      await play.loadOlder();
      expect(play.story!.scenes.map((s) => s.turn), [1, 2, 3]);
      expect(play.reachedStart, isTrue);
      // The anchor stays, so the page doesn't move.
      expect(play.anchorTurn, 2);
    });

    test('a story that can\'t load says why', () async {
      final (:play, notices: _, texts: _) = control(id: 'story_nope');
      await play.start();
      expect(play.story, isNull);
      expect(
        play.loadError,
        isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.notFound),
      );
    });

    test('a story started from a draft plays its opening at once', () async {
      final draft =
          await api.post('/v1/drafts', {
                'premise': 'A lighthouse keeper finds a door in the sea.',
                'rating': 'teen',
              })
              as JsonMap;
      final started = await api.post('/v1/drafts/${draft['id']}/start', {}) as JsonMap;
      final (:play, :notices, :texts) = control(id: started['story_id'] as String);
      await play.start();
      expect(play.pending?.isOpening, isTrue);

      await until(play, () => play.story!.scenes.isNotEmpty && play.pending == null);
      final opening = play.story!.scenes.single;
      expect(opening.turn, 1);
      expect(opening.kind, 'opening');
      expect(opening.playerAction, isNull);
      expect(opening.choices, isNotEmpty);
      expect(texts.last, isNotEmpty);
      expect(notices.whereType<SceneSaved>().single.turn, 1);
      final sent = turnRequests().single.json;
      expect(sent['kind'], 'opening');
      expect(sent.containsKey('input_mode'), isFalse);
    });
  });

  group('turns', () {
    test('a turn streams, then the saved scene joins the feed', () async {
      final (:play, :notices, :texts) = control();
      await play.start();
      final started = await play.act('I wait by the window', inputMode: 'voice');
      expect(started, isTrue);
      expect(play.busy, isTrue);
      await until(play, () => play.pending == null);

      final scene = play.story!.scenes.last;
      expect(scene.turn, 4);
      expect(scene.playerAction, 'I wait by the window');
      expect(scene.spoken, isTrue);
      expect(play.story!.version, 4);
      expect(play.story!.clockLabel, isNotNull);
      // The words arrived a few at a time, and the full text is the saved narration.
      expect(texts.where((t) => t.isNotEmpty).length, greaterThan(3));
      expect(texts.last, scene.narration);
      expect(notices.whereType<SceneSaved>().single.turn, 4);
    });

    test('a reset clears the streamed words and the scene still lands', () async {
      final (:play, notices: _, :texts) = control();
      await play.start();
      await play.act('[reset] I look around', inputMode: 'typed');
      await until(play, () => play.pending == null);
      final cleared = texts.indexWhere((t) => t.isEmpty, texts.indexWhere((t) => t.isNotEmpty));
      expect(cleared, greaterThan(0));
      expect(play.story!.scenes.last.turn, 4);
    });

    test('a storyteller failure drops the partial scene, and a retry plays it', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      repository.script.add(
        Stream.fromIterable([
          const TurnStarted(4),
          const NarrationDelta('You reach for the '),
          const TurnFailed(ApiException(ApiErrorCode.llmUnavailable)),
        ]),
      );
      await play.act('I look around', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      expect(play.pending!.text, isEmpty);
      expect(play.pending!.error!.code, ApiErrorCode.llmUnavailable);
      expect(play.busy, isFalse);
      expect(play.story!.version, 3);

      expect(await play.retry(), isTrue);
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.playerAction, 'I look around');
      expect(turnRequests().single.json['action'], 'I look around');
    });

    test('an unreadable action fails without saving, for the player to say it again', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('[fail:unreadable_action] Hm', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      expect(play.pending!.error!.code, ApiErrorCode.unreadableAction);
      expect(play.pending!.input.action, '[fail:unreadable_action] Hm');

      play.dismissFailure();
      expect(play.pending, isNull);
      expect(play.story!.version, 3);
    });

    test('a content limit carries its category and the server\'s words', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('[fail:limit] Someone famous', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      final error = play.pending!.error!;
      expect(error.code, ApiErrorCode.unreadableAction);
      expect(error.details['category'], 'real_person');
      expect(error.message, contains('real, living people'));
    });

    test('out of credits opens the sheet and leaves the story as it was', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      expect(await play.act('[fail:out_of_credits] Go', inputMode: 'typed'), isFalse);
      expect(play.pending, isNull);
      expect(notices.whereType<OutOfCredits>().single.error.code, ApiErrorCode.outOfCredits);
    });

    test('a turn refused for credits plays on the player\'s own key once they add it', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act('[fail:out_of_credits] I climb the wall', inputMode: 'typed');
      final refused = notices.whereType<OutOfCredits>().single.turn!;
      expect(refused.input.action, '[fail:out_of_credits] I climb the wall');

      keys.key = 'AIza-test';
      expect(await play.again(refused), isTrue);
      await until(play, () => play.story!.scenes.length == 4);
      expect(play.story!.scenes.last.playerAction, '[fail:out_of_credits] I climb the wall');
      // On the player's key: no credits spent on the turn, and the balance shown elsewhere is
      // refreshed.
      expect(
        backend.data.account.ledgerOf(FakeAuthState.demoUserId).where((e) => e['kind'] == 'turn'),
        isEmpty,
      );
      expect(notices.whereType<CreditsSpent>(), isNotEmpty);
    });

    test('a rate limit fails the turn with the wait, for the retry to count down', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('[fail:rate_limited] Go', inputMode: 'typed');
      expect(play.pending!.failed, isTrue);
      expect(play.pending!.error!.retryAfter, const Duration(seconds: 20));
    });

    test('another device played first: the story is fetched again', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      // Another device plays turn 4.
      await collect(
        await StoryRepository(
          api,
        ).takeTurn(_demo, const TurnInput.standing('observe'), expectedVersion: 3),
      );

      expect(await play.act('I run', inputMode: 'typed'), isFalse);
      await until(play, () => play.story!.version == 4);
      expect(notices.whereType<StoryMovedOn>(), hasLength(1));
      expect(play.story!.scenes.last.playerAction, 'observe');
      expect(play.pending, isNull);
    });

    test(
      'a turn that loses the race mid-stream fetches the story and gives the words back',
      () async {
        final (:play, :notices, texts: _) = control();
        await play.start();
        await play.act('[fail:lost_race] I run', inputMode: 'typed');
        await until(play, () => notices.whereType<StoryMovedOn>().isNotEmpty);
        expect(play.pending, isNull);
        expect(notices.whereType<StoryMovedOn>().single.action, '[fail:lost_race] I run');
      },
    );

    test('a dropped connection while another device played is not taken for this turn', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      // Another device plays turn 4, then this one's stream drops before it hears back.
      await collect(
        await StoryRepository(
          api,
        ).takeTurn(_demo, const TurnInput.standing('observe'), expectedVersion: 3),
      );
      repository.script.add(
        Stream.fromIterable([
          const TurnStarted(4),
          const TurnFailed(ApiException(ApiErrorCode.network)),
        ]),
      );
      await play.act('I search the shelves', inputMode: 'typed');
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.playerAction, 'observe');
      expect(notices.whereType<SceneSaved>(), isEmpty);
      expect(notices.whereType<StoryMovedOn>().single.action, 'I search the shelves');
    });

    test('a saved scene that can\'t be read shows the story as the server has it', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      repository.script.add(
        Stream.fromIterable([
          const TurnStarted(4),
          const SceneCompleted(scene: {'turn': 'four'}, version: 4, clock: {}),
        ]),
      );
      final errors = <FlutterErrorDetails>[];
      final previous = FlutterError.onError;
      FlutterError.onError = errors.add;
      addTearDown(() => FlutterError.onError = previous);
      await play.act('I look', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      expect(errors, hasLength(1));
      expect(play.busy, isFalse);
    });

    test('a dropped connection finds the scene that was saved', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act('[fail:dropped] I look at the stars', inputMode: 'typed');
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.turn, 4);
      expect(play.story!.version, 4);
      expect(notices.whereType<SceneSaved>().single.turn, 4);
    });

    test('a connection that drops before saving offers a retry', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      repository.script.add(
        Stream.fromIterable([
          const TurnStarted(4),
          const NarrationDelta('The '),
          const TurnFailed(ApiException(ApiErrorCode.network)),
        ]),
      );
      await play.act('I look', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      expect(play.pending!.error!.code, ApiErrorCode.network);
      expect(play.story!.scenes.last.turn, 3);
    });

    test('a choice no longer offered shows the story as it is now', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.choose(const Choice(id: 'gone', label: 'Gone'));
      expect(notices.whereType<TurnRefused>(), hasLength(1));
      expect(play.pending, isNull);
    });

    test('only one turn runs at a time', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      final first = play.act('I look', inputMode: 'typed');
      expect(await play.stand('wait', label: 'Wait'), isFalse);
      expect(await first, isTrue);
      await until(play, () => play.pending == null);
      expect(turnRequests(), hasLength(1));
    });

    test('leaving mid-turn stops listening without errors', () async {
      final play = PlayController(repository: repository, storyId: _demo);
      await play.start();
      unawaited(play.act('I look', inputMode: 'typed'));
      play.dispose();
      await pumpEventQueue();
    });
  });

  group('pictures', () {
    test(
      'a fight is painted after the text; a skipped picture leaves the scene without one',
      () async {
        final (:play, notices: _, texts: _) = control();
        await play.start();
        await play.act('I draw my blade and attack', inputMode: 'typed');
        await until(play, () => play.story!.scenes.length == 4);
        await until(play, () => play.story!.scenes.last.image?.isReady ?? false);

        await play.act('[fail:picture] I look at the sky', inputMode: 'typed');
        await until(play, () => play.story!.scenes.length == 5);
        await until(play, () => play.story!.scenes.last.image?.isSkipped ?? false);
      },
    );

    test('illustrating paints a picture for a scene without one', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('[fail:picture] I look at the sky', inputMode: 'typed');
      await until(play, () => play.story!.scenes.last.image?.isSkipped ?? false);

      await play.illustrate(4);
      final image = play.story!.scenes.last.image!;
      expect(image.isReady, isTrue);
      expect(
        backend.requests.where((r) => r.uri.path.endsWith('/scenes/4/illustrate')),
        isNotEmpty,
      );
    });

    test(
      'an Illustrate refused for credits leaves the scene as it was and opens the sheet',
      () async {
        final (:play, :notices, texts: _) = control();
        await play.start();
        await play.act('[fail:picture] I look at the sky', inputMode: 'typed');
        await until(play, () => play.story!.scenes.last.image?.isSkipped ?? false);

        repository.illustrateError = const ApiException(ApiErrorCode.outOfCredits, status: 402);
        await play.illustrate(4);
        expect(play.story!.scenes.last.image!.isSkipped, isTrue);
        expect(notices.whereType<OutOfCredits>().single.picture, 4);

        // With the player's own key it goes again.
        keys.key = 'AIza-test';
        await play.illustrate(4);
        expect(play.story!.scenes.last.image!.isReady, isTrue);
        expect(notices.whereType<CreditsSpent>(), isNotEmpty);
      },
    );

    test('a picture that fails to load gets a fresh URL by its id, once in a while', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      final opening = play.story!.scenes.first;
      expect(opening.image!.isReady, isTrue);

      // The server signs a new URL.
      final seeded = backend.data.stories.get(_demo, FakeAuthState.demoUserId).scenes.first;
      (seeded['image'] as JsonMap)['url'] = 'asset:assets/fake/scene-castle.jpg';
      await play.pictureFailed(1);
      final fresh = play.imageOf(play.story!.scenes.first)!;
      expect(fresh.expiresAt, isNotNull);
      expect(
        backend.requests.where((r) => r.uri.path.endsWith('/images/img_story_ninth_peak_1')),
        hasLength(1),
      );

      expect(fresh.url, 'asset:assets/fake/scene-castle.jpg');

      // Failing again right away gives up on it.
      await play.pictureFailed(1);
      expect(play.imageOf(play.story!.scenes.first)!.isSkipped, isTrue);
    });

    test('a refresh that brings back the same URL gives up at once', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.pictureFailed(1);
      expect(play.imageOf(play.story!.scenes.first)!.isSkipped, isTrue);
    });
  });

  group('reports and settings', () {
    test('a blocked report hides the scene for good', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      final scene = play.story!.scenes.last;
      await play.report(scene.turn, category: 'other', note: 'Too grim', block: true);
      expect(play.isBlocked(scene), isTrue);
      expect(backend.data.reports.single, containsPair('block', true));

      final again = control();
      await again.play.start();
      expect(again.play.story!.scenes.last.blocked, isTrue);
    });

    test('a report without a block leaves the scene', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.report(2, category: 'hate', block: false);
      expect(play.isBlocked(play.story!.scenes[1]), isFalse);
    });

    test('settings apply from the next scene and keep the version', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      final base = play.story!.settings;
      await play.save(
        title: 'The Tenth Peak',
        settings: base.copyWith(narrationLength: 'short', tone: 'Wry').changesFrom(base),
      );
      final patch = backend.requests.lastWhere((r) => r.method == 'PATCH');
      expect(patch.json['settings'], {'narration_length': 'short', 'tone': 'Wry'});
      expect(play.story!.title, 'The Tenth Peak');
      expect(play.story!.settings.narrationLength, 'short');
      expect(play.story!.settings.tone, 'Wry');
      expect(play.story!.version, 3);

      await play.act('I look around', inputMode: 'typed');
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.narration, isNot(contains('\n\n')));

      final now = play.story!.settings;
      await play.save(settings: now.copyWith(tone: '').changesFrom(now));
      expect(play.story!.settings.tone, isNull);
    });

    test('a title the server refuses is an error for the sheet', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await expectLater(
        play.save(title: 'x' * 121),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );
    });
  });
}
