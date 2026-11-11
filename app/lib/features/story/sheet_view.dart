import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import 'sheet.dart';

/// A card of the sheet: a soft layer with a hairline edge.
class _SheetCard extends StatelessWidget {
  const _SheetCard({required this.child, this.padding = const EdgeInsets.all(Space.lg)});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: Radii.card,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: child,
    );
  }
}

/// How they are (G13): health, wounds and passing states as chips, then what is left of each
/// of the world's energies as a meter.
class SheetConditionView extends StatelessWidget {
  const SheetConditionView({super.key, required this.condition});

  final SheetCondition condition;

  /// How much of a chip's own color washes the page behind its words.
  static const double chipWash = 0.10;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final health = switch (condition.health) {
      Health.unhurt => colors.success,
      Health.hurt => colors.caution,
      _ => colors.danger,
    };
    final chips = [
      if (condition.healthLabel.isNotEmpty)
        _Chip(
          condition.healthLabel,
          tone: health,
          icon: condition.health == Health.unhurt
              ? Icons.favorite_rounded
              : Icons.heart_broken_rounded,
        ),
      // A wound that heals reads as harm; one that stays is part of them now.
      for (final wound in condition.wounds)
        _Chip(wound.text, tone: wound.lasting ? null : colors.danger),
      for (final state in condition.states)
        _Chip(
          state.endsLabel == null ? state.name : '${state.name} · ${state.endsLabel}',
          note: state.effect,
        ),
      if (condition.expectingLabel case final expecting?) _Chip(expecting, tone: colors.accent),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (chips.isNotEmpty) Wrap(spacing: Space.sm, runSpacing: Space.sm, children: chips),
        for (final reserve in condition.reserves)
          Padding(
            padding: const EdgeInsets.only(top: Space.md),
            child: _ReserveMeter(reserve: reserve),
          ),
      ],
    );
  }
}

/// A short state in a pill. With a [tone] it is tinted; without, it is quiet.
class _Chip extends StatelessWidget {
  const _Chip(this.text, {this.tone, this.icon, this.note = ''});

  final String text;
  final Color? tone;
  final IconData? icon;

  /// What it does, for whoever holds a finger on it or listens to it.
  final String note;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final tint = tone ?? colors.textSecondary;
    final chip = Container(
      padding: EdgeInsets.fromLTRB(icon == null ? 12 : 9, 6, 12, 6),
      decoration: BoxDecoration(
        color: tone?.withValues(alpha: SheetConditionView.chipWash),
        borderRadius: BorderRadius.circular(Radii.lg),
        border: Border.all(color: tint.withValues(alpha: tone == null ? 0.35 : 0.5)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon case final icon?) ...[
            Icon(icon, size: 15, color: tint),
            const SizedBox(width: 6),
          ],
          Flexible(
            child: Text(
              text,
              style: theme.textTheme.labelLarge!.copyWith(
                fontSize: 13.5,
                color: tone ?? colors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
    return note.isEmpty ? chip : Tooltip(message: note, child: chip);
  }
}

/// What is left of an energy such as qi or mana, as a bar and a share.
class _ReserveMeter extends StatelessWidget {
  const _ReserveMeter({required this.reserve});

  final SheetReserve reserve;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return MergeSemantics(
      child: Row(
        children: [
          Flexible(child: Text(reserve.name.asHeading, style: theme.textTheme.labelLarge)),
          const SizedBox(width: Space.md),
          Expanded(
            flex: 3,
            child: ExcludeSemantics(
              child: _Bar(share: reserve.level / 100, color: colors.accent, height: 6),
            ),
          ),
          const SizedBox(width: Space.md),
          Text(context.l10n.sheetPercent(reserve.level), style: context.lucidText.meta),
        ],
      ),
    );
  }
}

/// A rounded bar filled to [share].
class _Bar extends StatelessWidget {
  const _Bar({required this.share, required this.color, this.height = 4});

  final double share;
  final Color color;
  final double height;

  @override
  Widget build(BuildContext context) => ClipRRect(
    borderRadius: BorderRadius.circular(height),
    child: SizedBox(
      height: height,
      child: Stack(
        fit: StackFit.expand,
        children: [
          ColoredBox(color: Theme.of(context).colorScheme.surfaceContainerHighest),
          FractionallySizedBox(
            alignment: AlignmentDirectional.centerStart,
            widthFactor: share.clamp(0, 1).toDouble(),
            child: ColoredBox(color: color),
          ),
        ],
      ),
    ),
  );
}

/// Where they stand on one of the world's ladders (G18): their own rung on top, lit, with its
/// stage, and under it the rungs they climbed. Nothing is drawn above: which rungs lie higher
/// is the story's to tell (C6).
class SheetPathCard extends StatelessWidget {
  const SheetPathCard({super.key, required this.path});

  final SheetPath path;

  @override
  Widget build(BuildContext context) {
    final rungs = path.rungs.reversed.toList();
    return _SheetCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            path.name.toUpperCase(),
            style: context.lucidText.overline.copyWith(color: context.lucid.textMuted),
          ),
          const SizedBox(height: Space.md),
          for (final (i, rung) in rungs.indexed)
            _RungRow(rung: rung, here: i == 0, last: i == rungs.length - 1),
        ],
      ),
    );
  }
}

class _RungRow extends StatelessWidget {
  const _RungRow({required this.rung, required this.here, required this.last});

  final SheetRung rung;

  /// The rung they stand on.
  final bool here;
  final bool last;

  static const double _track = 26;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    final node = here
        ? Container(
            width: 20,
            height: 20,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: colors.accentGradient(),
              boxShadow: [BoxShadow(color: colors.accent.withValues(alpha: 0.45), blurRadius: 14)],
            ),
          )
        : Container(
            width: 16,
            height: 16,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: scheme.surfaceContainerHigh,
              border: Border.all(color: scheme.outline),
            ),
            child: Icon(Icons.check_rounded, size: 11, color: colors.textMuted),
          );
    return MergeSemantics(
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ExcludeSemantics(
              child: SizedBox(
                width: _track,
                child: Column(
                  children: [
                    SizedBox(height: here ? 5 : 3),
                    node,
                    if (!last)
                      Expanded(
                        child: Container(
                          width: 2,
                          margin: const EdgeInsets.symmetric(vertical: 3),
                          color: scheme.outlineVariant,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Padding(
                padding: EdgeInsets.only(bottom: last ? 0 : Space.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      rung.name.asHeading,
                      style: here
                          ? theme.textTheme.headlineSmall!.copyWith(color: colors.accent)
                          : context.lucidText.narration.copyWith(
                              fontSize: 16,
                              height: 1.35,
                              color: colors.textSecondary,
                            ),
                    ),
                    if (rung.stage.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xxs),
                        child: Text(rung.stage.asHeading, style: theme.textTheme.bodyLarge),
                      ),
                    if (rung.description.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xs),
                        child: Text(
                          rung.description,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The parts of the sheet a player looks things up in, one at a time: what they carry, their
/// skills, their powers and techniques, and what they are like. A part with nothing in it has
/// no tab, except what they carry: carrying nothing is worth saying (C10).
enum SheetTab { carried, skills, moves, nature }

class SheetTabs extends StatefulWidget {
  const SheetTabs({super.key, required this.sheet});

  final Sheet sheet;

  @override
  State<SheetTabs> createState() => _SheetTabsState();
}

class _SheetTabsState extends State<SheetTabs> {
  SheetTab _tab = SheetTab.carried;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final sheet = widget.sheet;
    final tabs = [
      SheetTab.carried,
      if (sheet.skills.isNotEmpty) SheetTab.skills,
      if (sheet.hasMoves) SheetTab.moves,
      if (sheet.hasNature) SheetTab.nature,
    ];
    final tab = tabs.contains(_tab) ? _tab : SheetTab.carried;
    String name(SheetTab tab) => switch (tab) {
      SheetTab.carried => l10n.sheetCarried,
      SheetTab.skills => l10n.sheetSkills,
      // Named for what it holds: a world with powers and no techniques says "Powers".
      SheetTab.moves => sheet.techniques.isEmpty ? l10n.sheetPowers : l10n.sheetMoves,
      SheetTab.nature => l10n.sheetTraits,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (tabs.length > 1)
          _TabStrip(
            tabs: [for (final t in tabs) (t, name(t))],
            selected: tab,
            onSelected: (t) => setState(() => _tab = t),
          )
        else
          SectionLabel(name(tab), padding: const EdgeInsets.only(bottom: Space.md)),
        const SizedBox(height: Space.md),
        switch (tab) {
          SheetTab.carried => _Carried(sheet: sheet),
          SheetTab.skills => _Skills(skills: sheet.skills),
          SheetTab.moves => _Moves(sheet: sheet),
          SheetTab.nature => _Nature(sheet: sheet),
        },
      ],
    );
  }
}

/// The tabs as one strip, the chosen one raised. They share the width when they fit and scroll
/// sideways when they don't, as at a large text size.
class _TabStrip extends StatelessWidget {
  const _TabStrip({required this.tabs, required this.selected, required this.onSelected});

  final List<(SheetTab, String)> tabs;
  final SheetTab selected;
  final ValueChanged<SheetTab> onSelected;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return LayoutBuilder(
      // A Material of its own, so a tab's ink stays inside the strip's rounded edge.
      builder: (context, constraints) => Material(
        color: scheme.surfaceContainerLowest,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.lg),
          side: BorderSide(color: scheme.outlineVariant),
        ),
        clipBehavior: Clip.antiAlias,
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.all(Space.xs),
          child: ConstrainedBox(
            constraints: BoxConstraints(minWidth: constraints.maxWidth - 2 * Space.xs),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                for (final (tab, name) in tabs)
                  _Tab(
                    key: ValueKey('sheet.tab.${tab.name}'),
                    name: name,
                    selected: tab == selected,
                    onTap: () => onSelected(tab),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Tab extends StatelessWidget {
  const _Tab({super.key, required this.name, required this.selected, required this.onTap});

  final String name;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    return Semantics(
      button: true,
      selected: selected,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(Radii.md),
        child: AnimatedContainer(
          duration: Motion.of(context, Motion.fast),
          curve: Motion.standard,
          constraints: const BoxConstraints(minHeight: 44),
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 9),
          decoration: BoxDecoration(
            color: selected ? scheme.surfaceContainerHigh : null,
            borderRadius: BorderRadius.circular(Radii.md),
            border: Border.all(
              color: selected ? colors.accent.withValues(alpha: 0.45) : const Color(0x00000000),
            ),
          ),
          child: Text(
            name,
            style: theme.textTheme.labelLarge!.copyWith(
              fontSize: 13.5,
              color: selected ? colors.textPrimary : colors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }
}

/// A small label over a group inside a tab.
class _GroupLabel extends StatelessWidget {
  const _GroupLabel(this.text, {this.first = false});

  final String text;

  /// The first thing in its tab, so with no room above it.
  final bool first;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(Space.xs, first ? Space.xs : Space.lg, Space.xs, Space.sm),
    child: Semantics(
      header: true,
      child: Text(
        text.toUpperCase(),
        style: context.lucidText.overline.copyWith(color: context.lucid.textMuted),
      ),
    ),
  );
}

/// The small square that leads an entry in.
class _Glyph extends StatelessWidget {
  const _Glyph(this.icon, {this.lit = false});

  final IconData icon;

  /// In the accent, for what is theirs to use: money, a power.
  final bool lit;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return ExcludeSemantics(
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: lit ? colors.accentSoft : Theme.of(context).colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(Radii.md),
        ),
        child: Icon(icon, size: 19, color: lit ? colors.onAccentSoft : colors.textSecondary),
      ),
    );
  }
}

/// One entry of the sheet in its own card: a glyph, its name, a word or a mark on the right,
/// and what there is to say about it underneath.
class _Entry extends StatelessWidget {
  const _Entry({
    required this.icon,
    required this.title,
    this.lit = false,
    this.trailing,
    this.children = const [],
  });

  final IconData icon;
  final String title;
  final bool lit;
  final Widget? trailing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: MergeSemantics(
        child: _SheetCard(
          padding: const EdgeInsets.all(Space.md),
          child: Row(
            crossAxisAlignment: children.isEmpty
                ? CrossAxisAlignment.center
                : CrossAxisAlignment.start,
            children: [
              _Glyph(icon, lit: lit),
              const SizedBox(width: Space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Titled(
                      title: Text(title, style: theme.textTheme.titleMedium),
                      trailing: trailing,
                    ),
                    ...children,
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

/// A name with its mark at the far edge of the same line. The mark drops under the name when
/// the two don't fit, as at a large text size.
class _Titled extends StatelessWidget {
  const _Titled({required this.title, this.trailing});

  final Widget title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: double.infinity,
    child: Wrap(
      spacing: Space.md,
      runSpacing: Space.xs,
      alignment: WrapAlignment.spaceBetween,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [title, ?trailing],
    ),
  );
}

/// A line of an entry: what it is or does.
class _Line extends StatelessWidget {
  const _Line(this.text, {this.quiet = false});

  final String text;

  /// A note in the margin, such as where a technique comes from.
  final bool quiet;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.only(top: Space.xs),
      child: Text(
        text,
        style: quiet
            ? context.lucidText.meta.copyWith(color: colors.textMuted)
            : Theme.of(context).textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
      ),
    );
  }
}

/// A word on the right of an entry, in small capitals: what kind of thing it is.
class _Kind extends StatelessWidget {
  const _Kind(this.text, {this.color});

  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: context.lucidText.overline.copyWith(color: color ?? context.lucid.textMuted),
  );
}

/// The dice a skill or a technique throws (A3), as five small dice with that many lit. The
/// line under the name says the count in words, so a screen reader skips the picture.
class _Dice extends StatelessWidget {
  const _Dice(this.count);

  final int count;

  static const _most = 5;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final scheme = Theme.of(context).colorScheme;
    return ExcludeSemantics(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _most; i++)
            Container(
              width: 9,
              height: 9,
              margin: EdgeInsets.only(left: i == 0 ? 0 : 4),
              decoration: BoxDecoration(
                color: i < count ? colors.accent : null,
                borderRadius: BorderRadius.circular(2.5),
                border: i < count ? null : Border.all(color: scheme.outline),
              ),
            ),
        ],
      ),
    );
  }
}

IconData _itemIcon(ItemKind kind) => switch (kind) {
  ItemKind.weapon => Icons.bolt_rounded,
  ItemKind.armour => Icons.shield_outlined,
  ItemKind.gear => Icons.handyman_outlined,
  ItemKind.treasure => Icons.diamond_outlined,
  ItemKind.consumable => Icons.hourglass_bottom_rounded,
  ItemKind.vehicle => Icons.navigation_outlined,
  ItemKind.property => Icons.house_outlined,
  ItemKind.document => Icons.article_outlined,
  ItemKind.other => Icons.inventory_2_outlined,
};

/// What they hold (C10): the purse, what is on them, then what they keep elsewhere.
class _Carried extends StatelessWidget {
  const _Carried({required this.sheet});

  final Sheet sheet;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final carried = sheet.carried.toList();
    final elsewhere = sheet.elsewhere.toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (sheet.moneyLabel case final money?)
          _Entry(icon: Icons.toll_outlined, title: money, lit: true),
        for (final item in carried) _ItemEntry(item: item),
        if (carried.isEmpty && sheet.moneyLabel == null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.xs, vertical: Space.sm),
            child: Text(
              l10n.sheetNothingCarried,
              style: Theme.of(
                context,
              ).textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
            ),
          ),
        if (elsewhere.isNotEmpty) ...[
          _GroupLabel(l10n.sheetElsewhere),
          for (final item in elsewhere) _ItemEntry(item: item),
        ],
      ],
    );
  }
}

class _ItemEntry extends StatelessWidget {
  const _ItemEntry({required this.item});

  final SheetItem item;

  @override
  Widget build(BuildContext context) => _Entry(
    icon: _itemIcon(item.kind),
    title: item.quantity > 1 ? '${item.name.asHeading} × ${item.quantity}' : item.name.asHeading,
    trailing: item.kindLabel.isEmpty ? null : _Kind(item.kindLabel),
    children: [
      if (item.description.isNotEmpty) _Line(item.description),
      if (item.history.isNotEmpty) _Line(item.history, quiet: true),
    ],
  );
}

/// What they have learned, the best first, each with its level in the world's words and the
/// dice it throws.
class _Skills extends StatelessWidget {
  const _Skills({required this.skills});

  final List<SheetSkill> skills;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    return _SheetCard(
      padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final (i, skill) in skills.indexed)
            MergeSemantics(
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: Space.md),
                decoration: BoxDecoration(
                  border: i == 0
                      ? null
                      : Border(top: BorderSide(color: theme.colorScheme.outlineVariant)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    _Titled(
                      title: Text(skill.name.asHeading, style: theme.textTheme.titleMedium),
                      trailing: _Dice(skill.dice),
                    ),
                    const SizedBox(height: Space.xxs),
                    Text(
                      [
                        if (skill.levelLabel.isNotEmpty) skill.levelLabel,
                        l10n.sheetDice(skill.dice),
                      ].join(' · '),
                      style: context.lucidText.meta.copyWith(color: colors.textSecondary),
                    ),
                    if (skill.notes.isNotEmpty) _Line(skill.notes),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// What they can do beyond the ordinary: each power with its limits and cost, then each
/// technique with how well they have it.
class _Moves extends StatelessWidget {
  const _Moves({required this.sheet});

  final Sheet sheet;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final both = sheet.powers.isNotEmpty && sheet.techniques.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (both) _GroupLabel(l10n.sheetPowers, first: true),
        for (final power in sheet.powers) _PowerEntry(power: power),
        if (both) _GroupLabel(l10n.sheetMoves),
        for (final technique in sheet.techniques) _TechniqueEntry(technique: technique),
      ],
    );
  }
}

class _PowerEntry extends StatelessWidget {
  const _PowerEntry({required this.power});

  final SheetPower power;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    return _Entry(
      icon: Icons.auto_awesome_rounded,
      lit: true,
      title: power.name.asHeading,
      trailing: power.readyLabel.isEmpty
          ? null
          : _Kind(power.readyLabel, color: power.ready ? colors.success : colors.caution),
      children: [
        if (power.description.isNotEmpty) _Line(power.description),
        for (final limit in power.limits) _Line('·  $limit'),
        if (power.cost.isNotEmpty) _Line(l10n.sheetCost(power.cost)),
        if (power.secret) _Line(l10n.sheetSecret, quiet: true),
      ],
    );
  }
}

class _TechniqueEntry extends StatelessWidget {
  const _TechniqueEntry({required this.technique});

  final SheetTechnique technique;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    final need = technique.need;
    return _Entry(
      icon: Icons.gesture_rounded,
      title: technique.name.asHeading,
      trailing: _Dice(technique.dice),
      children: [
        Padding(
          padding: const EdgeInsets.only(top: Space.xxs),
          child: Text(
            [
              if (technique.masteryLabel.isNotEmpty) technique.masteryLabel,
              l10n.sheetDice(technique.dice),
            ].join(' · '),
            style: context.lucidText.meta.copyWith(color: colors.textSecondary),
          ),
        ),
        if (technique.style.isNotEmpty) _Line(technique.style),
        if (technique.effect.isNotEmpty) _Line(technique.effect),
        if (technique.cost.isNotEmpty) _Line(l10n.sheetCost(technique.cost)),
        if (need != null) ...[
          const SizedBox(height: Space.md),
          ExcludeSemantics(
            child: _Bar(share: technique.uses / need, color: colors.accent),
          ),
          _Line(l10n.sheetUses(technique.uses, need), quiet: true),
        ],
        if (technique.sourceLabel.isNotEmpty) _Line(technique.sourceLabel, quiet: true),
      ],
    );
  }
}

/// What they are like: their temperament in a few words, what sets them apart, and how they
/// learn (A4).
class _Nature extends StatelessWidget {
  const _Nature({required this.sheet});

  final Sheet sheet;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (sheet.temperament.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.md),
            child: Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [for (final word in sheet.temperament) _Chip(word.asHeading)],
            ),
          ),
        for (final trait in sheet.traits)
          _Entry(
            icon: switch (trait.kind) {
              TraitKind.gift => Icons.star_outline_rounded,
              TraitKind.flaw => Icons.heart_broken_outlined,
              TraitKind.quirk => Icons.fingerprint_rounded,
            },
            title: trait.name.asHeading,
            trailing: trait.kindLabel.isEmpty
                ? null
                : _Kind(
                    trait.kindLabel,
                    color: switch (trait.kind) {
                      TraitKind.gift => colors.success,
                      TraitKind.flaw => colors.caution,
                      TraitKind.quirk => null,
                    },
                  ),
            children: [if (trait.description.isNotEmpty) _Line(trait.description)],
          ),
        if (sheet.talents.isNotEmpty) ...[
          _GroupLabel(l10n.sheetLearning),
          for (final talent in sheet.talents)
            _Entry(
              icon: talent.weakness ? Icons.trending_down_rounded : Icons.trending_up_rounded,
              title: talent.name.asHeading,
              trailing: talent.strengthLabel.isEmpty
                  ? null
                  : _Kind(
                      talent.strengthLabel,
                      color: talent.weakness ? colors.caution : colors.accent,
                    ),
              children: [
                if (talent.paceLabel.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: Space.xxs),
                    child: Text(
                      talent.paceLabel,
                      style: context.lucidText.meta.copyWith(color: colors.textSecondary),
                    ),
                  ),
                if (talent.covers.isNotEmpty) _Line(talent.covers.asHeading),
              ],
            ),
          if (sheet.talentNotes.isNotEmpty)
            _SheetCard(
              padding: const EdgeInsets.fromLTRB(Space.lg, Space.sm, Space.lg, Space.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [for (final note in sheet.talentNotes) _Line(note)],
              ),
            ),
        ],
      ],
    );
  }
}
