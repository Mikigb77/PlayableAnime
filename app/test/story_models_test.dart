import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/story/story_models.dart';

void main() {
  test('Story parses the backend payload and applies a turn', () {
    final story = Story.fromJson({
      'id': 's1',
      'title': 'Courier',
      'premise': 'A courier finds a package.',
      'scenes': [
        {
          'turn': 1,
          'player_action': null,
          'narration': 'Rain falls.',
          'choices': [
            {'id': 'c1', 'label': 'Open it'},
          ],
          'image_prompt': null,
          'image_url': null,
        },
      ],
      'state': {
        'turn': 1,
        'summary': 'It begins.',
        'goals': ['Deliver the package'],
        'characters': [
          {'id': 'ren', 'name': 'Ren', 'description': '', 'status': 'dead', 'affinity': -5},
        ],
        'factions': [],
        'facts': [
          {'text': 'The package hums.', 'turn': 1, 'importance': 4},
        ],
      },
    });

    expect(story.scenes.single.choices.single.label, 'Open it');
    expect(story.state.characters.single.isDead, isTrue);
    expect(story.state.facts.single.importance, 4);

    final next = story.withTurn(
      TurnResult.fromJson({
        'scene': {'turn': 2, 'player_action': 'Open it', 'narration': 'It glows.', 'choices': []},
        'state': {'turn': 2},
      }),
    );

    expect(next.scenes, hasLength(2));
    expect(next.scenes.last.playerAction, 'Open it');
    expect(next.state.turn, 2);
  });
}
