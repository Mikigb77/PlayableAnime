import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_providers.dart';
import '../../core/api/turn_events.dart';
import 'story_models.dart';

/// A turn to take (docs/API.md `TurnRequest`).
class TurnInput {
  const TurnInput.action(String this.action, {required this.inputMode})
    : kind = 'action',
      choiceId = null,
      standing = null;

  const TurnInput.choice(String this.choiceId)
    : kind = 'choice',
      action = null,
      standing = null,
      inputMode = 'choice';

  const TurnInput.standing(String this.standing)
    : kind = 'standing',
      action = null,
      choiceId = null,
      inputMode = 'choice';

  final String kind;
  final String? action;
  final String? choiceId;
  final String? standing;
  final String inputMode;

  Json toJson(int expectedVersion) => {
    'kind': kind,
    'action': ?action,
    'choice_id': ?choiceId,
    'standing': ?standing,
    'input_mode': inputMode,
    'expected_version': expectedVersion,
  };
}

class StoryRepository {
  StoryRepository(this._api);

  final ApiClient _api;

  Future<List<Premise>> premises() async => [
    for (final json in await _api.get('/v1/premises') as List) Premise.fromJson(json as Json),
  ];

  Future<List<StorySummary>> stories() async => [
    for (final json in await _api.get('/v1/stories') as List) StorySummary.fromJson(json as Json),
  ];

  /// Today's backend creates a story straight from a premise. The create work (WS15) moves this to
  /// drafts (`POST /v1/drafts`, then `/start`).
  Future<Story> create({required String premise, String? title}) async {
    final json = await _api.post('/v1/stories', {
      'premise': premise,
      if (title != null && title.isNotEmpty) 'title': title,
    });
    return Story.fromJson(json as Json);
  }

  Future<Story> get(String id) async => Story.fromJson(await _api.get('/v1/stories/$id') as Json);

  Future<MemoryData> memory(String id) async =>
      MemoryData.fromJson(await _api.get('/v1/stories/$id/memory') as Json);

  Future<StatusData> status(String id) async =>
      StatusData.fromJson(await _api.get('/v1/stories/$id/status') as Json);

  /// Takes a turn and streams it. Errors before the stream starts throw `ApiException`; the
  /// stream ends with [SceneCompleted] or [TurnFailed].
  ///
  /// Until the turn graph lands (WS3), the backend answers with one JSON object,
  /// `{scene, state, version}`, instead of a stream; that reply is replayed as the same events, so
  /// the play screen has one code path.
  Future<Stream<TurnEvent>> takeTurn(
    String id,
    TurnInput input, {
    required int expectedVersion,
  }) async {
    final response = await _api.openStream('/v1/stories/$id/turns', input.toJson(expectedVersion));
    if (response.isEventStream) return response.turnEvents();
    final json = await response.json() as Json;
    final scene = json['scene'] as Json;
    return Stream.fromIterable([
      TurnStarted((scene['turn'] as num).toInt()),
      NarrationDelta(scene['narration'] as String),
      SceneCompleted(
        scene: scene,
        version: (json['version'] as num?)?.toInt() ?? expectedVersion + 1,
        clock: const {},
      ),
    ]);
  }

  /// Asks for a scene's planned picture (M3). Safe to repeat: the server makes and charges it once.
  /// [kind] is the scene's, kept when the answer leaves it out.
  Future<SceneImage> picture(String id, int turn, {String kind = 'scene'}) async {
    final json = await _api.post('/v1/stories/$id/scenes/$turn/image', null) as Json;
    return SceneImage(
      status: switch (json['status']) {
        'ready' => 'ready',
        'pending' => 'planned',
        _ => 'skipped',
      },
      url: json['url'] as String?,
      kind: json['kind'] as String? ?? kind,
      imageId: json['image_id'] as String?,
    );
  }
}

final storyRepositoryProvider = Provider((ref) => StoryRepository(ref.watch(apiClientProvider)));

final premisesProvider = FutureProvider((ref) => ref.watch(storyRepositoryProvider).premises());

final storiesProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(storyRepositoryProvider).stories(),
);

final memoryProvider = FutureProvider.autoDispose.family<MemoryData, String>(
  (ref, storyId) => ref.watch(storyRepositoryProvider).memory(storyId),
);

final statusProvider = FutureProvider.autoDispose.family<StatusData, String>(
  (ref, storyId) => ref.watch(storyRepositoryProvider).status(storyId),
);
