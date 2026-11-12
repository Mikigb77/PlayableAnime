import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/story/sheet.dart';
import 'package:playable_anime/features/story/sheet_view.dart';
import 'package:playable_anime/features/story/status_screen.dart';
import 'package:playable_anime/features/story/story_models.dart';
import 'package:playable_anime/features/story/story_repository.dart';

import '../helpers.dart';
import 'harness.dart';

/// The character sheet (S5; G13, G16, G18): who they are, how they are and where they stand,
/// then what they carry, their skills, their techniques and what they are like, a tab at a time.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  /// Opens the seeded story, then its sheet, as a player does.
  Future<void> openSheet(WidgetTester tester) async {
    await AppHarness().launch(tester, location: '/story/story_ninth_peak');
    await tester.tap(find.byTooltip(l10n.storyStatus));
    await settle(tester, frames: 10);
  }

  /// The screen alone, on what a server answered.
  Future<void> show(WidgetTester tester, JsonMap status) async {
    usePhone(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [statusProvider('s').overrideWith((ref) async => StatusData.fromJson(status))],
        child: wrap(const StatusScreen(storyId: 's')),
      ),
    );
    await settle(tester);
  }

  Finder tab(SheetTab tab) => find.byKey(ValueKey('sheet.tab.${tab.name}'));

  Future<void> openTab(WidgetTester tester, SheetTab which) async {
    await tester.ensureVisible(tab(which));
    await tester.pump();
    await tester.tap(tab(which));
    await settle(tester);
  }

  JsonMap status({JsonMap? sheet, List<String> lines = const []}) => {
    'character': {'name': 'Mara', 'lines': lines},
    'sheet': ?sheet,
    'reputation': <Object?>[],
    'since': <Object?>[],
  };

  testWidgets('opens on who they are, how they are and where they stand', (tester) async {
    await openSheet(tester);
    expect(
      find.descendant(of: find.byType(AppBar), matching: find.text(l10n.statusTitle)),
      findsOneWidget,
    );
    expect(find.text('Shen Yu'), findsOneWidget);
    expect(find.text('Outer disciple, the Azure Cloud Sect · 17 years old'), findsOneWidget);
    expect(
      find.text('A thin disciple in a patched grey robe, calmer than his years.'),
      findsOneWidget,
    );

    // How they are: health, a wound, a passing state with when it ends, and what qi is left.
    expect(find.text('Hurt'), findsOneWidget);
    expect(find.text('Meridians cut in the duel'), findsOneWidget);
    expect(find.text('Short of sleep · Passes in 8 hours'), findsOneWidget);
    expect(find.byTooltip('Slower to react'), findsOneWidget);
    expect(find.text('Qi'), findsOneWidget);
    expect(find.text(l10n.sheetPercent(20)), findsOneWidget);

    // Their path: their own rung on top with its stage, the one they climbed under it.
    expect(find.text(l10n.sheetPath.toUpperCase()), findsOneWidget);
    expect(find.text('CULTIVATION REALMS'), findsOneWidget);
    expect(find.text('Third stage'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Qi Condensation')).dy,
      lessThan(tester.getTopLeft(find.text('Mortal')).dy),
    );
    expect(find.text('Reached, day 2'), findsOneWidget);
    expect(find.text('Left behind, day 2'), findsOneWidget);
    // Over it, what the story has named to them, highest first: what nobody has told them, a
    // realm they only heard of, the room nobody measured for them, and a realm confirmed.
    double top(String text) => tester.getTopLeft(find.text(text)).dy;
    final upward = [
      l10n.pathAbove,
      'Nascent Soul',
      l10n.pathUnmeasured,
      'Foundation Establishment',
      'Qi Condensation',
    ];
    for (final (i, name) in upward.indexed.skip(1)) {
      expect(top(upward[i - 1]), lessThan(top(name)), reason: '${upward[i - 1]} over $name');
    }
    expect(find.text(l10n.pathAboveNote), findsOneWidget);
    expect(find.text('Heard of, day 4'), findsOneWidget);
    expect(find.text(l10n.pathUnmeasuredNote), findsOneWidget);
    expect(find.text('Confirmed before Master Hu, day 3'), findsOneWidget);
    expect(find.text('Master Hu took a pill and sat nine days alone to reach it.'), findsOneWidget);

    // The same sheet as plain lines, sent for older apps, is not repeated under it.
    expect(
      find.text('Outer disciple of the Azure Cloud Sect, to be expelled at dawn.'),
      findsNothing,
    );
    // Where they stand with people and how long ago things happened still follow.
    expect(find.text('Azure Cloud Sect'), findsOneWidget);
    expect(find.text('A failure they would rather forget'), findsOneWidget);
    expect(find.text('3 months ago'), findsOneWidget);
  });

  testWidgets('shows what they carry first, then each part in its tab', (tester) async {
    await openSheet(tester);
    expect(find.text('3 spirit stones'), findsOneWidget);
    expect(find.text('Sealed scroll'), findsOneWidget);
    expect(find.text('TREASURE'), findsOneWidget);
    expect(find.text('It speaks, to you alone.'), findsOneWidget);
    expect(find.text('Found under the ninth peak.'), findsOneWidget);
    expect(find.text('Healing pills × 2'), findsOneWidget);
    // What they keep somewhere else comes after what is on them.
    expect(find.text(l10n.sheetElsewhere.toUpperCase()), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Wooden chest')).dy,
      greaterThan(tester.getTopLeft(find.text('Healing pills × 2')).dy),
    );
    expect(find.text('Swordsmanship'), findsNothing);

    await openTab(tester, SheetTab.skills);
    expect(find.text('Sealed scroll'), findsNothing);
    expect(find.text('Swordsmanship'), findsOneWidget);
    expect(find.text('Skilled · ${l10n.sheetDice(3)}'), findsOneWidget);
    expect(find.text('Fair · ${l10n.sheetDice(2)}'), findsOneWidget);
    expect(find.text('Learned gathering herbs for the pill hall.'), findsOneWidget);

    await openTab(tester, SheetTab.moves);
    expect(find.text('Swordsmanship'), findsNothing);
    expect(find.text('Falling Leaf Palm'), findsOneWidget);
    expect(find.text('Skilled · ${l10n.sheetDice(3)}'), findsOneWidget);
    expect(find.text('Azure Cloud style'), findsOneWidget);
    expect(find.text(l10n.sheetCost('a little qi')), findsOneWidget);
    expect(find.text(l10n.sheetUses(12, 30)), findsOneWidget);
    expect(find.text('Learned from Senior Sister Lan'), findsOneWidget);
    // With techniques alone the tab needs no label inside it.
    expect(find.text(l10n.sheetPowers.toUpperCase()), findsNothing);

    await openTab(tester, SheetTab.nature);
    expect(find.text('Quiet'), findsOneWidget);
    expect(find.text('Patient'), findsOneWidget);
    expect(find.text('A stubborn streak'), findsOneWidget);
    expect(find.text('QUIRK'), findsOneWidget);
    expect(find.text(l10n.sheetLearning.toUpperCase()), findsOneWidget);
    expect(find.text('The sword'), findsOneWidget);
    expect(find.text('GENIUS'), findsOneWidget);
    expect(find.text('Four times as fast'), findsOneWidget);
    expect(find.text('Anything fought with a blade'), findsOneWidget);
    expect(
      find.text('Falling Leaf Palm: grows twice as fast, close to your talent (The sword)'),
      findsOneWidget,
    );
  });

  testWidgets('tells how they grew, latest first, each gain with its day and how', (tester) async {
    await openSheet(tester);
    expect(find.text(l10n.sheetGrew.toUpperCase()), findsOneWidget);
    double top(String text) => tester.getTopLeft(find.text(text)).dy;
    final grew = [
      'Falling Leaf Palm: Skilled',
      'Herb lore: Fair',
      'Learned Falling Leaf Palm',
      'Broke through to Qi Condensation',
    ];
    // Under the tabs, the latest gain first.
    expect(top(grew.first), greaterThan(tester.getTopLeft(tab(SheetTab.carried)).dy));
    for (final (i, text) in grew.indexed.skip(1)) {
      expect(top(grew[i - 1]), lessThan(top(text)), reason: '${grew[i - 1]} over $text');
    }
    expect(find.text('Day 4 · By doing it'), findsOneWidget);
    expect(find.text('Day 3 · From a manual'), findsOneWidget);
    expect(find.text('Day 3 · With a master'), findsOneWidget);
    // A gain whose record says no more than the day shows the day alone.
    expect(find.text('Day 2'), findsOneWidget);
  });

  testWidgets('says nothing of growth where the record holds none', (tester) async {
    await show(
      tester,
      status(
        sheet: {
          'items': [
            {'name': 'Sword', 'kind': 'weapon', 'kind_label': 'Weapon'},
          ],
        },
      ),
    );
    expect(find.text('Sword'), findsOneWidget);
    expect(find.text(l10n.sheetGrew.toUpperCase()), findsNothing);
  });

  testWidgets('offers no tab for a part with nothing in it, and says when they carry nothing', (
    tester,
  ) async {
    await show(
      tester,
      status(
        sheet: {
          'condition': {'health': 'unhurt', 'health_label': 'Unhurt'},
          'skills': [
            {'name': 'Sailing', 'level_label': 'Fair', 'dice': 2},
          ],
        },
      ),
    );
    expect(find.text('Unhurt'), findsOneWidget);
    expect(tab(SheetTab.carried), findsOneWidget);
    expect(tab(SheetTab.skills), findsOneWidget);
    expect(tab(SheetTab.moves), findsNothing);
    expect(tab(SheetTab.nature), findsNothing);
    expect(find.text(l10n.sheetNothingCarried), findsOneWidget);
    // No ladder in this world, so no path.
    expect(find.text(l10n.sheetPath.toUpperCase()), findsNothing);
  });

  testWidgets('a path with nothing named above it still says nobody has told them', (tester) async {
    // Also what a server from before the rungs above sends: the rungs they climbed, no more.
    await show(
      tester,
      status(
        sheet: {
          'paths': [
            {
              'name': 'Aura ranks',
              'rungs': [
                {'name': 'Squire'},
                {'name': 'Knight', 'stage': 'first star'},
              ],
            },
          ],
        },
      ),
    );
    expect(find.text('AURA RANKS'), findsOneWidget);
    expect(find.text(l10n.pathAbove), findsOneWidget);
    expect(find.text(l10n.pathAboveNote), findsOneWidget);
    expect(find.text(l10n.pathUnmeasured), findsNothing);
    expect(
      tester.getTopLeft(find.text(l10n.pathAbove)).dy,
      lessThan(tester.getTopLeft(find.text('Knight')).dy),
    );
    expect(find.text('First star'), findsOneWidget);
  });

  testWidgets('a ladder they do not stand on shows the rungs they have heard of', (tester) async {
    // G18: the world's ladder beside their own way, as far as the story named it to them.
    await show(
      tester,
      status(
        sheet: {
          'paths': [
            {
              'name': 'Aura ranks',
              'rungs': <Object?>[],
              'above': [
                {'name': 'Squire', 'known': true, 'note': 'Confirmed before Zephyr, day 1'},
                {'name': 'Aura master', 'note': 'Heard of, day 2', 'gap_below': true},
              ],
            },
          ],
        },
      ),
    );
    expect(find.text(l10n.sheetPath.toUpperCase()), findsOneWidget);
    expect(find.text('Squire'), findsOneWidget);
    expect(find.text('Confirmed before Zephyr, day 1'), findsOneWidget);
    expect(find.text('Aura master'), findsOneWidget);
    expect(find.text(l10n.pathUnmeasured), findsOneWidget);
    // Nothing is lit: no rung of it is theirs.
    expect(
      find.byWidgetPredicate((widget) => '${widget.key}'.contains('path.here.')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('path.known.3')), findsOneWidget);
    expect(find.byKey(const ValueKey('path.heard.1')), findsOneWidget);
  });

  testWidgets('needs no tabs for belongings alone', (tester) async {
    await show(
      tester,
      status(
        sheet: {
          'money_label': '40 dollars',
          'items': [
            {'name': 'a house key', 'kind': 'gear', 'kind_label': 'Gear'},
          ],
        },
      ),
    );
    for (final each in SheetTab.values) {
      expect(tab(each), findsNothing);
    }
    expect(find.text(l10n.sheetCarried.toUpperCase()), findsOneWidget);
    expect(find.text('40 dollars'), findsOneWidget);
    // A name the world wrote as a sentence holds it reads as a title.
    expect(find.text('A house key'), findsOneWidget);
    expect(find.text('GEAR'), findsOneWidget);
    expect(find.text(l10n.sheetNothingCarried), findsNothing);
  });

  testWidgets('names the tab for powers where a world has no techniques', (tester) async {
    await show(
      tester,
      status(
        sheet: {
          'powers': [
            {
              'name': 'Time stop',
              'description': 'Stops the world for three heartbeats.',
              'limits': ['Three heartbeats a use'],
              'cost': 'Leaves you drained',
              'ready': false,
              'ready_label': 'Ready in 2 hours',
              'secret': true,
            },
          ],
        },
      ),
    );
    expect(find.text(l10n.sheetMoves), findsNothing);
    expect(
      find.descendant(of: tab(SheetTab.moves), matching: find.text(l10n.sheetPowers)),
      findsOneWidget,
    );

    await openTab(tester, SheetTab.moves);
    expect(find.text('Time stop'), findsOneWidget);
    expect(find.text('READY IN 2 HOURS'), findsOneWidget);
    expect(find.text('Stops the world for three heartbeats.'), findsOneWidget);
    expect(find.text('·  Three heartbeats a use'), findsOneWidget);
    expect(find.text(l10n.sheetCost('Leaves you drained')), findsOneWidget);
    expect(find.text(l10n.sheetSecret), findsOneWidget);
  });

  testWidgets('labels powers and techniques where a sheet has both', (tester) async {
    await show(
      tester,
      status(
        sheet: {
          'powers': [
            {'name': 'Time stop', 'ready_label': 'Ready'},
          ],
          'techniques': [
            // Second nature: use alone takes it no further, so no count is shown.
            {'name': 'Cloud Step', 'mastery_label': 'Second nature', 'dice': 4, 'uses': 80},
          ],
        },
      ),
    );
    expect(
      find.descendant(of: tab(SheetTab.moves), matching: find.text(l10n.sheetMoves)),
      findsOneWidget,
    );

    await openTab(tester, SheetTab.moves);
    expect(find.text(l10n.sheetPowers.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.sheetMoves.toUpperCase()), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Time stop')).dy,
      lessThan(tester.getTopLeft(find.text('Cloud Step')).dy),
    );
    expect(find.text('Second nature · ${l10n.sheetDice(4)}'), findsOneWidget);
    expect(find.textContaining('80'), findsNothing);
  });

  testWidgets('shows the plain lines of a server from before the sheet', (tester) async {
    await show(tester, status(lines: ['Unhurt', 'A house key']));
    expect(find.text('Mara'), findsOneWidget);
    expect(find.text('Unhurt'), findsOneWidget);
    expect(find.text('A house key'), findsOneWidget);
    for (final each in SheetTab.values) {
      expect(tab(each), findsNothing);
    }
    expect(find.text(l10n.sheetCarried.toUpperCase()), findsNothing);
    expect(find.text(l10n.statusEmpty), findsNothing);
  });

  testWidgets('says so when the server sent nothing to show', (tester) async {
    await show(tester, status());
    expect(find.text(l10n.statusEmpty), findsOneWidget);
  });

  testWidgets('a screen reader hears each skill once, with its dice in words', (tester) async {
    final handle = tester.ensureSemantics();
    await openSheet(tester);
    await openTab(tester, SheetTab.skills);
    expect(
      find.bySemanticsLabel(RegExp('^Swordsmanship\nSkilled · ${l10n.sheetDice(3)}\$')),
      findsOneWidget,
    );
    // The chosen tab says it is the chosen one.
    expect(
      tester.getSemantics(tab(SheetTab.skills)),
      isSemantics(isButton: true, isSelected: true, label: l10n.sheetSkills),
    );
    handle.dispose();
  });

  group('the sheet as the server sends it', () {
    test('reads each section', () {
      final sheet = Sheet.fromJson({
        'about': ['Outer disciple', ' ', '17 years old'],
        'description': ' Thin and calm. ',
        'condition': {
          'health': 'badly_wounded',
          'health_label': 'Badly wounded',
          'wounds': [
            {'text': 'A lost eye', 'lasting': true},
            {'text': 'A cut'},
          ],
          'states': [
            {'name': 'Drunk', 'effect': 'Clumsy', 'ends_label': 'Passes in 2 hours'},
            {'name': 'Rested'},
          ],
          'reserves': [
            {'name': 'Qi', 'level': 180},
          ],
          'expecting_label': 'A child due in 3 months',
        },
        'paths': [
          {
            'name': 'Realms',
            'rungs': [
              {'name': 'Mortal'},
              {'name': 'Qi Condensation', 'stage': 'third stage'},
            ],
          },
          {'name': 'Ranks', 'rungs': <Object?>[]},
          {
            'name': 'Guild',
            'above': [
              {
                'name': 'A',
                'known': true,
                'note': 'Confirmed, day 3',
                'said': ['Only six hold it.', 7],
                'gap_below': true,
              },
              {'name': 'S'},
              {'name': ' '},
            ],
          },
        ],
        'money_label': '12 taels',
        'items': [
          {'name': 'Sword', 'kind': 'weapon', 'kind_label': 'Weapon'},
          {'name': 'Chest', 'kind': 'furniture', 'carried': false, 'quantity': 2},
          {'name': ''},
        ],
        'skills': [
          {'name': 'Sword', 'level_label': 'Skilled', 'dice': 3},
        ],
        'powers': [
          {'name': 'Time stop', 'ready': false, 'ready_label': 'Ready in 2 hours'},
        ],
        'techniques': [
          {'name': 'Palm', 'mastery_label': 'Learning', 'dice': 1, 'uses': 2, 'need': 6},
          {'name': 'Step', 'need': 0},
        ],
        'traits': [
          {'name': 'Old soul', 'kind': 'gift', 'kind_label': 'Gift'},
          {'name': 'Odd', 'kind': 'curse'},
        ],
        'temperament': ['calm'],
        'talents': [
          {'name': 'The sword', 'strength': 'genius', 'strength_label': 'Genius'},
          {'name': 'Haggling', 'strength': 'slow', 'strength_label': 'Weakness'},
        ],
        'talent_notes': ['Palm: grows twice as fast'],
        'grew': [
          {'kind': 'learned', 'when': 'Day 9', 'text': 'Learned Step', 'how': 'By watching'},
          {'kind': 'breakthrough', 'when': 'Day 2', 'text': 'Broke through to Qi Condensation'},
          {'kind': 'skill', 'when': 'Day 1', 'text': ' '},
          'odd',
        ],
      });
      expect(sheet.about, ['Outer disciple', '17 years old']);
      expect(sheet.description, 'Thin and calm.');
      expect(sheet.condition.health, Health.badlyWounded);
      expect([for (final wound in sheet.condition.wounds) wound.lasting], [true, false]);
      expect(sheet.condition.states.first.endsLabel, 'Passes in 2 hours');
      expect(sheet.condition.states.last.endsLabel, isNull);
      // A share is never over the whole.
      expect(sheet.condition.reserves.single.level, 100);
      expect(sheet.condition.expectingLabel, 'A child due in 3 months');
      // A ladder with no rung to stand on and none heard of is not a path.
      expect([for (final path in sheet.paths) path.name], ['Realms', 'Guild']);
      expect(sheet.paths.first.rungs.last.stage, 'third stage');
      expect(sheet.paths.first.rungs.last.note, isEmpty);
      expect(sheet.paths.first.above, isEmpty);
      // One they only heard of holds its rungs above: confirmed or not, with what was said.
      final guild = sheet.paths.last;
      expect(guild.rungs, isEmpty);
      expect([for (final rung in guild.above) rung.name], ['A', 'S']);
      expect([for (final rung in guild.above) rung.known], [true, false]);
      expect([for (final rung in guild.above) rung.gapBelow], [true, false]);
      expect(guild.above.first.note, 'Confirmed, day 3');
      expect(guild.above.first.said, ['Only six hold it.']);
      expect(sheet.moneyLabel, '12 taels');
      // A thing with no name is dropped, and a kind the app doesn't know is just a thing.
      expect([for (final item in sheet.items) item.kind], [ItemKind.weapon, ItemKind.other]);
      expect(sheet.carried.single.name, 'Sword');
      expect(sheet.elsewhere.single.quantity, 2);
      expect(sheet.skills.single.dice, 3);
      expect(sheet.powers.single.ready, isFalse);
      // No count where use alone takes a technique no further.
      expect([for (final t in sheet.techniques) t.need], [6, null]);
      expect([for (final trait in sheet.traits) trait.kind], [TraitKind.gift, TraitKind.quirk]);
      expect([for (final talent in sheet.talents) talent.weakness], [false, true]);
      expect(sheet.hasMoves, isTrue);
      expect(sheet.hasNature, isTrue);
      // How they grew, latest first: a gain with no words is dropped.
      expect(
        [for (final gain in sheet.grew) gain.text],
        ['Learned Step', 'Broke through to Qi Condensation'],
      );
      expect([for (final gain in sheet.grew) gain.isBreakthrough], [false, true]);
      expect((sheet.grew.first.when, sheet.grew.first.how), ('Day 9', 'By watching'));
      expect(sheet.grew.last.how, isEmpty);
    });

    test('reads an empty sheet, and one with parts it does not expect', () {
      final empty = Sheet.fromJson(const {});
      expect(empty.condition.health, Health.unhurt);
      expect(empty.moneyLabel, isNull);
      expect(empty.items, isEmpty);
      expect(empty.hasMoves, isFalse);
      expect(empty.hasNature, isFalse);
      expect(empty.grew, isEmpty);

      final odd = Sheet.fromJson({
        'condition': 'fine',
        'paths': 'none',
        'items': [3, 'sword'],
        'money_label': ' ',
      });
      expect(odd.condition.health, Health.unhurt);
      expect(odd.paths, isEmpty);
      expect(odd.items, isEmpty);
      expect(odd.moneyLabel, isNull);
      // A health the app doesn't know still reads as hurt, never as fine.
      expect(Health.parse('cursed'), Health.hurt);
    });

    test('a status with no sheet keeps its plain lines', () {
      final old = StatusData.fromJson({
        'character': {
          'name': 'Mara',
          'lines': ['Unhurt'],
        },
      });
      expect(old.sheet, isNull);
      expect(old.lines, ['Unhurt']);
      final now = StatusData.fromJson({
        'character': {
          'name': 'Mara',
          'lines': ['Unhurt'],
        },
        'sheet': <String, dynamic>{},
      });
      expect(now.sheet, isNotNull);
    });
  });
}
