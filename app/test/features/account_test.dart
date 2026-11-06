import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/byok_store.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/core/preferences.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/account/account_models.dart';
import 'package:playable_anime/features/account/account_screen.dart';
import 'package:playable_anime/features/account/credits_format.dart';
import 'package:playable_anime/features/account/credits_screen.dart';
import 'package:playable_anime/features/account/out_of_credits_sheet.dart';
import 'package:playable_anime/features/account/policy_view.dart';
import 'package:playable_anime/features/account/privacy_screen.dart';
import 'package:playable_anime/features/auth/welcome_screen.dart';
import 'package:playable_anime/features/voice/dictation_mode.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';
import 'account_helpers.dart';

/// Account (F7, F8, K1, K2, S9, T12) and the out-of-credits sheet, on the fake API.
void main() {
  late FakeBackend backend;
  late MemorySessionStore store;
  late AppLocalizations l10n;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    backend = FakeBackend.standard(pace: FakePace.instant);
    store = MemorySessionStore();
    l10n = await english();
  });

  /// Launches signed in and opens the Account tab.
  Future<void> openAccount(
    WidgetTester tester, {
    RecordingExportSaver? saver,
    StubGoogleAuth? google,
    String? email,
    String? password,
  }) async {
    store.value = await storedSession(backend, email: email, password: password);
    await launchApp(tester, backend: backend, store: store, saver: saver, google: google);
    await tester.tap(find.text(l10n.navAccount));
    await settle(tester);
    expect(find.byType(AccountScreen), findsOneWidget);
  }

  Iterable<FakeRequest> sent(String method, String path) =>
      backend.requests.where((r) => r.method == method && r.uri.path == path);

  group('account', () {
    testWidgets('shows who you are, your rating and your credits', (tester) async {
      await openAccount(tester);
      expect(find.text('Demo player'), findsOneWidget);
      expect(find.text(FakeAuthState.demoEmail), findsOneWidget);
      expect(find.text(l10n.accountRatingMature), findsOneWidget);
      expect(find.text(l10n.accountTeenNote), findsNothing);
      expect(find.text('50¢'), findsOneWidget);
      expect(find.text(l10n.accountTopUpsSoon), findsOneWidget);
    });

    testWidgets('a teen account says when Mature opens', (tester) async {
      final now = DateTime.now();
      backend.data.auth.users[FakeAuthState.demoUserId]!['birth_date'] = '${now.year - 15}-01-01';
      await openAccount(tester);
      expect(find.text(l10n.accountRatingTeen), findsOneWidget);
      expect(find.text(l10n.accountTeenNote), findsOneWidget);
    });

    testWidgets('the owner has unlimited credits and the role badge', (tester) async {
      backend.data.auth.passwords['owner@lucid.test'] = 'owner-pass';
      await openAccount(tester, email: 'owner@lucid.test', password: 'owner-pass');
      expect(find.text(l10n.accountOwner), findsOneWidget);
      expect(find.text(l10n.accountUnlimited), findsOneWidget);
      expect(find.text(l10n.accountTopUpsSoon), findsNothing);
    });

    testWidgets('the balance is read again when the tab comes back', (tester) async {
      await openAccount(tester);
      expect(find.text('50¢'), findsOneWidget);
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: 2.3,
        now: DateTime.now(),
      );
      await tester.tap(find.text(l10n.navLibrary));
      await settle(tester);
      await tester.tap(find.text(l10n.navAccount));
      await settle(tester);
      expect(find.text('47.7¢'), findsOneWidget);
    });

    testWidgets('renames the account', (tester) async {
      await openAccount(tester);
      await tapVisible(tester, find.byTooltip(l10n.accountEditName));
      await tester.enterText(find.byKey(const Key('account.name')), '  Kai Moreno ');
      await tapVisible(tester, find.byKey(const Key('account.name.save')));
      expect(find.text('Kai Moreno'), findsOneWidget);
      expect(sent('PATCH', '/v1/me').last.json, {'display_name': 'Kai Moreno'});
    });

    testWidgets('a content preference is saved on its own, at once', (tester) async {
      await openAccount(tester);
      await tapVisible(tester, find.byKey(const Key('account.romance')));
      expect(sent('PATCH', '/v1/me').last.json, {
        'content_prefs': {'romance': false},
      });
      expect(
        tester.widget<SwitchListTile>(find.byKey(const Key('account.romance'))).value,
        isFalse,
      );

      await tapVisible(tester, find.text(l10n.accountGoreHigh));
      expect(sent('PATCH', '/v1/me').last.json, {
        'content_prefs': {'gore': 'high'},
      });
      final prefs = backend.data.auth.users[FakeAuthState.demoUserId]!['content_prefs'];
      expect(prefs, {'gore': 'high', 'romance': false, 'dark_themes': true});
    });

    testWidgets('a preference the server refuses goes back, with a message', (tester) async {
      // A backend whose PATCH fails, with every other route as usual.
      backend = withAllRoutes(
        FakeBackend(pace: FakePace.instant)
          ..route('PATCH', '/v1/me', (_) => throw const FakeError(503, 'llm_unavailable', 'x')),
      );
      await openAccount(tester);
      await tapVisible(tester, find.byKey(const Key('account.darkThemes')));
      expect(
        tester.widget<SwitchListTile>(find.byKey(const Key('account.darkThemes'))).value,
        isTrue,
      );
      expect(find.text(l10n.errorLlm), findsOneWidget);
    });

    testWidgets('a slow reload never undoes a change made while it loads', (tester) async {
      // GET /v1/me answers with the account as it was when asked, once the test lets it.
      Completer<void>? gate;
      backend = withAllRoutes(
        FakeBackend(pace: FakePace.instant)..route('GET', '/v1/me', (r) async {
          final asked = fakeUserJson(backend, r.userId!);
          await gate?.future;
          return FakeResponse.json(asked);
        }),
      );
      await openAccount(tester);
      final reads = sent('GET', '/v1/me').length;
      gate = Completer<void>();
      await tester.tap(find.text(l10n.navLibrary));
      await settle(tester);
      await tester.tap(find.text(l10n.navAccount));
      await settle(tester);
      expect(sent('GET', '/v1/me'), hasLength(reads + 1));

      await tapVisible(tester, find.byKey(const Key('account.romance')));
      gate.complete();
      await settle(tester);
      expect(
        tester.widget<SwitchListTile>(find.byKey(const Key('account.romance'))).value,
        isFalse,
      );
    });

    testWidgets('the first visit reads the account once', (tester) async {
      await openAccount(tester);
      expect(sent('GET', '/v1/me'), hasLength(1));
    });

    testWidgets('saves and removes your own key, for this account only', (tester) async {
      await openAccount(tester);
      await tester.ensureVisible(find.byKey(const Key('account.ownKey')));
      await tester.enterText(find.byKey(const Key('account.ownKey')), 'AIza-test-key-9876');
      await tapVisible(tester, find.byKey(const Key('account.ownKey.save')));
      expect(find.text(l10n.accountKeyEnding('9876')), findsOneWidget);
      final container = ProviderScope.containerOf(tester.element(find.byType(AccountScreen)));
      expect(await container.read(byokStoreProvider).readGeminiKey(), 'AIza-test-key-9876');

      await tapVisible(tester, find.text(l10n.accountKeyRemove));
      expect(find.byKey(const Key('account.ownKey')), findsOneWidget);
      expect(await container.read(byokStoreProvider).readGeminiKey(), isNull);
    });

    testWidgets('says so when the device cannot store the key', (tester) async {
      store.value = await storedSession(backend);
      await launchApp(tester, backend: backend, store: store, overrides: [lockedKeys]);
      await tester.tap(find.text(l10n.navAccount));
      await settle(tester);
      await tester.ensureVisible(find.byKey(const Key('account.ownKey')));
      await tester.enterText(find.byKey(const Key('account.ownKey')), 'AIza-test-key-9876');
      await tapVisible(tester, find.byKey(const Key('account.ownKey.save')));
      expect(find.text(l10n.accountKeyStoreFailed), findsOneWidget);
      expect(find.text(l10n.accountKeyEnding('9876')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('dictation is online by default and can stay on this device', (tester) async {
      await openAccount(tester);
      final container = ProviderScope.containerOf(tester.element(find.byType(AccountScreen)));
      expect(container.read(dictationModeProvider), DictationMode.online);
      await tester.ensureVisible(find.text(l10n.dictationOnlineBody));
      expect(find.text(l10n.dictationOnlineBody), findsOneWidget);

      await tapVisible(tester, find.text(l10n.dictationDevice));

      expect(container.read(dictationModeProvider), DictationMode.device);
      expect(find.text(l10n.dictationDeviceBody), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('dictation.mode'), 'device');
    });

    testWidgets('the app follows the device until the player picks a language', (tester) async {
      await openAccount(tester);
      final container = ProviderScope.containerOf(tester.element(find.byType(AccountScreen)));
      expect(container.read(languageProvider), AppLanguage.system);

      await tapVisible(tester, find.text(l10n.languageSpanish));

      expect(container.read(languageProvider), AppLanguage.spanish);
      final es = await AppLocalizations.delegate.load(const Locale('es'));
      // The whole app switches, the tabs included, and each language keeps its own name.
      expect(find.text(es.navAccount), findsWidgets);
      expect(find.text(es.accountLanguageBody), findsOneWidget);
      expect(find.text(l10n.navAccount), findsNothing);
      expect(find.text('English'), findsOneWidget);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('appearance.language'), 'spanish');

      // "System" names the theme's option too.
      await tapVisible(
        tester,
        find.descendant(
          of: find.byKey(const Key('account.language')),
          matching: find.text(es.languageSystem),
        ),
      );
      expect(find.text(l10n.navAccount), findsWidgets);
      expect(prefs.getString('appearance.language'), 'system');
    });

    testWidgets('a saved language applies from the start', (tester) async {
      SharedPreferences.setMockInitialValues({'appearance.language': 'spanish'});
      final es = await AppLocalizations.delegate.load(const Locale('es'));
      await launchApp(tester, backend: backend, store: store);
      expect(find.text(es.authContinueWithGoogle), findsOneWidget);
      expect(find.text(l10n.authContinueWithGoogle), findsNothing);
    });

    testWidgets('exports everything as a JSON file', (tester) async {
      final saver = RecordingExportSaver();
      await openAccount(tester, saver: saver);
      await tapVisible(tester, find.byKey(const Key('account.export')));
      expect(saver.saved, hasLength(1));
      final (name, data) = saver.saved.single;
      expect(name, 'lucid-saga-export.json');
      expect(data.keys, containsAll(['user', 'stories', 'images']));
      expect(find.text(l10n.accountExportReady), findsOneWidget);
    });

    testWidgets('deleting asks for the word, then deletes and signs out', (tester) async {
      final google = StubGoogleAuth();
      await openAccount(tester, google: google);
      final container = ProviderScope.containerOf(tester.element(find.byType(AccountScreen)));
      await container.read(byokStoreProvider).saveGeminiKey('AIza-delete-me');

      await tapVisible(tester, find.byKey(const Key('account.delete')));
      expect(find.text(l10n.deleteTitle), findsOneWidget);
      expect(find.text(l10n.deleteNoUndo), findsOneWidget);
      FilledButton submit() => tester.widget<FilledButton>(find.byKey(const Key('delete.submit')));
      expect(submit().onPressed, isNull);

      await tester.enterText(find.byKey(const Key('delete.confirm')), 'nope');
      await settle(tester, frames: 2);
      expect(submit().onPressed, isNull);
      expect(sent('DELETE', '/v1/me'), isEmpty);

      await tester.enterText(find.byKey(const Key('delete.confirm')), ' Delete ');
      await settle(tester, frames: 2);
      expect(submit().onPressed, isNotNull);
      await tapVisible(tester, find.byKey(const Key('delete.submit')));

      expect(sent('DELETE', '/v1/me'), hasLength(1));
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.text(l10n.deleteDone), findsOneWidget);
      expect(store.value, isNull);
      expect(google.signOuts, 1);
      // The key went with the account.
      expect(await const ByokStore(FakeAuthState.demoUserId).readGeminiKey(), isNull);
    });

    testWidgets('a deleted account signs out even when the key can\'t be cleared', (tester) async {
      store.value = await storedSession(backend);
      await launchApp(tester, backend: backend, store: store, overrides: [lockedKeys]);
      await tester.tap(find.text(l10n.navAccount));
      await settle(tester);
      await tapVisible(tester, find.byKey(const Key('account.delete')));
      await tester.enterText(find.byKey(const Key('delete.confirm')), l10n.deleteWord);
      await settle(tester, frames: 2);
      await tapVisible(tester, find.byKey(const Key('delete.submit')));
      expect(sent('DELETE', '/v1/me'), hasLength(1));
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(store.value, isNull);
    });

    testWidgets('signing out forgets the Google account too', (tester) async {
      final google = StubGoogleAuth();
      await openAccount(tester, google: google);
      await tapVisible(tester, find.text(l10n.accountSignOut));
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(google.signOuts, 1);
      expect(sent('POST', '/v1/auth/logout'), hasLength(1));
    });

    testWidgets('fits at twice the text size', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await openAccount(tester);
      for (var i = 0; i < 12; i++) {
        await tester.drag(find.byType(ListView).first, const Offset(0, -400));
        await settle(tester, frames: 2);
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('on a wide screen the settings keep to the reading width', (tester) async {
      await openAccount(tester);
      usePhone(tester, size: const Size(1280, 900));
      await settle(tester);
      final title = tester.getTopLeft(
        find.descendant(of: find.byType(PageHeader), matching: find.text(l10n.accountTitle)),
      );
      final profile = tester.getRect(find.text('Demo player').first);
      final card = tester.getRect(
        find.ancestor(of: find.text('Demo player'), matching: find.byType(Card)).first,
      );
      // Under the title, from the same edge, and no wider than a reading column.
      expect(card.left, title.dx);
      expect(card.width, lessThanOrEqualTo(Layout.readingWidth - Space.gutter * 2));
      expect(profile.left, greaterThan(card.left));
      expect(tester.takeException(), isNull);
    });

    testWidgets('the Developer section shows here, in a development build', (tester) async {
      await openAccount(tester);
      await tester.scrollUntilVisible(
        find.text(l10n.accountApi),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text(l10n.accountDeveloper.toUpperCase()), findsOneWidget);
    });

    test('players never see the Developer section; the owner and development builds do', () {
      const player = AccountUser(id: 'u', email: 'p@x.test', displayName: 'P');
      const owner = AccountUser(id: 'o', email: 'o@x.test', displayName: 'O', isOwner: true);
      expect(showsDeveloper(player, devBuild: false), isFalse);
      expect(showsDeveloper(null, devBuild: false), isFalse);
      expect(showsDeveloper(owner, devBuild: false), isTrue);
      expect(showsDeveloper(player, devBuild: true), isTrue);
    });
  });

  group('credits', () {
    testWidgets('lists what each entry was for, newest first', (tester) async {
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: 2.25,
        now: DateTime.now(),
        storyId: 'story_ninth_peak',
        turn: 4,
      );
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'image',
        cents: 3.4,
        now: DateTime.now(),
        storyId: 'story_ninth_peak',
        turn: 4,
      );
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'speech',
        cents: 0.2,
        now: DateTime.now(),
        storyId: 'story_ninth_peak',
      );
      await openAccount(tester);
      await tapVisible(tester, find.text(l10n.accountCreditHistory));
      expect(find.byType(CreditsScreen), findsOneWidget);
      expect(find.byKey(const Key('credits.balance')), findsOneWidget);
      expect(find.text('44.2¢'), findsOneWidget);

      final tiles = find.byType(LedgerTile);
      expect(tiles, findsNWidgets(4));
      final kinds = [for (final tile in tester.widgetList<LedgerTile>(tiles)) tile.entry.kind.name];
      expect(kinds, ['speech', 'image', 'turn', 'starter']);
      expect(find.text('−3.4¢'), findsOneWidget);
      expect(find.text('−0.2¢'), findsOneWidget);
      expect(find.textContaining(l10n.creditsKindSpeech), findsOneWidget);
      expect(find.text('+50¢'), findsOneWidget);
      expect(find.textContaining(l10n.creditsStoryTurn('The Ninth Peak', 4)), findsNWidgets(2));
    });

    testWidgets('the history fits twice the text size', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'turn',
        cents: 2.25,
        now: DateTime.now(),
        storyId: 'story_ninth_peak',
        turn: 4,
      );
      backend.data.account.charge(
        FakeAuthState.demoUserId,
        kind: 'speech',
        cents: 0.2,
        now: DateTime.now(),
      );
      await openAccount(tester);
      await tapVisible(tester, find.text(l10n.accountCreditHistory));
      expect(find.byType(LedgerTile), findsNWidgets(3));
      for (var i = 0; i < 6; i++) {
        await tester.drag(find.byType(ListView).first, const Offset(0, -400));
        await settle(tester, frames: 2);
        expect(tester.takeException(), isNull);
      }
      // The amount and the balance after it stay beside what the entry was for.
      final amount = tester.getRect(find.text('−2.3¢'));
      final turn = tester.getRect(find.text(l10n.creditsKindTurn));
      expect(amount.left, greaterThan(turn.right));
    });
  });

  group('out of credits', () {
    Future<void> openSheet(WidgetTester tester, ApiException error) async {
      await openAccount(tester);
      unawaited(showOutOfCreditsSheet(tester.element(find.byType(AccountScreen)), error: error));
      await settle(tester);
      expect(find.text(l10n.oocTitle), findsOneWidget);
    }

    const error = ApiException(
      ApiErrorCode.outOfCredits,
      status: 402,
      details: {'balance_cents': 1.2, 'available_cents': 0.4},
    );

    testWidgets('says what is left and that top-ups are coming', (tester) async {
      await openSheet(tester, error);
      expect(find.text(l10n.oocBalance('1.2¢')), findsOneWidget);
      expect(find.text(l10n.oocHeld), findsOneWidget);
      expect(find.text(l10n.oocTopUps), findsOneWidget);
    });

    testWidgets('adding your own key ends it so the caller can try again', (tester) async {
      await openAccount(tester);
      final context = tester.element(find.byType(AccountScreen));
      final outcome = showOutOfCreditsSheet(context, error: error);
      await settle(tester);
      await tapVisible(tester, find.byKey(const Key('ooc.useKey')));
      final field = find.descendant(
        of: find.byType(OutOfCreditsSheet),
        matching: find.byKey(const Key('account.ownKey')),
      );
      await tester.enterText(field, 'AIza-from-the-sheet');
      await tapVisible(
        tester,
        find.descendant(
          of: find.byType(OutOfCreditsSheet),
          matching: find.byKey(const Key('account.ownKey.save')),
        ),
      );
      expect(await outcome, OutOfCreditsOutcome.keyAdded);
      expect(find.byType(OutOfCreditsSheet), findsNothing);
      expect(find.text(l10n.oocKeySaved), findsOneWidget);
      final container = ProviderScope.containerOf(tester.element(find.byType(AccountScreen)));
      expect(await container.read(byokStoreProvider).readGeminiKey(), 'AIza-from-the-sheet');
    });

    testWidgets('a caller that tries again by itself gets the one note that says so', (
      tester,
    ) async {
      await openAccount(tester);
      final context = tester.element(find.byType(AccountScreen));
      final outcome = showOutOfCreditsSheet(context, error: error, retriesItself: true);
      await settle(tester);
      await tapVisible(tester, find.byKey(const Key('ooc.useKey')));
      await tester.enterText(
        find.descendant(
          of: find.byType(OutOfCreditsSheet),
          matching: find.byKey(const Key('account.ownKey')),
        ),
        'AIza-from-the-sheet',
      );
      await tapVisible(
        tester,
        find.descendant(
          of: find.byType(OutOfCreditsSheet),
          matching: find.byKey(const Key('account.ownKey.save')),
        ),
      );
      expect(await outcome, OutOfCreditsOutcome.keyAdded);
      expect(find.text(l10n.oocKeySavedRetrying), findsOneWidget);
      expect(find.text(l10n.oocKeySaved), findsNothing);
    });

    testWidgets('opens the credit history', (tester) async {
      await openAccount(tester);
      final context = tester.element(find.byType(AccountScreen));
      final outcome = showOutOfCreditsSheet(context);
      await settle(tester);
      // Without details the sheet shows the balance it knows.
      expect(find.text(l10n.oocBalance('50¢')), findsOneWidget);
      await tapVisible(tester, find.text(l10n.oocHistory));
      expect(await outcome, OutOfCreditsOutcome.dismissed);
      expect(find.byType(CreditsScreen), findsOneWidget);
    });
  });

  group('privacy', () {
    test('the app ships the policy in docs/PRIVACY.md, word for word', () {
      final docs = File('../docs/PRIVACY.md').readAsStringSync();
      final shipped = File('assets/legal/privacy_en.md').readAsStringSync();
      expect(docs.endsWith(shipped), isTrue, reason: 'Copy docs/PRIVACY.md from "## Who we are"');
      expect(shipped, startsWith('## Who we are'));
    });

    test('the policy parses into headings, lists and tables', () {
      final blocks = parsePolicy(File('assets/legal/privacy_en.md').readAsStringSync());
      expect(blocks.whereType<PolicyHeading>().map((h) => h.text), contains('Your rights'));
      final table = blocks.whereType<PolicyTable>().first;
      expect(table.header, ['What', 'Why', 'Legal basis']);
      expect(table.rows.length, greaterThan(4));
      expect(blocks.whereType<PolicyBullets>(), isNotEmpty);
      // Indented lines continue their list item.
      final bullets = parsePolicy('- one\n  more\n- two').single as PolicyBullets;
      expect(bullets.items, ['one more', 'two']);
    });

    test('the Spanish policy has the same sections, tables and lists as the English', () {
      final english = parsePolicy(File('assets/legal/privacy_en.md').readAsStringSync());
      final spanish = parsePolicy(File('assets/legal/privacy_es.md').readAsStringSync());
      String shape(PolicyBlock block) => switch (block) {
        PolicyTable(:final rows) => 'table ${rows.length}',
        PolicyBullets(:final items) => 'list ${items.length}',
        _ => block.runtimeType.toString(),
      };
      expect(
        spanish.map(shape).toList(),
        english.map(shape).toList(),
        reason: 'Change assets/legal/privacy_es.md with docs/PRIVACY.md (S10)',
      );
      expect(spanish.whereType<PolicyHeading>().first.text, 'Quiénes somos');
    });

    testWidgets('opens signed out and reads as a page', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await tester.ensureVisible(find.textContaining(l10n.authPolicyLink, findRichText: true));
      await tester.tapOnText(find.textRange.ofSubstring(l10n.authPolicyLink));
      await settle(tester);
      expect(find.byType(PrivacyScreen), findsOneWidget);
      expect(find.text('Who we are'), findsOneWidget);
      await tester.tap(find.byType(BackButton));
      await settle(tester);
      expect(find.byType(WelcomeScreen), findsOneWidget);
    });
  });

  test('credits read as cents under a dollar and dollars above', () {
    expect(formatCreditsIn('en', 50), '50¢');
    expect(formatCreditsIn('en', 2.25), '2.3¢');
    expect(formatCreditsIn('en', 0), '0¢');
    expect(formatCreditsIn('en', 150), r'$1.50');
    expect(formatCreditsIn('en', -2.25, signed: true), '−2.3¢');
    expect(formatCreditsIn('en', 50, signed: true), '+50¢');
    expect(formatCreditsIn('es', 2.5), '2,5¢');
  });
}
