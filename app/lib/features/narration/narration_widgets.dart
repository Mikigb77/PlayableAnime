import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'narration_settings.dart';
import 'narrator.dart';

/// The play button in a scene's footer (V8): reads the scene aloud, and stops it while it is
/// read.
class ListenButton extends StatelessWidget {
  const ListenButton({
    super.key,
    required this.phase,
    required this.onListen,
    required this.onStop,
  });

  final NarrationPhase phase;
  final VoidCallback onListen;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return switch (phase) {
      NarrationPhase.idle => IconButton(
        tooltip: l10n.sceneListen,
        onPressed: onListen,
        icon: const Icon(Icons.volume_up_outlined),
      ),
      NarrationPhase.loading => IconButton(
        tooltip: l10n.sceneListenStop,
        onPressed: onStop,
        icon: SizedBox.square(
          dimension: 20,
          child: CircularProgressIndicator(strokeWidth: 2, color: context.lucid.accent),
        ),
      ),
      NarrationPhase.reading => IconButton(
        tooltip: l10n.sceneListenStop,
        onPressed: onStop,
        icon: Icon(Icons.stop_circle_outlined, color: context.lucid.accent),
      ),
    };
  }
}

/// Above the composer while a scene is read aloud: which voice reads it, whether new scenes are
/// read too, and stop.
class ReadingBar extends StatelessWidget {
  const ReadingBar({
    super.key,
    required this.deviceVoice,
    required this.readNewScenes,
    required this.onReadNewScenes,
    required this.onStop,
  });

  /// The device's voice is reading, chosen or standing in for the studio voice.
  final bool deviceVoice;
  final bool readNewScenes;
  final ValueChanged<bool> onReadNewScenes;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Layout.barInset, 0, Layout.barInset, Space.xs),
      child: Material(
        color: theme.colorScheme.surfaceContainerHigh,
        shape: StadiumBorder(side: BorderSide(color: colors.hairline)),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsetsDirectional.only(start: Space.gutter, end: Space.xs),
          child: Row(
            children: [
              Icon(Icons.graphic_eq_rounded, size: 20, color: colors.accent),
              const SizedBox(width: Space.sm),
              Expanded(
                child: Text(
                  deviceVoice ? l10n.narrationReadingDevice : l10n.narrationReading,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelLarge,
                ),
              ),
              const SizedBox(width: Space.sm),
              Flexible(
                child: FilterChip(
                  key: const ValueKey('reading.readNew'),
                  label: Text(
                    l10n.narrationKeepReading,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  selected: readNewScenes,
                  onSelected: onReadNewScenes,
                  visualDensity: VisualDensity.compact,
                ),
              ),
              IconButton(
                key: const ValueKey('reading.stop'),
                tooltip: l10n.narrationStop,
                onPressed: onStop,
                icon: const Icon(Icons.stop_rounded),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Account's "Reading aloud" (V9): the studio voice or the device's, which studio voice, and
/// whether new scenes are read as they land.
class NarrationSection extends ConsumerWidget {
  const NarrationSection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final settings = ref.watch(narrationSettingsProvider);
    final controller = ref.read(narrationSettingsProvider.notifier);
    final secondary = theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textSecondary);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(l10n.accountReadingAloudBody, style: secondary),
          const SizedBox(height: Space.lg),
          SegmentedButton<NarrationVoice>(
            key: const ValueKey('narration.voice'),
            segments: [
              ButtonSegment(
                value: NarrationVoice.studio,
                label: Text(l10n.narrationStudio),
                icon: const Icon(Icons.record_voice_over_outlined),
              ),
              ButtonSegment(
                value: NarrationVoice.device,
                label: Text(l10n.narrationDevice),
                icon: const Icon(Icons.smartphone_outlined),
              ),
            ],
            selected: {settings.voice},
            showSelectedIcon: false,
            onSelectionChanged: (s) => controller.setVoice(s.single),
          ),
          const SizedBox(height: Space.sm),
          Text(switch (settings.voice) {
            NarrationVoice.studio => l10n.narrationStudioBody,
            NarrationVoice.device => l10n.narrationDeviceBody,
          }, style: secondary),
          if (settings.voice == NarrationVoice.studio) ...[
            const SizedBox(height: Space.lg),
            Text(l10n.narrationVoiceLabel, style: theme.textTheme.labelLarge),
            const SizedBox(height: Space.sm),
            Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                for (final voice in StudioVoice.values)
                  ChoiceChip(
                    key: ValueKey('narration.studio.${voice.wire}'),
                    label: Text('${voice.wire} · ${_describe(l10n, voice)}'),
                    selected: settings.studioVoice == voice,
                    onSelected: (_) => controller.setStudioVoice(voice),
                  ),
              ],
            ),
          ],
          const SizedBox(height: Space.sm),
          SwitchListTile(
            key: const ValueKey('narration.readNew'),
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.narrationReadNew),
            subtitle: Text(l10n.narrationReadNewBody),
            value: settings.readNewScenes,
            onChanged: controller.setReadNewScenes,
          ),
        ],
      ),
    );
  }

  static String _describe(AppLocalizations l10n, StudioVoice voice) => switch (voice) {
    StudioVoice.sulafat => l10n.narrationVoiceWarm,
    StudioVoice.gacrux => l10n.narrationVoiceMature,
    StudioVoice.charon => l10n.narrationVoiceDeep,
    StudioVoice.algieba => l10n.narrationVoiceSmooth,
  };
}
