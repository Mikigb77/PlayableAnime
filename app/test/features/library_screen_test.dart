import 'package:flutter/widgets.dart';
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

  testWidgets('each row says where its story stands', (tester) async {
    StorySummary story(String id, int turn, {String? time, bool ended = false}) =>
        StorySummary(id: id, title: id, turn: turn, worldTimeLabel: time, ended: ended);
    final stories = [
      story('Playing', 3, time: 'Day 1, dawn'),
      story('Fresh', 0, time: 'Day 1, dawn'),
      story('Timeless', 5),
      story('Done', 12, time: 'Day 9, dusk', ended: true),
    ];
    final app = AppHarness();
    await app.launch(
      tester,
      location: '/library',
      overrides: [storiesProvider.overrideWith((ref) async => stories)],
    );
    final metas = [for (final t in tester.widgetList<StoryTile>(find.byType(StoryTile))) t.meta];
    expect(metas, [
      l10n.libraryMeta(3, 'Day 1, dawn'),
      l10n.libraryNotBegun('Day 1, dawn'),
      l10n.libraryTurn(5),
      l10n.libraryEnded(12),
    ]);
  });

  testWidgets('a wide screen shows the stories two across, never stretched', (tester) async {
    final stories = [
      for (final title in ['One', 'Two', 'Three'])
        StorySummary(id: title, title: title, turn: 2, worldTimeLabel: 'Day 1, dawn'),
    ];
    final app = AppHarness();
    await app.launch(
      tester,
      location: '/library',
      overrides: [storiesProvider.overrideWith((ref) async => stories)],
    );
    // One under another on a phone.
    Rect rect(String title) => tester.getRect(find.widgetWithText(StoryTile, title));
    expect(rect('Two').top, greaterThan(rect('One').bottom));
    expect(rect('One').width, 390 - Space.gutter * 2);

    usePhone(tester, size: const Size(1280, 900));
    await settle(tester);
    expect(rect('Two').top, rect('One').top);
    expect(rect('Two').height, rect('One').height);
    expect(rect('Two').left, greaterThan(rect('One').right));
    expect(rect('One').width, lessThan(Layout.contentWidth / 2));
    // An odd one out starts the next row, at the same width.
    expect(rect('Three').left, rect('One').left);
    expect(rect('Three').top, greaterThan(rect('One').bottom));
    expect(rect('Three').width, rect('One').width);
    expect(tester.takeException(), isNull);
  });

  testWidgets('two across still fits twice the text size', (tester) async {
    final stories = [
      for (final title in ['A story with a long name that wraps', 'Short'])
        StorySummary(
          id: title,
          title: title,
          genre: 'Many races and monsters',
          turn: 2,
          worldTimeLabel: 'Day 1, dawn',
        ),
    ];
    final app = AppHarness();
    await app.launch(
      tester,
      location: '/library',
      textScale: 2,
      overrides: [storiesProvider.overrideWith((ref) async => stories)],
    );
    usePhone(tester, size: const Size(1280, 900));
    await settle(tester);
    Rect rect(String title) => tester.getRect(find.widgetWithText(StoryTile, title));
    expect(rect('Short').top, rect('A story with a long name that wraps').top);
    expect(rect('Short').height, rect('A story with a long name that wraps').height);
    expect(tester.takeException(), isNull);
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

  test('a story at its ending says so', () {
    final story = StorySummary.fromJson(const {
      'id': 's',
      'title': 'T',
      'turn': 12,
      'ending': {'kind': 'death', 'character': 'Shen Yu', 'closed': true},
    });
    expect(story.ended, isTrue);
    expect(StorySummary.fromJson(const {'id': 's', 'title': 'T', 'turn': 1}).ended, isFalse);
  });
}
