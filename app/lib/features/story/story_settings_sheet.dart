import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// Saves a new title and the settings that changed (only those fields). Throws [ApiException]
/// when it can't.
typedef SettingsSaver = Future<void> Function({String? title, Json? settings});

/// The story's settings (S6): its title, how long the narration runs, the tone, difficulty (A5),
/// how often events arrive (W16), pictures (M2) and suggested choices (S2). Changes apply from the
/// next scene. Pops with true when something was saved.
Future<bool?> showStorySettings(
  BuildContext context, {
  required Story story,
  required SettingsSaver save,
}) => showAppSheet<bool>(
  context: context,
  title: context.l10n.settingsTitle,
  builder: (_) => StorySettingsForm(story: story, save: save),
);

class StorySettingsForm extends StatefulWidget {
  const StorySettingsForm({super.key, required this.story, required this.save});

  final Story story;
  final SettingsSaver save;

  @override
  State<StorySettingsForm> createState() => _StorySettingsFormState();
}

class _StorySettingsFormState extends State<StorySettingsForm> {
  late final _title = TextEditingController(text: widget.story.title);
  late final _tone = TextEditingController(text: widget.story.settings.tone ?? '');
  late StorySettings _settings = widget.story.settings;
  bool _saving = false;
  ApiException? _error;

  @override
  void initState() {
    super.initState();
    _title.addListener(_changed);
    _tone.addListener(_changed);
  }

  @override
  void dispose() {
    _title.dispose();
    _tone.dispose();
    super.dispose();
  }

  void _changed() => setState(() {});

  StorySettings get _edited => _settings.copyWith(tone: _tone.text);

  String get _titleText => _title.text.trim().replaceAll(RegExp(r'\s+'), ' ');

  bool get _dirty =>
      _edited != widget.story.settings ||
      (_titleText.isNotEmpty && _titleText != widget.story.title);

  Future<void> _save() async {
    if (!_dirty || _saving) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final title = _titleText.isNotEmpty && _titleText != widget.story.title ? _titleText : null;
    final changes = _edited.changesFrom(widget.story.settings);
    final settings = changes.isEmpty ? null : changes;
    try {
      await widget.save(title: title, settings: settings);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = e;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final hint = theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary);
    const gap = SizedBox(height: Space.xl);

    Widget choose(
      String label,
      String value,
      List<(String, String)> options,
      ValueChanged<String> onChanged, {
      String? help,
    }) => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(label, style: theme.textTheme.titleSmall),
        const SizedBox(height: Space.sm),
        _Options(value: value, options: options, onChanged: onChanged),
        if (help != null) ...[const SizedBox(height: Space.xs), Text(help, style: hint)],
      ],
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _title,
          maxLength: 120,
          textCapitalization: TextCapitalization.words,
          decoration: InputDecoration(labelText: l10n.settingsName),
        ),
        const SizedBox(height: Space.md),
        choose(
          l10n.settingsNarration,
          _settings.narrationLength,
          [
            ('short', l10n.settingsShort),
            ('medium', l10n.settingsMedium),
            ('long', l10n.settingsLong),
          ],
          (v) => setState(() => _settings = _settings.copyWith(narrationLength: v)),
        ),
        gap,
        TextField(
          controller: _tone,
          maxLength: 200,
          textCapitalization: TextCapitalization.sentences,
          decoration: InputDecoration(
            labelText: l10n.settingsTone,
            hintText: l10n.settingsToneHint,
          ),
        ),
        const SizedBox(height: Space.md),
        choose(
          l10n.settingsDifficulty,
          _settings.difficulty,
          [
            ('story', l10n.settingsStory),
            ('balanced', l10n.settingsBalanced),
            ('brutal', l10n.settingsBrutal),
          ],
          (v) => setState(() => _settings = _settings.copyWith(difficulty: v)),
          help: switch (_settings.difficulty) {
            'story' => l10n.settingsStoryHelp,
            'brutal' => l10n.settingsBrutalHelp,
            _ => l10n.settingsBalancedHelp,
          },
        ),
        gap,
        choose(
          l10n.settingsEvents,
          _settings.eventFrequency,
          [
            ('calm', l10n.settingsCalm),
            ('normal', l10n.settingsNormal),
            ('dramatic', l10n.settingsDramatic),
          ],
          (v) => setState(() => _settings = _settings.copyWith(eventFrequency: v)),
        ),
        gap,
        choose(
          l10n.settingsPictures,
          _settings.images,
          [
            ('off', l10n.settingsOff),
            ('key_moments', l10n.settingsKeyMoments),
            ('more', l10n.settingsMore),
          ],
          (v) => setState(() => _settings = _settings.copyWith(images: v)),
          help: l10n.settingsPicturesHelp,
        ),
        const SizedBox(height: Space.md),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          value: _settings.suggestions,
          onChanged: (v) => setState(() => _settings = _settings.copyWith(suggestions: v)),
          title: Text(l10n.settingsSuggestions),
          subtitle: Text(l10n.settingsSuggestionsHelp),
        ),
        if (_error case final error?) ...[
          const SizedBox(height: Space.sm),
          Text(
            describeError(l10n, error).message,
            style: theme.textTheme.bodyMedium!.copyWith(color: theme.colorScheme.error),
          ),
        ],
        const SizedBox(height: Space.lg),
        Text(l10n.settingsNextScene, style: context.lucidText.meta),
        const SizedBox(height: Space.md),
        FilledButton(
          onPressed: _dirty && !_saving ? _save : null,
          child: _saving
              ? SizedBox.square(
                  dimension: 20,
                  child: CircularProgressIndicator(strokeWidth: 2, color: colors.textMuted),
                )
              : Text(l10n.settingsSave),
        ),
      ],
    );
  }
}

/// A row of mutually exclusive options. Chips wrap onto a second line at large text sizes, where
/// a segmented button would squeeze its labels.
class _Options extends StatelessWidget {
  const _Options({required this.value, required this.options, required this.onChanged});

  final String value;
  final List<(String value, String label)> options;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Space.sm,
      runSpacing: Space.sm,
      children: [
        for (final (option, label) in options)
          ChoiceChip(
            label: Text(label),
            selected: option == value,
            showCheckmark: false,
            onSelected: (_) => onChanged(option),
          ),
      ],
    );
  }
}
