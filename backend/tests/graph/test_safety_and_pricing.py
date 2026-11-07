from decimal import Decimal

import pytest

from graph.llm.pricing import FALLBACK_PRICE, estimate_cost, price_for
from graph.llm.safety import HARM_CATEGORIES, THRESHOLDS, safety_settings
from graph.llm.types import Usage


@pytest.mark.parametrize("rating", ["teen", "mature"])
@pytest.mark.parametrize("picture", [False, True])
def test_every_category_gets_a_known_threshold(rating, picture):
    settings = safety_settings(rating, picture=picture)

    assert set(settings) == set(HARM_CATEGORIES)
    assert set(settings.values()) <= set(THRESHOLDS)


def test_mature_is_never_stricter_than_teen_and_pictures_never_looser_than_text():
    strictness = {name: rank for rank, name in enumerate(THRESHOLDS)}
    teen, mature = safety_settings("teen"), safety_settings("mature")
    pictures = safety_settings("mature", picture=True)

    for category in HARM_CATEGORIES:
        assert strictness[mature[category]] <= strictness[teen[category]]
        assert strictness[pictures[category]] >= strictness[teen[category]]


def test_backstops_hold_in_every_rating():
    # F3 and Google's policy: real-world harm instructions and explicit sex are filtered even in
    # Mature, at the most permissive level that still filters, for every node that writes text
    # without a code check behind it.
    for rating in ("teen", "mature"):
        settings = safety_settings(rating)
        assert settings["dangerous_content"] != "off"
        assert settings["sexually_explicit"] != "off"
        assert safety_settings(rating, node="drafter")["dangerous_content"] != "off"
    assert safety_settings("teen", node="narrator")["dangerous_content"] != "off"
    assert safety_settings("mature", node="narrator")["sexually_explicit"] != "off"


def test_mature_interpret_reads_the_action_with_the_text_filters_off():
    # F4: a blocked interpret step is the one block that stops the deed itself.
    interpret = safety_settings("mature", node="interpret")
    narrator = safety_settings("mature", node="narrator")
    strictness = {name: rank for rank, name in enumerate(THRESHOLDS)}

    assert set(interpret.values()) == {"off"}
    for category in HARM_CATEGORIES:
        assert strictness[interpret[category]] <= strictness[narrator[category]]
    # Pictures stay mild whoever draws them.
    assert safety_settings("mature", picture=True, node="interpret") == safety_settings(
        "mature", picture=True
    )


def test_a_characters_own_death_is_readable_in_every_rating():
    # Gemini files self-harm under dangerous content: "I stab myself" was blocked at the
    # interpret step on 2026-11-05, so the deed never happened (F1, F4).
    for rating in ("teen", "mature"):
        interpret = safety_settings(rating, node="interpret")
        assert interpret["dangerous_content"] == "off"
    # Teen keeps the narrator's other lines.
    teen = safety_settings("teen")
    teen_interpret = safety_settings("teen", node="interpret")
    assert {k: v for k, v in teen_interpret.items() if k != "dangerous_content"} == {
        k: v for k, v in teen.items() if k != "dangerous_content"
    }


def test_mature_tells_a_chosen_death_and_teen_cuts_away_from_it():
    # F1, Miki 2026-11-05: in Mature the narrator tells it; code holds F3's line on instructions
    # there (engine.limits.harm_instructions). Teen keeps the filter, so a blocked telling becomes
    # a cut-away (F4).
    assert safety_settings("mature", node="narrator")["dangerous_content"] == "off"
    assert safety_settings("teen", node="narrator")["dangerous_content"] == "block_only_high"


@pytest.mark.parametrize("rating", ["teen", "mature"])
def test_a_chapter_summary_is_never_blocked_for_a_death_already_told(rating):
    # C3: a summary only retells scenes already told, and a blocked one would be asked for again
    # every turn. Code drops one that reads as instructions (F3).
    summarizer = safety_settings(rating, node="summarizer")
    assert summarizer["dangerous_content"] == "off"
    others = {k: v for k, v in summarizer.items() if k != "dangerous_content"}
    assert others == {k: v for k, v in safety_settings(rating).items() if k != "dangerous_content"}


@pytest.mark.parametrize("rating", ["teen", "mature"])
@pytest.mark.parametrize("node", [None, "interpret", "narrator", "summarizer"])
@pytest.mark.parametrize("picture", [False, True])
def test_every_setting_is_one_gemini_accepts(rating, node, picture):
    from google.genai.types import HarmBlockThreshold

    from graph.llm.gemini import to_safety_settings

    settings = to_safety_settings(safety_settings(rating, node=node, picture=picture))

    assert len(settings) == len(HARM_CATEGORIES)
    # BLOCK_NONE is restricted to approved projects, so it is never used.
    assert HarmBlockThreshold.BLOCK_NONE not in settings.values()


def test_an_unknown_rating_is_refused():
    with pytest.raises(ValueError):
        safety_settings("adult")  # type: ignore[arg-type]


def test_a_typical_narrated_turn_costs_about_two_cents():
    # REQUIREMENTS.md's estimate: about 8,000 tokens in and under 1,000 out on Gemini 3.5 Flash.
    cost, known = estimate_cost("gemini-3.5-flash", Usage(8000, 1000))

    assert known
    assert cost == Decimal("0.021")


def test_thinking_tokens_bill_as_output():
    with_thinking, _ = estimate_cost("gemini-3.5-flash", Usage(0, 1000, thinking_tokens=600))
    without, _ = estimate_cost("gemini-3.5-flash", Usage(0, 1000))

    assert with_thinking == without


def test_cached_prompt_tokens_bill_at_a_tenth_of_the_input_price():
    # A narrator prompt of 14,000 tokens whose first 9,000 Gemini had just seen.
    cached, _ = estimate_cost("gemini-3.5-flash", Usage(14000, 0, cached_tokens=9000))

    assert cached == Decimal("0.00885")  # 5,000 at $1.50 and 9,000 at $0.15 per million


def test_a_model_without_a_cached_rate_bills_cached_tokens_as_input():
    cached, _ = estimate_cost("gemini-3.5-transcribe", Usage(1000, 0, cached_tokens=1000))
    plain, _ = estimate_cost("gemini-3.5-transcribe", Usage(1000, 0))

    assert cached == plain


def test_cached_tokens_never_count_for_more_than_the_prompt():
    odd, _ = estimate_cost("gemini-3.5-flash", Usage(1000, 0, cached_tokens=5000))
    all_cached, _ = estimate_cost("gemini-3.5-flash", Usage(1000, 0, cached_tokens=1000))

    assert odd == all_cached


def test_a_1k_picture_costs_about_three_cents_and_bigger_ones_more():
    one_k, known = estimate_cost("gemini-3.1-flash-lite-image", Usage(1120, 1120), images=1)
    four_k, _ = estimate_cost("gemini-3.1-flash-lite-image", Usage(1120, 2520), images=1)

    assert known
    assert one_k == Decimal("0.00028") + Decimal("0.0336")
    assert four_k > one_k


def test_nano_banana_2_1_costs_the_same_at_1k_with_dearer_references():
    """M8: the model T18's side-by-side weighs against today's, priced so its runs are known."""
    lite, _ = estimate_cost("gemini-3.1-flash-lite-image", Usage(2240, 1120), images=1)
    banana, known = estimate_cost("gemini-nano-banana-2.1", Usage(2240, 1120), images=1)

    assert known
    assert banana == Decimal("0.00336") + Decimal("0.0336")  # a reference portrait in, 1K out
    assert banana - lite < Decimal("0.003")


def test_a_picture_never_costs_less_than_1k_even_without_usage():
    cost, _ = estimate_cost("gemini-3.1-flash-lite-image", Usage(), images=2)

    assert cost == 2 * Decimal("0.0336")


def test_a_text_price_is_never_used_for_a_picture():
    cost, known = estimate_cost("gemini-3.5-flash", Usage(0, 1120), images=1)

    assert not known
    assert cost == Decimal(1120) * FALLBACK_PRICE.image_output_per_m / Decimal(1_000_000)


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("gemini-3.5-flash-001", "gemini-3.5-flash"),
        ("gemini-3.5-flash-preview-09-2026", "gemini-3.5-flash"),
        ("gemini-3.5-flash-lite-preview", "gemini-3.5-flash-lite"),
        ("gemini-3.1-flash-lite-image-latest", "gemini-3.1-flash-lite-image"),
    ],
)
def test_versioned_ids_match_their_family(model, family):
    assert price_for(model) == (price_for(family)[0], True)


@pytest.mark.parametrize("model", ["gemini-3.5-flash-image", "gemini-3.5-flashy", "gemini-9-ultra"])
def test_other_models_that_only_start_the_same_are_unknown(model):
    assert price_for(model) == (FALLBACK_PRICE, False)


def test_regional_endpoints_cost_ten_percent_more():
    usage = Usage(1_000_000, 0)

    assert estimate_cost("gemini-3.5-flash", usage, location="europe-west3")[0] == Decimal("1.65")
