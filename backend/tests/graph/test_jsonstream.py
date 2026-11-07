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


def _stream(text: str, field: str | tuple[str, ...], sizes: list[int]) -> str:
    streamer = JsonFieldStreamer(*((field,) if isinstance(field, str) else field))
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


# R1: the narrator's action, then its narration, streamed as one scene.
SCENE = ("action", "narration")


@pytest.mark.parametrize("action", [t for t in TRICKY if t])
@pytest.mark.parametrize("narration", [t for t in TRICKY if t])
def test_two_fields_stream_one_after_the_other_with_a_paragraph_between(action, narration):
    document = {
        "action": action,
        "nested": {"narration": "not this one"},
        "narration": narration,
        "suggestions": [{"label": "Run", "kind": "side"}],
    }
    text = json.dumps(document, ensure_ascii=False)
    rng = random.Random(11)
    for _ in range(20):
        sizes = [rng.randint(1, 9) for _ in range(8)]
        assert _stream(text, SCENE, sizes) == f"{action}\n\n{narration}"
    assert _stream(text, SCENE, [1]) == f"{action}\n\n{narration}"


def test_an_empty_first_field_adds_no_break():
    """An opening has no action: its narration streams alone, as it always did."""
    assert _stream('{"action": "", "narration": "You wake."}', SCENE, [3]) == "You wake."
    assert _stream('{"narration": "You wake."}', SCENE, [3]) == "You wake."


@pytest.mark.parametrize(
    ("action", "narration"),
    [
        ("You reach out.", "\n  The merchant  nods. "),
        ("\n You pay. ", "Hu nods."),
        ("  ", "Hu nods."),
        ("You wait.", "  "),
        ("", ""),
        ("A  gap,\n\nthen more.  ", "\tAnd\u00a0on."),
    ],
)
def test_the_stream_reads_as_the_saved_scene(action, narration):
    """Spaces at each field's edges are held back, so what streams is what is saved (R1)."""
    text = json.dumps({"action": action, "narration": narration, "suggestions": []})
    saved = "\n\n".join(part for part in (action.strip(), narration.strip()) if part)
    for size in (1, 2, 7, len(text)):
        assert _stream(text, SCENE, [size]) == saved


def test_a_field_that_comes_after_a_later_one_is_left_to_the_final_parse():
    """The stream never shows the outcome before the action: the saved scene puts it first."""
    text = '{"narration": "He takes it.", "action": "You hold out a coin."}'
    assert _stream(text, SCENE, [3]) == "He takes it."


def test_fields_stream_in_order_and_done_waits_for_the_last():
    streamer = JsonFieldStreamer(*SCENE)

    assert streamer.feed('{"action": "You hold out') == "You hold out"
    assert streamer.feed(' a coin.", "narr') == " a coin."
    assert not streamer.done
    assert streamer.feed('ation": "He takes it."') == "\n\nHe takes it."
    assert streamer.done
    assert streamer.feed(', "action": "again"}') == ""


def test_a_streamer_needs_a_field():
    with pytest.raises(ValueError):
        JsonFieldStreamer()


def test_strip_code_fence():
    assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}\n'
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'
    assert json.loads(strip_code_fence('  ```\n{"a": 1}```  ')) == {"a": 1}
