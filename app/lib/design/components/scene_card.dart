import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import '../tokens.dart';
import 'pills.dart';

/// One scene in the reading feed. It reads like a page, not a chat: what the player did beside
/// a thin line of the accent, the heading of a scene that hours or days passed in ("Three days
/// later"), then the time it took and any event as chips, the narration in the reading serif,
/// the picture full-bleed across the column, and a footer with the characters present and the
/// way into the scene's details, with a quiet ornament between scenes.
///
/// Every part is a slot, so the play screen (WS14) passes its own widgets: a [TimeChip], an
/// [EventBadge], a [PictureSlot], a [StreamingNarration] or [NarrationText], a [PortraitStack].
class SceneCard extends StatelessWidget {
  const SceneCard({
    super.key,
    required this.narration,
    this.playerAction,
    this.spokenAction = false,
    this.passage,
    this.time,
    this.event,
    this.picture,
    this.portraits,
    this.onDetails,
    this.listen,
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

  /// The heading of a scene that hours or days passed in, such as "Three days later" (W10).
  final String? passage;
  final Widget? time;
  final Widget? event;
  final Widget? picture;
  final Widget? portraits;

  /// Opens the scene details (steps, classes, rolls and reasons, A8).
  final VoidCallback? onDetails;

  /// Reads the scene aloud (V8): the play screen's listen button, beside the menu.
  final Widget? listen;

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
    final pad = EdgeInsets.symmetric(horizontal: gutter);
    final hasMeta = time != null || event != null;
    final hasFooter = portraits != null || onDetails != null || listen != null || onMore != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (playerAction case final action?)
          Padding(
            padding: pad.copyWith(bottom: 14),
            child: _PlayerAction(text: action, spoken: spokenAction),
          ),
        if (passage case final passage?)
          Padding(
            padding: pad.copyWith(top: playerAction == null ? 0 : 6, bottom: 20),
            child: PassageHeading(passage),
          ),
        if (hasMeta)
          Padding(
            padding: pad.copyWith(bottom: 18),
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
            padding: pad.copyWith(top: Space.sm),
            // Who is in the scene, and at the far side what can be done with it, or under the
            // portraits when the two don't fit on a line: a narrow phone in a long language.
            child: Wrap(
              alignment: portraits == null ? WrapAlignment.end : WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                ?portraits,
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (onDetails != null)
                      Flexible(
                        child: GhostPill(
                          icon: Icons.insights_rounded,
                          label: l10n.sceneDetails,
                          onPressed: onDetails,
                        ),
                      ),
                    ?listen,
                    if (onMore != null)
                      IconButton(
                        tooltip: l10n.sceneMore,
                        onPressed: onMore,
                        icon: const Icon(Icons.more_horiz_rounded),
                      ),
                  ],
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
              width: 2,
              decoration: BoxDecoration(
                color: colors.accent,
                borderRadius: BorderRadius.circular(1),
              ),
            ),
            const SizedBox(width: 14),
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

/// The heading over a scene that hours or days passed in, as a book marks a cut (W10): "Three
/// days later" in the display serif, between two hairlines of the accent that fade out to the
/// sides. The words are the server's, in the story's language.
class PassageHeading extends StatelessWidget {
  const PassageHeading(this.text, {super.key});

  final String text;

  /// The least a line keeps beside the words, and the gap between a line and the words.
  static const double _line = 28;
  static const double _gap = Space.lg;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final line = colors.accent.withValues(alpha: 0.5);
    final style = Theme.of(context).textTheme.headlineSmall!.copyWith(
      fontSize: 19,
      height: 26 / 19,
      letterSpacing: 0.2,
      color: colors.textPrimary,
    );
    return Semantics(
      header: true,
      child: LayoutBuilder(
        builder: (context, constraints) {
          // The words take what they need and the lines share the rest, so a long heading in
          // large text wraps between two short lines instead of running off the page.
          final room = constraints.maxWidth - 2 * (_line + _gap);
          return Row(
            children: [
              Expanded(child: _FadingLine(color: line)),
              const SizedBox(width: _gap),
              ConstrainedBox(
                constraints: BoxConstraints(maxWidth: room < 0 ? 0 : room),
                child: Text(text, textAlign: TextAlign.center, style: style),
              ),
              const SizedBox(width: _gap),
              Expanded(child: _FadingLine(color: line, reversed: true)),
            ],
          );
        },
      ),
    );
  }
}

/// A small diamond between scenes, on a hairline that fades out to both sides.
class SceneOrnament extends StatelessWidget {
  const SceneOrnament({super.key});

  @override
  Widget build(BuildContext context) {
    final accent = context.lucid.accent;
    return ExcludeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xxl),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _FadingLine(color: accent.withValues(alpha: 0.45), width: 64),
            const SizedBox(width: Space.md),
            Transform.rotate(
              angle: 0.785398,
              child: Container(width: 6, height: 6, color: accent.withValues(alpha: 0.8)),
            ),
            const SizedBox(width: Space.md),
            _FadingLine(color: accent.withValues(alpha: 0.45), width: 64, reversed: true),
          ],
        ),
      ),
    );
  }
}

/// The rule under a story's title: a star in the accent on a line that fades out to both sides,
/// across the column.
class StarRule extends StatelessWidget {
  const StarRule({super.key});

  @override
  Widget build(BuildContext context) {
    final accent = context.lucid.accent;
    return ExcludeSemantics(
      child: Row(
        children: [
          Expanded(child: _FadingLine(color: accent.withValues(alpha: 0.6))),
          const SizedBox(width: Space.md),
          Icon(Icons.auto_awesome_rounded, size: 13, color: accent),
          const SizedBox(width: Space.md),
          Expanded(child: _FadingLine(color: accent.withValues(alpha: 0.6), reversed: true)),
        ],
      ),
    );
  }
}

/// A hairline that comes out of nothing into [color], or, [reversed], goes back into nothing.
class _FadingLine extends StatelessWidget {
  const _FadingLine({required this.color, this.width, this.reversed = false});

  final Color color;
  final double? width;
  final bool reversed;

  @override
  Widget build(BuildContext context) {
    final clear = color.withValues(alpha: 0);
    return Container(
      width: width,
      height: 1,
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: reversed ? [color, clear] : [clear, color]),
      ),
    );
  }
}
