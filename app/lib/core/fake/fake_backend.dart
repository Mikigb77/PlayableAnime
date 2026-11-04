import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../api/sse.dart';
import '../json.dart';
import 'fake_account.dart';
import 'fake_auth.dart';
import 'fake_data.dart';
import 'fake_drafts.dart';
import 'fake_pictures.dart';
import 'fake_premises.dart';
import 'fake_reports.dart';
import 'fake_speech.dart';
import 'fake_stories.dart';
import 'fake_turns.dart';

/// How fast the fake answers. Tests use [FakePace.instant]; the app uses [FakePace.realistic] so
/// loading states, streaming and pictures look the way they will against the real backend.
class FakePace {
  const FakePace({
    required this.latency,
    required this.firstWords,
    required this.perChunk,
    required this.picture,
    this.drafting = Duration.zero,
  });

  static const instant = FakePace(
    latency: Duration.zero,
    firstWords: Duration.zero,
    perChunk: Duration.zero,
    picture: Duration.zero,
  );

  static const realistic = FakePace(
    latency: Duration(milliseconds: 350),
    firstWords: Duration(milliseconds: 700),
    perChunk: Duration(milliseconds: 45),
    picture: Duration(milliseconds: 2600),
    drafting: Duration(milliseconds: 3200),
  );

  /// Before any JSON reply.
  final Duration latency;

  /// From `turn.started` to the first narration words (S3 asks for under 2 s).
  final Duration firstWords;

  /// Between narration chunks.
  final Duration perChunk;

  /// How long a picture stays `pending` (M3).
  final Duration picture;

  /// How long drafting or redrafting a world takes, on top of [latency] (G1).
  final Duration drafting;
}

class FakeRequest {
  FakeRequest({
    required this.method,
    required this.uri,
    required this.params,
    required this.headers,
    required this.body,
    this.userId,
  });

  final String method;
  final Uri uri;

  /// Path parameters, such as `id` for `/v1/stories/:id`.
  final Map<String, String> params;
  final Map<String, String> headers;
  final Object? body;

  /// The signed-in user, set for every route that isn't public.
  final String? userId;

  JsonMap get json => body is JsonMap ? body! as JsonMap : const {};

  String param(String name) => params[name]!;

  String? query(String name) => uri.queryParameters[name];

  bool get usesOwnKey => headers['x-llm-api-key']?.isNotEmpty ?? false;
}

class FakeResponse {
  const FakeResponse._(this.status, {this.json, this.events});

  factory FakeResponse.json(Object? body, {int status = 200}) => FakeResponse._(status, json: body);

  static const noContent = FakeResponse._(204);

  /// The error envelope from docs/API.md.
  factory FakeResponse.error(
    int status,
    String code,
    String message, [
    JsonMap details = const {},
  ]) => FakeResponse._(
    status,
    json: {
      'error': {'code': code, 'message': message, 'details': details},
    },
  );

  /// A `text/event-stream` reply; each item is one encoded event (see [encodeSseEvent]).
  factory FakeResponse.sse(Stream<String> events) => FakeResponse._(200, events: events);

  final int status;
  final Object? json;
  final Stream<String>? events;
}

typedef FakeHandler = FutureOr<FakeResponse> Function(FakeRequest request);

class _Route {
  _Route(this.method, String pattern, this.handler, this.public)
    : names = [for (final m in RegExp(r':(\w+)').allMatches(pattern)) m.group(1)!],
      regex = RegExp('^${pattern.replaceAllMapped(RegExp(r':(\w+)'), (_) => '([^/]+)')}\$');

  final String method;
  final RegExp regex;
  final List<String> names;
  final FakeHandler handler;
  final bool public;
}

/// An in-memory backend that speaks docs/API.md, plugged in as the HTTP client so the real
/// [ApiClient], its error handling and the SSE parser all run unchanged.
///
/// Each feature area registers its routes from its own file (fake_auth.dart, fake_stories.dart,
/// fake_turns.dart and so on), so the app threads extend their own area without touching the rest.
class FakeBackend extends http.BaseClient {
  FakeBackend({FakeData? data, this.pace = FakePace.instant, DateTime Function()? clock})
    : data = data ?? FakeData(),
      now = clock ?? DateTime.now;

  /// The fake backend with every area registered and seeded.
  factory FakeBackend.standard({FakePace pace = FakePace.realistic, DateTime Function()? clock}) {
    final backend = FakeBackend(pace: pace, clock: clock);
    registerAuthRoutes(backend);
    registerAccountRoutes(backend);
    registerPremiseRoutes(backend);
    registerDraftRoutes(backend);
    registerStoryRoutes(backend);
    registerTurnRoutes(backend);
    registerPictureRoutes(backend);
    registerReportRoutes(backend);
    registerSpeechRoutes(backend);
    return backend;
  }

  static const baseUrl = 'https://fake.lucid.invalid';

  final FakeData data;
  final FakePace pace;
  final DateTime Function() now;

  /// Every request received, newest last, for tests.
  final List<FakeRequest> requests = [];

  final _routes = <_Route>[];

  /// Registers a handler. `:name` segments become [FakeRequest.params]. Routes need a valid
  /// access token unless [public] (the `/health` and `/v1/auth/*` routes).
  void route(String method, String pattern, FakeHandler handler, {bool public = false}) =>
      _routes.add(_Route(method, pattern, handler, public));

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    // JSON bodies arrive decoded; anything else, such as a dictated recording, as bytes.
    final body = switch (request) {
      http.Request(bodyBytes: final bytes) when bytes.isEmpty => null,
      http.Request(headers: final headers) when _isJson(headers) => jsonDecode(request.body),
      http.Request(:final bodyBytes) => bodyBytes,
      _ => null,
    };
    final path = request.url.path;
    final response = await _dispatch(request, path, body);
    if (pace.latency > Duration.zero && response.events == null) {
      await Future<void>.delayed(pace.latency);
    }
    return _encode(request, response);
  }

  static bool _isJson(Map<String, String> headers) {
    final type = headers.entries
        .where((e) => e.key.toLowerCase() == 'content-type')
        .map((e) => e.value)
        .firstOrNull;
    return type == null || type.startsWith('application/json');
  }

  Future<FakeResponse> _dispatch(http.BaseRequest request, String path, Object? body) async {
    var pathMatched = false;
    for (final route in _routes) {
      final match = route.regex.firstMatch(path);
      if (match == null) continue;
      pathMatched = true;
      if (route.method != request.method) continue;
      String? userId;
      if (!route.public) {
        final auth = request.headers['authorization'] ?? request.headers['Authorization'];
        userId = auth != null && auth.startsWith('Bearer ')
            ? data.auth.userForAccessToken(auth.substring(7), now())
            : null;
        if (userId == null) {
          return FakeResponse.error(401, 'unauthenticated', 'Sign in again.');
        }
      }
      final fakeRequest = FakeRequest(
        method: request.method,
        uri: request.url,
        params: {
          for (var i = 0; i < route.names.length; i++)
            route.names[i]: Uri.decodeComponent(match.group(i + 1)!),
        },
        headers: {for (final e in request.headers.entries) e.key.toLowerCase(): e.value},
        body: body,
        userId: userId,
      );
      requests.add(fakeRequest);
      try {
        return await route.handler(fakeRequest);
      } on FakeError catch (e) {
        return FakeResponse.error(e.status, e.code, e.message, e.details);
      }
    }
    return pathMatched
        ? FakeResponse.error(405, 'validation_error', 'Method not allowed')
        : FakeResponse.error(404, 'not_found', 'No fake route for $path');
  }

  http.StreamedResponse _encode(http.BaseRequest request, FakeResponse response) {
    if (response.events case final events?) {
      return http.StreamedResponse(
        events.map(utf8.encode),
        200,
        headers: {'content-type': 'text/event-stream; charset=utf-8'},
        request: request,
      );
    }
    final bytes = response.json == null && response.status == 204
        ? const <int>[]
        : utf8.encode(jsonEncode(response.json));
    return http.StreamedResponse(
      Stream.value(bytes),
      response.status,
      contentLength: bytes.length,
      headers: {'content-type': 'application/json; charset=utf-8'},
      request: request,
    );
  }
}

/// Thrown by a handler to answer with an API error.
class FakeError implements Exception {
  const FakeError(this.status, this.code, this.message, [this.details = const {}]);

  const FakeError.notFound([String what = 'Not found']) : this(404, 'not_found', what);

  const FakeError.validation(String message) : this(400, 'validation_error', message);

  final int status;
  final String code;
  final String message;
  final JsonMap details;
}

/// An event name that makes [pacedEvents] drop the connection instead of sending an event.
const fakeDroppedConnection = '__dropped__';

/// Paces a list of events: `await` the delay before each one. [fakeDroppedConnection] ends the
/// stream with a network error, as a dropped connection would.
Stream<String> pacedEvents(Iterable<(Duration, String event, Object? data)> events) async* {
  for (final (delay, event, data) in events) {
    if (delay > Duration.zero) await Future<void>.delayed(delay);
    if (event == fakeDroppedConnection) {
      throw http.ClientException('Connection closed while receiving data');
    }
    yield encodeSseEvent(event, data);
  }
}
