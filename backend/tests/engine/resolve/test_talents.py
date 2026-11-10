"""Rulings on talent and bridges (A4, A9), through the resolver.

Agreed with Miki on 2026-11-10. The first time a character sets out to learn or use a thing, the
engine rules once on how each of their talents stands to it, from the case the interpret step
proposes, and never flips it. Words alone don't reopen a ruling, but a deed does: a bridge is a
step of real work, thrown with their own skill against the reach.
"""

import pytest

from engine.contracts import (
    Bridge,
    Challenge,
    GrowthKind,
    Intent,
    OutcomeClass,
    SheetPart,
    SheetUse,
    TalentCase,
    Teacher,
)
from engine.state import (
    DieKind,
    Mastery,
    Skill,
    SkillLevel,
    StepResult,
    Talent,
    TalentFit,
    TalentRuling,
    TalentStrength,
    Technique,
    WorldState,
)

from .power_worlds import play, train
from .test_mastery import (
    awakened,
    blade_of,
    cut_the_rope,
    cut_the_thief,
    knowing,
    practising,
    technique,
)
from .worlds import SEEDS, facts, power, step

INSIDE, RELATED, OUTSIDE = TalentFit.INSIDE, TalentFit.RELATED, TalentFit.OUTSIDE
SLOW, KNACK, GENIUS, UNIQUE = (
    TalentStrength.SLOW,
    TalentStrength.KNACK,
    TalentStrength.GENIUS,
    TalentStrength.ONE_OF_A_KIND,
)
BLADE = "technique:aura-blade"
WALL = "technique:aura-wall"


def talent(talent_id: str, name: str, strength: TalentStrength, **kw) -> Talent:
    return Talent(id=talent_id, name=name, strength=strength, **kw)


SWORD = talent("sword", "The sword", UNIQUE, covers="anything fought with a blade")
ARCHITECT = talent("architect", "Genius architect", GENIUS, covers="structure and geometry")
WORDS = talent("words", "Hopeless with words", SLOW, covers="persuading anyone")


def talented(*talents: Talent, state: WorldState | None = None) -> WorldState:
    """Lin with an aura blade he is learning, the given talents, and an architect's training."""
    state = state or knowing(awakened())
    sheet = state.player.sheet
    sheet.talents = [t.model_copy() for t in talents]
    sheet.skills.append(Skill(name="architecture", level=SkillLevel.EXPERT))
    return state


def case(talent_id: str, fit: TalentFit, what: str = "Aura blade", reason: str = "") -> TalentCase:
    return TalentCase(what=what, talent_id=talent_id, fit=fit, reason=reason)


def arguing(a_step, *cases: TalentCase):
    return a_step.model_copy(update={"talent_cases": list(cases)})


def rulings(state: WorldState):
    return state.player.sheet.talent_rulings


def stands(state: WorldState, key: str = BLADE):
    from engine import talent as talent_mod

    return talent_mod.standing(state.player, key)


# --- the ruling ------------------------------------------------------------------------------


def test_the_first_time_a_thing_is_used_the_engine_rules_once_and_says_so():
    state = talented(SWORD, ARCHITECT)
    cut = arguing(
        cut_the_rope(technique("blade")),
        case("sword", INSIDE, reason="A blade is a blade, whatever it is made of."),
        case("architect", RELATED, reason="shaping aura is structure and geometry"),
    )

    played = play(state, Intent(steps=[cut]))

    (settled,) = played.resolution.steps
    assert (
        'Ruled once: Aura blade is inside your talent "The sword" (A blade is a blade, whatever'
        ' it is made of) and related to your talent "Genius architect" (shaping aura is structure'
        " and geometry). It grows eight times as fast." in settled.reason
    )
    (ruling,) = rulings(played.state)
    assert (ruling.key, ruling.what, ruling.turn) == (BLADE, "Aura blade", 3)
    assert [(c.talent_id, c.fit) for c in ruling.covers] == [
        ("sword", INSIDE),
        ("architect", RELATED),
    ]


def test_the_ruling_already_sets_the_pace_of_the_step_that_made_it():
    """Eight times as fast: the one use that would be one of six takes the blade to practiced."""
    state = talented(SWORD)

    played = play(
        state, Intent(steps=[arguing(cut_the_rope(technique("blade")), case("sword", INSIDE))])
    )

    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.PRACTICED, 0)
    assert played.resolution.steps[0].reason.endswith(
        "Your Aura blade has grown from learning to practiced."
    )


def test_a_ruling_never_flips_whatever_is_argued_later():
    state = talented(SWORD)
    first = play(
        state, Intent(steps=[arguing(cut_the_rope(technique("blade")), case("sword", RELATED))])
    )

    again = arguing(
        cut_the_rope(technique("blade")), case("sword", INSIDE, reason="but it IS a sword")
    )
    played = play(first.state, Intent(steps=[again]), turn=4)

    (ruling,) = rulings(played.state)
    assert [c.fit for c in ruling.covers] == [RELATED]
    assert "Ruled once" not in played.resolution.steps[0].reason
    assert stands(played.state).steps == 2


def test_with_no_case_the_thing_stays_unruled_at_the_ordinary_pace():
    state = talented(SWORD)

    played = play(state, Intent(steps=[cut_the_thief(technique("blade"))]))

    assert rulings(played.state) == []
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.LEARNING, 2)
    # Nothing was decided, so the case can still be made the next time.
    later = arguing(cut_the_rope(technique("blade")), case("sword", INSIDE))
    assert len(rulings(play(played.state, Intent(steps=[later]), turn=4).state)) == 1


def test_a_ruling_that_finds_every_talent_outside_is_kept_too():
    state = talented(SWORD)
    lesson = arguing(
        train(GrowthKind.SKILL, "Herb lore", 3),
        case("sword", OUTSIDE, what="Herb lore", reason="nothing to cut"),
    )

    played = play(state, Intent(steps=[lesson]))

    (ruling,) = rulings(played.state)
    assert (ruling.key, ruling.covers[0].fit) == ("skill:herb-lore", OUTSIDE)
    assert played.resolution.steps[0].reason.endswith(
        'Ruled once: Herb lore is outside your talent "The sword" (nothing to cut). It grows at'
        " the ordinary pace."
    )


def test_only_the_sheets_own_talents_can_be_ruled_on():
    """A talent is never declared in play: a case for one they don't hold counts for nothing."""
    state = talented(SWORD)
    cut = arguing(cut_the_rope(technique("blade")), case("chosen-one", INSIDE))

    played = play(state, Intent(steps=[cut]))

    assert rulings(played.state) == []
    assert blade_of(played.state).uses == 1


def test_a_talent_is_found_by_its_name_when_the_case_gives_no_id():
    state = talented(SWORD)

    played = play(
        state, Intent(steps=[arguing(cut_the_rope(technique("blade")), case("the sword", INSIDE))])
    )

    assert rulings(played.state)[0].covers[0].talent_id == "sword"


def test_a_general_talent_needs_no_ruling_and_takes_none():
    prodigy = talent("prodigy", "Prodigy", GENIUS, general=True)
    state = talented(prodigy)

    played = play(
        state, Intent(steps=[arguing(cut_the_thief(technique("blade")), case("prodigy", OUTSIDE))])
    )

    assert rulings(played.state) == []
    assert blade_of(played.state).mastery is Mastery.PRACTICED  # two uses at a quarter of six


def test_a_case_that_names_nothing_is_about_the_one_thing_at_stake():
    state = talented(SWORD)
    cut = arguing(cut_the_rope(technique("blade")), case("sword", INSIDE, what=""))

    assert rulings(play(state, Intent(steps=[cut])).state)[0].key == BLADE


def test_a_case_in_other_words_is_still_about_the_one_thing_at_stake():
    """The interpret step called it something else: there is only one thing it can mean."""
    state = talented(SWORD)
    cut = arguing(cut_the_rope(technique("blade")), case("sword", INSIDE, what="his edge of light"))

    (ruling,) = rulings(play(state, Intent(steps=[cut])).state)

    assert (ruling.key, ruling.what) == (BLADE, "Aura blade")


@pytest.mark.parametrize(
    "what",
    ["architecture", "Rising palm", "the cultivation realms", "Aura step"],
    ids=["a skill of theirs", "another technique", "a ladder", "a thing already ruled on"],
)
def test_a_case_about_some_other_thing_of_theirs_is_never_moved_onto_the_one_at_stake(what):
    """A ruling is kept for good, so a case made about their architecture is not read as one
    about the blade the step happens to use."""
    state = talented(SWORD)
    state.player.sheet.techniques.append(Technique(id="palm", name="Rising palm"))
    state.player.sheet.talent_rulings.append(
        TalentRuling(key="technique:aura-step", what="Aura step")
    )
    ladder = state.bible.ladders[0]
    said = ladder.name if what == "the cultivation realms" else what
    cut = arguing(cut_the_rope(technique("blade")), case("sword", INSIDE, what=said))

    played = play(state, Intent(steps=[cut]))

    assert [r.key for r in rulings(played.state)] == ["technique:aura-step"]
    assert "Ruled once" not in played.resolution.steps[0].reason


def test_with_two_things_at_stake_a_case_has_to_name_its_thing():
    state = talented(SWORD)
    state.player.sheet.techniques.append(Technique(id="step", name="Aura step", power_id="aura"))
    both = cut_the_rope(technique("blade"), technique("step"))

    unnamed = play(state, Intent(steps=[arguing(both, case("sword", INSIDE, what="that move"))]))
    named = play(state, Intent(steps=[arguing(both, case("sword", OUTSIDE, what="aura step"))]))

    assert rulings(unnamed.state) == []
    assert [(r.key, r.covers[0].fit) for r in rulings(named.state)] == [
        ("technique:aura-step", OUTSIDE)
    ]


def test_a_step_that_was_ruled_out_rules_on_nothing():
    state = talented(SWORD)
    cut = arguing(
        cut_the_rope(technique("blade")).model_copy(update={"facts": facts(world_allows=False)}),
        case("sword", INSIDE),
    )

    played = play(state, Intent(steps=[cut]))

    assert played.resolution.steps[0].outcome_class is OutcomeClass.RULED_OUT
    assert rulings(played.state) == []


def test_a_ruling_holds_for_the_steps_that_follow_in_the_same_plan():
    """Ruled on in the morning, practised in the afternoon: two hours at eight uses each."""
    state = talented(SWORD)
    plan = Intent(
        steps=[
            arguing(cut_the_rope(technique("blade")), case("sword", INSIDE)),
            *practising(2).steps,
        ]
    )

    played = play(state, plan)

    assert len(rulings(played.state)) == 1
    assert blade_of(played.state).mastery is Mastery.SECOND_NATURE


def test_practising_a_technique_rules_on_that_technique_whatever_the_step_calls_it():
    state = talented(SWORD)
    drill = arguing(
        train(GrowthKind.TECHNIQUE, "blade", 1), case("sword", INSIDE, what="the blade")
    )

    played = play(state, Intent(steps=[drill]))

    (ruling,) = rulings(played.state)
    assert (ruling.key, ruling.what) == (BLADE, "Aura blade")


# --- what the pace changes -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("held", "fit", "after"),
    [
        (talent("hands", "Quick hands", KNACK), INSIDE, (Mastery.LEARNING, 2, 3)),
        (ARCHITECT, RELATED, (Mastery.LEARNING, 2, 3)),
        (ARCHITECT, INSIDE, (Mastery.PRACTICED, 0, 4)),
        (SWORD, INSIDE, (Mastery.PRACTICED, 1, 2)),
        (talent("clumsy", "Clumsy", SLOW), INSIDE, (Mastery.LEARNING, 2, 12)),
    ],
    ids=["knack", "related genius", "genius", "one of a kind", "weakness"],
)
def test_a_fight_counts_two_uses_against_what_their_talent_asks(held, fit, after):
    state = talented(held)
    cut = arguing(cut_the_thief(technique("blade")), case(held.id, fit))

    played = play(state, Intent(steps=[cut]))

    from engine import levels

    blade = blade_of(played.state)
    need = levels.uses_to_next(blade.mastery, stands(played.state).pace)
    assert (blade.mastery, blade.uses, need) == after


@pytest.mark.parametrize(
    ("held", "fit", "start", "dice"),
    [
        (SWORD, INSIDE, Mastery.SKILLED, "3 dice"),
        (ARCHITECT, INSIDE, Mastery.PRACTICED, "2 dice"),
        (ARCHITECT, RELATED, Mastery.LEARNING, "1 die"),
        (SWORD, RELATED, Mastery.PRACTICED, "2 dice"),
    ],
    ids=["one of a kind", "genius", "related genius", "related one of a kind"],
)
def test_a_new_move_starts_where_the_talent_that_covers_it_puts_it(held, fit, start, dice):
    """A genius's new move starts at practiced and one of a kind's at skilled, and it is thrown
    with those dice the first time."""
    state = talented(held, state=awakened())
    cut = arguing(cut_the_thief(power("aura"), technique("Aura blade")), case(held.id, fit))

    for seed in SEEDS:
        played = play(state, Intent(steps=[cut]), seed)
        (settled,) = played.resolution.steps
        assert settled.roll.throw.hand_why == f"Aura blade (a new move), {dice}"
        if settled.result is StepResult.SUCCESS:
            (blade,) = played.state.player.sheet.techniques
            assert blade.mastery.rank >= start.rank
            return
    pytest.fail("the move never came off")


def test_training_goes_at_the_pace_the_ruling_gives():
    state = talented(ARCHITECT)
    lesson = arguing(
        train(GrowthKind.TECHNIQUE, "Aura wall", 4),
        case("architect", RELATED, what="Aura wall", reason="a wall is structure"),
    )

    played = play(state, Intent(steps=[lesson]))

    (settled,) = played.resolution.steps
    assert settled.reason.startswith(
        "You make progress toward Aura wall: about 8 hours of the 150 hours"
    )
    assert played.state.player.sheet.practice[0].effort_s == 8 * 3600


def test_one_of_a_kind_takes_in_a_technique_it_covers_by_watching_it_done():
    """Extreme perception: any move they can watch someone do is theirs on sight, at skilled."""
    sight = talent("sight", "Extreme perception", UNIQUE, covers="any move he can watch done")
    state = talented(sight)
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    watch = arguing(
        train(
            GrowthKind.TECHNIQUE, "Rising Palm", 0.1, teacher=Teacher.WATCHING, teacher_id="zhao"
        ),
        case("sight", INSIDE, what="Rising Palm", reason="he watches it done"),
    )

    played = play(state, Intent(steps=[watch]))

    assert "You pick up Rising Palm just by watching." in played.resolution.steps[0].reason
    palm = played.state.player.sheet.technique("technique-rising-palm")
    assert (palm.mastery, palm.learned_from) == (Mastery.SKILLED, "zhao")


def test_a_genius_still_has_to_put_in_the_hours_to_learn_by_watching():
    state = talented(ARCHITECT)
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    watch = arguing(
        train(
            GrowthKind.TECHNIQUE, "Rising Palm", 0.1, teacher=Teacher.WATCHING, teacher_id="zhao"
        ),
        case("architect", INSIDE, what="Rising Palm"),
    )

    played = play(state, Intent(steps=[watch]))

    assert "just by watching" not in played.resolution.steps[0].reason
    assert played.state.player.sheet.technique("technique-rising-palm") is None


def test_one_of_a_kind_that_was_ruled_outside_takes_nothing_on_sight():
    """Nothing to see in it: perception hands over no move it doesn't cover."""
    sight = talent("sight", "Extreme perception", UNIQUE)
    state = talented(sight)
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    watch = arguing(
        train(
            GrowthKind.TECHNIQUE, "Rising Palm", 0.1, teacher=Teacher.WATCHING, teacher_id="zhao"
        ),
        case("sight", OUTSIDE, what="Rising Palm", reason="it all happens inside his body"),
    )

    assert "just by watching" not in play(state, Intent(steps=[watch])).resolution.steps[0].reason


def test_a_climb_their_genius_covers_throws_a_green_die_and_a_weakness_adds_five():
    climb = train(GrowthKind.BREAKTHROUGH, "Foundation Establishment", 30, ladder_id="realms")
    gifted = talented(talent("roots", "Heavenly roots", GENIUS))
    cursed = talented(talent("roots", "Crippled meridians", SLOW))
    roots = case("roots", INSIDE, what="Foundation Establishment")

    blessed = play(gifted, Intent(steps=[arguing(climb, roots)]))
    hindered = play(cursed, Intent(steps=[arguing(climb, roots)]))
    plain = play(talented(), Intent(steps=[climb]))

    assert rulings(blessed.state)[0].key == "ladder:realms"
    assert blessed.resolution.steps[0].roll.throw.greens == ["a gift for learning"]
    assert plain.resolution.steps[0].roll.throw.greens == []
    assert hindered.resolution.steps[0].roll.throw.number == (
        plain.resolution.steps[0].roll.throw.number + 5
    )


# --- insight ---------------------------------------------------------------------------------


def test_two_talents_that_cover_the_move_show_an_insight_on_16():
    """The violet die of a move both talents cover fully shows an insight on 16 and 17 too."""
    hands = talent("hands", "Quick hands", KNACK)
    both = arguing(cut_the_thief(technique("blade")), case("sword", INSIDE), case("hands", INSIDE))
    one = arguing(cut_the_thief(technique("blade")), case("sword", INSIDE), case("hands", RELATED))
    seen = 0
    for seed in SEEDS:
        doubled = play(talented(SWORD, hands), Intent(steps=[both]), seed).resolution.steps[0]
        single = play(talented(SWORD, hands), Intent(steps=[one]), seed).resolution.steps[0]
        thrown = doubled.roll.throw
        (violet,) = [d for d in thrown.dice if d.kind is DieKind.VIOLET]
        assert (thrown.insight_at, single.roll.throw.insight_at) == (16, 18)
        if violet.face in (16, 17):
            seen += 1
            assert thrown.insight and not single.roll.throw.insight
            assert "An insight into Aura blade" in doubled.reason
    assert seen


# --- bridges ---------------------------------------------------------------------------------


def ruled_wall(fit: TalentFit = RELATED, *talents: Talent) -> WorldState:
    """Lin a few hours into an Aura wall that was ruled on for his architecture."""
    state = talented(*(talents or (ARCHITECT,)))
    lesson = arguing(
        train(GrowthKind.TECHNIQUE, "Aura wall", 2),
        case(state.player.sheet.talents[0].id, fit, what="Aura wall"),
    )
    return play(state, Intent(steps=[lesson])).state


def derive(rests_on: str = "the load formula behind the wall's shape", **kw):
    talent_id = kw.pop("talent_id", "architect")
    skill = kw.pop("skill", "architecture")
    update = kw.pop("facts", None)
    bridge = Bridge(talent_id=talent_id, what="Aura wall", rests_on=rests_on, **kw)
    built = step(
        "derive the formula behind the wall",
        uses=[SheetUse(part=SheetPart.SKILL, ref=skill)],
        bridge=bridge,
    )
    return built.model_copy(update={"facts": update}) if update is not None else built


def bridges(state: WorldState):
    return state.player.sheet.bridges


def first(state: WorldState, intent: Intent, result: StepResult, turn: int = 4):
    """The first seed on which the plan's one step ends this way."""
    for seed in SEEDS:
        played = play(state, intent, seed, turn)
        if played.resolution.steps[0].result is result:
            return played
    pytest.fail(f"never {result}")


def test_a_bridge_is_thrown_with_their_own_skill_against_the_reach():
    played = first(ruled_wall(), Intent(steps=[derive()]), StepResult.SUCCESS)

    (settled,) = played.resolution.steps
    assert settled.reason.startswith(
        "Architecture (expert), 4 dice, against the reach from Genius architect to Aura wall, a"
        " hard task, level 3:"
    )
    assert settled.reason.endswith(
        "The bridge holds: resting on the load formula behind the wall's shape, Aura wall now"
        ' grows four times as fast through your talent "Genius architect".'
    )
    (bridge,) = bridges(played.state)
    assert (bridge.key, bridge.talent_id, bridge.steps, bridge.turn) == (WALL, "architect", 1, 4)
    assert stands(played.state, WALL).steps == 2


def test_a_bridge_over_the_heart_of_the_thing_is_harder_and_lifts_two():
    sight = talent("sight", "Extreme perception", UNIQUE)
    state = ruled_wall(OUTSIDE, sight)
    heart = derive(talent_id="sight", heart=True)

    played = first(state, Intent(steps=[heart]), StepResult.SUCCESS)

    assert "a very hard task, level 4" in played.resolution.steps[0].reason
    assert bridges(played.state)[0].steps == 2
    assert stands(played.state, WALL).words == "four times as fast"


def test_a_reach_the_interpret_step_judged_harder_is_thrown_at_that():
    extreme = derive(facts=facts(challenge=Challenge.EXTREME))
    easy = derive(facts=facts(challenge=Challenge.EASY))

    harder = play(ruled_wall(), Intent(steps=[extreme]), turn=4).resolution.steps[0]
    floor = play(ruled_wall(), Intent(steps=[easy]), turn=4).resolution.steps[0]

    assert "level 5" in harder.reason
    assert "a hard task, level 3" in floor.reason


def test_a_bridge_is_always_thrown_against_the_reach_and_nothing_else():
    """Whatever else the step named in the way, even the character's own doubt."""
    doubt = derive(facts=facts(opposition="his own doubt", inner=True, opposition_ids=["zhao"]))

    settled = play(ruled_wall(), Intent(steps=[doubt]), turn=4).resolution.steps[0]

    assert "against the reach from Genius architect to Aura wall" in settled.reason
    assert settled.roll is not None and settled.opponent_ids == []


def test_a_bridge_that_misses_lifts_nothing_and_its_ground_wont_carry_a_second_try():
    state = ruled_wall()
    unskilled = derive(skill="stonework")

    missed = first(state, Intent(steps=[unskilled]), StepResult.FAILURE)

    assert missed.resolution.steps[0].reason.endswith(
        "The bridge doesn't hold, and the load formula behind the wall's shape won't carry a"
        " second try: the next one needs something new."
    )
    (bridge,) = bridges(missed.state)
    assert bridge.steps == 0 and stands(missed.state, WALL).steps == 1
    again = play(missed.state, Intent(steps=[derive("The load formula")]), turn=5)
    assert again.resolution.steps[0].outcome_class is OutcomeClass.RULED_OUT
    assert again.resolution.steps[0].reason == (
        "The load formula behind the wall's shape was already tried. A bridge has to rest on"
        " something new."
    )
    assert len(bridges(again.state)) == 1


def test_a_bridge_that_falls_just_short_doesnt_hold_either():
    played = first(ruled_wall(), Intent(steps=[derive(skill="stonework")]), StepResult.PARTIAL)

    assert bridges(played.state)[0].steps == 0
    assert "The bridge doesn't hold" in played.resolution.steps[0].reason


def test_new_ground_carries_another_bridge():
    state = first(ruled_wall(), Intent(steps=[derive(skill="stonework")]), StepResult.FAILURE).state

    played = first(
        state, Intent(steps=[derive("her teacher's notes on wards")]), StepResult.SUCCESS, 5
    )

    assert [b.steps for b in bridges(played.state)] == [0, 1]
    assert stands(played.state, WALL).steps == 2


def test_a_bridge_never_lifts_a_thing_past_the_talent_it_starts_from():
    """A knack stays a knack, and a thing at the talent's full pace takes no more bridges."""
    held = first(ruled_wall(), Intent(steps=[derive()]), StepResult.SUCCESS).state

    more = play(held, Intent(steps=[derive("the mason's rule of thirds")]), turn=5)

    assert more.resolution.steps[0].outcome_class is OutcomeClass.RULED_OUT
    assert more.resolution.steps[0].reason == (
        'Aura wall already grows at the full pace of your talent "Genius architect".'
    )
    assert len(bridges(more.state)) == 1


def test_a_bridge_over_the_heart_lifts_only_as_far_as_the_talent_goes():
    heart = derive(heart=True)

    played = first(ruled_wall(), Intent(steps=[heart]), StepResult.SUCCESS)

    assert bridges(played.state)[0].steps == 1  # related to a genius: one step is all there is


def test_one_of_a_kind_carries_a_second_thing_all_the_way_with_three_bridges():
    sight = talent("sight", "Extreme perception", UNIQUE)
    state = ruled_wall(OUTSIDE, sight)
    grounds = ["the flow he can see in it", "a mason's plumb line", "her teacher's notes on wards"]

    for turn, ground in enumerate(grounds, start=4):
        bridge = derive(ground, talent_id="sight")
        state = first(state, Intent(steps=[bridge]), StepResult.SUCCESS, turn).state

    assert stands(state, WALL).words == "eight times as fast"
    assert [b.steps for b in bridges(state)] == [1, 1, 1]


@pytest.mark.parametrize(
    ("bridge", "why"),
    [
        (derive(talent_id="chosen-one"), "You have no talent like that to build on."),
        (
            derive(talent_id="words"),
            'Your weakness "Hopeless with words" is a weakness, and nothing builds on it.',
        ),
        (derive(talent_id="prodigy"), 'Your talent "Prodigy" already covers everything.'),
        (derive("  "), "A bridge has to reach something and rest on something."),
    ],
    ids=["no such talent", "a weakness", "a general talent", "nothing to rest on"],
)
def test_what_a_bridge_cant_be_built_from(bridge, why):
    prodigy = talent("prodigy", "Prodigy", GENIUS, general=True)
    state = talented(ARCHITECT, WORDS, prodigy)

    played = play(state, Intent(steps=[bridge]))

    (settled,) = played.resolution.steps
    assert (settled.outcome_class, settled.reason) == (OutcomeClass.RULED_OUT, why)
    assert settled.roll is None and bridges(played.state) == []


def test_a_bridge_can_reach_a_thing_nobody_ruled_on_yet():
    state = talented(ARCHITECT)

    played = first(state, Intent(steps=[derive()]), StepResult.SUCCESS)

    assert (bridges(played.state)[0].key, stands(played.state, WALL).steps) == (WALL, 1)


def test_a_bridge_reaches_a_technique_of_theirs_by_the_name_the_player_uses():
    state = talented(ARCHITECT)
    bridge = step(
        "measure the blade's edge against the golden section",
        uses=[SheetUse(part=SheetPart.SKILL, ref="architecture")],
        bridge=Bridge(talent_id="architect", what="the blade", rests_on="the golden section"),
    )

    played = first(state, Intent(steps=[bridge]), StepResult.SUCCESS)

    assert bridges(played.state)[0].key == BLADE


def test_the_level_of_a_bridge_is_never_kept_on_the_place():
    """The reach is no thing of the place: nothing is judged there for later (A3)."""
    played = first(ruled_wall(), Intent(steps=[derive()]), StepResult.SUCCESS)

    assert not played.resolution.steps[0].effects.places
    assert all(not p.judged for p in played.state.places.values())


def test_a_bridge_built_in_a_plan_counts_for_the_steps_that_follow():
    state = ruled_wall()
    plan = Intent(steps=[derive(), train(GrowthKind.TECHNIQUE, "Aura wall", 1)])

    for seed in SEEDS:
        played = play(state, plan, seed, 4)
        if played.resolution.steps[0].result is StepResult.SUCCESS:
            break
    else:
        pytest.fail("the bridge never held")

    # Two hours at twice the pace before it, then one more at four times.
    assert played.state.player.sheet.practice[0].effort_s == (2 * 2 + 1 * 4) * 3600
