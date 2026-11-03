import 'package:flutter/material.dart';

import '../../design/design.dart';

/// A block of the policy's Markdown.
sealed class PolicyBlock {
  const PolicyBlock();
}

class PolicyHeading extends PolicyBlock {
  const PolicyHeading(this.text);
  final String text;
}

class PolicyParagraph extends PolicyBlock {
  const PolicyParagraph(this.text);
  final String text;
}

class PolicyBullets extends PolicyBlock {
  const PolicyBullets(this.items);
  final List<String> items;
}

/// A table, shown as one card per row on a phone: the first cell as the title, the others under
/// their column names.
class PolicyTable extends PolicyBlock {
  const PolicyTable(this.header, this.rows);
  final List<String> header;
  final List<List<String>> rows;
}

/// Parses the Markdown the privacy policy uses: `#` headings, paragraphs, `-` lists with indented
/// continuation lines, pipe tables, and `*italic*` and `**bold**` inside them.
List<PolicyBlock> parsePolicy(String source) {
  final blocks = <PolicyBlock>[];
  final lines = source.replaceAll('\r\n', '\n').split('\n');
  final paragraph = <String>[];
  final bullets = <String>[];
  final table = <List<String>>[];

  void flush() {
    if (paragraph.isNotEmpty) blocks.add(PolicyParagraph(paragraph.join(' ')));
    if (bullets.isNotEmpty) blocks.add(PolicyBullets([...bullets]));
    if (table.isNotEmpty) {
      // The second row is the `| --- |` separator.
      final rows = table.where((r) => !r.every((c) => RegExp(r'^:?-+:?$').hasMatch(c))).toList();
      if (rows.isNotEmpty) blocks.add(PolicyTable(rows.first, rows.sublist(1)));
    }
    paragraph.clear();
    bullets.clear();
    table.clear();
  }

  for (final raw in lines) {
    final line = raw.trimRight();
    final trimmed = line.trimLeft();
    if (trimmed.isEmpty) {
      flush();
    } else if (trimmed.startsWith('#')) {
      flush();
      blocks.add(PolicyHeading(trimmed.replaceFirst(RegExp(r'^#+\s*'), '')));
    } else if (trimmed.startsWith('|')) {
      if (paragraph.isNotEmpty || bullets.isNotEmpty) flush();
      final cells = trimmed.substring(1, trimmed.endsWith('|') ? trimmed.length - 1 : null);
      table.add([for (final cell in cells.split('|')) cell.trim()]);
    } else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (paragraph.isNotEmpty || table.isNotEmpty) flush();
      bullets.add(trimmed.substring(2).trim());
    } else if (bullets.isNotEmpty && line.startsWith(' ')) {
      bullets[bullets.length - 1] = '${bullets.last} $trimmed';
    } else {
      if (bullets.isNotEmpty || table.isNotEmpty) flush();
      paragraph.add(trimmed);
    }
  }
  flush();
  return blocks;
}

/// The privacy policy, set for reading: serif paragraphs in the reading column.
class PolicyView extends StatelessWidget {
  const PolicyView({super.key, required this.blocks});

  final List<PolicyBlock> blocks;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final body = theme.textTheme.bodyLarge!.copyWith(height: 1.55);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final block in blocks)
          switch (block) {
            PolicyHeading(:final text) => Padding(
              padding: const EdgeInsets.only(top: Space.xl, bottom: Space.md),
              child: Semantics(
                header: true,
                child: Text(text, style: theme.textTheme.headlineSmall),
              ),
            ),
            PolicyParagraph(:final text) => Padding(
              padding: const EdgeInsets.only(bottom: Space.md),
              child: _Inline(text, style: body),
            ),
            PolicyBullets(:final items) => Padding(
              padding: const EdgeInsets.only(bottom: Space.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final item in items)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.sm),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Padding(
                            padding: const EdgeInsets.only(top: 9, right: Space.md),
                            child: Container(
                              width: 5,
                              height: 5,
                              decoration: BoxDecoration(
                                color: colors.accent,
                                shape: BoxShape.circle,
                              ),
                            ),
                          ),
                          Expanded(child: _Inline(item, style: body)),
                        ],
                      ),
                    ),
                ],
              ),
            ),
            PolicyTable(:final header, :final rows) => Padding(
              padding: const EdgeInsets.only(bottom: Space.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final row in rows)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.sm),
                      child: Card(
                        child: Padding(
                          padding: const EdgeInsets.all(Space.lg),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              if (row.isNotEmpty)
                                _Inline(row.first, style: theme.textTheme.titleMedium!),
                              for (var i = 1; i < row.length; i++) ...[
                                const SizedBox(height: Space.md),
                                if (i < header.length)
                                  Text(header[i].toUpperCase(), style: context.lucidText.overline),
                                const SizedBox(height: Space.xxs),
                                _Inline(
                                  row[i],
                                  style: theme.textTheme.bodyMedium!.copyWith(
                                    color: colors.textSecondary,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          },
      ],
    );
  }
}

/// Text with `*italic*` and `**bold**`.
class _Inline extends StatelessWidget {
  const _Inline(this.text, {required this.style});

  final String text;
  final TextStyle style;

  @override
  Widget build(BuildContext context) => Text.rich(
    TextSpan(
      children: [
        for (final run in parseNarration(text))
          TextSpan(
            text: run.text,
            style: TextStyle(
              fontWeight: run.bold ? FontWeight.w600 : null,
              fontStyle: run.italic ? FontStyle.italic : null,
              color: run.bold ? context.lucid.textPrimary : null,
            ),
          ),
      ],
    ),
    style: style,
  );
}
