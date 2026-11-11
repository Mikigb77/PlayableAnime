import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import '../../../core/l10n.dart';
import '../../../design/design.dart';
import '../scene_view.dart';
import '../story_models.dart';
import 'replay_card.dart';
import 'replay_controller.dart';
import 'replay_plays.dart';

/// "How it played out" (S15, A8): the scene's steps one at a time, each with the throw that
/// decided it or the tick of a step the facts settled, then the whole turn as a list with its
/// time (W10), its chain of cause and effect (A9) and where a plan stopped (R6).
Future<void> showSceneReplay(BuildContext context, Scene scene) {
  final l10n = context.l10n;
  return showReplay(
    context,
    plays: playsOf(scene.details, stepText: (step) => scene.stepText(step, l10n)),
    chain: scene.details.chain,
    time: [
      scene.durationLabel,
      scene.timeLabel,
      scene.personalTimeLabel,
    ].nonNulls.where((label) => label.isNotEmpty).join(' · '),
  );
}

/// Opens the replay over the page. With [own] it opened by itself before the story's text (gamer
/// mode): it plays through and closes by itself. The future completes when it is closed.
Future<void> showReplay(
  BuildContext context, {
  required List<ReplayPlay> plays,
  bool own = false,
  List<ChainLink> chain = const [],
  String time = '',
}) {
  return Navigator.of(context).push<void>(
    PageRouteBuilder<void>(
      opaque: false,
      settings: const RouteSettings(name: 'replay'),
      transitionDuration: Motion.of(context, const Duration(milliseconds: 300)),
      reverseTransitionDuration: Motion.of(context, Motion.slow),
      pageBuilder: (context, _, _) =>
          ReplayScreen(plays: plays, own: own, chain: chain, time: time),
      transitionsBuilder: (context, animation, _, child) =>
          FadeTransition(opacity: animation, child: child),
    ),
  );
}

/// The replay (S15). A step appears only when its turn comes, so nothing says what is coming
/// next. While it plays it is the one thing to look at: large in the middle of the screen, over
/// the list, which dims behind it. When it is done it goes down to its place in the list as a
/// row, and a row can be tapped to open that step again as it ended.
///
/// A tap anywhere moves it on: it throws dice that are still waiting, shows a result that is
/// still being counted, and goes on from a result that is being read. Skip gives every result at
/// once.
class ReplayScreen extends StatefulWidget {
  const ReplayScreen({
    super.key,
    required this.plays,
    this.own = false,
    this.chain = const [],
    this.time = '',
  });

  final List<ReplayPlay> plays;

  /// It opened by itself before the text, and closes by itself when it has played.
  final bool own;

  /// The scene's cause-and-effect chain (A9) and its time (W10), shown under the list.
  final List<ChainLink> chain;
  final String time;

  @override
  State<ReplayScreen> createState() => _ReplayScreenState();
}

class _ReplayScreenState extends State<ReplayScreen> with TickerProviderStateMixin {
  late final ReplayController _replay;
  final _rowKeys = <int, GlobalKey>{};
  final _landingKey = GlobalKey();
  final _list = ScrollController();
  bool _started = false;

  /// The play open in the list, and whether its "Watch the throw again" is showing.
  (int, bool)? _open;

  @override
  void initState() {
    super.initState();
    _replay = ReplayController(plays: widget.plays, vsync: this, own: widget.own, onDone: _close)
      ..addListener(_changed);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final l10n = context.l10n;
    _replay
      ..reduced = Motion.reduced(context)
      ..verdictLength = (play) => verdictOf(l10n, play).length;
    if (_started) return;
    _started = true;
    // After the first frame, so the tray's size on this screen is known before any throw.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _replay.start();
    });
  }

  @override
  void dispose() {
    _replay
      ..removeListener(_changed)
      ..dispose();
    _list.dispose();
    super.dispose();
  }

  void _changed() {
    if (!mounted) return;
    setState(() {});
    // A step opened again in the list, or grown by its "Watch the throw again", is brought
    // into view.
    final stage = _replay.stage;
    final open = stage != null && !stage.staged ? (stage.index, stage.again) : null;
    if (open == _open) return;
    _open = open;
    if (open != null) _reveal(open.$1);
  }

  /// Scrolls the list so the card opened in it shows: its end first, then its start, so a card
  /// taller than the list is read from its top.
  void _reveal(int index) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_list.hasClients) return;
      final card = _rowKeys[index]?.currentContext?.findRenderObject();
      if (card == null || !card.attached) return;
      final viewport = RenderAbstractViewport.maybeOf(card);
      if (viewport == null) return;
      final position = _list.position;
      var to = math.max(position.pixels, viewport.getOffsetToReveal(card, 1).offset);
      to = math.min(to, viewport.getOffsetToReveal(card, 0).offset);
      to = to.clamp(position.minScrollExtent, position.maxScrollExtent);
      if ((to - position.pixels).abs() < 1) return;
      if (Motion.reduced(context)) {
        _list.jumpTo(to);
      } else {
        unawaited(_list.animateTo(to, duration: Motion.base, curve: Motion.standard));
      }
    });
  }

  void _close() {
    if (!mounted) return;
    final route = ModalRoute.of(context);
    if (route == null || !route.isActive) return;
    if (route.isCurrent) {
      Navigator.of(context).pop();
    } else {
      Navigator.of(context).removeRoute(route);
    }
  }

  GlobalKey _rowKey(int index) => _rowKeys.putIfAbsent(index, GlobalKey.new);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final reduced = Motion.reduced(context);
    final stage = _replay.stage;
    final staged = stage != null && stage.staged;
    final title = widget.own ? l10n.replayTitleOwn : l10n.sceneDetails;

    return Semantics(
      scopesRoute: true,
      namesRoute: true,
      explicitChildNodes: true,
      label: title,
      child: Material(
        type: MaterialType.transparency,
        child: Stack(
          children: [
            // A plain dark table with nothing showing through. Glass would have to blur the
            // whole page again for every frame the dice move.
            const Positioned.fill(child: ColoredBox(color: ReplayInk.veil)),
            SafeArea(
              child: GestureDetector(
                key: const ValueKey('replay.screen'),
                behavior: HitTestBehavior.opaque,
                onTap: _replay.hurry,
                child: LayoutBuilder(
                  builder: (context, box) {
                    final width = math.min(box.maxWidth - 28, 430.0);
                    // The card's padding and edge come off its width.
                    _replay.traySize = Size(math.max(120, width - 34), 158);
                    return Stack(
                      children: [
                        Column(
                          children: [
                            _Head(
                              title: title,
                              // Before the story's text, Skip goes straight to the text.
                              onSkip: !_replay.canSkip
                                  ? null
                                  : _replay.own
                                  ? _close
                                  : _replay.skip,
                              width: width,
                            ),
                            Expanded(
                              child: AnimatedOpacity(
                                opacity: _replay.focus ? 0.3 : 1,
                                duration: Motion.of(context, const Duration(milliseconds: 500)),
                                child: IgnorePointer(
                                  ignoring: _replay.focus,
                                  child: _body(context, width, reduced),
                                ),
                              ),
                            ),
                            if (_replay.showFoot)
                              _Foot(onAgain: _replay.start, onBack: _close, width: width),
                          ],
                        ),
                        if (staged)
                          Positioned.fill(
                            top: _Head.height,
                            child: _Stage(
                              key: ValueKey('replay.stage.${stage.index}.${stage.mode.name}'),
                              stage: stage,
                              width: width,
                              reduced: reduced,
                              // It comes up out of its place in the list, and goes back down
                              // into its row.
                              target: stage.leaving ? _rowKey(stage.index) : _landingKey,
                            ),
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The plays that have played, each as a row, and the one opened again as its card. The rest
  /// have nothing in the list, so it never says what is coming.
  Widget _body(BuildContext context, double width, bool reduced) {
    final l10n = context.l10n;
    final stage = _replay.stage;
    final children = <Widget>[];
    for (var i = 0; i < _replay.seen; i++) {
      final play = widget.plays[i];
      final open = stage != null && stage.index == i;
      if (open && stage.staged && !stage.leaving) {
        // It has the stage, and comes back to this place.
        children.add(SizedBox(key: i == _replay.seen - 1 ? _landingKey : null, height: 0));
        continue;
      }
      if (open && !stage.staged) {
        children.add(
          Padding(
            key: _rowKey(i),
            padding: const EdgeInsets.only(bottom: 8),
            child: ReplayCard(
              key: ValueKey('replay.open.$i'),
              stage: stage,
              reduced: reduced,
              onFold: () => _replay.goTo(i),
              onWatchAgain: play.sure ? null : () => _replay.watch(i),
            ),
          ),
        );
      } else {
        children.add(
          Padding(
            key: _rowKey(i),
            padding: const EdgeInsets.only(bottom: 8),
            child: _PlayRow(
              key: ValueKey('replay.row.$i'),
              play: play,
              landed: _replay.landed == i && !reduced,
              onTap: () => _replay.goTo(i),
            ),
          ),
        );
      }
      if (play.stoppedHere) children.add(const _Stopped());
    }
    // Where the next play's row will lie, for the card on the stage to come up out of.
    if (stage == null || stage.index >= _replay.seen) {
      children.add(SizedBox(key: _landingKey, height: 0));
    }
    if (_replay.canGoOn) {
      children.add(
        Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Center(
            child: ReplayButton(
              key: const ValueKey('replay.more'),
              label: l10n.replayGoOn,
              onPressed: _replay.goOn,
            ),
          ),
        ),
      );
    }
    if (_replay.done && !_replay.auto) {
      children.add(_Tail(chain: widget.chain, time: widget.time));
    }
    return SingleChildScrollView(
      controller: _list,
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 18),
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: width),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
        ),
      ),
    );
  }
}

class _Head extends StatelessWidget {
  const _Head({required this.title, required this.onSkip, required this.width});

  static const height = 62.0;

  final String title;
  final VoidCallback? onSkip;
  final double width;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: width + 28),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 8, 14, 8),
            child: Row(
              children: [
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: Fonts.serif,
                        fontWeight: FontWeight.w500,
                        fontSize: 19,
                        color: ReplayInk.text,
                      ),
                    ),
                  ),
                ),
                if (onSkip != null)
                  ReplayButton(
                    key: const ValueKey('replay.skip'),
                    label: context.l10n.replaySkip,
                    onPressed: onSkip!,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Foot extends StatelessWidget {
  const _Foot({required this.onAgain, required this.onBack, required this.width});

  final VoidCallback onAgain;
  final VoidCallback onBack;
  final double width;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
      child: Wrap(
        alignment: WrapAlignment.center,
        spacing: 10,
        runSpacing: 8,
        children: [
          ReplayButton(
            key: const ValueKey('replay.again'),
            label: l10n.replayAgain,
            onPressed: onAgain,
          ),
          ReplayButton(
            key: const ValueKey('replay.back'),
            label: l10n.replayBack,
            onPressed: onBack,
            primary: true,
          ),
        ],
      ),
    );
  }
}

/// The play that is playing, in the middle of what is left of the screen under the heading. On a
/// screen too short for the whole card it scrolls, and follows the card down to its result when
/// the result comes.
class _Stage extends StatefulWidget {
  const _Stage({
    super.key,
    required this.stage,
    required this.width,
    required this.reduced,
    required this.target,
  });

  final PlayStage stage;
  final double width;
  final bool reduced;
  final GlobalKey target;

  @override
  State<_Stage> createState() => _StageState();
}

class _StageState extends State<_Stage> {
  final _scroll = ScrollController();
  bool _ended = false;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _showEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      final end = _scroll.position.maxScrollExtent;
      if (end <= _scroll.position.pixels) return;
      if (widget.reduced) {
        _scroll.jumpTo(end);
      } else {
        _scroll.animateTo(end, duration: Motion.slow, curve: Motion.standard);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final stage = widget.stage;
    final ended = stage.stamp || stage.verdict;
    if (ended && !_ended) _showEnd();
    _ended = ended;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 4, 14, 12),
      child: Center(
        child: SingleChildScrollView(
          controller: _scroll,
          clipBehavior: Clip.none,
          child: _Fly(
            leaving: stage.leaving,
            reduced: widget.reduced,
            target: widget.target,
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: widget.width),
              child: ReplayCard(stage: stage, reduced: widget.reduced),
            ),
          ),
        ),
      ),
    );
  }
}

/// Brings the card up out of its place in the list, growing into the middle of the screen, and
/// takes it back down into its row. With reduced motion it is simply there, and then gone.
class _Fly extends StatefulWidget {
  const _Fly({
    required this.leaving,
    required this.reduced,
    required this.target,
    required this.child,
  });

  final bool leaving;
  final bool reduced;
  final GlobalKey target;
  final Widget child;

  @override
  State<_Fly> createState() => _FlyState();
}

class _FlyState extends State<_Fly> with SingleTickerProviderStateMixin {
  static const _enter = Cubic(0.22, 1, 0.36, 1);
  static const _leave = Cubic(0.5, 0, 0.25, 1);
  static const _small = 0.42;

  late final _fly = AnimationController(vsync: this, duration: const Duration(milliseconds: 680));
  Offset _away = const Offset(0, -60);
  bool _measured = false;
  bool _leaving = false;

  @override
  void initState() {
    super.initState();
    if (widget.reduced) {
      _fly.value = 1;
      _measured = true;
    } else {
      _begin(leaving: false);
    }
  }

  @override
  void didUpdateWidget(_Fly old) {
    super.didUpdateWidget(old);
    if (widget.leaving && !old.leaving && !widget.reduced) _begin(leaving: true);
  }

  @override
  void dispose() {
    _fly.dispose();
    super.dispose();
  }

  /// Measures, once the frame is laid out, how far the card's place in the list is from where
  /// it stands, and sets it moving.
  void _begin({required bool leaving}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final me = context.findRenderObject();
      final to = widget.target.currentContext?.findRenderObject();
      if (me is RenderBox && me.hasSize && to is RenderBox && to.hasSize) {
        final mine = me.localToGlobal(me.size.center(Offset.zero));
        // A place nothing lies in yet is a line: the row will be about this tall.
        final rowHeight = math.max(to.size.height, 52.0);
        final theirs = to.localToGlobal(Offset(to.size.width / 2, rowHeight / 2));
        _away = theirs - mine;
      }
      setState(() {
        _measured = true;
        _leaving = leaving;
      });
      _fly
        ..duration = Duration(milliseconds: leaving ? 520 : 680)
        ..forward(from: 0);
    });
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _fly,
      child: widget.child,
      builder: (context, child) {
        if (!_measured) return Opacity(opacity: 0, child: child);
        final v = _fly.value;
        // How far it is from standing in the middle, from 0 to 1, and how solid it is.
        final (double far, double solid) = _leaving
            ? (
                _leave.transform(v),
                v < 0.45 ? 1 - 0.15 * (v / 0.45) : 0.85 * (1 - (v - 0.45) / 0.55),
              )
            : (1 - _enter.transform(v), (v / 0.45).clamp(0.0, 1.0));
        if (far == 0 && solid == 1) return child!;
        return Transform.translate(
          offset: _away * far,
          child: Transform.scale(
            scale: 1 - (1 - _small) * far,
            child: Opacity(opacity: solid.clamp(0.0, 1.0), child: child),
          ),
        );
      },
    );
  }
}

/// A play that has played, in a line: how it fell, what it was, and its result.
class _PlayRow extends StatelessWidget {
  const _PlayRow({super.key, required this.play, required this.landed, required this.onTap});

  final ReplayPlay play;

  /// The card has just come down into it: it lights once.
  final bool landed;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final thrown = play.thrown;
    final color = ReplayInk.of(play.tone);
    final top = play.tone == PlayTone.top;
    final sub = thrown == null
        ? verdictOf(l10n, play)
        : l10n.replayRolled(thrown.total, thrown.number);
    final row = Material(
      color: ReplayInk.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: ReplayInk.outline),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            children: [
              Container(
                width: 30,
                height: 30,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: top ? null : color.withValues(alpha: 0.13),
                  gradient: top
                      ? const LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [ReplayInk.goldHi, ReplayInk.gold],
                        )
                      : null,
                  border: top ? null : Border.all(color: color.withValues(alpha: 0.45)),
                  boxShadow: [
                    if (top)
                      BoxShadow(color: ReplayInk.gold.withValues(alpha: 0.5), blurRadius: 14),
                  ],
                ),
                child: thrown == null
                    ? Icon(
                        play.tone == PlayTone.fail ? Icons.block_rounded : Icons.check_rounded,
                        size: 16,
                        color: color,
                      )
                    : Text(
                        '${thrown.total}',
                        style: TextStyle(
                          fontFamily: Fonts.sans,
                          fontSize: 12.5,
                          fontWeight: FontWeight.w600,
                          color: top ? const Color(0xFF3A2204) : color,
                        ),
                      ),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      titleOf(play),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: Fonts.serif,
                        fontWeight: FontWeight.w500,
                        fontSize: 14.5,
                        height: 1.3,
                        color: ReplayInk.text,
                      ),
                    ),
                    Text(
                      sub,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: Fonts.sans,
                        fontSize: 12,
                        height: 1.3,
                        color: ReplayInk.text2,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                endLabel(l10n, play.end).toUpperCase(),
                style: TextStyle(
                  fontFamily: Fonts.sans,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.1,
                  color: color,
                ),
              ),
              const SizedBox(width: 4),
              const Icon(Icons.keyboard_arrow_down_rounded, size: 18, color: ReplayInk.text3),
            ],
          ),
        ),
      ),
    );
    if (!landed) return row;
    // It lands with a little light around it, which goes.
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 600),
      curve: const Interval(0.25, 1, curve: Cubic(0.2, 0.8, 0.2, 1)),
      child: row,
      builder: (context, t, child) => Opacity(
        opacity: (t / 0.55).clamp(0.0, 1.0),
        child: Transform.scale(
          scale: 1.05 - 0.05 * t,
          child: DecoratedBox(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(color: ReplayInk.gold.withValues(alpha: 0.34 * (1 - t)), blurRadius: 26),
              ],
            ),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// Where a chained plan stopped (R6): what came after it didn't happen.
class _Stopped extends StatelessWidget {
  const _Stopped();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
      child: Row(
        children: [
          const Icon(Icons.front_hand_outlined, size: 16, color: ReplayInk.goldHi),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              context.l10n.detailsStopped,
              style: const TextStyle(
                fontFamily: Fonts.sans,
                fontSize: 12.5,
                height: 1.4,
                color: ReplayInk.text2,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Under the list, once every result is known: how long the scene took (W10), its chain of cause
/// and effect (A9), and the line that says what is rolled and what isn't (A8).
class _Tail extends StatelessWidget {
  const _Tail({required this.chain, required this.time});

  final List<ChainLink> chain;
  final String time;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    const meta = TextStyle(
      fontFamily: Fonts.sans,
      fontSize: 12.5,
      height: 1.5,
      color: ReplayInk.text3,
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 14, 4, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (time.isNotEmpty) ...[
            Row(
              children: [
                const Icon(Icons.schedule_rounded, size: 15, color: ReplayInk.text2),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(time, style: meta.copyWith(color: ReplayInk.text2)),
                ),
              ],
            ),
            const SizedBox(height: 14),
          ],
          if (chain.isNotEmpty) ...[
            Text(
              l10n.detailsChain.toUpperCase(),
              style: const TextStyle(
                fontFamily: Fonts.sans,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 1.8,
                color: ReplayInk.gold,
              ),
            ),
            const SizedBox(height: 10),
            for (final (i, link) in chain.indexed) _Link(link: link, last: i == chain.length - 1),
            const SizedBox(height: 14),
          ],
          Text(l10n.detailsLegend, style: meta),
        ],
      ),
    );
  }
}

/// One link of a cause-and-effect chain, joined to the next by a line (A9).
class _Link extends StatelessWidget {
  const _Link({required this.link, required this.last});

  final ChainLink link;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final color = switch (link.outcomeClass) {
      OutcomeClass.certain => ReplayInk.jade,
      OutcomeClass.contested => ReplayInk.gold,
      OutcomeClass.longShot => ReplayInk.goldHi,
      OutcomeClass.ruledOut => ReplayInk.miss,
    };
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 22,
            child: Column(
              children: [
                const SizedBox(height: 6),
                Container(
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                if (!last) Expanded(child: Container(width: 2, color: ReplayInk.outline2)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    link.text,
                    style: const TextStyle(
                      fontFamily: Fonts.serif,
                      fontSize: 14.5,
                      height: 1.35,
                      color: ReplayInk.text,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    classLabel(context.l10n, link.outcomeClass).toUpperCase(),
                    style: TextStyle(
                      fontFamily: Fonts.sans,
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 1.2,
                      color: color,
                    ),
                  ),
                  if (link.reason.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      link.reason,
                      style: const TextStyle(
                        fontFamily: Fonts.sans,
                        fontSize: 12.5,
                        height: 1.45,
                        color: ReplayInk.text2,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
