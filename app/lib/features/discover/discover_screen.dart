import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/l10n.dart';
import '../../design/design.dart';
import '../story/story_models.dart';
import '../story/story_repository.dart';

/// Starter premises, signature worlds first (S1), and a way to start from your own idea.
class DiscoverScreen extends ConsumerWidget {
  const DiscoverScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final l10n = context.l10n;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: AsyncValueView(
          value: ref.watch(premisesProvider),
          onRetry: () => ref.invalidate(premisesProvider),
          loading: (_) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ContentColumn(
                child: PageHeader(title: l10n.discoverTitle, subtitle: l10n.discoverSubtitle),
              ),
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
                  SliverToBoxAdapter(
                    child: ContentColumn(
                      child: PageHeader(title: l10n.discoverTitle, subtitle: l10n.discoverSubtitle),
                    ),
                  ),
                  if (signature.isNotEmpty) ...[
                    SliverToBoxAdapter(
                      child: ContentColumn(child: SectionLabel(l10n.discoverSignature)),
                    ),
                    _PremiseGrid(premises: signature, badge: l10n.discoverBadge),
                  ],
                  SliverToBoxAdapter(child: ContentColumn(child: _CreateYourOwn())),
                  if (more.isNotEmpty) ...[
                    SliverToBoxAdapter(
                      child: ContentColumn(child: SectionLabel(l10n.discoverMore)),
                    ),
                    _PremiseGrid(premises: more),
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

/// One column on phones, two from tablet width, within the content column.
class _PremiseGrid extends StatelessWidget {
  const _PremiseGrid({required this.premises, this.badge});

  final List<Premise> premises;
  final String? badge;

  @override
  Widget build(BuildContext context) {
    return SliverLayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.crossAxisExtent.clamp(0.0, Layout.contentWidth);
        final columns = width >= 640 ? 2 : 1;
        final side = (constraints.crossAxisExtent - width) / 2 + Space.gutter;
        return SliverPadding(
          padding: EdgeInsets.symmetric(horizontal: side),
          sliver: SliverGrid.builder(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: columns,
              mainAxisSpacing: Space.lg,
              crossAxisSpacing: Space.lg,
              mainAxisExtent: _cardHeight(context),
            ),
            itemCount: premises.length,
            itemBuilder: (context, i) {
              final premise = premises[i];
              return CoverCard(
                title: premise.title,
                genre: premise.genre,
                subtitle: premise.tagline ?? premise.premise,
                imageUrl: premise.coverUrl,
                badge: badge,
                height: 260,
                onTap: () => context.push('/create', extra: premise),
              );
            },
          ),
        );
      },
    );
  }

  static double _cardHeight(BuildContext context) {
    final scale = MediaQuery.textScalerOf(context).scale(1);
    return 260 * (scale > 1 ? 1 + (scale - 1) * 0.6 : 1);
  }
}

class _CreateYourOwn extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = context.lucid;
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xl, Space.gutter, 0),
      child: Card(
        color: colors.accentSoft,
        shape: RoundedRectangleBorder(
          borderRadius: Radii.card,
          side: BorderSide(color: colors.accent.withValues(alpha: 0.35)),
        ),
        child: InkWell(
          onTap: () => context.push('/create'),
          child: Padding(
            padding: const EdgeInsets.all(Space.gutter),
            child: Row(
              children: [
                Icon(Icons.auto_awesome_rounded, color: colors.onAccentSoft, size: 28),
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
                Icon(Icons.arrow_forward_rounded, color: colors.onAccentSoft),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
