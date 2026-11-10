import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart' show Size;

import '../dice/dice_tray.dart';
import '../story_models.dart';
import 'replay_plays.dart';

/// How a play is on show: [run] while the replay moves through the plays and each closes behind
/// itself, [still] to look at one again as it ended, and [again] to watch its throw once more.
enum PlayMode { run, still, again }

/// Where the play on show stands, which is what a tap means: while a throw rests on what it is
/// against ([hold]) a tap throws the dice, while it plays a tap shows the result, and while the
/// result lingers a tap moves on.
enum ReplayPhase { none, hold, playing, linger, leaving }

/// A ring of light on the tray, where a die did something: a 20 that throws one more die, an
/// insight, or mastery holding at ten.
enum FlareKind { twenty, insight, mastery }

typedef TrayFlare = ({int id, FlareKind kind, double x, double y});

/// A few words over a die on the tray: "A 20 throws one more", or "4 counts as 10".
typedef TrayTag = ({FlareKind kind, int face, double x, double y, double r});

/// The play on show, as far as it has got. The view draws exactly this.
class PlayStage {
  PlayStage({required this.index, required this.play, required this.mode, required this.staged});

  final int index;
  final ReplayPlay play;
  final PlayMode mode;

  /// Large in the middle of the screen, over the list. Otherwise it is open in its place in the
  /// list.
  bool staged;

  /// Going back down into the list as a row.
  bool leaving = false;

  // A play with no throw.
  bool tick = false;
  bool verdict = false;

  // A throw.

  /// How long it rests on what it is against, while it does: the line under the words runs out.
  Duration? rest;

  /// A miss can kill, and the dice aren't down yet.
  bool tense = false;
  DiceTray? tray;
  final clock = TrayClock();

  /// The dice are in the air: a tap shows the result.
  bool tapHint = false;

  /// How many dice have been read into the bar and the sum.
  int read = 0;

  /// The dice whose number was lifted to the gold die's floor.
  final floored = <int>{};

  /// How far past the most the hand could make the dice have run, once they have.
  int? over;
  bool summed = false;
  bool note = false;
  bool stamp = false;
  bool topped = false;
  bool why = false;

  /// The result is up, and a tap goes on.
  bool lingering = false;

  /// "Watch the throw again" is offered.
  bool again = false;
  final flares = <TrayFlare>[];
  TrayTag? tag;
}

class _Stopped implements Exception {
  const _Stopped();
}

/// Plays a turn's steps one at a time (S15), as the prototype does it. A step appears only when
/// its turn comes, so nothing says what is coming. While it plays it is the one thing to look at.
/// When it is done it goes down into the list as a row, and a row can be tapped to open that step
/// again as it ended.
///
/// Every throw first says what it is against and rests on that long enough to be read, longer
/// when a miss can kill, and then the dice are thrown by themselves. The dice only show what the
/// server decided (A3): nothing here rolls.
class ReplayController extends ChangeNotifier {
  ReplayController({
    required this.plays,
    required TickerProvider vsync,
    this.own = false,
    this.reduced = false,
    this.onDone,
  }) {
    _ticker = vsync.createTicker(_onTick);
  }

  final List<ReplayPlay> plays;

  /// Reduced motion: the dice appear where they came to rest and nothing flies. The time given
  /// to read stays.
  bool reduced;

  /// The replay opened by itself before the story's text and has played to its end (gamer mode):
  /// the host closes it and shows the text.
  final VoidCallback? onDone;

  /// The tray's size on the card, which the view measures before a throw.
  Size traySize = const Size(326, 158);

  /// How long the words of a sure step's verdict are, for the time it stays up.
  int Function(ReplayPlay play)? verdictLength;

  late final Ticker _ticker;
  bool _disposed = false;

  // `_run` ends everything in flight when it changes. `_fast` hurries the play on show to its
  // result, `_skipAll` hurries every play, and `_eager` says the player tapped while a throw was
  // still resting: the dice are thrown at once.
  int _run = 0;
  bool _fast = false;
  bool _skipAll = false;
  bool _eager = false;
  Completer<void>? _waiting;
  Timer? _timer;
  ({int ms, void Function(double gone) paint, Completer<void> done})? _motion;
  int _flares = 0;

  /// How many plays, from the first, have shown their result.
  int get seen => _seen;
  int _seen = 0;

  /// The play on show, if one is.
  PlayStage? get stage => _stage;
  PlayStage? _stage;

  /// The replay is moving through the plays by itself.
  bool get auto => _auto;
  bool _auto = false;

  /// It opened by itself before the text and will close by itself too, until the player takes
  /// it over by opening a step.
  bool own;

  ReplayPhase get phase => _phase;
  ReplayPhase _phase = ReplayPhase.none;

  /// The row that the play on show has just come down into, for the list to light it once.
  int get landed => _landed;
  int _landed = -1;

  /// A play has the stage: the list dims behind it.
  bool get focus => _stage != null && _stage!.staged && !_stage!.leaving;

  bool get done => _seen >= plays.length;

  /// Skip is offered until every result is known.
  bool get canSkip => !done;

  /// Stopped part of the way, the replay offers to go on.
  bool get canGoOn => !_auto && !own && !done;

  /// Play again and Back to the story, once it isn't moving by itself.
  bool get showFoot => !_auto && !own;

  // ---- What the player can do ---------------------------------------------------------------

  /// Plays from the first step.
  void start() {
    _stop();
    _seen = 0;
    _landed = -1;
    _lay();
    _spawn((mine) => _runFrom(0, mine));
  }

  /// A tap on a play that has played: it opens as it ended, or closes if it was the one open,
  /// and the replay stops moving by itself.
  void goTo(int index) {
    if (index < 0 || index >= _seen) return;
    final was = _stage?.index == index && !(_stage?.staged ?? false);
    _stop();
    _auto = false;
    own = false;
    _lay();
    notifyListeners();
    if (!was) _spawn((mine) => _playStep(index, mine, PlayMode.still));
  }

  /// Goes on from the first play that hasn't played.
  void goOn() {
    _stop();
    own = false;
    _lay();
    _spawn((mine) => _runFrom(_seen, mine));
  }

  /// Watches one play's throw once more.
  void watch(int index) {
    if (index < 0 || index >= plays.length) return;
    _stop();
    _auto = false;
    own = false;
    _lay();
    notifyListeners();
    _spawn((mine) => _playStep(index, mine, PlayMode.again));
  }

  /// A tap anywhere: while a throw rests on what it is against it only throws the dice, while it
  /// plays it shows the result, and once the result is up it moves on.
  void hurry() {
    switch (_phase) {
      case ReplayPhase.hold:
        _eager = true;
        _wake();
      case ReplayPhase.playing:
        _fast = true;
        _wake();
        _finishMotion();
      case ReplayPhase.linger:
        _wake();
      case ReplayPhase.none || ReplayPhase.leaving:
        break;
    }
  }

  /// Skip: every result at once, as a list.
  void skip() {
    if (_auto) {
      _skipAll = true;
      _wake();
      _finishMotion();
      return;
    }
    _stop();
    _seen = plays.length;
    _lay();
    notifyListeners();
  }

  // ---- The plays ----------------------------------------------------------------------------

  void _spawn(Future<void> Function(int mine) body) {
    final mine = _run;
    unawaited(
      body(mine).catchError((Object _) {
        // Replayed, jumped or closed: whoever did it has laid the list out again.
      }, test: (error) => error is _Stopped),
    );
  }

  void _stop() {
    _run += 1;
    _fast = false;
    _skipAll = false;
    _eager = false;
    _phase = ReplayPhase.none;
    _wake();
    _endMotion();
  }

  /// The plays that have played, each as a row, with no card open.
  void _lay() {
    _stage = null;
  }

  void _known(int index) {
    _seen = math.max(_seen, index + 1);
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> _runFrom(int start, int mine) async {
    _auto = true;
    _changed();
    for (var i = start; i < plays.length; i++) {
      await _playStep(i, mine, PlayMode.run);
    }
    _auto = false;
    _fast = false;
    _skipAll = false;
    _phase = own ? ReplayPhase.linger : ReplayPhase.none;
    _changed();
    if (!own) return;
    // In gamer mode it gives way to the story's text when it is done.
    await _wait(1500, mine);
    _phase = ReplayPhase.none;
    own = false;
    _changed();
    onDone?.call();
  }

  Future<void> _playStep(int index, int mine, PlayMode mode) async {
    final play = plays[index];
    if (_skipAll && mode == PlayMode.run) {
      _known(index);
      _landed = -1;
      _changed();
      return;
    }
    // From the moment a throw comes up until its dice are thrown, a tap only throws them sooner.
    _fast = mode == PlayMode.still;
    _eager = false;
    _phase = play.sure ? ReplayPhase.playing : ReplayPhase.hold;
    // A play that is playing takes the stage. One opened to look at again stays in the list.
    final staged = mode != PlayMode.still;
    final stage = _stage = PlayStage(index: index, play: play, mode: mode, staged: staged);
    _landed = -1;
    _changed();
    await _wait(staged ? 760 : 300, mine);

    if (play.sure) {
      stage.tick = true;
      _changed();
      await _wait(900, mine);
      stage
        ..verdict = true
        ..why = true;
      _known(index);
      _changed();
      if (mode != PlayMode.run) {
        _fast = false;
        _phase = ReplayPhase.none;
        if (staged) await _home(stage, mine);
        return;
      }
      _fast = false;
      _phase = ReplayPhase.linger;
      stage.lingering = true;
      _changed();
      // A step with no roll stays long enough for its reason to be read.
      final verdict = verdictLength?.call(play) ?? 0;
      await _wait(lingerAfter(play, verdict: verdict).inMilliseconds, mine);
    } else {
      await _throw(stage, mine);
      if (mode != PlayMode.run) {
        _fast = false;
        _phase = ReplayPhase.none;
        if (staged) {
          await _wait(1500, mine);
          await _home(stage, mine);
        }
        stage.again = true;
        _changed();
        return;
      }
      _fast = false;
      _phase = ReplayPhase.linger;
      stage.lingering = true;
      _changed();
      // And a result stays long enough for what happened to be read.
      await _wait(lingerAfter(play).inMilliseconds, mine);
    }

    // It goes back down into the list as a row.
    _phase = ReplayPhase.leaving;
    stage.leaving = true;
    _landed = index;
    _changed();
    await _wait(reduced ? 0 : 500, mine);
    _stage = null;
    _changed();
    await _wait(300, mine);
  }

  /// A play the player asked to watch again goes back to its place in the list as it stands.
  Future<void> _home(PlayStage stage, int mine) async {
    stage.staged = false;
    _changed();
    await _wait(0, mine);
  }

  /// One throw: what it is against, the dice, each die read into the bar and the sum, the total
  /// against the number, and the stamp.
  Future<void> _throw(PlayStage stage, int mine) async {
    final play = stage.play;
    final thrown = play.thrown!;
    final index = stage.index;
    // The tray lies empty while what it is against is read, with its heartbeat when a miss can
    // kill, and a line under the words runs out as the throw comes nearer. Then the dice are
    // thrown without being asked. A tap throws them sooner.
    final rest = restBefore(play);
    stage.tense = play.deadly;
    if (!_fast) stage.rest = rest;
    _changed();
    if (!_eager) await _wait(rest.inMilliseconds, mine);
    if (mine != _run) throw const _Stopped();
    _phase = ReplayPhase.playing;
    stage.rest = null;
    final tray = stage.tray = DiceTray(
      dice: play.dice,
      seed: play.seed,
      size: traySize,
      style: play.style,
      entrance: play.entrance,
    );
    stage.tapHint = true;
    _changed();
    var part = 0;
    var now = tray.stops[0];
    await _animate((now * 1000).round(), mine, (gone) => stage.clock.show(gone / 1000));
    // The dice lie still now, and nothing should cover a number.
    stage.tapHint = false;
    _changed();
    await _wait(250, mine);

    var running = 0;
    for (final (i, die) in thrown.dice.indexed) {
      if (die.sprung && i > 0) {
        // A 20 throws one more die: it leaps out of the die that threw it and is read next.
        final home = tray.rest(i - 1, now);
        stage.flares.add((id: _flares++, kind: FlareKind.twenty, x: home.x, y: home.y));
        stage.tag = (kind: FlareKind.twenty, face: 20, x: home.x, y: home.y, r: home.r);
        _changed();
        await _wait(620, mine);
        final began = now;
        part = math.min(part + 1, tray.stops.length - 1);
        now = tray.stops[part];
        await _animate(
          ((now - began) * 1000).round(),
          mine,
          (gone) => stage.clock.show(began + gone / 1000),
        );
        stage.tag = null;
        _changed();
        await _wait(180, mine);
      }
      stage.read = i + 1;
      _changed();
      // The die that is being read rises a little and settles back, eased at both ends.
      final at = now;
      await _animate(320, mine, (gone) {
        final u = gone / 320;
        final lift = math.sin(math.pi * u);
        tray
          ..light(i, u * u * (3 - 2 * u))
          ..pop(i, lift * lift);
        stage.clock.show(at);
      });
      final special = switch (die.kind) {
        DieKind.gold when die.face < ThrownDie.goldFloor => FlareKind.mastery,
        DieKind.violet when thrown.insight && !die.sprung => FlareKind.insight,
        _ => null,
      };
      if (special != null) {
        // The move's own die does its work where it lies: a ring on the die, and for the gold
        // die its number lifted.
        await _wait(280, mine);
        final lies = tray.rest(i, now);
        stage.flares.add((id: _flares++, kind: special, x: lies.x, y: lies.y));
        if (special == FlareKind.mastery) {
          stage.tag = (kind: special, face: die.face, x: lies.x, y: lies.y, r: lies.r);
          stage.floored.add(i);
        }
        _changed();
        await _animate(360, mine, (gone) {
          final u = math.sin(math.pi * gone / 360);
          tray.pop(i, u * u);
          stage.clock.show(at);
        });
      }
      running += die.value;
      if (running > thrown.most) {
        // Past the end of the bar: the bar is full, and what is over it is counted beside it.
        stage.over = running - thrown.most;
        _changed();
      }
      await _wait(110, mine);
    }
    await _wait(250, mine);
    stage
      ..summed = true
      ..note = true;
    _changed();
    await _wait(800, mine);
    stage
      ..stamp = true
      ..tense = false
      ..tag = null;
    _known(index);
    _changed();
    if (play.end == PlayEnd.overTheTop) {
      stage.topped = true;
      _changed();
      // The dice jump for it, one after another.
      final held = _fast;
      _fast = false;
      final at = now;
      await _animate(1200, mine, (gone) {
        for (var k = 0; k < thrown.dice.length; k++) {
          final u = (gone - k * 90) / 460;
          final lift = u > 0 && u < 1 ? math.sin(math.pi * u) : 0.0;
          tray.pop(k, 1.6 * lift * lift);
        }
        stage.clock.show(at);
      });
      _fast = held;
    }
    await _wait(550, mine);
    stage.why = true;
    _changed();
  }

  // ---- Time ---------------------------------------------------------------------------------

  /// Waits [ms], or less when the player taps. Ends the play with [_Stopped] when the replay has
  /// been started again, jumped or closed meanwhile.
  Future<void> _wait(int ms, int mine) async {
    if (mine != _run || _disposed) throw const _Stopped();
    if (_fast || _skipAll || ms <= 0) {
      // Even with nothing to wait for, whoever stopped the replay gets a turn first.
      await null;
      if (mine != _run || _disposed) throw const _Stopped();
      return;
    }
    final done = _waiting = Completer<void>();
    _timer = Timer(Duration(milliseconds: ms), _wake);
    await done.future;
    if (mine != _run || _disposed) throw const _Stopped();
  }

  void _wake() {
    _timer?.cancel();
    _timer = null;
    final done = _waiting;
    _waiting = null;
    if (done != null && !done.isCompleted) done.complete();
  }

  /// Calls [paint] with the milliseconds gone by, every frame, for [ms]. With reduced motion, or
  /// when the player taps to see the result, the end state is painted at once.
  Future<void> _animate(int ms, int mine, void Function(double gone) paint) async {
    if (mine != _run || _disposed) throw const _Stopped();
    if (reduced || _fast || _skipAll || ms <= 0) {
      paint(ms.toDouble());
      return;
    }
    final done = Completer<void>();
    _motion = (ms: ms, paint: paint, done: done);
    paint(0);
    if (!_ticker.isActive) unawaited(_ticker.start());
    await done.future;
    if (mine != _run || _disposed) throw const _Stopped();
  }

  void _onTick(Duration elapsed) {
    final motion = _motion;
    if (motion == null) {
      _ticker.stop();
      return;
    }
    final gone = math.min(motion.ms.toDouble(), elapsed.inMicroseconds / 1000);
    if (_fast || _skipAll) {
      _finishMotion();
      return;
    }
    motion.paint(gone);
    if (gone >= motion.ms) _endMotion();
  }

  /// Paints the end of the motion in flight and ends it.
  void _finishMotion() {
    final motion = _motion;
    if (motion == null) return;
    motion.paint(motion.ms.toDouble());
    _endMotion();
  }

  void _endMotion() {
    final motion = _motion;
    _motion = null;
    if (_ticker.isActive) _ticker.stop();
    if (motion != null && !motion.done.isCompleted) motion.done.complete();
  }

  @override
  void dispose() {
    _disposed = true;
    _run += 1;
    _wake();
    _endMotion();
    _ticker.dispose();
    super.dispose();
  }
}
