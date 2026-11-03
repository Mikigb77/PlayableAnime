import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/api/turn_events.dart';
import '../../core/l10n.dart';
import '../../core/navigation.dart';
import '../../design/design.dart';
import '../voice/dictation_button.dart';
import '../voice/input_mode.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// The play screen: the scene feed, the newest scene streaming in as it is written (S3), the
/// suggested choices and standing actions (S2), and the composer with dictation (V1). The play
/// screen work (WS14) builds the full version on this: scene details, report, settings, retries.
class StoryScreen extends ConsumerStatefulWidget {
  const StoryScreen({super.key, required this.storyId, this.initialStory});

  final String storyId;

  /// Passed when navigating straight from story creation, to skip a fetch.
  final Story? initialStory;

  @override
  ConsumerState<StoryScreen> createState() => _StoryScreenState();
}

class _StoryScreenState extends ConsumerState<StoryScreen> {
  final _action = TextEditingController();
  late final _mode = InputModeTracker(_action);
  final _focus = FocusNode();
  final _scroll = ScrollController();
  final _sceneKeys = <int, GlobalKey>{};
  late Story? _story = widget.initialStory;
  Object? _loadError;
  bool _landed = false;

  // The turn in flight.
  bool _busy = false;
  String? _pendingAction;
  String _streamed = '';
  TurnInput? _failedTurn;
  ApiException? _turnError;
  StreamSubscription<TurnEvent>? _turn;

  @override
  void initState() {
    super.initState();
    if (_story == null) {
      _load();
    } else {
      _landOnLatest();
    }
  }

  @override
  void dispose() {
    _turn?.cancel();
    _mode.dispose();
    _action.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final story = await ref.read(storyRepositoryProvider).get(widget.storyId);
      if (!mounted) return;
      setState(() => _story = story);
      _landOnLatest();
    } catch (e) {
      if (mounted) setState(() => _loadError = e);
    }
  }

  void _sendText(String text) {
    if (text.startsWith('/status')) {
      _action.clear();
      context.push('/story/${widget.storyId}/status', extra: _story?.genre);
      return;
    }
    _takeTurn(TurnInput.action(text, inputMode: _mode.mode.wire), label: text);
  }

  Future<void> _takeTurn(TurnInput input, {required String label}) async {
    final story = _story;
    if (story == null || _busy) return;
    setState(() {
      _busy = true;
      _pendingAction = label;
      _streamed = '';
      _turnError = null;
      _failedTurn = null;
    });
    _scrollToEnd();
    try {
      final events = await ref
          .read(storyRepositoryProvider)
          .takeTurn(widget.storyId, input, expectedVersion: story.version);
      if (input.kind == 'action') _action.clear();
      _turn = events.listen((event) => _onEvent(event, input), onDone: () => _turn = null);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _pendingAction = null;
      });
      if (e.code == ApiErrorCode.versionConflict) unawaited(_load());
      final copy = describeError(context.l10n, e);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(copy.message)));
    }
  }

  void _onEvent(TurnEvent event, TurnInput input) {
    if (!mounted) return;
    switch (event) {
      case TurnStarted():
        break;
      case NarrationDelta(:final text):
        setState(() => _streamed += text);
        _scrollToEnd(onlyIfNear: true);
      case NarrationReset():
        setState(() => _streamed = '');
      case SceneCompleted(:final scene, :final version, :final clock):
        setState(() {
          _story = _story!.withScene(
            Scene.fromJson(scene),
            version: version,
            clockLabel: clock['label'] as String?,
          );
          _busy = false;
          _pendingAction = null;
          _streamed = '';
        });
        ref.invalidate(storiesProvider);
      case TurnFailed(:final error):
        // Nothing was saved: drop the partial scene and offer the same turn again.
        setState(() {
          _busy = false;
          _streamed = '';
          _turnError = error;
          _failedTurn = input;
        });
    }
  }

  /// Opens the story where the player left it: at the top of the newest scene. The feed is built
  /// lazily, so this first jumps to the end until that scene is laid out.
  void _landOnLatest([int attempt = 0]) {
    if (_landed) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final turn = _story?.scenes.lastOrNull?.turn;
      if (!mounted || !_scroll.hasClients || turn == null) return;
      final target = _sceneKeys[turn]?.currentContext;
      if (target != null) {
        _landed = true;
        Scrollable.ensureVisible(target);
      } else if (attempt < 8) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
        _landOnLatest(attempt + 1);
      }
    });
  }

  void _scrollToEnd({bool onlyIfNear = false}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final position = _scroll.position;
      if (onlyIfNear && position.maxScrollExtent - position.pixels > 240) return;
      _scroll.animateTo(
        position.maxScrollExtent,
        duration: Motion.of(context, Motion.slow),
        curve: Motion.standard,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final story = _story;
    return StoryTheme(
      genre: story?.genre,
      child: Scaffold(
        appBar: AppBar(
          leading: backOr(context, '/library'),
          title: Text(story?.title ?? l10n.storyFallbackTitle),
          actions: [
            IconButton(
              tooltip: l10n.storyStatus,
              icon: const Icon(Icons.badge_outlined),
              onPressed: () => context.push('/story/${widget.storyId}/status', extra: story?.genre),
            ),
            IconButton(
              tooltip: l10n.storyMemory,
              icon: const Icon(Icons.auto_stories_outlined),
              onPressed: () => context.push('/story/${widget.storyId}/memory', extra: story?.genre),
            ),
          ],
        ),
        body: switch ((story, _loadError)) {
          (null, final Object error) => ErrorState(error: error, onRetry: _load),
          (null, _) => const Padding(
            padding: EdgeInsets.all(Space.gutter),
            child: ContentColumn.reading(
              child: SkeletonText(lines: 8, lineHeight: 14, spacing: 14),
            ),
          ),
          (final Story story, _) => Column(
            children: [
              Expanded(child: _feed(context, story)),
              Composer(
                controller: _action,
                focusNode: _focus,
                busy: _busy,
                onSubmit: _sendText,
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
    final l10n = context.l10n;
    final last = story.scenes.isEmpty ? null : story.scenes.last;
    final showChoices = !_busy && _turnError == null && last != null;
    return ListView(
      controller: _scroll,
      padding: const EdgeInsets.only(top: Space.lg, bottom: Space.xl),
      children: [
        if (story.scenes.isEmpty && !_busy)
          Padding(
            padding: const EdgeInsets.all(Space.xxl),
            child: Text(
              l10n.storyBeginning,
              textAlign: TextAlign.center,
              style: context.lucidText.playerAction,
            ),
          ),
        for (final (i, scene) in story.scenes.indexed)
          ContentColumn.reading(
            key: _sceneKeys.putIfAbsent(scene.turn, GlobalKey.new),
            child: _SceneView(
              storyId: story.id,
              scene: scene,
              ornament: i < story.scenes.length - 1 || _busy || _turnError != null,
              onPicture: (image) => setState(() {
                final scenes = [...story.scenes];
                final index = scenes.indexWhere((s) => s.turn == scene.turn);
                if (index >= 0) scenes[index] = scenes[index].withImage(image);
                _story = story.copyWith(scenes: scenes);
              }),
            ),
          ),
        if (_pendingAction != null && (_busy || _turnError != null))
          ContentColumn.reading(
            child: SceneCard(
              playerAction: _pendingAction,
              ornament: false,
              narration: _turnError == null
                  ? StreamingNarration(text: _streamed, streaming: true)
                  : _TurnErrorView(
                      error: _turnError!,
                      onRetry: _failedTurn == null
                          ? null
                          : () => _takeTurn(_failedTurn!, label: _pendingAction!),
                    ),
            ),
          ),
        if (showChoices)
          ContentColumn.reading(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
              child: StoryChoices(
                choices: [
                  for (final c in last.choices)
                    StoryChoice(id: c.id, label: c.label, kind: ChoiceKind.fromWire(c.kind)),
                ],
                standing: [
                  for (final s in last.standingActions)
                    ?StandingAction.values.where((a) => a.wire == s).firstOrNull,
                ],
                onChoice: (choice) => _takeTurn(TurnInput.choice(choice.id), label: choice.label),
                onStanding: (action) =>
                    _takeTurn(TurnInput.standing(action.wire), label: action.label(l10n)),
              ),
            ),
          ),
      ],
    );
  }
}

class _SceneView extends StatelessWidget {
  const _SceneView({
    required this.storyId,
    required this.scene,
    required this.ornament,
    required this.onPicture,
  });

  final String storyId;
  final Scene scene;
  final bool ornament;
  final ValueChanged<SceneImage> onPicture;

  @override
  Widget build(BuildContext context) {
    final image = scene.image;
    return SceneCard(
      playerAction: scene.playerAction,
      spokenAction: scene.spoken,
      ornament: ornament,
      time:
          scene.durationLabel == null && scene.timeLabel == null && scene.personalTimeLabel == null
          ? null
          : TimeChip(
              duration: scene.durationLabel,
              label: scene.timeLabel,
              personalLabel: scene.personalTimeLabel,
            ),
      event: scene.eventTitle == null
          ? null
          : EventBadge(size: EventSize.fromWire(scene.eventSize), title: scene.eventTitle!),
      picture: image == null
          ? null
          : ScenePicture(storyId: storyId, turn: scene.turn, image: image, onChanged: onPicture),
      narration: NarrationText(scene.narration),
      portraits: scene.portraits.isEmpty
          ? null
          : PortraitStack(
              portraits: [for (final p in scene.portraits) PortraitRef(name: p.name, url: p.url)],
            ),
    );
  }
}

/// A scene's picture: shown when ready, asked for when planned, and asked again while it is being
/// painted (M3). The text never waits for it.
class ScenePicture extends ConsumerStatefulWidget {
  const ScenePicture({
    super.key,
    required this.storyId,
    required this.turn,
    required this.image,
    required this.onChanged,
  });

  final String storyId;
  final int turn;
  final SceneImage image;
  final ValueChanged<SceneImage> onChanged;

  @override
  ConsumerState<ScenePicture> createState() => _ScenePictureState();
}

class _ScenePictureState extends ConsumerState<ScenePicture> {
  static const _interval = Duration(milliseconds: 1500);
  static const _maxTries = 20;
  Timer? _timer;
  int _tries = 0;

  @override
  void initState() {
    super.initState();
    if (widget.image.status == 'planned') _ask();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _ask() async {
    _tries++;
    SceneImage result;
    try {
      result = await ref.read(storyRepositoryProvider).picture(widget.storyId, widget.turn);
    } on ApiException catch (e) {
      // A picture is never an error (M3): retry quietly while it might work, then give up.
      result = SceneImage(status: e.code.isRetryable && _tries < _maxTries ? 'planned' : 'skipped');
    }
    if (!mounted) return;
    if (result.status == 'planned' && _tries < _maxTries) {
      _timer = Timer(_interval, _ask);
    } else {
      widget.onChanged(result.status == 'planned' ? const SceneImage(status: 'skipped') : result);
    }
  }

  @override
  Widget build(BuildContext context) {
    final image = widget.image;
    return PictureSlot(
      status: switch (image.status) {
        'ready' => PictureStatus.ready,
        'skipped' => PictureStatus.skipped,
        _ => PictureStatus.pending,
      },
      url: image.url,
      // Edge to edge on phones; rounded once the reading column floats in a wider screen.
      borderRadius: MediaQuery.sizeOf(context).width > Layout.readingWidth
          ? Radii.picture
          : BorderRadius.zero,
    );
  }
}

class _TurnErrorView extends StatelessWidget {
  const _TurnErrorView({required this.error, this.onRetry});

  final ApiException error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final copy = describeError(context.l10n, error);
    return Container(
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: theme.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(Radii.lg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            copy.title,
            style: theme.textTheme.titleMedium!.copyWith(color: theme.colorScheme.onErrorContainer),
          ),
          const SizedBox(height: Space.xs),
          Text(
            copy.message,
            style: theme.textTheme.bodyMedium!.copyWith(color: theme.colorScheme.onErrorContainer),
          ),
          if (onRetry != null) ...[
            const SizedBox(height: Space.md),
            FilledButton.tonal(onPressed: onRetry, child: Text(context.l10n.retry)),
          ],
        ],
      ),
    );
  }
}
