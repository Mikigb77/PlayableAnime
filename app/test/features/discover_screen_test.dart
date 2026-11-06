import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/fake/fake_premises.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/create/create_story_screen.dart';
import 'package:playable_anime/features/discover/premises.dart';
import 'package:playable_anime/features/library/library.dart';
import 'package:playable_anime/features/story/story_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// Discover: the way back into the latest story, the signature worlds first and large, a way to
/// start from your own idea, then the other worlds as a shelf of covers (S1).
void main() {
  testWidgets('the signature worlds come first, with their covers', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();

    expect(find.text(l10n.discoverSignature.toUpperCase()), findsOneWidget);
    final cards = tester.widgetList<CoverCard>(find.byType(CoverCard)).toList();
    expect(cards.first.title, 'The Last Outer Disciple');
    // The heading says they are the signature worlds; the cards don't say it again.
    expect(cards.every((c) => c.badge == null), isTrue);
    expect(cards.first.imageUrl, isNotNull);

    // Then your own idea, then the shelf of the other worlds. Small steps, so a scroll never
    // jumps past the shelf's label while it is built.
    final scroll = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(find.text(l10n.discoverCreateTitle), 100, scrollable: scroll);
    await tester.scrollUntilVisible(
      find.text(l10n.discoverMore.toUpperCase()),
      100,
      scrollable: scroll,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('on a phone the signature worlds are a row to swipe, so the rest stays close', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();
    final screen = tester.view.physicalSize.width;

    // One card at a time, lined up with the page's gutter, with the next one peeking in.
    final first = tester.getRect(find.widgetWithText(CoverCard, 'The Last Outer Disciple'));
    final second = tester.getRect(find.widgetWithText(CoverCard, 'Squire of the Ashen Crown'));
    expect(first.left, Space.gutter);
    expect(second.top, first.top);
    expect(second.left, lessThan(screen));
    expect(screen - second.left, greaterThan(Space.xl));

    // Your own idea comes right after the row, without scrolling past every signature world.
    expect(tester.getTopLeft(find.text(l10n.discoverCreateTitle)).dy, lessThan(844));

    // A swipe settles on the next card, at the gutter.
    final row = find
        .ancestor(of: find.byType(CoverCard).first, matching: find.byType(Scrollable))
        .first;
    await tester.fling(row, const Offset(-120, 0), 800);
    await settle(tester, frames: 30);
    final settled = tester.getRect(find.widgetWithText(CoverCard, 'Squire of the Ashen Crown'));
    expect(settled.left, moreOrLessEquals(Space.gutter, epsilon: 0.5));
    expect(tester.takeException(), isNull);
  });

  testWidgets('on a wide screen the signature worlds are two across', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    usePhone(tester, size: const Size(1280, 900));
    await settle(tester);

    final first = tester.getRect(find.widgetWithText(CoverCard, 'The Last Outer Disciple'));
    final second = tester.getRect(find.widgetWithText(CoverCard, 'Squire of the Ashen Crown'));
    expect(second.top, first.top);
    expect(second.width, first.width);
    expect(first.width, lessThan(Layout.contentWidth / 2));
    // The story to continue is as wide as a card under it, not a banner across the screen.
    final story = tester.getRect(find.byKey(const Key('discover.continue')));
    expect(story.left, first.left);
    expect(story.width, first.width);
    expect(
      find.ancestor(of: find.byType(CoverCard).first, matching: find.byType(ListView)),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('the latest story comes first, one tap from where you left off', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();

    expect(find.text(l10n.discoverContinue.toUpperCase()), findsOneWidget);
    final tile = tester.widget<StoryTile>(find.byKey(const Key('discover.continue')));
    expect(tile.title, 'The Ninth Peak');
    expect(tile.meta, l10n.libraryMeta(3, 'Day 1, dawn'));
    // Above the signature worlds.
    expect(
      tester.getTopLeft(find.byKey(const Key('discover.continue'))).dy,
      lessThan(tester.getTopLeft(find.text(l10n.discoverSignature.toUpperCase())).dy),
    );

    await tester.tap(find.byKey(const Key('discover.continue')));
    await settle(tester, frames: 10);
    expect(find.byType(StoryScreen), findsOneWidget);
    expect(app.location(tester), '/story/story_ninth_peak');
  });

  testWidgets('the latest story you can still play is the one offered', (tester) async {
    StorySummary story(String id, {bool ended = false}) =>
        StorySummary(id: id, title: id, turn: 4, worldTimeLabel: 'Day 2, noon', ended: ended);
    final app = AppHarness();
    await app.launch(
      tester,
      overrides: [
        storiesProvider.overrideWith(
          (ref) async => [story('Ended', ended: true), story('Older'), story('Oldest')],
        ),
      ],
    );
    expect(tester.widget<StoryTile>(find.byKey(const Key('discover.continue'))).title, 'Older');
  });

  testWidgets('the first load waits for your stories, so nothing jumps when they come', (
    tester,
  ) async {
    final stories = Completer<List<StorySummary>>();
    final app = AppHarness();
    await app.launch(tester, overrides: [storiesProvider.overrideWith((ref) => stories.future)]);
    final l10n = await english();
    expect(find.text(l10n.discoverSignature.toUpperCase()), findsNothing);
    expect(find.byType(SkeletonList), findsOneWidget);

    stories.complete(const [StorySummary(id: 's', title: 'Waiting', turn: 1)]);
    await settle(tester);
    expect(find.text(l10n.discoverSignature.toUpperCase()), findsOneWidget);
    expect(tester.widget<StoryTile>(find.byKey(const Key('discover.continue'))).title, 'Waiting');
  });

  testWidgets('nothing to continue: no stories, only ended ones, or a failed load', (tester) async {
    final l10n = await english();
    for (final stories in <Future<List<StorySummary>> Function()>[
      () async => const [],
      () async => const [StorySummary(id: 'a', title: 'Done', turn: 9, ended: true)],
      () async => throw const ApiException(ApiErrorCode.network, message: 'offline'),
    ]) {
      final app = AppHarness();
      await app.launch(tester, overrides: [storiesProvider.overrideWith((ref) => stories())]);
      expect(find.byKey(const Key('discover.continue')), findsNothing);
      expect(find.text(l10n.discoverContinue.toUpperCase()), findsNothing);
      // Discover itself is all there.
      expect(find.text(l10n.discoverSignature.toUpperCase()), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('a world opens its create page with its premise ready', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();

    await tester.tap(find.text('The Last Outer Disciple'));
    await settle(tester, frames: 10);
    expect(find.byType(CreateStoryScreen), findsOneWidget);
    expect(app.location(tester), '/create?premise=outer-disciple');
    expect(find.text(l10n.createStartTitle), findsOneWidget);
    final field = tester.widget<TextField>(find.byType(TextField).first);
    expect(field.controller!.text, startsWith('You are the weakest outer disciple'));
  });

  testWidgets('your own idea opens a blank page', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();

    final own = find.text(l10n.discoverCreateTitle);
    await tester.scrollUntilVisible(own, 300, scrollable: find.byType(Scrollable).first);
    await tester.tap(own);
    await settle(tester, frames: 10);
    expect(app.location(tester), '/create');
    expect(find.text(l10n.createNewTitle), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField).first).controller!.text, isEmpty);
  });

  testWidgets('worlds whose covers aren\'t drawn yet show a glow instead', (tester) async {
    final app = AppHarness();
    await app.launch(
      tester,
      overrides: [
        // No story to continue, whose cover would be the one picture on the page.
        storiesProvider.overrideWith((ref) async => const <StorySummary>[]),
        premisesProvider.overrideWith(
          (ref) async => flagshipFirst([
            for (final premise in fakePremises) Premise.fromJson({...premise, 'cover_url': null}),
          ]),
        ),
      ],
    );
    final l10n = await english();

    final cards = tester.widgetList<CoverCard>(find.byType(CoverCard)).toList();
    expect(cards, isNotEmpty);
    expect(cards.every((c) => c.imageUrl == null), isTrue);
    await tester.scrollUntilVisible(
      find.text('The Esposito Succession'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text(l10n.discoverMore.toUpperCase()), findsOneWidget);
    // No picture is asked for: every card, large or on the shelf, draws its own glow.
    expect(find.byType(Image), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('with no worlds to show, your own idea is still there', (tester) async {
    final app = AppHarness();
    await app.launch(
      tester,
      overrides: [premisesProvider.overrideWith((ref) async => const <Premise>[])],
    );
    final l10n = await english();
    expect(find.text(l10n.discoverEmptyTitle), findsOneWidget);
    await tester.tap(find.text(l10n.discoverCreateAction));
    await settle(tester, frames: 10);
    expect(find.byType(CreateStoryScreen), findsOneWidget);
  });

  test('flagship worlds sort first, keeping their order', () {
    Premise p(String id, {bool flagship = false}) =>
        Premise(id: id, title: id, genre: '', premise: '', flagship: flagship);
    final sorted = flagshipFirst([p('a'), p('b', flagship: true), p('c'), p('d', flagship: true)]);
    expect(sorted.map((p) => p.id), ['b', 'd', 'a', 'c']);
  });
}
