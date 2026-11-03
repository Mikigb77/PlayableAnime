import '../json.dart';
import 'fake_backend.dart';

/// Fake sign-in (docs/API.md, "Auth and account"). Owned by the accounts work (WS13).
///
/// The demo account is `demo@lucid.test` with password `lucid-demo`. Any Google ID token signs in
/// as the demo account, except `new-google-user`, which needs a birth date the first time (F8).
class FakeAuthState {
  FakeAuthState() {
    users[demoUserId] = {
      'id': demoUserId,
      'email': demoEmail,
      'display_name': 'Demo player',
      'role': 'player',
      'max_rating': 'mature',
      'content_prefs': {'gore': 'medium', 'romance': true, 'dark_themes': true},
    };
    passwords[demoEmail] = demoPassword;
  }

  static const demoUserId = 'user_demo';
  static const demoEmail = 'demo@lucid.test';
  static const demoPassword = 'lucid-demo';

  /// How long fake access tokens live.
  static const accessLifetime = Duration(minutes: 15);

  final users = <String, JsonMap>{};
  final passwords = <String, String>{};
  final _access = <String, (String userId, DateTime expiresAt)>{};
  final _refresh = <String, String>{};
  var _counter = 0;

  String? userForAccessToken(String token, DateTime now) {
    final entry = _access[token];
    if (entry == null) return _fromEarlierRun(token, 'fake-access-');
    return entry.$2.isAfter(now) ? entry.$1 : null;
  }

  /// The fake lives in memory, so a page reload forgets its tokens while the app still holds them.
  /// Tokens of the fake's own shape that it never issued are treated as the demo account's, so a
  /// reload keeps you signed in.
  String? _fromEarlierRun(String token, String prefix) =>
      token.startsWith(prefix) && int.tryParse(token.substring(prefix.length)) != null
      ? demoUserId
      : null;

  /// Ends every access token, as if 15 minutes passed. Tests use it to exercise the refresh.
  void expireAccessTokens() => _access.updateAll((_, v) => (v.$1, DateTime(2000)));

  JsonMap issue(String userId, DateTime now, JsonMap Function(String userId) userJson) {
    final n = ++_counter;
    final access = 'fake-access-$n';
    final refresh = 'fake-refresh-$n';
    _access[access] = (userId, now.add(accessLifetime));
    _refresh[refresh] = userId;
    return {
      'access_token': access,
      'refresh_token': refresh,
      'expires_in': accessLifetime.inSeconds,
      'user': userJson(userId),
    };
  }

  /// Rotates a refresh token: the old one stops working.
  String? redeem(String refreshToken) {
    if (!_redeemed.add(refreshToken)) return null;
    return _refresh.remove(refreshToken) ?? _fromEarlierRun(refreshToken, 'fake-refresh-');
  }

  final _redeemed = <String>{};

  void revoke(String refreshToken) {
    _refresh.remove(refreshToken);
    _redeemed.add(refreshToken);
  }
}

void registerAuthRoutes(FakeBackend b) {
  final auth = b.data.auth;
  JsonMap session(String userId) => auth.issue(userId, b.now(), (id) => fakeUserJson(b, id));

  b.route('GET', '/health', (_) => FakeResponse.json({'status': 'ok'}), public: true);

  b.route('POST', '/v1/auth/login', (r) {
    final email = (r.json['email'] as String? ?? '').trim().toLowerCase();
    if (auth.passwords[email] != r.json['password']) {
      throw const FakeError(401, 'unauthenticated', 'Wrong email or password.');
    }
    final user = auth.users.values.firstWhere((u) => u['email'] == email);
    return FakeResponse.json(session(user['id'] as String));
  }, public: true);

  b.route('POST', '/v1/auth/register', (r) {
    final email = (r.json['email'] as String? ?? '').trim().toLowerCase();
    final password = r.json['password'] as String? ?? '';
    if (!email.contains('@') || password.length < 8 || r.json['birth_date'] == null) {
      throw const FakeError(400, 'validation_error', 'Check the form.', {
        'fields': ['email', 'password', 'birth_date'],
      });
    }
    if (auth.passwords.containsKey(email)) {
      throw const FakeError(400, 'validation_error', 'That email already has an account.', {
        'fields': ['email'],
      });
    }
    final id = b.data.id('user');
    auth.users[id] = {
      'id': id,
      'email': email,
      'display_name': r.json['display_name'] as String? ?? email.split('@').first,
      'role': 'player',
      'max_rating': _maxRating(r.json['birth_date'] as String, b.now()),
      'content_prefs': {'gore': 'medium', 'romance': true, 'dark_themes': true},
    };
    auth.passwords[email] = password;
    return FakeResponse.json(session(id), status: 201);
  }, public: true);

  b.route('POST', '/v1/auth/google', (r) {
    final token = r.json['id_token'] as String? ?? '';
    if (token.isEmpty) throw const FakeError.validation('id_token is required');
    if (token == 'new-google-user' && r.json['birth_date'] == null) {
      throw const FakeError(400, 'birth_date_required', 'Tell us your birth date first.');
    }
    return FakeResponse.json(session(FakeAuthState.demoUserId));
  }, public: true);

  b.route('POST', '/v1/auth/refresh', (r) {
    final userId = auth.redeem(r.json['refresh_token'] as String? ?? '');
    if (userId == null) throw const FakeError(401, 'unauthenticated', 'Sign in again.');
    return FakeResponse.json(session(userId));
  }, public: true);

  b.route('POST', '/v1/auth/logout', (r) {
    auth.revoke(r.json['refresh_token'] as String? ?? '');
    return FakeResponse.noContent;
  }, public: true);
}

/// The `User` object (docs/API.md) for a fake user, with their credit balance.
JsonMap fakeUserJson(FakeBackend b, String userId) => {
  ...b.data.auth.users[userId]!,
  'credits': {'balance_cents': b.data.account.balanceOf(userId), 'unlimited': false},
};

String _maxRating(String birthDate, DateTime now) {
  final born = DateTime.tryParse(birthDate);
  if (born == null) return 'teen';
  final age =
      now.year - born.year - (DateTime(now.year, born.month, born.day).isAfter(now) ? 1 : 0);
  return age >= 17 ? 'mature' : 'teen';
}
