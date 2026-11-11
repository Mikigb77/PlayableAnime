import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/story/replay/replay_cheers.dart';
import 'package:playable_anime/features/story/replay/replay_plays.dart';
import 'package:playable_anime/features/story/replay/replay_view.dart';
import 'package:playable_anime/features/story/story_models.dart';

import '../../helpers.dart';

Finder _key(String name) => find.byKey(ValueKey(name));

SceneRoll _roll(
  String seed,
  List<(DieKind, int)> dice, {
  required int number,
  required String handWhy,
  required String against,
  String level = "the guard's swordplay (skilled), level 3",
  bool deadly = false,
  String missCosts = '',
  Set<int> sprung = const {},
}) {
  final thrown = [
    for (final (i, (kind, face)) in dice.indexed)
      ThrownDie(kind: kind, face: face, sprung: sprung.contains(i)),
  ];
  final hand = thrown.where((die) => !die.sprung).length;
  final total = thrown.fold<int>(0, (sum, die) => sum + die.value);
  final mark = total >= number
      ? (total > 20 * hand ? ThrowMark.overTheTop : ThrowMark.passed)
      : (number - total <= 5 ? ThrowMark.soClose : ThrowMark.missed);
  return SceneRoll(
    oddsLabel: '$total against $number',
    result: mark.reached ? RollResult.success : RollResult.failure,
    seed: seed,
    thrown: SceneThrow(
      dice: thrown,
      hand: hand,
      handWhy: handWhy,
      number: number,
      madeOf: [(text: level, points: 0)],
      total: total,
      most: 20 * hand,
      mark: mark,
      against: against,
      deadly: deadly,
      missCosts: missCosts,
    ),
  );
}

const _door = SceneStep(
  text: 'I open the door',
  outcomeClass: OutcomeClass.certain,
  reason: 'The door was never locked.',
);

/// 12 + 9 + 10 = 31 against 27: passed.
final _strike = SceneStep(
  text: 'I strike the guard',
  outcomeClass: OutcomeClass.contested,
  reason:
      "Sword form (skilled), 3 dice, against the guard's swordplay (skilled), level 3: "
      '31 against 27, passed. The blade finds the gap.',
  roll: _roll(
    'seed-strike',
    [(DieKind.plain, 12), (DieKind.plain, 9), (DieKind.violet, 10)],
    number: 27,
    handWhy: 'Sword form (skilled), 3 dice',
    against: 'The guard has trained with a sword for years.',
  ),
);

/// The guard's answer: 3 and a gold 4 that counts as 10, 13 against 17, so close, and deadly.
final _struckBack = SceneStruck(
  by: 'the guard',
  outcomeClass: OutcomeClass.contested,
  harm: 'wounded',
  reason: 'The guard strikes back. His edge opens your arm.',
  roll: _roll(
    'seed-guard',
    [(DieKind.plain, 3), (DieKind.gold, 4)],
    number: 17,
    handWhy: 'Footwork (practiced), 2 dice',
    against: "The guard's blade comes for your throat.",
    deadly: true,
    missCosts: 'A miss can kill.',
  ),
);

/// A 20 that throws one more: 20 + 13 = 33, more than one die can make.
final _leap = SceneStep(
  text: 'I leap the wall',
  outcomeClass: OutcomeClass.contested,
  reason: 'You clear it with room to spare.',
  roll: _roll(
    'seed-leap',
    [(DieKind.violet, 20), (DieKind.plain, 13)],
    number: 17,
    handWhy: 'Jumping (a new move), 1 die',
    against: 'The wall is twice your height.',
    level: 'a hard jump, level 2',
    sprung: {1},
  ),
);

SceneStep _with(SceneStep step, List<SceneStruck> struck) => SceneStep(
  text: step.text,
  outcomeClass: step.outcomeClass,
  reason: step.reason,
  roll: step.roll,
  struck: struck,
);

List<ReplayPlay> _plays(List<SceneStep> steps, {int? stoppedAt}) =>
    playsOf(SceneDetails(steps: steps, stoppedAtStep: stoppedAt));

/// The door, the strike, the guard's answer and the leap.
List<ReplayPlay> _turn() => _plays([
  _door,
  _with(_strike, [_struckBack]),
  _leap,
]);

/// Lets [ms] go by a frame at a time, so the dice and the timers run as on a phone.
Future<void> _wait(WidgetTester tester, int ms) async {
  for (var left = ms; left > 0; left -= 50) {
    await tester.pump(Duration(milliseconds: math.min(50, left)));
  }
}

Future<void> _tapScreen(WidgetTester tester) async {
  await tester.tapAt(const Offset(30, 300));
  await tester.pump();
}

/// Opens the replay over a page, as the story does, and says whether it has closed.
Future<bool Function()> _open(
  WidgetTester tester,
  List<ReplayPlay> plays, {
  bool own = false,
  bool reduced = false,
  double textScale = 1,
  Size size = const Size(390, 844),
  List<ChainLink> chain = const [],
  String time = '',
}) async {
  usePhone(tester, size: size);
  var closed = false;
  await tester.pumpWidget(
    wrap(
      Builder(
        builder: (context) => Center(
          child: TextButton(
            onPressed: () => showReplay(
              context,
              plays: plays,
              own: own,
              chain: chain,
              time: time,
            ).then((_) => closed = true),
            child: const Text('open'),
          ),
        ),
      ),
      reduceMotion: reduced,
      textScale: textScale,
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 300));
  return () => closed;
}

/// Leaves nothing running when a test ends part of the way through a replay.
Future<void> _leave(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  await tester.pump(const Duration(seconds: 1));
}

/// "How it played out" as a replay (S15): the steps one at a time, each with its dice, and then
/// the whole turn as a list.
void main() {
  late AppLocalizations l10n;
  setUpAll(() async => l10n = await english());

  testWidgets('a step appears only when its turn comes, and then lies in the list', (tester) async {
    await _open(tester, _turn());
    await _wait(tester, 400);

    expect(find.text(l10n.sceneDetails), findsOneWidget);
    expect(_key('replay.stage.0.run'), findsOneWidget);
    expect(find.text('I open the door'), findsOneWidget);
    // Nothing says what is coming: no row, no title and no count of the steps to come.
    expect(find.textContaining('guard'), findsNothing);
    expect(find.textContaining('leap'), findsNothing);
    expect(_key('replay.row.0'), findsNothing);
    expect(_key('replay.row.1'), findsNothing);
    expect(_key('replay.again'), findsNothing);
    expect(_key('replay.skip'), findsOneWidget);

    // A step with no roll shows why, and stays long enough to be read.
    await _wait(tester, 1500);
    expect(find.text(l10n.replayCertain.toUpperCase()), findsOneWidget);
    expect(find.text('The door was never locked.'), findsOneWidget);
    await _wait(tester, 2500);
    expect(_key('replay.stage.0.run'), findsOneWidget);

    // Then it goes down into the list as a row, and the next step takes the stage.
    await _wait(tester, 2700);
    expect(_key('replay.row.0'), findsOneWidget);
    expect(_key('replay.stage.1.run'), findsOneWidget);
    expect(find.text('I strike the guard'), findsOneWidget);
    expect(find.textContaining('leap'), findsNothing);
    await _leave(tester);
  });

  testWidgets('a tap throws the dice, then shows the result, then moves on', (tester) async {
    await _open(tester, _plays([_strike, _door]));
    await _wait(tester, 1000);

    // It rests on what it is against, with the hand it throws, before any die moves.
    expect(find.text(l10n.replayAgainst.toUpperCase()), findsOneWidget);
    expect(find.text('The guard has trained with a sword for years.'), findsOneWidget);
    expect(find.text('Sword form (skilled), 3 dice'), findsOneWidget);
    expect(find.text(l10n.replayNeeds(27).toUpperCase()), findsOneWidget);
    expect(find.text(l10n.replayTapResult), findsNothing);
    expect(_key('replay.stamp'), findsNothing);
    // And it goes on resting: the dice aren't thrown for seconds yet.
    await _wait(tester, 2000);
    expect(find.text(l10n.replayTapResult), findsNothing);

    await _tapScreen(tester);
    expect(find.text(l10n.replayTapResult), findsOneWidget);
    expect(_key('replay.stamp'), findsNothing);

    await _wait(tester, 300);
    await _tapScreen(tester);
    await tester.pump();
    expect(_key('replay.stamp'), findsOneWidget);
    expect(find.text(l10n.replayMarkPassed.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.replayTapResult), findsNothing);
    expect(
      tester.widget<Text>(_key('replay.sum')).textSpan!.toPlainText(),
      '12  +  9  +  10  =  31  ${l10n.replayVs}  27',
    );
    // The dice told the throw: the words under them say only what it meant.
    expect(find.text('The blade finds the gap.'), findsOneWidget);
    expect(find.textContaining('31 against 27'), findsNothing);
    expect(find.bySemanticsLabel(l10n.replayDice('12, 9, 10')), findsOneWidget);
    expect(find.textContaining(l10n.replayTapOn, findRichText: true), findsOneWidget);
    // The result is being read: it doesn't leave by itself yet.
    await _wait(tester, 1500);
    expect(_key('replay.stage.0.run'), findsOneWidget);
    expect(_key('replay.row.0'), findsNothing);

    await _tapScreen(tester);
    await _wait(tester, 900);
    expect(_key('replay.row.0'), findsOneWidget);
    expect(find.text(l10n.replayRolled(31, 27)), findsOneWidget);
    expect(_key('replay.stage.1.run'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('a deadly throw says so and what a miss costs, and the gold die holds at ten', (
    tester,
  ) async {
    await _open(
      tester,
      _plays([
        _with(_door, [_struckBack]),
      ]),
    );
    await _wait(tester, 400);
    // The door first: a tap for its result and a tap to move on.
    await _tapScreen(tester);
    await _wait(tester, 100);
    await _tapScreen(tester);
    await _wait(tester, 1300);

    expect(_key('replay.stage.1.run'), findsOneWidget);
    expect(find.text(l10n.replayStruck(1).toUpperCase()), findsOneWidget);
    expect(find.text('The guard'), findsOneWidget);
    expect(find.text(l10n.replayDeadly.toUpperCase()), findsOneWidget);
    expect(find.text("The guard's blade comes for your throat."), findsOneWidget);
    expect(find.text('A miss can kill.'), findsOneWidget);
    expect(find.text(l10n.replayLastMastery), findsOneWidget);

    await _tapScreen(tester);
    await _wait(tester, 200);
    await _tapScreen(tester);
    await tester.pump();
    expect(find.text(l10n.replayMarkClose.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.replayMasteryHolds(4, 10)), findsOneWidget);
    expect(
      tester.widget<Text>(_key('replay.sum')).textSpan!.toPlainText(),
      '3  +  4 10  =  13  ${l10n.replayVs}  17',
    );
    expect(find.text('The guard strikes back. His edge opens your arm.'), findsOneWidget);
    await _leave(tester);
  });

  testWidgets('Skip gives every result at once, as a list in order', (tester) async {
    final closed = await _open(
      tester,
      _turn(),
      chain: const [ChainLink(text: 'The guard falls back', outcomeClass: OutcomeClass.certain)],
      time: 'A few minutes',
    );
    await _wait(tester, 400);
    await tester.tap(_key('replay.skip'));
    await tester.pump();
    await _wait(tester, 600);

    expect(find.byKey(const ValueKey('replay.stage.0.run')), findsNothing);
    final tops = [for (var i = 0; i < 4; i++) tester.getTopLeft(_key('replay.row.$i')).dy];
    expect(tops, [...tops]..sort());
    expect(find.text('I open the door'), findsOneWidget);
    expect(find.text(l10n.replayCertain), findsOneWidget);
    expect(find.text(l10n.replayRolled(31, 27)), findsOneWidget);
    expect(find.text('The guard'), findsOneWidget);
    expect(find.text(l10n.replayRolled(13, 17)), findsOneWidget);
    expect(find.text(l10n.replayRolled(33, 17)), findsOneWidget);
    expect(find.text(l10n.replayMarkTop.toUpperCase()), findsOneWidget);
    // Under the list: how long it took, the chain, and what is rolled and what isn't.
    expect(find.text('A few minutes'), findsOneWidget);
    expect(find.text('The guard falls back'), findsOneWidget);
    expect(find.text(l10n.detailsLegend), findsOneWidget);
    expect(_key('replay.skip'), findsNothing);
    expect(_key('replay.more'), findsNothing);
    expect(_key('replay.again'), findsOneWidget);

    await tester.tap(_key('replay.back'));
    await _wait(tester, 800);
    expect(closed(), isTrue);
    expect(_key('replay.screen'), findsNothing);
  });

  testWidgets('a played step opens again as it ended, and its throw can be watched again', (
    tester,
  ) async {
    await _open(tester, _turn());
    await _wait(tester, 400);
    await tester.tap(_key('replay.skip'));
    await _wait(tester, 600);

    await tester.tap(_key('replay.row.1'));
    await _wait(tester, 600);
    expect(_key('replay.open.1'), findsOneWidget);
    expect(_key('replay.row.1'), findsNothing);
    expect(_key('replay.row.0'), findsOneWidget);
    expect(_key('replay.stamp'), findsOneWidget);
    expect(find.text('The blade finds the gap.'), findsOneWidget);
    expect(find.text(l10n.detailsSeed('seed-strike')), findsOneWidget);
    expect(_key('replay.watch'), findsOneWidget);

    // Its arrow closes it again.
    await tester.tap(_key('replay.fold'));
    await _wait(tester, 400);
    expect(_key('replay.open.1'), findsNothing);
    expect(_key('replay.row.1'), findsOneWidget);

    // Opening another closes the one that was open. A step with no roll has no throw to watch.
    await tester.tap(_key('replay.row.1'));
    await _wait(tester, 400);
    await tester.ensureVisible(_key('replay.row.0'));
    await tester.pump();
    await tester.tap(_key('replay.row.0'));
    await _wait(tester, 400);
    expect(_key('replay.open.0'), findsOneWidget);
    expect(_key('replay.open.1'), findsNothing);
    expect(_key('replay.watch'), findsNothing);

    await tester.tap(_key('replay.row.1'));
    await _wait(tester, 600);
    await tester.ensureVisible(_key('replay.watch'));
    await tester.pump();
    await tester.tap(_key('replay.watch'));
    await _wait(tester, 400);
    expect(_key('replay.stage.1.again'), findsOneWidget);
    expect(_key('replay.stamp'), findsNothing);
    await _tapScreen(tester);
    await _wait(tester, 200);
    await _tapScreen(tester);
    await tester.pump();
    expect(_key('replay.stamp'), findsOneWidget);
    // It goes back to its place in the list by itself, still open.
    await _wait(tester, 1800);
    expect(_key('replay.stage.1.again'), findsNothing);
    expect(_key('replay.open.1'), findsOneWidget);
    expect(_key('replay.watch'), findsOneWidget);

    // Play again starts from the first step, with nothing of the rest in sight.
    await tester.tap(_key('replay.again'));
    await _wait(tester, 400);
    expect(_key('replay.stage.0.run'), findsOneWidget);
    expect(_key('replay.row.1'), findsNothing);
    expect(find.textContaining('guard'), findsNothing);
    await _leave(tester);
  });

  testWidgets('opening a played step stops the replay, and it offers to go on', (tester) async {
    await _open(tester, _plays([_door, _strike]));
    await _wait(tester, 1600);
    // The first result is up. A tap moves on, and its row is tapped before the next step comes.
    await _tapScreen(tester);
    await _wait(tester, 550);
    await tester.tap(_key('replay.row.0'));
    await _wait(tester, 400);

    expect(_key('replay.open.0'), findsOneWidget);
    expect(_key('replay.stage.1.run'), findsNothing);
    expect(find.text('I strike the guard'), findsNothing);
    expect(_key('replay.skip'), findsOneWidget);
    expect(_key('replay.again'), findsOneWidget);

    await tester.tap(_key('replay.more'));
    await _wait(tester, 400);
    expect(_key('replay.stage.1.run'), findsOneWidget);
    expect(_key('replay.more'), findsNothing);
    await _leave(tester);
  });

  testWidgets('a turn the facts settled plays the same way, and throws nothing', (tester) async {
    const road = SceneStep(
      text: 'I set off down the road',
      outcomeClass: OutcomeClass.certain,
      reason: 'Nothing stands in the way.',
      beats: [
        SceneBeat(
          beat: 'Walk the path',
          thing: 'the road',
          madeCanon: true,
          reason: 'A road runs from the gate to the town.',
        ),
      ],
    );
    await _open(tester, _plays([_door, road]), time: '+5 min · Day 1, morning');
    await _wait(tester, 400);

    // The first step alone, with its tick and why.
    expect(_key('replay.stage.0.run'), findsOneWidget);
    expect(find.textContaining('road'), findsNothing);
    await _wait(tester, 1800);
    expect(find.text(l10n.replayCertain.toUpperCase()), findsOneWidget);
    expect(find.textContaining(l10n.replayTapOn, findRichText: true), findsOneWidget);

    // A tap moves on to what the second step relied on, then to the step itself.
    await _tapScreen(tester);
    await _wait(tester, 2800);
    expect(_key('replay.stage.1.run'), findsOneWidget);
    expect(
      find.textContaining(l10n.replayCheck(2).toUpperCase(), findRichText: true),
      findsOneWidget,
    );
    expect(find.text(l10n.detailsBeatMadeCanon('the road').toUpperCase()), findsOneWidget);
    await _tapScreen(tester);
    await _wait(tester, 2800);
    expect(_key('replay.stage.2.run'), findsOneWidget);
    expect(find.text('I set off down the road'), findsOneWidget);
    await _tapScreen(tester);
    await _wait(tester, 1200);

    // The whole turn as a list, with its time, and no die anywhere in it.
    for (final row in [0, 1, 2]) {
      expect(_key('replay.row.$row'), findsOneWidget);
    }
    expect(find.text(l10n.replayEndCertain.toUpperCase()), findsNWidgets(2));
    expect(find.text(l10n.replayEndThere.toUpperCase()), findsOneWidget);
    expect(find.text('+5 min · Day 1, morning'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('^${l10n.replayDice('')}')), findsNothing);
    expect(_key('replay.again'), findsOneWidget);

    // A row opens with why, and offers no throw to watch.
    await tester.tap(_key('replay.row.2'));
    await _wait(tester, 1600);
    expect(find.text('Nothing stands in the way.'), findsOneWidget);
    expect(_key('replay.watch'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a scene with a chain and no steps opens on the chain (A9)', (tester) async {
    await _open(
      tester,
      const [],
      chain: const [
        ChainLink(
          text: 'The lamp falls into the straw',
          outcomeClass: OutcomeClass.certain,
          reason: 'Dry straw catches at once.',
        ),
      ],
    );
    await _wait(tester, 400);
    expect(find.text('The lamp falls into the straw'), findsOneWidget);
    expect(find.text(l10n.detailsLegend), findsOneWidget);
    expect(_key('replay.skip'), findsNothing);
    expect(_key('replay.back'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a plan that stopped says where (R6)', (tester) async {
    await _open(tester, _plays([_door, _strike], stoppedAt: 0));
    await _wait(tester, 400);
    await tester.tap(_key('replay.skip'));
    await _wait(tester, 400);

    final stopped = tester.getTopLeft(find.text(l10n.detailsStopped)).dy;
    expect(stopped, greaterThan(tester.getTopLeft(_key('replay.row.0')).dy));
    expect(stopped, lessThan(tester.getTopLeft(_key('replay.row.1')).dy));
    await _leave(tester);
  });

  testWidgets('a throw over the top is counted past the bar and celebrated', (tester) async {
    await _open(tester, _plays([_leap]));
    await _wait(tester, 400);
    await _tapScreen(tester);
    await _wait(tester, 200);
    await _tapScreen(tester);
    await tester.pump();
    await _wait(tester, 100);

    expect(find.text(l10n.replayMarkTop.toUpperCase()), findsOneWidget);
    expect(find.descendant(of: _key('replay.spill'), matching: find.text('+13')), findsOneWidget);
    expect(find.text(l10n.replayOverTop(13)), findsOneWidget);
    expect(find.byType(Cheer), findsOneWidget);
    await _wait(tester, 4000);
    await _leave(tester);
  });

  testWidgets('with reduced motion nothing flies or flashes, and the time to read stays', (
    tester,
  ) async {
    await _open(tester, _plays([_leap]), reduced: true);
    await _wait(tester, 3000);

    // Still resting on what it is against, as long as with motion.
    expect(find.text('The wall is twice your height.'), findsOneWidget);
    expect(_key('replay.stamp'), findsNothing);
    expect(tester.widget<Text>(_key('replay.sum')).textSpan!.toPlainText(), isEmpty);

    // Then the dice are simply there, where they came to rest.
    await _wait(tester, 4000);
    expect(find.text(l10n.replayTapResult), findsNothing);
    await _wait(tester, 3000);
    expect(_key('replay.stamp'), findsOneWidget);
    expect(find.text(l10n.replayMarkTop.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.replayOverTop(13)), findsOneWidget);
    expect(find.byType(Cheer), findsNothing);
    expect(find.byKey(const ValueKey('flare.0')), findsNothing);
    await _leave(tester);
  });

  group('before the story (gamer mode)', () {
    testWidgets('it plays through and closes by itself', (tester) async {
      final closed = await _open(tester, _plays([_door]), own: true);
      await _wait(tester, 400);

      expect(find.text(l10n.replayTitleOwn), findsOneWidget);
      expect(find.text(l10n.sceneDetails), findsNothing);
      // The step, its reason for as long as it takes to read, and its row.
      await _wait(tester, 6200);
      expect(_key('replay.row.0'), findsOneWidget);
      expect(closed(), isFalse);
      // It doesn't stop to offer anything: the story is waiting behind it.
      expect(_key('replay.again'), findsNothing);
      expect(_key('replay.back'), findsNothing);

      await _wait(tester, 2400);
      expect(closed(), isTrue);
      expect(_key('replay.screen'), findsNothing);
    });

    testWidgets('Skip goes straight to the story', (tester) async {
      final closed = await _open(tester, _turn(), own: true);
      await _wait(tester, 400);
      await tester.tap(_key('replay.skip'));
      await _wait(tester, 800);

      expect(closed(), isTrue);
      expect(_key('replay.screen'), findsNothing);
    });

    testWidgets('a tap on the last result closes it without the wait', (tester) async {
      final closed = await _open(tester, _plays([_door]), own: true);
      await _wait(tester, 1600);
      await _tapScreen(tester);
      await _wait(tester, 900);
      expect(closed(), isFalse);
      await _tapScreen(tester);
      await _wait(tester, 800);
      expect(closed(), isTrue);
    });
  });

  testWidgets('a small screen with large text shows every step whole', (tester) async {
    await _open(tester, _turn(), size: const Size(360, 640), textScale: 1.3);
    // Tapped through from the first step to the last: any overflow fails the test.
    for (var taps = 0; taps < 40 && _key('replay.back').evaluate().isEmpty; taps++) {
      await _wait(tester, 400);
      await _tapScreen(tester);
    }
    await _wait(tester, 5000);
    expect(_key('replay.back'), findsOneWidget);
    for (var i = 0; i < 4; i++) {
      await tester.ensureVisible(_key('replay.row.$i'));
      await tester.pump();
      await tester.tap(_key('replay.row.$i'));
      await _wait(tester, 800);
      expect(_key('replay.open.$i'), findsOneWidget);
      await tester.tap(_key('replay.fold'));
      await _wait(tester, 400);
    }
    await _leave(tester);
  });
}
