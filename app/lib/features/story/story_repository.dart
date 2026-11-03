import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import 'story_models.dart';

class StoryRepository {
  StoryRepository(this._api);

  final ApiClient _api;

  Future<List<Premise>> premises() async => [
    for (final json in await _api.get('/v1/premises') as List) Premise.fromJson(json as Json),
  ];

  Future<List<StorySummary>> stories() async => [
    for (final json in await _api.get('/v1/stories') as List) StorySummary.fromJson(json as Json),
  ];

  Future<Story> create({required String premise, String? title}) async {
    final json = await _api.post('/v1/stories', {
      'premise': premise,
      if (title != null && title.isNotEmpty) 'title': title,
    });
    return Story.fromJson(json as Json);
  }

  Future<Story> get(String id) async => Story.fromJson(await _api.get('/v1/stories/$id') as Json);

  Future<WorldState> memory(String id) async =>
      WorldState.fromJson(await _api.get('/v1/stories/$id/memory') as Json);

  /// Advances the story with either one of the offered choices or a free-text action.
  Future<TurnResult> takeTurn(String id, {String? choiceId, String? action}) async {
    final json = await _api.post('/v1/stories/$id/turns', {
      'choice_id': ?choiceId,
      'action': ?action,
    });
    return TurnResult.fromJson(json as Json);
  }
}

final storyRepositoryProvider = Provider((ref) => StoryRepository(ref.watch(apiClientProvider)));

final premisesProvider = FutureProvider((ref) => ref.watch(storyRepositoryProvider).premises());

final storiesProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(storyRepositoryProvider).stories(),
);

final memoryProvider = FutureProvider.autoDispose.family<WorldState, String>(
  (ref, storyId) => ref.watch(storyRepositoryProvider).memory(storyId),
);
