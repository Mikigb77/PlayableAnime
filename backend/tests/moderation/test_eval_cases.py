"""T15's content-line cases are complete, well formed, and their deterministic ones hold today."""

from collections import Counter

import pytest

from engine import limits
from engine.invariants import check_state
from moderation.evals import TABLE_THEMES, build_world, judge_instructions, load_cases

CASES = load_cases()
DETERMINISTIC = [case for case in CASES if case.deterministic]


def test_case_ids_are_unique():
    counts = Counter(case.id for case in CASES)
    assert [name for name, n in counts.items() if n > 1] == []


def test_every_line_of_the_ratings_table_is_covered_in_both_ratings():
    covered = {(case.theme, case.rating.value) for case in CASES}
    for theme in TABLE_THEMES:
        assert (theme, "teen") in covered, theme
        assert (theme, "mature") in covered, theme


def test_a_grounded_story_and_mild_pictures_are_covered():
    # Apple 1.1.2 bites hardest on grounded violence, so T15 includes a grounded story (F2).
    assert any(case.world == "grounded" and case.theme == "violence_and_gore" for case in CASES)
    pictured = {case.theme for case in CASES if case.expect.picture}
    assert {"violence_and_gore", "romance_and_sex"} <= pictured


def test_every_hard_limit_has_a_case():
    expected = {category for category in limits.LimitCategory}
    covered = {case.expect.limit for case in DETERMINISTIC}
    # Instructions are caught in the narration, so their cases are live.
    assert covered == expected - {limits.LimitCategory.HARM_INSTRUCTIONS}
    assert any("harm-instructions" in case.id for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_a_case_is_well_formed(case):
    assert case.script and case.requirements and "T15" in case.requirements
    if case.deterministic:
        assert len(case.interpretation) == len(case.script)
        assert not case.expect.must and not case.expect.narration_mode
    else:
        assert case.expect.must and case.expect.narration_mode
        assert "template" not in case.expect.narration_mode
    if case.world == "premise":
        assert case.premise and build_world(case) is None
    else:
        world = build_world(case)
        assert check_state(world) == []


@pytest.mark.parametrize("case", DETERMINISTIC, ids=lambda case: case.id)
def test_a_deterministic_case_is_refused_by_the_engine(case):
    world = build_world(case)
    [intent] = case.interpretation
    hits = limits.check_action(world, intent, case.rating, case.language)
    assert limits.gravest(hits).category is case.expect.limit


def test_the_judge_has_instructions_for_scenes_and_pictures():
    instructions = judge_instructions()
    assert instructions["instructions"] and instructions["picture_instructions"]
