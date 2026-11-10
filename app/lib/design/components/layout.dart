import 'package:flutter/material.dart';

import '../theme.dart';
import '../tokens.dart';
import 'brand_mark.dart';
import 'gradient_text.dart';

/// Centers a column no wider than [maxWidth] and gives [child] its full width, so text keeps a
/// readable measure on tablets and the web and still starts at the column's edge.
class ContentColumn extends StatelessWidget {
  const ContentColumn({super.key, required this.child, this.maxWidth = Layout.contentWidth});

  const ContentColumn.reading({super.key, required this.child}) : maxWidth = Layout.readingWidth;

  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: maxWidth),
      child: SizedBox(width: double.infinity, child: child),
    ),
  );
}

/// The room at the end of a page that scrolls: a breath after the last thing on it, and whatever
/// floats over the page's foot or belongs to the system there, such as the glass tab bar and
/// the home indicator, so the last thing on the page can always be scrolled clear of them.
class PageEnd extends StatelessWidget {
  const PageEnd({super.key, this.gap = Space.xl});

  /// The room above the bar, or above the screen's edge when nothing floats there.
  final double gap;

  @override
  Widget build(BuildContext context) =>
      SizedBox(height: gap + MediaQuery.paddingOf(context).bottom);
}

/// Holds how far a large headline grows with the system's text size. It is already several
/// times the size of body text, and at twice that a single word no longer fits a phone's line.
class HeadlineScaling extends StatelessWidget {
  const HeadlineScaling({super.key, required this.child});

  /// The most a headline grows.
  static const maxScale = 1.4;

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      MediaQuery.withClampedTextScaling(maxScaleFactor: maxScale, child: child);
}

/// The top of a tab: the app's mark and name, then a large serif headline. A second line of the
/// headline can be set in the accent's gradient ([accentTitle]), as on the website: "Pick a
/// world, or" then, in gold, "dream up your own."
class PageHeader extends StatelessWidget {
  const PageHeader({
    super.key,
    required this.title,
    this.accentTitle,
    this.subtitle,
    this.trailing,
    this.brand = false,
  });

  final String title;

  /// The headline's second line, in the accent's gradient.
  final String? accentTitle;
  final String? subtitle;
  final Widget? trailing;

  /// Shows the app's mark and name above the headline, on the tabs of a phone. A wide screen
  /// has the mark on its rail already.
  final bool brand;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final brand = this.brand && MediaQuery.sizeOf(context).width < Layout.railBreakpoint;
    final headline = theme.textTheme.displaySmall!.copyWith(
      fontSize: accentTitle == null ? 30 : 33,
      height: 1.12,
      letterSpacing: -0.5,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(
        Space.gutter,
        brand ? Space.md : Space.xl,
        Space.gutter,
        Space.lg,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (brand) ...[const BrandMark(size: 30), const SizedBox(height: Space.xl)],
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // One heading for a screen reader, however many lines it is set in.
                    Semantics(
                      header: true,
                      label: [title, ?accentTitle].join(' '),
                      excludeSemantics: true,
                      child: HeadlineScaling(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(title, style: headline),
                            if (accentTitle case final accentTitle?)
                              GradientText(accentTitle, style: headline, balanced: true),
                          ],
                        ),
                      ),
                    ),
                    if (subtitle case final subtitle?) ...[
                      const SizedBox(height: Space.xs),
                      Text(
                        subtitle,
                        style: theme.textTheme.bodyLarge!.copyWith(
                          color: context.lucid.textSecondary,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              ?trailing,
            ],
          ),
        ],
      ),
    );
  }
}

/// A small uppercase label in the accent, led in by a short line that fades up into it: a
/// genre over a title, or, as a [SectionLabel], the name of a group.
class Eyebrow extends StatelessWidget {
  const Eyebrow(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    final accent = context.lucid.accent;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        ExcludeSemantics(
          child: Container(
            width: 22,
            height: 1,
            margin: const EdgeInsetsDirectional.only(end: 10),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: AlignmentDirectional.centerStart,
                end: AlignmentDirectional.centerEnd,
                colors: [accent.withValues(alpha: 0), accent],
              ),
            ),
          ),
        ),
        Flexible(child: Text(text.toUpperCase(), style: context.lucidText.overline)),
      ],
    );
  }
}

/// A small uppercase label above a group, such as "Signature worlds": an [Eyebrow] that is a
/// heading.
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.padding});

  final String text;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => Padding(
    padding: padding ?? const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, Space.md),
    child: Semantics(header: true, child: Eyebrow(text)),
  );
}
