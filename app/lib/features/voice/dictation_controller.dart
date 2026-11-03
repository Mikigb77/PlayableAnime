import 'package:flutter/foundation.dart';

import 'input_mode.dart';
import 'speech_engine.dart';

enum DictationPhase {
  /// Ready to listen.
  idle,

  /// Asking for permission or starting the recognizer.
  starting,

  /// The mic is on.
  listening,

  /// The player refused permission. Typing still works; the button explains how to allow it.
  denied,

  /// No recognizer on this device or browser: the button hides.
  unavailable,
}

/// Dictation into a text box (V1, V2). Words appear live in the box as the player speaks and stay
/// there to edit, extend or send; nothing is ever sent from here. Tapping the mic again adds to
/// what is there. Recognition runs on the device where the phone supports it, and falls back to the
/// platform's own service when it doesn't (V6).
class DictationController extends ChangeNotifier {
  DictationController({required this.engine, required this.tracker, this.localeId});

  final SpeechEngine engine;

  /// Writes into the box and records that the words were dictated (V7).
  final InputModeTracker tracker;

  /// The story's language for recognition (V4), or the device's when null.
  final String? localeId;

  DictationPhase get phase => _phase;
  DictationPhase _phase = DictationPhase.idle;

  /// The input level while listening, 0 to 1.
  double get level => _level;
  double _level = 0;

  /// The last failure worth telling the player about, if any.
  SpeechFailure? get failure => _failure;
  SpeechFailure? _failure;

  bool _ready = false;
  bool _onDevice = true;
  bool _heard = false;
  bool _disposed = false;
  String _prefix = '';

  bool get isListening => _phase == DictationPhase.listening;

  Future<void> toggle() async {
    if (_phase == DictationPhase.listening || _phase == DictationPhase.starting) {
      await stop();
    } else {
      await start();
    }
  }

  Future<void> start() async {
    if (_phase == DictationPhase.denied || _phase == DictationPhase.unavailable) return;
    _failure = null;
    _set(DictationPhase.starting);
    if (!_ready) {
      _ready = await engine.initialize();
      if (_disposed) return;
      if (!_ready) {
        final allowed = await engine.hasPermission();
        _set(allowed ? DictationPhase.unavailable : DictationPhase.denied);
        return;
      }
      // The player tapped again while the permission prompt was up.
      if (_phase != DictationPhase.starting) return;
    }
    final current = tracker.controller.text;
    _prefix = current.isEmpty || current.endsWith(' ') || current.endsWith('\n')
        ? current
        : '$current ';
    _heard = false;
    await _listen();
  }

  Future<void> _listen() async {
    try {
      await engine.listen(
        onResult: _onResult,
        onStopped: _onStopped,
        onError: _onError,
        onLevel: (level) {
          _level = level;
          if (!_disposed) notifyListeners();
        },
        localeId: localeId,
        onDevice: _onDevice,
      );
      if (!_disposed && _phase == DictationPhase.starting) _set(DictationPhase.listening);
    } on Object {
      _set(DictationPhase.idle);
    }
  }

  Future<void> stop() async {
    if (_phase != DictationPhase.listening && _phase != DictationPhase.starting) return;
    _set(DictationPhase.idle);
    await engine.stop();
  }

  void _onResult(String words, bool isFinal) {
    if (_disposed) return;
    _heard = _heard || words.isNotEmpty;
    tracker.applyDictation('$_prefix$words');
    if (isFinal && _phase == DictationPhase.listening) _set(DictationPhase.idle);
  }

  void _onStopped() {
    if (_phase == DictationPhase.listening) _set(DictationPhase.idle);
  }

  void _onError(SpeechFailure failure) {
    if (_disposed) return;
    if (failure.isPermission) {
      _set(DictationPhase.denied);
      return;
    }
    // On-device recognition isn't available for this language or phone: try the platform's
    // service once, and keep using it for this box.
    if (_onDevice && !_heard && !failure.isSilence) {
      _onDevice = false;
      _set(DictationPhase.starting);
      _listen();
      return;
    }
    _failure = failure.isSilence ? null : failure;
    _set(DictationPhase.idle);
  }

  void _set(DictationPhase phase) {
    if (_disposed) return;
    _phase = phase;
    if (phase != DictationPhase.listening) _level = 0;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    if (_phase == DictationPhase.listening || _phase == DictationPhase.starting) {
      engine.cancel();
    }
    super.dispose();
  }
}
