import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_error.dart';
import '../../core/api/api_error_text.dart';
import '../../core/l10n.dart';
import '../../core/preferences.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// Saves a new title and the settings that changed (only those fields). Throws [ApiException]
/// when it can't.
typedef SettingsSaver = Future<void> Function({String? title, Json? settings});

/// The story's settings (S6): its title, its color (S13), how long the narration runs, the tone,
/// difficulty (A5), how often events arrive (W16), pictures (M2) and suggested choices (S2). The
/// title and color show at once, the rest applies from the next scene. Gamer mode (S15) is here
/// too, and belongs to the device: it applies as it is flipped. A story's language isn't here:
/// it stays the one it started in (S10). Pops with what was saved, or null for nothing.
Future<SettingsSaved?> showStorySettings(
  BuildContext context, {
  required Story story,
  required SettingsSaver save,
}) => showAppSheet<SettingsSaved>(
  context: context,
  title: context.l10n.settingsTitle,
  builder: (_) => StorySettingsForm(story: story, save: save),
);

/// When what the player saved takes effect.
enum SettingsSaved {
  /// Only the title or the color (S13), which show at once.
  now,

  /// Something the storyteller reads, which applies from the next scene.
  nextScene,
}

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
      final later = changes.keys.any((key) => key != 'accent');
      if (mounted) Navigator.of(context).pop(later ? SettingsSaved.nextScene : SettingsSaved.now);
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

    // The form wears the color being picked, so the player sees it before saving (S13).
    final accent = GenreAccent.of(genre: widget.story.genre, chosen: _settings.accent);
    return AnimatedTheme(
      data: AppTheme.build(theme.brightness, accent),
      duration: Motion.of(context, Motion.slow),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _title,
            maxLength: 120,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(labelText: l10n.settingsName),
          ),
          const SizedBox(height: Space.md),
          Text(l10n.settingsColor, style: theme.textTheme.titleSmall),
          const SizedBox(height: Space.sm),
          _AccentPicker(
            genre: widget.story.genre,
            chosen: _settings.accent,
            onChanged: (v) => setState(() => _settings = _settings.copyWith(accent: () => v)),
          ),
          const SizedBox(height: Space.xs),
          Text(l10n.settingsColorHelp, style: hint),
          gap,
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
          // Gamer mode (S15) is how this device shows a turn, not part of the story: it applies
          // the moment it is flipped, with nothing to save.
          Consumer(
            builder: (context, ref, _) => SwitchListTile(
              key: const ValueKey('settings.gamer'),
              contentPadding: EdgeInsets.zero,
              value: ref.watch(gamerModeProvider),
              onChanged: (on) => unawaited(ref.read(gamerModeProvider.notifier).set(on)),
              title: Text(l10n.settingsGamer),
              subtitle: Text(l10n.settingsGamerHelp),
            ),
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
      ),
    );
  }
}

/// The story's color (S13): Automatic, which follows its genre, then every accent around the
/// color wheel. Each swatch shows the accent as this theme draws it.
class _AccentPicker extends StatelessWidget {
  const _AccentPicker({required this.genre, required this.chosen, required this.onChanged});

  final String genre;

  /// The accent's name, or null for Automatic.
  final String? chosen;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final brightness = Theme.of(context).brightness;
    // A name this app doesn't know counts as Automatic, the color the story shows.
    final picked = GenreAccent.byNameOrNull(chosen);
    return Wrap(
      spacing: Space.sm,
      runSpacing: Space.sm,
      children: [
        _Swatch(
          key: const Key('settings.color.auto'),
          color: accentFor(GenreAccent.forGenre(genre), brightness),
          label: l10n.settingsColorAuto,
          selected: picked == null,
          automatic: true,
          onTap: () => onChanged(null),
        ),
        for (final accent in GenreAccent.palette)
          _Swatch(
            key: Key('settings.color.${accent.name}'),
            color: accentFor(accent, brightness),
            label: _colorName(l10n, accent),
            selected: picked == accent,
            onTap: () => onChanged(accent.name),
          ),
      ],
    );
  }
}

/// An accent's name in the app's language, for the swatch's tooltip and screen readers.
String _colorName(AppLocalizations l10n, GenreAccent accent) => switch (accent) {
  GenreAccent.crimson => l10n.colorCrimson,
  GenreAccent.ember => l10n.colorEmber,
  GenreAccent.lucid => l10n.colorLucid,
  GenreAccent.lime => l10n.colorLime,
  GenreAccent.jade => l10n.colorJade,
  GenreAccent.cyan => l10n.colorCyan,
  GenreAccent.azure => l10n.colorAzure,
  GenreAccent.violet => l10n.colorViolet,
  GenreAccent.orchid => l10n.colorOrchid,
  GenreAccent.rose => l10n.colorRose,
  GenreAccent.silver => l10n.colorSilver,
};

/// One round color to pick, 48 dp across so it is easy to hit. A ring marks the one picked, and
/// Automatic carries a sparkle so it reads apart from the accent it stands for.
class _Swatch extends StatelessWidget {
  const _Swatch({
    super.key,
    required this.color,
    required this.label,
    required this.selected,
    required this.onTap,
    this.automatic = false,
  });

  final Color color;
  final String label;
  final bool selected;
  final bool automatic;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final mark = onColor(color);
    return Semantics(
      button: true,
      selected: selected,
      inMutuallyExclusiveGroup: true,
      label: label,
      // The tap below is left out with the rest of the swatch's own semantics, so it goes here.
      onTap: onTap,
      excludeSemantics: true,
      child: Tooltip(
        message: label,
        child: InkResponse(
          onTap: onTap,
          radius: 26,
          child: AnimatedContainer(
            duration: Motion.of(context, Motion.fast),
            width: 48,
            height: 48,
            padding: const EdgeInsets.all(3),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: selected ? context.lucid.textPrimary : Colors.transparent,
                width: 2,
              ),
            ),
            child: DecoratedBox(
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: automatic
                  ? Icon(Icons.auto_awesome_rounded, size: 20, color: mark)
                  : selected
                  ? Icon(Icons.check_rounded, size: 22, color: mark)
                  : null,
            ),
          ),
        ),
      ),
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
