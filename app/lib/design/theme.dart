import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'accent.dart';
import 'tokens.dart';
import 'typography.dart';

/// Colors the app needs beyond Material's [ColorScheme]. Read with `context.lucid`.
@immutable
class LucidColors extends ThemeExtension<LucidColors> {
  const LucidColors({
    required this.accent,
    required this.onAccent,
    required this.accentSoft,
    required this.onAccentSoft,
    required this.background,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.shimmerBase,
    required this.shimmerHighlight,
    required this.vignette,
    required this.success,
    required this.caution,
    required this.danger,
  });

  /// The story's accent, readable as text on every surface of the theme.
  final Color accent;

  /// Text and icons on a solid [accent] fill.
  final Color onAccent;

  /// A quiet tint of the accent for selected states and badges.
  final Color accentSoft;

  /// Text and icons on [accentSoft].
  final Color onAccentSoft;

  final Color background;
  final Color textPrimary;
  final Color textSecondary;

  /// The quietest text that still reaches 4.5:1 on every surface.
  final Color textMuted;

  final Color shimmerBase;
  final Color shimmerHighlight;

  /// The dark edge of a picture's vignette, in both themes.
  final Color vignette;

  /// Outcome colors for scene details (a success, a partial result, a failure).
  final Color success;
  final Color caution;
  final Color danger;

  @override
  LucidColors copyWith({Color? accent, Color? onAccent, Color? accentSoft, Color? onAccentSoft}) =>
      LucidColors(
        accent: accent ?? this.accent,
        onAccent: onAccent ?? this.onAccent,
        accentSoft: accentSoft ?? this.accentSoft,
        onAccentSoft: onAccentSoft ?? this.onAccentSoft,
        background: background,
        textPrimary: textPrimary,
        textSecondary: textSecondary,
        textMuted: textMuted,
        shimmerBase: shimmerBase,
        shimmerHighlight: shimmerHighlight,
        vignette: vignette,
        success: success,
        caution: caution,
        danger: danger,
      );

  @override
  LucidColors lerp(LucidColors? other, double t) {
    if (other == null) return this;
    Color l(Color a, Color b) => Color.lerp(a, b, t)!;
    return LucidColors(
      accent: l(accent, other.accent),
      onAccent: l(onAccent, other.onAccent),
      accentSoft: l(accentSoft, other.accentSoft),
      onAccentSoft: l(onAccentSoft, other.onAccentSoft),
      background: l(background, other.background),
      textPrimary: l(textPrimary, other.textPrimary),
      textSecondary: l(textSecondary, other.textSecondary),
      textMuted: l(textMuted, other.textMuted),
      shimmerBase: l(shimmerBase, other.shimmerBase),
      shimmerHighlight: l(shimmerHighlight, other.shimmerHighlight),
      vignette: l(vignette, other.vignette),
      success: l(success, other.success),
      caution: l(caution, other.caution),
      danger: l(danger, other.danger),
    );
  }
}

extension LucidThemeContext on BuildContext {
  LucidColors get lucid => Theme.of(this).extension<LucidColors>()!;
  LucidTextStyles get lucidText => Theme.of(this).extension<LucidTextStyles>()!;
}

/// Builds the dark ("ink") and light ("paper") themes for any accent.
abstract final class AppTheme {
  static final _cache = <(Brightness, GenreAccent), ThemeData>{};

  static ThemeData dark([GenreAccent accent = GenreAccent.lucid]) => build(Brightness.dark, accent);

  static ThemeData light([GenreAccent accent = GenreAccent.lucid]) =>
      build(Brightness.light, accent);

  static ThemeData build(Brightness brightness, GenreAccent accent) =>
      _cache.putIfAbsent((brightness, accent), () => _build(brightness, accent));

  static ThemeData _build(Brightness brightness, GenreAccent genreAccent) {
    final dark = brightness == Brightness.dark;
    final background = dark ? Palette.inkBackground : Palette.paperBackground;
    final surface = dark ? Palette.inkSurface : Palette.paperSurface;
    final lowest = dark ? Palette.inkContainerLowest : Palette.paperContainerLowest;
    final low = dark ? Palette.inkContainerLow : Palette.paperContainerLow;
    final container = dark ? Palette.inkContainer : Palette.paperContainer;
    final high = dark ? Palette.inkContainerHigh : Palette.paperContainerHigh;
    final highest = dark ? Palette.inkContainerHighest : Palette.paperContainerHighest;
    final textPrimary = dark ? Palette.inkTextPrimary : Palette.paperTextPrimary;
    final textSecondary = dark ? Palette.inkTextSecondary : Palette.paperTextSecondary;
    final textMuted = dark ? Palette.inkTextMuted : Palette.paperTextMuted;
    final outline = dark ? Palette.inkOutline : Palette.paperOutline;
    final outlineVariant = dark ? Palette.inkOutlineVariant : Palette.paperOutlineVariant;
    final error = dark ? Palette.inkError : Palette.paperError;

    final accent = accentFor(genreAccent, brightness);
    final onAccent = onColor(accent);
    final accentSoft = blend(surface, accent, dark ? 0.16 : 0.14);
    final onAccentSoft = ensureContrast(accent, accentSoft);
    final errorContainer = blend(surface, error, 0.16);

    final scheme = ColorScheme(
      brightness: brightness,
      primary: accent,
      onPrimary: onAccent,
      primaryContainer: accentSoft,
      onPrimaryContainer: onAccentSoft,
      secondary: textSecondary,
      onSecondary: background,
      secondaryContainer: highest,
      onSecondaryContainer: textPrimary,
      tertiary: accent,
      onTertiary: onAccent,
      tertiaryContainer: accentSoft,
      onTertiaryContainer: onAccentSoft,
      error: error,
      onError: onColor(error),
      errorContainer: errorContainer,
      onErrorContainer: ensureContrast(error, errorContainer),
      surface: surface,
      onSurface: textPrimary,
      onSurfaceVariant: textSecondary,
      surfaceDim: background,
      surfaceBright: highest,
      surfaceContainerLowest: lowest,
      surfaceContainerLow: low,
      surfaceContainer: container,
      surfaceContainerHigh: high,
      surfaceContainerHighest: highest,
      outline: outline,
      outlineVariant: outlineVariant,
      shadow: const Color(0xFF000000),
      scrim: const Color(0xFF000000),
      inverseSurface: dark ? Palette.paperSurface : Palette.inkSurface,
      onInverseSurface: dark ? Palette.paperTextPrimary : Palette.inkTextPrimary,
      inversePrimary: accentFor(genreAccent, dark ? Brightness.light : Brightness.dark),
      surfaceTint: Colors.transparent,
    );

    final text = buildTextTheme(primary: textPrimary, secondary: textSecondary);
    final colors = LucidColors(
      accent: accent,
      onAccent: onAccent,
      accentSoft: accentSoft,
      onAccentSoft: onAccentSoft,
      background: background,
      textPrimary: textPrimary,
      textSecondary: textSecondary,
      textMuted: textMuted,
      shimmerBase: dark ? Palette.inkContainer : Palette.paperContainerLow,
      shimmerHighlight: dark ? Palette.inkContainerHighest : Palette.paperContainerHighest,
      vignette: const Color(0xFF05060A),
      success: ensureContrast(const Color(0xFF5CC98A), highest),
      caution: ensureContrast(const Color(0xFFE5B454), highest),
      danger: ensureContrast(error, highest),
    );
    final styles = LucidTextStyles.build(
      primary: textPrimary,
      secondary: textSecondary,
      accent: accent,
    );

    const buttonShape = RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(14)));
    const buttonPadding = EdgeInsets.symmetric(horizontal: 20, vertical: 14);
    final buttonText = text.labelLarge!.copyWith(fontSize: 15);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      canvasColor: background,
      fontFamily: Fonts.sans,
      textTheme: text,
      primaryTextTheme: text,
      extensions: [colors, styles],
      splashFactory: InkSparkle.splashFactory,
      visualDensity: VisualDensity.standard,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      appBarTheme: AppBarTheme(
        backgroundColor: background,
        foregroundColor: textPrimary,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: text.titleLarge,
        systemOverlayStyle: dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: surface,
        surfaceTintColor: Colors.transparent,
        indicatorColor: accentSoft,
        elevation: 0,
        height: 68,
        labelTextStyle: WidgetStateProperty.resolveWith(
          (states) => text.labelMedium!.copyWith(
            color: states.contains(WidgetState.selected) ? textPrimary : textSecondary,
          ),
        ),
        iconTheme: WidgetStateProperty.resolveWith(
          (states) => IconThemeData(
            size: 24,
            color: states.contains(WidgetState.selected) ? onAccentSoft : textSecondary,
          ),
        ),
      ),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: surface,
        indicatorColor: accentSoft,
        selectedIconTheme: IconThemeData(color: onAccentSoft),
        unselectedIconTheme: IconThemeData(color: textSecondary),
        selectedLabelTextStyle: text.labelMedium!.copyWith(color: textPrimary),
        unselectedLabelTextStyle: text.labelMedium!.copyWith(color: textSecondary),
      ),
      cardTheme: CardThemeData(
        color: low,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: Radii.card,
          side: BorderSide(color: outlineVariant),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          shape: buttonShape,
          padding: buttonPadding,
          minimumSize: const Size(64, Layout.minTouch),
          textStyle: buttonText,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          shape: buttonShape,
          padding: buttonPadding,
          minimumSize: const Size(64, Layout.minTouch),
          foregroundColor: textPrimary,
          side: BorderSide(color: outline),
          textStyle: buttonText,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          shape: buttonShape,
          minimumSize: const Size(48, Layout.minTouch),
          foregroundColor: accent,
          textStyle: buttonText,
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          foregroundColor: textSecondary,
          minimumSize: const Size.square(Layout.minTouch),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: container,
        hintStyle: text.bodyLarge!.copyWith(color: textMuted),
        labelStyle: text.bodyLarge!.copyWith(color: textSecondary),
        floatingLabelStyle: text.bodyMedium!.copyWith(color: accent),
        helperStyle: text.bodySmall,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: const OutlineInputBorder(borderRadius: Radii.field, borderSide: BorderSide.none),
        enabledBorder: OutlineInputBorder(
          borderRadius: Radii.field,
          borderSide: BorderSide(color: outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: Radii.field,
          borderSide: BorderSide(color: accent, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: Radii.field,
          borderSide: BorderSide(color: error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: Radii.field,
          borderSide: BorderSide(color: error, width: 1.5),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: container,
        selectedColor: accentSoft,
        side: BorderSide(color: outlineVariant),
        labelStyle: text.labelLarge!.copyWith(color: textPrimary),
        shape: const StadiumBorder(),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: low,
        surfaceTintColor: Colors.transparent,
        modalBackgroundColor: low,
        showDragHandle: true,
        dragHandleColor: outline,
        shape: const RoundedRectangleBorder(borderRadius: Radii.sheet),
        clipBehavior: Clip.antiAlias,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: low,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.xl)),
        titleTextStyle: text.headlineSmall,
        contentTextStyle: text.bodyLarge!.copyWith(color: textSecondary),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: dark ? Palette.inkContainerHighest : Palette.inkSurface,
        contentTextStyle: text.bodyMedium!.copyWith(color: Palette.inkTextPrimary),
        actionTextColor: accentFor(genreAccent, Brightness.dark),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: textSecondary,
        textColor: textPrimary,
        titleTextStyle: text.bodyLarge,
        subtitleTextStyle: text.bodyMedium!.copyWith(color: textSecondary),
        contentPadding: const EdgeInsets.symmetric(horizontal: Space.gutter),
        minVerticalPadding: 12,
      ),
      dividerTheme: DividerThemeData(color: outlineVariant, thickness: 1, space: 1),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: accent,
        linearTrackColor: container,
        circularTrackColor: Colors.transparent,
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: dark ? Palette.inkContainerHighest : Palette.inkSurface,
          borderRadius: BorderRadius.circular(Radii.sm),
        ),
        textStyle: text.bodySmall!.copyWith(color: Palette.inkTextPrimary),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: SegmentedButton.styleFrom(
          selectedBackgroundColor: accentSoft,
          selectedForegroundColor: onAccentSoft,
          foregroundColor: textSecondary,
          side: BorderSide(color: outlineVariant),
          textStyle: text.labelLarge,
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? onAccent : textSecondary,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? accent : highest,
        ),
        trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
      ),
    );
  }
}
