"""R2's beat check, G8's world rules and G14's sheet check, all settled in code before anyone
pushes back."""

from engine.contracts import (
    ActionKind,
    Beat,
    BeatUse,
    BeatVerdict,
    Intent,
    OutcomeClass,
    Plausibility,
    SheetPart,
    SheetUse,
    StopReason,
    UseSource,
)
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    CharacterStatus,
    DeathCertainty,
    Item,
    ItemKind,
    StepResult,
    Technique,
)

from .worlds import SEEDS, facts, power, resolve, step


def throw(thing: str, source: UseSource, plausibility: Plausibility | None = None, **kw):
    beats = [
        Beat(text="feel along the floor"),
        Beat(
            text=f"take {thing}",
            uses=[BeatUse(source=source, thing=thing, plausibility=plausibility, **kw)],
        ),
    ]
    return step("throw it at Zhao", beats=beats)


def test_something_the_place_plausibly_holds_becomes_canon():
    state = cultivation_world()
    intent = Intent(
        steps=[throw("a stone the size of an egg", UseSource.NEW, Plausibility.PLAUSIBLE)]
    )

    resolution = resolve(state, intent)

    (check,) = resolution.steps[0].beats
    assert check.verdict is BeatVerdict.MADE_CANON
    assert check.reason == "There is a stone the size of an egg here."
    assert resolution.canon == ["a stone the size of an egg"]
    assert resolution.steps[0].result is StepResult.SUCCESS


def test_something_the_place_cant_hold_is_an_empty_search_and_the_plan_stops():
    state = cultivation_world()
    intent = Intent(
        steps=[
            throw("a loaded crossbow", UseSource.NEW, Plausibility.ABSENT),
            step("run for the gate", ActionKind.MOVE, 20),
        ]
    )

    resolution = resolve(state, intent)

    (settled,) = resolution.steps
    assert (settled.outcome_class, settled.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert settled.roll is None
    assert settled.reason == "There is no loaded crossbow to be found here."
    assert resolution.unplayed == ["run for the gate"]
    assert resolution.stop_reason is StopReason.RULED_OUT
    assert resolution.canon == []


def test_an_uncertain_find_is_rolled_and_a_miss_stops_the_step():
    state = cultivation_world()
    intent = Intent(steps=[throw("a loose brick", UseSource.NEW, Plausibility.UNCERTAIN)])

    steps = [resolve(state, intent, seed).steps[0] for seed in SEEDS]

    found = [s for s in steps if s.beats[0].verdict is BeatVerdict.MADE_CANON]
    missed = [s for s in steps if s.beats[0].verdict is BeatVerdict.EMPTY]
    assert found and missed
    assert all(s.beats[0].roll is not None for s in steps)
    assert all(s.result is StepResult.SUCCESS and s.roll is None for s in found)
    assert all(
        (s.outcome_class, s.result) == (OutcomeClass.CONTESTED, StepResult.FAILURE) for s in missed
    )
    assert all(s.roll is s.beats[0].roll or s.roll == s.beats[0].roll for s in missed)


def test_a_claim_that_the_scene_holds_something_it_doesnt_is_judged_as_new():
    state = grounded_world()
    held = Intent(steps=[throw("the bottle of grappa", UseSource.SCENE)])
    not_held = Intent(steps=[throw("a shotgun", UseSource.SCENE)])

    assert resolve(state, held).steps[0].beats[0].verdict is BeatVerdict.HOLDS
    rolled = {resolve(state, not_held, seed).steps[0].beats[0].roll is not None for seed in SEEDS}
    assert rolled == {True}


def test_canon_from_an_earlier_beat_this_turn_holds_and_unsupported_canon_does_not():
    state = cultivation_world()
    beats = [
        Beat(
            text="pull a stone from the rim",
            uses=[BeatUse(source=UseSource.NEW, thing="a loose stone", plausibility="plausible")],
        ),
        Beat(text="throw it", uses=[BeatUse(source=UseSource.CANON, thing="the loose stone")]),
    ]
    resolution = resolve(state, Intent(steps=[step("throw a stone", beats=beats)]))
    assert [b.verdict for b in resolution.steps[0].beats] == [
        BeatVerdict.MADE_CANON,
        BeatVerdict.HOLDS,
    ]

    lone = Intent(steps=[throw("the silver key", UseSource.CANON)])
    assert resolve(state, lone).steps[0].beats[0].roll is not None


def test_what_the_character_carries_is_checked_against_the_sheet():
    state = grounded_world()
    state.player.sheet.resources.items.append(
        Item(id="ledger", name="family ledger", kind=ItemKind.DOCUMENT, carried=False)
    )

    def use(thing: str, **kw):
        return resolve(state, Intent(steps=[throw(thing, UseSource.CARRIED, **kw)])).steps[0]

    assert use("my pistol").beats[0].verdict is BeatVerdict.HOLDS
    assert use("my shotgun").reason == "You have no shotgun on you."
    assert use("the ledger").reason == "Your family ledger isn't on you."
    assert use("the old ledger", ref="ledger").result is StepResult.FAILURE
    # A car or a house is used where it stands.
    assert use("the Alfa", ref="car").beats[0].verdict is BeatVerdict.HOLDS


def test_a_fireball_in_a_grounded_world_is_ruled_out_whatever_the_model_proposed():
    state = grounded_world()
    fireball = step(
        "throw a fireball at Carmine",
        verb="attack",
        target_ids=["carmine"],
        uses=[SheetUse(part=SheetPart.POWER, ref="fireball")],
        facts=facts(world_allows=True, proposed_class=OutcomeClass.CERTAIN),
    )

    for actor in (None, "carmine"):  # NPCs get no powers the world lacks either (G8)
        target = "luca" if actor else "carmine"
        intent = Intent(
            actor_id=actor, steps=[fireball.model_copy(update={"target_ids": [target]})]
        )
        (settled,) = resolve(state, intent).steps
        assert (settled.outcome_class, settled.result) == (
            OutcomeClass.RULED_OUT,
            StepResult.FAILURE,
        )
        assert settled.roll is None
        assert settled.reason == (
            "Grounded: no magic and nothing supernatural, and that won't change."
        )
        assert settled.effects.empty and settled.deeds == []


def test_a_step_against_a_world_rule_names_the_rule_and_unknown_rules_are_ignored():
    state = grounded_world()
    against = step("fly over the bay", facts=facts(against_rule_ids=["human-limits", "made-up"]))
    unknown = step("walk to the door", facts=facts(against_rule_ids=["made-up"]))
    forbidden = step("read Carmine's mind", facts=facts(world_allows=False))

    assert resolve(state, Intent(steps=[against])).steps[0].reason == (
        "Nobody can do more than a real person could."
    )
    assert resolve(state, Intent(steps=[unknown])).steps[0].result is StepResult.SUCCESS
    assert resolve(state, Intent(steps=[forbidden])).steps[0].outcome_class is (
        OutcomeClass.RULED_OUT
    )


def test_a_power_must_be_on_the_sheet_and_ready():
    state = cultivation_world()
    missing = step("call down lightning", uses=[power("lightning")])
    assert resolve(state, Intent(steps=[missing])).steps[0].reason == (
        "You have no power like that."
    )

    state.player.sheet.powers[0].ready_at_personal_s = 5
    tired = resolve(state, Intent(steps=[step("stop time", uses=[power("time-stop")])])).steps[0]
    assert tired.reason == "Your time stop hasn't recovered yet."
    assert tired.costs == []


def test_a_power_used_pays_its_costs():
    state = cultivation_world()
    used = resolve(state, Intent(steps=[step("stop time", uses=[power("time-stop")])])).steps[0]

    assert [(c.kind.value, c.ref) for c in used.costs] == [("fatigue", "time-stop")]


def test_a_technique_must_have_been_learned():
    state = cultivation_world()
    move = step(
        "use the Nine Suns Sword",
        uses=[SheetUse(part=SheetPart.TECHNIQUE, ref="nine-suns")],
    )
    assert resolve(state, Intent(steps=[move])).steps[0].reason == (
        "You never learned that technique."
    )

    state.player.sheet.techniques.append(Technique(id="nine-suns", name="Nine Suns Sword"))
    assert resolve(state, Intent(steps=[move])).steps[0].result is StepResult.SUCCESS


def test_the_dead_do_nothing():
    state = grounded_world()
    carmine = state.characters["carmine"]
    carmine.status, carmine.death_certainty = CharacterStatus.DEAD, DeathCertainty.CONFIRMED

    (settled,) = resolve(state, Intent(actor_id="carmine", steps=[step("leave")])).steps

    assert settled.outcome_class is OutcomeClass.RULED_OUT
    assert settled.reason == "Carmine Russo is dead."
