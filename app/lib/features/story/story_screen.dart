import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../core/navigation.dart';
import '../../core/preferences.dart';
import '../../design/design.dart';
import '../../router.dart' show Routes;
import '../account/account_repository.dart';
import '../account/out_of_credits_sheet.dart';
import '../create/create_story_screen.dart' show StartAgain;
import '../library/library.dart';
import '../narration/narration_settings.dart';
import '../narration/narration_widgets.dart';
import '../narration/narrator.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';
import '../voice/speech_engine.dart';
import 'ending_card.dart';
import 'play_controller.dart';
import 'replay/replay_plays.dart';
import 'replay/replay_view.dart';
import 'rewind_sheet.dart';
import 'scene_details_sheet.dart';
import 'scene_menu.dart';
import 'scene_view.dart';
import 'story_models.dart';
import 'story_repository.dart';
import 'story_settings_sheet.dart';
import 'turn_error_card.dart';

/// The play screen (S2, S3): the story as a page of scenes, the newest one streaming in as it is
/// written with a calm reveal, older scenes loading as the player scrolls back, the suggested
/// choices and the standing actions, and the composer with dictation (V1) and slash commands (S5).
///
/// Every scene has its details (A8), which replay its dice when it has any (S15), a listen button
/// that reads it aloud (V8), and a menu to illustrate (M2) or report it (F6); the app bar opens
/// `/status`, Memory and the story's settings (S6). A story that has no scenes yet, just
/// started from a draft, plays its opening turn as soon as it opens, and so does a story someone
/// new carries on after its ending (N6). A turn that was decided and shown but never told is
/// played out before anything else (A3).
class StoryScreen extends ConsumerStatefulWidget {
  const StoryScreen({super.key, required this.storyId, this.initialStory});

  final String storyId;

  /// Passed when navigating straight from creating a story, to skip a fetch.
  final Story? initialStory;

  @override
  ConsumerState<StoryScreen> createState() => _StoryScreenState();
}

class _StoryScreenState extends ConsumerState<StoryScreen> {
  late final PlayController _play;
  late final StreamSubscription<PlayNotice> _notices;
  late final Narrator _narrator;
  late final StreamSubscription<NarrationNotice> _narration;
  final _action = TextEditingController();
  late final _mode = InputModeTracker(_action);
  final _focus = FocusNode();
  final _scroll = ScrollController();

  /// Older scenes grow upward from here, so loading them never moves the page (scrollback).
  final _center = const ValueKey('play.center');
  final _sceneKeys = <int, GlobalKey>{};
  final _narrationKeys = <int, GlobalKey>{};
  final _pendingKey = GlobalKey();
  final _pendingNarrationKey = GlobalKey();

  /// Opened at the newest scene.
  bool _landed = false;
  bool _landing = false;

  /// Keeps the streaming scene in view until the player scrolls away or its top reaches the top.
  bool _following = false;

  /// The turn in flight is one the story owed, and the page has been sent to it once.
  bool _owedInView = false;
  bool _showLatest = false;

  /// A turn the player started is waiting for the mic to turn off (V2).
  bool _waitingForMic = false;

  /// The replay of the turn in flight is open over the page (gamer mode, S15).
  bool _replaying = false;

  /// The scene that landed behind the replay, to read aloud once the replay is closed (V8).
  int? _readAfterReplay;

  @override
  void initState() {
    super.initState();
    _play = PlayController(
      repository: ref.read(storyRepositoryProvider),
      storyId: widget.storyId,
      initialStory: widget.initialStory,
    )..addListener(_changed);
    _notices = _play.notices.listen(_onNotice);
    _narrator = ref.read(narratorProvider)..addListener(_narrationChanged);
    _narration = _narrator.notices.listen(_onNarration);
    // Read from the device now, so the first turn's dice already know the player's choice (S15).
    ref.read(gamerModeProvider);
    unawaited(_play.start());
  }

  @override
  void dispose() {
    unawaited(_notices.cancel());
    unawaited(_narration.cancel());
    // Leaving the story ends its reading.
    _narrator.removeListener(_narrationChanged);
    unawaited(_narrator.stopStory(widget.storyId));
    _play
      ..removeListener(_changed)
      ..dispose();
    _mode.dispose();
    _action.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _changed() {
    if (!mounted) return;
    setState(() {});
    if (!_landed && _play.story != null) _landOnLatest();
    // A turn the story owes starts by itself as the story opens (A3): the page goes to it, as it
    // does to a turn the player sends.
    final owed = _play.pending?.resumes ?? false;
    if (owed && !_owedInView) _following = true;
    _owedInView = owed;
    // Keeps the turn in view as it streams, and its error card if it fails.
    if (_following && _play.pending != null) _follow();
  }

  void _onNotice(PlayNotice notice) {
    if (!mounted) return;
    final l10n = context.l10n;
    switch (notice) {
      case SceneSaved(:final turn):
        // In gamer mode the dice come first: the reading waits for the replay to close (S15).
        if (_replaying) {
          _readAfterReplay = turn;
        } else {
          unawaited(_readNew(turn));
        }
        // The saved scene takes the streaming one's place, with its time and event above the
        // words: keep the words where the player is reading them.
        final before = _topOf(_pendingNarrationKey);
        final following = _following;
        // The opening is read from the title page above it, which stays in view.
        final unseen =
            following &&
            !_opensPage(turn) &&
            (before == null || before > MediaQuery.sizeOf(context).height);
        _following = false;
        ref.invalidate(storiesProvider);
        if (unseen) {
          // It landed before the page reached it: show the new scene from its top.
          _reveal(turn);
          return;
        }
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!mounted || _opensPage(turn)) return;
          final after = _topOf(_narrationKeys[turn]);
          if (before != null && after != null && _scroll.hasClients) {
            final position = _scroll.position;
            final delta = after - before;
            if (delta.abs() >= 0.5) {
              _scroll.jumpTo(
                (position.pixels + delta).clamp(position.minScrollExtent, position.maxScrollExtent),
              );
            }
          }
          // A short or quick scene can finish before the page has followed it up: carry on to
          // its top, or to its choices when the whole of it fits, as following it would have.
          if (following) _bringUp(turn);
        });
      case StoryMovedOn(:final action):
        _snack(l10n.errorVersionConflict);
        // The player's words for the turn that lost go back in the box, to send again or not.
        if (action != null) _giveBack(action);
      case StepsShown(:final details):
        unawaited(_showThrows(details));
      case OwedTurnPlaying(:final action):
        // Another turn was already decided, so that one plays (A3). Words written for this one
        // go back in the box.
        _snack(action == null ? l10n.turnOwedPlaying : l10n.turnOwedWordsBack);
        if (action != null) _giveBack(action);
      case OwedTurnLetGo(:final action):
        _snack(l10n.turnOwedLetGo);
        if (action != null) _giveBack(action);
      case OutOfCredits(:final error, :final turn, :final picture):
        unawaited(_outOfCredits(error, turn: turn, picture: picture));
      case CreditsSpent():
        // Only a balance something has shown is out of date; the next one loads fresh.
        if (ref.exists(meProvider)) ref.read(meProvider.notifier).refreshQuietly();
      case TurnRefused(:final error):
        _snack(describeError(l10n, error).message);
      case CloseFailed():
        _snack(l10n.endingCloseFailed);
      case RewindFailed():
        _snack(l10n.rewindFailed);
    }
  }

  /// The out-of-credits sheet (K2). With the player's own key added (K6), what was refused goes
  /// again on that key.
  Future<void> _outOfCredits(ApiException error, {PendingTurn? turn, int? picture}) async {
    final outcome = await showOutOfCreditsSheet(context, error: error, retriesItself: true);
    if (!mounted || outcome != OutOfCreditsOutcome.keyAdded) return;
    if (turn != null) {
      if (await _micOff() == null) return;
      _following = true;
      final started = await _play.again(turn);
      // The refused turn left its words in the box; now it is under way.
      final action = turn.input.action;
      if (started && mounted && action != null && _action.text.trim() == action.trim()) {
        _action.clear();
      }
    } else if (picture != null) {
      unawaited(_play.illustrate(picture));
    }
  }

  // ---- The dice ----------------------------------------------------------------------------

  /// Gamer mode (S15): the turn's steps are decided, so its dice play at once, over the page,
  /// while the story is written behind them. Only a turn with a throw opens it.
  Future<void> _showThrows(SceneDetails details) async {
    if (_replaying || !details.hasThrows) return;
    // From here the reading waits: a scene that lands while the player's choice is still being
    // read from the device waits for the dice like any other.
    _replaying = true;
    try {
      final on = await ref.read(gamerModeProvider.notifier).loaded();
      if (!mounted || !on) return;
      // Never over a sheet or another page the player has opened.
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) return;
      final l10n = context.l10n;
      final standing = _play.pending?.kind == 'standing';
      await showReplay(
        context,
        own: true,
        plays: playsOf(
          details,
          // A standing action's one step is the action's wire name (S2).
          stepText: (step) => (standing ? _standingLabel(step.text, l10n) : null) ?? step.text,
        ),
        chain: details.chain,
      );
    } finally {
      _replaying = false;
      final landed = _readAfterReplay;
      _readAfterReplay = null;
      if (mounted && landed != null) unawaited(_readNew(landed));
    }
  }

  /// A scene's details (A8): its dice replayed when any were thrown (S15), or the list of what
  /// the facts settled.
  void _openDetails(Scene scene) {
    if (scene.details.hasThrows) {
      unawaited(showSceneReplay(context, scene));
    } else {
      showSceneDetails(context, scene);
    }
  }

  static String? _standingLabel(String? wire, AppLocalizations l10n) =>
      StandingAction.values.where((a) => a.wire == wire).firstOrNull?.label(l10n);

  /// What a turn the story owed shows as the player's action. The server keeps a standing action
  /// by its wire name, and an ending with no note as nothing (A3).
  String? _owedLabel(String kind, String? action) => switch (kind) {
    'standing' => _standingLabel(action, context.l10n) ?? action,
    'end' => action ?? context.l10n.endLabel,
    _ => action,
  };

  /// Plays out the turn the story owes (A3).
  Future<void> _playOwed() async {
    if (await _micOff() == null) return;
    _following = true;
    _quiet();
    await _play.resume();
  }

  // ---- Reading aloud ------------------------------------------------------------------------

  void _narrationChanged() {
    if (mounted) setState(() {});
  }

  /// Reads [scene] aloud (V8), in the voice the player chose (V9).
  void _listen(Scene scene) {
    unawaited(
      _narrator.read(
        storyId: widget.storyId,
        turn: scene.turn,
        narration: scene.narration,
        language: _play.story?.settings.language ?? 'en',
      ),
    );
  }

  /// A new scene, read as it lands when the player asked for that.
  Future<void> _readNew(int turn) async {
    final settings = await ref.read(narrationSettingsProvider.notifier).loaded();
    if (!mounted || !settings.readNewScenes) return;
    final scene = _play.story?.scenes.where((s) => s.turn == turn).firstOrNull;
    if (scene != null && !_play.isBlocked(scene)) _listen(scene);
  }

  /// The player acted: the scene being read gives way to the next.
  void _quiet() => unawaited(_narrator.stopStory(widget.storyId));

  void _onNarration(NarrationNotice notice) {
    if (!mounted || notice.storyId != widget.storyId) return;
    final l10n = context.l10n;
    switch (notice) {
      case ReadOnPhone(reason: StudioFallback.outOfCredits):
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(
            SnackBar(
              content: Text(l10n.narrationOutOfCredits),
              action: SnackBarAction(
                label: l10n.accountCredits,
                onPressed: () => unawaited(context.push(Routes.credits)),
              ),
            ),
          );
      case ReadOnPhone(reason: StudioFallback.quota):
        _snack(l10n.narrationQuota);
      case ReadOnPhone(reason: StudioFallback.unavailable):
        _snack(l10n.narrationUnavailable);
      case NoPhoneVoice(:final language):
        _snack(l10n.narrationNoDeviceVoice(language));
      case StudioCreditsSpent():
        if (ref.exists(meProvider)) ref.read(meProvider.notifier).refreshQuietly();
    }
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  double? _topOf(GlobalKey? key) {
    final box = key?.currentContext?.findRenderObject();
    if (box is! RenderBox || !box.attached || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero).dy;
  }

  // ---- Acting -----------------------------------------------------------------------------

  Future<void> _send(String text) async {
    if (text.startsWith('/')) {
      _command(text);
      return;
    }
    final mode = _mode.mode.wire;
    _following = true;
    _quiet();
    final started = await _play.act(text, inputMode: mode);
    // The turn is under way: empty the box, unless the player has started writing the next one.
    if (started && mounted && _action.text.trim() == text) _action.clear();
  }

  void _command(String text) {
    final name = text.substring(1).split(RegExp(r'\s')).first.toLowerCase();
    switch (name) {
      case 'status':
        _action.clear();
        _openStatus();
      case 'end':
        final note = text.substring(1 + name.length).trim();
        unawaited(_end(note.isEmpty ? null : note));
      default:
        _snack(context.l10n.storyUnknownCommand(name));
    }
  }

  /// `/end`, with or without a note on how the story should end (N6). It can't be undone, so the
  /// player confirms first.
  Future<void> _end(String? note) async {
    final l10n = context.l10n;
    final mode = _mode.mode.wire;
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.endConfirmTitle),
        content: Text(note == null ? l10n.endConfirmBody : l10n.endConfirmBodyNote),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(l10n.endConfirmKeep),
          ),
          TextButton(
            key: const ValueKey('end.confirm'),
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(l10n.endConfirmEnd),
          ),
        ],
      ),
    );
    if (!(sure ?? false) || !mounted) return;
    _following = true;
    _quiet();
    final sent = _action.text.trim();
    final started = await _play.end(note: note, inputMode: mode, label: note ?? l10n.endLabel);
    if (started && mounted && _action.text.trim() == sent) _action.clear();
  }

  Future<void> _endWithoutRefused() async {
    if (await _micOff() == null) return;
    _following = true;
    await _play.endWithoutRefused();
  }

  /// Rewinding a few scenes after a death (C8): how far back, then the feed from there.
  Future<void> _rewind(int most) async {
    final scenes = _play.story?.scenes ?? const <Scene>[];
    final count = await showRewindSheet(context, most: most, scenes: scenes);
    if (count == null || !mounted) return;
    // The scenes being rewound go, and their reading with them.
    _quiet();
    if (await _play.rewind(count) && mounted) {
      ref.invalidate(storiesProvider);
      _following = true;
    }
  }

  /// Carrying the story on as someone else (N6): the person drawn, to start as or draw again. Once
  /// the player starts as them, their opening plays here.
  Future<void> _carryOn() async {
    final carried = await context.push<Story>(Routes.successor(widget.storyId), extra: _play.story);
    if (!mounted) return;
    if (carried == null) {
      // Whoever was drawn stays with the story, to come back to.
      unawaited(_play.reload());
      return;
    }
    ref.invalidate(storiesProvider);
    _following = true;
    _play.carriedOn(carried);
  }

  /// The create flow with this story's premise filled in, to keep or change (N6).
  void _startAgain() {
    final premise = _play.story?.premise;
    unawaited(context.push(Routes.create, extra: StartAgain(premise ?? '')));
  }

  /// No turn starts while the mic is on or its words are on their way (V2): every turn the player
  /// starts here first turns it off and waits, with the composer busy and the suggestions hidden.
  /// True once what was said is in the box, false when it couldn't be written down: sending the
  /// box goes only on true, and any other turn goes either way, leaving the words in the box for
  /// the next one. Null once the screen is gone, or while another turn already waits: then no
  /// turn starts, so the first the player asked for is the one that plays.
  Future<bool?> _micOff() async {
    if (!_mode.dictating.value) return true;
    if (_waitingForMic) return null;
    setState(() => _waitingForMic = true);
    final landed = await _mode.finishDictation();
    if (!mounted) return null;
    setState(() => _waitingForMic = false);
    return landed;
  }

  /// The composer's send, with the mic on.
  Future<bool> _micOffToSend() async => await _micOff() ?? false;

  Future<void> _choose(Choice choice) async {
    if (await _micOff() == null) return;
    _following = true;
    _quiet();
    await _play.choose(choice);
  }

  Future<void> _stand(StandingAction action) async {
    final label = action.label(context.l10n);
    if (await _micOff() == null) return;
    _following = true;
    _quiet();
    await _play.stand(action.wire, label: label);
  }

  Future<void> _retry() async {
    final action = _play.pending?.input.action;
    if (await _micOff() == null) return;
    _following = true;
    final started = await _play.retry();
    // A turn refused before it started left its words in the box; now it is under way.
    if (started && mounted && action != null && _action.text.trim() == action.trim()) {
      _action.clear();
    }
  }

  /// Puts words back in the box, unless the player has started writing something else.
  void _giveBack(String text) {
    if (_action.text.trim().isNotEmpty) return;
    _action.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }

  /// Puts the action back in the box to say it another way (F4).
  void _rephrase(String text) {
    _play.dismissFailure();
    _action.value = TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
    _focus.requestFocus();
  }

  void _dismiss(PendingTurn failed) {
    _play.dismissFailure();
    // Words the player wrote are never lost: back in the box if it was emptied. A turn the
    // story owes still plays those words, so they stay with it.
    if (_play.owes) return;
    if (failed.input.action case final action?) _giveBack(action);
  }

  /// The story's accent, for the pages above it (S13).
  GenreAccent? get _accent => switch (_play.story) {
    final story? => GenreAccent.of(genre: story.genre, chosen: story.settings.accent),
    null => null,
  };

  void _openStatus() => context.push(Routes.status(widget.storyId), extra: _accent);

  void _openMemory() => context.push(Routes.memory(widget.storyId), extra: _accent);

  Future<void> _openSettings() async {
    final story = _play.story;
    if (story == null) return;
    final saved = await showStorySettings(context, story: story, save: _play.save);
    if (saved == null || !mounted) return;
    // The Library shows the new title and color too.
    ref.invalidate(storiesProvider);
    _snack(switch (saved) {
      // A title or a color shows at once (S13).
      SettingsSaved.now => context.l10n.settingsSavedNow,
      SettingsSaved.nextScene => context.l10n.settingsSaved,
    });
  }

  Future<void> _sceneMenu(Scene scene) async {
    final image = _play.imageOf(scene);
    final blocked = _play.isBlocked(scene);
    final action = await showSceneMenu(
      context,
      canIllustrate: !blocked && (image == null || image.isSkipped),
    );
    if (!mounted || action == null) return;
    switch (action) {
      case SceneAction.illustrate:
        unawaited(_play.illustrate(scene.turn));
      case SceneAction.report:
        final hid = await showReportSheet(
          context,
          send: ({required category, note, required block}) =>
              _play.report(scene.turn, category: category, note: note, block: block),
        );
        if (hid != null && mounted) {
          // A blocked scene is never read (F6, V8).
          if (hid && _narrator.phaseOf(widget.storyId, scene.turn) != NarrationPhase.idle) {
            _quiet();
          }
          _snack(hid ? context.l10n.reportSentHidden : context.l10n.reportSent);
        }
    }
  }

  // ---- Scrolling --------------------------------------------------------------------------

  /// Opens the story where the player left it: at the top of the newest scene, or at the title
  /// page when the newest scene is the opening.
  void _landOnLatest() {
    if (_landed || _landing) return;
    final turn = _play.story?.scenes.lastOrNull?.turn;
    if (turn == null || _opensPage(turn)) {
      _landed = true;
      return;
    }
    _landing = true;
    _reveal(turn, animate: false, done: () => _landed = true);
  }

  /// Scrolls a scene's top into view. The feed is built lazily, so a scene that isn't laid out is
  /// found from the end, where the newest scenes are, then by stepping back up a screen at a time.
  void _reveal(
    int turn, {
    bool animate = true,
    VoidCallback? done,
    int attempt = 0,
    bool climbing = false,
  }) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (!_scroll.hasClients || !_scroll.position.hasContentDimensions) {
        // Not built or laid out yet, as under a page opened straight from a link (the page under
        // the glass bar is built when it is laid out): look again next frame.
        _reveal(turn, animate: animate, done: done, attempt: attempt, climbing: climbing);
        return;
      }
      final position = _scroll.position;
      final target = _sceneKeys[turn]?.currentContext;
      if (target != null || attempt >= 16) {
        done?.call();
        final to = _restingOffset(target?.findRenderObject());
        if (to == null) return;
        if (animate) {
          unawaited(
            _scroll.animateTo(
              to,
              duration: Motion.of(context, Motion.slow),
              curve: Motion.standard,
            ),
          );
        } else {
          _scroll.jumpTo(to);
        }
        return;
      }
      // The end moves as the scenes on the way are laid out: go there until it holds still, then
      // climb.
      final up = climbing || (position.maxScrollExtent - position.pixels).abs() < 1;
      _scroll.jumpTo(
        up
            ? math.max(position.minScrollExtent, position.pixels - position.viewportDimension)
            : position.maxScrollExtent,
      );
      _reveal(turn, animate: animate, done: done, attempt: attempt + 1, climbing: up);
    });
  }

  /// Where the page rests to read a scene from its top: a little room under the glass bar, the
  /// same for landing, following and bringing a scene up (S3), and never past the end. Null when
  /// [card] isn't laid out.
  double? _restingOffset(RenderObject? card) {
    if (card == null || !card.attached || !_scroll.hasClients) return null;
    final top = RenderAbstractViewport.maybeOf(card)?.getOffsetToReveal(card, 0).offset;
    if (top == null) return null;
    final position = _scroll.position;
    return (top - Space.lg - _barInset).clamp(position.minScrollExtent, position.maxScrollExtent);
  }

  /// How far the glass bar reaches down the page, which runs on behind it.
  double get _barInset => MediaQuery.paddingOf(context).top + GlassTopBar.extent;

  /// Whether [turn] is the opening, right under the title page at the start of the feed.
  bool _opensPage(int turn) => turn <= 1 && _play.anchorTurn <= 1;

  /// Brings the streaming scene into view as it grows, but never past its own top, so the player
  /// reads it from the start at their own pace (S3). A turn that fails stays in view too.
  void _follow([int attempt = 0]) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_following || !_scroll.hasClients) return;
      // The first opening is read from the title page; someone new's opening is followed (N6).
      if ((_play.pending?.isOpening ?? false) && (_play.story?.scenes.isEmpty ?? true)) return;
      if (!_scroll.position.hasContentDimensions) return;
      final card = _pendingKey.currentContext?.findRenderObject();
      final position = _scroll.position;
      if (card == null || !card.attached) {
        // The player acted from far up the page, and the feed hasn't built that far: go to the
        // end, then look again.
        if (attempt < 4 && _play.pending != null) {
          _scroll.jumpTo(position.maxScrollExtent);
          _follow(attempt + 1);
        }
        return;
      }
      final target = _restingOffset(card) ?? position.maxScrollExtent;
      if (target <= position.pixels + 1) return;
      _scroll.animateTo(target, duration: Motion.of(context, Motion.slow), curve: Motion.standard);
    });
  }

  /// Glides a saved scene up towards the top of the view, never past its own top and never back
  /// down the page.
  void _bringUp(int turn) {
    if (_opensPage(turn)) return;
    if (!_scroll.hasClients) return;
    final target = _restingOffset(_sceneKeys[turn]?.currentContext?.findRenderObject());
    if (target == null || target <= _scroll.position.pixels + 1) return;
    unawaited(
      _scroll.animateTo(target, duration: Motion.of(context, Motion.slow), curve: Motion.standard),
    );
  }

  bool _onScroll(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (notification is UserScrollNotification && notification.direction != ScrollDirection.idle) {
      _following = false;
    }
    if (WidgetsBinding.instance.schedulerPhase == SchedulerPhase.persistentCallbacks) {
      // A scroll can end while the page is being laid out, when what it holds changes size.
      // Nothing may be rebuilt from in there, so the rest waits for the frame to end.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _scroll.hasClients) _scrolled(_scroll.position);
      });
    } else {
      _scrolled(notification.metrics);
    }
    return false;
  }

  /// What follows from where the page now stands: older scenes are fetched near the top, and
  /// the way back to the newest scene is offered far above it.
  void _scrolled(ScrollMetrics metrics) {
    // After a failed page, only the retry button asks again, so a lost connection isn't hammered.
    if (_landed && metrics.extentBefore < 900 && _play.olderError == null) {
      unawaited(_play.loadOlder());
    }
    // Only once the newest scene is well out of reach, so the pill doesn't sit over the words.
    final latest = _landed && metrics.extentAfter > metrics.viewportDimension * 1.5;
    if (latest != _showLatest) setState(() => _showLatest = latest);
  }

  /// Back to the end of the feed. From far back it jumps most of the way and glides the rest, and
  /// it settles at the true end once the scenes on the way have been laid out.
  Future<void> _toLatest() async {
    if (!_scroll.hasClients || !_scroll.position.hasContentDimensions) return;
    final position = _scroll.position;
    final glide = position.viewportDimension * 1.5;
    if (position.maxScrollExtent - position.pixels > glide) {
      _scroll.jumpTo(position.maxScrollExtent - glide);
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted || !_scroll.hasClients) return;
    }
    await _scroll.animateTo(
      _scroll.position.maxScrollExtent,
      duration: Motion.of(context, const Duration(milliseconds: 400)),
      curve: Motion.standard,
    );
    for (var i = 0; i < 4 && mounted && _scroll.hasClients; i++) {
      final end = _scroll.position.maxScrollExtent;
      if (end - _scroll.position.pixels < 1) break;
      _scroll.jumpTo(end);
      await WidgetsBinding.instance.endOfFrame;
    }
  }

  // ---- Building ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final story = _play.story;
    return StoryTheme(
      genre: story?.genre,
      chosen: story?.settings.accent,
      child: Scaffold(
        // The page runs on behind the bar: a story opens on its cover, and scenes pass under
        // the glass as they are read.
        extendBodyBehindAppBar: true,
        appBar: GlassTopBar(
          leading: backOr(context, Routes.library) ?? const BackButton(),
          title: _BarTitle(
            title: story?.title ?? l10n.storyFallbackTitle,
            clock: story?.clockLabel,
          ),
          actions: [
            IconButton(
              tooltip: l10n.storyStatus,
              icon: const Icon(Icons.badge_outlined),
              onPressed: _openStatus,
            ),
            IconButton(
              tooltip: l10n.storyMemory,
              icon: const Icon(Icons.auto_stories_outlined),
              onPressed: _openMemory,
            ),
            IconButton(
              tooltip: l10n.storySettings,
              icon: const Icon(Icons.tune_rounded),
              onPressed: story == null ? null : _openSettings,
            ),
          ],
        ),
        body: switch ((story, _play.loadError)) {
          (null, final Object error) => SafeArea(
            child: ErrorState(error: error, onRetry: _play.reload),
          ),
          (null, _) => const SafeArea(
            child: Padding(
              padding: EdgeInsets.all(Space.gutter),
              child: ContentColumn.reading(
                child: SkeletonText(lines: 8, lineHeight: 14, spacing: 14),
              ),
            ),
          ),
          (final Story story, _) => Column(
            children: [
              Expanded(
                child: Stack(
                  children: [
                    NotificationListener<ScrollNotification>(
                      onNotification: _onScroll,
                      child: _feed(context, story),
                    ),
                    // The page's last lines fade out towards the action box.
                    const Positioned(left: 0, right: 0, bottom: 0, child: _FootFade()),
                    Positioned(
                      bottom: Space.md,
                      left: 0,
                      right: 0,
                      child: Center(
                        child: _LatestButton(visible: _showLatest, onPressed: _toLatest),
                      ),
                    ),
                  ],
                ),
              ),
              if (_narrator.isReading(widget.storyId))
                ReadingBar(
                  deviceVoice: _narrator.voice == NarrationVoice.device,
                  readNewScenes: ref.watch(narrationSettingsProvider).readNewScenes,
                  onReadNewScenes: (on) =>
                      ref.read(narrationSettingsProvider.notifier).setReadNewScenes(on),
                  onStop: () => unawaited(_narrator.stop()),
                ),
              // A story at its ending takes no more turns (N6): its card says what's next.
              if (story.ending == null)
                Composer(
                  controller: _action,
                  focusNode: _focus,
                  // A turn the story owes plays before any new one (A3). While it is being
                  // written the box is open as in any turn, to write what comes after it.
                  enabled:
                      story.scenes.isNotEmpty && !story.openingDue && !(_play.owes && !_play.busy),
                  busy: _play.busy || _waitingForMic,
                  onSubmit: _send,
                  dictating: _mode.dictating,
                  onFinishDictation: _micOffToSend,
                  mic: DictationButton(
                    tracker: _mode,
                    storyId: widget.storyId,
                    localeId: speechLocale(story.settings.language),
                  ),
                  commands: [
                    SlashCommand('status', l10n.slashStatus),
                    SlashCommand('end', l10n.slashEnd),
                  ],
                )
              else
                // Nothing floats under an ended story: only the system's own inset.
                SizedBox(height: MediaQuery.paddingOf(context).bottom),
            ],
          ),
        },
      ),
    );
  }

  Widget _feed(BuildContext context, Story story) {
    final anchor = _play.anchorTurn;
    final older = [
      for (final s in story.scenes)
        if (s.turn < anchor) s,
    ];
    final newer = [
      for (final s in story.scenes)
        if (s.turn >= anchor) s,
    ];
    final pending = _play.pending;
    final last = story.scenes.lastOrNull;
    // When the first load reached the opening, nothing older can arrive: the title page sits at
    // the top of the main list. Otherwise it waits above the older scenes.
    final startsHere = anchor <= 1;

    Widget scene(Scene scene) => ContentColumn.reading(
      key: _sceneKeys.putIfAbsent(scene.turn, GlobalKey.new),
      child: SceneView(
        scene: scene,
        image: _play.imageOf(scene),
        hidden: _play.isBlocked(scene),
        ornament: scene != last || pending != null,
        narrationKey: _narrationKeys.putIfAbsent(scene.turn, GlobalKey.new),
        dropCap: scene.kind == 'opening',
        onDetails: () => _openDetails(scene),
        // A scene the player blocked (F6) is never read.
        listen: _play.isBlocked(scene) || scene.narration.trim().isEmpty
            ? null
            : ListenButton(
                key: ValueKey('scene.listen.${scene.turn}'),
                phase: _narrator.phaseOf(widget.storyId, scene.turn),
                onListen: () => _listen(scene),
                onStop: () => unawaited(_narrator.stop()),
              ),
        onMore: () => _sceneMenu(scene),
        onPictureError: () => _play.pictureFailed(scene.turn),
      ),
    );

    final top = _Top(
      story: story,
      barInset: _barInset,
      reachedStart: _play.reachedStart,
      loading: _play.loadingOlder,
      error: _play.olderError,
      onRetry: _play.loadOlder,
    );

    return CustomScrollView(
      controller: _scroll,
      center: _center,
      slivers: [
        SliverList.builder(
          itemCount: older.length + (startsHere ? 0 : 1),
          itemBuilder: (context, i) => i < older.length ? scene(older[older.length - 1 - i]) : top,
        ),
        SliverPadding(
          key: _center,
          padding: const EdgeInsets.only(bottom: Space.xxl),
          sliver: SliverList.list(
            children: [
              // Without the title page above it, the first scene starts clear of the bar.
              if (startsHere) top else SizedBox(height: Space.lg + _barInset),
              for (final s in newer) scene(s),
              if (_play.opening && pending == null)
                ContentColumn.reading(
                  child: _Begin(onBegin: _play.begin, carriedOn: story.scenes.isNotEmpty),
                ),
              if (pending != null)
                ContentColumn.reading(
                  key: _pendingKey,
                  child: _PendingScene(
                    pending: pending,
                    label: pending.owedKind == null
                        ? pending.label
                        : _owedLabel(pending.kind, pending.label),
                    narrationKey: _pendingNarrationKey,
                    onRetry: _retry,
                    onRephrase: _rephrase,
                    onAccount: () => unawaited(context.push(Routes.account)),
                    onDismiss: pending.isOpening ? null : () => _dismiss(pending),
                  ),
                ),
              if (story.unfinishedTurn case final owed? when pending == null && _play.owes)
                ContentColumn.reading(
                  child: _OwedTurn(
                    action: _owedLabel(owed.kind, owed.action),
                    onContinue: _waitingForMic ? null : () => unawaited(_playOwed()),
                  ),
                ),
              if (_play.refusal case final refusal? when pending == null)
                ContentColumn.reading(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
                    child: EndingRefusedCard(
                      parts: refusal.parts,
                      onPlayOn: _play.playOn,
                      onEndWithout: () => unawaited(_endWithoutRefused()),
                    ),
                  ),
                ),
              if (story.ending case final ending? when pending == null)
                ContentColumn.reading(
                  child: EndingCard(
                    ending: ending,
                    closing: _play.closing || _play.rewinding,
                    onClose: () => unawaited(_play.close()),
                    onRewind: () => unawaited(_rewind(ending.rewind)),
                    onCarryOn: () => unawaited(_carryOn()),
                    onStartAgain: (story.premise ?? '').trim().isEmpty ? null : _startAgain,
                  ),
                ),
              if (last != null &&
                  !_play.busy &&
                  !_play.owes &&
                  !_waitingForMic &&
                  story.ending == null &&
                  !story.openingDue)
                ContentColumn.reading(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
                    child: StoryChoices(
                      key: ValueKey('choices-${last.turn}'),
                      // A blocked scene's choices are written from its text, so they go with it.
                      choices: [
                        if (!_play.isBlocked(last))
                          for (final c in last.choices)
                            StoryChoice(
                              id: c.id,
                              label: c.label,
                              kind: ChoiceKind.fromWire(c.kind),
                            ),
                      ],
                      standing: [
                        for (final s in last.standingActions)
                          ?StandingAction.values.where((a) => a.wire == s).firstOrNull,
                      ],
                      onChoice: (choice) => unawaited(
                        _choose(
                          last.choices.firstWhere(
                            (c) => c.id == choice.id,
                            orElse: () => Choice(id: choice.id, label: choice.label),
                          ),
                        ),
                      ),
                      onStanding: (action) => unawaited(_stand(action)),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The story's title and the world's date and time, always in sight in the glass bar (W10).
class _BarTitle extends StatelessWidget {
  const _BarTitle({required this.title, this.clock});

  final String title;
  final String? clock;

  @override
  Widget build(BuildContext context) {
    final clock = this.clock;
    final colors = context.lucid;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontFamily: Fonts.display,
            fontWeight: FontWeight.w500,
            fontSize: 15.5,
            height: 1.2,
            color: colors.textPrimary,
          ),
        ),
        if (clock != null)
          Semantics(
            label: context.l10n.storyClock(clock),
            excludeSemantics: true,
            child: AnimatedSwitcher(
              duration: Motion.of(context, Motion.slow),
              child: Text(
                clock,
                key: ValueKey(clock),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: context.lucidText.meta.copyWith(fontSize: 12, color: colors.accent),
              ),
            ),
          ),
      ],
    );
  }
}

/// The feed's last lines going out into the page's color, just above the action box.
class _FootFade extends StatelessWidget {
  const _FootFade();

  @override
  Widget build(BuildContext context) {
    final page = Theme.of(context).scaffoldBackgroundColor;
    return IgnorePointer(
      child: Container(
        height: 28,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [page.withValues(alpha: 0), page],
          ),
        ),
      ),
    );
  }
}

/// The top of the feed: a title page once the opening is loaded, or the older scenes loading.
///
/// The title page is the story's cover: the painting from the very top of the screen, behind
/// the glass bar, going down into the page's color, with the genre, the title in the accent's
/// gradient and a rule with a star standing on its foot. A story without a cover opens on the
/// same words under the bar.
class _Top extends StatelessWidget {
  const _Top({
    required this.story,
    required this.barInset,
    required this.reachedStart,
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final Story story;

  /// How far the glass bar reaches down the page.
  final double barInset;
  final bool reachedStart;
  final bool loading;
  final Object? error;
  final VoidCallback onRetry;

  /// The cover's height on a phone, and its share of a shorter screen.
  static const _coverHeight = 470.0;
  static const _coverShare = 0.56;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    if (!reachedStart) {
      return Padding(
        padding: EdgeInsets.only(top: barInset + Space.xl, bottom: Space.xl),
        child: Center(
          child: error != null && !loading
              ? TextButton.icon(
                  onPressed: onRetry,
                  icon: const Icon(Icons.refresh_rounded),
                  label: Text(l10n.storyEarlierFailed),
                )
              : Semantics(
                  label: l10n.storyEarlierLoading,
                  child: SizedBox.square(
                    dimension: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: context.lucid.textMuted,
                    ),
                  ),
                ),
        ),
      );
    }
    final cover = story.coverUrl;
    final screen = MediaQuery.sizeOf(context);
    final height = cover == null ? 0.0 : math.min(_coverHeight, screen.height * _coverShare);
    final words = Padding(
      padding: EdgeInsets.fromLTRB(
        Space.gutter,
        // On a cover the words stand on its foot; without one, under the bar.
        cover == null ? barInset + Space.xxl : math.max(barInset + Space.xl, height * 0.66),
        Space.gutter,
        Space.xl,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (story.genre.isNotEmpty) ...[Eyebrow(story.genre), const SizedBox(height: Space.md)],
          // A heading of its own, apart from the genre over it.
          Semantics(
            header: true,
            container: true,
            child: HeadlineScaling(
              child: GradientText(
                story.title,
                style: theme.textTheme.displayMedium!.copyWith(
                  fontSize: 40,
                  height: 1.05,
                  letterSpacing: -0.8,
                ),
              ),
            ),
          ),
          const SizedBox(height: 18),
          const StarRule(),
        ],
      ),
    );
    return ContentColumn.reading(
      child: cover == null
          ? words
          : Stack(
              children: [
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: height,
                  child: _TitleCover(url: cover, fadeSides: screen.width > Layout.readingWidth),
                ),
                words,
              ],
            ),
    );
  }
}

/// The cover behind a story's title: dimmed under the bar, clear over its focal point, then
/// down into the page's color. In a column that floats in a wider screen, its sides fade too.
class _TitleCover extends StatelessWidget {
  const _TitleCover({required this.url, required this.fadeSides});

  final String url;
  final bool fadeSides;

  @override
  Widget build(BuildContext context) {
    final page = Theme.of(context).scaffoldBackgroundColor;
    final width = math.min(MediaQuery.sizeOf(context).width, Layout.readingWidth);
    Widget cover = Stack(
      fit: StackFit.expand,
      children: [
        CoverImage(
          url: url,
          cacheWidth: (width * MediaQuery.devicePixelRatioOf(context)).round(),
          fallback: ColoredBox(color: page),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              // The glass bar dims the very top itself.
              colors: [
                page.withValues(alpha: 0.3),
                page.withValues(alpha: 0),
                page.withValues(alpha: 0),
                page.withValues(alpha: 0.86),
                page,
              ],
              stops: const [0, 0.26, 0.44, 0.78, 1],
            ),
          ),
        ),
      ],
    );
    if (fadeSides) {
      cover = ShaderMask(
        blendMode: BlendMode.dstIn,
        shaderCallback: (bounds) => const LinearGradient(
          colors: [Color(0x00000000), Color(0xFF000000), Color(0xFF000000), Color(0x00000000)],
          stops: [0, 0.12, 0.88, 1],
        ).createShader(bounds),
        child: cover,
      );
    }
    return ExcludeSemantics(child: IgnorePointer(child: cover));
  }
}

/// An opening that didn't start (out of credits, say): begin by hand. The story has no scenes
/// yet, or someone new carries it on ([carriedOn], N6).
class _Begin extends StatelessWidget {
  const _Begin({required this.onBegin, this.carriedOn = false});

  final VoidCallback onBegin;
  final bool carriedOn;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.all(Space.gutter),
      child: Column(
        children: [
          Text(
            carriedOn ? l10n.storyCarriedOnBeginning : l10n.storyBeginning,
            textAlign: TextAlign.center,
            style: context.lucidText.playerAction,
          ),
          const SizedBox(height: Space.lg),
          FilledButton(
            onPressed: onBegin,
            child: Text(carriedOn ? l10n.storyCarriedOnBegin : l10n.storyBegin),
          ),
        ],
      ),
    );
  }
}

/// A turn the story owes (A3): it was decided and its dice were shown, but its scene never
/// arrived. It is the next thing that happens, whatever else the player meant to do.
class _OwedTurn extends StatelessWidget {
  const _OwedTurn({required this.action, required this.onContinue});

  final String? action;
  final VoidCallback? onContinue;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    return SceneCard(
      playerAction: action,
      ornament: false,
      narration: Container(
        key: const ValueKey('turn.owed'),
        padding: const EdgeInsets.all(Space.lg),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(Radii.lg),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.turnOwedTitle, style: theme.textTheme.titleMedium),
            const SizedBox(height: Space.xs),
            Text(
              l10n.turnOwed,
              style: theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary),
            ),
            const SizedBox(height: Space.md),
            FilledButton.tonal(
              key: const ValueKey('turn.owed.continue'),
              onPressed: onContinue,
              child: Text(l10n.turnOwedContinue),
            ),
          ],
        ),
      ),
    );
  }
}

/// The turn in flight: the player's action, then the narration as it streams in, or what went
/// wrong.
class _PendingScene extends StatelessWidget {
  const _PendingScene({
    required this.pending,
    required this.label,
    required this.narrationKey,
    required this.onRetry,
    required this.onRephrase,
    required this.onAccount,
    this.onDismiss,
  });

  final PendingTurn pending;

  /// What the player did, in the app's words.
  final String? label;
  final Key narrationKey;
  final VoidCallback onRetry;
  final ValueChanged<String> onRephrase;
  final VoidCallback onAccount;
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    final error = pending.error;
    final action = pending.input.action;
    return SceneCard(
      playerAction: label,
      spokenAction: pending.spoken,
      ornament: false,
      narration: KeyedSubtree(
        key: narrationKey,
        child: pending.failed && error != null
            ? TurnErrorCard(
                error: error,
                onRetry: onRetry,
                onRephrase: action == null ? null : () => onRephrase(action),
                onAccount: onAccount,
                onDismiss: onDismiss,
              )
            // An opening is set with its drop capital from its first words, as it will be saved.
            : StreamingNarration(text: pending.text, streaming: true, dropCap: pending.isOpening),
      ),
    );
  }
}

/// "Latest", when the player has scrolled far back: a small pill of glass over the page.
class _LatestButton extends StatelessWidget {
  const _LatestButton({required this.visible, required this.onPressed});

  final bool visible;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: Motion.of(context, Motion.base),
        child: AnimatedSlide(
          offset: visible ? Offset.zero : const Offset(0, 0.3),
          duration: Motion.of(context, Motion.base),
          curve: Motion.standard,
          child: Glass(
            child: Material(
              type: MaterialType.transparency,
              child: InkWell(
                customBorder: const StadiumBorder(),
                onTap: onPressed,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: Layout.minTouch - 4),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.sm),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.arrow_downward_rounded, size: 18, color: context.lucid.accent),
                        const SizedBox(width: Space.sm),
                        Text(context.l10n.storyLatest, style: theme.textTheme.labelLarge),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
