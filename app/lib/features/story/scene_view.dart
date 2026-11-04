import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import 'story_models.dart';

/// One saved scene in the feed: what the player did, how long it took and when it ended (W10,
/// W10a), any event (W16), the narration, its picture once painted (M3), the characters present
/// (M4) and a footer that opens the details (A8) and the scene menu (F6, M2).
class SceneView extends StatelessWidget {
  const SceneView({
    super.key,
    required this.scene,
    required this.image,
    this.hidden = false,
    this.ornament = true,
    this.narrationKey,
    this.onDetails,
    this.onMore,
    this.onPictureError,
  });

  final Scene scene;

  /// The picture to show: the scene's own, or the same picture's current URL (M4).
  final SceneImage? image;

  /// The player blocked this scene (F6): its text and picture stay out of sight, for good.
  final bool hidden;
  final bool ornament;

  /// Marks the narration, so the screen can keep it in place when the scene lands.
  final Key? narrationKey;
  final VoidCallback? onDetails;
  final VoidCallback? onMore;

  final VoidCallback? onPictureError;

  @override
  Widget build(BuildContext context) {
    if (hidden) {
      return SceneCard(
        ornament: ornament,
        onMore: onMore,
        narration: KeyedSubtree(key: narrationKey, child: const _HiddenScene()),
      );
    }
    final image = this.image;
    return SceneCard(
      playerAction: scene.playerAction,
      spokenAction: scene.spoken,
      ornament: ornament,
      pictureAfterNarration: true,
      time: scene.hasTime
          ? TimeChip(
              // An opening takes no time, so it shows only when it happens.
              duration: scene.kind == 'opening' ? null : scene.durationLabel,
              label: scene.timeLabel,
              personalLabel: scene.personalTimeLabel,
            )
          : null,
      event: scene.eventTitle == null
          ? null
          : EventBadge(size: EventSize.fromWire(scene.eventSize), title: scene.eventTitle!),
      picture: image == null || image.isSkipped
          ? null
          : ScenePictureView(image: image, onError: onPictureError),
      narration: KeyedSubtree(key: narrationKey, child: NarrationText(scene.narration)),
      portraits: scene.portraits.isEmpty ? null : ScenePortraits(portraits: scene.portraits),
      onDetails: scene.details.isEmpty ? null : onDetails,
      onMore: onMore,
    );
  }
}

/// A scene's picture in its slot: a shimmer while it is painted, then the picture, shaped by its
/// kind before it arrives so nothing jumps (portraits 3:4, places and scenes 16:9).
class ScenePictureView extends StatelessWidget {
  const ScenePictureView({super.key, required this.image, this.onError});

  final SceneImage image;
  final VoidCallback? onError;

  @override
  Widget build(BuildContext context) {
    final status = switch (image.status) {
      'ready' => PictureStatus.ready,
      'skipped' => PictureStatus.skipped,
      _ => PictureStatus.pending,
    };
    if (image.aspectRatio < 1) {
      // A portrait or cover is tall: shown at a portrait's width, centered, so it doesn't fill
      // the whole screen.
      return Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 280),
          child: PictureSlot(
            status: status,
            url: image.url,
            aspectRatio: image.aspectRatio,
            onError: onError,
          ),
        ),
      );
    }
    return PictureSlot(
      status: status,
      url: image.url,
      aspectRatio: image.aspectRatio,
      onError: onError,
      // Edge to edge on phones; rounded once the reading column floats in a wider screen.
      borderRadius: MediaQuery.sizeOf(context).width > Layout.readingWidth
          ? Radii.picture
          : BorderRadius.zero,
    );
  }
}

/// The known characters in a scene. Tapping them lists who is there, with larger portraits.
class ScenePortraits extends StatelessWidget {
  const ScenePortraits({super.key, required this.portraits});

  final List<ScenePortrait> portraits;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      button: true,
      label: l10n.storyPortraitsLabel(portraits.map((p) => p.name).join(', ')),
      excludeSemantics: true,
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.pill),
        onTap: () => showAppSheet<void>(
          context: context,
          title: l10n.storyPortraits,
          builder: (sheet) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final p in portraits)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: Space.sm),
                  child: Row(
                    children: [
                      PortraitAvatar(name: p.name, url: p.url, size: 56),
                      const SizedBox(width: Space.lg),
                      Expanded(child: Text(p.name, style: Theme.of(sheet).textTheme.titleMedium)),
                    ],
                  ),
                ),
            ],
          ),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: Layout.minTouch),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.xs),
            child: Center(
              widthFactor: 1,
              child: PortraitStack(
                portraits: [for (final p in portraits) PortraitRef(name: p.name, url: p.url)],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HiddenScene extends StatelessWidget {
  const _HiddenScene();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    return Container(
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(Radii.lg),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(Icons.visibility_off_outlined, size: 20, color: colors.textMuted),
          const SizedBox(width: Space.md),
          Expanded(
            child: Text(
              context.l10n.storyHidden,
              style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }
}
