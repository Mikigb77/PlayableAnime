import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/account/out_of_credits_sheet.dart';
import 'package:playable_anime/features/create/create_story_screen.dart';
import 'package:playable_anime/features/create/draft_widgets.dart';
import 'package:playable_anime/features/discover/discover_screen.dart';
import 'package:playable_anime/features/story/story_screen.dart';

import '../../helpers.dart';
import '../harness.dart';

/// Creating a story on the fake API, the way a player does it (G1, G2, F2, F8, K2, T10).
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  Finder inSheet(Finder finder) => find.descendant(of: find.byType(BottomSheet), matching: finder);

  Future<void> scrollTo(WidgetTester tester, Finder target) async {
    await tester.scrollUntilVisible(
      target,
      300,
      scrollable: find
          .descendant(of: find.byType(CreateStoryScreen), matching: find.byType(Scrollable))
          .first,
    );
    // Let the fling end: a scrolling list ignores taps.
    await tester.pump(const Duration(seconds: 1));
  }

  Future<void> tapAndSettle(WidgetTester tester, Finder target, {int frames = 10}) async {
    await tester.ensureVisible(target);
    await tester.pump();
    await tester.tap(target);
    await settle(tester, frames: frames);
  }

  /// Writes a premise on a blank page and drafts it, choosing [rating] first.
  Future<void> draft(
    WidgetTester tester, {
    String premise = 'A lighthouse keeper finds a door in the sea.',
    String? rating,
  }) async {
    await tester.enterText(find.byType(TextField).first, premise);
    // Done typing: a focused field would scroll itself back into view.
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump(const Duration(seconds: 1));
    if (rating != null) await tapAndSettle(tester, find.text(rating), frames: 2);
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
  }

  testWidgets('a premise becomes a draft to change, then a story', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    expect(find.text(l10n.createHeading), findsOneWidget);

    // A spark fills the box; the player writes their own instead.
    await tapAndSettle(tester, find.text(l10n.createSparkSalvage), frames: 2);
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller!.text,
      l10n.createSparkSalvage,
    );
    await draft(tester, rating: l10n.ratingMature);
    expect(app.sent('POST', (p) => p == '/v1/drafts').single.json, {
      'premise': 'A lighthouse keeper finds a door in the sea.',
      'rating': 'mature',
      'language': 'en',
    });

    // The review: title, both parts, and the settings.
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    expect(find.text('A story of your own'), findsOneWidget);
    expect(find.text(l10n.reviewWorld.toUpperCase()), findsOneWidget);
    const line = 'Three factions want the same thing, and only one of them knows you exist.';
    expect(find.text(line), findsOneWidget);

    // Rewriting a line says what it costs, then redrafts the world.
    await tapAndSettle(tester, find.text(line), frames: 6);
    expect(find.text(l10n.lineSheetTitle), findsOneWidget);
    // Until the line changes, the cost is Remove's, which redrafts the world too.
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Four factions, and all of them know.');
    await tester.pump();
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    int meReads() => app.sent('GET', (p) => p == '/v1/me').length;
    var reads = meReads();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    // A paid change reads the balance again (K2).
    expect(meReads(), greaterThan(reads));
    final patch = app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')).single.json;
    expect(patch['expected_version'], 1);
    expect(patch['world_lines'], contains('Four factions, and all of them know.'));
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('Four factions, and all of them know.'), findsOneWidget);

    // Asking for a different character, in plain words.
    await scrollTo(tester, find.text(l10n.reviewAskCharacter));
    await tapAndSettle(tester, find.text(l10n.reviewAskCharacter), frames: 6);
    expect(inSheet(find.text(l10n.costCharacter)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Make me older, with a scar');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    final revise = app.sent('POST', (p) => p.endsWith('/revise')).single.json;
    expect(revise, {
      'target': 'character',
      'instruction': 'Make me older, with a scar',
      'expected_version': 2,
    });
    expect(find.text(l10n.reviewCharacterRedrafted), findsOneWidget);

    // Strict physics is free.
    await scrollTo(tester, find.text(l10n.reviewAdvanced));
    await tapAndSettle(tester, find.text(l10n.reviewAdvanced), frames: 6);
    expect(find.text(l10n.advancedTitle), findsWidgets);
    await tapAndSettle(tester, inSheet(find.text(l10n.physicsStrict)), frames: 2);
    await tester.ensureVisible(inSheet(find.text(l10n.costFree)));
    expect(inSheet(find.text(l10n.costFree)), findsOneWidget);
    reads = meReads();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(meReads(), reads, reason: 'a free change spends nothing');
    expect(app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')).last.json, {
      'advanced': {'physics': 'strict'},
      'expected_version': 3,
    });
    expect(find.text(l10n.reviewSaved), findsOneWidget);
    expect(find.textContaining(l10n.physicsStrict), findsOneWidget);

    // Lowering the rating to Teen redrafts both parts, and says so first.
    await tapAndSettle(tester, find.text(l10n.reviewRating), frames: 6);
    await tapAndSettle(tester, inSheet(find.text(l10n.ratingTeen)), frames: 2);
    expect(inSheet(find.text(l10n.costBoth)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')).last.json, {
      'rating': 'teen',
      'expected_version': 4,
    });
    expect(find.text(l10n.reviewBothRedrafted), findsOneWidget);

    // Starting opens the play screen.
    await tapAndSettle(tester, find.text(l10n.reviewStart), frames: 14);
    final start = app.sent('POST', (p) => p.endsWith('/start')).single;
    expect(start.json, {'expected_version': 5});
    expect(find.byType(StoryScreen), findsOneWidget);
    expect(app.location(tester), startsWith('/story/story_'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('a starter drafts by id, keeping its own words', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create?premise=outer-disciple');
    expect(find.text(l10n.createStartTitle), findsOneWidget);
    expect(find.text('The Last Outer Disciple'), findsOneWidget);
    // New stories are Teen until the player picks Mature.
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    expect(app.sent('POST', (p) => p == '/v1/drafts').single.json, {
      'premise_id': 'outer-disciple',
      'rating': 'teen',
      'language': 'en',
    });
    expect(find.textContaining('Lin Feng'), findsOneWidget);
  });

  testWidgets('a draft is written, dictated and started in the app\'s language (S10)', (
    tester,
  ) async {
    tester.platformDispatcher.localesTestValue = const [Locale('es', 'ES')];
    addTearDown(tester.platformDispatcher.clearLocalesTestValue);
    final app = AppHarness();
    await app.launch(tester, location: '/create?premise=outer-disciple');
    final es = await AppLocalizations.delegate.load(const Locale('es'));

    await tester.tap(find.byType(MicButton).first);
    await tester.pump();
    expect(app.speech.listens.last.localeId, 'es-ES');
    await tester.tap(find.byTooltip(es.micStop));
    await tester.pump();

    await scrollTo(tester, find.text(es.createDraftAction));
    await tapAndSettle(tester, find.text(es.createDraftAction), frames: 12);
    expect(app.sent('POST', (p) => p == '/v1/drafts').single.json['language'], 'es');

    await scrollTo(tester, find.text(es.reviewStart));
    await tapAndSettle(tester, find.text(es.reviewStart), frames: 12);
    expect(find.byType(StoryScreen), findsOneWidget);
    final id = Uri.decodeComponent(app.location(tester).split('/').last);
    final story = app.backend.data.stories
        .ownedBy(FakeAuthState.demoUserId)
        .where((s) => s.id == id);
    expect(story.single.settings['language'], 'es');
  });

  testWidgets('a teen account cannot pick Mature (F8)', (tester) async {
    final app = AppHarness()..maxRating = 'teen';
    await app.launch(tester, location: '/create');
    await tester.enterText(find.byType(TextField).first, 'A door in the sea opens at low tide.');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump(const Duration(seconds: 1));
    await scrollTo(tester, find.text(l10n.ratingMatureLocked));
    expect(find.text(l10n.ratingMatureLocked), findsOneWidget);
    // Locked: a tap changes nothing.
    await tester.tap(find.text(l10n.ratingMature), warnIfMissed: false);
    await tester.pump();
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    expect(app.sent('POST', (p) => p == '/v1/drafts').single.json['rating'], 'teen');
    expect(find.text(l10n.reviewTitle), findsOneWidget);
  });

  /// Adds the player's own key in the out-of-credits sheet (K6).
  Future<void> addKeyInSheet(WidgetTester tester) async {
    Finder inOoc(Finder finder) =>
        find.descendant(of: find.byType(OutOfCreditsSheet), matching: finder);
    await tapAndSettle(tester, inOoc(find.byKey(const Key('ooc.useKey'))));
    await tester.enterText(inOoc(find.byKey(const Key('account.ownKey'))), 'AIza-test-key-4321');
    await tapAndSettle(tester, inOoc(find.byKey(const Key('account.ownKey.save'))), frames: 14);
  }

  /// Spends the demo account's credits, so the next paid request is refused (K2).
  void spendAll(AppHarness app) => app.backend.data.account.charge(
    FakeAuthState.demoUserId,
    kind: 'draft',
    cents: 1000,
    now: DateTime.utc(2026, 11, 2),
  );

  testWidgets('out of credits offers your own key and keeps the premise (K2)', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester, premise: 'A quiet village by the sea [fail:out_of_credits]');
    // The sheet opens by itself, over the premise.
    expect(find.byType(OutOfCreditsSheet), findsOneWidget);
    expect(find.text(l10n.oocTitle), findsOneWidget);

    await tapAndSettle(tester, find.text(l10n.close));
    expect(find.byType(OutOfCreditsSheet), findsNothing);
    expect(find.text(l10n.createHeading), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller!.text,
      'A quiet village by the sea [fail:out_of_credits]',
    );
    // The failure stays, with the way back to the sheet.
    await scrollTo(tester, find.text(l10n.oocCarryOn));
    await tapAndSettle(tester, find.text(l10n.oocCarryOn));
    expect(find.byType(OutOfCreditsSheet), findsOneWidget);
    expect(app.sent('POST', (p) => p == '/v1/drafts'), hasLength(1));
  });

  testWidgets('with your own key added, drafting carries on at no charge (K6)', (tester) async {
    final app = AppHarness();
    spendAll(app);
    await app.launch(tester, location: '/create');
    await draft(tester);
    expect(find.byType(OutOfCreditsSheet), findsOneWidget);
    final ledger = app.backend.data.account.ledgerOf(FakeAuthState.demoUserId).length;

    await addKeyInSheet(tester);
    expect(find.byType(OutOfCreditsSheet), findsNothing);
    expect(find.text(l10n.oocKeySavedRetrying), findsOneWidget);
    final drafts = app.sent('POST', (p) => p == '/v1/drafts');
    expect(drafts, hasLength(2));
    expect(drafts.first.usesOwnKey, isFalse);
    expect(drafts.last.usesOwnKey, isTrue);
    expect(drafts.last.json, drafts.first.json);
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    // Drafting on the player's own key spends nothing.
    expect(app.backend.data.account.ledgerOf(FakeAuthState.demoUserId), hasLength(ledger));
  });

  testWidgets('a change out of credits is made again on your own key (K6)', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    spendAll(app);

    const line = 'Three factions want the same thing, and only one of them knows you exist.';
    await tapAndSettle(tester, find.text(line), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Four factions, and all of them know.');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(OutOfCreditsSheet), findsOneWidget);

    await addKeyInSheet(tester);
    final patches = app.sent('PATCH', (p) => p.startsWith('/v1/drafts/'));
    expect(patches, hasLength(2));
    expect(patches.last.usesOwnKey, isTrue);
    expect(patches.last.json, patches.first.json);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('Four factions, and all of them know.'), findsOneWidget);
  });

  const realPerson =
      'The person you named is a real person, and stories only have fictional people. '
      'Try someone made up instead.';

  testWidgets('a real person in the premise is refused under the box (G12)', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester, premise: 'I am the bodyguard of [fail:real_person] in Rome.');
    expect(find.text(l10n.createHeading), findsOneWidget);
    expect(find.text(realPerson), findsOneWidget);
    expect(find.byType(InlineError), findsNothing);
    final field = tester.widget<TextField>(find.byType(TextField).first);
    expect(field.decoration!.errorText, realPerson);

    // Changing the words takes the refusal away.
    await tester.enterText(find.byType(TextField).first, 'I am the bodyguard of a senator.');
    await tester.pump();
    expect(find.text(realPerson), findsNothing);
  });

  testWidgets('a refused rule shows under that rule, and blank rules are never sent', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await scrollTo(tester, find.text(l10n.reviewAdvanced));
    await tapAndSettle(tester, find.text(l10n.reviewAdvanced), frames: 6);

    // A blank rule, then one naming a real person.
    final add = inSheet(find.text(l10n.ruleAdd));
    await tapAndSettle(tester, add, frames: 2);
    await tapAndSettle(tester, add, frames: 2);
    final rules = inSheet(find.widgetWithText(TextField, l10n.ruleHint));
    await tester.enterText(rules.last, '[fail:real_person] rules the sea.');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump(const Duration(seconds: 1));
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));

    final sent = app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')).single.json;
    final sentRules = (sent['advanced'] as Map)['rules'] as List;
    expect(sentRules, hasLength(3));
    expect(sentRules.last, {'text': '[fail:real_person] rules the sea.', 'fixed': true});
    expect(find.byType(BottomSheet), findsOneWidget);
    await tester.ensureVisible(inSheet(find.text(realPerson)));
    expect(inSheet(find.text(realPerson)), findsOneWidget);
    expect(inSheet(find.byType(InlineError)), findsNothing);
  });

  testWidgets('a failed change keeps the sheet open with what was written', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await scrollTo(tester, find.text(l10n.reviewAskWorld));
    await tapAndSettle(tester, find.text(l10n.reviewAskWorld), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add rain [fail:rate_limited]');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(inSheet(find.text('Add rain [fail:rate_limited]')), findsOneWidget);
    expect(inSheet(find.byType(InlineError)), findsOneWidget);
  });

  testWidgets('a draft changed elsewhere is reloaded, and the change asked again', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await scrollTo(tester, find.text(l10n.reviewAskWorld));
    await tapAndSettle(tester, find.text(l10n.reviewAskWorld), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add a storm [fail:version_conflict]');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewConflict), findsOneWidget);
    expect(app.sent('GET', (p) => p.startsWith('/v1/drafts/')), hasLength(1));
  });

  testWidgets('a draft that fails after a while keeps the premise and choices', (tester) async {
    const slow = FakePace(
      latency: Duration.zero,
      firstWords: Duration.zero,
      perChunk: Duration.zero,
      picture: Duration.zero,
      drafting: Duration(seconds: 2),
    );
    final app = AppHarness(pace: slow);
    await app.launch(tester, location: '/create');
    await draft(
      tester,
      premise: 'A quiet village by the sea [fail:llm_unavailable]',
      rating: l10n.ratingMature,
    );
    expect(find.text(l10n.draftingTitle), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    await settle(tester, frames: 12);
    expect(find.text(l10n.createHeading), findsOneWidget);
    expect(find.byType(InlineError), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller!.text,
      'A quiet village by the sea [fail:llm_unavailable]',
    );
    // Drafting again keeps the rating chosen before.
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 2);
    expect(app.sent('POST', (p) => p == '/v1/drafts').last.json['rating'], 'mature');
    await tester.pump(const Duration(seconds: 3));
    await settle(tester, frames: 12);
  });

  testWidgets('a sheet closed while its change saves leaves the review open', (tester) async {
    const slow = FakePace(
      latency: Duration.zero,
      firstWords: Duration.zero,
      perChunk: Duration.zero,
      picture: Duration.zero,
      drafting: Duration(seconds: 2),
    );
    final app = AppHarness(pace: slow);
    await app.launch(tester, location: '/create');
    await draft(tester);
    await tester.pump(const Duration(seconds: 2));
    await settle(tester, frames: 12);
    expect(find.text(l10n.reviewTitle), findsOneWidget);

    const line = 'Three factions want the same thing, and only one of them knows you exist.';
    await tapAndSettle(tester, find.text(line), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Four factions, and all of them know.');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)), frames: 2);
    // Closed by a tap above it just before the redrafted world comes back, which lands while
    // the sheet is still sliding away.
    await tester.pump(const Duration(milliseconds: 1850));
    await tester.tapAt(const Offset(195, 20));
    await settle(tester, frames: 12);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.byType(CreateStoryScreen), findsOneWidget);
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    expect(find.text('Four factions, and all of them know.'), findsOneWidget);
  });

  testWidgets('removing a line says what it costs, then redrafts the world', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    const line = 'News travels at the speed of a fast horse, and rumours travel faster.';
    await scrollTo(tester, find.text(line));
    await tapAndSettle(tester, find.text(line), frames: 6);
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.lineRemove)));
    final sent = app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')).single.json;
    expect(sent['world_lines'], isNot(contains(line)));
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text(line), findsNothing);
  });

  testWidgets('back from a link asks before losing the draft', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create?premise=outer-disciple');
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    await tester.tap(find.byType(BackButton));
    await settle(tester);
    expect(find.text(l10n.reviewLeaveTitle), findsOneWidget);
    await tapAndSettle(tester, find.text(l10n.reviewLeave));
    expect(find.byType(DiscoverScreen), findsOneWidget);
    expect(app.location(tester), '/discover');
  });

  testWidgets('leaving a draft asks first, since it is not in the library yet', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/discover');
    await tapAndSettle(tester, find.text('The Last Outer Disciple'));
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    expect(find.text(l10n.reviewTitle), findsOneWidget);

    await tester.tap(find.byType(BackButton));
    await settle(tester);
    expect(find.text(l10n.reviewLeaveTitle), findsOneWidget);
    await tapAndSettle(tester, find.text(l10n.reviewLeaveStay));
    expect(find.text(l10n.reviewTitle), findsOneWidget);

    await tester.tap(find.byType(BackButton));
    await settle(tester);
    await tapAndSettle(tester, find.text(l10n.reviewLeave));
    expect(find.byType(DiscoverScreen), findsOneWidget);
    expect(find.byType(CreateStoryScreen), findsNothing);
  });
}
