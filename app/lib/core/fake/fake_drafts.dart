import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_premises.dart';
import 'fake_stories.dart';

/// Fake drafting (docs/API.md, "Drafting a world and a character", G1, G2). Owned by the create
/// work (WS15).
class FakeDraftState {
  final drafts = <String, (String ownerId, JsonMap draft)>{};

  JsonMap get(String id, String userId) {
    final entry = drafts[id];
    if (entry == null || entry.$1 != userId) throw const FakeError.notFound('No such draft');
    return entry.$2;
  }
}

void registerDraftRoutes(FakeBackend b) {
  final state = b.data.drafts;

  b.route('POST', '/v1/drafts', (r) {
    final premise = (r.json['premise'] as String? ?? '').trim();
    if (premise.length < 10) throw const FakeError.validation('Write a little more.');
    final starter = fakePremises.where((p) => p['id'] == r.json['premise_id']).firstOrNull;
    final id = b.data.id('draft');
    final draft = <String, dynamic>{
      'id': id,
      'premise': premise,
      'rating': r.json['rating'] ?? 'teen',
      'title': starter?['title'] ?? 'A story of your own',
      'genre': starter?['genre'] ?? 'Your own',
      'tone': 'Tense, with room for wonder',
      'world_lines': [
        'A world shaped by your premise, where power has rules and the rules have a price.',
        'Three factions want the same thing, and only one of them knows you exist.',
        'News travels at the speed of a fast horse; rumours travel faster.',
      ],
      'character_lines': [
        'Someone with more nerve than standing.',
        'Owes a favour to the wrong person.',
        'Carries one thing they would die before losing.',
      ],
      'advanced': {
        'physics': 'fun_first',
        'rules': [
          {'id': 'r1', 'text': 'The dead stay dead.', 'fixed': true},
          {'id': 'r2', 'text': 'Power grows through effort, teachers and luck.', 'fixed': false},
        ],
        'difficulty': 'balanced',
        'event_frequency': 'normal',
        ...?r.json['advanced'] as JsonMap?,
      },
      'created_at': b.now().toUtc().toIso8601String(),
    };
    state.drafts[id] = (r.userId!, draft);
    return FakeResponse.json(draft, status: 201);
  });

  b.route('GET', '/v1/drafts/:id', (r) => FakeResponse.json(state.get(r.param('id'), r.userId!)));

  b.route('PATCH', '/v1/drafts/:id', (r) {
    final draft = state.get(r.param('id'), r.userId!);
    for (final key in ['world_lines', 'character_lines', 'rating']) {
      if (r.json.containsKey(key)) draft[key] = r.json[key];
    }
    if (r.json['advanced'] case final JsonMap advanced) {
      draft['advanced'] = {...draft['advanced'] as JsonMap, ...advanced};
    }
    return FakeResponse.json(draft);
  });

  b.route('POST', '/v1/drafts/:id/revise', (r) {
    final draft = state.get(r.param('id'), r.userId!);
    final target = r.json['target'] == 'character' ? 'character_lines' : 'world_lines';
    final instruction = (r.json['instruction'] as String? ?? '').trim();
    if (instruction.isEmpty) throw const FakeError.validation('Say what to change.');
    draft[target] = [...draft[target] as List, 'Now: $instruction.'];
    return FakeResponse.json(draft);
  });

  b.route('POST', '/v1/drafts/:id/start', (r) {
    final draft = state.get(r.param('id'), r.userId!);
    final story = b.data.stories.add(
      FakeStory(
        id: b.data.id('story'),
        ownerId: r.userId!,
        title: draft['title'] as String,
        genre: draft['genre'] as String,
        premise: draft['premise'] as String,
        rating: draft['rating'] as String,
        updatedAt: b.now(),
        coverUrl: FakeAssets.forGenre(draft['genre'] as String),
      ),
    );
    if (r.json['settings'] case final JsonMap settings) {
      story.settings = {...story.settings, ...settings};
    }
    state.drafts.remove(r.param('id'));
    return FakeResponse.json({'story_id': story.id}, status: 201);
  });
}
