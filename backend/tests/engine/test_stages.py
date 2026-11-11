"""Hostility grows in stages, and each needs its own evidence (W4, W5, W11, W13).

From the review of Miki's long story (2026-11-11): "a group turns on you although nobody could
have told them, or the change is immediate". How far anyone goes against the doer follows how
they know. Talk makes them wary and sends nobody after the doer. The word of someone who knows
brings an accusation: the law comes to arrest, and a friend of the dead comes to face the doer
with it. What they saw, what is beyond one person's word, or an accusation that changed nothing
brings revenge.
"""

import pytest

from engine.base import DAY, HOUR
from engine.contracts import ProposedDeed
from engine.state import (
    Character,
    Connection,
    ConnectionKind,
    Deed,
    EventStatus,
    Faction,
    Membership,
    PendingEvent,
    Visibility,
    WorldState,
)
from engine.visibility import memory_view
from engine.world import Kind
from engine.world.answers import HOSTILE, Answer
from engine.world.knowledge import Grounds, character_learns, faction_learns, proven
from engine.world.scheduling import World

from .test_carriers import SECT, feels, kill, knows, slay, well
from .test_world import ctx, deed_step, idle, moved_on, pending_of, play, rng, the_deed

BROTHERHOOD = "brotherhood"


def with_a_friend(state: WorldState) -> WorldState:
    """Mei, Zhao's sworn friend, lives in the inner court, forty minutes from the well."""
    state.characters["mei"] = Character(id="mei", name="Mei", location_id="inner-court")
    state.characters["mei"].sheet.resources.connections.append(
        Connection(name="Zhao", kind=ConnectionKind.ALLY, character_id="zhao")
    )
    return state


def with_a_comrade(state: WorldState) -> WorldState:
    """Bo is of Zhao's brotherhood and no friend of his. He is at the well, out of the scene."""
    state.factions[BROTHERHOOD] = Faction(id=BROTHERHOOD, name="the Brotherhood", kind="band")
    state.characters["zhao"].memberships = [Membership(faction_id=BROTHERHOOD)]
    state.characters["bo"] = Character(
        id="bo", name="Bo", location_id="well", memberships=[Membership(faction_id=BROTHERHOOD)]
    )
    return state


def with_a_second_witness(state: WorldState) -> WorldState:
    state.characters["jun"] = Character(id="jun", name="Jun", location_id="well")
    state.scene.present_ids.append("jun")
    return state


def killing(state: WorldState, **more) -> WorldState:
    """Lin drowns Zhao with whoever is in the scene looking on, the scene moves on, and the
    world has three hours: word gets out and reaches whoever it is sent to."""
    after = play(state, deed_step(kill(**more), dead=("zhao",))).state
    after, _ = idle(moved_on(after), the_deed(after).world_s + 3 * HOUR)
    return after


def coming(state: WorldState, avenger_id: str = "mei") -> list[PendingEvent]:
    return [e for e in pending_of(state, Kind.ANSWER) if e.payload["avenger_id"] == avenger_id]


def toward_lin(state: WorldState, character_id: str):
    return state.characters[character_id].attitude_toward("lin")


def at(state: WorldState, turn: int = 2) -> World:
    return World(state=state, ctx=ctx(turn), at_s=state.world_s, rng=rng(turn))


def secret_killing(state: WorldState) -> Deed:
    """A killing on record that nobody has been told of."""
    slay(state, "zhao")
    deed = Deed(
        id="deed-1",
        actor_id="lin",
        kind="kill",
        text="Lin drowned Zhao in the well",
        turn=1,
        world_s=state.world_s,
        place_id="well",
        victim_ids=["zhao"],
        severity=4,
        visibility=Visibility.WITNESSED,
        witness_ids=["wei"],
        known_by=["lin", "wei"],
    )
    state.deeds[deed.id] = deed
    return deed


# --- People (W4) --------------------------------------------------------------------------------


def test_one_witnesss_word_brings_a_friend_of_the_dead_to_face_the_doer_and_revenge_only_after():
    after = killing(with_a_friend(well(sect=False)))
    deed = the_deed(after)

    assert not proven(after, deed)  # Wei's word is all there is
    mei = toward_lin(after, "mei")
    assert [g.deed_id for g in mei.grudges] == [deed.id] and "mei" in deed.known_by
    (comes,) = coming(after)
    assert comes.payload["answer"] == Answer.CONFRONT.value
    assert "not to attack" in comes.title and "Zhao" in comes.title

    # She finds him at the well and puts it to his face. Only then is revenge on its way.
    after, fired = idle(after, comes.due_s)
    (faced,) = [e for e in fired if e.id == comes.id]
    assert faced.status is EventStatus.APPLIED and faced.needs_player
    (revenge,) = coming(after)
    assert revenge.payload["answer"] == Answer.REVENGE.value and revenge.payload["faced"]
    assert revenge.due_s >= comes.due_s + 6 * HOUR

    after, fired = idle(after, revenge.due_s)
    (came,) = [e for e in fired if e.id == revenge.id]
    assert came.status is EventStatus.APPLIED and came.needs_player


def test_memory_tells_who_came_over_it_and_nothing_of_what_went_on_out_of_the_doers_sight():
    """C6: word reaching Mei and her setting out are nothing Lin could know. Her coming is."""
    state = with_a_friend(well(sect=False))
    state.characters["mei"].known_by.append("lin")
    after = killing(state)
    (comes,) = coming(after)

    (entry,) = memory_view(after).deeds
    assert entry.trail == [] and entry.open_label is not None  # Wei saw it: who else knows?

    after, _ = idle(after, comes.due_s)
    (entry,) = memory_view(after).deeds
    assert [(t.kind.value, t.text) for t in entry.trail] == [
        ("came", "Mei came to face you over it, moments ago")
    ]

    (revenge,) = coming(after)
    after, _ = idle(after, revenge.due_s)
    (entry,) = memory_view(after).deeds
    assert [t.text.rsplit(",", 1)[0] for t in entry.trail] == [
        "Mei came to face you over it",
        "Mei came for revenge",
    ]


@pytest.mark.parametrize("changed", ["cowed", "won over"])
def test_someone_cowed_or_won_over_after_facing_the_doer_comes_for_nothing_more(changed):
    after = killing(with_a_friend(well(sect=False)))
    (comes,) = coming(after)
    after, _ = idle(after, comes.due_s)
    (revenge,) = coming(after)
    grudges = toward_lin(after, "mei").grudges
    if changed == "cowed":
        feels(after, "mei", fear=80, affinity=-60, grudges=grudges)
    else:
        feels(after, "mei", affinity=10, grudges=grudges)

    after, fired = idle(after, revenge.due_s)

    (dropped,) = [e for e in fired if e.id == revenge.id]
    assert dropped.status is EventStatus.CANCELLED and not dropped.needs_player
    assert not coming(after)


def test_someone_too_afraid_of_the_doer_never_comes_to_face_them():
    after = killing(with_a_friend(well(sect=False)))
    (comes,) = coming(after)
    feels(after, "mei", fear=80, affinity=-60)

    after, fired = idle(after, comes.due_s)

    (dropped,) = [e for e in fired if e.id == comes.id]
    assert dropped.status is EventStatus.CANCELLED and not coming(after)


def test_revenge_that_finds_the_doer_gone_is_still_called_off_once_they_let_it_rest():
    after = killing(with_a_friend(well(sect=False)))
    (comes,) = coming(after)
    after, _ = idle(after, comes.due_s)
    (revenge,) = coming(after)
    after.characters["lin"].location_id = "inner-court"  # he has gone by the time she comes

    after, _ = idle(after, revenge.due_s)

    (again,) = coming(after)  # she goes on looking for him
    assert again.payload["answer"] == Answer.REVENGE.value and again.payload["faced"]
    feels(after, "mei", affinity=10, grudges=toward_lin(after, "mei").grudges)
    after, fired = idle(after, again.due_s)
    (dropped,) = [e for e in fired if e.id == again.id]
    assert dropped.status is EventStatus.CANCELLED


@pytest.mark.parametrize("beyond_doubt", ["two saw it", "a crowd saw it"])
def test_what_is_beyond_one_persons_word_brings_revenge_with_no_accusation_first(beyond_doubt):
    state = with_a_friend(well(sect=False))
    if beyond_doubt == "two saw it":
        after = killing(with_a_second_witness(state))
    else:
        after = killing(state, visibility=Visibility.PUBLIC)

    assert proven(after, the_deed(after))
    (comes,) = coming(after)
    assert comes.payload["answer"] == Answer.REVENGE.value and not comes.payload.get("faced")


def test_what_someone_saw_done_needs_nobodys_word():
    """Mei stands at the well herself: she saw it, so she comes for revenge."""
    state = with_a_friend(well(sect=False))
    state.characters["mei"].location_id = "well"
    state.scene.present_ids.append("mei")
    state.characters["wei"].location_id = "inner-court"
    state.scene.present_ids.remove("wei")

    after = play(state, deed_step(kill(), dead=("zhao",))).state

    assert the_deed(after).witness_ids == ["mei"]
    (comes,) = coming(after)
    assert comes.payload["answer"] == Answer.REVENGE.value


def test_talk_alone_leaves_no_grudge_and_the_rest_counts_once_someone_who_knows_tells_it():
    after = killing(with_a_comrade(well(sect=False)))
    deed = the_deed(after)

    # Bo heard what goes round the well, which is one man's story (W2).
    bo = toward_lin(after, "bo")
    assert bo.affinity < 0 and bo.trust < 0 and not bo.grudges
    assert deed.heard_by["bo"] == pytest.approx(0.9) and "bo" not in deed.known_by
    assert not coming(after, "bo")
    heard = bo.affinity

    character_learns(at(after), "bo", deed, grounds=Grounds.TOLD)

    bo = toward_lin(after, "bo")
    assert [g.deed_id for g in bo.grudges] == [deed.id]
    assert "bo" not in deed.heard_by
    # No more than if he had been told in the first place: the talk already counted.
    fresh = with_a_comrade(well(sect=False))
    told = secret_killing(fresh)
    character_learns(at(fresh), "bo", told, grounds=Grounds.TOLD)
    assert heard > bo.affinity >= toward_lin(fresh, "bo").affinity - 1


def test_the_same_talk_heard_again_changes_nothing():
    state = with_a_comrade(well(sect=False))
    deed = secret_killing(state)
    character_learns(at(state), "bo", deed, weight=0.7, grounds=Grounds.HEARD)
    once = toward_lin(state, "bo").model_copy(deep=True)

    character_learns(at(state), "bo", deed, weight=0.9, grounds=Grounds.HEARD)

    assert toward_lin(state, "bo") == once


def test_talk_of_what_is_beyond_one_persons_word_counts_as_knowing():
    after = killing(with_a_second_witness(with_a_comrade(well(sect=False))))
    deed = the_deed(after)

    bo = toward_lin(after, "bo")
    assert [g.deed_id for g in bo.grudges] == [deed.id]
    assert "bo" in deed.known_by and "bo" not in deed.heard_by


# --- Factions (W5, W11) -------------------------------------------------------------------------


def answers(state: WorldState, faction_id: str = SECT) -> list[str]:
    return [
        e.payload["answer"]
        for e in pending_of(state, Kind.ANSWER)
        if e.payload["faction_id"] == faction_id
    ]


def test_on_talk_those_who_keep_the_law_come_to_look_into_it_and_not_to_arrest():
    state = well()
    deed = secret_killing(state)

    faction_learns(at(state), SECT, deed, weight=0.7, grounds=Grounds.HEARD)

    assert answers(state) == [Answer.INVESTIGATE.value]
    assert deed.heard_by_factions == {SECT: 0.7} and not knows(state)
    assert state.factions[SECT].player_reputation.fear > 0  # they believe some of it


def test_those_who_look_into_it_take_the_word_of_a_witness_who_is_still_there():
    state = well()
    deed = secret_killing(state)
    faction_learns(at(state), SECT, deed, weight=0.7, grounds=Grounds.HEARD)
    (looking,) = pending_of(state, Kind.ANSWER)
    state.characters["lin"].location_id = "inner-court"  # he is long gone from the well

    state, _ = idle(moved_on(state), looking.due_s)

    assert knows(state) and SECT not in state.deeds[deed.id].heard_by_factions
    assert answers(state) == [Answer.ARREST.value]
    # They came for what happened, with nobody to look for yet.
    (came,) = [f for f in state.facts.values() if "look into" in f.text]
    assert came.text.endswith("comes to look into what happened at the outer-court well.")
    assert "lin" not in came.subject_ids


@pytest.mark.parametrize("silenced", ["dead", "cowed", "gone"])
def test_with_no_witness_there_to_ask_and_nothing_left_behind_it_stays_talk(silenced):
    state = well()
    deed = secret_killing(state)
    faction_learns(at(state), SECT, deed, weight=0.7, grounds=Grounds.HEARD)
    (looking,) = pending_of(state, Kind.ANSWER)
    state.characters["lin"].location_id = "inner-court"
    if silenced == "dead":
        slay(state, "wei")
    elif silenced == "cowed":
        feels(state, "wei", fear=80)
    else:
        state.characters["wei"].location_id = "inner-court"

    state, _ = idle(moved_on(state), looking.due_s + DAY)

    assert not knows(state) and state.deeds[deed.id].heard_by_factions == {SECT: 0.7}
    assert answers(state) == []  # they looked, and found nobody to lay it on


def test_knowing_who_did_it_ends_the_look_into_it():
    state = well()
    deed = secret_killing(state)
    faction_learns(at(state), SECT, deed, weight=0.7, grounds=Grounds.HEARD)
    (looking,) = pending_of(state, Kind.ANSWER)
    before = state.factions[SECT].player_reputation.model_copy()

    faction_learns(at(state), SECT, deed)  # Wei reaches them after all

    assert state.pending_events[looking.id].status is EventStatus.CANCELLED
    assert answers(state) == [Answer.ARREST.value] and knows(state)
    # The rest of it counts now, and no more than if they had been told in the first place.
    fresh = well()
    told = secret_killing(fresh)
    faction_learns(at(fresh), SECT, told)
    after = state.factions[SECT].player_reputation
    assert after.fear > before.fear
    assert after.fear <= fresh.factions[SECT].player_reputation.fear + 1


def test_a_faction_whose_own_were_struck_waits_for_word_from_someone_who_knows():
    state = with_a_comrade(well(sect=False))
    deed = secret_killing(state)
    brotherhood = state.factions[BROTHERHOOD]

    faction_learns(at(state), BROTHERHOOD, deed, weight=0.7, grounds=Grounds.HEARD)

    assert brotherhood.player_reputation.esteem < 0  # they think worse of him already
    assert brotherhood.threat == 0 and answers(state, BROTHERHOOD) == []

    faction_learns(at(state), BROTHERHOOD, deed)

    assert brotherhood.threat > 0 and len(answers(state, BROTHERHOOD)) == 1


def test_talk_of_what_the_player_did_brings_nobody_to_take_hurt_or_kill():
    """Over many draws: a faction that only heard of a massacre answers the threat it now sees
    with what isn't hostile, and one that was told may send hunters."""
    drawn: dict[Grounds, set[str]] = {Grounds.HEARD: set(), Grounds.TOLD: set()}
    for grounds in drawn:
        for turn in range(2, 42):
            state = well(sect=False)
            state.factions["river-gang"] = Faction(id="river-gang", name="the River Gang")
            deed = secret_killing(state)
            deed.kind, deed.severity = "massacre", 5
            faction_learns(at(state, turn), "river-gang", deed, weight=0.9, grounds=grounds)
            drawn[grounds].update(answers(state, "river-gang"))

    hostile = {a.value for a in HOSTILE}
    assert drawn[Grounds.HEARD] and not drawn[Grounds.HEARD] & hostile
    assert drawn[Grounds.TOLD] & hostile


def test_talk_of_what_two_saw_is_enough_for_the_law():
    state = with_a_second_witness(well())
    deed = secret_killing(state)
    deed.witness_ids.append("jun")

    faction_learns(at(state), SECT, deed, weight=0.7, grounds=Grounds.HEARD)

    assert knows(state) and answers(state) == [Answer.ARREST.value]


@pytest.mark.parametrize("second_voice", ["dead", "cowed", "devoted"])
def test_what_two_saw_is_one_persons_word_again_once_one_of_them_wont_say_so(second_voice):
    state = with_a_second_witness(well(sect=False))
    after = play(state, deed_step(ProposedDeed(kind="kill", text="x", victim_ids=["zhao"]))).state
    deed = the_deed(after)
    slay(after, "zhao")

    assert set(deed.witness_ids) >= {"wei", "jun"} and proven(after, deed)
    if second_voice == "dead":
        slay(after, "jun")
    elif second_voice == "cowed":
        feels(after, "jun", fear=80)
    else:
        feels(after, "jun", affinity=80)
    assert not proven(after, deed)
