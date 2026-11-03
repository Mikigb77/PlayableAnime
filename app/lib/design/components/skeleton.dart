import 'package:flutter/material.dart';

import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';

/// Sweeps a soft highlight across its child's shapes while content loads. Children are drawn in
/// the shimmer's base color; with reduce-motion on they stay still.
class Shimmer extends StatefulWidget {
  const Shimmer({super.key, required this.child});

  final Widget child;

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: Motion.shimmer);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (Motion.reduced(context)) {
      _controller.stop();
    } else if (!_controller.isAnimating) {
      _controller.repeat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.lucid;
    if (Motion.reduced(context)) return widget.child;
    return AnimatedBuilder(
      animation: _controller,
      child: widget.child,
      builder: (context, child) {
        final t = _controller.value;
        return ShaderMask(
          blendMode: BlendMode.srcATop,
          shaderCallback: (bounds) => LinearGradient(
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
            colors: [colors.shimmerBase, colors.shimmerHighlight, colors.shimmerBase],
            stops: const [0.35, 0.5, 0.65],
            transform: _SlideGradient(t),
          ).createShader(bounds),
          child: child,
        );
      },
    );
  }
}

class _SlideGradient extends GradientTransform {
  const _SlideGradient(this.t);

  final double t;

  @override
  Matrix4? transform(Rect bounds, {TextDirection? textDirection}) =>
      Matrix4.translationValues(bounds.width * (t * 2 - 1), 0, 0);
}

/// A placeholder block in the shimmer's base color.
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({super.key, this.width, this.height = 16, this.radius = Radii.sm});

  final double? width;
  final double height;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
    width: width,
    height: height,
    decoration: BoxDecoration(
      color: context.lucid.shimmerBase,
      borderRadius: BorderRadius.circular(radius),
    ),
  );
}

/// A few lines of placeholder text, the last one shorter.
class SkeletonText extends StatelessWidget {
  const SkeletonText({
    super.key,
    this.lines = 3,
    this.lineHeight = 12,
    this.spacing = 10,
    this.lastLineFactor = 0.6,
  });

  final int lines;
  final double lineHeight;
  final double spacing;
  final double lastLineFactor;

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.hasBoundedWidth ? constraints.maxWidth : 280.0;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < lines; i++) ...[
                if (i > 0) SizedBox(height: spacing),
                SkeletonBox(
                  width: i == lines - 1 && lines > 1 ? width * lastLineFactor : width,
                  height: lineHeight,
                  radius: lineHeight / 2,
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

/// A placeholder for a card in a list: an image block and two lines.
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key, this.imageHeight = 160});

  final double imageHeight;

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBox(height: imageHeight, radius: Radii.lg),
          const SizedBox(height: Space.md),
          const SkeletonBox(width: 90, height: 10, radius: 5),
          const SizedBox(height: Space.sm),
          const FractionallySizedBox(widthFactor: 0.7, child: SkeletonBox(height: 18, radius: 9)),
        ],
      ),
    );
  }
}

/// A placeholder list of [count] cards, for screens that are loading.
class SkeletonList extends StatelessWidget {
  const SkeletonList({super.key, this.count = 3, this.imageHeight = 160});

  final int count;
  final double imageHeight;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(Space.gutter),
      itemCount: count,
      separatorBuilder: (_, _) => const SizedBox(height: Space.xl),
      itemBuilder: (_, _) => SkeletonCard(imageHeight: imageHeight),
    );
  }
}
