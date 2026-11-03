import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';

/// "Continue with Google", drawn the way Google's branding guidelines ask for a custom button:
/// the full-color G on Google's light or dark button colors, whatever the app's accent.
class GoogleButton extends StatelessWidget {
  const GoogleButton({super.key, required this.onPressed, this.busy = false});

  final VoidCallback? onPressed;

  /// Shows a spinner in place of the logo while a sign-in runs.
  final bool busy;

  // Google's button colors (developers.google.com/identity/branding-guidelines).
  static const _darkFill = Color(0xFF131314);
  static const _darkStroke = Color(0xFF8E918F);
  static const _darkText = Color(0xFFE3E3E3);
  static const _lightFill = Color(0xFFFFFFFF);
  static const _lightStroke = Color(0xFF747775);
  static const _lightText = Color(0xFF1F1F1F);

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final text = dark ? _darkText : _lightText;
    return OutlinedButton(
      onPressed: busy ? null : onPressed,
      style: OutlinedButton.styleFrom(
        backgroundColor: dark ? _darkFill : _lightFill,
        disabledBackgroundColor: dark ? _darkFill : _lightFill,
        foregroundColor: text,
        disabledForegroundColor: text.withValues(alpha: 0.6),
        overlayColor: text,
        side: BorderSide(color: dark ? _darkStroke : _lightStroke),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox.square(
            dimension: 20,
            child: busy
                ? CircularProgressIndicator(strokeWidth: 2, color: text)
                : const ExcludeSemantics(child: CustomPaint(painter: GoogleLogoPainter())),
          ),
          const SizedBox(width: Space.md),
          Flexible(child: Text(context.l10n.authContinueWithGoogle, textAlign: TextAlign.center)),
        ],
      ),
    );
  }
}

/// Google's four-color G, from its 48 × 48 artwork.
class GoogleLogoPainter extends CustomPainter {
  const GoogleLogoPainter();

  static final _parts = [
    (
      const Color(0xFFEA4335),
      'M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 '
          '2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z',
    ),
    (
      const Color(0xFF4285F4),
      'M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 '
          '6c4.51-4.18 7.09-10.36 7.09-17.65z',
    ),
    (
      const Color(0xFFFBBC05),
      'M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 '
          '24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z',
    ),
    (
      const Color(0xFF34A853),
      'M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 '
          '0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z',
    ),
  ].map((p) => (p.$1, parseSvgPath(p.$2))).toList();

  @override
  void paint(Canvas canvas, Size size) {
    canvas
      ..save()
      ..scale(size.width / 48, size.height / 48);
    for (final (color, path) in _parts) {
      canvas.drawPath(path, Paint()..color = color);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(GoogleLogoPainter oldDelegate) => false;
}

/// Parses the subset of SVG path data the logo uses: M, L, H, V, C, S and Z, absolute or relative.
Path parseSvgPath(String data) {
  final tokens = RegExp(
    r'[MmLlHhVvCcSsZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',
  ).allMatches(data).map((m) => m.group(0)!).toList();
  final path = Path();
  var i = 0;
  var command = 'M';
  var x = 0.0, y = 0.0, startX = 0.0, startY = 0.0;
  // The second control point of the last curve, for S.
  double? lastCx, lastCy;

  bool isCommand(String t) => RegExp('[A-Za-z]').hasMatch(t);
  double next() => double.parse(tokens[i++]);

  while (i < tokens.length) {
    if (isCommand(tokens[i])) command = tokens[i++];
    final relative = command == command.toLowerCase();
    final dx = relative ? x : 0.0;
    final dy = relative ? y : 0.0;
    switch (command.toUpperCase()) {
      case 'M':
        x = next() + dx;
        y = next() + dy;
        startX = x;
        startY = y;
        path.moveTo(x, y);
        // Further pairs after a move are lines.
        command = relative ? 'l' : 'L';
        lastCx = null;
      case 'L':
        x = next() + dx;
        y = next() + dy;
        path.lineTo(x, y);
        lastCx = null;
      case 'H':
        x = next() + dx;
        path.lineTo(x, y);
        lastCx = null;
      case 'V':
        y = next() + dy;
        path.lineTo(x, y);
        lastCx = null;
      case 'C':
        final c1x = next() + dx, c1y = next() + dy;
        final c2x = next() + dx, c2y = next() + dy;
        x = next() + dx;
        y = next() + dy;
        path.cubicTo(c1x, c1y, c2x, c2y, x, y);
        lastCx = c2x;
        lastCy = c2y;
      case 'S':
        // The first control point mirrors the last curve's second one.
        final c1x = lastCx == null ? x : 2 * x - lastCx;
        final c1y = lastCy == null ? y : 2 * y - lastCy;
        final c2x = next() + dx, c2y = next() + dy;
        x = next() + dx;
        y = next() + dy;
        path.cubicTo(c1x, c1y, c2x, c2y, x, y);
        lastCx = c2x;
        lastCy = c2y;
      case 'Z':
        path.close();
        x = startX;
        y = startY;
        lastCx = null;
      default:
        throw FormatException('Unsupported path command $command');
    }
  }
  return path;
}
