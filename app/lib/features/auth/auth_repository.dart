import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/api/api_providers.dart';
import '../../core/json.dart';
import '../../core/l10n.dart';
import '../../core/session/session_controller.dart';
import 'google_auth.dart';

/// Signs in through `/v1/auth/*` (T8, F8) and hands the `Session` to the session controller,
/// which the router follows.
class AuthRepository {
  const AuthRepository(this._api, this._session, this._google);

  final ApiClient _api;
  final SessionController _session;
  final GoogleAuth _google;

  /// Sends a Google ID token. A first sign-in without [birthDate] throws `birth_date_required`;
  /// ask for the date and send the same token again (it lasts an hour).
  Future<void> signInWithGoogle(String idToken, {DateTime? birthDate}) => _signIn(
    '/v1/auth/google',
    {'id_token': idToken, if (birthDate != null) 'birth_date': isoDate(birthDate)},
  );

  Future<void> register({
    required String email,
    required String password,
    required String displayName,
    required DateTime birthDate,
  }) => _signIn('/v1/auth/register', {
    'email': email.trim(),
    'password': password,
    'display_name': displayName.trim(),
    'birth_date': isoDate(birthDate),
  });

  Future<void> logIn({required String email, required String password}) =>
      _signIn('/v1/auth/login', {'email': email.trim(), 'password': password});

  Future<void> _signIn(String path, JsonMap body) async {
    final json = await _api.post(path, body, authenticated: false);
    if (json is! JsonMap) throw const ApiException(ApiErrorCode.server);
    await _session.signIn(json);
  }

  /// Signs this device out on the server and forgets the Google account, so the next Google
  /// sign-in asks which account to use. Always works offline.
  Future<void> signOut() async {
    await _session.signOut();
    await _google.signOut();
  }
}

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(
    ref.watch(authApiClientProvider),
    ref.read(sessionProvider.notifier),
    ref.watch(googleAuthProvider),
  ),
);

/// `YYYY-MM-DD`, the API's date format.
String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// The problems a `validation_error` lists (`details.fields`), by field, in the player's words.
/// The server's own messages aren't localized, so only its `type` is used.
Map<String, String> fieldErrors(AppLocalizations l10n, ApiException error) {
  final problems = <String, String>{};
  for (final entry in error.fields) {
    if (entry case {'field': final String field}) {
      final type = entry['type'] as String? ?? '';
      problems.putIfAbsent(field, () => describeFieldProblem(l10n, field, type));
    }
  }
  return problems;
}

String describeFieldProblem(AppLocalizations l10n, String field, String type) => switch (type) {
  'invalid_email' => l10n.authBadEmail,
  'email_taken' => l10n.authEmailTaken,
  'password_too_short' => l10n.authPasswordShort,
  'password_too_common' => l10n.authPasswordCommon,
  'password_too_similar' => l10n.authPasswordSimilar,
  'password_entirely_numeric' => l10n.authPasswordNumeric,
  'future' => l10n.authBirthDateFuture,
  'implausible' => l10n.authBirthDateImplausible,
  'too_young' => l10n.authTooYoung,
  'missing' => switch (field) {
    'display_name' => l10n.authNeedName,
    'email' => l10n.authNeedEmail,
    'password' => l10n.authNeedPassword,
    'birth_date' => l10n.authNeedBirthDate,
    _ => l10n.authFieldInvalid,
  },
  _ when field == 'email' => l10n.authBadEmail,
  _ => l10n.authFieldInvalid,
};
