import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/config.dart';
import 'core/session/session_controller.dart';
import 'design/gallery/gallery_screen.dart';
import 'features/account/account_screen.dart';
import 'features/auth/welcome_screen.dart';
import 'features/create/create_story_screen.dart';
import 'features/discover/discover_screen.dart';
import 'features/library/library_screen.dart';
import 'features/story/memory_screen.dart';
import 'features/story/status_screen.dart';
import 'features/story/story_models.dart';
import 'features/story/story_screen.dart';
import 'home_shell.dart';

/// Route paths, so features link without spelling them out.
abstract final class Routes {
  static const splash = '/splash';
  static const welcome = '/welcome';
  static const discover = '/discover';
  static const library = '/library';
  static const account = '/account';
  static const create = '/create';
  static const gallery = '/gallery';

  static String story(String id) => '/story/$id';
  static String memory(String id) => '/story/$id/memory';
  static String status(String id) => '/story/$id/status';

  /// Reachable while signed out.
  static const _public = {splash, welcome, gallery};
}

/// Signed out: the welcome and sign-in screens (WS13). Signed in: the tabs (Discover, Library,
/// Account), the create flow, and the play screen with its memory and status pages.
final routerProvider = Provider<GoRouter>((ref) {
  final session = ValueNotifier(ref.read(sessionProvider));
  ref
    ..listen(sessionProvider, (_, next) => session.value = next)
    ..onDispose(session.dispose);

  final router = GoRouter(
    initialLocation: Routes.discover,
    refreshListenable: session,
    redirect: (context, state) {
      final status = session.value.status;
      final path = state.matchedLocation;
      if (status == SessionStatus.restoring) {
        return path == Routes.splash
            ? null
            : '${Routes.splash}?to=${Uri.encodeComponent(state.uri.toString())}';
      }
      final inApp = session.value.canEnterApp;
      if (!inApp && !Routes._public.contains(path)) return Routes.welcome;
      if (!inApp && path == Routes.splash) return Routes.welcome;
      if (inApp && (path == Routes.welcome || path == Routes.splash)) {
        final to = state.uri.queryParameters['to'];
        return to != null && to.startsWith('/') && !to.startsWith(Routes.splash)
            ? to
            : Routes.discover;
      }
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (_, _) => Routes.discover),
      GoRoute(path: Routes.splash, builder: (_, _) => const SizedBox.shrink()),
      GoRoute(path: Routes.welcome, builder: (_, _) => const WelcomeScreen()),
      if (AppConfig.showGallery)
        GoRoute(
          path: Routes.gallery,
          builder: (_, state) => GalleryScreen.fromQuery(state.uri.queryParameters),
        ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(
            routes: [GoRoute(path: Routes.discover, builder: (_, _) => const DiscoverScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: Routes.library, builder: (_, _) => const LibraryScreen())],
          ),
          StatefulShellBranch(
            routes: [GoRoute(path: Routes.account, builder: (_, _) => const AccountScreen())],
          ),
        ],
      ),
      GoRoute(
        path: Routes.create,
        builder: (_, state) => CreateStoryScreen(premise: _extra<Premise>(state)),
      ),
      GoRoute(
        path: '/story/:id',
        builder: (_, state) =>
            StoryScreen(storyId: state.pathParameters['id']!, initialStory: _extra<Story>(state)),
        routes: [
          GoRoute(
            path: 'memory',
            builder: (_, state) =>
                MemoryScreen(storyId: state.pathParameters['id']!, genre: _extra<String>(state)),
          ),
          GoRoute(
            path: 'status',
            builder: (_, state) =>
                StatusScreen(storyId: state.pathParameters['id']!, genre: _extra<String>(state)),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

/// A route's `extra` when it is a [T]. Extras are a shortcut only: a reload or a link drops them,
/// and every screen works without one.
T? _extra<T>(GoRouterState state) => switch (state.extra) {
  final T value => value,
  _ => null,
};
