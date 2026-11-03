import 'package:flutter/material.dart';

import '../theme.dart';
import '../tokens.dart';

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

/// The large serif title at the top of a tab, with an optional line under it.
class PageHeader extends StatelessWidget {
  const PageHeader({super.key, required this.title, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, Space.lg),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(header: true, child: Text(title, style: theme.textTheme.displaySmall)),
                if (subtitle case final subtitle?) ...[
                  const SizedBox(height: Space.xs),
                  Text(
                    subtitle,
                    style: theme.textTheme.bodyLarge!.copyWith(color: context.lucid.textSecondary),
                  ),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// A small uppercase label above a group, such as "Signature worlds".
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.padding});

  final String text;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => Padding(
    padding: padding ?? const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, Space.md),
    child: Semantics(
      header: true,
      child: Text(text.toUpperCase(), style: context.lucidText.overline),
    ),
  );
}
