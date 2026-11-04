import 'dart:typed_data';

import 'fake_backend.dart';

/// Fake dictation (V6), as docs/API.md "Dictation" describes it: `POST /v1/transcriptions` takes
/// the recording as the body and answers with [heard], charging a fraction of a cent (K2). It
/// always runs on our credits, even with the player's own key.
///
/// Speaking can't be scripted, so the fake hears the same line every time. A recording of only
/// the WAV header (no audio) is silence: an empty transcript, charged like any other.
void registerSpeechRoutes(FakeBackend b) {
  b.route('POST', '/v1/transcriptions', (r) {
    final type = r.headers['content-type']?.split(';').first.trim() ?? '';
    final audio = r.body;
    if (!type.startsWith('audio/')) {
      throw const FakeError.validation('Send the recording as audio, such as audio/wav.');
    }
    if (audio is! Uint8List || audio.isEmpty) {
      throw const FakeError.validation('The recording is empty.');
    }
    if (audio.length > maxAudioBytes) {
      throw const FakeError.validation('The recording is too long: a minute at most.');
    }
    final account = b.data.account;
    final balance = account.balanceOf(r.userId!);
    if (!account.unlimited.contains(r.userId) && balance < speechCents) {
      throw FakeError(402, 'out_of_credits', 'Not enough credits.', {
        'balance_cents': balance,
        'available_cents': balance,
      });
    }
    account.charge(
      r.userId!,
      kind: 'speech',
      cents: speechCents,
      now: b.now(),
      storyId: r.query('story_id'),
    );
    return FakeResponse.json({'text': audio.length > _wavHeader ? heard : ''});
  });
}

/// What the fake hears in every recording.
const heard = 'I look around slowly and listen.';

/// A dictation's cost: a fraction of a cent, as a short one costs on Gemini.
const speechCents = 0.2;

/// The API's limit on a recording.
const maxAudioBytes = 2 * 1024 * 1024;

const _wavHeader = 44;
