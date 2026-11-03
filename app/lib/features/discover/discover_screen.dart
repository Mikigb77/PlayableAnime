import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/async_value_view.dart';
import '../story/story_models.dart';
import '../story/story_repository.dart';

class DiscoverScreen extends ConsumerWidget {
  const DiscoverScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Discover')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/create'),
        icon: const Icon(Icons.auto_awesome),
        label: const Text('Create your own'),
      ),
      body: AsyncValueView(
        value: ref.watch(premisesProvider),
        onRetry: () => ref.invalidate(premisesProvider),
        builder: (premises) => ListView.separated(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
          itemCount: premises.length,
          separatorBuilder: (_, _) => const SizedBox(height: 12),
          itemBuilder: (_, i) => _PremiseCard(premise: premises[i]),
        ),
      ),
    );
  }
}

class _PremiseCard extends StatelessWidget {
  const _PremiseCard({required this.premise});

  final Premise premise;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => context.push('/create', extra: premise),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(premise.genre.toUpperCase(), style: theme.textTheme.labelSmall),
              const SizedBox(height: 4),
              Text(premise.title, style: theme.textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(premise.premise, maxLines: 4, overflow: TextOverflow.ellipsis),
            ],
          ),
        ),
      ),
    );
  }
}
