/// The pieces the Character and Memory screens are both built from: a card, a chip, an entry
/// with its mark and its lines.
library;

import 'package:flutter/material.dart';

import '../../design/design.dart';

/// A card of the character's record: a soft layer with a hairline edge.
class RecordCard extends StatelessWidget {
  const RecordCard({super.key, required this.child, this.padding = const EdgeInsets.all(Space.lg)});

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

/// A short state in a pill. With a [tone] it is tinted; without, it is quiet.
class RecordChip extends StatelessWidget {
  const RecordChip(this.text, {super.key, this.tone, this.icon, this.note = ''});

  /// How much of a tinted chip's own color washes the page behind its words.
  static const double wash = 0.10;

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
        color: tone?.withValues(alpha: wash),
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

/// A small label over a group inside a tab or a section.
class RecordGroupLabel extends StatelessWidget {
  const RecordGroupLabel(this.text, {super.key, this.first = false});

  final String text;

  /// The first thing in its tab or section, so with no room above it.
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
class RecordGlyph extends StatelessWidget {
  const RecordGlyph(this.icon, {super.key, this.lit = false});

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

/// One entry in its own card: a glyph or a picture, its name, a word or a mark at the far
/// edge, and what there is to say about it underneath.
class RecordEntry extends StatelessWidget {
  const RecordEntry({
    super.key,
    this.icon,
    this.leading,
    required this.title,
    this.titleStyle,
    this.tag,
    this.lit = false,
    this.trailing,
    this.children = const [],
  }) : assert(icon != null || leading != null);

  /// The glyph that leads the entry in, unless [leading] takes its place.
  final IconData? icon;

  /// A portrait or a picture in place of the glyph.
  final Widget? leading;
  final String title;
  final TextStyle? titleStyle;

  /// A short state right after the name, such as "Presumed dead".
  final Widget? tag;
  final bool lit;
  final Widget? trailing;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final name = Text(title, style: titleStyle ?? theme.textTheme.titleMedium);
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: MergeSemantics(
        child: RecordCard(
          padding: const EdgeInsets.all(Space.md),
          child: Row(
            crossAxisAlignment: children.isEmpty
                ? CrossAxisAlignment.center
                : CrossAxisAlignment.start,
            children: [
              leading ?? RecordGlyph(icon!, lit: lit),
              const SizedBox(width: Space.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    RecordTitled(
                      title: tag == null
                          ? name
                          : Wrap(
                              spacing: Space.sm,
                              runSpacing: Space.xxs,
                              crossAxisAlignment: WrapCrossAlignment.center,
                              children: [name, tag!],
                            ),
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
class RecordTitled extends StatelessWidget {
  const RecordTitled({super.key, required this.title, this.trailing});

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
class RecordLine extends StatelessWidget {
  const RecordLine(this.text, {super.key, this.quiet = false});

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

/// A word at the far edge of an entry, in small capitals: what kind of thing it is.
class RecordKind extends StatelessWidget {
  const RecordKind(this.text, {super.key, this.color});

  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) => Text(
    text.toUpperCase(),
    style: context.lucidText.overline.copyWith(color: color ?? context.lucid.textMuted),
  );
}
