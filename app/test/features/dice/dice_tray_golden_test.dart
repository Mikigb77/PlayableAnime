import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/story/dice/dice_tray.dart';

/// Compares a picture with its saved one the way an eye would: a pixel counts as different only
/// when a channel is off by more than [channel], and the pictures match while no more than
/// [share] of the pixels are. The last bit of an edge or a gradient is drawn differently from one
/// processor to the next, and a wrong face, color or number moves far more than that.
class _ByEye extends LocalFileComparator {
  _ByEye(super.testFile);

  static const channel = 24;
  static const share = 0.004;

  @override
  Future<bool> compare(Uint8List imageBytes, Uri golden) async {
    final got = await _pixels(imageBytes);
    final want = await _pixels(Uint8List.fromList(await getGoldenBytes(golden)));
    if (got.width != want.width || got.height != want.height) {
      throw FlutterError(
        '$golden is ${want.width}x${want.height}, and the picture is ${got.width}x${got.height}.',
      );
    }
    var off = 0;
    for (var i = 0; i < got.bytes.length; i += 4) {
      for (var c = 0; c < 4; c++) {
        if ((got.bytes[i + c] - want.bytes[i + c]).abs() > channel) {
          off += 1;
          break;
        }
      }
    }
    final pixels = got.width * got.height;
    if (off <= pixels * share) return true;
    throw FlutterError(
      '$golden: $off of $pixels pixels differ, more than the ${(pixels * share).round()} allowed. '
      'If the dice are meant to look different now, run '
      '`flutter test --update-goldens test/features/dice` and look at the pictures.',
    );
  }

  static Future<({int width, int height, Uint8List bytes})> _pixels(Uint8List png) async {
    final codec = await ui.instantiateImageCodec(png);
    final image = (await codec.getNextFrame()).image;
    final data = await image.toByteData();
    final read = (width: image.width, height: image.height, bytes: data!.buffer.asUint8List());
    image.dispose();
    codec.dispose();
    return read;
  }
}

/// The dice as the painter draws them (S15), against saved pictures at fixed seeds: every color
/// of die at rest, a die a 20 threw, and a hand in the air. How the dice move is checked against
/// the prototype's own numbers in `throw_sim_test.dart`; this checks how they look.
void main() {
  const size = Size(326, 158);

  setUpAll(() async {
    // The numbers on the faces are set in the reading serif.
    final serif = FontLoader(Fonts.serif);
    for (final file in ['Literata-Regular', 'Literata-SemiBold']) {
      serif.addFont(rootBundle.load('assets/fonts/$file.ttf'));
    }
    await serif.load();
    goldenFileComparator = _ByEye(Uri.parse('test/features/dice/dice_tray_golden_test.dart'));
  });

  Future<void> shows(
    WidgetTester tester,
    String name,
    DiceTray tray, {
    double? at,
    bool still = false,
    void Function(DiceTray tray)? lit,
  }) async {
    tester.view
      ..physicalSize = size
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    lit?.call(tray);
    final clock = TrayClock()..show(at ?? tray.duration);
    await tester.pumpWidget(
      RepaintBoundary(
        child: ColoredBox(
          // The felt the tray lies on, so the dice and their shadows are seen as in the app.
          color: const Color(0xFF10151F),
          child: CustomPaint(
            size: size,
            painter: DiceTrayPainter(tray: tray, clock: clock, still: still),
          ),
        ),
      ),
    );
    await expectLater(find.byType(RepaintBoundary), matchesGoldenFile('goldens/$name.png'));
  }

  testWidgets('a hand with a green die and the move\'s violet die, at rest', (tester) async {
    await shows(
      tester,
      'hand_at_rest',
      DiceTray(
        dice: const [
          TrayDie(value: 14, skin: DieSkin.plain),
          TrayDie(value: 9, skin: DieSkin.plain),
          TrayDie(value: 12, skin: DieSkin.adv),
          TrayDie(value: 19, skin: DieSkin.insight),
        ],
        seed: 7,
        size: size,
        style: 'spill',
        entrance: 'plunge',
      ),
    );
  });

  testWidgets('a gold die lit where it lies, among plain ones', (tester) async {
    await shows(
      tester,
      'gold_lit',
      DiceTray(
        dice: const [
          TrayDie(value: 12, skin: DieSkin.plain),
          TrayDie(value: 8, skin: DieSkin.plain),
          TrayDie(value: 5, skin: DieSkin.plain),
          TrayDie(value: 4, skin: DieSkin.mastery),
        ],
        seed: 21,
        size: size,
        style: 'whirl',
        entrance: 'bank',
      ),
      lit: (tray) => tray
        ..light(3, 1)
        ..pop(3, 1),
    );
  });

  testWidgets('a 20 and the die it threw', (tester) async {
    await shows(
      tester,
      'twenty_throws_one_more',
      DiceTray(
        dice: const [
          TrayDie(value: 20, skin: DieSkin.insight),
          TrayDie(value: 13, skin: DieSkin.burst, from: 0),
        ],
        seed: 33,
        size: size,
        style: 'tops',
        entrance: 'strike',
      ),
    );
  });

  testWidgets('the world\'s grey die', (tester) async {
    await shows(
      tester,
      'world_die',
      DiceTray(
        dice: const [TrayDie(value: 14, skin: DieSkin.world)],
        seed: 5,
        size: size,
        style: 'drop',
        entrance: 'fall',
      ),
    );
  });

  testWidgets('a hand in the air, and the same moment with reduced motion', (tester) async {
    DiceTray tray() => DiceTray(
      dice: const [
        TrayDie(value: 17, skin: DieSkin.plain),
        TrayDie(value: 3, skin: DieSkin.plain),
        TrayDie(value: 11, skin: DieSkin.insight),
      ],
      seed: 12,
      size: size,
      style: 'pour',
      entrance: 'hop',
    );
    final flying = tray();
    await shows(tester, 'hand_in_the_air', flying, at: flying.stops[0] * 0.45);
    final still = tray();
    await shows(tester, 'hand_in_the_air_still', still, at: still.stops[0] * 0.45, still: true);
  });
}
