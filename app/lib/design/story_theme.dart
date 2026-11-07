import 'package:flutter/material.dart';

import 'accent.dart';
import 'motion.dart';
import 'theme.dart';

/// Tints everything below it with a story's accent, in the current brightness: the color the
/// player chose for the story (S13), or else its genre's.
class StoryTheme extends StatelessWidget {
  StoryTheme({super.key, String? genre, String? chosen, required this.child})
    : accent = GenreAccent.of(genre: genre, chosen: chosen);

  /// Tints with an accent already worked out, such as the one a page above the story was handed.
  const StoryTheme.accent({super.key, required this.accent, required this.child});

  final GenreAccent accent;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    return AnimatedTheme(
      data: AppTheme.build(brightness, accent),
      duration: Motion.of(context, Motion.slow),
      child: child,
    );
  }
}
