import '../json.dart';
import 'fake_backend.dart';
import 'fake_data.dart';
import 'fake_stories.dart';

/// Fake pictures (docs/API.md, "Pictures", M1 to M8). Owned by the play screen work (WS14).
///
/// The first request for a planned picture answers `pending`; once [FakePace.picture] has passed,
/// requests answer `ready` with a bundled image. Each picture is charged once (M3). A scene whose
/// action contains `[fail:picture]` answers `skipped`, as a blocked picture would, until the
/// player asks to illustrate it again. Illustrate on credits that can't cover a picture answers
/// `402 out_of_credits` and leaves the scene as it was (M2); a planned picture is never refused.
class FakePictureState {
  final requestedAt = <String, DateTime>{};
  final charged = <String>{};

  /// Scenes played with `[fail:picture]`, as `<story id>-<turn>`.
  final failing = <String>{};

  /// How long a picture's signed URL lasts.
  Duration ttl = const Duration(hours: 1);
}

void registerPictureRoutes(FakeBackend b) {
  FakeResponse picture(FakeRequest r, {required bool illustrate}) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('turn'));
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    if (scene == null) throw const FakeError.notFound('No such scene');
    final key = '${story.id}-$turn';
    final image = scene['image'] as JsonMap?;
    final pictures = b.data.pictures;
    final unpaid = !r.usesOwnKey && !pictures.charged.contains(key);
    final balance = b.data.account.balanceOf(r.userId!);
    // A picture being drawn answers pending, as the server does, without asking the meter.
    final drawing = image?['status'] == 'planned' && pictures.requestedAt.containsKey(key);
    if (illustrate &&
        image?['status'] != 'ready' &&
        !drawing &&
        unpaid &&
        balance < _pictureCents) {
      throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
        'balance_cents': balance,
        'available_cents': balance,
      });
    }
    if (illustrate && (image == null || image['status'] == 'skipped')) {
      // Illustrating plans a scene picture, or plans a skipped one again.
      scene['image'] = {'planned': true, 'kind': image?['kind'] ?? 'scene', 'status': 'planned'};
      pictures.failing.remove(key);
      pictures.requestedAt.remove(key);
    } else if (image == null) {
      return FakeResponse.json({'status': 'skipped'});
    }
    final current = scene['image'] as JsonMap;
    if (pictures.failing.contains(key)) {
      current['status'] = 'skipped';
      return FakeResponse.json({'status': 'skipped'});
    }
    if (current['status'] == 'ready') return FakeResponse.json(_ready(b, current));

    final first = pictures.requestedAt.putIfAbsent(key, b.now);
    if (b.now().difference(first) < b.pace.picture) {
      return FakeResponse.json({'status': 'pending'});
    }
    current
      ..['status'] = 'ready'
      ..['image_id'] = 'img_${story.id}_$turn'
      ..['url'] = current['kind'] == 'portrait'
          ? FakeAssets.portrait(3)
          : _pictureFor(story, turn!);
    if (!r.usesOwnKey && pictures.charged.add(key)) {
      // A picture never takes the balance below zero (M7).
      if (b.data.account.balanceOf(r.userId!) >= _pictureCents) {
        b.data.account.charge(
          r.userId!,
          kind: 'image',
          cents: _pictureCents,
          now: b.now(),
          storyId: story.id,
          turn: turn!,
        );
      }
    }
    return FakeResponse.json(_ready(b, current));
  }

  b.route('POST', '/v1/stories/:id/scenes/:turn/image', (r) => picture(r, illustrate: false));
  b.route('POST', '/v1/stories/:id/scenes/:turn/illustrate', (r) => picture(r, illustrate: true));
  // A fresh URL for a picture whose URL expired. It never draws.
  b.route('GET', '/v1/stories/:id/images/:image', (r) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('image').split('_').last);
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    final image = scene?['image'] as JsonMap?;
    if (image == null) throw const FakeError.notFound('No such picture');
    return FakeResponse.json(image['status'] == 'ready' ? _ready(b, image) : {'status': 'pending'});
  });
}

/// What a picture costs on credits.
const _pictureCents = 3.4;

JsonMap _ready(FakeBackend b, JsonMap image) => {
  'status': 'ready',
  'image_id': image['image_id'],
  'kind': image['kind'] ?? 'scene',
  'url': image['url'],
  'expires_at': b.now().add(b.data.pictures.ttl).toUtc().toIso8601String(),
};

String _pictureFor(FakeStory story, int turn) {
  final suits = FakeAssets.scenesFor(story.genre);
  return suits[turn % suits.length];
}
