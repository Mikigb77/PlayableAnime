import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../story/record_widgets.dart';
import '../story/sheet.dart';
import '../story/sheet_view.dart';
import 'create_flow.dart';
import 'draft.dart';
import 'draft_sheets.dart';
import 'draft_widgets.dart';
import 'review_widgets.dart';

/// The second screen of the review: the character, and only the character (G2; Miki,
/// 2026-11-14), laid out as the story's own Character page will show them, so what the player
/// approves here is what they find in play.
///
/// Who they are comes first, typed by the player. Then how they learn (A4), before anything
/// else the storyteller drafted: most players describe a character in a line and go on, without
/// knowing the story tells a knack from a genius from one of a kind. So the screen says which of
/// those it read, quotes the player's own words it read it from, says what each is worth, and
/// offers the words to change it. Then their path, their skills with the dice each throws, their
/// powers and the gift, what they are like and what they carry.
class CharacterReview extends StatelessWidget {
  const CharacterReview({super.key, required this.flow});

  final CreateFlow flow;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return ListenableBuilder(
      listenable: flow,
      builder: (context, _) {
        final draft = flow.draft!;
        final busy = flow.busy;
        final character = draft.character;
        VoidCallback? typed(PlainField field) =>
            busy ? null : () => showFieldSheet(context, flow: flow, field: field);
        return ListView(
          padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, Space.xxl),
          children: [
            ContentColumn.reading(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ReviewSteps(flow: flow),
                  const SizedBox(height: Space.xl),
                  _Header(
                    character: character,
                    onTap: busy ? null : () => showNameSheet(context, flow: flow),
                  ),
                  const SizedBox(height: Space.lg),
                  const ReviewLegend(),
                  const SizedBox(height: Space.md),
                  ReviewCard(
                    child: ReviewRows([
                      ReviewRow(
                        label: l10n.rowLooks,
                        text: character.looks,
                        direct: true,
                        onTap: typed(PlainField.looks),
                      ),
                      ReviewRow(
                        label: l10n.rowManner,
                        text: character.manner,
                        direct: true,
                        onTap: typed(PlainField.manner),
                      ),
                    ]),
                  ),
                  if (flow.redrafting.character) ...[
                    const SizedBox(height: Space.xl),
                    ReviewCard(
                      redrafting: l10n.reviewRedraftingCharacter,
                      child: const SizedBox.shrink(),
                    ),
                  ] else
                    _Drafted(flow: flow, draft: draft),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

/// Who they are: their portrait, their name, and their age, their people and their standing in
/// a line, as the story's Character page opens. The name and the age are the player's to type.
class _Header extends StatelessWidget {
  const _Header({required this.character, this.onTap});

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
        borderRadius: Radii.card,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Space.xs),
          child: Row(
            children: [
              ExcludeSemantics(child: PortraitAvatar(name: character.name, size: 76, ring: true)),
              const SizedBox(width: Space.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Semantics(
                      header: true,
                      child: Text(character.name, style: theme.textTheme.headlineMedium),
                    ),
                    if (about.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xxs),
                        child: Text(
                          about,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: Space.sm),
              const ExcludeSemantics(child: ReviewMark(direct: true)),
            ],
          ),
        ),
      ),
    );
  }
}

/// What the storyteller drafted of the character, a section each, in the Character page's own
/// pieces. A section the sheet has nothing for falls back on the summary's line for it, and has
/// no place when that is empty too.
class _Drafted extends StatelessWidget {
  const _Drafted({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final sheet = draft.sheet;
    String lines(LineKind kind) => draft.linesOf(DraftPart.character, kind).join('\n');
    VoidCallback? ask(LineKind kind, String label, [String? text]) =>
        askAt(context, flow, DraftPart.character, kind, text ?? lines(kind), label: label);

    final rank = lines(LineKind.rank);
    final ladder = draft.ladder;
    final path = ladder == null ? null : _pathOf(ladder);
    final skills = lines(LineKind.skills);
    final power = lines(LineKind.power);
    final nature = [lines(LineKind.traits), lines(LineKind.nature)].where((l) => l.isNotEmpty);
    final wants = _wants(lines(LineKind.nature), chips: sheet.temperament.isNotEmpty);
    final belongings = lines(LineKind.belongings);
    final openers = draft.openers.any((opener) => opener.$1 == DraftPart.character);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Learning(flow: flow, draft: draft),
        if (path != null || ladder != null || rank.isNotEmpty) ...[
          _Section(l10n.sheetPath, kind: LineKind.rank, onAsk: ask(LineKind.rank, l10n.sheetPath)),
          if (path != null)
            SheetPathCard(path: path)
          else
            RecordCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (rank.isNotEmpty) _Line(rank),
                  if (ladder != null) ...[
                    if (rank.isNotEmpty) const SizedBox(height: Space.md),
                    _Rungs(ladder: ladder),
                  ],
                ],
              ),
            ),
        ],
        if (sheet.skills.isNotEmpty || skills.isNotEmpty) ...[
          _Section(
            l10n.sheetSkills,
            kind: LineKind.skills,
            onAsk: ask(LineKind.skills, l10n.sheetSkills),
          ),
          if (sheet.skills.isNotEmpty)
            SheetSkillList(skills: sheet.skills)
          else
            RecordCard(child: _Line(skills)),
        ],
        _Section(
          l10n.sheetPowers,
          kind: LineKind.power,
          onAsk: ask(LineKind.power, l10n.sheetPowers),
        ),
        if (sheet.hasMoves)
          SheetMoves(sheet: sheet)
        else if (power.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: RecordCard(child: _Line(power)),
          ),
        _Gift(flow: flow, draft: draft),
        if (sheet.traits.isNotEmpty || sheet.temperament.isNotEmpty || nature.isNotEmpty) ...[
          _Section(
            l10n.sheetTraits,
            kind: LineKind.nature,
            onAsk: ask(LineKind.nature, l10n.sheetTraits, nature.join('\n')),
          ),
          if (sheet.traits.isNotEmpty || sheet.temperament.isNotEmpty) ...[
            SheetNature(sheet: sheet, learning: false),
            // What they want shows only when the player's own words say it (G1).
            if (wants.isNotEmpty) RecordCard(child: _Line(wants)),
          ] else
            RecordCard(child: _Line(nature.join('\n'))),
        ],
        _Section(
          l10n.sheetCarried,
          kind: LineKind.belongings,
          onAsk: ask(LineKind.belongings, l10n.sheetCarried),
        ),
        if (sheet.items.isEmpty && sheet.moneyLabel == null && belongings.isNotEmpty)
          RecordCard(child: _Line(belongings))
        else
          SheetCarried(sheet: sheet),
        if (openers) ...[
          _Section(l10n.reviewYours),
          ReviewCard(
            child: ReviewOpeners(flow: flow, draft: draft, part: DraftPart.character),
          ),
        ],
        const SizedBox(height: Space.xl),
        ReviewCard(
          child: ReviewAsk(
            label: l10n.reviewAskCharacter,
            note: l10n.reviewAskOwnWords,
            onTap: flow.busy
                ? null
                : () => showReviseSheet(context, flow: flow, part: DraftPart.character),
          ),
        ),
      ],
    );
  }
}

/// The world's ladder as the Character page draws a path, from what the draft tells of it: the
/// rungs everyone has heard of, theirs lit with its stage. Null when they stand above those.
SheetPath? _pathOf(DraftLadder ladder) {
  final at = ladder.at;
  if (at == null || at < 0 || at >= ladder.rungs.length) return null;
  return SheetPath(
    name: ladder.name,
    rungs: [
      for (final (i, name) in ladder.rungs.take(at + 1).indexed)
        SheetRung(name: name, stage: i == at ? ladder.stage : ''),
    ],
    above: [for (final name in ladder.rungs.skip(at + 1)) SheetRungAbove(name: name, known: true)],
  );
}

/// What the character wants, out of the summary's line of their nature: the line leads with
/// their temperament, which the screen shows as [chips], and says what they want after it.
String _wants(String nature, {required bool chips}) {
  if (!chips) return nature;
  final cut = nature.indexOf('. ');
  return cut < 0 ? '' : nature.substring(cut + 2);
}

/// The name of a section, as the Character page names it, with the wand that asks the
/// storyteller to change what is under it.
class _Section extends StatelessWidget {
  const _Section(this.label, {this.kind, this.onAsk});

  final String label;

  /// What the section tells of, when it can be asked about.
  final LineKind? kind;
  final VoidCallback? onAsk;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: Space.lg, bottom: Space.xs),
    child: ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 48),
      child: Row(
        children: [
          Expanded(child: Semantics(header: true, child: Eyebrow(label))),
          if (kind case final kind?)
            IconButton(
              key: ValueKey('review.ask.${kind.name}'),
              tooltip: context.l10n.reviewAskHere,
              onPressed: onAsk,
              color: context.lucid.accent,
              icon: const Icon(Icons.auto_fix_high_rounded, size: 20),
            ),
        ],
      ),
    ),
  );
}

/// A line of the summary, where the sheet has nothing to lay out in its place.
class _Line extends StatelessWidget {
  const _Line(this.text);

  final String text;

  @override
  Widget build(BuildContext context) =>
      Text(text, style: context.lucidText.narration.copyWith(fontSize: 16, height: 1.45));
}

/// How they learn (A4): each talent with how strong it is, the pace it gives, what it covers
/// and the player's own words it was read from, or that nothing sets them apart. Under it, what
/// each strength is worth, and the words that change it, started for the player to finish.
class _Learning extends StatelessWidget {
  const _Learning({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final talents = draft.sheet.talents;
    final line = draft.linesOf(DraftPart.character, LineKind.talents).join('\n');
    VoidCallback? ask([String seed = '']) => askAt(
      context,
      flow,
      DraftPart.character,
      LineKind.talents,
      line,
      label: l10n.sheetLearning,
      seed: seed,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Section(l10n.sheetLearning, kind: LineKind.talents, onAsk: ask()),
        if (talents.isNotEmpty)
          for (final talent in talents) SheetTalentEntry(talent: talent)
        else if (line.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: RecordCard(child: _Line(line)),
          )
        else
          RecordEntry(
            key: const ValueKey('review.learning.ordinary'),
            icon: Icons.trending_flat_rounded,
            title: l10n.learnOrdinary,
            children: [RecordLine(l10n.learnOrdinaryBody)],
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xs, Space.xs, Space.xs, 0),
          child: Text(
            l10n.learnScale,
            style: context.lucidText.meta.copyWith(color: colors.textMuted),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.xs, Space.md, Space.xs, Space.sm),
          child: Text(
            l10n.learnAskLabel,
            style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
          ),
        ),
        Wrap(
          spacing: Space.sm,
          runSpacing: Space.sm,
          children: [
            _Seed(
              key: const ValueKey('review.seed.genius'),
              label: l10n.learnSeedGenius,
              onTap: ask(l10n.learnSeedGeniusText),
            ),
            _Seed(
              key: const ValueKey('review.seed.unique'),
              label: l10n.learnSeedUnique,
              onTap: ask(l10n.learnSeedUniqueText),
            ),
            _Seed(
              key: const ValueKey('review.seed.knack'),
              label: l10n.learnSeedKnack,
              onTap: ask(l10n.learnSeedKnackText),
            ),
            if (talents.isNotEmpty || line.isNotEmpty)
              _Seed(
                key: const ValueKey('review.seed.none'),
                label: l10n.learnSeedNone,
                onTap: ask(l10n.learnSeedNoneText),
              ),
          ],
        ),
      ],
    );
  }
}

/// Words that start a change for the player, as a chip: tapping it opens the box where they
/// tell the storyteller, with the words already in it.
class _Seed extends StatelessWidget {
  const _Seed({super.key, required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Semantics(
      button: true,
      enabled: onTap != null,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(Radii.lg),
        child: Container(
          constraints: const BoxConstraints(minHeight: 40),
          padding: const EdgeInsets.fromLTRB(10, 6, 14, 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Radii.lg),
            border: Border.all(color: colors.accent.withValues(alpha: 0.45)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              ExcludeSemantics(
                child: Icon(Icons.auto_fix_high_rounded, size: 15, color: colors.accent),
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  label,
                  style: theme.textTheme.labelLarge!.copyWith(
                    fontSize: 13.5,
                    color: colors.textPrimary,
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

/// The rungs of the world's ladder everyone has heard of (G18), for a character who stands
/// above them all, so on no rung the draft can light.
class _Rungs extends StatelessWidget {
  const _Rungs({required this.ladder});

  final DraftLadder ladder;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final scheme = Theme.of(context).colorScheme;
    Widget rung(String name, {bool beyond = false}) => Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.xs),
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.all(Radius.circular(Radii.pill)),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Text(
        name,
        style: context.lucidText.meta.copyWith(
          color: beyond ? colors.textMuted : colors.textSecondary,
        ),
      ),
    );
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: [
        for (final name in ladder.rungs) rung(name),
        if (ladder.more) rung(context.l10n.reviewRungsBeyond, beyond: true),
      ],
    );
  }
}

/// The strongest gift the character holds (G22), chosen next to their powers. Picking another
/// redrafts the character, so it says what that costs first.
class _Gift extends StatelessWidget {
  const _Gift({required this.flow, required this.draft});

  final CreateFlow flow;
  final Draft draft;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    Future<void> pick(GiftStrength value) async {
      final edit = DraftEdit(giftStrength: value);
      if (!redraftFor(draft, edit).isFree) {
        return showChoiceSheet(
          context,
          flow: flow,
          title: l10n.giftLabel,
          choice: l10n.gift(value),
          body: l10n.giftBody(value),
          edit: edit,
        );
      }
      final failure = await flow.edit(edit);
      if (failure != null && context.mounted) showEditFailure(context, failure);
    }

    return RecordCard(
      padding: const EdgeInsets.fromLTRB(Space.lg, 0, Space.lg, Space.lg),
      child: ChoiceField<GiftStrength>(
        label: l10n.giftLabel,
        top: Space.lg,
        values: GiftStrength.values,
        value: draft.advanced.giftStrength,
        labelOf: l10n.gift,
        bodyOf: l10n.giftBody,
        onChanged: flow.busy ? null : pick,
      ),
    );
  }
}
