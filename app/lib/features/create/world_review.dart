import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../discover/premises.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_sheets.dart';
import 'draft_widgets.dart';
import 'review_widgets.dart';

/// The first screen of the review: the world, and only the world (G1; Miki, 2026-11-14: "one
/// is just for the world where the user can tweak stuff, and on the next screen is just for the
/// character"). The story's title and tone, the setting row by row, its rules, what the
/// player's own words named of how it starts, a count of what the story keeps back, and how it
/// plays.
///
/// Every row says how it changes (Miki, 2026-11-10: "it's very difficult to edit stuff"): a
/// pencil is a plain value the player types, saved at once and free; a wand opens the box where
/// they tell the storyteller, already pointed at that row, and says what it costs first.
class WorldReview extends StatelessWidget {
  const WorldReview({super.key, required this.flow, this.starter});

  final CreateFlow flow;

  /// The starter it came from, for its cover.
  final Premise? starter;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) {
        final draft = flow.draft!;
        final cover = starter?.id == draft.premiseId ? starter?.coverUrl : null;
        final redrafting = flow.redrafting.world ? l10n.reviewRedraftingWorld : null;
        final openers = draft.openers.any((opener) => opener.$1 == DraftPart.world);
        return ListView(
          padding: const EdgeInsets.only(bottom: Space.xxl),
          children: [
            ContentColumn.reading(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, 0),
                child: ReviewSteps(flow: flow),
              ),
            ),
            if (cover != null)
              ContentColumn.reading(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(Space.gutter, Space.lg, Space.gutter, 0),
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
                    _Hero(flow: flow, draft: draft),
                    const SizedBox(height: Space.md),
                    const ReviewLegend(),
                    FieldLabel(l10n.reviewWorld),
                    ReviewCard(
                      redrafting: redrafting,
                      child: _Setting(flow: flow, draft: draft),
                    ),
                    FieldLabel(l10n.reviewRules),
                    ReviewCard(
                      redrafting: redrafting,
                      child: _Rules(flow: flow, draft: draft),
                    ),
                    FieldLabel(l10n.reviewYours),
                    ReviewCard(
                      child: openers
                          ? ReviewOpeners(flow: flow, draft: draft, part: DraftPart.world)
                          : Padding(
                              padding: const EdgeInsets.all(Space.lg),
                              child: Text(
                                l10n.reviewYoursNone,
                                style: Theme.of(context).textTheme.bodyMedium!.copyWith(
                                  color: context.lucid.textSecondary,
                                ),
                              ),
                            ),
                    ),
                    FieldLabel(l10n.reviewKept),
                    ReviewCard(child: _Kept(kept: draft.kept)),
                    FieldLabel(l10n.reviewPlays),
                    ReviewCard(
                      child: _Plays(flow: flow, draft: draft),
                    ),
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

/// The story's genre and rating, its title and its tone. The title and the tone are the
/// player's to type.
class _Hero extends StatelessWidget {
  const _Hero({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final busy = flow.busy;
    return Column(
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
        ReviewTyped(
          hint: l10n.reviewEditTitle,
          header: true,
          onTap: busy ? null : () => showFieldSheet(context, flow: flow, field: PlainField.title),
          child: Text(draft.title, style: Theme.of(context).textTheme.headlineLarge),
        ),
        if (draft.tone.isNotEmpty)
          ReviewTyped(
            hint: l10n.reviewEditTone,
            onTap: busy ? null : () => showFieldSheet(context, flow: flow, field: PlainField.tone),
            child: Text(
              draft.tone,
              style: context.lucidText.playerAction.copyWith(color: colors.textSecondary),
            ),
          ),
      ],
    );
  }
}

const _settingRows = [LineKind.era, LineKind.ladder, LineKind.peoples, LineKind.faction];

/// What the storyteller drafted of the world, row by row: when and where, its ranks, its
/// peoples and who holds power. Each row is asked about on its own, and the button at the foot
/// asks for a different world.
class _Setting extends StatelessWidget {
  const _Setting({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ReviewRows([
      for (final kind in _settingRows)
        if (draft.linesOf(DraftPart.world, kind) case final lines when lines.isNotEmpty)
          ReviewRow(
            label: l10n.row(kind),
            text: lines.join('\n'),
            direct: false,
            onTap: askAt(context, flow, DraftPart.world, kind, lines.join('\n')),
          ),
      ReviewAsk(
        label: l10n.reviewAskWorld,
        note: l10n.reviewAskOwnWords,
        onTap: flow.busy ? null : () => showReviseSheet(context, flow: flow, part: DraftPart.world),
      ),
    ]);
  }
}

/// The world's rules, each locked for the whole story or true for now (G6, G7).
class _Rules extends StatelessWidget {
  const _Rules({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final busy = flow.busy;
    final rules = draft.advanced.rules;
    final fixed = [
      for (final (i, rule) in rules.indexed)
        if (rule.fixed) (i, rule),
    ];
    final open = [
      for (final (i, rule) in rules.indexed)
        if (!rule.fixed) (i, rule),
    ];
    Widget rule(int index, DraftRule rule) => _Rule(
      rule: rule,
      onTap: busy ? null : () => showRuleSheet(context, flow: flow, index: index),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (fixed.isNotEmpty) ...[
          _Group(l10n.rulesFixedGroup),
          for (final (i, r) in fixed) rule(i, r),
        ],
        if (open.isNotEmpty) ...[
          _Group(l10n.rulesOpenGroup, note: l10n.rulesOpenGroupNote),
          for (final (i, r) in open) rule(i, r),
        ],
        if (rules.length < DraftLimits.rules)
          TextButton.icon(
            style: TextButton.styleFrom(
              alignment: AlignmentDirectional.centerStart,
              padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.md),
              shape: const RoundedRectangleBorder(),
              foregroundColor: context.lucid.textSecondary,
            ),
            onPressed: busy ? null : () => showRuleSheet(context, flow: flow),
            icon: const Icon(Icons.add_rounded, size: 20),
            label: Text(l10n.ruleAdd),
          )
        else
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.lg, Space.sm, Space.lg, Space.md),
            child: Text(l10n.rulesFull, style: context.lucidText.meta),
          ),
      ],
    );
  }
}

/// The name of a group of rules: the ones that never change, or the ones true for now.
class _Group extends StatelessWidget {
  const _Group(this.label, {this.note});

  final String label;
  final String? note;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.lg, Space.xxs),
      child: Semantics(
        header: true,
        child: Text.rich(
          TextSpan(
            text: label.toUpperCase(),
            style: context.lucidText.overline.copyWith(color: colors.textMuted),
            children: [
              if (note case final note?)
                TextSpan(
                  text: '  $note',
                  style: context.lucidText.meta.copyWith(color: colors.textMuted),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One rule of the world, with its lock: shut when it holds for the whole story (G7).
class _Rule extends StatelessWidget {
  const _Rule({required this.rule, this.onTap});

  final DraftRule rule;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      button: true,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.lg, Space.sm, Space.md, Space.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ExcludeSemantics(
                child: Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Icon(
                    rule.fixed ? Icons.lock_outline_rounded : Icons.lock_open_rounded,
                    size: 18,
                    color: rule.fixed ? colors.accent : colors.textMuted,
                  ),
                ),
              ),
              const SizedBox(width: Space.md),
              Expanded(
                child: Text(
                  rule.text,
                  style: context.lucidText.narration.copyWith(fontSize: 16, height: 1.45),
                ),
              ),
              const SizedBox(width: Space.sm),
              const ExcludeSemantics(
                child: Padding(padding: EdgeInsets.only(top: 3), child: ReviewMark(direct: true)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// How much of the story's start is kept out of sight, as counts and nothing more (G1).
class _Kept extends StatelessWidget {
  const _Kept({required this.kept});

  final DraftKept kept;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    Widget tile(int count, String label) => Expanded(
      child: MergeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: Space.md),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerLow,
            borderRadius: Radii.field,
          ),
          child: Column(
            children: [
              Text('$count', style: theme.textTheme.headlineSmall),
              const SizedBox(height: Space.xxs),
              Text(
                label,
                textAlign: TextAlign.center,
                style: context.lucidText.meta.copyWith(color: colors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
    return Padding(
      padding: const EdgeInsets.all(Space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            l10n.reviewKeptBody,
            style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
          ),
          if (!kept.isEmpty) ...[
            const SizedBox(height: Space.md),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                tile(kept.people, l10n.keptPeople(kept.people)),
                const SizedBox(width: Space.sm),
                tile(kept.events, l10n.keptEvents(kept.events)),
                const SizedBox(width: Space.sm),
                tile(kept.questions, l10n.keptQuestions(kept.questions)),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// How the story plays: the rating (F2, F8), difficulty (A5), world events (W16) and physics
/// (A9). A choice that redrafts nothing is saved as it is picked; one that redrafts something
/// says what it costs first. The gift is the character's, and is chosen on their screen.
class _Plays extends ConsumerStatefulWidget {
  const _Plays({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  ConsumerState<_Plays> createState() => _PlaysState();
}

class _PlaysState extends ConsumerState<_Plays> {
  /// The choice being saved, shown as picked until the draft comes back with it.
  DraftEdit? _saving;

  CreateFlow get _flow => widget.flow;

  Future<void> _save(DraftEdit edit) async {
    setState(() => _saving = edit);
    final failure = await _flow.edit(edit);
    if (!mounted) return;
    setState(() => _saving = null);
    if (failure != null) showEditFailure(context, failure);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final draft = widget.draft;
    final advanced = draft.advanced;
    final saving = _saving;
    final teenOnly = ref.watch(maxRatingProvider) == Rating.teen;
    final busy = _flow.busy;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.lg, 0, Space.lg, Space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ChoiceField<Rating>(
            label: l10n.createRatingLabel,
            top: Space.lg,
            values: Rating.values,
            value: saving?.rating ?? draft.rating,
            labelOf: l10n.rating,
            bodyOf: l10n.ratingBody,
            // Mature opens on the 17th birthday (F8).
            enabledOf: (rating) => rating == Rating.teen || !teenOnly,
            note: teenOnly ? l10n.ratingMatureLocked : null,
            onChanged: busy
                ? null
                : (value) {
                    final edit = DraftEdit(rating: value);
                    if (redraftFor(draft, edit).isFree) {
                      _save(edit);
                    } else {
                      showChoiceSheet(
                        context,
                        flow: _flow,
                        title: l10n.createRatingLabel,
                        choice: l10n.rating(value),
                        body: l10n.ratingBody(value),
                        edit: edit,
                      );
                    }
                  },
          ),
          ChoiceField<Difficulty>(
            label: l10n.difficultyLabel,
            values: Difficulty.values,
            value: saving?.difficulty ?? advanced.difficulty,
            labelOf: l10n.difficulty,
            bodyOf: l10n.difficultyBody,
            onChanged: busy ? null : (value) => _save(DraftEdit(difficulty: value)),
          ),
          ChoiceField<EventFrequency>(
            label: l10n.eventsLabel,
            values: EventFrequency.values,
            value: saving?.eventFrequency ?? advanced.eventFrequency,
            labelOf: l10n.events,
            bodyOf: l10n.eventsBody,
            onChanged: busy ? null : (value) => _save(DraftEdit(eventFrequency: value)),
          ),
          ChoiceField<Physics>(
            label: l10n.physicsLabel,
            values: Physics.values,
            value: saving?.physics ?? advanced.physics,
            labelOf: l10n.physics,
            bodyOf: l10n.physicsBody,
            onChanged: busy ? null : (value) => _save(DraftEdit(physics: value)),
          ),
        ],
      ),
    );
  }
}
