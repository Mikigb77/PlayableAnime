import 'dart:async';

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

  /// The mic is off and the words are being written down online (V6).
  transcribing,

  /// The player refused permission. Typing still works; the button explains how to allow it.
  denied,

  /// No recognizer on this device or browser: the button hides.
  unavailable,
}

/// Dictation into a text box (V1, V2). The words land in the box and stay there to edit, extend or
/// send; nothing is ever sent from here. Tapping the mic again adds to what is there.
///
/// Online (V6), the words come once the player taps the mic again, written down with the story's
/// names. With the phone's own recognizer they appear as the player speaks, recognized on the
/// device where the phone supports it, falling back to the platform's own service when it doesn't.
///
/// It is the box's mic for [tracker]: sending the box first [finish]es the dictation, so nothing
/// is sent while the mic is on or its words are on their way (V2).
class DictationController extends ChangeNotifier implements BoxMic {
  DictationController({
    required this.engine,
    required this.tracker,
    this.localeId = storyLanguage,
    this.context = const SpeechContext(),
    this.lastWords = const Duration(seconds: 2),
  }) {
    tracker.attach(this);
  }

  final SpeechEngine engine;

  /// Writes into the box and records that the words were dictated (V7).
  final InputModeTracker tracker;

  /// The BCP-47 tag to listen for, such as [storyLanguage]. A story can switch languages (S10),
  /// and the next dictation listens for the new one.
  String? localeId;

  /// The story or draft the words are for, whose names online dictation listens for (C6).
  final SpeechContext context;

  /// How long the phone's recognizer may take, once it stops, to give its last words: the most
  /// that sending waits for them.
  final Duration lastWords;

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
  bool _finishing = false;
  String _prefix = '';

  /// Each dictation's number: what a dictation hears after the next one started never lands in
  /// the box.
  int _session = 0;

  /// The dictation finished for sending: nothing it hears later lands in the box.
  int? _sealed;

  /// Done once the box holds everything the mic heard: online, when the words are written down;
  /// with the phone's recognizer, when its last words come after it stops, or [lastWords] passes.
  Completer<void>? _landing;
  Timer? _lastWordsTimer;

  bool get isListening => _phase == DictationPhase.listening;

  @override
  bool get dictating => _isOn || _phase == DictationPhase.transcribing || _landing != null;

  bool get _isOn => _phase == DictationPhase.listening || _phase == DictationPhase.starting;

  /// Sending is waiting for this dictation's words ([finish]): the mic can't be turned on again
  /// until they land.
  bool get finishing => _finishing;

  /// Turns the mic off and waits until what it heard is in the box, as sending does (V2). While
  /// it waits, the mic can't be turned on again. False when the words couldn't be written down:
  /// the button says why, and the words so far stay in the box to send once the player has seen
  /// them. Whatever the dictation hears later never lands in the box.
  @override
  Future<bool> finish() async {
    if (!dictating) return true;
    _finishing = true;
    notifyListeners();
    try {
      if (_isOn) await stop();
    } on Object catch (e) {
      debugPrint('Dictation failed to stop: ${e.runtimeType}');
    }
    if (_phase == DictationPhase.transcribing) _landing ??= Completer<void>();
    await _landing?.future;
    _finishing = false;
    _sealed = _session;
    if (_disposed) return false;
    notifyListeners();
    return _failure == null;
  }

  Future<void> toggle() async {
    if (_phase == DictationPhase.listening || _phase == DictationPhase.starting) {
      await stop();
    } else {
      await start();
    }
  }

  Future<void> start() async {
    if (_finishing ||
        _phase == DictationPhase.denied ||
        _phase == DictationPhase.unavailable ||
        _phase == DictationPhase.transcribing) {
      return;
    }
    _failure = null;
    // A new dictation: the last one's late words would land after these.
    _landed();
    _session++;
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
    final session = _session;
    bool live() => !_disposed && session == _session && session != _sealed;
    try {
      await engine.listen(
        onResult: (words, isFinal) {
          if (live()) _onResult(words, isFinal);
        },
        onStopped: () {
          if (live()) _onStopped();
        },
        onError: (failure) {
          if (live()) _onError(failure);
        },
        onLevel: (level) {
          if (!live()) return;
          _level = level;
          notifyListeners();
        },
        onTranscribing: () {
          if (live()) _onTranscribing();
        },
        localeId: localeId,
        context: context,
        onDevice: _onDevice,
      );
      if (live() && _phase == DictationPhase.starting) {
        _set(DictationPhase.listening);
      } else if (engine.onPhone && session == _session && (_disposed || !_isOn)) {
        // Turned off while the phone's recognizer was starting, which may have started anyway:
        // the mic is on only while the button shows it (V5). Online dictation sees to this itself.
        await (_disposed ? engine.cancel() : engine.stop());
      }
    } on Object {
      if (session == _session) _set(DictationPhase.idle);
    }
  }

  /// After a refusal, asks again whether the mic is allowed: the player may have turned it on in
  /// the system settings since. If it is, dictation starts; returns false while it is still
  /// refused, so the caller can explain how to allow it.
  Future<bool> retryPermission() async {
    if (_phase != DictationPhase.denied) return true;
    final allowed = await engine.hasPermission();
    if (_disposed || !allowed || _phase != DictationPhase.denied) return allowed;
    _ready = false;
    _set(DictationPhase.idle);
    await start();
    return true;
  }

  /// Turns the mic off. Online, what was said is then written down; the phone's recognizer has
  /// already put it in the box, but for its last words, which come a moment later.
  Future<void> stop() async {
    if (!_isOn) return;
    final heard = _phase == DictationPhase.listening;
    if (heard && engine.onPhone) _awaitLastWords();
    _set(heard && !engine.onPhone ? DictationPhase.transcribing : DictationPhase.idle);
    await engine.stop();
  }

  /// The phone's recognizer gives its last words a moment after it stops: until they come, or
  /// [lastWords] passes, the box doesn't hold everything that was said.
  void _awaitLastWords() {
    _landing ??= Completer<void>();
    _lastWordsTimer?.cancel();
    _lastWordsTimer = Timer(lastWords, _landed);
  }

  /// Everything the mic heard is in the box.
  void _landed() {
    _lastWordsTimer?.cancel();
    _lastWordsTimer = null;
    final landing = _landing;
    if (landing == null) return;
    _landing = null;
    landing.complete();
    if (!_disposed) notifyListeners();
  }

  void _onTranscribing() {
    if (_phase == DictationPhase.listening) _set(DictationPhase.transcribing);
  }

  void _onResult(String words, bool isFinal) {
    _heard = _heard || words.isNotEmpty;
    if (!engine.onPhone) {
      // The words come all at once, after the player may have typed: add them to what is there.
      final current = tracker.controller.text;
      _prefix = current.isEmpty || current.endsWith(' ') || current.endsWith('\n')
          ? current
          : '$current ';
    }
    tracker.applyDictation('$_prefix$words');
    if (!isFinal) return;
    if (_isActive) _set(DictationPhase.idle);
    _landed();
  }

  bool get _isActive => _phase == DictationPhase.listening || _phase == DictationPhase.transcribing;

  void _onStopped() {
    // The phone's recognizer can stop by itself, after a pause: its last words are still to come.
    if (engine.onPhone && _phase == DictationPhase.listening) _awaitLastWords();
    if (_isActive) _set(DictationPhase.idle);
    // Online, the words are all in.
    if (!engine.onPhone) _landed();
  }

  void _onError(SpeechFailure failure) {
    if (failure.isPermission) {
      _set(DictationPhase.denied);
      _landed();
      return;
    }
    // On-device recognition isn't available for this language or phone: try the platform's
    // service once, and keep using it for this box. Only the phone's recognizer runs on the device,
    // and only a mic that is still on tries again: once it is off, it stays off.
    if (engine.onPhone && _onDevice && !_heard && !failure.isSilence && _isOn) {
      _onDevice = false;
      _set(DictationPhase.starting);
      _listen();
      return;
    }
    _failure = failure.isSilence ? null : failure;
    _set(DictationPhase.idle);
    _landed();
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
    tracker.detach(this);
    if (_isOn) engine.cancel();
    _landed(); // nothing waits on a mic that is gone
    super.dispose();
  }
}
