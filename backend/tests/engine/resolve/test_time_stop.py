"""T17's time-stop scenarios over many seeds: time stop, stopped-time throw, light-speed throw,
unrivalled, player theory and stopped-time rescue (W10a, A2, A9, G22, W5, N6), with the handoffs
from the resolver: a step that outlasts a stop, a frozen body met by a hit's own force, and who
is immune to a stop."""

import pytest

from engine import pipeline
from engine.base import MINUTE
from engine.context import Difficulty
from engine.contracts import (
    ActionKind,
    Aim,
    Contact,
    Intent,
    MeansVerdict,
    OutcomeClass,
    PowerTheory,
    TheoryAbout,
)
from engine.resolve.powers import force
from engine.resolve.powers import time_stop as stop
from engine.resolve.powers.theories import strongest_tier
from engine.state import (
    Character,
    CharacterSheet,
    CharacterStatus,
    EventStatus,
    Faction,
    FactionStatus,
    ForceScale,
    GiftStrength,
    Health,
    HitMode,
    Membership,
    PendingEvent,
    Place,
    PlaceStatus,
    PowerAxes,
    RulingSource,
    StepResult,
    TraceKind,
    Trait,
    TraitKind,
)
from engine.world.answers import Answer, actor_might, choose_answer, faction_might
from engine.world.scheduling import World
from tests.engine.resolve.power_worlds import (
    SEEDS,
    army_throw,
    battlefield,
    ctx,
    friend,
    lin_power,
    play,
    resolve,
    rng,
    stop_time,
    throw,
    with_hit_mode,
    with_wall,
)
from tests.engine.resolve.worlds import add, facts, item, power, sect, step, strike, with_troll

E2E_SEEDS = range(40)


def died(resolution, character_id: str) -> bool:
    return any(
        c.id == character_id and c.status is CharacterStatus.DEAD
        for s in resolution.steps
        for c in s.effects.characters
    )


def health_of(resolution, character_id: str) -> Health | None:
    for s in resolution.steps:
        for c in s.effects.characters:
            if c.id == character_id and c.condition is not None and c.condition.health:
                return c.condition.health
    return None


# --- the force of a light-speed pebble -----------------------------------------------------------


def test_a_hundred_grams_at_relative_speed_is_about_three_megatons():
    joules = force.relative_speed_joules(force.PEBBLE_KG)
    blast = force.blast(joules)

    assert blast.words == "about 3 megatons"
    assert 13.0 < force.tier_for(joules, ForceScale()) < 13.2
    assert 6_000 < blast.lethal_m < 8_000  # Hiroshima's 15 kt kills out to about 1.2 km
    assert blast.lethal_m < 10_000 < blast.harm_m


# --- Time stop (T17) -----------------------------------------------------------------------------


def crowded_square():
    """Lin in the market square with a guard and a crowd, and a guard patrol due in a second."""
    state = sect()
    state.places["square"] = Place(id="square", name="the market square", kind="square")
    state.characters["lin"].location_id = "square"
    state.scene.place_id = "square"
    state.scene.present_ids = ["lin"]
    guard = Character(
        id="guard",
        name="the sect guard",
        location_id="square",
        sheet=CharacterSheet(axes=PowerAxes(might=2)),
    )
    crowd = [
        Character(id=f"vendor-{i}", name=f"vendor {i}", location_id="square") for i in range(4)
    ]
    add(state, guard, *crowd)
    state.pending_events["patrol"] = PendingEvent(
        id="patrol",
        kind="director.patrol",
        title="A patrol turns into the square.",
        due_s=state.world_s + 1,
    )
    return state


def kill_guard():
    return step(
        "cut the guard's throat",
        verb="kill",
        aim=Aim.KILL,
        target_ids=["guard"],
        uses=[item("sword")],
        proposed_personal_s=2,
    )


@pytest.mark.parametrize("seed", E2E_SEEDS)
def test_time_stop_the_kill_happens_with_no_roll_nothing_fires_nobody_sees_and_rumors_start(seed):
    state = crowded_square()
    played = play(state, Intent(steps=[stop_time(), kill_guard()]), seed)
    stopped, kill = played.resolution.steps

    assert (kill.outcome_class, kill.result, kill.roll) == (
        OutcomeClass.CERTAIN,
        StepResult.SUCCESS,
        None,
    )
    assert played.state.world_s == state.world_s  # the world clock stood still
    assert played.fired == ()  # the patrol due a second later never came
    assert played.state.pending_events["patrol"].status is EventStatus.PENDING
    assert not played.state.characters["guard"].alive
    deed = next(d for d in played.state.deeds.values() if "guard" in d.victim_ids)
    assert deed.in_stopped_time and deed.witness_ids == []
    assert any(t.kind is TraceKind.BODY and t.strength == 100 for t in deed.traces)
    assert played.state.time_effects == []  # the stop ran out within the plan

    later = pipeline.catch_up(played.state, played.state.world_s + 10 * MINUTE, ctx(4), rng(seed))
    rumors = [r for r in later.state.rumors.values() if r.deed_id == deed.id]
    assert rumors, "the body in the square starts rumors once time runs again (W13)"
    assert all("lin" not in r.about_ids for r in rumors)  # nobody saw who did it


# --- Stopped-time throw (T17) --------------------------------------------------------------------


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_stopped_time_throw_with_normal_force_the_pebble_bounces_off_the_troll(difficulty):
    state = with_hit_mode(with_wall(sect()), HitMode.NORMAL_FORCE)
    intent = Intent(steps=[stop_time(), throw(["troll", "wall"])])

    for seed in SEEDS:
        resolution = resolve(state, intent, seed, difficulty=difficulty)
        pebble = resolution.steps[1]
        assert pebble.outcome_class is OutcomeClass.RULED_OUT and pebble.roll is None
        assert not died(resolution, "troll")
        assert not pebble.effects.places
    assert "frozen in stopped time" in pebble.reason


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_stopped_time_throw_at_relative_speed_smashes_the_troll_and_the_wall_every_time(difficulty):
    state = with_hit_mode(with_wall(sect()), HitMode.RELATIVE_SPEED)
    # The interpret step thought a pebble couldn't hurt a troll; code follows the power.
    intent = Intent(steps=[stop_time(), throw(["troll", "wall"])])

    for seed in SEEDS:
        resolution = resolve(state, intent, seed, difficulty=difficulty)
        pebble = resolution.steps[1]
        assert (pebble.outcome_class, pebble.result, pebble.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert died(resolution, "troll")
        ruined = {p.id for p in pebble.effects.places if p.status is PlaceStatus.RUINED}
        assert "wall" in ruined
        # Ten meters from three megatons: the thrower dies in their own blast once time restarts.
        assert died(resolution, "lin")
    assert "3 megatons" in pebble.reason


@pytest.mark.parametrize("seed", range(10))
def test_the_stopped_time_blast_starts_rumors(seed):
    state = with_hit_mode(with_wall(sect()), HitMode.RELATIVE_SPEED)
    played = play(state, Intent(steps=[stop_time(), throw(["troll", "wall"])]), seed)

    blast = next(d for d in played.state.deeds.values() if "wall" in d.target_ids)
    assert blast.in_stopped_time and blast.witness_ids == []
    assert played.state.places["wall"].status is PlaceStatus.RUINED
    later = pipeline.catch_up(played.state, played.state.world_s + 10 * MINUTE, ctx(4), rng(seed))
    assert any(r.deed_id == blast.id for r in later.state.rumors.values())


# --- Light-speed throw (T17) ---------------------------------------------------------------------


def test_light_speed_throw_from_the_ridge_the_army_dies_and_the_thrower_lives():
    state = battlefield()
    intent = Intent(steps=[stop_time(), army_throw(10_000)])

    for seed in SEEDS:
        resolution = resolve(state, intent, seed, difficulty=Difficulty.BALANCED)
        pebble = resolution.steps[1]
        assert (pebble.outcome_class, pebble.result, pebble.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert "about 3 megatons" in pebble.reason
        (army,) = pebble.effects.factions
        assert (army.id, army.status) == ("army", FactionStatus.DESTROYED)
        assert all(died(resolution, f"soldier-{i}") for i in range(3))
        assert not died(resolution, "lin")
        assert health_of(resolution, "lin") is Health.HURT  # knocked down by the distant blast


def test_light_speed_throw_from_the_castle_wall_the_thrower_dies_with_the_army():
    state = battlefield()
    intent = Intent(steps=[stop_time(), army_throw(300), step("walk away", ActionKind.MOVE, 60)])

    for seed in SEEDS:
        resolution = resolve(state, intent, seed, difficulty=Difficulty.BALANCED)
        pebble = resolution.steps[1]
        assert pebble.outcome_class is OutcomeClass.CERTAIN and pebble.roll is None
        assert pebble.effects.factions[0].status is FactionStatus.DESTROYED
        assert died(resolution, "lin")
        castle = {p.id: p.status for p in pebble.effects.places}
        assert castle == {"plain": PlaceStatus.RUINED, "castle": PlaceStatus.RUINED}
        # Nothing after it plays: the thrower died once time restarted (N6).
        assert resolution.steps[2].outcome_class is OutcomeClass.RULED_OUT
        assert "blast" in resolution.steps[2].reason


def kingdoms(state):
    for i, might in enumerate((10, 8, 6)):
        state.factions[f"kingdom-{i}"] = Faction(id=f"kingdom-{i}", name=f"kingdom {i}")
        champion = Character(
            id=f"champion-{i}",
            name=f"champion {i}",
            memberships=[Membership(faction_id=f"kingdom-{i}")],
            sheet=CharacterSheet(axes=PowerAxes(might=might)),
        )
        state.characters[champion.id] = champion
    return state


def answers(state, faction_id: str, *, harmed: bool, seeds=range(300)) -> set[Answer]:
    found = set()
    for seed in seeds:
        w = World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng(seed))
        faction = state.factions[faction_id]
        found.add(choose_answer(w, faction, "lin", 13, enforcing=False, harmed=harmed))
    return found


def test_light_speed_throw_the_world_fears_courts_or_plots_against_a_known_survivor():
    state = kingdoms(battlefield())
    lin_power(state).secret = False  # the world knows what the power does

    assert stop.might_with_powers(state, state.characters["lin"]) >= 13
    for kingdom in ("kingdom-0", "kingdom-1", "kingdom-2"):
        gap = actor_might(state, "lin") - faction_might(
            state, state.factions[kingdom], excluding="lin"
        )
        assert gap > 2
        found = answers(state, kingdom, harmed=False)
        assert found <= {
            Answer.APPEASE,
            Answer.AVOID,
            Answer.RECRUIT,
            Answer.COALITION,
            Answer.SEAL,
            Answer.WORSHIP,
        }
        harmed = answers(state, kingdom, harmed=True)
        assert Answer.ARMY not in harmed and Answer.ELITE not in harmed


def test_a_secret_light_speed_thrower_is_measured_by_the_sheet_until_a_deed_is_laid_at_their_door():
    state = battlefield()
    lin = state.characters["lin"]
    assert lin_power(state).secret
    assert stop.might_with_powers(state, lin) == lin.sheet.axes.might

    played = play(state, Intent(steps=[stop_time(), army_throw(10_000)]))
    deed = next(d for d in played.state.deeds.values() if d.in_stopped_time)
    deed.known_by_factions.append("azure-cloud")
    assert stop.might_with_powers(played.state, played.state.characters["lin"]) >= 13


# --- Unrivalled (T17) ----------------------------------------------------------------------------


def test_unrivalled_nothing_in_the_world_survives_the_throw_and_no_faction_answers_with_force():
    state = kingdoms(sect())
    lin_power(state).secret = False
    pebble = force.tier_for(force.relative_speed_joules(force.PEBBLE_KG), state.bible.force)

    assert strongest_tier(state) < pebble  # the bible holds nothing that takes three megatons
    for faction_id in sorted(state.factions):
        faction = state.factions[faction_id]
        assert actor_might(state, "lin") - faction_might(state, faction, excluding="lin") > 2
        found = answers(state, faction_id, harmed=True, seeds=range(200))
        assert not found & {Answer.ARMY, Answer.ELITE}  # nobody conjured to match the player


def test_unrivalled_a_ruler_can_still_be_plotted_against():
    state = kingdoms(sect())
    lin_power(state).secret = False

    found = set().union(*(answers(state, f, harmed=True) for f in sorted(state.factions)))
    assert found & {Answer.ASSASSIN, Answer.BOUNTY, Answer.SEAL, Answer.APPEASE}


# --- Player theory (T17) -------------------------------------------------------------------------


def throw_at_the_troll_far_off():
    return throw(["troll"], range_m=8_000)


def speed_of_light():
    return PowerTheory(
        topic="throw_speed",
        claim="A rock thrown in stopped time should hit at the speed of light.",
        about=TheoryAbout.HIT_FORCE,
        claims_hit_mode=HitMode.RELATIVE_SPEED,
        rests_on=["time-stop"],
    )


def test_player_theory_the_rock_hits_with_overwhelming_force_and_the_power_works_that_way_after():
    state = with_hit_mode(with_troll(sect()), None)  # the player never said how it works
    lin_power(state).strength = GiftStrength.RARE

    intent = Intent(steps=[stop_time(), throw_at_the_troll_far_off()], theories=[speed_of_light()])
    first = play(state, intent)
    rock = first.resolution.steps[1]
    assert (rock.outcome_class, rock.result, rock.roll) == (
        OutcomeClass.CERTAIN,
        StepResult.SUCCESS,
        None,
    )
    assert "speed of light" in rock.reason
    (ruling,) = first.resolution.rulings
    assert ruling.holds and ruling.source is RulingSource.THEORY
    assert lin_power(first.state).time.hit_mode is HitMode.RELATIVE_SPEED
    assert first.state.characters["lin"].sheet.ruling("hit_mode", "time-stop") is not None

    # Some time later, with no theory at all, the power works that way on every seed.
    later = first.state
    later.time_effects.clear()
    later.characters["lin"].personal_offset_s += 60
    later.characters["troll-2"] = later.characters["troll"].model_copy(
        update={"id": "troll-2", "status": CharacterStatus.ALIVE}
    )
    later.scene.present_ids.append("troll-2")
    for seed in SEEDS:
        again = Intent(steps=[stop_time(), throw(["troll-2"], range_m=8_000)])
        resolution = resolve(later, again, seed, turn=5)
        assert died(resolution, "troll-2")
        assert resolution.steps[1].roll is None


def test_player_theory_a_grabbed_boulder_joins_the_stop_as_heavy_as_ever():
    state = with_hit_mode(sect(), None)
    boulder = step(
        "grab the boulder",
        ActionKind.INSTANT,
        1,
        verb="grab",
        contact=Contact.LIFT,
        mass_kg=2_000,
        proposed_personal_s=1,
    )

    for seed in SEEDS:
        resolution = resolve(state, Intent(steps=[stop_time(), boulder]), seed)
        grab = resolution.steps[1]
        assert grab.outcome_class is OutcomeClass.RULED_OUT and grab.roll is None
        assert "as heavy as ever" in grab.reason
        (change,) = grab.effects.characters
        (ruling,) = change.rulings
        assert (ruling.topic, ruling.holds) == ("move_frozen", True)
        assert ruling.source is RulingSource.TEST


def test_player_theory_nothing_the_player_didnt_raise_blocks_a_sprint_in_stopped_time():
    state = sect()
    sprint = step(
        "sprint across the square",
        ActionKind.MOVE,
        20,
        verb="sprint",
        proposed_personal_s=2,
        # The interpret step worried about air at that speed; the conventions settle it.
        facts=facts(hindrances=["air resistance at that speed"], means=MeansVerdict.CLOSE_CALL),
    )

    for seed in SEEDS:
        resolution = resolve(state, Intent(steps=[stop_time(), sprint]), seed)
        run = resolution.steps[1]
        assert (run.outcome_class, run.result, run.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert "air" not in run.reason
        assert resolution.rulings == []  # nobody asked the player how it works


def test_a_power_never_settled_is_settled_by_code_the_first_time_it_hits_never_asking():
    state = with_hit_mode(with_troll(sect()), None)
    lin_power(state).strength = GiftStrength.SMALL  # a modest stop lands with normal force

    played = play(state, Intent(steps=[stop_time(), strike("troll", proposed_personal_s=2)]))
    hit = played.resolution.steps[1]
    (change,) = [c for c in hit.effects.characters if c.rulings]
    assert change.rulings[0].source is RulingSource.TEST
    assert lin_power(played.state).time.hit_mode is HitMode.NORMAL_FORCE


# --- Stopped-time rescue (T17) -------------------------------------------------------------------


def carry_mei():
    return step(
        "carry Mei out of the arrow's path and set her down",
        ActionKind.MOVE,
        5,
        verb="carry",
        contact=Contact.LIFT,
        target_ids=["mei"],
        mass_kg=50,
        proposed_personal_s=2,
    )


def test_stopped_time_rescue_the_friend_is_unhurt_and_knows_nothing_of_the_stop():
    state = with_hit_mode(friend(sect()), HitMode.RELATIVE_SPEED)

    for seed in SEEDS[:60]:
        played = play(state, Intent(steps=[stop_time(), carry_mei()]), seed)
        carry = played.resolution.steps[1]
        assert (carry.outcome_class, carry.result, carry.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        mei = played.state.characters["mei"]
        assert mei.alive and mei.sheet.condition.health is Health.UNHURT
        assert not any("mei" in f.known_by for f in played.state.facts.values())
        assert not any("mei" in d.known_by for d in played.state.deeds.values())
        assert played.state.world_s == state.world_s


# --- handoffs from the resolver -----------------------------------------------------------------


def test_a_step_that_outlasts_the_stop_lives_it_out_and_then_takes_world_time():
    state = sect()
    lin_power(state).time.lasts_s = 10
    state.pending_events["bell"] = PendingEvent(
        id="bell", kind="director.bell", title="The bell rings.", due_s=5
    )
    walk = step("walk to the gate", ActionKind.MOVE, 30, verb="walk", proposed_personal_s=30)

    resolution = resolve(state, Intent(steps=[stop_time(), walk]))
    assert (resolution.steps[1].duration_s, resolution.steps[1].personal_s) == (21, 30)

    played = pipeline.play_out(state, resolution, ctx(), rng())
    assert played.state.world_s == 21
    assert played.state.characters["lin"].personal_s(played.state.world_s) == 31
    assert [e.id for e in played.fired] == ["bell"]  # it fires once time runs again
    assert played.state.time_effects == []


def test_someone_acted_on_by_a_step_that_outlasts_the_stop_can_answer_by_then():
    state = sect()
    lin_power(state).time.lasts_s = 2
    long_fight = strike("zhao", proposed_personal_s=60, kind=ActionKind.EXCHANGE)

    settled = resolve(state, Intent(steps=[stop_time(), long_fight])).steps[1]
    assert "frozen in stopped time" not in settled.reason


def test_a_frozen_body_meets_the_hits_own_force_not_the_arm_behind_it():
    state = with_hit_mode(sect(), HitMode.RELATIVE_SPEED)
    elder = state.characters["elder-mo"]
    elder.location_id = "well"
    add(state, elder)
    # Elder Mo stands two realms above Lin, so Lin's own arm couldn't hurt him at all.
    intent = Intent(steps=[stop_time(), strike("elder-mo", proposed_personal_s=2)])
    for seed in SEEDS:
        hit = resolve(state, intent, seed).steps[1]
        assert (hit.outcome_class, hit.result, hit.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert "like butter" in hit.reason


def test_a_body_tougher_than_the_hit_takes_it_unhurt():
    state = with_hit_mode(with_troll(sect()), HitMode.RELATIVE_SPEED)
    state.characters["troll"].sheet.axes.might = 20  # a being of a cosmic story
    intent = Intent(steps=[stop_time(), throw(["troll"], range_m=9_000)])
    for seed in SEEDS:
        hit = resolve(state, intent, seed).steps[1]
        assert hit.outcome_class is OutcomeClass.RULED_OUT
        assert "tough enough to take it" in hit.reason


def test_someone_immune_to_the_stop_can_respond_and_sees_what_is_done():
    state = sect()
    elder = state.characters["elder-mo"]
    elder.location_id = "well"
    elder.sheet.traits.append(
        Trait(
            name="Timeless Eye",
            kind=TraitKind.GIFT,
            description="Moves freely when time is stopped.",
        )
    )
    add(state, elder)

    intent = Intent(steps=[stop_time(), strike("zhao", proposed_personal_s=2)])
    hit = resolve(state, intent).steps[1]
    assert hit.deeds[0].witness_ids == ["elder-mo"]
    attack = resolve(state, Intent(steps=[stop_time(), strike("elder-mo", proposed_personal_s=2)]))
    assert "frozen" not in attack.steps[1].reason


def test_a_stop_used_twice_in_one_plan_hasnt_recovered_the_second_time():
    state = sect()
    wait = step("wait", ActionKind.WAIT, 3, verb="wait")

    resolution = resolve(state, Intent(steps=[stop_time(), wait, stop_time()]))
    assert resolution.steps[2].outcome_class is OutcomeClass.RULED_OUT
    assert "hasn't recovered" in resolution.steps[2].reason


def test_a_stop_that_outlasts_the_turn_still_holds_the_world_next_turn_with_no_new_cost():
    state = sect()
    lin_power(state).time.lasts_s = 60
    first = play(state, Intent(steps=[stop_time()]))
    assert [e.ends_personal_s for e in first.state.time_effects] == [60]

    keep_going = strike("zhao", proposed_personal_s=2)
    keep_going = keep_going.model_copy(update={"uses": [power("time-stop"), item("sword")]})
    second = resolve(first.state, Intent(steps=[keep_going]), turn=4).steps[0]
    assert second.outcome_class is OutcomeClass.CERTAIN
    assert "frozen in stopped time" in second.reason
    assert second.costs == [] and second.duration_s == 0


# --- From review: cooldowns, unstated lengths, rolled times, immunity and survived throws -------


def test_a_stop_carried_over_that_runs_out_mid_plan_cant_be_started_again_without_recharge():
    state = sect()
    lin_power(state).time.lasts_s = 5
    lin_power(state).time.recharge_s = 60
    first = play(state, Intent(steps=[stop_time()]))  # 1 s lived, 4 s of the stop left
    walk = step("walk over", ActionKind.TASK, 5, verb="walk", proposed_personal_s=5)

    later = resolve(first.state, Intent(steps=[walk, stop_time()]), turn=4)
    assert later.steps[1].outcome_class is OutcomeClass.RULED_OUT
    assert "hasn't recovered" in later.steps[1].reason


def test_a_stop_whose_sheet_gives_no_length_lasts_a_few_heartbeats():
    state = sect()
    lin_power(state).time.lasts_s = None
    long_task = step("tidy the courtyard", ActionKind.TASK, 600, verb="tidy")

    played = play(state, Intent(steps=[stop_time(), long_task]))
    assert played.state.time_effects == []  # lived out, so it never holds the world for good
    assert played.resolution.steps[1].duration_s == 600 - (stop.UNSTATED_LASTS_S - 1)
    assert lin_power(played.state).ready_at_personal_s is not None


@pytest.mark.parametrize("seed", SEEDS)
def test_a_rolled_time_in_a_stop_keeps_to_how_the_step_was_settled(seed):
    state = sect()
    lin_power(state).time.lasts_s = 10
    inside = strike("zhao", proposed_personal_s=8, duration_uncertain=True)
    outside = strike("zhao", proposed_personal_s=12, duration_uncertain=True)

    within = resolve(state, Intent(steps=[stop_time(), inside]), seed).steps[1]
    assert "frozen in stopped time" in within.reason and within.duration_s == 0
    past = resolve(state, Intent(steps=[stop_time(), outside]), seed).steps[1]
    assert "frozen in stopped time" not in past.reason and past.duration_s > 0


def test_immunity_comes_from_a_setting_or_words_that_say_so_not_from_a_stop_of_ones_own():
    state = sect()
    elder = state.characters["elder-mo"]
    rival = stop_power_like_lins("The World", "Stops time; only the user moves.")
    elder.sheet.powers.append(rival)
    assert not stop.immune(elder)

    rival.settings[stop.STOP_IMMUNITY] = "yes"
    assert stop.immune(elder)
    rival.settings.clear()
    rival.description = "Stops time, and its user is immune to anyone else's stop."
    assert stop.immune(elder)


def stop_power_like_lins(name: str, description: str):
    from engine.state import Power, TimeEffect, TimePower

    return Power(
        id="the-world",
        name=name,
        description=description,
        time=TimePower(effect=TimeEffect.STOP, lasts_s=5),
    )


def test_a_throw_the_target_survives_still_lets_its_blast_loose():
    state = with_wall(sect())
    state.characters["troll"].sheet.axes.might = 15  # far above three megatons
    bystander = Character(
        id="farmer",
        name="a farmer",
        location_id="wall",
        sheet=CharacterSheet(axes=PowerAxes(might=1)),
    )
    add(state, bystander)

    stone = resolve(state, Intent(steps=[stop_time(), throw(["troll"], range_m=9_000)])).steps[1]
    assert stone.outcome_class is OutcomeClass.RULED_OUT
    assert "unhurt" in stone.reason and "blast tears through" in stone.reason
    assert not any(c.id == "troll" and c.status for c in stone.effects.characters)
    assert any(
        c.id == "farmer" and c.status is CharacterStatus.DEAD for c in stone.effects.characters
    )
