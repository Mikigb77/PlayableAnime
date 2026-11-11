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

  /// The next turn is refused with this before its stream starts, once.
  ApiException? turnError;

  /// The next Illustrate fails with this, once.
  ApiException? illustrateError;

  /// The next fetch of the story reads it, then waits for this before answering, once.
  Completer<void>? getGate;

  @override
  Future<Story> get(String id, {int scenes = 20}) async {
    final story = await super.get(id, scenes: scenes);
    if (getGate case final gate?) {
      getGate = null;
      await gate.future;
    }
    return story;
  }

  @override
  Future<Stream<TurnEvent>> takeTurn(String id, TurnInput input, {required int expectedVersion}) {
    if (turnError case final error?) {
      turnError = null;
      return Future.error(error);
    }
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

  test('a copy fetched before a save never takes back the color it saved (S13)', () async {
    final (:play, notices: _, texts: _) = control();
    await play.start();
    final gate = Completer<void>();
    repository.getGate = gate;
    final reload = play.reload();
    await pumpEventQueue();

    await play.save(title: 'Rose Peak', settings: {'accent': 'rose'});
    expect(play.story!.settings.accent, 'rose');
    gate.complete();
    await reload;
    // The copy was read before the save: what the save wrote stands.
    expect(play.story!.settings.accent, 'rose');
    expect(play.story!.title, 'Rose Peak');

    // A copy fetched after it takes what the server says, such as another device's change.
    await api.patch('/v1/stories/$_demo', {
      'settings': {'accent': 'lime'},
    });
    await play.reload();
    expect(play.story!.settings.accent, 'lime');
  });

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

  group('a turn the story owes (A3)', () {
    const leap = '[fail:lost] I leap across the gap';

    /// Another device, or an earlier visit, starts a turn that is lost after its dice.
    Future<void> loseElsewhere({String words = leap}) async {
      final other = StoryRepository(api);
      final story = await other.get(_demo);
      final events = await other.takeTurn(
        _demo,
        TurnInput.action(words, inputMode: 'typed'),
        expectedVersion: story.version,
      );
      await events.drain<void>().catchError((Object _) {});
    }

    test(
      'the heading of a scene that days passed in stands before its first words (W10)',
      () async {
        final (:play, :notices, texts: _) = control();
        await play.start();
        (String?, String?)? atSteps;
        play.notices.listen((notice) {
          if (notice is StepsShown) atSteps = (play.pending?.passageLabel, play.pending?.text);
        });
        await play.act('I train with the sword for a week', inputMode: 'typed');
        await until(play, () => play.pending == null);

        // The heading was there when the steps were decided, before a word of the story.
        expect(atSteps, ('A week later', ''));
        expect(play.story!.scenes.last.passageLabel, 'A week later');

        // A scene of minutes has none, in flight or saved.
        atSteps = null;
        await play.act('I look around the courtyard', inputMode: 'typed');
        await until(play, () => play.pending == null);
        expect(atSteps, (null, ''));
        expect(play.story!.scenes.last.passageLabel, isNull);
        expect(notices.whereType<StepsShown>(), hasLength(2));
      },
    );

    test('the steps arrive before the story, dice and all', () async {
      final (:play, :notices, :texts) = control();
      await play.start();
      String? textAtDice;
      play.notices.listen((notice) {
        if (notice is StepsShown) textAtDice = play.pending?.text;
      });
      await play.act('I leap across the gap', inputMode: 'typed');
      await until(play, () => play.pending == null);

      final shown = notices.whereType<StepsShown>().single;
      expect(shown.turn, 4);
      expect(shown.details.hasThrows, isTrue);
      // Not a word of the story was written yet.
      expect(textAtDice, isEmpty);
      expect(notices.indexOf(shown), lessThan(notices.indexWhere((n) => n is SceneSaved)));
      // The saved scene carries the same dice, and the story owes nothing.
      final saved = play.story!.scenes.last.details.steps.single.roll!;
      final decided = shown.details.steps.single.roll!;
      expect(saved.seed, decided.seed);
      expect(saved.thrown!.total, decided.thrown!.total);
      expect(play.owes, isFalse);
      expect(play.canAct, isTrue);
    });

    test(
      'a connection lost after the dice leaves the turn owed, and a retry plays it out',
      () async {
        final (:play, :notices, texts: _) = control();
        await play.start();
        await play.act(leap, inputMode: 'typed');
        await until(play, () => play.pending?.failed ?? false);
        expect(play.owes, isTrue);
        expect(play.story!.unfinishedTurn!.turn, 4);
        expect(play.story!.unfinishedTurn!.action, leap);
        expect(play.story!.version, 3);
        expect(play.canAct, isFalse);
        final decided = notices.whereType<StepsShown>().single.details.steps.single.roll!;

        expect(await play.retry(), isTrue);
        await until(play, () => play.pending == null);
        // It asks for the owed turn by name, and sends no words a second time.
        expect(turnRequests().last.json['kind'], 'resume');
        expect(turnRequests().last.json.containsKey('action'), isFalse);
        final scene = play.story!.scenes.last;
        expect((scene.turn, scene.playerAction), (4, leap));
        // The same dice: nothing is rolled again.
        expect(scene.details.steps.single.roll!.seed, decided.seed);
        expect(scene.details.steps.single.roll!.thrown!.total, decided.thrown!.total);
        expect(play.owes, isFalse);
        expect(notices.whereType<OwedTurnPlaying>(), isEmpty);
        expect(notices.whereType<StoryMovedOn>(), isEmpty);
      },
    );

    test('a storyteller failure after the dice keeps the turn too', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('[fail:llm_unavailable] I leap across the gap', inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      expect(play.pending!.error!.code, ApiErrorCode.llmUnavailable);
      expect(play.owes, isTrue);

      // Dismissed, it is still what the story does next.
      play.dismissFailure();
      expect(play.pending, isNull);
      expect(play.owes, isTrue);
      expect(await play.resume(), isTrue);
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.turn, 4);
      expect(turnRequests().last.json['kind'], 'resume');
    });

    test('a story opened while it owes a turn plays it out at once', () async {
      await loseElsewhere();
      final (:play, :notices, texts: _) = control();
      final labels = <String?>{};
      play.addListener(() {
        if (play.pending case final pending?) labels.add(pending.label);
      });
      await play.start();
      await until(play, () => play.story?.scenes.lastOrNull?.turn == 4 && play.pending == null);

      expect(turnRequests().last.json['kind'], 'resume');
      // The feed shows what the player did then, and the dice are shown again.
      expect(labels, {leap});
      expect(notices.whereType<StepsShown>().single.turn, 4);
      expect(notices.whereType<OwedTurnPlaying>(), isEmpty);
      expect(play.owes, isFalse);
    });

    test('an owed standing action keeps its kind, for the feed to name it', () async {
      final other = StoryRepository(api);
      // The fake keeps any turn whose connection is lost after the dice; a wait has one step.
      final lost = backend.data.stories.get(_demo, FakeAuthState.demoUserId);
      final events = await other.takeTurn(
        _demo,
        const TurnInput.standing('wait'),
        expectedVersion: lost.version,
      );
      // Stop listening after the dice, as a lost connection would.
      await events.firstWhere((event) => event is StepsDecided);

      final (:play, notices: _, texts: _) = control();
      final kinds = <(String, String?)>{};
      play.addListener(() {
        if (play.pending case final pending?) kinds.add((pending.kind, pending.label));
      });
      await play.start();
      await until(play, () => play.story?.scenes.lastOrNull?.turn == 4 && play.pending == null);
      expect(kinds, {('standing', 'wait')});
      expect(play.story!.scenes.last.kind, 'standing');
    });

    test(
      'whatever is sent, the owed turn is the one that plays, and the words come back',
      () async {
        final (:play, :notices, texts: _) = control();
        await play.start();
        // This device hasn't heard that the story owes a turn.
        await loseElsewhere();
        expect(play.owes, isFalse);
        final labels = <String?>[];
        play.addListener(() {
          if (play.pending case final pending?) labels.add(pending.label);
        });

        await play.act('I go home', inputMode: 'typed');
        await until(play, () => play.pending == null);
        expect(notices.whereType<OwedTurnPlaying>().single.action, 'I go home');
        // The feed first showed the words sent, then the turn that is really playing.
        expect(labels.first, 'I go home');
        expect(labels.last, leap);
        expect(play.story!.scenes.last.playerAction, leap);
        expect(play.story!.scenes.last.turn, 4);
        expect(notices.whereType<StoryMovedOn>(), isEmpty);
      },
    );

    test('a turn the story let go is dropped, and its words go back', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act(leap, inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      // The server lets it go meanwhile.
      backend.data.stories.get(_demo, FakeAuthState.demoUserId).unfinished = null;

      expect(await play.retry(), isFalse);
      await until(play, () => play.pending == null);
      expect(notices.whereType<OwedTurnLetGo>().single.action, leap);
      expect(notices.whereType<TurnRefused>(), isEmpty);
      expect(play.owes, isFalse);
      expect(play.canAct, isTrue);
      expect(play.story!.scenes.last.turn, 3);
    });

    test('a turn saved by the stream that was lost joins the feed without a word', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act(leap, inputMode: 'typed');
      await until(play, () => play.pending?.failed ?? false);
      // The owed turn is played out elsewhere before this device asks.
      final other = StoryRepository(api);
      await (await other.takeTurn(
        _demo,
        const TurnInput.resume(),
        expectedVersion: 3,
      )).drain<void>();

      expect(await play.retry(), isFalse);
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.turn, 4);
      expect(play.owes, isFalse);
      expect(notices.whereType<SceneSaved>().single.turn, 4);
      expect(notices.whereType<StoryMovedOn>(), isEmpty);
      expect(notices.whereType<OwedTurnLetGo>(), isEmpty);
    });

    test('an opening and a plain turn with no dice are never owed', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act('I look around', inputMode: 'typed');
      await until(play, () => play.pending == null);
      // Its one step is certain: shown, with nothing to throw.
      expect(notices.whereType<StepsShown>().single.details.hasThrows, isFalse);
      expect(play.owes, isFalse);
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

  group('endings', () {
    test('a death by your own hand brings the story to its ending', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('I stab myself', inputMode: 'typed');
      await until(play, () => play.pending == null);

      final ending = play.story!.ending!;
      expect(ending.isDeath, isTrue);
      expect(ending.selfInflicted, isTrue);
      expect(ending.character, 'Shen Yu');
      expect(play.ended, isTrue);
      expect(play.canAct, isFalse);
      expect(play.story!.scenes.last.choices, isEmpty);
      // No more turns: nothing is sent.
      expect(await play.act('I get up', inputMode: 'typed'), isFalse);
      expect(turnRequests(), hasLength(1));
    });

    test('/end with no note tells an epilogue and ends the story', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.end(label: 'End the story');
      await until(play, () => play.pending == null);

      final last = play.story!.scenes.last;
      expect(last.kind, 'end');
      expect(play.story!.ending!.kind, 'chosen');
      final sent = turnRequests().single.json;
      expect(sent['kind'], 'end');
      expect(sent.containsKey('action'), isFalse);
      expect(sent.containsKey('input_mode'), isFalse);
      expect(sent.containsKey('drop_refused'), isFalse);
    });

    test('a note the world refuses changes nothing, until the player ends without it', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      final before = play.story!;
      await play.end(note: 'I take the throne', inputMode: 'voice', label: 'I take the throne');
      await until(play, () => play.pending == null);

      final refusal = play.refusal!;
      expect(refusal.parts.single.text, 'take the throne');
      expect(refusal.parts.single.reason, isNotEmpty);
      expect(play.story!.version, before.version);
      expect(play.story!.ending, isNull);

      play.playOn();
      expect(play.refusal, isNull);
      expect(play.canAct, isTrue);

      await play.end(note: 'I take the throne', inputMode: 'voice', label: 'I take the throne');
      await until(play, () => play.refusal != null);
      await play.endWithoutRefused();
      await until(play, () => play.pending == null);
      expect(play.refusal, isNull);
      expect(play.story!.ending!.kind, 'chosen');
      final last = turnRequests().last.json;
      expect(
        (last['action'], last['input_mode'], last['drop_refused']),
        ('I take the throne', 'voice', true),
      );
    });

    test('closing a story at its ending keeps it to read', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.end(label: 'End the story');
      await until(play, () => play.pending == null);

      await play.close();
      expect(play.story!.ending!.closed, isTrue);
      expect(play.closing, isFalse);
      expect(notices.whereType<CloseFailed>(), isEmpty);
      expect(
        backend.requests.where((r) => r.method == 'POST' && r.uri.path.endsWith('/close')),
        hasLength(1),
      );
    });

    test('a story that ended on another device is shown as it is now', () async {
      final elsewhere = control();
      final here = control();
      await elsewhere.play.start();
      await here.play.start();
      await elsewhere.play.end(label: 'End the story');
      await until(elsewhere.play, () => elsewhere.play.pending == null);

      await here.play.act('I wait by the window', inputMode: 'typed');
      await until(here.play, () => here.play.ended);
      expect(here.notices.whereType<StoryMovedOn>(), hasLength(1));
      expect(here.play.pending, isNull);
    });

    test('a death by others is rewound: the world and the feed go back to before it', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act('I look around', inputMode: 'typed');
      await until(play, () => play.pending == null);
      final before = play.story!.scenes.last;
      await play.act('I challenge the elder', inputMode: 'typed');
      await until(play, () => play.ended);

      final ending = play.story!.ending!;
      expect((ending.selfInflicted, ending.rewind, ending.canRewind), (false, 1, true));
      final version = play.story!.version;

      expect(await play.rewind(1), isTrue);
      expect(play.ended, isFalse);
      expect(play.rewinding, isFalse);
      expect(play.story!.scenes.last.turn, before.turn);
      expect(play.story!.scenes.last.narration, before.narration);
      expect(play.story!.version, version + 1);
      expect(play.canAct, isTrue);
      expect(notices.whereType<RewindFailed>(), isEmpty);
      final sent = backend.requests
          .where((r) => r.method == 'POST' && r.uri.path.endsWith('/rewind'))
          .single
          .json;
      expect(sent, {'expected_version': version, 'scenes': 1});

      // The story plays on from there, in the turn it went back to.
      await play.act('I bow to the elder', inputMode: 'typed');
      await until(play, () => play.pending == null);
      expect(play.story!.scenes.last.turn, before.turn + 1);
      expect(play.ended, isFalse);
    });

    test('a death the player chose is always real: there is no rewind', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('I stab myself', inputMode: 'typed');
      await until(play, () => play.ended);

      expect(play.story!.ending!.canRewind, isFalse);
      expect(await play.rewind(1), isFalse);
      expect(backend.requests.where((r) => r.uri.path.endsWith('/rewind')), isEmpty);
    });

    test('a rewind the server refuses says so and keeps the ending', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      await play.act('I fight the wolves', inputMode: 'typed');
      await until(play, () => play.ended);

      // Balanced reaches one scene back, not two.
      expect(await play.rewind(2), isFalse);
      expect(play.ended, isTrue);
      expect(notices.whereType<RewindFailed>(), hasLength(1));
    });

    test('a story rewound on another device loads without the scenes taken back', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('I look around', inputMode: 'typed');
      await until(play, () => play.pending == null);
      final before = play.story!.scenes.last.turn;
      await play.act('I cross the rotten bridge', inputMode: 'typed');
      await until(play, () => play.ended);
      await repository.rewind(_demo, expectedVersion: play.story!.version, scenes: 1);

      await play.reload();

      expect(play.ended, isFalse);
      expect(play.story!.scenes.last.turn, before);
    });

    test('a turn played anew after a rewind elsewhere is not hidden by a block here', () async {
      final here = control();
      final elsewhere = control();
      await here.play.start();
      await here.play.act('I challenge the elder', inputMode: 'typed');
      await until(here.play, () => here.play.ended);
      final turn = here.play.story!.scenes.last.turn;
      await here.play.report(turn, category: 'other', block: true);
      expect(here.play.isBlocked(here.play.story!.scenes.last), isTrue);

      await elsewhere.play.start();
      expect(await elsewhere.play.rewind(1), isTrue);
      await elsewhere.play.act('I bow to the elder', inputMode: 'typed');
      await until(elsewhere.play, () => elsewhere.play.pending == null);

      await here.play.reload();
      final last = here.play.story!.scenes.last;
      expect(last.turn, turn);
      expect(here.play.ended, isFalse);
      expect(here.play.isBlocked(last), isFalse);
    });

    test('someone new carries the story on: their opening comes first, then play', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('I stab myself', inputMode: 'typed');
      await until(play, () => play.pending == null);

      await repository.drawSuccessor(_demo);
      final carried = await repository.carryOn(_demo, expectedVersion: play.story!.version);
      expect(carried.openingDue, isTrue);
      expect(carried.ending, isNull);
      play.carriedOn(carried);

      expect(play.ended, isFalse);
      expect(play.opening, isTrue);
      expect(play.canAct, isFalse);
      expect(await play.act('I look around', inputMode: 'typed'), isFalse);
      await until(play, () => play.pending == null);
      // Only the opening came next.
      expect(turnRequests().last.json['kind'], 'opening');
      expect(play.story!.scenes.last.kind, 'opening');
      expect(play.story!.scenes.last.narration, startsWith('At dawn, Mei Lin'));
      expect(play.story!.openingDue, isFalse);
      expect(play.opening, isFalse);
      expect(play.canAct, isTrue);
    });

    test('a story carried on elsewhere loads without its ending, and opens', () async {
      final (:play, notices: _, texts: _) = control();
      await play.start();
      await play.act('I stab myself', inputMode: 'typed');
      await until(play, () => play.pending == null);
      await repository.drawSuccessor(_demo);
      await repository.carryOn(_demo, expectedVersion: play.story!.version);

      await play.reload();
      expect(play.ended, isFalse);
      await until(play, () => play.pending == null && play.story!.scenes.last.kind == 'opening');
      expect(play.canAct, isTrue);
    });

    test('a turn refused because the story ended reloads it', () async {
      final (:play, :notices, texts: _) = control();
      await play.start();
      repository.turnError = const ApiException(ApiErrorCode.storyEnded, status: 409);

      expect(await play.act('I wait', inputMode: 'typed'), isFalse);
      expect(play.pending, isNull);
      expect(notices.whereType<TurnRefused>().single.error.code, ApiErrorCode.storyEnded);
      await until(play, () => !play.loading);
    });
  });
}
