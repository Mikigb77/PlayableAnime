import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// "How it played out" (A8): each step of the action as the engine settled it, whether the facts
/// settled it or a roll did, the odds and the result, the reason in the world's words, where a
/// chained plan stopped (R6), any cause-and-effect chain (A9), and both clocks (W10, W10a).
Future<void> showSceneDetails(BuildContext context, Scene scene) => showAppSheet<void>(
  context: context,
  title: context.l10n.sceneDetails,
  builder: (_) => SceneDetailsView(scene: scene),
);

class SceneDetailsView extends StatelessWidget {
  const SceneDetailsView({super.key, required this.scene});

  final Scene scene;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final details = scene.details;
    final stoppedAt = details.stoppedAtStep;
    const label = EdgeInsets.only(top: Space.xl, bottom: Space.md);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (scene.playerAction case final action?)
          Text(action, style: context.lucidText.playerAction),
        if (scene.hasTime) ...[
          const SizedBox(height: Space.md),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TimeChip(
              duration: scene.durationLabel,
              label: scene.timeLabel,
              personalLabel: scene.personalTimeLabel,
            ),
          ),
        ],
        if (details.steps.isNotEmpty) ...[
          SectionLabel(l10n.detailsSteps, padding: label),
          for (final (i, step) in details.steps.indexed) ...[
            _StepTile(number: i + 1, step: step, last: i == details.steps.length - 1),
            if (stoppedAt == i) const _Stopped(),
          ],
          if (stoppedAt != null && stoppedAt >= details.steps.length) const _Stopped(),
        ],
        if (details.chain.isNotEmpty) ...[
          SectionLabel(l10n.detailsChain, padding: label),
          for (final (i, link) in details.chain.indexed)
            _ChainTile(link: link, last: i == details.chain.length - 1),
        ],
        const SizedBox(height: Space.lg),
        Text(l10n.detailsLegend, style: context.lucidText.meta.copyWith(height: 1.5)),
      ],
    );
  }
}

/// A step's class as a small label: settled by the facts (certain, ruled out) or open to a roll
/// (contested, long shot), in colors that never carry the meaning alone.
class OutcomeClassLabel extends StatelessWidget {
  const OutcomeClassLabel(this.outcome, {super.key});

  final OutcomeClass outcome;

  static IconData iconFor(OutcomeClass outcome) => switch (outcome) {
    OutcomeClass.certain => Icons.check_circle_outline_rounded,
    OutcomeClass.contested => Icons.balance_rounded,
    OutcomeClass.longShot => Icons.track_changes_rounded,
    OutcomeClass.ruledOut => Icons.block_rounded,
  };

  static String labelFor(AppLocalizations l10n, OutcomeClass outcome) => switch (outcome) {
    OutcomeClass.certain => l10n.classCertain,
    OutcomeClass.contested => l10n.classContested,
    OutcomeClass.longShot => l10n.classLongShot,
    OutcomeClass.ruledOut => l10n.classRuledOut,
  };

  static Color colorFor(BuildContext context, OutcomeClass outcome) {
    final colors = context.lucid;
    return switch (outcome) {
      OutcomeClass.certain => colors.success,
      OutcomeClass.contested => colors.accent,
      OutcomeClass.longShot => colors.caution,
      OutcomeClass.ruledOut => colors.danger,
    };
  }

  @override
  Widget build(BuildContext context) {
    final color = colorFor(context, outcome);
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 3, 10, 3),
      decoration: BoxDecoration(
        border: Border.all(color: color.withValues(alpha: 0.55)),
        borderRadius: BorderRadius.circular(Radii.pill),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(iconFor(outcome), size: 14, color: color),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              labelFor(context.l10n, outcome).toUpperCase(),
              style: context.lucidText.overline.copyWith(color: color),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _StepTile extends StatelessWidget {
  const _StepTile({required this.number, required this.step, required this.last});

  final int number;
  final SceneStep step;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final roll = step.roll;
    return Padding(
      padding: EdgeInsets.only(bottom: last ? 0 : Space.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHigh,
              shape: BoxShape.circle,
            ),
            child: Text(
              '$number',
              style: context.lucidText.meta.copyWith(color: colors.textPrimary),
            ),
          ),
          const SizedBox(width: Space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(step.text, style: theme.textTheme.titleMedium),
                const SizedBox(height: Space.sm),
                Wrap(
                  spacing: Space.sm,
                  runSpacing: Space.sm,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    OutcomeClassLabel(step.outcomeClass),
                    if (roll != null)
                      _RollLine(roll: roll)
                    else
                      Text(l10n.detailsNoRoll, style: context.lucidText.meta),
                  ],
                ),
                if (step.reason.isNotEmpty) ...[
                  const SizedBox(height: Space.sm),
                  Text(
                    step.reason,
                    style: context.lucidText.narration.copyWith(
                      fontSize: 16,
                      height: 1.5,
                      color: colors.textSecondary,
                    ),
                  ),
                ],
                if (roll?.seed case final seed?) ...[
                  const SizedBox(height: Space.xs),
                  Text(
                    l10n.detailsSeed(seed),
                    style: context.lucidText.meta.copyWith(color: colors.textMuted),
                  ),
                ],
                for (final beat in step.beats) ...[
                  const SizedBox(height: Space.md),
                  _BeatTile(beat: beat),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// A beat of a step (R2): something the scene hadn't established that is now true, or something
/// that wasn't there, which stopped the step.
class _BeatTile extends StatelessWidget {
  const _BeatTile({required this.beat});

  final SceneBeat beat;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final color = beat.madeCanon ? colors.success : colors.caution;
    final roll = beat.roll;
    return Container(
      padding: const EdgeInsets.fromLTRB(Space.md, Space.sm, Space.md, Space.sm),
      decoration: BoxDecoration(
        border: BorderDirectional(start: BorderSide(color: color, width: 2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Icon(
                  beat.madeCanon ? Icons.add_circle_outline_rounded : Icons.do_not_disturb_rounded,
                  size: 16,
                  color: color,
                ),
              ),
              const SizedBox(width: Space.sm),
              Expanded(child: Text(beat.beat, style: theme.textTheme.titleSmall)),
            ],
          ),
          const SizedBox(height: Space.xxs),
          Text(
            beat.madeCanon
                ? l10n.detailsBeatMadeCanon(beat.thing)
                : l10n.detailsBeatEmpty(beat.thing),
            style: context.lucidText.meta.copyWith(color: color),
          ),
          if (beat.reason.isNotEmpty) ...[
            const SizedBox(height: Space.xs),
            Text(
              beat.reason,
              style: context.lucidText.narration.copyWith(
                fontSize: 15,
                height: 1.45,
                color: colors.textSecondary,
              ),
            ),
          ],
          if (roll != null) ...[const SizedBox(height: Space.xs), _RollLine(roll: roll)],
        ],
      ),
    );
  }
}

class _RollLine extends StatelessWidget {
  const _RollLine({required this.roll});

  final SceneRoll roll;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    final (icon, color, result) = switch (roll.result) {
      RollResult.success => (Icons.check_rounded, colors.success, l10n.resultSuccess),
      RollResult.partial => (Icons.contrast_rounded, colors.caution, l10n.resultPartial),
      RollResult.failure => (Icons.close_rounded, colors.danger, l10n.resultFailure),
    };
    final meta = context.lucidText.meta;
    return Text.rich(
      TextSpan(
        children: [
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Icon(Icons.casino_outlined, size: 14, color: colors.textSecondary),
          ),
          TextSpan(text: ' ${l10n.detailsOdds(roll.oddsLabel)}  ·  '),
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Icon(icon, size: 14, color: color),
          ),
          TextSpan(
            text: ' $result',
            style: TextStyle(color: color, fontWeight: FontWeight.w600),
          ),
        ],
      ),
      style: meta,
    );
  }
}

/// Where a chained plan stopped (R6): the steps after it never happened.
class _Stopped extends StatelessWidget {
  const _Stopped();

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final line = Theme.of(context).colorScheme.outlineVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Space.lg),
      child: Row(
        children: [
          SizedBox(width: 28, child: Divider(color: line)),
          const SizedBox(width: Space.md),
          Icon(Icons.front_hand_outlined, size: 16, color: colors.caution),
          const SizedBox(width: Space.sm),
          Expanded(
            child: Text(
              context.l10n.detailsStopped,
              style: context.lucidText.meta.copyWith(color: colors.textSecondary, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

/// One link of a cause-and-effect chain, joined to the next by a line (A9).
class _ChainTile extends StatelessWidget {
  const _ChainTile({required this.link, required this.last});

  final ChainLink link;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final color = OutcomeClassLabel.colorFor(context, link.outcomeClass);
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 28,
            child: Column(
              children: [
                const SizedBox(height: 6),
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
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
                  Text(link.text, style: theme.textTheme.bodyLarge),
                  const SizedBox(height: Space.xs),
                  OutcomeClassLabel(link.outcomeClass),
                  if (link.reason.isNotEmpty) ...[
                    const SizedBox(height: Space.xs),
                    Text(
                      link.reason,
                      style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
