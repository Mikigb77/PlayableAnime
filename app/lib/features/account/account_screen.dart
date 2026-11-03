import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/config.dart';
import '../../core/l10n.dart';
import '../../core/preferences.dart';
import '../../design/design.dart';
import '../../router.dart';
import '../auth/auth_repository.dart';
import 'account_models.dart';
import 'account_repository.dart';
import 'credits_screen.dart';
import 'delete_account_sheet.dart';
import 'export_saver.dart';
import 'own_key_editor.dart';

/// Account: who you are and your rating limit (F8), credits (K1, K2), your own key (S9), story
/// content (F7), appearance, privacy, export and delete (T12), and sign out.
class AccountScreen extends ConsumerStatefulWidget {
  const AccountScreen({super.key});

  @override
  ConsumerState<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends ConsumerState<AccountScreen> {
  var _visible = false;
  var _exporting = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // The tabs keep this screen alive behind the others; read the balance again whenever the tab
    // comes back, since turns elsewhere have spent from it.
    final visible = TickerMode.valuesOf(context).enabled;
    if (visible && !_visible) {
      _visible = true;
      Future.microtask(() {
        if (mounted) ref.invalidate(meProvider);
      });
    } else if (!visible) {
      _visible = false;
    }
  }

  void _showError(Object error) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(describeError(context.l10n, error).message)));
  }

  Future<void> _updatePrefs(ContentPrefs prefs) async {
    try {
      await ref.read(meProvider.notifier).updatePrefs(prefs);
    } on ApiException catch (e) {
      _showError(e);
    }
  }

  Future<void> _editName(AccountUser user) async {
    await showAppSheet<bool>(
      context: context,
      title: context.l10n.accountNameTitle,
      builder: (_) => _NameEditor(initial: user.displayName),
    );
  }

  Future<void> _export(BuildContext anchor) async {
    if (_exporting) return;
    final l10n = context.l10n;
    final origin = originOf(anchor);
    setState(() => _exporting = true);
    try {
      final bytes = await ref.read(accountRepositoryProvider).export();
      final saved = await ref
          .read(exportSaverProvider)
          .save(bytes, fileName: 'lucid-saga-export.json', origin: origin);
      if (saved && mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(l10n.accountExportReady)));
      }
    } on ApiException catch (e) {
      _showError(e);
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  Future<void> _delete(BuildContext anchor) async {
    final messenger = ScaffoldMessenger.of(context);
    final done = context.l10n.deleteDone;
    final deleted = await showDeleteAccountSheet(context, onExport: () => _export(anchor));
    if (deleted) messenger.showSnackBar(SnackBar(content: Text(done)));
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final me = ref.watch(meProvider);
    final user = me.value ?? ref.read(meProvider.notifier).current;
    final mode = ref.watch(themeModeProvider);
    final secondary = theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          onRefresh: () => ref.refresh(meProvider.future).then((_) {}, onError: _showError),
          child: ListView(
            padding: const EdgeInsets.only(bottom: Space.xxxl),
            children: [
              ContentColumn(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    PageHeader(title: l10n.accountTitle),
                    if (user != null) ...[
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                        child: _ProfileCard(user: user, onEdit: () => _editName(user)),
                      ),
                      SectionLabel(l10n.accountCredits),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                        child: BalanceCard(
                          balanceCents: user.balanceCents,
                          unlimited: user.unlimited,
                          onHistory: () => context.push(Routes.credits),
                        ),
                      ),
                    ] else if (me.hasError)
                      ErrorState(error: me.error!, onRetry: () => ref.invalidate(meProvider)),
                    SectionLabel(l10n.accountOwnKey),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(l10n.accountOwnKeyBody, style: secondary),
                          const SizedBox(height: Space.lg),
                          const OwnKeyEditor(),
                        ],
                      ),
                    ),
                    if (user != null) ...[
                      SectionLabel(l10n.accountContent),
                      _ContentPrefsSection(user: user, onChanged: _updatePrefs),
                    ],
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
                        onSelectionChanged: (s) =>
                            ref.read(themeModeProvider.notifier).set(s.single),
                      ),
                    ),
                    SectionLabel(l10n.accountPrivacy),
                    ListTile(
                      leading: const Icon(Icons.policy_outlined),
                      title: Text(l10n.accountPrivacyPolicy),
                      subtitle: Text(l10n.accountPrivacyPolicyBody),
                      trailing: const Icon(Icons.chevron_right_rounded),
                      onTap: () => context.push(Routes.privacy),
                    ),
                    Builder(
                      builder: (tile) => ListTile(
                        key: const Key('account.export'),
                        leading: const Icon(Icons.download_rounded),
                        title: Text(l10n.accountExport),
                        subtitle: Text(l10n.accountExportBody),
                        trailing: _exporting
                            ? const SizedBox.square(
                                dimension: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : null,
                        onTap: _exporting ? null : () => _export(tile),
                      ),
                    ),
                    Builder(
                      builder: (tile) => ListTile(
                        key: const Key('account.delete'),
                        leading: Icon(
                          Icons.delete_forever_outlined,
                          color: theme.colorScheme.error,
                        ),
                        title: Text(
                          l10n.accountDelete,
                          style: TextStyle(color: theme.colorScheme.error),
                        ),
                        subtitle: Text(l10n.accountDeleteBody),
                        onTap: () => _delete(tile),
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
                        onTap: () => context.push(Routes.gallery),
                      ),
                    const SizedBox(height: Space.xl),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
                      child: OutlinedButton.icon(
                        onPressed: () => ref.read(authRepositoryProvider).signOut(),
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
      ),
    );
  }
}

/// The player's name and email, their rating limit (F8) and, for the owner, the role (K7).
class _ProfileCard extends StatelessWidget {
  const _ProfileCard({required this.user, required this.onEdit});

  final AccountUser user;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.lg, Space.lg, Space.sm, Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                PortraitAvatar(name: user.label, size: 56, ring: true),
                const SizedBox(width: Space.lg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(user.label, style: theme.textTheme.titleLarge),
                      if (user.email.isNotEmpty && user.email != user.label)
                        Text(
                          user.email,
                          style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: l10n.accountEditName,
                  icon: const Icon(Icons.edit_outlined),
                  onPressed: onEdit,
                ),
              ],
            ),
            const SizedBox(height: Space.md),
            Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                if (user.isOwner)
                  _Badge(icon: Icons.workspace_premium_outlined, label: l10n.accountOwner),
                _Badge(
                  icon: Icons.shield_outlined,
                  label: user.matureAllowed ? l10n.accountRatingMature : l10n.accountRatingTeen,
                ),
              ],
            ),
            if (!user.matureAllowed) ...[
              const SizedBox(height: Space.sm),
              Text(l10n.accountTeenNote, style: context.lucidText.meta),
            ],
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.xs + 2),
      decoration: BoxDecoration(
        color: colors.accentSoft,
        borderRadius: BorderRadius.circular(Radii.pill),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: colors.onAccentSoft),
          const SizedBox(width: Space.xs),
          Flexible(
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelMedium!.copyWith(color: colors.onAccentSoft),
            ),
          ),
        ],
      ),
    );
  }
}

/// Gore, romance and dark themes (F7), each saved as soon as it changes.
class _ContentPrefsSection extends StatelessWidget {
  const _ContentPrefsSection({required this.user, required this.onChanged});

  final AccountUser user;
  final ValueChanged<ContentPrefs> onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    final prefs = user.prefs;
    final secondary = theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
          child: Text(l10n.accountContentBody, style: secondary),
        ),
        const SizedBox(height: Space.lg),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(l10n.accountGore, style: theme.textTheme.bodyLarge),
              const SizedBox(height: Space.xxs),
              Text(l10n.accountGoreBody, style: secondary),
              const SizedBox(height: Space.md),
              SegmentedButton<GoreLevel>(
                key: const Key('account.gore'),
                segments: [
                  ButtonSegment(value: GoreLevel.low, label: Text(l10n.accountGoreLow)),
                  ButtonSegment(value: GoreLevel.medium, label: Text(l10n.accountGoreMedium)),
                  ButtonSegment(value: GoreLevel.high, label: Text(l10n.accountGoreHigh)),
                ],
                selected: {prefs.gore},
                showSelectedIcon: false,
                onSelectionChanged: (s) => onChanged(prefs.copyWith(gore: s.single)),
              ),
            ],
          ),
        ),
        const SizedBox(height: Space.sm),
        SwitchListTile(
          key: const Key('account.romance'),
          title: Text(l10n.accountRomance),
          subtitle: Text(l10n.accountRomanceBody),
          value: prefs.romance,
          onChanged: (v) => onChanged(prefs.copyWith(romance: v)),
        ),
        SwitchListTile(
          key: const Key('account.darkThemes'),
          title: Text(l10n.accountDarkThemes),
          subtitle: Text(l10n.accountDarkThemesBody),
          value: prefs.darkThemes,
          onChanged: (v) => onChanged(prefs.copyWith(darkThemes: v)),
        ),
      ],
    );
  }
}

/// Changes the display name (`PATCH /v1/me`).
class _NameEditor extends ConsumerStatefulWidget {
  const _NameEditor({required this.initial});

  final String initial;

  @override
  ConsumerState<_NameEditor> createState() => _NameEditorState();
}

class _NameEditorState extends ConsumerState<_NameEditor> {
  late final _name = TextEditingController(text: widget.initial);
  var _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final l10n = context.l10n;
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _error = l10n.authNeedName);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(meProvider.notifier).rename(name);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) {
        setState(
          () => _error = e.code == ApiErrorCode.validationError
              ? fieldErrors(l10n, e)['display_name'] ?? describeError(l10n, e).message
              : describeError(l10n, e).message,
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: const Key('account.name'),
          controller: _name,
          autofocus: true,
          enabled: !_busy,
          maxLength: 80,
          textCapitalization: TextCapitalization.words,
          textInputAction: TextInputAction.done,
          onSubmitted: (_) => _save(),
          decoration: InputDecoration(
            labelText: l10n.authNameLabel,
            helperText: l10n.accountNameHelper,
            helperMaxLines: 2,
            errorText: _error,
          ),
        ),
        const SizedBox(height: Space.lg),
        FilledButton(
          key: const Key('account.name.save'),
          onPressed: _busy ? null : _save,
          child: Text(l10n.accountSave),
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
