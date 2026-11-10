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


def test_a_thing_nobody_judged_is_there_whatever_source_it_was_filed_under():
    """Decided 2026-11-10 (Miki): nothing natural fails for no reason. The scene's record is
    never the whole scene, so a judgement left out never rolls and never fails a step."""
    for source in (UseSource.NEW, UseSource.SCENE, UseSource.CANON):
        state = cultivation_world()
        intent = Intent(steps=[throw("a fallen branch", source)])

        steps = [resolve(state, intent, seed).steps[0] for seed in SEEDS[:40]]

        assert {(s.beats[0].verdict, s.beats[0].roll) for s in steps} == {
            (BeatVerdict.MADE_CANON, None)
        }
        assert steps[0].beats[0].reason == "There is a fallen branch here."
        assert {s.result for s in steps} == {StepResult.SUCCESS}


def test_a_claim_that_the_scene_holds_something_is_checked_against_its_record_first():
    state = grounded_world()
    held = Intent(steps=[throw("the bottle of grappa", UseSource.SCENE)])
    doubted = Intent(steps=[throw("a shotgun", UseSource.SCENE, Plausibility.UNCERTAIN)])
    denied = Intent(steps=[throw("a shotgun", UseSource.SCENE, Plausibility.ABSENT)])

    assert resolve(state, held).steps[0].beats[0].verdict is BeatVerdict.HOLDS
    # Not on record: the claim is judged like anything new.
    rolled = {resolve(state, doubted, seed).steps[0].beats[0].roll is not None for seed in SEEDS}
    assert rolled == {True}
    assert resolve(state, denied).steps[0].reason == "There is no shotgun to be found here."


def test_naming_something_the_scene_holds_doesnt_make_what_is_beside_it_real():
    state = grounded_world()
    knife = "the knife Gennaro keeps under the counter"
    claim = Intent(steps=[throw(knife, UseSource.SCENE, Plausibility.UNCERTAIN)])

    checks = [resolve(state, claim, seed).steps[0].beats[0] for seed in SEEDS]

    assert all(c.roll is not None for c in checks)
    assert {c.verdict for c in checks} == {BeatVerdict.MADE_CANON, BeatVerdict.EMPTY}


def test_what_the_scene_records_is_there_whatever_source_it_was_filed_under():
    """R2, R3: nothing on the scene's record is ever rolled for, however the interpret step
    filed it and whatever it doubted."""
    state = grounded_world()  # a telephone behind the bar
    filed = [
        (UseSource.NEW, None),
        (UseSource.NEW, Plausibility.UNCERTAIN),
        (UseSource.CANON, Plausibility.UNCERTAIN),
        (UseSource.SCENE, Plausibility.ABSENT),
        (UseSource.CARRIED, None),
    ]

    for source, judged in filed:
        intent = Intent(steps=[throw("the telephone", source, judged)])
        check = resolve(state, intent).steps[0].beats[0]
        assert (check.verdict, check.roll) == (BeatVerdict.HOLDS, None), (source, judged)


def test_a_plain_absent_for_something_new_stands_against_a_loose_match():
    """Words match loosely: the well's rim of worn stone is no stone to pick up."""
    state = cultivation_world()
    intent = Intent(steps=[throw("a stone", UseSource.NEW, Plausibility.ABSENT)])

    (settled,) = resolve(state, intent).steps

    assert settled.reason == "There is no stone to be found here."
    assert settled.outcome_class is OutcomeClass.RULED_OUT


def test_what_a_turn_found_is_listed_for_the_scenes_record():
    """R3: what code made canon is what the scene's record keeps (`engine.apply`): never what
    was already there, and never what a step that was cut short would have found."""
    state = cultivation_world()
    bucket = Beat(
        text="lift the bucket", uses=[BeatUse(source=UseSource.SCENE, thing="the wooden bucket")]
    )
    intent = Intent(
        steps=[
            throw("a fallen branch", UseSource.NEW, Plausibility.PLAUSIBLE),
            step("lift the bucket", beats=[bucket]),
        ]
    )

    resolution = resolve(state, intent)

    assert resolution.found == ["a fallen branch"]
    cut_short = resolution.steps[0].model_copy(update={"interrupted": True})
    assert resolution.model_copy(update={"steps": [cut_short]}).found == []


def test_canon_from_an_earlier_beat_this_turn_holds_and_unsupported_canon_is_judged():
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

    # Canon this turn never made is judged like anything new.
    lone = Intent(steps=[throw("the silver key", UseSource.CANON, Plausibility.UNCERTAIN)])
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


def stop_time_in_a_beat():
    beats = [
        Beat(
            text="stop time",
            uses=[BeatUse(source=UseSource.POWER, thing="time stop", ref="time-stop")],
        )
    ]
    return step(
        "stop time and slip past Zhao", ActionKind.MOVE, 2, proposed_personal_s=2, beats=beats
    )


def test_a_power_a_beat_uses_must_be_ready_too():
    state = cultivation_world()
    state.player.sheet.powers[0].ready_at_personal_s = 5

    (settled,) = resolve(state, Intent(steps=[stop_time_in_a_beat()])).steps

    assert settled.beats[0].verdict is BeatVerdict.EMPTY
    assert (settled.outcome_class, settled.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert settled.reason == "Your time stop hasn't recovered yet."
    assert settled.costs == [] and settled.duration_s == 2


def test_a_time_stop_used_in_a_beat_stops_the_world_clock():
    state = cultivation_world()

    (settled,) = resolve(state, Intent(steps=[stop_time_in_a_beat()])).steps

    assert (settled.duration_s, settled.personal_s) == (0, 2)
    assert [c.ref for c in settled.costs] == ["time-stop"]


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
