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

    assert (
        "How the people in it look: Rosa: dark curls, a scar over one brow; Tonio: grey suit"
        in (prompt.user)
    )
    # M5: each image is labelled with whose it is, and used only for the face, not the pose,
    # framing, background or light of the portrait.
    assert prompt.labels == ("Image 1: the portrait of Rosa.", "Image 2: the portrait of Tonio.")
    assert "only for that person's face, hair, build and colouring" in prompt.user
    assert "not from the portrait" in prompt.user


def test_the_moment_comes_before_the_people_and_the_world():
    brief = Brief(
        description="Rosa confronts Tonio on the stairs.",
        look=LOOK,
        figures=(Figure("rosa", "Rosa", "dark curls"),),
    )

    user = build_prompt("scene", brief).user

    moment, people, world = (
        user.index("What it shows:"),
        user.index("How the people in it look:"),
        user.index("World:"),
    )
    assert moment < people < world


def test_only_a_cover_carries_the_premise():
    """The premise tells how the story began, not the scene a picture shows."""
    for kind in ("portrait", "place", "scene"):
        assert "A family" not in build_prompt(kind, Brief(look=LOOK)).user
    assert "setting: A family" in build_prompt("cover", Brief(look=LOOK)).user


def test_a_scene_is_lit_for_its_time_of_day():
    brief = Brief(description="The don's funeral.", time="dusk")

    assert "Time of day: dusk." in build_prompt("scene", brief).user
    # A portrait or place is reused at any hour, so it keeps the house light.
    assert "Time of day" not in build_prompt("place", brief).user
    assert "low-key" not in HOUSE_STYLE and "time of day" in HOUSE_STYLE


def test_the_description_is_told_who_you_is():
    said = Brief(description="Tonio hands you the envelope.", you="Rosa")
    unsaid = Brief(description="Tonio counts the money.", you="Rosa")

    assert '"You" in the description is Rosa.' in build_prompt("scene", said).user
    assert '"You" in the description is Rosa.' in build_prompt("cover", said).user
    assert '"You"' not in build_prompt("scene", unsaid).user
    assert '"You"' not in build_prompt("portrait", said).user


def test_a_portrait_takes_only_its_expression_from_the_moment():
    """M5: the portrait is every later picture's reference, so rain, blood or a drawn sword in
    the scene it was drawn in must not carry over."""
    brief = Brief(
        description="Rosa steps out of the rain, a bloody knife in hand.",
        subject_name="Rosa",
        subject_appearance="dark curls",
    )

    user = build_prompt("portrait", brief).user

    assert "for their expression only" in user
    assert "What it shows" not in user
    assert "calm pose" in FRAMING["portrait"]


def test_a_scene_shows_what_its_description_says_and_nothing_more():
    assert "no extra people, creatures or props" in FRAMING["scene"]
    assert "highest tension" not in FRAMING["scene"]


def test_a_redraw_asks_for_the_same_person_as_they_look_now():
    brief = Brief(subject_name="Rosa", subject_appearance="an eyepatch over her left eye")

    prompt = build_prompt("portrait", brief, references=["Rosa"], redraw=True)

    assert "Subject: Rosa: an eyepatch over her left eye" in prompt.user
    assert "earlier portrait. Draw the same person" in prompt.user
    assert prompt.labels == ("Image 1: the earlier portrait of Rosa.",)


def test_a_changed_place_is_asked_for_as_the_same_place_as_it_is_now():
    brief = Brief(subject_name="The Inn", subject_appearance="Two storeys. It is ruined now.")

    prompt = build_prompt("place", brief, references=["The Inn"], redraw=True)

    assert "Subject: The Inn: Two storeys. It is ruined now." in prompt.user
    assert "this place's earlier picture. Draw the same place" in prompt.user
    assert "same person" not in prompt.user
    assert prompt.labels == ("Image 1: the earlier picture of The Inn.",)


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
        you="Rosa",
        time="dusk",
    )

    assert Brief.from_json(brief.to_json()) == brief
    assert Brief.from_json(None) == Brief()
    # A brief stored before "you" and the time of day existed still reads.
    older = {k: v for k, v in brief.to_json().items() if k not in ("you", "time")}
    assert Brief.from_json(older) == Brief(
        description="d", look=LOOK, subject_name="Rosa", subject_appearance="curls",
        figures=(Figure("rosa", "Rosa", "curls"),),
    )  # fmt: skip
    junk = {"look": {"era": None, "extra": 1}, "figures": [{}, {"name": "X"}]}
    assert Brief.from_json(junk) == Brief(figures=(Figure("", "X", ""),))


def test_unknown_kinds_are_refused_and_prompts_never_print():
    with pytest.raises(ValueError):
        build_prompt("selfie", Brief())

    prompt = build_prompt("scene", Brief(description="secret plot"))
    assert "secret plot" not in repr(prompt)
