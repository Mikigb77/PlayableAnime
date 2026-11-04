import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../../router.dart';
import 'premises.dart';

/// Starter premises, the flagship worlds first and large (S1), a way to start from your own idea,
/// then the other worlds as a shelf of covers.
class DiscoverScreen extends ConsumerWidget {
  const DiscoverScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final header = ContentColumn(
      child: PageHeader(title: l10n.discoverTitle, subtitle: l10n.discoverSubtitle),
    );
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: AsyncValueView(
          value: ref.watch(premisesProvider),
          onRetry: () => ref.invalidate(premisesProvider),
          loading: (_) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              header,
              const Expanded(child: ContentColumn(child: SkeletonList(imageHeight: 220))),
            ],
          ),
          builder: (premises) {
            final signature = premises.where((p) => p.flagship).toList();
            final more = premises.where((p) => !p.flagship).toList();
            return RefreshIndicator(
              onRefresh: () => ref.refresh(premisesProvider.future),
              child: CustomScrollView(
                slivers: [
                  SliverToBoxAdapter(child: header),
                  if (premises.isEmpty)
                    SliverToBoxAdapter(
                      child: EmptyState(
                        icon: Icons.explore_outlined,
                        title: l10n.discoverEmptyTitle,
                        message: l10n.discoverEmptyBody,
                        actionLabel: l10n.discoverCreateAction,
                        onAction: () => context.push(Routes.create),
                      ),
                    ),
                  if (signature.isNotEmpty) ...[
                    SliverToBoxAdapter(
                      child: ContentColumn(child: SectionLabel(l10n.discoverSignature)),
                    ),
                    _PremiseGrid(premises: signature, badge: l10n.discoverBadge),
                  ],
                  if (premises.isNotEmpty)
                    const SliverToBoxAdapter(child: ContentColumn(child: _CreateYourOwn())),
                  if (more.isNotEmpty) ...[
                    SliverToBoxAdapter(
                      child: ContentColumn(child: SectionLabel(l10n.discoverMore)),
                    ),
                    _PremiseGrid(premises: more, compact: true),
                  ],
                  const SliverToBoxAdapter(child: SizedBox(height: Space.xxxl)),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

void _open(BuildContext context, Premise premise) =>
    context.push(Routes.createFrom(premise.id), extra: premise);

/// Large cards, one column on phones and two from tablet width; or, [compact], a shelf of covers
/// in their own 3:4 shape, two to four across.
class _PremiseGrid extends StatelessWidget {
  const _PremiseGrid({required this.premises, this.badge, this.compact = false});

  final List<Premise> premises;
  final String? badge;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.textScalerOf(context).scale(1);
    // Cards grow with the text size, so large type never clips.
    final grow = scale > 1 ? 1 + (scale - 1) * 0.6 : 1.0;
    return SliverLayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.crossAxisExtent.clamp(0.0, Layout.contentWidth);
        final inner = width - Space.gutter * 2;
        final columns = compact
            ? (inner >= 760
                  ? 4
                  : inner >= 520
                  ? 3
                  : 2)
            : (inner >= 600 ? 2 : 1);
        final side = (constraints.crossAxisExtent - width) / 2 + Space.gutter;
        final tile = (inner - Space.lg * (columns - 1)) / columns;
        return SliverPadding(
          padding: EdgeInsets.symmetric(horizontal: side),
          sliver: SliverGrid.builder(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: columns,
              mainAxisSpacing: Space.lg,
              crossAxisSpacing: Space.lg,
              mainAxisExtent: compact ? tile * 4 / 3 * grow : 260 * grow,
            ),
            itemCount: premises.length,
            itemBuilder: (context, i) {
              final premise = premises[i];
              if (compact) {
                return _CompactCover(premise: premise, onTap: () => _open(context, premise));
              }
              return CoverCard(
                title: premise.title,
                genre: premise.genre,
                subtitle: premise.tagline ?? premise.premise,
                imageUrl: premise.coverUrl,
                badge: badge,
                onTap: () => _open(context, premise),
              );
            },
          ),
        );
      },
    );
  }
}

/// A premise as a book on a shelf: its cover in its own 3:4 shape, the genre and title over the
/// scrim in its lower third (DESIGN.md, Pictures). Without a cover, a glow in the genre's accent.
class _CompactCover extends StatelessWidget {
  const _CompactCover({required this.premise, required this.onTap});

  final Premise premise;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = accentFor(GenreAccent.forGenre(premise.genre), Brightness.dark);
    final url = premise.coverUrl;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(0.4, -0.5),
          radius: 1.2,
          colors: [blend(Palette.inkContainer, accent, 0.5), Palette.inkBackground],
        ),
      ),
    );
    return Semantics(
      button: true,
      label: [
        if (premise.genre.isNotEmpty) premise.genre,
        premise.title,
        ?premise.tagline,
      ].join('. '),
      excludeSemantics: true,
      child: ClipRRect(
        borderRadius: Radii.card,
        child: Material(
          color: Palette.inkContainer,
          child: InkWell(
            onTap: onTap,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (url == null)
                  fallback
                else
                  LayoutBuilder(
                    builder: (context, constraints) => Image(
                      image: appImage(url, cacheWidth: (constraints.maxWidth * dpr).round()),
                      fit: BoxFit.cover,
                      excludeFromSemantics: true,
                      // Fades in over the glow as it arrives, like the signature cards' covers.
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
                    ),
                  ),
                DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Palette.inkBackground.withValues(alpha: 0),
                        Palette.inkBackground.withValues(alpha: 0.7),
                        Palette.inkBackground.withValues(alpha: 0.96),
                      ],
                      stops: const [0.3, 0.62, 1],
                    ),
                  ),
                ),
                Positioned(
                  left: Space.md,
                  right: Space.md,
                  bottom: Space.md,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (premise.genre.isNotEmpty) ...[
                        Text(
                          premise.genre.toUpperCase(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: context.lucidText.overline.copyWith(color: accent),
                        ),
                        const SizedBox(height: Space.xs),
                      ],
                      Text(
                        premise.title,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleLarge!.copyWith(
                          fontFamily: theme.textTheme.headlineSmall!.fontFamily,
                          fontWeight: FontWeight.w500,
                          height: 1.2,
                          color: Palette.inkTextPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CreateYourOwn extends StatelessWidget {
  const _CreateYourOwn();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, 0),
      child: Card(
        margin: EdgeInsets.zero,
        color: colors.accentSoft,
        shape: RoundedRectangleBorder(
          borderRadius: Radii.card,
          side: BorderSide(color: colors.accent.withValues(alpha: 0.35)),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => context.push(Routes.create),
          child: Padding(
            padding: const EdgeInsets.all(Space.gutter),
            child: Row(
              children: [
                ExcludeSemantics(
                  child: Icon(Icons.auto_awesome_rounded, color: colors.onAccentSoft, size: 28),
                ),
                const SizedBox(width: Space.lg),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.discoverCreateTitle, style: theme.textTheme.titleMedium),
                      const SizedBox(height: Space.xs),
                      Text(
                        l10n.discoverCreateBody,
                        style: theme.textTheme.bodyMedium!.copyWith(color: colors.textSecondary),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: Space.sm),
                ExcludeSemantics(
                  child: Icon(Icons.arrow_forward_rounded, color: colors.onAccentSoft),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
