"""W17: a step that is a move in a romance, ruled by the bond on record and the other's own heart.

Logic first (A2): a kiss with a partner needs no dice, an ask is answered by their heart where it
is surely there or surely not, and only what that leaves open is thrown for. An advance that was
answered moves their heart at their own pace, and the bond comes to the stage the story earned.
"""

import pytest

from engine import bonds, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR
from engine.contracts import ActionKind, Aim, Intent, OutcomeClass, RomanceMove
from engine.samples import farm_world
from engine.state import (
    Attitude,
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Character,
    CharacterSheet,
    Disposition,
    PendingEvent,
    PowerAxis,
    StepResult,
    WorldState,
)

from .worlds import SEEDS, add, ctx, facts, resolve, rng, step

YOU = "tomas"


def neighbour(attraction: int = 0, *, affinity: int = 20, trust: int = 20, age: int | None = 29):
    return Character(
        id="mara",
        name="Mara",
        age=age,
        description="The miller's daughter.",
        location_id="farm",
        known_by=[YOU],
        met_by=[YOU],
        sheet=CharacterSheet(
            disposition=Disposition(
                attitudes={YOU: Attitude(affinity=affinity, trust=trust, attraction=attraction)}
            )
        ),
    )


def world(attraction: int = 0, stage: BondStage | None = None, **who) -> WorldState:
    """Tomas on his farm with Mara, a neighbour, and whatever stands between the two."""
    state = add(farm_world(), neighbour(attraction, **who))
    if stage is not None:
        bond = Bond(id="bond-9", a_id=YOU, b_id="mara", stage=stage, steps=[BondStep(stage=stage)])
        state.bonds[bond.id] = bond
    return state


def to(who: str, text: str, move: RomanceMove | None = None, **kw):
    return step(
        text,
        kw.pop("kind", ActionKind.CONVERSATION),
        kw.pop("duration_s", 600),
        axis=PowerAxis.INFLUENCE,
        target_ids=[who],
        romance=move,
        facts=facts(opposition_ids=[who], can_respond=True),
        **kw,
    )


def flirt(who: str = "mara", **kw):
    """The reading names no move: the step's own words make it an advance."""
    return to(who, f"flirt with {who}", verb="flirt", **kw)


def ask(who: str = "mara"):
    return to(who, "ask her to be with me", RomanceMove.DECLARE, verb="ask")


def propose(who: str = "mara"):
    return to(who, "ask her to marry me", RomanceMove.PROPOSE, verb="propose")


def wed(who: str = "mara"):
    return to(who, "marry her", RomanceMove.WED, verb="marry")


def part(who: str = "mara"):
    return to(who, "tell her it is over", RomanceMove.PART, verb="leave")


def one(state: WorldState, a_step, seed: int = 0):
    return resolve(state, Intent(steps=[a_step]), seed).steps[0]


def seed_for(state: WorldState, a_step, result: StepResult) -> int:
    found = [s for s in SEEDS if one(state, a_step, s).result is result]
    assert found, f"no seed gives {result}"
    return found[0]


def after(state: WorldState, *settled) -> WorldState:
    for done in settled:
        applied = apply_delta(state, done.effects, ctx(), source=DeltaSource.ENGINE)
        assert not applied.rejected
        state = applied.state
    return state


def heart(state: WorldState, who: str = "mara") -> int:
    return state.characters[who].attitude_toward(YOU).attraction


def stage(state: WorldState, who: str = "mara") -> BondStage | None:
    bond = bonds.live(state, YOU, who)
    return bond.stage if bond is not None else None


# --- an advance ------------------------------------------------------------------------------


def test_a_flirt_is_thrown_for_and_a_heart_moves_when_it_is_answered():
    state = world()
    won = one(state, flirt(), seed_for(state, flirt(), StepResult.SUCCESS))
    assert won.roll is not None
    assert "Mara is more drawn to you than before." in won.reason
    told = after(state, won)
    assert heart(told) == bonds.NOTCH
    # The first move opens the romance, and it isn't answered yet.
    assert stage(told) is BondStage.INTEREST


def test_a_flirt_that_misses_moves_no_heart_and_still_makes_it_plain():
    state = world()
    missed = one(state, flirt(), seed_for(state, flirt(), StepResult.FAILURE))
    assert "drawn" not in missed.reason
    told = after(state, missed)
    assert heart(told) == 0
    assert stage(told) is BondStage.INTEREST


def test_a_heart_rests_after_it_moves_for_as_long_as_their_pace_says():
    state = world()
    seed = seed_for(state, flirt(), StepResult.SUCCESS)
    told = after(state, one(state, flirt(), seed))
    rest = bonds.REST_S[bonds.pace("mara")]

    again = seed_for(told, flirt(), StepResult.SUCCESS)
    soon = after(told, one(told, flirt(), again))
    assert heart(soon) == heart(told)

    told.world_s += rest
    later = after(told, one(told, flirt(), seed_for(told, flirt(), StepResult.SUCCESS)))
    assert heart(later) == heart(told) + bonds.NOTCH


def test_one_plan_of_sweet_words_moves_a_heart_once():
    state = world()
    for seed in SEEDS:
        done = resolve(state, Intent(steps=[flirt(), flirt(), flirt()]), seed)
        if len(done.steps) == 3 and all(s.result is StepResult.SUCCESS for s in done.steps):
            break
    else:
        pytest.fail("no seed passes all three")
    assert heart(after(state, *done.steps)) == bonds.NOTCH


def test_a_season_of_courting_counts_for_more_than_a_moment_and_never_for_everything():
    state = world()
    season = flirt(kind=ActionKind.TIME_SKIP, duration_s=90 * DAY)
    told = after(state, one(state, season, seed_for(state, season, StepResult.SUCCESS)))
    assert heart(told) == bonds.NOTCH * bonds.MOST_NOTCHES
    assert heart(told) < bonds.DECLARE_SURE


def test_an_answered_advance_past_the_mark_makes_it_a_courtship():
    state = world(bonds.COURTING_AT - bonds.NOTCH, BondStage.INTEREST)
    won = one(state, flirt(), seed_for(state, flirt(), StepResult.SUCCESS))
    assert "Mara answers it, and the two of you are courting now." in won.reason
    assert stage(after(state, won)) is BondStage.COURTING


def test_someone_drawn_to_them_is_easier_to_move():
    cold = one(world(bonds.DRAWN_AT - 1), flirt())
    drawn = one(world(bonds.DRAWN_AT), flirt())
    assert "Mara is drawn to you" in drawn.reason
    assert "is drawn to you" not in cold.reason
    assert drawn.roll.throw.number < cold.roll.throw.number


def test_nobody_throws_to_kiss_their_own_wife():
    state = farm_world()
    state.scene.present_ids = [YOU, "ilse"]
    kiss = to("ilse", "kiss Ilse", verb="kiss", kind=ActionKind.INSTANT, duration_s=5)
    done = one(state, kiss)
    assert (done.outcome_class, done.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert done.roll is None
    assert done.reason.startswith("You and Ilse Weller are married: nothing stands in the way.")


def test_a_kiss_with_a_partner_whose_heart_has_gone_is_thrown_for_again():
    state = world(bonds.TENDER_SURE - 1, BondStage.TOGETHER)
    kiss = to("mara", "kiss Mara", verb="kiss")
    assert one(state, kiss).roll is not None


def test_beyond_a_kiss_takes_a_partner_or_someone_surely_drawn():
    night = to("mara", "make love to Mara", verb="make love", kind=ActionKind.REST)
    stranger = one(world(bonds.INTIMATE_NO - 1), night)
    assert stranger.outcome_class is OutcomeClass.RULED_OUT
    assert stranger.reason.startswith("Mara's heart isn't there.")
    open_ = one(world(bonds.INTIMATE_NO), night)
    assert open_.roll is not None
    sure = one(world(bonds.INTIMATE_SURE), night)
    assert (sure.outcome_class, sure.roll) == (OutcomeClass.CERTAIN, None)
    partner = one(world(bonds.INTIMATE_PARTNER, BondStage.TOGETHER), night)
    assert (partner.outcome_class, partner.roll) == (OutcomeClass.CERTAIN, None)


# --- courting an event cuts short (E7) -------------------------------------------------------


def cut_at(state: WorldState, due_s: int) -> WorldState:
    """The world with something that needs the player due `due_s` from now."""
    state = state.model_copy(deep=True)
    knock = PendingEvent(id="knock", kind="test", due_s=state.world_s + due_s, needs_player=True)
    state.pending_events[knock.id] = knock
    return state


def a_season(state: WorldState, result: StepResult = StepResult.SUCCESS):
    """Ninety days of courting, as resolve settles the whole of it."""
    season = flirt(kind=ActionKind.TIME_SKIP, duration_s=90 * DAY)
    seed = seed_for(state, season, result)
    return resolve(state, Intent(steps=[season]), seed), seed


def test_courting_cut_short_keeps_what_the_time_it_ran_earned():
    rest = bonds.REST_S[bonds.pace("mara")]
    state = cut_at(world(), 3 * rest + HOUR)
    whole, seed = a_season(state)
    assert "the two of you are courting now" in whole.steps[0].reason

    played = pipeline.play_out(state, whole, ctx(), rng(seed))

    (courted,) = played.resolution.steps
    assert courted.interrupted and courted.duration_s <= 3 * rest + HOUR
    times = courted.duration_s // rest
    # Her heart moved each time it had rested while the courting ran, and no more than that.
    assert heart(played.state) == bonds.NOTCH * times < bonds.NOTCH * bonds.MOST_NOTCHES
    assert not played.rejected
    if times == 3:  # nothing of the valley's own stopped it sooner
        assert stage(played.state) is BondStage.COURTING
        assert "Mara is more drawn to you than before." in courted.reason
        assert "the two of you are courting now" in courted.reason
        moved = played.state.characters["mara"].attitude_toward(YOU).heart_moved_s
        assert moved == played.state.world_s
    assert times == 3 or bonds.NOTCH * times < bonds.COURTING_AT


def test_courting_cut_short_before_a_heart_could_move_didnt_happen():
    rest = bonds.REST_S[bonds.pace("mara")]
    state = cut_at(world(), rest - HOUR)
    whole, seed = a_season(state)

    played = pipeline.play_out(state, whole, ctx(), rng(seed))

    (courted,) = played.resolution.steps
    assert courted.interrupted
    assert heart(played.state) == 0 and not played.state.bonds.keys() - {"bond-1"}
    assert "drawn" not in courted.reason and "courting" not in courted.reason


def test_courting_that_only_half_came_off_keeps_half_when_cut_short():
    rest = bonds.REST_S[bonds.pace("mara")]
    state = cut_at(world(), 2 * rest + HOUR)
    half, seed = a_season(state, StepResult.PARTIAL)

    played = pipeline.play_out(state, half, ctx(), rng(seed))

    (courted,) = played.resolution.steps
    times = courted.duration_s // rest
    assert heart(played.state) == (bonds.NOTCH // 2) * times
    # Half an answer makes it no courtship, however far her heart has come.
    assert stage(played.state) in (None, BondStage.INTEREST)


def test_only_an_advance_that_was_answered_is_kept_for_a_step_cut_short():
    state = world(bonds.DECLARE_SURE, BondStage.COURTING)
    assert one(state, ask()).wooing is None  # an ask is one moment: cut short, it didn't happen
    missed = one(world(), flirt(), seed_for(world(), flirt(), StepResult.FAILURE))
    assert missed.wooing is None
    won = one(world(), flirt(), seed_for(world(), flirt(), StepResult.SUCCESS))
    assert won.wooing.other_id == "mara" and won.wooing.whole
    assert won.wooing.said == ["Mara is more drawn to you than before."]


# --- asking ----------------------------------------------------------------------------------


def test_an_ask_their_heart_isnt_there_for_is_turned_down_with_no_throw():
    state = world(bonds.DECLARE_NO - 1)
    done = one(state, ask())
    assert (done.outcome_class, done.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert done.roll is None
    assert done.reason == "Mara's heart isn't there yet."
    told = after(state, done)
    assert stage(told) is BondStage.INTEREST  # asked, and not answered with a yes
    assert heart(told) == bonds.DECLARE_NO - 1


def test_an_ask_their_heart_is_surely_there_for_is_a_yes_with_no_throw():
    state = world(bonds.DECLARE_SURE, BondStage.COURTING)
    done = one(state, ask())
    assert (done.outcome_class, done.result) == (OutcomeClass.CERTAIN, StepResult.SUCCESS)
    assert done.roll is None
    assert done.reason == "Mara wants this too. You and Mara are together now."
    assert stage(after(state, done)) is BondStage.TOGETHER


def test_an_ask_in_between_is_thrown_for():
    state = world(bonds.DECLARE_NO, BondStage.COURTING)
    yes = one(state, ask(), seed_for(state, ask(), StepResult.SUCCESS))
    assert yes.roll is not None
    assert stage(after(state, yes)) is BondStage.TOGETHER

    no = one(state, ask(), seed_for(state, ask(), StepResult.FAILURE))
    assert "Mara says no, and it sets things back between you." in no.reason
    told = after(state, no)
    assert stage(told) is BondStage.COURTING
    # Asked too soon, it sets things back, so asking again and again only digs the hole.
    assert heart(told) == bonds.DECLARE_NO - bonds.TURNED_DOWN
    assert one(told, ask()).outcome_class is OutcomeClass.RULED_OUT


def test_a_yes_makes_a_couple_of_two_who_were_only_interested():
    state = world(bonds.DECLARE_SURE)
    told = after(state, one(state, ask()))
    bond = bonds.live(told, YOU, "mara")
    assert [s.stage for s in bond.steps] == [BondStage.INTEREST, BondStage.TOGETHER]
    assert bond.steps[-1].how == "Tomas Weller asked, and Mara said yes."
    assert bond.steps[-1].by_id == YOU


def test_asking_someone_they_are_already_with_changes_nothing():
    state = world(50, BondStage.TOGETHER)
    done = one(state, ask())
    assert done.reason == "You and Mara are together already."
    assert done.effects.bonds == []


def test_a_promise_is_asked_of_a_partner():
    courting = one(world(100, BondStage.COURTING), propose())
    assert courting.outcome_class is OutcomeClass.RULED_OUT
    assert courting.reason == "You and Mara aren't together."

    not_yet = one(world(bonds.PROPOSE_NO - 1, BondStage.TOGETHER), propose())
    assert not_yet.reason == "Mara's heart isn't there yet."

    state = world(bonds.PROPOSE_SURE, BondStage.TOGETHER)
    yes = one(state, propose())
    assert yes.reason == "Mara wants this too. You and Mara are promised to each other now."
    assert stage(after(state, yes)) is BondStage.PROMISED

    between = world(bonds.PROPOSE_NO, BondStage.TOGETHER)
    assert one(between, propose()).roll is not None


def test_a_wedding_takes_two_who_are_promised():
    together = one(world(100, BondStage.TOGETHER), wed())
    assert together.outcome_class is OutcomeClass.RULED_OUT
    assert together.reason == "You and Mara aren't promised to each other."

    state = world(60, BondStage.PROMISED)
    done = one(state, wed())
    assert (done.outcome_class, done.roll) == (OutcomeClass.CERTAIN, None)
    assert done.reason.endswith("You and Mara are married now.")
    assert stage(after(state, done)) is BondStage.MARRIED


def test_a_plan_can_ask_and_wed_in_one_go():
    """The later steps of a plan see what its earlier ones made of the romance."""
    state = world(bonds.PROPOSE_SURE, BondStage.TOGETHER)
    done = resolve(state, Intent(steps=[propose(), wed()]))
    assert [s.result for s in done.steps] == [StepResult.SUCCESS, StepResult.SUCCESS]
    assert stage(after(state, *done.steps)) is BondStage.MARRIED


# --- ending it -------------------------------------------------------------------------------


def test_ending_it_is_always_theirs_to_do_and_costs_what_the_other_felt():
    state = world(90, BondStage.MARRIED, affinity=60, trust=60)
    done = one(state, part())
    assert (done.outcome_class, done.roll) == (OutcomeClass.CERTAIN, None)
    assert done.reason == "Ending it is yours to do. It is over between you and Mara."
    told = after(state, done)
    assert stage(told) is None
    over = bonds.last_over(told, YOU, "mara")
    assert (over.stage, over.end) == (BondStage.OVER, BondEnd.PARTED)
    felt = told.characters["mara"].attitude_toward(YOU)
    assert (felt.affinity, felt.trust) == (60 - bonds.PARTED_COUPLE, 60 - bonds.PARTED_COUPLE)
    # Getting back together has to be won again.
    assert felt.attraction == 90 - bonds.PARTED_HEART_COUPLE
    assert one(told, ask()).roll is not None


def test_there_is_nothing_to_end_where_nothing_stands():
    done = one(world(80), part())
    assert done.outcome_class is OutcomeClass.RULED_OUT
    assert done.reason == "There is nothing between you and Mara to end."
    assert done.effects.bonds == []


def test_a_romance_that_starts_again_is_a_new_bond():
    state = world(bonds.DECLARE_SURE, BondStage.TOGETHER)
    told = after(state, one(state, part()))
    told.characters["mara"].attitude_toward(YOU).attraction = bonds.DECLARE_SURE
    again = after(told, one(told, ask()))
    assert stage(again) is BondStage.TOGETHER
    assert len([b for b in again.bonds.values() if b.holds("mara")]) == 2


# --- a heart that is closed -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "reason"),
    [
        ({"affinity": -bonds.WARM_AT}, "Mara wants nothing of the kind from you."),
        ({"fear": bonds.AFRAID_AT}, "Mara is too afraid of you for anything to be freely given."),
    ],
)
def test_nothing_moves_someone_who_wants_none_of_it_or_is_too_afraid(who, reason):
    state = world(90)
    felt = state.characters["mara"].attitude_toward(YOU)
    for field, value in who.items():
        setattr(felt, field, value)
    for move in (flirt(), ask()):
        done = one(state, move)
        assert (done.outcome_class, done.roll) == (OutcomeClass.RULED_OUT, None)
        assert done.reason == reason


def test_family_is_never_drawn_that_way():
    state = world(90)
    state.characters["mara"].parent_ids = [YOU]
    done = one(state, flirt())
    assert done.outcome_class is OutcomeClass.RULED_OUT
    assert done.reason == "Mara is family, and nothing in them answers this."

    # Nothing of the kind is ever on record between them, not even that it was tried.
    assert done.effects.bonds == [] and stage(after(state, done)) is None

    sister = world(90)
    sister.characters["mara"].parent_ids = ["bram"]
    sister.characters[YOU].parent_ids = ["bram"]
    asked = one(sister, ask())
    assert asked.outcome_class is OutcomeClass.RULED_OUT
    assert asked.effects.bonds == []


def test_a_move_someone_wants_none_of_is_still_on_record_as_made():
    state = world(90)
    state.characters["mara"].attitude_toward(YOU).affinity = -bonds.WARM_AT
    told = after(state, one(state, flirt()))
    assert stage(told) is BondStage.INTEREST and heart(told) == 90


# --- what is no move in a romance --------------------------------------------------------------


def test_only_adults_on_record_are_in_a_romance():
    """F3 holds the turn before it plays; here nothing is read as a romance either."""
    for age in (16, None):
        state = world(90, age=age)
        done = one(state, flirt())
        assert done.effects.bonds == []
        assert heart(after(state, done)) == 90


def test_a_step_that_aims_harm_or_forces_itself_on_someone_is_no_romance():
    state = world(90)
    blow = to("mara", "kiss Mara and stab her", RomanceMove.ADVANCE, verb="stab", aim=Aim.KILL)
    assert one(state, blow).effects.bonds == []
    forced = to("mara", "force myself on Mara", RomanceMove.ADVANCE, verb="force")
    assert one(state, forced).effects.bonds == []


def test_a_move_with_nobody_on_record_to_be_with_is_an_ordinary_step():
    state = world()
    lonely = step("write a love song", ActionKind.TASK, 600, romance=RomanceMove.ADVANCE)
    done = one(state, lonely)
    assert done.effects.bonds == []


def test_a_step_that_is_no_move_leaves_every_romance_alone():
    state = world(50, BondStage.COURTING)
    chat = to("mara", "ask Mara about the harvest", verb="ask")
    done = one(state, chat)
    assert done.effects.bonds == []
    assert heart(after(state, done)) == 50
