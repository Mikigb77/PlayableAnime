import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'features/create/create_story_screen.dart';
import 'features/discover/discover_screen.dart';
import 'features/library/library_screen.dart';
import 'features/settings/settings_screen.dart';
import 'features/story/memory_screen.dart';
import 'features/story/story_models.dart';
import 'features/story/story_screen.dart';
import 'home_shell.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    routes: [
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: '/', builder: (_, _) => const DiscoverScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/library', builder: (_, _) => const LibraryScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: '/settings', builder: (_, _) => const SettingsScreen())],
          ),
        ],
      ),
      GoRoute(
        path: '/create',
        builder: (_, state) => CreateStoryScreen(premise: state.extra as Premise?),
      ),
      GoRoute(
        path: '/story/:id',
        builder: (_, state) =>
            StoryScreen(storyId: state.pathParameters['id']!, initialStory: state.extra as Story?),
        routes: [
          GoRoute(
            path: 'memory',
            builder: (_, state) => MemoryScreen(storyId: state.pathParameters['id']!),
          ),
        ],
      ),
    ],
  );
});
