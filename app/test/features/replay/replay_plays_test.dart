import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/turn_events.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/story/dice/dice_tray.dart';
import 'package:playable_anime/features/story/dice/throw_sim.dart';
import 'package:playable_anime/features/story/replay/replay_plays.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

import '../../helpers.dart';

SceneThrow _throw(
  List<(DieKind, int)> dice, {
  required int number,
  String handWhy = 'Sword form (skilled), 3 dice',
  List<String> greens = const [],
  List<NumberPart> madeOf = const [(text: "the guard's swordplay (skilled), level 3", points: 0)],
  String against = '',
  bool deadly = false,
  String missCosts = '',
  bool insight = false,
  Set<int> sprung = const {},
}) {
  final thrown = [
    for (final (i, (kind, face)) in dice.indexed)
      ThrownDie(kind: kind, face: face, sprung: sprung.contains(i)),
  ];
  final hand = thrown.where((die) => !die.sprung).length;
  final total = thrown.fold<int>(0, (sum, die) => sum + die.value);
  final most = 20 * hand;
  return SceneThrow(
    dice: thrown,
    hand: hand,
    handWhy: handWhy,
    greens: greens,
    number: number,
    madeOf: madeOf,
    total: total,
    most: most,
    mark: total >= number
        ? (total > most ? ThrowMark.overTheTop : ThrowMark.passed)
        : (number - total <= 5 ? ThrowMark.soClose : ThrowMark.missed),
    against: against,
    deadly: deadly,
    missCosts: missCosts,
    insight: insight,
  );
}

SceneRoll _roll(SceneThrow thrown, {String seed = 'seed-1'}) => SceneRoll(
  oddsLabel: '${thrown.total} against ${thrown.number}',
  result: thrown.mark.reached ? RollResult.success : RollResult.failure,
  seed: seed,
  thrown: thrown,
);

/// What the replay plays (S15): a scene's steps in the order they happened, each with the dice
/// the server sent. Nothing here decides anything (A3).
void main() {
  final attack = _throw(
    [(DieKind.plain, 12), (DieKind.plain, 9), (DieKind.violet, 10)],
    number: 27,
    against: 'The guard has trained with a sword for years.',
  );

  group('the order', () {
    test("a step's checks come first, then the step, then what struck back", () {
      final defence = _throw(
        [(DieKind.plain, 3), (DieKind.gold, 4)],
        number: 17,
        handWhy: 'Footwork (practiced), 2 dice',
        deadly: true,
        missCosts: 'A miss can kill.',
      );
      final plays = playsOf(
        SceneDetails(
          steps: [
            SceneStep(
              text: 'I climb down the rope',
              outcomeClass: OutcomeClass.contested,
              roll: _roll(attack),
              beats: [
                SceneBeat(
                  beat: 'Find a rope',
                  thing: 'a rope in the bell tower',
                  madeCanon: true,
                  roll: _roll(
                    _throw([(DieKind.grey, 14)], number: 11, handWhy: "The world's die"),
                    seed: 'seed-0',
                  ),
                ),
              ],
              struck: [
                SceneStruck(
                  by: 'the guard',
                  outcomeClass: OutcomeClass.contested,
                  harm: 'wounded',
                  roll: _roll(defence, seed: 'seed-2'),
                ),
                const SceneStruck(by: 'the long drop', outcomeClass: OutcomeClass.certain),
              ],
            ),
            const SceneStep(text: 'I walk away', outcomeClass: OutcomeClass.certain),
          ],
        ),
      );

      expect(
        [for (final play in plays) (play.kind, play.step, play.title)],
        [
          (PlayKind.beat, 1, 'Find a rope'),
          (PlayKind.step, 1, 'I climb down the rope'),
          (PlayKind.struck, 1, 'the guard'),
          (PlayKind.struck, 1, 'the long drop'),
          (PlayKind.step, 2, 'I walk away'),
        ],
      );
      expect(
        [for (final play in plays) play.end],
        [PlayEnd.there, PlayEnd.passed, PlayEnd.soClose, PlayEnd.held, PlayEnd.certain],
      );
      expect(plays[0].thing, 'a rope in the bell tower');
      expect(plays[2].deadly, isTrue);
      expect(plays[3].sure, isTrue);
      expect(plays.map((play) => play.stoppedHere), everyElement(isFalse));
    });

    test('a plan that stopped says so on the last thing that happened in that step (R6)', () {
      final plays = playsOf(
        SceneDetails(
          stoppedAtStep: 1,
          steps: [
            const SceneStep(text: 'I open the door', outcomeClass: OutcomeClass.certain),
            SceneStep(
              text: 'I slip past the guard',
              outcomeClass: OutcomeClass.contested,
              roll: _roll(_throw([(DieKind.plain, 4), (DieKind.plain, 7)], number: 27)),
              struck: const [
                SceneStruck(by: 'the guard', outcomeClass: OutcomeClass.certain, harm: 'hurt'),
              ],
            ),
          ],
        ),
      );

      expect([for (final play in plays) play.stoppedHere], [false, false, true]);
      expect(plays.last.kind, PlayKind.struck);
      expect(plays.last.end, PlayEnd.lands);
      expect(plays[1].end, PlayEnd.missed);
    });

    test("a step takes the words the scene shows for it", () {
      final plays = playsOf(
        const SceneDetails(
          steps: [SceneStep(text: 'wait', outcomeClass: OutcomeClass.certain)],
        ),
        stepText: (step) => 'Let time pass',
      );
      expect(plays.single.title, 'Let time pass');
    });

    test('how a play ends follows the server, never the dice read again (A3)', () {
      SceneStep step(OutcomeClass outcome, [SceneRoll? roll]) =>
          SceneStep(text: 'x', outcomeClass: outcome, roll: roll);
      // A mark the dice alone wouldn't give: the server said so close, and so close it is.
      final ruled = SceneThrow(
        dice: const [ThrownDie(kind: DieKind.plain, face: 20)],
        number: 7,
        total: 20,
        most: 20,
        mark: ThrowMark.soClose,
      );
      final plays = playsOf(
        SceneDetails(
          steps: [
            step(OutcomeClass.contested, _roll(ruled)),
            step(OutcomeClass.ruledOut),
            step(OutcomeClass.certain),
            // Rolls saved before the dice travelled: the result, with no throw to show.
            step(
              OutcomeClass.contested,
              const SceneRoll(oddsLabel: 'about even', result: RollResult.success),
            ),
            step(
              OutcomeClass.contested,
              const SceneRoll(oddsLabel: 'about even', result: RollResult.partial),
            ),
            step(
              OutcomeClass.longShot,
              const SceneRoll(oddsLabel: 'a long shot', result: RollResult.failure),
            ),
          ],
        ),
      );
      expect(
        [for (final play in plays) play.end],
        [
          PlayEnd.soClose,
          PlayEnd.ruledOut,
          PlayEnd.certain,
          PlayEnd.passed,
          PlayEnd.soClose,
          PlayEnd.missed,
        ],
      );
      expect(
        [for (final play in plays) play.tone],
        [
          PlayTone.close,
          PlayTone.fail,
          PlayTone.pass,
          PlayTone.pass,
          PlayTone.close,
          PlayTone.fail,
        ],
      );
    });

    test('a check that came up empty, and one the facts settled', () {
      final plays = playsOf(
        const SceneDetails(
          steps: [
            SceneStep(
              text: 'I grab the rope',
              outcomeClass: OutcomeClass.ruledOut,
              beats: [
                SceneBeat(beat: 'Find a rope', thing: 'a rope on the balcony', madeCanon: false),
              ],
            ),
          ],
        ),
      );
      expect(plays.first.end, PlayEnd.notThere);
      expect(plays.first.outcomeClass, OutcomeClass.certain);
      expect(plays.first.sure, isTrue);
    });
  });

  group('the dice of a play', () {
    test('each die wears its color, and a die a 20 threw leaps out of the one before', () {
      final play = playsOf(
        SceneDetails(
          steps: [
            SceneStep(
              text: 'I leap',
              outcomeClass: OutcomeClass.contested,
              roll: _roll(
                _throw(
                  [
                    (DieKind.plain, 18),
                    (DieKind.green, 19),
                    (DieKind.violet, 20),
                    (DieKind.plain, 13),
                  ],
                  number: 27,
                  sprung: {3},
                ),
              ),
            ),
          ],
        ),
      ).single;

      expect(
        [for (final die in play.dice) (die.value, die.skin, die.from)],
        [
          (18, DieSkin.plain, null),
          (19, DieSkin.adv, null),
          (20, DieSkin.insight, null),
          (13, DieSkin.burst, 2),
        ],
      );
      expect(skinOf(DieKind.gold), DieSkin.mastery);
      expect(skinOf(DieKind.grey), DieSkin.world);
      expect(handOf(play.thrown!), 3);
      expect(play.end, PlayEnd.overTheTop);
    });

    test('the die shows the face that fell, also when the gold die counts for more', () {
      final thrown = _throw([(DieKind.plain, 12), (DieKind.gold, 3)], number: 17);
      final play = playsOf(
        SceneDetails(
          steps: [SceneStep(text: 'x', outcomeClass: OutcomeClass.contested, roll: _roll(thrown))],
        ),
      ).single;
      expect(play.dice.last.value, 3);
      expect(thrown.total, 22);
      expect(masteryHeld(thrown), isTrue);
      expect(masteryHeld(attack), isFalse);
    });

    test('a scene always replays the same way, and its throws never look alike in a row', () {
      SceneDetails scene(String seed) => SceneDetails(
        steps: [
          for (var i = 0; i < 4; i++)
            SceneStep(
              text: 'step $i',
              outcomeClass: OutcomeClass.contested,
              roll: _roll(attack, seed: '$seed-$i'),
            ),
        ],
      );
      final once = playsOf(scene('a'));
      final twice = playsOf(scene('a'));
      expect(
        [for (final play in once) (play.seed, play.style, play.entrance, play.cheer)],
        [for (final play in twice) (play.seed, play.style, play.entrance, play.cheer)],
      );
      for (var i = 1; i < once.length; i++) {
        expect(once[i].style, isNot(once[i - 1].style));
        expect(once[i].seed, isNot(once[i - 1].seed));
      }
      // Another scene starts somewhere else in the list of ways.
      final other = playsOf(scene('b'));
      expect(other.first.seed, isNot(once.first.seed));
    });

    test('every way the replay throws a hand is one the dice know', () {
      expect(throwWays, hasLength(20));
      for (final (style, entrance) in throwWays) {
        expect(knownWay(style, entrance), isTrue, reason: '$style, $entrance');
      }
      // All twenty ways to throw and all eight ways for the last die to come in get their turn.
      expect({for (final (style, _) in throwWays) style}, throwStyles.toSet());
      expect({for (final (_, entrance) in throwWays) entrance}, lastDieEntrances.toSet());
      expect(knownWay('spill', 'nowhere'), isFalse);
      expect(cheerCount, 5);
    });
  });

  group('a reason without its throw told twice (A8)', () {
    test("the engine's sentence for a step's throw goes, and what it meant stays", () {
      final thrown = _throw(
        [(DieKind.plain, 12), (DieKind.plain, 9), (DieKind.green, 6), (DieKind.violet, 4)],
        number: 32,
        handWhy: 'Aura blade (skilled), 3 dice',
        greens: ['Coming from behind'],
        madeOf: [
          (text: "the guard's swordplay (skilled), level 3", points: 0),
          (text: 'you are wounded', points: 5),
        ],
      );
      final roll = _roll(thrown);
      expect(roll.oddsLabel, '31 against 32');
      expect(
        whyWithoutThrow(
          'Aura blade (skilled), 3 dice, and a green die for coming from behind, against the '
          "guard's swordplay (skilled), level 3; you are wounded (+5): 31 against 32, so close. "
          'The blade grazes his sleeve.',
          roll,
        ),
        'The blade grazes his sleeve.',
      );
      // With nothing after the throw, nothing is left to say.
      expect(
        whyWithoutThrow(
          'Aura blade (skilled), 3 dice, and a green die for coming from behind, against the '
          "guard's swordplay (skilled), level 3; you are wounded (+5): 31 against 32, so close.",
          roll,
        ),
        '',
      );
    });

    test('what struck back keeps who struck and what it did', () {
      final thrown = _throw(
        [(DieKind.plain, 8), (DieKind.plain, 11)],
        number: 37,
        handWhy: 'Speed, 2 dice',
        madeOf: [(text: "the grey mage's spellcraft (expert), level 4", points: 0)],
      );
      expect(
        whyWithoutThrow(
          "The grey mage strikes back. Speed, 2 dice, against the grey mage's spellcraft "
          '(expert), level 4: 19 against 37, missed. It kills you.',
          _roll(thrown),
        ),
        'The grey mage strikes back. It kills you.',
      );
    });

    test('a hand with no reason of its own, and a part that takes points away', () {
      final thrown = _throw(
        [(DieKind.plain, 15), (DieKind.plain, 14)],
        number: 12,
        handWhy: '',
        madeOf: [(text: 'a good lock, level 2', points: 0), (text: 'the right tools', points: -5)],
      );
      expect(partsTold(thrown.madeOf), 'a good lock, level 2; the right tools (-5)');
      expect(
        whyWithoutThrow(
          '2 dice, against a good lock, level 2; the right tools (-5): 29 against 12, passed. '
          'The lock gives.',
          _roll(thrown),
        ),
        'The lock gives.',
      );
    });

    test('a reason worded another way, or with no throw, is left whole', () {
      const reason = 'The guard never saw it coming.';
      expect(whyWithoutThrow(reason, _roll(attack)), reason);
      expect(whyWithoutThrow('  $reason ', null), reason);
      expect(
        whyWithoutThrow(
          reason,
          const SceneRoll(oddsLabel: 'about even', result: RollResult.success),
        ),
        reason,
      );
    });
  });

  group('what a throw is up against', () {
    ReplayPlay play(SceneThrow thrown, {PlayKind kind = PlayKind.step, String thing = ''}) =>
        ReplayPlay(
          kind: kind,
          step: 1,
          title: 'x',
          outcomeClass: OutcomeClass.contested,
          end: PlayEnd.passed,
          why: '',
          thrown: thrown,
          thing: thing,
        );

    test("the server's sentence, else the thing a check looks for, else the level", () {
      expect(play(attack).facing, 'The guard has trained with a sword for years.');
      final bare = _throw([(DieKind.grey, 14)], number: 11, handWhy: "The world's die");
      expect(
        play(bare, kind: PlayKind.beat, thing: 'a rope in the bell tower').facing,
        'A rope in the bell tower',
      );
      expect(play(bare).facing, "The guard's swordplay (skilled), level 3");
      expect(play(_throw([(DieKind.plain, 3)], number: 7, madeOf: const [])).facing, '');
    });

    test('it rests long enough to be read, and longer when a miss can kill', () {
      final short = play(_throw([(DieKind.plain, 3)], number: 7, against: 'A low wall.'));
      final long = play(
        _throw(
          [(DieKind.plain, 3)],
          number: 7,
          against: 'The masked disciple has trained with a sword since childhood.',
        ),
      );
      final deadly = play(
        _throw(
          [(DieKind.plain, 3)],
          number: 7,
          against: 'The masked disciple has trained with a sword since childhood.',
          deadly: true,
          missCosts: 'A miss can kill.',
        ),
      );
      final endless = play(_throw([(DieKind.plain, 3)], number: 7, against: 'word ' * 200));

      expect(restBefore(short), greaterThan(const Duration(milliseconds: 3700)));
      expect(restBefore(long), greaterThan(restBefore(short)));
      // About six seconds for a sentence, and about two more when it is deadly.
      expect(restBefore(long).inMilliseconds, inInclusiveRange(5200, 6800));
      expect(restBefore(deadly).inMilliseconds, inInclusiveRange(7600, 9600));
      expect(restBefore(deadly), greaterThan(restBefore(long)));
      expect(restBefore(endless), const Duration(milliseconds: 7800));
    });

    test('a result stays long enough for what happened to be read', () {
      ReplayPlay ended(PlayEnd end, String why, {SceneThrow? thrown}) => ReplayPlay(
        kind: PlayKind.step,
        step: 1,
        title: 'x',
        outcomeClass: OutcomeClass.contested,
        end: end,
        why: why,
        thrown: thrown,
      );
      const why = 'The blade grazes his sleeve, and he steps back out of reach of the next one.';
      final thrown = ended(PlayEnd.passed, why, thrown: attack);
      final sure = ended(PlayEnd.certain, why);

      expect(lingerAfter(thrown).inMilliseconds, inInclusiveRange(4500, 6000));
      expect(lingerAfter(sure, verdict: 16).inMilliseconds, inInclusiveRange(4500, 6000));
      expect(lingerAfter(ended(PlayEnd.passed, '', thrown: attack)).inMilliseconds, 3000);
      // A throw over the top stays up a little longer, for its celebration.
      expect(
        lingerAfter(ended(PlayEnd.overTheTop, why, thrown: attack)) - lingerAfter(thrown),
        const Duration(milliseconds: 1200),
      );
      expect(
        lingerAfter(ended(PlayEnd.passed, 'word ' * 200, thrown: attack)).inMilliseconds,
        6600,
      );
      expect(lingerAfter(ended(PlayEnd.certain, 'word ' * 200)).inMilliseconds, 7000);
    });
  });

  test('the offline mode: every throw it sends replays, with its reason told once', () async {
    final (:api, backend: _, :tokens) = fakeApi();
    final json =
        await api.post('/v1/auth/login', {
              'email': FakeAuthState.demoEmail,
              'password': FakeAuthState.demoPassword,
            }, authenticated: false)
            as JsonMap;
    tokens.accessToken = json['access_token'] as String;
    final stories = StoryRepository(api);
    final ends = <PlayEnd>{};
    final kinds = <DieKind>{};
    for (final words in [
      'I duel the masked disciple from behind',
      'I leap across the gap',
      'I climb down a rope from the bell tower',
      'I open the door, then slip past the guard',
      'I attack the masked disciple',
      'I look around',
      'I leap across the gap',
      'I try to fly over the wall',
    ]) {
      final story = await stories.get('story_ninth_peak');
      final events = await (await stories.takeTurn(
        story.id,
        TurnInput.action(words, inputMode: 'typed'),
        expectedVersion: story.version,
      )).toList();
      final details = SceneDetails.fromJson(events.whereType<StepsDecided>().single.details);
      final plays = playsOf(details);
      final rolls = [
        for (final step in details.steps) ...[
          for (final beat in step.beats) beat.roll,
          step.roll,
          for (final struck in step.struck) struck.roll,
        ],
      ];
      expect(plays, hasLength(rolls.length), reason: words);
      for (final (i, play) in plays.indexed) {
        ends.add(play.end);
        final thrown = play.thrown;
        if (thrown == null) continue;
        kinds.addAll(thrown.dice.map((die) => die.kind));
        expect(knownWay(play.style, play.entrance), isTrue);
        expect(play.facing, isNotEmpty, reason: words);
        // The dice say the total and the number: the words under them don't say it again.
        expect(play.why, isNot(contains(rolls[i]!.oddsLabel)), reason: play.why);
        expect(play.why, isNot(contains(' dice, against ')), reason: play.why);
      }
    }
    // Everything a throw or the facts can end in. What strikes back there always throws.
    expect(
      ends,
      containsAll([
        PlayEnd.overTheTop,
        PlayEnd.passed,
        PlayEnd.soClose,
        PlayEnd.missed,
        PlayEnd.certain,
        PlayEnd.ruledOut,
        PlayEnd.there,
      ]),
    );
    expect(kinds, DieKind.values.toSet());
  });
}
