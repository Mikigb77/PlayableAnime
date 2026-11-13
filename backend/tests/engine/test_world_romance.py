"""W17: what the world makes of a move in a romance that wrongs someone.

It is a deed (W1) that harms nobody: no law is broken and no faction is told. It is something
to whoever is a couple with either of the two, who learns of it only by seeing it or from
someone who did (W2), loses liking, trust and heart by how far it went, comes to have it out,
and ends it when their heart is gone. To someone whose partner was courted, whoever did it is
a rival.
"""

import pytest

from engine import bonds
from engine.base import DAY, HOUR
from engine.context import Language
from engine.contracts import ProposedDeed
from engine.samples import farm_world
from engine.state import (
    Attitude,
    Bond,
    BondEnd,
    BondStage,
    BondStep,
    Character,
    Faction,
    Membership,
    Place,
    Route,
    Visibility,
    WorldState,
)
from engine.visibility import memory_view
from engine.world import Kind, knowledge
from engine.world.answers import Answer
from engine.world.norms import Nature, deed_nature, is_crime
from engine.world.telling import YOU as TOLD_AS_YOU
from engine.world.telling import account
from engine.world.tuning import SILENT_FEAR

from .test_world import at, deed_step, idle, moved_on, pending_of, play

YOU = "tomas"
EN, ES, CA = Language.EN, Language.ES, Language.CA


def valley(*, heart: int = 80, drawn: int = 0) -> WorldState:
    """Tomas in Millbrook with Mara and old Bram, and his wife Ilse at home on the farm, forty
    minutes away. `heart` is how drawn Ilse is to him, and `drawn` how drawn Mara is."""
    state = farm_world()
    mara = Character(
        id="mara", name="Mara", age=29, location_id="village", known_by=[YOU], met_by=[YOU]
    )
    mara.sheet.disposition.attitudes[YOU] = Attitude(affinity=30, trust=30, attraction=drawn)
    state.characters["mara"] = mara
    state.characters["ilse"].sheet.disposition.attitudes[YOU].attraction = heart
    state.characters[YOU].location_id = "village"
    state.scene.place_id = "village"
    state.scene.present_ids = [YOU, "mara", "bram"]
    return state


def with_husband(state: WorldState, *, there: bool = False) -> WorldState:
    """Mara is married to Jorn, who is in Millbrook and, with `there`, in the scene."""
    state.characters["jorn"] = Character(id="jorn", name="Jorn", age=33, location_id="village")
    state.bonds["bond-2"] = Bond(
        id="bond-2",
        a_id="jorn",
        b_id="mara",
        stage=BondStage.MARRIED,
        steps=[BondStep(stage=BondStage.MARRIED, how="As the story opens.")],
    )
    if there:
        state.scene.present_ids.append("jorn")
    return state


def move(
    severity: int = bonds.AFFAIR, kind: str = "court", wronged=("ilse",), **more
) -> ProposedDeed:
    return ProposedDeed(
        kind=kind,
        text="walk Mara home (it worked)",
        target_ids=["mara"],
        wronged_ids=list(wronged),
        severity=severity,
        **more,
    )


def done(state: WorldState, *moves: ProposedDeed) -> WorldState:
    """The moves, made and recorded, with the scene over: whoever saw them is free to talk."""
    for made in moves:
        state = play(state, deed_step(made)).state
    return moved_on(state)


def feels(state: WorldState, who: str = "ilse") -> tuple[int, int, int]:
    toward = state.characters[who].attitude_toward(YOU)
    return toward.affinity, toward.trust, toward.attraction


def answers(events, answer: Answer = Answer.CONFRONT) -> list:
    return [e for e in events if e.kind == Kind.ANSWER and e.payload.get("answer") == answer.value]


def marriage(state: WorldState) -> Bond:
    return state.bonds["bond-1"]


# --- what kind of deed it is -----------------------------------------------------------------


def test_it_harms_nobody_and_breaks_no_law():
    state = valley()
    state.factions["watch"] = Faction(id="watch", name="the Millbrook watch", kind="watch")
    state.places["village"].controller_id = "watch"
    state.characters["bram"].memberships = [Membership(faction_id="watch", rank="watchman")]
    after = play(state, deed_step(move(bonds.BETRAYAL, "lie_with"))).state
    (deed,) = after.deeds.values()
    assert deed.wronged_ids == ["ilse"] and deed.severity == bonds.BETRAYAL
    assert deed_nature(after, deed) is Nature.ROMANCE
    assert not is_crime(after, deed)
    # Nobody runs to tell the watch whom someone courts, and the watch thinks nothing of it.
    assert not pending_of(after, Kind.REPORT)
    after, fired = idle(moved_on(after), after.world_s + 7 * DAY)
    assert not [e for e in fired if e.kind == Kind.REPORT]
    assert not [e for e in fired if e.payload.get("faction_id") == "watch"]
    reputation = after.factions["watch"].player_reputation
    assert (reputation.esteem, reputation.fear, after.factions["watch"].threat) == (0, 0, 0)


def test_nobody_but_the_wronged_and_those_close_to_them_minds_it():
    state = valley()
    state.scene.present_ids.append("ilse")
    state.characters["ilse"].location_id = "village"
    before = {who: feels(state, who) for who in ("bram", "mara")}
    after = play(state, deed_step(move(bonds.BETRAYAL, "lie_with"))).state
    assert {who: feels(after, who) for who in ("bram", "mara")} == before
    assert feels(after) < feels(state)
    # Someone close to her holds it against him a little, and keeps no grudge.
    friend = valley()
    friend.scene.present_ids.append("ilse")
    friend.characters["ilse"].location_id = "village"
    friend.characters["bram"].sheet.disposition.attitudes["ilse"] = Attitude(affinity=60)
    told = play(friend, deed_step(move(bonds.AFFAIR))).state
    liking = bonds.TIE_LIKING * bonds.AFFAIR * knowledge.FRIEND
    assert feels(told, "bram") == (30 - liking, 40 - liking // 2, 0)
    assert not told.characters["bram"].attitude_toward(YOU).grudges


# --- a partner who sees it -------------------------------------------------------------------


@pytest.mark.parametrize("severity", [bonds.SLIGHT, bonds.AFFAIR, bonds.BETRAYAL])
def test_a_partner_who_sees_it_loses_liking_trust_and_heart_by_how_far_it_went(severity):
    state = valley()
    state.scene.present_ids.append("ilse")
    state.characters["ilse"].location_id = "village"
    after = play(state, deed_step(move(severity))).state
    assert feels(after) == (
        80 - bonds.WRONGED_LIKING * severity,
        80 - bonds.WRONGED_TRUST * severity,
        80 - bonds.WRONGED_HEART * severity,
    )
    grudges = after.characters["ilse"].attitude_toward(YOU).grudges
    # A flirt that went nowhere is no grudge and nothing to have out. An affair is both.
    assert bool(grudges) == (severity >= bonds.FACED_FROM)
    assert bool(answers(pending_of(after, Kind.ANSWER))) == (severity >= bonds.FACED_FROM)
    assert marriage(after).stage is BondStage.MARRIED  # nothing ends in the moment


def test_only_a_heart_is_lost_never_won():
    state = valley()
    ilse = state.characters["ilse"]
    assert not knowledge.shift_attitude(ilse, YOU, attraction=30)
    assert ilse.attitude_toward(YOU).attraction == 80
    knowledge.shift_attitude(ilse, YOU, attraction=-200)
    assert ilse.attitude_toward(YOU).attraction == 0


# --- word of it (W2) -------------------------------------------------------------------------


def test_a_partner_elsewhere_knows_nothing_until_someone_who_saw_it_tells_them():
    state = done(valley(), move())
    (deed,) = state.deeds.values()
    assert "ilse" not in deed.known_by and feels(state) == (80, 80, 80)
    state, fired = idle(state, state.world_s + DAY)
    (deed,) = state.deeds.values()
    assert [e.title for e in fired if e.kind == Kind.TIDINGS] == [
        "Word of what Tomas Weller did reaches Ilse Weller"
    ]
    assert "ilse" in deed.known_by
    assert feels(state)[2] == 80 - bonds.WRONGED_HEART * bonds.AFFAIR
    (grudge,) = state.characters["ilse"].attitude_toward(YOU).grudges
    assert grudge.reason == "Tomas Weller courted Mara in Millbrook."


def test_while_the_witnesses_are_still_with_them_nobody_has_told():
    state = play(valley(), deed_step(move())).state  # the scene goes on, Bram and Mara in it
    state, fired = idle(state, state.world_s + 2 * DAY)
    assert not [e for e in fired if e.kind == Kind.TIDINGS]
    assert feels(state) == (80, 80, 80)


def test_whoever_was_courted_and_is_in_it_tells_nobody():
    # Only Mara saw it. Drawn to him, she keeps it to herself, and Ilse never hears.
    state = valley(drawn=bonds.DRAWN_AT)
    state.scene.present_ids = [YOU, "mara"]
    state = done(state, move())
    (deed,) = state.deeds.values()
    assert knowledge.in_it(state, state.characters["mara"], deed)
    state, fired = idle(state, state.world_s + 14 * DAY)
    assert not [e for e in fired if e.kind == Kind.TIDINGS] and feels(state) == (80, 80, 80)
    # One who wanted none of it tells like any witness.
    cold = valley(drawn=0)
    cold.scene.present_ids = [YOU, "mara"]
    cold = done(cold, move())
    (deed,) = cold.deeds.values()
    assert not knowledge.in_it(cold, cold.characters["mara"], deed)
    cold, fired = idle(cold, cold.world_s + DAY)
    assert [e for e in fired if e.kind == Kind.TIDINGS] and feels(cold) < (80, 80, 80)
    # And two who are courting are in it together, whatever her heart says today.
    courting = valley(drawn=0)
    courting.bonds["bond-2"] = Bond(
        id="bond-2", a_id=YOU, b_id="mara", stage=BondStage.COURTING, steps=[]
    )
    assert knowledge.in_it(courting, courting.characters["mara"], deed)


def test_a_flirt_that_went_nowhere_is_nobodys_errand():
    state = done(valley(), move(bonds.SLIGHT))
    state, fired = idle(state, state.world_s + 14 * DAY)
    assert not [e for e in fired if e.kind in (Kind.TIDINGS, Kind.RUMOR)]
    assert not state.rumors and feels(state) == (80, 80, 80)


def far_city(state: WorldState) -> WorldState:
    """Harrowgate, three days by cart from Millbrook, with Tomas and the scene in it."""
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        routes=[Route(to_id="village", travel_s=3 * DAY, mode="by cart")],
    )
    for who in (YOU, "mara", "bram"):
        state.characters[who].location_id = "city"
    state.scene.place_id = "city"
    return state


def test_far_from_home_nobody_carries_it_to_them_unless_someone_who_saw_it_is_theirs():
    state = done(far_city(valley()), move(bonds.BETRAYAL, "lie_with"))
    state, fired = idle(state, state.world_s + 30 * DAY)
    assert not [e for e in fired if e.kind == Kind.TIDINGS]
    assert "ilse" not in next(iter(state.deeds.values())).known_by
    # Her friend saw it: word sets out, and takes the road's time to reach her (W10).
    tied = far_city(valley())
    tied.characters["bram"].sheet.disposition.attitudes["ilse"] = Attitude(affinity=60)
    tied = done(tied, move(bonds.BETRAYAL, "lie_with"))
    soon, fired = idle(tied, tied.world_s + 2 * DAY)
    assert not [e for e in fired if e.kind == Kind.TIDINGS]
    later, fired = idle(soon, soon.world_s + 10 * DAY)
    assert [e for e in fired if e.kind == Kind.TIDINGS]
    assert "ilse" in next(iter(later.deeds.values())).known_by


def test_far_from_home_talk_may_still_reach_them_and_a_devoted_partner_does_not_believe_it():
    def talked_of(affinity: int) -> tuple[WorldState, list]:
        # Mara is in it and keeps quiet, so it rests on old Bram's word alone.
        state = far_city(valley(drawn=bonds.DRAWN_AT))
        state.characters["ilse"].sheet.disposition.attitudes[YOU].affinity = affinity
        state = done(state, move(bonds.BETRAYAL, "lie_with"))
        return idle(state, state.world_s + 30 * DAY)

    devoted, fired = talked_of(80)
    assert [e for e in fired if e.kind == Kind.RUMOR and e.place_id == "farm"]
    assert feels(devoted) == (80, 80, 80)  # she won't hear a word against him

    wary, _ = talked_of(40)
    (deed,) = wary.deeds.values()
    assert "ilse" in deed.heard_by and "ilse" not in deed.known_by
    liking, _, heart = feels(wary)
    assert liking < 40 and heart < 80
    # Suspicion: nothing held against him, and nobody comes to have anything out.
    assert not wary.characters["ilse"].attitude_toward(YOU).grudges
    assert not answers(wary.pending_events.values())


def test_what_reaches_them_as_talk_moves_them_and_nothing_more():
    state = valley(drawn=bonds.DRAWN_AT)  # Mara keeps quiet: it is one person's word
    state.characters["ilse"].sheet.disposition.attitudes[YOU].affinity = 40
    state = play(state, deed_step(move(bonds.BETRAYAL, "lie_with"))).state
    (deed,) = state.deeds.values()
    w = at(state)
    knowledge.character_learns(w, "ilse", deed, weight=0.5, grounds=knowledge.Grounds.HEARD)
    assert deed.heard_by == {"ilse": 0.5} and "ilse" not in deed.known_by
    half = bonds.BETRAYAL / 2
    assert feels(state) == (
        40 - bonds.WRONGED_LIKING * half,
        80 - bonds.WRONGED_TRUST * half,
        80 - bonds.WRONGED_HEART * half,
    )
    toward = state.characters["ilse"].attitude_toward(YOU)
    assert not toward.grudges and not answers(pending_of(state, Kind.ANSWER))
    # Told by someone who knows, she takes in the rest, holds it and comes to have it out.
    knowledge.character_learns(w, "ilse", deed, grounds=knowledge.Grounds.TOLD)
    assert feels(state)[2] == 80 - bonds.WRONGED_HEART * bonds.BETRAYAL
    assert toward.grudges and answers(pending_of(state, Kind.ANSWER))


def test_more_of_the_same_counts_for_less_and_further_counts_again():
    state = valley()
    state.scene.present_ids.append("ilse")
    state.characters["ilse"].location_id = "village"
    unit = bonds.WRONGED_HEART
    state = play(state, deed_step(move(bonds.AFFAIR))).state
    assert feels(state)[2] == 80 - 2 * unit
    state = play(state, deed_step(move(bonds.AFFAIR))).state
    assert feels(state)[2] == 80 - 2 * unit - bonds.AGAIN * unit
    state = play(state, deed_step(move(bonds.BETRAYAL, "lie_with"))).state
    assert feels(state)[2] == 80 - 3 * unit - bonds.AGAIN * unit
    # One grudge for the affair and one for how far it went, none for the evening between.
    assert len(state.characters["ilse"].attitude_toward(YOU).grudges) == 2
    # With someone else it is new again.
    other = Character(id="ana", name="Ana", age=30, location_id="village")
    state.characters["ana"] = other
    with_ana = ProposedDeed(
        kind="court", text="flirt with Ana", target_ids=["ana"], wronged_ids=["ilse"], severity=1
    )
    before = feels(state)[2]
    state = play(state, deed_step(with_ana)).state
    assert feels(state)[2] == before - unit


# --- having it out ---------------------------------------------------------------------------


def faced(state: WorldState, days: int = 4) -> tuple[WorldState, list]:
    """The days it takes for word to get round and for whoever was wronged to come."""
    state, fired = idle(state, state.world_s + days * DAY)
    return state, fired


def test_a_partner_comes_to_have_it_out_and_stays_while_their_heart_holds():
    state, fired = faced(done(valley(), move()))
    (came,) = answers(fired)
    assert came.needs_player and came.payload["avenger_id"] == "ilse"
    assert came.title == (
        "Ilse Weller comes to have it out with Tomas Weller, to hear it answered and not to "
        "attack: Tomas Weller courted Mara in Millbrook."
    )
    assert marriage(state).stage is BondStage.MARRIED
    # Nobody comes for revenge on their own partner.
    assert not answers(state.pending_events.values(), Answer.REVENGE)
    ilse = next(p for p in memory_view(state).people if p.id == "ilse")
    assert ilse.bond is BondStage.MARRIED


def test_they_come_however_much_they_still_like_them_and_only_fear_keeps_them_away():
    state = done(valley(), move())
    state, _ = idle(state, state.world_s + 3 * HOUR)  # she has been told
    assert state.characters["ilse"].attitude_toward(YOU).affinity > 0
    assert answers(pending_of(state, Kind.ANSWER))
    afraid = state.model_copy(deep=True)
    afraid.characters["ilse"].sheet.disposition.attitudes[YOU].fear = SILENT_FEAR
    afraid, fired = faced(afraid)
    assert not [e for e in answers(fired) if e.needs_player]
    state, fired = faced(state)
    assert [e for e in answers(fired) if e.needs_player]


def test_a_partner_whose_heart_is_gone_comes_to_end_it():
    state = done(valley(heart=60), move(), move(bonds.BETRAYAL, "lie_with"))
    state, fired = faced(state)
    assert feels(state)[2] == 60 - bonds.WRONGED_HEART * bonds.BETRAYAL < bonds.LEAVES_UNDER
    (came,) = [e for e in answers(fired) if e.needs_player]
    # What she ends it over is the gravest of it she knows, not the first she heard.
    assert came.title == (
        "Ilse Weller comes to tell Tomas Weller it is over between them: Tomas Weller slept "
        "with Mara in Millbrook."
    )
    gravest = next(d for d in state.deeds.values() if d.kind == "lie_with")
    assert came.payload["deed_id"] == gravest.id  # and Memory files her coming under it
    bond = marriage(state)
    assert (bond.stage, bond.end) == (BondStage.OVER, BondEnd.PARTED)
    assert bond.steps[-1].by_id == "ilse" and bond.steps[-1].world_s == came.applied_s
    assert bonds.partners(state, YOU) == []
    ilse = next(p for p in memory_view(state).people if p.id == "ilse")
    assert ilse.bond is BondStage.OVER
    assert ilse.bond_line.startswith("You were married until they ended it")


def test_it_ends_only_once_they_have_found_them():
    state = done(valley(heart=60), move(), move(bonds.BETRAYAL, "lie_with"))
    state, _ = idle(state, state.world_s + 3 * HOUR)  # she has been told, and is not there yet
    assert marriage(state).stage is BondStage.MARRIED
    state.characters[YOU].location_id = None  # and he is nowhere she can find him
    state, fired = faced(state, 30)
    assert not [e for e in answers(fired) if e.needs_player]
    assert marriage(state).stage is BondStage.MARRIED


def test_one_more_evening_of_an_affair_they_know_brings_them_back_once_they_have_had_enough():
    state = done(valley(heart=45), move())  # an affair leaves her heart at 25: she ends it
    state, fired = faced(state)
    assert marriage(state).stage is BondStage.OVER
    # With a heart that held, the next evenings wear it down, and then she comes again.
    state = done(valley(heart=62), move())
    state, fired = faced(state)
    assert marriage(state).stage is BondStage.MARRIED and len(answers(fired)) == 1
    state.scene.present_ids = [YOU, "mara", "bram"]
    state = done(state, move())  # 62 - 20 - 5 = 37
    state, fired = faced(state)
    assert [e for e in answers(fired) if e.needs_player]
    assert marriage(state).stage is BondStage.OVER


# --- a rival -----------------------------------------------------------------------------------


def unmarried(state: WorldState) -> WorldState:
    del state.bonds["bond-1"]
    return state


def test_to_the_partner_of_whoever_was_courted_they_are_a_rival():
    state = with_husband(unmarried(valley()), there=True)
    after = play(state, deed_step(move(wronged=("jorn",)))).state
    liking, trust = bonds.RIVAL_LIKING * bonds.AFFAIR, bonds.RIVAL_TRUST * bonds.AFFAIR
    assert feels(after, "jorn") == (-liking, -trust, 0)  # no heart to lose there
    assert after.characters["jorn"].attitude_toward(YOU).grudges
    assert answers(pending_of(after, Kind.ANSWER))
    # Mara is in it or isn't, but she is no one's rival, and her marriage stands on record.
    assert feels(after, "mara") == (30, 30, 0)
    assert after.bonds["bond-2"].stage is BondStage.MARRIED


def test_a_rival_has_it_out_and_comes_for_revenge_only_over_a_betrayal():
    affair = done(with_husband(unmarried(valley())), move(wronged=("jorn",)))
    affair, fired = faced(affair, 8)
    assert [e for e in answers(fired) if e.needs_player]
    assert not answers(affair.pending_events.values(), Answer.REVENGE)
    assert not answers(fired, Answer.REVENGE)

    night = move(bonds.BETRAYAL, "lie_with", wronged=("jorn",))
    betrayal = done(with_husband(unmarried(valley())), night)
    betrayal, fired = faced(betrayal, 8)
    assert [e for e in answers(fired) if e.needs_player]
    assert answers(betrayal.pending_events.values(), Answer.REVENGE) or answers(
        fired, Answer.REVENGE
    )


def test_whoever_is_already_where_they_are_has_found_them():
    """He saw it in Millbrook and means to look for the man there. When his time comes the man
    has gone home: looking in Millbrook finds nobody, and a husband who is at the farm himself
    by then has found him, wherever he had meant to look (A2)."""

    def comes(jorn_at: str) -> tuple[WorldState, list]:
        state = with_husband(unmarried(valley()), there=True)
        state = moved_on(play(state, deed_step(move(wronged=("jorn",)))).state)
        (coming,) = answers(pending_of(state, Kind.ANSWER))
        assert coming.place_id == "village"
        coming.due_s = state.world_s + HOUR
        state.characters[YOU].location_id = "farm"
        state.characters["jorn"].location_id = jorn_at
        return idle(state, state.world_s + 2 * HOUR)

    state, fired = comes("village")
    assert not [e for e in answers(fired) if e.needs_player]
    assert any("found them gone" in fact.text for fact in state.facts.values())

    state, fired = comes("farm")
    (came,) = [e for e in answers(fired) if e.needs_player]
    assert came.place_id == "farm" and state.characters["jorn"].location_id == "farm"
    assert came.title.startswith("Jorn comes to have it out with Tomas Weller")


def test_a_rival_who_no_longer_thinks_ill_of_them_lets_it_rest():
    night = move(bonds.BETRAYAL, "lie_with", wronged=("jorn",))
    state = done(with_husband(unmarried(valley())), night)
    state, fired = faced(state, 8)
    state.characters["jorn"].sheet.disposition.attitudes[YOU].affinity = 10  # amends were made
    state, fired = idle(state, state.world_s + 30 * DAY)
    assert not [e for e in answers(fired, Answer.REVENGE) if e.needs_player]


def test_both_partners_are_wronged_each_in_their_own_way():
    state = with_husband(valley(), there=True)
    state.scene.present_ids.append("ilse")
    state.characters["ilse"].location_id = "village"
    after = play(state, deed_step(move(wronged=("ilse", "jorn")))).state
    assert feels(after)[2] == 80 - bonds.WRONGED_HEART * bonds.AFFAIR
    assert feels(after, "jorn")[0] == -bonds.RIVAL_LIKING * bonds.AFFAIR
    assert {e.payload["avenger_id"] for e in answers(pending_of(after, Kind.ANSWER))} == {
        "ilse",
        "jorn",
    }


# --- before a crowd, and in the world's words --------------------------------------------------


def test_done_before_a_crowd_word_sets_out_at_once():
    state = valley()
    public = move(bonds.BETRAYAL, "wed", visibility=Visibility.PUBLIC)
    after = play(state, deed_step(public)).state  # the scene is still on
    assert [e.payload["character_id"] for e in pending_of(after, Kind.TIDINGS)] == ["ilse"]


@pytest.mark.parametrize(
    ("kind", "language", "told", "as_you", "to_you"),
    [
        ("court", EN, "Tomas courted Mara", "You courted Mara", "Mara courted you"),
        ("lie_with", EN, "Tomas slept with Mara", "You slept with Mara", "Mara slept with you"),
        ("wed", EN, "Tomas married Mara", "You married Mara", "Mara married you"),
        ("court", ES, "Tomas cortejó a Mara", "Cortejaste a Mara", "Mara te cortejó"),
        (
            "lie_with",
            ES,
            "Tomas se acostó con Mara",
            "Te acostaste con Mara",
            "Mara se acostó contigo",
        ),
        ("wed", ES, "Tomas se casó con Mara", "Te casaste con Mara", "Mara se casó contigo"),
        (
            "court",
            CA,
            "Tomas va fer la cort a Mara",
            "Vas fer la cort a Mara",
            "Mara et va fer la cort",
        ),
        (
            "lie_with",
            CA,
            "Tomas se'n va anar al llit amb Mara",
            "Te'n vas anar al llit amb Mara",
            "Mara se'n va anar al llit amb tu",
        ),
        (
            "wed",
            CA,
            "Tomas es va casar amb Mara",
            "Et vas casar amb Mara",
            "Mara es va casar amb tu",
        ),
    ],
)
def test_the_world_tells_it_in_its_own_words_in_each_language(kind, language, told, as_you, to_you):
    state = valley()
    state.characters[YOU].name = "Tomas"
    state = play(state, deed_step(move(kind=kind))).state
    (deed,) = state.deeds.values()
    deed.place_id = None  # the sentence without its place
    assert account(state, deed, language=language) == f"{told}."
    assert account(state, deed, doer=TOLD_AS_YOU, language=language) == f"{as_you}."

    class _Mine:
        """Mara telling it of herself, with Tomas as "you"."""

        def name(self, record):
            return TOLD_AS_YOU if record.id == "mara" else record.name

        def believes_dead(self, victim_id, deed):
            return False

    turned = deed.model_copy(update={"actor_id": "mara", "target_ids": [YOU]})

    class _Yours(_Mine):
        def name(self, record):
            return TOLD_AS_YOU if record.id == YOU else record.name

    assert account(state, turned, teller=_Yours(), language=language) == f"{to_you}."
