/// How a throw moves: a small physics run on a flat tray (walls, dice knocking into each other, a
/// hop on every knock), with each die's spin in 3D. The run is worked out in full, then played
/// back by the tray's painter. It decides only how the dice travel and which face each ends on;
/// the numbers on those faces are the server's (A3).
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'd20.dart';

/// The run's step: 120 to a second.
const double throwStep = 1 / 120;

/// The fastest a rolling die turns, in radians a second: past this a d20 flickers on a screen.
const double _spin = 14;

/// The ways a handful of dice can be thrown, some of them soft and some of them hard. A throw
/// picks one by its seed, so the same roll never has to look the same twice.
const throwStyles = [
  'sweep',
  'clash',
  'drop',
  'toss',
  'corner',
  'lazy',
  'volley',
  'slam',
  'pour',
  'tops',
  'cross',
  'spill',
  'skip',
  'break',
  'arc',
  'whirl',
  'pop',
  'hail',
  'push',
  'ricochet',
];

/// The ways the move's own die, thrown last, comes in.
const lastDieEntrances = ['spin', 'lob', 'strike', 'plunge', 'bank', 'hop', 'curl', 'fall'];

/// A flash where two dice, or a die and a wall, met hard.
typedef Spark = ({double t, double x, double y, double s});

/// A ring on the tray where a die landed hard.
typedef LandingRing = ({double t, double x, double y, double s});

/// A push the tray gives under a hard landing.
typedef Shake = ({double t, double a, double p});

/// A throw, worked out from its first frame to its last.
class ThrowRun {
  ThrowRun._({
    required this.frames,
    required this.sparks,
    required this.rings,
    required this.shakes,
    required this.stops,
    required this.style,
    required this.entrance,
    required this.delays,
    required this.tops,
  });

  /// One frame a step: seven numbers a die, its place (x, y, z) and its turn (w, x, y, z).
  final List<Float32List> frames;
  final List<Spark> sparks;
  final List<LandingRing> rings;
  final List<Shake> shakes;

  /// When everything lies still: once for the hand, then once more after each die a 20 threw.
  final List<double> stops;
  final String style;

  /// How the last die came in, or empty when it came with the rest.
  final String entrance;

  /// When each die is thrown, in seconds from the start.
  final List<double> delays;

  /// The face each die ends on, and which of its corners points up the screen.
  final List<({int face, int corner})> tops;

  double get duration => (frames.length - 1) * throwStep;
}

enum _State { roll, top, settle, slide, rest, wait }

class _Die {
  _Die({
    this.x = 0,
    this.y = 0,
    this.z = 0,
    this.vx = 0,
    this.vy = 0,
    this.vz = 0,
    this.delay = 0,
    this.state,
    this.parent = -1,
  });

  double x;
  double y;
  double z;
  double vx;
  double vy;
  double vz;
  double delay;
  _State? state;

  /// The die whose 20 threw this one, and the die it is still leaping clear of.
  int parent;
  int clearOf = -1;

  bool rise = false;
  bool calm = false;
  bool hop = false;
  bool landed = false;
  bool fixed = false;
  bool inX = false;
  bool inY = false;

  /// How much of a fall comes back as a bounce; 0 for the tray's ordinary 0.42.
  double bounce = 0;
  double curl = 0;

  /// Where the last die looks for room before it comes in: a `lane` or a `spot`.
  String? find;

  // Spinning on its point.
  double wz = 0;
  double wz0 = 0;
  double ang = 0;
  int up = 0;
  Quat q0 = Quat.identity;

  Quat q = Quat.identity;
  double w0 = 0;
  double w1 = 0;
  double w2 = 0;

  // Tipping onto its face.
  double since = 0;
  Quat? from;
  Quat? to;
}

/// Works out a throw of [count] dice of radius [radius] on a tray [width] by [height].
///
/// [from] says, for each die, which die's 20 threw it, or -1: those dice wait until everything
/// thrown before them lies still, then leap out of the die that threw them, one at a time.
/// [late] is the move's own die, thrown last and a beat after the others, or -1.
ThrowRun simulate({
  required int count,
  required double radius,
  required double width,
  required double height,
  required int seed,
  List<int> from = const [],
  int late = -1,
  String? style,
  String? entrance,
}) {
  final rnd = seeded(seed);
  final n = count;
  final R = radius;
  final r = R * 0.95;
  final W = width;
  final H = height;
  final edge = R + 4;
  final waiting = <int>[
    for (var i = 0; i < n; i++)
      if (i < from.length && from[i] >= 0) i,
  ];
  final main = n - waiting.length - (late >= 0 ? 1 : 0);
  final how = style ?? throwStyles[(rnd() * throwStyles.length).floor()];
  final last = entrance ?? lastDieEntrances[(rnd() * lastDieEntrances.length).floor()];
  final dice = <_Die>[];
  final frames = <Float32List>[];
  final sparks = <Spark>[];
  final rings = <LandingRing>[];
  final shakes = <Shake>[];
  var t = 0.0;
  var restedAt = -1.0;
  final side = rnd() < 0.5 ? 1.0 : -1.0;
  final vert = rnd() < 0.5 ? 1.0 : -1.0;
  final turn = rnd() < 0.5 ? 1.0 : -1.0;
  var lastDelay = 0.0;
  final first = (rnd() * 4).floor();
  final heartX = W * (0.42 + rnd() * 0.16);
  final heartY = H * (0.46 + rnd() * 0.08);
  final fan = rnd() * 6.283;
  final places = [for (var i = 0; i < main; i++) i];
  for (var i = main - 1; i > 0; i--) {
    final j = (rnd() * (i + 1)).floor();
    final keep = places[i];
    places[i] = places[j];
    places[j] = keep;
  }

  double inX(double x) => math.max(edge + 2, math.min(W - edge - 2, x));
  double inY(double y) => math.max(edge + 2, math.min(H - edge - 2, y));

  _Die fromSide(double s, double at, double of, double speed, double lift, double sway) {
    final y = inY(H * (0.26 + 0.48 * ((at + 0.5) / of)) + (rnd() - 0.5) * 12);
    return _Die(
      x: s > 0 ? -R - 8 : W + R + 8,
      y: y,
      z: R * 0.7,
      vx: s * speed,
      vy: (rnd() - 0.5) * sway,
      vz: lift,
    );
  }

  _Die fromEnd(double v, double at, double of, double speed, double lift, double sway) {
    final x = inX(W * (0.2 + 0.6 * ((at + 0.5) / of)) + (rnd() - 0.5) * 16);
    return _Die(
      x: x,
      y: v > 0 ? -R - 8 : H + R + 8,
      z: R * 0.7,
      vx: (rnd() - 0.5) * sway,
      vy: v * speed,
      vz: lift,
    );
  }

  _Die onItsPoint(_Die d, double spin) {
    d.z = d.z > R ? d.z : 0;
    d.vz = d.z != 0 ? d.vz : 0;
    d.state = _State.top;
    d.wz = (rnd() < 0.5 ? -1 : 1) * spin;
    d.wz0 = spin;
    d.up = (rnd() * 12).floor();
    d.ang = rnd() * 6;
    return d;
  }

  // Every draw from the stream below is made in the order the prototype makes it, so a seed
  // throws here as it does there.
  _Die thrown(int k) {
    final at = places[k].toDouble();
    final of = math.max(1, main).toDouble();
    final _Die d;
    switch (how) {
      case 'pop':
        // They jump up out of the middle of the tray and come down all around it.
        final turnAt = fan + (at / of) * 6.283 + (rnd() - 0.5) * 0.6;
        final away = 150 + rnd() * 150;
        d = _Die(
          x: inX(heartX + math.cos(turnAt) * 7),
          y: inY(heartY + math.sin(turnAt) * 5),
          z: 2,
          vx: math.cos(turnAt) * away,
          vy: math.sin(turnAt) * away * 0.55,
          vz: 560 + rnd() * 240,
        );
        d.rise = true;
        d.delay = k * 0.07 + rnd() * 0.03;
      case 'hail':
        // They come down all over the tray, almost at once.
        d = _Die(
          x: edge + 4 + rnd() * (W - 2 * edge - 8),
          y: edge + 4 + rnd() * (H - 2 * edge - 8),
          z: 210 + rnd() * 130,
          vx: (rnd() - 0.5) * 240,
          vy: (rnd() - 0.5) * 180,
          vz: -160 - rnd() * 200,
        );
        d.x = math.max(
          edge + 4,
          math.min(W - edge - 4, W * (0.12 + 0.76 * ((at + 0.5) / of)) + (rnd() - 0.5) * 30),
        );
        d.delay = rnd() * 0.22;
      case 'push':
        // Lined up and pushed in together, the way a hand slides dice across a table.
        d = fromSide(side, at, of, 470, 0, 0);
        d.y = edge + 3 + (H - 2 * edge - 6) * (of > 1 ? at / (of - 1) : 0.5);
        d.x += -side * (at % 2) * R * 1.75;
        d.z = 0;
        d.vz = 0;
        d.vx = side * (455 + rnd() * 30);
        d.delay = 0.02 + rnd() * 0.01;
        d.calm = true;
      case 'ricochet':
        // Thrown hard at the long wall, to come back off it.
        d = _Die(
          x: W * (0.12 + 0.76 * ((at + 0.5) / of)) + (rnd() - 0.5) * 14,
          y: vert > 0 ? -R - 8 : H + R + 8,
          z: R * 0.7,
          vx: side * (300 + rnd() * 260),
          vy: vert * (900 + rnd() * 260),
          vz: 130 + rnd() * 160,
        );
        d.delay = k * 0.075 + rnd() * 0.03;
      case 'pour':
        // Poured along the far edge, one after another, as the hand moves across.
        final along = of > 1 ? k / (of - 1) : 0.5;
        d = fromEnd(vert, 0, 1, 290 + rnd() * 90, 60 + rnd() * 90, 120);
        d.x = W * (0.16 + 0.68 * (side > 0 ? along : 1 - along)) + (rnd() - 0.5) * 12;
        d.vx += side * (50 + rnd() * 90);
        d.delay = k * 0.17 + rnd() * 0.04;
        d.calm = true;
      case 'tops':
        // Every die comes in spinning on its point, and they fall one after another.
        final came = fromSide(k.isOdd ? -side : side, at, of, 170 + rnd() * 90, 0, 70);
        d = onItsPoint(came, 12 + 2.2 * k + rnd() * 3);
        d.z = 0;
        d.vz = 0;
        d.delay = k * 0.13 + rnd() * 0.04;
      case 'cross':
        // From all four sides, to meet in the middle.
        final way = (k + first) % 4;
        d = way.isEven
            ? fromSide(way == 0 ? 1 : -1, at, of, 500 + rnd() * 160, 90 + rnd() * 120, 200)
            : fromEnd(way == 1 ? 1 : -1, at, of, 300 + rnd() * 90, 90 + rnd() * 120, 200);
        d.delay = k * 0.1 + rnd() * 0.03;
      case 'spill':
        // Tipped out of a cup over the middle: they fall together and spread.
        final ang = fan + (at / of) * 6.283 + (rnd() - 0.5) * 0.5;
        final out = 110 + rnd() * 130;
        d = _Die(
          x: inX(heartX + math.cos(ang) * R * 0.8),
          y: inY(heartY + math.sin(ang) * R * 0.55),
          z: 150 + rnd() * 40,
          vx: math.cos(ang) * out,
          vy: math.sin(ang) * out * 0.6,
          vz: -40 - rnd() * 60,
        );
        d.delay = k * 0.035 + rnd() * 0.02;
      case 'skip':
        // Thrown low, they hop across the tray.
        d = fromSide(side, at, of, 430 + rnd() * 120, 340 + rnd() * 70, 110);
        d.bounce = 0.64;
        d.hop = true;
        d.delay = k * 0.14 + rnd() * 0.04;
      case 'break':
        // Half of them roll in and gather; the rest come hard from the other side and scatter
        // them.
        final lead = (of / 2).ceil();
        if (k < lead) {
          d = fromSide(side, at, of, 200 + rnd() * 60, 40 + rnd() * 50, 90);
          d.delay = k * 0.08 + rnd() * 0.03;
          d.calm = true;
        } else {
          d = fromSide(-side, at, of, 1050 + rnd() * 300, 160 + rnd() * 200, 420);
          d.delay = 0.95 + (k - lead) * 0.07 + rnd() * 0.02;
        }
      case 'arc':
        // Lobbed high: a long moment in the air, a heavy landing and a short roll.
        d = fromSide(side, at, of, 250 + rnd() * 110, 640 + rnd() * 130, 90);
        d.bounce = 0.3;
        d.delay = k * 0.13 + rnd() * 0.04;
      case 'whirl':
        // Swirled out of the hand: every die comes round on a curve, all the same way.
        d = fromSide(side, at, of, 540 + rnd() * 140, 90 + rnd() * 90, 80);
        d.curl = turn * (3.3 + rnd() * 1.2);
        d.delay = k * 0.1 + rnd() * 0.03;
      case 'clash':
        d = fromSide(k.isOdd ? -side : side, at, of, 760 + rnd() * 240, 140 + rnd() * 200, 300);
        d.delay = (k ~/ 2) * 0.07 + rnd() * 0.03;
      case 'drop':
        d = _Die(
          x: W * (0.14 + 0.72 * ((at + 0.5) / of)) + (rnd() - 0.5) * 18,
          y: H * (0.32 + rnd() * 0.36),
          z: 250 + rnd() * 90,
          vx: (rnd() - 0.5) * 260,
          vy: (rnd() - 0.5) * 200,
          vz: -120 - rnd() * 160,
        );
        d.delay = k * 0.12 + rnd() * 0.04;
      case 'toss':
        d = _Die(
          x: W * (0.5 + (rnd() - 0.5) * 0.3),
          y: H + R + 8,
          z: R * 0.7,
          vx: (at - (of - 1) / 2) * 150 + (rnd() - 0.5) * 120,
          vy: -(720 + rnd() * 260),
          vz: 260 + rnd() * 200,
        );
        d.delay = k * 0.05 + rnd() * 0.03;
      case 'corner':
        d = _Die(
          x: side > 0 ? -R - 8 : W + R + 8,
          y: vert > 0 ? H - edge - 2 - rnd() * 10 : edge + 2 + rnd() * 10,
          z: R * 0.7,
          vx: side * (820 + rnd() * 260),
          vy: -vert * (380 + rnd() * 300),
          vz: 150 + rnd() * 180,
        );
        d.delay = k * 0.09 + rnd() * 0.03;
      case 'lazy':
        d = fromSide(side, at, of, 430 + rnd() * 130, 50 + rnd() * 70, 160);
        d.delay = k * 0.07 + rnd() * 0.03;
        d.calm = true;
      case 'volley':
        d = fromSide(side, at, of, 820 + rnd() * 330, 150 + rnd() * 230, 480);
        d.delay = k * 0.24 + rnd() * 0.04;
      case 'slam':
        d = fromSide(side, at, of, 1350 + rnd() * 350, 220 + rnd() * 260, 900);
        d.delay = k * 0.06 + rnd() * 0.02;
      default:
        d = fromSide(side, at, of, 900 + rnd() * 300, 150 + rnd() * 230, 560);
        d.delay = k * 0.085 + rnd() * 0.03;
    }
    return d;
  }

  // The move's own die is thrown last, a beat after the others, and never the same way they
  // were.
  _Die thrownLast() {
    final _Die d;
    final wait = main > 0 ? lastDelay + 0.5 + rnd() * 0.25 : 0.0;
    if (how == 'drop') {
      d = _Die(
        x: W * (0.4 + rnd() * 0.2),
        y: H * (0.4 + rnd() * 0.2),
        z: 360 + rnd() * 60,
        vx: (rnd() - 0.5) * 200,
        vy: (rnd() - 0.5) * 160,
        vz: -160,
      );
    } else if (last == 'spin') {
      final came = _Die(
        x: side > 0 ? W + R + 8 : -R - 8,
        y: H * (0.36 + rnd() * 0.28),
        vx: -side * (330 + rnd() * 120),
        vy: (rnd() - 0.5) * 120,
      );
      d = onItsPoint(came, 17 + rnd() * 3);
      d.find = 'lane';
    } else if (last == 'plunge') {
      // It falls from high up, already spinning on its point, and spins on where it lands.
      final came = _Die(
        x: W * (0.3 + rnd() * 0.4),
        y: H * (0.4 + rnd() * 0.2),
        z: 300 + rnd() * 50,
        vz: -120,
      );
      d = onItsPoint(came, 17.5 + rnd() * 3);
      d.bounce = 0.22;
      d.find = 'spot';
    } else if (last == 'fall') {
      // Let go from high above the others: one heavy landing.
      d = _Die(
        x: W * (0.3 + rnd() * 0.4),
        y: H * (0.4 + rnd() * 0.2),
        z: 330 + rnd() * 60,
        vx: (rnd() - 0.5) * 120,
        vy: (rnd() - 0.5) * 90,
        vz: -140,
      );
      d.bounce = 0.36;
      d.find = 'spot';
    } else if (last == 'bank') {
      // In from a corner, to come back off the walls.
      d = _Die(
        x: side > 0 ? W + R + 8 : -R - 8,
        y: vert > 0 ? edge + 3 : H - edge - 3,
        z: R * 0.7,
        vx: -side * (560 + rnd() * 120),
        vy: vert * (300 + rnd() * 90),
        vz: 80 + rnd() * 80,
      );
    } else if (last == 'hop') {
      d = fromSide(-side, 0.5 + (rnd() - 0.5) * 0.6, 1, 420 + rnd() * 100, 350 + rnd() * 60, 100);
      d.bounce = 0.64;
      d.hop = true;
    } else if (last == 'curl') {
      d = fromSide(-side, 0.5 + (rnd() - 0.5) * 0.6, 1, 560 + rnd() * 120, 90 + rnd() * 80, 60);
      d.curl = (rnd() < 0.5 ? -1 : 1) * (3.4 + rnd() * 1.2);
    } else if (last == 'lob') {
      d = _Die(
        x: W * (0.3 + rnd() * 0.4),
        y: how == 'toss' ? -R - 8 : H + R + 8,
        z: R * 0.7,
        vx: (rnd() - 0.5) * 300,
        vy: (how == 'toss' ? 1 : -1) * (520 + rnd() * 180),
        vz: 520 + rnd() * 160,
      );
    } else {
      d = fromSide(
        how == 'clash' ? (rnd() < 0.5 ? 1 : -1) : -side,
        0.5 + (rnd() - 0.5) * 0.6,
        1,
        1000 + rnd() * 300,
        170 + rnd() * 200,
        420,
      );
    }
    d.delay = wait;
    return d;
  }

  var hand = 0;
  for (var i = 0; i < n; i++) {
    if (i < from.length && from[i] >= 0) {
      dice.add(_Die(delay: 1e9, state: _State.wait, parent: from[i]));
    } else if (i != late) {
      final d = thrown(hand);
      hand += 1;
      lastDelay = math.max(lastDelay, d.delay);
      dice.add(d);
    } else {
      dice.add(_Die());
    }
  }
  if (late >= 0) dice[late] = thrownLast();
  for (final d in dice) {
    final calm = d.calm ? 0.45 : 1.0;
    d.q = Quat(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).unit;
    d.w0 = (rnd() - 0.5) * 18 * calm;
    d.w1 = (rnd() - 0.5) * 18 * calm;
    d.w2 = (rnd() - 0.5) * 12 * calm;
    d.state ??= _State.roll;
    d.inX = false;
    d.inY = false;
    d.since = 0;
    d.from = null;
    d.to = null;
    if (d.state == _State.top) d.q0 = Quat.between(verts[d.up], V3.up);
  }

  void topple(_Die d) {
    d.state = _State.roll;
    d.w0 = (rnd() - 0.5) * 9;
    d.w1 = (rnd() - 0.5) * 9;
    d.w2 = d.wz;
    d.vx += (rnd() - 0.5) * 170;
    d.vy += (rnd() - 0.5) * 130;
    d.vz = 70;
  }

  void knock(_Die d, double strength) {
    if (d.fixed) {
      if (d.state == _State.rest) d.state = _State.slide;
      return;
    }
    if (d.state == _State.top) {
      if (strength > 110) topple(d);
      return;
    }
    // A knock nudges the way a die is turning; it never throws it into a new spin.
    final nudge = math.min(strength, 420.0);
    d.w0 += (rnd() - 0.5) * nudge * 0.036;
    d.w1 += (rnd() - 0.5) * nudge * 0.036;
    d.w2 += (rnd() - 0.5) * nudge * 0.03;
    if (d.z <= 0.5) d.vz += math.min(250.0, strength * 0.32);
    if (d.state != _State.roll && strength > 45) d.state = _State.roll;
  }

  void wall(_Die d, double strength, double x, double y) {
    knock(d, strength);
    if (strength > 260) sparks.add((t: t, x: x, y: y, s: math.min(1.0, strength / 900) * 0.7));
    if (strength > 520) shakes.add((t: t, a: math.min(2.6, strength / 420), p: rnd() * 6));
  }

  void advance(_Die d) {
    d.vz -= 2400 * throwStep;
    d.z += d.vz * throwStep;
    if (d.z < 0) {
      d.z = 0;
      d.landed = true;
      if (d.vz < -130) {
        if (d.hop && d.vz >= -420 && d.vz < -230) rings.add((t: t, x: d.x, y: d.y, s: 0.45));
        if (d.vz < -420) {
          // A die that lands hard skids off where it fell, and the tray feels it.
          rings.add((t: t, x: d.x, y: d.y, s: math.min(1.0, -d.vz / 1100)));
          if (d.vz < -700) shakes.add((t: t, a: math.min(2.4, -d.vz / 520), p: rnd() * 6));
          d.vx += (rnd() - 0.5) * -d.vz * 0.45;
          d.vy += (rnd() - 0.5) * -d.vz * 0.35;
        }
        d.vz = -d.vz * (d.bounce != 0 ? d.bounce : 0.42);
        d.w0 += (rnd() - 0.5) * 3.5;
        d.w1 += (rnd() - 0.5) * 3.5;
      } else {
        d.vz = 0;
      }
    }
    final grounded = d.z <= 0.5;
    final speed = math.sqrt(d.vx * d.vx + d.vy * d.vy);
    if (grounded) {
      // The tray holds a slow die more than a fast one, and the hold comes on gradually.
      final slow = math.max(0.0, math.min(1.0, (190 - speed) / 130));
      final drag = math.exp(-(1.2 + 1.3 * slow * slow * (3 - 2 * slow)) * throwStep);
      d.vx *= drag;
      d.vy *= drag;
    }
    if (d.curl != 0 && d.inX && d.inY) {
      // A die thrown with a twist comes round on a curve that straightens as it slows.
      final cs = math.cos(d.curl * throwStep);
      final sn = math.sin(d.curl * throwStep);
      final was = d.vx;
      d.vx = was * cs - d.vy * sn;
      d.vy = was * sn + d.vy * cs;
      d.curl *= math.exp(-0.9 * throwStep);
    }
    d.x += d.vx * throwStep;
    d.y += d.vy * throwStep;
    // The tray's walls, a little inside the picture so a die at rest is never cut off. A wall
    // counts for a die once it has come in past it, from whichever side it was thrown.
    if (!d.inX && d.x > edge && d.x < W - edge) d.inX = true;
    if (!d.inY && d.y > edge && d.y < H - edge) d.inY = true;
    // The hand follows through: a die still on its way in keeps coming, whatever lies by the
    // wall.
    if (!d.inX) {
      final inward = d.x < W / 2 ? 1.0 : -1.0;
      if (d.vx * inward < 240) d.vx = inward * 240;
    }
    if (!d.inY) {
      final inward = d.y < H / 2 ? 1.0 : -1.0;
      if (d.vy * inward < 240) d.vy = inward * 240;
    }
    if (t - d.delay > 1.4) {
      d.inX = true;
      d.inY = true;
    }
    if (d.inX && d.x < edge) {
      d.x = edge;
      if (d.vx < 0) {
        wall(d, -d.vx, 0, d.y);
        d.vx = -d.vx * 0.68;
      }
    }
    if (d.inX && d.x > W - edge) {
      d.x = W - edge;
      if (d.vx > 0) {
        wall(d, d.vx, W, d.y);
        d.vx = -d.vx * 0.68;
      }
    }
    if (d.inY && d.y < edge) {
      d.y = edge;
      if (d.vy < 0) {
        wall(d, -d.vy, d.x, 0);
        d.vy = -d.vy * 0.68;
      }
    }
    if (d.inY && d.y > H - edge) {
      d.y = H - edge;
      if (d.vy > 0) {
        wall(d, d.vy, d.x, H);
        d.vy = -d.vy * 0.68;
      }
    }
    switch (d.state!) {
      case _State.top:
        // Spinning on its point: it turns upright, leans further as the spin runs down, and
        // falls.
        d.wz *= math.exp(-1.0 * throwStep);
        d.ang += d.wz * throwStep;
        final left = d.wz.abs() / d.wz0;
        final lean = 0.1 + 0.5 * (1 - left) * (1 - left);
        final sweep = d.ang * 0.21;
        d.q =
            (Quat.axis(V3(math.cos(sweep), math.sin(sweep), 0), lean) *
                    (Quat.axis(V3.up, d.ang) * d.q0))
                .unit;
        if (d.wz.abs() < 6.5) topple(d);
      case _State.roll:
        if (grounded) {
          // A die on the tray turns the way it travels.
          final pull = math.min(1.0, 7 * throwStep);
          d.w0 += (-d.vy / r * 0.6 - d.w0) * pull;
          d.w1 += (d.vx / r * 0.6 - d.w1) * pull;
          d.w2 *= math.exp(-2.5 * throwStep);
        }
        var spin = math.sqrt(d.w0 * d.w0 + d.w1 * d.w1 + d.w2 * d.w2);
        if (spin > _spin) {
          d.w0 = d.w0 * _spin / spin;
          d.w1 = d.w1 * _spin / spin;
          d.w2 = d.w2 * _spin / spin;
          spin = _spin;
        }
        if (spin > 1e-4) {
          d.q = (Quat.axis(V3(d.w0 / spin, d.w1 / spin, d.w2 / spin), spin * throwStep) * d.q).unit;
        }
        if (grounded && speed < 40 && d.w2.abs() < 6) {
          d.state = _State.settle;
          d.since = t;
          d.from = d.q;
          d.to = restPose(d.q);
        }
      case _State.settle:
        // It tips onto its face and stills, like a die that still has a little weight to shed.
        // The tip starts from nothing and gathers, so the last turn follows on from the roll.
        final u = math.min(1.0, (t - d.since) / 0.7);
        final e = u >= 1
            ? 1.0
            : 1 - math.exp(-6.4 * u) * (math.cos(7.2 * u) + 0.889 * math.sin(7.2 * u));
        d.q = Quat.slerp(d.from!, d.to!, e);
        d.vx *= math.exp(-10 * throwStep);
        d.vy *= math.exp(-10 * throwStep);
        if (u >= 1) {
          d.state = _State.rest;
          d.q = d.to!;
          d.w0 = 0;
          d.w1 = 0;
          d.w2 = 0;
        }
      case _State.slide:
        // Shouldered aside by a die thrown after it was read: it slides a little and keeps its
        // face.
        d.vx *= math.exp(-9 * throwStep);
        d.vy *= math.exp(-9 * throwStep);
        if (speed < 14) {
          d.state = _State.rest;
          d.vx = 0;
          d.vy = 0;
        }
      case _State.rest || _State.wait:
        d.vx = 0;
        d.vy = 0;
    }
  }

  // The die that comes in spinning on its point takes the side and the lane with the most room,
  // so it has the space to spin before anything touches it.
  void lane(_Die d) {
    var best = -1.0;
    for (final way in const [-1.0, 1.0]) {
      for (var k = 0; k < 5; k++) {
        final y = edge + 4 + (H - 2 * edge - 8) * k / 4;
        var room = 1e9;
        for (final other in dice) {
          if (identical(other, d)) continue;
          for (var reach = 0; reach <= 170; reach += 17) {
            final px = (way > 0 ? -R - 8 : W + R + 8) + way * reach;
            final gap = math.sqrt((other.x - px) * (other.x - px) + (other.y - y) * (other.y - y));
            if (gap < room) room = gap;
          }
        }
        room += rnd() * 6;
        if (room > best) {
          best = room;
          d.x = way > 0 ? -R - 8 : W + R + 8;
          d.y = y;
          d.vx = way * d.vx.abs();
        }
      }
    }
  }

  // Where the tray is emptiest: the die that falls spinning lands there, and a die thrown by a
  // 20 leaps towards it.
  (double, double) emptiest(_Die d) {
    var best = -1.0;
    var at = (W / 2, H / 2);
    for (var a = 0; a < 7; a++) {
      for (var b = 0; b < 3; b++) {
        final x = edge + 6 + (W - 2 * edge - 12) * a / 6;
        final y = edge + 6 + (H - 2 * edge - 12) * b / 2;
        var room = 1e9;
        for (final other in dice) {
          if (identical(other, d) || t < other.delay) continue;
          final gap = math.sqrt((other.x - x) * (other.x - x) + (other.y - y) * (other.y - y));
          if (gap < room) room = gap;
        }
        room = math.min(room, 3.2 * R) + rnd() * 8;
        if (room > best) {
          best = room;
          at = (x, y);
        }
      }
    }
    return at;
  }

  void spot(_Die d) {
    final (x, y) = emptiest(d);
    d.x = x;
    d.y = y;
  }

  // A 20 throws one more die. Everything that lies still keeps its face from then on, so no
  // number that has been read can change: such a die can be slid aside, never tumbled.
  void leap(_Die d) {
    final parent = dice[d.parent];
    for (final other in dice) {
      if (other.state == _State.rest) other.fixed = true;
    }
    final (toX, toY) = emptiest(d);
    final up = 560 + rnd() * 90;
    final air = 2 * up / 2400;
    var vx = (toX - parent.x) / air * 0.8;
    var vy = (toY - parent.y) / air * 0.8;
    final v = math.sqrt(vx * vx + vy * vy);
    if (v > 380) {
      vx *= 380 / v;
      vy *= 380 / v;
    }
    if (v < 90) {
      final a0 = rnd() * 6.283;
      vx = math.cos(a0) * 140;
      vy = math.sin(a0) * 140;
    }
    d
      ..x = parent.x
      ..y = parent.y
      ..z = 6
      ..vx = vx
      ..vy = vy
      ..vz = up
      ..delay = t
      ..state = _State.roll
      ..inX = true
      ..inY = true
      ..clearOf = d.parent
      ..bounce = 0.36;
  }

  var placed = late < 0 || dice[late].find == null;
  final stops = <double>[];
  var until = 9.0;
  while (t < until) {
    if (!placed && t >= dice[late].delay) {
      (dice[late].find == 'spot' ? spot : lane)(dice[late]);
      placed = true;
    }
    for (var i = 0; i < n; i++) {
      if (t >= dice[i].delay) advance(dice[i]);
    }
    var apart = true;
    for (var i = 0; i < n; i++) {
      for (var j = i + 1; j < n; j++) {
        final a = dice[i];
        final b = dice[j];
        if (t < a.delay || t < b.delay) continue;
        var dx = b.x - a.x;
        var dy = b.y - a.y;
        var gap = math.sqrt(dx * dx + dy * dy);
        // A die that leaps out of another is clear of it once it is above it or beside it.
        final child = a.clearOf == j
            ? a
            : b.clearOf == i
            ? b
            : null;
        if (child != null) {
          if ((a.z - b.z).abs() > R * 1.3 || gap >= 2 * r) {
            child.clearOf = -1;
          } else {
            continue;
          }
        }
        // They leave the same spot together.
        if (a.rise && b.rise && !a.landed && !b.landed) continue;
        // One is still in the air above the other.
        if ((a.z - b.z).abs() > R * 1.3) continue;
        if (gap >= 2 * r) continue;
        if (gap < 1e-6) {
          dx = 1;
          dy = 0;
          gap = 1;
        }
        // Two dice that overlap slide apart over a few steps, never in one jump: a die that
        // lands on another shoulders it aside.
        final nx = dx / gap;
        final ny = dy / gap;
        final push = math.min(2.6, (2 * r - gap) / 2);
        a.x -= nx * push;
        a.y -= ny * push;
        b.x += nx * push;
        b.y += ny * push;
        if (2 * r - gap > 1) apart = false;
        final closing = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny;
        if (closing <= 0) continue;
        final hit = 0.9 * closing;
        a.vx -= hit * nx;
        a.vy -= hit * ny;
        b.vx += hit * nx;
        b.vy += hit * ny;
        knock(a, hit);
        knock(b, hit);
        if (hit > 70) {
          sparks.add((t: t, x: a.x + nx * r, y: a.y + ny * r, s: math.min(1.0, hit / 500)));
        }
        if (hit > 620) shakes.add((t: t, a: math.min(2.0, hit / 520), p: rnd() * 6));
      }
    }
    frames.add(_frame(dice));
    t += throwStep;
    if (apart && dice.every((d) => d.state == _State.rest || d.state == _State.wait)) {
      if (restedAt < 0) restedAt = t;
      if (t - restedAt > 0.1) {
        stops.add((frames.length - 1) * throwStep);
        if (waiting.isEmpty) break;
        leap(dice[waiting.removeAt(0)]);
        restedAt = -1;
        until = t + 6;
      }
    } else {
      restedAt = -1;
    }
  }
  // A run that never stilled in its time ends where it stands, flat on the faces that are up, and
  // a die still waiting for its 20 is set down where there is room: every die the server threw
  // is on the tray, with a moment of rest to be read at.
  final unfinished = waiting.isNotEmpty || dice.any((d) => d.state != _State.rest);
  if (unfinished) {
    for (final d in dice) {
      if (d.state == _State.wait) {
        spot(d);
        d.delay = t;
      }
      d
        ..z = 0
        ..q = restPose(d.q)
        ..state = _State.rest;
    }
    frames.add(_frame(dice));
  }
  final end = (frames.length - 1) * throwStep;
  if (stops.isEmpty || stops.last < end) stops.add(end);
  while (stops.length < n - main - (late >= 0 ? 1 : 0) + 1) {
    stops.add(end);
  }
  return ThrowRun._(
    frames: frames,
    sparks: sparks,
    rings: rings,
    shakes: shakes,
    stops: stops,
    style: how,
    entrance: late >= 0 && how != 'drop' ? last : '',
    delays: [for (final d in dice) d.delay],
    tops: [for (final d in dice) _topOf(d.q)],
  );
}

({int face, int corner}) _topOf(Quat q) {
  final top = topFace(q);
  return (face: top, corner: upright(q, top).corner);
}

Float32List _frame(List<_Die> dice) {
  final frame = Float32List(dice.length * 7);
  for (var i = 0; i < dice.length; i++) {
    final d = dice[i];
    frame[i * 7] = d.x;
    frame[i * 7 + 1] = d.y;
    frame[i * 7 + 2] = d.z;
    frame[i * 7 + 3] = d.q.w;
    frame[i * 7 + 4] = d.q.x;
    frame[i * 7 + 5] = d.q.y;
    frame[i * 7 + 6] = d.q.z;
  }
  return frame;
}
