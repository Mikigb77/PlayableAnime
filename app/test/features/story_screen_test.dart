import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/testing.dart';
import 'package:http/http.dart' as http;
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/turn_events.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/create/create_story_screen.dart' show StartAgain;
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';
import 'package:playable_anime/features/story/story_screen.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

import '../helpers.dart';

/// A repository whose turns the test answers by hand.
class _Turns extends StoryRepository {
  _Turns() : super(ApiClient(baseUrl: 'https://api.test', httpClient: MockClient(_never)));

  static Future<http.Response> _never(http.Request _) => Completer<http.Response>().future;

  final story = Story(
    id: 's1',
    title: 'The Ninth Peak',
    premise: 'An outer disciple hears a voice in the forbidden library.',
    version: 1,
    scenes: [
      Scene.fromJson(const {
        'turn': 1,
        'narration': 'Mist rolls over the ninth peak.',
        'choices': [
          {'id': 'c1', 'label': 'Climb'},
        ],
      }),
    ],
  );
  final requests = <TurnInput>[];

  /// The turn in flight, made when it is asked for, inside the test's zone.
  Completer<Stream<TurnEvent>>? pending;

  @override
  Future<Story> get(String id, {int scenes = 20}) async => story;

  @override
  Future<Stream<TurnEvent>> takeTurn(String id, TurnInput input, {required int expectedVersion}) {
    requests.add(input);
    return (pending = Completer()).future;
  }

  /// The ending the story reached, which closing marks closed (N6).
  StoryEnding? ending;
  int closes = 0;

  @override
  Future<Story> close(String id) async {
    closes++;
    final e = ending!;
    // Closing doesn't move the version: the story stays at the scene that ended it.
    return story.copyWith(
      version: e.turn,
      ending: StoryEnding(
        kind: e.kind,
        characterId: e.characterId,
        character: e.character,
        selfInflicted: e.selfInflicted,
        turn: e.turn,
        closed: true,
      ),
    );
  }

  /// Each rewind asked for, as (expected version, scenes) (C8).
  final rewinds = <(int, int)>[];

  @override
  Future<Story> rewind(String id, {required int expectedVersion, required int scenes}) async {
    rewinds.add((expectedVersion, scenes));
    // Only the opening is left after the rewind these tests ask for.
    return Story(
      id: story.id,
      title: story.title,
      premise: story.premise,
      version: expectedVersion + 1,
      scenes: story.scenes,
    );
  }
}

const _death = {
  'kind': 'death',
  'character_id': 'shen_yu',
  'character': 'Shen Yu',
  'self_inflicted': true,
  'turn': 2,
  'closed': false,
};

const _chosen = {
  'kind': 'chosen',
  'character_id': 'shen_yu',
  'character': 'Shen Yu',
  'self_inflicted': false,
  'turn': 2,
  'closed': false,
};

Stream<TurnEvent> _ends(int turn, String text, JsonMap ending) => Stream.fromIterable([
  TurnStarted(turn),
  NarrationDelta(text),
  SceneCompleted(
    scene: {'turn': turn, 'narration': text, 'kind': 'end', 'choices': const <Object>[]},
    version: turn,
    clock: const {},
    ending: ending,
  ),
]);

Stream<TurnEvent> _completes(int turn, String text) => Stream.fromIterable([
  TurnStarted(turn),
  NarrationDelta(text),
  SceneCompleted(
    scene: {'turn': turn, 'narration': text, 'choices': const <Object>[]},
    version: turn,
    clock: const {},
  ),
]);

void main() {
  late _Turns turns;
  late GoRouter router;

  setUp(() => turns = _Turns());

  Future<void> open(WidgetTester tester, {FakeSpeechEngine? speech}) async {
    usePhone(tester);
    router = GoRouter(
      initialLocation: '/story/s1',
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => const Scaffold(body: Text('Library')),
        ),
        GoRoute(
          path: '/story/:id',
          builder: (_, _) => const StoryScreen(storyId: 's1'),
        ),
        GoRoute(
          path: '/create',
          builder: (_, state) =>
              Scaffold(body: Text('Create: ${(state.extra as StartAgain?)?.premise}')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          storyRepositoryProvider.overrideWithValue(turns),
          speechEngineProvider.overrideWithValue(speech ?? FakeSpeechEngine(supported: false)),
        ],
        child: MaterialApp.router(
          theme: AppTheme.build(Brightness.dark, GenreAccent.lucid),
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          routerConfig: router,
        ),
      ),
    );
    await settle(tester);
  }

  Future<void> send(WidgetTester tester, String text) async {
    await tester.enterText(find.byType(TextField), text);
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
  }

  testWidgets('what the player writes while a turn starts is kept', (tester) async {
    await open(tester);
    await send(tester, 'I climb');
    expect(turns.requests.single.action, 'I climb');

    await tester.enterText(find.byType(TextField), 'Then I look back');
    turns.pending!.complete(_completes(2, 'The wind bites.'));
    await settle(tester);
    expect(find.text('Then I look back'), findsOneWidget);

    // Unchanged, the box empties once the turn is under way.
    await send(tester, 'Then I look back');
    expect(turns.requests, hasLength(2));
    turns.pending!.complete(_completes(3, 'The valley is gone.'));
    await settle(tester);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
  });

  String box(WidgetTester tester) =>
      tester.widget<TextField>(find.byType(TextField)).controller!.text;

  group('with the mic on (V2)', () {
    testWidgets('send turns it off and waits for the words, then sends the whole box', (
      tester,
    ) async {
      final mic = FakeSpeechEngine(onPhone: false);
      await open(tester, speech: mic);
      final l10n = await english();
      await tester.enterText(find.byType(TextField), 'Quietly,');
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      expect(mic.listens, hasLength(1));

      await tester.tap(find.byTooltip(l10n.composerSend));
      await tester.pump();
      expect(mic.stops, 1);
      expect(turns.requests, isEmpty, reason: 'half of what was said never goes');

      mic
        ..hear('I bow.')
        ..stopped();
      await tester.pump();
      final sent = turns.requests.single;
      expect(sent.action, 'Quietly, I bow.');
      expect(sent.inputMode, 'voice_edited');

      turns.pending!.complete(_completes(2, 'The elder nods.'));
      await settle(tester);
      expect(box(tester), isEmpty);
    });

    testWidgets('send with an empty box sends what was said', (tester) async {
      final mic = FakeSpeechEngine(onPhone: false);
      await open(tester, speech: mic);
      final l10n = await english();
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      await tester.tap(find.byTooltip(l10n.composerSend));
      await tester.pump();
      mic
        ..hear('I climb.')
        ..stopped();
      await tester.pump();
      expect(turns.requests.single.action, 'I climb.');
      expect(turns.requests.single.inputMode, 'voice');
    });

    testWidgets('words that cannot be written down are not sent', (tester) async {
      final mic = FakeSpeechEngine(onPhone: false);
      await open(tester, speech: mic);
      final l10n = await english();
      await tester.enterText(find.byType(TextField), 'I climb');
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      await tester.tap(find.byTooltip(l10n.composerSend));
      await tester.pump();
      mic.fail(SpeechFailure.offline);
      await tester.pump();
      expect(turns.requests, isEmpty);
      expect(find.text(l10n.micOffline), findsOneWidget);
      expect(box(tester), 'I climb');
    });

    testWidgets('a suggestion waits for it too, and what was said stays in the box', (
      tester,
    ) async {
      final mic = FakeSpeechEngine(onPhone: false);
      await open(tester, speech: mic);
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      await tester.ensureVisible(find.text('Climb'));
      await tester.tap(find.text('Climb'));
      await tester.pump();
      expect(mic.stops, 1);
      expect(turns.requests, isEmpty);
      expect(tester.widget<Composer>(find.byType(Composer)).busy, isTrue);

      mic
        ..hear('I look around.')
        ..stopped();
      await tester.pump();
      expect(turns.requests.single.choiceId, 'c1');
      expect(box(tester), 'I look around.');
    });
  });

  testWidgets('a retry of a turn refused before it started empties the box', (tester) async {
    await open(tester);
    await send(tester, 'I climb');
    turns.pending!.completeError(const ApiException(ApiErrorCode.llmUnavailable));
    await settle(tester);
    // Refused before it started: the words stay in the box.
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, 'I climb');

    final l10n = await english();
    await tester.ensureVisible(find.text(l10n.retry));
    await settle(tester);
    await tester.tap(find.text(l10n.retry));
    await tester.pump();
    turns.pending!.complete(_completes(2, 'The wind bites.'));
    await settle(tester);
    expect(turns.requests, hasLength(2));
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
  });

  testWidgets('leaving while a turn starts is safe', (tester) async {
    await open(tester);
    await send(tester, 'I climb');
    router.go('/');
    await settle(tester);
    expect(find.text('Library'), findsOneWidget);

    turns.pending!.complete(_completes(2, 'The wind bites.'));
    await settle(tester);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a turn that fails in an unexpected way still frees the composer', (tester) async {
    await open(tester);
    await send(tester, 'I climb');
    turns.pending!.completeError(const FormatException('Unexpected end of input'));
    await settle(tester);

    final l10n = await english();
    expect(tester.widget<Composer>(find.byType(Composer)).busy, isFalse);
    expect(find.text(l10n.errorUnknown), findsOneWidget);
    // The words stay in the box, to send again.
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, 'I climb');
    expect(tester.takeException(), isFormatException);
  });

  Future<void> confirmEnd(WidgetTester tester) async {
    await tester.tap(find.byKey(const ValueKey('end.confirm')));
    await tester.pump();
  }

  testWidgets('a death ends the story: the ending card instead of the composer', (tester) async {
    await open(tester);
    await send(tester, 'I stab myself');
    turns
      ..ending = StoryEnding.fromJson(_death)
      ..pending!.complete(_ends(2, 'Your hand shakes, then it does not.', _death));
    await settle(tester);

    final l10n = await english();
    expect(find.byType(Composer), findsNothing);
    expect(find.text(l10n.endingDeathTitle('Shen Yu')), findsOneWidget);
    // One quiet line after a character took their own life.
    expect(find.text(l10n.endingHelpline), findsOneWidget);

    await tester.ensureVisible(find.byKey(const ValueKey('ending.close')));
    await tester.tap(find.byKey(const ValueKey('ending.close')));
    await settle(tester);
    expect(turns.closes, 1);
    expect(find.text(l10n.endingClosedTitle), findsOneWidget);
    expect(find.byKey(const ValueKey('ending.close')), findsNothing);
  });

  testWidgets('a death by others offers a rewind of as many scenes as it reaches', (tester) async {
    await open(tester);
    await send(tester, 'I climb');
    turns.pending!.complete(
      Stream.fromIterable([
        const TurnStarted(2),
        const NarrationDelta('You climb.'),
        const SceneCompleted(
          scene: {'turn': 2, 'narration': 'You climb.', 'player_action': 'I climb'},
          version: 2,
          clock: {},
        ),
      ]),
    );
    await settle(tester);
    await send(tester, 'I challenge the elder');
    final cutDown = <String, Object?>{..._death, 'self_inflicted': false, 'turn': 3, 'rewind': 2};
    turns.pending!.complete(
      Stream.fromIterable([
        const TurnStarted(3),
        const NarrationDelta('The blow comes.'),
        SceneCompleted(
          scene: const {
            'turn': 3,
            'narration': 'The blow comes.',
            'kind': 'end',
            'player_action': 'I challenge the elder',
            'choices': <Object>[],
          },
          version: 3,
          clock: const {},
          ending: cutDown,
        ),
      ]),
    );
    await settle(tester);

    final l10n = await english();
    expect(find.text(l10n.endingBodyRewind(2)), findsOneWidget);
    expect(find.text(l10n.endingHelpline), findsNothing);
    await tester.ensureVisible(find.byKey(const ValueKey('ending.rewind')));
    await tester.tap(find.byKey(const ValueKey('ending.rewind')));
    await settle(tester);

    expect(find.text(l10n.rewindTitle), findsOneWidget);
    expect(find.text(l10n.rewindBefore('I challenge the elder')), findsOneWidget);
    expect(find.text(l10n.rewindBefore('I climb')), findsOneWidget);
    expect(find.byKey(const ValueKey('rewind.3')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('rewind.2')));
    await settle(tester);

    expect(turns.rewinds, [(3, 2)]);
    expect(find.byKey(const ValueKey('ending.title')), findsNothing);
    expect(find.byType(Composer), findsOneWidget);
    expect(find.text('You climb.'), findsNothing);
  });

  testWidgets('a death the player chose offers no rewind', (tester) async {
    await open(tester);
    await send(tester, 'I stab myself');
    turns.pending!.complete(_ends(2, 'Your hand shakes, then it does not.', _death));
    await settle(tester);

    expect(find.byKey(const ValueKey('ending.title')), findsOneWidget);
    expect(find.byKey(const ValueKey('ending.rewind')), findsNothing);
  });

  testWidgets('/end asks first, then tells the epilogue and ends the story', (tester) async {
    await open(tester);
    final l10n = await english();
    await send(tester, '/end I walk into the mist');
    expect(find.text(l10n.endConfirmTitle), findsOneWidget);
    expect(turns.requests, isEmpty);
    await confirmEnd(tester);

    final sent = turns.requests.single;
    expect((sent.kind, sent.action, sent.dropRefused), ('end', 'I walk into the mist', false));
    turns.pending!.complete(_ends(2, 'The mist takes the road.', _chosen));
    await settle(tester);
    expect(find.text(l10n.endingChosenTitle('Shen Yu')), findsOneWidget);
    expect(find.text(l10n.endingHelpline), findsNothing);
    expect(find.byType(Composer), findsNothing);
  });

  testWidgets('/end can be called off', (tester) async {
    await open(tester);
    final l10n = await english();
    await send(tester, '/end');
    await tester.tap(find.text(l10n.endConfirmKeep));
    await settle(tester);
    expect(turns.requests, isEmpty);
    expect(find.byType(Composer), findsOneWidget);
  });

  testWidgets('a refused ending offers to play on or to end without it', (tester) async {
    await open(tester);
    final l10n = await english();
    await send(tester, '/end I take the throne');
    await confirmEnd(tester);
    turns.pending!.complete(
      Stream.fromIterable(const [
        TurnStarted(2),
        EndingRefused(
          message: 'No.',
          refused: [RefusedPart(text: 'take the throne', reason: 'Nobody would follow you.')],
        ),
      ]),
    );
    await settle(tester);
    expect(find.text(l10n.endRefusedTitle), findsOneWidget);
    expect(find.textContaining('Nobody would follow you.', findRichText: true), findsOneWidget);
    expect(find.byType(Composer), findsOneWidget);

    await tester.ensureVisible(find.byKey(const ValueKey('ending.endWithout')));
    await tester.tap(find.byKey(const ValueKey('ending.endWithout')));
    await tester.pump();
    expect(turns.requests.last.dropRefused, isTrue);
    expect(turns.requests.last.action, 'I take the throne');
    turns.pending!.complete(_ends(2, 'You leave the peak.', _chosen));
    await settle(tester);
    expect(find.text(l10n.endRefusedTitle), findsNothing);
    expect(find.text(l10n.endingChosenTitle('Shen Yu')), findsOneWidget);
  });

  testWidgets('starting again opens the create flow with the same premise', (tester) async {
    await open(tester);
    await send(tester, '/end');
    await confirmEnd(tester);
    turns.pending!.complete(_ends(2, 'The end.', _chosen));
    await settle(tester);

    await tester.ensureVisible(find.byKey(const ValueKey('ending.startAgain')));
    await tester.tap(find.byKey(const ValueKey('ending.startAgain')));
    await settle(tester);
    expect(
      find.text('Create: An outer disciple hears a voice in the forbidden library.'),
      findsOneWidget,
    );
  });
}
