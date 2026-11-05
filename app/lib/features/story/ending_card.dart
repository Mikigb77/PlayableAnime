import 'package:flutter/material.dart';

import '../../core/api/turn_events.dart';
import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// The end of a story (N6), under its last scene: the character died, or the player ended it with
/// `/end`. It takes no more turns, so the composer gives way to this. The player closes the story
/// or starts again from the same premise. After a character took their own life, one quiet line
/// says where to find support.
class EndingCard extends StatelessWidget {
  const EndingCard({
    super.key,
    required this.ending,
    required this.onStartAgain,
    this.onClose,
    this.closing = false,
  });

  final StoryEnding ending;

  /// Opens the create flow with the same premise filled in, to keep or change.
  final VoidCallback? onStartAgain;

  /// Closes the story. Not offered once it is closed.
  final VoidCallback? onClose;
  final bool closing;

  String _title(BuildContext context) {
    final l10n = context.l10n;
    final name = ending.character.trim();
    if (ending.closed) return l10n.endingClosedTitle;
    if (ending.isDeath) {
      return name.isEmpty ? l10n.endingDeathTitleNameless : l10n.endingDeathTitle(name);
    }
    return name.isEmpty ? l10n.endingChosenTitleNameless : l10n.endingChosenTitle(name);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final muted = context.lucid.textMuted;
    return Semantics(
      container: true,
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, 0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const SceneOrnament(),
            const SizedBox(height: Space.lg),
            Semantics(
              header: true,
              child: Text(
                _title(context),
                key: const ValueKey('ending.title'),
                textAlign: TextAlign.center,
                style: theme.textTheme.headlineSmall,
              ),
            ),
            const SizedBox(height: Space.sm),
            Text(
              ending.closed ? l10n.endingClosedBody : l10n.endingBody,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium!.copyWith(color: muted),
            ),
            const SizedBox(height: Space.lg),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                if (!ending.closed && onClose != null)
                  OutlinedButton(
                    key: const ValueKey('ending.close'),
                    onPressed: closing ? null : onClose,
                    child: Text(l10n.endingClose),
                  ),
                FilledButton.tonal(
                  key: const ValueKey('ending.startAgain'),
                  onPressed: onStartAgain,
                  child: Text(l10n.endingStartAgain),
                ),
              ],
            ),
            if (ending.isDeath && ending.selfInflicted) ...[
              const SizedBox(height: Space.xl),
              Text(
                l10n.endingHelpline,
                key: const ValueKey('ending.helpline'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall!.copyWith(color: muted),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// What the world refused of an ending's note (N6), each part with its reason in the world's
/// words. Nothing was saved: the player plays on to earn it, or ends without it.
class EndingRefusedCard extends StatelessWidget {
  const EndingRefusedCard({
    super.key,
    required this.parts,
    required this.onPlayOn,
    required this.onEndWithout,
  });

  final List<RefusedPart> parts;
  final VoidCallback onPlayOn;
  final VoidCallback onEndWithout;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Semantics(
      container: true,
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(Space.lg),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(Radii.lg),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l10n.endRefusedTitle, style: theme.textTheme.titleMedium),
            const SizedBox(height: Space.sm),
            for (final part in parts)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.sm),
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: part.text,
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      if (part.reason.trim().isNotEmpty) TextSpan(text: ': ${part.reason.trim()}'),
                    ],
                  ),
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            Text(
              l10n.endRefusedBody,
              style: theme.textTheme.bodyMedium!.copyWith(color: context.lucid.textMuted),
            ),
            const SizedBox(height: Space.md),
            Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [
                FilledButton.tonal(
                  key: const ValueKey('ending.playOn'),
                  onPressed: onPlayOn,
                  child: Text(l10n.endRefusedPlayOn),
                ),
                OutlinedButton(
                  key: const ValueKey('ending.endWithout'),
                  onPressed: onEndWithout,
                  child: Text(l10n.endRefusedEndWithout),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
