import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// A recognizer failure, such as `error_no_match` or `error_permission`.
@immutable
class SpeechFailure {
  const SpeechFailure(this.code, {this.permanent = false});

  final String code;
  final bool permanent;

  bool get isPermission => code.contains('permission');

  /// The player said nothing, or nothing that could be recognized: not worth a message.
  bool get isSilence =>
      code == 'error_no_match' || code == 'error_speech_timeout' || code == 'error_busy';
}

/// The speech recognizer behind the dictation button. P0 is the phone's own recognizer (V6); a
/// Gemini transcriber can implement the same interface later, so the app reaches both through it.
abstract interface class SpeechEngine {
  /// Whether this platform can recognize speech at all. Never asks for permission.
  Future<bool> isSupported();

  /// Prepares the recognizer, asking for microphone (and on iOS speech recognition) permission the
  /// first time (V5). False when refused or unavailable.
  Future<bool> initialize();

  Future<bool> hasPermission();

  /// Starts listening. [onResult] gets everything heard so far in this session.
  Future<void> listen({
    required void Function(String words, bool isFinal) onResult,
    required VoidCallback onStopped,
    required void Function(SpeechFailure failure) onError,
    void Function(double level)? onLevel,
    String? localeId,
    bool onDevice = true,
  });

  Future<void> stop();

  Future<void> cancel();
}

/// [SpeechEngine] on the `speech_to_text` plugin (Apple's Speech framework, Android's
/// SpeechRecognizer, the browser's Web Speech API). Audio never reaches our backend.
class PlatformSpeechEngine implements SpeechEngine {
  PlatformSpeechEngine([SpeechToText? speech]) : _speech = speech ?? SpeechToText();

  final SpeechToText _speech;
  bool? _initialized;

  // The plugin is a singleton that keeps the first listeners it is given, so this engine owns
  // them and forwards to whichever dictation is listening now.
  VoidCallback? _onStopped;
  void Function(SpeechFailure)? _onError;

  @override
  Future<bool> isSupported() async {
    if (kIsWeb) return initialize(); // The browser asks for the mic only when listening starts.
    return switch (defaultTargetPlatform) {
      TargetPlatform.android || TargetPlatform.iOS || TargetPlatform.macOS => true,
      _ => false,
    };
  }

  @override
  Future<bool> initialize() async {
    if (_initialized == true) return true;
    try {
      _initialized = await _speech.initialize(
        onStatus: (status) {
          if (status == SpeechToText.notListeningStatus || status == SpeechToText.doneStatus) {
            _onStopped?.call();
          }
        },
        onError: (SpeechRecognitionError error) =>
            _onError?.call(SpeechFailure(error.errorMsg, permanent: error.permanent)),
      );
    } on Object catch (e) {
      debugPrint('Speech init failed: ${e.runtimeType}');
      _initialized = false;
    }
    return _initialized!;
  }

  @override
  Future<bool> hasPermission() async {
    try {
      return await _speech.hasPermission;
    } on Object {
      return false;
    }
  }

  @override
  Future<void> listen({
    required void Function(String words, bool isFinal) onResult,
    required VoidCallback onStopped,
    required void Function(SpeechFailure failure) onError,
    void Function(double level)? onLevel,
    String? localeId,
    bool onDevice = true,
  }) async {
    _onStopped = onStopped;
    _onError = onError;
    await _speech.listen(
      onResult: (SpeechRecognitionResult result) =>
          onResult(result.recognizedWords, result.finalResult),
      // Platform levels run from about -2 to 10 dB; the button wants 0 to 1.
      onSoundLevelChange: onLevel == null
          ? null
          : (level) => onLevel(((level + 2) / 12).clamp(0, 1)),
      listenOptions: SpeechListenOptions(
        partialResults: true,
        onDevice: onDevice,
        listenMode: ListenMode.dictation,
        cancelOnError: true,
        localeId: localeId,
        pauseFor: const Duration(seconds: 4),
        listenFor: const Duration(minutes: 1),
      ),
    );
  }

  @override
  Future<void> stop() => _speech.stop();

  @override
  Future<void> cancel() => _speech.cancel();
}

final speechEngineProvider = Provider<SpeechEngine>((ref) => PlatformSpeechEngine());
