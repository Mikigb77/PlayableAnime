/// The pieces both screens of the review are built from (G1, G2): the steps that lead from the
/// world to the character, the marks that say how a row changes, a card and its rows, and the
/// bar with the screen's one filled button.
library;

import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_sheets.dart';
import 'draft_widgets.dart';

/// The two screens of the review as steps, the one on show lit: the world, then the character
/// (Miki, 2026-11-14). Either is one tap away, so nothing is lost by moving on.
class ReviewSteps extends StatelessWidget {
  const ReviewSteps({super.key, required this.flow});

  final CreateFlow flow;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final scheme = Theme.of(context).colorScheme;
    final onCharacter = flow.stage == CreateStage.character;
    return Row(
      children: [
        Flexible(
          child: _Step(
            key: const ValueKey('review.step.world'),
            number: 1,
            label: l10n.reviewStepWorld,
            current: !onCharacter,
            done: onCharacter,
            onTap: () => flow.show(CreateStage.world),
          ),
        ),
        ExcludeSemantics(
          child: Container(
            width: Space.lg,
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: Space.xs),
            color: scheme.outlineVariant,
          ),
        ),
        Flexible(
          child: _Step(
            key: const ValueKey('review.step.character'),
            number: 2,
            label: l10n.reviewStepCharacter,
            current: onCharacter,
            onTap: () => flow.show(CreateStage.character),
          ),
        ),
      ],
    );
  }
}

class _Step extends StatelessWidget {
  const _Step({
    super.key,
    required this.number,
    required this.label,
    required this.current,
    required this.onTap,
    this.done = false,
  });

  final int number;
  final String label;
  final bool current;
  final bool done;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    return Semantics(
      button: true,
      selected: current,
      child: InkWell(
        onTap: current ? null : onTap,
        borderRadius: BorderRadius.circular(Radii.pill),
        child: AnimatedContainer(
          duration: Motion.of(context, Motion.fast),
          curve: Motion.standard,
          constraints: const BoxConstraints(minHeight: 40),
          padding: const EdgeInsets.fromLTRB(Space.xs, Space.xs, Space.md, Space.xs),
          decoration: BoxDecoration(
            color: current ? colors.accentSoft : null,
            borderRadius: BorderRadius.circular(Radii.pill),
            border: Border.all(
              color: current ? colors.accent.withValues(alpha: 0.6) : scheme.outlineVariant,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ExcludeSemantics(
                child: Container(
                  width: 26,
                  height: 26,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: current ? colors.accentGradient() : null,
                    color: current ? null : scheme.surfaceContainerHigh,
                  ),
                  child: done
                      ? Icon(Icons.check_rounded, size: 15, color: colors.textSecondary)
                      : Text(
                          '$number',
                          textScaler: TextScaler.noScaling,
                          style: theme.textTheme.labelLarge!.copyWith(
                            fontSize: 13,
                            height: 1,
                            color: current ? colors.onAccent : colors.textSecondary,
                          ),
                        ),
                ),
              ),
              const SizedBox(width: Space.sm),
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelLarge!.copyWith(
                    color: current ? colors.onAccentSoft : colors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// How a row changes: a pencil for what the player types themselves, a wand for what they tell
/// the storyteller.
class ReviewMark extends StatelessWidget {
  const ReviewMark({super.key, required this.direct});

  final bool direct;

  @override
  Widget build(BuildContext context) => Icon(
    direct ? Icons.edit_outlined : Icons.auto_fix_high_rounded,
    size: 18,
    color: direct ? context.lucid.textMuted : context.lucid.accent,
  );
}

/// What the two marks mean, said once at the top of a screen.
class ReviewLegend extends StatelessWidget {
  const ReviewLegend({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final style = context.lucidText.meta.copyWith(color: context.lucid.textMuted);
    Widget item(bool direct, String text) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(child: ReviewMark(direct: direct)),
        const SizedBox(width: Space.xs),
        Flexible(child: Text(text, style: style)),
      ],
    );
    return Wrap(
      spacing: Space.lg,
      runSpacing: Space.xs,
      children: [item(true, l10n.reviewLegendDirect), item(false, l10n.reviewLegendAsk)],
    );
  }
}

/// A text the player types over, with its pencil: the title, the tone.
class ReviewTyped extends StatelessWidget {
  const ReviewTyped({
    super.key,
    required this.child,
    required this.hint,
    this.onTap,
    this.header = false,
  });

  final Widget child;
  final String hint;
  final VoidCallback? onTap;
  final bool header;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    header: header,
    hint: hint,
    child: InkWell(
      borderRadius: Radii.field,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xs),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(child: child),
            const SizedBox(width: Space.sm),
            const ExcludeSemantics(
              child: Padding(
                padding: EdgeInsets.only(top: Space.xs),
                child: ReviewMark(direct: true),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// A card of the review. While its part is redrafted, skeleton lines stand in its place with
/// what is happening.
class ReviewCard extends StatelessWidget {
  const ReviewCard({super.key, required this.child, this.redrafting});

  final Widget child;

  /// What is being redrafted, or null when nothing is.
  final String? redrafting;

  @override
  Widget build(BuildContext context) => Card(
    margin: EdgeInsets.zero,
    clipBehavior: Clip.antiAlias,
    child: AnimatedSwitcher(
      duration: Motion.of(context, Motion.base),
      child: switch (redrafting) {
        final label? => _Redrafting(key: const ValueKey('redrafting'), label: label),
        null => KeyedSubtree(key: const ValueKey('rows'), child: child),
      },
    ),
  );
}

/// A part being redrafted: skeleton lines in its place and what is happening.
class _Redrafting extends StatelessWidget {
  const _Redrafting({super.key, required this.label});

  final String label;

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
                  Flexible(
                    child: Text(
                      label,
                      style: context.lucidText.meta.copyWith(color: colors.textSecondary),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Space.lg),
            const ExcludeSemantics(child: SkeletonText(lines: 5)),
          ],
        ),
      ),
    );
  }
}

/// The rows of a card, with a hairline between each two.
class ReviewRows extends StatelessWidget {
  const ReviewRows(this.rows, {super.key});

  final List<Widget> rows;

  @override
  Widget build(BuildContext context) {
    final line = Divider(
      height: 1,
      indent: Space.lg,
      endIndent: Space.lg,
      color: Theme.of(context).colorScheme.outlineVariant,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final (i, row) in rows.indexed) ...[if (i > 0) line, row],
      ],
    );
  }
}

/// One row of a card: what it is, what it says, and the mark of how it changes.
class ReviewRow extends StatelessWidget {
  const ReviewRow({
    super.key,
    required this.label,
    required this.text,
    required this.direct,
    this.onTap,
    this.below,
    this.leading,
  });

  final String label;
  final String text;

  /// Whether the player types it themselves (a pencil) or tells the storyteller (a wand).
  final bool direct;
  final VoidCallback? onTap;

  /// Shown under the text, such as the rungs of a ladder.
  final Widget? below;

  /// Shown before the label and the text, such as an opener's icon.
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      button: true,
      hint: direct ? null : context.l10n.reviewAskHere,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.md, Space.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (leading case final leading?) ...[
                ExcludeSemantics(
                  child: Padding(padding: const EdgeInsets.only(top: 2), child: leading),
                ),
                const SizedBox(width: Space.md),
              ],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label.toUpperCase(),
                      style: context.lucidText.overline.copyWith(color: colors.textMuted),
                    ),
                    if (text.isNotEmpty) ...[
                      const SizedBox(height: Space.xxs),
                      Text(
                        text,
                        style: context.lucidText.narration.copyWith(fontSize: 16, height: 1.45),
                      ),
                    ],
                    if (below case final below?) ...[const SizedBox(height: Space.sm), below],
                  ],
                ),
              ),
              const SizedBox(width: Space.sm),
              ExcludeSemantics(
                child: Padding(
                  padding: const EdgeInsets.only(top: Space.xs),
                  child: ReviewMark(direct: direct),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The button at the foot of a card: ask for a change to the whole part, in plain words.
class ReviewAsk extends StatelessWidget {
  const ReviewAsk({super.key, required this.label, this.note, this.onTap});

  final String label;
  final String? note;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return TextButton.icon(
      style: TextButton.styleFrom(
        alignment: AlignmentDirectional.centerStart,
        padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
        shape: const RoundedRectangleBorder(),
        foregroundColor: colors.accent,
      ),
      onPressed: onTap,
      icon: const Icon(Icons.auto_fix_high_rounded, size: 20),
      label: Text.rich(
        TextSpan(
          text: label,
          children: [
            if (note case final note?)
              TextSpan(
                text: '  $note',
                style: context.lucidText.meta.copyWith(color: colors.textMuted),
              ),
          ],
        ),
      ),
    );
  }
}

/// The rows the storyteller changes, by what they tell of.
extension ReviewRowNames on AppLocalizations {
  String row(LineKind kind) => switch (kind) {
    LineKind.rank => rowRank,
    LineKind.skills => rowSkills,
    LineKind.talents => rowTalents,
    LineKind.traits => rowTraits,
    LineKind.nature => rowNature,
    LineKind.power => rowPower,
    LineKind.belongings => rowBelongings,
    LineKind.era => rowEra,
    LineKind.ladder => rowLadder,
    LineKind.peoples => rowPeoples,
    LineKind.faction => rowFactions,
    LineKind.deadline => openerDeadline,
    LineKind.question => openerQuestion,
    LineKind.person => openerPerson,
    LineKind.connections => openerConnections,
    LineKind.goal => openerGoal,
    LineKind.manner => rowManner,
    LineKind.who || LineKind.standing => reviewYou,
    LineKind.rule => ruleSheetTitle,
  };
}

/// Opens the box where the player tells the storyteller what to change about one row, or
/// nothing while another change is in flight. A [seed] starts their words for them.
VoidCallback? askAt(
  BuildContext context,
  CreateFlow flow,
  DraftPart part,
  LineKind kind,
  String text, {
  String? label,
  String seed = '',
}) => flow.busy
    ? null
    : () => showReviseSheet(
        context,
        flow: flow,
        part: part,
        about: kind,
        aboutLabel: label ?? context.l10n.row(kind),
        aboutText: text,
        seed: seed,
      );

/// What the player's own words named of how the story starts (G1), as rows of [part]: a
/// deadline, an open question and a person on the world's screen, a goal and who they can count
/// on on the character's. Nothing else of the start is shown.
class ReviewOpeners extends StatelessWidget {
  const ReviewOpeners({super.key, required this.flow, required this.draft, required this.part});

  final CreateFlow flow;
  final Draft draft;
  final DraftPart part;

  static IconData _icon(LineKind kind) => switch (kind) {
    LineKind.deadline => Icons.hourglass_bottom_rounded,
    LineKind.question => Icons.help_outline_rounded,
    LineKind.person => Icons.person_outline_rounded,
    LineKind.connections => Icons.group_outlined,
    _ => Icons.flag_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    return ReviewRows([
      for (final (of, line) in draft.openers)
        if (of == part)
          ReviewRow(
            label: l10n.row(line.kind),
            text: line.text,
            direct: false,
            leading: Icon(_icon(line.kind), size: 20, color: colors.accent),
            onTap: askAt(context, flow, part, line.kind, line.text),
          ),
    ]);
  }
}

/// The bar under a screen of the review, with its one filled button: on to the character from
/// the world, and the start of the story from the character.
class ReviewBar extends StatelessWidget {
  const ReviewBar({super.key, required this.flow, required this.onStart});

  final CreateFlow flow;
  final VoidCallback onStart;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) {
        final last = flow.stage == CreateStage.character;
        return DecoratedBox(
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
                  padding: const EdgeInsets.fromLTRB(
                    Space.gutter,
                    Space.md,
                    Space.gutter,
                    Space.md,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (flow.error case final error?) ...[
                        InlineError(error),
                        const SizedBox(height: Space.md),
                      ],
                      if (last)
                        FilledButton.icon(
                          key: const ValueKey('review.start'),
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
                        )
                      else
                        // A change in flight carries on behind the next screen.
                        FilledButton.icon(
                          key: const ValueKey('review.next'),
                          onPressed: () => flow.show(CreateStage.character),
                          icon: const Icon(Icons.arrow_forward_rounded),
                          iconAlignment: IconAlignment.end,
                          label: Text(l10n.reviewNext),
                        ),
                      const SizedBox(height: Space.xs),
                      Text(
                        last ? l10n.reviewStartNote : l10n.reviewNextNote,
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
      },
    );
  }
}

/// Says why a choice saved on the spot didn't save, in a snackbar.
void showEditFailure(BuildContext context, Object failure) {
  final l10n = context.l10n;
  final text = switch (failure) {
    ApiException(code: ApiErrorCode.versionConflict) => l10n.reviewConflict,
    _ => describeError(l10n, failure).message,
  };
  ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(SnackBar(content: Text(text)));
}
