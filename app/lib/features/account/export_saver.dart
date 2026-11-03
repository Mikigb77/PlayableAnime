import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

/// Hands the player a file: the share sheet on a phone (save to Files, send it anywhere), a
/// download in a browser.
abstract interface class ExportSaver {
  /// Returns false when the player dismissed the share sheet.
  Future<bool> save(Uint8List bytes, {required String fileName, Rect? origin});
}

class ShareExportSaver implements ExportSaver {
  const ShareExportSaver();

  @override
  Future<bool> save(Uint8List bytes, {required String fileName, Rect? origin}) async {
    final result = await SharePlus.instance.share(
      ShareParams(
        files: [XFile.fromData(bytes, mimeType: 'application/json', name: fileName)],
        fileNameOverrides: [fileName],
        sharePositionOrigin: origin,
        // On the web, browsers that can't share a JSON file download it instead.
        downloadFallbackEnabled: true,
      ),
    );
    return result.status != ShareResultStatus.dismissed;
  }
}

final exportSaverProvider = Provider<ExportSaver>((ref) => const ShareExportSaver());

/// Where a share sheet anchors on an iPad: the widget that opened it.
Rect? originOf(BuildContext context) {
  final box = context.findRenderObject();
  if (box is! RenderBox || !box.hasSize) return null;
  return box.localToGlobal(Offset.zero) & box.size;
}
