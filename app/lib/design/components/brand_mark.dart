import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import '../typography.dart';

/// The app's mark and name, as on the website: the forest gate in a small round frame with a
/// warm glow, and "Lucid Saga" in the display serif.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.size = 32, this.showName = true});

  /// The round picture's width.
  final double size;
  final bool showName;

  /// The gate from the app's icon (app/tool/app_icon), cut close.
  static const asset = 'assets/brand/mark.jpg';

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final picture = ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: colors.accent.withValues(alpha: 0.4)),
          boxShadow: [
            BoxShadow(
              color: colors.accent.withValues(alpha: 0.28),
              blurRadius: 18,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        child: ClipOval(
          child: Image.asset(
            asset,
            fit: BoxFit.cover,
            cacheWidth: (size * dpr).round(),
            // A build without the picture still shows the frame and its glow.
            errorBuilder: (_, _, _) => ColoredBox(color: colors.accentSoft),
          ),
        ),
      ),
    );
    if (!showName) return picture;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        picture,
        SizedBox(width: size * 0.32),
        Flexible(
          child: Text(
            context.l10n.appTitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontFamily: Fonts.display,
              fontWeight: FontWeight.w500,
              fontSize: size * 0.6,
              height: 1.1,
              letterSpacing: -0.2,
              color: colors.textPrimary,
            ),
          ),
        ),
      ],
    );
  }
}
