import 'package:flutter/material.dart';

import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';

/// A quiet pill with a hairline edge: an action that sits beside the story without competing
/// with it, such as "How it played out", Wait and Observe. Its touch target is a full 48 px
/// whatever its drawn height.
class GhostPill extends StatelessWidget {
  const GhostPill({
    super.key,
    required this.label,
    this.icon,
    required this.onPressed,
    this.large = false,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;

  /// A taller pill with larger words, for an action that stands on its own row.
  final bool large;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final enabled = onPressed != null;
    final drawn = large ? 40.0 : 36.0;
    return Semantics(
      button: true,
      enabled: enabled,
      child: InkWell(
        onTap: onPressed,
        customBorder: const StadiumBorder(),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: (Layout.minTouch - drawn) / 2),
          child: Container(
            constraints: BoxConstraints(minHeight: drawn),
            padding: EdgeInsets.fromLTRB(icon == null ? 16 : 12, 6, large ? 18 : 14, 6),
            decoration: ShapeDecoration(
              shape: StadiumBorder(
                side: BorderSide(
                  color: colors.textPrimary.withValues(alpha: enabled ? 0.16 : 0.08),
                ),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon case final icon?) ...[
                  Icon(
                    icon,
                    size: large ? 18 : 17,
                    color: enabled ? colors.accent : colors.textMuted,
                  ),
                  const SizedBox(width: Space.sm),
                ],
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.labelLarge!.copyWith(
                      fontSize: large ? 14.5 : 13.5,
                      color: enabled ? colors.textPrimary : colors.textMuted,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A round button filled with the accent's gradient and lit from behind: the one bright thing on
/// a screen, such as send, or the way into the story to continue. Without [onPressed] and
/// [tooltip] it is an ornament on something that is itself the button.
class AccentOrb extends StatelessWidget {
  const AccentOrb({
    super.key,
    required this.icon,
    this.size = 46,
    this.onPressed,
    this.tooltip,
    this.lit = true,
  });

  final IconData icon;
  final double size;
  final VoidCallback? onPressed;
  final String? tooltip;

  /// False draws it unlit and grey: there, but with nothing to do yet.
  final bool lit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final orb = AnimatedContainer(
      duration: Motion.of(context, Motion.base),
      curve: Motion.standard,
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: lit ? colors.accentGradient() : null,
        color: lit ? null : theme.colorScheme.surfaceContainerHigh,
        boxShadow: [
          if (lit) BoxShadow(color: colors.accent.withValues(alpha: 0.45), blurRadius: 24),
        ],
      ),
      // A thin light along the top edge, as on a lit bead.
      foregroundDecoration: lit
          ? BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.center,
                colors: [const Color(0xFFFFFFFF).withValues(alpha: 0.26), const Color(0x00FFFFFF)],
              ),
            )
          : null,
      child: Icon(icon, size: size * 0.48, color: lit ? colors.onAccent : colors.textMuted),
    );
    if (onPressed == null && tooltip == null) return ExcludeSemantics(child: orb);
    final button = Semantics(
      button: true,
      enabled: onPressed != null,
      label: tooltip,
      // The name replaces the icon, so the tap is given again here.
      onTap: onPressed,
      excludeSemantics: true,
      child: InkResponse(
        onTap: onPressed,
        radius: size * 0.6,
        // The touch target is 48 px even when the bead is smaller.
        child: SizedBox.square(
          dimension: size < Layout.minTouch ? Layout.minTouch : size,
          child: Center(child: orb),
        ),
      ),
    );
    // The name on hover and on a long press. A screen reader has it from the button already.
    return tooltip == null
        ? button
        : Tooltip(message: tooltip, excludeFromSemantics: true, child: button);
  }
}
