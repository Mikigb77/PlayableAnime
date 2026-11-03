import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';

/// While the storyteller drafts (G1): what it is building, honestly, with no fake step-by-step
/// progress, and the promise that a failure costs nothing.
class DraftingView extends StatelessWidget {
  const DraftingView({super.key, required this.premise});

  /// The premise being drafted, quoted back to the player.
  final String premise;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final items = [
      (Icons.public_rounded, l10n.draftingReal),
      (Icons.groups_2_outlined, l10n.draftingPeople),
      (Icons.person_outline_rounded, l10n.draftingCharacter),
      (Icons.visibility_off_outlined, l10n.draftingSecrets),
    ];
    return Semantics(
      liveRegion: true,
      label: l10n.draftingTitle,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: Space.gutter, vertical: Space.xxl),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Center(child: _Emblem()),
                const SizedBox(height: Space.xl),
                Text(
                  l10n.draftingTitle,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineMedium,
                ),
                const SizedBox(height: Space.sm),
                Text(
                  l10n.draftingBody,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                ),
                if (premise.trim().isNotEmpty) ...[
                  const SizedBox(height: Space.xl),
                  Container(
                    padding: const EdgeInsets.only(left: Space.lg),
                    decoration: BoxDecoration(
                      border: Border(
                        left: BorderSide(color: colors.accent.withValues(alpha: 0.6), width: 2),
                      ),
                    ),
                    child: Text(
                      premise.trim(),
                      maxLines: 4,
                      overflow: TextOverflow.ellipsis,
                      style: context.lucidText.playerAction,
                    ),
                  ),
                ],
                // An endless sweep, so it goes with reduce motion; the words say it is working.
                if (!Motion.reduced(context)) ...[
                  const SizedBox(height: Space.xl),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(Radii.pill),
                    child: LinearProgressIndicator(
                      minHeight: 3,
                      color: colors.accent,
                      backgroundColor: theme.colorScheme.surfaceContainerHighest,
                    ),
                  ),
                ],
                const SizedBox(height: Space.xl),
                for (final (icon, text) in items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.md),
                    child: Row(
                      children: [
                        ExcludeSemantics(child: Icon(icon, size: 20, color: colors.textMuted)),
                        const SizedBox(width: Space.md),
                        Expanded(
                          child: Text(
                            text,
                            style: theme.textTheme.bodyMedium!.copyWith(
                              color: colors.textSecondary,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: Space.md),
                Text(
                  l10n.draftingNoCharge,
                  textAlign: TextAlign.center,
                  style: context.lucidText.meta.copyWith(color: colors.textMuted),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A slow breathing glow around the app's mark. Still with reduce motion on.
class _Emblem extends StatefulWidget {
  const _Emblem();

  @override
  State<_Emblem> createState() => _EmblemState();
}

class _EmblemState extends State<_Emblem> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1800),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (Motion.reduced(context)) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return ExcludeSemantics(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          final t = Curves.easeInOut.transform(_controller.value);
          return Container(
            width: 88,
            height: 88,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: colors.accentSoft,
              boxShadow: [
                BoxShadow(
                  color: colors.accent.withValues(alpha: 0.12 + 0.18 * t),
                  blurRadius: 24 + 16 * t,
                  spreadRadius: 2 + 4 * t,
                ),
              ],
            ),
            child: child,
          );
        },
        child: Icon(Icons.auto_awesome_rounded, size: 38, color: colors.onAccentSoft),
      ),
    );
  }
}
