"""What a scene sounds like read aloud (V8, V9, V10): its narration as spoken text, in parts.

The app reads a scene in parts, so the first words play within a couple of seconds and the next
part is read while one plays. Each part is read once per voice and kept (V10), so the same text
must always split the same way: the parts depend only on the narration.

- The narration's emphasis marks (`*italic*`, `**bold**`) are dropped: the voice reads words.
- A part is one or more whole paragraphs, joined with a blank line so the voice pauses there.
- The first part is short, a paragraph or its first sentences, so playback starts quickly. The
  others run up to `PART_CHARS`.
- A paragraph too long for a part is split between sentences, and a sentence too long for one
  between words.
"""

from __future__ import annotations

import re

# About 15 seconds of speech, then about 45: a model reads a part in a few seconds, well inside
# the time the part before it takes to play.
FIRST_PART_CHARS = 240
PART_CHARS = 700
# A scene is at most a few thousand characters (R1, S6's long narration is 250 to 450 words), so
# this only bounds a pathological text.
MAX_PARTS = 24

# Directions the voice model reads its text with (V9). Gemini's TTS models take them before the
# text, ending in a colon, and read only what follows. The language isn't named: a story can
# switch language (S10), so a scene is read in whatever language it was written in.
READING_STYLE = (
    "Read the following passage from a story aloud, as a skilled audiobook narrator would: "
    "warm, clear and immersive, at an unhurried pace, following the mood of each moment and "
    "giving the characters' lines a little life, without overacting. Read only the passage"
)

_EMPHASIS = re.compile(r"\*+")
_PARAGRAPH = re.compile(r"\n\s*\n")
_SPACES = re.compile(r"\s+")
# The end of a sentence: its mark and any closing quote or bracket, before a space.
_SENTENCE_END = re.compile(r"[.!?…][\"'”’»)\]]*(?=\s)")


def spoken_text(narration: str) -> str:
    """The narration as it is read: no emphasis marks, one space between words, and a blank line
    between paragraphs."""
    paragraphs = (
        _SPACES.sub(" ", p).strip() for p in _PARAGRAPH.split(_EMPHASIS.sub("", narration))
    )
    return "\n\n".join(p for p in paragraphs if p)


def reading_parts(narration: str) -> list[str]:
    """The scene's spoken text in parts, in reading order. Empty when there is nothing to read."""
    parts: list[str] = []
    current = ""
    for piece in _pieces(spoken_text(narration)):
        limit = FIRST_PART_CHARS if not parts else PART_CHARS
        if current and len(current) + 2 + len(piece.text) > limit:
            parts.append(current)
            current = ""
        if current:
            current += "\n\n" if piece.starts_paragraph else " "
        current += piece.text
    if current:
        parts.append(current)
    if len(parts) > MAX_PARTS:
        parts[MAX_PARTS - 1 :] = [" ".join(parts[MAX_PARTS - 1 :])]
    return parts


def reading_prompt(part: str) -> str:
    """What the voice model is sent for one part: the directions, then the text."""
    return f"{READING_STYLE}:\n\n{part}"


class _Piece:
    __slots__ = ("starts_paragraph", "text")

    def __init__(self, text: str, starts_paragraph: bool) -> None:
        self.text = text
        self.starts_paragraph = starts_paragraph


def _pieces(text: str) -> list[_Piece]:
    """Whole paragraphs where they fit a part, else their sentences, else runs of words. A piece
    is never longer than the first part, so the first part always has one."""
    pieces: list[_Piece] = []
    for paragraph in text.split("\n\n"):
        if len(paragraph) <= FIRST_PART_CHARS:
            pieces.append(_Piece(paragraph, True))
            continue
        first = True
        for sentence in _sentences(paragraph):
            for words in _word_runs(sentence, FIRST_PART_CHARS):
                pieces.append(_Piece(words, first))
                first = False
    return [piece for piece in pieces if piece.text]


def _sentences(paragraph: str) -> list[str]:
    """A paragraph's sentences, each with its own closing mark and quotes."""
    sentences = []
    start = 0
    for end in _SENTENCE_END.finditer(paragraph):
        sentences.append(paragraph[start : end.end()].strip())
        start = end.end()
    sentences.append(paragraph[start:].strip())
    return [sentence for sentence in sentences if sentence]


def _word_runs(sentence: str, limit: int) -> list[str]:
    """A sentence in runs of whole words, each at most `limit` characters (a single longer word
    stands alone)."""
    if len(sentence) <= limit:
        return [sentence]
    runs: list[str] = []
    current = ""
    for word in sentence.split(" "):
        if current and len(current) + 1 + len(word) > limit:
            runs.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        runs.append(current)
    return runs
