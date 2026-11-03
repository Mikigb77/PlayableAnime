import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_providers.dart';
import '../../core/json.dart';

/// A story in the library (docs/API.md `StorySummary`). Only the player's own (S8).
class StorySummary {
  const StorySummary({
    required this.id,
    required this.title,
    required this.turn,
    this.genre = '',
    this.rating = 'teen',
    this.worldTimeLabel,
    this.coverUrl,
    this.updatedAt,
  });

  factory StorySummary.fromJson(JsonMap json) => StorySummary(
    id: json['id'] as String,
    title: json['title'] as String? ?? '',
    turn: (json['turn'] as num? ?? 0).toInt(),
    genre: json['genre'] as String? ?? '',
    rating: json['rating'] as String? ?? 'teen',
    worldTimeLabel: json['world_time_label'] as String?,
    coverUrl: json['cover_url'] as String?,
    updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? ''),
  );

  final String id;
  final String title;

  /// Scenes played. A story just started from a draft is at turn 0 until its opening is written.
  final int turn;
  final String genre;

  /// teen or mature (F2).
  final String rating;

  /// Where the story stands in its own calendar, such as "Day 3, dusk" (W10).
  final String? worldTimeLabel;
  final String? coverUrl;
  final DateTime? updatedAt;
}

class LibraryRepository {
  LibraryRepository(this._api);

  final ApiClient _api;

  /// Newest first, as the server sends them.
  Future<List<StorySummary>> stories() async => [
    for (final json in await _api.get('/v1/stories') as List)
      StorySummary.fromJson(json as JsonMap),
  ];

  /// Deletes a story with its scenes and pictures, for good.
  Future<void> delete(String id) => _api.delete('/v1/stories/${Uri.encodeComponent(id)}');
}

final libraryRepositoryProvider = Provider(
  (ref) => LibraryRepository(ref.watch(apiClientProvider)),
);

/// The player's stories. Invalidate it after anything that changes the list or a story's place in
/// it: a new story, a turn, a delete.
final storiesProvider = FutureProvider.autoDispose(
  (ref) => ref.watch(libraryRepositoryProvider).stories(),
);
