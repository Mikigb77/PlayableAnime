import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../discover/premises.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_sheets.dart';
import 'draft_widgets.dart';

/// The drafted world and character, to change or start (G1, G2): any line can be rewritten or
/// removed, either part can be asked for in plain words, and the rating and the advanced fields
/// sit below. Every change says what it costs before the player makes it.
class DraftReview extends StatelessWidget {
  const DraftReview({super.key, required this.flow, this.starter});

  final CreateFlow flow;

  /// The starter it came from, for its cover.
  final Premise? starter;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) {
        final draft = flow.draft!;
        final cover = starter?.id == draft.premiseId ? starter?.coverUrl : null;
        final redrafting = flow.redrafting;
        return ListView(
          padding: const EdgeInsets.only(bottom: Space.xxl),
          children: [
            if (cover != null)
              ContentColumn.reading(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, 0),
                  child: PictureSlot(
                    status: PictureStatus.ready,
                    url: cover,
                    aspectRatio: 21 / 9,
                    alignment: coverFocus,
                    semanticLabel: draft.title,
                  ),
                ),
              ),
            ContentColumn.reading(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      [
                        if (draft.genre.isNotEmpty) draft.genre,
                        l10n.rating(draft.rating),
                      ].join(' · ').toUpperCase(),
                      style: context.lucidText.overline.copyWith(color: colors.accent),
                    ),
                    const SizedBox(height: Space.xs),
                    Semantics(
                      header: true,
                      child: Text(draft.title, style: theme.textTheme.headlineLarge),
                    ),
                    if (draft.tone.isNotEmpty) ...[
                      const SizedBox(height: Space.sm),
                      Text(
                        draft.tone,
                        style: context.lucidText.playerAction.copyWith(color: colors.textSecondary),
                      ),
                    ],
                    const SizedBox(height: Space.xs),
                    Text(
                      l10n.reviewTapToEdit,
                      style: context.lucidText.meta.copyWith(color: colors.textMuted),
                    ),
                    for (final part in DraftPart.values)
                      _PartCard(
                        flow: flow,
                        part: part,
                        lines: draft.linesOf(part),
                        redrafting: switch (part) {
                          DraftPart.world => redrafting.world,
                          DraftPart.character => redrafting.character,
                        },
                      ),
                    FieldLabel(l10n.reviewSettings),
                    _SettingsCard(flow: flow, draft: draft),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// One part of the draft: its lines, each one tappable, and a way to ask for something different.
class _PartCard extends StatelessWidget {
  const _PartCard({
    required this.flow,
    required this.part,
    required this.lines,
    required this.redrafting,
  });

  final CreateFlow flow;
  final DraftPart part;
  final List<String> lines;
  final bool redrafting;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    final colors = context.lucid;
    final busy = flow.busy;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FieldLabel(switch (part) {
          DraftPart.world => l10n.reviewWorld,
          DraftPart.character => l10n.reviewCharacter,
        }),
        Card(
          margin: EdgeInsets.zero,
          clipBehavior: Clip.antiAlias,
          child: AnimatedSwitcher(
            duration: Motion.of(context, Motion.base),
            child: redrafting
                ? _Redrafting(
                    key: const ValueKey('redrafting'),
                    label: switch (part) {
                      DraftPart.world => l10n.reviewRedraftingWorld,
                      DraftPart.character => l10n.reviewRedraftingCharacter,
                    },
                    lines: lines.length.clamp(2, 6),
                  )
                : Column(
                    key: const ValueKey('lines'),
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      for (final (i, line) in lines.indexed) ...[
                        if (i > 0)
                          Divider(
                            height: 1,
                            indent: Space.lg,
                            endIndent: Space.lg,
                            color: scheme.outlineVariant,
                          ),
                        _Line(
                          text: line,
                          onTap: busy
                              ? null
                              : () => showLineSheet(context, flow: flow, part: part, index: i),
                        ),
                      ],
                      Divider(height: 1, color: scheme.outlineVariant),
                      TextButton.icon(
                        style: TextButton.styleFrom(
                          alignment: AlignmentDirectional.centerStart,
                          padding: const EdgeInsets.symmetric(
                            horizontal: Space.lg,
                            vertical: Space.md,
                          ),
                          shape: const RoundedRectangleBorder(),
                          foregroundColor: colors.accent,
                        ),
                        onPressed: busy
                            ? null
                            : () => showReviseSheet(context, flow: flow, part: part),
                        icon: const Icon(Icons.auto_fix_high_rounded, size: 20),
                        label: Text(switch (part) {
                          DraftPart.world => l10n.reviewAskWorld,
                          DraftPart.character => l10n.reviewAskCharacter,
                        }),
                      ),
                    ],
                  ),
          ),
        ),
      ],
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.text, this.onTap});

  final String text;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      button: true,
      hint: context.l10n.reviewEditLine,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.sm, Space.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  text,
                  style: context.lucidText.narration.copyWith(fontSize: 16, height: 1.5),
                ),
              ),
              const SizedBox(width: Space.sm),
              ExcludeSemantics(
                child: Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Icon(Icons.edit_outlined, size: 18, color: colors.textMuted),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A part being redrafted: skeleton lines in its place and what is happening.
class _Redrafting extends StatelessWidget {
  const _Redrafting({super.key, required this.label, required this.lines});

  final String label;
  final int lines;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      liveRegion: true,
      label: label,
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ExcludeSemantics(
              child: Row(
                children: [
                  SizedBox.square(
                    dimension: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: colors.accent),
                  ),
                  const SizedBox(width: Space.sm),
                  Text(label, style: context.lucidText.meta.copyWith(color: colors.textSecondary)),
                ],
              ),
            ),
            const SizedBox(height: Space.lg),
            ExcludeSemantics(child: SkeletonText(lines: lines)),
          ],
        ),
      ),
    );
  }
}

/// The rating (F2) and the advanced fields (G1), each opening its sheet.
class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    final colors = context.lucid;
    final advanced = draft.advanced;
    final busy = flow.busy;
    Widget tile(IconData icon, String title, String subtitle, VoidCallback onTap) => ListTile(
      leading: Icon(icon, color: colors.textSecondary),
      title: Text(title),
      subtitle: Text(subtitle, style: TextStyle(color: colors.textSecondary)),
      trailing: Icon(Icons.chevron_right_rounded, color: colors.textMuted),
      onTap: busy ? null : onTap,
    );
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          tile(
            Icons.shield_outlined,
            l10n.reviewRating,
            l10n.rating(draft.rating),
            () => showRatingSheet(context, flow: flow),
          ),
          Divider(height: 1, indent: Space.lg, endIndent: Space.lg, color: scheme.outlineVariant),
          tile(
            Icons.tune_rounded,
            l10n.reviewAdvanced,
            [
              l10n.physics(advanced.physics),
              l10n.gift(advanced.giftStrength),
              l10n.difficulty(advanced.difficulty),
              l10n.events(advanced.eventFrequency),
              l10n.reviewRules(advanced.rules.length),
            ].join(' · '),
            () => showAdvancedSheet(context, flow: flow),
          ),
        ],
      ),
    );
  }
}

/// The one filled button of the review: start the story.
class StartBar extends StatelessWidget {
  const StartBar({super.key, required this.flow, required this.onStart});

  final CreateFlow flow;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) => DecoratedBox(
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          border: Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
        ),
        child: SafeArea(
          top: false,
          // Not a ContentColumn: its Align would fill the whole screen in the bottom bar slot.
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
                    if (flow.error case final error?) ...[
                      InlineError(error),
                      const SizedBox(height: Space.md),
                    ],
                    FilledButton.icon(
                      onPressed: flow.busy || flow.starting ? null : onStart,
                      icon: flow.starting
                          ? SizedBox.square(
                              dimension: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: theme.colorScheme.onSurface,
                              ),
                            )
                          : const Icon(Icons.play_arrow_rounded),
                      label: Text(l10n.reviewStart),
                    ),
                    const SizedBox(height: Space.xs),
                    Text(
                      l10n.reviewStartNote,
                      textAlign: TextAlign.center,
                      style: context.lucidText.meta.copyWith(color: colors.textMuted),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
