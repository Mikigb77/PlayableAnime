import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';

/// What the microphone button shows (V1, V5). The dictation controller in features/voice maps its
/// state to this; the button itself only draws.
enum MicVisual {
  /// Ready: tap to dictate.
  idle,

  /// Asking for permission or starting the recognizer.
  starting,

  /// The mic is on. It is on only while the button shows this (V5).
  listening,

  /// Permission was refused: tapping explains how to turn it on.
  denied,
}

class MicButton extends StatelessWidget {
  const MicButton({super.key, required this.visual, required this.onPressed, this.level = 0});

  final MicVisual visual;
  final VoidCallback? onPressed;

  /// The input level while listening, from 0 to 1, for the halo.
  final double level;

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    final l10n = context.l10n;
    final listening = visual == MicVisual.listening;
    final tooltip = switch (visual) {
      MicVisual.idle => l10n.micStart,
      MicVisual.starting => l10n.micStarting,
      MicVisual.listening => l10n.micStop,
      MicVisual.denied => l10n.micDeniedTitle,
    };
    final icon = switch (visual) {
      MicVisual.idle || MicVisual.starting => Icons.mic_none_rounded,
      MicVisual.listening => Icons.mic_rounded,
      MicVisual.denied => Icons.mic_off_outlined,
    };
    final halo = listening ? 1 + 0.35 * level.clamp(0, 1) : 1.0;
    return Semantics(
      button: true,
      toggled: listening,
      label: tooltip,
      excludeSemantics: true,
      child: Tooltip(
        message: tooltip,
        child: SizedBox.square(
          dimension: Layout.minTouch,
          child: Stack(
            alignment: Alignment.center,
            children: [
              if (listening)
                AnimatedScale(
                  scale: halo,
                  duration: Motion.of(context, Motion.fast),
                  child: Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: colors.accent.withValues(alpha: 0.22),
                    ),
                  ),
                ),
              AnimatedContainer(
                duration: Motion.of(context, Motion.fast),
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: listening ? colors.accent : Colors.transparent,
                ),
                child: Material(
                  type: MaterialType.transparency,
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: onPressed,
                    child: visual == MicVisual.starting
                        ? Padding(
                            padding: const EdgeInsets.all(11),
                            child: CircularProgressIndicator(strokeWidth: 2, color: colors.accent),
                          )
                        : Icon(
                            icon,
                            size: 22,
                            color: listening ? colors.onAccent : colors.textSecondary,
                          ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
