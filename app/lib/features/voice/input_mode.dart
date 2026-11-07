import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// How an action was entered (V7), sent as the turn's `input_mode`.
enum InputMode {
  typed('typed'),
  voice('voice'),
  voiceEdited('voice_edited'),
  choice('choice');

  const InputMode(this.wire);

  final String wire;
}

/// A box's mic as its tracker sees it (V2). `DictationController` is the one.
abstract interface class BoxMic implements Listenable {
  /// The mic is on, or what it heard is still on its way to the box.
  bool get dictating;

  /// Turns the mic off and waits until what it heard is in the box. False when the words
  /// couldn't be written down: the mic tells the player, and the words so far stay in the box.
  Future<bool> finish();
}

/// Watches a text box and works out whether its text was typed, dictated, or dictated and then
/// edited (V7). Dictation writes through [applyDictation]; everything else counts as typing.
/// Clearing the box (as sending does) starts over.
///
/// It also knows whether the box's mic is on ([dictating]), so whatever sends the box can first
/// [finishDictation]: nothing is sent while the mic is on or its words are on their way (V2).
class InputModeTracker {
  InputModeTracker(this.controller) : _last = controller.text {
    controller.addListener(_changed);
  }

  final TextEditingController controller;
  String _last;
  bool _dictated = false;
  bool _typed = false;
  bool _applying = false;
  BoxMic? _mic;
  final _dictating = ValueNotifier(false);

  /// Whether the box's mic is on, or what it heard is still on its way: until then the box
  /// doesn't hold everything the player said (V2).
  ValueListenable<bool> get dictating => _dictating;

  /// Turns the box's mic off, if it is on, and waits until what it heard is in the box, as
  /// sending does (V2). False when the words couldn't be written down: the mic says so, the
  /// words so far stay in the box, and the box shouldn't be sent yet.
  Future<bool> finishDictation() async => await _mic?.finish() ?? true;

  /// The mic that writes into this box, until [detach]. A new mic replaces the last.
  void attach(BoxMic mic) {
    _mic?.removeListener(_micChanged);
    _mic = mic..addListener(_micChanged);
    _micChanged();
  }

  /// Lets go of [mic], if it is still the box's.
  void detach(BoxMic mic) {
    if (!identical(mic, _mic)) return;
    mic.removeListener(_micChanged);
    _mic = null;
    _micChanged();
  }

  void _micChanged() => _dictating.value = _mic?.dictating ?? false;

  /// [InputMode.voice] only when every word came from dictation; any typing around it makes it
  /// [InputMode.voiceEdited].
  InputMode get mode => switch ((_dictated, _typed)) {
    (false, _) => InputMode.typed,
    (true, false) => InputMode.voice,
    (true, true) => InputMode.voiceEdited,
  };

  /// Puts dictated text in the box, with the cursor at the end.
  void applyDictation(String text) {
    _applying = true;
    controller.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    _applying = false;
    _dictated = true;
    _last = text;
  }

  void reset() {
    _dictated = false;
    _typed = false;
  }

  void _changed() {
    final text = controller.text;
    if (text == _last) return; // A cursor move, not an edit.
    _last = text;
    if (_applying) return;
    if (text.isEmpty) {
      reset();
    } else {
      _typed = true;
    }
  }

  void dispose() {
    controller.removeListener(_changed);
    _mic?.removeListener(_micChanged);
    _mic = null;
    _dictating.dispose();
  }
}
