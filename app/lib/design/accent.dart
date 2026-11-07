import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// The accent family a story is tinted with: picked from its genre, unless the player chose
/// another for the story in its settings (S13).
enum GenreAccent {
  lucid(Palette.lucidGold),
  jade(Color(0xFF5CC9A7)),
  azure(Color(0xFF84A9F5)),
  ember(Color(0xFFF08A5D)),
  violet(Color(0xFFB08CFA)),
  crimson(Color(0xFFEF7A82)),
  cyan(Color(0xFF4FCFE0)),
  orchid(Color(0xFFDD8BE8)),
  // No genre picks these: they are there for the player to choose (S13).
  lime(Color(0xFFA8D46F)),
  rose(Color(0xFFF390B8)),
  silver(Color(0xFFB7BFCC));

  const GenreAccent(this.seed);

  /// The accent as tuned for the dark theme. The light theme darkens it (see [accentFor]).
  final Color seed;

  /// Every accent in the order a story's settings offer them (S13): around the color wheel from
  /// red, then silver.
  static const palette = [
    crimson,
    ember,
    lucid,
    lime,
    jade,
    cyan,
    azure,
    violet,
    orchid,
    rose,
    silver,
  ];

  /// A story's accent: the one the player chose for it ([chosen], an accent's name), or else its
  /// genre's. A name this app doesn't know, say from a newer app, counts as no choice.
  static GenreAccent of({String? genre, String? chosen}) => byNameOrNull(chosen) ?? forGenre(genre);

  /// The accent called [name], or null when there is none.
  static GenreAccent? byNameOrNull(String? name) => name == null ? null : _byName[name];

  static final _byName = values.asNameMap();

  /// Picks the accent for a genre label such as "cultivation", "a modern city with hidden
  /// vampires" or, in Spanish (S10), "Reencarnación". Unknown genres get the app's own accent.
  /// Nothing in the app depends on a genre beyond this tint (G5).
  static GenreAccent forGenre(String? genre) {
    final g = (genre ?? '').toLowerCase();
    if (g.isEmpty) return lucid;
    for (final (accent, pattern) in _rules) {
      if (pattern.hasMatch(g)) return accent;
    }
    return lucid;
  }

  // Order matters: "urban fantasy" is supernatural before it is fantasy. Each rule matches the
  // English and the Spanish words, since a genre label comes in the language it was written in.
  static final _rules = <(GenreAccent, RegExp)>[
    (
      orchid,
      RegExp(
        r'supernatural|occult|urban|vampire|horror|ghost|hidden|witch'
        r'|sobrenatural|ocult|vampir|terror|fantasma|bruj',
      ),
    ),
    (violet, RegExp(r'reincarnat|isekai|rebirth|regress|transmigrat|reborn|reencarna|renac')),
    (jade, RegExp(r'cultivat|xianxia|wuxia|murim|martial|immortal|cultivo|marcial|inmortal')),
    (azure, RegExp(r'knight|aura|chivalr|paladin|superpower|superhero|caballer|superpoder|superh')),
    (
      cyan,
      RegExp(r'\bsci|space|cyber|\bstar|mecha|future|android|robot|ciencia|espacio|ciber|futur'),
    ),
    (
      crimson,
      RegExp(
        r'crime|mafia|noir|thriller|vendetta|modern|grounded|detective|mob\b'
        r'|crimen|realista|mafios|polic',
      ),
    ),
    (
      ember,
      RegExp(
        r'monster|races|dungeon|fantasy|magic|dragon|sorcer|beast|apocalyp|wasteland'
        r'|monstruo|razas|mazmorra|fantas|magia|drag|hechic|bestia|apocal|yermo',
      ),
    ),
  ];
}

/// WCAG 2 contrast ratio between two opaque colors, from 1 to 21.
double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

/// Moves [color]'s lightness away from [background] until the pair reaches [minRatio], keeping
/// its hue and saturation. Text in an accent color uses this, so every genre accent stays
/// readable in both themes.
Color ensureContrast(Color color, Color background, {double minRatio = 4.5}) {
  var hsl = HSLColor.fromColor(color);
  final lighten = background.computeLuminance() < 0.18;
  for (var i = 0; i < 100 && contrastRatio(hsl.toColor(), background) < minRatio; i++) {
    final next = (hsl.lightness + (lighten ? 0.01 : -0.01)).clamp(0.0, 1.0);
    hsl = hsl.withLightness(next);
  }
  return hsl.toColor();
}

/// Whichever of near-black ink and white reads better on [background].
Color onColor(Color background) {
  const dark = Palette.inkBackground;
  const light = Color(0xFFFFFFFF);
  return contrastRatio(dark, background) >= contrastRatio(light, background) ? dark : light;
}

/// Alpha-blends [top] over [bottom] at [opacity] into an opaque color.
Color blend(Color bottom, Color top, double opacity) =>
    Color.alphaBlend(top.withValues(alpha: opacity), bottom);

/// The accent as used in a theme of [brightness]: readable as text on every surface of that theme.
Color accentFor(GenreAccent accent, Brightness brightness) {
  if (brightness == Brightness.dark) {
    return ensureContrast(accent.seed, Palette.inkContainerHighest);
  }
  // Paper backgrounds need a deeper, slightly richer tone of the same hue.
  final hsl = HSLColor.fromColor(accent.seed);
  final deeper = hsl.withSaturation(math.min(1, hsl.saturation * 1.05)).toColor();
  return ensureContrast(deeper, Palette.paperContainerHighest);
}
