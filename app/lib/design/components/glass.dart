import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme.dart';
import '../tokens.dart';

/// A panel of smoked glass that floats over the page: what lies behind it shows through,
/// blurred, under a hairline edge, and the panel casts a soft shadow. The tabs at the bottom of
/// the app and the bar at the top of a story are made of it.
class Glass extends StatelessWidget {
  const Glass({
    super.key,
    required this.child,
    this.borderRadius = const BorderRadius.all(Radius.circular(Radii.pill)),
    this.padding = EdgeInsets.zero,
    this.borderColor,
    this.glow,
    this.blur = 20,
  });

  final Widget child;
  final BorderRadius borderRadius;
  final EdgeInsetsGeometry padding;

  /// Replaces the hairline edge, such as the accent around the action box while it has focus.
  final Color? borderColor;

  /// A halo in this color around the panel, for something lit up.
  final Color? glow;

  /// How much what lies behind is blurred. Zero for a panel with nothing behind it to show.
  final double blur;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final panel = DecoratedBox(
      decoration: BoxDecoration(
        color: colors.glass,
        borderRadius: borderRadius,
        border: Border.all(color: borderColor ?? colors.glassBorder),
      ),
      child: Padding(padding: padding, child: child),
    );
    return CustomPaint(
      painter: _GlassShadow(radius: borderRadius, shadow: colors.glassShadow, glow: glow),
      child: ClipRRect(
        borderRadius: borderRadius,
        child: blur <= 0
            ? panel
            : BackdropFilter(
                filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
                child: panel,
              ),
      ),
    );
  }
}

/// The shadow under a glass panel, and its halo. It is painted only outside the panel: glass is
/// see-through, and a shadow under it would darken what it shows.
class _GlassShadow extends CustomPainter {
  const _GlassShadow({required this.radius, required this.shadow, this.glow});

  final BorderRadius radius;
  final Color shadow;
  final Color? glow;

  @override
  void paint(Canvas canvas, Size size) {
    final box = Offset.zero & size;
    final panel = radius.toRRect(box);
    final outside = Path.combine(
      PathOperation.difference,
      Path()..addRect(box.inflate(96)),
      Path()..addRRect(panel),
    );
    canvas
      ..save()
      ..clipPath(outside)
      ..drawRRect(
        panel.shift(const Offset(0, 16)),
        Paint()
          ..color = shadow
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20),
      );
    if (glow case final glow?) {
      canvas.drawRRect(
        panel,
        Paint()
          ..color = glow
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 14),
      );
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_GlassShadow old) =>
      old.radius != radius || old.shadow != shadow || old.glow != glow;
}

/// The bar at the top of a story: a pill of [Glass] that floats over the page, so a cover or a
/// picture runs on behind it. Use it as a scaffold's `appBar` with `extendBodyBehindAppBar`, and
/// keep the page's first words below [extent].
class GlassTopBar extends StatelessWidget implements PreferredSizeWidget {
  const GlassTopBar({super.key, this.leading, required this.title, this.actions = const []});

  final Widget? leading;
  final Widget title;
  final List<Widget> actions;

  /// The gap above and below the bar.
  static const double _gap = 4;

  /// How far the bar's words grow with the system's text size.
  static const double _maxTextScale = 1.3;

  /// How far down the page the bar reaches, below the system's own top inset.
  static const double extent = Layout.storyBarHeight + _gap * 2;

  @override
  Size get preferredSize => const Size.fromHeight(extent);

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final dark = Theme.of(context).brightness == Brightness.dark;
    // No app bar sets the status bar's icons here, so the glass bar does.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Stack(
        children: [
          // The page dims as it passes under the status bar, so nothing is read through the
          // clock, and comes back clear below the glass.
          Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      colors.background.withValues(alpha: 0.92),
                      colors.background.withValues(alpha: 0),
                    ],
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: Layout.barInset, vertical: _gap),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: Layout.readingWidth),
                  child: Glass(
                    padding: const EdgeInsets.symmetric(horizontal: 3),
                    child: IconTheme.merge(
                      data: IconThemeData(color: colors.textPrimary, size: 22),
                      child: SizedBox(
                        height: Layout.storyBarHeight - 2,
                        child: Row(
                          children: [
                            ?leading,
                            Expanded(
                              child: Padding(
                                padding: EdgeInsetsDirectional.only(
                                  start: leading == null ? 18 : 2,
                                ),
                                // The bar keeps its height, as an app bar does, so its words
                                // grow with the text size only as far as they fit.
                                child: MediaQuery.withClampedTextScaling(
                                  maxScaleFactor: _maxTextScale,
                                  child: title,
                                ),
                              ),
                            ),
                            ...actions,
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
