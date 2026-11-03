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
      child: PageHeader(title: l10n.libraryTitle, subtitle: l10n.librarySubtitle),
    );
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: AsyncValueView(
          value: ref.watch(storiesProvider),
          onRetry: () => ref.invalidate(storiesProvider),
          loading: (_) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              header,
              const Expanded(child: ContentColumn(child: SkeletonList(count: 4, imageHeight: 80))),
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
                      ],
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.only(bottom: Space.xxxl),
                      itemCount: stories.length + 1,
                      separatorBuilder: (_, i) => SizedBox(height: i == 0 ? 0 : Space.md),
                      itemBuilder: (context, i) {
                        if (i == 0) return header;
                        final story = stories[i - 1];
                        return ContentColumn(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                            child: _StoryRow(
                              story: story,
                              confirm: () => _confirm(story),
                              onDelete: () => _delete(story),
                              onDeleteAsked: () => _confirmAndDelete(story),
                            ),
                          ),
                        );
                      },
                    ),
            );
          },
        ),
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
    final time = story.worldTimeLabel;
    final meta = switch ((story.turn, time)) {
      (0, final time?) => l10n.libraryNotBegun(time),
      (_, final time?) => l10n.libraryMeta(story.turn, time),
      _ => l10n.libraryTurn(story.turn),
    };
    return Dismissible(
      key: ValueKey(story.id),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) => confirm(),
      onDismissed: (_) => onDelete(),
      background: Container(
        alignment: AlignmentDirectional.centerEnd,
        padding: const EdgeInsets.symmetric(horizontal: Space.xl),
        decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: Radii.card),
        child: Icon(Icons.delete_outline_rounded, color: scheme.onErrorContainer),
      ),
      child: StoryTile(
        title: story.title,
        genre: story.genre,
        imageUrl: story.coverUrl,
        meta: meta,
        onTap: () => context.push('/story/${Uri.encodeComponent(story.id)}'),
        trailing: PopupMenuButton<String>(
          tooltip: l10n.libraryOptions,
          icon: Icon(Icons.more_vert_rounded, color: context.lucid.textMuted),
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
