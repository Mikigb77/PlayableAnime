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
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';
import 'package:playable_anime/features/story/story_screen.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';

import '../helpers.dart';

/// A repository whose turns the test answers by hand.
class _Turns extends StoryRepository {
  _Turns() : super(ApiClient(baseUrl: 'https://api.test', httpClient: MockClient(_never)));

  static Future<http.Response> _never(http.Request _) => Completer<http.Response>().future;

  final story = Story(
    id: 's1',
    title: 'The Ninth Peak',
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
}

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

  Future<void> open(WidgetTester tester) async {
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
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          storyRepositoryProvider.overrideWithValue(turns),
          speechEngineProvider.overrideWithValue(FakeSpeechEngine(supported: false)),
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
}
