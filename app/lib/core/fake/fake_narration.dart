import 'fake_backend.dart';

/// Fake reading aloud (V8 to V10), as docs/API.md "Reading aloud" describes it:
/// `POST /v1/stories/{id}/scenes/{turn}/audio?part=&voice=` answers one part of the scene read in
/// the studio voice, with a bundled chime for the audio. The fake reads a scene a paragraph at a
/// time. Each part is charged once per voice (V10), always on our credits, and a part asked for
/// again is free. A scene whose action contains `[fail:voice]` answers `blocked`, as a part the
/// voice model refused would, for the phone's voice to read.
void registerNarrationRoutes(FakeBackend b) {
  final read = <String>{};
  b.route('POST', '/v1/stories/:id/scenes/:turn/audio', (r) {
    final story = b.data.stories.get(r.param('id'), r.userId!);
    final turn = int.tryParse(r.param('turn'));
    final scene = story.scenes.where((s) => s['turn'] == turn).firstOrNull;
    if (scene == null) throw const FakeError.notFound('Scene not found.');
    final voice = r.query('voice') ?? 'Sulafat';
    if (!studioVoices.contains(voice)) {
      throw const FakeError.validation('Pick one of the studio voices.');
    }
    final parts = _parts(scene['narration'] as String? ?? '');
    final part = int.tryParse(r.query('part') ?? '0') ?? -1;
    if (part < 0 || part >= parts.length) {
      throw const FakeError.validation('The scene has no such part.');
    }
    final answer = {'part': part, 'parts': parts.length, 'text': parts[part]};
    if ((scene['player_action'] as String? ?? '').contains('[fail:voice]')) {
      return FakeResponse.json({...answer, 'status': 'blocked'});
    }
    final key = '${story.id}-$turn-$voice-$part';
    if (!read.contains(key)) {
      final account = b.data.account;
      final balance = account.balanceOf(r.userId!);
      if (!account.unlimited.contains(r.userId) && balance < voiceCents) {
        throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
          'balance_cents': balance,
          'available_cents': balance,
        });
      }
      account.charge(
        r.userId!,
        kind: 'voice',
        cents: voiceCents,
        now: b.now(),
        storyId: story.id,
        turn: turn,
      );
      read.add(key);
    }
    return FakeResponse.json({
      ...answer,
      'status': 'ready',
      'url': narrationAsset,
      'expires_at': b.now().add(const Duration(hours: 1)).toUtc().toIso8601String(),
      'duration_ms': 1500,
    });
  });
}

/// The studio voices the API knows (`speech.voices.VOICES`).
const studioVoices = {'Sulafat', 'Gacrux', 'Charon', 'Algieba'};

/// What a part costs: about what a paragraph costs on Gemini's TTS.
const voiceCents = 0.5;

/// The chime every fake part plays.
const narrationAsset = 'asset:///assets/fake/narration.mp3';

List<String> _parts(String narration) => [
  for (final paragraph in narration.replaceAll('*', '').split(RegExp(r'\n\s*\n')))
    if (paragraph.trim().isNotEmpty) paragraph.replaceAll(RegExp(r'\s+'), ' ').trim(),
];
