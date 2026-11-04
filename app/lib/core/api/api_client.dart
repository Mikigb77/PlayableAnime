import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_error.dart';
import 'sse.dart';
import 'turn_events.dart';

/// Supplies the bearer token and refreshes it (T8). The session controller implements this; the
/// accounts work (WS13) adds the sign-in flows that create a session.
abstract interface class TokenSource {
  /// The current access token, or null when signed out.
  String? get accessToken;

  /// Gets a fresh access token after a 401. Returns false when the session can't be refreshed.
  /// Concurrent calls share one refresh.
  Future<bool> refresh();

  /// Called when a refreshed request is still unauthenticated, or the refresh failed: sign out.
  Future<void> onSessionExpired();
}

/// Supplies the player's own model key (S9). It travels only with requests that may call a model
/// and the backend never stores or logs it (T6).
abstract interface class ByokSource {
  Future<String?> readGeminiKey();
}

/// The response of a request that may stream: a turn (`text/event-stream`) or, from the legacy
/// backend, a plain JSON reply.
class ApiStreamResponse {
  ApiStreamResponse(this.statusCode, this.contentType, this._body);

  final int statusCode;
  final String? contentType;
  final Stream<List<int>> _body;

  bool get isEventStream => contentType?.startsWith('text/event-stream') ?? false;

  Stream<SseEvent> events() => _body.transform(const SseParser());

  Stream<TurnEvent> turnEvents() => parseTurnEvents(events());

  /// The whole body as JSON. Like every other call, a failure comes back as [ApiException].
  Future<Object?> json() async {
    try {
      return _decode(await http.ByteStream(_body).toBytes());
    } on ApiException {
      rethrow;
    } on FormatException {
      throw ApiException(ApiErrorCode.server, status: statusCode);
    } on http.ClientException catch (e) {
      throw ApiException(ApiErrorCode.network, message: e.message);
    } on Exception catch (e) {
      throw ApiException(ApiErrorCode.network, message: '$e');
    }
  }
}

Object? _decode(List<int> bytes) => bytes.isEmpty ? null : jsonDecode(utf8.decode(bytes));

/// The HTTP client for docs/API.md: JSON in and out, bearer tokens with one refresh on a 401,
/// typed errors ([ApiException]) for every failure, and streamed turns.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    required http.Client httpClient,
    this.byok,
    this.tokens,
    this.timeout = const Duration(seconds: 30),
    this.modelTimeout = const Duration(minutes: 3),
    this.speechTimeout = const Duration(seconds: 90),
    this.streamIdleTimeout = const Duration(seconds: 150),
  }) : _http = httpClient;

  final String baseUrl;
  final http.Client _http;
  final ByokSource? byok;
  final TokenSource? tokens;

  /// How long to wait for a reply's headers and, for JSON, its body.
  final Duration timeout;

  /// The same for a request that calls a model (creating, drafting, a turn, a picture). Those
  /// answer only when the model has, and the model layer allows a node up to 120 s plus a retry;
  /// giving up sooner would not stop the server, which would still save the result.
  final Duration modelTimeout;

  /// The same for a dictation being written down (V6), which the player waits on with the mic
  /// spinning: longer than the server's worst case (three tries at the speech model's 20 s
  /// deadline after 429s, with 8 s of waits), plus an upload on a slow network.
  final Duration speechTimeout;

  /// How long a stream may stay silent before it counts as dropped: longer than the narrator's
  /// whole budget, because a turn can think for a while before its first words.
  final Duration streamIdleTimeout;

  Future<Object?> get(String path, {Map<String, String>? query}) =>
      _json('GET', path, query: query);

  /// Set [authenticated] to false for the `/v1/auth/*` calls, which run without a session.
  Future<Object?> post(String path, Object? body, {bool authenticated = true}) =>
      _json('POST', path, body: body, authenticated: authenticated);

  Future<Object?> patch(String path, Object? body) => _json('PATCH', path, body: body);

  Future<Object?> delete(String path) => _json('DELETE', path);

  /// Sends [bytes] as the body, such as a recording, with its own [contentType]. The reply is
  /// JSON, and failures throw [ApiException] like any other call.
  Future<Object?> postBytes(
    String path,
    List<int> bytes, {
    required String contentType,
    Map<String, String>? query,
  }) => _json('POST', path, bytes: (bytes, contentType), query: query);

  /// Sends a request whose reply may be a stream. Errors before the stream starts (auth, version,
  /// credits, rate limits) throw [ApiException] like any other call.
  Future<ApiStreamResponse> openStream(String path, Object? body) async {
    final response = await _send('POST', path, body: body, accept: 'text/event-stream');
    final idle = response.stream.timeout(
      streamIdleTimeout,
      onTimeout: (sink) {
        sink.addError(const ApiException(ApiErrorCode.timeout));
        sink.close();
      },
    );
    return ApiStreamResponse(response.statusCode, response.headers['content-type'], idle);
  }

  /// Takes a turn: `POST /v1/stories/{id}/turns` as server-sent events. The stream ends with
  /// [SceneCompleted] or [TurnFailed]; errors before streaming throw [ApiException].
  Future<Stream<TurnEvent>> turn(String storyId, Map<String, Object?> request) async {
    final response = await openStream('/v1/stories/$storyId/turns', request);
    return response.turnEvents();
  }

  Future<Object?> _json(
    String method,
    String path, {
    Object? body,
    (List<int>, String)? bytes,
    Map<String, String>? query,
    bool authenticated = true,
  }) async {
    final response = await _send(
      method,
      path,
      body: body,
      bytes: bytes,
      query: query,
      authenticated: authenticated,
    );
    final reply = await _guard(response.stream.toBytes(), _timeoutFor(method, path));
    try {
      return _decode(reply);
    } on FormatException {
      throw ApiException(ApiErrorCode.server, status: response.statusCode);
    }
  }

  Future<http.StreamedResponse> _send(
    String method,
    String path, {
    Object? body,
    (List<int>, String)? bytes,
    Map<String, String>? query,
    bool authenticated = true,
    String accept = 'application/json',
  }) async {
    final tokens = authenticated ? this.tokens : null;
    final byokKey = _callsModel(method, path) ? await byok?.readGeminiKey() : null;
    final wait = _timeoutFor(method, path);

    Future<http.StreamedResponse> attempt() async {
      final uri = Uri.parse(
        '$baseUrl$path',
      ).replace(queryParameters: query == null || query.isEmpty ? null : query);
      final request = http.Request(method, uri)..headers['Accept'] = accept;
      final token = tokens?.accessToken;
      if (token != null) request.headers['Authorization'] = 'Bearer $token';
      if (byokKey != null && byokKey.isNotEmpty) {
        request.headers['X-LLM-Provider'] = 'gemini';
        request.headers['X-LLM-Api-Key'] = byokKey;
      }
      if (bytes case (final data, final contentType)) {
        request.headers['Content-Type'] = contentType;
        request.bodyBytes = data;
      } else if (body != null) {
        request.headers['Content-Type'] = 'application/json; charset=utf-8';
        request.body = jsonEncode(body);
      }
      return _guard(_http.send(request), wait);
    }

    var response = await attempt();
    if (response.statusCode == 401 && tokens != null && tokens.accessToken != null) {
      // Refresh once and retry. A refresh that fails on the network throws and keeps the
      // session; one the server rejects signs out.
      await _drain(response);
      if (!await tokens.refresh()) {
        await tokens.onSessionExpired();
        throw const ApiException(ApiErrorCode.unauthenticated, status: 401);
      }
      response = await attempt();
      if (response.statusCode == 401) await tokens.onSessionExpired();
    }
    if (response.statusCode >= 400) {
      final text = utf8.decode(await _guard(response.stream.toBytes(), wait), allowMalformed: true);
      throw ApiException.fromResponse(response.statusCode, text);
    }
    return response;
  }

  /// Model-calling requests are the POSTs under drafts and stories (creating, revising, starting,
  /// turns, pictures) and a draft's direct edits, which redraft the world or the character when
  /// lines, rules, the gift or the rating change. Nothing else gets the player's key, or the longer
  /// timeout. Dictation calls a model too, but always on our account (V6), so it never gets the
  /// key, and it has a timeout of its own.
  static bool _callsModel(String method, String path) => switch (method) {
    'POST' =>
      (path.startsWith('/v1/drafts') || path.startsWith('/v1/stories')) &&
          !path.endsWith('/report'),
    'PATCH' => path.startsWith('/v1/drafts'),
    _ => false,
  };

  Duration _timeoutFor(String method, String path) => _callsModel(method, path)
      ? modelTimeout
      : path.startsWith('/v1/transcriptions')
      ? speechTimeout
      : timeout;

  Future<T> _guard<T>(Future<T> future, Duration wait) async {
    try {
      return await future.timeout(wait);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException(ApiErrorCode.timeout);
    } on http.ClientException catch (e) {
      throw ApiException(ApiErrorCode.network, message: e.message);
    } on Exception catch (e) {
      // dart:io's SocketException and friends, which can't be named on the web.
      throw ApiException(ApiErrorCode.network, message: '$e');
    }
  }

  static Future<void> _drain(http.StreamedResponse response) async {
    try {
      await response.stream.drain<void>();
    } on Object {
      // The body of a 401 doesn't matter.
    }
  }
}
