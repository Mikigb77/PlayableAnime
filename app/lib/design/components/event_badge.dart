import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import '../tokens.dart';

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

/// Marks a scene where an event arrived, such as "Local event · Fire in the lower market".
class EventBadge extends StatelessWidget {
  const EventBadge({super.key, required this.size, required this.title});

  final EventSize size;
  final String title;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    final (background, foreground, border) = switch (size) {
      EventSize.personal => (
        Colors.transparent,
        colors.accent,
        colors.accent.withValues(alpha: 0.5),
      ),
      EventSize.local => (colors.accentSoft, colors.onAccentSoft, Colors.transparent),
      EventSize.world => (colors.accent, colors.onAccent, Colors.transparent),
    };
    final (icon, kind) = switch (size) {
      EventSize.personal => (Icons.person_pin_outlined, l10n.eventPersonal),
      EventSize.local => (Icons.location_on_outlined, l10n.eventLocal),
      EventSize.world => (Icons.public_rounded, l10n.eventWorld),
    };
    final overline = context.lucidText.overline.copyWith(color: foreground);
    return Semantics(
      container: true,
      label: '$kind: $title',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.fromLTRB(10, 6, 14, 6),
        decoration: BoxDecoration(
          color: background,
          border: Border.all(color: border),
          borderRadius: BorderRadius.circular(Radii.pill),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: foreground),
            const SizedBox(width: 6),
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
                style: Theme.of(context).textTheme.labelLarge!.copyWith(color: foreground),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
