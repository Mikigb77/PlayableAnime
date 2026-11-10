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
import 'package:playable_anime/features/update/update_cover.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers.dart';
import 'harness.dart';

/// Stands in for Android: this install is build 12, on a metered network unless [onWifi], and it
/// records what Android's installer was opened on.
class FakeInstaller implements AppInstaller {
  FakeInstaller(this.updatesDir, {this.build = 12, this.onWifi = false, this.failInstall});

  final String updatesDir;
  final int build;
  bool onWifi;
  UpdateProblem? failInstall;
  final installs = <(String path, String sha256)>[];
  final _closed = StreamController<void>.broadcast();

  /// Android's installer closes while the app still runs.
  void close() => _closed.add(null);

  @override
  Future<InstalledApp?> installed() async =>
      InstalledApp(build: build, version: '1.0.0', updatesDir: updatesDir);

  @override
  Future<bool> unmetered() async => onWifi;

  @override
  Future<void> install(String path, String sha256) async {
    if (failInstall case final problem?) throw problem;
    installs.add((path, sha256));
  }

  @override
  Stream<void> get closed => _closed.stream;
}

void main() {
  late Directory updates;
  late AppHarness harness;
  late FakeInstaller installer;
  late DateTime time;

  setUp(() {
    time = DateTime.utc(2026, 11, 10, 12);
    updates = Directory.systemTemp.createTempSync('lucid-updates');
    addTearDown(() {
      if (updates.existsSync()) updates.deleteSync(recursive: true);
    });
    harness = AppHarness();
    installer = FakeInstaller(updates.path);
  });

  List<FakeRequest> checks() => harness.sent('GET', (p) => p == '/v1/app/latest');
  List<FakeRequest> downloads() => harness.sent('GET', (p) => p.startsWith('/fake-releases/'));

  /// Answers like the fake backend, once [wait] lets each request through.
  http.Client held(Future<void> Function(http.BaseRequest request) wait) =>
      MockClient.streaming((request, body) async {
        await wait(request);
        final copy = http.Request(request.method, request.url)..headers.addAll(request.headers);
        copy.bodyBytes = await body.toBytes();
        return harness.backend.send(copy);
      });

  /// Holds each APK download until [gate] completes.
  http.Client heldDownloads(Completer<void> gate) => held((request) async {
    if (request.url.path.startsWith('/fake-releases/')) await gate.future;
  });

  /// Holds the second check until [gate] completes.
  http.Client heldSecondCheck(Completer<void> gate) {
    var checks = 0;
    return held((request) async {
      if (request.url.path == '/v1/app/latest' && ++checks == 2) await gate.future;
    });
  }

  Future<ProviderContainer> signedIn({bool selfUpdate = true, http.Client? client}) async {
    await harness.signIn();
    final container = ProviderContainer(
      overrides: [
        httpClientProvider.overrideWithValue(client ?? harness.backend),
        apiBaseUrlProvider.overrideWithValue(FakeBackend.baseUrl),
        sessionStoreProvider.overrideWithValue(harness.store),
        selfUpdateProvider.overrideWithValue(selfUpdate),
        appInstallerProvider.overrideWithValue(installer),
        updateClockProvider.overrideWithValue(() => time),
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

    test('is up to date while nothing is published, and clears old downloads', () async {
      File('${updates.path}/lucid-saga-12.apk').writeAsBytesSync([9, 9]);
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.upToDate);
      expect(state.installed?.build, 12);
      expect(checks().single.uri.queryParameters['platform'], 'android');
      expect(updates.listSync(), isEmpty);
    });

    test('is up to date on the newest build or a newer one', () async {
      publish(12);
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.upToDate);
      expect(c.read(appUpdateProvider).hasUpdate, isFalse);
    });

    test('offers a newer build on a metered network, without downloading it', () async {
      publish(13, apk: List.filled(2600000, 1));
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.available);
      expect(state.release?.build, 13);
      expect(state.release?.version, '1.0.0');
      expect(state.release?.megabytes, 3);
      expect(state.hasUpdate, isTrue);
      expect(downloads(), isEmpty);
    });

    test('on Wi-Fi fetches a newer build at once, so it is ready to install', () async {
      installer.onWifi = true;
      File('${updates.path}/lucid-saga-11.apk').writeAsBytesSync([9, 9]);
      publish(13, apk: List.filled(1000, 7));
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.ready);
      expect(state.release?.build, 13);
      expect(File('${updates.path}/lucid-saga-13.apk').readAsBytesSync(), List.filled(1000, 7));
      expect(File('${updates.path}/lucid-saga-11.apk').existsSync(), isFalse);
      expect(downloads(), hasLength(1));
      expect(installer.installs, isEmpty);
    });

    test('a build already on the phone is ready without the network', () async {
      File('${updates.path}/lucid-saga-13.apk').writeAsBytesSync([1, 2, 3, 4, 5]);
      publish(13);
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);
      expect(downloads(), isEmpty);
    });

    test('a quiet fetch that fails is offered as usual, with no error', () async {
      installer.onWifi = true;
      publish(13);
      final c = await signedIn(
        client: MockClient((request) async {
          if (request.url.path.startsWith('/fake-releases/')) return http.Response('gone', 403);
          return http.Response.fromStream(await harness.backend.send(request));
        }),
      );

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.available);
      expect(state.problem, isNull);
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

    test('Update downloads the newer build and opens Android\'s installer on it', () async {
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

    test('Install opens the installer on the fetched build at once', () async {
      installer.onWifi = true;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);

      controller.dismiss();
      await controller.update();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(c.read(appUpdateProvider).dismissed, isFalse);
      expect(installer.installs.single.$1, '${updates.path}/lucid-saga-13.apk');
      expect(downloads(), hasLength(1));
      expect(checks(), hasLength(1));
    });

    test('Update while it is fetched quietly shows the download, then installs it', () async {
      installer.onWifi = true;
      publish(13);
      final gate = Completer<void>();
      final c = await signedIn(client: heldDownloads(gate));
      final controller = c.read(appUpdateProvider.notifier);

      final checking = controller.check();
      for (var i = 0; i < 20 && c.read(appUpdateProvider).phase != UpdatePhase.preparing; i++) {
        await Future<void>.delayed(Duration.zero);
      }
      expect(c.read(appUpdateProvider).phase, UpdatePhase.preparing);

      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.downloading);
      await controller.update(); // a second tap starts nothing new
      gate.complete();
      await checking;

      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(installer.installs, hasLength(1));
      expect(downloads(), hasLength(1));
    });

    test('the installer closing with the app still here offers it again', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      await controller.update();

      // A check, or another tap, while the installer is open starts nothing.
      await controller.check(now: true);
      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(installer.installs, hasLength(1));

      installer.close();
      await Future<void>.delayed(Duration.zero);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);
      // The finished download is used again.
      await controller.update();
      expect(installer.installs, hasLength(2));
      expect(downloads(), hasLength(1));
    });

    test('the cover\'s way out only acts while the installer is open', () async {
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      controller.installerClosed();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);

      await controller.update();
      controller.installerClosed();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);
    });

    test('a newer build replaces one that is ready', () async {
      installer.onWifi = true;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);

      publish(14, apk: [4, 4, 4]);
      await controller.check(now: true);

      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);
      expect(c.read(appUpdateProvider).release?.build, 14);
      expect(updates.listSync().map((f) => f.path), ['${updates.path}/lucid-saga-14.apk']);
      await controller.update();
      expect(installer.installs.single.$1, '${updates.path}/lucid-saga-14.apk');
    });

    test('an installer that can\'t open is a failed install, and Try again reopens it', () async {
      installer.failInstall = UpdateProblem.install;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      await controller.update();
      controller.dismiss();
      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.failed);
      expect(state.problem, UpdateProblem.install);

      installer.failInstall = null;
      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(c.read(appUpdateProvider).dismissed, isFalse);
      expect(downloads(), hasLength(1));
    });

    test('a damaged download is never installed, and Try again downloads it again', () async {
      installer.failInstall = UpdateProblem.corrupt;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      await controller.update();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.failed);
      expect(c.read(appUpdateProvider).problem, UpdateProblem.corrupt);

      installer.failInstall = null;
      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(downloads(), hasLength(2));
    });

    test('a fetched build that Android cleared from the cache downloads again', () async {
      installer.onWifi = true;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.ready);

      // Android trims the app's cache.
      updates.deleteSync(recursive: true);
      installer.onWifi = false;
      await controller.check(now: true);
      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);

      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(File(installer.installs.single.$1).existsSync(), isTrue);
      expect(downloads(), hasLength(2));
    });

    test('Install on a build the cache lost downloads it again instead of failing', () async {
      installer.onWifi = true;
      publish(13);
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      updates.deleteSync(recursive: true);
      await controller.update();

      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(File(installer.installs.single.$1).existsSync(), isTrue);
      expect(downloads(), hasLength(2));
    });

    test('a check on its own leaves alone an update the player starts meanwhile', () async {
      publish(13);
      final gate = Completer<void>();
      final c = await signedIn(client: heldSecondCheck(gate));
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);

      time = time.add(AppUpdateController.checkEvery);
      final checking = controller.check(); // waits on the API
      await controller.update();
      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      gate.complete();
      await checking;

      expect(c.read(appUpdateProvider).phase, UpdatePhase.installing);
      expect(installer.installs, hasLength(1));
      expect(downloads(), hasLength(1));
    });

    test('Later while a check waits on the API holds', () async {
      publish(13);
      final gate = Completer<void>();
      final c = await signedIn(client: heldSecondCheck(gate));
      final controller = c.read(appUpdateProvider.notifier);
      await controller.check();

      time = time.add(AppUpdateController.checkEvery);
      final checking = controller.check();
      controller.dismiss();
      gate.complete();
      await checking;

      expect(checks(), hasLength(2));
      expect(c.read(appUpdateProvider).phase, UpdatePhase.available);
      expect(c.read(appUpdateProvider).dismissed, isTrue);
    });

    test('says once that the app was updated, on the first run of a newer build', () async {
      SharedPreferences.setMockInitialValues({AppUpdateController.lastBuildKey: 11});
      final c = await signedIn();
      final controller = c.read(appUpdateProvider.notifier);

      await controller.check();
      expect(c.read(appUpdateProvider).justUpdated, isTrue);
      controller.acknowledgeUpdated();
      expect(c.read(appUpdateProvider).justUpdated, isFalse);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getInt(AppUpdateController.lastBuildKey), 12);

      // The next start on the same build says nothing.
      final again = await signedIn();
      await again.read(appUpdateProvider.notifier).check();
      expect(again.read(appUpdateProvider).justUpdated, isFalse);
    });

    test('says it was updated even when the API can\'t be reached', () async {
      SharedPreferences.setMockInitialValues({AppUpdateController.lastBuildKey: 11});
      final c = await signedIn(
        client: MockClient((request) async {
          if (request.url.path == '/v1/app/latest') return http.Response('oops', 502);
          return http.Response.fromStream(await harness.backend.send(request));
        }),
      );

      await c.read(appUpdateProvider.notifier).check();

      final state = c.read(appUpdateProvider);
      expect(state.phase, UpdatePhase.unknown);
      expect(state.justUpdated, isTrue);
      expect(state.installed?.build, 12);
    });

    test('says nothing on the very first run', () async {
      final c = await signedIn();

      await c.read(appUpdateProvider.notifier).check();

      expect(c.read(appUpdateProvider).justUpdated, isFalse);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getInt(AppUpdateController.lastBuildKey), 12);
    });
  });

  group('the Android side', () {
    const channel = MethodChannel('lucid_saga/app_update');

    test('says when Android\'s installer closes', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final android = PlatformAppInstaller();
      var closed = 0;
      android.closed.listen((_) => closed++);

      await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
        channel.name,
        const StandardMethodCodec().encodeMethodCall(const MethodCall('installerClosed')),
        (_) {},
      );
      await Future<void>.delayed(Duration.zero);

      expect(closed, 1);
    });

    test('asks Android about the network and the installed build', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(channel, (call) async {
        return switch (call.method) {
          'unmetered' => true,
          'info' => {'build': 40, 'version': '1.0.0', 'updates_dir': '/cache/updates'},
          _ => null,
        };
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

      final android = PlatformAppInstaller();
      expect(await android.unmetered(), isTrue);
      final installed = await android.installed();
      expect(installed?.build, 40);
      expect(installed?.updatesDir, '/cache/updates');
    });

    test('a failed hand-over is an install problem, and a damaged file says so', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      var code = 'failed';
      messenger.setMockMethodCallHandler(channel, (_) async => throw PlatformException(code: code));
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));

      await expectLater(
        PlatformAppInstaller().install('/updates/a.apk', 'ab'),
        throwsA(UpdateProblem.install),
      );
      code = 'checksum';
      await expectLater(
        PlatformAppInstaller().install('/updates/a.apk', 'ab'),
        throwsA(UpdateProblem.corrupt),
      );
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

    test('a finished download counts only at its full size, and can be cleared', () async {
      final folder = '${updates.path}/nested';
      expect(await hasApk(folder: folder, name: 'lucid-saga-13.apk', size: 4), isFalse);
      await download(MockClient((_) async => http.Response.bytes([1, 2, 3, 4], 200)));
      expect(await hasApk(folder: folder, name: 'lucid-saga-13.apk', size: 4), isTrue);
      expect(await hasApk(folder: folder, name: 'lucid-saga-13.apk', size: 5), isFalse);

      await clearDownloads(folder);
      expect(Directory(folder).listSync(), isEmpty);
      await clearDownloads('${updates.path}/missing');
    });
  });

  group('the banner, the cover and Account', () {
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
      // The check reads and clears the updates folder, which takes real time.
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
      await settle(tester);
    }

    /// Taps [button] and waits, in real time, for the download to land and the installer to open.
    Future<void> tapUntilInstalling(WidgetTester tester, Finder button) async {
      await tester.runAsync(() async {
        await tester.tap(button);
        for (var i = 0; i < 100 && installer.installs.isEmpty; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
      });
      await settle(tester);
    }

    testWidgets('offers a newer build above the tabs with its size, and Later hides it', (
      tester,
    ) async {
      publish(13, apk: List.filled(2600000, 1));
      await launch(tester);
      final l10n = await english();

      expect(find.text(l10n.updateAvailable), findsOneWidget);
      expect(find.text(l10n.updateAvailableBody('1.0.0', 13, 3)), findsOneWidget);
      expect(find.text(l10n.updateNow), findsOneWidget);

      await tester.tap(find.text(l10n.updateLater));
      await settle(tester);
      expect(find.byKey(const Key('update.banner')), findsNothing);
    });

    testWidgets('on Wi-Fi the offer is ready to install, and Install covers the app', (
      tester,
    ) async {
      installer.onWifi = true;
      publish(13);
      await launch(tester);
      final l10n = await english();

      expect(find.text(l10n.updateReady), findsOneWidget);
      expect(find.text(l10n.updateReadyBody('1.0.0', 13)), findsOneWidget);
      expect(find.byKey(const Key('update.cover')), findsNothing);

      await tapUntilInstalling(tester, find.text(l10n.updateInstall));

      // The whole app is covered while Android installs it, and nothing under it can be pressed.
      expect(find.byKey(const Key('update.cover')), findsOneWidget);
      expect(find.text(l10n.updateCoverTitle), findsOneWidget);
      expect(find.text(l10n.updateCoverBody), findsOneWidget);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      await tester.tap(find.text(l10n.navAccount), warnIfMissed: false);
      await settle(tester);
      expect(find.byKey(const Key('account.update')), findsNothing);

      // The installer closing with the app still here takes the cover away; Install reopens it.
      await tester.runAsync(() async {
        installer.close();
        await Future<void>.delayed(Duration.zero);
      });
      await settle(tester);
      expect(find.byKey(const Key('update.cover')), findsNothing);
      expect(find.text(l10n.updateInstall), findsOneWidget);
    });

    testWidgets('Update downloads it first on a metered network', (tester) async {
      publish(13);
      await launch(tester);
      final l10n = await english();

      await tapUntilInstalling(tester, find.byKey(const Key('update.now')));

      expect(installer.installs, hasLength(1));
      expect(find.byKey(const Key('update.cover')), findsOneWidget);
      expect(find.text(l10n.updateCoverTitle), findsOneWidget);
    });

    testWidgets('the cover never traps the player if the installer says nothing', (tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      publish(13);
      await launch(tester);

      await tapUntilInstalling(tester, find.byKey(const Key('update.now')));
      await tester.pump(UpdateCover.giveUpAfter * 2);
      expect(find.byKey(const Key('update.cover')), findsOneWidget);

      // The installer takes the screen, and the cover stays however long it's open.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await tester.pump(UpdateCover.giveUpAfter * 2);
      expect(find.byKey(const Key('update.cover')), findsOneWidget);

      // Back in front with no word from Android: the cover goes after a moment.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(UpdateCover.giveUpAfter ~/ 2);
      expect(find.byKey(const Key('update.cover')), findsOneWidget);
      await tester.pump(UpdateCover.giveUpAfter);
      await settle(tester);
      expect(find.byKey(const Key('update.cover')), findsNothing);
      expect(find.byKey(const Key('update.now')), findsOneWidget);
    });

    testWidgets('the cover covers any screen, and stays still with reduce motion', (tester) async {
      tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(
        disableAnimations: true,
      );
      addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
      publish(13);
      await launch(tester, location: '/account');
      final l10n = await english();
      final tile = find.byKey(const Key('account.update'));
      await tester.ensureVisible(tile);
      await settle(tester);

      await tapUntilInstalling(
        tester,
        find.descendant(of: tile, matching: find.text(l10n.updateNow)),
      );

      // Account's own line says so too, under the cover.
      final cover = find.byKey(const Key('update.cover'));
      expect(cover, findsOneWidget);
      expect(
        find.descendant(of: cover, matching: find.text(l10n.updateCoverTitle)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: cover, matching: find.byType(LinearProgressIndicator)),
        findsNothing,
      );
    });

    testWidgets('a failure says why and offers it again', (tester) async {
      installer.failInstall = UpdateProblem.install;
      publish(13);
      await launch(tester);
      final l10n = await english();

      await tapUntilInstalling(tester, find.byKey(const Key('update.now')));

      expect(find.byKey(const Key('update.cover')), findsNothing);
      expect(find.text(l10n.updateFailedInstall), findsOneWidget);
      expect(find.text(l10n.updateTryAgain), findsOneWidget);
    });

    testWidgets('says the app was updated on the first run of a newer build', (tester) async {
      SharedPreferences.setMockInitialValues({AppUpdateController.lastBuildKey: 11});
      await launch(tester);
      final l10n = await english();

      expect(find.text(l10n.updateDone('1.0.0', 12)), findsOneWidget);
      expect(find.byKey(const Key('update.banner')), findsNothing);
    });

    testWidgets('shows nothing on the newest build', (tester) async {
      publish(12);
      await launch(tester);

      expect(find.byKey(const Key('update.banner')), findsNothing);
      expect(find.byKey(const Key('update.done')), findsNothing);
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
      expect(find.text(l10n.accountUpdateOut(13)), findsOneWidget);
      expect(find.descendant(of: tile, matching: find.text(l10n.updateNow)), findsOneWidget);

      // On Wi-Fi the next check fetches it, and Account offers Install.
      installer.onWifi = true;
      await tester.runAsync(() async {
        await tester.tap(find.descendant(of: tile, matching: find.text(l10n.updateNow)));
        for (var i = 0; i < 100 && installer.installs.isEmpty; i++) {
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
        installer.close();
        await Future<void>.delayed(Duration.zero);
      });
      await settle(tester);
      expect(find.text(l10n.accountUpdateReady(13)), findsOneWidget);
      expect(find.descendant(of: tile, matching: find.text(l10n.updateInstall)), findsOneWidget);
    });

    testWidgets('Account has no app section in a build that an app store updates', (tester) async {
      await tester.runAsync(() => harness.launch(tester, location: '/account'));
      await settle(tester);

      expect(find.byKey(const Key('account.update'), skipOffstage: false), findsNothing);
    });
  });
}
