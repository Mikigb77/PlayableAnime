"""apply_delta: the narrator proposes, the engine decides, and C1 holds either way."""

import pytest

from engine.apply import NARRATOR_ATTITUDE_CAP, DeltaSource, apply_delta
from engine.context import TurnContext
from engine.contracts import (
    AttitudeShift,
    CharacterChange,
    FactionChange,
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
    Cause,
    CauseMechanism,
    CauseRef,
    CharacterStatus,
    DeathCertainty,
    Deed,
    EventStatus,
    FactionStatus,
    PendingEvent,
    PlaceStatus,
    Resurrection,
    Ruling,
    RulingSource,
    WorldState,
)

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


def test_the_scene_end_keeps_only_real_people_and_places():
    applied = apply(
        grounded_world(),
        scene_end=SceneEnd(ended_on="A shot", place_id="moon", present_ids=["luca", "ghost"]),
        summary="Luca fired.",
    )

    scene = applied.state.scene
    assert (scene.place_id, scene.present_ids, scene.ended_on) == ("bar", ["luca"], "A shot")
    assert applied.state.summary == "Luca fired."


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
