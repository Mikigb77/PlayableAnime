import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import 'sheet_view.dart';
import 'story_models.dart';
import 'story_repository.dart';

/// `/status` (S5): the character sheet in the world's words (G13, G16), laid out in parts: who
/// they are and how they are, where they stand on the world's ladders (G18), then what they
/// carry, their skills, their powers and techniques and what they are like, a part at a time.
/// Under it, where they stand with people and factions (A8, W3) and how long ago key events
/// happened (W10).
class StatusScreen extends ConsumerWidget {
  const StatusScreen({super.key, required this.storyId, this.accent});

  final String storyId;

  /// The story's accent (its genre's, or the one the player chose, S13) when the play screen
  /// opened this page. The app's own otherwise.
  final GenreAccent? accent;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    return StoryTheme.accent(
      accent: accent ?? GenreAccent.lucid,
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
    final sheet = status.sheet;
    const label = EdgeInsets.only(top: Space.xxl, bottom: Space.md);
    final empty =
        sheet == null && status.lines.isEmpty && status.reputation.isEmpty && status.since.isEmpty;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, Space.xxxl),
      children: [
        ContentColumn.reading(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _Header(status: status),
              if (sheet != null) ...[
                const SizedBox(height: Space.lg),
                SheetConditionView(condition: sheet.condition),
                if (sheet.paths.isNotEmpty) SectionLabel(l10n.sheetPath, padding: label),
                for (final (i, path) in sheet.paths.indexed)
                  Padding(
                    padding: EdgeInsets.only(top: i == 0 ? 0 : Space.sm),
                    child: SheetPathCard(path: path),
                  ),
                const SizedBox(height: Space.xl),
                SheetTabs(sheet: sheet),
              ] else ...[
                // A server from before the sheet came in parts sends it as plain lines.
                if (status.lines.isNotEmpty) const SizedBox(height: Space.xl),
                for (final line in status.lines)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.md),
                    child: Text(line, style: context.lucidText.narration.copyWith(fontSize: 17)),
                  ),
              ],
              if (status.reputation.isNotEmpty) ...[
                SectionLabel(l10n.statusReputation, padding: label),
                for (final (name, standing) in status.reputation)
                  _Standing(name: name, standing: standing),
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

/// Who they are: their portrait, their name, their place in the world in a few words, the
/// world's date and time (W10), and how they come across.
class _Header extends StatelessWidget {
  const _Header({required this.status});

  final StatusData status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final sheet = status.sheet;
    final about = sheet?.about ?? const <String>[];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            PortraitAvatar(name: status.name, url: status.portraitUrl, size: 76, ring: true),
            const SizedBox(width: Space.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Semantics(
                    header: true,
                    child: Text(status.name.asHeading, style: theme.textTheme.headlineMedium),
                  ),
                  if (about.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: Space.xxs),
                      child: Text(
                        about.join(' · '),
                        style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                      ),
                    ),
                  if (status.clockLabel case final clock?)
                    Padding(
                      padding: const EdgeInsets.only(top: Space.sm),
                      child: _Now(label: clock),
                    ),
                ],
              ),
            ),
          ],
        ),
        if (sheet != null && sheet.description.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Space.lg),
            child: Text(
              sheet.description,
              style: context.lucidText.playerAction.copyWith(color: colors.textSecondary),
            ),
          ),
      ],
    );
  }
}

/// The world's date and time now (W10), in a line under the name.
class _Now extends StatelessWidget {
  const _Now({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      label: '${context.l10n.statusNow}: $label',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.schedule_rounded, size: 15, color: colors.accent),
          const SizedBox(width: 6),
          Flexible(
            child: Text(label, style: context.lucidText.meta.copyWith(color: colors.accent)),
          ),
        ],
      ),
    );
  }
}

/// Where they stand with a faction (W3): its name, and how its people take them.
class _Standing extends StatelessWidget {
  const _Standing({required this.name, required this.standing});

  final String name;
  final String standing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: MergeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerLow,
            borderRadius: Radii.card,
            border: Border.all(color: theme.colorScheme.outlineVariant),
          ),
          child: Wrap(
            spacing: Space.md,
            runSpacing: Space.xs,
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(name.asHeading, style: theme.textTheme.titleMedium),
              Text(
                standing,
                style: theme.textTheme.labelLarge!.copyWith(color: colors.textSecondary),
              ),
            ],
          ),
        ),
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
