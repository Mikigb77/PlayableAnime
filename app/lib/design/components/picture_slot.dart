import 'package:flutter/material.dart';

import '../../core/l10n.dart';
import '../motion.dart';
import '../theme.dart';
import '../tokens.dart';
import 'skeleton.dart';

/// An image provider for a picture URL. `asset:` URLs (the fake API's) load bundled assets; anything
/// else loads over the network, decoded at no more than [cacheWidth] pixels wide to save memory.
ImageProvider appImage(String url, {int? cacheWidth}) {
  final ImageProvider provider = url.startsWith('asset:')
      ? AssetImage(url.substring('asset:'.length))
      : NetworkImage(url);
  return cacheWidth == null
      ? provider
      : ResizeImage(provider, width: cacheWidth, allowUpscaling: false);
}

/// Where a scene's picture is (docs/API.md `SceneImage.status`, plus the client's own loading).
enum PictureStatus {
  /// Planned or being generated: a shimmer holds its place.
  pending,

  /// Ready: the image fades in when it has loaded.
  ready,

  /// Skipped, blocked or failed: the slot quietly collapses and the scene is complete without it
  /// (M3). Never shown as an error.
  skipped,
}

/// A scene's picture: full-bleed, with a soft vignette, a shimmer while it is painted, a fade-in when
/// ready, and a quiet collapse when there is none.
class PictureSlot extends StatefulWidget {
  const PictureSlot({
    super.key,
    required this.status,
    this.url,
    this.aspectRatio = 16 / 9,
    this.alignment = Alignment.center,
    this.borderRadius = Radii.picture,
    this.semanticLabel,
    this.vignette = true,
    this.fadeInto,
    this.onTap,
    this.onError,
  });

  final PictureStatus status;
  final String? url;
  final double aspectRatio;

  /// Which part of a picture of another shape the slot keeps, such as [coverFocus] for a cover.
  final Alignment alignment;
  final BorderRadius borderRadius;

  /// What the picture shows, for screen readers.
  final String? semanticLabel;
  final bool vignette;

  /// The page's color, when the picture runs edge to edge: its foot fades into the page, so
  /// the picture is part of the page and not a box on it.
  final Color? fadeInto;
  final VoidCallback? onTap;

  /// Called once when a ready picture fails to load, such as a signed URL that expired. When set,
  /// the slot keeps its shimmer and waits for the owner to pass a fresh [url] or a skipped
  /// [status]; when null, the slot collapses quietly (M3).
  final VoidCallback? onError;

  @override
  State<PictureSlot> createState() => _PictureSlotState();
}

class _PictureSlotState extends State<PictureSlot> {
  bool _failed = false;

  /// The URL whose failure was reported to [PictureSlot.onError].
  String? _reported;

  /// The picture has faded in, so the shimmer under it can stop.
  bool _shown = false;

  @override
  void didUpdateWidget(PictureSlot old) {
    super.didUpdateWidget(old);
    if (old.url != widget.url) {
      _failed = _shown = false;
      _reported = null;
    }
  }

  void _markShown() {
    if (_shown) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && !_shown) setState(() => _shown = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    final collapsed = widget.status == PictureStatus.skipped || _failed;
    return AnimatedSize(
      duration: Motion.of(context, Motion.slow),
      curve: Motion.standard,
      alignment: Alignment.topCenter,
      child: collapsed ? const SizedBox(width: double.infinity) : _frame(context),
    );
  }

  Widget _frame(BuildContext context) {
    final url = widget.url;
    final ready = widget.status == PictureStatus.ready && url != null;
    return Semantics(
      image: true,
      label: ready ? widget.semanticLabel : context.l10n.picturePending,
      child: ClipRRect(
        borderRadius: widget.borderRadius,
        child: AspectRatio(
          aspectRatio: widget.aspectRatio,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final dpr = MediaQuery.devicePixelRatioOf(context);
              final cacheWidth = constraints.maxWidth.isFinite
                  ? (constraints.maxWidth * dpr).round()
                  : null;
              return Stack(
                fit: StackFit.expand,
                children: [
                  if (!ready || !_shown) const Shimmer(child: SkeletonBox(radius: 0)),
                  if (ready)
                    Image(
                      image: appImage(url, cacheWidth: cacheWidth),
                      fit: BoxFit.cover,
                      alignment: widget.alignment,
                      excludeFromSemantics: true,
                      frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
                        final fade = Motion.of(context, Motion.slow);
                        if (wasSynchronouslyLoaded || (frame != null && fade == Duration.zero)) {
                          _markShown();
                          return child;
                        }
                        return AnimatedOpacity(
                          opacity: frame == null ? 0 : 1,
                          duration: fade,
                          curve: Motion.standard,
                          onEnd: frame == null ? null : _markShown,
                          child: child,
                        );
                      },
                      errorBuilder: (context, error, stack) {
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (!mounted) return;
                          if (widget.onError case final onError?) {
                            if (_reported == widget.url) return;
                            _reported = widget.url;
                            onError();
                          } else if (!_failed) {
                            setState(() => _failed = true);
                          }
                        });
                        return const SizedBox.shrink();
                      },
                    ),
                  if (ready && widget.vignette) _Vignette(fadeInto: widget.fadeInto),
                  if (widget.onTap != null)
                    Material(
                      type: MaterialType.transparency,
                      child: InkWell(onTap: widget.onTap),
                    ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

/// Darkens the edges and the bottom, so a picture sits in the dark reading column like a film
/// still. With [fadeInto], the foot goes all the way into the page's color instead.
class _Vignette extends StatelessWidget {
  const _Vignette({this.fadeInto});

  final Color? fadeInto;

  @override
  Widget build(BuildContext context) {
    final edge = context.lucid.vignette;
    final foot = fadeInto;
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                radius: 1.05,
                colors: [edge.withValues(alpha: 0), edge.withValues(alpha: 0.42)],
                stops: const [0.62, 1],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: foot == null
                  ? LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [edge.withValues(alpha: 0), edge.withValues(alpha: 0.35)],
                      stops: const [0.6, 1],
                    )
                  : LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        foot.withValues(alpha: 0.4),
                        foot.withValues(alpha: 0),
                        foot.withValues(alpha: 0),
                        foot,
                      ],
                      stops: const [0, 0.16, 0.68, 1],
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
