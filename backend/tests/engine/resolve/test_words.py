from engine.resolve.words import mentions, odds_label, stems


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


def test_odds_read_as_words():
    assert odds_label(0.1) == "about 1 in 10"
    assert odds_label(0.03) == "about 1 in 33"
    assert odds_label(0.5) == "even odds"
    assert odds_label(0.9) == "very likely"


def test_spanish_and_catalan_small_words_and_accents_match_like_english_ones():
    # S10: a Spanish story's sheet and the models' words are in Spanish.
    assert mentions("Cuchilla del Aura", "la cuchilla de aura")
    assert mentions("L'espasa de llum", "espasa de la llum")
    assert stems("técnica") == {"técnica"}
    assert mentions("Técnica secreta", "técnica")
    assert not mentions("Técnica secreta", "tecnica prohibida")
    # English words that happen to be Spanish ones still count.
    assert mentions("a sin against the gods", "sin")
