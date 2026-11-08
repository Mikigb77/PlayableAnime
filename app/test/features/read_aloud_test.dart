import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_narration.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/narration/narration_widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';
import 'harness.dart';

const _story = '/story/story_ninth_peak';

/// Reading scenes aloud on the play screen (V8 to V10): the listen button, the reading bar, new
/// scenes read as they land, the device's voice standing in, and the choices in Account.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  Finder listen(int turn) => find.byKey(ValueKey('scene.listen.$turn'));

  /// Taps a scene's listen button once the landing has settled and the button is mid-view.
  Future<void> tapListen(WidgetTester tester, int turn) async {
    await settle(tester, frames: 20);
    await Scrollable.ensureVisible(tester.element(listen(turn)), alignment: 0.5);
    await tester.pump();
    await settle(tester);
    await tester.tap(listen(turn));
    await settle(tester);
  }

  List<String> audioAsked(AppHarness app, int turn) => [
    for (final r in app.sent('POST', (p) => p.endsWith('/scenes/$turn/audio')))
      '${r.uri.queryParameters['part']} ${r.uri.queryParameters['voice']}',
  ];

  testWidgets('a scene is read in the studio voice, a part at a time, and stops', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: _story);

    await tapListen(tester, 3);

    expect(app.player.played, [narrationAsset]);
    // The next part is asked for while the first plays.
    expect(audioAsked(app, 3), ['0 Sulafat', '1 Sulafat']);
    expect(find.byType(ReadingBar), findsOneWidget);
    expect(find.text(l10n.narrationReading), findsOneWidget);
    expect(
      find.descendant(of: listen(3), matching: find.byTooltip(l10n.sceneListenStop)),
      findsOneWidget,
    );

    app.player.finish();
    await settle(tester);
    expect(app.player.played, hasLength(2));
    expect(audioAsked(app, 3), hasLength(3));

    await tester.tap(find.byKey(const ValueKey('reading.stop')));
    await settle(tester);
    expect(find.byType(ReadingBar), findsNothing);
    expect(app.player.playing, isFalse);
    expect(find.descendant(of: listen(3), matching: find.byTooltip(l10n.sceneListen)), findsOne);
    // The scene's parts were charged as voice, once each.
    final ledger = app.backend.data.account.ledgerOf(FakeAuthState.demoUserId);
    expect(ledger.where((e) => e['kind'] == 'voice'), hasLength(3));
    expect(tester.takeException(), isNull);
  });

  testWidgets('with "read new scenes" on, the next scene is read as it lands', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: _story);

    await tapListen(tester, 3);
    await tester.tap(find.byKey(const ValueKey('reading.readNew')));
    await settle(tester);
    expect((await SharedPreferences.getInstance()).getBool('narration.read_new_scenes'), isTrue);

    await tester.enterText(find.byType(TextField), 'I climb down the cliff path');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await settle(tester, frames: 20);

    // Acting stopped the old scene; the new one is being read.
    expect(audioAsked(app, 4), isNotEmpty);
    expect(app.player.played.length, greaterThan(1));
    expect(find.byType(ReadingBar), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets("out of credits, the device's voice reads the scene and says why", (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: _story);
    final account = app.backend.data.account;
    final user = FakeAuthState.demoUserId;
    account.charge(user, kind: 'turn', cents: account.balanceOf(user), now: DateTime.now());

    await tapListen(tester, 3);

    expect(find.text(l10n.narrationOutOfCredits), findsOneWidget);
    expect(app.player.played, isEmpty);
    final spoken = app.phoneVoice.spoken.single;
    expect(spoken.language, 'en');
    expect(spoken.text, startsWith('The scroll is warm, like something alive.'));
    expect(find.text(l10n.narrationReadingDevice), findsOneWidget);
    app.phoneVoice.finish();
    await settle(tester);
    expect(find.byType(ReadingBar), findsNothing);
  });

  testWidgets("the device's voice and a studio voice are chosen in Account", (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/account');

    final section = find.byType(NarrationSection);
    await tester.scrollUntilVisible(section, 300, scrollable: find.byType(Scrollable).first);
    await settle(tester);
    expect(find.text(l10n.narrationStudioBody), findsOneWidget);

    final charon = find.byKey(const ValueKey('narration.studio.Charon'));
    await tester.ensureVisible(charon);
    await tester.tap(charon);
    await settle(tester);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('narration.studio_voice'), 'Charon');

    await tester.ensureVisible(find.byKey(const ValueKey('narration.voice')));
    await tester.pump();
    await tester.tap(
      find.descendant(
        of: find.byKey(const ValueKey('narration.voice')),
        matching: find.text(l10n.narrationDevice),
      ),
    );
    await settle(tester);
    expect(prefs.getString('narration.voice'), 'device');
    expect(find.text(l10n.narrationDeviceBody), findsOneWidget);
    expect(charon, findsNothing);

    final readNew = find.byKey(const ValueKey('narration.readNew'));
    await tester.ensureVisible(readNew);
    await tester.tap(readNew);
    await settle(tester);
    expect(prefs.getBool('narration.read_new_scenes'), isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets("with the device's voice chosen, nothing goes to the API", (tester) async {
    final app = AppHarness();
    // After the harness, which starts with no preferences.
    SharedPreferences.setMockInitialValues({'narration.voice': 'device'});
    await app.launch(tester, location: _story);

    await tapListen(tester, 3);

    expect(app.phoneVoice.spoken.single.text, startsWith('The scroll is warm'));
    expect(audioAsked(app, 3), isEmpty);
    expect(find.text(l10n.narrationReadingDevice), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('reading.stop')));
    await settle(tester);
    expect(app.phoneVoice.speaking, isFalse);
  });

  testWidgets("a device with no voice for the story's language says which it needs", (
    tester,
  ) async {
    final app = AppHarness();
    SharedPreferences.setMockInitialValues({'narration.voice': 'device'});
    await app.launch(tester, location: _story);
    app.phoneVoice.available = false;

    await tapListen(tester, 3);

    expect(find.text(l10n.narrationNoDeviceVoice('en')), findsOneWidget);
    expect(l10n.narrationNoDeviceVoice('en'), contains('English voice'));
    expect(l10n.narrationNoDeviceVoice('es'), contains('Spanish (Spain) voice'));
    expect(find.byType(ReadingBar), findsNothing);
  });

  testWidgets('leaving the story stops its reading', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: _story);
    await tapListen(tester, 3);
    expect(app.player.playing, isTrue);

    await tester.pageBack();
    await settle(tester, frames: 10);
    expect(app.player.playing, isFalse);
  });

  testWidgets('the reading bar fits at 2× text in Spanish', (tester) async {
    tester.platformDispatcher.localesTestValue = const [Locale('es', 'ES')];
    addTearDown(tester.platformDispatcher.clearLocalesTestValue);
    final app = AppHarness();
    await app.launch(tester, location: _story, textScale: 2);
    await tapListen(tester, 3);

    expect(find.byType(ReadingBar), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
