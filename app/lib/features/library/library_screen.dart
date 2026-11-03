import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../story/story_repository.dart';

/// Your stories (S8), newest first, with their covers and where each one stands.
class LibraryScreen extends ConsumerWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
          builder: (stories) => RefreshIndicator(
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
                          child: StoryTile(
                            title: story.title,
                            genre: story.genre,
                            imageUrl: story.coverUrl,
                            meta: story.worldTimeLabel == null
                                ? l10n.libraryTurn(story.turn)
                                : l10n.libraryMeta(story.turn, story.worldTimeLabel!),
                            onTap: () => context.push('/story/${story.id}'),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ),
      ),
    );
  }
}
