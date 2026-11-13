"""W17: a step that is a move in a romance, ruled by the bond on record and the other's own heart.

Logic first (A2): a kiss with a partner needs no dice, an ask is answered by their heart where it
is surely there or surely not, and only what that leaves open is thrown for. An advance that was
answered moves their heart at their own pace, and the bond comes to the stage the story earned.
"""

import pytest

from engine import bonds, limits, pipeline
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR
from engine.context import Language, Rating
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
    CharacterStatus,
    DeathCertainty,
    Disposition,
    Encounter,
    EncounterKind,
    Faith,
    PendingEvent,
    Place,
    PowerAxis,
    Route,
    StepResult,
    Unions,
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


@pytest.mark.parametrize("named", ["aimed at her", "in its words alone"])
def test_a_move_is_a_step_of_words_to_them_whatever_the_reading_gave(named):
    """A2. On the real model (2026-11-13) a kiss after a breakup was read with no axis and
    nobody in its way, so nobody answered it and it was certain. Code says what a move in a
    romance is measured on and whom it is made to: their own heart stands in its way."""
    state = world(bonds.TENDER_SURE - 1, BondStage.TOGETHER)
    targets = ["mara"] if named == "aimed at her" else []
    kiss = step("kiss Mara", ActionKind.EXCHANGE, 60, verb="kiss", target_ids=targets)
    assert kiss.axis is None and not kiss.facts.opposition_ids

    done = one(state, kiss)

    assert done.roll is not None
    assert done.opponent_ids == ["mara"]


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


def test_the_reason_says_that_two_slept_together_only_when_they_did():
    """W17: the scene tells a night together only where the step's reason says it, so the
    telling and the deed on record hold the same. On the real model (2026-11-13) a night the
    reading had worded as courting was told as a night in the hayloft."""
    night = to("mara", "spend the night with Mara", RomanceMove.ADVANCE, verb="sleep with")
    said = "You and Mara sleep together."
    assert said in one(world(bonds.INTIMATE_SURE), night).reason
    # Turned down, it didn't happen, and a throw that missed made it no night either.
    assert said not in one(world(bonds.INTIMATE_NO - 1), night).reason
    open_ = world(bonds.INTIMATE_NO)
    assert said not in one(open_, night, seed_for(open_, night, StepResult.FAILURE)).reason
    assert said in one(open_, night, seed_for(open_, night, StepResult.SUCCESS)).reason
    # The same words read as an evening of courting are an evening of courting.
    evening = to("mara", "spend the night with Mara", RomanceMove.ADVANCE, verb="romance")
    sure = world(bonds.INTIMATE_SURE)
    assert said not in one(sure, evening, seed_for(sure, evening, StepResult.SUCCESS)).reason


def test_a_night_together_is_a_move_of_its_own_whatever_its_words():
    """W17: the reading says a night as lovers as a move of its own, and code takes it as an
    advance beyond a kiss however the step is worded. On the real model (2026-11-13) "I spend
    the night with Mara, and we sleep together" came back as an advance with the verb
    "romance" although the guide asked for the verb "sleep with": the record held courting,
    and the scene told a night."""
    words = "spend the night with Mara, and we sleep together"
    night = to("mara", words, RomanceMove.NIGHT, verb="romance")
    assert limits.intimacy(night) is limits.Intimacy.SEXUAL
    assert limits.intimacy(night, Language.ES) is limits.Intimacy.SEXUAL
    # The same words as an advance name no act, so they stay an evening in her company.
    evening = to("mara", words, RomanceMove.ADVANCE, verb="romance")
    assert limits.intimacy(evening) is limits.Intimacy.ROMANCE

    # It is ruled on as a night together: sure with someone this drawn, ruled out with
    # someone barely drawn, and on record as what it was.
    sure = one(world(bonds.INTIMATE_SURE), night)
    assert (sure.outcome_class, sure.roll) == (OutcomeClass.CERTAIN, None)
    assert "You and Mara sleep together." in sure.reason
    stranger = one(world(bonds.INTIMATE_NO - 1), night)
    assert stranger.outcome_class is OutcomeClass.RULED_OUT
    assert "sleep together" not in stranger.reason
    deed = wrong(sure)  # Tomas is married to Ilse
    assert (deed.kind, deed.severity) == ("lie_with", bonds.BETRAYAL)

    # A Teen story stops at a kiss, whatever the words (F2).
    hits = limits.check_action(world(bonds.INTIMATE_SURE), Intent(steps=[night]), Rating.TEEN)
    assert [hit.category for hit in hits] == [limits.LimitCategory.SEXUAL]
    assert not limits.check_action(world(bonds.INTIMATE_SURE), Intent(steps=[night]), Rating.MATURE)


def test_a_night_together_an_event_cut_short_didnt_happen():
    night = to(
        "mara",
        "spend the night with Mara",
        RomanceMove.ADVANCE,
        verb="sleep with",
        kind=ActionKind.REST,
        duration_s=8 * HOUR,
    )
    state = cut_at(world(bonds.INTIMATE_SURE), HOUR)
    whole = resolve(state, Intent(steps=[night]), 0)
    assert "You and Mara sleep together." in whole.steps[0].reason

    played = pipeline.play_out(state, whole, ctx(), rng(0))

    (cut,) = played.resolution.steps
    assert cut.interrupted
    assert "sleep together" not in cut.reason
    assert not played.state.deeds and heart(played.state) == bonds.INTIMATE_SURE


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


def she_ended_it(attraction: int = 35, *, ago_s: int = 0) -> WorldState:
    """Mara ended her marriage to Tomas `ago_s` ago, and still feels something for him."""
    state = world(attraction, BondStage.MARRIED, affinity=50, trust=45)
    state.world_s = 400 * DAY
    bonds.end(
        state.bonds["bond-9"],
        by_id="mara",
        how="Mara ended it.",
        turn=3,
        world_s=state.world_s - ago_s,
    )
    return state


def test_someone_who_ended_it_is_moved_by_nothing_of_the_kind_for_a_good_while():
    """The first live story about it (2026-11-13): a wife ended her marriage over an affair,
    he took her hands and asked her to stay, the step was read as an advance and thrown for,
    and one good throw later the two were courting again. Whoever ended it has made up their
    mind: for a good while nothing of the kind moves them, however the step is read."""
    state = she_ended_it()
    for move in (flirt(), ask(), propose()):
        for seed in SEEDS:
            done = one(state, move, seed)
            assert (done.outcome_class, done.roll) == (OutcomeClass.RULED_OUT, None)
            assert done.reason.startswith(
                "Mara ended it with you, and it is too soon for anything to mend it."
            )
            told = after(state, done)
            assert heart(told) == 35
            assert stage(told) in (None, BondStage.INTEREST)
    assert bonds.closed_to(state, state.characters["mara"], YOU) is bonds.Closed.ENDED
    # Asking makes it plain and opens nothing in them: their heart stays closed after it.
    asked = after(state, one(state, ask()))
    assert stage(asked) is BondStage.INTEREST
    assert bonds.closed_to(asked, asked.characters["mara"], YOU) is bonds.Closed.ENDED
    assert one(asked, flirt()).outcome_class is OutcomeClass.RULED_OUT


def test_a_heart_that_closed_opens_again_at_their_own_pace():
    rest = bonds.REST_S[bonds.pace("mara")] * bonds.ENDED_RESTS
    still = she_ended_it(ago_s=rest - HOUR)
    assert one(still, flirt()).outcome_class is OutcomeClass.RULED_OUT
    later = she_ended_it(ago_s=rest)
    assert bonds.closed_to(later, later.characters["mara"], YOU) is None
    assert one(later, flirt()).roll is not None  # to be won again, from where their heart stands
    assert bonds.REST_S[bonds.Pace.QUICK] * bonds.ENDED_RESTS == 10 * DAY
    assert bonds.REST_S[bonds.Pace.SLOW] * bonds.ENDED_RESTS == 90 * DAY


def test_only_the_one_who_ended_it_closed_their_heart():
    """Someone who was left answers by their heart as it now stands, as before: it was never
    theirs to end. And whoever ended it is free to ask again themselves."""
    state = world(90, BondStage.MARRIED, affinity=60, trust=60)
    left = after(state, one(state, part()))  # Tomas ended it
    assert bonds.closed_to(left, left.characters["mara"], YOU) is None
    assert bonds.ended_by(left, YOU, "mara") == left.world_s
    assert bonds.ended_by(left, "mara", YOU) is None
    assert one(left, ask()).roll is not None

    widowed = world(90, BondStage.MARRIED)
    assert bonds.ended_by(widowed, "mara", YOU) is None  # nothing between them is over


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


# --- a move that wrongs a partner is a deed (W1, W17) ------------------------------------------


def wrong(done):
    """The step's deed that wrongs someone, if it left one."""
    return next((d for d in done.deeds if d.wronged_ids), None)


def lie_with(who: str = "mara"):
    return to(who, f"sleep with {who}", RomanceMove.ADVANCE, verb="sleep", duration_s=8 * HOUR)


def married_to(state: WorldState, who: str, partner: Character) -> WorldState:
    """Someone on record married to `who` since before the story, and not in the scene."""
    add(state, partner, present=False)
    wed_long_ago = BondStep(stage=BondStage.MARRIED, how="As the story opens.")
    state.bonds[f"bond-{partner.id}"] = Bond(
        id=f"bond-{partner.id}",
        a_id=partner.id,
        b_id=who,
        stage=BondStage.MARRIED,
        steps=[wed_long_ago],
    )
    return state


def since(state: WorldState, world_s: int) -> WorldState:
    """The world with what stands between Tomas and Mara begun at `world_s`, after his
    marriage, and some days gone by."""
    state.bonds["bond-9"].steps[0].world_s = world_s
    state.world_s = world_s + 4 * DAY
    return state


def jorn() -> Character:
    return Character(id="jorn", name="Jorn", age=33, location_id="village")


def test_a_move_toward_someone_else_is_a_deed_that_wrongs_a_partner():
    state = world(0)  # Tomas is married to Ilse
    done = one(state, flirt(), seed_for(state, flirt(), StepResult.FAILURE))
    deed = wrong(done)
    assert deed is not None and len(done.deeds) == 1  # in place of the step's plain deed
    assert (deed.kind, deed.target_ids, deed.wronged_ids) == ("court", ["mara"], ["ilse"])
    assert deed.victim_ids == [] and deed.actor_id is None
    assert deed.severity == bonds.SLIGHT  # it went nowhere


def test_how_grave_it_is_follows_how_far_it_went():
    # Courting by now: an affair, whatever came of this evening.
    courting = world(50, BondStage.COURTING)
    assert wrong(one(courting, flirt())).severity == bonds.AFFAIR
    # An ask is an affair when the answer is no, and a betrayal when it makes them a couple.
    cold = world(0)
    assert wrong(one(cold, ask())).severity == bonds.AFFAIR
    won = one(world(90, BondStage.COURTING), ask())
    assert wrong(won).severity == bonds.BETRAYAL and wrong(won).kind == "court"
    # A night together is a betrayal, and told as what it was.
    night = one(world(90), lie_with())
    assert night.outcome_class is OutcomeClass.CERTAIN
    assert (wrong(night).kind, wrong(night).severity) == ("lie_with", bonds.BETRAYAL)
    # One that wasn't is an affair.
    refused = one(world(0), lie_with())
    assert refused.outcome_class is OutcomeClass.RULED_OUT
    assert (wrong(refused).kind, wrong(refused).severity) == ("court", bonds.AFFAIR)
    # A wedding is one once the two are wed, and nothing while it can't be.
    wedding = one(since(world(90, BondStage.PROMISED), DAY), wed())
    assert (wrong(wedding).kind, wrong(wedding).severity) == ("wed", bonds.BETRAYAL)
    assert wrong(one(since(world(90, BondStage.TOGETHER), DAY), wed())) is None


def test_a_couple_already_is_an_affair_each_time_and_no_new_betrayal():
    lovers = since(world(90, BondStage.TOGETHER), DAY)
    kiss = to("mara", "kiss Mara", RomanceMove.ADVANCE, verb="kiss")
    assert wrong(one(lovers, kiss)).severity == bonds.AFFAIR
    assert wrong(one(lovers, ask())).severity == bonds.AFFAIR  # they are together already


def test_a_move_that_wrongs_nobody_is_no_such_deed():
    alone = world(0)
    alone.bonds.clear()
    assert wrong(one(alone, flirt())) is None
    # A kiss with his own wife wrongs nobody, and needs no deed at all.
    home = world(0)
    kiss = to("ilse", "kiss Ilse", RomanceMove.ADVANCE, verb="kiss")
    assert one(home, kiss).deeds == []
    # Ending it is no wrong, and nor is anything toward close family.
    assert wrong(one(world(50, BondStage.COURTING), part())) is None
    kin = world(0)
    kin.characters["mara"].parent_ids = [YOU]
    assert wrong(one(kin, flirt())) is None


def test_where_several_partners_are_the_custom_nobody_is_wronged():
    state = world(50, BondStage.COURTING)
    state.bible.several_partners = True
    assert wrong(one(state, flirt())) is None


def test_someone_left_earlier_in_the_plan_is_not_wronged_by_what_comes_after():
    state = world(0)
    plan = Intent(steps=[part("ilse"), flirt()])
    left, flirted = resolve(state, plan).steps
    assert left.effects.bonds and wrong(flirted) is None


def test_whoever_came_after_is_not_wronged_by_the_first_two():
    state = since(world(90, BondStage.TOGETHER), 5 * DAY)  # Mara came after Ilse
    kiss_wife = to("ilse", "kiss Ilse", RomanceMove.ADVANCE, verb="kiss")
    assert wrong(one(state, kiss_wife)) is None
    kiss_mara = to("mara", "kiss Mara", RomanceMove.ADVANCE, verb="kiss")
    assert wrong(one(state, kiss_mara)).wronged_ids == ["ilse"]


def test_two_who_shared_someone_as_the_story_opened_mind_neither_kiss():
    state = world(90, BondStage.MARRIED)  # two wives, both from the premise
    for who in ("ilse", "mara"):
        kiss = to(who, f"kiss {who}", RomanceMove.ADVANCE, verb="kiss")
        assert one(state, kiss).deeds == []


def test_the_partner_of_whoever_is_courted_is_wronged_too():
    state = married_to(world(0), "mara", jorn())
    assert wrong(one(state, flirt())).wronged_ids == ["ilse", "jorn"]  # the actor's own first
    state.bonds.pop("bond-1")  # Tomas is no longer married
    assert wrong(one(state, flirt())).wronged_ids == ["jorn"]
    state.characters["jorn"].status = CharacterStatus.DEAD
    state.characters["jorn"].death_certainty = DeathCertainty.CONFIRMED
    assert wrong(one(state, flirt())) is None  # the dead mind nothing


# --- someone who has a partner already (W17) ---------------------------------------------------


def someone_elses(
    drawn: int = 0,
    *,
    faith: Faith,
    theirs: int = 80,
    stage: BondStage | None = None,
    unions: Unions = Unions.HELD,
) -> WorldState:
    """Tomas, unmarried here, and Mara, who is Jorn's wife: how she holds to a partner, how
    drawn she is to her husband (`theirs`), and what the custom makes of a marriage."""
    state = world(drawn, stage)
    state.bonds.pop("bond-1")
    state.bible.unions = unions
    married_to(state, "mara", jorn())
    mara, husband = state.characters["mara"], state.characters["jorn"]
    mara.faith = faith
    mara.sheet.disposition.attitudes["jorn"] = Attitude(affinity=50, trust=50, attraction=theirs)
    husband.sheet.disposition.attitudes["mara"] = Attitude(affinity=60, trust=60, attraction=70)
    return state


def with_jorn(state: WorldState) -> BondStage | None:
    bond = bonds.live(state, "mara", "jorn")
    return bond.stage if bond is not None else None


KEEPS = "Mara keeps to Jorn, and nothing of the kind moves them."
BETWEEN = "Jorn still stands between you and Mara."


@pytest.mark.parametrize("move", [flirt, ask, lie_with])
def test_someone_who_keeps_to_their_partner_is_moved_by_nothing_of_the_kind(move):
    state = someone_elses(bonds.DECLARE_SURE, faith=Faith.STEADFAST)
    done = one(state, move())
    assert (done.outcome_class, done.roll) == (OutcomeClass.RULED_OUT, None)
    assert done.reason.startswith(KEEPS)
    # It was still made, and her husband is wronged by it.
    told = after(state, done)
    assert stage(told) is BondStage.INTEREST and heart(told) == bonds.DECLARE_SURE
    assert with_jorn(told) is BondStage.MARRIED
    assert wrong(done).wronged_ids == ["jorn"]


def test_with_someone_torn_their_partner_stands_in_the_way():
    held = 80 // bonds.HOLD  # a loved husband: every mark is this much higher

    def asked(drawn: int, **kw):
        return one(someone_elses(drawn, faith=Faith.TORN, **kw), ask())

    cold = asked(bonds.DECLARE_NO - 1)
    assert cold.outcome_class is OutcomeClass.RULED_OUT
    assert cold.reason.startswith("Mara's heart isn't there yet.")
    # Drawn enough for someone free to be asked, and not for her.
    between = asked(bonds.DECLARE_NO + held - 1)
    assert between.outcome_class is OutcomeClass.RULED_OUT and between.reason.startswith(BETWEEN)
    assert one(world(bonds.DECLARE_NO + held - 1), ask()).roll is not None
    # Sure with someone free, and a throw with her: a step harder for her husband.
    free = one(world(bonds.DECLARE_SURE), ask())
    thrown = asked(bonds.DECLARE_SURE)
    assert (free.outcome_class, free.roll) == (OutcomeClass.CERTAIN, None)
    assert thrown.roll is not None
    assert "Mara is with Jorn" in thrown.reason
    roving = one(someone_elses(bonds.DECLARE_SURE - 1, faith=Faith.ROVING), ask())
    torn = asked(bonds.DECLARE_SURE - 1)
    assert "is with Jorn" not in roving.reason
    assert torn.roll.throw.number > roving.roll.throw.number
    # Her heart far enough past it is a yes all the same.
    sure = asked(bonds.DECLARE_SURE + held)
    assert (sure.outcome_class, sure.roll) == (OutcomeClass.CERTAIN, None)
    # A husband she has little left for stands half as much in the way.
    assert asked(bonds.DECLARE_NO + held - 1, theirs=40).roll is not None


def test_with_someone_torn_a_night_and_a_courtship_take_more_too():
    held = 80 // bonds.HOLD
    night = one(someone_elses(bonds.INTIMATE_NO + held - 1, faith=Faith.TORN), lie_with())
    assert night.outcome_class is OutcomeClass.RULED_OUT and night.reason.startswith(BETWEEN)
    assert one(someone_elses(bonds.INTIMATE_SURE, faith=Faith.TORN), lie_with()).roll is not None
    sure = one(someone_elses(bonds.INTIMATE_SURE + held, faith=Faith.TORN), lie_with())
    assert sure.outcome_class is OutcomeClass.CERTAIN
    assert "You and Mara sleep together." in sure.reason
    assert with_jorn(after(someone_elses(100, faith=Faith.TORN), sure)) is BondStage.MARRIED
    # An answered advance makes it a courtship only with her heart that much further along.
    about = bonds.COURTING_AT - bonds.NOTCH
    for drawn, courting in ((about, False), (about + held, True)):
        state = someone_elses(drawn, faith=Faith.TORN, stage=BondStage.INTEREST)
        won = one(state, flirt(), seed_for(state, flirt(), StepResult.SUCCESS))
        assert (stage(after(state, won)) is BondStage.COURTING) is courting
        assert ("courting now" in won.reason) is courting


def test_someone_roving_lets_a_partner_stand_in_nobodys_way():
    state = someone_elses(bonds.DECLARE_SURE, faith=Faith.ROVING)
    yes = one(state, ask())
    assert (yes.outcome_class, yes.roll) == (OutcomeClass.CERTAIN, None)
    assert "leaves" not in yes.reason
    told = after(state, yes)
    # She is his as well now, and her husband's still.
    assert stage(told) is BondStage.TOGETHER and with_jorn(told) is BondStage.MARRIED
    assert (wrong(yes).wronged_ids, wrong(yes).severity) == (["jorn"], bonds.BETRAYAL)
    assert one(someone_elses(bonds.INTIMATE_SURE, faith=Faith.ROVING), lie_with()).roll is None


def test_someone_steadfast_whose_own_bond_has_gone_cold_leaves_on_a_yes():
    """Never two people's at once: she can be courted once her marriage no longer holds her,
    there is no night before she has left it, and her yes is leaving it."""
    state = someone_elses(80, faith=Faith.STEADFAST, theirs=bonds.LEAVES_UNDER - 20)
    assert one(state, flirt()).roll is not None
    night = one(state, lie_with())
    assert night.outcome_class is OutcomeClass.RULED_OUT
    assert night.reason.startswith("Mara won't while they are still with Jorn.")

    yes = one(state, ask())

    assert (yes.outcome_class, yes.roll) == (OutcomeClass.CERTAIN, None)
    assert yes.reason.startswith(
        "Mara wants this too. Mara leaves Jorn for you. You and Mara are together now."
    )
    moves = [(b.a_id, b.b_id, b.stage, b.by_id) for b in yes.effects.bonds]
    assert moves == [
        (YOU, "mara", BondStage.INTEREST, YOU),
        ("mara", "jorn", BondStage.OVER, "mara"),
        (YOU, "mara", BondStage.TOGETHER, YOU),
    ]
    assert yes.effects.bonds[1].how == "Mara left Jorn for Tomas Weller."
    told = after(state, yes)
    assert stage(told) is BondStage.TOGETHER and with_jorn(told) is None
    over = bonds.last_over(told, "mara", "jorn")
    assert (over.end, over.steps[-1].by_id) == (BondEnd.PARTED, "mara")
    # Being left costs him what it costs anyone, and it is the two of them who wronged him.
    his = told.characters["jorn"].attitude_toward("mara")
    cost = bonds.PARTED_COUPLE
    assert (his.affinity, his.trust) == (60 - cost, 60 - cost)
    assert his.attraction == 70 - bonds.PARTED_HEART_COUPLE
    assert (wrong(yes).wronged_ids, wrong(yes).severity) == (["jorn"], bonds.BETRAYAL)
    # Once she is with him and no one else, a night is theirs and wrongs nobody.
    theirs = one(told, lie_with())
    assert theirs.outcome_class is OutcomeClass.CERTAIN and wrong(theirs) is None


def test_a_husband_the_record_gives_no_heart_is_left_from_the_one_he_had():
    state = someone_elses(80, faith=Faith.STEADFAST, theirs=10)
    del state.characters["jorn"].sheet.disposition.attitudes["mara"]
    told = after(state, one(state, ask()))
    his = told.characters["jorn"].attitude_toward("mara")
    assert his.attraction == bonds.settled_heart("jorn", "mara") - bonds.PARTED_HEART_COUPLE
    assert his.heart_moved_s == told.world_s


def test_a_promise_is_to_one_person_so_it_means_leaving_the_other():
    # Whoever she is, a promise to him ends her marriage.
    state = someone_elses(bonds.PROPOSE_SURE, faith=Faith.ROVING, stage=BondStage.TOGETHER)
    yes = one(state, propose())
    assert (yes.outcome_class, yes.roll) == (OutcomeClass.CERTAIN, None)
    assert yes.reason.startswith(
        "Mara wants this too. Mara leaves Jorn for you. You and Mara are promised to each other"
    )
    told = after(state, yes)
    assert stage(told) is BondStage.PROMISED and with_jorn(told) is None
    # With someone torn her husband stands in the way of it, lovers as the two are.
    held = 80 // bonds.HOLD
    torn = someone_elses(bonds.PROPOSE_NO + held - 1, faith=Faith.TORN, stage=BondStage.TOGETHER)
    no = one(torn, propose())
    assert no.outcome_class is OutcomeClass.RULED_OUT and no.reason.startswith(BETWEEN)
    assert with_jorn(after(torn, no)) is BondStage.MARRIED
    # An evening with her is as it was: only a promise asks her to leave him.
    kiss = to("mara", "kiss Mara", RomanceMove.ADVANCE, verb="kiss")
    assert one(torn, kiss).outcome_class is OutcomeClass.CERTAIN


def test_nobody_leaves_a_marriage_where_that_is_for_life():
    def here(drawn: int, faith: Faith, **kw) -> WorldState:
        return someone_elses(drawn, faith=faith, unions=Unions.FOR_LIFE, **kw)

    lovers = here(100, Faith.ROVING, stage=BondStage.TOGETHER)
    no = one(lovers, propose())
    assert no.outcome_class is OutcomeClass.RULED_OUT
    assert no.reason.startswith("Mara is married to Jorn, and here that is for life.")
    told = after(lovers, no)
    assert stage(told) is BondStage.TOGETHER and with_jorn(told) is BondStage.MARRIED
    # Someone steadfast keeps to such a marriage however cold it has gone.
    cold = here(90, Faith.STEADFAST, theirs=5)
    assert one(cold, ask()).reason.startswith(KEEPS)
    # Even one the story opened in a courtship with him: her yes would be leaving it.
    courted = here(90, Faith.STEADFAST, theirs=5, stage=BondStage.COURTING)
    asked = one(courted, ask())
    assert asked.outcome_class is OutcomeClass.RULED_OUT
    assert asked.reason.startswith("Mara is married to Jorn, and here that is for life.")
    assert with_jorn(after(courted, asked)) is BondStage.MARRIED
    # Two who aren't wed can part here like anywhere.
    cold.bonds["bond-jorn"].stage = BondStage.TOGETHER
    left = one(cold, ask())
    assert "Mara leaves Jorn for you." in left.reason
    assert with_jorn(after(cold, left)) is None


def test_someone_left_in_a_plan_is_left_once_and_not_wronged_by_what_comes_after():
    state = someone_elses(bonds.PROPOSE_SURE, faith=Faith.STEADFAST, theirs=10)
    kiss = to("mara", "kiss Mara", RomanceMove.ADVANCE, verb="kiss")
    asked, kissed, promised = resolve(state, Intent(steps=[ask(), kiss, propose()])).steps
    assert "Mara leaves Jorn for you." in asked.reason and wrong(asked).wronged_ids == ["jorn"]
    for later in (kissed, promised):
        assert later.outcome_class is OutcomeClass.CERTAIN
        assert "Jorn" not in later.reason and wrong(later) is None
        assert all("jorn" not in (b.a_id, b.b_id) for b in later.effects.bonds)
        assert all(c.id != "jorn" for c in later.effects.characters)
    told = after(state, asked, kissed, promised)
    assert stage(told) is BondStage.PROMISED and with_jorn(told) is None


def test_where_several_partners_are_the_custom_a_partner_stands_in_nobodys_way():
    state = someone_elses(bonds.DECLARE_SURE, faith=Faith.STEADFAST)
    state.bible.several_partners = True
    yes = one(state, ask())
    assert yes.outcome_class is OutcomeClass.CERTAIN and "Jorn" not in yes.reason
    assert with_jorn(after(state, yes)) is BondStage.MARRIED


def test_courting_cut_short_makes_a_courtship_only_past_what_stands_in_the_way():
    rest = bonds.REST_S[bonds.pace("mara")]
    for faith, courting in ((Faith.ROVING, True), (Faith.TORN, False)):
        state = cut_at(someone_elses(faith=faith), 3 * rest + HOUR)
        whole, seed = a_season(state)
        played = pipeline.play_out(state, whole, ctx(), rng(seed))
        (courted,) = played.resolution.steps
        assert courted.duration_s // rest == 3
        assert heart(played.state) == bonds.COURTING_AT
        assert (stage(played.state) is BondStage.COURTING) is courting
        assert ("courting now" in courted.reason) is courting


# --- they have to be there (W10) --------------------------------------------------------------

WALK = 40 * 60  # the farm to Millbrook, by the map


def gone_home(state: WorldState, where: str | None = "village") -> WorldState:
    """Mara has gone home: out of the scene, and on record in Millbrook."""
    state.characters["mara"].location_id = where
    state.scene.present_ids = [i for i in state.scene.present_ids if i != "mara"]
    return state


def in_town(state: WorldState, away_s: int = 3 * HOUR) -> WorldState:
    """Mara has gone to Harrow, a market town `away_s` down the road that Tomas knows."""
    state.places["town"] = Place(id="town", name="Harrow", kind="town", known_by=[YOU])
    state.places["farm"].routes.append(Route(to_id="town", travel_s=away_s))
    return gone_home(state, "town")


def week_of_courting():
    return to(
        "mara",
        "court her for a week",
        RomanceMove.ADVANCE,
        verb="court",
        kind=ActionKind.TIME_SKIP,
        duration_s=7 * DAY,
    )


def kiss():
    return to("mara", "kiss her", RomanceMove.ADVANCE, verb="kiss", duration_s=60)


def test_a_move_goes_to_someone_who_is_a_short_way_off():
    state = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING))
    done = one(state, ask())
    # He walks over to Millbrook and asks her there: the way is the least the step takes.
    assert done.trip is not None and (done.trip.from_id, done.trip.to_id) == ("farm", "village")
    assert done.trip.arrived and done.trip.takes_s == WALK
    assert done.outcome_class is OutcomeClass.CERTAIN and done.duration_s == WALK
    played = pipeline.play_out(state, resolve(state, Intent(steps=[ask()]), 0), ctx(), rng(0))
    assert played.state.characters[YOU].location_id == "village"
    assert stage(played.state) is BondStage.TOGETHER


def test_the_way_is_made_whatever_they_answer():
    state = gone_home(world(0))
    whole = resolve(state, Intent(steps=[ask()]), 0)
    [done] = whole.steps
    # Her heart isn't there, and it was at her door that she said so.
    assert (done.outcome_class, done.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
    assert "heart isn't there" in done.reason
    assert done.trip is not None and done.trip.arrived and done.duration_s == WALK
    played = pipeline.play_out(state, whole, ctx(), rng(0))
    assert played.state.characters[YOU].location_id == "village"
    assert played.state.world_s - state.world_s == WALK


def test_a_move_toward_someone_far_off_reaches_nobody():
    state = in_town(world(bonds.DECLARE_SURE, BondStage.COURTING))
    for made in (ask(), flirt(), kiss(), propose(), wed()):
        done = one(state, made)
        assert (done.outcome_class, done.result) == (OutcomeClass.RULED_OUT, StepResult.FAILURE)
        assert done.reason == "Mara isn't here." and done.roll is None
        # He went nowhere, and nothing of it is on record: no heart moved, no stage, and no
        # deed that wrongs Ilse.
        assert done.trip is None and not done.deeds and done.wooing is None
        told = after(state, done)
        assert heart(told) == bonds.DECLARE_SURE and stage(told) is BondStage.COURTING
    # And nothing opens with someone who never heard it.
    fresh = in_town(world(50))
    assert stage(after(fresh, one(fresh, flirt()))) is None


def test_someone_at_the_place_or_in_the_scene_is_there():
    # About the farm and out of the scene: the scene can bring her in (W4).
    about = world(bonds.DECLARE_SURE, BondStage.COURTING)
    about.scene.present_ids = [YOU]
    assert one(about, ask()).outcome_class is OutcomeClass.CERTAIN
    assert one(about, ask()).trip is None
    # In the scene, whatever the record says of where she is.
    here = world(bonds.DECLARE_SURE, BondStage.COURTING)
    here.characters["mara"].location_id = "village"
    assert one(here, ask()).trip is None
    # Nowhere on record: she is the scene's to place.
    unplaced = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING), None)
    assert one(unplaced, ask()).outcome_class is OutcomeClass.CERTAIN
    assert one(unplaced, ask()).trip is None


def test_going_to_them_first_finds_them():
    state = in_town(world(bonds.DECLARE_SURE, BondStage.COURTING))
    ride = step("ride to Harrow", ActionKind.TRAVEL, 3 * HOUR, destination="town")
    went, asked = resolve(state, Intent(steps=[ride, ask()]), 0).steps
    assert went.trip is not None and went.trip.arrived
    assert asked.outcome_class is OutcomeClass.CERTAIN and asked.trip is None
    assert stage(after(state, went, asked)) is BondStage.TOGETHER


def test_a_step_that_goes_somewhere_else_finds_nobody_there():
    state = in_town(gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING)))
    there = to("mara", "ask her to be with me", RomanceMove.DECLARE, destination="village")
    done = one(state, there)
    # He went to Millbrook, as he said, and she is in Harrow.
    assert done.reason == "Mara isn't here." and done.outcome_class is OutcomeClass.RULED_OUT
    assert done.trip is not None and done.trip.to_id == "village" and done.trip.arrived
    assert stage(after(state, done)) is BondStage.COURTING
    # Where the step goes is where she is: asked there.
    town = to("mara", "ask her to be with me", RomanceMove.DECLARE, destination="town")
    found = one(state, town)
    assert found.outcome_class is OutcomeClass.CERTAIN and found.trip.to_id == "town"


def test_a_stretch_of_courting_goes_further_than_a_moment_does():
    state = in_town(world(30), DAY)
    assert one(state, kiss()).reason == "Mara isn't here."
    week = one(state, week_of_courting())
    # A day's ride is a small part of a week: he goes to her, and the week is spent there.
    assert week.outcome_class is not OutcomeClass.RULED_OUT
    assert week.trip is not None and week.trip.to_id == "town" and week.trip.arrived
    assert week.duration_s >= 7 * DAY
    # Two days of it are no time for a day's ride each way with anything left.
    days = to("mara", "court her", RomanceMove.ADVANCE, verb="court", duration_s=2 * DAY)
    assert one(state, days).reason == "Mara isn't here."


def test_courting_cut_short_on_the_way_to_them_didnt_happen():
    """E7, W10: the way to her is no time with her. Stopped on the road, a fortnight of
    courting moved no heart, and stopped later it keeps the time he was there."""
    rest, ride = bonds.REST_S[bonds.pace("mara")], 12 * HOUR
    fortnight = flirt(kind=ActionKind.TIME_SKIP, duration_s=14 * DAY)

    def stopped_after(due_s: int) -> pipeline.PlayOut:
        state = cut_at(in_town(world(), ride), due_s)
        seed = seed_for(state, fortnight, StepResult.SUCCESS)
        whole = resolve(state, Intent(steps=[fortnight]), seed)
        return pipeline.play_out(state, whole, ctx(), rng(seed))

    early, late = stopped_after(ride - HOUR), stopped_after(ride + 2 * rest + HOUR)

    (on_the_road,) = early.resolution.steps
    assert on_the_road.interrupted and not on_the_road.trip.arrived
    assert heart(early.state) == 0 and stage(early.state) is None
    assert early.state.characters[YOU].location_id == "farm"
    (courted,) = late.resolution.steps
    assert courted.interrupted and courted.duration_s == ride + 2 * rest + HOUR
    assert courted.trip.arrived and late.state.characters[YOU].location_id == "town"
    assert heart(late.state) == bonds.NOTCH * 2


def test_nobody_goes_to_someone_they_have_no_way_to_find():
    # Nothing on the map joins the two.
    state = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING), "isle")
    state.places["isle"] = Place(id="isle", name="the Isle", kind="island", known_by=[YOU])
    assert one(state, week_of_courting()).reason == "Mara isn't here."
    # A cave in the valley that he has never heard of: a short walk, to nowhere he knows.
    hidden = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING), "cave")
    hidden.places["cave"] = Place(id="cave", name="the cave", kind="cave", parent_id="valley")
    done = one(hidden, ask())
    assert done.reason == "Mara isn't here." and done.trip is None
    hidden.places["cave"].known_by = [YOU]
    found = one(hidden, ask())
    assert found.trip is not None and found.trip.to_id == "cave" and found.trip.arrived


def test_nobody_walks_off_from_a_fight_to_find_them():
    state = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING))
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["bram"], started_turn=1, started_s=state.world_s
    )
    done = one(state, ask())
    assert done.reason == "Mara isn't here." and done.trip is None


def test_what_wrongs_someone_is_done_where_the_step_went():
    """W1, W2: his wife is at the gate with him, and Mara is in Millbrook. The kiss he walks
    over for is done in Millbrook: old Bram, who is there, sees it, and Ilse doesn't."""
    state = gone_home(world(bonds.DECLARE_SURE, BondStage.COURTING))
    assert "ilse" in state.scene.present_ids
    whole = resolve(state, Intent(steps=[kiss()]), 0)
    [done] = whole.steps
    assert done.trip is not None and done.trip.to_id == "village"
    assert [d.place_id for d in done.deeds] == ["village"]
    played = pipeline.play_out(state, whole, ctx(), rng(0))
    [deed] = [d for d in played.state.deeds.values() if "ilse" in d.wronged_ids]
    assert deed.place_id == "village"
    assert "bram" in deed.witness_ids and "ilse" not in deed.witness_ids
    # Read as a few steps over to her, it is the same walk and the same place.
    over = to("mara", "walk over and kiss her", RomanceMove.ADVANCE, kind=ActionKind.MOVE)
    stepped = one(state, over)
    assert stepped.trip.to_id == "village" and stepped.duration_s == WALK
    assert [d.place_id for d in stepped.deeds] == ["village"]


def test_ending_it_needs_nobody_there():
    state = in_town(world(60, BondStage.TOGETHER))
    done = one(state, part())
    assert done.outcome_class is OutcomeClass.CERTAIN and done.trip is None
    assert after(state, done).bonds["bond-9"].stage is BondStage.OVER
