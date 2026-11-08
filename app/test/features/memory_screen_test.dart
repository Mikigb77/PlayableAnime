import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/features/story/memory.dart';
import 'package:playable_anime/features/story/memory_screen.dart';

import '../helpers.dart';
import 'harness.dart';

/// Memory (C6, G16): only what the character knows, in the world's words.
void main() {
  late AppLocalizations l10n;

  setUpAll(() async => l10n = await english());

  Finder memoryList() =>
      find.descendant(of: find.byType(MemoryScreen), matching: find.byType(Scrollable)).first;

  /// Opens the story, then its memory, as a player does.
  Future<void> openMemory(WidgetTester tester, AppHarness app) async {
    await app.launch(tester, location: '/story/story_ninth_peak');
    await tester.tap(find.byTooltip(l10n.storyMemory));
    await settle(tester, frames: 10);
  }

  testWidgets('shows the character, then each group with what they know', (tester) async {
    await openMemory(tester, AppHarness());
    expect(find.text(l10n.memoryTitle), findsOneWidget);
    expect(find.text(l10n.memoryYou.toUpperCase()), findsOneWidget);
    expect(find.text('Shen Yu'), findsOneWidget);
    expect(find.text('Carries a sealed scroll that speaks.'), findsOneWidget);

    // People with what the character thinks of them, and how they stand as far as they know.
    expect(find.text('Senior Sister Lan'), findsOneWidget);
    expect(find.text('Fond of you'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Master Hu'), 200, scrollable: memoryList());
    expect(find.text('PRESUMED DEAD'), findsOneWidget);

    // A rumor is marked unconfirmed, one the character lived confirmed, and a closed thread
    // says how it ended.
    await tester.scrollUntilVisible(
      find.text('Elder Wen once studied forbidden arts'),
      300,
      scrollable: memoryList(),
    );
    expect(find.text(l10n.memoryUnconfirmed.toUpperCase()), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Shen Yu lost the outer court ranking in the first round'),
      300,
      scrollable: memoryList(),
    );
    expect(find.text(l10n.memoryConfirmed.toUpperCase()), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('The ranking of the outer court'),
      300,
      scrollable: memoryList(),
    );
    expect(find.text(l10n.threadFailed.toUpperCase()), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a filter shows one group at a time', (tester) async {
    await openMemory(tester, AppHarness());
    final places = find.widgetWithText(ChoiceChip, '${l10n.memoryPlaces} 2');
    expect(places, findsOneWidget);
    await tester.tap(places);
    await settle(tester);
    expect(find.text('The forbidden library'), findsOneWidget);
    expect(find.text('Senior Sister Lan'), findsNothing);
    expect(tester.widget<ChoiceChip>(places).selected, isTrue);

    await tester.tap(find.widgetWithText(ChoiceChip, l10n.memoryAll));
    await settle(tester);
    expect(find.text('Senior Sister Lan'), findsOneWidget);
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
    test('reads fates from the world\'s own words', () {
      MemoryPerson person(String label) =>
          MemoryPerson.fromJson({'id': 'p', 'name': 'P', 'status_label': label});
      expect(person('Alive').fate, Fate.alive);
      expect(person('Dead').fate, Fate.dead);
      expect(person('Presumed dead').fate, Fate.presumedDead);
      expect(person('Bound to the scroll').fate, Fate.other);
    });

    test('keeps only groups with something in them, in reading order', () {
      final view = MemoryView.fromJson(const {
        'character': {'name': 'Ada', 'lines': <String>[]},
        'people': [
          {'id': 'p1', 'name': 'Bo', 'status_label': 'Alive'},
        ],
        'leads': [
          {'id': 'l1', 'text': 'The tide turns at noon', 'expires_label': 'Until noon'},
        ],
        'threads': [
          {'id': 't1', 'title': 'The door', 'status': 'resolved_without_player'},
          {'id': 't2', 'title': 'The bell', 'status': 'something_new'},
        ],
      });
      expect(view.sections, [MemorySection.people, MemorySection.goals, MemorySection.threads]);
      expect(view.count(MemorySection.goals), 1);
      expect(view.threads.first.status, ThreadStatus.resolvedWithoutPlayer);
      expect(view.threads.first.status.isClosed, isTrue);
      expect(view.threads.last.status, ThreadStatus.open);
    });

    test('says what the character knows of each rumor, unconfirmed from an older server', () {
      final view = MemoryView.fromJson(const {
        'rumors': [
          {'id': 'r1', 'text': 'A', 'heard_label': 'Heard today', 'certainty': 'confirmed'},
          {'id': 'r2', 'text': 'B', 'heard_label': 'Heard today', 'certainty': 'false'},
          {'id': 'r3', 'text': 'C', 'heard_label': 'Heard today', 'unconfirmed': true},
          {'id': 'r4', 'text': 'D', 'heard_label': 'Heard today', 'certainty': 'new_kind'},
        ],
        'goals': [
          {'id': 'g1', 'text': 'Get home'},
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
      expect(view.goals.single.certainty, isNull);
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
