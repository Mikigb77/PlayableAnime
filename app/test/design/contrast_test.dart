import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';

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
