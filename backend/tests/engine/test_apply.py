"""apply_delta: the narrator proposes, the engine decides, and C1 holds either way."""

import pytest

from engine.apply import (
    MAX_PROGRESS,
    MAX_PROPS,
    NARRATOR_ATTITUDE_CAP,
    DeltaSource,
    apply_delta,
)
from engine.context import TurnContext
from engine.contracts import (
    AttitudeShift,
    CharacterChange,
    FactionChange,
    GoalEnd,
    GoalMoved,
    GoalOver,
    ItemChange,
    NewFact,
    NewLead,
    PlaceChange,
    RuleChange,
    SceneEnd,
    StateDelta,
)
from engine.invariants import check_transition
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Attributes,
    Cause,
    CauseMechanism,
    CauseRef,
    CharacterStatus,
    DeathCertainty,
    Deed,
    Encounter,
    EncounterKind,
    EventStatus,
    FactionStatus,
    Goal,
    GoalStatus,
    Judged,
    PendingEvent,
    PlaceStatus,
    Resurrection,
    Ruling,
    RulingSource,
    Talent,
    TalentBridge,
    TalentCover,
    TalentFit,
    TalentRuling,
    TalentStrength,
    WorldState,
)
from engine.state.cast import MAX_JUDGED

ENGINE = DeltaSource.ENGINE
NARRATOR = DeltaSource.NARRATOR


def ctx(turn: int) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn)


def apply(state: WorldState, source: DeltaSource = NARRATOR, turn: int = 3, **delta):
    return apply_delta(state, StateDelta(**delta), ctx(turn), source=source)


def reasons(applied) -> list[str]:
    return [r.reason for r in applied.rejected]


def kill(state: WorldState, cid: str, certainty=DeathCertainty.CONFIRMED) -> WorldState:
    change = CharacterChange(id=cid, status=CharacterStatus.DEAD, death_certainty=certainty)
    applied = apply(state, ENGINE, characters=[change])
    assert not applied.rejected
    return applied.state


def deed(state: WorldState, deed_id: str, *, subject: str, at_s: int, timeline="main") -> None:
    state.deeds[deed_id] = Deed(
        id=deed_id,
        actor_id=state.player_id,
        kind="ritual",
        text="A ritual",
        turn=3,
        world_s=at_s,
        timeline_id=timeline,
        target_ids=[subject],
    )


def cause(mechanism: CauseMechanism, ref_id: str, ref_kind=CauseRef.DEED) -> Cause:
    return Cause(mechanism=mechanism, ref_kind=ref_kind, ref_id=ref_id, text="because")


# --- the input is never changed ------------------------------------------------------------


def test_apply_delta_changes_neither_the_state_nor_the_delta():
    state = grounded_world()
    delta = StateDelta(
        characters=[
            CharacterChange(id="vito", name="Vito Greco", status=CharacterStatus.DEAD),
            CharacterChange(id="carmine", attitudes=[AttitudeShift(affinity=-5)]),
        ],
        facts=[NewFact(text="Vito was found in the harbour.", subject_ids=["vito"])],
    )
    state_before, delta_before = state.model_dump(), delta.model_dump()

    applied = apply_delta(state, delta, ctx(3), source=NARRATOR)

    assert state.model_dump() == state_before
    assert delta.model_dump() == delta_before
    assert applied.state.characters["vito"].status is CharacterStatus.DEAD


# --- names (C1) ----------------------------------------------------------------------------


@pytest.mark.parametrize("name", [None, "Unknown", "stranger", "  someone ", "?"])
def test_a_new_character_needs_a_real_name(name):
    applied = apply(grounded_world(), characters=[CharacterChange(id="x", name=name)])

    assert "x" not in applied.state.characters
    assert reasons(applied) == ["a new character needs a name (C1)"]


def test_new_records_get_names_and_the_narrator_origin():
    applied = apply(
        grounded_world(),
        places=[PlaceChange(id="docks", name="the docks", known_to_player=True)],
        factions=[FactionChange(id="camorra", name="the Camorra")],
        characters=[
            CharacterChange(id="vito", name="Vito Greco", location_id="docks", faction_id="camorra")
        ],
    )
    state = applied.state

    assert not applied.rejected
    assert state.characters["vito"].location_id == "docks"
    assert state.characters["vito"].memberships[0].faction_id == "camorra"
    assert state.characters["vito"].origin.kind.value == "narrator"
    assert "luca" in state.places["docks"].known_by
    nameless = apply(state, places=[PlaceChange(id="nowhere")])
    assert reasons(nameless) == ["a new place needs a name"]


def test_a_rename_keeps_the_old_name_as_an_alias_and_refuses_placeholders():
    state = apply(
        grounded_world(), characters=[CharacterChange(id="bartender", name="Gennaro Iovine")]
    ).state

    assert state.characters["bartender"].name == "Gennaro Iovine"
    assert state.characters["bartender"].aliases == ["Gennaro"]
    bad = apply(state, characters=[CharacterChange(id="bartender", name="Unknown")])
    assert bad.state.characters["bartender"].name == "Gennaro Iovine"
    assert bad.rejected[0].change == "rename"


def test_references_must_point_somewhere():
    applied = apply(
        grounded_world(),
        characters=[CharacterChange(id="carmine", location_id="moon", faction_id="ghosts")],
    )

    assert applied.state.characters["carmine"].location_id == "bar"
    assert [r.change for r in applied.rejected] == ["location", "faction"]


# --- deaths (C1, F4) -----------------------------------------------------------------------


def test_the_narrator_cannot_kill_but_the_engine_can():
    state = grounded_world()
    death = CharacterChange(id="carmine", status=CharacterStatus.DEAD)

    narrated = apply(state, characters=[death])
    resolved = apply(state, ENGINE, characters=[death])

    assert narrated.state.characters["carmine"].status is CharacterStatus.ALIVE
    assert "engine's resolution" in reasons(narrated)[0]
    carmine = resolved.state.characters["carmine"]
    assert carmine.status is CharacterStatus.DEAD
    assert carmine.death_certainty is DeathCertainty.CONFIRMED
    entry = carmine.status_history[-1]
    assert (entry.status, entry.from_status, entry.turn) == ("dead", "alive", 3)
    # Carmine is in the scene, so the player character knows.
    assert entry.known_by == ["luca"]


def test_an_off_screen_death_is_not_known_to_the_player():
    state = grounded_world()
    state.characters["carmine"].location_id = "questura"
    state.scene.present_ids = ["luca"]

    dead = kill(state, "carmine")

    assert dead.characters["carmine"].status_history[-1].known_by == []


def test_a_new_character_may_start_dead_as_news_of_the_past():
    applied = apply(
        grounded_world(),
        characters=[CharacterChange(id="don", name="Don Salvatore", status=CharacterStatus.DEAD)],
    )

    assert not applied.rejected
    assert applied.state.characters["don"].death_certainty is DeathCertainty.CONFIRMED


def test_the_dead_stay_dead_without_a_cause():
    state = kill(grounded_world(), "carmine")
    back = CharacterChange(id="carmine", status=CharacterStatus.ALIVE)

    narrated = apply(state, characters=[back])
    resolved = apply(state, ENGINE, characters=[back])

    assert narrated.state.characters["carmine"].status is CharacterStatus.DEAD
    assert resolved.state.characters["carmine"].status is CharacterStatus.DEAD
    assert reasons(resolved) == ["the dead stay dead without a cause"]


def test_resurrection_needs_a_world_that_allows_it():
    state = kill(grounded_world(), "carmine")
    deed(state, "rite", subject="carmine", at_s=0)
    back = CharacterChange(
        id="carmine",
        status=CharacterStatus.ALIVE,
        cause=cause(CauseMechanism.RESURRECTION, "rite"),
    )

    applied = apply(state, ENGINE, characters=[back])

    assert applied.state.characters["carmine"].status is CharacterStatus.DEAD
    assert reasons(applied) == ["nothing in this world brings back the dead"]


def resurrection_world() -> WorldState:
    state = cultivation_world()
    state.bible.medicine.resurrection = Resurrection.RARE
    state.world_s = 1000
    return kill(state, "zhao")


def test_resurrection_by_a_recorded_deed_that_names_them():
    state = resurrection_world()
    deed(state, "rite", subject="zhao", at_s=1000)
    back = CharacterChange(
        id="zhao", status=CharacterStatus.ALIVE, cause=cause(CauseMechanism.RESURRECTION, "rite")
    )

    applied = apply(state, ENGINE, characters=[back])

    zhao = applied.state.characters["zhao"]
    assert not applied.rejected
    assert zhao.status is CharacterStatus.ALIVE and zhao.death_certainty is None
    assert zhao.status_history[-1].cause.ref_id == "rite"
    assert check_transition(state, applied.state) == []


@pytest.mark.parametrize(
    ("setup", "ref_id", "expected"),
    [
        (lambda s: None, "nothing", "no recorded deed 'nothing'"),
        (lambda s: deed(s, "old", subject="zhao", at_s=10), "old", "came before"),
        (lambda s: deed(s, "other", subject="lin", at_s=1000), "other", "doesn't involve"),
        (
            lambda s: deed(s, "rewound", subject="zhao", at_s=1000, timeline="t2"),
            "rewound",
            "another timeline",
        ),
    ],
)
def test_a_resurrection_cause_must_be_real(setup, ref_id, expected):
    state = resurrection_world()
    setup(state)
    back = CharacterChange(
        id="zhao", status=CharacterStatus.ALIVE, cause=cause(CauseMechanism.RESURRECTION, ref_id)
    )

    applied = apply(state, ENGINE, characters=[back])

    assert applied.state.characters["zhao"].status is CharacterStatus.DEAD
    assert expected in reasons(applied)[0]


def test_a_cause_can_be_a_fired_event_but_not_one_still_pending():
    state = resurrection_world()
    state.pending_events["return"] = PendingEvent(
        id="return", kind="revival", due_s=5000, subject_ids=["zhao"]
    )
    back = CharacterChange(
        id="zhao",
        status=CharacterStatus.ALIVE,
        cause=cause(CauseMechanism.RESURRECTION, "return", CauseRef.EVENT),
    )

    early = apply(state, ENGINE, characters=[back])
    state.pending_events["return"].status = EventStatus.APPLIED
    state.pending_events["return"].applied_s = 5000
    state.world_s = 5000
    later = apply(state, ENGINE, characters=[back])

    assert reasons(early) == ["event 'return' hasn't happened"]
    assert later.state.characters["zhao"].status is CharacterStatus.ALIVE


def test_only_a_presumed_death_can_turn_out_false():
    presumed = kill(grounded_world(), "carmine", DeathCertainty.PRESUMED)
    confirmed = kill(grounded_world(), "carmine")
    for state in (presumed, confirmed):
        deed(state, "found", subject="carmine", at_s=0)
    back = CharacterChange(
        id="carmine", status=CharacterStatus.ALIVE, cause=cause(CauseMechanism.SURVIVED, "found")
    )

    survived = apply(presumed, ENGINE, characters=[back])
    refused = apply(confirmed, ENGINE, characters=[back])

    assert survived.state.characters["carmine"].status is CharacterStatus.ALIVE
    assert refused.state.characters["carmine"].status is CharacterStatus.DEAD
    assert reasons(refused) == ["a confirmed death never turns out false"]


def test_a_presumed_death_can_be_confirmed_by_the_engine_only_and_never_unconfirmed():
    state = kill(grounded_world(), "carmine", DeathCertainty.PRESUMED)
    assert state.characters["carmine"].status_history[-1].presumed
    confirm = CharacterChange(id="carmine", death_certainty=DeathCertainty.CONFIRMED)
    presume = CharacterChange(id="carmine", death_certainty=DeathCertainty.PRESUMED)

    narrated = apply(state, characters=[confirm])
    confirmed = apply(state, ENGINE, characters=[confirm])
    walked_back = apply(confirmed.state, ENGINE, characters=[presume])

    assert narrated.state.characters["carmine"].death_certainty is DeathCertainty.PRESUMED
    assert confirmed.state.characters["carmine"].death_certainty is DeathCertainty.CONFIRMED
    assert reasons(walked_back) == ["a confirmed death never becomes presumed"]


def test_the_narrator_cannot_give_a_cause_but_can_make_someone_missing():
    rite = cause(CauseMechanism.RESURRECTION, "x")
    applied = apply(
        grounded_world(),
        characters=[CharacterChange(id="carmine", status=CharacterStatus.MISSING, cause=rite)],
    )

    carmine = applied.state.characters["carmine"]
    assert carmine.status is CharacterStatus.MISSING
    assert carmine.status_history[-1].cause is None
    assert reasons(applied) == ["only the engine records a cause"]


# --- factions and places (C1, W7, W15a) -----------------------------------------------------


def test_only_the_engine_destroys_a_faction_and_it_returns_only_by_revival():
    state = grounded_world()
    destroy = FactionChange(id="carmine-crew", status=FactionStatus.DESTROYED)

    assert apply(state, factions=[destroy]).state.factions["carmine-crew"].status is (
        FactionStatus.INTACT
    )
    destroyed = apply(state, ENGINE, factions=[destroy]).state
    destroyed.world_s = 500
    deed(destroyed, "regroup", subject="carmine-crew", at_s=500)
    revival = cause(CauseMechanism.REVIVAL, "regroup")

    as_intact = apply(
        destroyed,
        ENGINE,
        factions=[FactionChange(id="carmine-crew", status=FactionStatus.INTACT, cause=revival)],
    )
    nobody_left = apply(
        destroyed,
        ENGINE,
        factions=[FactionChange(id="carmine-crew", status=FactionStatus.REBUILDING, cause=revival)],
    )
    destroyed.factions["carmine-crew"].survivors = ["two soldiers who were in Rome"]
    revived = apply(
        destroyed,
        ENGINE,
        factions=[FactionChange(id="carmine-crew", status=FactionStatus.REBUILDING, cause=revival)],
    )

    assert reasons(as_intact) == ["a destroyed faction comes back only as rebuilding"]
    assert reasons(nobody_left) == ["nobody survived to carry it on"]
    assert revived.state.factions["carmine-crew"].status is FactionStatus.REBUILDING
    assert check_transition(destroyed, revived.state) == []


def test_a_ruined_place_recovers_only_by_rebuilding():
    state = grounded_world()
    ruin = PlaceChange(id="bar", status=PlaceStatus.RUINED)
    assert apply(state, places=[ruin]).state.places["bar"].status is PlaceStatus.THRIVING
    ruined = apply(state, ENGINE, places=[ruin]).state
    deed(ruined, "rebuild", subject="bar", at_s=0)
    repair = PlaceChange(id="bar", status=PlaceStatus.DAMAGED)

    no_cause = apply(ruined, ENGINE, places=[repair])
    wrong = apply(
        ruined,
        ENGINE,
        places=[repair.model_copy(update={"cause": cause(CauseMechanism.REVIVAL, "rebuild")})],
    )
    rebuilt = apply(
        ruined,
        ENGINE,
        places=[repair.model_copy(update={"cause": cause(CauseMechanism.REBUILD, "rebuild")})],
    )

    assert reasons(no_cause) == ["a ruined place recovers only with a cause (C1)"]
    assert "revival can't change this" in reasons(wrong)[0]
    assert rebuilt.state.places["bar"].status is PlaceStatus.DAMAGED
    assert rebuilt.state.places["bar"].status_history[-1].from_status == "ruined"


def test_faction_reputation_is_the_engines_and_stays_in_bounds():
    state = grounded_world()
    change = FactionChange(id="police", esteem=-100, fear=100)

    narrated = apply(state, factions=[change])
    resolved = apply(apply(state, ENGINE, factions=[change]).state, ENGINE, factions=[change])

    assert narrated.state.factions["police"].player_reputation.fear == 0
    assert narrated.rejected[0].change == "reputation"
    rep = resolved.state.factions["police"].player_reputation
    assert (rep.esteem, rep.fear) == (-100, 100)


# --- attitudes (W4) ------------------------------------------------------------------------


def test_the_narrator_nudges_attitudes_within_a_cap_however_it_splits_them():
    state = grounded_world()
    shifts = [AttitudeShift(affinity=8), AttitudeShift(affinity=8), AttitudeShift(trust=-30)]

    applied = apply(state, characters=[CharacterChange(id="carmine", attitudes=shifts)])

    before = state.characters["carmine"].sheet.disposition.attitudes["luca"]
    after = applied.state.characters["carmine"].sheet.disposition.attitudes["luca"]
    assert after.affinity - before.affinity == NARRATOR_ATTITUDE_CAP
    assert after.trust - before.trust == -NARRATOR_ATTITUDE_CAP


def test_the_engine_moves_attitudes_freely_within_bounds_and_records_grudges():
    shift = AttitudeShift(toward_id="carmine", affinity=-100, fear=100, grudge="He shot at me")

    applied = apply(
        grounded_world(), ENGINE, characters=[CharacterChange(id="bartender", attitudes=[shift])]
    )

    attitude = applied.state.characters["bartender"].sheet.disposition.attitudes["carmine"]
    assert (attitude.affinity, attitude.fear) == (-100, 100)
    assert attitude.grudges[0].reason == "He shot at me"


def resents(character_id: str, **more) -> CharacterChange:
    """The narrator has someone think worse of the player character, and hold it against him."""
    shift = AttitudeShift(affinity=-8, grudge="Lin Feng shamed Zhao Kun at the well")
    return CharacterChange(id=character_id, attitudes=[shift], **more)


def feelings(state: WorldState, character_id: str):
    return state.characters[character_id].sheet.disposition.attitudes.get("lin")


def test_the_narrator_moves_only_the_feelings_of_people_in_the_scene():
    """Miki, 2026-11-11: "that person realizes that you are the murderer of his father, but
    that happens off screen". Someone who wasn't there saw none of it, so a scene can't change
    how they feel: word has to reach them first, and code moves their feelings then (W2, W4)."""
    state = cultivation_world()  # Lin and Zhao at the well; Elder Mo is in the inner court
    before = feelings(state, "elder-mo")

    applied = apply(state, characters=[resents("zhao"), resents("elder-mo")])

    assert feelings(applied.state, "zhao").grudges
    assert feelings(applied.state, "elder-mo") == before
    (refused,) = applied.rejected
    assert (refused.subject, refused.change) == ("character elder-mo", "attitude")
    assert "aren't in the scene" in refused.reason


@pytest.mark.parametrize("way", ["listed", "meets", "comes", "fight", "reached", "brought"])
def test_whoever_comes_into_the_scene_or_the_turn_reached_can_be_moved(way):
    state = cultivation_world()
    change, end, reached, brought = resents("elder-mo"), None, [], []
    there = SceneEnd(ended_on="Elder Mo looks on.", present_ids=["lin", "zhao", "elder-mo"])
    if way in ("listed", "meets", "comes"):
        # The record has him by the well, out of the scene: the scene can bring him into it.
        state.characters["elder-mo"].location_id = "well"
    if way == "listed":  # this scene's end lists him: he walked into it
        end = there
    elif way == "meets":  # the scene has him meet the player character
        change = resents("elder-mo", meets_player=True)
    elif way == "comes":  # the scene says he is where it is
        change = resents("elder-mo", location_id="well")
    elif way == "fight":  # he is in the scene's fight, whatever its last end listed
        state.scene.encounter = Encounter(
            kind=EncounterKind.FIGHT, opponent_ids=["elder-mo"], started_turn=2, started_s=0
        )
    elif way == "reached":  # a step of the turn faced him, or an event was about him
        reached = ["elder-mo"]
    else:  # the world brought him over from the inner court, and the scene ends with him there
        brought, end = ["elder-mo"], there

    delta = StateDelta(characters=[change], scene_end=end)
    applied = apply_delta(state, delta, ctx(3), source=NARRATOR, reached=reached, brought=brought)

    assert not applied.rejected
    assert feelings(applied.state, "elder-mo").grudges
    if end is not None:
        assert "elder-mo" in applied.state.scene.present_ids


@pytest.mark.parametrize("way", ["listed", "meets", "comes"])
def test_a_scene_brings_in_nobody_the_record_has_elsewhere(way):
    """W10, W4. In the first stories about an affair on the real model (2026-11-13) the
    narrator walked the wronged wife into the scene from a farm forty minutes away: its end
    listed her, the record took its word, and she had seen the next move. Only the world
    moves people between places, so the scene's word about someone the record has elsewhere
    is refused: they aren't in it, they stay where they were, and it moves nothing in them."""
    state = cultivation_world()  # Lin and Zhao at the well; Elder Mo is in the inner court
    before = feelings(state, "elder-mo")
    change, end = resents("elder-mo"), None
    if way == "listed":
        end = SceneEnd(ended_on="Elder Mo looks on.", present_ids=["lin", "zhao", "elder-mo"])
    elif way == "meets":
        change = resents("elder-mo", meets_player=True)
    else:
        change = resents("elder-mo", location_id="well")

    applied = apply(state, characters=[change], scene_end=end)

    elder = applied.state.characters["elder-mo"]
    assert elder.location_id == "inner-court"
    assert "elder-mo" not in applied.state.scene.present_ids
    assert "lin" not in elder.met_by
    assert feelings(applied.state, "elder-mo") == before
    refused = {(r.subject, r.change) for r in applied.rejected}
    what = {"listed": "presence", "meets": "meeting", "comes": "location"}[way]
    assert refused == {("character elder-mo", what), ("character elder-mo", "attitude")}
    assert "only the world brings them here" in " ".join(reasons(applied))


@pytest.mark.parametrize("named", ["inner-court", "the Inner Court"])
def test_a_scene_that_ends_somewhere_else_has_the_people_the_record_puts_there(named):
    """The scene walks Lin to the inner court, where Elder Mo is: he is in it as it ends,
    whether the end names the place by its id or by its name."""
    state = cultivation_world()
    end = SceneEnd(
        ended_on="Elder Mo looks up from his tea.",
        place_id=named,
        present_ids=["lin", "elder-mo"],
    )

    applied = apply(state, characters=[resents("elder-mo")], scene_end=end)

    assert not applied.rejected
    assert applied.state.scene.present_ids == ["lin", "elder-mo"]
    assert feelings(applied.state, "elder-mo").grudges


def test_someone_the_record_places_nowhere_is_the_scene_s_to_place():
    state = cultivation_world()
    state.characters["elder-mo"].location_id = None
    end = SceneEnd(ended_on="Elder Mo looks on.", present_ids=["lin", "zhao", "elder-mo"])

    applied = apply(
        state, characters=[CharacterChange(id="elder-mo", location_id="well")], scene_end=end
    )

    assert not applied.rejected
    assert applied.state.characters["elder-mo"].location_id == "well"
    assert "elder-mo" in applied.state.scene.present_ids


def test_the_scene_says_where_its_own_people_go():
    """Zhao is in the scene, so the scene can send him off to the inner court."""
    state = cultivation_world()

    applied = apply(state, characters=[CharacterChange(id="zhao", location_id="inner-court")])

    assert not applied.rejected
    assert applied.state.characters["zhao"].location_id == "inner-court"


def test_whoever_the_scene_is_barred_from_has_no_part_in_it():
    """W17. Whoever a move in a romance wrongs and who didn't see it has no part in the scene
    that tells it (`engine.pipeline.kept_out`): not by standing near, not by being reached,
    and the scene moves nothing in them. Someone it finds in the scene stays there."""
    state = cultivation_world()
    state.characters["elder-mo"].location_id = "well"  # by the well, and out of the scene
    before = feelings(state, "elder-mo")
    end = SceneEnd(ended_on="Elder Mo looks on.", present_ids=["lin", "zhao", "elder-mo"])
    delta = StateDelta(
        characters=[resents("elder-mo", meets_player=True, location_id="well"), resents("zhao")],
        scene_end=end,
    )

    applied = apply_delta(
        state,
        delta,
        ctx(3),
        source=NARRATOR,
        reached=["elder-mo", "zhao"],
        barred=["elder-mo", "zhao"],
    )

    assert applied.state.scene.present_ids == ["lin", "zhao"]
    assert feelings(applied.state, "elder-mo") == before
    assert not feelings(applied.state, "zhao").grudges
    assert {(r.subject, r.change) for r in applied.rejected} == {
        ("character elder-mo", "location"),
        ("character elder-mo", "meeting"),
        ("character elder-mo", "attitude"),
        ("character elder-mo", "presence"),
        ("character zhao", "attitude"),
    }


def test_the_engine_s_own_changes_pass_no_door():
    """Only a narrated scene is held to it: the world moves whom it moves."""
    state = cultivation_world()
    end = SceneEnd(ended_on="Elder Mo looks on.", present_ids=["lin", "zhao", "elder-mo"])

    applied = apply(
        state,
        ENGINE,
        characters=[CharacterChange(id="elder-mo", location_id="well", meets_player=True)],
        scene_end=end,
    )

    assert not applied.rejected
    assert applied.state.characters["elder-mo"].location_id == "well"
    assert "elder-mo" in applied.state.scene.present_ids


def test_someone_new_in_the_scene_feels_as_the_scene_says():
    newcomer = CharacterChange(
        id="sister-yun",
        name="Yun Shu",
        description="An inner disciple who watched from the wall.",
        attitudes=[AttitudeShift(affinity=6)],
    )

    applied = apply(cultivation_world(), characters=[newcomer])

    assert not applied.rejected
    assert feelings(applied.state, "sister-yun").affinity == 6


def test_the_engine_moves_the_feelings_of_someone_far_away():
    """Word of a deed reaches people where they are, and the engine moves how they feel."""
    applied = apply(cultivation_world(), ENGINE, characters=[resents("elder-mo")])

    assert not applied.rejected
    assert feelings(applied.state, "elder-mo").grudges


def test_attitudes_need_someone_else_to_be_about():
    applied = apply(
        grounded_world(),
        characters=[
            CharacterChange(
                id="carmine",
                attitudes=[AttitudeShift(toward_id="carmine"), AttitudeShift(toward_id="nobody")],
            )
        ],
    )

    assert len(applied.rejected) == 2


# --- rulings, gains, backstory and rules (A9, A4, N4, G7) ----------------------------------


def ruling(answer: str, holds: bool = True) -> Ruling:
    return Ruling(
        id="r1",
        topic="stop-and-blood",
        power_id="time-stop",
        question="Does blood flow in stopped time?",
        answer=answer,
        holds=holds,
        source=RulingSource.THEORY,
    )


def test_rulings_are_the_engines_and_settled_for_good():
    state = cultivation_world()
    first = CharacterChange(id="lin", rulings=[ruling("No, it freezes.")])

    narrated = apply(state, characters=[first])
    settled = apply(state, ENGINE, turn=7, characters=[first]).state
    flipped = apply(
        settled, ENGINE, characters=[CharacterChange(id="lin", rulings=[ruling("Yes.", False)])]
    )

    assert narrated.state.characters["lin"].sheet.rulings == []
    stored = settled.characters["lin"].sheet.rulings
    assert [(r.answer, r.turn) for r in stored] == [("No, it freezes.", 7)]
    assert flipped.state.characters["lin"].sheet.rulings == stored
    assert "settled for good on turn 7" in reasons(flipped)[0]


def test_gains_and_backstory_are_the_engines():
    change = CharacterChange(id="luca", backstory=["I learned to shoot in the army."])

    narrated = apply(grounded_world(), characters=[change])
    accepted = apply(grounded_world(), ENGINE, characters=[change])

    assert narrated.state.player.sheet.backstory == []
    assert accepted.state.player.sheet.backstory[0].text == "I learned to shoot in the army."


def test_fixed_rules_never_change_and_open_ones_change_by_discovery():
    state = cultivation_world()
    deed(state, "breakthrough", subject="lin", at_s=0)
    discovery = cause(CauseMechanism.DISCOVERY, "breakthrough")

    fixed = apply(
        state, ENGINE, rule_changes=[RuleChange(rule_id="qi-exists", text="No", cause=discovery)]
    )
    narrated = apply(
        state, rule_changes=[RuleChange(rule_id="realm-ceiling", text="New", cause=discovery)]
    )
    opened = apply(
        state,
        ENGINE,
        rule_changes=[RuleChange(rule_id="realm-ceiling", text="Lin passed it.", cause=discovery)],
    )

    assert reasons(fixed) == ["a fixed rule never changes (G7)"]
    assert reasons(narrated) == ["only the engine decides this"]
    assert opened.state.bible.rule("realm-ceiling").text == "Lin passed it."
    assert check_transition(state, opened.state) == []


# --- facts, items, leads and the scene -----------------------------------------------------


def test_facts_record_who_knows_them():
    applied = apply(
        grounded_world(),
        facts=[
            NewFact(text="Carmine met the Calabrians.", known_by=["bartender", "ghost"]),
            NewFact(text="A secret.", known_to_player=False, is_true=False),
        ],
    )

    facts = sorted(applied.state.facts.values(), key=lambda f: f.id)
    assert [f.known_by for f in facts] == [["bartender", "luca"], []]
    assert facts[1].is_true is False and facts[0].turn == 3


def test_items_are_gained_used_up_and_never_conjured_away():
    state = grounded_world()

    gained = apply(
        state, items=[ItemChange(name="bullets", quantity=6, from_id="world", to_id="luca")]
    ).state
    used = apply(
        gained, items=[ItemChange(name="Bullets", quantity=6, from_id="luca", to_id="world")]
    ).state
    missing = apply(state, items=[ItemChange(name="grenade", from_id="luca", to_id="world")])

    def names(s):
        return [i.name for i in s.player.sheet.resources.items]

    assert "bullets" in names(gained) and "bullets" not in names(used)
    assert missing.rejected[0].reason == "they don't have it"


def test_leads_expire_on_in_world_time():
    state = grounded_world()
    state.world_s = 100

    applied = apply(state, leads=[NewLead(text="Meet me at the docks", expires_in_s=3600)])

    (lead,) = applied.state.leads.values()
    assert (lead.offered_s, lead.expires_s, lead.offered_turn) == (100, 3700, 3)


def close(state: WorldState, *over: GoalOver, player_acted: bool = True):
    return apply_delta(
        state, StateDelta(goals_over=list(over)), ctx(3), source=NARRATOR, player_acted=player_acted
    )


def with_goals() -> WorldState:
    state = grounded_world()  # find-killer, set on turn 0
    state.goals["goal-2"] = Goal(id="goal-2", text="Get out of Naples alive", set_turn=2)
    state.goals["goal-3"] = Goal(id="goal-3", text="Leave Naples and stay alive", set_turn=5)
    state.goals["goal-4"] = Goal(id="goal-4", text="Save Rosa", set_turn=6)
    return state


def test_a_goal_that_is_over_closes_and_is_never_rewritten():
    state = with_goals()
    applied = close(
        state,
        GoalOver(goal_id="find-killer", how=GoalEnd.ACHIEVED),
        GoalOver(goal_id="goal-4", how=GoalEnd.FAILED),
    )

    goals = applied.state.goals
    assert not applied.rejected
    assert (goals["find-killer"].status, goals["find-killer"].closed_turn) == (
        GoalStatus.ACHIEVED,
        3,
    )
    assert goals["goal-4"].status is GoalStatus.FAILED
    assert [g.text for g in goals.values()] == [g.text for g in state.goals.values()]
    assert goals["goal-2"].status is GoalStatus.ACTIVE


@pytest.mark.parametrize("named, same_as", [("goal-3", "goal-2"), ("goal-2", "goal-3")])
def test_a_goal_said_again_closes_into_the_older_one(named, same_as):
    applied = close(with_goals(), GoalOver(goal_id=named, how=GoalEnd.REPEATS, same_as=same_as))

    goals = applied.state.goals
    assert not applied.rejected
    assert goals["goal-2"].status is GoalStatus.ACTIVE  # the words the player set first stay
    assert (goals["goal-3"].status, goals["goal-3"].merged_into) == (GoalStatus.MERGED, "goal-2")


def test_only_an_active_goal_closes_and_a_repeat_needs_another_active_goal():
    state = with_goals()
    state.goals["goal-4"].status = GoalStatus.ABANDONED
    applied = close(
        state,
        GoalOver(goal_id="ghost", how=GoalEnd.ACHIEVED),
        GoalOver(goal_id="goal-4", how=GoalEnd.ACHIEVED),
        GoalOver(goal_id="goal-2", how=GoalEnd.REPEATS),
        GoalOver(goal_id="goal-2", how=GoalEnd.REPEATS, same_as="goal-2"),
        GoalOver(goal_id="goal-3", how=GoalEnd.REPEATS, same_as="goal-4"),
    )

    assert reasons(applied) == ["not an active goal"] * 2 + ["it repeats no other active goal"] * 3
    assert applied.state.goals == state.goals


def test_no_goal_closes_on_a_turn_the_player_didnt_act():
    state = with_goals()
    applied = close(state, GoalOver(goal_id="goal-2", how=GoalEnd.ACHIEVED), player_acted=False)
    assert reasons(applied) == ["the player didn't act this turn"]
    assert applied.state.goals == state.goals


def move(state: WorldState, *moved: GoalMoved, **more):
    return apply_delta(state, StateDelta(goals_moved=list(moved), **more), ctx(3), source=NARRATOR)


def test_a_scene_notes_where_a_goal_stands_and_never_rewrites_it():
    """N2, C6: the sentence is kept beside the goal, and the goal the story last moved is the
    thread the player follows. It needs no action of the player's: news can come to them."""
    state = with_goals()
    applied = move(state, GoalMoved(goal_id="goal-2", progress="  The ferry leaves\n at dawn. "))

    goal = applied.state.goals["goal-2"]
    assert not applied.rejected
    assert (goal.progress, goal.moved_turn) == ("The ferry leaves at dawn.", 3)
    assert (goal.text, goal.status) == ("Get out of Naples alive", GoalStatus.ACTIVE)

    later = move(applied.state, GoalMoved(goal_id="goal-2", progress="x" * 400)).state
    assert later.goals["goal-2"].progress == "x" * MAX_PROGRESS  # the last note replaces it


def test_a_note_needs_an_active_goal_and_something_of_its_own_to_say():
    state = with_goals()
    state.goals["goal-4"].status = GoalStatus.ABANDONED
    applied = move(
        state,
        GoalMoved(goal_id="ghost", progress="Seen at the docks."),
        GoalMoved(goal_id="goal-4", progress="Rosa is safe."),
        GoalMoved(goal_id="goal-2", progress="   "),
        GoalMoved(goal_id="goal-2", progress="Get out of Naples... ALIVE!"),
    )

    said_nothing = "it says nothing beyond the goal's own words"
    assert reasons(applied) == ["not an active goal"] * 2 + [said_nothing] * 2
    assert applied.state.goals == state.goals


def test_a_goal_that_closes_keeps_when_and_takes_no_note_in_the_same_update():
    state = with_goals()
    state.world_s = 5000
    applied = apply_delta(
        state,
        StateDelta(
            goals_over=[GoalOver(goal_id="goal-4", how=GoalEnd.ACHIEVED)],
            goals_moved=[GoalMoved(goal_id="goal-4", progress="Rosa is on the train.")],
        ),
        ctx(3),
        source=NARRATOR,
        player_acted=True,
    )

    goal = applied.state.goals["goal-4"]
    assert reasons(applied) == ["not an active goal"]
    assert (goal.status, goal.closed_turn, goal.closed_s) == (GoalStatus.ACHIEVED, 3, 5000)
    assert goal.progress == ""


def test_a_goal_said_again_hands_what_the_story_did_with_it_to_the_one_that_stays():
    state = with_goals()
    state.goals["goal-3"].progress = "The ferry leaves at dawn."
    state.goals["goal-3"].moved_turn = 6
    merged = close(state, GoalOver(goal_id="goal-3", how=GoalEnd.REPEATS, same_as="goal-2")).state
    stays = merged.goals["goal-2"]
    assert (stays.progress, stays.moved_turn) == ("The ferry leaves at dawn.", 6)
    assert merged.goals["goal-3"].closed_s == state.world_s

    state.goals["goal-2"].progress = "A boat waits at Pozzuoli."
    state.goals["goal-2"].moved_turn = 9  # the one that stays was moved later: its own holds
    merged = close(state, GoalOver(goal_id="goal-3", how=GoalEnd.REPEATS, same_as="goal-2")).state
    stays = merged.goals["goal-2"]
    assert (stays.progress, stays.moved_turn) == ("A boat waits at Pozzuoli.", 9)


def test_the_scene_end_keeps_only_real_people_and_places():
    applied = apply(
        grounded_world(),
        scene_end=SceneEnd(ended_on="A shot", place_id="moon", present_ids=["luca", "ghost"]),
        summary="Luca fired.",
    )

    scene = applied.state.scene
    assert (scene.place_id, scene.present_ids, scene.ended_on) == ("bar", ["luca"], "A shot")
    assert applied.state.summary == "Luca fired."


def end_scene(state: WorldState, *, found=(), **end):
    """The narrator ends the scene on a turn whose steps found `found` (R2, R3)."""
    delta = StateDelta(scene_end=SceneEnd(ended_on="A pause.", **end))
    return apply_delta(state, delta, ctx(3), source=NARRATOR, found=found).state.scene


def test_the_scene_keeps_what_the_turn_found_beside_what_the_narrator_lists():
    """R2, R3: the narrator lists what matters next and often leaves out the thing the character
    just picked up. Code found it, so code keeps it for the next turn's check."""
    state = grounded_world()

    scene = end_scene(state, found=["a broken chair leg"], props=["a telephone behind the bar"])
    assert scene.props == ["a telephone behind the bar", "a broken chair leg"]

    # With no list from the narrator the record still holds it, and with nothing found the
    # narrator's list stands as it is.
    assert end_scene(state, found=[" a broken chair leg "]).props == ["a broken chair leg"]
    assert end_scene(state, props=["a telephone behind the bar"]).props == [
        "a telephone behind the bar"
    ]


def test_a_scene_that_goes_on_with_no_new_ending_keeps_what_was_found_too():
    """The narrator may leave the scene's end out: the scene goes on as it was, plus the find."""
    state = grounded_world()
    told = list(state.scene.props)

    applied = apply_delta(
        state, StateDelta(summary="Luca looked around."), ctx(3), source=NARRATOR, found=["a coin"]
    )

    assert applied.state.scene.props == [*told, "a coin"]
    assert applied.state.scene.ended_on == state.scene.ended_on
    assert state.scene.props == told


def test_what_the_narrator_already_lists_is_never_listed_twice():
    scene = end_scene(
        grounded_world(),
        found=["the grappa", "a telephone", "a coin", "a coin", " "],
        props=["a bottle of grappa on the bar", "a telephone behind the bar"],
    )

    assert scene.props == ["a bottle of grappa on the bar", "a telephone behind the bar", "a coin"]


def test_what_was_found_stays_behind_when_the_scene_moves_on():
    """R3: a stone found at the bar is no part of the room the next scene opens in."""
    state = grounded_world()

    moved = end_scene(state, found=["a loose cobblestone"], place_id="questura", props=["a desk"])
    assert (moved.place_id, moved.props) == ("questura", ["a desk"])

    # Named again, or named wrongly, the scene is where it was, and keeps what was found there.
    for place_id in ("bar", "moon", None):
        stayed = end_scene(state, found=["a loose cobblestone"], place_id=place_id)
        assert (stayed.place_id, stayed.props) == ("bar", ["a loose cobblestone"])


def test_the_scenes_record_never_grows_past_its_cap():
    told = [f"crate number {i}" for i in range(MAX_PROPS - 1)]
    found = ["a rope", "a lantern", "a hook"]

    scene = end_scene(grounded_world(), found=found, props=told)

    assert scene.props == [*told, "a rope"]
    # The narrator's own list is never cut: only what code adds stops at the cap.
    long = [f"crate number {i}" for i in range(MAX_PROPS + 3)]
    assert end_scene(grounded_world(), found=found, props=long).props == long


def test_the_player_sees_what_happens_to_the_place_they_are_in():
    state = grounded_world()  # Luca is in the bar
    ruin = [PlaceChange(id="bar", status=PlaceStatus.RUINED)]
    away = [PlaceChange(id="questura", status=PlaceStatus.DAMAGED)]

    applied = apply(state, ENGINE, places=ruin + away)

    assert applied.state.places["bar"].status_history[-1].known_by == ["luca"]
    assert applied.state.places["questura"].status_history[-1].known_by == []


def test_parents_never_loop():
    state = grounded_world()
    state.places["bar"].parent_id = "naples"

    looped = apply(state, places=[PlaceChange(id="naples", parent_id="bar")])
    itself = apply(state, factions=[FactionChange(id="police", parent_id="police")])
    fine = apply(state, factions=[FactionChange(id="carmine-crew", parent_id="esposito")])

    assert looped.state.places["naples"].parent_id is None
    assert reasons(looped) == ["'bar' lies within it"]
    assert reasons(itself) == ["'police' is part of it"]
    assert fine.state.factions["carmine-crew"].parent_id == "esposito"


def test_an_event_that_is_due_but_never_applied_is_no_cause():
    state = resurrection_world()
    state.pending_events["return"] = PendingEvent(
        id="return", kind="revival", due_s=500, subject_ids=["zhao"]
    )
    back = CharacterChange(
        id="zhao",
        status=CharacterStatus.ALIVE,
        cause=cause(CauseMechanism.RESURRECTION, "return", CauseRef.EVENT),
    )

    applied = apply(state, ENGINE, characters=[back])

    assert reasons(applied) == ["event 'return' hasn't happened"]


# --- what only the engine writes (A3, F1) ---------------------------------------------------------


def judged(key: str, level: int = 3) -> Judged:
    return Judged(key=key, what=key, level=level)


def test_a_place_keeps_the_first_level_a_thing_was_judged_at():
    state = cultivation_world()
    first = PlaceChange(id="well", judged=[judged("archiv door lock pick")])
    state = apply(state, ENGINE, places=[first]).state
    again = PlaceChange(
        id="well", judged=[judged("archiv door lock pick", level=1), judged("gate")]
    )
    applied = apply(state, ENGINE, places=[again])

    assert not applied.rejected
    kept = applied.state.places["well"]
    assert [(j.key, j.level) for j in kept.judged] == [("archiv door lock pick", 3), ("gate", 3)]
    assert kept.level_of("archiv door lock pick") == 3 and kept.level_of("a wall") is None


def test_a_place_forgets_the_oldest_judged_things_first():
    state = cultivation_world()
    for n in range(MAX_JUDGED + 2):
        state = apply(
            state, ENGINE, places=[PlaceChange(id="well", judged=[judged(f"thing {n}")])]
        ).state

    kept = [j.key for j in state.places["well"].judged]
    assert (
        len(kept) == MAX_JUDGED and kept[0] == "thing 2" and kept[-1] == f"thing {MAX_JUDGED + 1}"
    )


def test_the_narrator_cant_say_how_hard_a_thing_is():
    state = cultivation_world()
    applied = apply(state, NARRATOR, places=[PlaceChange(id="well", judged=[judged("a lock", 1)])])

    assert applied.state.places["well"].judged == []
    assert reasons(applied) == ["only the engine decides this"]


def test_someone_the_engine_makes_real_comes_with_the_body_it_gave_them():
    state = cultivation_world()
    body = Attributes(strength=5, speed=5, toughness=5, wits=5)
    stranger = CharacterChange(id="old-man", name="the old man", attributes=body)
    applied = apply(state, ENGINE, characters=[stranger])

    assert not applied.rejected
    assert applied.state.characters["old-man"].sheet.attributes == body


def test_a_known_characters_body_doesnt_change_and_never_on_the_narrators_word():
    state = cultivation_world()
    before = state.characters["zhao"].sheet.attributes.model_copy()
    stronger = CharacterChange(id="zhao", attributes=Attributes(strength=5))

    applied = apply(state, ENGINE, characters=[stronger])
    assert reasons(applied) == ["a known character's body doesn't change here"]
    assert applied.state.characters["zhao"].sheet.attributes == before

    applied = apply(state, NARRATOR, characters=[stronger])
    assert reasons(applied) == ["only the engine decides this"]
    assert applied.state.characters["zhao"].sheet.attributes == before


# --- talent (A4) ------------------------------------------------------------------------------


def _blade_ruling(fit: TalentFit) -> TalentRuling:
    cover = TalentCover(talent_id="sword", fit=fit)
    return TalentRuling(key="technique:aura-blade", what="Aura blade", covers=[cover])


def test_a_ruling_on_talent_is_recorded_once_with_when_it_was_made():
    state = cultivation_world()
    state.world_s = 500
    state.player.sheet.talents = [
        Talent(id="sword", name="The sword", strength=TalentStrength.ONE_OF_A_KIND)
    ]
    first = CharacterChange(id="lin", talent_rulings=[_blade_ruling(TalentFit.RELATED)])
    flipped = CharacterChange(id="lin", talent_rulings=[_blade_ruling(TalentFit.INSIDE)])

    ruled = apply(state, ENGINE, characters=[first])
    again = apply(ruled.state, ENGINE, turn=9, characters=[flipped])

    (ruling,) = again.state.player.sheet.talent_rulings
    assert (ruling.covers[0].fit, ruling.turn, ruling.world_s) == (TalentFit.RELATED, 3, 500)
    assert not ruled.rejected and not again.rejected


def test_a_bridge_is_kept_with_when_it_was_built():
    state = cultivation_world()
    bridge = TalentBridge(
        key="technique:aura-blade", talent_id="sword", rests_on="the formula", steps=1
    )

    applied = apply(state, ENGINE, turn=7, characters=[CharacterChange(id="lin", bridges=[bridge])])

    (kept,) = applied.state.player.sheet.bridges
    assert (kept.rests_on, kept.steps, kept.turn) == ("the formula", 1, 7)


def test_the_narrator_can_neither_rule_on_a_talent_nor_build_a_bridge():
    state = cultivation_world()
    bridge = TalentBridge(key="technique:aura-blade", talent_id="sword", rests_on="a wish")
    change = CharacterChange(
        id="lin", talent_rulings=[_blade_ruling(TalentFit.INSIDE)], bridges=[bridge]
    )

    applied = apply(state, characters=[change])

    assert reasons(applied) == ["only the engine decides this", "only the engine decides this"]
    assert applied.state.player.sheet.talent_rulings == []
    assert applied.state.player.sheet.bridges == []
