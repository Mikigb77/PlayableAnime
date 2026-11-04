import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../core/navigation.dart';
import '../../design/design.dart';
import '../../router.dart' show Routes;
import '../account/account_repository.dart';
import '../account/out_of_credits_sheet.dart';
import '../library/library.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';
import 'play_controller.dart';
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
/// Every scene has its details (A8) and a menu to illustrate (M2) or report it (F6); the app bar
/// opens `/status`, Memory and the story's settings (S6). A story that has no scenes yet, just
/// started from a draft, plays its opening turn as soon as it opens.
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
  bool _showLatest = false;

  @override
  void initState() {
    super.initState();
    _play = PlayController(
      repository: ref.read(storyRepositoryProvider),
      storyId: widget.storyId,
      initialStory: widget.initialStory,
    )..addListener(_changed);
    _notices = _play.notices.listen(_onNotice);
    unawaited(_play.start());
  }

  @override
  void dispose() {
    unawaited(_notices.cancel());
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
    // Keeps the turn in view as it streams, and its error card if it fails.
    if (_following && _play.pending != null) _follow();
  }

  void _onNotice(PlayNotice notice) {
    if (!mounted) return;
    final l10n = context.l10n;
    switch (notice) {
      case SceneSaved(:final turn):
        // The saved scene takes the streaming one's place, with its time and event above the
        // words: keep the words where the player is reading them.
        final before = _topOf(_pendingNarrationKey);
        final following = _following;
        final unseen = following && (before == null || before > MediaQuery.sizeOf(context).height);
        _following = false;
        ref.invalidate(storiesProvider);
        if (unseen) {
          // It landed before the page reached it: show the new scene from its top.
          _reveal(turn);
          return;
        }
        WidgetsBinding.instance.addPostFrameCallback((_) {
          // The opening is read from the title page above it, which stays in view.
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
      case OutOfCredits(:final error, :final turn, :final picture):
        unawaited(_outOfCredits(error, turn: turn, picture: picture));
      case CreditsSpent():
        // Only a balance something has shown is out of date; the next one loads fresh.
        if (ref.exists(meProvider)) ref.read(meProvider.notifier).refreshQuietly();
      case TurnRefused(:final error):
        _snack(describeError(l10n, error).message);
    }
  }

  /// The out-of-credits sheet (K2). With the player's own key added (K6), what was refused goes
  /// again on that key.
  Future<void> _outOfCredits(ApiException error, {PendingTurn? turn, int? picture}) async {
    final outcome = await showOutOfCreditsSheet(context, error: error, retriesItself: true);
    if (!mounted || outcome != OutOfCreditsOutcome.keyAdded) return;
    if (turn != null) {
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
      default:
        _snack(context.l10n.storyUnknownCommand(name));
    }
  }

  void _choose(Choice choice) {
    _following = true;
    unawaited(_play.choose(choice));
  }

  void _stand(StandingAction action) {
    _following = true;
    unawaited(_play.stand(action.wire, label: action.label(context.l10n)));
  }

  Future<void> _retry() async {
    _following = true;
    final action = _play.pending?.input.action;
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
    // Words the player wrote are never lost: back in the box if it was emptied.
    if (failed.input.action case final action?) _giveBack(action);
  }

  void _openStatus() => context.push(Routes.status(widget.storyId), extra: _play.story?.genre);

  void _openMemory() => context.push(Routes.memory(widget.storyId), extra: _play.story?.genre);

  Future<void> _openSettings() async {
    final story = _play.story;
    if (story == null) return;
    final saved = await showStorySettings(context, story: story, save: _play.save);
    if ((saved ?? false) && mounted) _snack(context.l10n.settingsSaved);
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
      if (!mounted || !_scroll.hasClients) return;
      final position = _scroll.position;
      if (!position.hasContentDimensions) {
        // Not laid out yet, as under a page opened straight from a link: look again next frame.
        _reveal(turn, animate: animate, done: done, attempt: attempt, climbing: climbing);
        return;
      }
      final target = _sceneKeys[turn]?.currentContext;
      if (target != null || attempt >= 16) {
        done?.call();
        if (target == null) return;
        unawaited(
          Scrollable.ensureVisible(
            target,
            duration: animate ? Motion.of(context, Motion.slow) : Duration.zero,
            curve: Motion.standard,
          ),
        );
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

  /// Whether [turn] is the opening, right under the title page at the start of the feed.
  bool _opensPage(int turn) => turn <= 1 && _play.anchorTurn <= 1;

  /// Brings the streaming scene into view as it grows, but never past its own top, so the player
  /// reads it from the start at their own pace (S3). A turn that fails stays in view too.
  void _follow([int attempt = 0]) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_following || !_scroll.hasClients) return;
      if (_play.pending?.isOpening ?? false) return;
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
      final top = RenderAbstractViewport.maybeOf(card)?.getOffsetToReveal(card, 0).offset;
      final target = math.min(
        position.maxScrollExtent,
        (top ?? position.maxScrollExtent) - Space.lg,
      );
      if (target <= position.pixels + 1) return;
      _scroll.animateTo(target, duration: Motion.of(context, Motion.slow), curve: Motion.standard);
    });
  }

  /// Glides a saved scene up towards the top of the view, never past its own top and never back
  /// down the page.
  void _bringUp(int turn) {
    if (_opensPage(turn)) return;
    final card = _sceneKeys[turn]?.currentContext?.findRenderObject();
    if (card == null || !card.attached || !_scroll.hasClients) return;
    final position = _scroll.position;
    final top = RenderAbstractViewport.maybeOf(card)?.getOffsetToReveal(card, 0).offset;
    if (top == null) return;
    final target = math.min(position.maxScrollExtent, top - Space.lg);
    if (target <= position.pixels + 1) return;
    unawaited(
      _scroll.animateTo(target, duration: Motion.of(context, Motion.slow), curve: Motion.standard),
    );
  }

  bool _onScroll(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    if (notification is UserScrollNotification && notification.direction != ScrollDirection.idle) {
      _following = false;
    }
    final metrics = notification.metrics;
    // After a failed page, only the retry button asks again, so a lost connection isn't hammered.
    if (_landed && metrics.extentBefore < 900 && _play.olderError == null) {
      unawaited(_play.loadOlder());
    }
    // Only once the newest scene is well out of reach, so the pill doesn't sit over the words.
    final latest = _landed && metrics.extentAfter > metrics.viewportDimension * 1.5;
    if (latest != _showLatest) setState(() => _showLatest = latest);
    return false;
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
      child: Scaffold(
        appBar: AppBar(
          leading: backOr(context, Routes.library),
          titleSpacing: 0,
          title: _AppBarTitle(
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
          (null, final Object error) => ErrorState(error: error, onRetry: _play.reload),
          (null, _) => const Padding(
            padding: EdgeInsets.all(Space.gutter),
            child: ContentColumn.reading(
              child: SkeletonText(lines: 8, lineHeight: 14, spacing: 14),
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
              Composer(
                controller: _action,
                focusNode: _focus,
                enabled: story.scenes.isNotEmpty,
                busy: _play.busy,
                onSubmit: _send,
                mic: DictationButton(tracker: _mode),
                commands: [SlashCommand('status', l10n.slashStatus)],
              ),
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
        onDetails: () => showSceneDetails(context, scene),
        onMore: () => _sceneMenu(scene),
        onPictureError: () => _play.pictureFailed(scene.turn),
      ),
    );

    final top = _Top(
      story: story,
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
              if (startsHere) top else const SizedBox(height: Space.lg),
              for (final s in newer) scene(s),
              if (story.scenes.isEmpty && pending == null)
                ContentColumn.reading(child: _Begin(onBegin: _play.begin)),
              if (pending != null)
                ContentColumn.reading(
                  key: _pendingKey,
                  child: _PendingScene(
                    pending: pending,
                    narrationKey: _pendingNarrationKey,
                    onRetry: _retry,
                    onRephrase: _rephrase,
                    onAccount: () => unawaited(context.push(Routes.account)),
                    onDismiss: pending.isOpening ? null : () => _dismiss(pending),
                  ),
                ),
              if (last != null && !_play.busy)
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
                      onChoice: (choice) => _choose(
                        last.choices.firstWhere(
                          (c) => c.id == choice.id,
                          orElse: () => Choice(id: choice.id, label: choice.label),
                        ),
                      ),
                      onStanding: _stand,
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

/// The story's title and the world's date and time, always in sight (W10).
class _AppBarTitle extends StatelessWidget {
  const _AppBarTitle({required this.title, this.clock});

  final String title;
  final String? clock;

  @override
  Widget build(BuildContext context) {
    final clock = this.clock;
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: Space.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
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
                  style: context.lucidText.meta,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// The top of the feed: a title page once the opening is loaded, or the older scenes loading.
class _Top extends StatelessWidget {
  const _Top({
    required this.story,
    required this.reachedStart,
    required this.loading,
    required this.error,
    required this.onRetry,
  });

  final Story story;
  final bool reachedStart;
  final bool loading;
  final Object? error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    if (!reachedStart) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xl),
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
    return ContentColumn.reading(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xxl, Space.gutter, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (story.genre.isNotEmpty)
              Text(
                story.genre.toUpperCase(),
                textAlign: TextAlign.center,
                style: context.lucidText.overline,
              ),
            const SizedBox(height: Space.sm),
            Semantics(
              header: true,
              child: Text(
                story.title,
                textAlign: TextAlign.center,
                style: theme.textTheme.displaySmall,
              ),
            ),
            const SceneOrnament(),
          ],
        ),
      ),
    );
  }
}

/// A story with no scenes whose opening didn't start (out of credits, say): begin by hand.
class _Begin extends StatelessWidget {
  const _Begin({required this.onBegin});

  final VoidCallback onBegin;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.all(Space.gutter),
      child: Column(
        children: [
          Text(
            l10n.storyBeginning,
            textAlign: TextAlign.center,
            style: context.lucidText.playerAction,
          ),
          const SizedBox(height: Space.lg),
          FilledButton(onPressed: onBegin, child: Text(l10n.storyBegin)),
        ],
      ),
    );
  }
}

/// The turn in flight: the player's action, then the narration as it streams in, or what went
/// wrong.
class _PendingScene extends StatelessWidget {
  const _PendingScene({
    required this.pending,
    required this.narrationKey,
    required this.onRetry,
    required this.onRephrase,
    required this.onAccount,
    this.onDismiss,
  });

  final PendingTurn pending;
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
      playerAction: pending.label,
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
            : StreamingNarration(text: pending.text, streaming: true),
      ),
    );
  }
}

/// "Latest", when the player has scrolled far back.
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
          child: Material(
            color: theme.colorScheme.surfaceContainerHighest,
            shape: const StadiumBorder(),
            elevation: 0,
            child: InkWell(
              customBorder: const StadiumBorder(),
              onTap: onPressed,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 40),
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
    );
  }
}
