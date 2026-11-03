import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/byok_store.dart';
import '../../core/config.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
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
    setState(() => _hasKey = true);
  }

  Future<void> _clear() async {
    await ref.read(byokStoreProvider).clearGeminiKey();
    setState(() => _hasKey = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Your own API key', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
            'Use your own Gemini API key instead of app credits. It stays on this device and is '
            'sent only with your story requests.',
          ),
          const SizedBox(height: 16),
          if (_hasKey)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.key),
              title: const Text('Gemini key saved'),
              trailing: TextButton(onPressed: _clear, child: const Text('Remove')),
            )
          else
            TextField(
              controller: _key,
              obscureText: true,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: 'Gemini API key',
                suffixIcon: IconButton(icon: const Icon(Icons.save), onPressed: _save),
              ),
              onSubmitted: (_) => _save(),
            ),
          const Divider(height: 48),
          Text('Developer', style: theme.textTheme.titleMedium),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('API base URL'),
            subtitle: const Text(AppConfig.apiBaseUrl),
          ),
        ],
      ),
    );
  }
}
