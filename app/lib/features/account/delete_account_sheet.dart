import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/byok_store.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import '../auth/auth_repository.dart';
import '../auth/auth_widgets.dart';
import 'account_repository.dart';

/// Asks before deleting the account (T12): what goes, that there is no undo, a way to export
/// first, and a typed word so it can't happen by a stray tap. Returns true once deleted and
/// signed out.
Future<bool> showDeleteAccountSheet(BuildContext context, {VoidCallback? onExport}) async =>
    await showAppSheet<bool>(
      context: context,
      title: context.l10n.deleteTitle,
      builder: (_) => DeleteAccountSheet(onExport: onExport),
    ) ??
    false;

class DeleteAccountSheet extends ConsumerStatefulWidget {
  const DeleteAccountSheet({super.key, this.onExport});

  final VoidCallback? onExport;

  @override
  ConsumerState<DeleteAccountSheet> createState() => _DeleteAccountSheetState();
}

class _DeleteAccountSheetState extends ConsumerState<DeleteAccountSheet> {
  final _confirm = TextEditingController();
  var _busy = false;
  String? _error;

  @override
  void dispose() {
    _confirm.dispose();
    super.dispose();
  }

  bool _matches(AppLocalizations l10n) =>
      _confirm.text.trim().toLowerCase() == l10n.deleteWord.toLowerCase();

  Future<void> _delete() async {
    final l10n = context.l10n;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // The key is kept per account on this device; it goes with the account.
      final keys = ref.read(byokStoreProvider);
      final auth = ref.read(authRepositoryProvider);
      await ref.read(accountRepositoryProvider).deleteAccount();
      await keys.clearGeminiKey();
      if (mounted) Navigator.of(context).pop(true);
      await auth.signOut();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = describeError(l10n, e).message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final scheme = theme.colorScheme;
    final body = theme.textTheme.bodyLarge!.copyWith(color: colors.textSecondary);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(l10n.deleteIntro, style: body),
        const SizedBox(height: Space.md),
        for (final (icon, text) in [
          (Icons.auto_stories_outlined, l10n.deleteStories),
          (Icons.image_outlined, l10n.deletePictures),
          (Icons.toll_outlined, l10n.deleteCredits),
          (Icons.devices_outlined, l10n.deleteDevices),
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: Space.sm),
            child: Row(
              children: [
                Icon(icon, size: 20, color: scheme.error),
                const SizedBox(width: Space.md),
                Expanded(child: Text(text, style: theme.textTheme.bodyLarge)),
              ],
            ),
          ),
        const SizedBox(height: Space.md),
        Text(l10n.deleteNoUndo, style: body),
        if (widget.onExport case final onExport?)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton.icon(
              onPressed: _busy ? null : onExport,
              icon: const Icon(Icons.download_rounded),
              label: Text(l10n.accountExport),
            ),
          ),
        const SizedBox(height: Space.lg),
        if (_error case final message?) ...[FormMessage(message), const SizedBox(height: Space.lg)],
        TextField(
          key: const Key('delete.confirm'),
          controller: _confirm,
          enabled: !_busy,
          autocorrect: false,
          enableSuggestions: false,
          onChanged: (_) => setState(() {}),
          decoration: InputDecoration(labelText: l10n.deleteTypeLabel(l10n.deleteWord)),
        ),
        const SizedBox(height: Space.lg),
        FilledButton(
          key: const Key('delete.submit'),
          style: FilledButton.styleFrom(
            backgroundColor: scheme.error,
            foregroundColor: scheme.onError,
          ),
          onPressed: _busy || !_matches(l10n) ? null : _delete,
          child: _busy
              ? SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: scheme.onError),
                )
              : Text(l10n.deleteConfirm),
        ),
        const SizedBox(height: Space.sm),
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(false),
          child: Text(l10n.cancel),
        ),
      ],
    );
  }
}
