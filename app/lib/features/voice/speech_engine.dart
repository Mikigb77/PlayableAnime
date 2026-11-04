import 'package:flutter/foundation.dart';
import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// The language every story is told in until S10 adds Spanish (V4), as a BCP-47 tag. Recognition
/// listens for it rather than the phone's own language, so English spoken to a phone set to
/// Spanish is heard as English.
const storyLanguage = 'en-US';

/// A recognizer failure, such as `error_no_match` or `error_permission`. Online dictation adds
/// [offline], [outOfCredits] and [limited].
@immutable
class SpeechFailure {
  const SpeechFailure(this.code, {this.permanent = false});

  /// The server couldn't be reached, or couldn't write the words down right now.
  static const offline = 'server_unreachable';

  /// The player has no credits left for online dictation (K2).
  static const outOfCredits = 'out_of_credits';

  /// Too many dictations for now: the rate limit or the daily quota (T9).
  static const limited = 'rate_limited';

  final String code;
  final bool permanent;

  bool get isPermission => code.contains('permission');

  /// The player said nothing, or nothing that could be recognized: not worth a message.
  bool get isSilence =>
      code == 'error_no_match' || code == 'error_speech_timeout' || code == 'error_busy';
}

/// Where the words go, so online dictation can listen for the names the character knows there
/// (V6, C6). Both null for a box with no story yet, such as the premise.
@immutable
class SpeechContext {
  const SpeechContext({this.storyId, this.draftId});

  final String? storyId;
  final String? draftId;

  @override
  bool operator ==(Object other) =>
      other is SpeechContext && other.storyId == storyId && other.draftId == draftId;

  @override
  int get hashCode => Object.hash(storyId, draftId);
}

/// The speech recognizer behind the dictation button (V6): the phone's own
/// ([PlatformSpeechEngine]) or Gemini through our API ([CloudSpeechEngine]), which the player picks
/// in Account. The app reaches both through this interface.
abstract interface class SpeechEngine {
  /// Whether this is the phone's own recognizer: the words show as they are spoken (V2), and it
  /// may run on the device itself (V5). An online engine writes the words down once the player
  /// stops, saying so with `onTranscribing`.
  bool get onPhone;

  /// Whether this platform can recognize speech at all. Never asks for permission.
  Future<bool> isSupported();

  /// Prepares the recognizer, asking for microphone (and on iOS speech recognition) permission the
  /// first time (V5). False when refused or unavailable.
  Future<bool> initialize();

  Future<bool> hasPermission();

  /// Starts listening. [onResult] gets everything heard so far in this session. [localeId] is a
  /// BCP-47 tag such as [storyLanguage]; null leaves it to the recognizer. An online engine calls
  /// [onTranscribing] when the recording ends and the words are being written down, then
  /// [onResult] once, final, then [onStopped].
  Future<void> listen({
    required void Function(String words, bool isFinal) onResult,
    required VoidCallback onStopped,
    required void Function(SpeechFailure failure) onError,
    void Function(double level)? onLevel,
    VoidCallback? onTranscribing,
    String? localeId,
    SpeechContext context = const SpeechContext(),
    bool onDevice = true,
  });

  /// Stops listening, keeping what was heard (an online engine then writes it down).
  Future<void> stop();

  /// Stops listening and throws away what was heard, with no more callbacks.
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
  bool get onPhone => true;

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
    VoidCallback? onTranscribing,
    String? localeId,
    SpeechContext context = const SpeechContext(),
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
        // The plugin names locales with an underscore: en_US.
        localeId: localeId?.replaceAll('-', '_'),
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
