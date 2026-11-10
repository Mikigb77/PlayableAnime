/// The geometry of a 20-sided die and the little 3D maths a throw needs: points, turns, the
/// die's corners, faces and edges, which face is up, and a seeded stream of numbers.
///
/// A throw is worked out in full before it is shown (`simulate` in `throw_sim.dart`) and then
/// played back by the tray's painter. The result is decided by the story, never by the throw:
/// once the run says which face each die ends on, that face is given the number the server
/// rolled ([labelsFor]). The app never rolls a die of its own (A3).
library;

import 'dart:math' as math;

/// A point or a direction in three dimensions. On the tray x runs right, y runs down the screen
/// and z rises towards the eye.
final class V3 {
  const V3(this.x, this.y, this.z);

  final double x;
  final double y;
  final double z;

  static const up = V3(0, 0, 1);

  V3 operator -(V3 o) => V3(x - o.x, y - o.y, z - o.z);
  V3 operator +(V3 o) => V3(x + o.x, y + o.y, z + o.z);
  V3 operator *(double k) => V3(x * k, y * k, z * k);

  double dot(V3 o) => x * o.x + y * o.y + z * o.z;

  V3 cross(V3 o) => V3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);

  V3 get unit {
    final length = math.sqrt(dot(this));
    final l = length == 0 || length.isNaN ? 1.0 : length;
    return V3(x / l, y / l, z / l);
  }
}

/// A turn in three dimensions, as a unit quaternion (w first).
final class Quat {
  const Quat(this.w, this.x, this.y, this.z);

  /// A turn of [angle] radians about [axis], which has length one.
  factory Quat.axis(V3 axis, double angle) {
    final s = math.sin(angle / 2);
    return Quat(math.cos(angle / 2), axis.x * s, axis.y * s, axis.z * s);
  }

  /// The shortest turn that takes direction [a] to direction [b].
  factory Quat.between(V3 a, V3 b) {
    final d = a.dot(b);
    if (d > 0.999999) return identity;
    if (d < -0.999999) {
      final other = a.x.abs() < 0.9 ? const V3(1, 0, 0) : const V3(0, 1, 0);
      return Quat.axis(a.cross(other).unit, math.pi);
    }
    final c = a.cross(b);
    return Quat(1 + d, c.x, c.y, c.z).unit;
  }

  final double w;
  final double x;
  final double y;
  final double z;

  static const identity = Quat(1, 0, 0, 0);

  /// This turn after [b]: `(a * b).rotate(v)` is `a.rotate(b.rotate(v))`.
  Quat operator *(Quat b) => Quat(
    w * b.w - x * b.x - y * b.y - z * b.z,
    w * b.x + x * b.w + y * b.z - z * b.y,
    w * b.y - x * b.z + y * b.w + z * b.x,
    w * b.z + x * b.y - y * b.x + z * b.w,
  );

  double dot(Quat o) => w * o.w + x * o.x + y * o.y + z * o.z;

  Quat get unit {
    final length = math.sqrt(dot(this));
    final l = length == 0 || length.isNaN ? 1.0 : length;
    return Quat(w / l, x / l, y / l, z / l);
  }

  V3 rotate(V3 v) {
    final u = V3(x, y, z);
    final t = u.cross(v) * 2;
    final c = u.cross(t);
    return V3(v.x + w * t.x + c.x, v.y + w * t.y + c.y, v.z + w * t.z + c.z);
  }

  /// The turn a share [t] of the way from [a] to [b], the short way round.
  static Quat slerp(Quat a, Quat b, double t) {
    var d = a.dot(b);
    var to = b;
    if (d < 0) {
      to = Quat(-b.w, -b.x, -b.y, -b.z);
      d = -d;
    }
    if (d > 0.9995) {
      return Quat(
        a.w + (to.w - a.w) * t,
        a.x + (to.x - a.x) * t,
        a.y + (to.y - a.y) * t,
        a.z + (to.z - a.z) * t,
      ).unit;
    }
    final th = math.acos(d);
    final s = math.sin(th);
    final p = math.sin((1 - t) * th) / s;
    final q = math.sin(t * th) / s;
    return Quat(a.w * p + to.w * q, a.x * p + to.x * q, a.y * p + to.y * q, a.z * p + to.z * q);
  }
}

/// A stream of numbers from 0 up to 1 that is the same for the same [seed] on every device, so a
/// throw looks the same each time it is watched again.
double Function() seeded(int seed) {
  var a = seed & 0xFFFFFFFF;
  return () {
    a = (a + 0x6D2B79F5) & 0xFFFFFFFF;
    var t = _imul(a ^ (a >>> 15), 1 | a);
    t = ((t + _imul(t ^ (t >>> 7), 61 | t)) & 0xFFFFFFFF) ^ t;
    return ((t ^ (t >>> 14)) & 0xFFFFFFFF) / 4294967296;
  };
}

/// 32-bit multiplication that wraps, the same on a phone and in a browser, where whole numbers
/// are held differently.
int _imul(int a, int b) {
  final al = a & 0xFFFF;
  final ah = (a >>> 16) & 0xFFFF;
  final bl = b & 0xFFFF;
  final bh = (b >>> 16) & 0xFFFF;
  return (al * bl + (((ah * bl + al * bh) & 0xFFFF) << 16)) & 0xFFFFFFFF;
}

/// A number for a throw's seed as the server sends it, which is text.
int seedOf(String seed) {
  // FNV-1a, 32 bits.
  var hash = 0x811C9DC5;
  for (final unit in seed.codeUnits) {
    hash = _imul(hash ^ (unit & 0xFF), 0x01000193);
    hash = _imul(hash ^ (unit >> 8), 0x01000193);
  }
  return hash;
}

/// One of the die's twenty faces: its three corners in [verts], counted so the face looks
/// outwards, the way it faces and its middle.
final class Face {
  Face._(this.index, this.v, this.n, this.c);

  final int index;
  final List<int> v;
  final V3 n;
  final V3 c;

  /// The face on the other side of the die.
  late final int opposite;
}

/// One of the die's thirty edges, with the way it faces: halfway between its two faces.
final class Edge {
  Edge._(this.a, this.b, this.n, int face) : faces = [face];

  final int a;
  final int b;
  final V3 n;
  final List<int> faces;
}

final double _phi = (1 + math.sqrt(5)) / 2;

/// The die's twelve corners, each at distance one from its middle.
final List<V3> verts = () {
  final raw = <V3>[];
  final length = math.sqrt(1 + _phi * _phi);
  for (final a in const [-1.0, 1.0]) {
    for (final b in const [-1.0, 1.0]) {
      raw
        ..add(V3(0, a, b * _phi))
        ..add(V3(a, b * _phi, 0))
        ..add(V3(a * _phi, 0, b));
    }
  }
  return List<V3>.unmodifiable([for (final v in raw) V3(v.x / length, v.y / length, v.z / length)]);
}();

final List<Face> faces = () {
  final edge = 2 / math.sqrt(1 + _phi * _phi);
  bool near(int i, int j) {
    final d = verts[i] - verts[j];
    return (math.sqrt(d.dot(d)) - edge).abs() < 1e-6;
  }

  final found = <Face>[];
  for (var i = 0; i < 12; i++) {
    for (var j = i + 1; j < 12; j++) {
      for (var k = j + 1; k < 12; k++) {
        if (!(near(i, j) && near(j, k) && near(i, k))) continue;
        final c = V3(
          (verts[i].x + verts[j].x + verts[k].x) / 3,
          (verts[i].y + verts[j].y + verts[k].y) / 3,
          (verts[i].z + verts[j].z + verts[k].z) / 3,
        );
        final outward = (verts[j] - verts[i]).cross(verts[k] - verts[i]).dot(c) > 0;
        found.add(Face._(found.length, outward ? [i, j, k] : [i, k, j], c.unit, c));
      }
    }
  }
  for (final face in found) {
    for (final other in found) {
      if (face.n.dot(other.n) < -0.999) face.opposite = other.index;
    }
  }
  return List<Face>.unmodifiable(found);
}();

final List<Edge> edges = () {
  final seen = <int, Edge>{};
  final list = <Edge>[];
  for (final face in faces) {
    for (var k = 0; k < 3; k++) {
      final a = face.v[k];
      final b = face.v[(k + 1) % 3];
      final key = a < b ? a * 12 + b : b * 12 + a;
      final known = seen[key];
      if (known != null) {
        known.faces.add(face.index);
        continue;
      }
      final edge = Edge._(a, b, (verts[a] + verts[b]).unit, face.index);
      seen[key] = edge;
      list.add(edge);
    }
  }
  return List<Edge>.unmodifiable(list);
}();

/// The numbers on a die's faces before any is moved. Opposite faces add up to 21, as on a real
/// die.
final List<int> _baseLabels = () {
  final labels = List<int>.filled(faces.length, 0);
  var next = 1;
  for (final face in faces) {
    if (labels[face.index] != 0) continue;
    labels[face.index] = next;
    labels[face.opposite] = 21 - next;
    next += 1;
  }
  return List<int>.unmodifiable(labels);
}();

/// The numbers on a die whose face [top] shows [value], from 1 to 20: the face the throw ends on
/// is given the number the story rolled, and opposite faces still add up to 21.
List<int> labelsFor(int top, int value) {
  final labels = List<int>.of(_baseLabels);
  final shown = value.clamp(1, 20);
  final holds = labels.indexOf(shown);
  if (holds == top) return labels;
  final a = faces[top].opposite;
  final b = faces[holds].opposite;
  var keep = labels[top];
  labels[top] = shown;
  labels[holds] = keep;
  if (holds != a) {
    keep = labels[a];
    labels[a] = labels[b];
    labels[b] = keep;
  }
  return labels;
}

/// The face of a die turned by [q] that is nearest to up.
int topFace(Quat q) {
  var best = 0;
  var most = -2.0;
  for (final face in faces) {
    final z = q.rotate(face.n).z;
    if (z > most) {
      most = z;
      best = face.index;
    }
  }
  return best;
}

/// Which corner of a face points up the screen, and how far the face has to turn to stand on its
/// base.
({int corner, double turn}) upright(Quat q, int faceIndex) {
  final face = faces[faceIndex];
  final centre = q.rotate(face.c);
  var best = 0;
  var least = 9.0;
  for (var k = 0; k < 3; k++) {
    final p = q.rotate(verts[face.v[k]]) - centre;
    var turn = -math.pi / 2 - math.atan2(p.y, p.x);
    turn = math.atan2(math.sin(turn), math.cos(turn));
    if (turn.abs() < least.abs()) {
      least = turn;
      best = k;
    }
  }
  return (corner: best, turn: least);
}

/// Where a die comes to rest: flat on the face that is nearest to up, standing on its base.
Quat restPose(Quat q) {
  final face = topFace(q);
  final flat = Quat.between(q.rotate(faces[face].n), V3.up) * q;
  return (Quat.axis(V3.up, upright(flat, face).turn) * flat).unit;
}
