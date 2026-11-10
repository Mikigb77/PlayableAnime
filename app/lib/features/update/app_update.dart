import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/api/api_providers.dart';
import '../../core/config.dart';
import '../../core/json.dart';
import 'apk_download.dart';
import 'update_problem.dart';

export 'update_problem.dart';

/// The newest build the deploy published, from `GET /v1/app/latest` (S12).
@immutable
class AppRelease {
  const AppRelease({
    required this.build,
    required this.version,
    required this.size,
    required this.sha256,
    required this.url,
    required this.expiresAt,
  });

  factory AppRelease.fromJson(JsonMap json) => AppRelease(
    build: json['build'] as int,
    version: json['version'] as String,
    size: json['size'] as int,
    sha256: json['sha256'] as String,
    url: Uri.parse(json['url'] as String),
    expiresAt: DateTime.parse(json['expires_at'] as String),
  );

  /// Android's versionCode, which grows with every deploy.
  final int build;

  /// The version name, such as 1.0.0.
  final String version;

  /// The APK's size in bytes and its SHA-256, checked before Android sees the file.
  final int size;
  final String sha256;

  /// Downloads the APK until [expiresAt].
  final Uri url;
  final DateTime expiresAt;

  /// The size in whole megabytes, at least 1, for the offer.
  int get megabytes => math.max(1, (size / 1000000).round());
}

/// This install of the app: its build and version, and where it keeps a downloaded update.
@immutable
class InstalledApp {
  const InstalledApp({required this.build, required this.version, required this.updatesDir});

  final int build;
  final String version;
  final String updatesDir;
}

/// Android's side of updating: what is installed, the network, and Android's own installer.
abstract interface class AppInstaller {
  /// This install, or null where the app can't update itself (the web, iOS).
  Future<InstalledApp?> installed();

  /// Whether the phone is on a network that isn't metered, such as Wi-Fi, so the app may fetch a
  /// newer build before the player asks for it.
  Future<bool> unmetered();

  /// Opens Android's installer on the APK at [path], whose SHA-256 must be [sha256]. Android asks
  /// the player, installs it, which ends this app, and then offers Open, which starts the new
  /// build. Throws [UpdateProblem] when the installer can't open.
  Future<void> install(String path, String sha256);

  /// Fires when Android's installer closes and this app is still running: the player said no, or
  /// Android couldn't install it and said why on its own screen.
  Stream<void> get closed;
}

/// The Kotlin side is `MainActivity.kt`: it opens Android's installer on the file through
/// `UpdateFileProvider`, which lets only that installer read it.
class PlatformAppInstaller implements AppInstaller {
  PlatformAppInstaller() {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'installerClosed') _closed.add(null);
    });
  }

  static const _channel = MethodChannel('lucid_saga/app_update');
  final _closed = StreamController<void>.broadcast();

  bool get _android => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  @override
  Future<InstalledApp?> installed() async {
    if (!_android) return null;
    final info = await _channel.invokeMapMethod<String, Object?>('info');
    if (info == null) return null;
    return InstalledApp(
      build: info['build']! as int,
      version: info['version']! as String,
      updatesDir: info['updates_dir']! as String,
    );
  }

  @override
  Future<bool> unmetered() async =>
      _android && (await _channel.invokeMethod<bool>('unmetered') ?? false);

  @override
  Future<void> install(String path, String sha256) async {
    try {
      await _channel.invokeMethod<void>('install', {'path': path, 'sha256': sha256});
    } on PlatformException catch (e) {
      throw e.code == 'checksum' ? UpdateProblem.corrupt : UpdateProblem.install;
    }
  }

  @override
  Stream<void> get closed => _closed.stream;
}

enum UpdatePhase {
  /// This build doesn't update itself: an app store does, or it is a development build.
  off,

  /// Not checked yet.
  unknown,
  checking,
  upToDate,

  /// A newer build is out and isn't on the phone yet: it downloads when the player asks.
  available,

  /// Fetching the newer build on Wi-Fi before the player asks. Nothing shows for it.
  preparing,

  /// Downloading it because the player asked; Android's installer opens once it's in.
  downloading,

  /// On the phone and checked, waiting for the player's Install.
  ready,

  /// Android's installer is open on it. The app is covered until Android replaces it, which ends
  /// the app, or the installer closes.
  installing,
  failed,
}

@immutable
class UpdateState {
  const UpdateState(
    this.phase, {
    this.installed,
    this.release,
    this.progress,
    this.problem,
    this.dismissed = false,
    this.justUpdated = false,
  });

  static const off = UpdateState(UpdatePhase.off);
  static const unknown = UpdateState(UpdatePhase.unknown);

  final UpdatePhase phase;
  final InstalledApp? installed;

  /// The newer build, from [UpdatePhase.available] on.
  final AppRelease? release;

  /// How much of the download is done, from 0 to 1.
  final double? progress;
  final UpdateProblem? problem;

  /// The player chose Later: the banner stays away until the app starts again, and Account still
  /// offers the update.
  final bool dismissed;

  /// This run is the first on a newer build than the last run's, so the app says it was updated.
  final bool justUpdated;

  /// Whether there is a newer build to offer, or one on its way.
  bool get hasUpdate => release != null && phase.index >= UpdatePhase.available.index;

  UpdateState copyWith({
    required UpdatePhase phase,
    AppRelease? release,
    double? progress,
    UpdateProblem? problem,
    bool? dismissed,
    bool? justUpdated,
  }) => UpdateState(
    phase,
    installed: installed,
    release: release ?? this.release,
    progress: progress,
    problem: problem,
    dismissed: dismissed ?? this.dismissed,
    justUpdated: justUpdated ?? this.justUpdated,
  );
}

/// Whether this build updates itself (`--dart-define=SELF_UPDATE=true`, which the deploy's APK
/// has). Tests override it.
final selfUpdateProvider = Provider<bool>((ref) => AppConfig.selfUpdate);

final appInstallerProvider = Provider<AppInstaller>((ref) => PlatformAppInstaller());

final appUpdateProvider = NotifierProvider<AppUpdateController, UpdateState>(
  AppUpdateController.new,
);

/// Checks for a newer build, fetches it, and opens Android's installer on it (S12). On Wi-Fi it
/// fetches the build as soon as it sees it, so the offer is ready to install with one tap. The
/// APK on the GitHub release does this; a build that Google Play updates never does, as Play's
/// policy requires.
class AppUpdateController extends Notifier<UpdateState> {
  /// A check runs at most this often on its own: at start, and when the app comes back.
  static const checkEvery = Duration(minutes: 30);

  /// The build the app last ran as, kept on the phone, to say "updated" once on a newer one.
  static const lastBuildKey = 'update.last_build';

  DateTime? _lastCheck;
  StreamSubscription<void>? _closed;

  /// The downloaded APK, of the right size, and the build it holds.
  ({String path, AppRelease release})? _apk;

  @override
  UpdateState build() {
    ref.onDispose(() => _closed?.cancel());
    return ref.watch(selfUpdateProvider) ? UpdateState.unknown : UpdateState.off;
  }

  AppInstaller get _installer => ref.read(appInstallerProvider);
  ApiClient get _api => ref.read(apiClientProvider);

  /// A check or an update leaves alone one already on its way.
  bool get _busy => switch (state.phase) {
    UpdatePhase.off ||
    UpdatePhase.checking ||
    UpdatePhase.preparing ||
    UpdatePhase.downloading ||
    UpdatePhase.installing => true,
    _ => false,
  };

  /// Asks the API for the newest build. On its own (at start and on resume) at most every
  /// [checkEvery], quietly: a failed check changes nothing. [now] checks at once and shows the
  /// result, for the player's "Check for updates". On Wi-Fi a newer build is fetched right away.
  Future<void> check({bool now = false}) async {
    if (_busy) return;
    final last = _lastCheck;
    if (!now && last != null && DateTime.now().difference(last) < checkEvery) return;
    _lastCheck = DateTime.now();
    final before = state;
    if (now) state = before.copyWith(phase: UpdatePhase.checking);
    try {
      var installed = before.installed;
      var justUpdated = before.justUpdated;
      if (installed == null) {
        installed = await _installer.installed();
        if (installed == null) {
          state = UpdateState.off;
          return;
        }
        justUpdated = await _noteBuild(installed.build);
      }
      final release = await _latest();
      if (!ref.mounted) return;
      if (release == null || release.build <= installed.build) {
        _apk = null;
        await clearDownloads(installed.updatesDir);
        if (!ref.mounted) return;
        state = UpdateState(UpdatePhase.upToDate, installed: installed, justUpdated: justUpdated);
        return;
      }
      // Later holds for that build only.
      final dismissed = before.dismissed && before.release?.build == release.build;
      if (_apk?.release.build != release.build) _apk = null;
      final UpdatePhase phase;
      if (_apk != null) {
        phase = UpdatePhase.ready;
      } else if (await _canFetchQuietly(release, installed)) {
        phase = UpdatePhase.preparing;
      } else {
        phase = UpdatePhase.available;
      }
      if (!ref.mounted) return;
      state = UpdateState(
        phase,
        installed: installed,
        release: release,
        progress: phase == UpdatePhase.preparing ? 0 : null,
        dismissed: dismissed,
        justUpdated: justUpdated,
      );
      if (phase == UpdatePhase.preparing) await _download(release, installed);
    } on Object catch (e) {
      if (!ref.mounted) return;
      final problem = e is UpdateProblem ? e : UpdateProblem.download;
      state = now ? before.copyWith(phase: UpdatePhase.failed, problem: problem) : before;
    }
  }

  /// The banner's Later.
  void dismiss() => state = UpdateState(
    state.phase,
    installed: state.installed,
    release: state.release,
    progress: state.progress,
    problem: state.problem,
    dismissed: true,
    justUpdated: state.justUpdated,
  );

  /// The "updated" note was shown.
  void acknowledgeUpdated() => state = state.copyWith(
    phase: state.phase,
    progress: state.progress,
    problem: state.problem,
    justUpdated: false,
  );

  /// The player's Update or Install: opens Android's installer on the fetched build, or downloads
  /// it first and then opens the installer. Once Android has installed it, which ends the app, its
  /// Open button starts the new build.
  Future<void> update() async {
    final installed = state.installed;
    final offered = state.release;
    if (installed == null || offered == null || !state.hasUpdate) return;
    if (state.phase == UpdatePhase.preparing) {
      // Already on its way: show it, and open the installer as soon as it's in.
      state = state.copyWith(
        phase: UpdatePhase.downloading,
        progress: state.progress,
        dismissed: false,
      );
      return;
    }
    if (_busy) return;
    if (_apk?.release.build == offered.build) return _install();
    // The player asked for it, so the banner shows how it goes even after a Later.
    state = state.copyWith(phase: UpdatePhase.downloading, progress: 0, dismissed: false);
    final AppRelease? release;
    try {
      // A fresh URL: the one from the check may have expired while the banner waited.
      release = await _latest();
    } on Object catch (e) {
      if (!ref.mounted) return;
      final problem = e is UpdateProblem ? e : UpdateProblem.download;
      state = state.copyWith(phase: UpdatePhase.failed, problem: problem);
      return;
    }
    if (!ref.mounted) return;
    if (release == null || release.build <= installed.build) {
      state = UpdateState(UpdatePhase.upToDate, installed: installed);
      return;
    }
    state = state.copyWith(phase: UpdatePhase.downloading, release: release, progress: 0);
    await _download(release, installed);
  }

  /// The cover's way out when the app is back in front with no word from Android's installer.
  void installerClosed() {
    if (!ref.mounted || state.phase != UpdatePhase.installing) return;
    state = state.copyWith(phase: _apk == null ? UpdatePhase.available : UpdatePhase.ready);
  }

  /// Downloads [release]: quietly while [UpdatePhase.preparing], and then it is ready; or
  /// because the player asked ([UpdatePhase.downloading]), and then the installer opens.
  Future<void> _download(AppRelease release, InstalledApp installed) async {
    try {
      final path = await downloadApk(
        client: ref.read(httpClientProvider),
        url: release.url,
        size: release.size,
        folder: installed.updatesDir,
        name: _apkName(release),
        onProgress: (done) {
          final phase = state.phase;
          if (ref.mounted && (phase == UpdatePhase.preparing || phase == UpdatePhase.downloading)) {
            state = state.copyWith(phase: phase, progress: done);
          }
        },
      );
      if (!ref.mounted) return;
      _apk = (path: path, release: release);
      switch (state.phase) {
        case UpdatePhase.downloading:
          await _install();
        case UpdatePhase.preparing:
          state = state.copyWith(phase: UpdatePhase.ready);
        case _:
          break;
      }
    } on Object catch (e) {
      if (!ref.mounted) return;
      switch (state.phase) {
        case UpdatePhase.downloading:
          final problem = e is UpdateProblem ? e : UpdateProblem.download;
          state = state.copyWith(phase: UpdatePhase.failed, problem: problem);
        // Fetching it quietly failed: the banner offers it as usual, and the next check tries
        // again.
        case UpdatePhase.preparing:
          state = state.copyWith(phase: UpdatePhase.available);
        case _:
          break;
      }
    }
  }

  /// Opens Android's installer on the fetched build and covers the app until Android replaces it
  /// or the installer closes.
  Future<void> _install() async {
    final apk = _apk;
    if (apk == null) return;
    _closed ??= _installer.closed.listen((_) => installerClosed());
    state = state.copyWith(phase: UpdatePhase.installing, release: apk.release, dismissed: false);
    try {
      await _installer.install(apk.path, apk.release.sha256);
    } on Object catch (e) {
      if (!ref.mounted) return;
      final problem = e is UpdateProblem ? e : UpdateProblem.install;
      // A damaged file goes, so Try again downloads it again.
      if (problem == UpdateProblem.corrupt) {
        _apk = null;
        if (state.installed case final installed?) await clearDownloads(installed.updatesDir);
        if (!ref.mounted) return;
      }
      state = state.copyWith(phase: UpdatePhase.failed, problem: problem);
    }
  }

  /// Whether to fetch [release] before the player asks: it's on the phone already, or the phone
  /// is on Wi-Fi or another network that isn't metered.
  Future<bool> _canFetchQuietly(AppRelease release, InstalledApp installed) async {
    try {
      final name = _apkName(release);
      if (await hasApk(folder: installed.updatesDir, name: name, size: release.size)) return true;
      return await _installer.unmetered();
    } on Object {
      return false;
    }
  }

  /// Keeps the build this run is on, and says whether it is newer than the last run's.
  Future<bool> _noteBuild(int build) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final last = prefs.getInt(lastBuildKey);
      if (last != build) await prefs.setInt(lastBuildKey, build);
      return last != null && last < build;
    } on Object {
      return false;
    }
  }

  static String _apkName(AppRelease release) => 'lucid-saga-${release.build}.apk';

  /// The newest build, or null when none is published (404).
  Future<AppRelease?> _latest() async {
    try {
      final json = await _api.get('/v1/app/latest', query: {'platform': 'android'}) as JsonMap;
      return AppRelease.fromJson(json);
    } on ApiException catch (e) {
      if (e.code == ApiErrorCode.notFound) return null;
      throw UpdateProblem.download;
    } on TypeError {
      throw UpdateProblem.download;
    }
  }
}
