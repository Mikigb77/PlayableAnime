import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/story/dice/d20.dart';
import 'package:playable_anime/features/story/dice/throw_sim.dart';

/// The throws in `prototype_throws.json` were run with the prototype's own code (version 9, the
/// one Miki approved): each seed must throw here as it does there, from the first frame to the
/// face every die ends on.
void main() {
  final cases =
      (jsonDecode(File('test/features/dice/prototype_throws.json').readAsStringSync()) as List)
          .cast<Map<String, dynamic>>();

  test('a seed throws as it does in the prototype, in every style and entrance', () {
    final styles = <String>{};
    final entrances = <String>{};
    for (final c in cases) {
      final ran = c['ran'] as Map<String, dynamic>;
      final run = simulate(
        count: c['count'] as int,
        radius: (c['radius'] as num).toDouble(),
        width: 300,
        height: 158,
        seed: c['seed'] as int,
        late: c['late'] as int,
        from: (c['from'] as List).cast<int>(),
        style: c['style'] as String?,
        entrance: c['entrance'] as String?,
      );
      final what = 'seed ${c['seed']} (${ran['style']}, ${ran['entrance']})';
      expect(run.style, ran['style'], reason: what);
      expect(run.entrance, ran['entrance'], reason: what);
      expect(run.frames.length, ran['frames'], reason: what);
      expect(run.sparks.length, ran['sparks'], reason: what);
      expect(run.rings.length, ran['rings'], reason: what);
      expect(run.shakes.length, ran['shakes'], reason: what);
      expect(
        [
          for (final top in run.tops) [top.face, top.corner],
        ],
        ran['tops'],
        reason: what,
      );
      final stops = (ran['stops'] as List).cast<num>();
      expect(run.stops.length, stops.length, reason: what);
      for (final (i, stop) in stops.indexed) {
        expect(run.stops[i], closeTo(stop, 1e-3), reason: what);
      }
      for (final (i, delay) in (ran['delays'] as List).cast<num>().indexed) {
        expect(run.delays[i], closeTo(delay, 1e-4), reason: what);
      }
      for (final (i, value) in (ran['last'] as List).cast<num>().indexed) {
        expect(run.frames.last[i], closeTo(value, 0.02), reason: '$what, frame value $i');
      }
      styles.add(run.style);
      if (run.entrance.isNotEmpty) entrances.add(run.entrance);
    }
    expect(styles, throwStyles.toSet());
    expect(entrances, lastDieEntrances.toSet());
  });

  test('every die lies still at each stop, flat on a face', () {
    for (final seed in [3, 77, 2024, 99991]) {
      final run = simulate(
        count: 7,
        radius: 24,
        width: 300,
        height: 158,
        seed: seed,
        late: 6,
        from: const [-1, -1, 1, -1, 3, -1, -1],
      );
      // Once for the hand, then once after each die a 20 threw.
      expect(run.stops, hasLength(3));
      expect(run.stops, orderedEquals(run.stops.toList()..sort()));
      expect(run.duration, closeTo(run.stops.last, 1e-9));
      final end = run.frames.last;
      for (var i = 0; i < 7; i++) {
        expect(end[i * 7 + 2], 0, reason: 'die $i is on the tray');
        expect(end[i * 7], inInclusiveRange(24 + 4 - 0.01, 300 - 24 - 4 + 0.01));
        expect(end[i * 7 + 1], inInclusiveRange(24 + 4 - 0.01, 158 - 24 - 4 + 0.01));
        final q = Quat(end[i * 7 + 3], end[i * 7 + 4], end[i * 7 + 5], end[i * 7 + 6]);
        // The face that is up points straight at the eye.
        expect(q.rotate(faces[run.tops[i].face].n).z, closeTo(1, 1e-3));
      }
      // The dice thrown by a 20 come out after the hand lies still, one at a time.
      expect(run.delays[2], greaterThanOrEqualTo(run.stops[0]));
      expect(run.delays[4], greaterThanOrEqualTo(run.stops[1]));
    }
  });

  test('the face a die ends on shows the number the server rolled', () {
    for (var top = 0; top < 20; top++) {
      for (var value = 1; value <= 20; value++) {
        final labels = labelsFor(top, value);
        expect(labels[top], value);
        expect(labels.toSet(), {for (var n = 1; n <= 20; n++) n});
        // Opposite faces add up to 21, as on a real die.
        for (final face in faces) {
          expect(labels[face.index] + labels[face.opposite], 21);
        }
      }
    }
  });

  test('a seed sent as text always gives the same number', () {
    expect(seedOf('a1b2c3'), seedOf('a1b2c3'));
    expect(seedOf('a1b2c3'), isNot(seedOf('a1b2c4')));
    expect(seedOf(''), inInclusiveRange(0, 0xFFFFFFFF));
    final rnd = seeded(seedOf('a1b2c3'));
    final again = seeded(seedOf('a1b2c3'));
    for (var i = 0; i < 50; i++) {
      final value = rnd();
      expect(value, inInclusiveRange(0, 1));
      expect(again(), value);
    }
  });
}
