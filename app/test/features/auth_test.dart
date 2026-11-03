import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/features/account/privacy_screen.dart';
import 'package:playable_anime/features/auth/auth_repository.dart';
import 'package:playable_anime/features/auth/birth_date_screen.dart';
import 'package:playable_anime/features/auth/email_auth_screen.dart';
import 'package:playable_anime/features/auth/google_auth.dart';
import 'package:playable_anime/features/auth/google_button.dart';
import 'package:playable_anime/features/auth/welcome_screen.dart';
import 'package:playable_anime/features/discover/discover_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';
import 'account_helpers.dart';

/// Sign-in (T8, F8): Google with the birth-date step, email sign-in and sign-up, on the fake API.
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

  String? signedInAs() => store.value?.user['email'] as String?;

  /// The last sign-in request; Discover loads its own once signed in.
  FakeRequest lastAuth() => backend.requests.lastWhere((r) => r.uri.path.startsWith('/v1/auth/'));

  Future<void> openEmail(WidgetTester tester, {bool register = false}) async {
    await tapVisible(tester, find.text(register ? l10n.authSignUpWithEmail : l10n.authHaveAccount));
    expect(find.byType(EmailAuthScreen), findsOneWidget);
  }

  /// Types a date into the date picker, in the test locale's format (MM/DD/YYYY).
  Future<void> pickBirthDate(WidgetTester tester, String date) async {
    await tapVisible(tester, find.byKey(const Key('auth.birthDate')));
    await tester.enterText(
      find.descendant(of: find.byType(Dialog), matching: find.byType(TextField)),
      date,
    );
    await tester.tap(find.text('OK'));
    await settle(tester);
  }

  group('welcome', () {
    testWidgets('offers Google and email, and the privacy policy', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      expect(find.byType(GoogleButton), findsOneWidget);
      expect(find.text(l10n.authSignUpWithEmail), findsOneWidget);
      expect(find.text(l10n.authHaveAccount), findsOneWidget);

      final policy = find.textContaining(l10n.authPolicyLink, findRichText: true);
      await tester.ensureVisible(policy);
      await tester.tapOnText(find.textRange.ofSubstring(l10n.authPolicyLink));
      await settle(tester);
      expect(find.byType(PrivacyScreen), findsOneWidget);
    });

    testWidgets('hides Google where this build has no client for it', (tester) async {
      await launchApp(
        tester,
        backend: backend,
        store: store,
        google: PluginGoogleAuth.forThisPlatform(),
      );
      expect(find.byType(GoogleButton), findsNothing);
      expect(find.text(l10n.authSignUpWithEmail), findsOneWidget);
    });
  });

  group('google', () {
    testWidgets('a returning account signs straight in', (tester) async {
      final google = StubGoogleAuth(token: FakeGoogleTokens.demo);
      await launchApp(tester, backend: backend, store: store, google: google);
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.byType(DiscoverScreen), findsOneWidget);
      expect(signedInAs(), FakeAuthState.demoEmail);
      final sent = lastAuth();
      expect(sent.uri.path, '/v1/auth/google');
      expect(sent.json, {'id_token': FakeGoogleTokens.demo});
    });

    testWidgets('a first sign-in asks for the birth date, then signs in', (tester) async {
      final google = StubGoogleAuth(token: FakeGoogleTokens.newPlayer);
      await launchApp(tester, backend: backend, store: store, google: google);
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.byType(BirthDateScreen), findsOneWidget);
      expect(find.text(l10n.authBirthDateTitle), findsOneWidget);

      // Continuing without a date asks for one, without calling the server.
      final calls = backend.requests.length;
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.text(l10n.authNeedBirthDate), findsOneWidget);
      expect(backend.requests, hasLength(calls));

      await pickBirthDate(tester, '06/21/1998');
      expect(find.text('June 21, 1998'), findsOneWidget);
      await tapVisible(tester, find.byKey(const Key('auth.submit')));

      expect(find.byType(DiscoverScreen), findsOneWidget);
      expect(signedInAs(), 'new.player@gmail.test');
      expect(lastAuth().json, {'id_token': FakeGoogleTokens.newPlayer, 'birth_date': '1998-06-21'});
    });

    testWidgets('a birth date under the minimum age is refused in plain words', (tester) async {
      final google = StubGoogleAuth(token: FakeGoogleTokens.newPlayer);
      await launchApp(tester, backend: backend, store: store, google: google);
      await tapVisible(tester, find.byType(GoogleButton));
      final year = DateTime.now().year - 8;
      await pickBirthDate(tester, '01/15/$year');
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.byType(BirthDateScreen), findsOneWidget);
      expect(find.text(l10n.authTooYoung), findsOneWidget);
      expect(store.value, isNull);
    });

    testWidgets('backing out of Google does nothing', (tester) async {
      final google = StubGoogleAuth();
      await launchApp(tester, backend: backend, store: store, google: google);
      final calls = backend.requests.length;
      await tapVisible(tester, find.byType(GoogleButton));
      expect(google.signIns, 1);
      expect(backend.requests, hasLength(calls));
      expect(find.byType(WelcomeScreen), findsOneWidget);
      expect(find.text(l10n.authGoogleFailed), findsNothing);
    });

    testWidgets('a Google failure or an outage says what to do', (tester) async {
      final google = StubGoogleAuth(fails: true);
      await launchApp(tester, backend: backend, store: store, google: google);
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.text(l10n.authGoogleFailed), findsOneWidget);

      google
        ..fails = false
        ..token = FakeGoogleTokens.unavailable;
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.text(l10n.errorSignInUnavailable), findsOneWidget);

      google.token = FakeGoogleTokens.unverified;
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.text(l10n.authGoogleUnverified), findsOneWidget);
      expect(store.value, isNull);
    });

    testWidgets('the offline picker signs in as the account picked', (tester) async {
      await launchApp(tester, backend: backend, store: store, google: const FakeGoogleAuth());
      await tapVisible(tester, find.byType(GoogleButton));
      expect(find.text(l10n.fakeGoogleTitle), findsOneWidget);
      await tester.tap(find.text(l10n.fakeGoogleOwner));
      await settle(tester);
      expect(find.byType(DiscoverScreen), findsOneWidget);
      expect(signedInAs(), 'owner@lucid.test');
    });
  });

  group('email', () {
    testWidgets('signs in and opens Discover', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester);
      expect(find.text(l10n.authSignInTitle), findsOneWidget);
      await tester.enterText(find.byKey(const Key('auth.email')), ' Demo@Lucid.test ');
      await tester.enterText(find.byKey(const Key('auth.password')), FakeAuthState.demoPassword);
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.byType(DiscoverScreen), findsOneWidget);
      expect(signedInAs(), FakeAuthState.demoEmail);
    });

    testWidgets('a wrong password says so and keeps what was typed', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester);
      await tester.enterText(find.byKey(const Key('auth.email')), FakeAuthState.demoEmail);
      await tester.enterText(find.byKey(const Key('auth.password')), 'wrong-one');
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.text(l10n.authWrongPassword), findsOneWidget);
      expect(find.text(FakeAuthState.demoEmail), findsOneWidget);

      // Typing again clears the message.
      await tester.enterText(find.byKey(const Key('auth.password')), 'another');
      await settle(tester, frames: 2);
      expect(find.text(l10n.authWrongPassword), findsNothing);
    });

    testWidgets('an empty form is checked before anything is sent', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester, register: true);
      expect(find.text(l10n.authNeedName), findsNothing);
      final calls = backend.requests.length;
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.text(l10n.authNeedName), findsOneWidget);
      expect(find.text(l10n.authNeedEmail), findsOneWidget);
      expect(find.text(l10n.authNeedPassword), findsOneWidget);
      expect(find.text(l10n.authNeedBirthDate), findsOneWidget);
      expect(backend.requests, hasLength(calls));
    });

    testWidgets('the server\'s problems show under their fields', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester, register: true);
      await tester.enterText(find.byKey(const Key('auth.name')), 'Ren');
      await tester.enterText(find.byKey(const Key('auth.email')), FakeAuthState.demoEmail);
      await tester.enterText(find.byKey(const Key('auth.password')), 'password');
      await pickBirthDate(tester, '02/03/2001');
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.text(l10n.authPasswordCommon), findsOneWidget);

      await tester.enterText(find.byKey(const Key('auth.password')), 'moonlit-harbor');
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.text(l10n.authPasswordCommon), findsNothing);
      expect(find.text(l10n.authEmailTaken), findsOneWidget);
      expect(store.value, isNull);
    });

    testWidgets('creates an account and signs in', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester, register: true);
      await tester.enterText(find.byKey(const Key('auth.name')), 'Ren Ito');
      await tester.enterText(find.byKey(const Key('auth.email')), 'ren@example.com');
      await tester.enterText(find.byKey(const Key('auth.password')), 'moonlit-harbor');
      await pickBirthDate(tester, '02/03/2001');
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(find.byType(DiscoverScreen), findsOneWidget);
      expect(signedInAs(), 'ren@example.com');
      expect(lastAuth().json, {
        'email': 'ren@example.com',
        'password': 'moonlit-harbor',
        'display_name': 'Ren Ito',
        'birth_date': '2001-02-03',
      });
    });

    testWidgets('switches between signing in and creating an account', (tester) async {
      await launchApp(tester, backend: backend, store: store);
      await openEmail(tester);
      expect(find.byKey(const Key('auth.name')), findsNothing);
      await tapVisible(tester, find.text(l10n.authToRegister));
      expect(find.text(l10n.authRegisterTitle), findsOneWidget);
      expect(find.byKey(const Key('auth.name')), findsOneWidget);
      expect(find.byKey(const Key('auth.birthDate')), findsOneWidget);
      await tapVisible(tester, find.text(l10n.authToSignIn));
      expect(find.text(l10n.authSignInTitle), findsOneWidget);
    });

    testWidgets('fits at twice the text size', (tester) async {
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await launchApp(tester, backend: backend, store: store);
      expect(tester.takeException(), isNull);
      await openEmail(tester, register: true);
      await tapVisible(tester, find.byKey(const Key('auth.submit')));
      expect(tester.takeException(), isNull);
    });
  });

  group('field problems', () {
    test('each type the backend sends has its own words', () {
      for (final (field, type, text) in [
        ('email', 'invalid_email', l10n.authBadEmail),
        ('email', 'email_taken', l10n.authEmailTaken),
        ('password', 'password_too_short', l10n.authPasswordShort),
        ('password', 'password_too_common', l10n.authPasswordCommon),
        ('password', 'password_too_similar', l10n.authPasswordSimilar),
        ('password', 'password_entirely_numeric', l10n.authPasswordNumeric),
        ('display_name', 'missing', l10n.authNeedName),
        ('birth_date', 'future', l10n.authBirthDateFuture),
        ('birth_date', 'implausible', l10n.authBirthDateImplausible),
        ('birth_date', 'too_young', l10n.authTooYoung),
        ('email', 'string_too_short', l10n.authBadEmail),
        ('birth_date', 'date_from_datetime_parsing', l10n.authFieldInvalid),
      ]) {
        expect(describeFieldProblem(l10n, field, type), text, reason: '$field $type');
      }
    });

    test('dates go to the API as YYYY-MM-DD', () {
      expect(isoDate(DateTime(998, 3, 4)), '0998-03-04');
      expect(isoDate(DateTime(2001, 12, 31, 23, 59)), '2001-12-31');
    });
  });

  test('the G is drawn inside its box', () {
    final bounds = parseSvgPath('M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85z').getBounds();
    expect(bounds.left, closeTo(24, 0.01));
    expect(bounds.top, closeTo(6.25, 0.01));
    expect(bounds.bottom, closeTo(13.1, 0.01));
    expect(bounds.right, closeTo(40.06, 0.01));
    const logo = GoogleLogoPainter();
    expect(logo.shouldRepaint(logo), isFalse);
  });
}
