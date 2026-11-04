import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/core/api/api_client.dart';
import 'package:playable_anime/core/api/api_error.dart';
import 'package:playable_anime/core/fake/fake_auth.dart';
import 'package:playable_anime/core/fake/fake_backend.dart';
import 'package:playable_anime/core/fake/fake_speech.dart';
import 'package:playable_anime/core/json.dart';
import 'package:playable_anime/features/voice/cloud_speech_engine.dart';
import 'package:playable_anime/features/voice/pcm.dart';
import 'package:playable_anime/features/voice/speech_engine.dart';

import '../helpers.dart';

/// 100 ms of 16 kHz mono PCM at [amplitude] (0 is silence, 32767 full scale).
Uint8List tone(int amplitude, {int ms = 100, PcmFormat format = PcmFormat.speech}) {
  final frames = format.sampleRate * ms ~/ 1000;
  final data = ByteData(frames * format.channels * 2);
  for (var i = 0; i < frames * format.channels; i++) {
    // A square wave: loud enough to measure, simple to check.
    data.setInt16(i * 2, i.isEven ? amplitude : -amplitude, Endian.little);
  }
  return data.buffer.asUint8List();
}

final speech = tone(8000); // about -12 dBFS
final quiet = tone(20); // about -64 dBFS, a quiet room

class FakeRecorder implements SpeechRecorder {
  bool supported = true;
  bool allowed = true;
  PcmFormat? records;
  Completer<void>? starting;
  StreamController<Uint8List>? _mic;
  int starts = 0;
  int stops = 0;
  int cancels = 0;
  final permissionRequests = <bool>[];

  bool get recording => _mic != null && !_mic!.isClosed;

  void say(Uint8List chunk) => _mic!.add(chunk);

  @override
  Future<bool> isSupported() async => supported;

  @override
  Future<bool> hasPermission({bool request = true}) async {
    permissionRequests.add(request);
    return allowed;
  }

  @override
  Future<Stream<Uint8List>> start(PcmFormat wanted, void Function(PcmFormat) onFormat) async {
    starts++;
    await starting?.future;
    if (records case final actual?) onFormat(actual);
    _mic = StreamController<Uint8List>();
    return _mic!.stream;
  }

  // Not awaited: a stream nobody listened to never finishes closing.
  @override
  Future<void> stop() async {
    stops++;
    unawaited(_mic?.close());
  }

  @override
  Future<void> cancel() async {
    cancels++;
    unawaited(_mic?.close());
  }
}

class FakeTranscriber implements Transcriber {
  FakeTranscriber([this.words = 'I bow to Senior Brother Zhao.']);

  String words;
  Object? failure;
  Completer<void>? answering;
  final calls = <({Uint8List wav, String? language, SpeechContext context})>[];

  @override
  Future<String> transcribe(
    Uint8List wav, {
    String? language,
    SpeechContext context = const SpeechContext(),
  }) async {
    calls.add((wav: wav, language: language, context: context));
    await answering?.future;
    if (failure case final failure?) throw failure;
    return words;
  }
}

/// What one dictation told the box.
class Box {
  final results = <(String, bool)>[];
  final failures = <String>[];
  int stopped = 0;
  int transcribing = 0;
  final levels = <double>[];

  Future<void> listen(
    CloudSpeechEngine engine, {
    String? language = 'en-US',
    SpeechContext context = const SpeechContext(),
  }) => engine.listen(
    onResult: (words, isFinal) => results.add((words, isFinal)),
    onStopped: () => stopped++,
    onError: (failure) => failures.add(failure.code),
    onLevel: levels.add,
    onTranscribing: () => transcribing++,
    localeId: language,
    context: context,
  );
}

void main() {
  late FakeRecorder recorder;
  late FakeTranscriber transcriber;
  late CloudSpeechEngine engine;

  /// A moment of the room, then a word.
  Future<void> talk() async {
    recorder
      ..say(quiet)
      ..say(speech);
    await pumpEventQueue();
  }

  setUp(() {
    recorder = FakeRecorder();
    transcriber = FakeTranscriber();
    engine = CloudSpeechEngine(recorder: recorder, transcriber: transcriber);
  });

  test('is online, and asks for the mic only when initialized', () async {
    expect(engine.onPhone, isFalse);
    expect(await engine.isSupported(), isTrue);
    expect(await engine.hasPermission(), isTrue);
    expect(await engine.initialize(), isTrue);
    expect(recorder.permissionRequests, [false, true]);
  });

  test('records until the tap, then writes it down with the language and the story', () async {
    final box = Box();
    await box.listen(engine, context: const SpeechContext(storyId: 'story_1'));
    await talk();
    expect(box.levels, [0, closeTo(0.96, 0.01)]);

    await engine.stop();

    final call = transcriber.calls.single;
    expect(call.language, 'en-US');
    expect(call.context, const SpeechContext(storyId: 'story_1'));
    expect(call.wav.length, 44 + speech.length * 2);
    expect(String.fromCharCodes(call.wav.sublist(0, 4)), 'RIFF');
    expect(box.transcribing, 1);
    expect(box.results, [('I bow to Senior Brother Zhao.', true)]);
    expect(box.stopped, 1);
    expect(box.failures, isEmpty);
    expect(recorder.stops, 1);
  });

  // Time is measured in the audio itself, so these need no clock.
  test('a pause after speaking ends the dictation by itself', () async {
    final box = Box();
    await box.listen(engine);
    await talk();
    for (var i = 0; i < 24; i++) {
      recorder.say(quiet);
    }
    await pumpEventQueue();
    expect(recorder.stops, 0, reason: '2.4 s of quiet is still a pause in the sentence');

    recorder.say(quiet);
    await pumpEventQueue();

    expect(recorder.stops, 1);
    expect(box.transcribing, 1);
    expect(box.results.single.$2, isTrue);
  });

  test('saying nothing sends nothing and is silence, not a failure', () async {
    final box = Box();
    await box.listen(engine);
    for (var i = 0; i < 79; i++) {
      recorder.say(quiet);
    }
    await pumpEventQueue();
    expect(recorder.stops, 0);

    recorder.say(quiet);
    await pumpEventQueue();

    expect(recorder.stops, 1);
    expect(transcriber.calls, isEmpty);
    expect(box.failures, ['error_speech_timeout']);
    expect(const SpeechFailure('error_speech_timeout').isSilence, isTrue);
  });

  test('a word said at the tap counts once the room is heard', () async {
    final box = Box();
    await box.listen(engine);
    recorder.say(speech);
    for (var i = 0; i < 5; i++) {
      recorder.say(quiet);
    }
    await pumpEventQueue();

    await engine.stop();

    expect(box.results, hasLength(1));
  });

  test('a minute is the longest dictation', () async {
    final box = Box();
    await box.listen(engine);
    for (var i = 0; i < 600; i++) {
      recorder.say(i.isEven ? quiet : speech); // words and the gaps between them
    }
    await pumpEventQueue();

    expect(recorder.stops, 1);
    expect(transcriber.calls.single.wav.length, 44 + 600 * speech.length);
    expect(transcriber.calls.single.wav.length, lessThan(maxAudioBytes));
    expect(box.results, hasLength(1));
  });

  test('a browser that records 48 kHz stereo still sends 16 kHz mono', () async {
    recorder.records = const PcmFormat(sampleRate: 48000, channels: 2);
    final format = recorder.records!;
    final box = Box();
    await box.listen(engine);
    recorder
      ..say(tone(20, format: format))
      ..say(tone(8000, format: format));
    await pumpEventQueue();

    await engine.stop();

    expect(transcriber.calls.single.wav.length, 44 + 3200 * 2); // 200 ms at 16 kHz
    expect(box.results, hasLength(1));
  });

  test('failures map to what the player can do about them', () async {
    final cases = <Object, String>{
      const ApiException(ApiErrorCode.outOfCredits): SpeechFailure.outOfCredits,
      const ApiException(ApiErrorCode.rateLimited): SpeechFailure.limited,
      const ApiException(ApiErrorCode.quotaExceeded): SpeechFailure.limited,
      const ApiException(ApiErrorCode.network): SpeechFailure.offline,
      const ApiException(ApiErrorCode.timeout): SpeechFailure.offline,
      const ApiException(ApiErrorCode.llmUnavailable): SpeechFailure.offline,
      const ApiException(ApiErrorCode.unreadableAction): 'error_no_match',
      StateError('boom'): SpeechFailure.offline,
    };
    for (final MapEntry(key: failure, value: code) in cases.entries) {
      transcriber.failure = failure;
      final box = Box();
      await box.listen(engine);
      await talk();
      await engine.stop();
      expect(box.failures, [code], reason: '$failure');
      expect(box.results, isEmpty);
    }
  });

  test('an empty transcript is a no-match', () async {
    transcriber.words = '  ';
    final box = Box();
    await box.listen(engine);
    await talk();
    await engine.stop();
    expect(box.failures, ['error_no_match']);
  });

  test('cancelling drops the recording with no callbacks', () async {
    final box = Box();
    await box.listen(engine);
    await talk();

    await engine.cancel();
    await pumpEventQueue();

    expect(recorder.cancels, 1);
    expect(transcriber.calls, isEmpty);
    expect(box.results, isEmpty);
    expect(box.failures, isEmpty);
    expect(box.stopped, 0);
  });

  test('another box taking the mic stops the first, which keeps nothing', () async {
    final first = Box();
    final second = Box();
    await first.listen(engine);
    await talk();

    await second.listen(engine);
    await talk();
    await engine.stop();

    expect(first.stopped, 1);
    expect(first.results, isEmpty);
    expect(second.results, hasLength(1));
    expect(transcriber.calls.single.wav.length, 44 + speech.length * 2);
  });

  test('a stop while the mic is starting records nothing', () async {
    recorder.starting = Completer();
    final box = Box();
    final listening = box.listen(engine);
    await pumpEventQueue();

    final stopping = engine.stop();
    recorder.starting!.complete();
    await listening;
    await stopping;

    expect(recorder.cancels, 1);
    expect(recorder.recording, isFalse);
    expect(transcriber.calls, isEmpty);
    expect(box.failures, ['error_speech_timeout']);
  });

  test('a mic that fails to start is an audio error', () async {
    final failing = CloudSpeechEngine(recorder: _BrokenRecorder(), transcriber: transcriber);
    final box = Box();
    await box.listen(failing);
    expect(box.failures, ['error_audio']);
  });

  test('the platform ending the recording, such as a call, keeps what was said', () async {
    final box = Box();
    await box.listen(engine);
    await talk();
    await recorder.stop();
    await pumpEventQueue();

    expect(transcriber.calls, hasLength(1));
    expect(box.results, hasLength(1));
  });

  group('ApiTranscriber', () {
    Future<({ApiClient api, FakeBackend backend})> signedIn() async {
      final (:api, :backend, :tokens) = fakeApi();
      final session =
          await api.post('/v1/auth/login', {
                'email': FakeAuthState.demoEmail,
                'password': FakeAuthState.demoPassword,
              }, authenticated: false)
              as JsonMap;
      tokens
        ..accessToken = session['access_token'] as String
        ..refreshToken = session['refresh_token'] as String;
      return (api: api, backend: backend);
    }

    test('sends the recording and is charged a fraction of a cent', () async {
      final (:api, :backend) = await signedIn();
      final wav = speechWav(toSpeechPcm(speech, PcmFormat.speech));

      final words = await ApiTranscriber(api).transcribe(
        wav,
        language: 'en-US',
        context: const SpeechContext(storyId: 'story_1'),
      );

      expect(words, heard);
      final request = backend.requests.last;
      expect(request.uri.path, '/v1/transcriptions');
      expect(request.uri.queryParameters, {'language': 'en-US', 'story_id': 'story_1'});
      expect(request.headers['content-type'], 'audio/wav');
      expect(request.headers.containsKey('x-llm-api-key'), isFalse);
      expect(request.body, wav);
      final entry = backend.data.account.ledgerOf(request.userId!).last;
      expect((entry['kind'], entry['amount_cents']), ('speech', -speechCents));
    });

    test('needs a little credit, and an audio body', () async {
      final (:api, :backend) = await signedIn();
      final wav = speechWav(toSpeechPcm(speech, PcmFormat.speech));
      final user = FakeAuthState.demoUserId;
      final account = backend.data.account;
      account.charge(user, kind: 'turn', cents: account.balanceOf(user), now: DateTime.now());

      await expectLater(
        ApiTranscriber(api).transcribe(wav),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.outOfCredits)),
      );
      await expectLater(
        api.postBytes('/v1/transcriptions', wav, contentType: 'text/plain'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', ApiErrorCode.validationError)),
      );
    });

    test('silence comes back empty', () async {
      final (:api, backend: _) = await signedIn();
      final words = await ApiTranscriber(api).transcribe(speechWav(Int16List(0)));
      expect(words, isEmpty);
    });
  });
}

class _BrokenRecorder extends FakeRecorder {
  @override
  Future<Stream<Uint8List>> start(PcmFormat wanted, void Function(PcmFormat) onFormat) =>
      Future.error(StateError('no mic'));
}
