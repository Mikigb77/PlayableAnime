import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import 'pcm.dart';
import 'speech_engine.dart';

/// The microphone as raw 16-bit PCM, for online dictation. [RecordSpeechRecorder] is the real
/// one; tests use a fake.
abstract interface class SpeechRecorder {
  /// Whether this platform can record. Never asks for permission.
  Future<bool> isSupported();

  /// Whether the mic is allowed, asking the first time when [request] is true (V5).
  Future<bool> hasPermission({bool request = true});

  /// Starts recording [wanted]. A platform that can't record it calls [onFormat] with what it
  /// records instead, before the first chunk.
  Future<Stream<Uint8List>> start(PcmFormat wanted, void Function(PcmFormat actual) onFormat);

  /// Stops recording; the stream sends what is left, then closes.
  Future<void> stop();

  /// Stops recording and drops what is left.
  Future<void> cancel();
}

/// [SpeechRecorder] on the `record` plugin (Android, iOS and the web).
class RecordSpeechRecorder implements SpeechRecorder {
  AudioRecorder? _recorder;

  // Made on first use, so on a phone a screen with a mic never touches the plugin until it's tapped.
  AudioRecorder get _mic => _recorder ??= AudioRecorder();

  @override
  Future<bool> isSupported() async {
    if (kIsWeb) {
      try {
        return await _mic.isEncoderSupported(AudioEncoder.pcm16bits);
      } on Object {
        return false;
      }
    }
    return switch (defaultTargetPlatform) {
      TargetPlatform.android || TargetPlatform.iOS || TargetPlatform.macOS => true,
      _ => false,
    };
  }

  @override
  Future<bool> hasPermission({bool request = true}) async {
    try {
      return await _mic.hasPermission(request: request);
    } on Object catch (e) {
      debugPrint('Mic permission check failed: ${e.runtimeType}');
      return false;
    }
  }

  @override
  Future<Stream<Uint8List>> start(
    PcmFormat wanted,
    void Function(PcmFormat actual) onFormat,
  ) async {
    await _mic.setOnConfigChanged(
      (config) => onFormat(PcmFormat(sampleRate: config.sampleRate, channels: config.numChannels)),
    );
    return _mic.startStream(
      RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: wanted.sampleRate,
        numChannels: wanted.channels,
        // Steady levels and less background, so a pause is heard as one and the words carry.
        autoGain: true,
        noiseSuppress: true,
        // A call or another app taking the mic ends the dictation; what was said is kept.
        audioInterruption: AudioInterruptionMode.none,
      ),
    );
  }

  @override
  Future<void> stop() async {
    await _recorder?.stop();
  }

  @override
  Future<void> cancel() async {
    await _recorder?.cancel();
  }

  Future<void> dispose() async {
    await _recorder?.dispose();
    _recorder = null;
  }
}

/// Writes a recording down (V6): `POST /v1/transcriptions`.
abstract interface class Transcriber {
  Future<String> transcribe(Uint8List wav, {String? language, SpeechContext context});
}

class ApiTranscriber implements Transcriber {
  ApiTranscriber(this.api);

  final ApiClient api;

  @override
  Future<String> transcribe(
    Uint8List wav, {
    String? language,
    SpeechContext context = const SpeechContext(),
  }) async {
    final json = await api.postBytes(
      '/v1/transcriptions',
      wav,
      contentType: 'audio/wav',
      query: {'language': ?language, 'story_id': ?context.storyId, 'draft_id': ?context.draftId},
    );
    return switch (json) {
      {'text': final String text} => text,
      _ => throw const ApiException(ApiErrorCode.server),
    };
  }
}

/// How online dictation treats pauses, and the only times it stops by itself. A pause never ends
/// it: the player takes the time they need to think, and taps the mic when done (Miki,
/// 2026-11-04).
class ListenLimits {
  const ListenLimits({
    this.keptPause = const Duration(seconds: 1),
    this.longest = const Duration(seconds: 60),
    this.forgotten = const Duration(minutes: 5),
  });

  /// A pause longer than this is cut to this length in what is sent, so thinking costs nothing
  /// and a long dictation fits. Only the room's own quiet is cut, never a sound above it.
  final Duration keptPause;

  /// The most audio a dictation sends, which the API's size limit allows with room to spare.
  /// Reaching it writes down what was said.
  final Duration longest;

  /// The mic turns itself off after this long, so a forgotten mic doesn't stay on.
  final Duration forgotten;
}

/// Online dictation (V6): records while the mic is on, then sends the recording to our API,
/// where Gemini 3.5 Transcribe writes it down in the story's language with the names the
/// character knows. The words appear once the player taps the mic again, and are never sent on
/// their own (V2). Audio leaves the phone only for that request, and we never keep it (V5).
class CloudSpeechEngine implements SpeechEngine {
  CloudSpeechEngine({
    required this.recorder,
    required this.transcriber,
    this.limits = const ListenLimits(),
  });

  final SpeechRecorder recorder;
  final Transcriber transcriber;
  final ListenLimits limits;

  _Dictation? _current;

  @override
  bool get onPhone => false;

  @override
  Future<bool> isSupported() => recorder.isSupported();

  @override
  Future<bool> initialize() => recorder.hasPermission();

  @override
  Future<bool> hasPermission() => recorder.hasPermission(request: false);

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
    // One mic: a box that is still recording stops for this one, keeping nothing. One already
    // being written down finishes on its own. This one starts once the last has let go of the
    // mic, so a late start or stop of that one never lands on this one's recording.
    final previous = _current;
    final dictation = _Dictation(
      engine: this,
      onResult: onResult,
      onStopped: onStopped,
      onError: onError,
      onLevel: onLevel,
      onTranscribing: onTranscribing,
      language: localeId,
      context: context,
    );
    _current = dictation;
    if (previous != null && !previous.finishing) await previous.cancel(notify: true);
    await dictation.start(previous?.released ?? Future<void>.value());
  }

  /// Ends the dictation that is recording, keeping what was said.
  @override
  Future<void> stop() async => _current?.finish();

  @override
  Future<void> cancel() async => _current?.cancel();
}

/// One dictation, from the tap to the words.
class _Dictation {
  _Dictation({
    required this.engine,
    required this.onResult,
    required this.onStopped,
    required this.onError,
    required this.onLevel,
    required this.onTranscribing,
    required this.language,
    required this.context,
  });

  // Speech is louder than this, and louder than the room by [_aboveRoomDb].
  static const _speechDb = -48.0;
  static const _aboveRoomDb = 12.0;

  // Within this of the room's level, and below [_stillMaxDb], is the room's own quiet, which a
  // long pause may lose. Nothing louder is ever cut, so a voice never is.
  static const _stillDb = 6.0;
  static const _stillMaxDb = -40.0;

  // How fast the room's level may rise, in dB a second, in case the room gets louder.
  static const _roomRiseDb = 6.0;

  final CloudSpeechEngine engine;
  final void Function(String words, bool isFinal) onResult;
  final VoidCallback onStopped;
  final void Function(SpeechFailure failure) onError;
  final void Function(double level)? onLevel;
  final VoidCallback? onTranscribing;
  final String? language;
  final SpeechContext context;

  final _audio = BytesBuilder(copy: false);
  final _closed = Completer<void>();
  final _started = Completer<void>(); // the mic has started for this dictation, or never will
  final _released = Completer<void>();
  StreamSubscription<Uint8List>? _subscription;
  PcmFormat _format = PcmFormat.speech;
  int _bytes = 0; // recorded
  int _keptBytes = 0; // to be sent
  int _stillBytes = 0; // of the room's quiet, in a row
  double? _roomDb;
  double _loudestDb = -100;
  bool _heard = false;
  bool _finishing = false;
  bool _cancelled = false;

  /// Recording has stopped, and what was said is being (or was) written down.
  bool get finishing => _finishing;

  /// Done once this dictation no longer uses the mic: it never started, or it has stopped.
  Future<void> get released => _released.future;

  void _release() {
    if (!_released.isCompleted) _released.complete();
  }

  Duration _length(int bytes) =>
      Duration(microseconds: bytes * Duration.microsecondsPerSecond ~/ _format.bytesPerSecond);

  /// Starts recording once [micFree]: the last dictation has let go of the mic.
  Future<void> start(Future<void> micFree) async {
    try {
      await micFree;
      if (_cancelled || _finishing) return; // stopped before the mic was free: nothing was said
      final Stream<Uint8List> stream;
      try {
        stream = await engine.recorder.start(PcmFormat.speech, (actual) => _format = actual);
      } on Object catch (e) {
        debugPrint('Recording failed to start: ${e.runtimeType}');
        if (!_cancelled && !_finishing) onError(const SpeechFailure('error_audio'));
        return;
      }
      if (_cancelled || _finishing) {
        await engine.recorder.cancel(); // stopped while the mic was starting: nothing was said
        return;
      }
      _subscription = stream.listen(
        _add,
        onError: (Object e) {
          debugPrint('Recording failed: ${e.runtimeType}');
          _finishClosed();
          finish();
        },
        onDone: () {
          _finishClosed();
          finish(); // the platform stopped it, such as a phone call
        },
      );
    } finally {
      _started.complete();
      if (_subscription == null) _release();
    }
  }

  void _finishClosed() {
    if (!_closed.isCompleted) _closed.complete();
  }

  void _add(Uint8List chunk) {
    if (_cancelled) return;
    _bytes += chunk.length;
    if (_finishing) return _keep(chunk); // the end of the recording, after the tap
    final db = pcmLevelDb(chunk);
    onLevel?.call(((db + 60) / 50).clamp(0.0, 1.0));
    // The room's level: the quietest so far, drifting up slowly in case it gets louder.
    final rise = _roomRiseDb * chunk.length / _format.bytesPerSecond;
    final room = _roomDb = _roomDb == null ? db : math.min(db, _roomDb! + rise);
    // Speech decides whether anything is sent at all; the tap alone ends the dictation.
    final speechDb = math.max(_speechDb, room + _aboveRoomDb);
    _loudestDb = math.max(_loudestDb, db);
    if (_loudestDb > speechDb) _heard = true; // a word at the tap counts once the room is heard
    // A pause to think is kept up to [ListenLimits.keptPause]; the rest of it isn't sent.
    final limits = engine.limits;
    final still = db <= room + _stillDb && db < _stillMaxDb;
    _stillBytes = still ? _stillBytes + chunk.length : 0;
    if (_length(_stillBytes) <= limits.keptPause) _keep(chunk);
    if (_length(_keptBytes) >= limits.longest || _length(_bytes) >= limits.forgotten) finish();
  }

  void _keep(Uint8List chunk) {
    _audio.add(chunk);
    _keptBytes += chunk.length;
  }

  /// Stops recording and writes down what was said: on the player's tap, or at the longest a
  /// dictation may be.
  Future<void> finish() async {
    if (_finishing || _cancelled) return;
    _finishing = true;
    await _started.future; // a mic still starting then cancels itself: nothing was said
    if (_subscription case final subscription?) {
      try {
        await engine.recorder.stop();
        // The last moment of speech is still on its way: wait for the stream to close.
        await _closed.future.timeout(const Duration(seconds: 1), onTimeout: () {});
      } on Object catch (e) {
        debugPrint('Recording failed to stop: ${e.runtimeType}');
      }
      await subscription.cancel();
      _release();
    }
    if (_cancelled) return;
    if (!_heard) {
      onError(const SpeechFailure('error_speech_timeout')); // silence: nothing sent, no message
      return;
    }
    onTranscribing?.call();
    final wav = speechWav(toSpeechPcm(_audio.takeBytes(), _format));
    final String words;
    try {
      words = await engine.transcriber.transcribe(wav, language: language, context: context);
    } on ApiException catch (e) {
      if (!_cancelled) onError(SpeechFailure(_failureCode(e.code)));
      return;
    } on Object catch (e) {
      debugPrint('Transcription failed: ${e.runtimeType}');
      if (!_cancelled) onError(const SpeechFailure(SpeechFailure.offline));
      return;
    }
    if (_cancelled) return;
    if (words.trim().isEmpty) {
      // The mic heard something, but no words: worth saying, unlike a dictation of silence.
      onError(const SpeechFailure(SpeechFailure.unclear));
      return;
    }
    onResult(words.trim(), true);
    onStopped();
  }

  /// Drops the dictation with no more callbacks, unless [notify]: then the box hears that it
  /// stopped, as when another box takes the mic.
  Future<void> cancel({bool notify = false}) async {
    if (_cancelled) return;
    _cancelled = true;
    await _started.future; // a mic still starting then cancels itself
    if (_subscription case final subscription?) {
      await subscription.cancel();
      if (!_finishing) await engine.recorder.cancel();
      _release();
    }
    if (notify) onStopped();
  }

  static String _failureCode(ApiErrorCode code) => switch (code) {
    ApiErrorCode.outOfCredits => SpeechFailure.outOfCredits,
    ApiErrorCode.rateLimited || ApiErrorCode.quotaExceeded => SpeechFailure.limited,
    ApiErrorCode.unreadableAction => SpeechFailure.unclear,
    ApiErrorCode.network ||
    ApiErrorCode.timeout ||
    ApiErrorCode.server ||
    ApiErrorCode.internalError ||
    ApiErrorCode.llmUnavailable => SpeechFailure.offline,
    _ => 'error_${code.wire}',
  };
}
