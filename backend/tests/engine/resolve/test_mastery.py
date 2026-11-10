"""Mastery (A4, G25): a move is the character's from the first time it works, and it grows with
use and practice, never with hours that don't pass.

Decided 2026-11-10 (Miki), from a long story: aura was the heart of the play and was never on the
sheet, a move that worked early on was "never learned" much later, and the quickest thing
practised would have taken thousands of turns at the hours the engine asked for. A move the
engine lets work is recorded at once, at learning, and each use counts toward the next mastery.
"""

from engine import pipeline
from engine.base import HOUR, MINUTE
from engine.contracts import (
    Aim,
    Beat,
    BeatUse,
    BeatVerdict,
    Challenge,
    GrowthKind,
    Intent,
    OutcomeClass,
    Plausibility,
    SheetPart,
    SheetUse,
    Teacher,
    UseSource,
)
from engine.samples import cultivation_world
from engine.state import (
    Character,
    CharacterSheet,
    CostKind,
    Extraordinary,
    LadderPosition,
    Mastery,
    PendingEvent,
    Power,
    PowerAxes,
    PowerAxis,
    PowerCost,
    Practice,
    Prevalence,
    Skill,
    SkillLevel,
    StepResult,
    Technique,
    Trait,
    TraitKind,
    WorldState,
)

from .power_worlds import ctx, play, rng, train
from .worlds import SEEDS, add, facts, power, resolve, step


def technique(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.TECHNIQUE, ref=ref)


def skill(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.SKILL, ref=ref)


def awakened() -> WorldState:
    """Lin Feng with an awakened aura, and a thief of his own realm in the scene."""
    state = cultivation_world()
    state.player.sheet.powers.append(
        Power(
            id="aura",
            name="Aura",
            description="An inner spring of aura that he shapes at will.",
            costs=[PowerCost(kind=CostKind.ENERGY, text="Spends aura.")],
        )
    )
    thief = Character(
        id="thief",
        name="the thief",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2), ladders=[LadderPosition(ladder_id="realms", rung=0)]
        ),
    )
    return add(state, thief)


def knowing(state: WorldState, mastery: Mastery = Mastery.LEARNING, uses: int = 0) -> WorldState:
    """The same, with an aura blade already a technique of his."""
    blade = Technique(id="blade", name="Aura blade", power_id="aura", mastery=mastery, uses=uses)
    state.player.sheet.techniques.append(blade)
    return state


def squire() -> WorldState:
    """Lin where combat aura exists, an hour into learning an Aura Step, with no power of aura
    on his sheet."""
    state = cultivation_world()
    state.bible.extraordinary.append(
        Extraordinary(id="aura", kind="combat aura", prevalence=Prevalence.COMMON)
    )
    state.player.sheet.practice.append(
        Practice(key="technique:aura-step", what="Aura Step", effort_s=HOUR)
    )
    return state


def cut_the_rope(*uses: SheetUse):
    """Nothing pushes back: it simply comes off."""
    return step("cut the rope with an aura blade", uses=list(uses))


def cut_the_thief(*uses: SheetUse):
    """A real contest with the thief, who can push back, so a roll decides it."""
    return step(
        "cut at the thief's hand with an aura blade",
        verb="attack",
        aim=Aim.WOUND,
        target_ids=["thief"],
        axis=PowerAxis.MIGHT,
        uses=list(uses),
        facts=facts(opposition_ids=["thief"], can_respond=True, challenge=Challenge.MODERATE),
    )


def blade_of(state: WorldState) -> Technique:
    return state.player.sheet.technique("blade")


def learned_in(settled) -> list[Technique]:
    """The techniques a settled step's changes hold, new ones and ones that grew."""
    return [t for change in settled.effects.characters for t in change.techniques]


# --- what a move records ---------------------------------------------------------------------


def test_a_technique_saved_before_mastery_was_kept_is_practiced():
    old = Technique.model_validate({"id": "blade", "name": "Aura blade", "power_id": "aura"})

    assert (old.mastery, old.uses) == (Mastery.PRACTICED, 0)


def test_using_a_move_with_nothing_in_the_way_counts_once():
    state = knowing(awakened())

    played = play(state, Intent(steps=[cut_the_rope(technique("blade"))]))

    (settled,) = played.resolution.steps
    assert (settled.outcome_class, settled.roll) == (OutcomeClass.CERTAIN, None)
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.LEARNING, 1)
    assert "grown" not in settled.reason
    assert played.state.player.sheet.growth == []


def test_a_use_a_roll_decided_counts_twice_however_it_went():
    state = knowing(awakened())
    results = set()
    for seed in SEEDS:
        (fight,) = resolve(state, Intent(steps=[cut_the_thief(technique("blade"))]), seed).steps
        assert fight.roll is not None
        (grown,) = learned_in(fight)
        assert (grown.id, grown.mastery, grown.uses) == ("blade", Mastery.LEARNING, 2)
        results.add(fight.result)

    assert results == set(StepResult)  # a miss against real resistance teaches as well


def test_a_move_that_could_not_be_used_counts_nothing():
    state = knowing(awakened())
    state.player.sheet.power("aura").ready_at_personal_s = 10**9

    (settled,) = resolve(state, Intent(steps=[cut_the_rope(technique("blade"))])).steps

    assert settled.reason == "Your Aura hasn't recovered yet."
    assert learned_in(settled) == []


def test_a_step_that_stopped_at_an_empty_reach_never_used_the_move():
    """Reaching for a brick that isn't there ends the step before the blade is ever drawn."""
    state = knowing(awakened())
    reach = Beat(
        text="take a loose brick",
        uses=[
            BeatUse(
                source=UseSource.NEW, thing="a loose brick", plausibility=Plausibility.UNCERTAIN
            )
        ],
    )
    move = step("cut the brick in the air", uses=[technique("blade")], beats=[reach])

    counted = set()
    for seed in SEEDS:
        (settled,) = resolve(state, Intent(steps=[move]), seed).steps
        empty = settled.beats[0].verdict is BeatVerdict.EMPTY
        assert [t.uses for t in learned_in(settled)] == ([] if empty else [1])
        counted.add(empty)

    assert counted == {True, False}


def test_a_turn_counts_once_for_a_move_at_its_best_step():
    """Naming the same move in every step of a plan is one turn's use of it."""
    state = knowing(awakened())
    plan = Intent(
        steps=[
            cut_the_rope(technique("blade")),
            cut_the_rope(technique("blade")),
            cut_the_thief(technique("blade")),
        ]
    )

    played = play(state, plan)

    rope, again, fight = played.resolution.steps
    assert [t.uses for t in learned_in(rope)] == [1]
    assert learned_in(again) == []
    assert [t.uses for t in learned_in(fight)] == [2]  # the fight is worth one more
    assert blade_of(played.state).uses == 2


def test_six_uses_take_a_move_from_learning_to_practiced():
    state = knowing(awakened(), uses=5)

    played = play(state, Intent(steps=[cut_the_rope(technique("blade"))]))

    (settled,) = played.resolution.steps
    assert settled.reason.endswith("Your Aura blade has grown from learning to practiced.")
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.PRACTICED, 0)
    (gain,) = played.state.player.sheet.growth
    assert (gain.what, gain.change, gain.source) == (
        "Aura blade",
        "learning to practiced",
        "use in play",
    )


def test_use_alone_stops_at_second_nature():
    state = knowing(awakened(), Mastery.SECOND_NATURE, 100)

    played = play(state, Intent(steps=[cut_the_thief(technique("blade"))]))

    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (
        Mastery.SECOND_NATURE,
        102,
    )
    assert played.state.player.sheet.growth == []


# --- the moment a move first works -----------------------------------------------------------


def test_a_move_made_with_their_power_starts_at_learning_with_its_first_use_counted():
    state = awakened()

    played = play(state, Intent(steps=[cut_the_rope(power("aura"), technique("aura blade"))]))

    (learned,) = played.state.player.sheet.techniques
    assert (learned.name, learned.style, learned.power_id) == ("Aura blade", "Aura", "aura")
    assert (learned.mastery, learned.uses) == (Mastery.LEARNING, 1)


def test_a_move_made_of_the_worlds_energy_is_theirs_the_first_time_it_works():
    """ "Aura to my feet" worked for a hundred turns and was never on the sheet."""
    state = squire()

    played = play(state, Intent(steps=[step("leap the wall", uses=[technique("aura leap")])]))

    (settled,) = played.resolution.steps
    assert settled.reason.endswith("Aura leap is a technique of yours now.")
    (leap,) = played.state.player.sheet.techniques
    assert (leap.id, leap.name, leap.style) == ("technique-aura-leap", "Aura leap", "combat aura")
    assert (leap.power_id, leap.learned_from) == (None, "their own")
    assert (leap.mastery, leap.uses) == (Mastery.LEARNING, 1)

    # From then on it is on the sheet, whichever part the interpret step files it under.
    for use in (technique("the aura leap"), power("aura leap"), technique("technique-aura-leap")):
        again = play(played.state, Intent(steps=[step("leap the wall", uses=[use])]))
        assert again.resolution.steps[0].drew_on == ["Aura leap"]
        assert [(t.name, t.uses) for t in again.state.player.sheet.techniques] == [("Aura leap", 2)]


def test_the_energy_alone_is_no_move_to_record():
    state = squire()

    played = play(state, Intent(steps=[step("gather it", uses=[power("combat aura")])]))

    assert played.resolution.steps[0].result is StepResult.SUCCESS
    assert played.state.player.sheet.techniques == []


def test_only_a_clean_success_records_a_new_move():
    state = squire()
    state = add(
        state,
        Character(
            id="thief",
            name="the thief",
            location_id="well",
            sheet=CharacterSheet(
                axes=PowerAxes(might=2), ladders=[LadderPosition(ladder_id="realms", rung=0)]
            ),
        ),
    )
    results = set()
    for seed in SEEDS:
        (fight,) = resolve(
            state, Intent(steps=[cut_the_thief(technique("aura blade"))]), seed
        ).steps
        assert bool(learned_in(fight)) == (fight.result is StepResult.SUCCESS)
        results.add(fight.result)

    assert results == set(StepResult)


def test_a_technique_they_are_learning_is_theirs_once_it_works_in_play():
    """Hours never stand between a character and a move the story already let them do."""
    state = cultivation_world()
    state.player.sheet.practice.append(
        Practice(key="technique:rising-palm", what="Rising Palm", effort_s=HOUR)
    )
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    move = step("split the log", uses=[technique("the rising palm, with all my weight")])

    played = play(state, Intent(steps=[move]))

    lin = played.state.player.sheet
    (palm,) = lin.techniques
    assert (palm.name, palm.mastery, palm.uses) == ("Rising Palm", Mastery.LEARNING, 1)
    assert palm.learned_from == "zhao"  # the one who knows it, whose school it is
    assert [(p.key, p.effort_s) for p in lin.practice] == [("technique:rising-palm", 0)]

    # Training it from here is practice, never "about 2 hours of the 450 it takes".
    more = play(played.state, Intent(steps=[train(GrowthKind.TECHNIQUE, "Rising Palm", 3)]))
    assert more.resolution.steps[0].reason == "You already know Rising Palm, so this is practice."
    assert more.state.player.sheet.technique(palm.id).uses == 4


def test_a_technique_of_someone_elses_school_is_not_picked_up_by_improvising_it():
    state = squire()
    state.characters["zhao"].sheet.techniques.append(Technique(id="leap", name="Aura Leap"))

    played = play(state, Intent(steps=[step("leap the wall", uses=[technique("aura leap")])]))

    assert played.resolution.steps[0].result is StepResult.SUCCESS
    assert played.state.player.sheet.techniques == []


def test_a_new_way_to_use_a_power_is_earned_by_its_ruling_never_by_doing_it():
    """A9: a refused idea is earned by training it, with a ruling of its own."""
    state = cultivation_world()
    state.player.sheet.practice.append(
        Practice(
            key="power:time-stop:relative_speed_throws:falling-star-release",
            what="Falling Star Release",
            effort_s=HOUR,
        )
    )

    played = play(
        state, Intent(steps=[step("split the log", uses=[technique("falling star release")])])
    )

    (settled,) = played.resolution.steps
    assert (settled.result, settled.drew_on) == (StepResult.SUCCESS, [])
    assert played.state.player.sheet.techniques == []


def test_a_new_move_starts_two_steps_under_the_skill_it_belongs_to():
    """A master swordsman's new cut starts at skilled, not as a beginner's."""
    starts = {}
    for level in (None, SkillLevel.SKILLED, SkillLevel.EXPERT, SkillLevel.MASTER):
        state = awakened()
        if level is not None:
            state.player.sheet.skills.append(Skill(name="swordsmanship", level=level))
        uses = [power("aura"), technique("aura blade"), skill("swordsmanship")]
        played = play(state, Intent(steps=[cut_the_rope(*uses)]))
        (learned,) = played.state.player.sheet.techniques
        starts[level] = learned.mastery

    assert starts == {
        None: Mastery.LEARNING,
        SkillLevel.SKILLED: Mastery.LEARNING,
        SkillLevel.EXPERT: Mastery.PRACTICED,
        SkillLevel.MASTER: Mastery.SKILLED,
    }


def test_a_technique_named_in_more_words_is_that_technique():
    """ "A long aura blade, thin as a hair" is their Aura blade, not a second technique."""
    state = knowing(awakened())

    played = play(
        state,
        Intent(steps=[cut_the_rope(technique("a long aura blade, thin as a hair"))]),
    )

    assert played.resolution.steps[0].drew_on == ["Aura", "Aura blade"]
    assert [(t.name, t.uses) for t in played.state.player.sheet.techniques] == [("Aura blade", 1)]


def test_a_move_that_names_a_technique_of_theirs_counts_as_using_it():
    """Filed as a power, an aura blade plays as the aura at work, and it is still their blade."""
    state = knowing(awakened())

    played = play(state, Intent(steps=[cut_the_rope(power("aura blade"))]))

    assert [(t.name, t.uses) for t in played.state.player.sheet.techniques] == [("Aura blade", 1)]


def test_a_power_named_by_its_id_is_the_power_and_no_new_move():
    """An id is no move's name, however the interpret step joins its words."""
    state = awakened()
    state.player.sheet.power("aura").id = "pw-aura"

    for ref in ("pw-aura", "pw_aura", "PW aura"):
        played = play(state, Intent(steps=[cut_the_rope(power(ref))]))
        assert played.resolution.steps[0].drew_on == ["Aura"], ref
        assert played.state.player.sheet.techniques == [], ref


def test_a_one_word_technique_is_not_every_move_that_holds_the_word():
    """An "aura strike" is no plain Strike."""
    state = awakened()
    state.player.sheet.techniques.append(Technique(id="strike", name="Strike"))

    played = play(state, Intent(steps=[cut_the_rope(technique("aura strike"))]))

    names = [(t.name, t.uses) for t in played.state.player.sheet.techniques]
    assert names == [("Strike", 0), ("Aura strike", 1)]


# --- a technique learned by training ---------------------------------------------------------


def nearly_there(level: SkillLevel | None = None) -> WorldState:
    """Lin an hour short of a Rising Palm he has been training with Zhao, who knows it."""
    state = cultivation_world()
    state.player.sheet.practice.append(
        Practice(key="technique:rising-palm", what="Rising Palm", effort_s=149 * HOUR)
    )
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    if level is not None:
        state.player.sheet.skills.append(Skill(name="palm fighting", level=level))
    return state


def palm_lesson(hours: float = 2):
    lesson = train(
        GrowthKind.TECHNIQUE, "Rising Palm", hours, teacher=Teacher.MASTER, teacher_id="zhao"
    )
    return lesson.model_copy(update={"uses": [skill("palm fighting")]})


def test_a_technique_trained_all_the_way_through_is_practiced():
    played = play(nearly_there(), Intent(steps=[palm_lesson()]))

    (settled,) = played.resolution.steps
    assert settled.reason.endswith("You learn Rising Palm.")
    (palm,) = played.state.player.sheet.techniques
    assert (palm.mastery, palm.uses) == (Mastery.PRACTICED, 0)


def test_a_masters_trained_technique_starts_where_their_skill_puts_it():
    played = play(nearly_there(SkillLevel.MASTER), Intent(steps=[palm_lesson()]))

    (palm,) = played.state.player.sheet.techniques
    assert palm.mastery is Mastery.SKILLED


def test_a_move_copied_at_a_glance_starts_where_the_gift_puts_a_new_move():
    """A copycat has the move at once, and has it at practiced, as the gifted have a new move."""
    state = cultivation_world()
    state.player.sheet.traits.append(Trait(name="copycat eyes", kind=TraitKind.GIFT))
    state.characters["zhao"].sheet.techniques.append(Technique(id="palm", name="Rising Palm"))
    watch = train(
        GrowthKind.TECHNIQUE, "Rising Palm", 0.1, teacher=Teacher.WATCHING, teacher_id="zhao"
    )

    played = play(state, Intent(steps=[watch]))

    assert "just by watching" in played.resolution.steps[0].reason
    (palm,) = played.state.player.sheet.techniques
    assert (palm.mastery, palm.uses) == (Mastery.PRACTICED, 0)


def test_a_technique_a_plan_taught_is_theirs_for_the_rest_of_it():
    """Learned in the morning and used in the afternoon: one technique, with that use counted."""
    plan = Intent(
        steps=[
            palm_lesson(),
            step("split the log", uses=[technique("rising palm")]),
            train(GrowthKind.TECHNIQUE, "Rising Palm", 2),
        ]
    )

    played = play(nearly_there(), plan)

    lesson, use, practice = played.resolution.steps
    assert use.result is StepResult.SUCCESS and "technique of yours now" not in use.reason
    assert practice.reason == "You already know Rising Palm, so this is practice."
    (palm,) = played.state.player.sheet.techniques
    assert (palm.mastery, palm.uses, palm.learned_from) == (Mastery.PRACTICED, 3, "zhao")


# --- practice ---------------------------------------------------------------------------------


def practising(hours: float, **kw):
    return Intent(steps=[train(GrowthKind.TECHNIQUE, "Aura blade", hours, **kw)])


def test_an_hour_of_practice_counts_as_a_use():
    state = knowing(awakened())

    played = play(state, practising(3))

    (settled,) = played.resolution.steps
    assert settled.reason == "You already know Aura blade, so this is practice."
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.LEARNING, 3)


def test_a_few_minutes_of_practice_count_as_one_use():
    state = knowing(awakened())

    played = play(state, practising(10 * MINUTE / HOUR))

    assert blade_of(played.state).uses == 1


def test_practice_beside_a_master_counts_double():
    state = knowing(awakened())

    played = play(state, practising(3, teacher=Teacher.MASTER, teacher_id="zhao"))

    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.PRACTICED, 0)


def test_a_long_stretch_of_practice_climbs_and_carries_on():
    """Twenty hours at it: twelve count in full and the rest a third, fourteen uses in all."""
    state = knowing(awakened())

    played = play(state, practising(20))

    (settled,) = played.resolution.steps
    assert played.interrupted_by is None
    assert settled.reason.endswith("Your Aura blade has grown from learning to practiced.")
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.PRACTICED, 8)
    (gain,) = played.state.player.sheet.growth
    assert (gain.change, gain.source) == ("learning to practiced", "practice")


def test_practice_counts_on_top_of_the_turns_use():
    """A fight with the blade and then an hour's practice of it are a use each way."""
    state = knowing(awakened())
    plan = Intent(
        steps=[
            cut_the_rope(technique("blade")),
            train(GrowthKind.TECHNIQUE, "Aura blade", 2),
        ]
    )

    played = play(state, plan)

    assert blade_of(played.state).uses == 3


def test_a_move_learned_in_this_plan_can_be_practised_in_it():
    state = awakened()
    plan = Intent(
        steps=[
            cut_the_rope(power("aura"), technique("aura blade")),
            train(GrowthKind.TECHNIQUE, "Aura blade", 2),
        ]
    )

    played = play(state, plan)

    first, second = played.resolution.steps
    assert second.reason == "You already know Aura blade, so this is practice."
    (learned,) = played.state.player.sheet.techniques
    assert (learned.name, learned.uses) == ("Aura blade", 3)


def test_practice_cut_short_counts_the_time_it_ran():
    state = knowing(awakened())
    state.pending_events["visitor"] = PendingEvent(
        id="visitor",
        kind="director.visit",
        title="Zhao bangs on the door.",
        due_s=3 * HOUR,
        needs_player=True,
    )

    resolution = resolve(state, practising(10))
    played = pipeline.play_out(state, resolution, ctx(), rng())

    assert played.interrupted_by is not None and played.resolution.steps[0].interrupted
    assert played.rejected == ()
    assert blade_of(played.state).uses == 3


# --- talent sets the pace ---------------------------------------------------------------------


def gifted(state: WorldState, name: str = "Genius", kind: TraitKind = TraitKind.GIFT):
    state.player.sheet.traits.append(Trait(name=name, kind=kind))
    return state


def test_a_genius_needs_a_quarter_of_the_uses():
    """Two uses where an ordinary character needs six: one fight takes the blade to practiced."""
    state = gifted(knowing(awakened()))

    played = play(state, Intent(steps=[cut_the_thief(technique("blade"))]))

    (settled,) = played.resolution.steps
    assert settled.reason.endswith("Your Aura blade has grown from learning to practiced.")
    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.PRACTICED, 0)


def test_a_genius_takes_a_move_to_second_nature_in_fourteen_uses():
    state = gifted(knowing(awakened()))
    seen = []
    for turn in range(14):
        played = play(state, Intent(steps=[cut_the_rope(technique("blade"))]), turn=turn + 3)
        state = played.state
        seen.append(blade_of(state).mastery)

    assert seen[:1] == [Mastery.LEARNING] and seen[1] is Mastery.PRACTICED
    assert seen[5] is Mastery.SKILLED and seen[12] is Mastery.SKILLED
    assert seen[13] is Mastery.SECOND_NATURE


def test_a_geniuss_new_move_starts_at_practiced():
    played = play(
        gifted(awakened()), Intent(steps=[cut_the_rope(power("aura"), technique("aura blade"))])
    )

    (learned,) = played.state.player.sheet.techniques
    assert (learned.mastery, learned.uses) == (Mastery.PRACTICED, 1)


def test_an_hour_of_a_geniuss_practice_counts_four():
    """Four uses an hour against a need of two, four and eight: an afternoon masters the move."""
    state = gifted(knowing(awakened()))

    played = play(state, practising(4))

    assert blade_of(played.state).mastery is Mastery.SECOND_NATURE


def test_a_slow_learner_needs_twice_the_uses():
    state = gifted(knowing(awakened(), uses=5), "Slow learner", TraitKind.FLAW)

    played = play(state, Intent(steps=[cut_the_rope(technique("blade"))]))

    assert (blade_of(played.state).mastery, blade_of(played.state).uses) == (Mastery.LEARNING, 6)


def test_a_gift_for_learning_is_read_in_spanish_and_catalan():
    """A sheet written in the story's language names its gifts in it (S10)."""
    for name in ("Genio de la espada", "Un prodigio", "Superdotada", "Geni", "Talentós"):
        state = gifted(knowing(awakened()), name)
        played = play(state, Intent(steps=[cut_the_thief(technique("blade"))]))
        assert blade_of(played.state).mastery is Mastery.PRACTICED, name
    for name in ("Sin talento", "Sense talent"):
        state = gifted(knowing(awakened(), uses=5), name, TraitKind.FLAW)
        played = play(state, Intent(steps=[cut_the_rope(technique("blade"))]))
        assert blade_of(played.state).mastery is Mastery.LEARNING, name
