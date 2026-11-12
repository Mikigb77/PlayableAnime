"""T17's earned technique, controlled throw and nonsense-not-power scenarios over many seeds, and
the rest of WS9b: theories ruled once (A9), growth (A4), breakthroughs (G19), hidden strength
(G20), backstory claims (N4), haste (W10a) and a chain that burns a place down (A9, W7)."""

from collections import Counter

import pytest

from engine.base import DAY, HOUR
from engine.contracts import (
    ActionKind,
    Aim,
    Contact,
    EffectScale,
    GrowthKind,
    Intent,
    MeansVerdict,
    OutcomeClass,
    PastClaim,
    PlaceHarm,
    PowerGrant,
    PowerTheory,
    ShowStrength,
    StepFacts,
    Teacher,
    TheoryAbout,
)
from engine.director import rules
from engine.resolve.powers import sensing
from engine.resolve.powers import time_stop as stop
from engine.resolve.powers.growth import GainHow, GainKind, GainRead, read_gain
from engine.resolve.powers.theories import NEW_POWER, NOTHING_BEHIND_IT, TOO_BIG
from engine.state import (
    Character,
    CharacterSheet,
    CharacterStatus,
    Fact,
    Gain,
    GiftStrength,
    HitMode,
    Item,
    LadderPosition,
    PassingState,
    PlaceStatus,
    Power,
    PowerAxes,
    RulingSource,
    SkillLevel,
    StepResult,
    Technique,
    TimeEffect,
    TimePower,
    Trait,
    TraitKind,
    Visibility,
)
from engine.world.answers import actor_might
from tests.engine.resolve.power_worlds import (
    SEEDS,
    bandit_camp,
    lin_power,
    play,
    resolve,
    stop_time,
    throw,
    train,
    train_power,
    train_until_done,
    with_hit_mode,
)
from tests.engine.resolve.worlds import (
    add,
    burn_the_hall,
    facts,
    power,
    sect,
    shielded_mage,
    step,
    with_troll,
)


@pytest.fixture(autouse=True)
def quiet_days(monkeypatch):
    """Nothing cuts a stretch of training short here (E7): these tests are about what the
    training earns. That skipped time may be interrupted is `test_story_clock`'s."""
    monkeypatch.setattr(rules, "MONTAGE_MIN_S", 10**12)


def died(resolution, character_id: str) -> bool:
    return any(
        c.id == character_id and c.status is CharacterStatus.DEAD
        for s in resolution.steps
        for c in s.effects.characters
    )


def light_speed_question(**kw) -> PowerTheory:
    kw.setdefault("claims_hit_mode", HitMode.RELATIVE_SPEED)
    return PowerTheory(
        topic="throw_speed",
        claim="Could a throw in stopped time hit at the speed of light?",
        about=TheoryAbout.HIT_FORCE,
        **kw,
    )


def rested(state, *, minutes: int = 10):
    """Some time later: the stop has run out and recovered, and the character has healed."""
    state.time_effects.clear()
    lin = state.characters["lin"]
    lin.personal_offset_s += minutes * 60
    lin.sheet.condition.health = lin.sheet.condition.health.__class__.UNHURT
    return state


# --- Earned technique (T17) ----------------------------------------------------------------------


def test_earned_technique_no_twice_then_the_trained_throw_lands_at_relative_speed():
    state = with_hit_mode(with_troll(sect()), HitMode.NORMAL_FORCE)

    first = play(state, Intent(theories=[light_speed_question()]))
    second = play(first.state, Intent(theories=[light_speed_question()]), turn=4)
    (no,) = first.resolution.rulings
    (again,) = second.resolution.rulings
    assert not no.holds and no.answer == stop.HIT_MODE_ANSWERS[HitMode.NORMAL_FORCE]
    assert (again.answer, again.holds) == (no.answer, no.holds)  # the same answer, never re-argued
    assert len(second.state.characters["lin"].sheet.rulings) == 1

    trained = train_until_done(
        second.state, Intent(steps=[train_power(PowerGrant.RELATIVE_SPEED_THROWS)]), turn=5
    )
    lin = trained.state.characters["lin"]
    technique = lin.sheet.technique("technique-falling-star-release")
    assert technique is not None and technique.power_id == "time-stop"
    assert lin.sheet.ruling("hit_mode", "time-stop").holds is False  # the first ruling stands
    assert lin.sheet.ruling("technique:falling-star-release", "time-stop").holds
    assert lin_power(trained.state).time.hit_mode is HitMode.NORMAL_FORCE

    later = rested(trained.state)
    later.characters["troll"].location_id = lin.location_id
    for seed in SEEDS:
        resolution = resolve(
            later, Intent(steps=[stop_time(), throw(["troll"], range_m=9_000)]), seed, turn=6
        )
        rock = resolution.steps[1]
        assert (rock.outcome_class, rock.result, rock.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert died(resolution, "troll")
        assert "speed of light" in rock.reason


def test_a_trained_way_to_throw_doesnt_change_how_blows_land():
    state = with_hit_mode(with_troll(sect()), HitMode.NORMAL_FORCE)
    lin_power(state).settings[stop.THROWS] = stop.RELATIVE
    blow = step(
        "punch the troll",
        verb="punch",
        aim=Aim.KILL,
        target_ids=["troll"],
        contact=Contact.STRIKE,
        facts=facts(means=MeansVerdict.CLEARLY_NOT),
    )

    settled = resolve(state, Intent(steps=[stop_time(), blow])).steps[1]
    assert settled.outcome_class is OutcomeClass.RULED_OUT


# --- Controlled throw (T17) ----------------------------------------------------------------------


def test_controlled_throw_the_bandit_dies_and_nothing_else_is_wrecked():
    state = bandit_camp(sect())
    trained = train_until_done(state, Intent(steps=[train_power(PowerGrant.CONTROLLED_FORCE)]), 3)
    lin = trained.state.characters["lin"]
    assert lin.sheet.technique("technique-gentle-release") is not None
    assert lin_power(trained.state).settings[stop.CONTROL] == stop.CONTROLLED

    later = rested(trained.state)
    for seed in SEEDS:
        resolution = resolve(later, Intent(steps=[stop_time(), throw(["bandit"])]), seed, turn=4)
        stone = resolution.steps[1]
        assert (stone.outcome_class, stone.result, stone.roll) == (
            OutcomeClass.CERTAIN,
            StepResult.SUCCESS,
            None,
        )
        assert [c.id for c in stone.effects.characters] == ["bandit"]
        assert died(resolution, "bandit")
        assert not stone.effects.places and not stone.effects.factions
        assert len(stone.deeds) == 1  # no blast


def test_full_force_still_lands_with_everything_the_power_can_give():
    state = bandit_camp(sect())
    lin_power(state).settings[stop.CONTROL] = stop.CONTROLLED
    everything = throw(["bandit"], range_m=9_000, full_force=True)

    stone = resolve(state, Intent(steps=[stop_time(), everything])).steps[1]
    assert "3 megatons" in stone.reason
    assert any(p.status is PlaceStatus.RUINED for p in stone.effects.places)


# --- Nonsense, not power (T17) -------------------------------------------------------------------


def test_nonsense_not_power_the_flick_is_refused_with_no_lecture():
    state = with_hit_mode(sect(), None)
    flick = PowerTheory(
        topic="planet_flick",
        claim="A flick of my finger in stopped time blows up the planet.",
        scale=EffectScale.WORLD,
    )

    for seed in SEEDS[:20]:
        (ruling,) = resolve(state, Intent(theories=[flick]), seed).rulings
        assert not ruling.holds and ruling.answer == NOTHING_BEHIND_IT
    grounded = flick.model_copy(update={"rests_on": ["time-stop"]})
    (ruling,) = resolve(state, Intent(theories=[grounded])).rulings
    assert not ruling.holds and ruling.answer == TOO_BIG


def test_nonsense_not_power_a_way_that_holds_works_however_strong_it_makes_the_character():
    state = with_hit_mode(sect(), None)
    lin_power(state).strength = GiftStrength.RARE  # a modest stop would land with normal force
    lin_power(state).secret = False
    way = light_speed_question(rests_on=["time-stop"])
    elder = state.characters["elder-mo"]
    elder.location_id = "well"
    add(state, elder)
    kill = throw(["elder-mo"], range_m=9_000)

    first = play(state, Intent(theories=[way], steps=[stop_time(), kill]))
    (ruling,) = first.resolution.rulings
    assert ruling.holds and ruling.cost == stop.HEAVY_DRAIN_COST  # a yes with a heavier drain
    assert lin_power(first.state).settings[stop.DRAIN] == stop.HEAVY
    assert died(first.resolution, "elder-mo")
    # The world answers that strength: it measures the thrower as far above the sect.
    assert actor_might(first.state, "lin") >= 13

    for seed in SEEDS:
        again = resolve(state, Intent(theories=[way], steps=[stop_time(), kill]), seed)
        assert died(again, "elder-mo") and again.steps[1].roll is None


# --- theories (A9) -------------------------------------------------------------------------------


def test_a_theory_that_adds_a_power_or_breaks_a_fixed_rule_is_refused():
    state = sect()
    wings = PowerTheory(topic="flight", claim="Stopping time lets me fly.", adds_power=True)
    rule = PowerTheory(
        topic="ascend",
        claim="In stopped time I pass Soul Transformation.",
        rests_on=["time-stop"],
        against_rule_ids=["qi-exists"],
    )

    first, second = resolve(state, Intent(theories=[wings, rule])).rulings
    assert (first.holds, first.answer) == (False, NEW_POWER)
    assert not second.holds and second.answer.startswith("No: Qi cultivation")


def test_a_theory_with_something_behind_it_holds_whatever_it_does_for_the_character():
    state = sect()
    lungs = PowerTheory(
        topic="breath",
        claim="The air in my lungs is enough for a long stop.",
        rests_on=["time-stop"],
        scale=EffectScale.PERSON,
    )

    (ruling,) = resolve(state, Intent(theories=[lungs])).rulings
    assert ruling.holds and ruling.source is RulingSource.THEORY


def test_untouchable_isnt_settled_once_the_power_has_picked_frozen_things_up():
    state = with_hit_mode(sect(), None)
    lin_power(state).settings[stop.MOVE_FROZEN] = stop.YES
    theory = light_speed_question(claims_hit_mode=HitMode.UNTOUCHABLE)

    (ruling,) = resolve(state, Intent(theories=[theory])).rulings
    assert not ruling.holds


# --- growth (A4) ---------------------------------------------------------------------------------


def test_training_adds_up_across_sessions_until_the_skill_climbs():
    state = sect()
    first = play(state, Intent(steps=[train(GrowthKind.SKILL, "swordsmanship", 20)]))
    assert first.state.characters["lin"].sheet.practiced("skill:swordsmanship").effort_s > 0
    assert first.state.characters["lin"].sheet.skill("swordsmanship") is None

    more = Intent(steps=[train(GrowthKind.SKILL, "swordsmanship", 100)])
    second = play(first.state, more, turn=4)
    lin = second.state.characters["lin"]
    assert lin.sheet.skill("swordsmanship").level is SkillLevel.NOVICE
    assert lin.sheet.practiced("skill:swordsmanship").effort_s == 0
    assert lin.sheet.growth[-1].what == "swordsmanship"


def with_master(state):
    state.characters["elder-mo"].location_id = "well"
    return state


def palm_lesson(**kw):
    kw.setdefault("teacher", Teacher.MASTER)
    return train(GrowthKind.TECHNIQUE, "Drifting Cloud Palm", 40, **kw)


def test_a_master_and_a_gift_for_learning_speed_it_up():
    slow = with_master(sect())
    fast = with_master(sect())
    fast.characters["lin"].sheet.traits.append(Trait(name="a genius", kind=TraitKind.GIFT))
    lesson = palm_lesson(teacher_id="elder-mo")

    assert "progress" in resolve(slow, Intent(steps=[lesson])).steps[0].reason
    learned = play(fast, Intent(steps=[lesson]))
    assert learned.state.characters["lin"].sheet.techniques[0].name == "Drifting Cloud Palm"


def test_a_master_counts_only_when_they_are_really_there():
    genius = Trait(name="a genius", kind=TraitKind.GIFT)
    unnamed = sect()
    unnamed.characters["lin"].sheet.traits.append(genius)
    # No master the world holds: the genius learns alone, too slowly to finish in 40 hours.
    alone = resolve(unnamed, Intent(steps=[palm_lesson()])).steps[0]
    assert "progress" in alone.reason

    away = sect()
    away.characters["lin"].sheet.traits.append(genius)
    settled = resolve(away, Intent(steps=[palm_lesson(teacher_id="elder-mo")])).steps[0]
    assert settled.outcome_class is OutcomeClass.RULED_OUT and "isn't here" in settled.reason


def copycat_watch(state, teacher_id="zhao"):
    state.characters["lin"].sheet.traits.append(Trait(name="copycat eyes", kind=TraitKind.GIFT))
    return train(
        GrowthKind.TECHNIQUE, "Iron Fist", 0.1, teacher=Teacher.WATCHING, teacher_id=teacher_id
    )


def test_a_copycat_watching_learns_a_technique_at_once():
    state = sect()
    state.characters["zhao"].sheet.techniques.append(Technique(id="iron-fist", name="Iron Fist"))
    played = play(state, Intent(steps=[copycat_watch(state)]))

    assert "just by watching" in played.resolution.steps[0].reason
    assert played.state.characters["lin"].sheet.techniques[0].learned_from == "zhao"


def test_a_gain_reads_back_as_what_it_was_and_how_it_was_made():
    # A4, G17: the record keeps a gain in the engine's own words, and a screen reads it back.
    def last(played):
        return read_gain(played.state.characters["lin"].sheet.growth[-1])

    first = play(sect(), Intent(steps=[train(GrowthKind.SKILL, "swordsmanship", 20)]))
    skill = play(first.state, Intent(steps=[train(GrowthKind.SKILL, "swordsmanship", 100)]), turn=4)
    assert last(skill) == GainRead(GainKind.SKILL, now=SkillLevel.NOVICE, how=GainHow.SELF)

    state = sect()
    state.characters["zhao"].sheet.techniques.append(Technique(id="iron-fist", name="Iron Fist"))
    watched = play(state, Intent(steps=[copycat_watch(state)]))
    assert last(watched) == GainRead(GainKind.LEARNED, how=GainHow.WATCHING)

    release = Intent(steps=[train_power(PowerGrant.CONTROLLED_FORCE)])
    earned = train_until_done(bandit_camp(sect()), release, 3)
    assert last(earned) == GainRead(GainKind.NEW_USE, power="time stop", how=GainHow.SELF)

    climbed = next(
        played
        for seed in SEEDS
        if (played := play(sect(), Intent(steps=[seclusion()]), seed))
        .state.characters["lin"]
        .sheet.ladders[0]
        .rung
        == 1
    )
    assert last(climbed) == GainRead(GainKind.BREAKTHROUGH)

    # Words nobody writes are nobody's to read.
    assert read_gain(Gain(what="luck", change="more of it", source="a wish", reason="")) is None


def test_a_copycat_learns_nothing_at_once_from_someone_who_doesnt_know_it_or_from_no_one():
    state = sect()
    from_zhao = resolve(state, Intent(steps=[copycat_watch(state)])).steps[0]
    assert "progress" in from_zhao.reason

    nobody = sect()
    alone = resolve(nobody, Intent(steps=[copycat_watch(nobody, None)])).steps[0]
    assert "progress" in alone.reason


def test_no_power_grows_in_a_world_with_nothing_extraordinary():
    from engine.samples import grounded_world

    state = grounded_world()
    state.characters[state.player_id].sheet.powers.append(
        Power(id="time-stop", name="time stop", time=TimePower(effect=TimeEffect.STOP))
    )
    settled = resolve(state, Intent(steps=[train_power(PowerGrant.RELATIVE_SPEED_THROWS)])).steps[0]
    assert settled.outcome_class is OutcomeClass.RULED_OUT


def test_a_dead_master_teaches_nothing():
    state = sect()
    state.characters["elder-mo"].status = CharacterStatus.DEAD
    lesson = train(
        GrowthKind.TECHNIQUE,
        "Drifting Cloud Palm",
        40,
        teacher=Teacher.MASTER,
        teacher_id="elder-mo",
    )

    assert resolve(state, Intent(steps=[lesson])).steps[0].outcome_class is OutcomeClass.RULED_OUT


# --- Breakthrough (T17, G19) ---------------------------------------------------------------------


def seclusion():
    return train(GrowthKind.BREAKTHROUGH, "Foundation Establishment", 30, ladder_id="realms")


def test_a_missing_need_is_a_bottleneck():
    state = sect()
    state.bible.ladders[0].rungs[1].needs = ["a Foundation Pill"]

    settled = resolve(state, Intent(steps=[seclusion()])).steps[0]
    assert settled.outcome_class is OutcomeClass.RULED_OUT and "bottleneck" in settled.reason


def test_breakthrough_can_fail_or_wound_and_its_length_varies_with_the_roll():
    state = sect()
    state.bible.ladders[0].rungs[1].needs = ["a Foundation Pill"]
    give_pill = Item(id="pill", name="Foundation Pill")
    state.characters["lin"].sheet.resources.items.append(give_pill)

    results, lengths = Counter(), set()
    for seed in SEEDS:
        settled = resolve(state, Intent(steps=[seclusion()]), seed).steps[0]
        assert settled.outcome_class is OutcomeClass.CONTESTED and settled.roll is not None
        results[settled.result] += 1
        lengths.add(settled.duration_s)
        (change,) = settled.effects.characters
        if settled.result is StepResult.SUCCESS:
            assert change.ladders[0].rung == 1
        else:
            assert change.condition is not None and not change.ladders
    assert set(results) == set(StepResult)
    assert max(lengths) > 10 * min(lengths)


def test_the_world_interrupts_a_long_seclusion_when_something_needs_the_player():
    from engine import pipeline
    from engine.state import PendingEvent
    from tests.engine.resolve.power_worlds import ctx, rng

    state = sect()
    state.pending_events["visitor"] = PendingEvent(
        id="visitor",
        kind="director.visit",
        title="Zhao bangs on the door.",
        due_s=HOUR,
        needs_player=True,
    )
    long_one = train(
        GrowthKind.BREAKTHROUGH, "Foundation Establishment", 24 * 20, ladder_id="realms"
    )
    resolution = resolve(state, Intent(steps=[long_one]), 3)
    played = pipeline.play_out(state, resolution, ctx(), rng(3))

    assert played.interrupted_by is not None and played.resolution.steps[0].interrupted
    assert played.state.characters["lin"].sheet.ladders[0].rung == 0


def test_a_loud_breakthrough_is_a_public_deed():
    state = sect()
    state.bible.ladders[0].rungs[1].loud = True
    for seed in SEEDS:
        settled = resolve(state, Intent(steps=[seclusion()]), seed).steps[0]
        if settled.result is StepResult.SUCCESS:
            (deed,) = settled.deeds
            assert deed.kind == "breakthrough" and deed.visibility is Visibility.PUBLIC
            return
    pytest.fail("no breakthrough succeeded")


# --- Hidden strength (T17, G20) ------------------------------------------------------------------


def disguised_expert():
    state = sect()
    state.characters["lin"].sheet.ladders = [LadderPosition(ladder_id="realms", rung=2)]
    young = Character(
        id="young-master",
        name="Young Master Wu",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=4), ladders=[LadderPosition(ladder_id="realms", rung=1)]
        ),
    )
    return add(state, young)


def test_hidden_strength_npcs_see_what_they_can_perceive_until_the_reveal():
    from engine import pipeline
    from tests.engine.resolve.power_worlds import ctx, rng

    state = disguised_expert()
    hide = step(
        "hide my cultivation",
        ActionKind.INSTANT,
        1,
        verb="hide",
        show_strength=ShowStrength(ladder_id="realms", shown_rung=0),
    )
    hidden = play(state, Intent(steps=[hide]))
    lin, wu = hidden.state.characters["lin"], hidden.state.characters["young-master"]
    assert sensing.perceived_rung(hidden.state, wu, lin, "realms") == 0
    assert actor_might(hidden.state, "lin") == 2  # the world measures what it shows

    reveal = step(
        "let my cultivation show",
        ActionKind.INSTANT,
        1,
        verb="reveal",
        show_strength=ShowStrength(ladder_id="realms"),
    )
    shown = play(hidden.state, Intent(steps=[reveal]), turn=4)
    attitude = shown.state.characters["young-master"].attitude_toward("lin")
    assert attitude.fear >= 40
    assert any(d.kind == "reveal" for d in shown.state.deeds.values())
    # W2: nobody speaks of it to his face. Word of it goes round once he has left them.
    after = shown.state
    assert after.rumors == {}
    after.scene.present_ids = []
    until_s, turn = after.world_s + HOUR, 5
    while after.world_s < until_s:
        after = pipeline.catch_up(after, until_s, ctx(turn), rng(0, turn)).state
        turn += 1
    assert after.rumors
    assert actor_might(shown.state, "lin") >= 2


def _hidden_expert():
    state = disguised_expert()
    hide = step(
        "hide my cultivation",
        ActionKind.INSTANT,
        1,
        verb="hide",
        show_strength=ShowStrength(ladder_id="realms", shown_rung=0),
    )
    return play(state, Intent(steps=[hide])).state


def test_showing_the_rung_one_truly_stands_on_is_a_reveal():
    """G20: the real model may name the rung to show ("I let my Core Formation show") where
    the engine expects none for all of it. That is the same reveal: a deed, and everyone who
    underestimated them moved at once. Never one more disguise that nobody notices."""
    named = step(
        "let my Core Formation show",
        ActionKind.INSTANT,
        1,
        verb="reveal",
        show_strength=ShowStrength(ladder_id="realms", shown_rung=2),
    )
    shown = play(_hidden_expert(), Intent(steps=[named]), turn=4)
    lin = shown.state.characters["lin"]
    assert sensing.position(lin, "realms").shown_rung is None
    assert shown.state.characters["young-master"].attitude_toward("lin").fear >= 40
    assert [d.kind for d in shown.state.deeds.values()] == ["reveal"]
    # With nothing hidden, showing that rung changes nothing, as showing all of it would.
    again = resolve(shown.state, Intent(steps=[named])).steps[0]
    assert again.outcome_class is OutcomeClass.CERTAIN and "never hidden" in again.reason


def test_a_reveal_before_a_crowd_moves_everyone_there_whoever_the_scene_listed():
    """G20, W2: in the first live story (2026-11-11) the scene before the reveal had dropped
    the young master from its people, so the reveal "in front of everyone watching" moved him
    as a bystander who hears of a display, and not as someone who had taken a master for a
    novice. Before a crowd, everyone the record puts at the place sees it. Without one, only
    the scene's people do, and nobody asleep does."""
    reveal = dict(verb="reveal", show_strength=ShowStrength(ladder_id="realms"))

    def fear_after(state, **facts):
        shown = step("let my cultivation show", ActionKind.INSTANT, 1, **reveal, **facts)
        played = play(state, Intent(steps=[shown]), turn=4)
        return played.state.characters["young-master"].attitude_toward("lin").fear

    dropped = _hidden_expert()
    dropped.scene.present_ids = ["lin"]
    assert fear_after(dropped.model_copy(deep=True), facts=StepFacts(crowd=True)) >= 40
    assert fear_after(dropped.model_copy(deep=True)) == 0
    asleep = _hidden_expert()
    asleep.characters["young-master"].sheet.condition.states = [PassingState(name="asleep")]
    assert fear_after(asleep) == 0


def test_strength_can_be_hidden_never_inflated():
    state = disguised_expert()
    boast = step(
        "show a higher realm",
        ActionKind.INSTANT,
        1,
        verb="show",
        show_strength=ShowStrength(ladder_id="realms", shown_rung=4),
    )
    assert resolve(state, Intent(steps=[boast])).steps[0].outcome_class is OutcomeClass.RULED_OUT


def test_someone_above_the_hiders_true_rung_sees_through_it():
    state = disguised_expert()
    lin = state.characters["lin"]
    lin.sheet.ladders = [LadderPosition(ladder_id="realms", rung=1, shown_rung=0)]
    elder = state.characters["elder-mo"]
    assert sensing.perceived_rung(state, elder, lin, "realms") == 1


# --- backstory claims (N4) ----------------------------------------------------------------------


def test_backstory_is_recorded_unless_it_grants_contradicts_or_breaks_a_rule():
    state = sect()
    state.facts["parents"] = Fact(
        id="parents", text="Lin's parents died in a fire.", known_by=["lin"]
    )
    intent = Intent(
        backstory=[
            "I was raised by a kind old herbalist.",
            PastClaim(text="I am the sect master's secret heir.", grants_power=True),
            PastClaim(text="My parents are alive.", contradicts_ids=["parents"]),
            PastClaim(text="Elder Mo has always adored me.", about_others=True),
            PastClaim(text="I was born a dragon.", against_rule_ids=["time-powers-exist"]),
        ]
    )

    played = play(state, intent)
    verdicts = [(c.text, c.accepted) for c in played.resolution.claims]
    assert [accepted for _, accepted in verdicts] == [True, False, False, False, False]
    lin = played.state.characters["lin"]
    assert [b.text for b in lin.sheet.backstory] == ["I was raised by a kind old herbalist."]
    beliefs = [f for f in played.state.facts.values() if not f.is_true]
    assert len(beliefs) == 1 and "lin" in beliefs[0].known_by


# --- haste (W10a) --------------------------------------------------------------------------------


def test_a_haste_lets_the_actor_live_more_than_the_world_passes():
    state = sect()
    state.characters["lin"].sheet.powers.append(
        Power(
            id="haste",
            name="Swift Wind",
            time=TimePower(effect=TimeEffect.HASTE, rate=4.0, lasts_s=600, recharge_s=HOUR),
        )
    )
    run = step(
        "run to the inner court",
        ActionKind.MOVE,
        1200,
        verb="run",
        uses=[power("haste")],
        proposed_personal_s=400,
    )
    search = step("search the hall", ActionKind.TASK, 400, verb="search")

    first, second = resolve(state, Intent(steps=[run, search])).steps
    assert (first.duration_s, first.personal_s) == (100, 400)
    # 200 lived seconds of haste are left: 50 world seconds, then the rest at the world's pace.
    assert (second.duration_s, second.personal_s) == (250, 400)


# --- a chain that burns a place down (A9, W7, agreed with WS10) --------------------------------


def test_a_link_that_burns_the_hall_down_ruins_it_and_is_a_deed_of_its_own():
    state = shielded_mage()
    hall = burn_the_hall()
    links = list(hall.chain)
    links[0] = links[0].model_copy(update={"place_id": "hall", "place_harm": PlaceHarm.RUINED})
    hall = hall.model_copy(update={"chain": links})

    for seed in SEEDS[:50]:
        played = play(state, Intent(steps=[hall]), seed)
        assert played.state.places["hall"].status is PlaceStatus.RUINED
        burned = [d for d in played.state.deeds.values() if "hall" in d.target_ids]
        assert burned and burned[0].kind == "burn"


def test_a_place_only_burns_if_the_link_held():
    state = shielded_mage(teleport=True)
    hall = burn_the_hall()
    links = list(hall.chain)
    links[-1] = links[-1].model_copy(update={"place_id": "hall", "place_harm": PlaceHarm.RUINED})
    hall = hall.model_copy(update={"chain": links})

    settled = resolve(state, Intent(steps=[hall])).steps[0]
    assert not settled.effects.places


def test_training_time_counts_on_the_trainers_own_clock_in_a_long_time_skip():
    state = sect()
    year = train(GrowthKind.TECHNIQUE, "Falling Leaf Sword", 365 * 24)

    settled = resolve(state, Intent(steps=[year])).steps[0]
    assert settled.duration_s == 365 * DAY
    assert "Falling Leaf Sword" in settled.reason


# --- From review: grounding, ambiguous powers and a master's guidance ----------------------------


def test_a_theory_nothing_stands_behind_is_refused_at_any_scale():
    state = sect()
    small = PowerTheory(
        topic="stop_heals",
        claim="Stopping time heals my wounds.",
        scale=EffectScale.PERSON,
    )
    (ruling,) = resolve(state, Intent(theories=[small])).rulings
    assert not ruling.holds and ruling.answer == NOTHING_BEHIND_IT


def test_a_theory_about_a_power_the_engine_cant_tell_apart_sets_nothing_in_stone():
    state = sect()
    state.characters["lin"].sheet.powers.append(
        Power(id="flame", name="spirit flame", description="Calls up a pale flame.")
    )
    vague = PowerTheory(
        topic="melt_steel",
        claim="It should melt steel.",
        rests_on=["heat"],
        about=TheoryAbout.OTHER,
    )
    assert resolve(state, Intent(theories=[vague])).rulings == []

    named = vague.model_copy(update={"claim": "My spirit flame should melt steel."})
    (ruling,) = resolve(state, Intent(theories=[named])).rulings
    assert ruling.power_id == "flame" and ruling.holds


def test_a_rung_that_needs_a_masters_guidance_needs_a_master_who_is_there():
    state = sect()
    state.bible.ladders[0].rungs[1].needs = ["a master's guidance"]
    guided = train(
        GrowthKind.BREAKTHROUGH,
        "Foundation Establishment",
        30,
        ladder_id="realms",
        teacher=Teacher.MASTER,
    )
    settled = resolve(state, Intent(steps=[guided])).steps[0]
    assert settled.outcome_class is OutcomeClass.RULED_OUT and "bottleneck" in settled.reason

    with_master(state)
    named = guided.model_copy(
        update={"training": guided.training.model_copy(update={"teacher_id": "elder-mo"})}
    )
    assert resolve(state, Intent(steps=[named])).steps[0].outcome_class is OutcomeClass.CONTESTED


def test_training_cut_short_keeps_the_effort_and_the_next_stretch_finishes_it():
    from engine import pipeline
    from engine.state import PendingEvent
    from tests.engine.resolve.power_worlds import ctx, rng

    state = sect()
    state.pending_events["visitor"] = PendingEvent(
        id="visitor",
        kind="director.visit",
        title="Zhao bangs on the door.",
        due_s=8 * DAY,
        needs_player=True,
    )
    long_one = train(GrowthKind.TECHNIQUE, "Falling Leaf Sword", 60 * 24)
    resolution = resolve(state, Intent(steps=[long_one]))
    cut = pipeline.play_out(state, resolution, ctx(), rng())
    assert cut.resolution.steps[0].interrupted and cut.rejected == ()
    lin = cut.state.characters["lin"]
    kept = lin.sheet.practiced("technique:falling-leaf-sword")
    assert kept is not None and 0 < kept.effort_s < 150 * HOUR
    assert lin.sheet.techniques == []

    again = train_until_done(cut.state, Intent(steps=[long_one]), 4)
    assert again.state.characters["lin"].sheet.techniques[0].name == "Falling Leaf Sword"
