import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

/// The launcher icons that tool/app_icon/render.mjs draws (DESIGN.md, "App icon"): every platform
/// gets each size it asks for, and the icons that must be opaque have no alpha channel.

const _res = 'android/app/src/main/res';
const _iosSet = 'ios/Runner/Assets.xcassets/AppIcon.appiconset';
const _densities = {'mdpi': 1.0, 'hdpi': 1.5, 'xhdpi': 2.0, 'xxhdpi': 3.0, 'xxxhdpi': 4.0};

// PNG colour types: 2 is RGB, 6 is RGBA.
const _rgb = 2;
const _rgba = 6;

typedef _Png = ({int width, int height, int colorType});

_Png _readPng(String path) {
  final file = File(path);
  expect(file.existsSync(), isTrue, reason: '$path is missing');
  final bytes = file.readAsBytesSync();
  expect(ascii.decode(bytes.sublist(1, 4)), 'PNG', reason: '$path is not a PNG');
  final header = ByteData.sublistView(bytes, 16, 26);
  return (width: header.getUint32(0), height: header.getUint32(4), colorType: header.getUint8(9));
}

void _expectPng(String path, int side, {required int colorType}) {
  final png = _readPng(path);
  expect((png.width, png.height), (side, side), reason: '$path should be $side px square');
  expect(png.colorType, colorType, reason: '$path has the wrong colour type');
}

void main() {
  test('Android has the adaptive layers and the legacy icon at every density', () {
    for (final MapEntry(key: density, value: scale) in _densities.entries) {
      final dir = '$_res/mipmap-$density';
      _expectPng('$dir/ic_launcher.png', (48 * scale).round(), colorType: _rgba);
      _expectPng('$dir/ic_launcher_background.png', (108 * scale).round(), colorType: _rgb);
      _expectPng('$dir/ic_launcher_foreground.png', (108 * scale).round(), colorType: _rgba);
      _expectPng('$dir/ic_launcher_monochrome.png', (108 * scale).round(), colorType: _rgba);
    }
    final adaptive = File('$_res/mipmap-anydpi-v26/ic_launcher.xml').readAsStringSync();
    for (final layer in ['background', 'foreground', 'monochrome']) {
      expect(adaptive, contains('<$layer android:drawable="@mipmap/ic_launcher_$layer"'));
    }
    final manifest = File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(manifest, contains('android:icon="@mipmap/ic_launcher"'));
  });

  test('iOS has every icon its asset catalog lists, opaque as the App Store requires', () {
    final contents = jsonDecode(File('$_iosSet/Contents.json').readAsStringSync()) as Map;
    final images = (contents['images'] as List).cast<Map>();
    expect(images, isNotEmpty);
    for (final image in images) {
      final points = double.parse((image['size'] as String).split('x').first);
      final scale = double.parse((image['scale'] as String).replaceAll('x', ''));
      _expectPng('$_iosSet/${image['filename']}', (points * scale).round(), colorType: _rgb);
    }
  });

  test('the web has its favicon, its manifest icons and an opaque home-screen icon', () {
    _expectPng('web/favicon.png', 32, colorType: _rgba);
    final manifest = jsonDecode(File('web/manifest.json').readAsStringSync()) as Map;
    final icons = (manifest['icons'] as List).cast<Map>();
    expect(icons, hasLength(4));
    for (final icon in icons) {
      final side = int.parse((icon['sizes'] as String).split('x').first);
      // A maskable icon is cropped by the browser, so it is full bleed and opaque.
      final maskable = icon['purpose'] == 'maskable';
      _expectPng('web/${icon['src']}', side, colorType: maskable ? _rgb : _rgba);
    }
    final index = File('web/index.html').readAsStringSync();
    expect(index, contains('<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">'));
    _expectPng('web/icons/apple-touch-icon.png', 180, colorType: _rgb);
  });
}
