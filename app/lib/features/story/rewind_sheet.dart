import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// Asks how many scenes back to rewind a story from its ending (C8), at most [most]. Each choice
/// names the action it takes back first, read from the [scenes] on screen. Answers the number of
/// scenes, or null when the player changes their mind.
Future<int?> showRewindSheet(
  BuildContext context, {
  required int most,
  required List<Scene> scenes,
}) {
  final l10n = context.l10n;
  return showAppSheet<int>(
    context: context,
    title: l10n.rewindTitle,
    builder: (context) => _RewindChoices(most: most, scenes: scenes),
  );
}

class _RewindChoices extends StatelessWidget {
  const _RewindChoices({required this.most, required this.scenes});

  final int most;
  final List<Scene> scenes;

  /// What the player did in the first scene a rewind of [count] takes back, if the scene had an
  /// action and is on screen.
  String? _takenBack(int count) {
    final index = scenes.length - count;
    if (index < 0) return null;
    final action = scenes[index].playerAction?.trim() ?? '';
    return action.isEmpty ? null : action;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          l10n.rewindBody,
          style: theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textMuted),
        ),
        const SizedBox(height: Space.md),
        for (var count = 1; count <= most; count++)
          ListTile(
            key: ValueKey('rewind.$count'),
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.history),
            title: Text(l10n.rewindScenes(count)),
            subtitle: switch (_takenBack(count)) {
              final action? => Text(
                l10n.rewindBefore(action),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              null => null,
            },
            onTap: () => Navigator.of(context).pop(count),
          ),
      ],
    );
  }
}
