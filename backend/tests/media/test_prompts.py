"""The house style, the world's look and the mild-in-every-rating rules (S7, M5, M6)."""

import pytest

from media.prompts import (
    ASPECT_RATIOS,
    FRAMING,
    HOUSE_STYLE,
    MAX_DESCRIPTION_CHARS,
    MILD_RULES,
    Brief,
    Figure,
    WorldLook,
    build_prompt,
)

LOOK = WorldLook(
    genre="crime", era="Naples, 1974: suits, Fiat 124s, smoke", tone="tense", setting="A family"
)


@pytest.mark.parametrize("kind", ["portrait", "place", "scene", "cover"])
def test_every_picture_has_the_house_style_and_the_mild_rules(kind):
    prompt = build_prompt(kind, Brief(description="A shootout in a bar.", look=LOOK))

    assert HOUSE_STYLE in prompt.system
    assert MILD_RULES in prompt.system
    assert FRAMING[kind] in prompt.user
    assert prompt.aspect_ratio == ASPECT_RATIOS[kind]


def test_the_rules_keep_pictures_mild_whatever_the_rating():
    """M6: no rating in the prompt at all, so a Mature story's picture is as mild as a Teen's."""
    assert "no nudity" in MILD_RULES
    assert "no gore" in MILD_RULES
    assert "child is never shown in a romantic or suggestive way" in MILD_RULES
    assert "No real people" in MILD_RULES


def test_pictures_are_drawn_in_the_worlds_era_and_look():
    prompt = build_prompt("scene", Brief(description="The don's funeral.", look=LOOK))

    assert "era and look: Naples, 1974: suits, Fiat 124s, smoke" in prompt.user
    assert "genre: crime" in prompt.user
    assert "world's own era and look" in prompt.system


def test_known_characters_go_along_with_their_appearance_and_reference_portraits():
    brief = Brief(
        description="Rosa confronts Tonio on the stairs.",
        figures=(
            Figure("rosa", "Rosa", "dark curls, a scar over one brow"),
            Figure("tonio", "Tonio", "grey suit, gold ring"),
        ),
    )

    prompt = build_prompt("scene", brief, references=["Rosa", "Tonio"])

    assert "People in it: Rosa: dark curls, a scar over one brow; Tonio: grey suit" in prompt.user
    assert "reference portraits of Rosa, Tonio, in that order" in prompt.user


def test_a_redraw_asks_for_the_same_person_as_they_look_now():
    brief = Brief(subject_name="Rosa", subject_appearance="an eyepatch over her left eye")

    prompt = build_prompt("portrait", brief, references=["Rosa"], redraw=True)

    assert "Subject: Rosa: an eyepatch over her left eye" in prompt.user
    assert "earlier portrait. Draw the same person" in prompt.user


def test_long_descriptions_are_cut_so_the_rules_stay_in_charge():
    prompt = build_prompt("scene", Brief(description="word " * 2000))

    described = prompt.user.split("What it shows: ", 1)[1]
    assert len(described) <= MAX_DESCRIPTION_CHARS
    assert described.endswith("…")


def test_a_brief_round_trips_through_json_and_tolerates_junk():
    brief = Brief(
        description="d",
        look=LOOK,
        subject_name="Rosa",
        subject_appearance="curls",
        figures=(Figure("rosa", "Rosa", "curls"),),
    )

    assert Brief.from_json(brief.to_json()) == brief
    assert Brief.from_json(None) == Brief()
    junk = {"look": {"era": None, "extra": 1}, "figures": [{}, {"name": "X"}]}
    assert Brief.from_json(junk) == Brief(figures=(Figure("", "X", ""),))


def test_unknown_kinds_are_refused_and_prompts_never_print():
    with pytest.raises(ValueError):
        build_prompt("selfie", Brief())

    prompt = build_prompt("scene", Brief(description="secret plot"))
    assert "secret plot" not in repr(prompt)
