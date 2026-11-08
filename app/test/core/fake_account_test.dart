import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';

import '../helpers.dart';

/// The fake's auth and account areas follow the merged backend (accounts and billing apps), so
/// the sign-in and account screens are built against the real shapes.
void main() {
  late ApiClient api;
  late FakeBackend backend;
  late TestTokens tokens;

  setUp(() {
    final fake = fakeApi();
    api = fake.api;
    backend = fake.backend;
    tokens = fake.tokens;
  });

  Future<JsonMap> post(String path, JsonMap body) async =>
      await api.post(path, body, authenticated: false) as JsonMap;

  JsonMap use(JsonMap session) {
    tokens
      ..accessToken = session['access_token'] as String
      ..refreshToken = session['refresh_token'] as String;
    return session;
  }

  Matcher apiError(ApiErrorCode code) => isA<ApiException>().having((e) => e.code, 'code', code);

  Matcher fieldProblem(String field, String type) =>
      isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError).having(
        (e) => e.fields,
        'fields',
        [allOf(containsPair('field', field), containsPair('type', type), contains('message'))],
      );

  JsonMap register({
    String email = 'ren@example.com',
    String password = 'moonlit-harbor',
    String name = '  Ren   Ito ',
    String birthDate = '2001-02-03',
  }) => {'email': email, 'password': password, 'display_name': name, 'birth_date': birthDate};

  group('register', () {
    test('answers 200 with a session, no starter credit until the email is verified', () async {
      final session = use(await post('/v1/auth/register', register()));
      final user = session['user'] as JsonMap;
      expect(user['display_name'], 'Ren Ito');
      expect(user['role'], 'player');
      expect(user['max_rating'], 'mature');
      expect(user, isNot(contains('birth_date')));
      expect(user['credits'], {'balance_cents': 0, 'unlimited': false});
      final credits = await api.get('/v1/me/credits') as JsonMap;
      expect(credits['entries'], isEmpty);
    });

    test('each problem names its field and type, the way the backend does', () async {
      await expectLater(
        post('/v1/auth/register', register(email: 'not-an-email')),
        throwsA(fieldProblem('email', 'invalid_email')),
      );
      await expectLater(
        post('/v1/auth/register', register(name: '   ')),
        throwsA(fieldProblem('display_name', 'missing')),
      );
      await expectLater(
        post('/v1/auth/register', register(birthDate: '2999-01-01')),
        throwsA(fieldProblem('birth_date', 'future')),
      );
      final now = DateTime.now();
      await expectLater(
        post('/v1/auth/register', register(birthDate: '${now.year - 10}-01-01')),
        throwsA(fieldProblem('birth_date', 'too_young')),
      );
      await expectLater(
        post('/v1/auth/register', register(birthDate: '1850-01-01')),
        throwsA(fieldProblem('birth_date', 'implausible')),
      );
      await expectLater(
        post('/v1/auth/register', register(email: FakeAuthState.demoEmail)),
        throwsA(fieldProblem('email', 'email_taken')),
      );
    });

    test('every password problem is listed at once', () async {
      await expectLater(
        post('/v1/auth/register', register(password: '1234')),
        throwsA(
          isA<ApiException>().having(
            (e) => [for (final f in e.fields) (f! as JsonMap)['type']],
            'types',
            ['password_too_short', 'password_entirely_numeric'],
          ),
        ),
      );
      await expectLater(
        post('/v1/auth/register', register(password: 'password')),
        throwsA(fieldProblem('password', 'password_too_common')),
      );
      await expectLater(
        post('/v1/auth/register', register(password: 'ren-rocks-1')),
        throwsA(fieldProblem('password', 'password_too_similar')),
      );
    });

    test('sign-up starts at 16, as the privacy policy says (F8)', () async {
      final now = DateTime.now();
      await expectLater(
        post('/v1/auth/register', register(birthDate: '${now.year - 15}-01-01')),
        throwsA(fieldProblem('birth_date', 'too_young')),
      );
    });

    test('a teen account is limited to Teen until their 17th birthday', () async {
      final now = DateTime.now();
      final session = await post(
        '/v1/auth/register',
        register(birthDate: '${now.year - 16}-01-01'),
      );
      expect((session['user'] as JsonMap)['max_rating'], 'teen');
    });
  });

  group('login', () {
    test('ten wrong passwords in 15 minutes for one email are rate limited', () async {
      var now = DateTime(2026, 11, 3, 12);
      final fake = fakeApi(clock: () => now);
      Future<JsonMap> logIn(String password) async =>
          await fake.api.post('/v1/auth/login', {
                'email': FakeAuthState.demoEmail,
                'password': password,
              }, authenticated: false)
              as JsonMap;

      for (var i = 0; i < 10; i++) {
        await expectLater(logIn('nope'), throwsA(apiError(ApiErrorCode.unauthenticated)));
        now = now.add(const Duration(seconds: 30));
      }
      await expectLater(
        logIn(FakeAuthState.demoPassword),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', ApiErrorCode.rateLimited)
              .having((e) => e.details['retry_after_s'], 'retry_after_s', 600),
        ),
      );

      // Once the first failure is 15 minutes old, the right password works again.
      now = DateTime(2026, 11, 3, 12, 15);
      expect((await logIn(FakeAuthState.demoPassword))['user'], isNotNull);
    });
  });

  group('google', () {
    test('a first sign-in asks for a birth date, then gets the starter credit', () async {
      await expectLater(
        post('/v1/auth/google', {'id_token': FakeGoogleTokens.newPlayer}),
        throwsA(apiError(ApiErrorCode.birthDateRequired)),
      );
      final session = use(
        await post('/v1/auth/google', {
          'id_token': FakeGoogleTokens.newPlayer,
          'birth_date': '1999-09-09',
        }),
      );
      final user = session['user'] as JsonMap;
      expect(user['credits'], {'balance_cents': 50, 'unlimited': false});

      // The account exists now, so the date isn't asked again.
      final again = await post('/v1/auth/google', {'id_token': FakeGoogleTokens.newPlayer});
      expect((again['user'] as JsonMap)['id'], user['id']);
    });

    test('a birth date too young is refused like on register', () async {
      final now = DateTime.now();
      await expectLater(
        post('/v1/auth/google', {
          'id_token': FakeGoogleTokens.newPlayer,
          'birth_date': '${now.year - 9}-05-05',
        }),
        throwsA(fieldProblem('birth_date', 'too_young')),
      );
    });

    test('its error triggers match the backend', () async {
      await expectLater(
        post('/v1/auth/google', {'id_token': FakeGoogleTokens.invalid}),
        throwsA(apiError(ApiErrorCode.unauthenticated)),
      );
      await expectLater(
        post('/v1/auth/google', {'id_token': FakeGoogleTokens.unavailable}),
        throwsA(apiError(ApiErrorCode.signInUnavailable)),
      );
      await expectLater(
        post('/v1/auth/google', {'id_token': FakeGoogleTokens.unverified}),
        throwsA(apiError(ApiErrorCode.forbidden)),
      );
    });

    test('the owner plays free and still sees what each turn cost', () async {
      use(await post('/v1/auth/google', {'id_token': FakeGoogleTokens.owner}));
      final me = await api.get('/v1/me') as JsonMap;
      expect(me['role'], 'owner');
      expect(me['credits'], {'balance_cents': 50, 'unlimited': true});

      backend.data.account.charge(
        FakeAuthState.ownerUserId,
        kind: 'turn',
        cents: 2,
        now: DateTime.now(),
      );
      final credits = await api.get('/v1/me/credits') as JsonMap;
      expect(credits['unlimited'], isTrue);
      expect(credits['balance_cents'], 50);
      expect((credits['entries'] as List).first, containsPair('amount_cents', 0));
    });
  });

  group('account', () {
    setUp(() async {
      use(
        await post('/v1/auth/login', {
          'email': FakeAuthState.demoEmail,
          'password': FakeAuthState.demoPassword,
        }),
      );
    });

    test('PATCH changes only what is sent', () async {
      final me =
          await api.patch('/v1/me', {
                'display_name': '  Kai  ',
                'content_prefs': {'romance': false},
              })
              as JsonMap;
      expect(me['display_name'], 'Kai');
      expect(me['content_prefs'], {'gore': 'medium', 'romance': false, 'dark_themes': true});
      await expectLater(
        api.patch('/v1/me', {'display_name': '  '}),
        throwsA(fieldProblem('display_name', 'missing')),
      );
    });

    test('credits list newest first and check the limit', () async {
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: 2.25,
        now: DateTime.now(),
        storyId: 'story_ninth_peak',
        turn: 4,
      );
      final credits = await api.get('/v1/me/credits', query: {'limit': '1'}) as JsonMap;
      expect(credits['balance_cents'], 47.75);
      expect(credits['entries'], [
        allOf(
          containsPair('kind', 'turn'),
          containsPair('amount_cents', -2.25),
          containsPair('story_id', 'story_ninth_peak'),
          containsPair('turn', 4),
        ),
      ]);
      await expectLater(
        api.get('/v1/me/credits', query: {'limit': '500'}),
        throwsA(apiError(ApiErrorCode.validationError)),
      );
    });

    test('a charge never takes the balance below zero', () async {
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: 80,
        now: DateTime.now(),
      );
      final credits = await api.get('/v1/me/credits') as JsonMap;
      expect(credits['balance_cents'], 0);
      expect((credits['entries'] as List).first, containsPair('amount_cents', -50));
    });

    test('export holds the user, every story with its scenes, pictures and reports', () async {
      final scene = backend.data.stories.ownedBy(FakeAuthState.demoUserId).first.scenes.first;
      scene['image'] = {
        'planned': true,
        'kind': 'scene',
        'status': 'ready',
        'image_id': 'img_1',
        'url': 'asset:x',
      };
      await api.post('/v1/stories/story_ninth_peak/scenes/2/report', {
        'category': 'other',
        'note': 'Odd',
      });
      final export = await api.get('/v1/me/export') as JsonMap;
      expect((export['user'] as JsonMap)['id'], FakeAuthState.demoUserId);
      expect(export['stories'], hasLength(1));
      expect((export['stories'] as List).first, contains('scenes'));
      expect(export['images'], [
        allOf(
          containsPair('id', 'img_1'),
          containsPair('story_id', 'story_ninth_peak'),
          contains('expires_at'),
        ),
      ]);
      expect(export['reports'], [
        allOf(
          containsPair('story_id', 'story_ninth_peak'),
          containsPair('turn', 2),
          containsPair('block', false),
          containsPair('status', 'open'),
        ),
      ]);
    });

    test('deleting the account signs out every device and removes its stories', () async {
      final user = use(await post('/v1/auth/register', register()));
      final userId = (user['user'] as JsonMap)['id'] as String;
      await api.delete('/v1/me');
      expect(backend.data.auth.users, isNot(contains(userId)));
      await expectLater(api.get('/v1/me'), throwsA(apiError(ApiErrorCode.unauthenticated)));
      await expectLater(
        post('/v1/auth/refresh', {'refresh_token': user['refresh_token']}),
        throwsA(apiError(ApiErrorCode.unauthenticated)),
      );
      await expectLater(
        post('/v1/auth/login', {'email': 'ren@example.com', 'password': 'moonlit-harbor'}),
        throwsA(apiError(ApiErrorCode.unauthenticated)),
      );
    });

    test('the demo account comes back fresh after it is deleted', () async {
      await api.patch('/v1/me', {'display_name': 'Changed'});
      await api.post('/v1/stories/story_ninth_peak/scenes/2/report', {'category': 'other'});
      await api.delete('/v1/me');
      use(
        await post('/v1/auth/login', {
          'email': FakeAuthState.demoEmail,
          'password': FakeAuthState.demoPassword,
        }),
      );
      final me = await api.get('/v1/me') as JsonMap;
      expect(me['display_name'], 'Demo player');
      expect(me['credits'], {'balance_cents': 50, 'unlimited': false});
      // Nothing of the deleted account carries over, its reports included.
      expect((await api.get('/v1/me/export') as JsonMap)['reports'], isEmpty);
    });
  });
}
