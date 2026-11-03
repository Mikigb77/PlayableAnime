import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../theme.dart';
import 'picture_slot.dart';

/// A character's portrait (M4, M5), or their initials until a portrait exists.
class PortraitAvatar extends StatelessWidget {
  const PortraitAvatar({
    super.key,
    required this.name,
    this.url,
    this.size = 40,
    this.ring = false,
  });

  final String name;
  final String? url;
  final double size;

  /// An accent ring, for the player character or the speaker.
  final bool ring;

  static String initials(String name) {
    final words = name
        .split(RegExp(r'\s+'))
        .where((w) => w.isNotEmpty && w.toLowerCase() != 'the')
        .toList();
    if (words.isEmpty) return '?';
    final first = words.first.characters.first;
    final last = words.length > 1 ? words.last.characters.first : '';
    return (first + last).toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = context.lucid;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final url = this.url;
    final face = url == null
        ? Center(
            child: Text(
              initials(name),
              style: TextStyle(
                fontSize: size * 0.36,
                fontWeight: FontWeight.w600,
                color: colors.textSecondary,
                height: 1,
              ),
            ),
          )
        : Image(
            image: appImage(url, cacheWidth: (size * dpr).round()),
            fit: BoxFit.cover,
            // Portraits are 3:4, head and shoulders: keep the face in the circle.
            alignment: const Alignment(0, -0.4),
            width: size,
            height: size,
            excludeFromSemantics: true,
            errorBuilder: (_, _, _) => const SizedBox.shrink(),
          );
    return Semantics(
      label: context.l10n.portraitOf(name),
      image: true,
      child: Container(
        width: size,
        height: size,
        padding: EdgeInsets.all(ring ? 2 : 0),
        decoration: BoxDecoration(shape: BoxShape.circle, color: ring ? colors.accent : null),
        child: ClipOval(
          child: ColoredBox(color: scheme.surfaceContainerHighest, child: face),
        ),
      ),
    );
  }
}

/// A portrait and name, as listed on a scene.
class PortraitRef {
  const PortraitRef({required this.name, this.url});

  final String name;
  final String? url;
}

/// The known characters in a scene, overlapping, with "+N" past [max].
class PortraitStack extends StatelessWidget {
  const PortraitStack({super.key, required this.portraits, this.size = 28, this.max = 3});

  final List<PortraitRef> portraits;
  final double size;
  final int max;

  @override
  Widget build(BuildContext context) {
    if (portraits.isEmpty) return const SizedBox.shrink();
    final shown = portraits.take(max).toList();
    final extra = portraits.length - shown.length;
    final background = Theme.of(context).scaffoldBackgroundColor;
    final overlap = size * 0.32;
    final count = shown.length + (extra > 0 ? 1 : 0);
    return Semantics(
      label: portraits.map((p) => p.name).join(', '),
      excludeSemantics: true,
      child: SizedBox(
        height: size + 4,
        width: count * (size + 4) - (count - 1) * overlap,
        child: Stack(
          children: [
            for (final (i, p) in shown.indexed)
              Positioned(
                left: i * (size + 4 - overlap),
                child: _Ringed(
                  color: background,
                  child: PortraitAvatar(name: p.name, url: p.url, size: size),
                ),
              ),
            if (extra > 0)
              Positioned(
                left: shown.length * (size + 4 - overlap),
                child: _Ringed(
                  color: background,
                  child: CircleAvatar(
                    radius: size / 2,
                    backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: Text('+$extra', style: Theme.of(context).textTheme.labelSmall),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Ringed extends StatelessWidget {
  const _Ringed({required this.color, required this.child});

  final Color color;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(2),
    decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    child: child,
  );
}
