"""R9: the wording the last scenes repeated, read by code, and whether the player's own words
are about how the character looks. Every scene here is made up."""

import pytest

from engine.context import Language
from graph.turn.types import WORN_SCENES, PastScene
from graph.turn.worn import (
    FILLER,
    MINE,
    OWN,
    SHOWING,
    WORN_MAX,
    WORN_MIN,
    phrases,
    touches,
    worn_phrases,
)

EN, ES, CA = Language.EN, Language.ES, Language.CA


def scenes(*texts: str) -> list[PastScene]:
    return [PastScene(turn, text) for turn, text in enumerate(texts, start=1)]


def test_a_phrase_starts_and_ends_on_a_word_that_says_something():
    found = phrases("You meet her deep black eyes, and your leather boots scuff the stone.", EN)

    assert {"deep black eyes", "black eyes", "leather boots", "scuff the stone"} <= found
    # Never a phrase that starts or ends on a small word, nor one across a comma.
    assert not any(p.split()[0] in ("you", "her", "and", "your", "the") for p in found)
    assert not any(p.split()[-1] in ("her", "the", "your") for p in found)
    assert "eyes and" not in found and "black eyes and your leather" not in found
    assert all(2 <= len(p.split()) <= 4 for p in found)


def test_a_name_is_never_wording():
    text = "Old Hu nods slowly. You follow Zhao Kun past the Azure Peak gate. Hu nods slowly."
    found = phrases(text, EN, ["Old Hu"])

    # A capital inside a sentence is a name, and so is a name on record at a sentence's start.
    assert "nods slowly" in found
    assert not any(word in p.split() for p in found for word in ("hu", "zhao", "kun", "azure"))
    # An ordinary word at a sentence's start is no name.
    assert "old stones crack" in phrases("Old stones crack underfoot.", EN, ["Hu"])


def test_a_name_on_record_is_a_name_in_small_letters_too():
    crossing = "You cross the outer court as cold rain falls, three spirit stones in your fist."
    told = scenes(crossing, crossing, crossing)

    # Without the record, the place and the money read as wording like any other.
    assert "outer court" in phrases(crossing, EN) and "spirit stones" in phrases(crossing, EN)
    # With it no phrase holds them, whole or in part, and the rest still counts.
    found = phrases(crossing, EN, ["The Outer Court", "spirit stones"])
    assert not any(word in p.split() for p in found for word in ("outer", "court", "spirit"))
    assert worn_phrases(told, EN, ["The Outer Court", "spirit stones"]) == ["cold rain falls"]
    # A word a name shares is still wording on its own: a rung called Body Tempering doesn't
    # make "absolute body mastery" a name.
    mastery = scenes(*["With absolute body mastery, you hold."] * 3)
    assert worn_phrases(mastery, EN, ["Body Tempering"]) == ["absolute body mastery"]


def test_every_language_a_story_is_told_in_has_its_small_words():
    assert set(FILLER) == set(SHOWING) == set(OWN) == set(MINE) == set(Language)


@pytest.mark.parametrize(
    ("language", "text", "phrase"),
    [
        (
            ES,
            "—No lo sé —dice, y sus ojos negros te miran. Las botas de cuero crujen.",
            "ojos negros",
        ),
        (ES, "Notas que tus botas de cuero crujen sobre la piedra.", "botas de cuero crujen"),
        (CA, "Sents que l'espasa de ferro et pesa a la mà.", "l'espasa de ferro"),
        (CA, "Els teus ulls negres es claven en l'home.", "ulls negres"),
    ],
)
def test_phrases_are_read_in_spanish_and_catalan(language, text, phrase):
    found = phrases(text, language)

    assert phrase in found
    assert not any(p.split()[0] in ("de", "la", "el", "tus", "els", "teus", "que") for p in found)


def test_a_phrase_is_worn_once_three_of_the_last_dozen_scenes_used_it():
    twice = scenes("Your deep black eyes narrow.", "She studies your deep black eyes.", "Rain.")
    assert worn_phrases(twice, EN) == []

    thrice = [*twice, PastScene(4, "His gaze meets your deep black eyes.")]
    assert worn_phrases(thrice, EN) == ["deep black eyes"]
    assert WORN_MIN == 3
    # Said three times in one scene is one scene.
    once = scenes("Deep black eyes. Deep black eyes. Deep black eyes, again.")
    assert worn_phrases(once, EN) == []
    # Scenes older than the last dozen are not read.
    later = [*thrice, *scenes(*["The rain keeps falling."] * WORN_SCENES)]
    assert "deep black eyes" not in worn_phrases(later, EN)


def test_one_worn_sentence_gives_one_phrase():
    spine = "A shiver runs down your spine."
    told = scenes(spine, spine, spine, "Leather boots.", "Your leather boots.", "Leather boots!")

    # Phrases that share a word that says something count once, the longest first.
    assert worn_phrases(told, EN) == ["runs down your spine", "leather boots"]
    # A shorter phrase that more scenes used stands in for the longer ones that hold it.
    eyes = scenes(
        "Your deep black eyes.",
        "Deep black eyes.",
        "Deep black eyes.",
        "Black eyes.",
        "Black eyes.",
    )
    assert worn_phrases(eyes, EN) == ["black eyes"]


def test_the_list_is_short_and_leaves_names_out():
    pairs = [
        "pale moon", "cold wind", "wet stone", "thin smoke", "grey dawn", "soft rain",
        "dark water", "bright steel", "old oak", "red clay", "dry reeds",
    ]  # fmt: skip
    many = " ".join(f"A {pair} rises." for pair in pairs)
    told = scenes(*[f"{many} Old Hu nods slowly."] * 3)

    worn = worn_phrases(told, EN, ["Old Hu"])
    assert len(pairs) > WORN_MAX == len(worn)
    assert not any("hu" in phrase.split() for phrase in worn)


def test_the_players_words_touch_their_looks():
    looks = "16, slight, black hair tied back, steady eyes. A thin disciple in a patched grey robe."

    assert touches("I tie my hair back and bow", looks, EN)
    assert touches("I brush the dust from my robe", looks, EN)
    assert touches("I wipe the blood from my face", looks, EN)
    assert touches("I study my reflection in the water", looks, EN)
    assert not touches("I ask Old Hu what the draught is for", looks, EN)
    # A word of their looks that isn't said of them is no look of theirs.
    assert not touches("I step back and look the disciple in the eyes", looks, EN)
    assert not touches("I hit him in the face", looks, EN)
    assert not touches("I ask my master why the grey disciple left", looks, EN)
    # A small word they share is no look.
    assert not touches("I sit in the shade", looks, EN)
    assert touches("Me miro en el espejo", "Pelo negro recogido.", ES)
    assert touches("Me recojo el pelo", "Pelo negro recogido.", ES)
    assert touches("Me ajusto la túnica gris", "Pelo negro recogido, túnica gris.", ES)
    assert not touches("Le tiro del pelo", "Pelo negro recogido.", ES)
    assert not touches(
        "Le pregunto a Hu por la poción", "Pelo negro recogido, de mirada firme.", ES
    )
    assert touches("Em miro al mirall", "Cabells negres recollits.", CA)
    assert touches("M’aparto els cabells de la cara", "Cabells negres recollits.", CA)
    assert not touches("Li estiro els cabells", "Cabells negres recollits.", CA)
    assert not touches("Li pregunto pel beuratge", "Cabells negres recollits.", CA)
