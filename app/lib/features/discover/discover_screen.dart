import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../../router.dart';
import '../library/library.dart';
import '../library/library_screen.dart' show storyMeta;
import 'premises.dart';

/// The app's name and a headline in the night air, a way to start from your own idea, the way
/// back into the latest story when there is one to play on, then the starter premises: the
/// flagship worlds first and large (S1), and the others as a shelf of covers.
class DiscoverScreen extends ConsumerWidget {
  const DiscoverScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    final header = ContentColumn(
      child: PageHeader(
        brand: true,
        title: l10n.discoverHeadline,
        accentTitle: l10n.discoverHeadlineAccent,
      ),
    );
    // The first load waits for the stories too, so the story to continue doesn't push the worlds
    // down once they show. A failed or retried load of them never holds Discover up.
    final premises = ref.watch(premisesProvider);
    final stories = ref.watch(storiesProvider);
    final storiesFirstLoad = stories.isLoading && !stories.hasValue && !stories.hasError;
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(child: Ambient()),
          SafeArea(
            bottom: false,
            child: AsyncValueView(
              value: storiesFirstLoad ? const AsyncLoading<List<Premise>>() : premises,
              onRetry: () => ref.invalidate(premisesProvider),
              loading: (_) => Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  header,
                  const Expanded(child: ContentColumn(child: SkeletonList(imageHeight: 220))),
                ],
              ),
              builder: (premises) {
                final continuing = stories.value ?? const <StorySummary>[];
                final signature = premises.where((p) => p.flagship).toList();
                final more = premises.where((p) => !p.flagship).toList();
                return RefreshIndicator(
                  onRefresh: () {
                    ref.invalidate(storiesProvider);
                    return ref.refresh(premisesProvider.future);
                  },
                  child: CustomScrollView(
                    slivers: [
                      SliverToBoxAdapter(child: RiseIn(child: header)),
                      if (premises.isNotEmpty)
                        const SliverToBoxAdapter(
                          child: RiseIn(order: 1, child: ContentColumn(child: _CreateYourOwn())),
                        ),
                      SliverToBoxAdapter(
                        child: RiseIn(order: 2, child: _ContinueStory(stories: continuing)),
                      ),
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
                          child: RiseIn(
                            order: 3,
                            child: ContentColumn(child: SectionLabel(l10n.discoverSignature)),
                          ),
                        ),
                        _PremiseGrid(premises: signature),
                      ],
                      if (more.isNotEmpty) ...[
                        SliverToBoxAdapter(
                          child: ContentColumn(child: SectionLabel(l10n.discoverMore)),
                        ),
                        _PremiseGrid(premises: more, compact: true),
                      ],
                      const SliverToBoxAdapter(child: PageEnd()),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

/// The width inside the gutters from which the signature worlds go two across.
const _twoAcross = 600.0;

void _open(BuildContext context, Premise premise) =>
    context.push(Routes.createFrom(premise.id), extra: premise);

/// Large cards: on a phone a row to swipe through, with the next card peeking in, and two columns
/// from tablet width; or, [compact], a shelf of covers in their own 3:4 shape, two to four across.
class _PremiseGrid extends StatelessWidget {
  const _PremiseGrid({required this.premises, this.compact = false});

  final List<Premise> premises;
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
            : (inner >= _twoAcross ? 2 : 1);
        final side = (constraints.crossAxisExtent - width) / 2 + Space.gutter;
        if (columns == 1) {
          return SliverToBoxAdapter(
            child: _SignatureRow(premises: premises, side: side, inner: inner, height: 284 * grow),
          );
        }
        final tile = (inner - Space.lg * (columns - 1)) / columns;
        return SliverPadding(
          padding: EdgeInsets.symmetric(horizontal: side),
          sliver: SliverGrid.builder(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: columns,
              mainAxisSpacing: Space.lg,
              crossAxisSpacing: Space.lg,
              mainAxisExtent: compact ? tile * 4 / 3 * grow : 284 * grow,
            ),
            itemCount: premises.length,
            itemBuilder: (context, i) {
              final premise = premises[i];
              if (compact) {
                return _CompactCover(premise: premise, onTap: () => _open(context, premise));
              }
              return _SignatureCard(premise: premise);
            },
          ),
        );
      },
    );
  }
}

/// A signature world as a large card with its cover, genre, title and tagline.
class _SignatureCard extends StatelessWidget {
  const _SignatureCard({required this.premise});

  final Premise premise;

  @override
  Widget build(BuildContext context) => CoverCard(
    title: premise.title,
    genre: premise.genre,
    subtitle: premise.tagline ?? premise.premise,
    imageUrl: premise.coverUrl,
    onTap: () => _open(context, premise),
  );
}

/// The signature worlds on a phone: one large card at a time, lined up with the page's gutter,
/// with the next one peeking in so the row reads as one to swipe. A swipe settles on a card.
class _SignatureRow extends StatelessWidget {
  const _SignatureRow({
    required this.premises,
    required this.side,
    required this.inner,
    required this.height,
  });

  final List<Premise> premises;

  /// The page's gutter, where the first card starts.
  final double side;

  /// The width inside the gutters.
  final double inner;
  final double height;

  /// How much of the column a card takes when more follow, leaving room for the next to peek in.
  static const _share = 0.86;

  @override
  Widget build(BuildContext context) {
    final card = premises.length == 1 ? inner : inner * _share;
    return SizedBox(
      height: height,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: side),
        physics: _CardSnap(extent: card + 14),
        itemCount: premises.length,
        separatorBuilder: (_, _) => const SizedBox(width: 14),
        itemBuilder: (context, i) => SizedBox(
          width: card,
          child: _SignatureCard(premise: premises[i]),
        ),
      ),
    );
  }
}

/// Settles a swipe on a card's start, like a page view whose pages are [extent] wide, one card and
/// the gap after it. The row's last card settles at the end of the row instead.
class _CardSnap extends ScrollPhysics {
  const _CardSnap({required this.extent, super.parent});

  final double extent;

  @override
  _CardSnap applyTo(ScrollPhysics? ancestor) =>
      _CardSnap(extent: extent, parent: buildParent(ancestor));

  @override
  Simulation? createBallisticSimulation(ScrollMetrics position, double velocity) {
    if ((velocity <= 0 && position.pixels <= position.minScrollExtent) ||
        (velocity >= 0 && position.pixels >= position.maxScrollExtent)) {
      return super.createBallisticSimulation(position, velocity);
    }
    final tolerance = toleranceFor(position);
    var card = position.pixels / extent;
    if (velocity < -tolerance.velocity) {
      card -= 0.5;
    } else if (velocity > tolerance.velocity) {
      card += 0.5;
    }
    final target = (card.roundToDouble() * extent).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    if ((target - position.pixels).abs() < tolerance.distance) return null;
    return ScrollSpringSimulation(spring, position.pixels, target, velocity, tolerance: tolerance);
  }

  @override
  bool get allowImplicitScrolling => false;
}

/// A premise as a book on a shelf: its cover in its own 3:4 shape, the genre and title over the
/// scrim in its lower third (DESIGN.md, Pictures). Without a cover, a glow in the genre's accent.
class _CompactCover extends StatelessWidget {
  const _CompactCover({required this.premise, required this.onTap});

  final Premise premise;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
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
          color: Palette.inkSurface,
          child: InkWell(
            onTap: onTap,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (url == null)
                  fallback
                else
                  LayoutBuilder(
                    builder: (context, constraints) => CoverImage(
                      url: url,
                      cacheWidth: (constraints.maxWidth * dpr).round(),
                      fallback: fallback,
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
                        style: coverTitleStyle(18).copyWith(color: Palette.inkTextPrimary),
                      ),
                    ],
                  ),
                ),
                // A thin ring in the genre's accent, as on the large cards.
                Positioned.fill(
                  child: IgnorePointer(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        borderRadius: Radii.card,
                        border: Border.all(color: accent.withValues(alpha: 0.34)),
                      ),
                    ),
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

/// The way into a world of the player's own: a long pill in the accent, right under the
/// headline that promises it, with a lit round for its icon. It grows with the text size.
class _CreateYourOwn extends StatelessWidget {
  const _CreateYourOwn();

  static const _shape = RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(30)));

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    final dark = theme.brightness == Brightness.dark;
    final lit = dark ? colors.accentHi : colors.onAccentSoft;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.gutter, 2, Space.gutter, 0),
      child: Material(
        type: MaterialType.transparency,
        shape: _shape.copyWith(side: BorderSide(color: colors.accent.withValues(alpha: 0.42))),
        clipBehavior: Clip.antiAlias,
        child: Ink(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                colors.accent.withValues(alpha: dark ? 0.16 : 0.2),
                colors.accent.withValues(alpha: dark ? 0.05 : 0.08),
              ],
              stops: const [0, 0.6],
            ),
          ),
          child: InkWell(
            onTap: () => context.push(Routes.create),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 60),
              child: Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(9, 8, 10, 8),
                child: Row(
                  children: [
                    ExcludeSemantics(
                      child: Container(
                        width: 42,
                        height: 42,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: colors.accent.withValues(alpha: 0.16),
                          boxShadow: [
                            BoxShadow(color: colors.accent.withValues(alpha: 0.3), blurRadius: 22),
                          ],
                        ),
                        child: Icon(Icons.auto_awesome_rounded, color: lit, size: 21),
                      ),
                    ),
                    const SizedBox(width: Space.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            l10n.discoverCreateTitle,
                            style: theme.textTheme.titleMedium!.copyWith(fontSize: 15, height: 1.2),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            l10n.discoverCreateBody,
                            style: theme.textTheme.bodySmall!.copyWith(color: colors.textSecondary),
                          ),
                        ],
                      ),
                    ),
                    ExcludeSemantics(
                      child: SizedBox.square(
                        dimension: 40,
                        child: Icon(Icons.arrow_forward_rounded, color: lit, size: 21),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The latest story the player can play on, as its painted Library row with a lit way in, so
/// coming back to the app is one tap from where they left off. Nothing while the stories load,
/// when they fail to, or when none is left to play.
class _ContinueStory extends StatelessWidget {
  const _ContinueStory({required this.stories});

  /// The player's stories, as loaded so far.
  final List<StorySummary> stories;

  @override
  Widget build(BuildContext context) {
    // The server sends the most recently played first.
    final story = stories.where((s) => !s.ended).firstOrNull;
    if (story == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    return ContentColumn(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionLabel(l10n.discoverContinue),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Space.gutter),
            // As wide as a signature card below it: a row stretched across a wide screen reads
            // as a banner, not a story.
            child: LayoutBuilder(
              builder: (context, constraints) => Align(
                alignment: AlignmentDirectional.topStart,
                child: SizedBox(
                  width: constraints.maxWidth >= _twoAcross
                      ? (constraints.maxWidth - Space.lg) / 2
                      : constraints.maxWidth,
                  child: StoryTile(
                    key: const Key('discover.continue'),
                    title: story.title,
                    genre: story.genre,
                    accent: story.accent,
                    imageUrl: story.coverUrl,
                    meta: storyMeta(l10n, story),
                    onTap: () => context.push('/story/${Uri.encodeComponent(story.id)}'),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
