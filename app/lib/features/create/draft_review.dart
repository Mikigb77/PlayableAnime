import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import '../discover/premises.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_sheets.dart';
import 'draft_widgets.dart';

/// The drafted story, to change or start (G1, G2). The character comes first, then the world
/// with its rules, then what the player's own words named of how the story starts, a count of
/// what the story keeps back, and how it plays.
///
/// Every row says how it changes (Miki, 2026-11-10: "it's very difficult to edit stuff"): a
/// pencil is a plain value the player types, saved at once and free; a wand opens the box where
/// they tell the storyteller, already pointed at that row, and says what it costs first.
class DraftReview extends StatelessWidget {
  const DraftReview({super.key, required this.flow, this.starter});

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
                    _Hero(flow: flow, draft: draft),
                    const SizedBox(height: Space.md),
                    const _Legend(),
                    FieldLabel(l10n.reviewYou),
                    _Card(
                      redrafting: redrafting.character ? l10n.reviewRedraftingCharacter : null,
                      child: _You(flow: flow, draft: draft),
                    ),
                    FieldLabel(l10n.reviewWorld),
                    _Card(
                      redrafting: redrafting.world ? l10n.reviewRedraftingWorld : null,
                      child: _World(flow: flow, draft: draft),
                    ),
                    FieldLabel(l10n.reviewYours),
                    _Card(
                      child: _Yours(flow: flow, draft: draft),
                    ),
                    FieldLabel(l10n.reviewKept),
                    _Card(child: _Kept(kept: draft.kept)),
                    FieldLabel(l10n.reviewPlays),
                    _Card(
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
        _Typed(
          hint: l10n.reviewEditTitle,
          header: true,
          onTap: busy ? null : () => showFieldSheet(context, flow: flow, field: PlainField.title),
          child: Text(draft.title, style: Theme.of(context).textTheme.headlineLarge),
        ),
        if (draft.tone.isNotEmpty)
          _Typed(
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

/// A text of the hero that the player types over, with its pencil.
class _Typed extends StatelessWidget {
  const _Typed({required this.child, required this.hint, this.onTap, this.header = false});

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
                child: _Mark(direct: true),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// How a row changes: a pencil for what the player types themselves, a wand for what they tell
/// the storyteller.
class _Mark extends StatelessWidget {
  const _Mark({required this.direct});

  final bool direct;

  @override
  Widget build(BuildContext context) => Icon(
    direct ? Icons.edit_outlined : Icons.auto_fix_high_rounded,
    size: 18,
    color: direct ? context.lucid.textMuted : context.lucid.accent,
  );
}

/// What the two marks mean, said once above the cards.
class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final style = context.lucidText.meta.copyWith(color: context.lucid.textMuted);
    Widget item(bool direct, String text) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(child: _Mark(direct: direct)),
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

/// A card of the review. While its part is redrafted, skeleton lines stand in its place with
/// what is happening.
class _Card extends StatelessWidget {
  const _Card({required this.child, this.redrafting});

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
                  Text(label, style: context.lucidText.meta.copyWith(color: colors.textSecondary)),
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
class _Rows extends StatelessWidget {
  const _Rows(this.rows);

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
class _Row extends StatelessWidget {
  const _Row({
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
                  child: _Mark(direct: direct),
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
class _Ask extends StatelessWidget {
  const _Ask({required this.label, this.note, this.onTap});

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

/// The rows the storyteller changes, by what they tell of, in the order a card shows them.
extension on AppLocalizations {
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

const _characterRows = [
  LineKind.rank,
  LineKind.skills,
  LineKind.talents,
  LineKind.traits,
  LineKind.nature,
  LineKind.power,
  LineKind.belongings,
];

const _worldRows = [LineKind.era, LineKind.ladder, LineKind.peoples, LineKind.faction];

/// Opens the box where the player tells the storyteller what to change about one row.
VoidCallback? _askAt(
  BuildContext context,
  CreateFlow flow,
  DraftPart part,
  LineKind kind,
  String text,
) => flow.busy
    ? null
    : () => showReviseSheet(
        context,
        flow: flow,
        part: part,
        about: kind,
        aboutLabel: context.l10n.row(kind),
        aboutText: text,
      );

/// The character: who they are, typed by the player, then what the storyteller drafted of them,
/// row by row.
class _You extends StatelessWidget {
  const _You({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final busy = flow.busy;
    final character = draft.character;
    VoidCallback? typed(PlainField field) =>
        busy ? null : () => showFieldSheet(context, flow: flow, field: field);
    return _Rows([
      _Who(
        character: character,
        onTap: busy ? null : () => showNameSheet(context, flow: flow),
      ),
      _Row(
        label: l10n.rowLooks,
        text: character.looks,
        direct: true,
        onTap: typed(PlainField.looks),
      ),
      _Row(
        label: l10n.rowManner,
        text: character.manner,
        direct: true,
        onTap: typed(PlainField.manner),
      ),
      for (final kind in _characterRows)
        if (draft.linesOf(DraftPart.character, kind) case final lines when lines.isNotEmpty)
          _Row(
            label: l10n.row(kind),
            text: lines.join('\n'),
            direct: false,
            below: kind == LineKind.rank && draft.ladder != null
                ? _Rungs(ladder: draft.ladder!)
                : null,
            onTap: _askAt(context, flow, DraftPart.character, kind, lines.join('\n')),
          ),
      _Ask(
        label: l10n.reviewAskCharacter,
        note: l10n.reviewAskOwnWords,
        onTap: busy ? null : () => showReviseSheet(context, flow: flow, part: DraftPart.character),
      ),
    ]);
  }
}

/// The character's name, with their age, their people and their standing, typed by the player.
class _Who extends StatelessWidget {
  const _Who({required this.character, this.onTap});

  final DraftCharacter character;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final about = [
      if (character.age case final age?) l10n.reviewYearsOld(age),
      if (character.people.isNotEmpty) character.people,
      if (character.standing.isNotEmpty) character.standing,
    ].join(' · ');
    return Semantics(
      button: true,
      hint: l10n.reviewEditName,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.lg, Space.lg, Space.md, Space.md),
          child: Row(
            children: [
              ExcludeSemantics(child: PortraitAvatar(name: character.name, size: 44)),
              const SizedBox(width: Space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(character.name, style: theme.textTheme.titleLarge),
                    if (about.isNotEmpty) ...[
                      const SizedBox(height: Space.xxs),
                      Text(
                        about,
                        style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: Space.sm),
              const ExcludeSemantics(child: _Mark(direct: true)),
            ],
          ),
        ),
      ),
    );
  }
}

/// The rungs of the world's ladder everyone has heard of, with the character's own lit (G18).
class _Rungs extends StatelessWidget {
  const _Rungs({required this.ladder});

  final DraftLadder ladder;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final scheme = Theme.of(context).colorScheme;
    Widget rung(String name, {bool here = false, bool beyond = false}) => Semantics(
      // Their own rung is read once, with where they stand.
      label: here ? '$name, ${l10n.reviewRungHere}' : null,
      excludeSemantics: here,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.xs),
        decoration: BoxDecoration(
          color: here ? colors.accentSoft : null,
          borderRadius: const BorderRadius.all(Radius.circular(Radii.pill)),
          border: Border.all(
            color: here ? colors.accent.withValues(alpha: 0.7) : scheme.outlineVariant,
          ),
        ),
        child: Text(
          name,
          style: context.lucidText.meta.copyWith(
            color: here
                ? colors.onAccentSoft
                : beyond
                ? colors.textMuted
                : colors.textSecondary,
          ),
        ),
      ),
    );
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: [
        for (final (i, name) in ladder.rungs.indexed) rung(name, here: i == ladder.at),
        if (ladder.more) rung(l10n.reviewRungsBeyond, beyond: true),
      ],
    );
  }
}

/// The world: its rules, each locked for the whole story or true for now, then what the
/// storyteller drafted of it, row by row.
class _World extends StatelessWidget {
  const _World({required this.flow, required this.draft});

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
    return _Rows([
      Column(
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
      ),
      for (final kind in _worldRows)
        if (draft.linesOf(DraftPart.world, kind) case final lines when lines.isNotEmpty)
          _Row(
            label: l10n.row(kind),
            text: lines.join('\n'),
            direct: false,
            onTap: _askAt(context, flow, DraftPart.world, kind, lines.join('\n')),
          ),
      _Ask(
        label: l10n.reviewAskWorld,
        onTap: busy ? null : () => showReviseSheet(context, flow: flow, part: DraftPart.world),
      ),
    ]);
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
                child: Padding(padding: EdgeInsets.only(top: 3), child: _Mark(direct: true)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// What the player's own words named of how the story starts: a deadline, an open question, a
/// person, a connection, a goal (G1). Nothing else of the start is shown.
class _Yours extends StatelessWidget {
  const _Yours({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

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
    final openers = draft.openers;
    if (openers.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Text(
          l10n.reviewYoursNone,
          style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
        ),
      );
    }
    return _Rows([
      for (final (part, line) in openers)
        _Row(
          label: l10n.row(line.kind),
          text: line.text,
          direct: false,
          leading: Icon(_icon(line.kind), size: 20, color: colors.accent),
          onTap: _askAt(context, flow, part, line.kind, line.text),
        ),
    ]);
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

/// How the story plays: the rating (F2, F8), difficulty (A5), world events (W16), physics (A9)
/// and the gift (G22), on the same screen. A choice that redrafts nothing is saved as it is
/// picked; one that redrafts something says what it costs first.
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

  /// Saves a free choice at once, or asks first when it redrafts something.
  Future<void> _pick(DraftEdit edit, {required String label, required (String, String) choice}) {
    if (redraftFor(widget.draft, edit).isFree) return _save(edit);
    return showChoiceSheet(
      context,
      flow: _flow,
      title: label,
      choice: choice.$1,
      body: choice.$2,
      edit: edit,
    );
  }

  Future<void> _save(DraftEdit edit) async {
    setState(() => _saving = edit);
    final failure = await _flow.edit(edit);
    if (!mounted) return;
    setState(() => _saving = null);
    if (failure == null) return;
    final l10n = context.l10n;
    final text = switch (failure) {
      ApiException(code: ApiErrorCode.versionConflict) => l10n.reviewConflict,
      _ => describeError(l10n, failure).message,
    };
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(text)));
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
                : (value) => _pick(
                    DraftEdit(rating: value),
                    label: l10n.createRatingLabel,
                    choice: (l10n.rating(value), l10n.ratingBody(value)),
                  ),
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
          ChoiceField<GiftStrength>(
            label: l10n.giftLabel,
            values: GiftStrength.values,
            value: saving?.giftStrength ?? advanced.giftStrength,
            labelOf: l10n.gift,
            bodyOf: l10n.giftBody,
            onChanged: busy
                ? null
                : (value) => _pick(
                    DraftEdit(giftStrength: value),
                    label: l10n.giftLabel,
                    choice: (l10n.gift(value), l10n.giftBody(value)),
                  ),
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
