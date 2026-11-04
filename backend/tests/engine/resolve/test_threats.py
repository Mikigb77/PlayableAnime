"""Threats backed by what the actor can do (W5, A8, gap 8 of the evals).

An intimidation from someone whose might, as the world can know it, is above their standing is
measured by that might, against the target's own might or standing, whichever is higher. So a
known light-speed thrower's threat lands on a king, a secret one's doesn't, and a target as
strong as the threat isn't cowed by it.
"""

from engine.contracts import Intent, OutcomeClass
from engine.state import HitMode, PowerAxis, StepResult

from .power_worlds import lin_power, with_hit_mode
from .worlds import facts, resolve, sect, step


def threaten(target: str = "zhao", verb: str = "threaten"):
    return step(
        "tell Zhao to kneel or die",
        verb=verb,
        target_ids=[target],
        axis=PowerAxis.INFLUENCE,
        facts=facts(opposition_ids=[target], can_respond=True),
    )


def thrower(*, known: bool):
    """Lin, whose stopped-time throws land at the speed of light, before Zhao, who stands far
    above him in the sect."""
    state = with_hit_mode(sect(), HitMode.RELATIVE_SPEED)
    lin_power(state).secret = not known
    state.characters["zhao"].sheet.axes.influence = 8
    return state


def test_a_known_light_speed_thrower_s_threat_lands_with_no_roll():
    (threat,) = resolve(thrower(known=True), Intent(steps=[threaten()])).steps

    assert threat.outcome_class is OutcomeClass.CERTAIN
    assert threat.result is StepResult.SUCCESS and threat.roll is None
    assert "knowing what you can do" in threat.reason


def test_a_secret_power_backs_no_threat():
    (threat,) = resolve(thrower(known=False), Intent(steps=[threaten()])).steps

    assert threat.outcome_class is not OutcomeClass.CERTAIN
    assert "knowing what you can do" not in threat.reason


def test_only_an_intimidation_leans_on_might():
    persuade = threaten(verb="persuade")
    (asked,) = resolve(thrower(known=True), Intent(steps=[persuade])).steps

    assert asked.outcome_class is not OutcomeClass.CERTAIN
    assert "knowing what you can do" not in asked.reason


def test_a_target_as_strong_as_the_threat_withstands_it():
    state = thrower(known=True)
    zhao = state.characters["zhao"]
    zhao.sheet.axes.might = 20  # nothing a pebble can do frightens him

    (threat,) = resolve(state, Intent(steps=[threaten()])).steps

    assert threat.outcome_class is not OutcomeClass.CERTAIN
    assert "knowing what you can do" in threat.reason


def test_a_brute_s_threat_rests_on_force_and_a_favourite_s_on_standing():
    """A fighter with no standing frightens a merchant who outranks him; the sect master's
    favourite, who can't fight, is measured by standing as before."""
    brute = sect()
    zhao = brute.characters["zhao"]
    zhao.sheet.axes.might, zhao.sheet.axes.influence = 1, 3
    brute.characters["lin"].sheet.axes.might = 9
    (forced,) = resolve(brute, Intent(steps=[threaten()])).steps

    favourite = sect()
    favourite.characters["lin"].sheet.axes.influence = 6
    (asked,) = resolve(favourite, Intent(steps=[threaten()])).steps

    assert forced.outcome_class is OutcomeClass.CERTAIN
    assert "knowing what you can do" not in forced.reason
    # Measured on standing, his six against Zhao's two, not on his might of two.
    assert asked.outcome_class is OutcomeClass.CERTAIN
    assert "Foundation Establishment" not in asked.reason


def test_a_weakened_brute_threatens_with_what_he_has_left():
    """Weakening counts once (A8): a fighter of ten, weakened by two, threatens as an eight,
    which still towers over a merchant of four."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.axes.might = 10
    lin.sheet.condition.weakened_tiers = 2
    zhao = state.characters["zhao"]
    zhao.sheet.axes.might, zhao.sheet.axes.influence = 1, 4

    (threat,) = resolve(state, Intent(steps=[threaten()])).steps

    assert threat.outcome_class is OutcomeClass.CERTAIN


def test_a_threat_rests_on_the_rung_the_actor_stands_on():
    """G18: a cultivator at Soul Transformation threatens as one, whatever the sheet's own
    might says."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders[0].rung = 4
    lin.sheet.axes.might = 2
    zhao = state.characters["zhao"]
    zhao.sheet.axes.might, zhao.sheet.axes.influence = 1, 4

    (threat,) = resolve(state, Intent(steps=[threaten()])).steps

    assert threat.outcome_class is OutcomeClass.CERTAIN
    assert "Soul Transformation" in threat.reason


def test_hidden_strength_threatens_only_as_much_as_it_shows():
    """A threat frightens by what others believe (G20): Lin at Soul Transformation, showing Qi
    Condensation, threatens like the outer disciple he seems."""

    def hiding(shown: int | None):
        state = sect()
        lin = state.characters["lin"]
        lin.sheet.ladders[0].rung = 4
        lin.sheet.ladders[0].shown_rung = shown
        lin.sheet.axes.might = 10
        state.characters["zhao"].sheet.axes.influence = 3
        (threat,) = resolve(state, Intent(steps=[threaten()])).steps
        return threat

    shown = hiding(None)
    hidden = hiding(0)

    assert shown.outcome_class is OutcomeClass.CERTAIN
    assert hidden.outcome_class is not OutcomeClass.CERTAIN
