import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';

import '../helpers.dart';
import 'harness.dart';

/// A story's language (S10): its settings switch what comes next, and the mic listens for it.
/// What the story has already told stays as it was.
void main() {
  testWidgets('a story switched to Spanish carries on in Spanish, mic included', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/story/story_ninth_peak');
    final l10n = await english();

    Future<String?> dictate() async {
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      final heard = app.speech.listens.last.localeId;
      await tester.tap(find.byTooltip(l10n.micStop));
      await tester.pump();
      return heard;
    }

    expect(await dictate(), 'en-US');

    await tester.tap(find.byTooltip(l10n.storySettings));
    await settle(tester);
    expect(find.text(l10n.settingsLanguageHelp), findsOneWidget);
    await tester.tap(find.text(l10n.languageSpanish));
    await tester.pump();
    final save = find.widgetWithText(FilledButton, l10n.settingsSave);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await settle(tester, frames: 10);

    expect(app.sent('PATCH', (p) => p.startsWith('/v1/stories/')).last.json['settings'], {
      'language': 'es',
    });
    // The saved note sits over the composer for a few seconds.
    await tester.pump(const Duration(seconds: 10));
    await settle(tester);
    expect(await dictate(), 'es-ES');
    expect(tester.takeException(), isNull);
  });
}
