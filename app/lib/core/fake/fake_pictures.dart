import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_stories.dart';

/// Fake pictures (docs/API.md, "Pictures", M1 to M8). Owned by the play screen work (WS14).
///
/// The first request for a planned picture answers `pending`; once [FakePace.picture] has passed,
/// requests answer `ready` with a bundled image. Each picture is charged once (M3). A scene whose
/// action contains `[fail:picture]` answers `skipped`, as a blocked picture would.
class FakePictureState {
  final requestedAt = <String, DateTime>{};
  final charged = <String>{};
}

void registerPictureRoutes(FakeBackend b) {
  FakeResponse picture(FakeRequest r, {required bool illustrate}) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('turn'));
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    if (scene == null) throw const FakeError.notFound('No such scene');
    final image = scene['image'] as JsonMap?;
    if (illustrate && image == null) {
      scene['image'] = {'planned': true, 'kind': 'scene', 'status': 'planned'};
    } else if (image == null ||
        (scene['player_action'] as String? ?? '').contains('[fail:picture]')) {
      return FakeResponse.json({'status': 'skipped'});
    }
    final current = scene['image'] as JsonMap;
    if (current['status'] == 'ready') return FakeResponse.json(_ready(b, current));

    final key = '${story.id}-$turn';
    final first = b.data.pictures.requestedAt.putIfAbsent(key, b.now);
    if (b.now().difference(first) < b.pace.picture) {
      return FakeResponse.json({'status': 'pending'});
    }
    current
      ..['status'] = 'ready'
      ..['url'] = _pictureFor(story, turn!);
    if (!r.usesOwnKey && b.data.pictures.charged.add(key)) {
      // A picture never takes the balance below zero (M7).
      if (b.data.account.balanceOf(r.userId!) >= 3.4) {
        b.data.account.charge(
          r.userId!,
          kind: 'image',
          cents: 3.4,
          now: b.now(),
          storyId: story.id,
          turn: turn,
        );
      }
    }
    return FakeResponse.json(_ready(b, current));
  }

  b.route('POST', '/v1/stories/:id/scenes/:turn/image', (r) => picture(r, illustrate: false));
  b.route('POST', '/v1/stories/:id/scenes/:turn/illustrate', (r) => picture(r, illustrate: true));
  b.route('GET', '/v1/stories/:id/images/:image', (r) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('image').split('-').last);
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    final image = scene?['image'] as JsonMap?;
    if (image == null) throw const FakeError.notFound('No such picture');
    return FakeResponse.json(image['status'] == 'ready' ? _ready(b, image) : {'status': 'pending'});
  });
}

JsonMap _ready(FakeBackend b, JsonMap image) => {
  'status': 'ready',
  'url': image['url'],
  'expires_at': b.now().add(const Duration(hours: 1)).toUtc().toIso8601String(),
};

String _pictureFor(FakeStory story, int turn) {
  final suits = FakeAssets.scenesFor(story.genre);
  return suits[turn % suits.length];
}
