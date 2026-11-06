import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';

/// What `POST /v1/stories/{id}/scenes/{turn}/audio` answers for one part of a scene read in the
/// studio voice (docs/API.md, "Reading aloud").
@immutable
class StudioPart {
  const StudioPart({
    required this.status,
    required this.part,
    required this.parts,
    required this.text,
    this.url,
    this.duration,
  });

  factory StudioPart.fromJson(Map<String, Object?> json) => StudioPart(
    status: StudioPartStatus.fromWire(json['status']),
    part: (json['part'] as num?)?.toInt() ?? 0,
    parts: (json['parts'] as num?)?.toInt() ?? 0,
    text: json['text'] as String? ?? '',
    url: json['url'] as String?,
    duration: switch (json['duration_ms']) {
      final num ms => Duration(milliseconds: ms.toInt()),
      _ => null,
    },
  );

  final StudioPartStatus status;
  final int part;

  /// How many parts the scene is read in.
  final int parts;

  /// The words this part reads.
  final String text;

  /// The MP3, while it is [StudioPartStatus.ready].
  final String? url;
  final Duration? duration;
}

enum StudioPartStatus {
  ready,

  /// Another request is reading it: ask again in a moment.
  pending,

  /// The voice model won't read it: the phone's voice reads it instead.
  blocked;

  static StudioPartStatus fromWire(Object? value) =>
      values.where((s) => s.name == value).firstOrNull ?? blocked;
}

/// Asks the API for a scene's parts in the studio voice.
class StudioVoiceApi {
  StudioVoiceApi(
    this.api, {
    this.pendingDelay = const Duration(seconds: 1),
    this.pendingTries = 60,
  });

  final ApiClient api;

  /// How long to wait before asking again for a part another request is reading, and how often.
  final Duration pendingDelay;
  final int pendingTries;

  /// Part [part] of the scene, once it is ready or refused. Throws [ApiException] when the
  /// studio voice can't read it now (out of credits, a limit, the model unavailable).
  Future<StudioPart> part(String storyId, int turn, int part, {required String voice}) async {
    for (var attempt = 0; ; attempt++) {
      final json = await api.post(
        '/v1/stories/$storyId/scenes/$turn/audio',
        null,
        query: {'part': '$part', 'voice': voice},
      );
      if (json is! Map<String, Object?>) throw const ApiException(ApiErrorCode.server);
      final read = StudioPart.fromJson(json);
      if (read.status != StudioPartStatus.pending) return read;
      if (attempt + 1 >= pendingTries) throw const ApiException(ApiErrorCode.llmUnavailable);
      await Future<void>.delayed(pendingDelay);
    }
  }
}

/// Plays the studio voice's MP3s, one part after another. Tests replace it with a fake.
abstract class AudioPlayback {
  /// Plays the file at [url] (an `https:` URL, or `asset:///` for the offline API), and
  /// completes when it has played or [stop] cut it short. Throws when it can't be played.
  Future<void> play(String url);

  Future<void> stop();

  void dispose() {}
}

/// [AudioPlayback] on `just_audio`: ExoPlayer on Android, AVPlayer on iOS, an audio element on
/// the web. The player is made on the first part, so nothing loads until a scene is read.
class JustAudioPlayback implements AudioPlayback {
  AudioPlayer? _player;
  Completer<void>? _done;

  @override
  Future<void> play(String url) async {
    final player = _player ??= AudioPlayer();
    final done = _done = Completer<void>();
    StreamSubscription<PlayerState>? listening;
    try {
      await player.setUrl(url);
      if (done.isCompleted) return; // stopped while it loaded
      // Listened to once loaded, so the last part's "completed" doesn't end this one.
      listening = player.playerStateStream.listen(
        (state) {
          if (state.processingState == ProcessingState.completed && !done.isCompleted) {
            done.complete();
          }
        },
        onError: (Object error, StackTrace stack) {
          if (!done.isCompleted) done.completeError(error, stack);
        },
      );
      unawaited(
        player.play().catchError((Object error, StackTrace stack) {
          if (!done.isCompleted) done.completeError(error, stack);
        }),
      );
      await done.future;
    } finally {
      await listening?.cancel();
      // A finished player still counts as playing: pause it, so the next part starts.
      await player.pause();
    }
  }

  @override
  Future<void> stop() async {
    final done = _done;
    if (done != null && !done.isCompleted) done.complete();
    await _player?.stop();
  }

  @override
  void dispose() {
    final player = _player;
    _player = null;
    if (player != null) unawaited(player.dispose());
  }
}
