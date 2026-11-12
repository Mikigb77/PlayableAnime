"""Word needs someone to carry it (W2, W3, W11, W13, `engine.world.carriers`).

Miki, 2026-11-11: only the people in the scene can be witnesses, so what becomes of them decides
what the world learns. A witness who is killed, bound, cowed or won over tells nobody, another
who can takes the word instead, and nothing of a deed goes round (the rumor, the region's
opinion, the news to the victim's family) until a witness is free to talk.
"""

import pytest

from engine import pipeline
from engine.base import DAY, HOUR, MINUTE
from engine.contracts import ProposedDeed
from engine.samples import cultivation_world
from engine.state import (
    Character,
    CharacterStatus,
    Connection,
    ConnectionKind,
    DeathCertainty,
    Encounter,
    EncounterKind,
    EventStatus,
    PassingState,
    PendingEvent,
    Place,
    Visibility,
    WorldState,
)
from engine.state.sheet import Attitude
from engine.world import Kind, carriers
from engine.world.tuning import CHATTER_S, FLEE_S

from .test_world import deed_step, idle, moved_on, pending_of, play, the_deed

SECT = "azure-cloud"
WALK_S = 40 * MINUTE  # from the well to the inner court, where the sect sits


def well(*, sect: bool = True) -> WorldState:
    """Lin and Zhao at the well, with Wei looking on. The sect holds the inner court, forty
    minutes away on foot in a world without phones. Without `sect`, nobody holds the place or
    keeps a law there, so there is nobody to tell and all that can happen is talk."""
    state = cultivation_world()
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    if sect:
        state.places["inner-court"].controller_id = SECT
    else:
        state.bible.laws = []
    state.characters["zhao"].memberships = []
    return state


def shove(**more) -> ProposedDeed:
    return ProposedDeed(
        kind="assault", text="Lin shoves Zhao into the well", victim_ids=["zhao"], **more
    )


def kill(**more) -> ProposedDeed:
    return ProposedDeed(
        kind="kill", text="Lin drowns Zhao in the well", victim_ids=["zhao"], **more
    )


def shoved(state: WorldState | None = None, **more) -> WorldState:
    return play(state or well(), deed_step(shove(**more))).state


def killed(state: WorldState | None = None, **more) -> WorldState:
    return play(state or well(), deed_step(kill(**more), dead=("zhao",))).state


def report(state: WorldState, witness_id: str = "wei") -> PendingEvent:
    (event,) = [
        e
        for e in pending_of(state, Kind.REPORT)
        if e.payload["witness_id"] == witness_id and e.payload["faction_id"] == SECT
    ]
    return event


def knows(state: WorldState, faction_id: str = SECT) -> bool:
    return faction_id in the_deed(state).known_by_factions


def slay(state: WorldState, *ids: str) -> None:
    for character_id in ids:
        state.characters[character_id].status = CharacterStatus.DEAD
        state.characters[character_id].death_certainty = DeathCertainty.CONFIRMED


def standing(state: WorldState) -> dict:
    """W3: what every region and faction makes of the player."""
    return {r.id: r.player_reputation for r in (*state.places.values(), *state.factions.values())}


def bind(state: WorldState, character_id: str) -> None:
    state.characters[character_id].sheet.condition.states.append(PassingState(name="bound"))


def feels(state: WorldState, character_id: str, **attitude: int) -> None:
    state.characters[character_id].sheet.disposition.attitudes["lin"] = Attitude(**attitude)


# --- Reports (W11) ------------------------------------------------------------------------------


def test_a_bystander_runs_to_tell_and_the_one_it_fell_on_stays_to_deal_with_the_doer():
    after = shoved()

    event = report(after)
    assert not [e for e in pending_of(after, Kind.REPORT) if e.payload["witness_id"] == "zhao"]
    left_s = event.payload["sets_off_s"] - the_deed(after).world_s
    assert FLEE_S[0] <= left_s <= FLEE_S[1]
    assert event.due_s == event.payload["sets_off_s"] + WALK_S
    assert not knows(after)  # the sect hears when he gets there (W10)


def test_a_witness_who_is_killed_tells_nobody_and_another_takes_the_word_from_then():
    after = shoved()
    first = report(after)
    slay(after, "wei")

    after, fired = idle(after, first.due_s)

    # Wei's report came to nothing, and Zhao, who saw it too, sets off only now.
    (dropped,) = [e for e in fired if e.id == first.id]
    assert dropped.status is EventStatus.CANCELLED and not knows(after)
    second = report(after, "zhao")
    assert second.payload["sets_off_s"] >= first.due_s + FLEE_S[0]
    after, _ = idle(after, second.due_s)
    assert knows(after) and after.characters["zhao"].location_id == "inner-court"


@pytest.mark.parametrize("silenced", ["dead", "bound", "cowed", "won over"])
def test_with_no_witness_able_and_willing_nobody_is_told(silenced):
    state = well()
    state.characters["zhao"].status = CharacterStatus.MISSING  # only Wei is left to tell
    after = shoved(state, witness_ids=["wei"])
    first = report(after)
    if silenced == "dead":
        slay(after, "wei")
    elif silenced == "bound":
        bind(after, "wei")
    elif silenced == "cowed":
        feels(after, "wei", fear=80)
    else:
        feels(after, "wei", affinity=60)
    assert carriers.runners(after) == []  # he is going nowhere, so no scene shows him go

    after, _ = idle(moved_on(after), first.due_s + DAY)

    deed = the_deed(after)
    assert not knows(after) and deed.word_out_s is None
    assert not [r for r in after.rumors.values() if r.deed_id == deed.id]
    assert standing(after) == standing(well())  # W3: the region's opinion never moved


def test_a_bound_witness_tells_once_they_are_free():
    state = well()
    state.characters["zhao"].status = CharacterStatus.MISSING
    after = shoved(state, witness_ids=["wei"])
    bind(after, "wei")
    after, _ = idle(after, 3 * HOUR)

    # The report waits for him: the world asks again later, each time after as long again.
    waiting = report(after)
    assert waiting.payload["waits"] and "sets_off_s" not in waiting.payload
    assert waiting.due_s > after.world_s and not knows(after)
    assert "lin" not in waiting.subject_ids  # nothing the player character could notice (C6)

    # Cut loose, he is asked at once instead of hours later, and sets off.
    after.characters["wei"].sheet.condition.states.clear()
    assert carriers.unsettled(after)
    carriers.settle(after)
    assert waiting.due_s <= after.world_s
    after, _ = idle(after, after.world_s + 1)
    going = report(after)
    assert going.payload["sets_off_s"] > after.world_s - 1
    after, _ = idle(after, going.due_s)
    assert knows(after)


def test_a_witness_fighting_the_player_character_gets_no_word_out_until_the_fight_lets_go():
    after = shoved()
    first = report(after)
    after.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["wei", "zhao"], started_turn=2, started_s=0
    )
    assert carriers.runners(after) == []
    after.world_s = first.payload["sets_off_s"]
    assert carriers.settle(after) == [] and "wei" in after.scene.present_ids

    after, _ = idle(after, first.due_s)
    assert not knows(after) and report(after).payload.get("waits")

    # The fight over, whoever of them can sets off.
    after.scene.encounter = None
    carriers.settle(after)
    after, _ = idle(after, after.world_s + 1)
    going = report(after)
    assert "sets_off_s" in going.payload
    after, _ = idle(after, going.due_s)
    assert knows(after)


def test_what_was_done_before_a_crowd_is_reported_whatever_becomes_of_one_witness():
    after = shoved(visibility=Visibility.PUBLIC)
    first = report(after)
    slay(after, "wei", "zhao")

    after, _ = idle(after, first.due_s)

    assert knows(after)  # someone else of the crowd went


def test_a_report_scheduled_before_word_needed_a_carrier_still_lands():
    after = shoved()
    old = report(after)
    del old.payload["sets_off_s"]

    assert carriers.runners(after) == [] and not carriers.unsettled(after)
    after, _ = idle(after, old.due_s)

    assert knows(after) and after.characters["wei"].location_id == "inner-court"


# --- The scene (W11) ----------------------------------------------------------------------------


def test_the_scene_shows_who_is_off_to_tell_until_they_set_off_and_then_they_are_out_of_it():
    after = shoved()
    event = report(after)

    (runner,) = carriers.runners(after)
    assert (runner.witness_id, runner.faction_id) == ("wei", SECT)
    assert runner.sets_off_s == event.payload["sets_off_s"] > after.world_s
    assert carriers.settle(after) == [] and "wei" in after.scene.present_ids  # still in reach

    after.world_s = runner.sets_off_s
    assert carriers.settle(after) == ["wei"]
    assert after.scene.present_ids == ["lin", "zhao"]
    # Out of the scene, he is nobody the next one shows going.
    assert carriers.runners(after) == []


def test_a_witness_the_scenes_end_left_out_is_within_reach_until_they_set_off():
    after = shoved()
    after.turn = 2  # the scene that told the shove is over, and its end didn't list Wei
    after.scene.present_ids = ["lin", "zhao"]

    (runner,) = carriers.runners(after)
    assert runner.witness_id == "wei"
    after.world_s = runner.sets_off_s
    assert carriers.runners(after) == [] and carriers.settle(after) == []

    # Someone who saw a deed done somewhere else is nobody this scene shows going.
    away = shoved()
    away.turn = 2
    away.scene.present_ids = ["lin"]
    away.scene.place_id = away.player.location_id = "inner-court"
    assert carriers.runners(away) == [] and carriers.runners(away, turn=2) == []
    # Nor is one from a scene told before the last one.
    old = shoved()
    old.turn = 3
    old.scene.present_ids = ["lin", "zhao"]
    assert carriers.runners(old) == []


def test_the_scene_that_tells_a_turn_is_told_who_ran_in_it_though_no_scene_listed_them():
    state = well()
    state.scene.present_ids = ["lin", "zhao"]  # Wei is one of a crowd no scene has shown
    after = shoved(state, visibility=Visibility.PUBLIC)

    assert carriers.runners(after) == []
    (runner,) = carriers.runners(after, turn=2)
    assert runner.witness_id == "wei"

    # A turn that lasted until he had told the sect: he left the scene in it.
    state = well()
    played = play(state, deed_step(shove()), deed_step(duration_s=HOUR), turn=2)
    assert knows(played.state) and "wei" not in played.state.scene.present_ids
    assert [r.witness_id for r in carriers.runners(played.state, turn=2)] == ["wei"]
    assert carriers.runners(played.state, turn=3) == []


def test_the_deed_keeps_whom_the_character_saw_set_off_to_tell_and_to_whom():
    """C6: it is theirs to remember. Whether he got there is nothing they know."""
    after = shoved()
    assert the_deed(after).went_to_tell == {}  # still in the scene, within reach

    after.world_s = report(after).payload["sets_off_s"]
    carriers.settle(after)
    assert the_deed(after).went_to_tell == {"wei": SECT} and not knows(after)

    # One who got away while a long step played went in front of them too.
    played = play(well(), deed_step(shove()), deed_step(duration_s=HOUR), turn=2)
    assert the_deed(played.state).went_to_tell == {"wei": SECT}

    # A crowd's witness no scene had listed yet ran in the scene that told the deed.
    state = well()
    state.scene.present_ids = ["lin", "zhao"]
    played = play(
        state,
        deed_step(shove(visibility=Visibility.PUBLIC)),
        deed_step(duration_s=HOUR),
        turn=2,
    )
    assert the_deed(played.state).went_to_tell == {"wei": SECT}


def test_a_witness_who_sets_off_once_the_character_is_gone_is_nobody_they_saw_go():
    after = shoved()
    event = report(after)
    after.turn = 3
    after.scene.present_ids = ["lin"]
    after.scene.place_id = after.player.location_id = "inner-court"

    after.world_s = event.payload["sets_off_s"]
    carriers.settle(after)
    after, _ = idle(after, event.due_s)

    assert knows(after) and the_deed(after).went_to_tell == {}

    # Nor one who is stopped before he sets off.
    stopped = shoved()
    slay(stopped, "wei")
    stopped.world_s = report(stopped).payload["sets_off_s"]
    carriers.settle(stopped)
    assert the_deed(stopped).went_to_tell == {}

    # Nor a watcher they never noticed, though he runs like anyone.
    hidden = shoved(unnoticed_witness_ids=["wei"])
    hidden.world_s = report(hidden).payload["sets_off_s"]
    assert carriers.settle(hidden) == ["wei"] and the_deed(hidden).went_to_tell == {}


def ended(played: WorldState, *present: str, turn: int = 2) -> tuple[WorldState, list[str]]:
    """The scene of `played` once its end listed only `present`, and who code kept in it."""
    after = played.model_copy(deep=True)
    after.scene.present_ids = list(present)
    return after, carriers.keep(after, played, turn)


def test_a_scenes_end_takes_nobody_out_of_it_who_has_word_to_bring_and_hasnt_gone():
    """Who runs is code's to decide (W11). On the real model (2026-11-11) the narrator ended a
    scene without the witness, and nothing after it had the character see him go."""
    played = shoved()

    # The scene that told the shove ended without Wei, who is yet to set off: he is still in it.
    after, kept = ended(played, "lin", "zhao")
    assert kept == ["wei"] and after.scene.present_ids == ["lin", "zhao", "wei"]
    assert the_deed(after).went_to_tell == {} and carriers.settle(after) == []
    # One its end listed is nobody code had to put back.
    assert ended(played, "lin", "zhao", "wei")[1] == []

    # Nor is a watcher nobody noticed, or someone who wasn't in the scene as it played.
    hidden = shoved(unnoticed_witness_ids=["wei"])
    after, kept = ended(hidden, "lin", "zhao")
    assert kept == [] and after.scene.present_ids == ["lin", "zhao"]
    old = shoved()
    old.scene.present_ids = ["lin", "zhao"]
    assert ended(old, "lin", "zhao", turn=3) == (old, [])


def test_a_witness_the_scenes_end_left_out_once_he_had_set_off_went_in_front_of_them():
    played = shoved()
    played.world_s = report(played).payload["sets_off_s"]

    # The scene was told he got away while it played, and left him out as it should.
    after, kept = ended(played, "lin", "zhao")

    assert kept == [] and after.scene.present_ids == ["lin", "zhao"]
    assert the_deed(after).went_to_tell == {"wei": SECT}
    assert carriers.settle(after) == []  # nobody left whom its end still listed

    # One the scene sent somewhere else before he had set off went in front of them too.
    played = shoved()
    after = played.model_copy(deep=True)
    after.scene.present_ids = ["lin", "zhao"]
    after.characters["wei"].location_id = "inner-court"
    assert carriers.keep(after, played, 2) == []
    assert the_deed(after).went_to_tell == {"wei": SECT}


def test_a_witness_held_in_a_fight_is_in_the_scene_whatever_its_end_listed():
    played = shoved()
    played.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT, opponent_ids=["wei"], started_turn=2, started_s=played.world_s
    )
    played.world_s = report(played).payload["sets_off_s"] + MINUTE

    assert [r.witness_id for r in carriers.held(played)] == ["wei"]
    assert carriers.runners(played) == []  # he is going nowhere while it lasts
    after, kept = ended(played, "lin", "zhao")
    assert kept == ["wei"] and "wei" in after.scene.present_ids
    assert the_deed(after).went_to_tell == {} and carriers.settle(after) == []

    # The fight over, he goes, and they see it.
    after.scene.encounter = None
    assert carriers.held(after) == [] and carriers.settle(after) == ["wei"]
    assert the_deed(after).went_to_tell == {"wei": SECT}


def test_a_scene_that_ends_somewhere_else_leaves_its_witnesses_behind():
    played = shoved()
    after = played.model_copy(deep=True)
    after.scene.present_ids = ["lin"]
    after.scene.place_id = after.player.location_id = "inner-court"

    assert carriers.keep(after, played, 2) == []
    assert after.scene.present_ids == ["lin"] and the_deed(after).went_to_tell == {}

    # Also out in the place around the well, though not at a spot inside it.
    around = played.model_copy(deep=True)
    around.scene.present_ids = ["lin"]
    around.scene.place_id = around.player.location_id = "azure-peak"
    assert carriers.keep(around, played, 2) == [] and around.scene.present_ids == ["lin"]
    inside = played.model_copy(deep=True)
    inside.places["bucket-side"] = Place(id="bucket-side", name="by the bucket", parent_id="well")
    inside.scene.present_ids = ["lin"]
    inside.scene.place_id = inside.player.location_id = "bucket-side"
    assert carriers.keep(inside, played, 2) == ["wei"]


# --- Talk (W2, W3, W4) --------------------------------------------------------------------------


def nothing_out(state: WorldState) -> bool:
    deed = the_deed(state)
    return (
        deed.word_out_s is None
        and not [r for r in state.rumors.values() if r.deed_id == deed.id]
        and not pending_of(state, Kind.TIDINGS)
        and standing(state) == standing(well())
    )


def with_sister(state: WorldState) -> WorldState:
    """Zhao's sister lives at the inner court."""
    mei = Character(id="mei", name="Zhao Mei", location_id="inner-court")
    mei.sheet.resources.connections.append(
        Connection(name="Zhao Kun", kind=ConnectionKind.FAMILY, character_id="zhao")
    )
    state.characters["mei"] = mei
    return state


def test_nothing_of_a_deed_goes_round_while_its_witnesses_are_with_the_player_who_did_it():
    after = killed(with_sister(well(sect=False)))
    assert nothing_out(after)
    (ask,) = pending_of(after, Kind.WORD)
    assert CHATTER_S[0] <= ask.due_s - the_deed(after).world_s <= CHATTER_S[1]
    assert ask.subject_ids == []  # nothing the player character could notice (C6)

    # Three hours on Wei is still in the scene, so he has told nobody.
    after, _ = idle(after, 3 * HOUR)
    assert nothing_out(after)
    (again,) = pending_of(after, Kind.WORD)
    assert again.payload["again"] and again.due_s > after.world_s

    # The scene lets go of him: the world asks at once, and word is out.
    moved_on(after)
    carriers.settle(after)
    after, _ = idle(after, after.world_s + 1)
    deed = the_deed(after)
    assert deed.word_out_s == after.world_s - 1
    (rumor,) = [r for r in after.rumors.values() if r.deed_id == deed.id]
    assert rumor.is_true and "wei" in rumor.heard_at
    assert standing(after) != standing(well())  # W3
    # W4: word sets off to his sister, who learns who did it when it reaches her.
    (tidings,) = pending_of(after, Kind.TIDINGS)
    assert tidings.payload["character_id"] == "mei"
    after, _ = idle(after, tidings.due_s)
    assert "mei" in the_deed(after).known_by


def test_once_nobody_who_would_talk_is_able_to_the_deed_is_the_worlds_to_find_from_the_body():
    after = killed(with_sister(well(sect=False)))
    slay(after, "wei")

    after, _ = idle(moved_on(after), 2 * HOUR)

    # Nobody told, so no rumor names Lin. What is left is two dead at the well, and people who
    # will miss them, looked for as a secret deed's traces are (W13).
    deed = the_deed(after)
    assert deed.word_out_s is None and not pending_of(after, Kind.WORD)
    assert {t.kind.value for t in deed.traces} >= {"ties"}
    looks = [e for e in after.pending_events.values() if e.kind == Kind.DISCOVERY]
    assert looks


def test_a_deed_nobody_can_tell_of_is_looked_for_once_however_often_the_world_asks():
    after = killed(with_sister(well(sect=False)))
    bind(after, "wei")  # he would talk, and can't: the world keeps asking
    (first,) = pending_of(after, Kind.WORD)
    after, _ = idle(moved_on(after), first.due_s)
    (look,) = pending_of(after, Kind.DISCOVERY)
    (again,) = pending_of(after, Kind.WORD)

    # The look came to nothing and the traces have faded. Asked again, the world doesn't start
    # looking from the beginning.
    look.status = EventStatus.CANCELLED
    after, _ = idle(after, again.due_s)

    assert pending_of(after, Kind.WORD) and not pending_of(after, Kind.DISCOVERY)


def test_a_deed_before_a_crowd_is_out_at_once():
    after = killed(with_sister(well(sect=False)), visibility=Visibility.PUBLIC)

    deed = the_deed(after)
    assert deed.word_out_s == deed.world_s
    assert [r for r in after.rumors.values() if r.deed_id == deed.id]
    assert pending_of(after, Kind.TIDINGS) and not pending_of(after, Kind.WORD)


def test_what_an_npc_did_gets_out_once_people_have_had_their_time_to_talk():
    state = well(sect=False)
    step = deed_step(
        ProposedDeed(
            actor_id="zhao",
            kind="assault",
            text="Zhao shoves Wei into the well",
            victim_ids=["wei"],
        )
    )
    after = play(state, step, actor_id="zhao").state
    deed = the_deed(after)
    assert deed.word_out_s is None

    # Wei is in the scene with Lin, who did nothing: nobody is keeping him from talking.
    after, _ = idle(after, deed.world_s + CHATTER_S[1])

    assert the_deed(after).word_out_s is not None


def test_settling_a_scene_with_nothing_waiting_changes_nothing():
    state = well()

    assert not carriers.unsettled(state) and carriers.settle(state) == []
    assert state == well()
    # The turn's seam copies only when there is something to settle.
    same, left, kept = pipeline.settle_witnesses(state, state, 2)
    assert same is state and left == [] and kept == []
    after = shoved()
    after.world_s += FLEE_S[1]
    settled, left, kept = pipeline.settle_witnesses(after, after, 2)
    assert settled is not after and left == ["wei"] and "wei" in after.scene.present_ids
    assert kept == []
    # A witness its end left out who is yet to set off is put back, on the copy.
    played = shoved()
    after = played.model_copy(deep=True)
    after.scene.present_ids = ["lin", "zhao"]
    settled, left, kept = pipeline.settle_witnesses(played, after, 2)
    assert (left, kept) == ([], ["wei"]) and after.scene.present_ids == ["lin", "zhao"]
    assert settled.scene.present_ids == ["lin", "zhao", "wei"]


def test_the_same_deed_plays_the_same_way_again():
    one, _ = idle(moved_on(shoved()), DAY)
    two, _ = idle(moved_on(shoved()), DAY)

    assert one == two
