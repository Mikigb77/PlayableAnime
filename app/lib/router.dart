import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/config.dart';
import 'core/session/session_controller.dart';
import 'design/gallery/gallery_screen.dart';
import 'features/account/account_screen.dart';
import 'features/account/credits_screen.dart';
import 'features/account/privacy_screen.dart';
import 'features/auth/welcome_screen.dart';
import 'features/create/create_story_screen.dart';
import 'features/discover/discover_screen.dart';
import 'features/discover/premises.dart';
import 'features/library/library_screen.dart';
import 'features/story/memory_screen.dart';
import 'features/story/status_screen.dart';
import 'features/story/story_models.dart';
import 'features/story/story_screen.dart';
import 'features/story/successor_screen.dart';
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
  static const credits = '/credits';
  static const privacy = '/privacy';

  /// A new story from a starter premise (S1).
  static String createFrom(String premiseId) =>
      '$create?premise=${Uri.encodeQueryComponent(premiseId)}';

  static String story(String id) => '/story/$id';
  static String memory(String id) => '/story/$id/memory';
  static String status(String id) => '/story/$id/status';

  /// Who carries a story on after its ending (N6).
  static String successor(String id) => '/story/$id/successor';

  /// Reachable while signed out.
  static const _public = {splash, welcome, gallery, privacy};
}

/// Signed out: the welcome and sign-in screens (WS13). Signed in: the tabs (Discover, Library,
/// Account), the create flow, and the play screen with its memory and status pages and, after an
/// ending, the person drawn to carry the story on.
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
      final to = _target(state);
      if (!session.value.canEnterApp) {
        // A link opened while signed out goes where it points when that is public, such as the
        // gallery; otherwise welcome keeps it for after sign-in.
        if (path == Routes.splash) {
          if (to != null && Routes._public.contains(Uri.parse(to).path)) return to;
          return to == null || to == Routes.discover
              ? Routes.welcome
              : '${Routes.welcome}?to=${Uri.encodeComponent(to)}';
        }
        return Routes._public.contains(path) ? null : Routes.welcome;
      }
      if (path == Routes.welcome || path == Routes.splash) return to ?? Routes.discover;
      return null;
    },
    routes: [
      GoRoute(path: '/', redirect: (_, _) => Routes.discover),
      GoRoute(path: Routes.splash, builder: (_, _) => const SizedBox.shrink()),
      GoRoute(path: Routes.welcome, builder: (_, _) => const WelcomeScreen()),
      GoRoute(path: Routes.privacy, builder: (_, _) => const PrivacyScreen()),
      GoRoute(path: Routes.credits, builder: (_, _) => const CreditsScreen()),
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
        builder: (_, state) => CreateStoryScreen(
          premise: _extra<Premise>(state),
          premiseId: state.uri.queryParameters['premise'],
          again: _extra<StartAgain>(state)?.premise,
        ),
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
          GoRoute(
            path: 'successor',
            builder: (_, state) =>
                SuccessorScreen(storyId: state.pathParameters['id']!, story: _extra<Story>(state)),
          ),
        ],
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});

/// The `to` a splash or welcome location carries: where the player was going. Only a path inside
/// the app, and never back to the splash or welcome screens.
String? _target(GoRouterState state) {
  final to = state.uri.queryParameters['to'];
  if (to == null || !to.startsWith('/') || to.startsWith('//')) return null;
  final path = Uri.tryParse(to)?.path;
  return path == null || path == Routes.splash || path == Routes.welcome ? null : to;
}

/// A route's `extra` when it is a [T]. Extras are a shortcut only: a reload or a link drops them,
/// and every screen works without one.
T? _extra<T>(GoRouterState state) => switch (state.extra) {
  final T value => value,
  _ => null,
};
