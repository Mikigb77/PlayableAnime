import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/l10n.dart';
import 'package:playable_anime/design/design.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

/// Wraps [child] in the app's theme and strings, inside a scaffold, for widget tests.
Widget wrap(
  Widget child, {
  Brightness brightness = Brightness.dark,
  GenreAccent accent = GenreAccent.lucid,
  double textScale = 1,
  bool scroll = false,
  bool reduceMotion = false,
}) {
  return MaterialApp(
    theme: AppTheme.build(brightness, accent),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    builder: (context, app) => MediaQuery(
      data: MediaQuery.of(
        context,
      ).copyWith(textScaler: TextScaler.linear(textScale), disableAnimations: reduceMotion),
      child: app!,
    ),
    home: Scaffold(body: scroll ? SingleChildScrollView(child: child) : child),
  );
}

/// The English strings, for finding text the way the app shows it.
Future<AppLocalizations> english() => AppLocalizations.delegate.load(const Locale('en'));

/// A phone-sized test window.
void usePhone(WidgetTester tester, {Size size = const Size(390, 844)}) {
  tester.view
    ..physicalSize = size
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

/// Holds tokens the way the session does, for driving the fake backend straight from an
/// [ApiClient].
class TestTokens implements TokenSource {
  TestTokens([this.accessToken]);

  @override
  String? accessToken;
  String? refreshToken;
  int expired = 0;
  Future<bool> Function()? onRefresh;

  @override
  Future<bool> refresh() => onRefresh?.call() ?? Future.value(false);

  @override
  Future<void> onSessionExpired() async {
    expired++;
    accessToken = null;
  }
}

/// An [ApiClient] on a fresh fake backend that answers at once.
({ApiClient api, FakeBackend backend, TestTokens tokens}) fakeApi({
  FakePace pace = FakePace.instant,
  DateTime Function()? clock,
}) {
  final backend = FakeBackend.standard(pace: pace, clock: clock);
  final tokens = TestTokens();
  final api = ApiClient(baseUrl: FakeBackend.baseUrl, httpClient: backend, tokens: tokens);
  return (api: api, backend: backend, tokens: tokens);
}

/// A recognizer the test drives by hand.
class FakeSpeechEngine implements SpeechEngine {
  FakeSpeechEngine({this.supported = true, this.grants = true, this.permission = true});

  bool supported;

  /// Whether [initialize] succeeds (the player allowed the mic).
  bool grants;

  /// What [hasPermission] answers after a failed initialize.
  bool permission;

  int initializations = 0;
  int stops = 0;
  int cancels = 0;
  final listens = <({String? localeId, bool onDevice})>[];

  void Function(String words, bool isFinal)? _onResult;
  VoidCallback? _onStopped;
  void Function(SpeechFailure failure)? _onError;
  void Function(double level)? _onLevel;

  bool get listening => _onResult != null;

  void hear(String words, {bool isFinal = false}) => _onResult!(words, isFinal);
  void level(double value) => _onLevel?.call(value);
  void fail(String code) => _onError!(SpeechFailure(code));
  void stopped() => _onStopped!();

  @override
  Future<bool> isSupported() async => supported;

  @override
  Future<bool> initialize() async {
    initializations++;
    return grants;
  }

  @override
  Future<bool> hasPermission() async => permission;

  @override
  Future<void> listen({
    required void Function(String words, bool isFinal) onResult,
    required VoidCallback onStopped,
    required void Function(SpeechFailure failure) onError,
    void Function(double level)? onLevel,
    String? localeId,
    bool onDevice = true,
  }) async {
    listens.add((localeId: localeId, onDevice: onDevice));
    _onResult = onResult;
    _onStopped = onStopped;
    _onError = onError;
    _onLevel = onLevel;
  }

  @override
  Future<void> stop() async {
    stops++;
  }

  @override
  Future<void> cancel() async {
    cancels++;
  }
}

/// Lets pending futures and zero-length timers run, without waiting on endless animations.
Future<void> settle(WidgetTester tester, {int frames = 6}) async {
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// Collects a stream without letting a test hang on it.
Future<List<T>> collect<T>(Stream<T> stream) => stream.toList().timeout(const Duration(seconds: 5));
