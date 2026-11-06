// The download needs files, which the web build doesn't have; it never updates itself anyway.
export 'apk_download_stub.dart' if (dart.library.io) 'apk_download_io.dart';
