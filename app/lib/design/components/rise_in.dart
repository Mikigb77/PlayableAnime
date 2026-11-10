import 'package:flutter/widgets.dart';

import '../motion.dart';

/// Lets a part of a page fade in and rise into place when it first shows. Parts with a higher
/// [order] start a little later, so a page arrives from the top down and a list cascades. With
/// the system's reduce-motion setting on, everything is simply there.
class RiseIn extends StatefulWidget {
  const RiseIn({super.key, required this.child, this.order = 0, this.duration = Motion.rise});

  final Widget child;

  /// Its place in the cascade, from 0.
  final int order;
  final Duration duration;

  @override
  State<RiseIn> createState() => _RiseInState();
}

class _RiseInState extends State<RiseIn> with SingleTickerProviderStateMixin {
  // The delay is part of the animation (an Interval), so no timer outlives the widget.
  late final _delay = Motion.riseStagger * widget.order;
  late final _controller = AnimationController(vsync: this, duration: widget.duration + _delay);
  late final _curve = CurvedAnimation(
    parent: _controller,
    curve: Interval(
      _delay.inMicroseconds / _controller.duration!.inMicroseconds,
      1,
      curve: Motion.emphasized,
    ),
  );
  late final _offset = Tween(begin: const Offset(0, 14), end: Offset.zero).animate(_curve);
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (Motion.reduced(context)) {
      _controller.value = 1;
    } else {
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _curve.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
    opacity: _curve,
    child: AnimatedBuilder(
      animation: _offset,
      child: widget.child,
      builder: (context, child) => Transform.translate(offset: _offset.value, child: child),
    ),
  );
}
