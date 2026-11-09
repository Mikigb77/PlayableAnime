import '../json.dart';
import 'fake_backend.dart';

/// Fake sign-in (docs/API.md, "Auth and account"), matching the backend's accounts app. Owned by
/// the accounts work (WS13).
///
/// - Email: the demo account is `demo@lucid.test` with password `lucid-demo`. Register checks the
///   form the way the backend does and answers `validation_error` with one `details.fields` entry
///   per problem. A new email account gets no starter credit, because its address isn't verified
///   (K1). Ten wrong passwords for one email answer `rate_limited`.
/// - Google: the fake's Google picker sends one of the [FakeGoogleTokens]. `new-google-user` is a
///   first sign-in, so it needs a birth date (F8) and then gets the starter credit;
///   `fake-google-owner` is the owner (K7, unlimited credits). Any other token signs in as the
///   demo account, except the error triggers in [FakeGoogleTokens].
class FakeAuthState {
  FakeAuthState() {
    users[demoUserId] = _demoUser();
    passwords[demoEmail] = demoPassword;
    users[ownerUserId] = {
      'id': ownerUserId,
      'email': 'owner@lucid.test',
      'display_name': 'Story owner',
      'role': 'owner',
      'max_rating': 'mature',
      'birth_date': '1990-04-12',
      'content_prefs': {...defaultPrefs},
    };
    google[FakeGoogleTokens.owner] = ownerUserId;
  }

  static const demoUserId = 'user_demo';
  static const demoEmail = 'demo@lucid.test';
  static const demoPassword = 'lucid-demo';
  static const ownerUserId = 'user_owner';

  /// Under this age nobody can sign up (`MIN_SIGNUP_AGE` on the backend, F8).
  static const minSignupAge = 16;

  static const defaultPrefs = {'gore': 'medium', 'romance': true, 'dark_themes': true};

  /// How long fake access tokens live.
  static const accessLifetime = Duration(minutes: 15);

  static JsonMap _demoUser() => {
    'id': demoUserId,
    'email': demoEmail,
    'display_name': 'Demo player',
    'role': 'player',
    'max_rating': 'mature',
    'birth_date': '1998-06-21',
    'content_prefs': {...defaultPrefs},
  };

  final users = <String, JsonMap>{};
  final passwords = <String, String>{};

  /// Google ID tokens of accounts that already signed in, and their users.
  final google = <String, String>{};

  /// When each email's recent logins failed, for the throttle: 10 in 15 minutes (API.md).
  final failures = <String, List<DateTime>>{};
  static const loginWindow = Duration(minutes: 15);
  static const loginLimit = 10;

  final _access = <String, (String userId, DateTime expiresAt)>{};
  final _refresh = <String, String>{};
  var _counter = 0;

  String? userForAccessToken(String token, DateTime now) {
    final entry = _access[token];
    if (entry == null) return _fromEarlierRun(token, 'fake-access-');
    return entry.$2.isAfter(now) && users.containsKey(entry.$1) ? entry.$1 : null;
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

  /// Signs every device of [userId] out, as deleting the account does.
  void revokeAll(String userId) {
    // Ended rather than forgotten, so they aren't taken for tokens of an earlier run.
    _access.updateAll((_, v) => v.$1 == userId ? (v.$1, DateTime(2000)) : v);
    for (final token in [
      for (final e in _refresh.entries)
        if (e.value == userId) e.key,
    ]) {
      revoke(token);
    }
  }

  /// Deletes an account. The demo account comes back fresh, so the fake can always sign in.
  void delete(String userId) {
    revokeAll(userId);
    final email = users[userId]?['email'];
    google.removeWhere((_, id) => id == userId);
    if (userId == demoUserId) {
      users[demoUserId] = _demoUser();
      passwords[demoEmail] = demoPassword;
    } else {
      users.remove(userId);
      passwords.remove(email);
    }
  }
}

/// The Google ID tokens the fake understands. The app's fake Google picker sends the first three.
abstract final class FakeGoogleTokens {
  static const demo = 'fake-google-demo';

  /// A first sign-in: answers `birth_date_required` until a birth date comes with it (F8).
  static const newPlayer = 'new-google-user';

  /// The owner account (K7): unlimited credits.
  static const owner = 'fake-google-owner';

  /// Google hasn't verified the account's email: `403 forbidden`.
  static const unverified = 'fake-google-unverified';

  /// Google can't be reached: `503 sign_in_unavailable`.
  static const unavailable = 'fake-google-unavailable';

  /// An expired or forged token: `401 unauthenticated`.
  static const invalid = 'fake-google-invalid';
}

void registerAuthRoutes(FakeBackend b) {
  final auth = b.data.auth;
  JsonMap session(String userId) => auth.issue(userId, b.now(), (id) => fakeUserJson(b, id));

  b.route('GET', '/health', (_) => FakeResponse.json({'status': 'ok'}), public: true);

  b.route('POST', '/v1/auth/login', (r) {
    final email = (r.json['email'] as String? ?? '').trim().toLowerCase();
    final now = b.now();
    final failed = (auth.failures[email] ?? [])
      ..removeWhere((at) => now.difference(at) >= FakeAuthState.loginWindow);
    if (failed.length >= FakeAuthState.loginLimit) {
      final retry = FakeAuthState.loginWindow - now.difference(failed.first);
      throw FakeError(429, 'rate_limited', 'Too many attempts. Try again later.', {
        'retry_after_s': (retry.inMilliseconds / 1000).ceil(),
      });
    }
    if (email.isEmpty || auth.passwords[email] != r.json['password']) {
      auth.failures[email] = [...failed, now];
      throw const FakeError(401, 'unauthenticated', 'Wrong email or password.');
    }
    auth.failures.remove(email);
    final user = auth.users.values.firstWhere((u) => u['email'] == email);
    return FakeResponse.json(session(user['id'] as String));
  }, public: true);

  b.route('POST', '/v1/auth/register', (r) {
    final email = (r.json['email'] as String? ?? '').trim().toLowerCase();
    final password = r.json['password'] as String? ?? '';
    final name = _displayName(r.json['display_name'] as String? ?? '');
    final birthDate = DateTime.tryParse(r.json['birth_date'] as String? ?? '');
    // The backend stops at the first problem with the email, name or birth date, then lists
    // every password problem at once (`accounts.services.register`).
    final problems = <JsonMap>[
      if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email))
        _field('email', 'invalid_email', 'Enter a valid email address.')
      else if (name.isEmpty)
        _field('display_name', 'missing', 'Enter a name.')
      else if (birthDate == null)
        _field('birth_date', 'date_from_datetime_parsing', 'Input should be a valid date.')
      else
        ?_birthDateProblem(birthDate, b.now()),
    ];
    if (problems.isEmpty) problems.addAll(_passwordProblems(password, email, name));
    if (problems.isEmpty && auth.passwords.containsKey(email)) {
      problems.add(
        _field(
          'email',
          'email_taken',
          'An account with this email already exists. Sign in instead.',
        ),
      );
    }
    if (problems.isNotEmpty) {
      throw FakeError(400, 'validation_error', problems.first['message'] as String, {
        'fields': problems,
      });
    }
    final id = b.data.id('user');
    auth.users[id] = {
      'id': id,
      'email': email,
      'display_name': name,
      'role': 'player',
      'birth_date': _isoDate(birthDate!),
      'content_prefs': {...FakeAuthState.defaultPrefs},
    };
    auth.passwords[email] = password;
    // No starter credit: the email isn't verified (K1, "verified" policy).
    return FakeResponse.json(session(id));
  }, public: true);

  b.route('POST', '/v1/auth/google', (r) {
    final token = r.json['id_token'] as String? ?? '';
    if (token.isEmpty) {
      throw FakeError(400, 'validation_error', 'id_token is required', {
        'fields': [
          _field('id_token', 'string_too_short', 'String should have at least 1 character'),
        ],
      });
    }
    switch (token) {
      case FakeGoogleTokens.invalid:
        throw const FakeError(401, 'unauthenticated', 'Google sign-in failed. Try again.');
      case FakeGoogleTokens.unavailable:
        throw const FakeError(503, 'sign_in_unavailable', 'Google sign-in is unavailable.');
      case FakeGoogleTokens.unverified:
        throw const FakeError(
          403,
          'forbidden',
          'Verify the email on your Google account, then try again.',
        );
    }
    final known = auth.google[token];
    if (known != null) return FakeResponse.json(session(known));
    if (token != FakeGoogleTokens.newPlayer) {
      return FakeResponse.json(session(FakeAuthState.demoUserId));
    }

    // A first Google sign-in creates the account, which needs a birth date (F8).
    final raw = r.json['birth_date'] as String?;
    if (raw == null) {
      throw const FakeError(400, 'birth_date_required', 'Tell us your birth date first.');
    }
    final birthDate = DateTime.tryParse(raw);
    final problem = birthDate == null
        ? _field('birth_date', 'date_from_datetime_parsing', 'Input should be a valid date.')
        : _birthDateProblem(birthDate, b.now());
    if (problem != null) {
      throw FakeError(400, 'validation_error', problem['message'] as String, {
        'fields': [problem],
      });
    }
    final id = b.data.id('user');
    auth.users[id] = {
      'id': id,
      'email': 'new.player@gmail.test',
      'display_name': 'New player',
      'role': 'player',
      'birth_date': _isoDate(birthDate!),
      'content_prefs': {...FakeAuthState.defaultPrefs},
    };
    auth.google[token] = id;
    // Google verified the email, so the starter credit comes at once (K1).
    b.data.account.grantStarter(id, b.now());
    return FakeResponse.json(session(id));
  }, public: true);

  b.route('POST', '/v1/auth/refresh', (r) {
    final userId = auth.redeem(r.json['refresh_token'] as String? ?? '');
    if (userId == null || !auth.users.containsKey(userId)) {
      throw const FakeError(401, 'unauthenticated', 'Sign in again.');
    }
    return FakeResponse.json(session(userId));
  }, public: true);

  b.route('POST', '/v1/auth/logout', (r) {
    auth.revoke(r.json['refresh_token'] as String? ?? '');
    return FakeResponse.noContent;
  }, public: true);
}

/// The `User` object (docs/API.md) for a fake user, with their credit balance.
JsonMap fakeUserJson(FakeBackend b, String userId) {
  final user = b.data.auth.users[userId]!;
  return {
    for (final e in user.entries)
      if (e.key != 'birth_date') e.key: e.value,
    'max_rating': fakeMaxRating(user['birth_date'] as String?, b.now()),
    'credits': {
      'balance_cents': b.data.account.balanceOf(userId),
      'unlimited': b.data.account.unlimited.contains(userId),
    },
  };
}

/// Teen under 17, Mature from the 17th birthday (F8). No birth date means Teen.
String fakeMaxRating(String? birthDate, DateTime now) {
  final born = birthDate == null ? null : DateTime.tryParse(birthDate);
  if (born == null) return 'teen';
  return _age(born, now) >= 17 ? 'mature' : 'teen';
}

int _age(DateTime born, DateTime now) =>
    now.year - born.year - (DateTime(now.year, born.month, born.day).isAfter(now) ? 1 : 0);

/// The backend's birth date checks (`accounts.rules.check_birth_date`).
JsonMap? _birthDateProblem(DateTime born, DateTime now) {
  final today = DateTime(now.year, now.month, now.day);
  if (born.isAfter(today)) {
    return _field('birth_date', 'future', "Your birth date can't be in the future.");
  }
  final age = _age(born, today);
  if (age > 120) return _field('birth_date', 'implausible', 'Check your birth date.');
  if (age < FakeAuthState.minSignupAge) {
    return _field(
      'birth_date',
      'too_young',
      'You need to be at least ${FakeAuthState.minSignupAge} to play.',
    );
  }
  return null;
}

/// Django's password validators, as the backend configures them.
List<JsonMap> _passwordProblems(String password, String email, String name) {
  final lower = password.toLowerCase();
  final local = email.split('@').first.toLowerCase();
  return [
    if ((local.length >= 3 && lower.contains(local)) ||
        (name.length >= 3 && lower.contains(name.toLowerCase())))
      _field('password', 'password_too_similar', 'The password is too similar to the email.'),
    if (password.length < 8)
      _field(
        'password',
        'password_too_short',
        'This password is too short. It must contain at least 8 characters.',
      ),
    if (_common.contains(lower))
      _field('password', 'password_too_common', 'This password is too common.'),
    if (RegExp(r'^\d+$').hasMatch(password))
      _field('password', 'password_entirely_numeric', 'This password is entirely numeric.'),
  ];
}

const _common = {'password', 'password1', '12345678', '123456789', 'qwertyuiop', 'iloveyou'};

JsonMap _field(String field, String type, String message) => {
  'field': field,
  'source': 'body',
  'message': message,
  'type': type,
};

String _displayName(String name) {
  final collapsed = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
  return collapsed.length > 80 ? collapsed.substring(0, 80) : collapsed;
}

String _isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';
