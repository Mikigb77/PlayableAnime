import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api/api_client.dart';
import 'session/session_controller.dart';

/// Keeps the player's own Gemini API key on the device (S9). The key travels only with requests
/// that may call a model, and the backend never stores or logs it (T6).
///
/// Each account on the device has its own key, so whoever signs in next never plays, or is billed,
/// on someone else's. Signed out, there is no key.
class ByokStore implements ByokSource {
  const ByokStore(this.userId, [this._storage = const FlutterSecureStorage()]);

  /// The signed-in account, or null when signed out.
  final String? userId;
  final FlutterSecureStorage _storage;

  String get _geminiKey => 'byok.$userId.gemini_api_key';

  @override
  Future<String?> readGeminiKey() async {
    if (userId == null) return null;
    try {
      return await _storage.read(key: _geminiKey);
    } on Object catch (e) {
      debugPrint('Key read failed: ${e.runtimeType}');
      return null;
    }
  }

  Future<void> saveGeminiKey(String key) {
    if (userId == null) throw StateError('Saving a key needs a signed-in account');
    return _storage.write(key: _geminiKey, value: key);
  }

  Future<void> clearGeminiKey() async {
    if (userId != null) await _storage.delete(key: _geminiKey);
  }
}

final byokStoreProvider = Provider<ByokStore>(
  (ref) => ByokStore(ref.watch(sessionProvider.select((s) => s.session?.user['id'] as String?))),
);
