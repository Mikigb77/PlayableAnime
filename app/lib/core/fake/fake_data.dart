import 'fake_account.dart';
import 'fake_auth.dart';
import 'fake_drafts.dart';
import 'fake_pictures.dart';
import 'fake_stories.dart';

/// The fake backend's in-memory database. Each feature area keeps its own slice, defined in its
/// own file; adding a slice here is the only shared edit.
class FakeData {
  FakeData() {
    stories.seed(ownerId: FakeAuthState.demoUserId);
  }

  final auth = FakeAuthState();
  final account = FakeAccountState();
  final drafts = FakeDraftState();
  final stories = FakeStoryState();
  final pictures = FakePictureState();
  final reports = <Map<String, dynamic>>[];

  var _nextId = 100;

  /// A fresh opaque id such as `story_101`.
  String id(String prefix) => '${prefix}_${++_nextId}';
}

/// Fake picture URLs point at bundled assets; the design system's image loader understands them.
abstract final class FakeAssets {
  static const peaks = 'asset:assets/fake/scene-peaks.jpg';
  static const city = 'asset:assets/fake/scene-city.jpg';
  static const castle = 'asset:assets/fake/scene-castle.jpg';
  static const forest = 'asset:assets/fake/scene-forest.jpg';
  static const nebula = 'asset:assets/fake/scene-nebula.jpg';
  static const dawn = 'asset:assets/fake/scene-dawn.jpg';

  static String portrait(int i) => 'asset:assets/fake/portrait-${(i % 4) + 1}.jpg';

  /// Scene pictures that suit a genre, the cover first.
  static List<String> scenesFor(String genre) {
    final g = genre.toLowerCase();
    if (g.contains('cultivation')) return const [peaks, forest];
    if (g.contains('knight')) return const [castle, dawn];
    if (g.contains('reincarnat') || g.contains('isekai')) return const [dawn, castle];
    if (g.contains('science') || g.contains('sci')) return const [nebula];
    if (g.contains('modern') || g.contains('supernatural') || g.contains('crime')) {
      return const [city];
    }
    return const [forest, castle];
  }

  /// The cover picture for a genre.
  static String forGenre(String genre) => scenesFor(genre).first;
}
