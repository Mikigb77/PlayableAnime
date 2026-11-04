import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:playable_anime/features/voice/pcm.dart';

Uint8List pcm(List<int> samples) {
  final data = ByteData(samples.length * 2);
  for (var i = 0; i < samples.length; i++) {
    data.setInt16(i * 2, samples[i], Endian.little);
  }
  return data.buffer.asUint8List();
}

void main() {
  test('a minute of speech fits the API limit', () {
    expect(PcmFormat.speech.bytesPerSecond * 60, 1920000);
    expect(const PcmFormat(sampleRate: 48000, channels: 2).bytesPerSecond, 192000);
  });

  test('the level is in dBFS, with silence at the floor', () {
    expect(pcmLevelDb(Uint8List(0)), -100);
    expect(pcmLevelDb(pcm([0, 0, 0, 0])), -100);
    expect(pcmLevelDb(pcm([32767, -32768])), closeTo(0, 0.01));
    expect(pcmLevelDb(pcm([16384, -16384])), closeTo(-6.02, 0.01));
  });

  test('16 kHz mono passes through unchanged', () {
    expect(toSpeechPcm(pcm([1, -2, 3]), PcmFormat.speech), [1, -2, 3]);
  });

  test('stereo is averaged into mono', () {
    final stereo = pcm([100, 300, -100, -300]);
    expect(toSpeechPcm(stereo, const PcmFormat(sampleRate: 16000, channels: 2)), [200, -200]);
  });

  test('48 kHz comes down to 16 kHz by averaging each three samples', () {
    final high = pcm([3, 6, 9, 30, 60, 90, 1]);
    expect(toSpeechPcm(high, const PcmFormat(sampleRate: 48000, channels: 1)), [6, 60]);
  });

  test('44.1 kHz comes down to the right length', () {
    final second = pcm(List.filled(44100, 1000));
    final out = toSpeechPcm(second, const PcmFormat(sampleRate: 44100, channels: 1));
    expect(out.length, 16000);
    expect(out, everyElement(1000));
  });

  test('8 kHz goes up to 16 kHz by interpolation', () {
    final low = pcm([0, 100, 200]);
    expect(toSpeechPcm(low, const PcmFormat(sampleRate: 8000, channels: 1)), [
      0,
      50,
      100,
      150,
      200,
      200,
    ]);
  });

  test('a WAV is a 44-byte header and the samples', () {
    final wav = speechWav(Int16List.fromList([1, -1]));
    final data = ByteData.sublistView(wav);
    expect(wav.length, 48);
    expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
    expect(data.getUint32(4, Endian.little), 40);
    expect(String.fromCharCodes(wav.sublist(8, 16)), 'WAVEfmt ');
    expect(data.getUint16(20, Endian.little), 1); // PCM
    expect(data.getUint16(22, Endian.little), 1); // mono
    expect(data.getUint32(24, Endian.little), 16000);
    expect(data.getUint16(34, Endian.little), 16);
    expect(String.fromCharCodes(wav.sublist(36, 40)), 'data');
    expect(data.getUint32(40, Endian.little), 4);
    expect(data.getInt16(44, Endian.little), 1);
    expect(data.getInt16(46, Endian.little), -1);
  });
}
