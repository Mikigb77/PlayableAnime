import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api/api_providers.dart';
import 'cloud_speech_engine.dart';
import 'speech_engine.dart';

/// Which recognizer the mic uses (V6), chosen in Account.
enum DictationMode {
  /// Gemini through our API: more accurate, knows the story's names, costs a little credit.
  online,

  /// The phone's own recognizer: free, words as you speak, audio may stay on the phone (V5).
  device,
}

/// The player's dictation choice, kept on this device. Online by default (Miki, 2026-11-04: the
/// phone's recognizer heard English badly).
class DictationModeController extends Notifier<DictationMode> {
  static const _key = 'dictation.mode';

  @override
  DictationMode build() {
    _load();
    return DictationMode.online;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = DictationMode.values.where((m) => m.name == prefs.getString(_key)).firstOrNull;
      if (saved != null) state = saved;
    } on Object {
      // No stored choice (or no storage, as in tests): online.
    }
  }

  Future<void> set(DictationMode mode) async {
    state = mode;
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_key, mode.name);
    } on Object {
      // The choice still applies for this run.
    }
  }
}

final dictationModeProvider = NotifierProvider<DictationModeController, DictationMode>(
  DictationModeController.new,
);

/// The recognizer behind every mic: the one the player chose. Tests override it with a fake.
final speechEngineProvider = Provider<SpeechEngine>(
  (ref) => switch (ref.watch(dictationModeProvider)) {
    DictationMode.online => ref.watch(_cloudEngineProvider),
    DictationMode.device => ref.watch(_phoneEngineProvider),
  },
);

final _cloudEngineProvider = Provider<SpeechEngine>((ref) {
  final recorder = RecordSpeechRecorder();
  ref.onDispose(recorder.dispose);
  return CloudSpeechEngine(
    recorder: recorder,
    transcriber: ApiTranscriber(ref.watch(apiClientProvider)),
  );
});

final _phoneEngineProvider = Provider<SpeechEngine>((ref) => PlatformSpeechEngine());
