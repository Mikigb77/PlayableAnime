"""A scene's narration as the voice reads it, in parts (V9, V10), and the MP3 the app plays."""

import io
import struct
import wave

import pytest

from graph.llm.fake import offline_speech
from speech.audio import MP3, to_mp3
from speech.reading import (
    FIRST_PART_CHARS,
    MAX_PARTS,
    PART_CHARS,
    READING_STYLE,
    reading_parts,
    reading_prompt,
    spoken_text,
)

SENTENCE = "The bodyguards stir, chairs scraping on the tiles as they rise one by one."


def test_the_voice_reads_words_not_emphasis_marks():
    narration = "You step *inside*.\n\n**Carmine**  looks\nup.\n\n\n  "

    assert spoken_text(narration) == "You step inside.\n\nCarmine looks up."


def test_a_short_scene_is_one_part():
    assert reading_parts("The rain stops. You listen.") == ["The rain stops. You listen."]


def test_nothing_to_read_is_no_parts():
    assert reading_parts("  **  ") == []


def test_the_first_part_is_short_so_playback_starts_quickly():
    long_paragraph = " ".join([SENTENCE] * 20)
    narration = f'The door creaks. "Who\'s there?"\n\n{long_paragraph}\n\nYou fire twice.'

    parts = reading_parts(narration)

    assert len(parts[0]) <= FIRST_PART_CHARS
    assert parts[0].startswith('The door creaks. "Who\'s there?"')
    assert all(len(part) <= PART_CHARS for part in parts)
    assert parts[-1].endswith("You fire twice.")
    # Nothing is lost or reordered, and sentences keep their closing marks and quotes.
    assert " ".join(" ".join(parts).split()) == " ".join(spoken_text(narration).split())


def test_paragraphs_stay_whole_and_pause_between_them():
    narration = "\n\n".join(f"Paragraph {n} is short." for n in range(1, 40))

    parts = reading_parts(narration)

    assert "\n\nParagraph 2 is short." in parts[0]
    for part in parts:
        assert all(p.startswith("Paragraph ") for p in part.split("\n\n"))


def test_a_sentence_too_long_for_a_part_splits_between_words():
    sentence = " ".join(["word"] * 400) + "."

    parts = reading_parts(sentence)

    assert len(parts) > 1
    assert all(len(part) <= PART_CHARS for part in parts)
    assert " ".join(parts).split() == sentence.split()


def test_the_same_narration_always_splits_the_same_way():
    narration = "\n\n".join([" ".join([SENTENCE] * 6)] * 5)

    assert reading_parts(narration) == reading_parts(narration)


def test_a_pathological_text_has_a_bounded_number_of_parts():
    narration = "\n\n".join([" ".join([SENTENCE] * 9)] * 40)

    assert len(reading_parts(narration)) == MAX_PARTS


def test_the_voice_gets_directions_then_the_passage():
    prompt = reading_prompt("Rain on the roof.")

    assert prompt == f"{READING_STYLE}:\n\nRain on the roof."
    assert "Spanish" not in READING_STYLE and "English" not in READING_STYLE  # any language


def test_geminis_pcm_becomes_mp3_with_its_length():
    pcm = offline_speech("x" * 80)  # two seconds at 24 kHz

    encoded = to_mp3(pcm, "audio/L16;codec=pcm;rate=24000")

    assert encoded.mime_type == MP3
    assert encoded.duration_ms == 2000
    assert encoded.data[:3] == b"ID3" or encoded.data[0] == 0xFF  # an MP3 frame or tag
    assert len(encoded.data) < len(pcm) / 6


def test_a_wav_is_read_as_its_pcm():
    out = io.BytesIO()
    with wave.open(out, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16_000)
        clip.writeframes(struct.pack("<h", 0) * 8_000)

    assert to_mp3(out.getvalue(), "audio/wav").duration_ms == 500


def test_audio_it_cant_read_is_refused():
    with pytest.raises(ValueError):
        to_mp3(b"\x00" * 100, "audio/ogg")
    with pytest.raises(ValueError):
        to_mp3(b"", "audio/L16;rate=24000")
