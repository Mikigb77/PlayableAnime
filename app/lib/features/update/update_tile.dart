import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import 'app_update.dart';

/// Account's line for the app itself (S12): this build, and a check for a newer one that also
/// offers the update the banner was told to keep for later, or the one being fetched quietly.
/// Shown only in a build that updates itself.
class AppUpdateTile extends ConsumerWidget {
  const AppUpdateTile({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final update = ref.watch(appUpdateProvider);
    final controller = ref.read(appUpdateProvider.notifier);
    final installed = update.installed;
    final release = update.release;
    final subtitle = switch (update.phase) {
      UpdatePhase.checking => l10n.accountUpdateChecking,
      UpdatePhase.upToDate => l10n.accountUpToDate,
      UpdatePhase.available when release != null => l10n.accountUpdateOut(release.build),
      UpdatePhase.preparing when release != null => l10n.accountUpdatePreparing(release.build),
      UpdatePhase.downloading => l10n.updateDownloading(((update.progress ?? 0) * 100).floor()),
      UpdatePhase.ready when release != null => l10n.accountUpdateReady(release.build),
      UpdatePhase.installing => l10n.updateCoverTitle,
      UpdatePhase.failed => switch (update.problem) {
        UpdateProblem.corrupt => l10n.updateFailedCorrupt,
        UpdateProblem.install => l10n.updateFailedInstall,
        _ => l10n.updateFailedDownload,
      },
      _ => null,
    };
    final canUpdate = release != null && update.hasUpdate;
    // While it's fetched quietly, Update shows the download and installs it once it's in.
    final busy = switch (update.phase) {
      UpdatePhase.checking || UpdatePhase.downloading || UpdatePhase.installing => true,
      _ => false,
    };
    return ListTile(
      key: const Key('account.update'),
      leading: const Icon(Icons.system_update_rounded),
      title: Text(
        installed == null
            ? l10n.accountUpdateCheck
            : l10n.accountVersion(installed.version, installed.build),
      ),
      subtitle: subtitle == null ? null : Text(subtitle),
      trailing: busy
          ? const SizedBox.square(dimension: 20, child: CircularProgressIndicator(strokeWidth: 2))
          : TextButton(
              onPressed: canUpdate ? controller.update : () => controller.check(now: true),
              child: Text(switch (update.phase) {
                _ when !canUpdate => l10n.accountUpdateCheck,
                UpdatePhase.ready => l10n.updateInstall,
                _ => l10n.updateNow,
              }),
            ),
    );
  }
}
