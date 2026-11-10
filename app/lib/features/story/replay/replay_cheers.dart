import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../dice/d20.dart';

/// A throw that goes over the top is celebrated (S15): one of five ways, by turns, so the same
/// one rarely comes twice running. Rays break out of the end of the bar, rings run out from the
/// tray, gold motes rise through the card, three bursts go off over the dice, or a band of light
/// crosses the card with stars behind it.
///
/// It is drawn over the card for a little over three seconds and takes no taps. With reduced
/// motion the card doesn't build it at all.
class Cheer extends StatefulWidget {
  const Cheer({
    super.key,
    required this.kind,
    required this.seed,
    required this.cardKey,
    required this.trayKey,
    required this.gaugeKey,
  });

  /// Which of the five, from 0.
  final int kind;
  final int seed;

  /// The card, its tray and its bar, to find where the light comes from.
  final GlobalKey cardKey;
  final GlobalKey trayKey;
  final GlobalKey gaugeKey;

  static const names = ['sunburst', 'ripple', 'embers', 'fireworks', 'shine'];

  @override
  State<Cheer> createState() => _CheerState();
}

enum _BitKind { flash, ray, ring, mote, spark, band, star }

/// One piece of a celebration: where it starts, when, and the few numbers its motion needs.
typedef _Bit = ({
  _BitKind kind,
  double x,
  double y,
  double delay,
  double angle,
  double reach,
  double dx,
  double dy,
  double size,
  double lasts,
});

class _CheerState extends State<Cheer> with SingleTickerProviderStateMixin {
  late final _time = AnimationController(vsync: this, duration: const Duration(milliseconds: 3400));
  List<_Bit>? _bits;

  @override
  void initState() {
    super.initState();
    // The card is laid out by now; where its tray and bar are is read once, after this frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      setState(() => _bits = _make());
      _time.forward();
    });
  }

  @override
  void dispose() {
    _time.dispose();
    super.dispose();
  }

  Rect? _rectOf(GlobalKey key, RenderBox card) {
    final box = key.currentContext?.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero, ancestor: card) & box.size;
  }

  List<_Bit> _make() {
    final card = widget.cardKey.currentContext?.findRenderObject();
    if (card is! RenderBox || !card.hasSize) return const [];
    final size = card.size;
    final tray =
        _rectOf(widget.trayKey, card) ??
        Rect.fromLTWH(16, size.height * 0.3, size.width - 32, size.height * 0.3);
    final gauge = _rectOf(widget.gaugeKey, card);
    // The end of the bar, which the dice ran past.
    final end = gauge == null
        ? Offset(size.width - 16, size.height * 0.68)
        : Offset(gauge.right, gauge.top + 6);
    final rnd = seeded(977 + widget.kind * 131 + widget.seed);
    _Bit bit(
      _BitKind kind,
      double x,
      double y, {
      double delay = 0,
      double angle = 0,
      double reach = 0,
      double dx = 0,
      double dy = 0,
      double size = 0,
      double lasts = 1,
    }) => (
      kind: kind,
      x: x,
      y: y,
      delay: delay,
      angle: angle,
      reach: reach,
      dx: dx,
      dy: dy,
      size: size,
      lasts: lasts,
    );
    final bits = <_Bit>[];
    switch (Cheer.names[widget.kind % Cheer.names.length]) {
      case 'sunburst':
        bits.add(bit(_BitKind.flash, end.dx, end.dy, lasts: 0.8));
        for (var i = 0; i < 18; i++) {
          bits.add(
            bit(
              _BitKind.ray,
              end.dx,
              end.dy,
              angle: (i * 20 + rnd() * 9) * math.pi / 180,
              reach: 50 + rnd() * 80,
              delay: rnd() * 0.14,
              lasts: 0.9,
            ),
          );
        }
      case 'ripple':
        for (var i = 0; i < 4; i++) {
          bits.add(bit(_BitKind.ring, tray.center.dx, tray.center.dy, delay: i * 0.17, lasts: 1.4));
        }
      case 'embers':
        for (var i = 0; i < 44; i++) {
          bits.add(
            bit(
              _BitKind.mote,
              rnd() * size.width,
              size.height * (0.35 + rnd() * 0.65),
              dx: (rnd() - 0.5) * 80,
              dy: -(130 + rnd() * 260),
              delay: rnd() * 0.7,
              lasts: 1.3 + rnd() * 0.9,
              size: 4 + rnd() * 7,
            ),
          );
        }
      case 'fireworks':
        for (var burst = 0; burst < 3; burst++) {
          final x = tray.left + tray.width * (0.2 + 0.3 * burst + (rnd() - 0.5) * 0.1);
          final y = tray.top + tray.height * (0.25 + rnd() * 0.5);
          for (var i = 0; i < 12; i++) {
            bits.add(
              bit(
                _BitKind.spark,
                x,
                y,
                angle: (i * 30 + rnd() * 14) * math.pi / 180,
                reach: 30 + rnd() * 34,
                delay: burst * 0.3 + rnd() * 0.05,
              ),
            );
          }
        }
      default:
        bits.add(bit(_BitKind.band, 0, 0, lasts: 1.6));
        for (var i = 0; i < 11; i++) {
          bits.add(
            bit(
              _BitKind.star,
              size.width * (0.1 + rnd() * 0.8),
              size.height * (0.08 + rnd() * 0.84),
              delay: 0.25 + rnd() * 0.9,
              size: 9 + rnd() * 10,
              lasts: 1.1,
            ),
          );
        }
    }
    return bits;
  }

  @override
  Widget build(BuildContext context) {
    final bits = _bits;
    if (bits == null || bits.isEmpty) return const SizedBox.expand();
    return CustomPaint(
      key: ValueKey('replay.cheer.${Cheer.names[widget.kind % Cheer.names.length]}'),
      painter: _CheerPainter(bits: bits, time: _time),
    );
  }
}

const _gold = Color(0xFFE3B66B);
const _goldHi = Color(0xFFF6DFA8);
const _white = Color(0xFFFFFFFF);

class _CheerPainter extends CustomPainter {
  _CheerPainter({required this.bits, required this.time}) : super(repaint: time);

  final List<_Bit> bits;
  final Animation<double> time;

  static const _rayEase = Cubic(0.1, 0.7, 0.2, 1);
  static const _ringEase = Cubic(0.2, 0.6, 0.2, 1);
  static const _sparkEase = Cubic(0.1, 0.7, 0.3, 1);

  /// Comes in over the first [rise] of its life and goes out over the rest.
  static double _fade(double u, double rise) => u < rise ? u / rise : 1 - (u - rise) / (1 - rise);

  @override
  void paint(Canvas canvas, Size size) {
    final seconds = time.value * 3.4;
    for (final bit in bits) {
      final u = (seconds - bit.delay) / bit.lasts;
      if (u <= 0 || u >= 1) continue;
      switch (bit.kind) {
        case _BitKind.flash:
          final e = Curves.easeOut.transform(u);
          final radius = 11 * (0.4 + 7.6 * e);
          final at = Offset(bit.x, bit.y);
          canvas.drawCircle(
            at,
            radius,
            Paint()
              ..shader = RadialGradient(
                colors: [
                  _white.withValues(alpha: 1 - e),
                  _goldHi.withValues(alpha: 0.85 * (1 - e)),
                  _goldHi.withValues(alpha: 0),
                ],
                stops: const [0, 0.4, 0.7],
              ).createShader(Rect.fromCircle(center: at, radius: radius)),
          );
        case _BitKind.ray:
          final e = _rayEase.transform(u);
          final alpha = _fade(u, 0.15);
          canvas
            ..save()
            ..translate(bit.x, bit.y)
            ..rotate(bit.angle)
            ..translate(4 + (bit.reach - 4) * e, 0)
            ..scale(0.2 + 0.8 * e, 1);
          const ray = Rect.fromLTWH(0, -1.25, 34, 2.5);
          canvas
            ..drawRRect(
              RRect.fromRectAndRadius(ray, const Radius.circular(2)),
              Paint()
                ..shader = LinearGradient(
                  colors: [
                    const Color(0x00FFF6D6),
                    _goldHi.withValues(alpha: alpha),
                    _white.withValues(alpha: alpha),
                  ],
                  stops: const [0, 0.4, 1],
                ).createShader(ray),
            )
            ..restore();
        case _BitKind.ring:
          final e = _ringEase.transform(u);
          final alpha = _fade(u, 0.12);
          final radius = 30 * (0.2 + 8.8 * e);
          final at = Offset(bit.x, bit.y);
          canvas
            ..drawCircle(
              at,
              radius,
              Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 8
                ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10)
                ..color = _gold.withValues(alpha: 0.5 * alpha),
            )
            ..drawCircle(
              at,
              radius,
              Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 2
                ..color = _goldHi.withValues(alpha: 0.9 * alpha),
            );
        case _BitKind.mote:
          final e = Curves.easeOut.transform(u);
          final alpha = _fade(u, 0.18);
          final at = Offset(bit.x + bit.dx * e, bit.y + bit.dy * e);
          final radius = bit.size / 2 * (0.4 + 0.6 * e);
          canvas.drawCircle(
            at,
            radius,
            Paint()
              ..shader = RadialGradient(
                colors: [
                  _white.withValues(alpha: alpha),
                  _goldHi.withValues(alpha: alpha),
                  _gold.withValues(alpha: 0),
                ],
                stops: const [0, 0.45, 0.72],
              ).createShader(Rect.fromCircle(center: at, radius: radius)),
          );
        case _BitKind.spark:
          final e = _sparkEase.transform(u);
          final alpha = u < 0.1
              ? u / 0.1
              : u < 0.7
              ? 1.0
              : 1 - (u - 0.7) / 0.3;
          final at = Offset(
            bit.x + math.cos(bit.angle) * bit.reach * e,
            bit.y + math.sin(bit.angle) * bit.reach * e,
          );
          final radius = 2.5 * (1 - 0.7 * e);
          canvas
            ..drawCircle(
              at,
              radius + 4,
              Paint()
                ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4)
                ..color = _goldHi.withValues(alpha: 0.9 * alpha),
            )
            ..drawCircle(at, radius, Paint()..color = _white.withValues(alpha: alpha));
        case _BitKind.band:
          final e = Curves.easeInOut.transform(u);
          final width = size.width * 0.6;
          final band = Rect.fromLTWH((-1.1 + 3.0 * e) * width, 0, width, size.height);
          canvas.drawRect(
            band,
            Paint()
              ..shader = const LinearGradient(
                colors: [
                  Color(0x00FFF6D6),
                  Color(0x33FFF6D6),
                  Color(0x6BFFFFFF),
                  Color(0x33FFF6D6),
                  Color(0x00FFF6D6),
                ],
                stops: [0.2, 0.44, 0.5, 0.56, 0.8],
                transform: GradientRotation(10 * math.pi / 180),
              ).createShader(band),
          );
        case _BitKind.star:
          final swell = math.sin(math.pi * u);
          final half = bit.size / 2;
          canvas
            ..save()
            ..translate(bit.x, bit.y)
            ..rotate(40 * math.pi / 180 * swell)
            ..scale(swell);
          // A four-pointed star: long points up, down and to the sides, pinched between them.
          final star = Path()
            ..moveTo(0, -half)
            ..lineTo(0.18 * half, -0.18 * half)
            ..lineTo(half, 0)
            ..lineTo(0.18 * half, 0.18 * half)
            ..lineTo(0, half)
            ..lineTo(-0.18 * half, 0.18 * half)
            ..lineTo(-half, 0)
            ..lineTo(-0.18 * half, -0.18 * half)
            ..close();
          canvas
            ..drawPath(
              star,
              Paint()
                ..shader = RadialGradient(
                  colors: [
                    _white.withValues(alpha: swell),
                    _goldHi.withValues(alpha: swell),
                  ],
                  stops: const [0.3, 1],
                ).createShader(Rect.fromCircle(center: Offset.zero, radius: half)),
            )
            ..restore();
      }
    }
  }

  @override
  bool shouldRepaint(_CheerPainter old) => old.bits != bits;
}
