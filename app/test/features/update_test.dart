import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:playable_anime/core/api/api_providers.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/fake/fake_releases.dart';
import 'package:playable_anime/core/session/session_controller.dart';
import 'package:playable_anime/features/update/apk_download.dart';
import 'package:playable_anime/features/update/app_update.dart';

import '../helpers.dart';
import 'harness.dart';

/// Stands in for Android: this install is build 12, and it records what it was asked to install
/// and how often the app was closed.
class FakeInstaller implements AppInstaller {
  FakeInstaller(this.updatesDir, {this.build = 12, this.failInstall});

  final String updatesDir;
  final int build;
  final UpdateProblem? failInstall;
  final installs = <(String path, String sha256)>[];
  var closes = 0;
  final _outcomes = StreamController<InstallOutcome>.broadcast();

  void finish(InstallOutcome outcome) => _outcomes.add(outcome);

  @override
  Future<InstalledApp?> installed() async =>
      InstalledApp(build: build, version: '1.0.0', updatesDir: updatesDir);

  @override
  Future<void> install(String path, String sha256) async {
    if (failInstall case final problem?) throw problem;
    installs.add((path, sha256));
  }

  @override
  Stream<InstallOutcome> get outcomes => _outcomes.stream;

  @override
  Future<void> close() async => closes++;
}

void main() {
  late Directory updates;
  late AppHarness harness;
  late FakeInstaller installer;

  setUp(() {
    updates = Directory.systemTemp.createTempSync('lucid-updates');
    addTearDown(() => updates.deleteSync(recursive: true));
    harness = AppHarness();
    installer = FakeInstaller(updates.path);
  });

  List<FakeRequest> checks() => harness.sent('GET', (p) => p == '/v1/app/latest');

  Future<ProviderContainer> signedIn({bool selfUpdate = true, http.Client? client}) async {
    await harness.signIn();
    final container = ProviderContainer(
      overrides: [
        httpClientProvider.overrideWithValue(client ?? harness.backend),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(harness.store),
        selfUpdateProvider.overrideWithValue(selfUpdate),
        appInstallerProvider.overrideWithValue(installer),
      ],
    );
    addTearDown(container.dispose);
    container.read(sessionProvider);
    for (var i = 0; i < 10; i++) {
      if (container.read(sessionProvider).status != SessionStatus.restoring) break;
      await Future<void>.delayed(Duration.zero);
    }
    return container;
  }

  void publish(int build, {List<int> apk = const [1, 2, 3, 4, 5]}) =>
      harness.backend.data.releases.latest = FakeRelease(build: build, apk: apk, sha256: 'ab' * 32);

  group('the controller', () {
    test('does nothing in a build that an app store updates', () async {
      publish(13);
      final c = await signedIn(selfUpdate: false);

      await c.read(appUpdateProvider.notifier).check(now: true);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.off);
      expect(checks(), isEmpty);
    });

    test('is up to date while nothing is published', () async {
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.upToDate);
      expect(state.installed?.build, 12);
      expect(checks().single.uri.queryParameters['platform'], 'android');
    });

    test('is up to date on the newest build or a newer one', () async {
      publish(12);
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.upToDate);
      expect(c.read(appUpdateProvider).hasUpdate, isFalse);
    });

    test('offers a newer build', () async {
      publish(13);
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.available);
      expect(state.release?.build, 13);
      expect(state.release?.version, '1.0.0');
      expect(state.hasUpdate, isTrue);
    });

    test('checks on its own at most every half hour, and at once when asked', () async {
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);

      await controller.check();
      publish(13);
      await controller.check();
      expect(checks(), hasLength(1));
      expect(c.read(appUpdateProvider).phase, UpdatePhase.upToDate);

      await controller.check(now: true);
      expect(checks(), hasLength(2));
      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);
    });

    test('a failed check on its own changes nothing; one the player asked for says so', () async {
      final c = await signedIn(
        client: MockClient((request) async {
          if (request.url.path == '/v1/app/latest') return http.Response('oops', 502);
          return http.Response.fromStream(await harness.backend.send(request));
        }),
      );
      final controller = c.read(appUpdateProvider.notifier);

      await controller.check();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.unknown);

      await controller.check(now: true);
      expect(c.read(appUpdateProvider).phase, UpdatePhase.failed);
      expect(c.read(appUpdateProvider).problem, UpdateProblem.download);
    });

    test('Later holds for that build only', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      controller.dismiss();
      expect(c.read(appUpdateProvider).dismissed, isTrue);
      await controller.check(now: true);
      expect(c.read(appUpdateProvider).dismissed, isTrue);

      publish(14);
      await controller.check(now: true);
      expect(c.read(appUpdateProvider).release?.build, 14);
      expect(c.read(appUpdateProvider).dismissed, isFalse);
    });

    test('downloads the newer build and hands it to Android', () async {
      File('${updates.path}/lucid-saga-11.apk').writeAsBytesSync([9, 9]);
      publish(13, apk: List.filled(1000, 7));
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      final progress = <double>[];
      c.listen(appUpdateProvider, (_, next) {
        if (next.progress case final done?) progress.add(done);
      });

      await controller.update();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.installing);
      final (path, sha) = installer.installs.single;
      expect(path, '${updates.path}/lucid-saga-13.apk');
      expect(sha, 'ab' * 32);
      expect(File(path).readAsBytesSync(), List.filled(1000, 7));
      expect(File('${updates.path}/lucid-saga-11.apk').existsSync(), isFalse);
      expect(progress.last, 1.0);
      // A fresh URL right before the download, as the one from the check may have expired.
      expect(checks(), hasLength(2));
    });

    test('the player saying no to Android offers the update again', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();

      installer.finish(InstallOutcome.cancelled);
      await Future<void>.delayed(Duration.zero);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);
      // The finished download is used again.
      await controller.update();
      expect(installer.installs, hasLength(2));
      expect(harness.sent('GET', (p) => p.startsWith('/fake-releases/')), hasLength(1));
    });

    test('can ask Android again while it is asked, and Later never hides a failure', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);

      await controller.check(now: true); // a check leaves it alone
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      await controller.update();
      expect(installer.installs, hasLength(2));

      installer.finish(InstallOutcome.failed);
      await Future<void>.delayed(Duration.zero);
      controller.dismiss();
      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.failed);
      expect(state.problem, UpdateProblem.install);
      expect(state.dismissed, isTrue);

      await controller.update();
      expect(c.read(appUpdateProvider).dismissed, isFalse);
    });

    test('the app closes once Android starts installing, and leaves the install alone', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();
      expect(installer.closes, 0); // not while Android asks

      installer.finish(InstallOutcome.started);
      await Future<void>.delayed(Duration.zero);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.replacing);
      expect(c.read(appUpdateProvider).hasUpdate, isTrue);
      expect(installer.closes, 1);

      // Coming back while Android installs it starts nothing new.
      await controller.check(now: true);
      await controller.update();
      installer.finish(InstallOutcome.started);
      await Future<void>.delayed(Duration.zero);
      expect(c.read(appUpdateProvider).phase, UpdatePhase.replacing);
      expect(installer.installs, hasLength(1));
      expect(checks(), hasLength(2));
      expect(installer.closes, 1);
    });

    test('a no to a question asked again leaves the started install alone', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();
      await controller.update();

      installer.finish(InstallOutcome.started);
      installer.finish(InstallOutcome.cancelled);
      await Future<void>.delayed(Duration.zero);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.replacing);
    });

    test('Android refusing it after the app closed is there to see on coming back', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();

      installer.finish(InstallOutcome.started);
      installer.finish(InstallOutcome.failed);
      await Future<void>.delayed(Duration.zero);

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.failed);
      expect(state.problem, UpdateProblem.install);
      expect(installer.closes, 1);
      await controller.update();
      expect(installer.installs, hasLength(2));
    });

    test('Android refusing it is a failed install', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();

      installer.finish(InstallOutcome.failed);
      await Future<void>.delayed(Duration.zero);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.failed);
      expect(c.read(appUpdateProvider).problem, UpdateProblem.install);
    });

    test('a damaged download is never installed', () async {
      installer = FakeInstaller(updates.path, failInstall: UpdateProblem.corrupt);
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      await controller.update();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.failed);
      expect(c.read(appUpdateProvider).problem, UpdateProblem.corrupt);
    });
  });

  group('the Android side', () {
    const channel = MethodChannel('lucid_saga/app_update');

    Future<void> androidSays(String status) =>
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
          channel.name,
          const StandardMethodCodec().encodeMethodCall(
            MethodCall('installStatus', {'status': status}),
          ),
          (_) {},
        );

    test('says when Android starts installing, and closes the app when asked', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      final asked = <String>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        asked.add(call.method);
        return true;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
      final android = PlatformAppInstaller();
      final outcomes = <InstallOutcome>[];
      android.outcomes.listen(outcomes.add);

      for (final status in ['started', 'cancelled', 'installed', 'something new']) {
        await androidSays(status);
      }
      await android.close();
      await Future<void>.delayed(Duration.zero);

      expect(outcomes, [
        InstallOutcome.started,
        InstallOutcome.cancelled,
        InstallOutcome.installed,
        InstallOutcome.failed,
      ]);
      expect(asked, ['close']);
    });

    test('closing quietly leaves the app open when Android can not', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(channel, (_) async => throw PlatformException(code: 'x'));
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

      await expectLater(PlatformAppInstaller().close(), completes);
    });
  });

  group('the download', () {
    Future<String> download(http.Client client, {int size = 4}) => downloadApk(
      client: client,
      url: Uri.parse('https://storage.invalid/apk'),
      size: size,
      folder: '${updates.path}/nested',
      name: 'lucid-saga-13.apk',
      onProgress: (_) {},
    );

    test('must be exactly the published size', () async {
      final longer = MockClient((_) async => http.Response.bytes([1, 2, 3, 4, 5], 200));
      await expectLater(download(longer), throwsA(UpdateProblem.corrupt));
      final shorter = MockClient((_) async => http.Response.bytes([1, 2], 200));
      await expectLater(download(shorter), throwsA(UpdateProblem.download));
      expect(Directory('${updates.path}/nested').listSync(), isEmpty);
    });

    test('fails on an error reply or a dropped connection', () async {
      final expired = MockClient((_) async => http.Response('AccessDenied', 403));
      await expectLater(download(expired), throwsA(UpdateProblem.download));
      final dropped = MockClient((_) async => throw http.ClientException('reset'));
      await expectLater(download(dropped), throwsA(UpdateProblem.download));
    });
  });

  group('the banner and Account', () {
    Future<void> launch(WidgetTester tester, {String location = '/discover'}) async {
      await tester.runAsync(
        () => harness.launch(
          tester,
          location: location,
          overrides: [
            selfUpdateProvider.overrideWithValue(true),
            appInstallerProvider.overrideWithValue(installer),
          ],
        ),
      );
      await settle(tester);
    }

    testWidgets('offers a newer build above the tabs, and Later hides it', (tester) async {
      publish(13);
      await launch(tester);
      final l10n = await english();

      expect(find.text(l10n.updateAvailable), findsOneWidget);
      expect(find.text(l10n.updateAvailableBody('1.0.0', 13)), findsOneWidget);

      await tester.tap(find.text(l10n.updateLater));
      await settle(tester);
      expect(find.byKey(const Key('update.banner')), findsNothing);
    });

    testWidgets('Update downloads it and Android takes over', (tester) async {
      publish(13);
      await launch(tester);
      final l10n = await english();

      await tester.runAsync(() async {
        await tester.tap(find.byKey(const Key('update.now')));
        for (var i = 0; i < 50 && installer.installs.isEmpty; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      await settle(tester);

      expect(installer.installs, hasLength(1));
      expect(find.text(l10n.updateInstalling), findsOneWidget);

      await tester.runAsync(() async {
        installer.finish(InstallOutcome.started);
        await Future<void>.delayed(Duration.zero);
      });
      await settle(tester);

      expect(installer.closes, 1);
      expect(find.text(l10n.updateReplacing), findsOneWidget);
      expect(find.byKey(const Key('update.now')), findsNothing);
      expect(find.text(l10n.updateLater), findsNothing);
    });

    testWidgets('shows nothing on the newest build', (tester) async {
      publish(12);
      await launch(tester);

      expect(find.byKey(const Key('update.banner')), findsNothing);
    });

    testWidgets('Account shows this build and checks for a newer one', (tester) async {
      await launch(tester, location: '/account');
      final l10n = await english();
      final tile = find.byKey(const Key('account.update'));
      await tester.ensureVisible(tile);
      await settle(tester);

      expect(find.text(l10n.accountVersion('1.0.0', 12)), findsOneWidget);
      expect(find.text(l10n.accountUpToDate), findsOneWidget);

      publish(13);
      await tester.runAsync(() async {
        await tester.tap(find.descendant(of: tile, matching: find.text(l10n.accountUpdateCheck)));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await settle(tester);
      expect(find.text(l10n.accountUpdateReady(13)), findsOneWidget);
      expect(find.descendant(of: tile, matching: find.text(l10n.updateNow)), findsOneWidget);
    });

    testWidgets('Account has no app section in a build that an app store updates', (tester) async {
      await tester.runAsync(() => harness.launch(tester, location: '/account'));
      await settle(tester);

      expect(find.byKey(const Key('account.update'), skipOffstage: false), findsNothing);
    });
  });
}
