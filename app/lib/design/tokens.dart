import 'package:flutter/widgets.dart';

/// Raw design tokens. Widgets read colors through the theme ([LucidColors], [ColorScheme]) rather
/// than from here, so the light theme and per-story accents work. See app/DESIGN.md.
abstract final class Palette {
  // Dark ("ink"): deep blue-black layers, warm parchment text.
  static const inkBackground = Color(0xFF0B0D12);
  static const inkSurface = Color(0xFF11141B);
  static const inkContainerLowest = Color(0xFF0E1117);
  static const inkContainerLow = Color(0xFF151922);
  static const inkContainer = Color(0xFF1A1F29);
  static const inkContainerHigh = Color(0xFF212733);
  static const inkContainerHighest = Color(0xFF29303D);
  static const inkOutline = Color(0xFF3D4555);
  static const inkOutlineVariant = Color(0xFF272D39);
  static const inkTextPrimary = Color(0xFFEDE8DF);
  static const inkTextSecondary = Color(0xFFB4B8C3);
  static const inkTextMuted = Color(0xFF9399A6);
  static const inkError = Color(0xFFF4878A);

  // Light ("paper"): warm off-white layers, ink text.
  static const paperBackground = Color(0xFFF6F3ED);
  static const paperSurface = Color(0xFFFBF9F5);
  static const paperContainerLowest = Color(0xFFFFFFFF);
  static const paperContainerLow = Color(0xFFF1EDE5);
  static const paperContainer = Color(0xFFEBE6DC);
  static const paperContainerHigh = Color(0xFFE5DFD4);
  static const paperContainerHighest = Color(0xFFDED7CA);
  static const paperOutline = Color(0xFF8C8578);
  static const paperOutlineVariant = Color(0xFFD3CCBF);
  static const paperTextPrimary = Color(0xFF1B1D23);
  static const paperTextSecondary = Color(0xFF474B56);
  static const paperTextMuted = Color(0xFF545965);
  static const paperError = Color(0xFFB3261E);

  /// The app's own accent, used outside a story.
  static const lucidGold = Color(0xFFE3B66B);
}

/// Spacing on a 4 pt grid.
abstract final class Space {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 48;

  /// Side padding of a screen on a phone.
  static const double gutter = 20;
}

abstract final class Radii {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double pill = 999;

  static const card = BorderRadius.all(Radius.circular(lg));
  static const picture = BorderRadius.all(Radius.circular(md));
  static const field = BorderRadius.all(Radius.circular(lg));
  static const sheet = BorderRadius.vertical(top: Radius.circular(xl));
}

/// Layout widths.
abstract final class Layout {
  /// The reading column: about 70 characters of narration at the default size.
  static const double readingWidth = 680;

  /// Content width for lists and forms on wide screens.
  static const double contentWidth = 920;

  /// From this width the tabs move into a side rail.
  static const double railBreakpoint = 840;

  /// Minimum touch target (Material and Apple guidance).
  static const double minTouch = 48;
}
