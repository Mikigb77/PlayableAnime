import 'package:flutter/widgets.dart';

/// Quick, quiet motion: 150 to 250 ms, and none at all when the system asks to reduce motion.
abstract final class Motion {
  static const fast = Duration(milliseconds: 150);
  static const base = Duration(milliseconds: 200);
  static const slow = Duration(milliseconds: 250);

  /// How long freshly streamed narration takes to fade in.
  static const reveal = Duration(milliseconds: 220);

  /// One shimmer sweep across a skeleton or a pending picture.
  static const shimmer = Duration(milliseconds: 1400);

  static const standard = Curves.easeOutCubic;
  static const emphasized = Cubic(0.2, 0, 0, 1);
  static const exit = Curves.easeInCubic;

  /// True when the platform's reduce-motion (or disable-animations) setting is on.
  static bool reduced(BuildContext context) =>
      MediaQuery.maybeDisableAnimationsOf(context) ?? false;

  /// [duration], or zero when motion is reduced.
  static Duration of(BuildContext context, Duration duration) =>
      reduced(context) ? Duration.zero : duration;
}
