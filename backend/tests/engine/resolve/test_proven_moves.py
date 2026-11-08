"""A move made with the character's own power is that power at work, and once it comes off cleanly
it is theirs for good (A4, G14, G25), so a technique proven in play never fails as one they
"never learned". From Miki's Spanish story, where an aura blade used several times kept fizzling.
"""

from engine.contracts import (
    Aim,
    Challenge,
    Intent,
    OutcomeClass,
    SheetPart,
    SheetUse,
)
from engine.samples import cultivation_world
from engine.state import (
    Character,
    CharacterSheet,
    CostKind,
    LadderPosition,
    Power,
    PowerAxes,
    PowerAxis,
    PowerCost,
    StepResult,
    Technique,
    WorldState,
)

from .power_worlds import play
from .worlds import SEEDS, add, facts, power, resolve, step

BLADE = "cuchilla de aura"


def technique(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.TECHNIQUE, ref=ref)


def awakened() -> WorldState:
    """Lin Feng with an awakened aura besides his time stop, as a Spanish story's sheet has it,
    and a thief of his own realm in the scene."""
    state = cultivation_world()
    state.player.sheet.powers.append(
        Power(
            id="aura",
            name="Aura del despertar",
            description="Un manantial interior de aura que puede moldear a voluntad.",
            costs=[PowerCost(kind=CostKind.ENERGY, text="Gasta aura.")],
        )
    )
    thief = Character(
        id="ladron",
        name="el ladrón",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2), ladders=[LadderPosition(ladder_id="realms", rung=0)]
        ),
    )
    return add(state, thief)


def cut_the_rope(*uses: SheetUse):
    """Nothing pushes back: the means settle it, and it comes off cleanly."""
    return step("cortar la cuerda con una cuchilla de aura", uses=list(uses))


def cut_the_thief(*uses: SheetUse):
    """A real contest with the thief, who can push back."""
    return step(
        "cortarle la mano al ladrón con una cuchilla de aura",
        verb="attack",
        aim=Aim.WOUND,
        target_ids=["ladron"],
        axis=PowerAxis.MIGHT,
        uses=list(uses),
        facts=facts(opposition_ids=["ladron"], can_respond=True, challenge=Challenge.MODERATE),
    )


def test_a_move_made_with_their_own_power_is_that_power_at_work():
    state = awakened()

    (settled,) = resolve(state, Intent(steps=[cut_the_rope(power("aura"), technique(BLADE))])).steps

    assert (settled.outcome_class, settled.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert settled.drew_on == ["Aura del despertar", "Cuchilla de aura"]
    assert [c.ref for c in settled.costs] == ["aura"]


def test_the_move_alone_finds_the_power_it_is_made_with():
    """The interpret step named only the move, in Spanish: it shares "aura" with the power."""
    state = awakened()

    (settled,) = resolve(
        state, Intent(steps=[cut_the_rope(technique("la cuchilla_de_aura"))])
    ).steps

    assert settled.result is StepResult.SUCCESS
    assert settled.drew_on == ["Aura del despertar", "Cuchilla de aura"]


def test_a_power_is_found_by_its_name_as_well_as_its_id():
    state = awakened()

    (settled,) = resolve(state, Intent(steps=[cut_the_rope(power("Aura del despertar"))])).steps

    assert settled.result is StepResult.SUCCESS
    assert settled.drew_on == ["Aura del despertar"]


def test_a_move_no_power_of_theirs_makes_was_never_learned():
    state = cultivation_world()  # only a time stop
    move = cut_the_rope(technique("Nine Suns Sword"))

    (settled,) = resolve(state, Intent(steps=[move])).steps

    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert settled.reason == "You never learned that technique."
    assert settled.drew_on == []


def test_a_power_over_time_is_never_found_by_a_word_in_common():
    """'Travel back in time' shares "time" with the time stop, which never makes it a stop."""
    state = cultivation_world()

    by_technique = resolve(state, Intent(steps=[cut_the_rope(technique("time travel"))]))
    by_power = resolve(state, Intent(steps=[cut_the_rope(power("time travel"))]))

    assert by_technique.steps[0].reason == "You never learned that technique."
    assert by_power.steps[0].reason == "You have no power like that."
    assert by_technique.steps[0].duration_s > 0  # the world never froze


def test_a_clean_success_makes_the_move_a_technique_of_their_own():
    state = awakened()

    played = play(state, Intent(steps=[cut_the_rope(power("aura"), technique(BLADE))]))

    (settled,) = played.resolution.steps
    assert settled.reason.endswith("Cuchilla de aura is a technique of yours now.")
    lin = played.state.player
    (learned,) = lin.sheet.techniques
    assert (learned.id, learned.name, learned.power_id) == (
        "technique-cuchilla-de-aura",
        "Cuchilla de aura",
        "aura",
    )
    assert learned.learned_from == "their own use"
    assert (lin.sheet.growth[-1].what, lin.sheet.growth[-1].change) == (
        "Cuchilla de aura",
        "learned",
    )

    # Next time it is on the sheet: a technique like any other, counted in the odds and never
    # recorded twice. Named by its id or in other words, it is the same technique.
    for ref in ("technique-cuchilla-de-aura", "la cuchilla de aura"):
        again = resolve(played.state, Intent(steps=[cut_the_thief(power("aura"), technique(ref))]))
        (fight,) = again.steps
        assert fight.outcome_class is OutcomeClass.CONTESTED
        assert "your Cuchilla de aura" in fight.reason
        assert "technique of yours now" not in fight.reason
        assert fight.drew_on == ["Aura del despertar", "Cuchilla de aura"]


def test_the_technique_counts_in_the_odds_once_learned():
    state = awakened()
    before = resolve(state, Intent(steps=[cut_the_thief(power("aura"), technique(BLADE))]))
    state.player.sheet.techniques.append(
        Technique(id="technique-cuchilla-de-aura", name="Cuchilla de aura", power_id="aura")
    )
    after = resolve(state, Intent(steps=[cut_the_thief(power("aura"), technique(BLADE))]))

    assert after.steps[0].roll.odds > before.steps[0].roll.odds


def test_only_a_clean_success_makes_it_theirs():
    state = awakened()
    misses = [
        resolve(state, Intent(steps=[cut_the_thief(power("aura"), technique(BLADE))]), seed)
        for seed in SEEDS
    ]
    for resolution in misses:
        (fight,) = resolution.steps
        learned = [c for c in fight.effects.characters if c.techniques]
        assert bool(learned) == (fight.result is StepResult.SUCCESS)
        # Win or lose, the aura blade forms: a miss is the thief's doing.
        assert fight.drew_on == ["Aura del despertar", "Cuchilla de aura"]
    assert {r.steps[0].result for r in misses} == set(StepResult)


def test_a_technique_someone_else_knows_is_learned_from_them_not_improvised():
    state = awakened()
    state.characters["ladron"].sheet.techniques.append(
        Technique(id="blade", name="Cuchilla de aura", learned_from="the Red Sect")
    )

    (settled,) = resolve(state, Intent(steps=[cut_the_rope(power("aura"), technique(BLADE))])).steps

    assert settled.result is StepResult.SUCCESS  # something like it, made with their own aura
    assert not any(c.techniques for c in settled.effects.characters)


def test_a_technique_of_a_power_uses_that_power_and_needs_it_ready():
    state = awakened()
    state.player.sheet.techniques.append(
        Technique(id="technique-cuchilla-de-aura", name="Cuchilla de aura", power_id="aura")
    )
    move = cut_the_rope(technique("technique-cuchilla-de-aura"))

    (used,) = resolve(state, Intent(steps=[move])).steps
    assert [c.ref for c in used.costs] == ["aura"]

    state.player.sheet.power("aura").ready_at_personal_s = 60
    (tired,) = resolve(state, Intent(steps=[move])).steps
    assert tired.reason == "Your Aura del despertar hasn't recovered yet."
    assert tired.drew_on == []  # it didn't work, and the narrator is told so by the reason


def test_a_move_that_only_says_what_the_power_does_is_the_power_itself():
    """'Teleport' for a power that teleports is no new technique, and is never recorded."""
    state = awakened()
    state.player.sheet.powers.append(
        Power(id="void-step", name="Void Step", description="Teleports her a mile.")
    )

    (settled,) = resolve(state, Intent(steps=[cut_the_rope(technique("teleport"))])).steps

    assert settled.result is StepResult.SUCCESS
    assert settled.drew_on == ["Void Step"]
    assert not any(c.techniques for c in settled.effects.characters)


def test_a_power_the_step_claims_is_never_taken_for_another_it_names():
    """Lightning isn't the aura just because the step names the aura too."""
    state = awakened()
    move = cut_the_rope(power("aura"), power("lightning"))

    (settled,) = resolve(state, Intent(steps=[move])).steps

    assert settled.reason == "You have no power like that."
