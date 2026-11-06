import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_providers.dart';
import 'narration_settings.dart';
import 'phone_voice.dart';
import 'spoken_text.dart';
import 'studio_voice.dart';

/// What the narrator is doing with a scene.
enum NarrationPhase {
  idle,

  /// Waiting for the studio voice's first part.
  loading,
  reading,
}

/// Why the phone's voice read a scene the studio voice was asked for (V9).
enum StudioFallback {
  /// The player has no credits for it (K2).
  outOfCredits,

  /// Today's reading aloud is used up (T9).
  quota,

  /// The studio voice failed or is busy: the network, the server or the model.
  unavailable,
}

/// Something the play screen tells the player about reading aloud.
sealed class NarrationNotice {
  const NarrationNotice(this.storyId);

  final String storyId;
}

/// The phone's voice is reading the rest of the scene, and why.
class ReadOnPhone extends NarrationNotice {
  const ReadOnPhone(super.storyId, this.reason);

  final StudioFallback reason;
}

/// The phone has no voice to read with.
class NoPhoneVoice extends NarrationNotice {
  const NoPhoneVoice(super.storyId);
}

/// The studio voice read a part, which may have cost credits: the balance shown is out of date.
class StudioCreditsSpent extends NarrationNotice {
  const StudioCreditsSpent(super.storyId);
}

/// Reads scenes aloud (V8 to V10), one at a time, app-wide: starting another scene, or [stop],
/// ends the one being read.
///
/// In the studio voice it asks the API for the scene's parts in order, plays each as soon as it
/// comes, and asks for the next while one plays. A part the voice model refuses is read in the
/// phone's voice, and when the studio voice can't go on (no credits, a limit, a failure) the
/// phone's voice reads the rest of the scene, and the screen says why.
class Narrator extends ChangeNotifier {
  Narrator({
    required this._studio,
    required this._player,
    required this._phone,
    required this._settings,
    this.prefetchLead = const Duration(seconds: 20),
  });

  /// How long before a part ends the next is asked for: enough for the model to read it, late
  /// enough that a player who stops early isn't charged for a part they never hear (V10).
  final Duration prefetchLead;

  final StudioVoiceApi Function() _studio;
  final AudioPlayback Function() _player;
  final PhoneVoice Function() _phone;
  final Future<NarrationSettings> Function() _settings;

  final _notices = StreamController<NarrationNotice>.broadcast();

  /// Each read, so one that was stopped or replaced notices and goes quiet.
  var _session = 0;
  String? _storyId;
  int? _turn;
  var _phase = NarrationPhase.idle;
  NarrationVoice? _voice;

  Stream<NarrationNotice> get notices => _notices.stream;

  /// The scene being read, if any.
  String? get storyId => _storyId;
  int? get turn => _turn;

  /// The voice reading now: the studio's, or the phone's (chosen, or standing in for it).
  NarrationVoice? get voice => _voice;

  NarrationPhase phaseOf(String storyId, int turn) =>
      storyId == _storyId && turn == _turn ? _phase : NarrationPhase.idle;

  bool isReading(String storyId) => storyId == _storyId && _phase != NarrationPhase.idle;

  /// Reads the scene [turn] of [storyId] aloud, from the start, in the voice the player chose.
  /// [language] is the story's (`en`, `es`, `ca`), for the phone's voice: the studio voice hears it
  /// from the words. Completes when the scene has been read, or another read or [stop] ended it.
  Future<void> read({
    required String storyId,
    required int turn,
    required String narration,
    required String language,
  }) async {
    final session = ++_session;
    _set(storyId, turn, NarrationPhase.loading, null);
    try {
      final settings = await _settings();
      if (session != _session) return;
      _set(storyId, turn, NarrationPhase.loading, settings.voice);
      await _silence();
      if (session != _session) return;
      final spoken = spokenText(narration);
      if (settings.voice == NarrationVoice.device) {
        await _readOnPhone(session, storyId, spoken, language);
      } else {
        await _readInStudio(
          session,
          storyId: storyId,
          turn: turn,
          spoken: spoken,
          language: language,
          voice: settings.studioVoice,
        );
      }
    } finally {
      if (session == _session) _set(null, null, NarrationPhase.idle, null);
    }
  }

  /// Stops reading, if anything is being read.
  Future<void> stop() async {
    _session++;
    _set(null, null, NarrationPhase.idle, null);
    await _silence();
  }

  /// Stops reading if a scene of [storyId] is being read: the player acted, or left the story.
  Future<void> stopStory(String storyId) async {
    if (_storyId == storyId) await stop();
  }

  Future<void> _readInStudio(
    int session, {
    required String storyId,
    required int turn,
    required String spoken,
    required String language,
    required StudioVoice voice,
  }) async {
    final studio = _studio();
    Future<_Fetched> fetch(int part, {Duration after = Duration.zero}) async {
      if (after > Duration.zero) await Future<void>.delayed(after);
      // Stopped or replaced meanwhile: nothing more is read for it.
      if (session != _session) return const _Fetched.failed(_Stopped());
      return studio
          .part(storyId, turn, part, voice: voice.wire)
          .then<_Fetched>(_Fetched.new, onError: (Object error) => _Fetched.failed(error));
    }

    // Where the next part starts in the spoken text: the phone's voice reads from there if the
    // studio voice stops.
    var offset = 0;
    var spent = false;
    var next = fetch(0);
    while (true) {
      final fetched = await next;
      if (session != _session) return;
      final part = fetched.part;
      if (part == null) {
        _notify(ReadOnPhone(storyId, _fallbackFor(fetched.error)));
        await _readOnPhone(session, storyId, spoken.substring(offset), language);
        return;
      }
      final last = part.part + 1 >= part.parts;
      // The next part is read while this one plays, in time for its end.
      final plays = part.status == StudioPartStatus.ready ? part.duration : null;
      if (!last) next = fetch(part.part + 1, after: _lead(plays));
      final at = spoken.indexOf(part.text, offset);
      final end = at < 0 ? offset : at + part.text.length;
      if (part.status == StudioPartStatus.ready && part.url != null) {
        if (!spent) {
          spent = true;
          _notify(StudioCreditsSpent(storyId));
        }
        _set(storyId, turn, NarrationPhase.reading, NarrationVoice.studio);
        try {
          await _player().play(part.url!);
        } on Object {
          if (session != _session) return;
          _notify(ReadOnPhone(storyId, StudioFallback.unavailable));
          await _readOnPhone(session, storyId, spoken.substring(offset), language);
          return;
        }
      } else {
        // The voice model won't read this part: the phone's voice does, then the studio's goes
        // on.
        await _readOnPhone(session, storyId, part.text, language);
      }
      if (session != _session || last) return;
      _set(storyId, turn, NarrationPhase.reading, NarrationVoice.studio);
      offset = end;
    }
  }

  Future<void> _readOnPhone(int session, String storyId, String text, String language) async {
    if (text.trim().isEmpty || session != _session) return;
    _set(_storyId, _turn, NarrationPhase.reading, NarrationVoice.device);
    try {
      await _phone().speak(text.trim(), language: language);
    } on Object {
      if (session == _session) _notify(NoPhoneVoice(storyId));
    }
  }

  /// How long into a part of [length] to ask for the next one.
  Duration _lead(Duration? length) {
    if (length == null) return Duration.zero;
    final wait = length - prefetchLead;
    return wait.isNegative ? Duration.zero : wait;
  }

  static StudioFallback _fallbackFor(Object? error) => switch (error) {
    ApiException(code: ApiErrorCode.outOfCredits) => StudioFallback.outOfCredits,
    ApiException(code: ApiErrorCode.quotaExceeded) => StudioFallback.quota,
    _ => StudioFallback.unavailable,
  };

  /// Quiets both voices.
  Future<void> _silence() async {
    try {
      await _player().stop();
    } on Object {
      // Nothing was playing.
    }
    try {
      await _phone().stop();
    } on Object {
      // Nothing was reading.
    }
  }

  void _set(String? storyId, int? turn, NarrationPhase phase, NarrationVoice? voice) {
    if (storyId == _storyId && turn == _turn && phase == _phase && voice == _voice) return;
    _storyId = storyId;
    _turn = turn;
    _phase = phase;
    _voice = voice;
    notifyListeners();
  }

  void _notify(NarrationNotice notice) {
    if (!_notices.isClosed) _notices.add(notice);
  }

  @override
  void dispose() {
    _session++;
    unawaited(_notices.close());
    super.dispose();
  }
}

/// The read was stopped before the part was asked for.
class _Stopped {
  const _Stopped();
}

/// A part, or why it couldn't be had.
class _Fetched {
  const _Fetched(StudioPart this.part) : error = null;
  const _Fetched.failed(Object this.error) : part = null;

  final StudioPart? part;
  final Object? error;
}

/// The studio voice's MP3 player. Tests override it with a fake.
final audioPlaybackProvider = Provider<AudioPlayback>((ref) {
  final player = JustAudioPlayback();
  ref.onDispose(player.dispose);
  return player;
});

/// The phone's own voice. Tests override it with a fake.
final phoneVoiceProvider = Provider<PhoneVoice>((ref) {
  final voice = FlutterPhoneVoice();
  ref.onDispose(voice.dispose);
  return voice;
});

final studioVoiceApiProvider = Provider<StudioVoiceApi>(
  (ref) => StudioVoiceApi(ref.watch(apiClientProvider)),
);

/// The app's one narrator. It reads what it needs when it reads, so it lives as long as the app
/// and a screen can hold on to it.
final narratorProvider = Provider<Narrator>((ref) {
  final narrator = Narrator(
    studio: () => ref.read(studioVoiceApiProvider),
    player: () => ref.read(audioPlaybackProvider),
    phone: () => ref.read(phoneVoiceProvider),
    settings: () => ref.read(narrationSettingsProvider.notifier).loaded(),
  );
  ref.onDispose(narrator.dispose);
  return narrator;
});
