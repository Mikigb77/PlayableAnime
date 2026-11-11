import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/story/sheet_view.dart';
import 'package:playable_anime/features/story/status_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// Every new screen at twice the text size, on a phone: nothing clips or overflows (DESIGN.md,
/// Accessibility).
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  /// Scrolls the screen's main list to its end, a page at a time, so every part is laid out.
  Future<void> scrollThrough(WidgetTester tester) async {
    final list = find.byType(Scrollable).first;
    for (var i = 0; i < 12; i++) {
      await tester.drag(list, const Offset(0, -600), warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 400));
    }
  }

  for (final location in ['/discover', '/library', '/create', '/create?premise=outer-disciple']) {
    testWidgets('$location at 2× text', (tester) async {
      await AppHarness().launch(tester, location: location, textScale: 2);
      await scrollThrough(tester);
      expect(tester.takeException(), isNull);
    });
  }

  // Spanish runs longer than English (S10): the main screens on a phone set to Spanish, at twice
  // the text size.
  for (final location in [
    '/discover',
    '/library',
    '/create?premise=outer-disciple',
    '/account',
    '/credits',
    '/privacy',
    '/story/story_ninth_peak',
  ]) {
    testWidgets('$location in Spanish at 2× text', (tester) async {
      tester.platformDispatcher.localesTestValue = const [Locale('es', 'ES')];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      await AppHarness().launch(tester, location: location, textScale: 2);
      expect(
        Localizations.localeOf(tester.element(find.byType(Scaffold).first)).languageCode,
        'es',
      );
      await scrollThrough(tester);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('the review and its sheets at 2× text', (tester) async {
    await AppHarness().launch(tester, location: '/create?premise=outer-disciple', textScale: 2);
    final draft = find.text(l10n.createDraftAction);
    await tester.scrollUntilVisible(draft, 400, scrollable: find.byType(Scrollable).first);
    await tester.pump(const Duration(seconds: 1));
    await tester.tap(draft);
    await settle(tester, frames: 12);
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    await scrollThrough(tester);
    expect(tester.takeException(), isNull);

    final advanced = find.text(l10n.reviewAdvanced);
    await tester.tap(advanced);
    await settle(tester, frames: 8);
    final sheet = find.descendant(of: find.byType(BottomSheet), matching: find.byType(Scrollable));
    for (var i = 0; i < 8; i++) {
      await tester.drag(sheet.first, const Offset(0, -500), warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 400));
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('memory at 2× text', (tester) async {
    await AppHarness().launch(tester, location: '/story/story_ninth_peak', textScale: 2);
    await tester.tap(find.byTooltip(l10n.storyMemory));
    await settle(tester, frames: 10);
    final list = find.byType(Scrollable).last;
    for (var i = 0; i < 12; i++) {
      await tester.drag(list, const Offset(0, -600), warnIfMissed: false);
      await tester.pump(const Duration(milliseconds: 400));
    }
    expect(tester.takeException(), isNull);
  });

  // The character sheet, a tab at a time, in English and in Spanish, whose words run longer.
  for (final language in ['en', 'es']) {
    testWidgets('the character sheet at 2× text ($language)', (tester) async {
      tester.platformDispatcher.localesTestValue = [Locale(language)];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final words = await AppLocalizations.delegate.load(Locale(language));
      await AppHarness().launch(tester, location: '/story/story_ninth_peak', textScale: 2);
      await tester.tap(find.byTooltip(words.storyStatus));
      await settle(tester, frames: 10);
      final list = find
          .descendant(of: find.byType(StatusScreen), matching: find.byType(Scrollable))
          .first;
      // Each tab is laid out whole as it opens, so a part that doesn't fit shows at once.
      for (final tab in SheetTab.values) {
        // The tabs scroll sideways at this size, so the one wanted is brought into view.
        final key = find.byKey(ValueKey('sheet.tab.${tab.name}'));
        await tester.ensureVisible(key);
        await tester.pump();
        await tester.tap(key);
        await settle(tester);
        expect(tester.takeException(), isNull, reason: tab.name);
      }
      for (var i = 0; i < 6; i++) {
        await tester.drag(list, const Offset(0, -600), warnIfMissed: false);
        await tester.pump(const Duration(milliseconds: 400));
      }
      expect(tester.takeException(), isNull);
    });
  }
}
