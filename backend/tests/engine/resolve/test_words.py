from engine.resolve.words import contains, mentions, odds_label, stems


def test_stems_fold_simple_word_forms_together():
    assert stems("Teleports her out of danger") == {"teleport", "danger"}
    assert stems("stopped time") == stems("time stop")
    assert stems("breathing") == stems("breathe")
    assert stems("the fires") == stems("a fire")


def test_mentions_matches_either_way_and_contains_only_one_way():
    assert mentions("Beretta pistol", "my pistol")
    assert mentions("pistol", "the Beretta pistol")
    assert not mentions("a bottle of grappa on the bar", "the bar stool")
    assert contains("Void Step: teleports her a mile", "teleport")
    assert not contains("Fire", "put out the fire")
    assert not mentions("", "anything") and not contains("anything", "the")


def test_odds_read_as_words():
    assert odds_label(0.1) == "about 1 in 10"
    assert odds_label(0.03) == "about 1 in 33"
    assert odds_label(0.5) == "even odds"
    assert odds_label(0.9) == "very likely"
