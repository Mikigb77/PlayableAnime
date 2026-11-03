import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import 'byok_store.dart';
import 'config.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.body);

  final int statusCode;
  final String body;

  @override
  String toString() => 'ApiException($statusCode): $body';
}

class ApiClient {
  ApiClient(this._byok, {required this.baseUrl, http.Client? client})
    : _http = client ?? http.Client();

  final String baseUrl;
  final ByokStore _byok;
  final http.Client _http;

  Future<Object?> get(String path) => _send('GET', path);

  Future<Object?> post(String path, Map<String, Object?> body) => _send('POST', path, body);

  Future<Object?> _send(String method, String path, [Map<String, Object?>? body]) async {
    final request = http.Request(method, Uri.parse('$baseUrl$path'));
    final key = await _byok.readGeminiKey();
    if (key != null && key.isNotEmpty) {
      request.headers['X-LLM-Provider'] = 'gemini';
      request.headers['X-LLM-Api-Key'] = key;
    }
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    final response = await http.Response.fromStream(await _http.send(request));
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }
}

final apiClientProvider = Provider(
  (ref) => ApiClient(ref.watch(byokStoreProvider), baseUrl: AppConfig.apiBaseUrl),
);
