import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'api/api_client.dart';

/// Keeps the user's own Gemini API key on the device (S9). The key travels only with requests
/// that may call a model, and the backend never stores or logs it (T6).
class ByokStore implements ByokSource {
  const ByokStore([this._storage = const FlutterSecureStorage()]);

  static const _geminiKey = 'byok.gemini_api_key';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readGeminiKey() async {
    try {
      return await _storage.read(key: _geminiKey);
    } on Object catch (e) {
      debugPrint('Key read failed: ${e.runtimeType}');
      return null;
    }
  }

  Future<void> saveGeminiKey(String key) => _storage.write(key: _geminiKey, value: key);

  Future<void> clearGeminiKey() => _storage.delete(key: _geminiKey);
}

final byokStoreProvider = Provider<ByokStore>((ref) => const ByokStore());
