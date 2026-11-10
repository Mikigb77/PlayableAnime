import 'package:flutter/material.dart';

import '../theme.dart';

/// Lettering in the accent's gradient, bright to deep: the gold of a headline, a story's title
/// on its cover. Both ends of the gradient are readable on the page, like the accent itself.
class GradientText extends StatelessWidget {
  const GradientText(
    this.text, {
    super.key,
    required this.style,
    this.textAlign,
    this.maxLines,
    this.overflow,
    this.balanced = false,
  });

  final String text;
  final TextStyle style;
  final TextAlign? textAlign;
  final int? maxLines;
  final TextOverflow? overflow;

  /// Breaks a headline that takes more than one line into lines of like length ("The story" /
  /// "never ends."), so no line is left with a single word. See [balancedWidth].
  final bool balanced;

  @override
  Widget build(BuildContext context) {
    final gradient = context.lucid.accentGradient(
      begin: const Alignment(-1, -0.35),
      end: const Alignment(1, 0.35),
    );
    final lettering = ShaderMask(
      blendMode: BlendMode.srcIn,
      shaderCallback: (bounds) => gradient.createShader(Offset.zero & bounds.size),
      // The mask ends at the text's box: a little room below keeps the tails of g and y.
      child: Padding(
        padding: EdgeInsets.only(bottom: (style.fontSize ?? 16) * 0.08),
        child: Text(
          text,
          textAlign: textAlign,
          maxLines: maxLines,
          overflow: overflow,
          style: style.copyWith(color: const Color(0xFFFFFFFF)),
        ),
      ),
    );
    if (!balanced) return lettering;
    return LayoutBuilder(
      builder: (context, constraints) => ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: balancedWidth(
            context,
            text,
            DefaultTextStyle.of(context).style.merge(style),
            constraints.maxWidth,
          ),
        ),
        child: lettering,
      ),
    );
  }
}

/// The narrowest width at which [text] takes no more lines than it does at [maxWidth], or
/// [maxWidth] itself when it fits on one line. A headline set to it breaks evenly.
double balancedWidth(BuildContext context, String text, TextStyle style, double maxWidth) {
  if (!maxWidth.isFinite) return maxWidth;
  final painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
  );
  int linesAt(double width) {
    painter.layout(maxWidth: width);
    return painter.computeLineMetrics().length;
  }

  final lines = linesAt(maxWidth);
  var width = maxWidth;
  if (lines > 1) {
    var narrow = 0.0;
    for (var i = 0; i < 10; i++) {
      final middle = (narrow + width) / 2;
      if (linesAt(middle) <= lines) {
        width = middle;
      } else {
        narrow = middle;
      }
    }
    // A hair of room, so rounding never costs the line it was measured to hold.
    width = (width + 1).ceilToDouble().clamp(0, maxWidth);
  }
  painter.dispose();
  return width;
}
