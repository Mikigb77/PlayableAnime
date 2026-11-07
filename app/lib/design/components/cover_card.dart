import 'package:flutter/material.dart';

import '../accent.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';
import 'picture_slot.dart';

/// A story or premise with its cover: the picture, a deep scrim, and the genre, title and line set
/// over it, tinted with the genre's accent. Without a cover, a gradient in the accent stands in.
class CoverCard extends StatelessWidget {
  const CoverCard({
    super.key,
    required this.title,
    required this.genre,
    this.subtitle,
    this.imageUrl,
    this.badge,
    this.onTap,
    this.height = 260,
  });

  final String title;
  final String genre;
  final String? subtitle;
  final String? imageUrl;

  /// A small label in the top corner, such as "Signature".
  final String? badge;
  final VoidCallback? onTap;
  final double height;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final family = GenreAccent.forGenre(genre);
    // Text sits on the dark scrim in both themes, so it uses the dark-theme tones.
    final accent = accentFor(family, Brightness.dark);
    const ink = Palette.inkTextPrimary;
    final url = imageUrl;
    final scale = MediaQuery.textScalerOf(context).scale(1);

    return Semantics(
      button: onTap != null,
      label: [if (genre.isNotEmpty) genre, title, ?subtitle].join('. '),
      excludeSemantics: true,
      child: ClipRRect(
        borderRadius: Radii.card,
        child: Material(
          color: Palette.inkContainer,
          child: InkWell(
            onTap: onTap,
            child: SizedBox(
              // Grows with the text size, so large type never clips.
              height: height * (scale > 1 ? 1 + (scale - 1) * 0.6 : 1),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (url != null)
                    CoverImage(
                      url: url,
                      cacheWidth:
                          (MediaQuery.sizeOf(context).width *
                                  MediaQuery.devicePixelRatioOf(context))
                              .round(),
                      fallback: _Fallback(accent: accent),
                    )
                  else
                    _Fallback(accent: accent),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Palette.inkBackground.withValues(alpha: 0),
                          Palette.inkBackground.withValues(alpha: 0.55),
                          Palette.inkBackground.withValues(alpha: 0.94),
                        ],
                        stops: const [0.15, 0.5, 1],
                      ),
                    ),
                  ),
                  if (badge case final badge?)
                    Positioned(
                      top: Space.md,
                      left: Space.md,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: Palette.inkBackground.withValues(alpha: 0.72),
                          borderRadius: BorderRadius.circular(Radii.pill),
                          border: Border.all(color: accent.withValues(alpha: 0.6)),
                        ),
                        child: Text(
                          badge.toUpperCase(),
                          style: context.lucidText.overline.copyWith(color: accent),
                        ),
                      ),
                    ),
                  Positioned(
                    left: Space.gutter,
                    right: Space.gutter,
                    bottom: Space.gutter,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (genre.isNotEmpty) ...[
                          Text(
                            genre.toUpperCase(),
                            style: context.lucidText.overline.copyWith(color: accent),
                          ),
                          const SizedBox(height: Space.xs),
                        ],
                        Text(
                          title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.headlineMedium!.copyWith(color: ink),
                        ),
                        if (subtitle case final subtitle?) ...[
                          const SizedBox(height: Space.xs),
                          Text(
                            subtitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodyMedium!.copyWith(
                              color: Palette.inkTextSecondary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Where a tall 3:4 cover sits in a wider slot: its upper part, where the picture keeps its focal
/// point, since the lower third is calm space for the title (DESIGN.md, Pictures).
const coverFocus = Alignment(0, -0.5);

/// A cover filling its slot: [fallback] holds the place until the picture fades in over it, and
/// stays when the picture fails, such as a signed URL that has expired.
class CoverImage extends StatelessWidget {
  const CoverImage({super.key, required this.url, required this.fallback, this.cacheWidth});

  final String url;
  final Widget fallback;
  final int? cacheWidth;

  @override
  Widget build(BuildContext context) => Image(
    image: appImage(url, cacheWidth: cacheWidth),
    fit: BoxFit.cover,
    alignment: coverFocus,
    excludeFromSemantics: true,
    frameBuilder: (context, child, frame, sync) => sync
        ? child
        : Stack(
            fit: StackFit.expand,
            children: [
              fallback,
              AnimatedOpacity(
                opacity: frame == null ? 0 : 1,
                duration: Motion.of(context, Motion.slow),
                child: child,
              ),
            ],
          ),
    errorBuilder: (_, _, _) => fallback,
  );
}

class _Fallback extends StatelessWidget {
  const _Fallback({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      gradient: RadialGradient(
        center: const Alignment(0.6, -0.6),
        radius: 1.3,
        colors: [blend(Palette.inkContainer, accent, 0.45), Palette.inkBackground],
      ),
    ),
  );
}

/// A story in the library: a small cover, the genre, the title and where the story stands.
class StoryTile extends StatelessWidget {
  const StoryTile({
    super.key,
    required this.title,
    required this.genre,
    required this.meta,
    this.accent,
    this.imageUrl,
    this.onTap,
    this.trailing,
  });

  final String title;
  final String genre;

  /// The color the player chose for the story (S13), an accent's name, or null for its genre's.
  final String? accent;

  /// Such as "Turn 12 · Day 3, dusk".
  final String meta;
  final String? imageUrl;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final family = GenreAccent.of(genre: genre, chosen: this.accent);
    final accent = accentFor(family, theme.brightness);
    // The thumbnail's stand-in sits on dark ink in both themes, like a cover's.
    final fallback = _Fallback(accent: accentFor(family, Brightness.dark));
    final url = imageUrl;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(Space.md),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(Radii.md),
                child: SizedBox(
                  width: 64,
                  height: 80,
                  child: url == null
                      ? fallback
                      : Image(
                          image: appImage(url, cacheWidth: (64 * dpr).round()),
                          fit: BoxFit.cover,
                          excludeFromSemantics: true,
                          errorBuilder: (_, _, _) => fallback,
                        ),
                ),
              ),
              const SizedBox(width: Space.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (genre.isNotEmpty) ...[
                      Text(
                        genre.toUpperCase(),
                        style: context.lucidText.overline.copyWith(color: accent),
                      ),
                      const SizedBox(height: Space.xs),
                    ],
                    Text(title, style: theme.textTheme.titleMedium),
                    const SizedBox(height: Space.xs),
                    Text(meta, style: context.lucidText.meta.copyWith(color: colors.textSecondary)),
                  ],
                ),
              ),
              trailing ?? Icon(Icons.chevron_right_rounded, color: colors.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}
