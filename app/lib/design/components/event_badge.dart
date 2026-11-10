import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';

/// The size of an event (W16): it grows louder from personal to world.
enum EventSize {
  personal,
  local,
  world;

  static EventSize fromWire(String? value) => switch (value) {
    'world' => world,
    'local' => local,
    _ => personal,
  };
}

/// Marks a scene where an event arrived, such as "Local event · Fire in the lower market": a
/// lit dot, the kind in small capitals and the event's name, in a pill of the accent. It grows
/// louder with the event's size: an outline, then a tint with the dot aglow, then the accent's
/// own gradient.
class EventBadge extends StatelessWidget {
  const EventBadge({super.key, required this.size, required this.title});

  final EventSize size;
  final String title;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    final world = size == EventSize.world;
    final kind = switch (size) {
      EventSize.personal => l10n.eventPersonal,
      EventSize.local => l10n.eventLocal,
      EventSize.world => l10n.eventWorld,
    };
    final kindColor = world ? colors.onAccent : colors.accent;
    final titleColor = world ? colors.onAccent : colors.accentHi;
    final overline = context.lucidText.overline.copyWith(color: kindColor);
    return Semantics(
      container: true,
      label: '$kind: $title',
      excludeSemantics: true,
      child: Container(
        constraints: const BoxConstraints(minHeight: 30),
        padding: const EdgeInsets.fromLTRB(12, 5, 14, 5),
        decoration: ShapeDecoration(
          color: switch (size) {
            EventSize.personal => null,
            EventSize.local => colors.accent.withValues(alpha: 0.1),
            EventSize.world => null,
          },
          gradient: world ? colors.accentGradient() : null,
          shape: StadiumBorder(
            side: world
                ? BorderSide.none
                : BorderSide(color: colors.accent.withValues(alpha: 0.34)),
          ),
          shadows: [
            if (world) BoxShadow(color: colors.accent.withValues(alpha: 0.3), blurRadius: 22),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: kindColor,
                boxShadow: [
                  if (size == EventSize.local) BoxShadow(color: colors.accent, blurRadius: 10),
                ],
              ),
            ),
            const SizedBox(width: 9),
            // One paragraph, so a long title or large text wraps under the kind instead of
            // squeezing into a sliver beside it.
            Flexible(
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(text: kind.toUpperCase(), style: overline),
                    TextSpan(text: '  ·  ', style: overline),
                    TextSpan(text: title),
                  ],
                ),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.labelLarge!.copyWith(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: titleColor,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
