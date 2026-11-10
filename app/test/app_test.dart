import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
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
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/design/gallery/gallery_screen.dart';
import 'package:playable_anime/features/auth/welcome_screen.dart';
import 'package:playable_anime/features/story/story_screen.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'helpers.dart';

/// The whole app on the fake backend: the signed-out welcome, then the tabs, a story and a turn.
void main() {
  late FakeBackend backend;
  late MemorySessionStore store;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    backend = FakeBackend.standard(pace: FakePace.instant);
    store = MemorySessionStore();
  });

  Future<JsonMap> login() async =>
      await ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend).post('/v1/auth/login', {
            'email': FakeAuthState.demoEmail,
            'password': FakeAuthState.demoPassword,
          }, authenticated: false)
          as JsonMap;

  Future<void> signInStored() async => store.value = Session.fromApi(await login());

  /// Starts the app at [location], as a link or a browser address would.
  void openAt(WidgetTester tester, String location) {
    tester.platformDispatcher.defaultRouteNameTestValue = location;
    addTearDown(tester.platformDispatcher.clearDefaultRouteNameTestValue);
  }

  Future<void> launch(WidgetTester tester) async {
    usePhone(tester);
    await tester.pumpWidget(
      ProviderScope(
        retry: retryTransient,
        overrides: [
          httpClientProvider.overrideWithValue(backend),
          apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
          sessionStoreProvider.overrideWithValue(store),
          speechEngineProvider.overrideWithValue(FakeSpeechEngine()),
        ],
        child: const App(),
      ),
    );
    await settle(tester);
  }

  testWidgets('signed out, the app opens on the welcome screen', (tester) async {
    await launch(tester);
    final l10n = await english();
    expect(find.text(l10n.appTitle), findsOneWidget);
    expect(find.text(l10n.welcomeTagline), findsOneWidget);
    expect(find.byType(LucidTabBar), findsNothing);
  });

  testWidgets('signed in, a player browses, opens a story and takes a turn', (tester) async {
    await signInStored();
    await launch(tester);
    final l10n = await english();

    // Discover: the signature worlds.
    expect(find.text(l10n.discoverHeadline), findsOneWidget);
    expect(find.text('The Last Outer Disciple'), findsOneWidget);
    expect(find.byType(CoverCard), findsWidgets);

    // Library: the story in progress.
    await tester.tap(find.byTooltip(l10n.navLibrary));
    await settle(tester);
    expect(find.byType(StoryTile), findsOneWidget);
    await tester.tap(find.byType(StoryTile));
    await settle(tester, frames: 12);

    // The play screen opens on the newest scene, with its choices below.
    final newest = find.textContaining('The scroll is warm', findRichText: true);
    expect(newest, findsOneWidget);
    expect(tester.getTopLeft(newest).dy, inInclusiveRange(0, 844));
    final feed = find.ancestor(of: find.byType(SceneCard).first, matching: find.byType(Scrollable));
    await tester.scrollUntilVisible(find.byType(StoryChoices), 300, scrollable: feed.first);
    await settle(tester);

    // A typed turn streams in and lands as a new scene.
    await tester.enterText(find.byType(TextField), 'I listen at the door');
    await tester.pump();
    await tester.tap(find.byTooltip(l10n.composerSend));
    await settle(tester, frames: 12);
    expect(find.textContaining('I listen at the door'), findsOneWidget);
    await tester.scrollUntilVisible(find.byType(StoryChoices), 300, scrollable: feed.first);
    expect(find.byType(StoryChoices), findsOneWidget);
    final turn = backend.requests.lastWhere((r) => r.uri.path.endsWith('/turns'));
    expect(turn.json['input_mode'], 'typed');
    expect(turn.json['expected_version'], 3);

    // Memory opens in the story's accent.
    await tester.tap(find.byTooltip(l10n.storyMemory));
    await settle(tester, frames: 10);
    expect(find.text(l10n.memoryTitle), findsOneWidget);
    final accent = Theme.of(
      tester.element(find.text(l10n.memoryYou.toUpperCase())),
    ).extension<LucidColors>()!.accent;
    expect(accent, accentFor(GenreAccent.jade, Brightness.dark));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a story opened from a link has a way back', (tester) async {
    await signInStored();
    await launch(tester);
    GoRouter.of(tester.element(find.byType(LucidTabBar))).go('/story/story_ninth_peak');
    await settle(tester, frames: 10);
    expect(find.byType(BackButton), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await settle(tester);
    expect(find.byType(StoryTile), findsOneWidget);
  });

  testWidgets('a link to a public page opens it while signed out', (tester) async {
    openAt(tester, '/gallery?theme=light');
    await launch(tester);
    expect(find.byType(GalleryScreen), findsOneWidget);
  });

  testWidgets('a link to a story opened signed out leads there after sign-in', (tester) async {
    openAt(tester, '/story/story_ninth_peak');
    await launch(tester);
    expect(find.byType(WelcomeScreen), findsOneWidget);

    final container = ProviderScope.containerOf(tester.element(find.byType(WelcomeScreen)));
    await container.read(sessionProvider.notifier).signIn(await login());
    await settle(tester, frames: 10);
    expect(find.byType(StoryScreen), findsOneWidget);
    expect(find.text('The Ninth Peak'), findsWidgets);
  });

  testWidgets('signing out returns to the welcome screen', (tester) async {
    await signInStored();
    await launch(tester);
    final l10n = await english();
    await tester.tap(find.byTooltip(l10n.navAccount));
    await settle(tester);
    await tester.ensureVisible(find.text(l10n.accountSignOut));
    await settle(tester);
    await tester.tap(find.text(l10n.accountSignOut));
    await settle(tester);
    expect(find.text(l10n.welcomeTagline), findsOneWidget);
    expect(store.value, isNull);
  });
}
