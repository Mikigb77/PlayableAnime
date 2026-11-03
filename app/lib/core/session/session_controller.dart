import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/api_providers.dart';
import 'session.dart';

enum SessionStatus {
  /// Reading the stored session at startup.
  restoring,
  signedOut,
  signedIn,
}

class SessionState {
  const SessionState(this.status, [this.session]);

  static const restoring = SessionState(SessionStatus.restoring);
  static const signedOut = SessionState(SessionStatus.signedOut);

  final SessionStatus status;
  final Session? session;

  /// Whether the signed-in part of the app is open.
  bool get canEnterApp => status == SessionStatus.signedIn;
}

/// Owns the session: restore at startup, sign in, refresh, sign out. It is the [TokenSource] the
/// API client uses, and the hook the accounts work (WS13) builds sign-in on: its screens call
/// `POST /v1/auth/*` and hand the `Session` to [signIn].
class SessionController extends Notifier<SessionState> implements TokenSource {
  Future<bool>? _refreshing;

  @override
  SessionState build() {
    unawaited(_restore());
    return SessionState.restoring;
  }

  SessionStore get _store => ref.read(sessionStoreProvider);

  Future<void> _restore() async {
    final stored = await _store.read();
    // A sign-in that finished first wins over what was stored.
    if (state.status != SessionStatus.restoring) return;
    state = stored == null ? SessionState.signedOut : SessionState(SessionStatus.signedIn, stored);
  }

  /// Starts a session from the API's `Session` JSON.
  ///
  /// The new tokens are used at once, before they are saved: after a refresh the server has
  /// already spent the old refresh token, and using it again would sign the device out. If saving
  /// fails, the session works until the app closes and the stored one is dropped.
  Future<void> signIn(Map<String, dynamic> sessionJson) async {
    final session = Session.fromApi(sessionJson);
    state = SessionState(SessionStatus.signedIn, session);
    try {
      await _store.write(session);
    } on Object catch (e) {
      debugPrint('Session save failed: ${e.runtimeType}');
      await _forget();
    }
  }

  /// Drops the stored session. Never throws: a keychain that fails here only means the next start
  /// may need a sign-in.
  Future<void> _forget() async {
    try {
      await _store.clear();
    } on Object catch (e) {
      debugPrint('Session clear failed: ${e.runtimeType}');
    }
  }

  /// Signs out on the server too (revoking the refresh token) when it can, then forgets the
  /// session. Signing out always works offline.
  Future<void> signOut() async {
    final session = state.session;
    if (session != null) {
      try {
        await ref.read(authApiClientProvider).post('/v1/auth/logout', {
          'refresh_token': session.refreshToken,
        }, authenticated: false);
      } on ApiException {
        // Best effort: the token expires on its own.
      }
    }
    state = SessionState.signedOut;
    await _forget();
  }

  @override
  String? get accessToken => state.session?.accessToken;

  @override
  Future<bool> refresh() => _refreshing ??= _refresh().whenComplete(() => _refreshing = null);

  Future<bool> _refresh() async {
    final session = state.session;
    if (session == null) return false;
    try {
      final json = await ref.read(authApiClientProvider).post('/v1/auth/refresh', {
        'refresh_token': session.refreshToken,
      }, authenticated: false);
      await signIn(json! as Map<String, dynamic>);
      return true;
    } on ApiException catch (e) {
      // Offline or a server hiccup: keep the session and let the caller's request fail.
      if (e.code.isRetryable) rethrow;
      return false;
    }
  }

  @override
  Future<void> onSessionExpired() async {
    if (state.status != SessionStatus.signedIn) return;
    state = SessionState.signedOut;
    await _forget();
  }
}

final sessionStoreProvider = Provider<SessionStore>((ref) => const SecureSessionStore());

final sessionProvider = NotifierProvider<SessionController, SessionState>(SessionController.new);
