import 'fake_backend.dart';

/// The fake `GET /v1/app/latest` (S12): the newest build in [FakeReleaseState], or a 404 until a
/// test publishes one, and the fake APK its URL downloads. The fake app never updates itself on
/// its own, since `SELF_UPDATE` is off there.
void registerReleaseRoutes(FakeBackend b) {
  b.route('GET', '/v1/app/latest', (r) {
    final platform = r.query('platform') ?? 'android';
    if (platform != 'android') throw const FakeError.validation('Only android has builds.');
    final release = b.data.releases.latest;
    if (release == null) {
      throw const FakeError.notFound('No build of the app has been published yet.');
    }
    return FakeResponse.json({
      'platform': 'android',
      'build': release.build,
      'version': release.version,
      'size': release.apk.length,
      'sha256': release.sha256,
      'url': '${FakeBackend.baseUrl}${FakeReleaseState.downloadPath}${release.build}.apk',
      'expires_at': b.now().toUtc().add(const Duration(minutes: 30)).toIso8601String(),
    });
  });
  // A signed URL needs no session, as in Cloud Storage.
  b.route('GET', '${FakeReleaseState.downloadPath}:build.apk', (r) {
    final release = b.data.releases.latest;
    if (release == null || '${release.build}' != r.param('build')) {
      throw const FakeError.notFound('No such build');
    }
    return FakeResponse.file(release.apk, 'application/vnd.android.package-archive');
  }, public: true);
}

/// A build the fake deploy published.
class FakeRelease {
  const FakeRelease({
    required this.build,
    this.version = '1.0.0',
    this.apk = const [0x50, 0x4b, 0x03, 0x04],
    this.sha256 = 'f00d',
  });

  final int build;
  final String version;
  final List<int> apk;
  final String sha256;
}

class FakeReleaseState {
  static const downloadPath = '/fake-releases/lucid-saga-';

  /// The newest build, or null before any is published.
  FakeRelease? latest;
}
