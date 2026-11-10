import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'app_update.dart';

/// Covers the whole app while Android's installer is open on its update (S12), over every screen,
/// so the old build can't be used while the new one comes in. Android's installer shows over it:
/// it asks the player, installs the new build, which ends this app, and then offers Open, which
/// starts the new build; the cover says so. If the installer closes and the app is still here
/// (the player said no, or Android couldn't install it), the cover goes away and the banner
/// offers the update again.
class UpdateCover extends ConsumerStatefulWidget {
  const UpdateCover({super.key, required this.child});

  /// How long the app may be back in front, with no word from Android's installer, before the
  /// cover takes the installer as closed. Android says so at once; this is only a way out.
  static const giveUpAfter = Duration(seconds: 3);

  final Widget child;

  @override
  ConsumerState<UpdateCover> createState() => _UpdateCoverState();
}

class _UpdateCoverState extends ConsumerState<UpdateCover> {
  late final AppLifecycleListener _lifecycle;
  Timer? _giveUp;

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(
      onResume: _back,
      onInactive: () => _giveUp?.cancel(),
      onHide: () => _giveUp?.cancel(),
    );
  }

  @override
  void dispose() {
    _giveUp?.cancel();
    _lifecycle.dispose();
    super.dispose();
  }

  /// The app is back in front. While the installer is open it isn't, so if it stays in front the
  /// installer has closed without Android saying so; the cover must never trap the player.
  void _back() {
    if (ref.read(appUpdateProvider).phase != UpdatePhase.installing) return;
    _giveUp?.cancel();
    _giveUp = Timer(UpdateCover.giveUpAfter, () {
      if (mounted) ref.read(appUpdateProvider.notifier).installerClosed();
    });
  }

  @override
  Widget build(BuildContext context) {
    final child = widget.child;
    ref.listen(appUpdateProvider.select((u) => u.phase), (previous, phase) {
      if (phase != UpdatePhase.installing) _giveUp?.cancel();
    });
    final covered = ref.watch(appUpdateProvider.select((u) => u.phase == UpdatePhase.installing));
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
