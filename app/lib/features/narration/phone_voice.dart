import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'spoken_text.dart';

/// The phone's own text to speech (V9): free, and nothing leaves the phone, but flatter than the
/// studio voice. Tests replace it with a fake.
abstract class PhoneVoice {
  /// Reads [text] aloud in [language] (a code such as `en`, `es` or `ca`), and completes when it has been read or
  /// [stop] cut it short. Throws [PhoneVoiceUnavailable] when the phone has no voice to read with.
  Future<void> speak(String text, {required String language});

  Future<void> stop();

  void dispose() {}
}

/// The phone can't read aloud: no text to speech engine, or none for the language.
class PhoneVoiceUnavailable implements Exception {
  const PhoneVoiceUnavailable([this.reason]);

  final Object? reason;

  @override
  String toString() => 'PhoneVoiceUnavailable($reason)';
}

/// [PhoneVoice] on `flutter_tts`: Android's and iOS's engines, and the browser's speech
/// synthesis on the web. It picks the best voice the phone has for the language.
class FlutterPhoneVoice implements PhoneVoice {
  FlutterTts? _tts;
  Completer<void>? _utterance;
  String? _language;
  var _stopped = false;

  FlutterTts _engine() {
    final existing = _tts;
    if (existing != null) return existing;
    final tts = FlutterTts();
    void done() {
      final utterance = _utterance;
      if (utterance != null && !utterance.isCompleted) utterance.complete();
    }

    tts
      ..setCompletionHandler(done)
      ..setCancelHandler(done)
      ..setErrorHandler((message) {
        final utterance = _utterance;
        if (utterance != null && !utterance.isCompleted) {
          utterance.completeError(PhoneVoiceUnavailable(message));
        }
      });
    return _tts = tts;
  }

  @override
  Future<void> speak(String text, {required String language}) async {
    _stopped = false;
    final tts = _engine();
    try {
      if (_language != language) {
        await _setUp(tts, language);
        _language = language;
      }
    } on Object catch (e) {
      throw PhoneVoiceUnavailable(e);
    }
    for (final chunk in phoneChunks(text)) {
      if (_stopped) return;
      final utterance = _utterance = Completer<void>();
      final Object? started;
      try {
        started = await tts.speak(chunk);
      } on Object catch (e) {
        throw PhoneVoiceUnavailable(e);
      }
      // Android answers 1 when the engine took the text.
      if (started != 1 && started != null && started != true) {
        throw PhoneVoiceUnavailable(started);
      }
      await utterance.future;
    }
  }

  Future<void> _setUp(FlutterTts tts, String language) async {
    final locale = phoneLocale(language);
    await tts.awaitSpeakCompletion(false);
    // Android answers 0 when it has no voice for the locale itself, say only Mexican Spanish.
    final set = await tts.setLanguage(locale);
    // The engines' normal pace: Android and iOS count 0.5 as normal, browsers 1.0.
    await tts.setSpeechRate(kIsWeb ? 1.0 : 0.5);
    Map<String, String>? best;
    try {
      final voices = await tts.getVoices;
      if (voices is List) best = bestVoice(voices, language: language, locale: locale);
    } on Object {
      // The engine's default voice for the language still reads.
    }
    if (best != null) {
      await tts.setVoice(best);
    } else if (set == 0) {
      throw PhoneVoiceUnavailable('no voice for $language');
    }
  }

  @override
  Future<void> stop() async {
    _stopped = true;
    final utterance = _utterance;
    if (utterance != null && !utterance.isCompleted) utterance.complete();
    try {
      await _tts?.stop();
    } on Object {
      // Nothing is reading.
    }
  }

  @override
  void dispose() => unawaited(stop());
}

/// The locale the phone's voice reads [language] in: a story's language code, such as `es`, or
/// `ca` for Catalan.
String phoneLocale(String language) => switch (language) {
  'en' => 'en-US',
  'es' => 'es-ES',
  'ca' => 'ca-ES',
  _ => language,
};

/// The most natural of the phone's voices for [language], as `setVoice` takes it: a voice in the
/// language, the highest quality first, then one for [locale] itself, then one that works
/// offline. Null when the phone lists none.
@visibleForTesting
Map<String, String>? bestVoice(
  List<Object?> voices, {
  required String language,
  required String locale,
}) {
  int quality(Object? value) => switch ('$value'.toLowerCase()) {
    'very high' || 'premium' => 4,
    'high' || 'enhanced' => 3,
    'normal' => 2,
    _ => 1,
  };

  Map<String, String>? best;
  var bestScore = -1.0;
  for (final voice in voices) {
    if (voice is! Map) continue;
    final name = voice['name'];
    final tag = '${voice['locale'] ?? ''}'.replaceAll('_', '-');
    if (name is! String || tag.split('-').first.toLowerCase() != language) continue;
    final double score =
        quality(voice['quality']) +
        (tag.toLowerCase() == locale.toLowerCase() ? 0.5 : 0) +
        (voice['network_required'] == '1' ? 0 : 0.25);
    if (score > bestScore) {
      bestScore = score;
      best = {'name': name, 'locale': '${voice['locale']}'};
    }
  }
  return best;
}
