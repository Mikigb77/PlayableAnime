import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
}

/// This install of the app: its build and version, and where it keeps a downloaded update.
@immutable
class InstalledApp {
  const InstalledApp({required this.build, required this.version, required this.updatesDir});

  final int build;
  final String version;
  final String updatesDir;
}

/// How a handed-over update ended, when Android tells the app (the app is replaced on success,
/// so success is rarely heard).
enum InstallOutcome { installed, cancelled, failed }

/// Android's side of updating: what is installed, and handing a downloaded APK to its installer.
abstract interface class AppInstaller {
  /// This install, or null where the app can't update itself (the web, iOS).
  Future<InstalledApp?> installed();

  /// Hands the APK at [path] to Android's installer, which asks the player to confirm. The file's
  /// SHA-256 must be [sha256]. Throws [UpdateProblem] when it can't start.
  Future<void> install(String path, String sha256);

  /// Outcomes that arrive after [install] returned: the player said no, or Android refused.
  Stream<InstallOutcome> get outcomes;
}

/// The Kotlin side is `MainActivity.kt`: a PackageInstaller session, so no file is shared with
/// another app.
class PlatformAppInstaller implements AppInstaller {
  PlatformAppInstaller() {
    _channel.setMethodCallHandler((call) async {
      if (call.method != 'installStatus') return;
      final status = (call.arguments as Map?)?['status'];
      _outcomes.add(switch (status) {
        'installed' => InstallOutcome.installed,
        'cancelled' => InstallOutcome.cancelled,
        _ => InstallOutcome.failed,
      });
    });
  }

  static const _channel = MethodChannel('lucid_saga/app_update');
  final _outcomes = StreamController<InstallOutcome>.broadcast();

  @override
  Future<InstalledApp?> installed() async {
    if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) return null;
    final info = await _channel.invokeMapMethod<String, Object?>('info');
    if (info == null) return null;
    return InstalledApp(
      build: info['build']! as int,
      version: info['version']! as String,
      updatesDir: info['updates_dir']! as String,
    );
  }

  @override
  Future<void> install(String path, String sha256) async {
    try {
      await _channel.invokeMethod<void>('install', {'path': path, 'sha256': sha256});
    } on PlatformException catch (e) {
      throw e.code == 'checksum' ? UpdateProblem.corrupt : UpdateProblem.install;
    }
  }

  @override
  Stream<InstallOutcome> get outcomes => _outcomes.stream;
}

enum UpdatePhase {
  /// This build doesn't update itself: an app store does, or it is a development build.
  off,

  /// Not checked yet.
  unknown,
  checking,
  upToDate,
  available,
  downloading,

  /// Handed to Android, which asks the player to confirm.
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

  /// Whether there is a newer build to offer, or one on its way.
  bool get hasUpdate => release != null && phase.index >= UpdatePhase.available.index;

  UpdateState copyWith({
    required UpdatePhase phase,
    AppRelease? release,
    double? progress,
    UpdateProblem? problem,
    bool? dismissed,
  }) => UpdateState(
    phase,
    installed: installed,
    release: release ?? this.release,
    progress: progress,
    problem: problem,
    dismissed: dismissed ?? this.dismissed,
  );
}

/// Whether this build updates itself (`--dart-define=SELF_UPDATE=true`, which the deploy's APK
/// has). Tests override it.
final selfUpdateProvider = Provider<bool>((ref) => AppConfig.selfUpdate);

final appInstallerProvider = Provider<AppInstaller>((ref) => PlatformAppInstaller());

final appUpdateProvider = NotifierProvider<AppUpdateController, UpdateState>(
  AppUpdateController.new,
);

/// Checks for a newer build, downloads it and hands it to Android (S12). The APK on the GitHub
/// release does this; a build that Google Play updates never does, as Play's policy requires.
class AppUpdateController extends Notifier<UpdateState> {
  /// A check runs at most this often on its own: at start, and when the app comes back.
  static const checkEvery = Duration(minutes: 30);

  DateTime? _lastCheck;
  StreamSubscription<InstallOutcome>? _outcomes;

  @override
  UpdateState build() {
    ref.onDispose(() => _outcomes?.cancel());
    return ref.watch(selfUpdateProvider) ? UpdateState.unknown : UpdateState.off;
  }

  AppInstaller get _installer => ref.read(appInstallerProvider);
  ApiClient get _api => ref.read(apiClientProvider);

  /// A check leaves an update the player started alone; an update can start again while Android
  /// is asked, in case its question never showed or was left behind.
  bool get _busyForCheck => switch (state.phase) {
    UpdatePhase.off ||
    UpdatePhase.checking ||
    UpdatePhase.downloading ||
    UpdatePhase.installing => true,
    _ => false,
  };

  bool get _busyForUpdate => switch (state.phase) {
    UpdatePhase.off || UpdatePhase.checking || UpdatePhase.downloading => true,
    _ => false,
  };

  /// Asks the API for the newest build. On its own (at start and on resume) at most every
  /// [checkEvery], quietly: a failed check changes nothing. [now] checks at once and shows the
  /// result, for the player's "Check for updates".
  Future<void> check({bool now = false}) async {
    if (_busyForCheck) return;
    final last = _lastCheck;
    if (!now && last != null && DateTime.now().difference(last) < checkEvery) return;
    _lastCheck = DateTime.now();
    final before = state;
    if (now) state = before.copyWith(phase: UpdatePhase.checking);
    try {
      final installed = before.installed ?? await _installer.installed();
      if (installed == null) {
        state = UpdateState.off;
        return;
      }
      final release = await _latest();
      if (!ref.mounted) return;
      if (release == null || release.build <= installed.build) {
        state = UpdateState(UpdatePhase.upToDate, installed: installed);
        return;
      }
      state = UpdateState(
        UpdatePhase.available,
        installed: installed,
        release: release,
        // Later holds for that build only.
        dismissed: before.dismissed && before.release?.build == release.build,
      );
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
  );

  /// Downloads the newer build and hands it to Android, which asks the player to confirm. The
  /// app closes when Android replaces it, and opens on the new build.
  Future<void> update() async {
    final installed = state.installed;
    if (_busyForUpdate || installed == null || !state.hasUpdate) return;
    // The player asked for it, so the banner shows how it goes even after a Later.
    state = state.copyWith(phase: UpdatePhase.downloading, progress: 0, dismissed: false);
    try {
      // A fresh URL: the one from the check may have expired while the banner waited.
      final release = await _latest();
      if (release == null || release.build <= installed.build) {
        state = UpdateState(UpdatePhase.upToDate, installed: installed);
        return;
      }
      state = state.copyWith(phase: UpdatePhase.downloading, release: release, progress: 0);
      final path = await downloadApk(
        client: ref.read(httpClientProvider),
        url: release.url,
        size: release.size,
        folder: installed.updatesDir,
        name: 'lucid-saga-${release.build}.apk',
        onProgress: (done) {
          if (ref.mounted) {
            state = state.copyWith(phase: UpdatePhase.downloading, progress: done);
          }
        },
      );
      if (!ref.mounted) return;
      _outcomes ??= _installer.outcomes.listen(_onOutcome);
      state = state.copyWith(phase: UpdatePhase.installing);
      await _installer.install(path, release.sha256);
    } on Object catch (e) {
      if (!ref.mounted) return;
      final problem = e is UpdateProblem ? e : UpdateProblem.download;
      state = state.copyWith(phase: UpdatePhase.failed, problem: problem);
    }
  }

  void _onOutcome(InstallOutcome outcome) {
    if (state.phase != UpdatePhase.installing) return;
    state = switch (outcome) {
      InstallOutcome.installed => UpdateState(UpdatePhase.upToDate, installed: state.installed),
      InstallOutcome.cancelled => state.copyWith(phase: UpdatePhase.available),
      InstallOutcome.failed => state.copyWith(
        phase: UpdatePhase.failed,
        problem: UpdateProblem.install,
      ),
    };
  }

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
