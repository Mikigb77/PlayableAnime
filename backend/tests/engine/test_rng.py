import statistics

import pytest

from engine.rng import SeededRng


def draws(rng: SeededRng, n: int = 5) -> list[float]:
    return [rng.random() for _ in range(n)]


def test_the_same_seed_gives_the_same_numbers():
    assert draws(SeededRng("s")) == draws(SeededRng("s"))


def test_known_values_never_change_across_versions():
    # A recorded seed must replay its roll exactly, on any machine and any Python version (A3).
    # If this fails, old scenes' rolls no longer replay: don't change the generator.
    rng = SeededRng("story=s1/timeline=main/turn=1")

    assert rng.random() == 0.8866360731328866
    assert rng.randint(1, 100) == 23


def test_turn_seeds_are_readable_and_escape_separators():
    rng = SeededRng.for_turn("a/b", "main", 12)

    assert rng.seed == "story=a%2Fb/timeline=main/turn=12"
    assert (
        rng.child("resolve", "step", 0).seed == "story=a%2Fb/timeline=main/turn=12/resolve/step/0"
    )
    assert (
        SeededRng.for_turn("a", "b/turn=1", 2).seed != SeededRng.for_turn("a/b", "turn=1", 2).seed
    )


def test_children_depend_on_labels_not_on_draws_made_before():
    parent = SeededRng("s")
    before = parent.child("step", 1)
    parent.random()
    after = parent.child("step", 1)

    assert draws(before) == draws(after)
    assert draws(SeededRng("s").child("step", 1)) != draws(SeededRng("s").child("step", 2))


def test_turns_stories_and_timelines_get_different_streams():
    base = draws(SeededRng.for_turn("s", "main", 1))

    assert draws(SeededRng.for_turn("s", "main", 2)) != base
    assert draws(SeededRng.for_turn("t", "main", 1)) != base
    assert draws(SeededRng.for_turn("s", "rewound", 1)) != base


def test_random_is_uniform_enough():
    values = draws(SeededRng("uniform"), 20_000)

    assert all(0.0 <= v < 1.0 for v in values)
    assert statistics.fmean(values) == pytest.approx(0.5, abs=0.01)
    assert sum(v < 0.1 for v in values) / len(values) == pytest.approx(0.1, abs=0.01)


def test_chance_matches_its_probability():
    rng = SeededRng("chance")

    hits = sum(rng.chance(0.3) for _ in range(20_000))

    assert hits / 20_000 == pytest.approx(0.3, abs=0.015)
    assert not any(SeededRng("never").chance(0.0) for _ in range(1000))
    assert all(SeededRng("always").chance(1.0) for _ in range(1000))


def test_integers_stay_in_range_and_cover_it():
    rng = SeededRng("ints")

    values = [rng.randint(1, 6) for _ in range(6000)]

    assert set(values) == {1, 2, 3, 4, 5, 6}
    assert all(abs(values.count(face) - 1000) < 120 for face in range(1, 7))
    assert rng.randint(5, 5) == 5
    with pytest.raises(ValueError):
        rng.randint(2, 1)
    with pytest.raises(ValueError):
        rng.below(0)


def test_weighted_choice_follows_weights_and_never_picks_zero():
    rng = SeededRng("weighted")

    picks = [rng.weighted(["a", "b", "c"], [3, 1, 0]) for _ in range(8000)]

    assert "c" not in picks
    assert picks.count("a") / len(picks) == pytest.approx(0.75, abs=0.02)
    with pytest.raises(ValueError):
        rng.weighted(["a"], [0])
    with pytest.raises(ValueError):
        rng.weighted(["a", "b"], [1])


def test_log_uniform_spreads_over_orders_of_magnitude():
    rng = SeededRng("trap")

    values = [rng.log_uniform(60, 7 * 86_400) for _ in range(4000)]

    assert all(60 <= v <= 7 * 86_400 for v in values)
    assert sum(v < 3600 for v in values) > 1000  # minutes are common
    assert sum(v > 86_400 for v in values) > 500  # and so are days


def test_choice_and_shuffle_are_deterministic():
    items = list(range(10))

    assert SeededRng("x").shuffled(items) == SeededRng("x").shuffled(items)
    assert sorted(SeededRng("x").shuffled(items)) == items
    assert SeededRng("x").choice(items) == SeededRng("x").choice(items)
    with pytest.raises(ValueError):
        SeededRng("x").choice([])


def test_seeds_and_labels_must_not_be_empty():
    with pytest.raises(ValueError):
        SeededRng("")
    with pytest.raises(ValueError):
        SeededRng("s").child()
