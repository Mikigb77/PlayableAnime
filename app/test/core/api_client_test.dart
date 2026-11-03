import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/api/turn_events.dart';

class FakeTokens implements TokenSource {
  FakeTokens({this.token = 'old', this.refreshTo});

  String? token;
  final String? refreshTo;
  int refreshes = 0;
  int expired = 0;

  @override
  String? get accessToken => token;

  @override
  Future<bool> refresh() async {
    refreshes++;
    if (refreshTo == null) return false;
    token = refreshTo;
    return true;
  }

  @override
  Future<void> onSessionExpired() async {
    expired++;
    token = null;
  }
}

class FakeByok implements ByokSource {
  FakeByok(this.key);

  final String? key;

  @override
  Future<String?> readGeminiKey() async => key;
}

http.Response json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});

ApiClient client(MockClient mock, {TokenSource? tokens, ByokSource? byok}) => ApiClient(
  baseUrl: 'https://api.test',
  httpClient: mock,
  tokens: tokens,
  byok: byok,
  timeout: const Duration(milliseconds: 200),
  modelTimeout: const Duration(seconds: 2),
);

void main() {
  test('sends JSON with the bearer token and decodes the reply', () async {
    late http.Request seen;
    final api = client(
      MockClient((r) async {
        seen = r;
        return json({'ok': true});
      }),
      tokens: FakeTokens(),
    );
    expect(await api.patch('/v1/me', {'display_name': 'Ren'}), {'ok': true});
    expect(seen.method, 'PATCH');
    expect(seen.url.toString(), 'https://api.test/v1/me');
    expect(seen.headers['Authorization'], 'Bearer old');
    expect(jsonDecode(seen.body), {'display_name': 'Ren'});
  });

  test('turns the error envelope into a typed ApiException', () async {
    final api = client(
      MockClient(
        (_) async => json({
          'error': {
            'code': 'out_of_credits',
            'message': 'No credits',
            'details': {'balance_cents': 1.5},
          },
        }, 402),
      ),
    );
    final error = await api.get('/v1/x').then<Object?>((_) => null, onError: (Object e) => e);
    expect(error, isA<ApiException>());
    final e = error! as ApiException;
    expect(e.code, ApiErrorCode.outOfCredits);
    expect(e.status, 402);
    expect(e.balanceCents, 1.5);
  });

  test('reads the typed details of other errors', () {
    final conflict = ApiException.fromResponse(
      409,
      '{"error": {"code": "version_conflict", "message": "", "details": {"current_version": 12}}}',
    );
    expect(conflict.currentVersion, 12);
    final limited = ApiException.fromResponse(
      429,
      '{"error": {"code": "rate_limited", "message": "", "details": {"retry_after_s": 2.5}}}',
    );
    expect(limited.retryAfter, const Duration(milliseconds: 2500));
    final quota = ApiException.fromResponse(
      429,
      '{"error": {"code": "quota_exceeded", "message": "", "details": {"resets_at": "2026-11-04T00:00:00Z"}}}',
    );
    expect(quota.resetsAt, DateTime.utc(2026, 11, 4));
    expect(
      ApiException.fromResponse(400, '{"error": {"code": "brand_new"}}').code,
      ApiErrorCode.unknown,
    );
  });

  test('every server code is known, and a 5xx is worth retrying', () {
    for (final (status, wire, code) in [
      (405, 'method_not_allowed', ApiErrorCode.methodNotAllowed),
      (500, 'internal_error', ApiErrorCode.internalError),
      (503, 'sign_in_unavailable', ApiErrorCode.signInUnavailable),
      // A code added later is still a server failure on a 5xx.
      (503, 'brand_new', ApiErrorCode.server),
    ]) {
      final e = ApiException.fromResponse(status, '{"error": {"code": "$wire", "message": ""}}');
      expect(e.code, code, reason: wire);
    }
    expect(ApiErrorCode.internalError.isRetryable, isTrue);
    expect(ApiErrorCode.methodNotAllowed.isRetryable, isFalse);
  });

  test('reads retry on their own only after failures that may pass', () {
    Duration? retry(int count, ApiErrorCode code) => retryTransient(count, ApiException(code));
    expect(
      [for (var i = 0; i < 4; i++) retry(i, ApiErrorCode.network)],
      [
        const Duration(milliseconds: 500),
        const Duration(seconds: 1),
        const Duration(seconds: 2),
        null,
      ],
    );
    expect(retry(0, ApiErrorCode.internalError), isNotNull);
    for (final code in [
      ApiErrorCode.notFound,
      ApiErrorCode.forbidden,
      ApiErrorCode.rateLimited,
      ApiErrorCode.quotaExceeded,
      ApiErrorCode.unauthenticated,
    ]) {
      expect(retry(0, code), isNull, reason: code.wire);
    }
    expect(retryTransient(0, StateError('a bug')), isNull);
  });

  test('a reply without the envelope becomes a status-based code', () async {
    final api = client(MockClient((_) async => http.Response('<html>Bad gateway</html>', 502)));
    await expectLater(
      api.get('/v1/x'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.server)),
    );
    expect(ApiException.fromResponse(404, '').code, ApiErrorCode.notFound);
  });

  test('a request that calls a model may take longer than the others', () async {
    final api = client(
      MockClient((_) => Future.delayed(const Duration(milliseconds: 500), () => json({}))),
    );
    expect(await api.post('/v1/stories', {'premise': 'A long one'}), isEmpty);
    await expectLater(
      api.get('/v1/stories'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.timeout)),
    );
  });

  test('a JSON reply to a streamed request fails with a typed error', () async {
    ApiStreamResponse reply(Stream<List<int>> body) =>
        ApiStreamResponse(200, 'application/json', body);
    await expectLater(
      reply(Stream.error(http.ClientException('Connection closed'))).json(),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.network)),
    );
    await expectLater(
      reply(Stream.value(utf8.encode('{"scene": '))).json(),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.server)),
    );
  });

  test('a connection failure is a network error', () async {
    final api = client(MockClient((_) async => throw http.ClientException('refused')));
    await expectLater(
      api.get('/v1/x'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.network)),
    );
  });

  test('a slow server is a timeout', () async {
    final api = client(
      MockClient((_) => Future.delayed(const Duration(seconds: 1), () => json({}))),
    );
    await expectLater(
      api.get('/v1/x'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.timeout)),
    );
  });

  test('a 401 refreshes once and retries with the new token', () async {
    final seen = <String?>[];
    final tokens = FakeTokens(refreshTo: 'new');
    final api = client(
      MockClient((r) async {
        seen.add(r.headers['Authorization']);
        return r.headers['Authorization'] == 'Bearer new'
            ? json({'ok': true})
            : json({
                'error': {'code': 'unauthenticated', 'message': ''},
              }, 401);
      }),
      tokens: tokens,
    );
    expect(await api.get('/v1/me'), {'ok': true});
    expect(seen, ['Bearer old', 'Bearer new']);
    expect(tokens.refreshes, 1);
    expect(tokens.expired, 0);
  });

  test('a refresh the server refuses signs out', () async {
    final tokens = FakeTokens();
    final api = client(MockClient((_) async => json({}, 401)), tokens: tokens);
    await expectLater(
      api.get('/v1/me'),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.unauthenticated)),
    );
    expect(tokens.refreshes, 1);
    expect(tokens.expired, 1);
  });

  test('auth calls go without a token and never refresh', () async {
    late http.Request seen;
    final tokens = FakeTokens();
    final api = client(
      MockClient((r) async {
        seen = r;
        return json({}, 401);
      }),
      tokens: tokens,
    );
    await expectLater(
      api.post('/v1/auth/login', {}, authenticated: false),
      throwsA(isA<ApiException>()),
    );
    expect(seen.headers.containsKey('Authorization'), isFalse);
    expect(tokens.refreshes, 0);
  });

  test('the player key goes only with requests that may call a model', () async {
    final keyed = <String>[];
    final api = client(
      MockClient((r) async {
        if (r.headers['X-LLM-Api-Key'] == 'k-123') keyed.add('${r.method} ${r.url.path}');
        expect(
          r.headers['X-LLM-Provider'],
          r.headers.containsKey('X-LLM-Api-Key') ? 'gemini' : null,
        );
        return json({});
      }),
      byok: FakeByok('k-123'),
    );
    await api.get('/v1/stories');
    await api.post('/v1/stories/s1/turns', {});
    await api.post('/v1/drafts', {});
    await api.post('/v1/stories/s1/scenes/3/image', null);
    await api.post('/v1/stories/s1/scenes/3/report', {});
    await api.patch('/v1/me', {});
    await api.post('/v1/auth/login', {}, authenticated: false);
    expect(keyed, [
      'POST /v1/stories/s1/turns',
      'POST /v1/drafts',
      'POST /v1/stories/s1/scenes/3/image',
    ]);
  });

  test('a 204 decodes to null', () async {
    final api = client(MockClient((_) async => http.Response('', 204)));
    expect(await api.delete('/v1/stories/s1'), isNull);
  });

  test('openStream throws pre-stream errors and streams events', () async {
    final api = client(
      MockClient.streaming((request, _) async {
        if (request.url.path.endsWith('/bad/turns')) {
          return http.StreamedResponse(
            Stream.value(utf8.encode('{"error": {"code": "version_conflict", "message": ""}}')),
            409,
          );
        }
        return http.StreamedResponse(
          Stream.fromIterable([
            utf8.encode('event: turn.started\ndata: {"turn": 2}\n\n'),
            utf8.encode(
              'event: scene.completed\ndata: {"scene": {"turn": 2}, "story": {"version": 3}}\n\n',
            ),
          ]),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      }),
    );
    await expectLater(
      api.turn('bad', {}),
      throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.versionConflict)),
    );
    final events = await (await api.turn('good', {})).toList();
    expect(events.map((e) => e.runtimeType), [TurnStarted, SceneCompleted]);
  });
}
