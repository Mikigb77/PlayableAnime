"""Streams one string field out of a JSON object while the model is still writing it.

The narrator answers in one structured-output call (B5 step 5), but the player must see the
narration as it is written (S3, B7). This reads the raw JSON chunks and hands back the decoded
text of one top-level string field, such as `narration`, as soon as each character arrives. The
complete JSON is still parsed and validated at the end; the streamed text is for display only.
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


class JsonFieldStreamer:
    """Feed it JSON text in any chunk sizes; it returns the new text of `field` each time.

    It tracks just enough of the grammar to know where top-level keys and values are, and
    decodes escapes, including `\\uXXXX` surrogate pairs split across chunks. Only the first
    occurrence of the field is streamed.
    """

    def __init__(self, field: str):
        self._field = field
        self._depth = 0
        self._expect: Literal["key", "colon", "value", "comma"] = "key"
        self._in_string = False
        self._role: _Role = "skip"
        self._escape: str | None = None
        self._high_surrogate: int | None = None
        self._key: list[str] = []
        self._last_key: str | None = None
        self._out: list[str] = []
        self.done = False

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
            and self._last_key == self._field
            and not self.done
        ):
            self._role = "target"
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
            if self._role == "target":
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
            self._out.append(text)
        elif self._role == "key":
            self._key.append(text)


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
