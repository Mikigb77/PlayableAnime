import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import '../account/account_repository.dart';
import '../create/draft_widgets.dart' show FieldLabel, InlineError;
import '../library/library.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// Carrying a story on as someone else after its ending (N6): a random person of its world, drawn
/// by the world's population odds, shown the way the create flow shows a character (G2, G16). The
/// player starts as them or draws someone else; nothing about them is edited. Drawing is one
/// drafting call, charged like a draft (K2).
///
/// The screen draws someone as it opens, unless someone was drawn already. Starting as them pops
/// the carried-on story back to the play screen, which plays their opening.
class SuccessorScreen extends ConsumerStatefulWidget {
  const SuccessorScreen({super.key, required this.storyId, this.story});

  final String storyId;

  /// The story as the play screen has it, to skip a fetch.
  final Story? story;

  @override
  ConsumerState<SuccessorScreen> createState() => _SuccessorScreenState();
}

class _SuccessorScreenState extends ConsumerState<SuccessorScreen> {
  Story? _story;
  Successor? _drawn;
  Object? _loadError;

  /// The last draw or start that failed, shown in place.
  Object? _error;
  bool _drawing = false;
  bool _starting = false;

  StoryRepository get _repository => ref.read(storyRepositoryProvider);

  @override
  void initState() {
    super.initState();
    if (widget.story case final story?) {
      _opened(story);
    } else {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final story = await _repository.get(widget.storyId, scenes: 1);
      if (!mounted) return;
      setState(() => _opened(story));
    } on Object catch (e) {
      if (mounted) setState(() => _loadError = e);
    }
  }

  /// Takes the story as it is: back to the play screen when someone already carries it on,
  /// otherwise who was drawn, or a first draw.
  void _opened(Story story) {
    _story = story;
    _drawn = story.successor;
    if (story.openingDue) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _done(story));
    } else if (_drawn == null && _available) {
      _drawing = true;
      _error = null;
      unawaited(_request());
    }
  }

  /// Someone can carry the story on: it reached an ending the player hasn't closed.
  bool get _available {
    final ending = _story?.ending;
    return ending != null && !ending.closed;
  }

  /// Draws someone (else), replacing whoever was drawn before.
  Future<void> _draw() async {
    if (_drawing || _starting) return;
    setState(() {
      _drawing = true;
      _error = null;
    });
    await _request();
  }

  Future<void> _request() async {
    try {
      final drawn = await _repository.drawSuccessor(widget.storyId);
      if (!mounted) return;
      _drawn = drawn;
      if (ref.exists(meProvider)) ref.read(meProvider.notifier).refreshQuietly();
    } on Object catch (e) {
      if (!mounted) return;
      _error = e;
      if (_ended(e)) unawaited(_load());
    } finally {
      if (mounted) setState(() => _drawing = false);
    }
  }

  Future<void> _start() async {
    final story = _story;
    if (story == null || _drawing || _starting) return;
    setState(() {
      _starting = true;
      _error = null;
    });
    try {
      final carried = await _repository.carryOn(widget.storyId, expectedVersion: story.version);
      if (!mounted) return;
      ref.invalidate(storiesProvider);
      _done(carried);
      return;
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.code == ApiErrorCode.versionConflict || _ended(e)) {
        // Played or carried on elsewhere: show the story as it is now.
        _snack(context.l10n.successorMovedOn);
        unawaited(_load());
      } else {
        _error = e;
      }
    } on Object catch (e) {
      if (mounted) _error = e;
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  /// The story can no longer be carried on from here: it isn't at an open ending any more.
  static bool _ended(Object error) => switch (error) {
    ApiException(code: ApiErrorCode.validationError, :final fields) => fields.any(
      (f) => f is Map && (f['type'] == 'not_ended' || f['type'] == 'closed'),
    ),
    _ => false,
  };

  /// Back to the play screen with the carried-on story, which plays the newcomer's opening.
  void _done(Story story) {
    if (!mounted) return;
    final router = GoRouter.of(context);
    if (router.canPop()) {
      context.pop(story);
    } else {
      context.go('/story/${widget.storyId}', extra: story);
    }
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final story = _story;
    final drawn = _drawn;
    return StoryTheme(
      genre: story?.genre ?? widget.story?.genre,
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.successorTitle)),
        body: switch ((story, drawn)) {
          (null, _) when _loadError != null => ErrorState(error: _loadError!, onRetry: _load),
          (null, _) => const Padding(
            padding: EdgeInsets.all(Space.gutter),
            child: ContentColumn.reading(child: SkeletonText(lines: 6, lineHeight: 14)),
          ),
          (final Story story, _) when !_available && !story.openingDue => EmptyState(
            icon: Icons.history_edu_outlined,
            title: l10n.successorUnavailable,
          ),
          (_, _) when _drawing => const _Drawing(),
          (_, null) => _FirstDrawFailed(error: _error, onDraw: _draw),
          (_, final Successor drawn) => _SuccessorView(successor: drawn),
        },
        bottomNavigationBar: drawn != null && _available && !_drawing
            ? _Actions(
                name: drawn.name,
                error: _error,
                starting: _starting,
                onStart: _start,
                onDrawAgain: _draw,
              )
            : null,
      ),
    );
  }
}

/// While someone is drawn: what is happening, honestly, without fake progress.
class _Drawing extends StatelessWidget {
  const _Drawing();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    return Semantics(
      liveRegion: true,
      label: l10n.successorDrawing,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: Space.gutter, vertical: Space.xxl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Center(child: CircularProgressIndicator()),
                const SizedBox(height: Space.xl),
                Text(
                  l10n.successorDrawing,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall,
                ),
                const SizedBox(height: Space.sm),
                Text(
                  l10n.successorDrawingBody,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The first draw failed: what went wrong, and a way to try again. Out of credits offers the
/// player's own key, and drawing again on it (K6).
class _FirstDrawFailed extends StatelessWidget {
  const _FirstDrawFailed({required this.error, required this.onDraw});

  final Object? error;
  final VoidCallback onDraw;

  @override
  Widget build(BuildContext context) => Center(
    child: SingleChildScrollView(
      padding: const EdgeInsets.all(Space.gutter),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: Layout.readingWidth),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (error case final error?) ...[
              InlineError(error, onKeyAdded: onDraw),
              const SizedBox(height: Space.lg),
            ],
            FilledButton(
              key: const ValueKey('successor.retry'),
              onPressed: onDraw,
              child: Text(context.l10n.retry),
            ),
          ],
        ),
      ),
    ),
  );
}

/// The person drawn, in the world's words: where they stand and how rare that is, who they are,
/// and the moment their story opens on.
class _SuccessorView extends StatelessWidget {
  const _SuccessorView({required this.successor});

  final Successor successor;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final name = successor.name.trim();
    final about = [
      if (successor.age case final age?) l10n.successorAge(age),
      if (successor.people case final people? when people.trim().isNotEmpty) people.trim(),
      if (successor.place case final place? when place.trim().isNotEmpty) place.trim(),
    ];
    final station = [
      l10n.successorStation(successor.station),
      if (successor.oneIn > 1) l10n.successorOneIn(successor.oneIn),
    ].join(' · ');
    return ListView(
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, Space.xxl),
      children: [
        ContentColumn.reading(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                l10n.successorIntro,
                style: theme.textTheme.bodyMedium!.copyWith(color: colors.textMuted),
              ),
              const SizedBox(height: Space.xl),
              Text(
                station.toUpperCase(),
                key: const ValueKey('successor.station'),
                style: context.lucidText.overline.copyWith(color: colors.accent),
              ),
              const SizedBox(height: Space.xs),
              Semantics(
                header: true,
                child: Text(
                  name.isEmpty ? l10n.successorStartNameless : name.asHeading,
                  key: const ValueKey('successor.name'),
                  style: theme.textTheme.headlineLarge,
                ),
              ),
              if (about.isNotEmpty) ...[
                const SizedBox(height: Space.xs),
                Text(
                  about.join(' · '),
                  style: context.lucidText.meta.copyWith(color: colors.textSecondary),
                ),
              ],
              if (successor.master) ...[const SizedBox(height: Space.lg), const _Master()],
              if (successor.lines.isNotEmpty) ...[
                FieldLabel(l10n.successorWhoTheyAre),
                Card(
                  margin: EdgeInsets.zero,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.lg, Space.xs),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        for (final line in successor.lines)
                          Padding(
                            padding: const EdgeInsets.only(bottom: Space.md),
                            child: Text(
                              line,
                              style: context.lucidText.narration.copyWith(
                                fontSize: 16,
                                height: 1.5,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
              if (successor.situation.trim().isNotEmpty) ...[
                FieldLabel(l10n.successorWhereItBegins),
                Container(
                  padding: const EdgeInsets.only(left: Space.lg),
                  decoration: BoxDecoration(
                    border: Border(
                      left: BorderSide(color: colors.accent.withValues(alpha: 0.6), width: 2),
                    ),
                  ),
                  child: Text(
                    successor.situation.trim(),
                    key: const ValueKey('successor.situation'),
                    style: context.lucidText.playerAction.copyWith(color: colors.textSecondary),
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// A hidden master (N6): far stronger than they look, which only the player knows.
class _Master extends StatelessWidget {
  const _Master();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Container(
      key: const ValueKey('successor.master'),
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: Radii.card,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(child: Icon(Icons.visibility_off_outlined, color: colors.accent)),
          const SizedBox(width: Space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l10n.successorMaster, style: theme.textTheme.titleSmall),
                const SizedBox(height: Space.xxs),
                Text(
                  l10n.successorMasterBody,
                  style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Start as the person drawn, or draw someone else, which uses credits.
class _Actions extends StatelessWidget {
  const _Actions({
    required this.name,
    required this.error,
    required this.starting,
    required this.onStart,
    required this.onDrawAgain,
  });

  final String name;
  final Object? error;
  final bool starting;
  final VoidCallback onStart;
  final VoidCallback onDrawAgain;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final shown = name.trim();
    return DecoratedBox(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
      ),
      child: SafeArea(
        top: false,
        child: Center(
          heightFactor: 1,
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: Layout.readingWidth),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(Space.gutter, Space.md, Space.gutter, Space.md),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (error case final error?) ...[
                    InlineError(error, onKeyAdded: onDrawAgain),
                    const SizedBox(height: Space.md),
                  ],
                  FilledButton.icon(
                    key: const ValueKey('successor.start'),
                    onPressed: starting ? null : onStart,
                    icon: starting
                        ? SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: theme.colorScheme.onSurface,
                            ),
                          )
                        : const Icon(Icons.play_arrow_rounded),
                    label: Text(
                      shown.isEmpty ? l10n.successorStartNameless : l10n.successorStart(shown),
                    ),
                  ),
                  const SizedBox(height: Space.sm),
                  OutlinedButton.icon(
                    key: const ValueKey('successor.drawAgain'),
                    onPressed: starting ? null : onDrawAgain,
                    icon: const Icon(Icons.casino_outlined),
                    label: Text(l10n.successorDrawAgain),
                  ),
                  const SizedBox(height: Space.xs),
                  Text(
                    l10n.successorDrawCost,
                    textAlign: TextAlign.center,
                    style: context.lucidText.meta.copyWith(color: colors.textMuted),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
