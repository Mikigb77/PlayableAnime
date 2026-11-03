import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/library/library.dart';
import 'package:playable_anime/features/story/story_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// A library whose deletes fail.
class _Undeletable extends LibraryRepository {
  _Undeletable(super.api);

  @override
  Future<void> delete(String id) async =>
      throw const ApiException(ApiErrorCode.network, message: 'offline');
}

/// The library (S8): your stories with their covers, the turn and the in-world time (W10), and a
/// delete that asks first.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  testWidgets('a story shows its cover, genre, turn and in-world time', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/library');
    final tile = tester.widget<StoryTile>(find.byType(StoryTile));
    expect(tile.title, 'The Ninth Peak');
    expect(tile.genre, 'Cultivation');
    expect(tile.imageUrl, isNotNull);
    expect(tile.meta, l10n.libraryMeta(3, 'Day 1, dawn'));

    await tester.tap(find.byType(StoryTile));
    await settle(tester, frames: 10);
    expect(find.byType(StoryScreen), findsOneWidget);
  });

  testWidgets('deleting asks first, then removes the story for good', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/library');

    await tester.tap(find.byTooltip(l10n.libraryOptions));
    await settle(tester);
    await tester.tap(find.text(l10n.libraryDelete));
    await settle(tester);
    expect(find.text(l10n.libraryDeleteTitle('The Ninth Peak')), findsOneWidget);
    await tester.tap(find.text(l10n.cancel));
    await settle(tester);
    expect(find.byType(StoryTile), findsOneWidget);
    expect(app.sent('DELETE', (_) => true), isEmpty);

    await tester.tap(find.byTooltip(l10n.libraryOptions));
    await settle(tester);
    await tester.tap(find.text(l10n.libraryDelete));
    await settle(tester);
    await tester.tap(find.text(l10n.libraryDeleteConfirm));
    await settle(tester, frames: 10);
    expect(app.sent('DELETE', (_) => true).single.uri.path, '/v1/stories/story_ninth_peak');
    expect(find.byType(StoryTile), findsNothing);
    expect(find.text(l10n.libraryDeleted('The Ninth Peak')), findsOneWidget);
    // Nothing left: the way back to Discover.
    expect(find.text(l10n.libraryEmptyTitle), findsOneWidget);
    expect(find.text(l10n.libraryEmptyAction), findsOneWidget);
  });

  testWidgets('a swipe deletes too, after the same question', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/library');
    await tester.drag(find.byType(StoryTile), const Offset(-500, 0));
    await settle(tester);
    expect(find.text(l10n.libraryDeleteTitle('The Ninth Peak')), findsOneWidget);
    await tester.tap(find.text(l10n.libraryDeleteConfirm));
    await settle(tester, frames: 10);
    expect(app.sent('DELETE', (_) => true), hasLength(1));
    expect(find.byType(StoryTile), findsNothing);
  });

  testWidgets('a failed delete puts the story back and says why', (tester) async {
    final app = AppHarness();
    await app.launch(
      tester,
      location: '/library',
      overrides: [
        libraryRepositoryProvider.overrideWith((ref) => _Undeletable(ref.watch(apiClientProvider))),
      ],
    );
    await tester.tap(find.byTooltip(l10n.libraryOptions));
    await settle(tester);
    await tester.tap(find.text(l10n.libraryDelete));
    await settle(tester);
    await tester.tap(find.text(l10n.libraryDeleteConfirm));
    await settle(tester, frames: 10);
    expect(find.byType(StoryTile), findsOneWidget);
    expect(find.textContaining(l10n.libraryDeleteFailed('The Ninth Peak', '')), findsOneWidget);
  });

  test('a story not yet begun says so', () {
    final story = StorySummary.fromJson(const {
      'id': 's',
      'title': 'T',
      'genre': 'Noir',
      'rating': 'teen',
      'turn': 0,
      'world_time_label': 'Day 1, dawn',
      'cover_url': null,
      'updated_at': '2026-11-03T10:00:00Z',
    });
    expect(story.turn, 0);
    expect(story.worldTimeLabel, 'Day 1, dawn');
    expect(story.coverUrl, isNull);
    expect(story.updatedAt, DateTime.utc(2026, 11, 3, 10));
  });
}
