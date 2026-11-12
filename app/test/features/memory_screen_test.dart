import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/story/memory.dart';
import 'package:playable_anime/features/story/memory_screen.dart';
import 'package:playable_anime/features/story/record_widgets.dart';

import '../helpers.dart';
import 'harness.dart';

/// Memory (C6, G16): only what the character knows, in the world's words, a group at a time.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  /// A window tall enough for the whole page, so a test reads it without scrolling.
  Future<void> unroll(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 3600);
    await tester.pump();
  }

  /// Opens the story, then its memory, as a player does.
  Future<void> openMemory(WidgetTester tester, AppHarness app, {bool whole = true}) async {
    await app.launch(tester, location: '/story/story_ninth_peak');
    await tester.tap(find.byTooltip(l10n.storyMemory));
    await settle(tester, frames: 10);
    if (whole) await unroll(tester);
  }

  /// The screen alone, on what a server answered.
  Future<void> show(WidgetTester tester, JsonMap memory) async {
    usePhone(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [memoryProvider('s').overrideWith((ref) async => MemoryView.fromJson(memory))],
        child: wrap(const MemoryScreen(storyId: 's')),
      ),
    );
    await settle(tester);
    await unroll(tester);
  }

  LucidColors colorsOf(WidgetTester tester) =>
      Theme.of(tester.element(find.byType(RecordEntry).first)).extension<LucidColors>()!;

  testWidgets('opens on what they are after, then who they know and what they heard', (
    tester,
  ) async {
    await openMemory(tester, AppHarness());
    expect(find.text(l10n.memoryTitle), findsOneWidget);
    expect(find.text(l10n.memoryYou.toUpperCase()), findsOneWidget);
    expect(find.text('Shen Yu'), findsOneWidget);
    expect(find.text('Carries a sealed scroll that speaks.'), findsOneWidget);

    // What they are after leads: the thread they follow, their own goals, what is on offer
    // and until when, and the story's threads still running.
    expect(find.text(l10n.memoryObjectives.toUpperCase()), findsOneWidget);
    expect(find.text(l10n.memoryFollowed.toUpperCase()), findsOneWidget);
    expect(find.text('Find out who is stealing from the pill hall'), findsOneWidget);
    expect(find.text('Find out who cut your meridians'), findsOneWidget);
    expect(find.text(l10n.memoryLeads.toUpperCase()), findsOneWidget);
    expect(find.text('Ends in 2 hours'), findsOneWidget);
    expect(find.text(l10n.memoryThreads.toUpperCase()), findsOneWidget);
    expect(
      tester.getTopLeft(find.text(l10n.memoryFollowed.toUpperCase())).dy,
      lessThan(tester.getTopLeft(find.text(l10n.memoryThreads.toUpperCase())).dy),
    );

    // People, each with how they take the character.
    expect(
      find.descendant(
        of: find.widgetWithText(RecordEntry, 'Senior Sister Lan'),
        matching: find.widgetWithText(RecordChip, 'Warm'),
      ),
      findsOneWidget,
    );

    // A rumor says what the character knows of it, and a deed who saw it.
    expect(
      find.descendant(
        of: find.widgetWithText(RecordEntry, 'Elder Wen once studied forbidden arts'),
        matching: find.widgetWithText(RecordChip, l10n.memoryUnconfirmed),
      ),
      findsOneWidget,
    );
    expect(find.text('Heard 3 days ago'), findsOneWidget);
    expect(find.text('You stole a sealed scroll from the forbidden library'), findsOneWidget);
    expect(find.text('Day 1, dawn'), findsOneWidget);
    expect(find.text('No one saw, as far as you know'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('goals show by where they stand: followed, their own, on the side, done', (
    tester,
  ) async {
    await openMemory(tester, AppHarness());
    double top(String text) => tester.getTopLeft(find.text(text)).dy;
    Finder fold(String name) => find.byKey(ValueKey('memory.$name'));
    Finder within(String entry, String text) =>
        find.descendant(of: find.widgetWithText(RecordEntry, entry), matching: find.text(text));

    // The thread they follow leads, lit, with where it stands and where it came from.
    const followed = 'Find out who is stealing from the pill hall';
    expect(top(followed), lessThan(top('Find out who cut your meridians')));
    expect(
      within(followed, 'It happens at night, and the east gate guard looks away.'),
      findsOneWidget,
    );
    expect(within(followed, 'Asked of you by Master Hu, day 3'), findsOneWidget);
    RecordGlyph glyph(String entry) => tester.widget(
      find.descendant(
        of: find.widgetWithText(RecordEntry, entry),
        matching: find.byType(RecordGlyph),
      ),
    );
    expect(glyph(followed).lit, isTrue);
    expect(glyph('Find out who cut your meridians').lit, isFalse);

    // Their own are open under their fold, with how many.
    expect(find.descendant(of: fold('own'), matching: find.text(l10n.memoryOwn)), findsOneWidget);
    expect(find.descendant(of: fold('own'), matching: find.text('1')), findsOneWidget);
    expect(within('Find out who cut your meridians', 'Yours from the start'), findsOneWidget);

    // The ones on the side and the ones that are over wait until asked for.
    expect(find.descendant(of: fold('side'), matching: find.text(l10n.memorySide)), findsOneWidget);
    expect(find.text('Bring Old Gu his moon-root'), findsNothing);
    await tester.tap(fold('side'));
    await settle(tester);
    expect(within('Bring Old Gu his moon-root', 'Asked of you by Old Gu, day 2'), findsOneWidget);

    expect(find.descendant(of: fold('done'), matching: find.text('2')), findsOneWidget);
    expect(find.text('Pass the outer disciple test'), findsNothing);
    await tester.tap(fold('done'));
    await settle(tester);
    // The latest to close leads, each with how it ended and the day.
    expect(top('Win the outer court ranking'), lessThan(top('Pass the outer disciple test')));
    expect(within('Pass the outer disciple test', l10n.goalAchieved.toUpperCase()), findsOneWidget);
    expect(within('Pass the outer disciple test', 'Day 2'), findsOneWidget);
    expect(within('Win the outer court ranking', l10n.threadFailed.toUpperCase()), findsOneWidget);

    // Their own fold shuts too.
    await tester.tap(fold('own'));
    await settle(tester);
    expect(find.text('Find out who cut your meridians'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('goals from a server before kinds show as their own, open', (tester) async {
    await show(tester, const {
      'goals': [
        {'id': 'g1', 'text': 'Get home'},
      ],
    });
    expect(find.text(l10n.memoryOwn), findsOneWidget);
    expect(find.text('Get home'), findsOneWidget);
    expect(find.text(l10n.memoryFollowed.toUpperCase()), findsNothing);
  });

  testWidgets('the goals on the side show when they are all the character is after', (
    tester,
  ) async {
    await show(tester, const {
      'goals': [
        {
          'id': 'g1',
          'text': 'Carry the parcel',
          'kind': 'side',
          'origin_label': 'A lead you took up',
        },
      ],
    });
    expect(find.text('Carry the parcel'), findsOneWidget);
    expect(find.text('A lead you took up'), findsOneWidget);
  });

  testWidgets('the threads that ended stay folded away until asked for', (tester) async {
    await openMemory(tester, AppHarness());
    final fold = find.byKey(const ValueKey('memory.closed'));
    expect(find.descendant(of: fold, matching: find.text(l10n.memoryClosed)), findsOneWidget);
    expect(find.descendant(of: fold, matching: find.text('1')), findsOneWidget);
    expect(find.text('The ranking of the outer court'), findsNothing);

    await tester.tap(fold);
    await settle(tester);
    expect(find.text('The ranking of the outer court'), findsOneWidget);
    expect(find.text(l10n.threadFailed.toUpperCase()), findsOneWidget);

    await tester.tap(fold);
    await settle(tester);
    expect(find.text('The ranking of the outer court'), findsNothing);
  });

  testWidgets('a filter shows one group at a time', (tester) async {
    await openMemory(tester, AppHarness());
    // The chips scroll sideways, so the one wanted is brought into view.
    final places = find.widgetWithText(ChoiceChip, '${l10n.memoryPlaces} 2');
    await tester.ensureVisible(places);
    await tester.pump();
    await tester.tap(places);
    await settle(tester);
    expect(find.text('The forbidden library'), findsOneWidget);
    expect(find.text('Find out who cut your meridians'), findsNothing);
    expect(tester.widget<ChoiceChip>(places).selected, isTrue);

    final all = find.widgetWithText(ChoiceChip, l10n.memoryAll);
    await tester.ensureVisible(all);
    await tester.pump();
    await tester.tap(all);
    await settle(tester);
    expect(find.text('Find out who cut your meridians'), findsOneWidget);
  });

  testWidgets('among the others a group shows its first few, and the rest when asked', (
    tester,
  ) async {
    await openMemory(tester, AppHarness());
    // The story knows six people. Five show, with a way to them all.
    final more = find.byKey(const ValueKey('memory.more.people'));
    expect(find.text(l10n.memoryShowAll(6)), findsOneWidget);
    expect(find.text('Zhao Kun'), findsOneWidget);
    expect(find.text('Master Hu'), findsNothing);

    await tester.tap(more);
    await settle(tester);
    expect(more, findsNothing);
    // Someone believed dead says so after their name, and no longer how they took you.
    expect(find.text('PRESUMED DEAD'), findsOneWidget);

    // Alone, a group shows everyone from the start.
    final people = find.widgetWithText(ChoiceChip, '${l10n.memoryPeople} 6');
    // The chips scroll sideways, so the one wanted is brought into view.
    await tester.ensureVisible(people);
    await tester.pump();
    await tester.tap(people);
    await settle(tester);
    expect(tester.widget<ChoiceChip>(people).selected, isTrue);
    expect(find.byKey(const ValueKey('memory.more.people')), findsNothing);
  });

  testWidgets('the latest thing heard or done leads its group', (tester) async {
    await show(tester, {
      'character': {'name': 'Mara', 'lines': <String>[]},
      'rumors': [
        for (final (i, text) in ['An old tale', 'Fresh talk'].indexed)
          {'id': 'r$i', 'text': text, 'heard_label': 'Heard', 'certainty': 'unconfirmed'},
      ],
    });
    expect(
      tester.getTopLeft(find.text('Fresh talk')).dy,
      lessThan(tester.getTopLeft(find.text('An old tale')).dy),
    );
    // One group needs no filter, and shows all it holds.
    expect(find.byType(ChoiceChip), findsNothing);
  });

  testWidgets('a word is colored by the value beside it, in any language', (tester) async {
    await show(tester, {
      'character': {'name': 'Mara', 'lines': <String>[]},
      'people': [
        {
          'id': 'p1',
          'name': 'Bruno',
          'attitude': 'hostile',
          'attitude_label': 'Hostil',
          'status': 'alive',
          'status_label': 'Con vida',
        },
        {
          'id': 'p2',
          'name': 'Carla',
          'attitude': 'warm',
          'attitude_label': 'Cordial',
          'status': 'missing',
          'status_label': 'En paradero desconocido',
        },
        {
          'id': 'p3',
          'name': 'Dario',
          'attitude': 'friendly',
          'attitude_label': 'Afable',
          'status': 'dead',
          'status_label': 'Ha muerto',
        },
      ],
      'factions': [
        {
          'id': 'f1',
          'name': 'La Guardia',
          'esteem': 'respected',
          'dread': 'feared',
          'standing_label': 'Respeto y temor',
        },
        {
          'id': 'f2',
          'name': 'Los Cuervos',
          'esteem': 'neutral',
          'dread': 'wary',
          'standing_label': 'Cautela',
        },
        {'id': 'f3', 'name': 'El Gremio', 'standing_label': 'Neutral'},
      ],
    });
    final colors = colorsOf(tester);
    RecordChip chip(String text) => tester.widget(find.widgetWithText(RecordChip, text));

    expect(chip('Hostil').tone, colors.danger);
    expect(chip('Cordial').tone, colors.success);
    // The living say nothing of it. Someone missing does, and the dead are struck through.
    expect(find.text('CON VIDA'), findsNothing);
    expect(find.text('EN PARADERO DESCONOCIDO'), findsOneWidget);
    expect(find.text('HA MUERTO'), findsOneWidget);
    expect(find.text('Afable'), findsNothing);
    expect(tester.widget<Text>(find.text('Dario')).style!.decoration, TextDecoration.lineThrough);

    expect(chip('Respeto y temor').tone, colors.success);
    expect(chip('Cautela').tone, colors.caution);
    expect(chip('Neutral').tone, isNull);
  });

  testWidgets('a romance leads their lines under a heart for where it stands (W17)', (
    tester,
  ) async {
    JsonMap person(String name, {String? bond, String? line, String status = 'alive'}) => {
      'id': name,
      'name': name,
      'lines': ['About $name.'],
      'status': status,
      'status_label': switch (status) {
        'alive' => 'Alive',
        'dead' => 'Dead',
        _ => 'Missing',
      },
      'bond': bond,
      'bond_line': line,
    };
    await show(tester, {
      'character': {'name': 'Tomas', 'lines': <String>[]},
      'people': [
        person('Mara', bond: 'married', line: 'You married, day 40.'),
        person('Nell', bond: 'interest', line: 'You made your interest plain, day 3.'),
        person('Odile', bond: 'over', line: 'You were a couple until you ended it, day 9.'),
        person('Piet', bond: 'courting', line: 'You began courting, day 5.', status: 'missing'),
        person('Quin', bond: 'over', line: 'You were married until their death.', status: 'dead'),
        // A stage from a newer server still tells its line.
        person('Rhea', bond: 'eloped', line: 'You eloped, day 2.'),
        person('Sam'),
      ],
    });
    final colors = colorsOf(tester);
    Finder within(String name, Finder what) => find.descendant(
      of: find.ancestor(of: find.text(name), matching: find.byType(RecordEntry)),
      matching: what,
    );
    Icon heart(String name) => tester.widget(
      within(
        name,
        find.byWidgetPredicate(
          (w) =>
              w is Icon &&
              (w.icon == Icons.favorite ||
                  w.icon == Icons.favorite_border ||
                  w.icon == Icons.heart_broken_outlined),
        ),
      ),
    );
    Color? ink(String line) => tester.widget<Text>(find.text(line)).style!.color;

    // A couple: a whole heart, in the accent, above who they are.
    expect((heart('Mara').icon, heart('Mara').color), (Icons.favorite, colors.accent));
    expect(ink('You married, day 40.'), colors.accent);
    expect(
      tester.getTopLeft(find.text('You married, day 40.')).dy,
      lessThan(tester.getTopLeft(find.text('About Mara.')).dy),
    );
    // Only starting: an outline.
    expect((heart('Nell').icon, heart('Nell').color), (Icons.favorite_border, colors.accent));
    expect(heart('Piet').icon, Icons.favorite_border);
    expect(within('Piet', find.text('MISSING')), findsOneWidget);
    expect(heart('Rhea').icon, Icons.favorite_border);
    // Ended by one of them: a broken heart, quiet.
    expect(
      (heart('Odile').icon, heart('Odile').color),
      (Icons.heart_broken_outlined, colors.textMuted),
    );
    expect(ink('You were a couple until you ended it, day 9.'), colors.textMuted);
    // Ended by a death: quiet, and nothing broke it.
    expect((heart('Quin').icon, heart('Quin').color), (Icons.favorite_border, colors.textMuted));
    expect(find.text('You were married until their death.'), findsOneWidget);
    // Someone with no romance has no heart.
    expect(
      within('Sam', find.byWidgetPredicate((w) => w is Icon && w.icon == Icons.favorite_border)),
      findsNothing,
    );
    expect(find.byIcon(Icons.favorite), findsOneWidget);
    expect(find.byIcon(Icons.favorite_border), findsNWidgets(4));
    expect(find.byIcon(Icons.heart_broken_outlined), findsOneWidget);
  });

  testWidgets('a deed says who saw it, and how someone else\'s reached them', (tester) async {
    await show(tester, {
      'character': {'name': 'Mara', 'lines': <String>[]},
      'deeds': [
        for (final (seen, known) in [
          ('unseen', 'No one saw, as far as you know'),
          ('seen', 'Seen by Bruno'),
          ('public', 'Done in public'),
          ('watched', 'You saw it'),
          ('heard_of', 'You heard of it'),
        ])
          {
            'id': seen,
            'text': 'Deed $seen',
            'when_label': 'Day 2',
            'seen': seen,
            'known_label': known,
          },
      ],
    });
    final colors = colorsOf(tester);
    Color? colorOf(String text) => tester.widget<Text>(find.text(text)).style!.color;
    IconData glyphOf(String deed) => tester
        .widget<Icon>(
          find.descendant(
            of: find.widgetWithText(RecordEntry, deed),
            matching: find.descendant(of: find.byType(RecordGlyph), matching: find.byType(Icon)),
          ),
        )
        .icon!;

    // Their own deed that someone saw is lit. One nobody saw stays quiet.
    expect(colorOf('Seen by Bruno'), colors.accent);
    expect(colorOf('Done in public'), colors.accent);
    expect(colorOf('No one saw, as far as you know'), colors.textMuted);
    expect(glyphOf('Deed seen'), Icons.history_edu_outlined);
    expect(glyphOf('Deed watched'), Icons.visibility_outlined);
    expect(glyphOf('Deed heard_of'), Icons.hearing_outlined);
  });

  testWidgets('a deed tells what became of it, as far as they know', (tester) async {
    await show(tester, {
      'character': {'name': 'Mara', 'lines': <String>[]},
      'deeds': [
        {
          'id': 'd1',
          'text': 'You shoved Zhao into the well',
          'when_label': 'Day 2',
          'seen': 'seen',
          'known_label': 'Seen by Wei',
          'trail': [
            {'kind': 'went', 'text': 'Wei went to tell the Azure Cloud Sect'},
            {'kind': 'dead', 'text': 'Wei is dead'},
            {'kind': 'heard', 'text': 'Heard a day ago: “Someone shoved Zhao into the well”'},
            {'kind': 'came', 'text': 'Zhao Mei came to face you over it, an hour ago'},
            {'kind': 'sung', 'text': 'A song is sung of it'},
            {'kind': 'went', 'text': '  '},
          ],
          'open_label': 'Who else knows? You can\'t tell until you hear it.',
        },
        {'id': 'd2', 'text': 'You bowed', 'when_label': 'Day 1', 'known_label': 'You were seen'},
      ],
    });
    final colors = colorsOf(tester);
    Color? colorOf(String text) => tester.widget<Text>(find.text(text)).style!.color;
    IconData markOf(String text) => tester
        .widget<Icon>(
          find.descendant(
            of: find.ancestor(of: find.text(text), matching: find.byType(Row)).first,
            matching: find.byType(Icon),
          ),
        )
        .icon!;

    // Word on its way and someone at the door are lit. The rest is told quietly.
    expect(colorOf('Wei went to tell the Azure Cloud Sect'), colors.caution);
    expect(markOf('Wei went to tell the Azure Cloud Sect'), Icons.directions_run_rounded);
    expect(colorOf('Zhao Mei came to face you over it, an hour ago'), colors.accent);
    expect(colorOf('Wei is dead'), colors.textMuted);
    expect(markOf('Heard a day ago: “Someone shoved Zhao into the well”'), Icons.hearing_outlined);
    // A kind this app doesn't know still says its words, and an empty line says nothing.
    expect(find.text('A song is sung of it'), findsOneWidget);
    expect(colorOf('Who else knows? You can\'t tell until you hear it.'), colors.textMuted);
    expect(
      markOf('Who else knows? You can\'t tell until you hear it.'),
      Icons.help_outline_rounded,
    );
    // In the order it happened, under who saw it.
    final lines = [
      for (final text in tester.widgetList<Text>(
        find.descendant(
          of: find.widgetWithText(RecordEntry, 'You shoved Zhao into the well'),
          matching: find.byType(Text),
        ),
      ))
        text.data,
    ];
    expect(lines, [
      'You shoved Zhao into the well',
      'Day 2',
      'Seen by Wei',
      'Wei went to tell the Azure Cloud Sect',
      'Wei is dead',
      'Heard a day ago: “Someone shoved Zhao into the well”',
      'Zhao Mei came to face you over it, an hour ago',
      'A song is sung of it',
      'Who else knows? You can\'t tell until you hear it.',
    ]);
    expect(tester.takeException(), isNull);
  });

  testWidgets('reads what a server from before the values sent', (tester) async {
    await show(tester, {
      'character': {'name': 'Mara', 'lines': <String>[]},
      'people': [
        {'id': 'p1', 'name': 'Bruno', 'attitude_label': 'Friendly', 'status_label': 'Alive'},
        {'id': 'p2', 'name': 'Carla', 'status_label': 'Presumed dead'},
      ],
      'factions': [
        {'id': 'f1', 'name': 'The Watch', 'standing_label': 'Respected and feared'},
      ],
      'deeds': [
        {'id': 'd1', 'text': 'You ran', 'when_label': 'Day 2', 'known_label': 'You were seen'},
      ],
    });
    RecordChip chip(String text) => tester.widget(find.widgetWithText(RecordChip, text));
    // The words are all there. Without a value beside them they stay quiet.
    expect(chip('Friendly').tone, isNull);
    expect(chip('Respected and feared').tone, isNull);
    expect(find.text('PRESUMED DEAD'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a screen reader hears each entry in one breath', (tester) async {
    final handle = tester.ensureSemantics();
    await openMemory(tester, AppHarness());
    expect(
      find.bySemanticsLabel(
        RegExp(r'^Senior Sister Lan\s+Warm\s+The only one who visited you after the duel\.$'),
      ),
      findsOneWidget,
    );
    // The fold says what it is and which way it is turned.
    final fold = find.byKey(const ValueKey('memory.closed'));
    expect(
      tester.getSemantics(find.ancestor(of: fold, matching: find.byType(Semantics)).first),
      isSemantics(
        label: '${l10n.memoryClosed}\n1',
        isButton: true,
        hasExpandedState: true,
        isExpanded: false,
      ),
    );
    handle.dispose();
  });

  testWidgets('a story just begun knows only its character', (tester) async {
    final app = AppHarness();
    await app.signIn();
    final tokens = TestTokens(app.store.value!.accessToken);
    final api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: app.backend, tokens: tokens);
    final draft = await api.post('/v1/drafts', {'premise_id': 'outer-disciple', 'rating': 'teen'});
    final started = await api.post('/v1/drafts/${(draft as Map)['id']}/start', {}) as Map;

    await app.launch(tester, location: '/story/${started['story_id']}/memory');
    expect(find.text('Lin Feng'), findsOneWidget);
    expect(find.text(l10n.memoryEmptyTitle), findsOneWidget);
    expect(find.byType(ChoiceChip), findsNothing);
  });

  group('MemoryView.fromJson', () {
    MemoryPerson person(JsonMap json) => MemoryPerson.fromJson({'id': 'p', 'name': 'P', ...json});

    test('reads a fate from the value the server sends, in any language', () {
      expect(person({'status': 'alive', 'status_label': 'Con vida'}).fate, Fate.alive);
      expect(person({'status': 'dead', 'status_label': 'Ha muerto'}).fate, Fate.dead);
      expect(
        person({'status': 'dead', 'presumed': true, 'status_label': 'Se cree que ha muerto'}).fate,
        Fate.presumedDead,
      );
      expect(person({'status': 'missing', 'status_label': 'Missing'}).fate, Fate.other);
    });

    test('reads a fate from the words of a server from before the value', () {
      expect(person({'status_label': 'Alive'}).fate, Fate.alive);
      expect(person({'status_label': 'Dead'}).fate, Fate.dead);
      expect(person({'status_label': 'Presumed dead'}).fate, Fate.presumedDead);
      expect(person({'status_label': 'Bound to the scroll'}).fate, Fate.other);
    });

    test('reads where a romance stands, and keeps the line of a stage it doesn\'t know', () {
      final courting = person({'bond': 'courting', 'bond_line': 'Us esteu coneixent.'});
      expect((courting.bond, courting.bondLine), (BondStage.courting, 'Us esteu coneixent.'));
      expect(courting.bond!.couple, isFalse);
      expect(
        [
          for (final stage in BondStage.values)
            if (stage.couple) stage,
        ],
        [BondStage.together, BondStage.promised, BondStage.married],
      );
      final newer = person({'bond': 'eloped', 'bond_line': 'You eloped, day 2.'});
      expect((newer.bond, newer.bondLine), (null, 'You eloped, day 2.'));
      // Someone with no romance has neither, as from a server older than it.
      expect((person({}).bond, person({}).bondLine), (null, null));
      expect(person({'bond': null, 'bond_line': null}).bondLine, isNull);
    });

    test('reads how people and factions take the character, and nothing it doesn\'t know', () {
      expect(person({'attitude': 'cold'}).attitude, Attitude.cold);
      expect(person({'attitude': 'smitten'}).attitude, isNull);
      expect(person({}).attitude, isNull);

      MemoryFaction faction(JsonMap json) =>
          MemoryFaction.fromJson({'id': 'f', 'name': 'F', ...json});
      expect(faction({'esteem': 'admired'}).esteem.good, isTrue);
      expect(faction({'esteem': 'despised'}).esteem.bad, isTrue);
      expect(faction({'esteem': 'adored'}).esteem, Esteem.neutral);
      expect(faction({'dread': 'wary'}).feared, isTrue);
      expect(faction({'dread': 'none'}).feared, isFalse);
      expect(faction({}).feared, isFalse);
    });

    test('keeps only groups with something in them, in reading order', () {
      final view = MemoryView.fromJson(const {
        'character': {'name': 'Ada', 'lines': <String>[]},
        'people': [
          {'id': 'p1', 'name': 'Bo', 'status_label': 'Alive'},
        ],
        'leads': [
          {'id': 'l1', 'text': 'The tide turns at noon', 'expires_label': 'Ends in 2 hours'},
        ],
        'threads': [
          {'id': 't1', 'title': 'The door', 'status': 'resolved_without_player'},
          {'id': 't2', 'title': 'The bell', 'status': 'something_new'},
        ],
      });
      // What they are after holds their goals, the leads and the story's threads.
      expect(view.sections, [MemorySection.objectives, MemorySection.people]);
      expect(view.count(MemorySection.objectives), 3);
      expect(view.goalsDone, isEmpty);
      expect(view.leads.single.expiresLabel, 'Ends in 2 hours');
      expect(view.closedThreads.single.status, ThreadStatus.resolvedWithoutPlayer);
      // A state this app doesn't know is still a thread that runs.
      expect(view.openThreads.single.status, ThreadStatus.open);
    });

    test('reads where a goal shows, where it came from and how one that is over ended', () {
      final view = MemoryView.fromJson(const {
        'goals': [
          {
            'id': 'g2',
            'text': 'Who robs the till',
            'kind': 'followed',
            'origin_label': 'Asked of you by Carmine, day 3',
            'progress': 'It happens at night.',
          },
          {'id': 'g1', 'text': 'Leave Naples', 'kind': 'own', 'origin_label': ' ', 'progress': ''},
          {'id': 'g3', 'text': 'The old ledger', 'kind': 'side'},
          {'id': 'g4', 'text': 'A kind from a later server', 'kind': 'sworn'},
        ],
        'goals_done': [
          {'id': 'g5', 'text': 'Save Rosa', 'how': 'achieved', 'when_label': 'Day 2'},
          {'id': 'g6', 'text': 'Keep the bar', 'how': 'failed'},
          {'id': 'g7', 'text': 'Find the priest', 'how': 'something_new'},
        ],
      });
      expect(
        [for (final g in view.goals) g.kind],
        [GoalKind.followed, GoalKind.own, GoalKind.side, GoalKind.own],
      );
      final followed = view.goalsOf(GoalKind.followed).single;
      expect(followed.originLabel, 'Asked of you by Carmine, day 3');
      expect(followed.progress, 'It happens at night.');
      expect(view.goals[1].originLabel, isNull);
      expect(view.goals[1].progress, isNull);
      expect(
        [for (final g in view.goalsDone) g.how],
        [GoalEnd.achieved, GoalEnd.failed, GoalEnd.abandoned],
      );
      expect(view.goalsDone.first.whenLabel, 'Day 2');
      expect(view.goalsDone.last.whenLabel, isNull);
      // The goals that are over count among what the character is after.
      expect(view.count(MemorySection.objectives), 7);
    });

    test('says what the character knows of each rumor, unconfirmed from an older server', () {
      final view = MemoryView.fromJson(const {
        'rumors': [
          {'id': 'r1', 'text': 'A', 'heard_label': 'Heard today', 'certainty': 'confirmed'},
          {'id': 'r2', 'text': 'B', 'heard_label': 'Heard today', 'certainty': 'false'},
          {'id': 'r3', 'text': 'C', 'heard_label': 'Heard today', 'unconfirmed': true},
          {'id': 'r4', 'text': 'D', 'heard_label': 'Heard today', 'certainty': 'new_kind'},
        ],
      });
      expect(
        [for (final r in view.rumors) r.certainty],
        [
          RumorCertainty.confirmed,
          RumorCertainty.wrong,
          RumorCertainty.unconfirmed,
          RumorCertainty.unconfirmed,
        ],
      );
      expect(view.rumors.first.heardLabel, 'Heard today');
    });

    test('reads who saw a deed, and leaves a mark it doesn\'t know unsaid', () {
      MemoryDeed deed(Object? seen) =>
          MemoryDeed.fromJson({'id': 'd', 'text': 'D', 'when_label': 'Day 1', 'seen': seen});
      expect(deed('heard_of').seen, DeedSeen.heardOf);
      expect(deed('public').seen, DeedSeen.public);
      expect(deed('filmed').seen, isNull);
      expect(deed(null).seen, isNull);
      expect(deed('seen').whenLabel, 'Day 1');
    });

    test('reads what became of a deed, and nothing from a server older than it', () {
      final deed = MemoryDeed.fromJson(const {
        'id': 'd',
        'text': 'D',
        'trail': [
          {'kind': 'went', 'text': 'Wei went to tell the sect'},
          {'kind': 'sung', 'text': 'A song is sung of it'},
          {'kind': 'dead'},
          'not a line',
        ],
        'open_label': 'Who else knows?',
      });
      expect(
        [for (final line in deed.trail) (line.kind, line.text)],
        [(DeedTrailKind.went, 'Wei went to tell the sect'), (null, 'A song is sung of it')],
      );
      expect(deed.openLabel, 'Who else knows?');
      final old = MemoryDeed.fromJson(const {'id': 'd', 'text': 'D', 'trail': 'none'});
      expect(old.trail, isEmpty);
      expect(old.openLabel, isNull);
    });

    test('takes a shape it doesn\'t expect without failing', () {
      final view = MemoryView.fromJson(const {
        'character': 'Ada',
        'people': {'id': 'p1'},
        'goals': [
          'Get home',
          {'id': 'g1', 'text': 'Get home'},
        ],
        'deeds': null,
      });
      expect(view.character, isNull);
      expect(view.people, isEmpty);
      expect(view.goals.single.text, 'Get home');
      expect(view.sections, [MemorySection.objectives]);
    });

    test('a character without a name is left out', () {
      final view = MemoryView.fromJson(const {
        'character': {'name': '', 'lines': <String>[]},
      });
      expect(view.character, isNull);
      expect(view.sections, isEmpty);
    });
  });
}
