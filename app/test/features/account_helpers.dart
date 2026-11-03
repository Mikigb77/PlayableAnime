import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/app.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/core/session/session.dart';
import 'package:playable_anime/core/session/session_controller.dart';
import 'package:playable_anime/features/account/export_saver.dart';
import 'package:playable_anime/features/auth/google_auth.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

import '../helpers.dart';

/// A Google sign-in the test scripts: the token to hand back (null when the player backs out),
/// or a failure.
class StubGoogleAuth implements GoogleAuth {
  StubGoogleAuth({this.token, this.fails = false});

  String? token;
  bool fails;
  int signIns = 0;
  int signOuts = 0;

  @override
  bool get isAvailable => true;

  @override
  bool get drawsOwnButton => true;

  @override
  Future<String?> signIn(BuildContext context) async {
    signIns++;
    if (fails) throw const GoogleSignInFailure('test');
    return token;
  }

  @override
  Stream<String> get idTokens => const Stream.empty();

  @override
  Widget buildWebButton(BuildContext context, double width) => const SizedBox.shrink();

  @override
  Future<void> signOut() async => signOuts++;
}

/// Keeps what the account screen exports instead of opening a share sheet.
class RecordingExportSaver implements ExportSaver {
  final saved = <(String fileName, JsonMap data)>[];

  @override
  Future<bool> save(Uint8List bytes, {required String fileName, Rect? origin}) async {
    saved.add((fileName, jsonDecode(utf8.decode(bytes)) as JsonMap));
    return true;
  }
}

/// Signs in on [backend] outside the app, as a stored session the app restores at launch.
Future<Session> storedSession(FakeBackend backend, {String? email, String? password}) async {
  final json =
      await ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend).post('/v1/auth/login', {
            'email': email ?? FakeAuthState.demoEmail,
            'password': password ?? FakeAuthState.demoPassword,
          }, authenticated: false)
          as JsonMap;
  return Session.fromApi(json);
}

/// The whole app on [backend], phone sized.
Future<void> launchApp(
  WidgetTester tester, {
  required FakeBackend backend,
  required MemorySessionStore store,
  GoogleAuth? google,
  ExportSaver? saver,
  Size size = const Size(390, 844),
}) async {
  usePhone(tester, size: size);
  await tester.pumpWidget(
    ProviderScope(
      retry: retryTransient,
      overrides: [
        httpClientProvider.overrideWithValue(backend),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(store),
        speechEngineProvider.overrideWithValue(FakeSpeechEngine()),
        googleAuthProvider.overrideWithValue(google ?? StubGoogleAuth()),
        exportSaverProvider.overrideWithValue(saver ?? RecordingExportSaver()),
      ],
      child: const App(),
    ),
  );
  await settle(tester);
}

/// Scrolls [finder] into view and taps it, once any scrolling has stopped: a list ignores taps
/// while it scrolls, as it does after a text field takes focus.
Future<void> tapVisible(WidgetTester tester, Finder finder) async {
  await settle(tester);
  await tester.ensureVisible(finder);
  await settle(tester);
  await tester.tap(finder);
  await settle(tester);
}
