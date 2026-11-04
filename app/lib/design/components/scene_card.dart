import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import '../tokens.dart';

/// One scene in the reading feed. It reads like a page, not a chat: what the player did, then the
/// time it took and any event, the picture full-bleed across the column, the narration in the
/// reading serif, and the characters present, with a quiet ornament between scenes.
///
/// Every part is a slot, so the play screen (WS14) passes its own widgets: a [TimeChip], an
/// [EventBadge], a [PictureSlot], a [StreamingNarration] or [NarrationText], a [PortraitStack].
class SceneCard extends StatelessWidget {
  const SceneCard({
    super.key,
    required this.narration,
    this.playerAction,
    this.spokenAction = false,
    this.time,
    this.event,
    this.picture,
    this.portraits,
    this.onDetails,
    this.onMore,
    this.ornament = true,
    this.gutter = Space.gutter,
    this.pictureAfterNarration = false,
  });

  final Widget narration;

  /// The action that led to this scene, as the player wrote, said or chose it.
  final String? playerAction;

  /// The action was dictated (V7), shown with a small mic.
  final bool spokenAction;
  final Widget? time;
  final Widget? event;
  final Widget? picture;
  final Widget? portraits;

  /// Opens the scene details (steps, classes, rolls and reasons, A8).
  final VoidCallback? onDetails;

  /// Opens the scene menu (report and block, F6; illustrate, M2).
  final VoidCallback? onMore;

  /// The divider ornament under the scene.
  final bool ornament;

  /// Side padding for the text. The picture ignores it and spans the column.
  final double gutter;

  /// Puts the picture under the narration instead of above it. The play screen does this, so a
  /// picture that arrives after the text (M3) lands where the reader's eyes are, and never pushes
  /// the words they are reading down the page.
  final bool pictureAfterNarration;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colors = context.lucid;
    final pad = EdgeInsets.symmetric(horizontal: gutter);
    final hasMeta = time != null || event != null;
    final hasFooter = portraits != null || onDetails != null || onMore != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (playerAction case final action?)
          Padding(
            padding: pad.copyWith(bottom: Space.md),
            child: _PlayerAction(text: action, spoken: spokenAction),
          ),
        if (hasMeta)
          Padding(
            padding: pad.copyWith(bottom: Space.lg),
            child: Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [?time, ?event],
            ),
          ),
        if (picture case final picture? when !pictureAfterNarration)
          Padding(
            padding: const EdgeInsets.only(bottom: Space.lg),
            child: picture,
          ),
        Padding(padding: pad, child: narration),
        if (picture case final picture? when pictureAfterNarration)
          Padding(
            padding: const EdgeInsets.only(top: Space.xl),
            child: picture,
          ),
        if (hasFooter)
          Padding(
            padding: pad.copyWith(top: Space.md),
            child: Row(
              children: [
                ?portraits,
                Expanded(
                  child: Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: onDetails == null
                        ? null
                        : TextButton.icon(
                            onPressed: onDetails,
                            icon: const Icon(Icons.insights_rounded, size: 18),
                            label: Text(
                              l10n.sceneDetails,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            style: TextButton.styleFrom(foregroundColor: colors.textSecondary),
                          ),
                  ),
                ),
                if (onMore != null)
                  IconButton(
                    tooltip: l10n.sceneMore,
                    onPressed: onMore,
                    icon: const Icon(Icons.more_horiz_rounded),
                  ),
              ],
            ),
          ),
        if (ornament) const SceneOrnament(),
      ],
    );
  }
}

class _PlayerAction extends StatelessWidget {
  const _PlayerAction({required this.text, required this.spoken});

  final String text;
  final bool spoken;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    return Semantics(
      label: context.l10n.youDid(text),
      excludeSemantics: true,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              width: 3,
              decoration: BoxDecoration(
                color: colors.accent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Text.rich(
                  TextSpan(
                    children: [
                      if (spoken)
                        WidgetSpan(
                          alignment: PlaceholderAlignment.middle,
                          child: Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: Icon(Icons.mic_none_rounded, size: 16, color: colors.textMuted),
                          ),
                        ),
                      TextSpan(text: text),
                    ],
                  ),
                  style: context.lucidText.playerAction,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A small diamond between scenes.
class SceneOrnament extends StatelessWidget {
  const SceneOrnament({super.key});

  @override
  Widget build(BuildContext context) {
    final line = Theme.of(context).colorScheme.outlineVariant;
    final accent = context.lucid.accent.withValues(alpha: 0.7);
    return ExcludeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xxl),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(width: 48, child: Divider(color: line)),
            const SizedBox(width: Space.md),
            Transform.rotate(angle: 0.785398, child: Container(width: 6, height: 6, color: accent)),
            const SizedBox(width: Space.md),
            SizedBox(width: 48, child: Divider(color: line)),
          ],
        ),
      ),
    );
  }
}
