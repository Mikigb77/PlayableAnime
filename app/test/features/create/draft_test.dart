import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/create/draft_widgets.dart';
import 'package:playable_anime/features/create/draft.dart';

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
    'world_lines': ['The sea keeps its doors shut.', 'The lighthouse has burned for a century.'],
    'character_lines': ['Ada, 40, the keeper.'],
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
      expect(draft.worldLines, hasLength(2));
      expect(draft.linesOf(DraftPart.character), ['Ada, 40, the keeper.']);
      expect(draft.advanced.rules.first, const DraftRule(id: 'r1', text: 'The dead stay dead.'));
      expect(draft.advanced.rules.last.fixed, isFalse);
      expect(draft.advanced.physics, Physics.funFirst);
      expect(draft.version, 4);
      expect(draft.storyId, isNull);
    });

    test('unknown values fall back to the defaults', () {
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
    });
  });

  group('DraftEdit.toJson', () {
    test('sends only what changed, with the version last seen', () {
      expect(const DraftEdit(physics: Physics.strict).toJson(expectedVersion: 4), {
        'advanced': {'physics': 'strict'},
        'expected_version': 4,
      });
      expect(DraftEdit.lines(DraftPart.character, ['Ada.']).toJson(expectedVersion: 2), {
        'character_lines': ['Ada.'],
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

    test('a rewritten line redrafts its own part, and spacing alone is not a change', () {
      expect(
        cost(DraftEdit.lines(DraftPart.world, ['The sea keeps its doors open.', 'Lit.'])),
        const Redraft(world: true),
      );
      expect(
        cost(DraftEdit.lines(DraftPart.character, ['Ada, 41, the keeper.'])),
        const Redraft(character: true),
      );
      expect(
        cost(
          DraftEdit.lines(DraftPart.world, [
            '  The sea keeps   its doors shut. ',
            'The lighthouse has burned for a century.',
            '',
          ]),
        ),
        Redraft.none,
      );
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

  test('lines are kept as the server keeps them', () {
    expect(normalizeLine('  a \n b\tc  '), 'a b c');
    expect(cleanLines(['one', '   ', ' two  lines ']), ['one', 'two lines']);
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
