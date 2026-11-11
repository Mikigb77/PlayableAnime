/// What the replay plays (S15): a scene's steps laid out one after another, in the order they
/// happened, each with the throw that decided it or the tick of a step the facts settled. A
/// step's checks come first, then the step, then whatever struck back after it.
///
/// Nothing here decides anything. The dice, the number and the mark are the server's (A3); this
/// only says how to show them: which die wears which color, which of the twenty ways the hand is
/// thrown, and which words of a step's reason the picture already says.
library;

import '../dice/d20.dart';
import '../dice/dice_tray.dart';
import '../dice/throw_sim.dart';
import '../story_models.dart';

/// What a play is: a step of the action, a check the step relied on (R2), or something that
/// struck back after it (N6).
enum PlayKind { step, beat, struck }

/// How a play ended, which is what its row and its stamp say.
enum PlayEnd {
  /// A throw, by its mark.
  overTheTop,
  passed,
  soClose,
  missed,

  /// A step the facts settled.
  certain,
  ruledOut,

  /// A check: the thing was there, or it wasn't.
  there,
  notThere,

  /// What struck back with no throw: it lands, or it can't get through.
  lands,
  held,
}

/// The color a play ends in: gold for over the top, jade for what went well, amber for so close
/// and red for what went badly.
enum PlayTone { top, pass, close, fail }

extension PlayEndTone on PlayEnd {
  PlayTone get tone => switch (this) {
    PlayEnd.overTheTop => PlayTone.top,
    PlayEnd.passed || PlayEnd.certain || PlayEnd.there || PlayEnd.held => PlayTone.pass,
    PlayEnd.soClose => PlayTone.close,
    PlayEnd.missed || PlayEnd.ruledOut || PlayEnd.notThere || PlayEnd.lands => PlayTone.fail,
  };
}

/// One thing the replay shows: a card while it plays and a row once it has.
final class ReplayPlay {
  const ReplayPlay({
    required this.kind,
    required this.step,
    required this.title,
    required this.outcomeClass,
    required this.end,
    required this.why,
    this.thrown,
    this.odds,
    this.rollSeed,
    this.seed = 0,
    this.style = 'spill',
    this.entrance = 'plunge',
    this.cheer = 0,
    this.thing = '',
    this.stoppedHere = false,
  });

  final PlayKind kind;

  /// The number of the step it belongs to, from 1.
  final int step;

  /// The step in the player's words, the check in plain words, or who struck back.
  final String title;
  final OutcomeClass outcomeClass;
  final PlayEnd end;

  /// What happened, in the world's words (A8), without the throw told a second time.
  final String why;

  /// The dice. None when the facts settled it, and on a scene saved before the dice travelled.
  final SceneThrow? thrown;

  /// A roll saved before the dice travelled, in the words that scene kept for it ("about even"):
  /// it was rolled, and there are no dice to show.
  final String? odds;

  /// The roll's seed as the server keeps it, so the same roll can be checked again (A3).
  final String? rollSeed;

  /// How the throw is shown: the seed of its motion, the way the hand is thrown, the way the last
  /// die comes in, and which celebration an over-the-top throw gets.
  final int seed;
  final String style;
  final String entrance;
  final int cheer;

  /// What a check relied on, such as "a rope on the balcony".
  final String thing;

  /// A chained plan stopped after this play (R6): what came after it didn't happen.
  final bool stoppedHere;

  /// Nothing is thrown on the screen: the facts settled it, or its roll kept no dice.
  bool get sure => thrown == null;
  bool get deadly => thrown?.deadly ?? false;
  PlayTone get tone => end.tone;

  /// What a throw is up against, in words to rest on before the dice: the server's sentence, or
  /// for a check the thing it looks for, or what the number starts from.
  String get facing {
    final thrown = this.thrown;
    if (thrown == null) return '';
    final against = thrown.against.trim();
    if (against.isNotEmpty) return against;
    if (kind == PlayKind.beat && thing.trim().isNotEmpty) return _capital(thing.trim());
    return _capital(thrown.madeOf.firstOrNull?.text.trim() ?? '');
  }

  /// The dice as the tray throws them: each die in its color, and a die a 20 threw leaping out
  /// of the die before it.
  List<TrayDie> get dice => [
    for (final (i, die) in (thrown?.dice ?? const <ThrownDie>[]).indexed)
      TrayDie(
        value: die.face,
        skin: die.sprung ? DieSkin.burst : skinOf(die.kind),
        from: die.sprung && i > 0 ? i - 1 : null,
      ),
  ];
}

String _capital(String text) =>
    text.isEmpty ? text : '${text[0].toUpperCase()}${text.substring(1)}';

DieSkin skinOf(DieKind kind) => switch (kind) {
  DieKind.plain => DieSkin.plain,
  DieKind.green => DieSkin.adv,
  DieKind.violet => DieSkin.insight,
  DieKind.gold => DieSkin.mastery,
  DieKind.grey => DieSkin.world,
};

/// The order the throws are shown in, so that each one in a replay looks unlike the one before:
/// a way to throw the hand, and a way for the last die to come in.
const _show = [
  ('spill', 'plunge'),
  ('whirl', 'bank'),
  ('tops', 'strike'),
  ('pop', 'curl'),
  ('skip', 'spin'),
  ('hail', 'hop'),
  ('arc', 'lob'),
  ('push', 'fall'),
  ('break', 'spin'),
  ('ricochet', 'plunge'),
  ('pour', 'hop'),
  ('cross', 'curl'),
  ('clash', 'spin'),
  ('drop', 'fall'),
  ('toss', 'strike'),
  ('slam', 'lob'),
  ('corner', 'bank'),
  ('volley', 'fall'),
  ('lazy', 'plunge'),
  ('sweep', 'curl'),
];

/// The celebrations of an over-the-top throw, in turn.
const cheerCount = 5;

/// A scene's plays in order. [stepText] gives a step's words as the scene shows them (a standing
/// action in the player's language).
List<ReplayPlay> playsOf(SceneDetails details, {String Function(SceneStep step)? stepText}) {
  // One scene always replays the same way, and two scenes rarely alike: where the list of ways
  // starts comes from the scene's own first seed.
  final first = _firstSeed(details);
  final base = first == null ? 0 : seedOf(first);
  final plays = <ReplayPlay>[];
  var throws = 0;

  void add({
    required PlayKind kind,
    required int step,
    required String title,
    required OutcomeClass outcomeClass,
    required PlayEnd end,
    required String reason,
    SceneRoll? roll,
    String thing = '',
  }) {
    final thrown = roll?.thrown;
    final (style, entrance) = _show[(base + throws) % _show.length];
    plays.add(
      ReplayPlay(
        kind: kind,
        step: step,
        title: title,
        outcomeClass: outcomeClass,
        end: end,
        why: whyWithoutThrow(reason, roll),
        thrown: thrown,
        odds: thrown == null && roll != null && roll.oddsLabel.trim().isNotEmpty
            ? roll.oddsLabel.trim()
            : null,
        rollSeed: roll?.seed,
        seed: seedOf('${roll?.seed ?? first ?? ''}/${plays.length}'),
        style: style,
        entrance: entrance,
        cheer: (base + throws) % cheerCount,
        thing: thing,
      ),
    );
    if (thrown != null) throws += 1;
  }

  for (final (i, step) in details.steps.indexed) {
    for (final beat in step.beats) {
      add(
        kind: PlayKind.beat,
        step: i + 1,
        title: beat.beat,
        outcomeClass: beat.roll == null ? OutcomeClass.certain : OutcomeClass.contested,
        end: beat.madeCanon ? PlayEnd.there : PlayEnd.notThere,
        reason: beat.reason,
        roll: beat.roll,
        thing: beat.thing,
      );
    }
    add(
      kind: PlayKind.step,
      step: i + 1,
      title: stepText?.call(step) ?? step.text,
      outcomeClass: step.outcomeClass,
      end: _endOfStep(step),
      reason: step.reason,
      roll: step.roll,
    );
    for (final struck in step.struck) {
      add(
        kind: PlayKind.struck,
        step: i + 1,
        title: struck.by,
        outcomeClass: struck.outcomeClass,
        end: switch (struck.roll?.thrown?.mark) {
          // The throw is the character's own, to get clear: its mark is their side of it.
          final ThrowMark mark => _endOfMark(mark),
          null => struck.harmed ? PlayEnd.lands : PlayEnd.held,
        },
        reason: struck.reason,
        roll: struck.roll,
      );
    }
    if (details.stoppedAtStep == i && plays.isNotEmpty) {
      final last = plays.removeLast();
      plays.add(last._stopped());
    }
  }
  return List.unmodifiable(plays);
}

extension on ReplayPlay {
  ReplayPlay _stopped() => ReplayPlay(
    kind: kind,
    step: step,
    title: title,
    outcomeClass: outcomeClass,
    end: end,
    why: why,
    thrown: thrown,
    odds: odds,
    rollSeed: rollSeed,
    seed: seed,
    style: style,
    entrance: entrance,
    cheer: cheer,
    thing: thing,
    stoppedHere: true,
  );
}

String? _firstSeed(SceneDetails details) {
  for (final step in details.steps) {
    for (final roll in [
      for (final beat in step.beats) beat.roll,
      step.roll,
      for (final struck in step.struck) struck.roll,
    ]) {
      if (roll?.seed case final seed?) return seed;
    }
  }
  return null;
}

PlayEnd _endOfMark(ThrowMark mark) => switch (mark) {
  ThrowMark.overTheTop => PlayEnd.overTheTop,
  ThrowMark.passed => PlayEnd.passed,
  ThrowMark.soClose => PlayEnd.soClose,
  ThrowMark.missed => PlayEnd.missed,
};

PlayEnd _endOfStep(SceneStep step) {
  if (step.roll?.thrown case final thrown?) return _endOfMark(thrown.mark);
  return switch ((step.roll?.result, step.outcomeClass)) {
    // A roll saved before the dice travelled: its result, with no throw to show.
    (RollResult.success, _) => PlayEnd.passed,
    (RollResult.partial, _) => PlayEnd.soClose,
    (RollResult.failure, _) => PlayEnd.missed,
    (null, OutcomeClass.ruledOut) => PlayEnd.ruledOut,
    (null, _) => PlayEnd.certain,
  };
}

const _markWords = {
  ThrowMark.overTheTop: 'over the top',
  ThrowMark.passed: 'passed',
  ThrowMark.soClose: 'so close',
  ThrowMark.missed: 'missed',
};

/// What a number is made of, in the engine's words: the level it starts from, then each thing
/// that moves it with its points, such as "the guard's swordplay (skilled), level 3; you are
/// wounded (+5)".
String partsTold(List<NumberPart> parts) => [
  for (final (i, part) in parts.indexed)
    i == 0 ? part.text : '${part.text} (${part.points >= 0 ? '+' : ''}${part.points})',
].join('; ');

/// A step's [reason] without the sentence that tells its throw (A8). The engine writes the throw
/// into the reason in words: the hand, each green die, what the number is made of, the total and
/// the mark. The replay shows all of that with the dice themselves, so saying it again under
/// them is only noise. What is left is what the throw meant. A reason worded another way is
/// left whole.
String whyWithoutThrow(String reason, SceneRoll? roll) {
  final thrown = roll?.thrown;
  if (thrown == null) return reason.trim();
  final hand = thrown.handWhy.isEmpty ? '${thrown.hand} dice' : thrown.handWhy;
  final greens = [
    for (final green in thrown.greens)
      if (green.isNotEmpty) ', and a green die for ${green[0].toLowerCase()}${green.substring(1)}',
  ].join();
  final told =
      '$hand$greens, against ${partsTold(thrown.madeOf)}: '
      '${roll!.oddsLabel}, ${_markWords[thrown.mark]}';
  final at = reason.toLowerCase().indexOf(told.toLowerCase());
  if (at < 0) return reason.trim();
  var after = reason.substring(at + told.length);
  if (after.startsWith('.')) after = after.substring(1);
  return '${reason.substring(0, at)}$after'.replaceAll(RegExp(r'\s+'), ' ').trim();
}

/// How many dice the hand threw, before any that a 20 threw.
int handOf(SceneThrow thrown) => thrown.dice.where((die) => !die.sprung).length;

/// Whether the throw's last die did its own work: an insight on the violet die, or the gold die
/// holding at ten.
bool masteryHeld(SceneThrow thrown) =>
    thrown.dice.any((die) => die.kind == DieKind.gold && die.face < ThrownDie.goldFloor);

/// How long a throw rests on what it is against before the dice are thrown: long enough to read
/// it, and longer when a miss can kill.
Duration restBefore(ReplayPlay play) {
  final words = play.facing.length + (play.thrown?.missCosts ?? '').length;
  final ms = play.deadly ? 4400 + 50 * words : 3700 + 34 * words;
  return Duration(milliseconds: ms.clamp(0, play.deadly ? 9600 : 7800));
}

/// How long a result stays up to be read before the replay moves on.
Duration lingerAfter(ReplayPlay play, {int verdict = 0}) {
  final ms = play.sure
      ? (2800 + 28 * (verdict + play.why.length)).clamp(0, 7000)
      : (3000 + 26 * play.why.length).clamp(0, 6600) + (play.end == PlayEnd.overTheTop ? 1200 : 0);
  return Duration(milliseconds: ms);
}

/// The tray's own measure, for a hand of [count] dice.
double trayRadius(int count) => dieRadius(count);

/// Every way a hand can be thrown, for the offline mode and the tests to go through.
List<(String, String)> get throwWays => _show;

/// Whether [style] and [entrance] are ways the physics knows.
bool knownWay(String style, String entrance) =>
    throwStyles.contains(style) && lastDieEntrances.contains(entrance);
