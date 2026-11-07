import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/byok_store.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/core/session/session_controller.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/account/account_repository.dart';
import 'package:playable_anime/features/account/out_of_credits_sheet.dart';
import 'package:playable_anime/features/story/scene_details_sheet.dart';
import 'package:playable_anime/features/story/scene_view.dart';
import 'package:playable_anime/features/story/status_screen.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';
import 'package:playable_anime/features/story/story_screen.dart';
import 'package:playable_anime/features/story/successor_screen.dart';
import 'package:playable_anime/features/story/turn_error_card.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';

import '../helpers.dart';

const _demo = 'story_ninth_peak';

/// The play screen on the fake backend, the way a player meets it: streamed turns, pictures,
/// details, reports, settings, every turn error and `/status`.
void main() {
  late FakeBackend backend;
  late ApiClient api;
  late ByokStore keys;
  late Session session;
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  /// The Semantics that carries a color swatch's name and whether it is picked.
  Finder semanticsOf(String key) => find
      .descendant(of: find.byKey(Key(key)), matching: find.byType(Semantics), matchRoot: true)
      .first;

  /// A signed-in fake backend whose clock is the test's.
  Future<void> serve(WidgetTester tester, {FakePace pace = FakePace.instant}) async {
    backend = FakeBackend.standard(pace: pace, clock: () => tester.binding.clock.now());
    final tokens = TestTokens();
    keys = const ByokStore(FakeAuthState.demoUserId);
    api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend, tokens: tokens, byok: keys);
    await tester.runAsync(() async {
      final json =
          await api.post('/v1/auth/login', {
                'email': FakeAuthState.demoEmail,
                'password': FakeAuthState.demoPassword,
              }, authenticated: false)
              as JsonMap;
      tokens.accessToken = json['access_token'] as String;
      session = Session.fromApi(json);
    });
  }

  Future<void> open(
    WidgetTester tester, {
    String id = _demo,
    String page = '',
    double textScale = 1,
  }) async {
    usePhone(tester);
    final router = GoRouter(
      initialLocation: '/story/$id$page',
      routes: [
        GoRoute(
          path: '/library',
          builder: (_, _) => const Scaffold(body: Text('Library')),
        ),
        GoRoute(
          path: '/account',
          builder: (_, _) => const Scaffold(body: Text('Account')),
        ),
        GoRoute(
          path: '/story/:id',
          builder: (_, state) => StoryScreen(storyId: state.pathParameters['id']!),
          routes: [
            GoRoute(
              path: 'status',
              builder: (_, state) => StatusScreen(
                storyId: state.pathParameters['id']!,
                accent: state.extra as GenreAccent?,
              ),
            ),
            GoRoute(
              path: 'memory',
              builder: (_, _) => const Scaffold(body: Text('Memory')),
            ),
            GoRoute(
              path: 'successor',
              builder: (_, state) => SuccessorScreen(
                storyId: state.pathParameters['id']!,
                story: state.extra as Story?,
              ),
            ),
          ],
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          storyRepositoryProvider.overrideWithValue(StoryRepository(api)),
          byokStoreProvider.overrideWithValue(keys),
          // The account screens' providers, as the out-of-credits sheet uses them.
          httpClientProvider.overrideWithValue(backend),
          apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
          sessionStoreProvider.overrideWithValue(MemorySessionStore(session)),
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
          builder: (context, app) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: app!,
          ),
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
    await settle(tester);
  }

  /// Pumps until [done], in steps of [step], for at most [limit].
  Future<void> pumpUntil(
    WidgetTester tester,
    bool Function() done, {
    Duration step = const Duration(milliseconds: 100),
    Duration limit = const Duration(seconds: 20),
  }) async {
    for (var waited = Duration.zero; !done(); waited += step) {
      if (waited > limit) fail('Gave up waiting after $limit');
      await tester.pump(step);
    }
  }

  /// Scrolls to the end of the feed, past the newest scene to its choices.
  Future<void> toEnd(WidgetTester tester) async {
    final scroll = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    for (var i = 0; i < 4; i++) {
      scroll.jumpTo(scroll.position.maxScrollExtent);
      await tester.pump();
    }
    await settle(tester);
  }

  /// Taps the last match, once it is scrolled to the middle of the view (clear of the Latest pill).
  Future<void> tapLast(WidgetTester tester, Finder finder) async {
    await Scrollable.ensureVisible(tester.element(finder.last), alignment: 0.5);
    await tester.pump();
    await settle(tester);
    await tester.tap(finder.last);
    await settle(tester);
  }

  /// Opens a scene's "How it played out" sheet, scrolling the feed down to its button.
  Future<void> openDetails(WidgetTester tester, int turn) async {
    final button = find.descendant(
      of: find.byWidgetPredicate((w) => w is SceneView && w.scene.turn == turn),
      matching: find.text(l10n.sceneDetails),
    );
    await tester.scrollUntilVisible(
      button,
      200,
      scrollable: find
          .descendant(of: find.byType(CustomScrollView), matching: find.byType(Scrollable))
          .first,
    );
    await tapLast(tester, button);
  }

  String box(WidgetTester tester) =>
      tester.widget<TextField>(find.byType(TextField)).controller!.text;

  Finder words(String text) => find.textContaining(text, findRichText: true);

  testWidgets('a scripted story plays through: streaming, the saved scene, a picture', (
    tester,
  ) async {
    await serve(
      tester,
      pace: const FakePace(
        latency: Duration.zero,
        firstWords: Duration(milliseconds: 300),
        perChunk: Duration(milliseconds: 30),
        picture: Duration(seconds: 2),
      ),
    );
    await open(tester);
    // It opens at the top of the newest scene, to read it from its first words.
    expect(words('The scroll is warm, like something alive.'), findsOneWidget);
    await toEnd(tester);
    expect(find.text('Climb down the cliff path in the dark'), findsOneWidget);

    await tester.tap(find.text('Climb down the cliff path in the dark'));
    await tester.pump(const Duration(milliseconds: 500));
    // The words arrive while the turn is written, under what the player chose.
    final streaming = find.byType(StreamingNarration);
    expect(streaming, findsOneWidget);
    final early = tester.widget<StreamingNarration>(streaming).text;
    expect(early, isNotEmpty);
    expect(tester.widget<Composer>(find.byType(Composer)).busy, isTrue);
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.widget<StreamingNarration>(streaming).text.length, greaterThan(early.length));

    await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
    await settle(tester);
    await toEnd(tester);
    expect(find.byKey(const ValueKey('choices-4')), findsOneWidget);
    expect(tester.widget<Composer>(find.byType(Composer)).busy, isFalse);

    // Turn 4 meets Senior Sister Lan: her portrait is painted after the words.
    bool painted() => tester
        .widgetList<ScenePictureView>(find.byType(ScenePictureView))
        .any((v) => v.image.kind == 'portrait' && v.image.isReady);
    await pumpUntil(tester, painted, step: const Duration(milliseconds: 500));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a story opens with its newest scene a little below the bar', (tester) async {
    await serve(tester);
    await open(tester);
    await settle(tester, frames: 12);

    final feed = tester.getTopLeft(find.byType(CustomScrollView)).dy;
    final newest = find.byWidgetPredicate((w) => w is SceneView && w.scene.turn == 3);
    // The same room a followed scene stops at, so its first line never sits under the bar.
    expect(tester.getTopLeft(newest).dy - feed, moreOrLessEquals(Space.lg, epsilon: 1));
  });

  testWidgets('a scene that is written quickly is still followed up to its top', (tester) async {
    // The whole scene arrives a moment after the action, before the page has followed it.
    await serve(
      tester,
      pace: const FakePace(
        latency: Duration.zero,
        firstWords: Duration(milliseconds: 60),
        perChunk: Duration.zero,
        picture: Duration(seconds: 30),
      ),
    );
    await open(tester);
    await toEnd(tester);
    await send(tester, 'I look around the courtyard');
    await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
    await settle(tester, frames: 12);

    final feed = tester.getTopLeft(find.byType(CustomScrollView)).dy;
    final scene = find.byWidgetPredicate((w) => w is SceneView && w.scene.turn == 4);
    final top = tester.getTopLeft(scene).dy - feed;
    final scroll = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    final atEnd = scroll.position.maxScrollExtent - scroll.position.pixels < 1;
    expect(top <= Space.lg + 1 || atEnd, isTrue, reason: 'the new scene starts $top px down');
    expect(top, greaterThanOrEqualTo(0));
  });

  testWidgets('a story started from a draft plays its opening scene', (tester) async {
    await serve(tester);
    late String id;
    await tester.runAsync(() async {
      final draft =
          await api.post('/v1/drafts', {
                'premise': 'A lighthouse keeper finds a door in the sea.',
                'rating': 'teen',
              })
              as JsonMap;
      final started = await api.post('/v1/drafts/${draft['id']}/start', {}) as JsonMap;
      id = started['story_id'] as String;
    });
    await open(tester, id: id);
    await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
    await settle(tester);
    expect(words('A lighthouse keeper finds a door in the sea.'), findsOneWidget);
    final turns = backend.requests.where((r) => r.uri.path.endsWith('/turns'));
    expect(turns.single.json['kind'], 'opening');
    // The opening reads from the title page, which stays whole above it.
    final scroll = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    expect(scroll.position.pixels, 0);

    // Opened again later, it lands on the title page too.
    await open(tester, id: id);
    await settle(tester, frames: 12);
    final again = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    expect(again.position.pixels, 0);
  });

  testWidgets('an opening played again on the player\'s own key reads from the title page', (
    tester,
  ) async {
    await serve(tester);
    late String id;
    await tester.runAsync(() async {
      final draft =
          await api.post('/v1/drafts', {
                'premise': 'A lighthouse keeper finds a door in the sea.',
                'rating': 'teen',
              })
              as JsonMap;
      final started = await api.post('/v1/drafts/${draft['id']}/start', {}) as JsonMap;
      id = started['story_id'] as String;
    });
    final account = backend.data.account;
    account.charge(
      FakeAuthState.demoUserId,
      kind: 'adjustment',
      cents: account.balanceOf(FakeAuthState.demoUserId),
      now: DateTime.now(),
    );
    await open(tester, id: id);
    await settle(tester);
    // Refused for credits, then sent again on the key the player adds on the sheet.
    await tester.tap(find.byKey(const Key('ooc.useKey')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('account.ownKey')), 'AIza-from-the-sheet');
    await tester.tap(find.byKey(const Key('account.ownKey.save')));
    await settle(tester);
    await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
    await settle(tester, frames: 12);

    expect(words('A lighthouse keeper finds a door in the sea.'), findsOneWidget);
    final scroll = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    expect(scroll.position.pixels, 0);
  });

  testWidgets('a standing action reads in the app\'s words, not the server\'s wire name', (
    tester,
  ) async {
    await serve(tester);
    await open(tester);
    await toEnd(tester);
    await tester.tap(find.widgetWithText(ActionChip, l10n.standingWait).last);
    await settle(tester);
    await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
    await settle(tester);

    final saved = tester.widgetList<SceneView>(find.byType(SceneView)).last.scene;
    expect((saved.kind, saved.playerAction), ('standing', 'wait'));
    final card = find.byWidgetPredicate((w) => w is SceneCard && w.playerAction != null).last;
    expect(tester.widget<SceneCard>(card).playerAction, l10n.standingWait);

    // Its one step in "How it played out" reads the same way.
    await openDetails(tester, saved.turn);
    final sheet = find.byType(SceneDetailsView);
    expect(find.descendant(of: sheet, matching: find.text(l10n.standingWait)), findsNWidgets(2));
    expect(find.descendant(of: sheet, matching: find.text('wait')), findsNothing);
  });

  testWidgets('scene details show the steps, the roll and where the plan stopped', (tester) async {
    await serve(tester);
    await open(tester);
    await openDetails(tester, 3);
    expect(find.text('Reach the window before the wards wake'), findsOneWidget);
    expect(words(l10n.detailsOdds('about even')), findsOneWidget);
    expect(find.text(l10n.detailsStopped), findsOneWidget);
    expect(find.text(l10n.classContested.toUpperCase()), findsWidgets);
  });

  testWidgets('scene details say what struck back after a step (N6)', (tester) async {
    await serve(tester);
    await open(tester);
    await send(tester, 'I strike at the masked disciple');
    await settle(tester);
    await openDetails(tester, 4);
    expect(find.text(l10n.detailsStruck), findsOneWidget);
    expect(
      find.text('The masked disciple strikes back (unlikely): it misses you.'),
      findsOneWidget,
    );
    expect(words(l10n.detailsOdds('unlikely')), findsOneWidget);
  });

  testWidgets('scene details explain the beats that made something true (R2)', (tester) async {
    await serve(tester);
    await open(tester);
    await send(tester, 'I climb down a rope from the bell tower');
    await settle(tester);
    await openDetails(tester, 4);
    expect(find.text('Find a rope'), findsOneWidget);
    expect(
      find.text(l10n.detailsBeatMadeCanon('a coil of rope by the bell tower')),
      findsOneWidget,
    );
  });

  testWidgets('a link straight to a page above the story opens cleanly', (tester) async {
    await serve(tester);
    await open(tester, page: '/memory');
    await settle(tester, frames: 12);
    expect(find.text('Memory'), findsOneWidget);
    expect(tester.takeException(), isNull);

    // Back on the story, it lands on the newest scene.
    tester.state<NavigatorState>(find.byType(Navigator).last).pop();
    await settle(tester, frames: 12);
    expect(words('The scroll is warm, like something alive.'), findsOneWidget);
  });

  testWidgets('a scene can be reported and blocked, and stays hidden', (tester) async {
    await serve(tester);
    await open(tester);
    await tapLast(tester, find.byTooltip(l10n.sceneMore));
    await tester.tap(find.text(l10n.sceneReport));
    await settle(tester);
    await tester.tap(find.text(l10n.reportHate));
    await tester.pump();
    await tester.tap(find.text(l10n.reportSend));
    await settle(tester);
    expect(find.text(l10n.storyHidden), findsOneWidget);
    expect(find.text(l10n.reportSentHidden), findsOneWidget);
    // Its choices were written from its text, so they go too; Wait and Observe stay.
    await toEnd(tester);
    expect(find.text('Climb down the cliff path in the dark'), findsNothing);
    expect(find.text(l10n.standingWait), findsOneWidget);
    expect(backend.data.reports.single, containsPair('category', 'hate'));
    expect(backend.data.reports.single, containsPair('block', true));
  });

  testWidgets('settings send only what changed', (tester) async {
    await serve(tester);
    await open(tester);
    await tester.tap(find.byTooltip(l10n.storySettings));
    await settle(tester);
    final save = find.widgetWithText(FilledButton, l10n.settingsSave);
    expect(tester.widget<FilledButton>(save).onPressed, isNull);

    await tester.tap(find.text(l10n.settingsShort));
    await tester.pump();
    await tester.ensureVisible(save);
    await tester.tap(save);
    await settle(tester);
    final patch = backend.requests.lastWhere((r) => r.method == 'PATCH');
    expect(patch.json.containsKey('title'), isFalse);
    expect(patch.json['settings'], {'narration_length': 'short'});
    expect(find.text(l10n.settingsSaved), findsOneWidget);
  });

  testWidgets('the player can change a story\'s color, and go back to its genre\'s (S13)', (
    tester,
  ) async {
    await serve(tester);
    await open(tester);
    Color primary(Finder finder) => Theme.of(tester.element(finder)).colorScheme.primary;
    final jade = accentFor(GenreAccent.jade, Brightness.dark);
    final rose = accentFor(GenreAccent.rose, Brightness.dark);
    // The demo story is cultivation, so it opens in jade.
    expect(primary(find.byType(AppBar)), jade);

    await tester.tap(find.byTooltip(l10n.storySettings));
    await settle(tester);
    final save = find.widgetWithText(FilledButton, l10n.settingsSave);
    expect(tester.widget<Semantics>(semanticsOf('settings.color.auto')).properties.selected, true);
    await tester.tap(find.byKey(const Key('settings.color.rose')));
    await settle(tester);
    // The sheet wears the color before it is saved.
    expect(primary(save), rose);
    final pink = tester.widget<Semantics>(semanticsOf('settings.color.rose')).properties;
    expect((pink.selected, pink.label), (true, l10n.colorRose));
    // A screen reader can pick it too.
    expect(pink.onTap, isNotNull);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await settle(tester, frames: 10);
    final patch = backend.requests.lastWhere((r) => r.method == 'PATCH');
    expect(patch.json['settings'], {'accent': 'rose'});
    // It shows at once, so the message doesn't wait for the next scene.
    expect(find.text(l10n.settingsSavedNow), findsOneWidget);
    expect(primary(find.byType(AppBar)), rose);

    // The pages above the story take it too.
    await tester.tap(find.byTooltip(l10n.storyStatus));
    await settle(tester, frames: 10);
    expect(
      primary(find.descendant(of: find.byType(StatusScreen), matching: find.byType(AppBar))),
      rose,
    );
    tester.state<NavigatorState>(find.byType(Navigator).last).pop();
    await settle(tester, frames: 10);

    await tester.tap(find.byTooltip(l10n.storySettings));
    await settle(tester);
    await tester.tap(find.byKey(const Key('settings.color.auto')));
    await settle(tester);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await settle(tester, frames: 10);
    expect(backend.requests.lastWhere((r) => r.method == 'PATCH').json['settings'], {
      'accent': null,
    });
    expect(primary(find.byType(AppBar)), jade);
  });

  group('turn errors', () {
    testWidgets('a storyteller failure drops the words; dismissing gives the action back', (
      tester,
    ) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:llm_unavailable] I look around');
      expect(find.byType(TurnErrorCard), findsOneWidget);
      expect(find.byType(StreamingNarration), findsNothing);
      expect(find.text(l10n.retry), findsOneWidget);
      expect(box(tester), isEmpty);

      await tester.tap(find.text(l10n.turnDismiss));
      await settle(tester);
      expect(find.byType(TurnErrorCard), findsNothing);
      expect(box(tester), '[fail:llm_unavailable] I look around');
    });

    testWidgets('an unreadable action goes back in the box to say it another way', (tester) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:unreadable_action] Hm');
      await tester.tap(find.text(l10n.turnRephrase));
      await settle(tester);
      expect(find.byType(TurnErrorCard), findsNothing);
      expect(box(tester), '[fail:unreadable_action] Hm');
    });

    testWidgets('a content limit shows the server\'s words and no retry', (tester) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:limit] Someone famous');
      expect(find.text(l10n.turnLimitTitle), findsOneWidget);
      expect(find.textContaining('real, living people'), findsOneWidget);
      expect(find.text(l10n.retry), findsNothing);
      expect(find.text(l10n.turnRephrase), findsOneWidget);
    });

    testWidgets('out of credits opens the sheet, and closing it keeps the words', (tester) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:out_of_credits] Go');
      expect(find.byType(OutOfCreditsSheet), findsOneWidget);
      expect(find.text(l10n.oocTitle), findsOneWidget);
      await tester.tap(find.text(l10n.close));
      await settle(tester);
      expect(find.byType(OutOfCreditsSheet), findsNothing);
      expect(find.byType(TurnErrorCard), findsNothing);
      expect(box(tester), '[fail:out_of_credits] Go');
    });

    testWidgets('a saved scene refreshes the balance the account screens show', (tester) async {
      await serve(tester);
      await open(tester);
      final container = ProviderScope.containerOf(tester.element(find.byType(StoryScreen)));
      // The account as a screen showed it.
      container.listen(meProvider, (_, _) {});
      await pumpUntil(tester, () => container.read(meProvider).hasValue);
      int reads() => backend.requests.where((r) => r.uri.path == '/v1/me').length;
      final before = reads();
      await send(tester, 'I wait by the fire');
      await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
      await settle(tester);
      expect(reads(), greaterThan(before));
    });

    testWidgets('adding your own key on that sheet plays the turn on it', (tester) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:out_of_credits] I climb the wall');
      await tester.tap(find.byKey(const Key('ooc.useKey')));
      await settle(tester);
      await tester.enterText(find.byKey(const Key('account.ownKey')), 'AIza-from-the-sheet');
      await tester.tap(find.byKey(const Key('account.ownKey.save')));
      await settle(tester);

      expect(find.byType(OutOfCreditsSheet), findsNothing);
      await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
      await settle(tester);
      await toEnd(tester);
      expect(find.byKey(const ValueKey('choices-4')), findsOneWidget);
      expect(box(tester), isEmpty);
      // On the player's key: no credits spent on the turn.
      expect(
        backend.data.account.ledgerOf(FakeAuthState.demoUserId).where((e) => e['kind'] == 'turn'),
        isEmpty,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('a rate limit counts down before the retry', (tester) async {
      await serve(tester);
      await open(tester);
      await send(tester, '[fail:rate_limited] Go');
      expect(find.text(l10n.turnRetryIn(20)), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      expect(find.text(l10n.turnRetryIn(19)), findsOneWidget);
      await tester.pump(const Duration(seconds: 20));
      expect(find.text(l10n.retry), findsOneWidget);
    });

    testWidgets('a turn another device played first shows the latest scene', (tester) async {
      await serve(tester);
      await open(tester);
      await tester.runAsync(() async {
        await collect(
          await StoryRepository(
            api,
          ).takeTurn(_demo, const TurnInput.standing('observe'), expectedVersion: 3),
        );
      });
      await send(tester, 'I run');
      await settle(tester);
      expect(find.text(l10n.errorVersionConflict), findsOneWidget);
      expect(box(tester), 'I run');
      await toEnd(tester);
      expect(find.byKey(const ValueKey('choices-4')), findsOneWidget);
    });
  });

  testWidgets('/status opens the character sheet', (tester) async {
    await serve(tester);
    await open(tester);
    await send(tester, '/status');
    expect(find.byType(StatusScreen), findsOneWidget);
    expect(find.text('Shen Yu'), findsOneWidget);
    expect(find.text('Azure Cloud Sect'), findsOneWidget);
    expect(find.text('3 months ago'), findsOneWidget);
    // The player character's portrait, as on the memory page (M4).
    final avatar = tester.widget<PortraitAvatar>(find.byType(PortraitAvatar));
    expect(avatar.url, 'asset:assets/fake/portrait-3.jpg');
  });

  testWidgets('scrolling back loads older scenes, and Latest returns to the newest', (
    tester,
  ) async {
    await serve(tester);
    await tester.runAsync(() async {
      final stories = StoryRepository(api);
      for (var version = 3; version < 25; version++) {
        await collect(
          await stories.takeTurn(
            _demo,
            const TurnInput.standing('observe'),
            expectedVersion: version,
          ),
        );
      }
    });
    await open(tester);
    await settle(tester, frames: 12);
    expect(find.byKey(const ValueKey('choices-25')), findsOneWidget);

    double latest() => tester
        .widget<AnimatedOpacity>(
          find.ancestor(of: find.text(l10n.storyLatest), matching: find.byType(AnimatedOpacity)),
        )
        .opacity;
    expect(latest(), 0);

    // Back to the first scene loaded: the scenes before it load above, and the page stays put.
    final scroll = tester.widget<CustomScrollView>(find.byType(CustomScrollView)).controller!;
    final sixth = find.byWidgetPredicate((w) => w is SceneView && w.scene.turn == 6);
    await tester.drag(find.byType(CustomScrollView), const Offset(0, 600));
    for (var i = 0; i < 4 && sixth.evaluate().isEmpty; i++) {
      scroll.jumpTo(scroll.position.minScrollExtent);
      await tester.pump();
    }
    final before = tester.getTopLeft(sixth).dy;
    await settle(tester);
    expect(backend.requests.where((r) => r.uri.path.endsWith('/scenes')), isNotEmpty);
    expect(find.byWidgetPredicate((w) => w is SceneView && w.scene.turn == 5), findsOneWidget);
    expect(tester.getTopLeft(sixth).dy, before);
    expect(latest(), 1);

    await tester.tap(find.text(l10n.storyLatest));
    await settle(tester, frames: 12);
    expect(find.byKey(const ValueKey('choices-25')), findsOneWidget);
  });

  group('after an ending (N6)', () {
    List<JsonMap> draws() => [
      for (final e in backend.data.account.ledgerOf(FakeAuthState.demoUserId))
        if (e['kind'] == 'draft') e,
    ];

    Future<void> die(WidgetTester tester) async {
      await send(tester, 'I stab myself');
      await settle(tester, frames: 10);
      expect(find.text(l10n.endingDeathTitle('Shen Yu')), findsOneWidget);
    }

    Future<void> carryOn(WidgetTester tester) async {
      await tapLast(tester, find.byKey(const ValueKey('ending.carryOn')));
      await settle(tester, frames: 10);
    }

    testWidgets('someone else carries the story on, starting with an opening of their own', (
      tester,
    ) async {
      await serve(tester);
      await open(tester);
      await die(tester);
      await carryOn(tester);

      // Someone is drawn as the screen opens, charged like a draft (K2).
      expect(find.byType(SuccessorScreen), findsOneWidget);
      expect(find.byKey(const ValueKey('successor.name')), findsOneWidget);
      expect(find.text('Mei Lin'), findsOneWidget);
      expect(find.text(l10n.successorStation('common').toUpperCase()), findsOneWidget);
      expect(find.byKey(const ValueKey('successor.master')), findsNothing);
      expect(draws(), hasLength(1));

      // Drawing again draws someone else.
      await tester.tap(find.byKey(const ValueKey('successor.drawAgain')));
      await settle(tester, frames: 10);
      expect(find.text('Old Bo'), findsOneWidget);
      expect(
        find.text(
          '${l10n.successorStation('skilled')} · ${l10n.successorOneIn(1000)}'.toUpperCase(),
        ),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('successor.master')), findsOneWidget);
      expect(draws(), hasLength(2));

      await tester.tap(find.byKey(const ValueKey('successor.start')));
      await settle(tester, frames: 12);

      // Back on the story: the ending is lifted and the newcomer's opening is told.
      expect(find.byType(SuccessorScreen), findsNothing);
      expect(find.text(l10n.endingDeathTitle('Shen Yu')), findsNothing);
      await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
      await settle(tester);
      final story = backend.data.stories.get(_demo, FakeAuthState.demoUserId);
      expect(story.openingDue, isFalse);
      expect(story.scenes.last['kind'], 'opening');
      expect(words('Old Bo\'s door'), findsWidgets);
      expect(tester.widget<Composer>(find.byType(Composer)).enabled, isTrue);

      // And the new character can die too, under their own name.
      await send(tester, 'I stab myself');
      await settle(tester, frames: 10);
      expect(find.text(l10n.endingDeathTitle('Old Bo')), findsOneWidget);
    });

    testWidgets('leaving the screen keeps who was drawn, at no new charge', (tester) async {
      await serve(tester);
      await open(tester);
      await die(tester);
      await carryOn(tester);
      expect(find.text('Mei Lin'), findsOneWidget);

      await tester.pageBack();
      await settle(tester, frames: 10);
      expect(find.text(l10n.endingDeathTitle('Shen Yu')), findsOneWidget);

      await carryOn(tester);
      expect(find.text('Mei Lin'), findsOneWidget);
      expect(draws(), hasLength(1));
    });

    testWidgets('out of credits offers the player\'s own key, and draws on it', (tester) async {
      await serve(tester);
      await open(tester);
      await die(tester);
      final account = backend.data.account;
      account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: account.balanceOf(FakeAuthState.demoUserId),
        now: backend.now(),
      );
      await carryOn(tester);

      expect(find.text('Mei Lin'), findsNothing);
      expect(find.text(l10n.oocCarryOn), findsOneWidget);
      await tester.tap(find.text(l10n.oocCarryOn));
      await settle(tester);
      await tester.tap(find.byKey(const Key('ooc.useKey')));
      await settle(tester);
      await tester.enterText(find.byKey(const Key('account.ownKey')), 'AIza-from-the-sheet');
      await tester.tap(find.byKey(const Key('account.ownKey.save')));
      await settle(tester, frames: 10);

      expect(find.text('Mei Lin'), findsOneWidget);
      expect(draws(), isEmpty);
    });

    testWidgets('an heir who didn\'t live to act leaves the choice open', (tester) async {
      await serve(tester);
      await open(tester);
      await die(tester);
      backend.data.stories.get(_demo, FakeAuthState.demoUserId).heirs = [
        {
          'id': 'xiao',
          'name': 'Shen Xiao',
          'relation': 'child',
          'age': 4,
          'years': 12,
          'lost': true,
        },
      ];
      await carryOn(tester);

      await tester.tap(find.byKey(const ValueKey('successor.heir.xiao')));
      await settle(tester, frames: 10);
      expect(find.text(l10n.successorHeirLost('Shen Xiao')), findsOneWidget);
      expect(find.text(l10n.successorChoose), findsOneWidget);
      expect(draws(), isEmpty);

      await tester.tap(find.byKey(const ValueKey('successor.random')));
      await settle(tester, frames: 10);
      expect(find.text('Mei Lin'), findsOneWidget);
      expect(draws(), hasLength(1));
    });

    testWidgets('a child carries the story on, years later, or someone from the world', (
      tester,
    ) async {
      await serve(tester);
      await open(tester);
      await die(tester);
      final fake = backend.data.stories.get(_demo, FakeAuthState.demoUserId);
      final worldS = fake.worldS;
      fake.heirs = [
        {'id': 'xiao', 'name': 'Shen Xiao', 'relation': 'child', 'age': 4, 'years': 12},
        {
          'id': 'unborn:lan',
          'name': 'Lan\'s child, not yet born',
          'relation': 'child',
          'age': null,
          'unborn': true,
          'years': 17,
        },
      ];
      await carryOn(tester);

      // The heirs come first, with someone from the world, and nothing is drawn until one is
      // picked.
      expect(find.text(l10n.successorChoose), findsOneWidget);
      expect(find.text('Shen Xiao'), findsOneWidget);
      expect(
        find.text('${l10n.successorHeirOf('child', 'Shen Yu')} · ${l10n.successorAge(4)}'),
        findsOneWidget,
      );
      expect(find.text(l10n.successorYearsLater(12)), findsOneWidget);
      expect(
        find.text('${l10n.successorHeirOf('child', 'Shen Yu')} · ${l10n.successorUnborn}'),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('successor.random')), findsOneWidget);
      expect(draws(), isEmpty);

      // Someone from the world is still a choice, and then the heirs again.
      await tester.tap(find.byKey(const ValueKey('successor.random')));
      await settle(tester, frames: 10);
      expect(find.text('Mei Lin'), findsOneWidget);
      expect(find.byKey(const ValueKey('successor.drawAgain')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('successor.chooseAgain')));
      await settle(tester);
      expect(find.text(l10n.successorChoose), findsOneWidget);
      expect(draws(), hasLength(1));

      await tester.tap(find.byKey(const ValueKey('successor.heir.xiao')));
      await settle(tester, frames: 10);
      expect(find.byKey(const ValueKey('successor.name')), findsOneWidget);
      expect(find.text('${l10n.successorAge(16)} · Azure Cloud Town'), findsOneWidget);
      expect(
        find.text(
          '${l10n.successorHeirOf('child', 'Shen Yu')} · ${l10n.successorYearsLater(12)}'
              .toUpperCase(),
        ),
        findsOneWidget,
      );
      expect(draws(), hasLength(2));

      await tester.tap(find.byKey(const ValueKey('successor.start')));
      await settle(tester, frames: 12);
      await pumpUntil(tester, () => find.byType(StreamingNarration).evaluate().isEmpty);
      await settle(tester);
      expect(find.byType(SuccessorScreen), findsNothing);
      final story = backend.data.stories.get(_demo, FakeAuthState.demoUserId);
      expect(story.playerName, 'Shen Xiao');
      expect(story.scenes.last['kind'], 'opening');
      expect(story.worldS, greaterThanOrEqualTo(worldS + 12 * 365 * 24 * 3600));
    });
  });

  testWidgets('at twice the text size nothing overflows', (tester) async {
    await serve(tester);
    await open(tester, textScale: 2);
    await send(tester, 'I draw my blade and attack');
    await settle(tester, frames: 12);
    await openDetails(tester, 4);
    expect(tester.takeException(), isNull);
  });
}
