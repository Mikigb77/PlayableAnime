import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/api/api_providers.dart';
import '../../core/api/turn_events.dart';
import 'story_models.dart';

/// A turn to take (docs/API.md `TurnRequest`). The interim endpoint takes the same body.
class TurnInput {
  const TurnInput.action(String this.action, {required this.inputMode})
    : kind = 'action',
      choiceId = null,
      standing = null,
      dropRefused = false;

  const TurnInput.choice(String this.choiceId)
    : kind = 'choice',
      action = null,
      standing = null,
      inputMode = 'choice',
      dropRefused = false;

  const TurnInput.standing(String this.standing)
    : kind = 'standing',
      action = null,
      choiceId = null,
      inputMode = 'choice',
      dropRefused = false;

  /// The opening scene of a story that has none yet, right after a draft starts.
  /// The opening has no input mode: nobody entered anything (V7).
  const TurnInput.opening()
    : kind = 'opening',
      action = null,
      choiceId = null,
      standing = null,
      inputMode = null,
      dropRefused = false;

  /// Ends the story with `/end` (N6): an epilogue, told from things as they stand or from
  /// [note], the player's words on how it should end. With [dropRefused], what the world refused
  /// of the note is left out instead of handed back.
  const TurnInput.end(String? note, {String? inputMode, this.dropRefused = false})
    : kind = 'end',
      action = note,
      choiceId = null,
      standing = null,
      inputMode = note == null ? null : inputMode;

  final String kind;
  final String? action;
  final String? choiceId;
  final String? standing;

  /// typed, voice, voice_edited or choice (V7).
  final String? inputMode;

  /// An end turn only: tell the epilogue without what the world refused of the note.
  final bool dropRefused;

  /// This end turn again, leaving out what the world refused.
  TurnInput withoutRefused() => TurnInput.end(action, inputMode: inputMode, dropRefused: true);

  Json toJson(int expectedVersion) => {
    'kind': kind,
    'action': ?action,
    'choice_id': ?choiceId,
    'standing': ?standing,
    'input_mode': ?inputMode,
    if (dropRefused) 'drop_refused': true,
    'expected_version': expectedVersion,
  };
}

class StoryRepository {
  StoryRepository(this._api);

  final ApiClient _api;

  /// A story with its latest [scenes] scenes.
  Future<Story> get(String id, {int scenes = 20}) async =>
      Story.fromJson(await _api.get('/v1/stories/$id', query: {'scenes': '$scenes'}) as Json);

  /// Scenes before [before], oldest first, for scrollback.
  Future<List<Scene>> olderScenes(String id, {required int before, int limit = 20}) async => [
    for (final json
        in await _api.get('/v1/stories/$id/scenes', query: {'before': '$before', 'limit': '$limit'})
            as List)
      Scene.fromJson(json as Json),
  ]..sort((a, b) => a.turn.compareTo(b.turn));

  /// Renames the story or changes some of its settings (S6). [settings] holds only the fields
  /// that change (see [StorySettings.changesFrom]); the server keeps the rest.
  Future<Story> update(String id, {String? title, Json? settings}) async => Story.fromJson(
    await _api.patch('/v1/stories/$id', {
          'title': ?title,
          if (settings != null && settings.isNotEmpty) 'settings': settings,
        })
        as Json,
  );

  /// Closes a story at its ending (N6). It stays in the Library to read.
  Future<Story> close(String id) async =>
      Story.fromJson(await _api.post('/v1/stories/$id/close', null) as Json);

  /// Takes the story back [scenes] scenes from a death (C8), to the world as it was then. The
  /// later scenes are gone from the story it answers with.
  Future<Story> rewind(String id, {required int expectedVersion, required int scenes}) async =>
      Story.fromJson(
        await _api.post('/v1/stories/$id/rewind', {
              'expected_version': expectedVersion,
              'scenes': scenes,
            })
            as Json,
      );

  /// Draws someone new to carry the story on after its ending (N6), or takes the heir [heirId],
  /// replacing anyone drawn before. It is one drafting call, charged like a draft (K2).
  Future<Successor> drawSuccessor(String id, {String? heirId}) async {
    final query = heirId == null ? '' : '?heir_id=${Uri.encodeQueryComponent(heirId)}';
    return Successor.fromJson(await _api.post('/v1/stories/$id/successor$query', null) as Json);
  }

  /// Starts as the person drawn (N6): the ending is lifted, and the story's next turn is their
  /// opening.
  Future<Story> carryOn(String id, {required int expectedVersion}) async => Story.fromJson(
    await _api.post('/v1/stories/$id/carry-on', {'expected_version': expectedVersion}) as Json,
  );

  Future<StatusData> status(String id) async =>
      StatusData.fromJson(await _api.get('/v1/stories/$id/status') as Json);

  /// Takes a turn and streams it (docs/API.md, Turns). Errors before the stream starts throw
  /// [ApiException]; the stream ends with [SceneCompleted] or [TurnFailed].
  Future<Stream<TurnEvent>> takeTurn(
    String id,
    TurnInput input, {
    required int expectedVersion,
  }) async {
    final response = await _api.openStream('/v1/stories/$id/turns', input.toJson(expectedVersion));
    if (response.isEventStream) return response.turnEvents();
    // Not a stream: a proxy's page or an old server. Read it so the connection is freed.
    try {
      await response.json();
    } on ApiException {
      // The body doesn't matter.
    }
    throw ApiException(ApiErrorCode.server, status: response.statusCode);
  }

  /// Asks for a scene's planned picture (M3). Safe to repeat: the server makes and charges it once.
  /// [kind] is the scene's, kept when the answer leaves it out.
  Future<SceneImage> picture(String id, int turn, {String kind = 'scene'}) async =>
      _picture(await _api.post('/v1/stories/$id/scenes/$turn/image', null) as Json, kind);

  /// Asks for a picture of any scene, which the player pays for (M2). Also safe to repeat: a
  /// picture already drawn comes back at no charge.
  Future<SceneImage> illustrate(String id, int turn, {String kind = 'scene'}) async => _picture(
    await _api.post('/v1/stories/$id/scenes/$turn/illustrate', null) as Json,
    kind,
    planned: false,
  );

  /// A fresh signed URL for a picture whose URL expired. Never draws.
  Future<SceneImage> refreshPicture(String id, String imageId, {String kind = 'scene'}) async =>
      _picture(
        await _api.get('/v1/stories/$id/images/${Uri.encodeComponent(imageId)}') as Json,
        kind,
      );

  /// Reports a scene (F6). With [block], the app also hides it.
  Future<void> report(
    String id,
    int turn, {
    required String category,
    String? note,
    required bool block,
  }) async {
    await _api.post('/v1/stories/$id/scenes/$turn/report', {
      'category': category,
      if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
      'block': block,
    });
  }

  static SceneImage _picture(Json json, String kind, {bool planned = true}) => SceneImage(
    status: switch (json['status']) {
      'ready' => 'ready',
      'pending' => 'planned',
      _ => 'skipped',
    },
    url: json['url'] as String?,
    kind: json['kind'] as String? ?? kind,
    imageId: json['image_id'] as String?,
    expiresAt: switch (json['expires_at']) {
      final String at => DateTime.tryParse(at),
      _ => null,
    },
    planned: planned,
  );
}

final storyRepositoryProvider = Provider((ref) => StoryRepository(ref.watch(apiClientProvider)));

final statusProvider = FutureProvider.autoDispose.family<StatusData, String>(
  (ref, storyId) => ref.watch(storyRepositoryProvider).status(storyId),
);
