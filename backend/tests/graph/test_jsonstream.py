import json
import random

import pytest

from graph.llm.jsonstream import JsonFieldStreamer, strip_code_fence

TRICKY = [
    "You drop to a crouch.\nYour fingers close on a stone.",
    'He says "run" and \\ runs, tab\there, slash / done.',
    "Emoji 🐉 and accents: café, 東京, ünïcödé",
    "Braces {like} [these], colons: and commas, inside text",
    "",
]


def _stream(text: str, field: str, sizes: list[int]) -> str:
    streamer = JsonFieldStreamer(field)
    out, pos, index = [], 0, 0
    while pos < len(text):
        size = sizes[index % len(sizes)]
        out.append(streamer.feed(text[pos : pos + size]))
        pos += size
        index += 1
    return "".join(out)


@pytest.mark.parametrize("narration", TRICKY)
@pytest.mark.parametrize("ensure_ascii", [True, False])
def test_streams_the_field_exactly_over_any_chunking(narration, ensure_ascii):
    document = {
        "title": 'A "quoted" {title}',
        "nested": {"narration": "not this one", "list": ["narration", 1, {"a": [2, 3]}]},
        "count": 3,
        "flag": True,
        "nothing": None,
        "narration": narration,
        "choices": [{"id": "c1", "label": "Run"}],
    }
    text = json.dumps(document, ensure_ascii=ensure_ascii)
    rng = random.Random(7)
    for _ in range(40):
        sizes = [rng.randint(1, 9) for _ in range(8)]
        assert _stream(text, "narration", sizes) == narration
    assert _stream(text, "narration", [1]) == narration
    assert _stream(text, "narration", [len(text)]) == narration


def test_streams_as_soon_as_characters_arrive():
    streamer = JsonFieldStreamer("narration")

    assert streamer.feed('{"narration": "You re') == "You re"
    assert streamer.feed("ach for the st") == "ach for the st"
    assert streamer.feed('one", "choices": []}') == "one"
    assert streamer.done


def test_an_escape_split_across_chunks_is_decoded_once_complete():
    streamer = JsonFieldStreamer("narration")
    pieces = ['{"narration": "a\\', "u00", "e9 b \\ud83d", "\\ude00", ' c"}']

    assert "".join(streamer.feed(p) for p in pieces) == "aé b 😀 c"


def test_a_lone_surrogate_becomes_a_replacement_character():
    streamer = JsonFieldStreamer("narration")

    assert streamer.feed('{"narration": "x\\ud83dy"}') == "x�y"


@pytest.mark.parametrize(
    "document",
    [
        {"other": "text"},
        {"narration": None},
        {"narration": 42},
        {"narration": ["a", "b"]},
        {"wrapper": {"narration": "nested"}},
    ],
)
def test_nothing_streams_unless_the_top_level_field_is_a_string(document):
    assert _stream(json.dumps(document), "narration", [3]) == ""


def test_only_the_first_occurrence_streams():
    assert _stream('{"narration": "one", "narration": "two"}', "narration", [4]) == "one"


def test_text_before_the_object_is_ignored():
    assert _stream('```json\n{"narration": "hi"}\n```', "narration", [5]) == "hi"


def test_strip_code_fence():
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}\n'
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
    assert json.loads(strip_code_fence('  ```\n{"a": 1}```  ')) == {"a": 1}
