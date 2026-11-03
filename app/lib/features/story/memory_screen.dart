import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// What the character knows, in the world's words (C6). The memory work (WS15) builds the full
/// screen on the v1 `MemoryView`.
class MemoryScreen extends ConsumerWidget {
  const MemoryScreen({super.key, required this.storyId, this.genre});

  final String storyId;

  /// The story's genre, for its accent, when the play screen opened this page.
  final String? genre;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    return StoryTheme(
      genre: genre,
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.memoryTitle)),
        body: AsyncValueView(
          value: ref.watch(memoryProvider(storyId)),
          onRetry: () => ref.invalidate(memoryProvider(storyId)),
          builder: (memory) => ListView(
            padding: const EdgeInsets.only(bottom: Space.xxxl),
            children: [
              ContentColumn(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Space.gutter, 0, Space.gutter, Space.sm),
                  child: Text(
                    l10n.memorySubtitle,
                    style: Theme.of(
                      context,
                    ).textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
                  ),
                ),
              ),
              for (final section in memory.sections)
                if (section.items.isNotEmpty)
                  ContentColumn(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        SectionLabel(_title(l10n, section.kind)),
                        for (final item in section.items)
                          _MemoryTile(item: item, kind: section.kind),
                      ],
                    ),
                  ),
            ],
          ),
        ),
      ),
    );
  }

  static String _title(AppLocalizations l10n, MemorySectionKind kind) => switch (kind) {
    MemorySectionKind.you => l10n.memoryYou,
    MemorySectionKind.people => l10n.memoryPeople,
    MemorySectionKind.places => l10n.memoryPlaces,
    MemorySectionKind.factions => l10n.memoryFactions,
    MemorySectionKind.goals => l10n.memoryGoals,
    MemorySectionKind.leads => l10n.memoryLeads,
    MemorySectionKind.rumors => l10n.memoryRumors,
    MemorySectionKind.deeds => l10n.memoryDeeds,
    MemorySectionKind.threads => l10n.memoryThreads,
    MemorySectionKind.summary => l10n.memorySummary,
    MemorySectionKind.facts => l10n.memoryFacts,
  };
}

class _MemoryTile extends StatelessWidget {
  const _MemoryTile({required this.item, required this.kind});

  final MemoryItem item;
  final MemorySectionKind kind;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final person = kind == MemorySectionKind.you || kind == MemorySectionKind.people;
    final leading = switch (kind) {
      _ when person => PortraitAvatar(
        name: item.title,
        url: item.imageUrl,
        size: 44,
        ring: kind == MemorySectionKind.you,
      ),
      MemorySectionKind.places when item.imageUrl != null => ClipRRect(
        borderRadius: BorderRadius.circular(Radii.sm),
        child: SizedBox.square(
          dimension: 44,
          child: Image(image: appImage(item.imageUrl!, cacheWidth: 132), fit: BoxFit.cover),
        ),
      ),
      _ => null,
    };
    final rumor = kind == MemorySectionKind.rumors;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.gutter, vertical: Space.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (leading != null) ...[leading, const SizedBox(width: Space.md)],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  style:
                      (kind == MemorySectionKind.summary
                              ? context.lucidText.narration.copyWith(fontSize: 16)
                              : theme.textTheme.titleMedium!)
                          .copyWith(
                            decoration: item.muted ? TextDecoration.lineThrough : null,
                            color: item.muted ? colors.textMuted : null,
                          ),
                ),
                for (final line in item.lines)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      line,
                      style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                    ),
                  ),
                if (rumor)
                  Padding(
                    padding: const EdgeInsets.only(top: Space.xs),
                    child: Text(
                      l10n.memoryUnconfirmed.toUpperCase(),
                      style: context.lucidText.overline.copyWith(color: colors.caution),
                    ),
                  ),
              ],
            ),
          ),
          if (item.trailing case final trailing?) ...[
            const SizedBox(width: Space.md),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 140),
              child: Text(trailing, textAlign: TextAlign.end, style: context.lucidText.meta),
            ),
          ],
        ],
      ),
    );
  }
}
