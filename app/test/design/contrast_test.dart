import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/story/record_widgets.dart';

/// Every text color the themes use reaches 4.5:1 on every surface it can sit on, in both
/// themes and for every genre accent (WCAG AA for body text).
void main() {
  for (final brightness in Brightness.values) {
    for (final accent in GenreAccent.values) {
      test('$brightness ${accent.name} meets 4.5:1', () {
        final theme = AppTheme.build(brightness, accent);
        final scheme = theme.colorScheme;
        final c = theme.extension<LucidColors>()!;
        final surfaces = {
          'background': c.background,
          'surface': scheme.surface,
          'lowest': scheme.surfaceContainerLowest,
          'low': scheme.surfaceContainerLow,
          'container': scheme.surfaceContainer,
          'high': scheme.surfaceContainerHigh,
          'highest': scheme.surfaceContainerHighest,
        };
        void check(String name, Color fg, Color bg) {
          final ratio = contrastRatio(fg, bg);
          expect(
            ratio,
            greaterThanOrEqualTo(4.5),
            reason: '$name is ${ratio.toStringAsFixed(2)}:1',
          );
        }

        for (final MapEntry(key: surface, value: bg) in surfaces.entries) {
          check('textPrimary on $surface', c.textPrimary, bg);
          check('textSecondary on $surface', c.textSecondary, bg);
          check('textMuted on $surface', c.textMuted, bg);
          check('accent on $surface', c.accent, bg);
          check('error on $surface', scheme.error, bg);
        }
        check('onAccent on accent', c.onAccent, c.accent);
        check('onAccentSoft on accentSoft', c.onAccentSoft, c.accentSoft);
        check('textPrimary on accentSoft', c.textPrimary, c.accentSoft);
        check('textSecondary on accentSoft', c.textSecondary, c.accentSoft);
        check('onErrorContainer on errorContainer', scheme.onErrorContainer, scheme.errorContainer);
        for (final (name, color) in [
          ('success', c.success),
          ('caution', c.caution),
          ('danger', c.danger),
        ]) {
          check('$name on highest', color, scheme.surfaceContainerHighest);
        }
      });
    }
  }

  test('gold lettering reads on the page and on a card, at both ends of the gradient', () {
    for (final brightness in Brightness.values) {
      for (final accent in GenreAccent.values) {
        final theme = AppTheme.build(brightness, accent);
        final scheme = theme.colorScheme;
        final c = theme.extension<LucidColors>()!;
        final name = '${brightness.name} ${accent.name}';
        expect((c.accentHi, c.accentLo), accentEnds(accent, brightness));
        // The gradient runs from bright to deep, with the accent between.
        expect(c.accentHi.computeLuminance(), greaterThan(c.accent.computeLuminance()));
        expect(c.accentLo.computeLuminance(), lessThan(c.accent.computeLuminance()));
        for (final end in [c.accentHi, c.accentLo]) {
          for (final bg in [
            c.background,
            scheme.surface,
            scheme.surfaceContainerLowest,
            scheme.surfaceContainerLow,
          ]) {
            expect(contrastRatio(end, bg), greaterThanOrEqualTo(4.5), reason: name);
          }
          // Text and icons on the gradient itself: a filled pill, the send button.
          expect(contrastRatio(c.onAccent, end), greaterThanOrEqualTo(4.5), reason: name);
        }
      }
    }
  });

  test('the lit tab reads on its own light, over the glass', () {
    for (final brightness in Brightness.values) {
      for (final accent in GenreAccent.values) {
        final c = AppTheme.build(brightness, accent).extension<LucidColors>()!;
        final glass = Color.alphaBlend(c.glass, c.background);
        final lit = Color.alphaBlend(c.accent.withValues(alpha: LucidTabBar.litWash), glass);
        final name = '${brightness.name} ${accent.name}';
        expect(
          contrastRatio(LucidTabBar.litForeground(c, brightness), lit),
          greaterThanOrEqualTo(4.5),
          reason: name,
        );
        // The other tabs, on the glass alone.
        expect(contrastRatio(c.textMuted, glass), greaterThanOrEqualTo(4.5), reason: name);
      }
    }
  });

  test('the words of Character and Memory read on a chip\'s wash and on a card', () {
    for (final brightness in Brightness.values) {
      for (final accent in GenreAccent.values) {
        final theme = AppTheme.build(brightness, accent);
        final c = theme.extension<LucidColors>()!;
        final card = theme.colorScheme.surfaceContainerLow;
        final name = '${brightness.name} ${accent.name}';
        for (final tone in [c.success, c.caution, c.danger, c.accent]) {
          // A chip of how they are: its words in its own color, over a wash of it on the page.
          final wash = Color.alphaBlend(tone.withValues(alpha: RecordChip.wash), c.background);
          expect(contrastRatio(tone, wash), greaterThanOrEqualTo(4.5), reason: name);
          // A word at an entry's edge: "Ready in 2 hours", "Gift", "Weakness".
          expect(contrastRatio(tone, card), greaterThanOrEqualTo(4.5), reason: name);
          // A chip inside an entry, on Memory: how someone takes them, what they know of a
          // rumor.
          final onCard = Color.alphaBlend(tone.withValues(alpha: RecordChip.wash), card);
          expect(contrastRatio(tone, onCard), greaterThanOrEqualTo(4.5), reason: name);
        }
      }
    }
  });

  test('cover text on the dark scrim meets 4.5:1 for every accent', () {
    for (final accent in GenreAccent.values) {
      final color = accentFor(accent, Brightness.dark);
      expect(contrastRatio(color, Palette.inkBackground), greaterThanOrEqualTo(4.5));
    }
    expect(
      contrastRatio(Palette.inkTextSecondary, Palette.inkBackground),
      greaterThanOrEqualTo(4.5),
    );
  });

  test('ensureContrast keeps the hue', () {
    const seed = Color(0xFF5CC9A7);
    final adjusted = ensureContrast(seed, Palette.paperBackground);
    expect(contrastRatio(adjusted, Palette.paperBackground), greaterThanOrEqualTo(4.5));
    expect(HSLColor.fromColor(adjusted).hue, closeTo(HSLColor.fromColor(seed).hue, 1));
  });
}
