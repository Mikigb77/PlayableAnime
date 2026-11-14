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
import 'package:playable_anime/features/story/sheet_view.dart';
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
    // Done typing: a focused field would scroll itself back into view. Typed into lower down
    // the page, it brings its caret on screen first, and a scrolling list ignores taps.
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump(const Duration(seconds: 1));
    await settle(tester);
    if (rating != null) await tapAndSettle(tester, find.text(rating), frames: 2);
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
  }

  /// From the world's screen on to the character's, and back by its step.
  Future<void> toCharacter(WidgetTester tester, [AppLocalizations? words]) =>
      tapAndSettle(tester, find.text((words ?? l10n).reviewNext), frames: 10);
  Future<void> toWorld(WidgetTester tester) =>
      tapAndSettle(tester, find.byKey(const ValueKey('review.step.world')), frames: 10);

  /// The button that asks for a different world, in plain words.
  Finder askWorld() => find.textContaining(l10n.reviewAskWorld, findRichText: true);

  const realPerson =
      'The person you named is a real person, and stories only have fictional people. '
      'Try someone made up instead.';

  /// The rows of the fake's draft of a premise of the player's own.
  const factions =
      'Three factions: they want the same thing, and only one of them knows you exist.';
  const looks = 'Lean and weathered, with watchful eyes and a coat that has seen better roads.';

  List<FakeRequest> patches(AppHarness app) =>
      app.sent('PATCH', (p) => p.startsWith('/v1/drafts/'));

  testWidgets('a premise becomes a draft to change, then a story', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    expect(find.text(l10n.createHeading), findsOneWidget);
    // What a premise can settle, with an example of each, and what it leaves a surprise.
    expect(find.text(l10n.createDecideLabel), findsOneWidget);
    expect(find.text(l10n.createDecideComingExample), findsOneWidget);
    // What the character is after is theirs to give too, said as an aim.
    expect(find.text(l10n.createDecideAimExample), findsOneWidget);
    expect(find.text(l10n.createDecideNote), findsOneWidget);

    // A spark fills the empty box and the sparks go, so a tap never replaces written words.
    await scrollTo(tester, find.text(l10n.createSparkSalvage));
    await tapAndSettle(tester, find.text(l10n.createSparkSalvage), frames: 6);
    expect(
      tester.widget<TextField>(find.byType(TextField).first).controller!.text,
      l10n.createSparkSalvage,
    );
    expect(find.text(l10n.createSparkNaples), findsNothing);
    // The player writes their own instead.
    await draft(tester, rating: l10n.ratingMature);
    expect(app.sent('POST', (p) => p == '/v1/drafts').single.json, {
      'premise': 'A lighthouse keeper finds a door in the sea.',
      'rating': 'mature',
      'language': 'en',
    });

    // The review opens on the world, and only the world: the character waits a step on.
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    expect(find.text('A story of your own'), findsOneWidget);
    expect(find.text(l10n.reviewStepWorld), findsOneWidget);
    expect(find.text(l10n.reviewStepCharacter), findsOneWidget);
    expect(find.text(l10n.reviewLegendDirect), findsOneWidget);
    expect(find.text(l10n.reviewLegendAsk), findsOneWidget);
    expect(find.text('Rowan'), findsNothing);
    expect(find.text(l10n.giftLabel.toUpperCase()), findsNothing);
    expect(find.text(l10n.reviewStart), findsNothing);
    expect(find.text(l10n.reviewNextNote), findsOneWidget);

    // The title is typed, saved at once, and free.
    int meReads() => app.sent('GET', (p) => p == '/v1/me').length;
    var reads = meReads();
    await tapAndSettle(tester, find.text('A story of your own'), frames: 6);
    expect(find.text(l10n.titleSheetTitle), findsOneWidget);
    expect(inSheet(find.text(l10n.costFree)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'The Door in the Sea');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(patches(app).single.json, {'title': 'The Door in the Sea', 'expected_version': 1});
    expect(meReads(), reads, reason: 'a free change spends nothing');
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewSaved), findsOneWidget);
    expect(find.text('The Door in the Sea'), findsOneWidget);

    // A row the storyteller wrote opens the box where the player says what to change, already
    // pointed at that row, with what it costs.
    await scrollTo(tester, find.text(factions));
    await tapAndSettle(tester, find.text(factions), frames: 6);
    expect(find.text(l10n.reviseWorldTitle), findsOneWidget);
    expect(inSheet(find.text(l10n.reviseAbout(l10n.rowFactions))), findsOneWidget);
    expect(inSheet(find.text(factions)), findsOneWidget);
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add a fourth, in hiding');
    await tester.pump();
    reads = meReads();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    // A paid change reads the balance again (K2).
    expect(meReads(), greaterThan(reads));
    expect(app.sent('POST', (p) => p.endsWith('/revise')).single.json, {
      'target': 'world',
      'instruction': 'Add a fourth, in hiding',
      'about': 'faction',
      'expected_version': 2,
    });
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('$factions A fourth, in hiding.'), findsOneWidget);

    // How it plays is the world's too. Strict physics is free: picked, it is saved.
    await scrollTo(tester, find.text(l10n.physicsStrict));
    reads = meReads();
    await tapAndSettle(tester, find.text(l10n.physicsStrict));
    expect(find.byType(BottomSheet), findsNothing);
    expect(meReads(), reads, reason: 'a free change spends nothing');
    expect(patches(app).last.json, {
      'advanced': {'physics': 'strict'},
      'expected_version': 3,
    });
    expect(find.text(l10n.physicsStrictBody), findsOneWidget);

    // On to the character, and only the character: who they are leads, as the story's own
    // Character page opens.
    await toCharacter(tester);
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    expect(find.text('Rowan'), findsOneWidget);
    expect(find.text(l10n.reviewYearsOld(19)), findsOneWidget);
    expect(find.text('The Door in the Sea'), findsNothing);
    expect(find.text(l10n.reviewNext), findsNothing);
    expect(find.text(l10n.reviewStart), findsOneWidget);

    // The name and the age are typed, saved at once, and free.
    reads = meReads();
    await tapAndSettle(tester, find.text('Rowan'), frames: 6);
    expect(find.text(l10n.nameSheetTitle), findsOneWidget);
    expect(inSheet(find.text(l10n.costFree)), findsOneWidget);
    await tester.enterText(inSheet(find.widgetWithText(TextField, l10n.nameLabel)), 'Mara Quill');
    await tester.enterText(inSheet(find.widgetWithText(TextField, l10n.ageLabel)), '23');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(patches(app).last.json, {
      'character': {'name': 'Mara Quill', 'age': 23},
      'expected_version': 4,
    });
    expect(meReads(), reads, reason: 'a free change spends nothing');
    expect(find.text('Mara Quill'), findsOneWidget);
    expect(find.text(l10n.reviewYearsOld(23)), findsOneWidget);

    // So are the looks, which every picture is drawn from.
    await tapAndSettle(tester, find.text(looks), frames: 6);
    expect(find.text(l10n.looksSheetTitle), findsOneWidget);
    expect(inSheet(find.text(l10n.looksHelp)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Tall, with a burn across one hand.');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(patches(app).last.json, {
      'character': {'looks': 'Tall, with a burn across one hand.'},
      'expected_version': 5,
    });
    expect(find.text('Tall, with a burn across one hand.'), findsOneWidget);

    // What the storyteller drafted is laid out as the Character page lays it out: skills
    // with the dice each throws, what they are like as chips, what they carry.
    await scrollTo(tester, find.text('Getting out of trouble'));
    expect(find.text('Fair · ${l10n.sheetDice(2)}'), findsOneWidget);
    await scrollTo(tester, find.text('Restless'));
    expect(find.text('Owes a favour to the wrong person'), findsOneWidget);

    // A section's wand asks about that section, with what the draft says of it.
    await scrollTo(tester, find.byKey(const ValueKey('review.ask.skills')));
    await tapAndSettle(tester, find.byKey(const ValueKey('review.ask.skills')), frames: 6);
    expect(find.text(l10n.reviseCharacterTitle), findsOneWidget);
    expect(inSheet(find.text(l10n.reviseAbout(l10n.sheetSkills))), findsOneWidget);
    expect(
      inSheet(find.text('Fair: getting out of trouble. Novice: staying out of it.')),
      findsOneWidget,
    );
    expect(inSheet(find.text(l10n.costCharacter)), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add sailing');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(app.sent('POST', (p) => p.endsWith('/revise')).last.json, {
      'target': 'character',
      'instruction': 'Add sailing',
      'about': 'skills',
      'expected_version': 6,
    });
    expect(find.text(l10n.reviewCharacterRedrafted), findsOneWidget);
    await scrollTo(tester, find.text('Sailing'));

    // Asking for a different character as a whole, in plain words, at the foot of the screen,
    // once the word that the last change saved has gone from over it.
    await tester.pump(const Duration(seconds: 5));
    await settle(tester);
    final ask = find.textContaining(l10n.reviewAskCharacter, findRichText: true);
    await scrollTo(tester, ask);
    await tapAndSettle(tester, ask, frames: 6);
    expect(inSheet(find.text(l10n.costCharacter)), findsOneWidget);
    expect(inSheet(find.textContaining(l10n.reviseAbout(''))), findsNothing);
    await tester.enterText(inSheet(find.byType(TextField)), 'Make me older, with a scar');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(app.sent('POST', (p) => p.endsWith('/revise')).last.json, {
      'target': 'character',
      'instruction': 'Make me older, with a scar',
      'expected_version': 7,
    });
    expect(find.text(l10n.reviewCharacterRedrafted), findsOneWidget);

    // The world is one tap back. Lowering the rating to Teen redrafts both parts, and says so
    // first.
    await toWorld(tester);
    expect(find.text('The Door in the Sea'), findsOneWidget);
    expect(find.text('Mara Quill'), findsNothing);
    await scrollTo(tester, find.widgetWithText(ChoiceChip, l10n.ratingTeen));
    await tapAndSettle(tester, find.widgetWithText(ChoiceChip, l10n.ratingTeen), frames: 6);
    expect(inSheet(find.text(l10n.ratingTeenBody)), findsOneWidget);
    expect(inSheet(find.text(l10n.costBoth)), findsOneWidget);
    expect(patches(app), hasLength(4));
    await tapAndSettle(tester, inSheet(find.text(l10n.choiceChange)));
    expect(patches(app).last.json, {'rating': 'teen', 'expected_version': 8});
    expect(find.text(l10n.reviewBothRedrafted), findsOneWidget);

    // The story starts from the character's screen.
    await toCharacter(tester);
    await tapAndSettle(tester, find.text(l10n.reviewStart), frames: 14);
    final start = app.sent('POST', (p) => p.endsWith('/start')).single;
    expect(start.json, {'expected_version': 9});
    expect(find.byType(StoryScreen), findsOneWidget);
    expect(app.location(tester), startsWith('/story/story_'));
    expect(tester.takeException(), isNull);
  });

  testWidgets('what the premise names of the start shows, and the rest is only counted (G1)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(
      tester,
      premise: 'I am a squire. My rival is called Garrick, and my trial is in three days.',
    );
    await scrollTo(tester, find.text(l10n.reviewKeptBody));
    expect(find.text(l10n.reviewYours.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.openerDeadline.toUpperCase()), findsOneWidget);
    expect(find.text('The reckoning: in 3 days'), findsOneWidget);
    expect(find.text(l10n.openerPerson.toUpperCase()), findsOneWidget);
    expect(find.text('Garrick: your rival.'), findsOneWidget);
    expect(find.text(l10n.reviewYoursNone), findsNothing);
    // What the story keeps back is a count and nothing more.
    expect(find.text(l10n.keptPeople(3)), findsOneWidget);
    expect(find.text(l10n.keptEvents(2)), findsOneWidget);
    expect(find.text(l10n.keptQuestions(2)), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
    expect(find.text('2'), findsNWidgets(2));

    // What the player named is theirs to change, by telling the storyteller.
    await tapAndSettle(tester, find.text('Garrick: your rival.'), frames: 6);
    expect(inSheet(find.text(l10n.reviseAbout(l10n.openerPerson))), findsOneWidget);
    await tester.enterText(inSheet(find.byType(TextField)), 'Make him my older brother');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(app.sent('POST', (p) => p.endsWith('/revise')).single.json, {
      'target': 'world',
      'instruction': 'Make him my older brother',
      'about': 'person',
      'expected_version': 1,
    });
  });

  testWidgets('a premise that names nothing of the start sees none of it (G1)', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await scrollTo(tester, find.text(l10n.reviewKeptBody));
    expect(find.text(l10n.reviewYoursNone), findsOneWidget);
    expect(find.textContaining('Garrick'), findsNothing);
    expect(find.textContaining('reckoning'), findsNothing);
    // The rival and the reckoning are in the story all the same: one more of each is kept.
    expect(find.text(l10n.keptPeople(4)), findsOneWidget);
    expect(find.text(l10n.keptEvents(3)), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('a rule is locked or opened for free, and its words redraft the world (G6, G7)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    expect(find.text(l10n.rulesFixedGroup.toUpperCase()), findsOneWidget);
    expect(
      find.textContaining(l10n.rulesOpenGroup.toUpperCase(), findRichText: true),
      findsOneWidget,
    );

    // Opening a locked rule changes no words, so it is free.
    await scrollTo(tester, find.text('The dead stay dead.'));
    await tapAndSettle(tester, find.text('The dead stay dead.'), frames: 6);
    expect(find.text(l10n.ruleSheetTitle), findsOneWidget);
    // Until something changes, the cost is Remove's, which redrafts the world.
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.byType(Switch)), frames: 2);
    expect(inSheet(find.text(l10n.costFree)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(patches(app).single.json, {
      'advanced': {
        'rules': [
          {'id': 'dead-stay-dead', 'text': 'The dead stay dead.', 'fixed': false},
          {
            'id': 'power-has-a-price',
            'text': 'Power grows through effort, teachers and luck.',
            'fixed': false,
          },
        ],
      },
      'expected_version': 1,
    });
    expect(find.text(l10n.reviewSaved), findsOneWidget);
    // No rule is locked now, so only the open group is left.
    expect(find.text(l10n.rulesFixedGroup.toUpperCase()), findsNothing);

    // A new rule naming a real person is refused under its own words, and nothing is saved.
    await scrollTo(tester, find.text(l10n.ruleAdd));
    await tapAndSettle(tester, find.text(l10n.ruleAdd), frames: 6);
    expect(find.text(l10n.ruleSheetNew), findsOneWidget);
    expect(inSheet(find.text(l10n.ruleRemove)), findsNothing);
    await tester.enterText(inSheet(find.byType(TextField)), '[fail:real_person] rules the sea.');
    await tester.pump();
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(inSheet(find.text(realPerson)), findsOneWidget);
    expect(inSheet(find.byType(InlineError)), findsNothing);
    expect(((patches(app).last.json['advanced'] as Map)['rules'] as List).last, {
      'text': '[fail:real_person] rules the sea.',
      'fixed': true,
    });

    // Other words go through, and the world is redrafted to match.
    await tester.enterText(inSheet(find.byType(TextField)), 'Iron burns the drowned.');
    await tester.pump();
    expect(inSheet(find.text(realPerson)), findsNothing);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('Iron burns the drowned.'), findsOneWidget);
    expect(find.text(l10n.rulesFixedGroup.toUpperCase()), findsOneWidget);

    // Removing a rule says what it costs, then redrafts the world.
    await tapAndSettle(tester, find.text('Iron burns the drowned.'), frames: 6);
    expect(inSheet(find.text(l10n.costWorld)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.ruleRemove)));
    final rules = (patches(app).last.json['advanced'] as Map)['rules'] as List;
    expect(rules, hasLength(2));
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('Iron burns the drowned.'), findsNothing);
  });

  testWidgets('a typed field left empty saves nothing, and a refused one says why (G12)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await toCharacter(tester);
    await tapAndSettle(tester, find.text('Rowan'), frames: 6);
    final name = inSheet(find.widgetWithText(TextField, l10n.nameLabel));
    FilledButton save() => tester.widget(inSheet(find.widgetWithText(FilledButton, l10n.save)));
    // Nothing changed yet, and an empty name is not a change.
    expect(save().onPressed, isNull);
    await tester.enterText(name, '   ');
    await tester.pump();
    expect(inSheet(find.text(l10n.fieldEmpty)), findsOneWidget);
    expect(save().onPressed, isNull);

    await tester.enterText(name, '[fail:real_person]');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(BottomSheet), findsOneWidget);
    expect(tester.widget<TextField>(name).decoration!.errorText, realPerson);
    expect(inSheet(find.byType(InlineError)), findsNothing);
    // Changing the words takes the refusal away, and the name goes through.
    await tester.enterText(name, 'Ilse');
    await tester.pump();
    expect(tester.widget<TextField>(name).decoration!.errorText, isNull);
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('Ilse'), findsOneWidget);
    expect(patches(app).last.json, {
      'character': {'name': 'Ilse'},
      'expected_version': 1,
    });
  });

  testWidgets('a new name takes the old one\'s place wherever the draft says it (G2)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create?premise=naples-vendetta');
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    await toCharacter(tester);
    expect(find.text('Luca Esposito'), findsOneWidget);
    await tapAndSettle(tester, find.text('Luca Esposito'), frames: 6);
    await tester.enterText(
      inSheet(find.widgetWithText(TextField, l10n.nameLabel)),
      'Nico Esposito',
    );
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.text('Nico Esposito'), findsOneWidget);
    expect(find.textContaining('Luca'), findsNothing);
    // The family keeps its name, in the world too.
    expect(find.textContaining('Esposito family'), findsOneWidget);
    await toWorld(tester);
    expect(find.textContaining('Luca'), findsNothing);
    await scrollTo(tester, find.textContaining('The Esposito family'));
    expect(find.textContaining('The Esposito family'), findsOneWidget);
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
    // The world leads, under the starter's cover. The starter's own words name the
    // tournament, so it shows; nobody else is named.
    expect(find.text('The Last Outer Disciple'), findsOneWidget);
    expect(find.text('Lin Feng'), findsNothing);
    await scrollTo(tester, find.text(l10n.reviewKeptBody));
    expect(find.text('The ranking tournament: in 2 days'), findsOneWidget);
    expect(find.textContaining('Zhao'), findsNothing);

    // Then the character, with their path drawn as the Character page draws it: the rungs
    // everyone has heard of, their own lit with its stage, and what lies above unknown (G18).
    await toCharacter(tester);
    expect(find.text('Lin Feng'), findsOneWidget);
    expect(find.textContaining('Outer disciple of the Azure Cloud Sect'), findsOneWidget);
    await scrollTo(tester, find.text('Qi Condensation'));
    expect(find.byType(SheetPathCard), findsOneWidget);
    expect(find.text('Early stage'), findsOneWidget);
    expect(find.text('Foundation Establishment'), findsOneWidget);
    expect(find.text(l10n.pathAbove), findsOneWidget);
    // The starter names no goal of theirs, so none shows.
    expect(find.textContaining('Keep your place'), findsNothing);
  });

  testWidgets('the character screen says how they learn, from the player\'s own words (A4, G2)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester, premise: 'I am a squire with no family name, a genius with the sword.');
    await toCharacter(tester);

    // How they learn comes before anything else the storyteller drafted, with the strength it
    // read, the pace that gives, what it covers and the words it read it from.
    final learning = find.text(l10n.sheetLearning.toUpperCase());
    await scrollTo(tester, learning);
    expect(
      tester.getTopLeft(learning).dy,
      lessThan(tester.getTopLeft(find.text(l10n.sheetSkills.toUpperCase())).dy),
    );
    expect(find.text('The sword'), findsOneWidget);
    expect(find.text('GENIUS'), findsOneWidget);
    expect(find.text('Four times as fast'), findsOneWidget);
    expect(find.text('Anything fought with a blade'), findsOneWidget);
    expect(find.text(l10n.sheetTalentSaid('a genius with the sword')), findsOneWidget);
    expect(find.byKey(const ValueKey('review.learning.ordinary')), findsNothing);
    // What each strength is worth is said once, for a player who has never heard of them.
    expect(find.text(l10n.learnScale), findsOneWidget);

    // A chip starts the player's words for them, at how they learn.
    await scrollTo(tester, find.text(l10n.learnSeedUnique));
    await tapAndSettle(tester, find.text(l10n.learnSeedUnique), frames: 6);
    expect(inSheet(find.text(l10n.reviseAbout(l10n.sheetLearning))), findsOneWidget);
    final box = tester.widget<TextField>(inSheet(find.byType(TextField)));
    expect(box.controller!.text, l10n.learnSeedUniqueText);
    expect(box.controller!.selection.baseOffset, l10n.learnSeedUniqueText.length);
    await tester.enterText(inSheet(find.byType(TextField)), 'I am one of a kind at the spear');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(app.sent('POST', (p) => p.endsWith('/revise')).single.json, {
      'target': 'character',
      'instruction': 'I am one of a kind at the spear',
      'about': 'talents',
      'expected_version': 1,
    });
    await scrollTo(tester, find.text('ONE OF A KIND'));
    expect(find.text('Eight times as fast'), findsOneWidget);
  });

  testWidgets('a character nobody called gifted is told they learn at the ordinary pace (A4)', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await toCharacter(tester);
    await scrollTo(tester, find.byKey(const ValueKey('review.learning.ordinary')));
    expect(find.text(l10n.learnOrdinary), findsOneWidget);
    expect(find.text(l10n.learnOrdinaryBody), findsOneWidget);
    expect(find.text(l10n.learnScale), findsOneWidget);
    // Nothing to take away, so no chip offers it.
    expect(find.text(l10n.learnSeedGenius), findsOneWidget);
    expect(find.byKey(const ValueKey('review.seed.none')), findsNothing);

    // The gift sits with their powers, and a stronger one says what it costs first.
    await scrollTo(tester, find.widgetWithText(ChoiceChip, l10n.giftRare));
    await tapAndSettle(tester, find.widgetWithText(ChoiceChip, l10n.giftRare), frames: 6);
    expect(inSheet(find.text(l10n.giftRareBody)), findsOneWidget);
    expect(inSheet(find.text(l10n.costCharacter)), findsOneWidget);
    await tapAndSettle(tester, inSheet(find.text(l10n.choiceChange)));
    expect(patches(app).single.json, {
      'advanced': {'gift_strength': 'rare'},
      'expected_version': 1,
    });
    expect(find.text(l10n.reviewCharacterRedrafted), findsOneWidget);
    await scrollTo(tester, find.text('A rare talent'));
  });

  testWidgets('back from the character is the world, and a goal of theirs is on their screen', (
    tester,
  ) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create?premise=outer-disciple');
    await tester.enterText(
      find.byType(TextField).first,
      'I am the weakest outer disciple of the Azure Cloud Sect. My goal is to stay.',
    );
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pump(const Duration(seconds: 1));
    await scrollTo(tester, find.text(l10n.createDraftAction));
    await tapAndSettle(tester, find.text(l10n.createDraftAction), frames: 12);
    // The goal is the character's: the world's screen doesn't show it.
    await scrollTo(tester, find.text(l10n.reviewKeptBody));
    expect(find.textContaining('Keep your place'), findsNothing);
    await toCharacter(tester);
    final goal = find.text('Goal: Keep your place on the mountain.');
    await scrollTo(tester, goal);
    expect(find.text(l10n.openerGoal.toUpperCase()), findsOneWidget);

    // Back leaves nothing: it is the world's screen again, with the draft as it was.
    await tester.tap(find.byType(BackButton));
    await settle(tester, frames: 10);
    expect(find.text(l10n.reviewLeaveTitle), findsNothing);
    expect(find.text(l10n.reviewNext), findsOneWidget);
    expect(find.text('The Last Outer Disciple'), findsOneWidget);
    expect(app.sent('POST', (p) => p == '/v1/drafts'), hasLength(1));
  });

  for (final (language, heard) in [('es', 'es-ES'), ('ca', 'ca-ES')]) {
    testWidgets(
      'a draft is written, dictated and started in the app\'s language: $language (S10)',
      (tester) async {
        tester.platformDispatcher.localesTestValue = [Locale(language, 'ES')];
        addTearDown(tester.platformDispatcher.clearLocalesTestValue);
        final app = AppHarness();
        await app.launch(tester, location: '/create?premise=outer-disciple');
        final words = await AppLocalizations.delegate.load(Locale(language));

        await tester.tap(find.byType(MicButton).first);
        await tester.pump();
        expect(app.speech.listens.last.localeId, heard);
        await tester.tap(find.byTooltip(words.micStop));
        await tester.pump();

        await scrollTo(tester, find.text(words.createDraftAction));
        await tapAndSettle(tester, find.text(words.createDraftAction), frames: 12);
        expect(app.sent('POST', (p) => p == '/v1/drafts').single.json['language'], language);

        await toCharacter(tester, words);
        await tapAndSettle(tester, find.text(words.reviewStart), frames: 12);
        expect(find.byType(StoryScreen), findsOneWidget);
        final id = Uri.decodeComponent(app.location(tester).split('/').last);
        final story = app.backend.data.stories
            .ownedBy(FakeAuthState.demoUserId)
            .where((s) => s.id == id);
        expect(story.single.settings['language'], language);
      },
    );
  }

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
    // The review locks it too, and says when it opens.
    await scrollTo(tester, find.text(l10n.ratingMatureLocked));
    final mature = find.widgetWithText(ChoiceChip, l10n.ratingMature);
    expect(tester.widget<ChoiceChip>(mature).onSelected, isNull);
    await tester.tap(mature, warnIfMissed: false);
    await settle(tester);
    expect(app.sent('PATCH', (p) => p.startsWith('/v1/drafts/')), isEmpty);
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

    // A typed field is free, so it saves with no credits left.
    await toCharacter(tester);
    await tapAndSettle(tester, find.text(looks), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Short, with a broken nose.');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.save)));
    expect(find.byType(OutOfCreditsSheet), findsNothing);
    expect(find.text('Short, with a broken nose.'), findsOneWidget);

    // A change the storyteller makes is not.
    await toWorld(tester);
    await scrollTo(tester, find.text(factions));
    await tapAndSettle(tester, find.text(factions), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add a fourth, in hiding');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)));
    expect(find.byType(OutOfCreditsSheet), findsOneWidget);

    await addKeyInSheet(tester);
    final asked = app.sent('POST', (p) => p.endsWith('/revise'));
    expect(asked, hasLength(2));
    expect(asked.last.usesOwnKey, isTrue);
    expect(asked.last.json, asked.first.json);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text(l10n.reviewWorldRedrafted), findsOneWidget);
    expect(find.text('$factions A fourth, in hiding.'), findsOneWidget);
  });

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

  testWidgets('a failed change keeps the sheet open with what was written', (tester) async {
    final app = AppHarness();
    await app.launch(tester, location: '/create');
    await draft(tester);
    await scrollTo(tester, askWorld());
    await tapAndSettle(tester, askWorld(), frames: 6);
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
    await scrollTo(tester, askWorld());
    await tapAndSettle(tester, askWorld(), frames: 6);
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

    await scrollTo(tester, find.text(factions));
    await tapAndSettle(tester, find.text(factions), frames: 6);
    await tester.enterText(inSheet(find.byType(TextField)), 'Add a fourth, in hiding');
    await tester.pump();
    await tapAndSettle(tester, inSheet(find.text(l10n.reviseAction)), frames: 2);
    // The card says what is happening while its part is rewritten.
    expect(find.text(l10n.reviewRedraftingWorld), findsWidgets);
    // Closed by a tap above it just before the redrafted world comes back, which lands while
    // the sheet is still sliding away.
    await tester.pump(const Duration(milliseconds: 1850));
    await tester.tapAt(const Offset(195, 20));
    await settle(tester, frames: 12);
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.byType(CreateStoryScreen), findsOneWidget);
    expect(find.text(l10n.reviewTitle), findsOneWidget);
    expect(find.text('$factions A fourth, in hiding.'), findsOneWidget);
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
