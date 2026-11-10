import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'app_update.dart';

/// Offers a newer build of the app above the tabs, and shows its download (S12). It checks when
/// the tabs first show and whenever the app comes back to the foreground, at most every half hour,
/// so a story is never interrupted: the play screen has no tabs. On Wi-Fi the build is fetched
/// before it's offered, so the offer is ready to install. On the first run of a newer build it
/// says the app was updated.
class UpdateBanner extends ConsumerStatefulWidget {
  const UpdateBanner({super.key});

  @override
  ConsumerState<UpdateBanner> createState() => _UpdateBannerState();
}

class _UpdateBannerState extends ConsumerState<UpdateBanner> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    Future.microtask(() {
      if (mounted) ref.read(appUpdateProvider.notifier).check();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) ref.read(appUpdateProvider.notifier).check();
  }

  void _sayUpdated(InstalledApp installed) {
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          key: const Key('update.done'),
          content: Text(context.l10n.updateDone(installed.version, installed.build)),
        ),
      );
    ref.read(appUpdateProvider.notifier).acknowledgeUpdated();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(appUpdateProvider, (previous, next) {
      final installed = next.installed;
      if (next.justUpdated && previous?.justUpdated != true && installed != null) {
        _sayUpdated(installed);
      }
    });
    final update = ref.watch(appUpdateProvider);
    final release = update.release;
    final visible =
        release != null &&
        switch (update.phase) {
          UpdatePhase.available || UpdatePhase.ready || UpdatePhase.failed => !update.dismissed,
          UpdatePhase.downloading => true,
          // Fetched quietly; and while Android installs it, the cover says so instead.
          _ => false,
        };
    final card = visible
        ? _Card(update: update, release: release)
        : const SizedBox(width: double.infinity);
    // With reduce motion it simply changes: an AnimatedSize with no time to animate trips over
    // its own layout.
    if (Motion.reduced(context)) return card;
    return AnimatedSize(
      duration: Motion.base,
      curve: Motion.standard,
      alignment: Alignment.topCenter,
      child: card,
    );
  }
}

class _Card extends ConsumerWidget {
  const _Card({required this.update, required this.release});

  final UpdateState update;
  final AppRelease release;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final controller = ref.read(appUpdateProvider.notifier);
    final secondary = theme.textTheme.bodyMedium?.copyWith(color: context.lucid.textSecondary);
    final progress = update.progress ?? 0;

    final (String title, String? body) = switch (update.phase) {
      UpdatePhase.downloading => (l10n.updateDownloading((progress * 100).floor()), null),
      UpdatePhase.ready => (l10n.updateReady, l10n.updateReadyBody(release.version, release.build)),
      UpdatePhase.failed => (
        l10n.updateAvailable,
        switch (update.problem) {
          UpdateProblem.corrupt => l10n.updateFailedCorrupt,
          UpdateProblem.install => l10n.updateFailedInstall,
          _ => l10n.updateFailedDownload,
        },
      ),
      _ => (
        l10n.updateAvailable,
        l10n.updateAvailableBody(release.version, release.build, release.megabytes),
      ),
    };

    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        key: const Key('update.banner'),
        width: double.infinity,
        color: theme.colorScheme.surfaceContainerHigh,
        padding: const EdgeInsets.fromLTRB(Space.gutter, Space.md, Space.md, Space.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Icon(Icons.system_update_rounded, color: context.lucid.accent),
                const SizedBox(width: Space.md),
                Expanded(child: Text(title, style: theme.textTheme.titleSmall)),
              ],
            ),
            if (body != null)
              Padding(
                padding: const EdgeInsets.only(top: Space.xs, left: 24 + Space.md),
                child: Text(
                  body,
                  style: update.phase == UpdatePhase.failed
                      ? secondary?.copyWith(color: theme.colorScheme.error)
                      : secondary,
                ),
              ),
            if (update.phase == UpdatePhase.downloading)
              Padding(
                padding: const EdgeInsets.only(top: Space.sm, bottom: Space.sm, right: Space.sm),
                child: LinearProgressIndicator(value: progress),
              ),
            // Nothing to press while it downloads: Android's installer opens once it's in.
            if (update.phase != UpdatePhase.downloading)
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: Wrap(
                  spacing: Space.sm,
                  children: [
                    TextButton(onPressed: controller.dismiss, child: Text(l10n.updateLater)),
                    FilledButton.tonal(
                      key: const Key('update.now'),
                      onPressed: controller.update,
                      child: Text(switch (update.phase) {
                        UpdatePhase.failed => l10n.updateTryAgain,
                        UpdatePhase.ready => l10n.updateInstall,
                        _ => l10n.updateNow,
                      }),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
