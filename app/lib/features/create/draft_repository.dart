import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_providers.dart';
import '../../core/json.dart';
import 'draft.dart';

/// `/v1/drafts` (docs/API.md). Every change sends the version last seen, so a stale copy is
/// refused with `409 version_conflict` before any model call (T10).
class DraftRepository {
  DraftRepository(this._api);

  final ApiClient _api;

  /// Drafts a world and a character. With [premiseId] alone the starter's own text is the
  /// premise; with both, [premise] is the player's text and the starter's genre still holds. The
  /// draft is written in [language], and its story starts in it (S10).
  Future<Draft> create({
    String? premise,
    String? premiseId,
    required Rating rating,
    String language = 'en',
    DraftChoices choices = const DraftChoices(),
  }) async {
    assert(premise != null || premiseId != null, 'A draft needs a premise or a starter');
    final json = await _api.post('/v1/drafts', {
      'premise': ?premise,
      'premise_id': ?premiseId,
      'rating': rating.wire,
      'language': language,
      if (!choices.isEmpty) 'advanced': choices.toJson(),
    });
    return Draft.fromJson(json as JsonMap);
  }

  Future<Draft> get(String id) async =>
      Draft.fromJson(await _api.get('/v1/drafts/${Uri.encodeComponent(id)}') as JsonMap);

  Future<Draft> edit(Draft draft, DraftEdit edit) async => Draft.fromJson(
    await _api.patch(
          '/v1/drafts/${Uri.encodeComponent(draft.id)}',
          edit.toJson(expectedVersion: draft.version),
        )
        as JsonMap,
  );

  /// A change in plain words, such as "add hidden vampires". [about] is the part of the summary
  /// the player asked it at, so "more of this" says what "this" is.
  Future<Draft> revise(Draft draft, DraftPart part, String instruction, {LineKind? about}) async =>
      Draft.fromJson(
        await _api.post('/v1/drafts/${Uri.encodeComponent(draft.id)}/revise', {
              'target': part.wire,
              'instruction': instruction,
              'about': ?about?.wire,
              'expected_version': draft.version,
            })
            as JsonMap,
      );

  /// Creates the story at turn 0, with no scenes; the play screen asks for the opening. A stale
  /// copy is refused with `409 version_conflict` (T10), and starting again returns the same
  /// story.
  Future<String> start(Draft draft) async {
    final json =
        await _api.post('/v1/drafts/${Uri.encodeComponent(draft.id)}/start', {
              'expected_version': draft.version,
            })
            as JsonMap;
    return json['story_id'] as String;
  }
}

final draftRepositoryProvider = Provider((ref) => DraftRepository(ref.watch(apiClientProvider)));
