import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/fake/fake_narration.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/narration/narration_widgets.dart';
import 'package:playable_anime/features/story/replay/replay_view.dart';
import 'package:playable_anime/features/story/scene_view.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';
import 'package:playable_anime/features/story/turn_error_card.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';
import 'harness.dart';

const _demo = 'story_ninth_peak';
const _story = '/story/$_demo';
const _leap = 'I leap across the gap';

Finder _key(String name) => find.byKey(ValueKey(name));

/// The dice on the story screen: gamer mode (S15), which plays a turn's dice before its scene,
/// and the turn a story owes (A3), which is played out before anything else.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  Future<void> send(WidgetTester tester, String text) async {
    await tester.enterText(find.byType(TextField), text);
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await settle(tester, frames: 16);
  }

  String box(WidgetTester tester) =>
      tester.widget<TextField>(find.byType(TextField)).controller!.text;

  List<Scene> scenes(WidgetTester tester) => [
    for (final view in tester.widgetList<SceneView>(find.byType(SceneView))) view.scene,
  ];

  /// The turns the app asked for, by kind.
  List<String?> asked(AppHarness app) => [
    for (final r in app.sent('POST', (p) => p.endsWith('/turns'))) r.json['kind'] as String?,
  ];

  /// Another device starts a turn with [words] on the story.
  Future<void> elsewhere(WidgetTester tester, AppHarness app, String words) async {
    await tester.runAsync(() async {
      await app.signIn();
      final stories = StoryRepository(
        ApiClient(
          baseUrl: FakeBackend.baseUrl,
          httpClient: app.backend,
          tokens: TestTokens(app.store.value!.accessToken),
        ),
      );
      final story = await stories.get(_demo);
      final events = await stories.takeTurn(
        _demo,
        TurnInput.action(words, inputMode: 'typed'),
        expectedVersion: story.version,
      );
      await events.drain<void>().catchError((Object _) {});
    });
  }

  group('gamer mode (S15)', () {
    testWidgets('off unless the player turns it on: the scene comes with nothing over it', (
      tester,
    ) async {
      final app = AppHarness();
      await app.launch(tester, location: _story);
      await send(tester, _leap);

      expect(find.byType(ReplayScreen), findsNothing);
      expect(scenes(tester).last.playerAction, _leap);
      expect(scenes(tester).last.details.hasThrows, isTrue);
    });

    testWidgets("its switch is in the story's settings, applies at once and is remembered", (
      tester,
    ) async {
      final app = AppHarness();
      await app.launch(tester, location: _story);
      await tester.tap(find.byTooltip(l10n.storySettings));
      await settle(tester);

      final gamer = _key('settings.gamer');
      await tester.ensureVisible(gamer);
      await tester.pump();
      expect(find.descendant(of: gamer, matching: find.text(l10n.settingsGamer)), findsOneWidget);
      expect(tester.widget<SwitchListTile>(gamer).value, isFalse);
      await tester.tap(gamer);
      await settle(tester);
      expect(tester.widget<SwitchListTile>(gamer).value, isTrue);
      // It is the player's own choice on this device, not a setting of the story: nothing is
      // sent, and nothing waits for Save.
      expect((await SharedPreferences.getInstance()).getBool('play.gamer_mode'), isTrue);
      expect(app.sent('PATCH', (p) => p.endsWith('/stories/$_demo')), isEmpty);

      tester.state<NavigatorState>(find.byType(Navigator).last).pop();
      await settle(tester, frames: 10);
      await send(tester, _leap);
      expect(find.byType(ReplayScreen), findsOneWidget);

      await tester.tap(_key('replay.skip'));
      await settle(tester, frames: 12);
      expect(find.byType(ReplayScreen), findsNothing);
    });

    testWidgets('the dice play before the scene, and the scene is read aloud after them', (
      tester,
    ) async {
      final app = AppHarness();
      SharedPreferences.setMockInitialValues({
        'play.gamer_mode': true,
        'narration.read_new_scenes': true,
      });
      await app.launch(tester, location: _story);
      await send(tester, _leap);

      // The replay opened by itself, with the step the turn was decided on.
      expect(find.byType(ReplayScreen), findsOneWidget);
      expect(find.text(l10n.replayTitleOwn), findsOneWidget);
      expect(_key('replay.stage.0.run'), findsOneWidget);
      expect(
        find.descendant(of: find.byType(ReplayScreen), matching: find.text(_leap)),
        findsOneWidget,
      );
      // The scene has landed behind it, and waits unread.
      expect(scenes(tester).last.playerAction, _leap);
      expect(app.player.played, isEmpty);
      expect(find.byType(ReadingBar), findsNothing);

      // Skip goes straight to the story, and now it is read.
      await tester.tap(_key('replay.skip'));
      await settle(tester, frames: 16);
      expect(find.byType(ReplayScreen), findsNothing);
      expect(app.player.played, [narrationAsset]);
      expect(find.byType(ReadingBar), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('played to its end, the replay gives way to the story by itself', (tester) async {
      final app = AppHarness();
      SharedPreferences.setMockInitialValues({'play.gamer_mode': true});
      await app.launch(tester, location: _story);
      await send(tester, _leap);
      expect(find.byType(ReplayScreen), findsOneWidget);

      // Tapped through: a tap throws the dice, a tap shows the result and a tap moves on.
      for (var taps = 0; taps < 8 && _key('replay.row.0').evaluate().isEmpty; taps++) {
        await tester.tapAt(const Offset(30, 300));
        await settle(tester, frames: 4);
      }
      expect(_key('replay.row.0'), findsOneWidget);
      // It offers nothing and waits for nothing: the story is behind it.
      expect(_key('replay.again'), findsNothing);
      await tester.pump(const Duration(milliseconds: 2600));
      await settle(tester, frames: 12);
      expect(find.byType(ReplayScreen), findsNothing);
      expect(scenes(tester).last.playerAction, _leap);
    });

    testWidgets('a turn the facts settled has no dice to play', (tester) async {
      final app = AppHarness();
      SharedPreferences.setMockInitialValues({'play.gamer_mode': true});
      await app.launch(tester, location: _story);
      await send(tester, 'I look around');

      expect(find.byType(ReplayScreen), findsNothing);
      expect(scenes(tester).last.playerAction, 'I look around');
    });

    testWidgets('it never opens over a page the player has opened', (tester) async {
      final app = AppHarness(
        pace: const FakePace(
          latency: Duration.zero,
          firstWords: Duration(milliseconds: 600),
          perChunk: Duration(milliseconds: 10),
          picture: Duration(seconds: 2),
        ),
      );
      SharedPreferences.setMockInitialValues({'play.gamer_mode': true});
      await app.launch(tester, location: _story);
      await tester.enterText(find.byType(TextField), _leap);
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pump(const Duration(milliseconds: 50));
      // The settings sheet is up when the dice are decided.
      await tester.tap(find.byTooltip(l10n.storySettings));
      await settle(tester, frames: 30);

      expect(find.byType(ReplayScreen), findsNothing);
      expect(_key('settings.gamer'), findsOneWidget);
    });
  });

  group('a turn the story owes (A3)', () {
    testWidgets('it is played out as the story opens, dice first in gamer mode', (tester) async {
      final app = AppHarness();
      SharedPreferences.setMockInitialValues({'play.gamer_mode': true});
      await elsewhere(tester, app, '[fail:lost] $_leap');
      await app.launch(tester, location: _story);
      await settle(tester, frames: 16);

      expect(asked(app).last, 'resume');
      expect(find.byType(ReplayScreen), findsOneWidget);
      await tester.tap(_key('replay.skip'));
      await settle(tester, frames: 12);
      // The scene is the one that was decided, with the words it was decided on.
      expect(scenes(tester).last.playerAction, '[fail:lost] $_leap');
      expect(scenes(tester).last.turn, 4);
      expect(_key('turn.owed'), findsNothing);
    });

    testWidgets('words sent for another turn come back, and the owed turn plays', (tester) async {
      final app = AppHarness();
      await app.launch(tester, location: _story);
      // The story came to owe a turn after this screen opened.
      await elsewhere(tester, app, '[fail:lost] $_leap');
      await send(tester, 'I walk to the gate');

      expect(find.text(l10n.turnOwedWordsBack), findsOneWidget);
      expect(box(tester), 'I walk to the gate');
      expect(scenes(tester).last.playerAction, '[fail:lost] $_leap');
      expect(scenes(tester).where((scene) => scene.playerAction == 'I walk to the gate'), isEmpty);
    });

    testWidgets('while a decided turn is written, the box stays open for what comes after', (
      tester,
    ) async {
      final app = AppHarness(
        pace: const FakePace(
          latency: Duration.zero,
          firstWords: Duration(milliseconds: 600),
          perChunk: Duration(milliseconds: 10),
          picture: Duration(seconds: 2),
        ),
      );
      await app.launch(tester, location: _story);
      await tester.enterText(find.byType(TextField), _leap);
      await tester.testTextInput.receiveAction(TextInputAction.send);
      await tester.pump(const Duration(milliseconds: 450));

      // Its dice are decided, so the story owes it, and it is the turn in flight: the player can
      // go on writing as in any turn.
      final story = app.backend.data.stories.get(_demo, FakeAuthState.demoUserId);
      expect(story.unfinished, isNotNull);
      expect(scenes(tester).where((scene) => scene.playerAction == _leap), isEmpty);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
      expect(_key('turn.owed'), findsNothing);

      await settle(tester, frames: 40);
      expect(scenes(tester).last.playerAction, _leap);
      expect(story.unfinished, isNull);
    });

    testWidgets('when its scene fails, dismissing leaves the turn waiting to be played out', (
      tester,
    ) async {
      final app = AppHarness();
      await app.launch(tester, location: _story);
      const words = '[fail:llm_unavailable] $_leap';
      await send(tester, words);
      expect(find.byType(TurnErrorCard), findsOneWidget);

      await tester.tap(find.text(l10n.turnDismiss));
      await settle(tester);
      expect(find.byType(TurnErrorCard), findsNothing);
      // The turn is decided: its words stay with it, and nothing else can be sent first.
      expect(_key('turn.owed'), findsOneWidget);
      expect(find.text(l10n.turnOwedTitle), findsOneWidget);
      expect(find.text(words), findsOneWidget);
      expect(box(tester), isEmpty);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);

      await tester.ensureVisible(_key('turn.owed.continue'));
      await tester.pump();
      await tester.tap(_key('turn.owed.continue'));
      await settle(tester, frames: 16);
      expect(asked(app).last, 'resume');
      expect(_key('turn.owed'), findsNothing);
      expect(scenes(tester).last.playerAction, words);
      expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
    });
  });
}
