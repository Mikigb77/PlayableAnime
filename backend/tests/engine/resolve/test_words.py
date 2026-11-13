from engine.resolve.words import mentions, stems
from engine.text import normalize


def test_stems_fold_simple_word_forms_together():
    assert stems("Teleports her out of danger") == {"teleport", "danger"}
    assert stems("stopped time") == stems("time stop")
    assert stems("breathing") == stems("breathe")
    assert stems("the fires") == stems("a fire")


def test_mentions_matches_one_way_only():
    assert mentions("Beretta pistol", "my pistol")
    assert mentions("Void Step: teleports her a mile", "teleport")
    # Extra words in what the model wrote never match by accident.
    assert not mentions("pistol", "a grenade in my pistol holster")
    assert not mentions("the bar", "a shotgun under the bar")
    assert not mentions("Fire", "put out the fire")
    assert not mentions("a bottle of grappa on the bar", "the bar stool")
    assert not mentions("", "anything") and not mentions("anything", "the")


def test_spanish_and_catalan_small_words_and_accents_match_like_english_ones():
    # S10: a Spanish story's sheet and the models' words are in Spanish.
    assert mentions("Cuchilla del Aura", "la cuchilla de aura")
    assert mentions("L'espasa de llum", "espasa de la llum")
    assert stems("técnica") == {"técnica"}
    assert mentions("Técnica secreta", "técnica")
    assert not mentions("Técnica secreta", "tecnica prohibida")
    # English words that happen to be Spanish ones still count.
    assert mentions("a sin against the gods", "sin")


def test_a_dash_or_a_quote_mark_parts_two_words_as_a_space_does():
    # Dropped like an accent, a dash ran the words beside it together, and the first live story
    # to name a realm between dashes lost the name (2026-11-13).
    told = "a higher realm—Ascendant Divinity—shimmers"
    assert normalize(told) == "a higher realm ascendant divinity shimmers"
    assert (
        normalize("so–on, “Void‐Walker”,«Reino Celestial»") == "so on void walker reino celestial"
    )
    # Either typographic apostrophe, the one that is a letter to Unicode included, and a
    # separator that is no plain space.
    assert normalize("Beyoncé’s l’amor, lʼaigua") == "beyonce s l amor l aigua"
    assert normalize("one\u2028two") == "one two"
    assert normalize("—¿Qué reino? —dijo—. ¡El Núcleo!") == "que reino dijo el nucleo"


def test_a_letter_an_accent_and_the_raised_dot_stay_inside_their_word():
    assert normalize("La col·lecció intel·ligent del Núcleo Daurat") == (
        "la colleccio intelligent del nucleo daurat"
    )
    assert normalize("naïve FAÇADE") == "naive facade"
