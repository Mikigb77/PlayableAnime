import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../core/names.dart';
import '../../design/design.dart';
import 'record_widgets.dart';
import 'sheet.dart';

/// How they are (G13): health, wounds and passing states as chips, then what is left of each
/// of the world's energies as a meter.
class SheetConditionView extends StatelessWidget {
  const SheetConditionView({super.key, required this.condition});

  final SheetCondition condition;

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
        RecordChip(
          condition.healthLabel,
          tone: health,
          icon: condition.health == Health.unhurt
              ? Icons.favorite_rounded
              : Icons.heart_broken_rounded,
        ),
      // A wound that heals reads as harm; one that stays is part of them now.
      for (final wound in condition.wounds)
        RecordChip(wound.text, tone: wound.lasting ? null : colors.danger),
      for (final state in condition.states)
        RecordChip(
          state.endsLabel == null ? state.name : '${state.name} · ${state.endsLabel}',
          note: state.effect,
        ),
      if (condition.expectingLabel case final expecting?)
        RecordChip(expecting, tone: colors.accent),
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
  const _Bar({super.key, required this.share, required this.color, this.height = 4});

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

/// One of the world's ladders as far as they know it (G18, C6), highest first. On top, what
/// nobody has told them, and under it whoever they have seen stand above every rung they know
/// of, so the ladder widens when the story reaches past it. Then the rungs over their own that
/// they have heard of: dashed while only heard of, solid once confirmed, with room left open
/// where rungs nobody named lie between. Then their own rung, lit, with the stage of their rank
/// and a bar of how full it is (G19), and under it the rungs they climbed.
class SheetPathCard extends StatelessWidget {
  const SheetPathCard({super.key, required this.path});

  final SheetPath path;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final rows = [
      _Rung(look: _Look.fog, name: l10n.pathAbove, note: l10n.pathAboveNote),
      if (path.higher.isNotEmpty)
        _Rung(look: _Look.higher, name: l10n.pathHigher, note: path.higher),
      for (final rung in path.above.reversed) ...[
        _Rung(
          look: rung.known ? _Look.known : _Look.heard,
          name: rung.name.asHeading,
          note: rung.note,
          said: rung.said,
        ),
        if (rung.gapBelow)
          _Rung(look: _Look.gap, name: l10n.pathUnmeasured, note: l10n.pathUnmeasuredNote),
      ],
      for (final (i, rung) in path.rungs.reversed.indexed)
        _Rung(
          look: i == 0 ? _Look.here : _Look.behind,
          name: rung.name.asHeading,
          stage: rung.stage.asHeading,
          filled: i == 0 ? rung.filled : null,
          description: rung.description,
          note: rung.note,
        ),
    ];
    return RecordCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            path.name.toUpperCase(),
            style: context.lucidText.overline.copyWith(color: context.lucid.textMuted),
          ),
          const SizedBox(height: Space.md),
          for (final (i, rung) in rows.indexed)
            _RungRow(
              key: ValueKey('path.${rung.look.name}.$i'),
              rung: rung,
              last: i == rows.length - 1,
            ),
        ],
      ),
    );
  }
}

/// How a row of the path is drawn.
enum _Look {
  /// What lies above everything they know of.
  fog,

  /// Where someone they have seen stands, above every rung they know of: a rung with no name.
  higher,

  /// A rung a scene named, not confirmed yet.
  heard,

  /// A rung above their own that the story confirmed.
  known,

  /// Room between two rungs they know of, with what lies in it unknown.
  gap,

  /// The rung they stand on.
  here,

  /// A rung they climbed.
  behind;

  /// Above their own rung: drawn lighter, on a dashed track.
  bool get above => index < here.index;
}

class _Rung {
  const _Rung({
    required this.look,
    required this.name,
    this.stage = '',
    this.filled,
    this.description = '',
    this.note = '',
    this.said = const [],
  });

  final _Look look;
  final String name;
  final String stage;

  /// How full the rank on their own rung is, from 0 to 1 (G19).
  final double? filled;
  final String description;
  final String note;
  final List<String> said;
}

class _RungRow extends StatelessWidget {
  const _RungRow({super.key, required this.rung, required this.last});

  final _Rung rung;
  final bool last;

  static const double _track = 26;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    final look = rung.look;
    final here = look == _Look.here;
    final name = switch (look) {
      _Look.here => theme.textTheme.headlineSmall!.copyWith(color: colors.accent),
      _Look.fog ||
      _Look.higher ||
      _Look.gap => theme.textTheme.titleSmall!.copyWith(color: colors.textMuted),
      _Look.heard => context.lucidText.narration.copyWith(
        fontSize: 16,
        height: 1.35,
        color: colors.textMuted,
      ),
      _Look.known || _Look.behind => context.lucidText.narration.copyWith(
        fontSize: 16,
        height: 1.35,
        color: colors.textSecondary,
      ),
    };
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
                    _RungNode(look: look),
                    if (!last)
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: look.above
                              ? CustomPaint(
                                  size: const Size(2, double.infinity),
                                  painter: _DashedLine(scheme.outlineVariant),
                                )
                              : Container(width: 2, color: scheme.outlineVariant),
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
                    Text(rung.name, style: name),
                    if (rung.stage.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xxs),
                        child: Text(rung.stage, style: theme.textTheme.bodyLarge),
                      ),
                    if (rung.filled case final filled?)
                      // G19: the rank fills toward the next rung. The stage says it in words.
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xs),
                        child: ExcludeSemantics(
                          child: FractionallySizedBox(
                            alignment: AlignmentDirectional.centerStart,
                            widthFactor: 0.6,
                            child: _Bar(
                              key: const ValueKey('rank-filled'),
                              share: filled,
                              color: colors.accent,
                            ),
                          ),
                        ),
                      ),
                    if (rung.description.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: Space.xs),
                        child: Text(
                          rung.description,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                        ),
                      ),
                    for (final line in rung.said) RecordLine(line),
                    if (rung.note.isNotEmpty) RecordLine(rung.note, quiet: true),
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

/// The mark on the track for one row of the path.
class _RungNode extends StatelessWidget {
  const _RungNode({required this.look});

  final _Look look;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final scheme = Theme.of(context).colorScheme;
    Widget ring({required Color line, bool dashed = false, Widget? child}) => SizedBox(
      width: 16,
      height: 16,
      child: CustomPaint(
        painter: _Ring(line, dashed: dashed),
        child: Center(child: child),
      ),
    );
    final unknown = Text(
      '?',
      style: context.lucidText.overline.copyWith(color: colors.textMuted, height: 1),
    );
    return switch (look) {
      _Look.here => Container(
        width: 20,
        height: 20,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: colors.accentGradient(),
          boxShadow: [BoxShadow(color: colors.accent.withValues(alpha: 0.45), blurRadius: 14)],
        ),
      ),
      _Look.behind => Container(
        width: 16,
        height: 16,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: scheme.surfaceContainerHigh,
          border: Border.all(color: scheme.outline),
        ),
        child: Icon(Icons.check_rounded, size: 11, color: colors.textMuted),
      ),
      _Look.known => ring(line: colors.accent),
      _Look.heard => ring(line: colors.textMuted, dashed: true),
      _Look.fog => ring(line: scheme.outlineVariant, dashed: true, child: unknown),
      _Look.higher => ring(line: colors.textMuted, child: unknown),
      _Look.gap => SizedBox(width: 16, height: 16, child: Center(child: unknown)),
    };
  }
}

/// A circle on the track: whole for a rung the story confirmed or one someone stands on,
/// dashed for one only heard of.
class _Ring extends CustomPainter {
  const _Ring(this.color, {this.dashed = false});

  final Color color;
  final bool dashed;

  static const int _dashes = 8;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final box = Offset.zero & size;
    final circle = box.deflate(paint.strokeWidth / 2);
    if (!dashed) {
      canvas.drawOval(circle, paint);
      return;
    }
    const step = 2 * math.pi / _dashes;
    for (var i = 0; i < _dashes; i++) {
      canvas.drawArc(circle, i * step, step * 0.55, false, paint);
    }
  }

  @override
  bool shouldRepaint(_Ring old) => old.color != color || old.dashed != dashed;
}

/// The track above their own rung: a way nobody has walked them through yet.
class _DashedLine extends CustomPainter {
  const _DashedLine(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 2;
    final x = size.width / 2;
    for (var y = 0.0; y < size.height; y += 7) {
      canvas.drawLine(Offset(x, y), Offset(x, (y + 3).clamp(0, size.height)), paint);
    }
  }

  @override
  bool shouldRepaint(_DashedLine old) => old.color != color;
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
          SheetTab.carried => SheetCarried(sheet: sheet),
          SheetTab.skills => SheetSkillList(skills: sheet.skills),
          SheetTab.moves => SheetMoves(sheet: sheet),
          SheetTab.nature => SheetNature(sheet: sheet),
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
class SheetCarried extends StatelessWidget {
  const SheetCarried({super.key, required this.sheet});

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
          RecordEntry(icon: Icons.toll_outlined, title: money, lit: true),
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
          RecordGroupLabel(l10n.sheetElsewhere),
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
  Widget build(BuildContext context) => RecordEntry(
    icon: _itemIcon(item.kind),
    title: item.quantity > 1 ? '${item.name.asHeading} × ${item.quantity}' : item.name.asHeading,
    trailing: item.kindLabel.isEmpty ? null : RecordKind(item.kindLabel),
    children: [
      if (item.description.isNotEmpty) RecordLine(item.description),
      if (item.history.isNotEmpty) RecordLine(item.history, quiet: true),
    ],
  );
}

/// What they have learned, the best first, each with its level in the world's words and the
/// dice it throws.
class SheetSkillList extends StatelessWidget {
  const SheetSkillList({super.key, required this.skills});

  final List<SheetSkill> skills;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    return RecordCard(
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
                    RecordTitled(
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
                    if (skill.notes.isNotEmpty) RecordLine(skill.notes),
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
class SheetMoves extends StatelessWidget {
  const SheetMoves({super.key, required this.sheet});

  final Sheet sheet;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final both = sheet.powers.isNotEmpty && sheet.techniques.isNotEmpty;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (both) RecordGroupLabel(l10n.sheetPowers, first: true),
        for (final power in sheet.powers) _PowerEntry(power: power),
        if (both) RecordGroupLabel(l10n.sheetMoves),
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
    return RecordEntry(
      icon: Icons.auto_awesome_rounded,
      lit: true,
      title: power.name.asHeading,
      trailing: power.readyLabel.isEmpty
          ? null
          : RecordKind(power.readyLabel, color: power.ready ? colors.success : colors.caution),
      children: [
        if (power.description.isNotEmpty) RecordLine(power.description),
        for (final limit in power.limits) RecordLine('·  $limit'),
        if (power.cost.isNotEmpty) RecordLine(l10n.sheetCost(power.cost)),
        if (power.secret) RecordLine(l10n.sheetSecret, quiet: true),
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
    return RecordEntry(
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
        if (technique.style.isNotEmpty) RecordLine(technique.style),
        if (technique.effect.isNotEmpty) RecordLine(technique.effect),
        if (technique.cost.isNotEmpty) RecordLine(l10n.sheetCost(technique.cost)),
        if (need != null) ...[
          const SizedBox(height: Space.md),
          ExcludeSemantics(
            child: _Bar(share: technique.uses / need, color: colors.accent),
          ),
          RecordLine(l10n.sheetUses(technique.uses, need), quiet: true),
        ],
        if (technique.sourceLabel.isNotEmpty) RecordLine(technique.sourceLabel, quiet: true),
      ],
    );
  }
}

/// What they are like: their temperament in a few words, what sets them apart, and how they
/// learn (A4), unless the screen says that somewhere of its own ([learning] false).
class SheetNature extends StatelessWidget {
  const SheetNature({super.key, required this.sheet, this.learning = true});

  final Sheet sheet;
  final bool learning;

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
              children: [for (final word in sheet.temperament) RecordChip(word.asHeading)],
            ),
          ),
        for (final trait in sheet.traits)
          RecordEntry(
            icon: switch (trait.kind) {
              TraitKind.gift => Icons.star_outline_rounded,
              TraitKind.flaw => Icons.heart_broken_outlined,
              TraitKind.quirk => Icons.fingerprint_rounded,
            },
            title: trait.name.asHeading,
            trailing: trait.kindLabel.isEmpty
                ? null
                : RecordKind(
                    trait.kindLabel,
                    color: switch (trait.kind) {
                      TraitKind.gift => colors.success,
                      TraitKind.flaw => colors.caution,
                      TraitKind.quirk => null,
                    },
                  ),
            children: [if (trait.description.isNotEmpty) RecordLine(trait.description)],
          ),
        if (learning && sheet.talents.isNotEmpty) ...[
          RecordGroupLabel(l10n.sheetLearning),
          for (final talent in sheet.talents) SheetTalentEntry(talent: talent),
          if (sheet.talentNotes.isNotEmpty)
            RecordCard(
              padding: const EdgeInsets.fromLTRB(Space.lg, Space.sm, Space.lg, Space.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [for (final note in sheet.talentNotes) RecordLine(note)],
              ),
            ),
        ],
      ],
    );
  }
}

/// One talent (A4): its name, how strong it is at the far edge, the pace it gives, what it
/// covers, and on a draft the player's own words it was read from (G2). The rarer it is, the
/// more it stands out: one of a kind is lit and starred.
class SheetTalentEntry extends StatelessWidget {
  const SheetTalentEntry({super.key, required this.talent});

  final SheetTalent talent;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return RecordEntry(
      icon: switch (talent.strength) {
        TalentStrength.slow => Icons.trending_down_rounded,
        TalentStrength.knack || TalentStrength.genius => Icons.trending_up_rounded,
        TalentStrength.oneOfAKind => Icons.auto_awesome_rounded,
      },
      lit: talent.strength.index >= TalentStrength.genius.index,
      title: talent.name.asHeading,
      trailing: talent.strengthLabel.isEmpty
          ? null
          : RecordKind(
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
        if (talent.covers.isNotEmpty) RecordLine(talent.covers.asHeading),
        if (talent.said.isNotEmpty)
          RecordLine(context.l10n.sheetTalentSaid(talent.said), quiet: true),
      ],
    );
  }
}
