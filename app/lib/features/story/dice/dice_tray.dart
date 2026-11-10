/// A tray of 20-sided dice, drawn on a flat canvas with the die's own geometry: no 3D engine and
/// no package. The throw is worked out first (`throw_sim.dart`), then any moment of it can be
/// painted, so the replay can play it, hold it, and come back to it later exactly as it was.
library;

import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

import '../../../design/typography.dart';
import 'd20.dart';
import 'throw_sim.dart';

/// What a die is made of, which says what it is. The plain ones are midnight resin with gold
/// leaf in it, an advantage's is jade, and the move's own die is amethyst while the move is still
/// being mastered and solid gold once it is second nature. A die thrown by a 20 is pearl, and the
/// world's own die is grey stone.
enum DieSkin { plain, adv, insight, mastery, burst, world }

/// One die of a throw: the number the server rolled on it, what it is made of, and the die whose
/// 20 threw it, if one did.
@immutable
class TrayDie {
  const TrayDie({required this.value, this.skin = DieSkin.plain, this.from});

  final int value;
  final DieSkin skin;
  final int? from;

  /// The move's own die, which is thrown last.
  bool get isOwn => skin == DieSkin.insight || skin == DieSkin.mastery;
}

typedef _Rgb = (double, double, double);

const _Rgb _white = (255, 255, 255);
const _Rgb _black = (0, 0, 0);

_Rgb _mix(_Rgb a, _Rgb b, double t) =>
    (a.$1 + (b.$1 - a.$1) * t, a.$2 + (b.$2 - a.$2) * t, a.$3 + (b.$3 - a.$3) * t);

Color _rgb(_Rgb c, [double alpha = 1]) => Color.fromRGBO(
  c.$1.round().clamp(0, 255),
  c.$2.round().clamp(0, 255),
  c.$3.round().clamp(0, 255),
  alpha.clamp(0.0, 1.0),
);

class _Skin {
  const _Skin({
    required this.dark,
    required this.light,
    required this.rim,
    required this.cool,
    required this.glow,
    required this.ink,
    required this.dip,
    required this.lit,
    required this.fleck,
    required this.flecks,
    required this.inner,
    required this.depth,
    required this.gloss,
    required this.aura,
    this.darkInk = false,
  });

  final _Rgb dark;
  final _Rgb light;
  final _Rgb rim;
  final _Rgb cool;
  final _Rgb glow;
  final _Rgb ink;
  final _Rgb dip;
  final _Rgb lit;
  final _Rgb? fleck;
  final int flecks;
  final _Rgb? inner;
  final double depth;
  final double gloss;
  final double aura;

  /// Its numbers are dark on a pale body, so on a face in shadow they are drawn pale.
  final bool darkInk;
}

const _skins = <DieSkin, _Skin>{
  DieSkin.plain: _Skin(
    dark: (6, 9, 26),
    light: (66, 90, 168),
    rim: (206, 220, 255),
    cool: (40, 84, 190),
    glow: (240, 234, 222),
    ink: (247, 236, 208),
    dip: (3, 5, 12),
    lit: (11, 13, 18),
    fleck: (250, 208, 122),
    flecks: 13,
    inner: (70, 116, 230),
    depth: 0.2,
    gloss: 0.55,
    aura: 0,
  ),
  DieSkin.adv: _Skin(
    dark: (3, 28, 24),
    light: (72, 192, 154),
    rim: (196, 250, 230),
    cool: (40, 150, 176),
    glow: (158, 236, 204),
    ink: (240, 252, 246),
    dip: (2, 14, 12),
    lit: (4, 22, 18),
    fleck: (226, 255, 242),
    flecks: 8,
    inner: (120, 240, 200),
    depth: 0.2,
    gloss: 0.5,
    aura: 0,
  ),
  DieSkin.insight: _Skin(
    dark: (22, 10, 56),
    light: (142, 106, 238),
    rim: (228, 214, 255),
    cool: (96, 110, 250),
    glow: (208, 190, 255),
    ink: (249, 244, 255),
    dip: (11, 5, 30),
    lit: (20, 9, 48),
    fleck: (240, 232, 255),
    flecks: 13,
    inner: (190, 150, 255),
    depth: 0.24,
    gloss: 0.55,
    aura: 0.2,
  ),
  DieSkin.mastery: _Skin(
    dark: (66, 36, 4),
    light: (246, 198, 108),
    rim: (255, 244, 204),
    cool: (196, 140, 70),
    glow: (255, 228, 156),
    ink: (50, 28, 3),
    dip: (255, 238, 194),
    lit: (40, 22, 2),
    fleck: null,
    flecks: 0,
    inner: null,
    depth: 0,
    gloss: 0.9,
    aura: 0.2,
    darkInk: true,
  ),
  DieSkin.burst: _Skin(
    dark: (92, 84, 96),
    light: (252, 248, 240),
    rim: (255, 255, 255),
    cool: (170, 190, 235),
    glow: (255, 246, 220),
    ink: (46, 32, 12),
    dip: (255, 255, 255),
    lit: (36, 24, 6),
    fleck: (255, 214, 140),
    flecks: 7,
    inner: (255, 226, 170),
    depth: 0.2,
    gloss: 0.7,
    aura: 0.26,
    darkInk: true,
  ),
  DieSkin.world: _Skin(
    dark: (14, 16, 20),
    light: (136, 142, 154),
    rim: (228, 232, 240),
    cool: (84, 98, 124),
    glow: (232, 234, 240),
    ink: (246, 247, 250),
    dip: (6, 7, 10),
    lit: (14, 15, 18),
    fleck: null,
    flecks: 0,
    inner: null,
    depth: 0,
    gloss: 0.35,
    aura: 0,
  ),
};

final V3 _light = const V3(-0.5, -0.64, 0.58).unit;

/// Halfway between the light and the eye.
final V3 _glint = V3(_light.x, _light.y, _light.z + 1).unit;

/// A cool light from the other side, low.
final V3 _back = const V3(0.62, 0.58, 0.3).unit;

/// How much light a surface facing [n] takes. The light wraps a little way round the die, so a
/// face turning away from it dims gradually and never drops to black.
double _lit(V3 n) => 0.08 + 0.92 * math.pow(0.5 + 0.5 * n.dot(_light), 2.4);

_Rgb _tone(_Skin skin, double shade, double back) =>
    _mix(_mix(skin.dark, skin.light, shade), skin.cool, 0.5 * back * back * (1 - shade));

/// The leaf inside a die: a few flakes at fixed places in its body, each facing its own way, so
/// they catch the light in turn as the die tumbles.
typedef _Fleck = ({V3 p, V3 n, double size});

List<_Fleck> _flecksFor(int seed, int count) {
  final rnd = seeded(seed);
  final flecks = <_Fleck>[];
  for (var i = 0; i < count; i++) {
    final p = V3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).unit;
    final far = 0.2 + rnd() * 0.46;
    final n = V3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).unit;
    flecks.add((p: p * far, n: n, size: 0.024 + rnd() * 0.034));
  }
  return flecks;
}

class _Look {
  _Look({
    required this.labels,
    required this.top,
    required this.corner,
    required this.skin,
    required this.flecks,
  });

  final List<int> labels;
  final int top;
  final int corner;
  final _Skin skin;
  final List<_Fleck> flecks;

  /// How far the face that is up is lit, and how far the die is lifted, each from 0 to 1 and a
  /// little past it.
  double lit = 0;
  double pop = 0;
}

typedef _Pose = ({double x, double y, double z, Quat q});

/// The radius of a die on a tray of [count] dice: the more there are, the smaller each is.
double dieRadius(int count) => switch (count) {
  <= 3 => 34,
  4 => 32,
  5 => 29,
  6 => 26,
  _ => 24,
};

/// A throw on its tray: where every die is at any moment, and how each looks. The dice land on
/// the numbers the server rolled (A3).
class DiceTray {
  /// Works out the throw of [dice] on a tray of [size], seeded by [seed]. [style] and [entrance]
  /// pick the way it is thrown, where the seed isn't to pick them.
  factory DiceTray({
    required List<TrayDie> dice,
    required int seed,
    required Size size,
    String? style,
    String? entrance,
  }) {
    final radius = dieRadius(dice.length);
    final run = simulate(
      count: dice.length,
      radius: radius,
      width: size.width,
      height: size.height,
      seed: seed,
      late: dice.indexWhere((die) => die.isOwn),
      style: style,
      entrance: entrance,
      from: [for (final die in dice) die.from ?? -1],
    );
    return DiceTray._(dice, size, radius, run, [
      for (final (i, die) in dice.indexed)
        _Look(
          labels: labelsFor(run.tops[i].face, die.value),
          top: run.tops[i].face,
          corner: run.tops[i].corner,
          skin: _skins[die.skin]!,
          flecks: _flecksFor((seed * 31 + i * 977 + 5) & 0xFFFFFFFF, _skins[die.skin]!.flecks),
        ),
    ]);
  }

  DiceTray._(this.dice, this.size, this.radius, this.run, this._looks);

  final List<TrayDie> dice;
  final Size size;
  final double radius;
  final ThrowRun run;
  final List<_Look> _looks;

  double get duration => run.duration;

  /// When everything lies still: once for the hand, then once more after each die a 20 threw.
  List<double> get stops => run.stops;

  /// Lights the face a die shows, from 0 to 1, as it is read.
  void light(int index, double amount) => _looks[index].lit = amount;

  /// Lifts a die a little off the tray, from 0 to 1 and a little past it.
  void pop(int index, double amount) => _looks[index].pop = amount;

  /// Where a die lies at [time], or at the end of the throw.
  ({double x, double y, double r}) rest(int index, [double? time]) {
    final d = _pose(index, time == null ? run.frames.length - 1.0 : time / throwStep);
    return (x: d.x, y: d.y, r: radius);
  }

  _Pose _pose(int index, double frame) {
    final at = frame.clamp(0.0, run.frames.length - 1.0);
    final i0 = at.floor();
    final i1 = math.min(run.frames.length - 1, i0 + 1);
    final k = at - i0;
    final f0 = run.frames[i0];
    final f1 = run.frames[i1];
    final o = index * 7;
    return (
      x: f0[o] + (f1[o] - f0[o]) * k,
      y: f0[o + 1] + (f1[o + 1] - f0[o + 1]) * k,
      z: f0[o + 2] + (f1[o + 2] - f0[o + 2]) * k,
      q: Quat.slerp(
        Quat(f0[o + 3], f0[o + 4], f0[o + 5], f0[o + 6]),
        Quat(f1[o + 3], f1[o + 4], f1[o + 5], f1[o + 6]),
        k,
      ),
    );
  }

  /// Paints the throw as it is [time] seconds in. With [still], nothing flashes or shakes: the
  /// dice are drawn where they are and that is all, as reduced motion asks.
  void paint(Canvas canvas, double time, {bool still = false}) {
    final at = time / throwStep;
    final R = radius;
    final order = <_Drawn>[];
    for (var i = 0; i < dice.length; i++) {
      final since = time - run.delays[i];
      if (since < 0) continue;
      final d = _pose(i, at);
      final was = _pose(i, at - 3);
      final same = d.q.dot(was.q).abs();
      final moved = math.sqrt((d.x - was.x) * (d.x - was.x) + (d.y - was.y) * (d.y - was.y));
      order.add(
        _Drawn(
          index: i,
          pose: d,
          look: _looks[i],
          alpha: math.min(1.0, since / 0.09 + 0.15),
          speed: moved / (3 * throwStep),
          turn: since < 3 * throwStep ? 0.0 : 2 * math.acos(math.min(1.0, same)) / (3 * throwStep),
        ),
      );
    }
    // The lowest first, and dice at the same height in the order they were thrown.
    order.sort((a, b) => a.pose.z != b.pose.z ? a.pose.z.compareTo(b.pose.z) : a.index - b.index);
    var ox = 0.0;
    var oy = 0.0;
    if (!still) {
      for (final shake in run.shakes) {
        final u = time - shake.t;
        if (u < 0 || u >= 0.3) continue;
        // The tray gives under a hard landing and comes back: a push that dies away, never a
        // rattle.
        final amount = 0.6 * shake.a * (1 - u / 0.3) * (1 - u / 0.3);
        ox += amount * math.sin(u * 46 + shake.p);
        oy += amount * math.cos(u * 38 + shake.p);
      }
    }
    final paint = Paint();
    canvas
      ..save()
      ..translate(ox, oy);
    for (final d in order) {
      final p = d.pose;
      final sx = p.x + 5 + p.z * 0.4;
      final sy = p.y + 7 + p.z * 0.7;
      final sr = R * (1.12 + p.z / 160);
      _glow(
        canvas,
        paint,
        Offset(sx, sy),
        sr * 0.25,
        sr,
        Color.fromRGBO(0, 0, 0, (0.5 * d.alpha / (1 + p.z / 40)).clamp(0.0, 1.0)),
      );
      if (p.z < 6) {
        // Where it touches the tray.
        _glow(
          canvas,
          paint,
          Offset(p.x + 1, p.y + 3),
          R * 0.5,
          R * 1.08,
          Color.fromRGBO(0, 0, 0, (0.42 * d.alpha).clamp(0.0, 1.0)),
        );
      }
    }
    if (!still) {
      for (final ring in run.rings) {
        final u = (time - ring.t) / 0.34;
        if (u < 0 || u >= 1) continue;
        canvas.drawCircle(
          Offset(ring.x, ring.y),
          R * (0.9 + 1.1 * u),
          Paint()
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.4 * (1 - u) + 0.4
            ..color = Color.fromRGBO(255, 240, 205, 0.3 * (1 - u) * ring.s),
        );
      }
      for (final spark in run.sparks) {
        final u = (time - spark.t) / 0.2;
        if (u < 0 || u >= 1) continue;
        final size = 5 + 20 * u * spark.s + 6 * u;
        _glow(
          canvas,
          paint,
          Offset(spark.x, spark.y),
          0,
          size,
          Color.fromRGBO(255, 240, 205, 0.85 * (1 - u) * spark.s),
        );
      }
    }
    for (final d in order) {
      final p = d.pose;
      final shine = math.max(d.look.skin.aura, 0.34 * d.look.lit);
      if (shine > 0) {
        _glow(
          canvas,
          paint,
          Offset(p.x, p.y),
          R * 0.5,
          R * (1.7 + p.z / 200),
          _rgb(d.look.skin.glow, shine * d.alpha),
        );
      }
      // A die that moves or turns fast leaves a blur behind it, and its numbers blur with it.
      // Both come on by degrees, so nothing switches on between one frame and the next.
      final blur = math.max((d.speed - 220) / 420, (d.turn - 6) / 7).clamp(0.0, 1.0);
      if (blur > 0.02 && !still) {
        for (var back = 3; back >= 1; back--) {
          final then = _pose(d.index, at - back * 1.5);
          _drawDie(canvas, d.look, then, (0.26 - 0.06 * back) * blur * d.alpha, true, 0);
        }
      }
      _drawDie(canvas, d.look, p, d.alpha, false, 1 - 0.7 * ((d.turn - 5) / 8).clamp(0.0, 1.0));
    }
    canvas.restore();
  }

  /// A soft round patch of [color] that is full from the middle out to [inner] and gone at
  /// [outer].
  void _glow(Canvas canvas, Paint paint, Offset centre, double inner, double outer, Color color) {
    if (outer <= 0 || color.a == 0) return;
    final from = (inner / outer).clamp(0.0, 0.999);
    paint
      ..style = PaintingStyle.fill
      ..shader = ui.Gradient.radial(
        centre,
        outer,
        [color, color, color.withValues(alpha: 0)],
        [0, from, 1],
      );
    canvas.drawRect(Rect.fromCircle(center: centre, radius: outer), paint);
    paint.shader = null;
  }

  /// One die. [clear] is how clearly the numbers show, from 0 to 1: a die turning fast blurs
  /// them. A [ghost] is the faint trail a fast die leaves: its faces only.
  void _drawDie(Canvas canvas, _Look look, _Pose pose, double alpha, bool ghost, double clear) {
    final x = pose.x;
    final y = pose.y;
    final q = pose.q;
    final s = radius * (1 + pose.z / 300) * (1 + 0.08 * look.pop);
    final skin = look.skin;
    // A little perspective: the corners nearer the eye stand a little further out.
    final turned = [for (final v in verts) q.rotate(v)];
    final flat = [
      for (final p in turned)
        Offset(x + p.x * (1 + p.z * 0.13) * s, y + p.y * (1 + p.z * 0.13) * s),
    ];
    final seen = List<bool>.filled(faces.length, false);
    final shown = <_Shown>[];
    final fill = Paint()..style = PaintingStyle.fill;
    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    for (final face in faces) {
      final nrm = q.rotate(face.n);
      seen[face.index] = nrm.z > 0.01;
      if (!seen[face.index]) continue;
      final a = flat[face.v[0]];
      final b = flat[face.v[1]];
      final c = flat[face.v[2]];
      final shade = _lit(nrm);
      final back = math.max(0.0, nrm.dot(_back));
      var tone = _tone(skin, shade, back);
      final isTop = face.index == look.top && look.lit > 0;
      if (isTop) tone = _mix(tone, skin.glow, look.lit);
      final path = Path()
        ..moveTo(a.dx, a.dy)
        ..lineTo(b.dx, b.dy)
        ..lineTo(c.dx, c.dy)
        ..close();
      canvas.drawPath(path, fill..color = _rgb(tone, alpha));
      if (ghost) continue;
      canvas.drawPath(
        path,
        line
          ..strokeWidth = 0.8
          ..color = _rgb(tone, alpha),
      );
      shown.add(_Shown(face, nrm, a, b, c, shade, back, isTop));
    }
    if (ghost) return;
    // The edges, worn round: each one takes the light for the way it faces itself, halfway
    // between its two faces, and is drawn soft at its sides. An edge turned to the light glints.
    final wide = math.max(1.5, s * 0.1);
    final fine = math.max(0.8, s * 0.044);
    for (final edge in edges) {
      if (!seen[edge.faces[0]] && !seen[edge.faces[1]]) continue;
      final n = q.rotate(edge.n);
      final shade = _lit(n);
      final back = math.max(0.0, n.dot(_back));
      final color = _mix(_tone(skin, shade, back), skin.rim, 0.05 + 0.36 * shade * shade);
      final a = flat[edge.a];
      final b = flat[edge.b];
      canvas
        ..drawLine(
          a,
          b,
          line
            ..strokeWidth = wide
            ..color = _rgb(color, 0.42 * alpha),
        )
        ..drawLine(
          a,
          b,
          line
            ..strokeWidth = fine
            ..color = _rgb(color, alpha),
        );
      final glint = n.dot(_glint);
      if (glint > 0.72) {
        final bright = skin.gloss * 0.85 * math.pow((glint - 0.72) / 0.28, 3);
        canvas.drawLine(
          a,
          b,
          line
            ..strokeWidth = fine * 0.7
            ..color = Color.fromRGBO(255, 255, 255, (bright * alpha).clamp(0.0, 1.0)),
        );
      }
    }
    // The faces, set inside their edges with their corners rounded. Across a face the light
    // leans towards what its corners take, so two faces meet in nearly the same tone.
    for (final f in shown) {
      final g = Offset((f.a.dx + f.b.dx + f.c.dx) / 3, (f.a.dy + f.b.dy + f.c.dy) / 3);
      const inset = 0.86;
      final a2 = g + (f.a - g) * inset;
      final b2 = g + (f.b - g) * inset;
      final c2 = g + (f.c - g) * inset;
      var most = 0.0;
      var least = 1.0;
      for (final v in f.face.v) {
        final at = _lit(turned[v]);
        if (at > most) most = at;
        if (at < least) least = at;
      }
      var hi = _tone(skin, f.shade + (math.max(most, f.shade) - f.shade) * 0.5, f.back);
      var lo = _tone(skin, f.shade + (math.min(least, f.shade) - f.shade) * 0.5, f.back);
      if (f.isTop) {
        hi = _mix(hi, skin.glow, look.lit);
        lo = _mix(lo, skin.glow, look.lit);
      }
      final span = s * 0.5;
      final path = _soft(a2, b2, c2, s * 0.085);
      canvas.drawPath(
        path,
        fill
          ..shader = ui.Gradient.linear(
            Offset(g.dx + _light.x * span, g.dy + _light.y * span),
            Offset(g.dx - _light.x * span, g.dy - _light.y * span),
            [
              _rgb(_mix(hi, _white, 0.05 + 0.1 * skin.gloss), alpha),
              _rgb(_mix(lo, _black, 0.14), alpha),
            ],
          ),
      );
      fill.shader = null;
      final glint = f.nrm.dot(_glint);
      if (glint > 0.8) {
        final bright = skin.gloss * 0.8 * math.pow((glint - 0.8) / 0.2, 3);
        canvas.drawPath(
          path,
          fill..color = Color.fromRGBO(255, 255, 255, (bright * alpha).clamp(0.0, 1.0)),
        );
      }
    }
    // The body under the faces: light gathers where it enters and where it leaves, the far
    // side falls away, and the leaf inside glitters as it turns.
    final body = Path();
    for (final f in shown) {
      body
        ..moveTo(f.a.dx, f.a.dy)
        ..lineTo(f.b.dx, f.b.dy)
        ..lineTo(f.c.dx, f.c.dy)
        ..close();
    }
    final around = Rect.fromLTWH(x - s * 1.15, y - s * 1.15, s * 2.3, s * 2.3);
    canvas
      ..save()
      ..clipPath(body);
    canvas.drawRect(
      around,
      fill
        ..shader = ui.Gradient.radial(
          Offset(x, y),
          s * 1.08,
          [
            Color.fromRGBO(255, 255, 255, (0.1 + 0.1 * skin.gloss) * alpha),
            const Color(0x00FFFFFF),
            const Color(0x00000000),
            Color.fromRGBO(0, 0, 0, 0.3 * alpha),
          ],
          const [0, 0.45, 0.72, 1],
          TileMode.clamp,
          null,
          Offset(x + _light.x * s * 0.5, y + _light.y * s * 0.5),
          s * 0.08,
        ),
    );
    fill.shader = null;
    if (skin.inner case final inner?) {
      final from = Offset(x - _light.x * s * 0.42, y - _light.y * s * 0.42);
      canvas.drawRect(
        around,
        fill
          ..shader = ui.Gradient.radial(from, s * 0.7, [
            _rgb(inner, skin.depth * 1.6 * alpha),
            _rgb(inner, 0),
          ]),
      );
      fill.shader = null;
    }
    if (skin.fleck case final leaf?) {
      for (final fleck in look.flecks) {
        final p = q.rotate(fleck.p);
        final facing = math.max(0.0, q.rotate(fleck.n).dot(_glint));
        final bright = (0.2 + 0.8 * facing * facing * facing) * (0.6 + 0.4 * (p.z + 0.64) / 1.28);
        final at = Offset(x + p.x * s, y + p.y * s);
        final size = math.max(0.55, fleck.size * s);
        canvas
          ..drawCircle(at, size * 2.2, fill..color = _rgb(leaf, 0.26 * bright * alpha))
          ..drawCircle(
            at,
            size,
            fill..color = _rgb(_mix(leaf, _white, 0.5 * bright), 0.95 * bright * alpha),
          );
      }
    }
    canvas.restore();
    for (final f in shown) {
      if (f.nrm.z < 0.3) continue;
      final face = f.face;
      final centre = q.rotate(face.c);
      final corner = turned[face.v[face.index == look.top ? look.corner : 0]];
      final up = (corner - centre).unit;
      final right = f.nrm.cross(up);
      final size = s * 0.47;
      final label = look.labels[face.index];
      final k = 1 + centre.z * 0.13;
      final shows = alpha * clear * math.min(1.0, (f.nrm.z - 0.3) / 0.3);
      if (shows <= 0.01) continue;
      final pale = skin.darkInk && f.shade < 0.5 && !f.isTop;
      final ink = pale
          ? skin.dip
          : f.isTop
          ? _mix(skin.ink, skin.lit, look.lit)
          : skin.ink;
      final dip = pale
          ? skin.ink
          : f.isTop
          ? _mix(skin.dip, _white, look.lit)
          : skin.dip;
      final scale = size / _Numbers.size;
      canvas
        ..save()
        ..transform(
          Float64List.fromList([
            right.x * scale, right.y * scale, 0, 0, //
            -up.x * scale, -up.y * scale, 0, 0, //
            0, 0, 1, 0, //
            x + centre.x * k * s, y + centre.y * k * s, 0, 1,
          ]),
        );
      // Cut into the face: a thin line of the other tone under each number.
      final sink = math.max(0.8 / scale, _Numbers.size * 0.07);
      _Numbers.draw(canvas, label, _rgb(dip, 0.6 * shows), _Numbers.size * 0.06 + sink);
      final inked = _rgb(ink, (f.isTop ? 1 : 0.95) * shows);
      _Numbers.draw(canvas, label, inked, _Numbers.size * 0.06);
      if (label == 6 || label == 9) {
        // The line under a 6 or a 9 that tells them apart.
        canvas.drawRect(
          Rect.fromLTWH(
            -_Numbers.size * 0.25,
            _Numbers.size * 0.46,
            _Numbers.size * 0.5,
            math.max(1 / scale, _Numbers.size * 0.08),
          ),
          fill..color = inked,
        );
      }
      canvas.restore();
    }
  }

  /// A triangle with its corners rounded, by no more than the triangle has room for.
  static Path _soft(Offset a, Offset b, Offset c, double radius) {
    final area = ((b.dx - a.dx) * (c.dy - a.dy) - (c.dx - a.dx) * (b.dy - a.dy)).abs() / 2;
    final around = (b - a).distance + (c - b).distance + (a - c).distance;
    final r = math.min(radius, around > 0 ? 0.9 * area / around : 0.0);
    final path = Path();
    if (r < 0.25) {
      return path
        ..moveTo(a.dx, a.dy)
        ..lineTo(b.dx, b.dy)
        ..lineTo(c.dx, c.dy)
        ..close();
    }
    path.moveTo((a.dx + b.dx) / 2, (a.dy + b.dy) / 2);
    _round(path, a, b, c, r);
    _round(path, b, c, a, r);
    _round(path, c, a, b, r);
    return path..close();
  }

  /// Goes on towards [corner] from [before], round it on an arc of radius [r], and leaves it
  /// towards [after].
  static void _round(Path path, Offset before, Offset corner, Offset after, double r) {
    final toBefore = before - corner;
    final toAfter = after - corner;
    final u = toBefore / toBefore.distance;
    final v = toAfter / toAfter.distance;
    // Half the angle at the corner.
    final half = math.acos((u.dx * v.dx + u.dy * v.dy).clamp(-1.0, 1.0)) / 2;
    final reach = r / math.tan(half);
    final start = corner + u * reach;
    final end = corner + v * reach;
    path
      ..lineTo(start.dx, start.dy)
      // An arc of a circle that touches both sides is a conic through the corner.
      ..conicTo(corner.dx, corner.dy, end.dx, end.dy, math.sin(half));
  }
}

class _Drawn {
  _Drawn({
    required this.index,
    required this.pose,
    required this.look,
    required this.alpha,
    required this.speed,
    required this.turn,
  });

  final int index;
  final _Pose pose;
  final _Look look;
  final double alpha;
  final double speed;
  final double turn;
}

class _Shown {
  _Shown(this.face, this.nrm, this.a, this.b, this.c, this.shade, this.back, this.isTop);

  final Face face;
  final V3 nrm;
  final Offset a;
  final Offset b;
  final Offset c;
  final double shade;
  final double back;
  final bool isTop;
}

/// The numbers on the faces, in the reading serif. Each is laid out once at one size and drawn
/// scaled, since a tray shows the same few numbers in the same few inks on every frame.
abstract final class _Numbers {
  static const double size = 40;
  static final _cache = <int, TextPainter>{};

  static void draw(Canvas canvas, int label, Color color, double middle) {
    // Alpha in sixteenths: close enough to see no step, few enough to keep.
    final alpha = (color.a * 16).round();
    if (alpha == 0) return;
    final inked = color.withValues(alpha: alpha / 16);
    final key = label * 0x100000000 + inked.toARGB32();
    var painter = _cache[key];
    if (painter == null) {
      if (_cache.length > 900) _cache.clear();
      painter = _cache[key] = TextPainter(
        textDirection: TextDirection.ltr,
        text: TextSpan(
          text: '$label',
          style: TextStyle(
            fontFamily: Fonts.serif,
            fontWeight: FontWeight.w600,
            fontSize: size,
            height: 1,
            color: inked,
            fontFeatures: const [FontFeature.liningFigures()],
          ),
        ),
      )..layout();
    }
    painter.paint(canvas, Offset(-painter.width / 2, middle - painter.height / 2));
  }
}

/// The moment of a throw that is on show. It tells the painter when to paint again: when the
/// moment moves, and when a die was lit or lifted where it lies.
class TrayClock extends ChangeNotifier {
  /// Seconds into the throw.
  double get time => _time;
  double _time = 0;

  void show(double time) {
    _time = time;
    notifyListeners();
  }
}

/// Paints a [DiceTray] at the moment its [clock] holds, and again whenever that says so.
class DiceTrayPainter extends CustomPainter {
  DiceTrayPainter({required this.tray, required this.clock, this.still = false})
    : super(repaint: clock);

  final DiceTray tray;
  final TrayClock clock;

  /// Reduced motion: nothing flashes, shakes or blurs.
  final bool still;

  @override
  void paint(Canvas canvas, Size size) => tray.paint(canvas, clock.time, still: still);

  @override
  bool shouldRepaint(DiceTrayPainter old) =>
      old.tray != tray || old.clock != clock || old.still != still;
}
