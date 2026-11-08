import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/fake/fake_narration.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/narration/narration_settings.dart';
import 'package:playable_anime/features/narration/narrator.dart';
import 'package:playable_anime/features/narration/phone_voice.dart';
import 'package:playable_anime/features/narration/spoken_text.dart';
import 'package:playable_anime/features/narration/studio_voice.dart';

import '../helpers.dart';

const _narration = 'The bell rings once.\n\nLin Feng *crosses* the courtyard.\n\nElder Mo waits.';
const _parts = ['The bell rings once.', 'Lin Feng crosses the courtyard.', 'Elder Mo waits.'];

StudioPart _ready(int part, {int parts = 3}) => StudioPart(
  status: StudioPartStatus.ready,
  part: part,
  parts: parts,
  text: _parts[part],
  url: 'https://audio.test/$part.mp3',
);

/// The studio voice's API, answered by the test: a part, or the error it throws.
class _Studio extends StudioVoiceApi {
  _Studio() : super(ApiClient(baseUrl: 'https://api.test', httpClient: MockClient(_unused)));

  static Future<http.Response> _unused(http.Request _) async => http.Response('', 500);

  final answers = <int, Object>{};
  final asked = <({int part, String voice})>[];

  @override
  Future<StudioPart> part(String storyId, int turn, int part, {required String voice}) async {
    asked.add((part: part, voice: voice));
    final answer = answers[part] ?? _ready(part);
    if (answer is StudioPart) return answer;
    throw answer;
  }
}

void main() {
  group('spoken text', () {
    test('is the narration as the server reads it', () {
      // The same case as the backend's `test_the_voice_reads_words_not_emphasis_marks`.
      expect(
        spokenText('You step *inside*.\n\n**Carmine**  looks\nup.\n\n\n  '),
        'You step inside.\n\nCarmine looks up.',
      );
    });

    test('goes to the phone in paragraphs, long ones between sentences', () {
      final long = List.filled(30, 'The rain keeps falling on the tiles.').join(' ');
      final chunks = phoneChunks('Short one.\n\n$long', limit: 200);

      expect(chunks.first, 'Short one.');
      expect(chunks.length, greaterThan(3));
      expect(chunks.every((c) => c.length <= 200), isTrue);
      expect(chunks.skip(1).join(' '), long);
    });
  });

  test("the phone's best voice for the language is picked", () {
    final voices = [
      {'name': 'en-us-x-low', 'locale': 'en-US', 'quality': 'normal', 'network_required': '0'},
      {'name': 'es-us-x-net', 'locale': 'es-US', 'quality': 'very high', 'network_required': '1'},
      {'name': 'es-es-x-local', 'locale': 'es-ES', 'quality': 'very high', 'network_required': '0'},
      {'name': 'es-es-x-low', 'locale': 'es-ES', 'quality': 'normal', 'network_required': '0'},
    ];

    expect(bestVoice(voices, language: 'es', locale: 'es-ES'), {
      'name': 'es-es-x-local',
      'locale': 'es-ES',
    });
    expect(bestVoice(voices, language: 'en', locale: 'en-US')!['name'], 'en-us-x-low');
    expect(bestVoice(voices, language: 'fr', locale: 'fr-FR'), isNull);
    expect(
      [
        for (final l in ['en', 'es', 'ca']) phoneLocale(l),
      ],
      ['en-US', 'es-ES', 'ca-ES'],
    );
  });

  group("the phone's voice reads a story only in a voice made for its language", () {
    test('Spanish only from Spain, however good a Latin American voice is', () {
      final voices = [
        {'name': 'es-us-x-sfb', 'locale': 'es-US', 'quality': 'very high'},
        {'name': 'Paulina', 'locale': 'es-MX', 'quality': 'premium'},
        {'name': 'Google español de Latinoamérica', 'locale': 'es-419'},
        {'name': 'Mónica', 'locale': 'es_ES', 'quality': 'default'},
      ];

      expect(bestVoice(voices, language: 'es', locale: 'es-ES'), {
        'name': 'Mónica',
        'locale': 'es_ES',
      });
      expect(bestVoice(voices.take(3).toList(), language: 'es', locale: 'es-ES'), isNull);
    });

    test('which voices read each language natively', () {
      expect(readsNatively('es-ES', 'es'), isTrue);
      expect(readsNatively('es_es', 'es'), isTrue);
      expect(readsNatively('es-Latn-ES', 'es'), isTrue);
      for (final latin in ['es-US', 'es-MX', 'es-AR', 'es-419', 'es']) {
        expect(readsNatively(latin, 'es'), isFalse, reason: latin);
      }
      for (final english in ['en-US', 'en-GB', 'en_AU', 'en']) {
        expect(readsNatively(english, 'en'), isTrue, reason: english);
      }
      for (final catalan in ['ca-ES', 'ca-ES-valencia', 'ca-AD', 'ca']) {
        expect(readsNatively(catalan, 'ca'), isTrue, reason: catalan);
      }
      // An English voice never reads Spanish, nor a Spanish one English.
      expect(readsNatively('en-US', 'es'), isFalse);
      expect(readsNatively('es-ES', 'en'), isFalse);
      expect(readsNatively('es-ES', 'ca'), isFalse);
    });

    test('English prefers an American voice, then any native English one', () {
      final voices = [
        {'name': 'Daniel', 'locale': 'en-GB', 'quality': 'enhanced'},
        {'name': 'Samantha', 'locale': 'en-US', 'quality': 'enhanced'},
        {'name': 'Mónica', 'locale': 'es-ES', 'quality': 'premium'},
      ];

      expect(bestVoice(voices, language: 'en', locale: 'en-US')!['name'], 'Samantha');
      expect(
        bestVoice(voices.take(1).toList(), language: 'en', locale: 'en-US')!['name'],
        'Daniel',
      );
    });

    test('a phone without one says so rather than read in another', () {
      final englishOnly = [
        {'name': 'Samantha', 'locale': 'en-US'},
      ];
      final latinOnly = [
        {'name': 'Paulina', 'locale': 'es-MX'},
      ];

      for (final voices in [englishOnly, latinOnly]) {
        expect(
          () => phoneVoiceFor(voices, language: 'es', languageSet: true, web: false),
          throwsA(isA<PhoneVoiceUnavailable>()),
        );
      }
      expect(phoneVoiceFor(englishOnly, language: 'en', languageSet: true, web: false), {
        'name': 'Samantha',
        'locale': 'en-US',
      });
    });

    test(
      "an engine that lists no voices reads in its own voice for the language, if it has one",
      () {
        expect(phoneVoiceFor(const [], language: 'es', languageSet: true, web: false), isNull);
        expect(
          () => phoneVoiceFor(const [], language: 'es', languageSet: false, web: false),
          throwsA(isA<PhoneVoiceUnavailable>()),
        );
        // A browser takes any language and reads it in its default voice, often an English one.
        expect(
          () => phoneVoiceFor(const [], language: 'es', languageSet: true, web: true),
          throwsA(isA<PhoneVoiceUnavailable>()),
        );
      },
    );
  });

  group('the studio voice API', () {
    test('asks again while another request reads the part', () async {
      final asked = <Uri>[];
      final answers = ['pending', 'pending', 'ready'];
      final api = ApiClient(
        baseUrl: 'https://api.test',
        httpClient: MockClient((r) async {
          asked.add(r.url);
          final status = answers[asked.length - 1];
          return http.Response(
            jsonEncode({
              'status': status,
              'part': 1,
              'parts': 3,
              'text': 'Lin Feng crosses the courtyard.',
              'url': status == 'ready' ? 'https://audio.test/1.mp3' : null,
              'duration_ms': status == 'ready' ? 2000 : null,
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }),
      );

      final part = await StudioVoiceApi(
        api,
        pendingDelay: Duration.zero,
      ).part('s1', 4, 1, voice: 'Charon');

      expect(asked, hasLength(3));
      expect(asked.first.path, '/v1/stories/s1/scenes/4/audio');
      expect(asked.first.queryParameters, {'part': '1', 'voice': 'Charon'});
      expect(part.status, StudioPartStatus.ready);
      expect(part.url, 'https://audio.test/1.mp3');
      expect(part.duration, const Duration(seconds: 2));
      expect((part.part, part.parts), (1, 3));
    });

    test('gives up on a part that stays pending', () async {
      final api = ApiClient(
        baseUrl: 'https://api.test',
        httpClient: MockClient(
          (_) async => http.Response(
            jsonEncode({'status': 'pending', 'part': 0, 'parts': 1, 'text': 'x'}),
            200,
            headers: {'content-type': 'application/json'},
          ),
        ),
      );

      await expectLater(
        StudioVoiceApi(
          api,
          pendingDelay: Duration.zero,
          pendingTries: 3,
        ).part('s1', 1, 0, voice: 'Sulafat'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.llmUnavailable)),
      );
    });
  });

  group('the narrator', () {
    late _Studio studio;
    late FakePlayback player;
    late FakePhoneVoice phone;
    late NarrationSettings settings;
    late Narrator narrator;
    late List<NarrationNotice> notices;

    setUp(() {
      studio = _Studio();
      player = FakePlayback();
      phone = FakePhoneVoice();
      settings = const NarrationSettings(studioVoice: StudioVoice.charon);
      narrator = Narrator(
        studio: () => studio,
        player: () => player,
        phone: () => phone,
        settings: () async => settings,
      );
      notices = [];
      narrator.notices.listen(notices.add);
    });

    tearDown(() => narrator.dispose());

    Future<void> read() =>
        narrator.read(storyId: 's1', turn: 3, narration: _narration, language: 'es');

    test('plays the parts in order, asking for the next while one plays', () async {
      final reading = read();
      expect(narrator.phaseOf('s1', 3), NarrationPhase.loading);
      await pumpEventQueue();

      expect(player.played, ['https://audio.test/0.mp3']);
      expect(studio.asked, [(part: 0, voice: 'Charon'), (part: 1, voice: 'Charon')]);
      expect(narrator.phaseOf('s1', 3), NarrationPhase.reading);
      expect(narrator.isReading('s1'), isTrue);
      expect(narrator.voice, NarrationVoice.studio);

      player.finish();
      await pumpEventQueue();
      expect(player.played.last, 'https://audio.test/1.mp3');
      expect(studio.asked, hasLength(3));
      player.finish();
      await pumpEventQueue();
      player.finish();
      await reading;

      expect(player.played, hasLength(3));
      expect(narrator.phaseOf('s1', 3), NarrationPhase.idle);
      expect(phone.spoken, isEmpty);
      expect(notices.single, isA<StudioCreditsSpent>());
    });

    test(
      'a part the voice model refuses is read in the phone voice, then the studio goes on',
      () async {
        studio.answers[1] = const StudioPart(
          status: StudioPartStatus.blocked,
          part: 1,
          parts: 3,
          text: 'Lin Feng crosses the courtyard.',
        );
        final reading = read();
        await pumpEventQueue();
        player.finish();
        await pumpEventQueue();

        expect(phone.spoken.single, (text: 'Lin Feng crosses the courtyard.', language: 'es'));
        expect(narrator.voice, NarrationVoice.device);
        phone.finish();
        await pumpEventQueue();
        expect(player.played.last, 'https://audio.test/2.mp3');
        expect(narrator.voice, NarrationVoice.studio);
        player.finish();
        await reading;
      },
    );

    test('out of credits, the phone reads the rest of the scene and says why', () async {
      studio.answers[1] = const ApiException(ApiErrorCode.outOfCredits);
      final reading = read();
      await pumpEventQueue();
      player.finish();
      await pumpEventQueue();

      expect(notices.whereType<ReadOnPhone>().single.reason, StudioFallback.outOfCredits);
      expect(phone.spoken.single.text, 'Lin Feng crosses the courtyard.\n\nElder Mo waits.');
      expect(studio.asked, hasLength(2)); // nothing more is asked of the studio voice
      phone.finish();
      await reading;
      expect(narrator.phaseOf('s1', 3), NarrationPhase.idle);
    });

    test('a quota or a failure falls back the same way', () async {
      studio.answers[0] = const ApiException(ApiErrorCode.quotaExceeded);
      var reading = read();
      await pumpEventQueue();
      expect(notices.whereType<ReadOnPhone>().last.reason, StudioFallback.quota);
      expect(phone.spoken.last.text, spokenText(_narration));
      phone.finish();
      await reading;

      studio.answers[0] = const ApiException(ApiErrorCode.network);
      reading = read();
      await pumpEventQueue();
      expect(notices.whereType<ReadOnPhone>().last.reason, StudioFallback.unavailable);
      phone.finish();
      await reading;
    });

    test("a part that won't play is read on the phone from that part on", () async {
      final reading = read();
      await pumpEventQueue();
      player
        ..failNext = Exception('Source error')
        ..finish();
      await pumpEventQueue();

      expect(notices.whereType<ReadOnPhone>().single.reason, StudioFallback.unavailable);
      expect(phone.spoken.single.text, 'Lin Feng crosses the courtyard.\n\nElder Mo waits.');
      phone.finish();
      await reading;
    });

    test('the next part is asked for near the end of a long one, and not after a stop', () async {
      narrator.dispose();
      narrator = Narrator(
        studio: () => studio,
        player: () => player,
        phone: () => phone,
        settings: () async => settings,
        prefetchLead: const Duration(milliseconds: 100),
      );
      for (final i in [0, 1]) {
        studio.answers[i] = StudioPart(
          status: StudioPartStatus.ready,
          part: i,
          parts: 3,
          text: _parts[i],
          url: 'https://audio.test/$i.mp3',
          duration: const Duration(milliseconds: 300),
        );
      }
      final reading = read();
      await pumpEventQueue();
      expect(studio.asked.map((a) => a.part), [0]);

      await Future<void>.delayed(const Duration(milliseconds: 250));
      expect(studio.asked.map((a) => a.part), [0, 1]);

      player.finish();
      await pumpEventQueue();
      expect(player.played.last, 'https://audio.test/1.mp3');
      // Stopped while part 1 plays, before part 2 is due: it is never asked for.
      await narrator.stop();
      await reading;
      await Future<void>.delayed(const Duration(milliseconds: 300));
      expect(studio.asked.map((a) => a.part), [0, 1]);
    });

    test('stop silences it at once and plays nothing more', () async {
      final reading = read();
      await pumpEventQueue();
      await narrator.stop();
      await reading;
      await pumpEventQueue();

      expect(player.played, hasLength(1));
      expect(player.stops, greaterThan(0));
      expect(narrator.phaseOf('s1', 3), NarrationPhase.idle);
      expect(narrator.isReading('s1'), isFalse);
    });

    test('another scene takes over from the one being read', () async {
      final first = read();
      await pumpEventQueue();
      final second = narrator.read(storyId: 's1', turn: 4, narration: 'Dawn.', language: 'en');
      await first;
      await pumpEventQueue();

      expect(narrator.phaseOf('s1', 3), NarrationPhase.idle);
      expect(narrator.phaseOf('s1', 4), NarrationPhase.reading);
      expect(player.played, hasLength(2));
      await narrator.stop();
      await second;
    });

    test("stopping another story's reading leaves this one alone", () async {
      final reading = read();
      await pumpEventQueue();
      await narrator.stopStory('s2');
      expect(narrator.isReading('s1'), isTrue);
      await narrator.stopStory('s1');
      await reading;
      expect(narrator.isReading('s1'), isFalse);
    });

    test("the device's voice reads the whole scene, with no call to the API", () async {
      settings = const NarrationSettings(voice: NarrationVoice.device);
      final reading = read();
      await pumpEventQueue();

      expect(phone.spoken.single, (text: spokenText(_narration), language: 'es'));
      expect(narrator.voice, NarrationVoice.device);
      expect(studio.asked, isEmpty);
      phone.finish();
      await reading;
    });

    test('a device with no voice says so', () async {
      settings = const NarrationSettings(voice: NarrationVoice.device);
      phone.available = false;
      await read();
      await pumpEventQueue();

      expect(notices.single, isA<NoPhoneVoice>().having((n) => n.language, 'language', 'es'));
      expect(narrator.isReading('s1'), isFalse);
    });
  });

  group('the fake API', () {
    Future<({ApiClient api, FakeBackend backend})> signedIn() async {
      final (:api, :backend, :tokens) = fakeApi();
      final session =
          await api.post('/v1/auth/login', {
                'email': FakeAuthState.demoEmail,
                'password': FakeAuthState.demoPassword,
              }, authenticated: false)
              as JsonMap;
      tokens.accessToken = session['access_token'] as String;
      return (api: api, backend: backend);
    }

    Future<JsonMap> audio(
      ApiClient api, {
      int turn = 1,
      int part = 0,
      String voice = 'Sulafat',
    }) async =>
        await api.post(
              '/v1/stories/story_ninth_peak/scenes/$turn/audio',
              null,
              query: {'part': '$part', 'voice': voice},
            )
            as JsonMap;

    test('reads a part once per voice and charges it once', () async {
      final (:api, :backend) = await signedIn();
      final ledger = backend.data.account.ledgerOf(FakeAuthState.demoUserId);
      final before = ledger.length;

      final first = await audio(api);
      await audio(api);
      await audio(api, voice: 'Charon');

      expect(first['status'], 'ready');
      expect(first['url'], narrationAsset);
      expect(first['parts'], 3);
      expect(first['text'], startsWith('The bell of the Azure Cloud Sect'));
      final charges = ledger.skip(before).toList();
      expect(charges.map((e) => e['kind']), ['voice', 'voice']);
      expect(charges.first['amount_cents'], -voiceCents);
    });

    test('refuses a broke player, an unknown voice and a part past the end', () async {
      final (:api, :backend) = await signedIn();
      final account = backend.data.account;
      final user = FakeAuthState.demoUserId;
      account.charge(user, kind: 'turn', cents: account.balanceOf(user), now: DateTime.now());

      Matcher code(ApiErrorCode code) =>
          throwsA(isA<ApiException>().having((e) => e.code, 'code', code));
      await expectLater(audio(api), code(ApiErrorCode.outOfCredits));
      await expectLater(audio(api, voice: 'Robot'), code(ApiErrorCode.validationError));
      await expectLater(audio(api, part: 9), code(ApiErrorCode.validationError));
    });
  });
}
