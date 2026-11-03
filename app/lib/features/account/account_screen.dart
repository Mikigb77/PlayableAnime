import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/byok_store.dart';
import '../../core/config.dart';
import '../../core/l10n.dart';
import '../../core/preferences.dart';
import '../../core/session/session_controller.dart';
import '../../design/design.dart';

/// Account: who you are, appearance, your own API key (S9), and developer tools. The accounts work
/// (WS13) adds the profile, credits, content preferences, privacy, export and delete.
class AccountScreen extends ConsumerStatefulWidget {
  const AccountScreen({super.key});

  @override
  ConsumerState<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends ConsumerState<AccountScreen> {
  final _key = TextEditingController();
  bool _hasKey = false;

  @override
  void initState() {
    super.initState();
    ref.read(byokStoreProvider).readGeminiKey().then((key) {
      if (mounted) setState(() => _hasKey = key != null && key.isNotEmpty);
    });
  }

  @override
  void dispose() {
    _key.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final key = _key.text.trim();
    if (key.isEmpty) return;
    await ref.read(byokStoreProvider).saveGeminiKey(key);
    _key.clear();
    if (mounted) setState(() => _hasKey = true);
  }

  Future<void> _clear() async {
    await ref.read(byokStoreProvider).clearGeminiKey();
    if (mounted) setState(() => _hasKey = false);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final session = ref.watch(sessionProvider);
    final name = session.session?.displayName;
    final mode = ref.watch(themeModeProvider);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.only(bottom: Space.xxxl),
          children: [
            ContentColumn(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  PageHeader(
                    title: l10n.accountTitle,
                    subtitle: name == null ? l10n.accountGuest : l10n.accountSignedInAs(name),
                  ),
                  SectionLabel(l10n.accountAppearance),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                    child: SegmentedButton<ThemeMode>(
                      segments: [
                        ButtonSegment(
                          value: ThemeMode.dark,
                          label: Text(l10n.themeDark),
                          icon: const Icon(Icons.dark_mode_outlined),
                        ),
                        ButtonSegment(
                          value: ThemeMode.light,
                          label: Text(l10n.themeLight),
                          icon: const Icon(Icons.light_mode_outlined),
                        ),
                        ButtonSegment(
                          value: ThemeMode.system,
                          label: Text(l10n.themeSystem),
                          icon: const Icon(Icons.brightness_auto_outlined),
                        ),
                      ],
                      selected: {mode},
                      showSelectedIcon: false,
                      onSelectionChanged: (s) => ref.read(themeModeProvider.notifier).set(s.single),
                    ),
                  ),
                  SectionLabel(l10n.accountOwnKey),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          l10n.accountOwnKeyBody,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                        ),
                        const SizedBox(height: Space.lg),
                        if (_hasKey)
                          Card(
                            child: ListTile(
                              leading: Icon(Icons.key_rounded, color: colors.accent),
                              title: Text(l10n.accountKeySaved),
                              trailing: TextButton(
                                onPressed: _clear,
                                child: Text(l10n.accountKeyRemove),
                              ),
                            ),
                          )
                        else
                          TextField(
                            controller: _key,
                            obscureText: true,
                            autocorrect: false,
                            enableSuggestions: false,
                            decoration: InputDecoration(
                              labelText: l10n.accountKeyLabel,
                              suffixIcon: IconButton(
                                tooltip: l10n.accountKeySave,
                                icon: const Icon(Icons.check_rounded),
                                onPressed: _save,
                              ),
                            ),
                            onSubmitted: (_) => _save(),
                          ),
                      ],
                    ),
                  ),
                  SectionLabel(l10n.accountDeveloper),
                  ListTile(
                    leading: const Icon(Icons.dns_outlined),
                    title: Text(l10n.accountApi),
                    subtitle: Text(AppConfig.isFake ? l10n.accountApiFake : AppConfig.apiBaseUrl),
                  ),
                  if (AppConfig.showGallery)
                    ListTile(
                      leading: const Icon(Icons.palette_outlined),
                      title: Text(l10n.accountGallery),
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => context.push('/gallery'),
                    ),
                  const SizedBox(height: Space.xl),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                    child: OutlinedButton.icon(
                      onPressed: () => ref.read(sessionProvider.notifier).signOut(),
                      icon: const Icon(Icons.logout_rounded),
                      label: Text(l10n.accountSignOut),
                    ),
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
