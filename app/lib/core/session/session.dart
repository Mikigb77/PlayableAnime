import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// A signed-in session: our own short-lived access token and rotating refresh token (T8), plus the
/// `User` object as JSON, which the accounts work (WS13) models.
@immutable
class Session {
  const Session({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresAt,
    required this.user,
  });

  /// Parses the API's `Session` object (docs/API.md).
  factory Session.fromApi(Map<String, dynamic> json, {DateTime? now}) => Session(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    expiresAt: (now ?? DateTime.now()).add(
      Duration(seconds: (json['expires_in'] as num? ?? 900).toInt()),
    ),
    user: json['user'] as Map<String, dynamic>? ?? const {},
  );

  factory Session.fromStorage(Map<String, dynamic> json) => Session(
    accessToken: json['access_token'] as String,
    refreshToken: json['refresh_token'] as String,
    expiresAt: DateTime.parse(json['expires_at'] as String),
    user: json['user'] as Map<String, dynamic>? ?? const {},
  );

  final String accessToken;
  final String refreshToken;
  final DateTime expiresAt;
  final Map<String, dynamic> user;

  String? get displayName => user['display_name'] as String?;

  Map<String, dynamic> toStorage() => {
    'access_token': accessToken,
    'refresh_token': refreshToken,
    'expires_at': expiresAt.toIso8601String(),
    'user': user,
  };

  /// Never prints the tokens (T6).
  @override
  String toString() => 'Session(user: ${user['id']}, expiresAt: $expiresAt)';
}

abstract interface class SessionStore {
  Future<Session?> read();
  Future<void> write(Session session);
  Future<void> clear();
}

/// Keeps the session in the platform keychain or keystore.
class SecureSessionStore implements SessionStore {
  const SecureSessionStore([this._storage = const FlutterSecureStorage()]);

  static const _key = 'session.v1';
  final FlutterSecureStorage _storage;

  @override
  Future<Session?> read() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw == null) return null;
      return Session.fromStorage(jsonDecode(raw) as Map<String, dynamic>);
    } on Object catch (e) {
      // A corrupt entry or an unavailable keychain means signed out, never a crash.
      debugPrint('Session restore failed: ${e.runtimeType}');
      return null;
    }
  }

  @override
  Future<void> write(Session session) =>
      _storage.write(key: _key, value: jsonEncode(session.toStorage()));

  @override
  Future<void> clear() => _storage.delete(key: _key);
}

/// For tests.
class MemorySessionStore implements SessionStore {
  MemorySessionStore([this.value]);

  Session? value;

  @override
  Future<Session?> read() async => value;

  @override
  Future<void> write(Session session) async => value = session;

  @override
  Future<void> clear() async => value = null;
}
