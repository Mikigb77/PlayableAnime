import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// `/status` (S5): the character sheet in the world's words (G16), where they stand with people
/// and factions (A8, W3), the world's date and time, and how long ago key events happened (W10).
class StatusScreen extends ConsumerWidget {
  const StatusScreen({super.key, required this.storyId, this.genre});

  final String storyId;

  /// The story's genre, for its accent, when the play screen opened this page.
  final String? genre;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    return StoryTheme(
      genre: genre,
      child: Scaffold(
        appBar: AppBar(title: Text(l10n.statusTitle)),
        body: AsyncValueView(
          value: ref.watch(statusProvider(storyId)),
          onRetry: () => ref.invalidate(statusProvider(storyId)),
          loading: (_) => const Padding(
            padding: EdgeInsets.all(Space.gutter),
            child: ContentColumn.reading(child: SkeletonText(lines: 6, lineHeight: 14)),
          ),
          builder: (status) => RefreshIndicator(
            onRefresh: () => ref.refresh(statusProvider(storyId).future),
            child: _StatusView(status: status),
          ),
        ),
      ),
    );
  }
}

class _StatusView extends StatelessWidget {
  const _StatusView({required this.status});

  final StatusData status;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    const label = EdgeInsets.only(top: Space.xxl, bottom: Space.md);
    final empty = status.lines.isEmpty && status.reputation.isEmpty && status.since.isEmpty;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, Space.xxxl),
      children: [
        ContentColumn.reading(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  PortraitAvatar(name: status.name, size: 56, ring: true),
                  const SizedBox(width: Space.lg),
                  Expanded(
                    child: Semantics(
                      header: true,
                      child: Text(status.name, style: theme.textTheme.headlineMedium),
                    ),
                  ),
                ],
              ),
              if (status.clockLabel case final clock?) ...[
                const SizedBox(height: Space.xl),
                _Now(label: clock),
              ],
              if (status.lines.isNotEmpty) const SizedBox(height: Space.xl),
              for (final line in status.lines)
                Padding(
                  padding: const EdgeInsets.only(bottom: Space.md),
                  child: Text(line, style: context.lucidText.narration.copyWith(fontSize: 17)),
                ),
              if (status.reputation.isNotEmpty) ...[
                SectionLabel(l10n.statusReputation, padding: label),
                for (final (name, standing) in status.reputation)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.sm),
                    child: Container(
                      padding: const EdgeInsets.all(Space.lg),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerLow,
                        borderRadius: Radii.card,
                        border: Border.all(color: theme.colorScheme.outlineVariant),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(name, style: theme.textTheme.titleMedium),
                          const SizedBox(height: Space.xxs),
                          Text(
                            standing,
                            style: theme.textTheme.bodyMedium!.copyWith(
                              color: colors.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
              if (status.since.isNotEmpty) ...[
                SectionLabel(l10n.statusSince, padding: label),
                for (final (i, (text, ago)) in status.since.indexed)
                  _SinceRow(text: text, ago: ago, last: i == status.since.length - 1),
              ],
              if (empty)
                Padding(
                  padding: const EdgeInsets.only(top: Space.xxl),
                  child: Text(
                    l10n.statusEmpty,
                    style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The world's date and time now (W10).
class _Now extends StatelessWidget {
  const _Now({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
      decoration: BoxDecoration(color: colors.accentSoft, borderRadius: Radii.card),
      child: Row(
        children: [
          Icon(Icons.schedule_rounded, size: 20, color: colors.onAccentSoft),
          const SizedBox(width: Space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.statusNow.toUpperCase(),
                  style: context.lucidText.overline.copyWith(color: colors.onAccentSoft),
                ),
                Text(
                  label,
                  style: Theme.of(
                    context,
                  ).textTheme.titleLarge!.copyWith(color: colors.onAccentSoft),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One key event and how long ago it happened, on a quiet timeline.
class _SinceRow extends StatelessWidget {
  const _SinceRow({required this.text, required this.ago, required this.last});

  final String text;
  final String ago;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 16,
            child: Column(
              children: [
                const SizedBox(height: 7),
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(color: colors.accent, shape: BoxShape.circle),
                ),
                if (!last)
                  Expanded(child: Container(width: 2, color: theme.colorScheme.outlineVariant)),
              ],
            ),
          ),
          const SizedBox(width: Space.md),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : Space.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(text, style: theme.textTheme.bodyLarge),
                  const SizedBox(height: Space.xxs),
                  Text(ago, style: context.lucidText.meta),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
