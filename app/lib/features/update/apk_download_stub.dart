import 'package:http/http.dart' as http;

import 'update_problem.dart';

/// The web build never updates itself, so it never downloads an APK.
Future<String> downloadApk({
  required http.Client client,
  required Uri url,
  required int size,
  required String folder,
  required String name,
  required void Function(double done) onProgress,
}) async => throw UpdateProblem.download;
