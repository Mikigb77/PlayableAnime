"""Speech the voice model read (V9), as the file the app plays: MP3.

Gemini's TTS models send raw 16-bit mono PCM, with its rate in the type
(`audio/L16;codec=pcm;rate=24000`): 48 KB a second. As 48 kbps MP3 it is an eighth of that, about
350 KB for a minute of narration, which a phone streams on any connection and plays everywhere
(Android, iOS and browsers). A WAV is read as PCM, and an MP3 is kept as it is.
"""

from __future__ import annotations

import io
import re
import wave
from dataclasses import dataclass

MP3 = "audio/mpeg"
BIT_RATE_KBPS = 48
_PCM_TYPES = ("audio/l16", "audio/pcm", "audio/raw")
_RATE = re.compile(r"(?:^|;)\s*rate=(\d+)")
_CHANNELS = re.compile(r"(?:^|;)\s*channels=(\d+)")


@dataclass(frozen=True, repr=False)
class Encoded:
    data: bytes
    mime_type: str
    duration_ms: int

    def __repr__(self) -> str:
        return (
            f"Encoded(mime_type={self.mime_type!r}, bytes={len(self.data)}, ms={self.duration_ms})"
        )


def to_mp3(data: bytes, mime_type: str) -> Encoded:
    """The speech as MP3, with how long it plays. Raises ValueError for audio it can't read."""
    kind = mime_type.split(";", 1)[0].strip().lower()
    if kind in _PCM_TYPES:
        params = mime_type.lower()
        rate = int(_RATE.search(params).group(1)) if _RATE.search(params) else 24_000
        channels = int(_CHANNELS.search(params).group(1)) if _CHANNELS.search(params) else 1
        return _encode(data, rate, channels)
    if kind in ("audio/wav", "audio/x-wav", "audio/wave"):
        with wave.open(io.BytesIO(data), "rb") as clip:
            if clip.getsampwidth() != 2:
                raise ValueError("Only 16-bit WAV can be read")
            pcm = clip.readframes(clip.getnframes())
            return _encode(pcm, clip.getframerate(), clip.getnchannels())
    if kind in (MP3, "audio/mp3"):
        # Kept as sent; its length is estimated from the bit rate the model is likely to use.
        return Encoded(data, MP3, round(len(data) * 8 / BIT_RATE_KBPS))
    raise ValueError(f"Unsupported speech type {kind!r}")


def _encode(pcm: bytes, rate: int, channels: int) -> Encoded:
    if channels not in (1, 2) or not 8_000 <= rate <= 48_000:
        raise ValueError("Unsupported PCM layout")
    frames = len(pcm) // (2 * channels)
    if frames == 0:
        raise ValueError("The speech is empty")
    import lameenc  # loads on first use (B10)

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(BIT_RATE_KBPS)
    encoder.set_in_sample_rate(rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)  # 2 is near the best LAME does, and still fast for speech
    data = bytes(encoder.encode(pcm[: frames * 2 * channels]) + encoder.flush())
    return Encoded(data, MP3, round(frames * 1000 / rate))
