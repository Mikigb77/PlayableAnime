import 'package:flutter/material.dart';

import '../theme.dart';

/// How much in-world time a scene took, such as "+8 h", and when it ended, such as "Day 3, dusk"
/// (W10). When the player's own clock ran differently, as in stopped time, the server's
/// [personalLabel] ("World: +0 s. You: +40 s.") replaces the duration and the chip takes the
/// accent (W10a). An opening scene has no duration, only its [label].
class TimeChip extends StatelessWidget {
  const TimeChip({super.key, this.duration, this.label, this.personalLabel})
    : assert(duration != null || label != null || personalLabel != null);

  final String? duration;
  final String? label;
  final String? personalLabel;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final meta = context.lucidText.meta;
    final split = personalLabel != null;
    final foreground = split ? colors.onAccentSoft : colors.textSecondary;
    return Container(
      constraints: const BoxConstraints(minHeight: 30),
      padding: const EdgeInsets.fromLTRB(10, 5, 12, 5),
      decoration: ShapeDecoration(
        color: split ? colors.accentSoft : colors.veil,
        shape: StadiumBorder(
          side: BorderSide(color: split ? colors.accent.withValues(alpha: 0.34) : colors.hairline),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            split ? Icons.hourglass_top_rounded : Icons.schedule_rounded,
            size: 15,
            color: foreground,
          ),
          const SizedBox(width: 7),
          Flexible(
            child: Text.rich(
              TextSpan(
                children: [
                  if (personalLabel ?? duration case final lead?)
                    TextSpan(
                      text: lead,
                      style: TextStyle(color: split ? colors.onAccentSoft : colors.textPrimary),
                    ),
                  if (label case final label?) ...[
                    if (personalLabel != null || duration != null)
                      TextSpan(
                        text: '  ·  ',
                        style: TextStyle(color: foreground),
                      ),
                    TextSpan(text: label),
                  ],
                ],
              ),
              style: meta.copyWith(color: foreground),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
