import 'package:flutter/material.dart';

import '../accent.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';
import '../typography.dart';
import 'picture_slot.dart';
import 'pills.dart';

/// A story or premise with its cover: the picture, a deep scrim, and the genre, title and line set
/// over it, inside a thin ring of the genre's accent. Without a cover, a glow in the accent
/// stands in.
class CoverCard extends StatelessWidget {
  const CoverCard({
    super.key,
    required this.title,
    required this.genre,
    this.subtitle,
    this.imageUrl,
    this.badge,
    this.onTap,
    this.height = 284,
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
        borderRadius: Radii.cover,
        child: Material(
          color: Palette.inkSurface,
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
                  const DecoratedBox(decoration: BoxDecoration(gradient: _coverScrim)),
                  if (badge case final badge?)
                    Positioned(
                      top: Space.lg,
                      left: Space.lg,
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
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: context.lucidText.overline.copyWith(color: accent),
                          ),
                          const SizedBox(height: 6),
                        ],
                        Text(
                          title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: coverTitleStyle(23).copyWith(color: ink),
                        ),
                        if (subtitle case final subtitle?) ...[
                          const SizedBox(height: 6),
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
                  _Ring(color: accent.withValues(alpha: 0.42)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The scrim under a cover's words: clear over the picture's focal point, then down into ink.
const _coverScrim = LinearGradient(
  begin: Alignment.topCenter,
  end: Alignment.bottomCenter,
  colors: [Color(0x000B0D12), Color(0xB80B0D12), Color(0xF70B0D12)],
  stops: [0.34, 0.64, 1],
);

/// A story's or a world's name on its cover: the reading serif, heavy enough to hold on a
/// painting.
TextStyle coverTitleStyle(double size) => TextStyle(
  fontFamily: Fonts.serif,
  fontWeight: FontWeight.w600,
  fontSize: size,
  height: 1.17,
  letterSpacing: -0.1,
);

/// A thin ring just inside a painted card's edge, drawn over the picture.
class _Ring extends StatelessWidget {
  const _Ring({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) => Positioned.fill(
    child: IgnorePointer(
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: Radii.cover,
          border: Border.all(color: color),
        ),
      ),
    ),
  );
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

/// A story to go back into, in the Library and at the top of Discover: a painted card with the
/// story's cover running off its far side under a shade, the genre, the title and where the
/// story stands, inside a thin ring of the story's accent. It is night ink in both themes, like a
/// cover, so give [trailing] light colors.
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

  /// What ends the row, such as the Library's menu. By default, a lit bead with an arrow: the
  /// way in.
  final Widget? trailing;

  static const _ink = Color(0xFF12151D);

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final family = GenreAccent.of(genre: genre, chosen: this.accent);
    final accent = accentFor(family, Brightness.dark);
    final fallback = _Fallback(accent: accent);
    final url = imageUrl;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: Radii.cover,
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF000000).withValues(alpha: dark ? 0.35 : 0.16),
            blurRadius: 32,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: Radii.cover,
        child: Material(
          color: _ink,
          child: InkWell(
            onTap: onTap,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 104),
              child: Stack(
                alignment: AlignmentDirectional.centerStart,
                children: [
                  Positioned.fill(
                    child: FractionallySizedBox(
                      alignment: AlignmentDirectional.centerEnd,
                      widthFactor: 0.66,
                      child: url == null
                          ? fallback
                          : CoverImage(
                              url: url,
                              // No wider than the screen's own share, whatever the row's width.
                              cacheWidth:
                                  (MediaQuery.sizeOf(context).width *
                                          0.66 *
                                          MediaQuery.devicePixelRatioOf(context))
                                      .round(),
                              fallback: fallback,
                            ),
                    ),
                  ),
                  // The picture comes out of the ink where the words end.
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: AlignmentDirectional.centerStart,
                          end: AlignmentDirectional.centerEnd,
                          colors: [
                            _ink,
                            _ink.withValues(alpha: 0.82),
                            _ink.withValues(alpha: 0.08),
                          ],
                          stops: const [0.3, 0.5, 1],
                        ),
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(Space.gutter, 16, 12, 16),
                    child: Row(
                      children: [
                        Expanded(
                          // As tall as the room it is given, so two tiles side by side match
                          // the taller one.
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              if (genre.isNotEmpty) ...[
                                Text(
                                  genre.toUpperCase(),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: context.lucidText.overline.copyWith(color: accent),
                                ),
                                const SizedBox(height: 6),
                              ],
                              Text(
                                title,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: coverTitleStyle(21).copyWith(color: Palette.inkTextPrimary),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                meta,
                                style: context.lucidText.meta.copyWith(
                                  fontSize: 13,
                                  color: Palette.inkTextSecondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: Space.sm),
                        trailing ??
                            Padding(
                              padding: const EdgeInsetsDirectional.only(end: 4),
                              // The bead wears the story's color as the night theme shows it.
                              child: Theme(
                                data: AppTheme.dark(family),
                                child: const AccentOrb(icon: Icons.arrow_forward_rounded),
                              ),
                            ),
                      ],
                    ),
                  ),
                  _Ring(color: accent.withValues(alpha: 0.3)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
