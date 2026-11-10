import 'package:flutter/material.dart';

/// Bundled font families (pubspec.yaml). Literata for reading, Literata Display for titles at large
/// sizes, Inter for the interface.
abstract final class Fonts {
  static const serif = 'Literata';
  static const display = 'LiterataDisplay';
  static const sans = 'Inter';
}

/// The Material text theme: display and headline sizes in the display serif, everything else in
/// the sans. Sizes are in logical pixels and scale with the system text size (dynamic type).
TextTheme buildTextTheme({required Color primary, required Color secondary}) {
  TextStyle display(double size, double height, {double spacing = 0}) => TextStyle(
    fontFamily: Fonts.display,
    fontWeight: FontWeight.w500,
    fontSize: size,
    height: height / size,
    letterSpacing: spacing,
    color: primary,
  );
  TextStyle sans(
    double size,
    double height, {
    FontWeight weight = FontWeight.w400,
    double spacing = 0,
    Color? color,
  }) => TextStyle(
    fontFamily: Fonts.sans,
    fontWeight: weight,
    fontSize: size,
    height: height / size,
    letterSpacing: spacing,
    color: color ?? primary,
  );

  return TextTheme(
    displayLarge: display(44, 52, spacing: -0.6),
    displayMedium: display(36, 44, spacing: -0.4),
    displaySmall: display(30, 38, spacing: -0.2),
    headlineLarge: display(28, 36, spacing: -0.2),
    headlineMedium: display(24, 32),
    headlineSmall: display(21, 28),
    titleLarge: sans(19, 26, weight: FontWeight.w600, spacing: -0.1),
    titleMedium: sans(16, 22, weight: FontWeight.w600),
    titleSmall: sans(14, 20, weight: FontWeight.w600),
    bodyLarge: sans(16, 24),
    bodyMedium: sans(14, 20),
    bodySmall: sans(12.5, 18, color: secondary),
    labelLarge: sans(14, 20, weight: FontWeight.w600, spacing: 0.1),
    labelMedium: sans(12, 16, weight: FontWeight.w500, spacing: 0.3),
    labelSmall: sans(11, 16, weight: FontWeight.w600, spacing: 0.8),
  );
}

/// Story-specific text styles that Material's text theme has no slot for.
@immutable
class LucidTextStyles extends ThemeExtension<LucidTextStyles> {
  const LucidTextStyles({
    required this.narration,
    required this.playerAction,
    required this.overline,
    required this.meta,
  });

  factory LucidTextStyles.build({
    required Color primary,
    required Color secondary,
    required Color accent,
  }) => LucidTextStyles(
    narration: TextStyle(
      fontFamily: Fonts.serif,
      fontSize: 18,
      height: 1.62,
      letterSpacing: 0.05,
      color: primary,
    ),
    playerAction: TextStyle(
      fontFamily: Fonts.serif,
      fontStyle: FontStyle.italic,
      fontSize: 16.5,
      height: 1.45,
      color: secondary,
    ),
    overline: TextStyle(
      fontFamily: Fonts.sans,
      fontWeight: FontWeight.w600,
      fontSize: 11,
      height: 16 / 11,
      letterSpacing: 1.4,
      color: accent,
    ),
    meta: TextStyle(
      fontFamily: Fonts.sans,
      fontWeight: FontWeight.w500,
      fontSize: 12.5,
      height: 16 / 12.5,
      letterSpacing: 0.2,
      color: secondary,
      fontFeatures: const [FontFeature.tabularFigures()],
    ),
  );

  /// Narration: the serif at a comfortable reading size and line height.
  final TextStyle narration;

  /// What the player did, shown above the narration it caused.
  final TextStyle playerAction;

  /// Small uppercase labels such as a genre ("CULTIVATION"). Apply `toUpperCase()` to the text.
  final TextStyle overline;

  /// Compact metadata such as "+8 h" or "Turn 12", with tabular figures.
  final TextStyle meta;

  @override
  LucidTextStyles copyWith({
    TextStyle? narration,
    TextStyle? playerAction,
    TextStyle? overline,
    TextStyle? meta,
  }) => LucidTextStyles(
    narration: narration ?? this.narration,
    playerAction: playerAction ?? this.playerAction,
    overline: overline ?? this.overline,
    meta: meta ?? this.meta,
  );

  @override
  LucidTextStyles lerp(LucidTextStyles? other, double t) {
    if (other == null) return this;
    return LucidTextStyles(
      narration: TextStyle.lerp(narration, other.narration, t)!,
      playerAction: TextStyle.lerp(playerAction, other.playerAction, t)!,
      overline: TextStyle.lerp(overline, other.overline, t)!,
      meta: TextStyle.lerp(meta, other.meta, t)!,
    );
  }
}
