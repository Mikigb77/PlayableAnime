import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

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
      expect(scene.image?.aspectRatio, 16 / 9);
      expect(
        SceneImage.fromJson(const {'status': 'planned', 'kind': 'portrait'}).aspectRatio,
        3 / 4,
      );
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

    test('a story at its ending reads who was drawn to carry it on (N6)', () {
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'The Ninth Peak',
        'version': 5,
        'scenes': <Object>[],
        'ending': {'kind': 'death', 'character': 'Shen Yu', 'turn': 5},
        'successor': {
          'name': 'Lady Qiao Yun',
          'age': 31,
          'station': 'noble',
          'one_in': 1000,
          'master': true,
          'place': 'The capital',
          'people': null,
          'lines': ['Lady Qiao Yun, 31.'],
          'situation': 'Her carriage stops at the gate.',
          'draws': 2,
        },
        'opening_due': false,
      });
      final drawn = story.successor!;
      expect(
        (drawn.name, drawn.age, drawn.station, drawn.oneIn),
        ('Lady Qiao Yun', 31, 'noble', 1000),
      );
      expect((drawn.master, drawn.place, drawn.people), (true, 'The capital', null));
      expect(drawn.lines, ['Lady Qiao Yun, 31.']);
      expect((drawn.situation, drawn.draws), ('Her carriage stops at the gate.', 2));
      expect(story.openingDue, isFalse);

      final carried = Story.fromJson(const {
        'id': 's',
        'title': 'The Ninth Peak',
        'version': 6,
        'scenes': <Object>[],
        'opening_due': true,
      });
      expect(carried.openingDue, isTrue);
      final opened = carried.withScene(
        const Scene(turn: 6, narration: 'n', choices: [], kind: 'opening'),
        version: 7,
      );
      expect(opened.openingDue, isFalse);
    });

    test('a story at its ending reads the heirs who can carry it on (N6)', () {
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'The Ninth Peak',
        'version': 5,
        'scenes': <Object>[],
        'ending': {'kind': 'death', 'character': 'Shen Yu', 'turn': 5},
        'heirs': [
          {'id': 'xiao', 'name': 'Shen Xiao', 'relation': 'child', 'age': 4, 'years': 12},
          {
            'id': 'unborn:lan',
            'name': "Lan's child, not yet born",
            'relation': 'grandchild',
            'age': null,
            'unborn': true,
            'years': 17,
          },
        ],
        'successor': {
          'name': 'Shen Xiao',
          'age': 16,
          'station': 'common',
          'one_in': 1,
          'lines': <Object>[],
          'situation': 'Dawn.',
          'heir': {'id': 'xiao', 'name': 'Shen Xiao', 'relation': 'child', 'age': 4, 'years': 12},
        },
      });
      final [xiao, unborn] = story.heirs;
      expect((xiao.id, xiao.name, xiao.relation, xiao.age), ('xiao', 'Shen Xiao', 'child', 4));
      expect((xiao.unborn, xiao.years), (false, 12));
      expect(
        (unborn.relation, unborn.age, unborn.unborn, unborn.years),
        ('grandchild', null, true, 17),
      );
      expect(story.successor!.heir?.id, 'xiao');
      expect(story.copyWith(version: 6).heirs, hasLength(2));

      final plain = Story.fromJson(const {
        'id': 's',
        'title': 't',
        'version': 1,
        'scenes': <Object>[],
      });
      expect(plain.heirs, isEmpty);
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
      // The opening takes no field and no input mode.
      expect(const TurnInput.opening().toJson(1), {'kind': 'opening', 'expected_version': 1});
      // Neither does playing out the turn a story owes (A3).
      expect(const TurnInput.resume().toJson(4), {'kind': 'resume', 'expected_version': 4});
    });

    test('a throw reads its dice, its number and its mark (A3)', () {
      final thrown = SceneDetails.fromJson(const {
        'steps': [
          {
            'text': 'Slip under the axe',
            'class': 'contested',
            'reason':
                'Footwork (second nature), 4 dice, against the bandit chief, level 3: '
                '43 against 27, over the top.',
            'roll': {
              'odds_label': '43 against 27',
              'result': 'success',
              'seed': 's9',
              'throw': {
                'dice': [
                  {'kind': 'plain', 'face': 20, 'sprung': false},
                  {'kind': 'plain', 'face': 6, 'sprung': true},
                  {'kind': 'green', 'face': 3, 'sprung': false},
                  {'kind': 'violet', 'face': 4, 'sprung': false},
                  {'kind': 'gold', 'face': 2, 'sprung': false},
                ],
                'hand': 4,
                'hand_why': 'Footwork (second nature), 4 dice',
                'greens': ['Coming from behind'],
                'number': 27,
                'made_of': [
                  {'text': 'the bandit chief, level 3', 'points': 27},
                ],
                'total': 43,
                'most': 80,
                'mark': 'passed',
                'against': 'His axe is already falling.',
                'deadly': true,
                'miss_costs': 'A miss by more than 5 kills.',
                'insight': false,
                'insight_at': 15,
              },
            },
          },
        ],
      }).steps.single.roll!.thrown!;
      expect(
        [for (final die in thrown.dice) die.kind],
        [DieKind.plain, DieKind.plain, DieKind.green, DieKind.violet, DieKind.gold],
      );
      expect([for (final die in thrown.dice) die.sprung], [false, true, false, false, false]);
      // A gold die never counts under ten.
      expect([for (final die in thrown.dice) die.value], [20, 6, 3, 4, 10]);
      expect((thrown.hand, thrown.number, thrown.total, thrown.most), (4, 27, 43, 80));
      expect(thrown.mark, ThrowMark.passed);
      expect(thrown.madeOf.single, (text: 'the bandit chief, level 3', points: 27));
      expect((thrown.deadly, thrown.missCosts), (true, 'A miss by more than 5 kills.'));
      expect((thrown.insight, thrown.insightAt), (false, 15));
      expect(thrown.greens, ['Coming from behind']);
      expect(thrown.ofTheWorld, isFalse);
    });

    test('a roll saved before the dice travelled has no throw, and a broken one is left out', () {
      final details = SceneDetails.fromJson(const {
        'steps': [
          {
            'text': 'Old',
            'class': 'contested',
            'reason': '',
            'roll': {'odds_label': 'about even', 'result': 'failure', 'seed': 's1'},
          },
          {
            'text': 'Broken',
            'class': 'contested',
            'reason': '',
            'roll': {'odds_label': '3 against 7', 'result': 'failure', 'seed': 's2', 'throw': 7},
          },
        ],
      });
      expect(details.steps.first.roll!.thrown, isNull);
      expect(details.steps.last.roll!.thrown, isNull);
      expect(details.hasThrows, isFalse);
    });

    test('a story reads the turn it owes, and a saved scene pays it (A3)', () {
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'T',
        'version': 3,
        'scenes': <Object>[],
        'unfinished_turn': {'turn': 4, 'kind': 'standing', 'action': 'wait'},
      });
      final owed = story.unfinishedTurn!;
      expect((owed.turn, owed.kind, owed.action), (4, 'standing', 'wait'));
      final after = story.withScene(
        Scene.fromJson(const {'turn': 4, 'narration': 'Done.'}),
        version: 4,
      );
      expect(after.unfinishedTurn, isNull);
      expect(Story.fromJson(const {'id': 's', 'title': 'T'}).unfinishedTurn, isNull);
    });

    test('scene details read steps, rolls, beats, the chain and where a plan stopped', () {
      final details = Scene.fromJson(const {
        'turn': 5,
        'kind': 'action',
        'narration': 'You swing across.',
        'time': {
          'world_start_s': 0,
          'world_end_s': 40,
          'label': 'Day 1, dusk',
          'duration_label': '',
        },
        'details': {
          'steps': [
            {
              'text': 'Swing across on a rope',
              'class': 'long_shot',
              'reason': 'Wet stone.',
              'roll': {'odds_label': 'a long shot', 'result': 'partial', 'seed': 's1'},
              'beats': [
                {
                  'beat': 'Find a rope',
                  'thing': 'a rope by the bell',
                  'verdict': 'made_canon',
                  'reason': 'Bells have ropes.',
                },
                {'beat': 'Fly', 'thing': 'wings', 'verdict': 'empty', 'reason': 'You have none.'},
              ],
            },
            {'text': 'Land', 'class': 'ruled_out', 'reason': 'Too far.'},
          ],
          'chain': null,
          'stopped_at_step': 1,
        },
        'blocked': true,
        'created_at': '2026-11-03T18:40:00Z',
      }).details;
      final step = details.steps.first;
      expect(step.outcomeClass, OutcomeClass.longShot);
      expect(step.roll!.result, RollResult.partial);
      expect(step.beats.map((b) => b.madeCanon), [true, false]);
      expect(step.beats.first.thing, 'a rope by the bell');
      expect(details.steps.last.outcomeClass, OutcomeClass.ruledOut);
      expect(details.steps.last.beats, isEmpty);
      expect(details.chain, isEmpty);
      expect(details.stoppedAtStep, 1);
    });

    test('an empty duration reads as none, and a blocked scene says so', () {
      final scene = Scene.fromJson(const {
        'turn': 1,
        'kind': 'opening',
        'narration': 'It begins.',
        'time': {
          'world_start_s': 0,
          'world_end_s': 0,
          'label': 'Day 1, dawn',
          'duration_label': '',
        },
        'blocked': true,
        'created_at': '2026-11-03T18:40:00Z',
      });
      expect(scene.durationLabel, isNull);
      expect(scene.timeLabel, 'Day 1, dawn');
      expect(scene.blocked, isTrue);
      expect(scene.details.isEmpty, isTrue);
    });

    test('settings send every field but the language, and an empty tone clears it', () {
      const settings = StorySettings(tone: 'Wry');
      expect(settings.toJson(), {
        'narration_length': 'medium',
        'tone': 'Wry',
        'difficulty': 'balanced',
        'event_frequency': 'normal',
        'images': 'key_moments',
        'suggestions': true,
        'accent': null,
      });
      final cleared = settings.copyWith(tone: '  ');
      expect(cleared.tone, isNull);
      expect(cleared.toJson()['tone'], isNull);
      expect(cleared, isNot(settings));
      expect(settings.copyWith(difficulty: 'brutal').difficulty, 'brutal');
    });

    test('a story keeps the language it started in, English unless it says otherwise (S10)', () {
      expect(StorySettings.fromJson(const {'difficulty': 'story'}).language, 'en');
      final spanish = StorySettings.fromJson(const {'language': 'es'});
      expect(spanish.language, 'es');
      expect(spanish, isNot(const StorySettings()));
      // A change never carries the language, so saving settings can't switch it.
      final calmer = spanish.copyWith(eventFrequency: 'calm');
      expect(calmer.language, 'es');
      expect(calmer.changesFrom(spanish), {'event_frequency': 'calm'});
      expect(speechLocale(spanish.language), 'es-ES');
      expect(speechLocale('ca'), 'ca-ES');
      expect(speechLocale('en'), 'en-US');
    });

    test('a story keeps the color the player picked, and null goes back to the genre (S13)', () {
      final rose = StorySettings.fromJson(const {'accent': 'rose', 'difficulty': 'story'});
      expect(rose.accent, 'rose');
      expect(const StorySettings().accent, isNull);
      expect(rose, isNot(rose.copyWith(accent: () => null)));
      // Other changes keep the color, and a change of color sends only the color.
      final calmer = rose.copyWith(eventFrequency: 'calm');
      expect(calmer.accent, 'rose');
      expect(calmer.changesFrom(rose), {'event_frequency': 'calm'});
      expect(rose.copyWith(accent: () => 'jade').changesFrom(rose), {'accent': 'jade'});
      expect(rose.copyWith(accent: () => null).changesFrom(rose), {'accent': null});
      expect(rose.copyWith(accent: () => null).difficulty, 'story');
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'T',
        'genre': 'Cultivation',
        'settings': {'accent': 'silver'},
      });
      expect(story.settings.accent, 'silver');
      expect(story.copyWith(title: 'U').settings.accent, 'silver');
    });

    test('a scene saved twice is kept once', () {
      final story = Story.fromJson(const {
        'id': 's',
        'title': 'T',
        'version': 1,
        'scenes': [
          {'turn': 1, 'narration': 'One.'},
        ],
      });
      final next = story
          .withScene(Scene.fromJson(const {'turn': 2, 'narration': 'Two.'}), version: 2)
          .withScene(Scene.fromJson(const {'turn': 2, 'narration': 'Two, again.'}), version: 2);
      expect(next.scenes.map((s) => s.narration), ['One.', 'Two, again.']);
    });
  });
}
