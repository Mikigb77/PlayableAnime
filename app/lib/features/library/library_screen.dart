import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'library.dart';

/// Your stories (S8), most recently played first, with their covers, the turn and the in-world
/// time each one stands at (W10). A story can be deleted, after a confirmation, for good.
class LibraryScreen extends ConsumerStatefulWidget {
  const LibraryScreen({super.key});

  @override
  ConsumerState<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends ConsumerState<LibraryScreen> {
  /// Stories being deleted, or deleted before the list caught up: hidden at once.
  final _gone = <String>{};

  Future<bool> _confirm(StorySummary story) async {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(l10n.libraryDeleteTitle(story.title)),
        content: Text(l10n.libraryDeleteBody),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: Text(l10n.cancel)),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: scheme.error),
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(l10n.libraryDeleteConfirm),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  Future<void> _delete(StorySummary story) async {
    final l10n = context.l10n;
    final messenger = ScaffoldMessenger.of(context);
    setState(() => _gone.add(story.id));
    String message;
    try {
      await ref.read(libraryRepositoryProvider).delete(story.id);
      message = l10n.libraryDeleted(story.title);
    } on Object catch (e) {
      if (e case ApiException(code: ApiErrorCode.notFound)) {
        // Already gone, which is what the player wanted.
        message = l10n.libraryDeleted(story.title);
      } else {
        if (mounted) setState(() => _gone.remove(story.id));
        message = l10n.libraryDeleteFailed(story.title, describeError(l10n, e).message);
      }
    }
    // The player may have left the Library meanwhile; the list reloads when they come back.
    if (mounted) ref.invalidate(storiesProvider);
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _confirmAndDelete(StorySummary story) async {
    if (await _confirm(story) && mounted) await _delete(story);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final header = ContentColumn(
      child: PageHeader(
        brand: true,
        title: l10n.libraryHeadline,
        accentTitle: l10n.libraryHeadlineAccent,
      ),
    );
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(child: Ambient()),
          SafeArea(
            bottom: false,
            child: AsyncValueView(
              value: ref.watch(storiesProvider),
              onRetry: () => ref.invalidate(storiesProvider),
              loading: (_) => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  header,
                  const Expanded(
                    child: ContentColumn(child: SkeletonList(count: 4, imageHeight: 80)),
                  ),
                ],
              ),
              builder: (all) {
                final stories = [
                  for (final story in all)
                    if (!_gone.contains(story.id)) story,
                ];
                return RefreshIndicator(
                  onRefresh: () => ref.refresh(storiesProvider.future),
                  child: stories.isEmpty
                      ? ListView(
                          children: [
                            header,
                            const SizedBox(height: Space.xxl),
                            EmptyState(
                              icon: Icons.auto_stories_outlined,
                              title: l10n.libraryEmptyTitle,
                              message: l10n.libraryEmptyBody,
                              actionLabel: l10n.libraryEmptyAction,
                              onAction: () => context.go('/discover'),
                            ),
                            const PageEnd(),
                          ],
                        )
                      : CustomScrollView(
                          slivers: [
                            SliverToBoxAdapter(child: RiseIn(child: header)),
                            _StoryGrid(
                              count: stories.length,
                              itemBuilder: (context, i) {
                                final story = stories[i];
                                return _StoryRow(
                                  story: story,
                                  confirm: () => _confirm(story),
                                  onDelete: () => _delete(story),
                                  onDeleteAsked: () => _confirmAndDelete(story),
                                );
                              },
                            ),
                            const SliverToBoxAdapter(child: PageEnd()),
                          ],
                        ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// A story's row: open it with a tap, swipe it away or use its menu to delete it.
class _StoryRow extends StatelessWidget {
  const _StoryRow({
    required this.story,
    required this.confirm,
    required this.onDelete,
    required this.onDeleteAsked,
  });

  final StorySummary story;
  final Future<bool> Function() confirm;

  /// Deletes after a swipe the player already confirmed.
  final VoidCallback onDelete;

  /// Asks, then deletes, from the menu.
  final VoidCallback onDeleteAsked;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    return Dismissible(
      key: ValueKey(story.id),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) => confirm(),
      onDismissed: (_) => onDelete(),
      background: Container(
        alignment: AlignmentDirectional.centerEnd,
        padding: const EdgeInsets.symmetric(horizontal: Space.xl),
        decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: Radii.cover),
        child: Icon(Icons.delete_outline_rounded, color: scheme.onErrorContainer),
      ),
      child: StoryTile(
        title: story.title,
        genre: story.genre,
        accent: story.accent,
        imageUrl: story.coverUrl,
        meta: storyMeta(l10n, story),
        onTap: () => context.push('/story/${Uri.encodeComponent(story.id)}'),
        trailing: PopupMenuButton<String>(
          tooltip: l10n.libraryOptions,
          // The row is a painting on night ink in both themes.
          icon: const Icon(Icons.more_vert_rounded, color: Palette.inkTextPrimary),
          onSelected: (_) => onDeleteAsked(),
          itemBuilder: (context) => [
            PopupMenuItem(
              value: 'delete',
              child: Row(
                children: [
                  Icon(Icons.delete_outline_rounded, color: scheme.error),
                  const SizedBox(width: Space.md),
                  Text(l10n.libraryDelete),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Where a story stands, under its title: its turn and the in-world time (W10), that it is ready
/// to begin, or that it ended.
String storyMeta(AppLocalizations l10n, StorySummary story) =>
    switch ((story.turn, story.worldTimeLabel)) {
      _ when story.ended => l10n.libraryEnded(story.turn),
      (0, final time?) => l10n.libraryNotBegun(time),
      (_, final time?) => l10n.libraryMeta(story.turn, time),
      _ => l10n.libraryTurn(story.turn),
    };

/// The stories in the content column: one under another on a phone, two side by side from
/// tablet width, so a row is never stretched across a wide screen. Rows side by side share their
/// height, which grows with the text size.
class _StoryGrid extends StatelessWidget {
  const _StoryGrid({required this.count, required this.itemBuilder});

  final int count;
  final IndexedWidgetBuilder itemBuilder;

  /// The content width (inside the gutters) from which stories go two across.
  static const _twoColumns = 640.0;

  @override
  Widget build(BuildContext context) => SliverLayoutBuilder(
    builder: (context, constraints) {
      final width = constraints.crossAxisExtent.clamp(0.0, Layout.contentWidth);
      final columns = width - Space.gutter * 2 >= _twoColumns ? 2 : 1;
      final rows = (count + columns - 1) ~/ columns;
      final side = (constraints.crossAxisExtent - width) / 2 + Space.gutter;
      return SliverPadding(
        padding: EdgeInsets.symmetric(horizontal: side),
        sliver: SliverList.separated(
          itemCount: rows,
          separatorBuilder: (_, _) => const SizedBox(height: 14),
          itemBuilder: (context, row) {
            if (columns == 1) return itemBuilder(context, row);
            final first = row * columns;
            return IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var i = first; i < first + columns; i++) ...[
                    if (i > first) const SizedBox(width: Space.md),
                    Expanded(child: i < count ? itemBuilder(context, i) : const SizedBox()),
                  ],
                ],
              ),
            );
          },
        ),
      );
    },
  );
}
