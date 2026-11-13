"""W17: the romances on record, and the rules a heart moves by."""

from engine import bonds
from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR
from engine.context import TurnContext
from engine.contracts import AttitudeShift, BondChange, CharacterChange, StateDelta
from engine.invariants import check_state, check_transition
from engine.samples import farm_world
from engine.state import (
    Attitude,
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Character,
    CharacterStatus,
    DeathCertainty,
    Deed,
    Faith,
    Unions,
    WorldState,
)
from engine.world import knowledge
from engine.world.tuning import SILENT_FEAR

ENGINE, NARRATOR = DeltaSource.ENGINE, DeltaSource.NARRATOR


def ctx(turn: int = 3) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn)


def farm(*, mara_age: int | None = 29) -> WorldState:
    """Tomas, his wife Ilse, old Bram, and Mara, a neighbour."""
    state = farm_world()
    state.characters["mara"] = Character(id="mara", name="Mara", age=mara_age, location_id="farm")
    return state


def moved(state: WorldState, a: str, b: str, stage: BondStage, source=ENGINE, **kw):
    change = BondChange(a_id=a, b_id=b, stage=stage, **kw)
    return apply_delta(state, StateDelta(bonds=[change]), ctx(), source=source)


def reasons(applied) -> list[str]:
    return [r.reason for r in applied.rejected]


# --- the record ------------------------------------------------------------------------------


def test_the_farm_sample_holds_a_marriage():
    state = farm_world()
    bond = bonds.live(state, "tomas", "ilse")
    assert bond is not None and bond.stage is BondStage.MARRIED
    assert bonds.live(state, "ilse", "tomas") is bond
    assert bonds.partners(state, "tomas") == ["ilse"]
    assert bonds.partners(state, "ilse") == ["tomas"]
    assert bonds.partners(state, "bram") == []
    assert check_state(state) == []


def test_stages_move_forward_and_an_end_is_final():
    bond = Bond(id="b", a_id="x", b_id="y")
    assert bonds.can_move(bond, BondStage.COURTING)
    assert bonds.can_move(bond, BondStage.TOGETHER)  # asked, and answered with a yes
    assert not bonds.can_move(bond, BondStage.PROMISED)
    assert not bonds.can_move(bond, BondStage.MARRIED)
    bond.stage = BondStage.MARRIED
    assert not bonds.can_move(bond, BondStage.TOGETHER)
    assert bonds.can_move(bond, BondStage.OVER)
    bond.stage = BondStage.OVER
    assert not any(bonds.can_move(bond, stage) for stage in BondStage)


def test_only_the_engine_moves_a_romance_or_a_heart():
    state = farm()
    told = moved(state, "tomas", "mara", BondStage.TOGETHER, source=NARRATOR)
    assert reasons(told) == ["only the engine decides this"]
    assert bonds.live(told.state, "tomas", "mara") is None

    shift = AttitudeShift(toward_id="tomas", attraction=30)
    state.scene.present_ids = ["tomas", "ilse"]
    sweet = apply_delta(
        state,
        StateDelta(characters=[CharacterChange(id="ilse", attitudes=[shift])]),
        ctx(),
        source=NARRATOR,
    )
    assert reasons(sweet) == ["only the engine decides this"]
    assert sweet.state.characters["ilse"].attitude_toward("tomas").attraction == 80


def test_the_narrators_form_holds_neither():
    schema = StateDelta.model_json_schema()
    assert "bonds" not in schema["properties"]
    assert "BondChange" not in schema["$defs"]
    assert "attraction" not in schema["$defs"]["AttitudeShift"]["properties"]


def test_a_romance_opens_between_living_adults_and_moves_a_stage_at_a_time():
    state = farm()
    opened = moved(state, "tomas", "mara", BondStage.INTEREST, by_id="tomas", how="A flower.")
    assert not opened.rejected
    bond = bonds.live(opened.state, "mara", "tomas")
    assert (bond.id, bond.a_id, bond.b_id, bond.stage) == ("bond-2", "tomas", "mara", "interest")
    assert bond.steps == [
        BondStep(stage=BondStage.INTEREST, turn=3, world_s=0, by_id="tomas", how="A flower.")
    ]
    assert check_transition(state, opened.state) == []

    skipped = moved(opened.state, "tomas", "mara", BondStage.MARRIED)
    assert reasons(skipped) == ["a romance doesn't go from interest to married"]
    on = moved(opened.state, "mara", "tomas", BondStage.COURTING)  # either way round
    assert bonds.live(on.state, "tomas", "mara").stage is BondStage.COURTING
    assert len(on.state.bonds) == 2
    same = moved(on.state, "tomas", "mara", BondStage.COURTING)
    assert not same.rejected and len(bonds.live(same.state, "tomas", "mara").steps) == 2


def test_a_romance_is_between_adults_on_record():
    for age in (16, None):
        refused = moved(farm(mara_age=age), "tomas", "mara", BondStage.INTEREST)
        assert refused.rejected and "a romance is between adults" in reasons(refused)[0]
        assert bonds.live(refused.state, "tomas", "mara") is None
    nobody = moved(farm(), "tomas", "nobody", BondStage.INTEREST)
    assert reasons(nobody) == ["no such two people"]
    alone = moved(farm(), "tomas", "tomas", BondStage.INTEREST)
    assert reasons(alone) == ["no such two people"]
    kin = farm()
    kin.characters["mara"].parent_ids = ["bram"]
    kin.characters["tomas"].parent_ids = ["bram"]
    assert reasons(moved(kin, "tomas", "mara", BondStage.INTEREST)) == ["the two are close family"]


def test_an_end_stays_an_end_and_a_new_romance_is_a_new_bond():
    state = farm()
    over = moved(state, "tomas", "ilse", BondStage.OVER, by_id="tomas", how="Tomas left.")
    ended = over.state.bonds["bond-1"]
    assert (ended.stage, ended.end) == (BondStage.OVER, BondEnd.PARTED)
    assert bonds.live(over.state, "tomas", "ilse") is None
    assert bonds.last_over(over.state, "ilse", "tomas") is ended
    assert bonds.partners(over.state, "tomas") == []
    assert check_transition(state, over.state) == []

    nothing = moved(over.state, "tomas", "ilse", BondStage.OVER)
    assert reasons(nothing) == ["there is nothing between them to end"]
    again = moved(over.state, "tomas", "ilse", BondStage.INTEREST)
    assert not again.rejected
    assert again.state.bonds["bond-1"].stage is BondStage.OVER
    assert bonds.live(again.state, "tomas", "ilse").id == "bond-2"


def test_a_death_ends_the_romances_of_the_dead_and_a_presumed_one_ends_none():
    state = farm()
    change = CharacterChange(
        id="ilse", status=CharacterStatus.DEAD, death_certainty=DeathCertainty.PRESUMED
    )
    lost = apply_delta(state, StateDelta(characters=[change]), ctx(), source=ENGINE).state
    assert bonds.live(lost, "tomas", "ilse") is not None  # she may still be alive

    change = CharacterChange(
        id="ilse", status=CharacterStatus.DEAD, death_certainty=DeathCertainty.CONFIRMED
    )
    for before in (state, lost):
        dead = apply_delta(before, StateDelta(characters=[change]), ctx(), source=ENGINE).state
        bond = dead.bonds["bond-1"]
        assert (bond.stage, bond.end) == (BondStage.OVER, BondEnd.DEATH)
        assert bond.steps[-1].how == "Ilse Weller died."
        assert check_transition(before, dead) == []
    assert reasons(moved(dead, "tomas", "ilse", BondStage.INTEREST)) == [
        "the dead start no romance"
    ]


def test_the_invariants_hold_a_romance_to_its_record():
    state = farm()
    state.bonds["bond-7"] = Bond(id="bond-7", a_id="tomas", b_id="ghost")
    state.bonds["bond-8"] = Bond(id="bond-8", a_id="ilse", b_id="tomas", stage=BondStage.TOGETHER)
    state.bonds["bond-9"] = Bond(id="bond-9", a_id="tomas", b_id="mara", stage=BondStage.OVER)
    found = {(v.subject, v.detail) for v in check_state(state)}
    assert found == {
        ("bond bond-7", "it isn't between two people on record"),
        ("bond bond-8", "the two already have a romance"),
        ("bond bond-9", "only a romance that is over has an end"),
    }

    before = farm()
    over = moved(before, "tomas", "ilse", BondStage.OVER).state
    back = over.model_copy(deep=True)
    back.bonds["bond-1"].stage, back.bonds["bond-1"].end = BondStage.MARRIED, None
    assert [v.detail for v in check_transition(over, back)] == ["a romance that is over stays over"]
    earlier = before.model_copy(deep=True)
    earlier.bonds["bond-1"].stage = BondStage.COURTING
    assert [v.detail for v in check_transition(before, earlier)] == [
        "a romance never goes back a stage"
    ]
    assert check_transition(earlier, before) == []  # forward, however many stages at once
    gone = over.model_copy(deep=True)
    del gone.bonds["bond-1"]
    assert [v.detail for v in check_transition(over, gone)] == [
        "records are archived, never deleted"
    ]


# --- a heart ---------------------------------------------------------------------------------


def test_a_pace_is_theirs_for_the_whole_story():
    assert {bonds.pace(f"npc-{i}") for i in range(40)} == set(bonds.Pace)
    assert bonds.pace("mara") is bonds.pace("mara")
    assert bonds.REST_S[bonds.Pace.SLOW] > bonds.REST_S[bonds.Pace.STEADY] > 8 * HOUR - 1


def someone(**felt) -> Character:
    character = Character(id="mara", name="Mara", age=29)
    character.sheet.disposition.attitudes["tomas"] = Attitude(**felt)
    return character


def gain(other: Character, **kw) -> int:
    given = {"whole": True, "over_the_top": False, "now_s": 10 * DAY, "lasted_s": 600} | kw
    return bonds.gain(other, "tomas", **given)


def test_an_answered_advance_moves_a_heart_a_notch():
    assert gain(someone()) == bonds.NOTCH
    assert gain(someone(), whole=False) == bonds.NOTCH // 2
    assert gain(someone(), over_the_top=True) == 2 * bonds.NOTCH
    warm = someone(affinity=bonds.WARM_AT, trust=bonds.WARM_AT)
    assert gain(warm) == bonds.NOTCH + bonds.WARM_BONUS
    cold = someone(affinity=-bonds.WARM_AT, trust=-bonds.WARM_AT)
    assert gain(cold) == 0


def test_a_heart_rests_after_it_moves():
    rest = bonds.REST_S[bonds.pace("mara")]
    just = someone(heart_moved_s=10 * DAY - rest + HOUR)  # an hour of its rest is left
    assert gain(just) == 0
    rested = someone(heart_moved_s=10 * DAY - rest)
    assert gain(rested) == bonds.NOTCH
    # What this plan already moved counts, whatever the record still says.
    assert gain(rested, moved_s=10 * DAY) == 0
    # A step that goes on past the rest counts from there.
    assert gain(just, lasted_s=HOUR) == bonds.NOTCH
    assert gain(just, lasted_s=rest + HOUR) == 2 * bonds.NOTCH
    assert gain(someone(heart_moved_s=10 * DAY), lasted_s=rest - 1) == 0
    assert gain(someone(heart_moved_s=10 * DAY), lasted_s=rest) == bonds.NOTCH


def test_a_long_step_counts_for_each_time_the_heart_could_move_up_to_a_cap():
    rest = bonds.REST_S[bonds.pace("mara")]
    assert gain(someone(), lasted_s=rest) == 2 * bonds.NOTCH
    season = bonds.MOST_NOTCHES * bonds.NOTCH
    assert gain(someone(), lasted_s=400 * DAY) == season
    # Liking them already and a throw over the top each add once, however long the step.
    warm = someone(affinity=bonds.WARM_AT, trust=bonds.WARM_AT)
    assert gain(warm, lasted_s=400 * DAY) == season + bonds.WARM_BONUS
    assert gain(someone(), lasted_s=400 * DAY, over_the_top=True) == season + bonds.NOTCH
    # So a season of courting leaves the asking to be played: it alone makes nobody sure.
    assert season + bonds.WARM_BONUS < bonds.DECLARE_SURE
    # One an event cut short counts the times their heart had rested while it ran.
    assert gain(someone(), lasted_s=rest - 1, cut=True) == 0
    assert gain(someone(), lasted_s=3 * rest + 5, cut=True) == 3 * bonds.NOTCH
    assert gain(someone(), lasted_s=3 * rest, cut=True, over_the_top=True) == 4 * bonds.NOTCH


def test_a_heart_is_closed_to_family_to_someone_unwanted_and_to_someone_feared():
    state = farm()
    mara = state.characters["mara"]
    assert bonds.closed_to(state, mara, "tomas") is None
    mara.sheet.disposition.attitudes["tomas"] = Attitude(affinity=-bonds.WARM_AT)
    assert bonds.closed_to(state, mara, "tomas") is bonds.Closed.AVERSE
    mara.sheet.disposition.attitudes["tomas"] = Attitude(fear=bonds.AFRAID_AT)
    assert bonds.closed_to(state, mara, "tomas") is bonds.Closed.AFRAID
    assert bonds.AFRAID_AT == SILENT_FEAR

    mara.parent_ids = ["bram"]
    assert bonds.closed_to(state, mara, "bram") is bonds.Closed.FAMILY  # her father
    assert bonds.closed_to(state, state.characters["bram"], "mara") is bonds.Closed.FAMILY
    state.characters["tomas"].parent_ids = ["bram"]
    assert bonds.kin(state.characters, "tomas", "mara")  # they share a parent
    state.characters["ilse"].parent_ids = ["mara"]
    assert bonds.kin(state.characters, "bram", "ilse")  # his grandchild
    assert not bonds.kin(state.characters, "tomas", "ilse")


def test_a_heart_in_words_follows_the_marks_the_rules_use():
    said = [bonds.heart_words(n, "you") for n in (0, 1, 30, 40, 70, 85)]
    assert said == [
        "not drawn to you",
        "curious about you, and no more than that yet",
        "starting to be drawn to you",
        "drawn to you",
        "in love with you",
        "deeply in love with you",
    ]


# --- who is close to whom (W4) ----------------------------------------------------------------


def test_a_couple_are_close_and_the_married_are_family():
    state = farm()
    ilse, mara = state.characters["ilse"], state.characters["mara"]
    ilse.sheet.disposition.attitudes["tomas"] = Attitude()  # whatever she feels today
    assert knowledge.closeness(state, ilse, "tomas") == knowledge.FAMILY
    assert knowledge.closeness(state, state.player, "ilse") == knowledge.FAMILY

    assert knowledge.closeness(state, mara, "tomas") == 0
    courting = moved(state, "tomas", "mara", BondStage.COURTING).state
    assert knowledge.closeness(courting, courting.characters["mara"], "tomas") == 0
    together = moved(courting, "tomas", "mara", BondStage.TOGETHER).state
    assert knowledge.closeness(together, together.characters["mara"], "tomas") == knowledge.FRIEND
    promised = moved(together, "tomas", "mara", BondStage.PROMISED).state
    assert knowledge.closeness(promised, promised.characters["mara"], "tomas") == knowledge.FAMILY
    over = moved(promised, "tomas", "mara", BondStage.OVER).state
    assert knowledge.closeness(over, over.characters["mara"], "tomas") == 0


def test_a_wife_keeps_what_she_saw_her_husband_do_to_herself():
    state = farm()
    ilse = state.characters["ilse"]
    ilse.sheet.disposition.attitudes["tomas"] = Attitude()
    deed = Deed(
        id="deed-1",
        actor_id="tomas",
        kind="theft",
        text="stole a hen",
        severity=2,
        turn=3,
        world_s=0,
    )
    assert knowledge.protects(state, ilse, deed)
    assert not knowledge.would_talk(state, ilse, deed)
    assert knowledge.would_talk(state, state.characters["mara"], deed)


# --- another romance, and whom it wrongs ------------------------------------------------------


def paired(state: WorldState, a: str, b: str, stage: BondStage, world_s: int = 0) -> Bond:
    number = len(state.bonds) + 1
    bond = Bond(
        id=f"bond-{number}",
        a_id=a,
        b_id=b,
        stage=stage,
        steps=[BondStep(stage=stage, world_s=world_s)],
    )
    state.bonds[bond.id] = bond
    return bond


def test_a_couple_dates_from_the_first_stage_that_made_them_one():
    assert bonds.couple_since(None) is None
    courting = Bond(id="b", a_id="a", b_id="b", stage=BondStage.COURTING, steps=[])
    assert bonds.couple_since(courting) is None
    married = Bond(
        id="b",
        a_id="a",
        b_id="b",
        stage=BondStage.MARRIED,
        steps=[
            BondStep(stage=BondStage.COURTING, world_s=DAY),
            BondStep(stage=BondStage.TOGETHER, world_s=3 * DAY),
            BondStep(stage=BondStage.MARRIED, world_s=90 * DAY),
        ],
    )
    assert bonds.couple_since(married) == 3 * DAY
    # A record with no steps is as old as the story.
    married.steps = []
    assert bonds.couple_since(married) == 0


def test_a_move_wrongs_whoever_is_a_couple_with_either_of_the_two():
    state = farm()
    assert bonds.wronged(state, "tomas", "mara") == ["ilse"]
    assert bonds.wronged(state, "tomas", "ilse") == []  # nobody is wronged by their own kiss
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    paired(state, "jorn", "mara", BondStage.TOGETHER)
    assert bonds.wronged(state, "tomas", "mara") == ["ilse", "jorn"]
    # Someone only courted, or it is over with, has no claim, and neither have the dead.
    state.bonds["bond-2"].stage = BondStage.COURTING
    assert bonds.wronged(state, "tomas", "mara") == ["ilse"]
    state.characters["ilse"].status = CharacterStatus.DEAD
    assert bonds.wronged(state, "tomas", "mara") == []


def test_whoever_came_later_or_at_the_same_time_has_no_claim_on_the_older_couple():
    state = farm()
    paired(state, "tomas", "mara", BondStage.TOGETHER, world_s=30 * DAY)
    # Mara knew he was married: his nights with his wife wrong nobody, and hers do wrong Ilse.
    assert bonds.wronged(state, "tomas", "ilse") == []
    assert bonds.wronged(state, "tomas", "mara") == ["ilse"]
    # Two who were his from the day the story opened mind neither kiss.
    both = farm()
    paired(both, "tomas", "mara", BondStage.MARRIED)
    assert bonds.wronged(both, "tomas", "ilse") == []
    assert bonds.wronged(both, "tomas", "mara") == []


def test_where_several_partners_are_the_custom_another_romance_wrongs_nobody():
    state = farm()
    state.bible.several_partners = True
    assert bonds.wronged(state, "tomas", "mara") == []


def test_how_grave_it_is_follows_how_far_it_went():
    def of(**kw) -> int:
        given = {"asked": False, "intimate": False, "answered": True, "before": None, "after": None}
        return bonds.gravity(**(given | kw))

    interest, courting = BondStage.INTEREST, BondStage.COURTING
    together, promised, married = BondStage.TOGETHER, BondStage.PROMISED, BondStage.MARRIED
    assert of(after=interest) == bonds.SLIGHT
    assert of(answered=False) == bonds.SLIGHT
    assert of(before=interest, after=courting) == bonds.AFFAIR
    assert of(asked=True, answered=False, before=interest, after=interest) == bonds.AFFAIR
    assert of(intimate=True, answered=False) == bonds.AFFAIR
    assert of(before=together, after=together) == bonds.AFFAIR  # one more evening with them
    assert of(intimate=True, before=courting, after=courting) == bonds.BETRAYAL
    assert of(asked=True, before=courting, after=together) == bonds.BETRAYAL
    assert of(asked=True, before=together, after=promised) == bonds.BETRAYAL
    assert of(before=promised, after=married) == bonds.BETRAYAL


def test_an_end_is_recorded_with_who_ended_it_and_when():
    state = farm()
    bond = bonds.live(state, "tomas", "ilse")
    bonds.end(bond, by_id="ilse", how="Ilse Weller ended it.", turn=7, world_s=4 * DAY)
    assert (bond.stage, bond.end) == (BondStage.OVER, BondEnd.PARTED)
    last = bond.steps[-1]
    assert (last.stage, last.by_id, last.turn, last.world_s) == (BondStage.OVER, "ilse", 7, 4 * DAY)
    assert bonds.live(state, "tomas", "ilse") is None and bonds.partners(state, "tomas") == []
    assert check_state(state) == []


# --- someone who has a partner already --------------------------------------------------------


def wife(state: WorldState, stage: BondStage = BondStage.MARRIED, **felt) -> Character:
    """Mara with Jorn, her husband since before the story, and her heart for him where the
    record holds one."""
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    paired(state, "jorn", "mara", stage)
    mara = state.characters["mara"]
    if felt:
        mara.sheet.disposition.attitudes["jorn"] = Attitude(**felt)
    return mara


def test_how_someone_holds_to_a_partner_is_theirs_and_follows_the_custom_of_the_world():
    state = farm()
    mara, lena = state.characters["mara"], Character(id="lena", name="Lena")
    kinds = {}
    for unions in Unions:
        state.bible.unions = unions
        kinds[unions] = (bonds.faith(state, mara), bonds.faith(state, lena))
        assert bonds.faith(state, mara) is kinds[unions][0]  # the same every time it is asked
    # Mara keeps to a partner where couples hold, and is torn where they part easily. Lena
    # lets a partner stand in nobody's way wherever she lives.
    assert kinds[Unions.FOR_LIFE] == (Faith.STEADFAST, Faith.ROVING)
    assert kinds[Unions.HELD] == (Faith.STEADFAST, Faith.ROVING)
    assert kinds[Unions.EASY] == (Faith.TORN, Faith.ROVING)
    # What the story said of someone wins over all of it.
    mara.faith = Faith.ROVING
    state.bible.unions = Unions.FOR_LIFE
    assert bonds.faith(state, mara) is Faith.ROVING


def test_how_many_keep_to_a_partner_is_the_custom_of_the_world():
    state = farm()
    people = [Character(id=f"someone-{n}", name="Someone") for n in range(1000)]
    shares, found = {}, {}
    for unions in Unions:
        state.bible.unions = unions
        found[unions] = [bonds.faith(state, person) for person in people]
        shares[unions] = {kind: found[unions].count(kind) / 10 for kind in Faith}
    for unions, (steadfast, roving) in bonds.FAITH.items():
        assert abs(shares[unions][Faith.STEADFAST] - steadfast) < 5
        assert abs(shares[unions][Faith.ROVING] - roving) < 5
    # Most keep to a partner where a marriage is for life, and fewer than half where couples
    # part easily: nobody anywhere is sure to, and nobody is sure not to.
    assert shares[Unions.FOR_LIFE][Faith.STEADFAST] > shares[Unions.HELD][Faith.STEADFAST] > 50
    assert shares[Unions.EASY][Faith.STEADFAST] < 50
    assert all(share > 0 for by_kind in shares.values() for share in by_kind.values())
    # A custom never turns anyone round: whoever keeps to a partner where couples part easily
    # does so anywhere, and whoever roves where a marriage is for life roves anywhere.
    kinds = zip(found[Unions.EASY], found[Unions.HELD], found[Unions.FOR_LIFE], strict=True)
    for easy, held, life in kinds:
        if easy is Faith.STEADFAST:
            assert held is Faith.STEADFAST and life is Faith.STEADFAST
        if life is Faith.ROVING:
            assert held is Faith.ROVING and easy is Faith.ROVING


def test_a_settled_couples_hearts_are_theirs_where_the_record_holds_none():
    state = farm()
    mara = wife(state)
    jorn = state.characters["jorn"]
    hers, his = bonds.heart_for(state, mara, "jorn"), bonds.heart_for(state, jorn, "mara")
    assert (hers, his) == (bonds.settled_heart("mara", "jorn"), bonds.settled_heart("jorn", "mara"))
    assert hers != his  # each heart is its own
    hearts = [bonds.settled_heart(f"one-{n}", "other") for n in range(300)]
    assert min(hearts) == bonds.SETTLED and max(hearts) == bonds.SETTLED_TOP
    assert any(heart < bonds.LEAVES_UNDER for heart in hearts)  # a few have gone cold
    # What the record holds is what counts, and so is a heart that moved all the way to nothing.
    mara.sheet.disposition.attitudes["jorn"] = Attitude(attraction=20)
    assert bonds.heart_for(state, mara, "jorn") == 20
    mara.sheet.disposition.attitudes["jorn"] = Attitude(attraction=0, heart_moved_s=DAY)
    assert bonds.heart_for(state, mara, "jorn") == 0
    # Anything with the player character is only ever what the story made of it.
    assert bonds.heart_for(state, state.characters["ilse"], "tomas") == 80
    assert bonds.heart_for(state, mara, "tomas") == 0
    assert bonds.heart_for(state, state.characters["tomas"], "ilse") == 0


def test_the_partner_who_stands_between_someone_and_a_suitor():
    state = farm()
    assert bonds.kept(state, "mara", "tomas") is None  # she has nobody
    wife(state)
    assert bonds.kept(state, "mara", "tomas") == "jorn"
    assert bonds.kept(state, "mara", "jorn") is None  # her own husband is no one else
    assert bonds.kept(state, "nobody", "tomas") is None
    # Someone only courted stands between nobody.
    state.characters["odo"] = Character(id="odo", name="Odo", age=40, location_id="village")
    courted = paired(state, "odo", "mara", BondStage.COURTING)
    assert bonds.kept(state, "mara", "jorn") is None
    # Of two, the one it has come furthest with, and then the one their heart is most with.
    courted.stage = BondStage.TOGETHER
    assert bonds.kept(state, "mara", "tomas") == "jorn"
    courted.stage = BondStage.MARRIED
    hearts = {who: bonds.heart_for(state, state.characters["mara"], who) for who in ("jorn", "odo")}
    assert bonds.kept(state, "mara", "tomas") == max(hearts, key=hearts.get)
    # The dead stand between nobody, and nor does anyone where several partners are the custom.
    del state.bonds[courted.id]
    state.bible.several_partners = True
    assert bonds.kept(state, "mara", "tomas") is None
    state.bible.several_partners = False
    state.characters["jorn"].status = CharacterStatus.DEAD
    assert bonds.kept(state, "mara", "tomas") is None


def test_the_steadfast_keep_to_a_partner_while_that_bond_holds():
    state = farm()
    mara = wife(state, attraction=70)
    assert bonds.faith(state, mara) is Faith.STEADFAST
    assert bonds.keeps_to(state, mara, "tomas") == "jorn"
    assert bonds.closed_to(state, mara, "tomas") is bonds.Closed.BOUND
    assert bonds.closed_to(state, mara, "jorn") is None  # never to her own husband
    # Someone torn or roving keeps to nobody: their partner only stands in the way.
    for other in (Faith.TORN, Faith.ROVING):
        mara.faith = other
        assert bonds.keeps_to(state, mara, "tomas") is None
        assert bonds.closed_to(state, mara, "tomas") is None
    mara.faith = None
    # A bond that has gone cold holds nobody, save a marriage where that is for life.
    mara.sheet.disposition.attitudes["jorn"].attraction = bonds.LEAVES_UNDER - 1
    assert bonds.keeps_to(state, mara, "tomas") is None
    state.bible.unions = Unions.FOR_LIFE
    assert bonds.for_life(state, "mara", "jorn") and bonds.for_life(state, "jorn", "mara")
    assert bonds.keeps_to(state, mara, "tomas") == "jorn"
    state.bonds["bond-2"].stage = BondStage.TOGETHER  # not wed: nothing is for life yet
    assert not bonds.for_life(state, "mara", "jorn")
    assert bonds.keeps_to(state, mara, "tomas") is None
    state.bible.unions = Unions.HELD
    state.bonds["bond-2"].stage = BondStage.MARRIED
    assert not bonds.for_life(state, "mara", "jorn")  # a marriage here can be left
    mara.sheet.disposition.attitudes["jorn"].attraction = bonds.LEAVES_UNDER
    assert bonds.keeps_to(state, mara, "tomas") == "jorn"
    # A first move on record changes nothing, and someone who answered the suitor already,
    # as the record has it, is past keeping to anyone.
    theirs = paired(state, "tomas", "mara", BondStage.INTEREST)
    assert bonds.keeps_to(state, mara, "tomas") == "jorn"
    theirs.stage = BondStage.COURTING
    assert bonds.keeps_to(state, mara, "tomas") is None


def test_an_answer_from_before_they_were_a_couple_is_no_answer_to_this():
    """W6, W17: someone the player character courted, left for years and who married since
    keeps to the partner they have now. Only an answer given while they had that partner
    puts them past keeping to anyone, and the latest one is what counts."""
    state = farm()
    courted = paired(state, "tomas", "mara", BondStage.COURTING, world_s=DAY)
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    paired(state, "jorn", "mara", BondStage.MARRIED, world_s=400 * DAY)
    mara = state.characters["mara"]
    mara.sheet.disposition.attitudes["jorn"] = Attitude(attraction=70)

    assert bonds.keeps_to(state, mara, "tomas") == "jorn"
    assert bonds.closed_to(state, mara, "tomas") is bonds.Closed.BOUND

    # She answers him again all the same, years into the marriage: that one is an answer.
    courted.steps.append(BondStep(stage=BondStage.TOGETHER, world_s=900 * DAY))
    courted.stage = BondStage.TOGETHER
    assert bonds.keeps_to(state, mara, "tomas") is None


def test_a_partner_stands_in_a_suitors_way_by_how_much_they_are_loved():
    state = farm()
    mara = state.characters["mara"]
    assert bonds.hold(state, mara, "tomas") == 0  # nobody stands in the way
    wife(state, attraction=80)
    mara.faith = Faith.TORN
    assert bonds.hold(state, mara, "tomas") == 80 // bonds.HOLD == 20
    mara.sheet.disposition.attitudes["jorn"].attraction = 40
    assert bonds.hold(state, mara, "tomas") == 10  # a neglected partner, half as much
    mara.faith = Faith.ROVING
    assert bonds.hold(state, mara, "tomas") == 0
    # For the steadfast it counts once their own bond no longer holds them.
    mara.faith = Faith.STEADFAST
    mara.sheet.disposition.attitudes["jorn"].attraction = 36
    assert bonds.keeps_to(state, mara, "tomas") is None and bonds.hold(state, mara, "tomas") == 9
    # Once the two are a couple as well, nothing more stands in the way of an evening, and
    # a promise still means leaving the other.
    mara.faith = Faith.TORN
    paired(state, "tomas", "mara", BondStage.TOGETHER)
    assert bonds.hold(state, mara, "tomas") == 0
    assert bonds.hold(state, mara, "tomas", promise=True) == 9
