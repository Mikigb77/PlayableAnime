import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keeps the user's own Gemini API key on the device. The key travels with each request and the
/// backend never stores it.
class ByokStore {
  const ByokStore([this._storage = const FlutterSecureStorage()]);

  static const _geminiKey = 'byok.gemini_api_key';

  final FlutterSecureStorage _storage;

  Future<String?> readGeminiKey() => _storage.read(key: _geminiKey);

  Future<void> saveGeminiKey(String key) => _storage.write(key: _geminiKey, value: key);

  Future<void> clearGeminiKey() => _storage.delete(key: _geminiKey);
}

final byokStoreProvider = Provider((ref) => const ByokStore());
