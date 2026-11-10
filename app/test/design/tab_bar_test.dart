import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';

import '../helpers.dart';

/// The glass tabs at the bottom of a phone, measured in the app's own font, so what fits here
/// is what fits on a phone.
void main() {
  setUpAll(() async {
    final inter = FontLoader(Fonts.sans);
    for (final weight in ['Regular', 'Medium', 'SemiBold']) {
      inter.addFont(rootBundle.load('assets/fonts/Inter-$weight.ttf'));
    }
    await inter.load();
  });

  List<LucidTab> tabsOf(AppLocalizations l10n) => [
    LucidTab(
      icon: Icons.explore_outlined,
      selectedIcon: Icons.explore_rounded,
      label: l10n.navDiscover,
    ),
    LucidTab(
      icon: Icons.auto_stories_outlined,
      selectedIcon: Icons.auto_stories_rounded,
      label: l10n.navLibrary,
    ),
    LucidTab(
      icon: Icons.person_outline_rounded,
      selectedIcon: Icons.person_rounded,
      label: l10n.navAccount,
    ),
  ];

  Widget bar(
    List<LucidTab> tabs, {
    int selected = 0,
    ValueChanged<int>? onSelected,
    double textScale = 1,
    Brightness brightness = Brightness.dark,
  }) => wrap(
    Align(
      alignment: Alignment.bottomCenter,
      child: LucidTabBar(tabs: tabs, selected: selected, onSelected: onSelected ?? (_) {}),
    ),
    textScale: textScale,
    brightness: brightness,
  );

  /// Whether a tab's name is drawn whole.
  bool whole(WidgetTester tester, String label) =>
      !tester.renderObject<RenderParagraph>(find.text(label)).didExceedMaxLines;

  for (final locale in AppLocalizations.supportedLocales) {
    testWidgets('on a phone every tab keeps its whole name in "$locale"', (tester) async {
      final l10n = await AppLocalizations.delegate.load(locale);
      final tabs = tabsOf(l10n);
      for (final width in [390.0, 360.0]) {
        usePhone(tester, size: Size(width, 780));
        for (var selected = 0; selected < tabs.length; selected++) {
          await tester.pumpWidget(bar(tabs, selected: selected));
          await tester.pump(Motion.base);
          expect(tester.takeException(), isNull);
          for (final tab in tabs) {
            expect(find.text(tab.label), findsOneWidget, reason: '$width: ${tab.label}');
            expect(whole(tester, tab.label), isTrue, reason: '$width: ${tab.label} is cut');
          }
        }
      }
    });
  }

  testWidgets('without room for every name, only the lit tab keeps its own', (tester) async {
    final l10n = await english();
    final tabs = tabsOf(l10n);
    final handle = tester.ensureSemantics();
    usePhone(tester);
    await tester.pumpWidget(bar(tabs, selected: 1, textScale: 2));
    await tester.pump(Motion.base);
    expect(tester.takeException(), isNull);
    expect(find.text(l10n.navLibrary), findsOneWidget);
    expect(find.text(l10n.navDiscover), findsNothing);
    expect(find.text(l10n.navAccount), findsNothing);
    // The others are still named for a screen reader, and on a long press.
    for (final (i, tab) in tabs.indexed) {
      expect(
        tester.getSemantics(find.bySemanticsLabel(tab.label)),
        isSemantics(isButton: true, isSelected: i == 1, hasTapAction: true),
      );
      expect(find.byTooltip(tab.label), findsOneWidget);
      expect(
        tester.getSize(find.byTooltip(tab.label)).shortestSide,
        greaterThanOrEqualTo(Layout.minTouch),
      );
    }
    handle.dispose();
  });

  testWidgets('a name too long for the room left ends in an ellipsis', (tester) async {
    const tabs = [
      LucidTab(icon: Icons.explore_outlined, selectedIcon: Icons.explore_rounded, label: 'Ideas'),
      LucidTab(
        icon: Icons.auto_stories_outlined,
        selectedIcon: Icons.auto_stories_rounded,
        label: 'Everything you have ever played',
      ),
      LucidTab(icon: Icons.person_outline, selectedIcon: Icons.person, label: 'You'),
    ];
    usePhone(tester, size: const Size(320, 640));
    await tester.pumpWidget(bar(tabs, selected: 1, textScale: 1.6));
    await tester.pump(Motion.base);
    expect(tester.takeException(), isNull);
    expect(whole(tester, 'Everything you have ever played'), isFalse);
    // The other two are still there to tap.
    expect(find.byIcon(Icons.explore_outlined), findsOneWidget);
    expect(find.byIcon(Icons.person_outline), findsOneWidget);
  });

  testWidgets('a tap picks a tab, from its icon or its name', (tester) async {
    final l10n = await english();
    final tabs = tabsOf(l10n);
    final picked = <int>[];
    usePhone(tester);
    await tester.pumpWidget(bar(tabs, onSelected: picked.add));
    await tester.tap(find.text(l10n.navLibrary));
    await tester.tap(find.byIcon(Icons.person_outline_rounded));
    expect(picked, [1, 2]);
    // The tab the player is on shows its filled icon.
    expect(find.byIcon(Icons.explore_rounded), findsOneWidget);
    expect(find.byIcon(Icons.auto_stories_outlined), findsOneWidget);
  });

  testWidgets('the lit tab wears the end of the gradient that reads in its theme', (tester) async {
    final l10n = await english();
    final tabs = tabsOf(l10n);
    usePhone(tester);
    for (final brightness in Brightness.values) {
      await tester.pumpWidget(bar(tabs, brightness: brightness));
      await tester.pump(const Duration(milliseconds: 400));
      final colors = AppTheme.build(brightness, GenreAccent.lucid).extension<LucidColors>()!;
      expect(
        tester.widget<Text>(find.text(l10n.navDiscover)).style!.color,
        brightness == Brightness.dark ? colors.accentHi : colors.accentLo,
      );
      expect(tester.widget<Text>(find.text(l10n.navLibrary)).style!.color, colors.textMuted);
    }
  });

  testWidgets('the bar keeps clear of the system\'s own space at the foot', (tester) async {
    final l10n = await english();
    usePhone(tester);
    await tester.pumpWidget(
      wrap(
        MediaQuery(
          data: const MediaQueryData(size: Size(390, 844), padding: EdgeInsets.only(bottom: 34)),
          child: Align(
            alignment: Alignment.bottomCenter,
            child: LucidTabBar(tabs: tabsOf(l10n), selected: 0, onSelected: (_) {}),
          ),
        ),
      ),
    );
    final glass = tester.getRect(find.byType(Glass));
    expect(844 - glass.bottom, greaterThanOrEqualTo(34));
    expect(glass.left, Layout.barInset);
    expect(glass.right, 390 - Layout.barInset);
  });
}
