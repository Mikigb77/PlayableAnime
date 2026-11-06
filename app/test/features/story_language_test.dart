import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/core/preferences.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/story/story_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// A story's language (S10): a story stays in the language it was set up in, whatever the app's
/// language does later, and the mic listens for it. Its settings don't offer to switch it.
void main() {
  testWidgets('a Catalan story stays in Catalan, mic included, whatever the app is in', (
    tester,
  ) async {
    final app = AppHarness();
    app.backend.data.stories
            .get('story_ninth_peak', FakeAuthState.demoUserId)
            .settings['language'] =
        'ca';
    await app.launch(tester, location: '/story/story_ninth_peak');
    final l10n = await english();

    Future<String?> dictate(String stop) async {
      await tester.tap(find.byType(MicButton));
      await tester.pump();
      final heard = app.speech.listens.last.localeId;
      await tester.tap(find.byTooltip(stop));
      await tester.pump();
      return heard;
    }

    expect(await dictate(l10n.micStop), 'ca-ES');

    // The settings change how it's told, never its language.
    await tester.tap(find.byTooltip(l10n.storySettings));
    await settle(tester);
    expect(find.text(l10n.settingsNarration), findsOneWidget);
    for (final language in [l10n.languageEnglish, l10n.languageSpanish, l10n.languageCatalan]) {
      expect(find.text(language), findsNothing);
    }
    await tester.tap(find.text(l10n.settingsShort));
    await tester.pump();
    final save = find.widgetWithText(FilledButton, l10n.settingsSave);
    await tester.ensureVisible(save);
    await tester.tap(save);
    await settle(tester, frames: 10);
    expect(app.sent('PATCH', (p) => p.startsWith('/v1/stories/')).last.json['settings'], {
      'narration_length': 'short',
    });
    // The saved note sits over the composer for a few seconds.
    await tester.pump(const Duration(seconds: 10));
    await settle(tester);

    // The app switching to Spanish leaves the story, and what the mic listens for, in Catalan.
    final container = ProviderScope.containerOf(tester.element(find.byType(StoryScreen)));
    await container.read(languageProvider.notifier).set(AppLanguage.spanish);
    await settle(tester);
    final es = await AppLocalizations.delegate.load(const Locale('es'));
    expect(await dictate(es.micStop), 'ca-ES');
    expect(tester.takeException(), isNull);
  });
}
