import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/story/memory_screen.dart';
import 'package:playable_anime/features/story/sheet_view.dart';
import 'package:playable_anime/features/story/status_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// Every new screen at twice the text size, on a phone: nothing clips or overflows (DESIGN.md,
/// Accessibility).
void main() {
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

  // The review and each kind of sheet it opens, in English and in Spanish, whose words run
  // longer.
  for (final language in ['en', 'es']) {
    testWidgets('the review and its sheets at 2× text ($language)', (tester) async {
      tester.platformDispatcher.localesTestValue = [Locale(language)];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final words = await AppLocalizations.delegate.load(Locale(language));
      await AppHarness().launch(tester, location: '/create?premise=outer-disciple', textScale: 2);
      final list = find.byType(Scrollable).first;
      final draft = find.text(words.createDraftAction);
      await tester.scrollUntilVisible(draft, 400, scrollable: list);
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(draft);
      await settle(tester, frames: 12);
      expect(find.text(words.reviewTitle), findsOneWidget);
      await scrollThrough(tester);
      expect(tester.takeException(), isNull);

      // Back to the top, then each sheet: opened, scrolled through, and closed.
      for (var i = 0; i < 12; i++) {
        await tester.drag(list, const Offset(0, 600), warnIfMissed: false);
        await tester.pump(const Duration(milliseconds: 400));
      }
      final rows = {
        'the name and the age': find.text('Lin Feng'),
        'a rule, with its switch and Remove': find.text('The dead stay dead.'),
        'a row the storyteller changes': find.textContaining('Fair: the sword'),
        'a choice that costs': find.widgetWithText(ChoiceChip, words.giftRare),
      };
      for (final MapEntry(key: what, value: row) in rows.entries) {
        await tester.scrollUntilVisible(row, 300, scrollable: list);
        await tester.pump(const Duration(seconds: 1));
        await tester.tap(row);
        await settle(tester, frames: 8);
        expect(find.byType(BottomSheet), findsOneWidget, reason: what);
        final sheet = find.descendant(
          of: find.byType(BottomSheet),
          matching: find.byType(Scrollable),
        );
        for (var i = 0; i < 6; i++) {
          await tester.drag(sheet.first, const Offset(0, -500), warnIfMissed: false);
          await tester.pump(const Duration(milliseconds: 400));
        }
        expect(tester.takeException(), isNull, reason: what);
        // At this size a sheet can fill the screen, with no scrim left to tap.
        Navigator.of(tester.element(find.byType(BottomSheet))).pop();
        await settle(tester, frames: 10);
        expect(find.byType(BottomSheet), findsNothing, reason: what);
      }
    });
  }

  // Memory with every group opened, in English and in Spanish, whose words run longer.
  for (final language in ['en', 'es']) {
    testWidgets('memory at 2× text ($language)', (tester) async {
      tester.platformDispatcher.localesTestValue = [Locale(language)];
      addTearDown(tester.platformDispatcher.clearLocalesTestValue);
      final words = await AppLocalizations.delegate.load(Locale(language));
      await AppHarness().launch(tester, location: '/story/story_ninth_peak', textScale: 2);
      await tester.tap(find.byTooltip(words.storyMemory));
      await settle(tester, frames: 10);
      final list = find
          .descendant(of: find.byType(MemoryScreen), matching: find.byType(Scrollable))
          .first;
      // The threads that ended and the people past the first few are opened on the way down.
      for (final key in ['memory.closed', 'memory.more.people']) {
        final button = find.byKey(ValueKey(key));
        await tester.scrollUntilVisible(button, 300, scrollable: list);
        await tester.pump(const Duration(milliseconds: 400));
        await tester.tap(button);
        await settle(tester);
        expect(tester.takeException(), isNull, reason: key);
      }
      for (var i = 0; i < 16; i++) {
        await tester.drag(list, const Offset(0, -600), warnIfMissed: false);
        await tester.pump(const Duration(milliseconds: 400));
      }
      expect(tester.takeException(), isNull);
    });
  }

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
