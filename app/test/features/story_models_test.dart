import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

/// The models read both the v1 API (docs/API.md) and today's FastAPI payloads.
void main() {
  group('today\'s backend', () {
    const story = {
      'id': 'abc',
      'title': 'Last Exam at Hollowmere',
      'premise': 'A school for witches.',
      'scenes': [
        {
          'turn': 1,
          'player_action': null,
          'narration': 'The exam hall is silent.',
          'choices': [
            {'id': 'c1', 'label': 'Open the paper'},
          ],
          'image_prompt': 'A silent hall',
          'image_url': 'https://example.test/hall.png',
        },
      ],
      'state': {'turn': 1, 'summary': '', 'goals': <String>[]},
    };

    test('a story reads with its scenes, choices and picture', () {
      final parsed = Story.fromJson(story);
      expect(parsed.title, 'Last Exam at Hollowmere');
      expect(parsed.version, 0);
      expect(parsed.genre, '');
      final scene = parsed.scenes.single;
      expect(scene.choices.single.kind, 'thread');
      expect(scene.image?.isReady, isTrue);
      expect(scene.standingActions, isEmpty);
      expect(scene.durationLabel, isNull);
    });

    test('a summary without v1 fields reads', () {
      final summary = StorySummary.fromJson(const {
        'id': 'abc',
        'title': 'T',
        'premise': 'P',
        'turn': 4,
      });
      expect(summary.turn, 4);
      expect(summary.coverUrl, isNull);
    });

    test('world state reads as memory', () {
      final memory = MemoryData.fromJson(const {
        'turn': 3,
        'summary': 'You passed.',
        'goals': ['Find the missing proctor'],
        'characters': [
          {'id': 'p1', 'name': 'Proctor Vale', 'description': 'Stern', 'affinity': 40},
        ],
        'factions': <Object>[],
        'facts': [
          {'text': 'The bell is cursed', 'turn': 2, 'importance': 5},
        ],
      });
      final titles = [for (final s in memory.sections) ...s.items.map((i) => i.title)];
      expect(titles, containsAll(['Find the missing proctor', 'Proctor Vale']));
    });
  });

  group('the v1 API', () {
    test('a scene reads its time, event, picture, portraits and standing actions', () {
      final scene = Scene.fromJson(const {
        'turn': 5,
        'kind': 'action',
        'player_action': 'I draw my blade',
        'input_mode': 'voice_edited',
        'narration': 'Steel sings.',
        'choices': [
          {'id': 'c1', 'label': 'Press the attack', 'kind': 'thread'},
          {'id': 'c2', 'label': 'Ask for mercy', 'kind': 'wild'},
        ],
        'standing_actions': ['wait', 'observe'],
        'time': {
          'world_start_s': 100,
          'world_end_s': 140,
          'label': 'Day 1, dawn',
          'duration_label': '+40 s',
          'personal_label': 'World: +0 s. You: +40 s.',
        },
        'event': {'size': 'local', 'title': 'Fire in the lower market'},
        'image': {'planned': true, 'kind': 'scene', 'status': 'planned'},
        'portraits': [
          {'name': 'Elder Wen', 'url': null},
        ],
      });
      expect(scene.spoken, isTrue);
      expect(scene.choices.last.kind, 'wild');
      expect(scene.durationLabel, '+40 s');
      expect(scene.personalTimeLabel, contains('You: +40 s'));
      expect(scene.eventSize, 'local');
      expect(scene.image?.status, 'planned');
      expect(scene.image?.isReady, isFalse);
      expect(scene.portraits.single.name, 'Elder Wen');
      expect(scene.withImage(const SceneImage(status: 'ready', url: 'u')).image?.isReady, isTrue);
    });

    test('a story reads its version and clock, and a new scene moves both', () {
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'The Ninth Peak',
        'genre': 'Cultivation',
        'version': 3,
        'clock': {'world_s': 480, 'label': 'Day 1, dawn'},
        'scenes': <Object>[],
      });
      expect(story.version, 3);
      expect(story.clockLabel, 'Day 1, dawn');
      final next = story.withScene(
        const Scene(turn: 1, narration: 'n', choices: []),
        version: 4,
        clockLabel: 'Day 1, morning',
      );
      expect(next.version, 4);
      expect(next.scenes, hasLength(1));
      expect(next.clockLabel, 'Day 1, morning');
    });

    test('a turn request carries its kind, mode and expected version', () {
      expect(const TurnInput.action('Go', inputMode: 'voice').toJson(7), {
        'kind': 'action',
        'action': 'Go',
        'input_mode': 'voice',
        'expected_version': 7,
      });
      expect(const TurnInput.choice('c2').toJson(1), {
        'kind': 'choice',
        'choice_id': 'c2',
        'input_mode': 'choice',
        'expected_version': 1,
      });
      expect(const TurnInput.standing('wait').toJson(2)['standing'], 'wait');
    });
  });
}
