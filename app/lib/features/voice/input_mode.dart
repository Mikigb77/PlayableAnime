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

/// Watches a text box and works out whether its text was typed, dictated, or dictated and then
/// edited (V7). Dictation writes through [applyDictation]; everything else counts as typing.
/// Clearing the box (as sending does) starts over.
class InputModeTracker {
  InputModeTracker(this.controller) : _last = controller.text {
    controller.addListener(_changed);
  }

  final TextEditingController controller;
  String _last;
  bool _dictated = false;
  bool _typed = false;
  bool _applying = false;

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

  void dispose() => controller.removeListener(_changed);
}
