import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'update_problem.dart';

/// How long the server may take to start answering, and to send the next part.
const _connectTimeout = Duration(seconds: 30);
const _idleTimeout = Duration(seconds: 60);

/// Downloads the APK at [url] to [folder]/[name] and returns its path. It must be exactly [size]
/// bytes; Android's installer checks its SHA-256 and signature after that. Earlier updates' files
/// in [folder] are deleted first, and a finished download of the same build is used again, so
/// trying again after the player said no to Android doesn't download it twice. [onProgress] gets
/// the share done, from 0 to 1, about a hundred times.
Future<String> downloadApk({
  required http.Client client,
  required Uri url,
  required int size,
  required String folder,
  required String name,
  required void Function(double done) onProgress,
}) async {
  final dir = Directory(folder);
  final target = File('${dir.path}/$name');
  final part = File('${target.path}.part');
  try {
    await dir.create(recursive: true);
    await for (final entry in dir.list()) {
      if (entry is File && entry.path != target.path) await entry.delete();
    }
    if (await target.exists()) {
      if (await target.length() == size) {
        onProgress(1);
        return target.path;
      }
      await target.delete();
    }
  } on FileSystemException {
    throw UpdateProblem.download;
  }

  final http.StreamedResponse response;
  try {
    response = await client.send(http.Request('GET', url)).timeout(_connectTimeout);
  } on Object {
    throw UpdateProblem.download;
  }
  if (response.statusCode != 200) {
    unawaited(response.stream.drain<void>().catchError((Object _) {}));
    throw UpdateProblem.download;
  }

  final sink = part.openWrite();
  var received = 0;
  var reported = -1;
  UpdateProblem? problem;
  try {
    await for (final chunk in response.stream.timeout(_idleTimeout)) {
      received += chunk.length;
      if (received > size) {
        problem = UpdateProblem.corrupt;
        break;
      }
      sink.add(chunk);
      final percent = received * 100 ~/ size;
      if (percent != reported) {
        reported = percent;
        onProgress(received / size);
      }
    }
    await sink.flush();
  } on Object {
    problem = UpdateProblem.download;
  } finally {
    await sink.close();
  }
  if (problem == null && received != size) problem = UpdateProblem.download;
  if (problem != null) {
    await _deleteQuietly(part);
    throw problem;
  }
  try {
    await part.rename(target.path);
  } on FileSystemException {
    await _deleteQuietly(part);
    throw UpdateProblem.download;
  }
  return target.path;
}

Future<void> _deleteQuietly(File file) async {
  try {
    await file.delete();
  } on FileSystemException {
    // Already gone; the next download clears the folder anyway.
  }
}
