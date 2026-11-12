"""W1, W4, N6: a bout both sides agreed to is not an attack (`engine.resolve.bouts`).

Lin spars with Elder Bai at the well. The interpret step proposes the terms; code keeps them for
the whole bout, holds every blow to them and decides when one went beyond them. From Miki's long
story (2026-11), where every blow of a lesson with a mentor was recorded as an attack on him.
"""

from collections import Counter

import pytest

from engine.contracts import (
    ActionKind,
    Aim,
    Harm,
    Intent,
    OutcomeClass,
    SheetPart,
    SheetUse,
    StandingAction,
)
from engine.resolve import bouts
from engine.state import (
    Attitude,
    Bout,
    Creature,
    Encounter,
    EncounterKind,
    Grudge,
    Health,
    PassingState,
    PowerAxis,
    StepResult,
    Terms,
    WorldState,
)

from .worlds import SEEDS, add, besides_rank, disciple, facts, resolve, sect, step, strike

NO_HARM, WOUNDS, DEATH = Terms.NO_HARM, Terms.WOUNDS, Terms.DEATH


def dojo(rung: int = 0, affinity: int = 40) -> WorldState:
    """Lin with Elder Bai, who is fond of him unless `affinity` says otherwise."""
    state = add(sect(), disciple("bai", "Elder Bai", rung=rung))
    state.characters["bai"].sheet.disposition.attitudes["lin"] = Attitude(affinity=affinity)
    return state


def in_bout(state: WorldState, terms: Terms = NO_HARM, *partners: str) -> WorldState:
    """The bout already on, from an earlier turn."""
    with_ids = list(partners or ["bai"])
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=with_ids,
        started_turn=2,
        started_s=0,
        bout=Bout(terms=terms, with_ids=with_ids),
    )
    return state


def spar(target: str = "bai", aim: Aim = Aim.SUBDUE, terms: Terms | None = NO_HARM, **more):
    """A blow at a sparring partner, as the interpret step proposes it."""
    return step(
        f"trade blows with {target}",
        verb="spar",
        aim=aim,
        target_ids=[target],
        axis=PowerAxis.MIGHT,
        facts=facts(opposition_ids=[target], can_respond=True, terms=terms, **more),
    )


def circle(meant: Aim | None = None):
    """A step of the bout that strikes nobody, so only the partner's answer is in play."""
    return step("circle, looking for an opening", verb="circle", facts=facts(foes_mean=meant))


def one(state: WorldState, *steps, seed: int = 0):
    return resolve(state, Intent(steps=list(steps)), seed).steps[0]


def bout_deed(settled):
    """The one deed a blow inside the terms proposes: the bout itself."""
    [deed] = settled.deeds
    assert (deed.kind, deed.victim_ids, deed.severity) == ("bout", [], 1)
    assert not deed.broke_terms
    return deed


# --- the terms -------------------------------------------------------------------------------


def test_each_terms_accepts_its_own_worst_and_nothing_beyond():
    assert [bouts.allows(NO_HARM, a) for a in (Aim.NONE, Aim.SUBDUE, Aim.WOUND, Aim.KILL)] == [
        True,
        True,
        False,
        False,
    ]
    assert bouts.allows(WOUNDS, Aim.WOUND) and not bouts.allows(WOUNDS, Aim.KILL)
    assert bouts.allows(DEATH, Aim.KILL)
    assert bouts.held(NO_HARM, Aim.KILL) is Aim.SUBDUE
    assert bouts.held(WOUNDS, Aim.KILL) is Aim.WOUND
    assert bouts.held(WOUNDS, Aim.SUBDUE) is Aim.SUBDUE  # a milder blow stays as it is
    assert bouts.milder(WOUNDS, DEATH) is WOUNDS
    assert bouts.milder(WOUNDS, NO_HARM) is NO_HARM
    assert bouts.milder(DEATH, None) is DEATH


def test_ill_will_is_a_grudge_or_real_dislike_by_their_true_feelings():
    bai = dojo().characters["bai"]
    assert not bouts.bears_ill_will(bai, "lin")
    assert not bouts.bears_ill_will(bai, "a stranger")
    attitudes = bai.sheet.disposition.attitudes
    attitudes["lin"] = Attitude(affinity=bouts.ILL_WILL)
    assert bouts.bears_ill_will(bai, "lin")
    # C6: a smile over a grudge is still a grudge.
    attitudes["lin"] = Attitude(affinity=30, grudges=[Grudge(reason="Lin shamed him")])
    assert bouts.bears_ill_will(bai, "lin")
    attitudes["lin"] = Attitude(affinity=-60, apparent_affinity=50)
    assert bouts.bears_ill_will(bai, "lin")


# --- inside the terms ------------------------------------------------------------------------


@pytest.mark.parametrize("aim", [Aim.SUBDUE, Aim.WOUND, Aim.KILL])
def test_a_sparring_blow_hurts_nobody_whatever_aim_was_proposed_for_it(aim):
    """A blow of a lesson read as a wounding, or a killing, is still a blow of the lesson."""
    state = dojo()
    results = set()
    for seed in SEEDS:
        settled = one(state, spar(aim=aim), seed=seed)
        results.add(settled.result)
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"])
        assert not settled.broke_terms
        # Neither of them is hurt or left helpless, however the exchange went.
        assert besides_rank(settled) == []
        deed = bout_deed(settled)
        assert (deed.target_ids, deed.terms) == (["bai"], NO_HARM)
        for peril in settled.perils:
            assert (peril.aim, peril.terms) == (Aim.SUBDUE, NO_HARM)
            assert peril.harm in (Harm.NONE, Harm.SUBDUED)
    assert results == set(StepResult)


def test_a_mentor_far_above_them_brings_them_down_unhurt():
    state = dojo(rung=3)
    found = Counter()
    for seed in SEEDS:
        settled = one(state, spar(), seed=seed)
        [peril] = settled.perils
        thrown = peril.roll.throw
        assert not thrown.deadly
        assert thrown.against == "Elder Bai strikes back, pulling the blow."
        found[peril.harm] += 1
        if peril.harm is Harm.SUBDUED:
            assert peril.reason.endswith("You are brought down, unhurt.")
        assert besides_rank(settled) == []
        bout_deed(settled)
    assert set(found) <= {Harm.SUBDUED, Harm.NONE}
    assert found[Harm.SUBDUED] > 0.9 * SEEDS.stop


def test_a_blow_that_only_touches_them_is_told_as_pulled():
    reasons = {
        peril.reason.rsplit(". ", 1)[-1]
        for seed in SEEDS
        for peril in one(in_bout(dojo()), circle(), seed=seed).perils
        if peril.result is StepResult.PARTIAL
    }

    assert reasons == {"The blow touches you, pulled."}


def test_the_terms_hold_for_the_whole_bout_though_later_steps_leave_them_out():
    """Code keeps them on the encounter, so the fifth blow of a lesson is still the lesson's."""
    state = in_bout(dojo())
    for seed in SEEDS:
        settled = one(state, strike("bai"), seed=seed)  # "cut down", meant to kill, no terms
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"])
        assert besides_rank(settled) == []
        bout_deed(settled)


def test_in_one_plan_the_first_blow_s_terms_cover_the_blows_after_it():
    state = dojo()
    plan = Intent(steps=[spar(), spar(aim=Aim.WOUND, terms=None)])
    both = 0
    for seed in SEEDS:
        steps = resolve(state, plan, seed).steps
        if len(steps) < 2:
            continue
        both += 1
        assert [s.bout for s in steps] == [Bout(terms=NO_HARM, with_ids=["bai"])] * 2
        assert all(besides_rank(s) == [] for s in steps)
    assert both


def practice(shape: str, **more):
    """A practice blow in the shapes an interpret step gives one. The first live lesson
    (2026-11-11) had one told as an attack that aims no harm and names no target, with the
    mentor only what stands in its way, and it was filed as an attack on him."""
    given = facts(opposition_ids=["bai"], can_respond=True, **more)
    text = "come at Elder Bai with the practice sword"
    if shape == "in the way":
        return step(text, verb="attack", axis=PowerAxis.MIGHT, facts=given)
    if shape == "no harm aimed":
        return step(text, verb="attack", target_ids=["bai"], axis=PowerAxis.MIGHT, facts=given)
    if shape == "an exchange":
        return step(text, verb="lunge", axis=PowerAxis.MIGHT, facts=given)
    assert shape == "harm at no target"
    return step(text, verb="swing", aim=Aim.WOUND, axis=PowerAxis.MIGHT, facts=given)


SHAPES = ["in the way", "no harm aimed", "an exchange", "harm at no target"]


@pytest.mark.parametrize("shape", SHAPES)
def test_a_practice_blow_is_a_blow_of_the_bout_however_it_was_read(shape):
    """Whoever a step fights is who it is a blow at, whether they are its targets or stand in
    its way, and whatever it aims to do."""
    state = in_bout(dojo())
    for seed in SEEDS:
        settled = one(state, practice(shape), seed=seed)
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"]), seed
        assert besides_rank(settled) == []
        assert bout_deed(settled).target_ids == ["bai"]
        assert (settled.encounter, settled.opponent_ids) == (EncounterKind.FIGHT, ["bai"])


@pytest.mark.parametrize("shape", SHAPES)
def test_a_bout_begins_with_a_practice_blow_however_it_was_read(shape):
    state = dojo()
    for seed in SEEDS:
        settled = one(state, practice(shape, terms=NO_HARM), seed=seed)
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"]), seed
        assert bout_deed(settled).terms is NO_HARM
        # The fight that keeps the bout's terms begins with it, though it aimed no harm.
        assert (settled.encounter, settled.opponent_ids) == (EncounterKind.FIGHT, ["bai"])


def test_another_deed_done_to_a_sparring_partner_is_still_that_deed():
    """Only blows come under the terms. An insult, a theft or a healing in the middle of a
    bout is the deed it is."""
    state = in_bout(dojo())
    there = facts(opposition_ids=["bai"], can_respond=True)
    insult = step("call Elder Bai a fraud", ActionKind.INSTANT, verb="insult", facts=there)
    steal = step("lift the jade token from Elder Bai's sash", verb="steal", facts=there)
    heal = step("mend Elder Bai's bruised wrist", verb="heal", target_ids=["bai"], facts=there)
    for seed in SEEDS:
        for other in (insult, steal, heal):
            assert not bouts.is_blow(other)
            [deed] = [d for d in one(state, other, seed=seed).deeds if d.actor_id is None]
            assert (deed.kind, deed.terms, deed.target_ids) == (other.verb, None, ["bai"])


def test_a_blow_is_at_whom_it_names_whoever_else_is_said_to_stand_in_its_way():
    """An onlooker the interpret step lists as in the way of a blow at a sparring partner
    doesn't make it an attack on the partner: the blow is at whom it names."""
    state = add(in_bout(dojo()), disciple("wei", "Wei"))
    watched = facts(opposition_ids=["bai", "wei"], can_respond=True)
    for shape in ("no harm aimed", "aimed"):
        aim = Aim.WOUND if shape == "aimed" else Aim.NONE
        blow = step(
            "strike at Elder Bai", verb="strike", aim=aim, target_ids=["bai"], facts=watched
        )
        assert bouts.against(state, "lin", blow) == ["bai"]
        for seed in SEEDS:
            settled = one(state, blow, seed=seed)
            assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"]), (shape, seed)
            assert all(d.kind == "bout" for d in settled.deeds if d.actor_id is None)
    # With no target named, it is a blow at everyone in its way, and Wei is in no bout.
    stray = step("lash out", verb="attack", axis=PowerAxis.MIGHT, facts=watched)
    assert bouts.against(state, "lin", stray) == ["bai", "wei"]
    [mine] = [d for d in one(state, stray).deeds if d.actor_id is None]
    assert (mine.kind, mine.terms, mine.target_ids) == ("attack", None, ["bai", "wei"])


def test_first_blood_accepts_a_wound_and_holds_a_killing_blow_to_one():
    state = dojo()
    worst = {"lin": set(), "bai": set()}
    for seed in SEEDS:
        settled = one(state, spar(aim=Aim.KILL, terms=WOUNDS), seed=seed)
        assert settled.bout == Bout(terms=WOUNDS, with_ids=["bai"])
        for change in besides_rank(settled):
            assert change.status is None and not change.condition.states
            worst[change.id].add(change.condition.health)
        bout_deed(settled)
        assert all((p.aim, p.terms) == (Aim.WOUND, WOUNDS) for p in settled.perils)
    assert worst["bai"] == {Health.HURT, Health.WOUNDED}
    assert worst["lin"] == {Health.HURT, Health.WOUNDED}


def test_a_death_in_a_duel_to_the_death_is_its_own_deed_and_both_accepted_it():
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders[0].rung, lin.sheet.axes.might = 3, 8
    state = add(state, disciple("zhou", "Zhou"))
    duel = strike("zhou", facts=facts(opposition_ids=["zhou"], can_respond=True, terms=DEATH))

    settled = one(state, duel)

    assert settled.result is StepResult.SUCCESS
    assert settled.bout == Bout(terms=DEATH, with_ids=["zhou"])
    [deed] = settled.deeds
    assert (deed.kind, deed.victim_ids, deed.terms) == ("attack", ["zhou"], DEATH)
    assert not deed.broke_terms


def test_dying_in_a_duel_to_the_death_is_the_killer_s_deed_and_both_accepted_it():
    state = in_bout(dojo(rung=3), DEATH)
    dead = 0
    for seed in SEEDS:
        settled = one(state, circle(Aim.KILL), seed=seed)
        [peril] = settled.perils
        assert (peril.aim, peril.terms) == (Aim.KILL, DEATH) and not settled.broke_terms
        if peril.harm is not Harm.DEAD:
            assert settled.deeds == []  # a blow inside the terms is no deed
            continue
        dead += 1
        [deed] = settled.deeds
        assert (deed.actor_id, deed.victim_ids, deed.terms) == ("bai", ["lin"], DEATH)
        assert not deed.broke_terms
    assert dead > 0.9 * SEEDS.stop


def test_a_death_the_terms_never_accepted_is_a_killing_like_any_other():
    """Lin fights to first blood while already dying: the wound that finishes him is a death
    nobody agreed to, though nobody meant to break the terms either."""
    state = in_bout(dojo(rung=3), WOUNDS)
    state.characters["lin"].sheet.condition.health = Health.DYING

    settled = one(state, circle(Aim.WOUND))

    [peril] = settled.perils
    assert (peril.harm, peril.terms) == (Harm.DEAD, WOUNDS) and not settled.broke_terms
    [deed] = settled.deeds
    assert (deed.actor_id, deed.victim_ids, deed.terms) == ("bai", ["lin"], None)


def test_the_terms_only_get_milder_while_the_bout_is_on():
    def after(proposed: Terms | None) -> Terms:
        return one(in_bout(dojo(), WOUNDS), spar(terms=proposed)).bout.terms

    assert after(DEATH) is WOUNDS
    assert after(None) is WOUNDS
    assert after(NO_HARM) is NO_HARM


def test_a_friendly_partner_waits_while_the_character_talks_or_looks_on():
    """The blows of a friendly bout are its exchanges. A question between two of them, or a
    moment standing still, gets no blow in answer unless the interpret step says it does."""
    state = in_bout(dojo(rung=3))
    ask = step(
        "ask Elder Bai how he turned that last cut",
        ActionKind.CONVERSATION,
        60,
        verb="ask",
        target_ids=["bai"],
    )
    for seed in range(40):
        assert one(state, ask, seed=seed).perils == []
        [waited] = resolve(state, Intent(standing=StandingAction.WAIT), seed).steps
        assert waited.perils == [] and waited.deeds == []
        # Told that he presses on, he does, and pulls it.
        pressed = ask.model_copy(update={"facts": facts(foes_mean=Aim.WOUND)})
        [peril] = one(state, pressed, seed=seed).perils
        assert (peril.aim, peril.terms) == (Aim.SUBDUE, NO_HARM)


def test_in_a_duel_that_accepts_wounds_nobody_waits():
    state = in_bout(dojo(rung=3), WOUNDS)

    [waited] = resolve(state, Intent(standing=StandingAction.WAIT)).steps

    [peril] = waited.perils
    assert (peril.aim, peril.terms) == (Aim.WOUND, WOUNDS)
    assert waited.bout == Bout(terms=WOUNDS, with_ids=["bai"]) and waited.deeds == []


# --- who can agree ---------------------------------------------------------------------------


def test_a_fight_in_earnest_never_becomes_a_bout():
    """An attack is never relabelled: once someone was hurt outside any terms, or the terms
    were broken, calling it sparring afterwards changes nothing."""
    state = dojo()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=["bai"],
        started_turn=2,
        started_s=0,
        in_earnest=True,
    )
    hurt = 0
    for seed in SEEDS:
        settled = one(state, spar(aim=Aim.WOUND), seed=seed)
        assert settled.bout is None and not settled.broke_terms
        assert all(d.terms is None and d.kind != "bout" for d in settled.deeds)
        hurt += any(c.id == "bai" for c in settled.effects.characters)
    assert hurt

    # The same inside one plan: a blow that wounds him, and then "let's call it a lesson".
    plan = Intent(steps=[spar(aim=Aim.WOUND, terms=None), spar()])
    later = [s for seed in SEEDS for s in resolve(dojo(), plan, seed).steps[1:]]
    assert later and all(s.bout is None for s in later)


def test_terms_left_out_on_a_first_blow_that_hurt_nobody_can_still_be_agreed():
    """The interpret step forgot the terms once. The fight so far harmed nobody, so the lesson
    is still a lesson from the blow that names them; the first blow stays what it was."""
    state = dojo()
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bai"], started_turn=2, started_s=0
    )

    for seed in range(40):
        settled = one(state, spar(aim=Aim.WOUND), seed=seed)
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"])
        assert besides_rank(settled) == []
        bout_deed(settled)


def test_only_someone_there_and_able_to_answer_can_agree():
    asleep = dojo()
    asleep.characters["bai"].sheet.condition.states.append(PassingState(name="asleep"))
    beast = dojo()
    beast.bible.creatures.append(Creature(id="ape", name="stone ape", tier=2))
    beast.characters["bai"].people_id = "ape"
    away = dojo()
    away.characters["bai"].location_id = "inner-court"
    away.scene.present_ids.remove("bai")

    assert bouts.can_agree(dojo(), dojo().characters["bai"])
    for state in (asleep, beast, away):
        assert not bouts.can_agree(state, state.characters["bai"])
        settled = one(state, spar())
        assert settled.bout is None
        assert all(d.kind != "bout" for d in settled.deeds)


def test_a_second_partner_joins_the_bout_by_taking_up_its_terms():
    state = add(in_bout(dojo()), disciple("wei", "Wei"))

    joined = one(state, spar("wei", aim=Aim.WOUND))
    assert joined.bout == Bout(terms=NO_HARM, with_ids=["bai", "wei"])
    assert besides_rank(joined) == []
    assert bout_deed(joined).target_ids == ["wei"]

    # A blow at them with no terms proposed is no blow of the bout: it is an attack on them.
    for seed in SEEDS:
        outside = one(state, spar("wei", aim=Aim.WOUND, terms=None), seed=seed)
        assert outside.bout is None
        assert all(d.kind != "bout" and d.terms is None for d in outside.deeds)


def test_someone_already_fighting_them_openly_cant_join_the_bout():
    state = add(in_bout(dojo()), disciple("wei", "Wei"))
    state.scene.encounter.opponent_ids.append("wei")  # Wei came at Lin on his own account

    settled = one(state, spar("wei"))

    assert settled.bout is None
    assert all(d.kind != "bout" for d in settled.deeds)


# --- beyond the terms ------------------------------------------------------------------------


def test_a_blow_meant_to_go_beyond_the_terms_is_an_attack_and_ends_the_bout():
    state = in_bout(dojo())
    blow = spar(aim=Aim.KILL, terms=None, breaks_terms=True)
    killed = 0
    for seed in SEEDS:
        settled = one(state, blow, seed=seed)
        assert settled.broke_terms and settled.bout is None
        mine = [d for d in settled.deeds if d.actor_id is None]
        assert [(d.broke_terms, d.terms) for d in mine] == [(True, None)]
        assert mine[0].kind != "bout"
        # Bai's answer is to an open attack now, in kind, and it is no breach of his.
        for peril in settled.perils:
            assert (peril.aim, peril.terms) == (Aim.KILL, None)
        assert not any(d.broke_terms for d in settled.deeds if d.actor_id == "bai")
        killed += any(c.id == "bai" and c.status is not None for c in settled.effects.characters)
    assert killed


def test_a_blow_said_to_maim_goes_beyond_the_terms_though_it_was_given_no_aim():
    """What a blow is out to do is its aim, or failing one what its verb says: a blow the
    interpret step says is meant to maim isn't taken into the bout for want of an aim."""
    state = in_bout(dojo())
    there = facts(opposition_ids=["bai"], can_respond=True, breaks_terms=True)
    gouge = step("drive my fingers at Elder Bai's eyes", verb="maim", facts=there)
    assert bouts.meant(gouge) is Aim.WOUND
    for seed in SEEDS:
        settled = one(state, gouge, seed=seed)
        assert settled.broke_terms and settled.bout is None, seed
        [mine] = [d for d in settled.deeds if d.actor_id is None]
        assert (mine.kind, mine.broke_terms, mine.terms) == ("maim", True, None)
    # The same blow in a duel that accepts wounds is one of the duel's.
    duel = one(in_bout(dojo(), WOUNDS), gouge)
    assert duel.bout is not None and not duel.broke_terms
    # A strike with no aim says nothing beyond a friendly bout's terms.
    tap = step("tap Elder Bai's shoulder with the flat", verb="strike", facts=there)
    assert bouts.meant(tap) is Aim.NONE
    assert not one(state, tap).broke_terms


def test_a_blow_beyond_the_terms_that_met_no_one_broke_nothing():
    """A blow meant to kill, made with a blade the record doesn't hold, is stopped before it is
    tried: nobody was struck at, so the bout stands as it stood and Bai's answer is one of its
    blows, where a blow that did come off is met as the attack it is."""
    bout = Bout(terms=NO_HARM, with_ids=["bai"])
    dagger = SheetUse(part=SheetPart.ITEM, ref="hidden dagger")
    stab = spar(aim=Aim.KILL, terms=None, breaks_terms=True)
    answered = 0
    for seed in SEEDS:
        untried = one(in_bout(dojo()), stab.model_copy(update={"uses": [dagger]}), seed=seed)
        assert untried.outcome_class is OutcomeClass.RULED_OUT, seed
        assert (untried.bout, untried.broke_terms, untried.deeds) == (bout, False, []), seed
        assert all(p.terms is NO_HARM and p.aim is Aim.SUBDUE for p in untried.perils), seed
        answered += bool(untried.perils)
    assert answered


def test_once_broken_the_bout_is_over_whatever_the_next_step_proposes():
    state = in_bout(dojo(rung=1))
    plan = Intent(steps=[spar(aim=Aim.WOUND, terms=None, breaks_terms=True), spar()])
    later = [s for seed in SEEDS for s in resolve(state, plan, seed).steps[1:]]

    assert later and all(s.bout is None and not s.broke_terms for s in later)


def test_meaning_to_break_the_terms_with_a_blow_inside_them_breaks_nothing():
    settled = one(in_bout(dojo()), spar(breaks_terms=True))

    assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"]) and not settled.broke_terms
    bout_deed(settled)


@pytest.mark.parametrize("meant", [None, Aim.WOUND, Aim.KILL])
def test_a_mentor_fond_of_their_student_never_goes_beyond_the_terms(meant):
    """Whatever the interpret step proposed for him: he bears Lin no ill will."""
    state = in_bout(dojo(rung=3))
    for seed in SEEDS:
        settled = one(state, circle(meant), seed=seed)
        [peril] = settled.perils
        assert (peril.aim, peril.terms) == (Aim.SUBDUE, NO_HARM)
        assert not settled.broke_terms
        assert besides_rank(settled) == [] and settled.deeds == []
        # The step struck nobody, and its answer was still a blow of the bout.
        assert settled.bout == Bout(terms=NO_HARM, with_ids=["bai"])


@pytest.mark.parametrize(
    "attitude",
    [Attitude(affinity=-40), Attitude(affinity=20, grudges=[Grudge(reason="Lin shamed him")])],
)
def test_a_rival_with_a_grudge_can_use_a_friendly_bout_as_a_lure(attitude):
    state = in_bout(dojo(rung=3))
    state.characters["bai"].sheet.disposition.attitudes["lin"] = attitude
    dead = 0
    for seed in SEEDS:
        settled = one(state, circle(Aim.KILL), seed=seed)
        [peril] = settled.perils
        assert (peril.aim, peril.terms) == (Aim.KILL, None)
        assert peril.roll.throw.deadly
        assert settled.broke_terms and settled.bout is None
        [deed] = settled.deeds
        assert (deed.actor_id, deed.broke_terms, deed.terms) == ("bai", True, None)
        dead += peril.harm is Harm.DEAD
    assert dead > 0.9 * SEEDS.stop

    # Unless the interpret step says he means it, he keeps to the terms like anyone.
    for seed in range(40):
        held = one(state, circle(None), seed=seed)
        assert [p.terms for p in held.perils] == [NO_HARM] and not held.broke_terms


def test_a_blow_beyond_the_terms_from_one_who_isnt_in_the_bout_breaks_nothing():
    """Wei attacks Lin while he spars with Bai: Wei's blow is an open attack, not a breach."""
    state = add(in_bout(dojo()), disciple("wei", "Wei"))
    state.scene.encounter.opponent_ids.append("wei")
    state.characters["wei"].sheet.disposition.attitudes["lin"] = Attitude(affinity=-60)

    settled = one(state, circle(Aim.KILL))

    [peril] = settled.perils
    assert peril.terms is None and not settled.broke_terms
    assert [d.broke_terms for d in settled.deeds] == [False]
