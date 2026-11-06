import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/core/preferences.dart';
import 'package:playable_anime/core/fake/fake_premises.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/create/create_story_screen.dart';
import 'package:playable_anime/features/discover/premises.dart';

import '../helpers.dart';
import 'harness.dart';

/// Discover: the signature worlds first and large, a way to start from your own idea, then the
/// other worlds as a shelf of covers (S1).
void main() {
  testWidgets('the signature worlds come first, with their covers and badge', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    final l10n = await english();

    expect(find.text(l10n.discoverSignature.toUpperCase()), findsOneWidget);
    final cards = tester.widgetList<CoverCard>(find.byType(CoverCard)).toList();
    expect(cards.first.title, 'The Last Outer Disciple');
    expect(cards.every((c) => c.badge == l10n.discoverBadge), isTrue);
    expect(cards.first.imageUrl, isNotNull);

    // Then your own idea, then the shelf of the other worlds.
    final scroll = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(find.text(l10n.discoverCreateTitle), 300, scrollable: scroll);
    await tester.scrollUntilVisible(
      find.text(l10n.discoverMore.toUpperCase()),
      300,
      scrollable: scroll,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('the worlds come in the app\'s language, and again when it changes', (tester) async {
    final app = AppHarness();
    await app.launch(tester);
    bool asked(String language) => app
        .sent('GET', (path) => path == '/v1/premises')
        .any((r) => r.uri.queryParameters['language'] == language);
    expect(asked('en'), isTrue);

    final container = ProviderScope.containerOf(tester.element(find.byType(CoverCard).first));
    await container.read(languageProvider.notifier).set(AppLanguage.spanish);
    await settle(tester, frames: 10);

    expect(asked('es'), isTrue);
    final es = await AppLocalizations.delegate.load(const Locale('es'));
    expect(find.text(es.discoverSignature.toUpperCase()), findsOneWidget);
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
