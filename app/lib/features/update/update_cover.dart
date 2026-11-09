import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'app_update.dart';

/// Covers the whole app while Android installs its update (S12), over every screen, so the old
/// build can't be used while the new one comes in. The app stays in front under it until Android
/// replaces it, which ends the app: Android and Google Play Protect may still check the build or
/// ask the player during the install, and an app that leaves the screen then can stall it. If the
/// install fails, the cover goes away and the banner says so.
class UpdateCover extends ConsumerWidget {
  const UpdateCover({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final covered = ref.watch(appUpdateProvider.select((u) => u.phase == UpdatePhase.replacing));
    return Stack(
      fit: StackFit.expand,
      children: [
        ExcludeSemantics(excluding: covered, child: child),
        if (covered) const Positioned.fill(child: AbsorbPointer(child: _Cover())),
      ],
    );
  }
}

class _Cover extends StatelessWidget {
  const _Cover();

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Material(
      key: const Key('update.cover'),
      color: theme.colorScheme.surface,
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Space.xxl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Semantics(
                container: true,
                liveRegion: true,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(color: colors.accentSoft, shape: BoxShape.circle),
                      child: Icon(
                        Icons.system_update_rounded,
                        size: 30,
                        color: colors.onAccentSoft,
                      ),
                    ),
                    const SizedBox(height: Space.lg),
                    Semantics(
                      header: true,
                      child: Text(
                        l10n.updateCoverTitle,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineSmall,
                      ),
                    ),
                    const SizedBox(height: Space.sm),
                    Text(
                      l10n.updateCoverBody,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary),
                    ),
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
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
