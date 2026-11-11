import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/l10n.dart';
import '../../../design/design.dart';
import '../dice/dice_tray.dart';
import '../story_models.dart';
import 'replay_cheers.dart';
import 'replay_controller.dart';
import 'replay_plays.dart';

/// The replay's own colors (S15). It is a dark table whatever the app's theme is, and its
/// colors are the dice's: bone, jade for a green die, violet for the insight die and gold for
/// mastery. A story's accent (S13) doesn't tint it, so a green die always reads as a green die.
abstract final class ReplayInk {
  /// What the replay lies on. It hides the page whole: words showing through, or still being
  /// written behind the dice, would pull the eye from them.
  static const veil = Color(0xFF080A0E);
  static const ink = Color(0xFF0B0D12);
  static const surface = Color(0xFF161A23);
  static const surface2 = Color(0xFF1D2230);
  static const outline = Color(0x1FEDE8DF);
  static const outline2 = Color(0x38EDE8DF);
  static const text = Color(0xFFEDE8DF);
  static const text2 = Color(0xFFB9B3A7);
  static const text3 = Color(0xFF8B8679);
  static const gold = Color(0xFFE3B66B);
  static const goldHi = Color(0xFFF6DFA8);
  static const jade = Color(0xFF7FD1AE);
  static const miss = Color(0xFFEF7A82);
  static const violet = Color(0xFFCDBCFF);

  static Color of(PlayTone tone) => switch (tone) {
    PlayTone.top || PlayTone.close => goldHi,
    PlayTone.pass => jade,
    PlayTone.fail => miss,
  };
}

const _ease = Cubic(0.2, 0.8, 0.2, 1);

/// What a play's result is called, on its row and on its stamp.
String endLabel(AppLocalizations l10n, PlayEnd end) => switch (end) {
  PlayEnd.overTheTop => l10n.replayMarkTop,
  PlayEnd.passed => l10n.replayMarkPassed,
  PlayEnd.soClose => l10n.replayMarkClose,
  PlayEnd.missed => l10n.replayMarkMissed,
  PlayEnd.certain => l10n.replayEndCertain,
  PlayEnd.ruledOut => l10n.classRuledOut,
  PlayEnd.there => l10n.replayEndThere,
  PlayEnd.notThere => l10n.replayEndNotThere,
  PlayEnd.lands => l10n.replayEndLands,
  PlayEnd.held => l10n.replayEndHeld,
};

/// A play with no dice to show, in a line: why it needed no throw, or the odds of a roll saved
/// before the dice travelled.
String verdictOf(AppLocalizations l10n, ReplayPlay play) => switch (play.end) {
  PlayEnd.there => l10n.detailsBeatMadeCanon(play.thing),
  PlayEnd.notThere => l10n.detailsBeatEmpty(play.thing),
  _ when play.odds != null => l10n.detailsOdds(play.odds!),
  PlayEnd.ruledOut => l10n.replayRuledOut,
  PlayEnd.lands => l10n.replayLands,
  PlayEnd.held => l10n.replayHeld,
  _ => l10n.replayCertain,
};

/// A step's class in a word: settled by the facts (certain, ruled out) or open to a throw
/// (contested, long shot).
String classLabel(AppLocalizations l10n, OutcomeClass outcome) => switch (outcome) {
  OutcomeClass.certain => l10n.classCertain,
  OutcomeClass.contested => l10n.classContested,
  OutcomeClass.longShot => l10n.classLongShot,
  OutcomeClass.ruledOut => l10n.classRuledOut,
};

/// The small line over a play's title: which step it is, and what kind of thing.
String eyebrowOf(AppLocalizations l10n, ReplayPlay play) => switch (play.kind) {
  PlayKind.step => l10n.replayStep(play.step),
  PlayKind.beat => l10n.replayCheck(play.step),
  PlayKind.struck => l10n.replayStruck(play.step),
};

/// A play's title as a sentence starts: "the masked disciple" strikes back as "The masked
/// disciple".
String titleOf(ReplayPlay play) {
  final title = play.title.trim();
  if (title.isEmpty) return title;
  return '${title[0].toUpperCase()}${title.substring(1)}';
}

/// One play as a card: a step with the throw that decided it, or the tick of a step the facts
/// settled. It is laid out whole from the start, with the room its result will need, so it never
/// changes size while it is watched.
class ReplayCard extends StatefulWidget {
  const ReplayCard({
    super.key,
    required this.stage,
    required this.reduced,
    this.onTraySize,
    this.onFold,
    this.onWatchAgain,
  });

  final PlayStage stage;
  final bool reduced;

  /// Says how large the tray is on this card, before the dice are thrown on it.
  final ValueChanged<Size>? onTraySize;
  final VoidCallback? onFold;
  final VoidCallback? onWatchAgain;

  @override
  State<ReplayCard> createState() => _ReplayCardState();
}

class _ReplayCardState extends State<ReplayCard> {
  final _trayKey = GlobalKey();
  final _gaugeKey = GlobalKey();
  final _cardKey = GlobalKey();

  @override
  Widget build(BuildContext context) {
    final stage = widget.stage;
    final play = stage.play;
    final l10n = context.l10n;
    final deadly = play.deadly;
    // A throw that could have killed ends in jade when it didn't and in red when it did.
    final spared =
        deadly && stage.stamp && play.tone != PlayTone.fail && play.tone != PlayTone.close;
    final struck = deadly && stage.stamp && play.tone == PlayTone.fail;
    final tint = deadly ? ReplayInk.miss : ReplayInk.gold;
    final (Color edge, double width, Color? glow) = switch (null) {
      _ when stage.topped => (ReplayInk.goldHi.withValues(alpha: 0.85), 1.5, ReplayInk.gold),
      _ when spared => (ReplayInk.jade.withValues(alpha: 0.5), 1.0, ReplayInk.jade),
      _ when struck => (ReplayInk.miss.withValues(alpha: 0.9), 1.5, ReplayInk.miss),
      _ when deadly => (ReplayInk.miss.withValues(alpha: 0.42), 1.0, null),
      _ => (ReplayInk.gold.withValues(alpha: 0.3), 1.0, null),
    };
    final lingering = stage.lingering && stage.mode == PlayMode.run;

    return AnimatedContainer(
      key: _cardKey,
      duration: Motion.of(context, const Duration(milliseconds: 500)),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        color: ReplayInk.surface,
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [ReplayInk.surface2, ReplayInk.surface],
        ),
        border: Border.all(color: edge, width: width),
        boxShadow: [
          if (glow != null) BoxShadow(color: glow.withValues(alpha: 0.24), blurRadius: 44),
          if (stage.staged)
            const BoxShadow(color: Color(0x99000000), blurRadius: 70, offset: Offset(0, 30)),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        children: [
          // A little of the card's color lies over its top, like light from above.
          Positioned.fill(
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    center: const Alignment(0, -1),
                    radius: 1.1,
                    colors: [tint.withValues(alpha: 0.12), tint.withValues(alpha: 0)],
                    stops: const [0, 0.6],
                  ),
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 18, 16, 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _Eyebrow(
                  text: eyebrowOf(l10n, play),
                  color: deadly ? ReplayInk.miss : ReplayInk.gold,
                  hint: lingering ? l10n.replayTapOn : null,
                ),
                const SizedBox(height: 8),
                Padding(
                  // Clear of the button that closes a step opened again.
                  padding: EdgeInsets.symmetric(horizontal: widget.onFold == null ? 0 : 30),
                  child: Text(
                    titleOf(play),
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontFamily: Fonts.serif,
                      fontWeight: FontWeight.w500,
                      fontSize: 21,
                      height: 1.25,
                      color: ReplayInk.text,
                    ),
                  ),
                ),
                if (play.sure) ..._sure(context) else ..._thrown(context),
                if (stage.again && widget.onWatchAgain != null) ...[
                  const SizedBox(height: 12),
                  Center(
                    child: ReplayButton(
                      key: const ValueKey('replay.watch'),
                      label: l10n.replayWatchAgain,
                      onPressed: widget.onWatchAgain!,
                    ),
                  ),
                ],
                // The roll's seed, on a step opened again: under "Watch the throw again", or
                // under a roll that kept no dice.
                if (play.rollSeed case final seed?
                    when stage.again || (play.sure && !stage.staged)) ...[
                  const SizedBox(height: 8),
                  Text(
                    l10n.detailsSeed(seed),
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontFamily: Fonts.sans,
                      fontSize: 11,
                      color: ReplayInk.text3,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (widget.onFold != null)
            Positioned(
              top: 6,
              right: 6,
              child: IconButton(
                key: const ValueKey('replay.fold'),
                tooltip: l10n.replayCloseStep,
                onPressed: widget.onFold,
                icon: const Icon(Icons.keyboard_arrow_up_rounded, size: 20),
                color: ReplayInk.text2,
              ),
            ),
          if (stage.topped && !widget.reduced)
            Positioned.fill(
              child: IgnorePointer(
                child: Cheer(
                  kind: play.cheer,
                  seed: play.seed,
                  cardKey: _cardKey,
                  trayKey: _trayKey,
                  gaugeKey: _gaugeKey,
                ),
              ),
            ),
        ],
      ),
    );
  }

  List<Widget> _sure(BuildContext context) {
    final stage = widget.stage;
    final play = stage.play;
    final l10n = context.l10n;
    final color = ReplayInk.of(play.tone);
    return [
      SizedBox(
        height: 104,
        child: Align(
          alignment: Alignment.bottomCenter,
          child: stage.tick
              // A bar only for what went badly, as on its row: an older roll that partly worked
              // keeps its tick, in amber.
              ? _SureMark(good: play.tone != PlayTone.fail, color: color, reduced: widget.reduced)
              : const SizedBox.square(dimension: 84),
        ),
      ),
      const SizedBox(height: 12),
      _Held(
        shown: stage.verdict,
        child: Text(
          // A roll that kept no dice says how it fell beside its odds, as its row does.
          (play.odds == null
                  ? verdictOf(l10n, play)
                  : '${verdictOf(l10n, play)}  ·  ${endLabel(l10n, play.end)}')
              .toUpperCase(),
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: Fonts.sans,
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.9,
            height: 1.4,
            color: color,
          ),
        ),
      ),
      _Why(text: play.why, shown: stage.why),
    ];
  }

  List<Widget> _thrown(BuildContext context) {
    final stage = widget.stage;
    final play = stage.play;
    final thrown = play.thrown!;
    final l10n = context.l10n;
    final note = _noteOf(l10n, play);
    final faces = [for (final die in thrown.dice) '${die.face}'].join(', ');
    return [
      const SizedBox(height: 12),
      _Facing(
        // A check asks whether a thing is there, as the line over its title already says.
        label: switch (play.kind) {
          _ when play.deadly => l10n.replayDeadly,
          PlayKind.beat => null,
          _ => l10n.replayAgainst,
        },
        text: play.facing,
        costs: thrown.missCosts,
        deadly: play.deadly,
        rest: widget.reduced ? null : stage.rest,
      ),
      const SizedBox(height: 12),
      Wrap(
        alignment: WrapAlignment.center,
        spacing: 6,
        runSpacing: 6,
        children: [
          if (thrown.ofTheWorld)
            _RuleChip(l10n.replayWorldDie)
          else if (thrown.handWhy.isNotEmpty)
            _RuleChip(thrown.handWhy),
          for (final green in thrown.greens) _RuleChip('+1 $green', color: ReplayInk.jade),
          if (thrown.dice.any((die) => die.kind == DieKind.violet))
            _RuleChip(l10n.replayLastInsight, color: ReplayInk.violet)
          else if (thrown.dice.any((die) => die.kind == DieKind.gold))
            _RuleChip(l10n.replayLastMastery, color: ReplayInk.goldHi),
        ],
      ),
      const SizedBox(height: 14),
      LayoutBuilder(
        builder: (context, box) {
          final size = Size(box.maxWidth, 158);
          widget.onTraySize?.call(size);
          return Semantics(
            key: _trayKey,
            image: true,
            label: stage.read >= thrown.dice.length ? l10n.replayDice(faces) : null,
            child: _TrayBox(stage: stage, size: size, reduced: widget.reduced),
          );
        },
      ),
      const SizedBox(height: 26),
      _Gauge(key: _gaugeKey, stage: stage),
      const SizedBox(height: 6),
      _Sum(stage: stage),
      const SizedBox(height: 2),
      ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 19),
        child: _Held(
          shown: stage.note && note != null,
          child: Text(
            note?.$2 ?? '',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: Fonts.sans,
              fontSize: 12.5,
              height: 1.45,
              color: note?.$1 ?? ReplayInk.text2,
            ),
          ),
        ),
      ),
      SizedBox(
        height: 54,
        child: Align(
          alignment: Alignment.bottomCenter,
          child: stage.stamp
              ? _Stamp(
                  label: endLabel(l10n, play.end),
                  tone: play.tone,
                  top: play.end == PlayEnd.overTheTop,
                  reduced: widget.reduced,
                )
              : null,
        ),
      ),
      _Why(text: play.why, shown: stage.why),
    ];
  }

  /// What the throw's own die did, or how far over the top it went, in a line under the sum.
  (Color, String)? _noteOf(AppLocalizations l10n, ReplayPlay play) {
    final thrown = play.thrown!;
    if (play.end == PlayEnd.overTheTop) {
      return (ReplayInk.goldHi, l10n.replayOverTop(thrown.total - thrown.most));
    }
    if (thrown.insight) {
      final face = thrown.dice
          .where((die) => die.kind == DieKind.violet && !die.sprung)
          .firstOrNull
          ?.face;
      if (face != null) return (ReplayInk.violet, l10n.replayInsight(face));
    }
    final gold = thrown.dice.where((die) => die.kind == DieKind.gold).firstOrNull;
    if (gold != null && gold.face < ThrownDie.goldFloor) {
      return (ReplayInk.goldHi, l10n.replayMasteryHolds(gold.face, ThrownDie.goldFloor));
    }
    return null;
  }
}

class _Eyebrow extends StatelessWidget {
  const _Eyebrow({required this.text, required this.color, this.hint});

  final String text;
  final Color color;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: text.toUpperCase()),
          if (hint case final hint?)
            TextSpan(
              text: '   $hint',
              style: const TextStyle(
                color: ReplayInk.text3,
                fontWeight: FontWeight.w500,
                letterSpacing: 0.7,
              ),
            ),
        ],
      ),
      textAlign: TextAlign.center,
      style: TextStyle(
        fontFamily: Fonts.sans,
        fontSize: 11,
        fontWeight: FontWeight.w600,
        letterSpacing: 1.8,
        height: 1.3,
        color: color,
      ),
    );
  }
}

/// Something the card keeps room for and shows when its moment comes.
class _Held extends StatelessWidget {
  const _Held({required this.shown, required this.child});

  final bool shown;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      excluding: !shown,
      child: AnimatedOpacity(
        opacity: shown ? 1 : 0,
        duration: Motion.of(context, const Duration(milliseconds: 450)),
        child: child,
      ),
    );
  }
}

class _Why extends StatelessWidget {
  const _Why({required this.text, required this.shown});

  final String text;
  final bool shown;

  @override
  Widget build(BuildContext context) {
    if (text.isEmpty) return const SizedBox(height: 4);
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 300, minHeight: 39),
          child: _Held(
            shown: shown,
            child: Text(
              text,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontFamily: Fonts.sans,
                fontSize: 13.5,
                height: 1.45,
                color: ReplayInk.text2,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A text button of the replay: an outline pill, or a filled gold one.
class ReplayButton extends StatelessWidget {
  const ReplayButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.primary = false,
  });

  final String label;
  final VoidCallback onPressed;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: primary ? ReplayInk.gold : Colors.transparent,
      shape: StadiumBorder(
        side: primary ? BorderSide.none : const BorderSide(color: ReplayInk.outline2),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 40),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Text(
                    label,
                    style: TextStyle(
                      fontFamily: Fonts.sans,
                      fontSize: 13,
                      fontWeight: primary ? FontWeight.w600 : FontWeight.w500,
                      color: primary ? ReplayInk.ink : ReplayInk.text2,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A step the facts settled: a ring that closes and a tick, or a bar across it when the world
/// ruled it out.
class _SureMark extends StatelessWidget {
  const _SureMark({required this.good, required this.color, required this.reduced});

  final bool good;
  final Color color;
  final bool reduced;

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: reduced ? 1 : 0, end: 1),
      duration: reduced ? Duration.zero : const Duration(milliseconds: 1000),
      builder: (context, t, _) => CustomPaint(
        size: const Size.square(84),
        painter: _SureMarkPainter(t: t, good: good, color: color),
      ),
    );
  }
}

class _SureMarkPainter extends CustomPainter {
  const _SureMarkPainter({required this.t, required this.good, required this.color});

  final double t;
  final bool good;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final centre = size.center(Offset.zero);
    final radius = size.width / 2 - 4;
    final faint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..color = color.withValues(alpha: 0.25);
    canvas.drawCircle(centre, radius, faint);
    final line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = color;
    // The ring closes first, from the top, and then the mark is drawn.
    final ring = Curves.ease.transform(((t - 0.15) / 0.6).clamp(0.0, 1.0));
    if (ring > 0) {
      canvas.drawArc(
        Rect.fromCircle(center: centre, radius: radius),
        -math.pi / 2,
        2 * math.pi * ring,
        false,
        line..strokeWidth = 3,
      );
    }
    final mark = Curves.ease.transform(((t - 0.65) / 0.35).clamp(0.0, 1.0));
    if (mark <= 0) return;
    final s = size.width / 84;
    final path = Path();
    if (good) {
      path
        ..moveTo(27 * s, 43 * s)
        ..lineTo(37.5 * s, 53.5 * s)
        ..lineTo(58 * s, 32 * s);
    } else {
      path
        ..moveTo(29 * s, 29 * s)
        ..lineTo(55 * s, 55 * s);
    }
    final measure = path.computeMetrics().first;
    canvas.drawPath(measure.extractPath(0, measure.length * mark), line..strokeWidth = 4.5);
  }

  @override
  bool shouldRepaint(_SureMarkPainter old) => old.t != t || old.good != good || old.color != color;
}

/// What a throw is against, said before any die moves. A throw that can kill says so here, with
/// what a miss costs (N6). While it rests, a line under the words runs out as the throw comes
/// nearer.
class _Facing extends StatelessWidget {
  const _Facing({
    required this.label,
    required this.text,
    required this.costs,
    required this.deadly,
    required this.rest,
  });

  final String? label;
  final String text;
  final String costs;
  final bool deadly;
  final Duration? rest;

  @override
  Widget build(BuildContext context) {
    final color = deadly ? ReplayInk.miss : ReplayInk.gold;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 320),
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
          decoration: BoxDecoration(
            color: deadly ? ReplayInk.miss.withValues(alpha: 0.08) : const Color(0x0BEDE8DF),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: deadly ? ReplayInk.miss.withValues(alpha: 0.36) : ReplayInk.outline2,
            ),
          ),
          child: Column(
            children: [
              if (label case final label?)
                Text(
                  label.toUpperCase(),
                  style: TextStyle(
                    fontFamily: Fonts.sans,
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2.1,
                    color: color,
                  ),
                ),
              if (text.isNotEmpty) ...[
                SizedBox(height: label == null ? 2 : 4),
                Text(
                  text,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: Fonts.serif,
                    fontSize: 14.5,
                    height: 1.42,
                    color: ReplayInk.text,
                  ),
                ),
              ],
              if (costs.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  costs,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontFamily: Fonts.sans,
                    fontSize: 12.5,
                    height: 1.4,
                    color: ReplayInk.miss,
                  ),
                ),
              ],
              const SizedBox(height: 7),
              SizedBox(
                height: 2,
                child: rest == null
                    ? null
                    : TweenAnimationBuilder<double>(
                        key: ValueKey(rest),
                        tween: Tween(begin: 1, end: 0),
                        duration: rest!,
                        builder: (context, left, _) => FractionallySizedBox(
                          alignment: AlignmentDirectional.centerStart,
                          widthFactor: left,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: deadly ? 0.85 : 0.6),
                              borderRadius: BorderRadius.circular(1),
                            ),
                          ),
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// What the hand is made of, in a small pill: the dice by skill, each green die's reason, and
/// what the last die is.
class _RuleChip extends StatelessWidget {
  const _RuleChip(this.text, {this.color});

  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tint = color;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
      decoration: BoxDecoration(
        color: tint?.withValues(alpha: 0.12) ?? const Color(0xBF161A23),
        borderRadius: BorderRadius.circular(Radii.pill),
        border: Border.all(color: tint?.withValues(alpha: 0.4) ?? ReplayInk.outline),
      ),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: Fonts.sans,
          fontSize: 12,
          height: 1.3,
          color: tint ?? ReplayInk.text2,
        ),
      ),
    );
  }
}

/// The tray the dice are thrown on: dark felt in a brass rim. It lies empty until the throw, with
/// a heartbeat when a miss can kill.
class _TrayBox extends StatelessWidget {
  const _TrayBox({required this.stage, required this.size, required this.reduced});

  final PlayStage stage;
  final Size size;
  final bool reduced;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final tray = stage.tray;
    final tag = stage.tag;
    return SizedBox(
      height: size.height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
          gradient: const RadialGradient(
            center: Alignment(0, -0.24),
            radius: 1.3,
            colors: [Color(0xFF1D2740), Color(0xFF111726), Color(0xFF090C14)],
            stops: [0, 0.55, 1],
          ),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(18),
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (tray != null)
                FittedBox(
                  child: SizedBox.fromSize(
                    size: tray.size,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Positioned.fill(
                          child: RepaintBoundary(
                            child: CustomPaint(
                              painter: DiceTrayPainter(
                                tray: tray,
                                clock: stage.clock,
                                still: reduced,
                              ),
                            ),
                          ),
                        ),
                        if (!reduced)
                          for (final flare in stage.flares)
                            Positioned(
                              key: ValueKey('flare.${flare.id}'),
                              left: flare.x,
                              top: flare.y,
                              child: _Flare(kind: flare.kind),
                            ),
                        if (tag != null)
                          _TagOver(
                            tag: tag,
                            width: tray.size.width,
                            text: switch (tag.kind) {
                              FlareKind.twenty => l10n.replayTwenty,
                              _ => l10n.replayCountsAs(tag.face, ThrownDie.goldFloor),
                            },
                          ),
                      ],
                    ),
                  ),
                ),
              // The rim: a hairline, a dark band and a line of brass, drawn over the felt.
              const IgnorePointer(child: CustomPaint(painter: _RimPainter())),
              if (stage.tense) IgnorePointer(child: _Heartbeat(still: reduced)),
              if (stage.tapHint && !reduced)
                Positioned(
                  right: 8,
                  bottom: 7,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0x990B0D12),
                      borderRadius: BorderRadius.circular(Radii.pill),
                      border: Border.all(color: ReplayInk.outline),
                    ),
                    child: Text(
                      l10n.replayTapResult,
                      style: const TextStyle(
                        fontFamily: Fonts.sans,
                        fontSize: 10.5,
                        letterSpacing: 0.6,
                        color: ReplayInk.text2,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RimPainter extends CustomPainter {
  const _RimPainter();

  @override
  void paint(Canvas canvas, Size size) {
    RRect inset(double by) =>
        RRect.fromRectAndRadius((Offset.zero & size).deflate(by), Radius.circular(18 - by));
    // Shade under the rim, deeper at the top, as a tray with walls has.
    canvas
      ..drawRect(
        Offset.zero & size,
        Paint()
          ..shader = const LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [Color(0x80000000), Color(0x00000000), Color(0x00000000), Color(0x47000000)],
            stops: [0, 0.22, 0.86, 1],
          ).createShader(Offset.zero & size),
      )
      ..drawRRect(
        inset(1.5),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 3
          ..color = const Color(0xFF0B0E15),
      )
      ..drawRRect(
        inset(3.5),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1
          ..color = ReplayInk.gold.withValues(alpha: 0.3),
      )
      ..drawRRect(
        inset(0.5),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1
          ..color = const Color(0x29EDE8DF),
      );
  }

  @override
  bool shouldRepaint(_RimPainter old) => false;
}

/// The tray's red edge beating like a heart while a throw that can kill is still to land.
class _Heartbeat extends StatefulWidget {
  const _Heartbeat({required this.still});

  final bool still;

  @override
  State<_Heartbeat> createState() => _HeartbeatState();
}

class _HeartbeatState extends State<_Heartbeat> with SingleTickerProviderStateMixin {
  late final _beat = AnimationController(vsync: this, duration: const Duration(milliseconds: 860));

  @override
  void initState() {
    super.initState();
    if (!widget.still) _beat.repeat();
  }

  @override
  void dispose() {
    _beat.dispose();
    super.dispose();
  }

  /// Two beats and a rest, as a heart goes.
  static double _strength(double t) {
    const stops = [0.0, 0.12, 0.24, 0.36, 0.6, 1.0];
    const levels = [0.25, 1.0, 0.4, 0.9, 0.25, 0.25];
    for (var i = 1; i < stops.length; i++) {
      if (t <= stops[i]) {
        final u = (t - stops[i - 1]) / (stops[i] - stops[i - 1]);
        return levels[i - 1] + (levels[i] - levels[i - 1]) * u;
      }
    }
    return 0.25;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _beat,
      builder: (context, _) =>
          CustomPaint(painter: _HeartbeatPainter(widget.still ? 0.6 : _strength(_beat.value))),
    );
  }
}

class _HeartbeatPainter extends CustomPainter {
  const _HeartbeatPainter(this.strength);

  final double strength;

  @override
  void paint(Canvas canvas, Size size) {
    final box = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(18));
    canvas
      ..drawRRect(
        box.deflate(8),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 30
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 16)
          ..color = const Color(0xFFEF3C50).withValues(alpha: 0.5 * strength),
      )
      ..drawRRect(
        box.deflate(0.75),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = ReplayInk.miss.withValues(alpha: 0.75 * strength),
      );
  }

  @override
  bool shouldRepaint(_HeartbeatPainter old) => old.strength != strength;
}

/// A ring of light that opens from a die and fades.
class _Flare extends StatelessWidget {
  const _Flare({required this.kind});

  final FlareKind kind;

  @override
  Widget build(BuildContext context) {
    final (Color ring, Color glow) = switch (kind) {
      FlareKind.twenty => (const Color(0xFFFFFFFF), const Color(0xFFFFF0C8)),
      FlareKind.insight => (const Color(0xFFDECEFF), const Color(0xFFA082FF)),
      FlareKind.mastery => (const Color(0xFFFFECB4), ReplayInk.gold),
    };
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 750),
      curve: Curves.easeOut,
      builder: (context, t, _) => FractionalTranslation(
        translation: const Offset(-0.5, -0.5),
        child: Opacity(
          opacity: 1 - t,
          child: Transform.scale(
            scale: 1 + 8 * t,
            child: Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: ring, width: 1.5),
                boxShadow: [
                  BoxShadow(color: glow.withValues(alpha: 0.6), blurRadius: 18, spreadRadius: 4),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A few words over a die: above it, or under it when the die lies against the top wall.
class _TagOver extends StatelessWidget {
  const _TagOver({required this.tag, required this.width, required this.text});

  final TrayTag tag;
  final double width;
  final String text;

  @override
  Widget build(BuildContext context) {
    final hot = tag.kind == FlareKind.twenty;
    final under = tag.y - tag.r - 26 < 2;
    return Positioned(
      left: 0,
      right: 0,
      top: under ? tag.y + tag.r + 4 : tag.y - tag.r - 26,
      child: Align(
        alignment: Alignment((2 * tag.x / width - 1).clamp(-0.62, 0.62), 0),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Radii.pill),
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: hot
                  ? const [Color(0xFFFFFFFF), Color(0xFFFFE7B4)]
                  : const [ReplayInk.goldHi, ReplayInk.gold],
            ),
            boxShadow: const [
              BoxShadow(color: Color(0x8C000000), blurRadius: 14, offset: Offset(0, 4)),
            ],
          ),
          child: Text(
            text,
            style: const TextStyle(
              fontFamily: Fonts.sans,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: Color(0xFF3A2204),
            ),
          ),
        ),
      ),
    );
  }
}

/// The color a die adds to the bar and the sum.
Color _dieColor(ThrownDie die) => die.sprung
    ? const Color(0xFFFFFFFF)
    : switch (die.kind) {
        DieKind.plain => ReplayInk.text,
        DieKind.green => ReplayInk.jade,
        DieKind.violet => ReplayInk.violet,
        DieKind.gold => ReplayInk.goldHi,
        DieKind.grey => ReplayInk.text2,
      };

List<Color> _pieceColors(ThrownDie die) => die.sprung
    ? const [Color(0xFFFFFFFF), Color(0xFFFFE9BD)]
    : switch (die.kind) {
        DieKind.plain => const [Color(0xFFF4EFE6), Color(0xFFC9C1B0)],
        DieKind.green => const [Color(0xFFB5EFD8), ReplayInk.jade],
        DieKind.violet => const [Color(0xFFE2D7FF), Color(0xFFA98DF2)],
        DieKind.gold => const [ReplayInk.goldHi, ReplayInk.gold],
        DieKind.grey => const [Color(0xFFC7CCD6), Color(0xFF8D94A3)],
      };

/// The bar the dice fill: each die adds its length in its own color, up to the most the hand
/// could make. A line marks the number it has to reach, with the stretch just short of it
/// hatched, where a throw is so close.
class _Gauge extends StatelessWidget {
  const _Gauge({super.key, required this.stage});

  final PlayStage stage;

  @override
  Widget build(BuildContext context) {
    final thrown = stage.play.thrown!;
    final l10n = context.l10n;
    final most = math.max(1, thrown.most);
    final over = stage.over;
    const small = TextStyle(
      fontFamily: Fonts.sans,
      fontSize: 10.5,
      color: ReplayInk.text3,
      fontFeatures: [FontFeature.tabularFigures()],
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        LayoutBuilder(
          builder: (context, box) {
            final width = box.maxWidth;
            double at(num value) => (width * value / most).clamp(0.0, width);
            final needs = at(thrown.number);
            // Each die read so far is a piece of the bar. Past the most the hand could make
            // the bar is full, and what is over shows on its badge.
            final pieces = <double>[];
            var filled = 0.0;
            for (final (i, die) in thrown.dice.indexed) {
              final value = stage.floored.contains(i) ? die.value : die.face;
              final piece = i < stage.read ? math.min(width * value / most, width - filled) : 0.0;
              pieces.add(piece);
              filled += piece;
            }
            return SizedBox(
              height: 12,
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned.fill(
                    child: AnimatedContainer(
                      duration: Motion.of(context, Motion.slow),
                      decoration: BoxDecoration(
                        color: ReplayInk.ink,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(
                          color: over == null
                              ? ReplayInk.outline2
                              : ReplayInk.goldHi.withValues(alpha: 0.95),
                        ),
                        boxShadow: [
                          if (over != null)
                            BoxShadow(color: ReplayInk.gold.withValues(alpha: 0.6), blurRadius: 18),
                        ],
                      ),
                    ),
                  ),
                  // Just short of the number is so close. The world's die only passes or misses.
                  if (!thrown.ofTheWorld)
                    Positioned(
                      left: at(thrown.number - 5),
                      width: needs - at(thrown.number - 5),
                      top: 0,
                      bottom: 0,
                      child: const CustomPaint(painter: _HatchPainter()),
                    ),
                  Positioned.fill(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      // The pieces grow one after another, and for a moment on the way they can
                      // be a hair wider than the bar: the bar's edge cuts them.
                      child: OverflowBox(
                        alignment: Alignment.centerLeft,
                        minWidth: 0,
                        maxWidth: double.infinity,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            for (final (i, die) in thrown.dice.indexed)
                              AnimatedContainer(
                                duration: Motion.of(context, const Duration(milliseconds: 260)),
                                curve: _ease,
                                width: pieces[i],
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: _pieceColors(die),
                                  ),
                                  border: const Border(right: BorderSide(color: Color(0x8C0B0D12))),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: needs - 1,
                    top: -5,
                    bottom: -5,
                    child: Container(
                      width: 2,
                      decoration: BoxDecoration(
                        color: ReplayInk.text,
                        borderRadius: BorderRadius.circular(1),
                      ),
                    ),
                  ),
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 19,
                    child: Align(
                      alignment: Alignment(
                        (2 * needs / math.max(1, width) - 1).clamp(-0.8, 0.8),
                        0,
                      ),
                      child: Text(
                        l10n.replayNeeds(thrown.number).toUpperCase(),
                        style: const TextStyle(
                          fontFamily: Fonts.sans,
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 0.85,
                          color: ReplayInk.text,
                        ),
                      ),
                    ),
                  ),
                  if (over != null)
                    Positioned(
                      right: -8,
                      bottom: 17,
                      child: Container(
                        key: const ValueKey('replay.spill'),
                        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(Radii.pill),
                          gradient: const LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [Color(0xFFFFF6DC), ReplayInk.gold],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: ReplayInk.goldHi.withValues(alpha: 0.7),
                              blurRadius: 16,
                            ),
                          ],
                        ),
                        child: Text(
                          '+$over',
                          style: const TextStyle(
                            fontFamily: Fonts.sans,
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFF3A2204),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            );
          },
        ),
        const SizedBox(height: 4),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('0', style: small),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Text(
                  partsTold(thrown.madeOf),
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: small,
                ),
              ),
            ),
            Text(l10n.replayAtMost(thrown.most), style: small),
          ],
        ),
      ],
    );
  }
}

class _HatchPainter extends CustomPainter {
  const _HatchPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas
      ..save()
      ..clipRect(Offset.zero & size);
    final line = Paint()
      ..color = ReplayInk.gold.withValues(alpha: 0.34)
      ..strokeWidth = 2;
    for (var x = -size.height; x < size.width + size.height; x += 6) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), line);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_HatchPainter old) => false;
}

/// The dice added up as they are read, each in its color, and then the total against the
/// number.
class _Sum extends StatelessWidget {
  const _Sum({required this.stage});

  final PlayStage stage;

  @override
  Widget build(BuildContext context) {
    final thrown = stage.play.thrown!;
    final long = thrown.dice.length > 5;
    const op = TextStyle(color: ReplayInk.text3);
    final spans = <InlineSpan>[];
    for (final (i, die) in thrown.dice.take(stage.read).indexed) {
      if (i > 0) spans.add(TextSpan(text: long ? ' + ' : '  +  ', style: op));
      final color = _dieColor(die);
      if (stage.floored.contains(i)) {
        spans
          ..add(
            TextSpan(
              text: '${die.face}',
              style: TextStyle(
                fontSize: long ? 12.5 : 14,
                color: ReplayInk.text3,
                decoration: TextDecoration.lineThrough,
                decorationColor: ReplayInk.text3,
              ),
            ),
          )
          ..add(
            TextSpan(
              text: ' ${die.value}',
              style: TextStyle(color: color),
            ),
          );
      } else {
        spans.add(
          TextSpan(
            text: '${die.face}',
            style: TextStyle(
              color: color,
              shadows: die.sprung
                  ? [Shadow(color: ReplayInk.goldHi.withValues(alpha: 0.9), blurRadius: 10)]
                  : null,
            ),
          ),
        );
      }
    }
    if (stage.summed) {
      spans
        ..add(TextSpan(text: long ? ' = ' : '  =  ', style: op))
        ..add(
          TextSpan(
            text: '${thrown.total}',
            style: const TextStyle(fontWeight: FontWeight.w600, color: ReplayInk.goldHi),
          ),
        )
        ..add(
          TextSpan(
            text: '  ${context.l10n.replayVs}  ',
            style: TextStyle(
              fontFamily: Fonts.sans,
              fontSize: long ? 12 : 13,
              color: ReplayInk.text3,
            ),
          ),
        )
        ..add(TextSpan(text: '${thrown.number}'));
    }
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 27),
      child: Text.rich(
        TextSpan(children: spans),
        key: const ValueKey('replay.sum'),
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: Fonts.serif,
          fontSize: long ? 15.5 : 18,
          height: 1.45,
          color: ReplayInk.text,
          fontFeatures: const [FontFeature.tabularFigures(), FontFeature.liningFigures()],
        ),
      ),
    );
  }
}

/// How it fell, stamped on the card at a slant.
class _Stamp extends StatelessWidget {
  const _Stamp({required this.label, required this.tone, required this.top, required this.reduced});

  final String label;
  final PlayTone tone;
  final bool top;
  final bool reduced;

  /// It comes down large, bites, and settles.
  static double _scale(double t) {
    if (t < 0.6) return 2.4 + (0.92 - 2.4) * (t / 0.6);
    if (t < 0.8) return 0.92 + (1.05 - 0.92) * ((t - 0.6) / 0.2);
    return 1.05 + (1 - 1.05) * ((t - 0.8) / 0.2);
  }

  @override
  Widget build(BuildContext context) {
    final color = top ? const Color(0xFFFFF3CF) : ReplayInk.of(tone);
    final stamp = Container(
      key: const ValueKey('replay.stamp'),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      decoration: BoxDecoration(
        color: top ? ReplayInk.gold.withValues(alpha: 0.16) : null,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: top ? ReplayInk.goldHi : color, width: 2),
        boxShadow: [
          if (top) BoxShadow(color: ReplayInk.gold.withValues(alpha: 0.45), blurRadius: 30),
        ],
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          fontFamily: Fonts.sans,
          fontSize: 17,
          height: 1.3,
          fontWeight: FontWeight.w600,
          letterSpacing: 3.4,
          color: color,
          shadows: top
              ? [Shadow(color: ReplayInk.goldHi.withValues(alpha: 0.9), blurRadius: 16)]
              : null,
        ),
      ),
    );
    return Semantics(
      liveRegion: true,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: reduced ? 1 : 0, end: 1),
        duration: reduced ? Duration.zero : const Duration(milliseconds: 420),
        curve: _ease,
        builder: (context, t, child) => Opacity(
          opacity: (t / 0.6).clamp(0.0, 1.0),
          child: Transform.rotate(
            angle: -6 * math.pi / 180,
            child: Transform.scale(scale: _scale(t), child: child),
          ),
        ),
        child: stamp,
      ),
    );
  }
}
