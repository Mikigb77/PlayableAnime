import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/async_value_view.dart';
import '../story/story_repository.dart';

class LibraryScreen extends ConsumerWidget {
  const LibraryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('Your stories')),
      body: AsyncValueView(
        value: ref.watch(storiesProvider),
        onRetry: () => ref.invalidate(storiesProvider),
        builder: (stories) => RefreshIndicator(
          onRefresh: () => ref.refresh(storiesProvider.future),
          child: stories.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(height: 120),
                    Center(child: Text('No stories yet. Pick a premise in Discover.')),
                  ],
                )
              : ListView.builder(
                  itemCount: stories.length,
                  itemBuilder: (_, i) {
                    final story = stories[i];
                    return ListTile(
                      title: Text(story.title),
                      subtitle: Text(story.premise, maxLines: 2, overflow: TextOverflow.ellipsis),
                      trailing: Text('Turn ${story.turn}'),
                      onTap: () => context.push('/story/${story.id}'),
                    );
                  },
                ),
        ),
      ),
    );
  }
}
