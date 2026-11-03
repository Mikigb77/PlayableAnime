import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_providers.dart';
import '../../core/json.dart';

/// A starter premise (docs/API.md `Premise`, S1). Each starter's genre fixes some rules (G7), which
/// every draft from it keeps until the player changes them.
class Premise {
  const Premise({
    required this.id,
    required this.title,
    required this.genre,
    required this.premise,
    this.tagline,
    this.flagship = false,
    this.coverUrl,
  });

  factory Premise.fromJson(JsonMap json) => Premise(
    id: json['id'] as String,
    title: json['title'] as String,
    genre: json['genre'] as String? ?? '',
    premise: json['premise'] as String,
    tagline: json['tagline'] as String?,
    flagship: json['flagship'] as bool? ?? false,
    coverUrl: json['cover_url'] as String?,
  );

  final String id;
  final String title;
  final String genre;

  /// The starter's own text. A draft from the starter alone uses it word for word.
  final String premise;
  final String? tagline;

  /// One of the flagship genres (cultivation, knights and aura, races and monsters,
  /// reincarnation), shown first.
  final bool flagship;
  final String? coverUrl;
}

/// The flagship starters first, each group in the server's order (S1).
List<Premise> flagshipFirst(Iterable<Premise> premises) => [
  ...premises.where((p) => p.flagship),
  ...premises.where((p) => !p.flagship),
];

/// The starter premises, flagship first.
final premisesProvider = FutureProvider<List<Premise>>((ref) async {
  final json = await ref.watch(apiClientProvider).get('/v1/premises') as List;
  return flagshipFirst([for (final premise in json) Premise.fromJson(premise as JsonMap)]);
});

/// One starter by id, for a create link opened without the premise in hand (a reload, or a link).
/// Null when no starter has that id.
final premiseProvider = FutureProvider.family<Premise?, String>((ref, id) async {
  final premises = await ref.watch(premisesProvider.future);
  return premises.where((p) => p.id == id).firstOrNull;
});
