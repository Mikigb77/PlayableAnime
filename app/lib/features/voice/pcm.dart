import 'dart:math' as math;
import 'dart:typed_data';

/// The shape of raw 16-bit little-endian PCM from the microphone.
class PcmFormat {
  const PcmFormat({required this.sampleRate, required this.channels});

  /// What online dictation records and sends (V6): what speech models are tuned for, and a
  /// minute of it is 1.92 MB, inside the API's limit.
  static const speech = PcmFormat(sampleRate: 16000, channels: 1);

  final int sampleRate;
  final int channels;

  int get bytesPerSecond => sampleRate * channels * 2;

  @override
  bool operator ==(Object other) =>
      other is PcmFormat && other.sampleRate == sampleRate && other.channels == channels;

  @override
  int get hashCode => Object.hash(sampleRate, channels);

  @override
  String toString() => 'PcmFormat($sampleRate Hz, $channels ch)';
}

/// The loudness of a chunk of PCM in dBFS: 0 is full scale, silence is [floorDb].
double pcmLevelDb(Uint8List chunk, {double floorDb = -100}) {
  final samples = chunk.length ~/ 2;
  if (samples == 0) return floorDb;
  final data = ByteData.sublistView(chunk);
  var sum = 0.0;
  for (var i = 0; i < samples; i++) {
    final value = data.getInt16(i * 2, Endian.little);
    sum += value * value;
  }
  final rms = math.sqrt(sum / samples);
  if (rms < 1) return floorDb;
  return math.max(floorDb, 20 * math.log(rms / 32768) / math.ln10);
}

/// The PCM as [PcmFormat.speech]: channels averaged into one and the rate brought to 16 kHz, by
/// averaging when it comes down (which also keeps out the highs that would alias) and by linear
/// interpolation when it goes up. A browser that can't record at 16 kHz sends 44.1 or 48 kHz.
Int16List toSpeechPcm(Uint8List bytes, PcmFormat format) {
  final data = ByteData.sublistView(bytes);
  final channels = math.max(1, format.channels);
  final frames = bytes.length ~/ (2 * channels);
  final mono = Float64List(frames);
  for (var f = 0; f < frames; f++) {
    var sum = 0;
    for (var c = 0; c < channels; c++) {
      sum += data.getInt16((f * channels + c) * 2, Endian.little);
    }
    mono[f] = sum / channels;
  }
  final target = PcmFormat.speech.sampleRate;
  if (format.sampleRate == target || frames == 0) return _clamped(mono);
  final ratio = format.sampleRate / target;
  final length = (frames / ratio).floor();
  final out = Float64List(length);
  for (var i = 0; i < length; i++) {
    final start = i * ratio;
    if (ratio > 1) {
      final from = start.floor();
      final to = math.min(frames, math.max(from + 1, (start + ratio).floor()));
      var sum = 0.0;
      for (var j = from; j < to; j++) {
        sum += mono[j];
      }
      out[i] = sum / (to - from);
    } else {
      final j = start.floor();
      final next = math.min(frames - 1, j + 1);
      final t = start - j;
      out[i] = mono[j] * (1 - t) + mono[next] * t;
    }
  }
  return _clamped(out);
}

Int16List _clamped(Float64List samples) {
  final out = Int16List(samples.length);
  for (var i = 0; i < samples.length; i++) {
    out[i] = samples[i].round().clamp(-32768, 32767);
  }
  return out;
}

/// A WAV file of 16 kHz mono 16-bit PCM, as the API takes it.
Uint8List speechWav(Int16List samples) {
  const rate = 16000;
  final dataBytes = samples.length * 2;
  final out = ByteData(44 + dataBytes);
  void ascii(int offset, String text) {
    for (var i = 0; i < text.length; i++) {
      out.setUint8(offset + i, text.codeUnitAt(i));
    }
  }

  ascii(0, 'RIFF');
  out.setUint32(4, 36 + dataBytes, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  out.setUint32(16, 16, Endian.little); // the size of this chunk
  out.setUint16(20, 1, Endian.little); // PCM
  out.setUint16(22, 1, Endian.little); // mono
  out.setUint32(24, rate, Endian.little);
  out.setUint32(28, rate * 2, Endian.little); // bytes a second
  out.setUint16(32, 2, Endian.little); // bytes a frame
  out.setUint16(34, 16, Endian.little); // bits a sample
  ascii(36, 'data');
  out.setUint32(40, dataBytes, Endian.little);
  for (var i = 0; i < samples.length; i++) {
    out.setInt16(44 + i * 2, samples[i], Endian.little);
  }
  return out.buffer.asUint8List();
}
