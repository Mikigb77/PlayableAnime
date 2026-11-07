"""Streams string fields out of a JSON object while the model is still writing it.

The narrator answers in one structured-output call (B5 step 5), but the player must see the
narration as it is written (S3, B7). This reads the raw JSON chunks and hands back the decoded
text of top-level string fields, such as `action` and then `narration` (R1), as soon as each
character arrives, with a paragraph break between one field's text and the next. The complete
JSON is still parsed and validated at the end; the streamed text is for display only.
"""

from __future__ import annotations

from typing import Literal

_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_Role = Literal["key", "target", "skip"]

# What goes between one streamed field's text and the next: a paragraph break (R1).
PARAGRAPH = "\n\n"


class JsonFieldStreamer:
    """Feed it JSON text in any chunk sizes; it returns the new text of `fields` each time.

    It tracks just enough of the grammar to know where top-level keys and values are, and
    decodes escapes, including `\\uXXXX` surrogate pairs split across chunks. Only the first
    occurrence of each field is streamed, and only in the order `fields` gives: once one has
    started, an earlier one that comes after it is left to the final parse, so the stream never
    shows the scene's parts out of order. Each field's text goes out without the spaces at its
    start and end, like `str.strip`, and one that follows streamed text starts with `joiner`, so
    a blank field adds nothing and the stream reads as the fields stripped and joined.
    """

    def __init__(self, *fields: str, joiner: str = PARAGRAPH):
        if not fields:
            raise ValueError("JsonFieldStreamer needs at least one field")
        self._fields = fields
        self._joiner = joiner
        self._at = -1  # the place in `fields` of the field that started last
        # Whether any field's text went out, whether the current one's has yet, and the spaces
        # held back until the current field's text goes on (dropped if it ends instead).
        self._wrote = False
        self._field_wrote = False
        self._spaces: list[str] = []
        self._depth = 0
        self._expect: Literal["key", "colon", "value", "comma"] = "key"
        self._in_string = False
        self._role: _Role = "skip"
        self._escape: str | None = None
        self._high_surrogate: int | None = None
        self._key: list[str] = []
        self._last_key: str | None = None
        self._out: list[str] = []
        self.done = False  # the last field has ended, so nothing more can stream

    def feed(self, text: str) -> str:
        for ch in text:
            self._step(ch)
        out = "".join(self._out)
        self._out.clear()
        return out

    def _step(self, ch: str) -> None:
        if self._in_string:
            self._string_char(ch)
        elif ch == '"':
            self._open_string()
        elif ch in "{[":
            self._depth += 1
            if self._depth == 1:
                self._expect = "key"
        elif ch in "}]":
            self._depth -= 1
            if self._depth == 1:
                self._expect = "comma"
        elif self._depth == 1:
            if ch == ":":
                self._expect = "value"
            elif ch == ",":
                self._expect = "key"
            elif not ch.isspace() and self._expect == "value":
                self._expect = "comma"  # a number, true, false or null

    def _open_string(self) -> None:
        self._in_string = True
        if self._depth == 1 and self._expect == "key":
            self._role = "key"
            self._key = []
        elif (
            self._depth == 1
            and self._expect == "value"
            and self._last_key in self._fields
            and self._fields.index(self._last_key) > self._at
        ):
            self._role = "target"
            self._at = self._fields.index(self._last_key)
            self._field_wrote = False
            self._spaces = []
        else:
            self._role = "skip"

    def _string_char(self, ch: str) -> None:
        if self._escape is not None:
            self._escape += ch
            if self._escape[0] != "u":
                self._escape, escape = None, self._escape
                self._emit(_SIMPLE_ESCAPES.get(escape, escape))
            elif len(self._escape) == 5:
                self._escape, escape = None, self._escape
                try:
                    self._emit_code(int(escape[1:], 16))
                except ValueError:
                    pass  # not valid JSON; the final parse will reject it
        elif ch == "\\":
            self._escape = ""
        elif ch == '"':
            self._close_string()
        else:
            self._emit(ch)

    def _close_string(self) -> None:
        self._flush_surrogate()
        self._in_string = False
        if self._depth != 1:
            return
        if self._role == "key":
            self._last_key = "".join(self._key)
            self._expect = "colon"
        else:
            if self._role == "target" and self._at == len(self._fields) - 1:
                self.done = True
            self._expect = "comma"

    def _emit_code(self, code: int) -> None:
        if 0xD800 <= code <= 0xDBFF:
            self._flush_surrogate()
            self._high_surrogate = code
        elif 0xDC00 <= code <= 0xDFFF and self._high_surrogate is not None:
            high, self._high_surrogate = self._high_surrogate, None
            self._put(chr(0x10000 + ((high - 0xD800) << 10) + (code - 0xDC00)))
        elif 0xDC00 <= code <= 0xDFFF:
            self._put("�")
        else:
            self._emit(chr(code))

    def _emit(self, text: str) -> None:
        self._flush_surrogate()
        self._put(text)

    def _flush_surrogate(self) -> None:
        if self._high_surrogate is not None:
            self._high_surrogate = None
            self._put("�")

    def _put(self, text: str) -> None:
        if self._role == "target":
            for ch in text:
                self._put_target(ch)
        elif self._role == "key":
            self._key.append(text)

    def _put_target(self, ch: str) -> None:
        if ch.isspace():
            if self._field_wrote:  # leading spaces are dropped, later ones wait for more text
                self._spaces.append(ch)
            return
        if not self._field_wrote:
            if self._wrote:
                self._out.append(self._joiner)
            self._field_wrote = self._wrote = True
        self._out.extend(self._spaces)
        self._spaces.clear()
        self._out.append(ch)


def strip_code_fence(text: str) -> str:
    """Removes a Markdown code fence around JSON, which some models add despite JSON mode."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    first_newline = stripped.find("\n")
    if first_newline == -1:
        return text
    body = stripped[first_newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body
