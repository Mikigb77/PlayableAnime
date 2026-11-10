import 'package:flutter/material.dart';

import '../typography.dart';
import 'gradient_text.dart';

/// A paragraph that opens with a large capital in the accent's gradient, set into its first two
/// lines, as a story opens in a printed book. Only a letter or a digit is set this way, so a
/// paragraph that opens with a line of speech keeps its mark and reads as plain text; so does
/// one in a column too narrow to hold words beside the capital.
///
/// A screen reader hears the paragraph whole, not the capital and then the rest.
class DropCapParagraph extends StatelessWidget {
  const DropCapParagraph({super.key, required this.spans, required this.style});

  /// The paragraph as flat spans: text spans without children, then any widgets, such as the
  /// caret of a story still being written.
  final List<InlineSpan> spans;

  /// The paragraph's own text style, which sets the size of the capital.
  final TextStyle style;

  /// How many lines the capital stands beside.
  static const _lines = 2;

  /// The room between the capital and the words.
  static const _gap = 8.0;

  /// The least width the words beside the capital need.
  static const _minBeside = 150.0;

  /// The height of a capital letter in the display serif, as a share of the font's size.
  static const _capHeight = 0.7;

  static final _letter = RegExp(r'^[\p{L}\p{N}]', unicode: true);

  /// Whether a paragraph that starts with [text] takes a capital.
  static bool fits(String text) => _letter.hasMatch(text);

  @override
  Widget build(BuildContext context) {
    final plain = Text.rich(TextSpan(children: spans));
    final first = spans.firstOrNull;
    if (first is! TextSpan || first.children != null || !fits(first.text ?? '')) return plain;
    final letter = first.text!.characters.first;
    final words = _slice(spans, letter.length);
    final inherited = DefaultTextStyle.of(context).style;
    final body = style.inherit ? inherited.merge(style) : style;
    final size = body.fontSize ?? 16;
    // Tall enough to stand from the foot of the second line to the top of the first line's own
    // capitals.
    final capStyle = TextStyle(
      fontFamily: Fonts.display,
      fontWeight: FontWeight.w500,
      fontSize: size * (1 + (_lines - 1) * (body.height ?? 1.4) / _capHeight),
      letterSpacing: 0,
      color: body.color,
    );
    final scaler = MediaQuery.textScalerOf(context);
    final direction = Directionality.of(context);

    return LayoutBuilder(
      builder: (context, constraints) {
        final cap = TextPainter(
          text: TextSpan(text: letter, style: inherited.merge(capStyle)),
          textDirection: direction,
          textScaler: scaler,
          maxLines: 1,
        )..layout();
        final capWidth = cap.width;
        final capBaseline = cap.computeDistanceToActualBaseline(TextBaseline.alphabetic);
        cap.dispose();
        final beside = constraints.maxWidth - capWidth - _gap;
        if (!beside.isFinite || beside < _minBeside) return plain;

        // Where the words run out of room beside the capital: the first line that starts at or
        // below its foot. Widgets come last and are left out of the measure, so every place
        // counted here is the same place in [spans].
        final measure = TextPainter(
          text: TextSpan(
            style: body,
            children: [
              for (final span in words)
                if (span is TextSpan) span,
            ],
          ),
          textDirection: direction,
          textScaler: scaler,
        )..layout(maxWidth: beside);
        final lines = measure.computeLineMetrics();
        if (lines.isEmpty) {
          measure.dispose();
          return plain;
        }
        final lineHeight = lines.first.height;
        final box = lineHeight * _lines;
        final foot = lines.length >= _lines
            ? lines[_lines - 1].baseline
            : lines.first.baseline + lineHeight * (_lines - 1);
        int? cut;
        var top = 0.0;
        for (final line in lines) {
          if (top >= box - 0.5) {
            // A place well inside the line, so it belongs to this line on every platform: at a
            // line's very start, some count the place as the end of the line before.
            final at = measure.getPositionForOffset(
              Offset(line.left + line.width / 2, top + line.height / 2),
            );
            cut = measure.getLineBoundary(at).start;
            break;
          }
          top += line.height;
        }
        measure.dispose();

        final opacity = _opacityOf(first, body);
        final capital = GradientText(letter, style: capStyle);
        return Semantics(
          label: TextSpan(children: spans).toPlainText(includePlaceholders: false),
          excludeSemantics: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: capWidth + _gap,
                    height: box,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        PositionedDirectional(
                          start: 0,
                          top: foot - capBaseline,
                          child: opacity < 1 ? Opacity(opacity: opacity, child: capital) : capital,
                        ),
                      ],
                    ),
                  ),
                  Expanded(
                    child: Text.rich(
                      TextSpan(children: cut == null ? words : _slice(words, 0, cut)),
                    ),
                  ),
                ],
              ),
              if (cut != null) Text.rich(TextSpan(children: _slice(words, cut))),
            ],
          ),
        );
      },
    );
  }

  /// How far the paragraph's first words have faded in, so the capital arrives with them.
  static double _opacityOf(TextSpan first, TextStyle body) {
    final full = body.color?.a ?? 1;
    final now = first.style?.color?.a ?? full;
    return full <= 0 ? 1 : (now / full).clamp(0.0, 1.0);
  }

  /// [spans] from the character at [start] up to [end], counting a widget as one character.
  static List<InlineSpan> _slice(List<InlineSpan> spans, int start, [int? end]) {
    final out = <InlineSpan>[];
    var offset = 0;
    for (final span in spans) {
      final text = span is TextSpan ? span.text ?? '' : null;
      final length = text?.length ?? 1;
      final from = (start - offset).clamp(0, length);
      final to = end == null ? length : (end - offset).clamp(0, length);
      if (from < to) {
        out.add(
          text != null && (from > 0 || to < length)
              ? TextSpan(text: text.substring(from, to), style: span.style)
              : span,
        );
      }
      offset += length;
    }
    return out;
  }
}
