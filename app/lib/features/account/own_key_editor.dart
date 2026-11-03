import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/byok_store.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';

/// The player's own Gemini key (S9): kept on this device for this account only, and sent only
/// with requests that call a model. Turns on it use no credits (K6).
final ownKeyProvider = FutureProvider.autoDispose<String?>(
  (ref) => ref.watch(byokStoreProvider).readGeminiKey(),
);

/// Shows the saved key by its last characters, or a field to add one.
class OwnKeyEditor extends ConsumerStatefulWidget {
  const OwnKeyEditor({super.key, this.onSaved, this.autofocus = false});

  /// Called once a key is saved.
  final VoidCallback? onSaved;
  final bool autofocus;

  @override
  ConsumerState<OwnKeyEditor> createState() => _OwnKeyEditorState();
}

class _OwnKeyEditorState extends ConsumerState<OwnKeyEditor> {
  final _key = TextEditingController();
  var _obscure = true;
  var _saving = false;
  var _failed = false;

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final key = _key.text.trim();
    if (key.isEmpty || _saving) return;
    setState(() {
      _saving = true;
      _failed = false;
    });
    try {
      await ref.read(byokStoreProvider).saveGeminiKey(key);
    } on Object catch (e) {
      // The device's secure storage refused it; never log the key itself.
      debugPrint('Saving the own key failed: ${e.runtimeType}');
      if (mounted) {
        setState(() {
          _saving = false;
          _failed = true;
        });
      }
      return;
    }
    _key.clear();
    ref.invalidate(ownKeyProvider);
    if (mounted) setState(() => _saving = false);
    widget.onSaved?.call();
  }

  Future<void> _remove() async {
    final messenger = ScaffoldMessenger.maybeOf(context);
    final failed = context.l10n.accountKeyStoreFailed;
    try {
      await ref.read(byokStoreProvider).clearGeminiKey();
    } on Object catch (e) {
      debugPrint('Removing the own key failed: ${e.runtimeType}');
      messenger?.showSnackBar(SnackBar(content: Text(failed)));
    }
    ref.invalidate(ownKeyProvider);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final saved = ref.watch(ownKeyProvider).value;
    if (saved != null && saved.isNotEmpty) {
      final last = saved.length > 4 ? saved.substring(saved.length - 4) : saved;
      return Card(
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(horizontal: Space.lg),
          leading: Icon(Icons.key_rounded, color: colors.accent),
          title: Text(l10n.accountKeyEnding(last)),
          subtitle: Text(l10n.accountKeyFree),
          trailing: TextButton(onPressed: _remove, child: Text(l10n.accountKeyRemove)),
        ),
      );
    }
    return TextField(
      key: const Key('account.ownKey'),
      controller: _key,
      autofocus: widget.autofocus,
      obscureText: _obscure,
      autocorrect: false,
      enableSuggestions: false,
      enabled: !_saving,
      onSubmitted: (_) => _save(),
      onChanged: (_) {
        if (_failed) setState(() => _failed = false);
      },
      decoration: InputDecoration(
        labelText: l10n.accountKeyLabel,
        helperText: l10n.accountKeyHelper,
        helperMaxLines: 3,
        errorText: _failed ? l10n.accountKeyStoreFailed : null,
        errorMaxLines: 3,
        suffixIcon: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              tooltip: _obscure ? l10n.accountKeyShow : l10n.accountKeyHide,
              icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
              onPressed: () => setState(() => _obscure = !_obscure),
            ),
            IconButton(
              key: const Key('account.ownKey.save'),
              tooltip: l10n.accountKeySave,
              icon: const Icon(Icons.check_rounded),
              onPressed: _saving ? null : _save,
            ),
          ],
        ),
      ),
    );
  }
}
