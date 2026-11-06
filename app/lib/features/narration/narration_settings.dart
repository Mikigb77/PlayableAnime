import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Which voice reads scenes aloud (V9), chosen in Account.
enum NarrationVoice {
  /// Gemini's studio voice through our API: natural, like an audiobook, costs a little credit
  /// the first time a scene is read (V10).
  studio,

  /// The phone's own text to speech: free and private, but flatter.
  device,
}

/// The studio voices a player can pick, as the API names them (`speech.voices.VOICES`), the
/// default first.
enum StudioVoice {
  sulafat('Sulafat'),
  gacrux('Gacrux'),
  charon('Charon'),
  algieba('Algieba');

  const StudioVoice(this.wire);

  /// The voice's name, as the API takes it and the app shows it.
  final String wire;
}

/// How the player likes scenes read aloud (V8, V9), kept on this device.
@immutable
class NarrationSettings {
  const NarrationSettings({
    this.voice = NarrationVoice.studio,
    this.studioVoice = StudioVoice.sulafat,
    this.readNewScenes = false,
  });

  /// The studio voice by default (Miki, 2026-11-06), with the phone's voice as the free option.
  final NarrationVoice voice;
  final StudioVoice studioVoice;

  /// Reads each new scene aloud as it lands, without pressing play. Off by default, so nothing
  /// is read, or charged, unless the player asks.
  final bool readNewScenes;

  NarrationSettings copyWith({
    NarrationVoice? voice,
    StudioVoice? studioVoice,
    bool? readNewScenes,
  }) => NarrationSettings(
    voice: voice ?? this.voice,
    studioVoice: studioVoice ?? this.studioVoice,
    readNewScenes: readNewScenes ?? this.readNewScenes,
  );

  @override
  bool operator ==(Object other) =>
      other is NarrationSettings &&
      other.voice == voice &&
      other.studioVoice == studioVoice &&
      other.readNewScenes == readNewScenes;

  @override
  int get hashCode => Object.hash(voice, studioVoice, readNewScenes);
}

/// The player's reading-aloud choices, kept on this device like the other preferences.
class NarrationSettingsController extends Notifier<NarrationSettings> {
  static const _voiceKey = 'narration.voice';
  static const _studioVoiceKey = 'narration.studio_voice';
  static const _readNewKey = 'narration.read_new_scenes';

  /// The stored choices being read, so a scene read the moment the app opens still gets them.
  Future<void> _loaded = Future.value();

  /// The player changed something before the stored choices were read: theirs wins.
  var _changed = false;

  @override
  NarrationSettings build() {
    _changed = false;
    _loaded = _load();
    return const NarrationSettings();
  }

  /// The player's choices, once the stored ones are read.
  Future<NarrationSettings> loaded() async {
    await _loaded;
    return state;
  }

  Future<void> _load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final voice = NarrationVoice.values
          .where((v) => v.name == prefs.getString(_voiceKey))
          .firstOrNull;
      final studio = StudioVoice.values
          .where((v) => v.wire == prefs.getString(_studioVoiceKey))
          .firstOrNull;
      final readNew = prefs.getBool(_readNewKey);
      if (_changed) return;
      state = state.copyWith(voice: voice, studioVoice: studio, readNewScenes: readNew);
    } on Object {
      // No stored choice (or no storage, as in tests): the defaults.
    }
  }

  Future<void> setVoice(NarrationVoice voice) =>
      _save(state.copyWith(voice: voice), (p) => p.setString(_voiceKey, voice.name));

  Future<void> setStudioVoice(StudioVoice voice) =>
      _save(state.copyWith(studioVoice: voice), (p) => p.setString(_studioVoiceKey, voice.wire));

  Future<void> setReadNewScenes(bool on) =>
      _save(state.copyWith(readNewScenes: on), (p) => p.setBool(_readNewKey, on));

  Future<void> _save(
    NarrationSettings next,
    Future<bool> Function(SharedPreferences prefs) write,
  ) async {
    _changed = true;
    state = next;
    try {
      await write(await SharedPreferences.getInstance());
    } on Object {
      // The choice still applies for this run.
    }
  }
}

final narrationSettingsProvider = NotifierProvider<NarrationSettingsController, NarrationSettings>(
  NarrationSettingsController.new,
);
