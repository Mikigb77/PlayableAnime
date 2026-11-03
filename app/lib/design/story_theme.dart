import 'package:flutter/material.dart';

import 'accent.dart';
import 'motion.dart';
import 'theme.dart';

/// Tints everything below it with a story's genre accent, in the current brightness.
class StoryTheme extends StatelessWidget {
  const StoryTheme({super.key, required this.genre, required this.child});

  final String? genre;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    return AnimatedTheme(
      data: AppTheme.build(brightness, GenreAccent.forGenre(genre)),
      duration: Motion.of(context, Motion.slow),
      child: child,
    );
  }
}
