"""Who words name, among the people on record (`engine.naming`, V3, W1, F3)."""

import pytest

from engine import naming
from engine.samples import grounded_world
from engine.state.cast import Character


def world(*people: Character):
    state = grounded_world()
    for person in people:
        state.characters[person.id] = person
    return state


def person(ref: str, name: str, *aliases: str) -> Character:
    return Character(id=ref, name=name, aliases=list(aliases))


MEI = person("mei", "Mei")
MEI_LIN = person("mei-lin", "Mei Lin")
MEI_HUA = person("mei-hua", "Mei Hua")
BRAM = person("bram", "Old Bram")
TESS = person("tess", "Old Tess", "the Widow")
SOL = person("sol", "Sol")
JOSE = person("jose", "José Ibáñez")


def test_names_are_folded_and_one_that_folds_to_nothing_is_left_out():
    state = world(JOSE, person("ghost", "幽鬼", "the Pale One"))
    assert naming.names(state, "jose") == ["jose ibanez"]
    assert naming.names(state, "ghost") == ["the pale one"]


def test_called_is_the_one_person_whose_name_the_words_are():
    state = world(JOSE, TESS, BRAM)
    everyone = ["jose", "tess", "bram"]
    assert naming.called(state, "jose ibañez", everyone) == "jose"
    assert naming.called(state, "The Widow!", everyone) == "tess"
    assert naming.called(state, "Old", everyone) is None  # a word of two names is neither
    assert naming.called(state, "", everyone) is None
    twins = world(person("a", "Mei"), person("b", "Mei"))
    assert naming.called(twins, "Mei", ["a", "b"]) is None


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("I kiss Mei", {"mei"}),
        ("then I kiss Mei", {"i", "mei"}),
        ("Old Bram waves. Then Mei smiles", {"bram", "mei"}),  # "Old" and "Then" open sentences
        ("Faig un petó a la Mei", {"mei"}),
        ("¿Dónde está José?", {"jose"}),
        ('she said: "Mei, wait"', set()),  # speech opens a sentence too
        ("under the sun", set()),
    ],
)
def test_a_capital_inside_a_sentence_is_a_sign_of_a_name(text, found):
    assert naming.capitals(text) == found


@pytest.mark.parametrize(
    ("label", "found"),
    [
        ("Mei", {"mei"}),
        ("la Mei", {"mei"}),
        ("La Mei", {"mei"}),
        ("L’Anna", {"anna"}),
        ("The barmaid", set()),
        ("the old man", set()),
        ("Old Bram", {"old", "bram"}),
    ],
)
def test_a_few_words_for_someone_count_from_their_first_word(label, found):
    assert naming.capitals(label, opening=True) == found


def test_named_in_singles_someone_out_or_names_nobody():
    state = world(MEI_LIN, MEI_HUA, BRAM, TESS, SOL)
    among = ["mei-lin", "mei-hua", "bram", "tess", "sol"]
    assert naming.named_in(state, ["I strike Bram"], among) == ["bram"]
    assert naming.named_in(state, ["strike old bram"], among) == ["bram"]  # the whole name
    assert naming.named_in(state, ["I strike the Widow"], among) == ["tess"]
    # A word two of them share singles out neither, and no blow lands on a guess (W1).
    assert naming.named_in(state, ["I strike Mei"], among) == []
    assert naming.named_in(state, ["I strike Mei Hua"], among) == ["mei-hua"]
    # A name that is also a word is only a name with its capital.
    assert naming.named_in(state, ["I rest under the sol tree"], among) == []
    assert naming.named_in(state, ["I rest beside Sol"], among) == ["sol"]


def test_everyone_named_takes_the_nearest_who_carry_the_word():
    state = world(MEI_LIN, MEI_HUA, MEI)
    near, far = ["mei-lin"], ["mei-hua", "mei"]
    assert naming.everyone_named(state, [near, far], ["I kiss Mei"]) == ["mei-lin"]
    assert naming.everyone_named(state, [[], far], ["I kiss Mei"]) == ["mei-hua", "mei"]
    assert naming.everyone_named(state, [near, far], ["I kiss her"]) == []


def test_everyone_named_holds_each_of_those_who_share_a_word():
    state = world(MEI_LIN, MEI_HUA)
    assert naming.everyone_named(state, [["mei-lin", "mei-hua"]], ["I kiss Mei"]) == [
        "mei-lin",
        "mei-hua",
    ]


def test_a_full_name_names_its_owner_wherever_they_are_and_keeps_its_words():
    state = world(MEI_LIN, MEI_HUA, BRAM, TESS)
    # Mei Hua is a day away and Mei Lin in the scene: the words still say which Mei.
    circles = [["mei-lin", "bram"], ["mei-hua", "tess"]]
    assert naming.everyone_named(state, circles, ["I kiss Mei Hua"]) == ["mei-hua"]
    # The "Old" of "Old Tess" isn't Old Bram.
    assert naming.everyone_named(state, circles, ["I kiss Old Tess"]) == ["tess"]
    assert naming.everyone_named(state, circles, ["I kiss Tess and Bram"]) == ["bram", "tess"]


def test_everyone_named_reads_a_few_words_for_someone_from_their_first():
    state = world(MEI, TESS)
    circles = [["mei", "tess"]]
    assert naming.everyone_named(state, circles, labels=["Mei"]) == ["mei"]
    assert naming.everyone_named(state, circles, labels=["la Mei"]) == ["mei"]
    assert naming.everyone_named(state, circles, labels=["the widow"]) == ["tess"]
    assert naming.everyone_named(state, circles, labels=["The barmaid", "her"]) == []
    # As a sentence, the same word only opens it.
    assert naming.everyone_named(state, circles, ["Mei"]) == []


def test_everyone_called_is_whoever_a_few_words_are_the_name_of():
    state = world(MEI, MEI_LIN, TESS, SOL, JOSE)
    circles = [["mei-lin", "tess"], ["mei", "sol", "jose"]]
    assert naming.everyone_called(state, circles, ["Mei"]) == ["mei-lin"]  # the nearest Mei
    assert naming.everyone_called(state, circles, ["la Mei", "Tess"]) == ["mei-lin", "tess"]
    assert naming.everyone_called(state, circles, ["the widow"]) == ["tess"]  # an alias, whole
    assert naming.everyone_called(state, circles, ["jos\u00e9 ib\u00e1\u00f1ez"]) == ["jose"]
    # One word is a name only with its capital, and words that only hold a name name nobody.
    assert naming.everyone_called(state, circles, ["sol", "the Sol Gate", "Tess's maid"]) == []
    assert naming.everyone_called(state, circles, ["her", "the barmaid", "", "The"]) == []


def test_someone_named_for_anothers_sake_counts():
    state = world(MEI)
    assert naming.everyone_named(state, [["mei"]], ["I flirt with Mei's mother"]) == ["mei"]
