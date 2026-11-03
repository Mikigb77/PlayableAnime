import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_repository.dart';

/// `/status` (S5): the character sheet in the world's words, reputation, and the date and time
/// (W10). The play screen work (WS14) extends it.
class StatusScreen extends ConsumerWidget {
  const StatusScreen({super.key, required this.storyId, this.genre});

  final String storyId;

  /// The story's genre, for its accent, when the play screen opened this page.
  final String? genre;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return StoryTheme(
      genre: genre,
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.statusTitle)),
        body: AsyncValueView(
          value: ref.watch(statusProvider(storyId)),
          onRetry: () => ref.invalidate(statusProvider(storyId)),
          builder: (status) => ListView(
            padding: const EdgeInsets.fromLTRB(Space.gutter, 0, Space.gutter, Space.xxxl),
            children: [
              ContentColumn.reading(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        PortraitAvatar(name: status.name, size: 56, ring: true),
                        const SizedBox(width: Space.lg),
                        Expanded(child: Text(status.name, style: theme.textTheme.headlineMedium)),
                      ],
                    ),
                    if (status.clockLabel case final label?) ...[
                      const SizedBox(height: Space.lg),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TimeChip(duration: label),
                      ),
                    ],
                    const SizedBox(height: Space.lg),
                    for (final line in status.lines)
                      Padding(
                        padding: const EdgeInsets.only(bottom: Space.sm),
                        child: Text(
                          line,
                          style: context.lucidText.narration.copyWith(fontSize: 17),
                        ),
                      ),
                    if (status.reputation.isNotEmpty) ...[
                      SectionLabel(
                        l10n.statusReputation,
                        padding: const EdgeInsets.only(top: Space.xl, bottom: Space.md),
                      ),
                      for (final (name, label) in status.reputation)
                        Padding(
                          padding: const EdgeInsets.only(bottom: Space.md),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(name, style: theme.textTheme.titleMedium),
                              Text(
                                label,
                                style: theme.textTheme.bodyMedium!.copyWith(
                                  color: colors.textSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                    ],
                    if (status.since.isNotEmpty) ...[
                      SectionLabel(
                        l10n.statusSince,
                        padding: const EdgeInsets.only(top: Space.xl, bottom: Space.md),
                      ),
                      for (final (text, ago) in status.since)
                        Padding(
                          padding: const EdgeInsets.only(bottom: Space.md),
                          child: Row(
                            children: [
                              Expanded(child: Text(text, style: theme.textTheme.bodyLarge)),
                              const SizedBox(width: Space.md),
                              Text(ago, style: context.lucidText.meta),
                            ],
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
