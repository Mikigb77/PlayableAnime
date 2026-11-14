import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/create/draft_widgets.dart';
import 'package:playable_anime/features/create/draft.dart';
import 'package:playable_anime/features/story/sheet.dart';

/// The draft model and what each change costs, by the server's own rules (docs/API.md, "Direct
/// edits"; the backend's `chain.plan_edit`).
void main() {
  final draft = Draft.fromJson(const {
    'id': 'draft_1',
    'premise': 'A lighthouse keeper finds a door in the sea.',
    'premise_id': null,
    'rating': 'mature',
    'title': 'The Door in the Sea',
    'genre': 'Mystery',
    'tone': 'Quiet and strange',
    'world_parts': [
      {'kind': 'rule', 'text': 'The dead stay dead.'},
      {'kind': 'era', 'text': 'The lighthouse has burned for a century.'},
      {'kind': 'deadline', 'text': 'The door opens at the spring tide, in nine days.'},
      {'kind': 'omen', 'text': 'A kind a later server tells of.'},
    ],
    'character_parts': [
      {'kind': 'who', 'text': 'Ada, 40, the keeper.'},
      {'kind': 'skills', 'text': 'Knots, tides and lamp oil.'},
      {'kind': 'goal', 'text': 'She wants the door open.'},
    ],
    'character': {
      'name': 'Ada',
      'age': 40,
      'people': 'Islander',
      'standing': 'Keeper of the light',
      'looks': 'Grey braid, oilskin coat.',
      'manner': 'Dry and watchful.',
    },
    'ladder': {
      'name': 'Keepers',
      'rungs': ['Hand', 'Keeper', 'Warden'],
      'more': true,
      'at': 1,
      'stage': 'early',
    },
    'sheet': {
      'money_label': '3 shillings',
      'items': [
        {'name': 'Oilskin coat', 'kind': 'armour', 'carried': true},
      ],
      'skills': [
        {'name': 'Knots', 'level_label': 'Skilled', 'dice': 3},
      ],
      'temperament': ['dry', 'watchful'],
      'talents': [
        {
          'name': 'The sea',
          'strength': 'one_of_a_kind',
          'strength_label': 'One of a kind',
          'pace_label': 'Eight times as fast',
          'covers': 'tides, weather and boats',
          'said': 'nobody reads the sea like her',
        },
        {'name': 'Lamps', 'strength': 'genius', 'strength_label': 'Genius'},
        {'name': 'Rope work', 'strength': 'knack'},
        {'name': 'Letters', 'strength': 'slow'},
        {'name': 'Something new', 'strength': 'a strength a later server tells of'},
      ],
    },
    'kept': {'people': 2, 'events': 1, 'questions': 3},
    'advanced': {
      'physics': 'fun_first',
      'rules': [
        {'id': 'r1', 'text': 'The dead stay dead.', 'fixed': true},
        {'id': 'r2', 'text': 'The door opens at low tide.', 'fixed': false},
      ],
      'gift_strength': 'none',
      'difficulty': 'balanced',
      'event_frequency': 'normal',
    },
    'version': 4,
    'story_id': null,
  });

  group('Draft.fromJson', () {
    test('reads every field', () {
      expect(draft.rating, Rating.mature);
      expect(draft.advanced.rules.first, const DraftRule(id: 'r1', text: 'The dead stay dead.'));
      expect(draft.advanced.rules.last.fixed, isFalse);
      expect(draft.advanced.physics, Physics.funFirst);
      expect(draft.version, 4);
      expect(draft.storyId, isNull);
    });

    test('reads the summary line by line, each with what it tells of', () {
      expect(
        draft.partsOf(DraftPart.character).first,
        const DraftLine(LineKind.who, 'Ada, 40, the keeper.'),
      );
      expect(draft.linesOf(DraftPart.character, LineKind.skills), ['Knots, tides and lamp oil.']);
      expect(draft.linesOf(DraftPart.world, LineKind.faction), isEmpty);
      // A kind this app doesn't know is left out, not shown under a wrong label.
      expect(draft.worldParts.map((line) => line.kind), [
        LineKind.rule,
        LineKind.era,
        LineKind.deadline,
      ]);
    });

    test('reads the plain fields, the ladder and what is kept back', () {
      expect(draft.character.name, 'Ada');
      expect(draft.character.age, 40);
      expect(draft.character.people, 'Islander');
      expect(draft.character.standing, 'Keeper of the light');
      expect(draft.character.looks, 'Grey braid, oilskin coat.');
      expect(draft.character.manner, 'Dry and watchful.');
      expect(draft.ladder!.rungs, ['Hand', 'Keeper', 'Warden']);
      expect(draft.ladder!.more, isTrue);
      expect(draft.ladder!.at, 1);
      expect(draft.ladder!.stage, 'early');
      expect(draft.kept.people, 2);
      expect(draft.kept.events, 1);
      expect(draft.kept.questions, 3);
      expect(draft.kept.isEmpty, isFalse);
    });

    test('reads the character\'s sheet, with how they learn and the words it came from', () {
      // G2, A4: the sheet the story's Character page will show, read from the draft.
      final sheet = draft.sheet;
      expect(sheet.moneyLabel, '3 shillings');
      expect(sheet.carried.single.name, 'Oilskin coat');
      expect(sheet.skills.single.dice, 3);
      expect(sheet.temperament, ['dry', 'watchful']);
      expect(
        [for (final talent in sheet.talents) talent.strength],
        [
          TalentStrength.oneOfAKind,
          TalentStrength.genius,
          TalentStrength.knack,
          TalentStrength.slow,
          // A strength this app doesn't know is the mildest one.
          TalentStrength.knack,
        ],
      );
      expect(sheet.talents.first.said, 'nobody reads the sea like her');
      expect(sheet.talents.first.paceLabel, 'Eight times as fast');
      expect(sheet.talents[1].said, isEmpty);
      expect(
        [for (final talent in sheet.talents) talent.weakness],
        [false, false, false, true, false],
      );
    });

    test('what the premise named of the start comes in the order the summary tells it', () {
      expect(draft.openers, [
        (
          DraftPart.world,
          const DraftLine(LineKind.deadline, 'The door opens at the spring tide, in nine days.'),
        ),
        (DraftPart.character, const DraftLine(LineKind.goal, 'She wants the door open.')),
      ]);
    });

    test('a started draft keeps everything, its language too', () {
      final started = Draft.fromJson(const {
        'id': 'd',
        'language': 'ca',
        'character': {'name': 'Ona'},
        'sheet': {
          'talents': [
            {'name': 'Song', 'strength': 'genius'},
          ],
        },
        'kept': {'people': 1},
      }).started('story_9');
      expect(started.storyId, 'story_9');
      expect(started.sheet.talents.single.name, 'Song');
      expect(started.language, 'ca');
      expect(started.character.name, 'Ona');
      expect(started.kept.people, 1);
    });

    test('unknown and missing values fall back to the defaults', () {
      final odd = Draft.fromJson(const {
        'id': 'd',
        'rating': 'adult',
        'advanced': {'physics': 'magic', 'gift_strength': 'divine', 'difficulty': 'nightmare'},
      });
      expect(odd.rating, Rating.teen);
      expect(odd.advanced.physics, Physics.funFirst);
      expect(odd.advanced.giftStrength, GiftStrength.none);
      expect(odd.advanced.difficulty, Difficulty.balanced);
      expect(odd.advanced.eventFrequency, EventFrequency.normal);
      expect(odd.version, 1);
      expect(odd.worldParts, isEmpty);
      expect(odd.character.name, '');
      expect(odd.character.age, isNull);
      expect(odd.ladder, isNull);
      // A server from before the sheet came with the draft sends none.
      expect(odd.sheet.talents, isEmpty);
      expect(odd.sheet.items, isEmpty);
      expect(odd.kept.isEmpty, isTrue);
      expect(odd.openers, isEmpty);
    });
  });

  group('DraftEdit.toJson', () {
    test('sends only what changed, with the version last seen', () {
      expect(const DraftEdit(physics: Physics.strict).toJson(expectedVersion: 4), {
        'advanced': {'physics': 'strict'},
        'expected_version': 4,
      });
    });

    test('sends the plain fields, the character\'s together', () {
      expect(
        const DraftEdit(title: 'Low Tide', tone: 'Salt and quiet').toJson(expectedVersion: 2),
        {'title': 'Low Tide', 'tone': 'Salt and quiet', 'expected_version': 2},
      );
      expect(const DraftEdit(name: 'Ida', age: 41).toJson(expectedVersion: 2), {
        'character': {'name': 'Ida', 'age': 41},
        'expected_version': 2,
      });
      expect(const DraftEdit(looks: 'Short hair.', manner: 'Blunt.').toJson(expectedVersion: 2), {
        'character': {'looks': 'Short hair.', 'manner': 'Blunt.'},
        'expected_version': 2,
      });
    });

    test('sends the whole list of rules, ids kept and new ones without', () {
      final json = DraftEdit(
        rules: [
          draft.advanced.rules.first.copyWith(fixed: false),
          const DraftRule(text: 'Iron burns the drowned.'),
        ],
        rating: Rating.teen,
      ).toJson(expectedVersion: 4);
      expect(json['rating'], 'teen');
      expect((json['advanced'] as Map)['rules'], [
        {'id': 'r1', 'text': 'The dead stay dead.', 'fixed': false},
        {'text': 'Iron burns the drowned.', 'fixed': true},
      ]);
    });
  });

  group('redraftFor', () {
    Redraft cost(DraftEdit edit) => redraftFor(draft, edit);

    test('settings that change no words are free', () {
      expect(cost(const DraftEdit(physics: Physics.strict)), Redraft.none);
      expect(cost(const DraftEdit(difficulty: Difficulty.brutal)), Redraft.none);
      expect(cost(const DraftEdit(eventFrequency: EventFrequency.dramatic)), Redraft.none);
      expect(cost(const DraftEdit(giftStrength: GiftStrength.none)), Redraft.none);
      expect(cost(const DraftEdit(rating: Rating.mature)), Redraft.none);
    });

    test('flipping a rule between fixed and open is free', () {
      final rules = [for (final rule in draft.advanced.rules) rule.copyWith(fixed: !rule.fixed)];
      expect(cost(DraftEdit(rules: rules)), Redraft.none);
    });

    test('drafted words are compared as they are, the way the server does', () {
      final spaced = Draft.fromJson(const {
        'id': 'd',
        'version': 1,
        'advanced': {
          'rules': [
            {'id': 'r1', 'text': 'The dead  stay dead.', 'fixed': true},
          ],
        },
      });
      // The server saves the player's list normalized, so even a flipped flag rewrites this rule.
      expect(
        redraftFor(spaced, DraftEdit(rules: [spaced.advanced.rules.single.copyWith(fixed: false)])),
        const Redraft(world: true),
      );
    });

    test('a rewritten, added or removed rule redrafts the world', () {
      final [first, second] = draft.advanced.rules;
      const world = Redraft(world: true);
      expect(
        cost(
          DraftEdit(
            rules: [
              first.copyWith(text: 'The dead walk.'),
              second,
            ],
          ),
        ),
        world,
      );
      expect(cost(DraftEdit(rules: [first])), world);
      expect(
        cost(
          DraftEdit(
            rules: [
              first,
              second,
              const DraftRule(text: 'Salt wards.'),
            ],
          ),
        ),
        world,
      );
      // A blank new rule is dropped, as the server drops it.
      expect(
        cost(
          DraftEdit(
            rules: [
              first,
              second,
              const DraftRule(text: '  '),
            ],
          ),
        ),
        Redraft.none,
      );
    });

    test('the plain fields are free: the server writes them in with no model call', () {
      expect(cost(const DraftEdit(title: 'Low Tide', tone: 'Salt and quiet')), Redraft.none);
      expect(cost(const DraftEdit(name: 'Ida', age: 41)), Redraft.none);
      expect(cost(const DraftEdit(looks: 'Short hair.', manner: 'Blunt.')), Redraft.none);
    });

    test('a new gift redrafts the character', () {
      expect(
        cost(const DraftEdit(giftStrength: GiftStrength.rare)),
        const Redraft(character: true),
      );
    });

    test('lowering the rating to Teen redrafts both parts, two calls', () {
      final both = cost(const DraftEdit(rating: Rating.teen));
      expect(both, const Redraft(world: true, character: true));
      expect(both.calls, 2);
      expect(both.isFree, isFalse);
    });
  });

  test('a line is kept as the server keeps it', () {
    expect(normalizeLine('  a \n b\tc  '), 'a b c');
  });

  test('every kind goes by the name the API gives it', () {
    expect(LineKind.fromWire('belongings'), LineKind.belongings);
    expect(LineKind.fromWire('omen'), isNull);
    expect(LineKind.connections.wire, 'connections');
    expect(
      [
        for (final kind in LineKind.values)
          if (kind.isOpener) kind,
      ],
      [LineKind.deadline, LineKind.question, LineKind.person, LineKind.connections, LineKind.goal],
    );
  });

  group('CodePointLimit', () {
    TextEditingValue typed(String text) => TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );

    test('counts code points, as the server does, and keeps whole characters', () {
      const limit = CodePointLimit(5);
      expect(limit.formatEditUpdate(typed(''), typed('abcde')).text, 'abcde');
      expect(limit.formatEditUpdate(typed(''), typed('abcdef')).text, 'abcde');
      // A flag is two code points: it fits only whole.
      expect(limit.formatEditUpdate(typed(''), typed('abcd🇪🇸')).text, 'abcd');
      expect(limit.formatEditUpdate(typed(''), typed('abc🇪🇸')).text, 'abc🇪🇸');
    });
  });
}
