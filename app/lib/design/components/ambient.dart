import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../motion.dart';
import '../theme.dart';

/// One firefly: where it floats, how large it is and how bright.
@immutable
class Mote {
  const Mote(this.x, this.y, this.size, this.opacity);

  /// Across the page, from 0 at the left edge to 1 at the right.
  final double x;

  /// Down the page, in logical pixels, from where its content starts.
  final double y;
  final double size;
  final double opacity;
}

/// The night air behind a page, as on the website: a glow in the accent that breathes, and a few
/// fireflies drifting in it. Purely decorative, so it takes no taps and says nothing to a screen
/// reader. With the system's reduce-motion setting on, the glow and the fireflies hold still.
///
/// Put it under the page's content, filling the page: `Positioned.fill(child: Ambient())`.
class Ambient extends StatefulWidget {
  const Ambient({
    super.key,
    this.glow = const Alignment(0.76, -0.96),
    this.motes = corner,
    this.strength = 1,
    this.belowSystemInset = true,
  });

  /// Where the glow is centered, or null for fireflies alone, such as over a painting that
  /// already holds the light.
  final Alignment? glow;
  final List<Mote> motes;

  /// Scales the glow, from 0 to 1.
  final double strength;

  /// Counts the fireflies' places from under the system's top inset, as a page's content does,
  /// so they keep their place beside it on a phone with a notch. False counts from the very
  /// top, for fireflies set around a picture that starts there.
  final bool belowSystemInset;

  /// Fireflies gathered in the glow at the top right of a tab. They keep above the headline:
  /// a point of light beside a word reads as a mark that isn't there.
  static const corner = [
    Mote(0.84, 46, 4, 0.85),
    Mote(0.93, 78, 3, 0.6),
    Mote(0.72, 30, 3, 0.55),
    Mote(0.62, 68, 2, 0.5),
    Mote(0.555, 22, 2, 0.45),
  ];

  /// Fireflies in the forest around the gate, on the welcome screen.
  static const forest = [
    Mote(0.149, 214, 4, 0.85),
    Mote(0.849, 150, 3, 0.7),
    Mote(0.815, 318, 5, 0.85),
    Mote(0.103, 352, 3, 0.6),
    Mote(0.231, 120, 3, 0.55),
    Mote(0.903, 258, 3, 0.6),
    Mote(0.185, 300, 2, 0.6),
  ];

  @override
  State<Ambient> createState() => _AmbientState();
}

class _AmbientState extends State<Ambient> with SingleTickerProviderStateMixin {
  // One slow loop drives everything, and every drift is a whole number of turns of it, so the
  // loop has no seam.
  late final _controller = AnimationController(vsync: this, duration: Motion.ambient);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (Motion.reduced(context)) {
      _controller
        ..stop()
        ..value = 0;
    } else if (!_controller.isAnimating) {
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final dark = Theme.of(context).brightness == Brightness.dark;
    return IgnorePointer(
      child: ExcludeSemantics(
        child: RepaintBoundary(
          child: CustomPaint(
            painter: _AmbientPainter(
              turn: _controller,
              glow: widget.glow,
              motes: widget.motes,
              top: widget.belowSystemInset ? MediaQuery.paddingOf(context).top : 0,
              accent: colors.accent,
              // On the night page the fireflies are warm light. On paper they are motes of the
              // accent, since light doesn't show on a light page.
              core: dark ? const Color(0xFFFFE6AE) : colors.accent,
              halo: dark ? const Color(0xFFFFC870) : colors.accent,
              glowAlpha: (dark ? 0.2 : 0.16) * widget.strength,
              moteAlpha: dark ? 1 : 0.5,
            ),
            size: Size.infinite,
          ),
        ),
      ),
    );
  }
}

class _AmbientPainter extends CustomPainter {
  _AmbientPainter({
    required this.turn,
    required this.glow,
    required this.motes,
    required this.top,
    required this.accent,
    required this.core,
    required this.halo,
    required this.glowAlpha,
    required this.moteAlpha,
  }) : super(repaint: turn);

  final Animation<double> turn;
  final Alignment? glow;
  final List<Mote> motes;

  /// Where the page's content starts, which the fireflies' places are counted from.
  final double top;
  final Color accent;
  final Color core;
  final Color halo;
  final double glowAlpha;
  final double moteAlpha;

  static const _tau = math.pi * 2;

  @override
  void paint(Canvas canvas, Size size) {
    final t = turn.value;
    if (glow case final glow?) {
      // The glow breathes twice a loop, between 80% and 100% of its strength.
      final breath = 0.9 + 0.1 * math.sin(_tau * t * 2);
      final center = glow.alongSize(size);
      _oval(
        canvas,
        center,
        math.min(size.width * 0.85, 520),
        320,
        accent.withValues(alpha: glowAlpha * breath),
      );
    }
    for (final (i, mote) in motes.indexed) {
      // Each firefly wanders a small loop of its own and brightens and dims as it goes.
      final phase = i * 0.37;
      final dx = 7 * math.sin(_tau * (t * (1 + i % 2) + phase));
      final dy = 9 * math.cos(_tau * (t * (1 + (i + 1) % 3) + phase * 1.7));
      final twinkle = 0.7 + 0.3 * math.sin(_tau * (t * (2 + i % 3) + phase * 2.3));
      final at = Offset(mote.x * size.width + dx, top + mote.y + dy);
      final alpha = mote.opacity * twinkle * moteAlpha;
      _soft(canvas, at, mote.size * 4.5, halo.withValues(alpha: 0.2 * alpha));
      _soft(canvas, at, mote.size * 1.9, halo.withValues(alpha: 0.75 * alpha));
      canvas.drawCircle(at, mote.size / 2, Paint()..color = core.withValues(alpha: alpha));
    }
  }

  /// A round light that fades to nothing at [radius].
  void _soft(Canvas canvas, Offset center, double radius, Color color) {
    canvas.drawCircle(
      center,
      radius,
      Paint()..shader = ui.Gradient.radial(center, radius, [color, color.withValues(alpha: 0)]),
    );
  }

  /// A wide, soft light [rx] across and [ry] down, gone at seven tenths of the way out.
  void _oval(Canvas canvas, Offset center, double rx, double ry, Color color) {
    canvas
      ..save()
      ..translate(center.dx, center.dy)
      ..scale(rx, ry)
      ..drawCircle(
        Offset.zero,
        1,
        Paint()
          ..shader = ui.Gradient.radial(
            Offset.zero,
            1,
            [color, color.withValues(alpha: 0)],
            const [0, 0.7],
          ),
      )
      ..restore();
  }

  @override
  bool shouldRepaint(_AmbientPainter old) =>
      old.glow != glow ||
      old.motes != motes ||
      old.top != top ||
      old.accent != accent ||
      old.core != core ||
      old.halo != halo ||
      old.glowAlpha != glowAlpha ||
      old.moteAlpha != moteAlpha;
}
