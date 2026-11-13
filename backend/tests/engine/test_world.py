"""The living world, piece by piece: deeds and witnesses, rumors, reputation, grudges, answers,
discovery, the cast, clocks and the tick (W1 to W8, W11 to W13, W15, W15a, E2, E5, K8)."""

import pytest

from engine import pipeline, world
from engine.base import DAY, HOUR, MINUTE
from engine.context import StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    CharacterChange,
    Intent,
    IntentStep,
    OutcomeClass,
    PlaceChange,
    ProposedDeed,
    Resolution,
    SheetPart,
    SheetUse,
    StateDelta,
    StepFacts,
    StepResolution,
)
from engine.invariants import check_transition
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Activity,
    Character,
    CharacterStatus,
    ClockStatus,
    Connection,
    ConnectionKind,
    DeathCertainty,
    Deed,
    EventStatus,
    Faction,
    FactionStatus,
    Law,
    OriginKind,
    PassingState,
    PendingEvent,
    Place,
    Prominence,
    Route,
    StatusChange,
    StepResult,
    Trace,
    TraceKind,
    Visibility,
    WorldState,
)
from engine.visibility import memory_view
from engine.world import Kind, carriers, hearsay, tick
from engine.world.answers import Answer, choose_answer
from engine.world.discovery import name_the_doer
from engine.world.geography import travel_s
from engine.world.knowledge import faction_learns
from engine.world.norms import assess_severity, is_crime
from engine.world.rumors import start_rumor
from engine.world.scheduling import World
from engine.world.tuning import (
    ACTIVE_FACTION_CAP,
    ACTIVE_NPC_CAP,
    AGENDA_FACTS_KEPT,
    CROWD_DELAY_S,
    GARBLED_BELOW,
    LOCAL_LINK_S,
    MAX_TICKS_PER_PASSAGE,
    REACTION_WINDOW_S,
    REPUTATION_STEP_MAX,
    UNKNOWN_TRIP_S,
)


def ctx(turn: int = 2) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings())


def rng(turn: int = 2) -> SeededRng:
    return SeededRng.for_turn("s1", "main", turn)


def settled(duration_s: int = 2, **kwargs) -> StepResolution:
    return StepResolution(
        index=0,
        text="a step",
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=duration_s,
        **kwargs,
    )


def deed_step(*deeds: ProposedDeed, dead: tuple[str, ...] = (), duration_s: int = 2):
    effects = StateDelta(
        characters=[CharacterChange(id=c, status=CharacterStatus.DEAD) for c in dead]
    )
    return settled(duration_s, effects=effects, deeds=list(deeds))


def play(state: WorldState, *steps: StepResolution, turn: int = 2, actor_id=None):
    resolution = Resolution(
        actor_id=actor_id, steps=[s.model_copy(update={"index": i}) for i, s in enumerate(steps)]
    )
    played = pipeline.play_out(state, resolution, ctx(turn), rng(turn))
    assert check_transition(state, played.state) == []
    return played


def idle(state: WorldState, until_s: int, *, turn: int = 3) -> tuple[WorldState, list]:
    """Catch the world up to a time, letting whatever needs the player pass."""
    fired: list[PendingEvent] = []
    while state.world_s < until_s:
        passage = pipeline.catch_up(state, until_s, ctx(turn), rng(turn))
        assert check_transition(state, passage.state) == []
        state = passage.state
        fired.extend(passage.fired)
        turn += 1
    return state, fired


def moved_on(state: WorldState) -> WorldState:
    """The scenes that follow no longer show anyone who was there: they are free to talk (W2)."""
    state.scene.present_ids = []
    return state


def pending_of(state: WorldState, kind: Kind) -> list[PendingEvent]:
    return [
        e
        for e in state.pending_events.values()
        if e.kind == kind and e.status is EventStatus.PENDING
    ]


def at(state: WorldState) -> World:
    return World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())


def the_deed(state: WorldState) -> Deed:
    (deed,) = state.deeds.values()
    return deed


# --- Severity (W1, W12) ----------------------------------------------------------------------


def test_severity_holds_the_floor_the_facts_set():
    state = grounded_world()
    state.characters["kid"] = Character(id="kid", name="Tonino", age=9, location_id="bar")
    many = [f"v{i}" for i in range(5)]  # nameless villagers
    state.characters["bartender"].status = CharacterStatus.DEAD
    state.characters["bartender"].death_certainty = DeathCertainty.CONFIRMED

    assert assess_severity(state, "murder", 1, ["bartender"]) == 4
    # A killing nobody died of counts as the wounding it was, and a miss keeps resolve's guess.
    assert assess_severity(state, "kill", 3, ["carmine"]) == 3
    assert assess_severity(state, "kill", 1, ["carmine"]) == 3
    assert assess_severity(state, "kill", 3, [], ["carmine"]) == 3
    assert assess_severity(state, "insult", 1, ["carmine"]) == 1
    assert assess_severity(state, "insult", 3, ["carmine"]) == 3
    assert assess_severity(state, "assault", 2, ["kid"]) == 5
    assert assess_severity(state, "kill", 4, many) == 5
    assert assess_severity(state, "Sexual assault", 1, ["carmine"]) == 5
    assert assess_severity(state, "save", 2, ["carmine"]) == 2


# --- Witnesses (W2, W10a) --------------------------------------------------------------------


def test_everyone_present_and_aware_sees_a_deed_but_not_someone_asleep():
    state = grounded_world()
    state.characters["bartender"].sheet.condition.states.append(PassingState(name="asleep"))
    punch = ProposedDeed(kind="punch", text="Luca punches Carmine", victim_ids=["carmine"])

    after = play(state, deed_step(punch)).state

    deed = the_deed(after)
    assert deed.witness_ids == ["carmine"]
    assert deed.visibility is Visibility.WITNESSED
    assert deed.severity == 2 and deed.kind == "punch"
    assert deed.known_by == ["luca", "carmine"]


def test_a_deed_in_stopped_time_is_secret_and_whoever_was_immune_goes_unnoticed():
    state = cultivation_world()
    state.characters["elder-mo"].location_id = "well"
    stopped = ProposedDeed(
        kind="assault", text="Lin breaks Zhao's arm", victim_ids=["zhao"], in_stopped_time=True
    )
    seen = stopped.model_copy(update={"witness_ids": ["elder-mo"]})

    unseen = play(state, deed_step(stopped)).state
    watched = play(state, deed_step(seen)).state

    deed = the_deed(unseen)
    assert deed.visibility is Visibility.SECRET and deed.witness_ids == []
    deed = the_deed(watched)
    assert deed.witness_ids == ["elder-mo"] and deed.unnoticed_witness_ids == ["elder-mo"]


def test_record_consequences_works_on_a_copy_and_skips_a_step_without_deeds():
    state = grounded_world()
    before = state.model_dump()
    resolution = Resolution(steps=[settled()])
    kill = ProposedDeed(kind="kill", text="Luca kills Carmine", victim_ids=["carmine"])

    same = world.record_consequences(state, resolution, settled(), ctx(), rng())
    new = world.record_consequences(state, resolution, settled(deeds=[kill]), ctx(), rng())

    assert same is state
    assert state.model_dump() == before
    assert len(new.deeds) == 1 and pending_of(new, Kind.REPORT)


# --- Rumors (W2) -----------------------------------------------------------------------------


def test_word_travels_at_the_pace_people_do_and_loses_accuracy_on_the_way():
    state = cultivation_world()
    beat = ProposedDeed(kind="assault", text="Lin beats Zhao", victim_ids=["zhao"])
    after = play(state, deed_step(beat)).state
    deed = the_deed(after)

    after, fired = idle(after, 6 * HOUR)

    (rumor,) = [r for r in after.rumors.values() if r.deed_id == deed.id]
    reached = [e for e in fired if e.kind == Kind.RUMOR and e.payload["place_id"] == "inner-court"]
    assert len(reached) == 1
    # 40 minutes on foot, a little slower as word of mouth, after people have talked.
    assert reached[0].applied_s >= deed.world_s + 70 * MINUTE
    assert reached[0].payload["accuracy"] < rumor.accuracy
    assert rumor.heard_at["elder-mo"] == reached[0].applied_s
    assert "elder-mo" in rumor.believed_by
    assert after.characters["elder-mo"].sheet.disposition.attitudes["lin"].fear > 0


def test_word_that_comes_to_where_the_player_character_is_waits_for_a_scene_to_tell_it():
    """Everyone at a place hears word when it comes, except the player character: nothing a
    scene didn't tell is in their memory (C6). It is the talk of the place, which a quiet scene
    may let them catch (`engine.world.hearsay`)."""
    state = cultivation_world()
    state.characters["bo"] = Character(id="bo", name="Bo Lang", location_id="inner-court")
    flog = ProposedDeed(kind="assault", text="Elder Mo flogs Bo", actor_id="elder-mo")
    flog = flog.model_copy(update={"victim_ids": ["bo"]})
    after = play(state, deed_step(flog), actor_id="elder-mo").state
    deed = the_deed(after)

    after, fired = idle(after, 6 * HOUR)

    assert any(e.kind == Kind.RUMOR and e.payload["place_id"] == "well" for e in fired)
    (rumor,) = [r for r in after.rumors.values() if r.deed_id == deed.id]
    assert "zhao" in rumor.heard_at and "lin" not in rumor.heard_at
    assert memory_view(after).rumors == []
    # It is what the well is saying now, and a scene that tells it is how he hears it.
    assert [r.id for r in hearsay.talk_of(after, "lin", "well", after.world_s)] == [rumor.id]
    assert hearsay.hear(at(after), "lin", rumor.id)
    assert [r.id for r in memory_view(after).rumors] == [rumor.id]


def test_a_retelling_that_strays_far_enough_no_longer_names_the_doer():
    state = grounded_world()
    w = at(state)
    deed = Deed(
        id="deed-1",
        actor_id="luca",
        kind="kill",
        text="Luca killed a man",
        turn=1,
        world_s=0,
        place_id="bar",
        victim_ids=["bartender"],
        severity=4,
    )
    state.deeds[deed.id] = deed
    start_rumor(
        w,
        text="Luca killed a man",
        is_true=True,
        place_id="bar",
        hops=2,
        deed=deed,
        about_ids=["luca", "bartender"],
        accuracy=GARBLED_BELOW + 4,
    )

    after, _ = idle(state, 3 * HOUR)

    garbled = [r for r in after.rumors.values() if r.text.startswith("A garbled account")]
    assert garbled and all("luca" not in r.about_ids for r in garbled)
    assert all(r.deed_id == deed.id for r in garbled)
    # Vaguer, not wrong: it no longer says who did it, but what it still says is so.
    assert all(r.is_true for r in garbled)


# --- Reputation (W3, W9) ---------------------------------------------------------------------


def test_one_deed_moves_reputation_by_a_bounded_step_and_counts_once_per_faction():
    state = grounded_world()
    w = at(state)
    reputation = state.factions["police"].player_reputation
    steps = []
    for i in range(12):
        deed = Deed(
            id=f"deed-{i}",
            actor_id="luca",
            kind="kill",
            text="Luca kills again",
            turn=1,
            world_s=0,
            place_id="bar",
            victim_ids=["bartender"],
            severity=5,
        )
        state.deeds[deed.id] = deed
        before = (reputation.esteem, reputation.fear)
        faction_learns(w, "police", deed)
        faction_learns(w, "police", deed)  # the same deed again counts for nothing
        steps.append((before[0] - reputation.esteem, reputation.fear - before[1]))
        assert state.deeds[deed.id].known_by_factions == ["police"]

    assert all(0 <= d <= REPUTATION_STEP_MAX for pair in steps for d in pair)
    assert steps[-1][1] < steps[0][1]  # harder to move the further it already is
    assert -100 <= reputation.esteem and reputation.fear <= 100


# --- Attitudes, grudges and revenge (W4, E5) -------------------------------------------------


def with_a_sister(state: WorldState) -> WorldState:
    state.places["vomero"] = Place(
        id="vomero",
        name="Vomero",
        kind="quarter",
        parent_id="naples",
        routes=[Route(to_id="bar", travel_s=20 * MINUTE)],
    )
    state.characters["maria"] = Character(
        id="maria",
        name="Maria",
        description="Gennaro's sister.",
        location_id="vomero",
    )
    state.characters["maria"].sheet.resources.connections.append(
        Connection(name="Gennaro", kind=ConnectionKind.FAMILY, character_id="bartender")
    )
    return state


def test_word_of_a_killing_reaches_family_elsewhere_who_keep_a_grudge_and_come_to_face_the_doer():
    state = with_a_sister(grounded_world())
    shoot = ProposedDeed(kind="kill", text="Luca shoots Gennaro", victim_ids=["bartender"])
    after = play(state, deed_step(shoot, dead=("bartender",))).state
    deed = the_deed(after)
    assert not pending_of(after, Kind.TIDINGS)  # nobody who saw it has told anyone yet (W2)

    # Carmine saw it. Once the scene lets go of him and people have had time to talk, word is
    # out, and it sets off to her.
    after, fired = idle(moved_on(after), deed.world_s + 3 * HOUR)

    (tidings,) = [e for e in fired if e.kind == Kind.TIDINGS]
    assert tidings.payload["character_id"] == "maria"
    out_s = after.deeds[deed.id].word_out_s
    assert out_s is not None and deed.world_s + 10 * MINUTE <= out_s <= deed.world_s + HOUR
    assert tidings.due_s >= out_s + 5 * MINUTE  # a phone call after a 20-minute drive's news
    attitude = after.characters["maria"].sheet.disposition.attitudes["luca"]
    assert attitude.affinity < -30 and [g.deed_id for g in attitude.grudges] == [deed.id]
    assert "maria" in after.deeds[deed.id].known_by
    # One man's word is all she has (Carmine's), so she comes to put it to Luca's face (W4).
    (comes,) = [e for e in pending_of(after, Kind.ANSWER) if e.payload["avenger_id"] == "maria"]
    assert comes.payload["answer"] == "confront" and comes.payload["target_id"] == "luca"
    assert comes.due_s >= tidings.due_s + HOUR


def test_an_npcs_deed_runs_the_same_loop_and_the_player_feels_nothing_for_them():
    state = grounded_world()
    # Someone besides the player character sees it, since they tell nobody by themselves (W2).
    state.characters["nico"] = Character(id="nico", name="Nico Greco", location_id="bar")
    state.scene.present_ids.append("nico")
    shoot = ProposedDeed(
        kind="kill", text="Carmine shoots Gennaro", actor_id="carmine", victim_ids=["bartender"]
    )
    after = play(state, deed_step(shoot, dead=("bartender",)), actor_id="carmine").state
    deed = the_deed(after)
    assert deed.actor_id == "carmine" and deed.witness_ids == ["luca", "nico"]

    after, fired = idle(after, 3 * HOUR)

    assert "carmine" not in after.player.sheet.disposition.attitudes  # G15
    police = [e for e in fired if e.kind == Kind.ANSWER and e.payload["faction_id"] == "police"]
    assert [e.payload["target_id"] for e in police] == ["carmine"]
    assert not police[0].needs_player
    # His own family doesn't answer its leader.
    assert all(e.payload["faction_id"] != "esposito" for e in fired if e.kind == Kind.ANSWER)


# --- Answers (W5, W11, A8) -------------------------------------------------------------------


def test_those_who_keep_the_law_come_to_arrest():
    state = grounded_world()
    w = at(state)
    police = state.factions["police"]
    assert choose_answer(w, police, "luca", 1, enforcing=True, harmed=False) is Answer.ARREST


@pytest.mark.parametrize("lin_might", [5, 9])
def test_a_faction_answers_with_what_it_really_has(lin_might):
    state = cultivation_world()
    state.characters["lin"].sheet.axes.might = lin_might
    state.characters["zhao"].sheet.axes.might = 2
    court = state.factions["outer-court"]

    drawn = {
        choose_answer(
            World(state=state, ctx=ctx(), at_s=0, rng=SeededRng(f"seed-{i}")),
            court,
            "lin",
            3,
            enforcing=False,
            harmed=False,
        )
        for i in range(40)
    }

    # Nobody in the outer court is anywhere near Lin, and Lin isn't their champion against Lin.
    assert Answer.ELITE not in drawn
    if lin_might == 9:
        assert drawn <= {Answer.APPEASE, Answer.AVOID, Answer.RECRUIT}


def test_a_crossed_threat_tier_sets_an_answer_under_way_within_the_window():
    state = cultivation_world()
    w = at(state)
    deed = Deed(
        id="deed-1",
        actor_id="lin",
        kind="kill",
        text="Lin kills an inner disciple",
        turn=1,
        world_s=0,
        place_id="well",
        victim_ids=["elder-mo"],
        severity=4,
    )
    state.deeds[deed.id] = deed

    faction_learns(w, "inner-court", deed)

    assert state.factions["inner-court"].threat >= 3
    (answer,) = pending_of(state, Kind.ANSWER)
    assert answer.payload["faction_id"] == "inner-court"
    assert answer.due_s <= REACTION_WINDOW_S + 40 * MINUTE


def test_people_who_come_and_find_the_target_gone_search_and_never_interrupt():
    state = grounded_world()
    shoot = ProposedDeed(kind="kill", text="Luca shoots Gennaro", victim_ids=["bartender"])
    after = play(state, deed_step(shoot, dead=("bartender",))).state
    after.characters["luca"].location_id = "questura"  # he walks into the Questura, of all places

    after, fired = idle(after, 2 * HOUR)

    (police,) = [e for e in fired if e.kind == Kind.ANSWER and e.payload["faction_id"] == "police"]
    assert police.status is EventStatus.APPLIED and not police.needs_player
    assert any("found them gone" in f.text for f in after.facts.values())


# --- Discovery (W13) -------------------------------------------------------------------------


def test_a_hermit_with_no_ties_who_leaves_no_trace_vanishes_unnoticed():
    state = cultivation_world()
    state.places["cave"] = Place(id="cave", name="a cave", kind="cave", parent_id="azure-peak")
    state.characters["hermit"] = Character(id="hermit", name="the hermit", location_id="cave")
    kill = ProposedDeed(kind="kill", text="Lin kills the hermit", victim_ids=["hermit"])
    kill = kill.model_copy(update={"place_id": "cave"})

    after = play(state, deed_step(kill, dead=("hermit",))).state
    after, _ = idle(after, 365 * DAY)

    deed = the_deed(after)
    assert deed.visibility is Visibility.SECRET and deed.traces == []
    assert not deed.discovered
    assert not [r for r in after.rumors.values() if r.deed_id == deed.id]


def test_a_body_left_in_a_crowd_is_found_within_moments():
    state = grounded_world()
    poison = ProposedDeed(
        kind="poison",
        text="Luca slips poison into Carmine's grappa",
        victim_ids=["carmine"],
        visibility=Visibility.SECRET,
        traces=[Trace(kind=TraceKind.BODY, text="Carmine slumped over the table", strength=100)],
    )
    after = play(state, deed_step(poison, dead=("carmine",))).state
    deed = the_deed(after)
    (look,) = pending_of(after, Kind.DISCOVERY)
    assert look.due_s <= deed.world_s + CROWD_DELAY_S[1]

    after, _ = idle(after, deed.world_s + CROWD_DELAY_S[1])

    assert after.deeds[deed.id].discovered
    assert [r for r in after.rumors.values() if r.deed_id == deed.id]


def test_a_wrong_rumor_blaming_a_rival_turns_the_victims_faction_against_it():
    state = grounded_world()
    state.factions["sanna"] = Faction(id="sanna", name="the Sanna clan", kind="crime family")
    w = at(state)
    deed = Deed(
        id="deed-1",
        actor_id="luca",
        kind="kill",
        text="Carmine was found dead",
        turn=1,
        world_s=0,
        place_id="questura",
        victim_ids=["carmine"],
        severity=4,
        visibility=Visibility.SECRET,
    )
    state.deeds[deed.id] = deed
    start_rumor(
        w,
        text="The Sanna clan did it",
        is_true=False,
        place_id="questura",
        hops=2,
        deed=deed,
        about_ids=["sanna", "carmine"],
        accuracy=80,
    )

    after, _ = idle(state, 3 * HOUR)

    # The bar is held by Carmine's crew, which he leads.
    assert after.factions["carmine-crew"].relations["sanna"] < 0
    assert "sanna" not in after.factions["police"].relations


# --- The cast (W7, W15, W15a, K8) ------------------------------------------------------------


def test_the_active_cast_stays_within_its_caps_and_the_scene_keeps_its_people():
    state = grounded_world()
    for i in range(10):
        state.characters[f"capo-{i}"] = Character(
            id=f"capo-{i}", name=f"Capo {i}", prominence=Prominence.KEY, location_id="naples"
        )
    for i in range(4):
        state.factions[f"family-{i}"] = Faction(id=f"family-{i}", name=f"Family {i}", kind="clan")

    after, _ = idle(state, 2 * DAY)

    active_npcs = [
        c for c in after.npcs() if c.prominence is Prominence.KEY and c.activity is Activity.ACTIVE
    ]
    active_factions = [f for f in after.factions.values() if f.activity is Activity.ACTIVE]
    assert len(active_npcs) == ACTIVE_NPC_CAP
    assert len(active_factions) == ACTIVE_FACTION_CAP
    assert after.characters["carmine"].activity is Activity.ACTIVE  # he's in the scene
    assert len(after.characters) == len(state.characters)  # dormant, never deleted


def destroyed(state: WorldState, faction_id: str) -> WorldState:
    faction = state.factions[faction_id]
    faction.status = FactionStatus.DESTROYED
    faction.status_history.append(
        StatusChange(status="destroyed", from_status="intact", turn=1, world_s=state.world_s)
    )
    return state


def test_a_destroyed_faction_rises_again_only_through_its_survivors():
    state = destroyed(grounded_world(), "police")
    state.factions["police"].survivors = ["the commissioner's widow"]

    after, fired = idle(state, 2 * 365 * DAY)

    (revival,) = [e for e in fired if e.kind == Kind.REVIVAL]
    police = after.factions["police"]
    heirs = [
        f
        for f in after.factions.values()
        if f.origin is not None and f.origin.kind is OriginKind.SUCCESSOR
    ]
    if police.status is FactionStatus.REBUILDING:
        assert police.status_history[-1].cause.ref_id == revival.id
    else:
        assert police.status is FactionStatus.DESTROYED
        assert [h.origin.ref_id for h in heirs] == ["police"]


def test_a_destroyed_faction_with_nobody_left_stays_gone():
    state = destroyed(grounded_world(), "police")

    after, fired = idle(state, 2 * 365 * DAY)

    assert [e.kind for e in fired].count(Kind.REVIVAL) == 1
    assert after.factions["police"].status is FactionStatus.DESTROYED
    assert len(after.factions) == len(state.factions)


@pytest.mark.parametrize(
    ("visibility", "answer"),
    [(Visibility.SECRET, "confront"), (Visibility.PUBLIC, "revenge")],
)
def test_an_avenger_emerges_with_a_recorded_origin_and_comes_for_the_killer(visibility, answer):
    """W15, W4: sure of who did it, they come for revenge. With no more than what is said, they
    come to face the killer with it first."""
    state = grounded_world()
    state.characters["carmine"].status = CharacterStatus.DEAD
    state.characters["carmine"].death_certainty = DeathCertainty.CONFIRMED
    state.deeds["deed-1"] = Deed(
        id="deed-1",
        actor_id="luca",
        kind="kill",
        text="Luca killed Carmine",
        turn=1,
        world_s=0,
        place_id="bar",
        victim_ids=["carmine"],
        severity=4,
        visibility=visibility,
    )
    state.pending_events["rise"] = PendingEvent(
        id="rise",
        kind=Kind.EMERGENCE,
        due_s=0,
        payload={"what": "avenger", "deed_id": "deed-1", "victim_id": "carmine"},
    )

    after = world.apply_event(state, state.pending_events["rise"], ctx(), rng())

    (avenger,) = [c for c in after.characters.values() if c.origin is not None]
    assert avenger.origin.kind is OriginKind.EMERGENCE and avenger.origin.ref_id == "deed-1"
    assert avenger.memberships[0].faction_id == "esposito"
    assert avenger.sheet.disposition.attitudes["luca"].grudges[0].deed_id == "deed-1"
    (comes,) = pending_of(after, Kind.ANSWER)
    assert comes.payload["avenger_id"] == avenger.id and comes.payload["target_id"] == "luca"
    assert comes.payload["answer"] == answer
    assert check_transition(state, after) == []


def test_a_conquered_place_loses_stability_and_grows_a_resistance():
    state = grounded_world()
    conquer = ProposedDeed(kind="conquer", text="Luca takes the Questura", target_ids=["questura"])
    held = StateDelta(places=[PlaceChange(id="questura", controller_id="esposito")])
    after = play(state, settled(effects=held, deeds=[conquer])).state
    assert after.places["questura"].stability == state.places["questura"].stability - 30
    assert after.places["bar"].stability == state.places["bar"].stability

    # Up to the moment it forms: the world's own moves shift how factions stand from then on.
    (due,) = pending_of(after, Kind.EMERGENCE)
    after, fired = idle(after, due.due_s)

    (emergence,) = [e for e in fired if e.kind == Kind.EMERGENCE]
    (resistance,) = [f for f in after.factions.values() if f.kind == "resistance"]
    assert resistance.origin.kind is OriginKind.EMERGENCE
    assert resistance.relations["esposito"] == -80
    assert resistance.player_reputation.esteem < 0
    assert emergence.applied_s >= 7 * DAY


def test_a_conquest_that_didnt_hold_leaves_nothing_to_resist():
    state = grounded_world()
    conquer = ProposedDeed(kind="conquer", text="Luca storms the Questura", target_ids=["questura"])
    after = play(state, settled(deeds=[conquer])).state

    after, fired = idle(after, 90 * DAY)

    assert [e.kind for e in fired].count(Kind.EMERGENCE) == 1
    assert not [f for f in after.factions.values() if f.kind == "resistance"]


# --- Clocks (E2) -----------------------------------------------------------------------------


def test_a_deed_a_clock_names_moves_it_whoever_saw_it():
    state = grounded_world()
    state.clocks["council"].advances_on = ["kill:bartender"]
    state.clocks["council"].reverses_on = ["save"]
    shoot = ProposedDeed(kind="murder", text="Luca shoots Gennaro", victim_ids=["bartender"])
    other = ProposedDeed(kind="kill", text="Luca shoots a stranger", victim_ids=["carmine"])

    moved = play(state, deed_step(shoot, dead=("bartender",))).state
    unmoved = play(state, deed_step(other, dead=("carmine",))).state

    assert moved.clocks["council"].filled == 1
    assert unmoved.clocks["council"].filled == 0
    assert any(f.text.endswith("The capos start counting votes.") for f in moved.facts.values())


# --- The tick and the loop (W6, W10, K8) -----------------------------------------------------


def test_a_year_long_skip_costs_a_bounded_number_of_ticks_and_keeps_the_state_flat():
    state = cultivation_world()

    passage = pipeline.catch_up(state, 365 * DAY, ctx(), rng())

    ticks = [e for e in passage.fired if e.kind == Kind.TICK]
    assert len(ticks) == MAX_TICKS_PER_PASSAGE
    by_subject: dict[str, int] = {}
    for fact in passage.state.facts.values():
        if fact.origin is not None and fact.origin.kind is OriginKind.AGENDA:
            by_subject[fact.origin.ref_id] = by_subject.get(fact.origin.ref_id, 0) + 1
    assert by_subject and max(by_subject.values()) <= AGENDA_FACTS_KEPT


def test_the_world_rolls_the_same_however_time_is_split():
    state = grounded_world()

    whole = pipeline.catch_up(state, 5 * DAY, ctx(), rng()).state
    split = state
    for day in range(1, 6):
        split = pipeline.catch_up(split, day * DAY, ctx(), rng()).state

    assert split.model_dump() == whole.model_dump()


def test_a_stretch_cut_short_has_the_world_live_no_part_of_it_twice(monkeypatch):
    """W10. The tick is spaced for the stretch a time skip plans. When something that needs
    the player cuts the stretch short, the scene that follows spaces the tick for its own
    short time, which leaves it due in the past: it runs at once, for the time up to now, and
    the next one starts from there."""
    lived: list[tuple[int, int]] = []
    monkeypatch.setattr(tick, "live_on", lambda w, since_s: lived.append((since_s, w.at_s)))
    spans: list[int] = []
    monkeypatch.setattr(tick, "_odds", lambda span_s, mean_s: spans.append(span_s) or 0.0)
    state = cultivation_world()
    state.pending_events["knock"] = PendingEvent(
        id="knock", kind="story.knock", due_s=200 * DAY, needs_player=True
    )

    cut = pipeline.catch_up(state, 3650 * DAY, ctx(), rng())
    assert cut.interrupted_by is not None and cut.state.world_s == 200 * DAY
    scene = pipeline.catch_up(cut.state, 200 * DAY + HOUR, ctx(3), rng(3)).state
    after = pipeline.catch_up(scene, 230 * DAY, ctx(4), rng(4)).state

    assert len(lived) > 3 and lived[0][0] == 0 and 200 * DAY < lived[-1][1] <= after.world_s
    assert (200 * DAY) in [upto for _, upto in lived]  # the scene's tick caught the world up
    assert all(upto == since for (_, upto), (since, _) in zip(lived, lived[1:], strict=False))
    # And whoever moves on their own has as much time to as the tick covers.
    assert set(spans) == {upto - since for since, upto in lived}


def test_events_the_world_doesnt_own_are_only_marked_applied():
    state = grounded_world()
    state.pending_events["visit"] = PendingEvent(
        id="visit", kind="director.encounter", due_s=0, needs_player=True
    )

    after = world.apply_event(state, state.pending_events["visit"], ctx(), rng())

    visit = after.pending_events["visit"]
    assert visit.status is EventStatus.APPLIED and visit.needs_player
    assert visit.applied_s == 0 and visit.applied_turn == 2
    assert state.pending_events["visit"].status is EventStatus.PENDING
    with pytest.raises(ValueError):
        world.apply_event(after, visit, ctx(), rng())


def test_reports_without_phones_take_the_trip_and_move_the_witness():
    state = cultivation_world()
    state.places["inner-court"].controller_id = "azure-cloud"
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    shove = ProposedDeed(kind="assault", text="Lin shoves Zhao into the well", victim_ids=["zhao"])
    after = play(state, deed_step(shove)).state

    # Wei only looked on, so he is away before Zhao, whom it fell on (W11).
    reports = pending_of(after, Kind.REPORT)
    assert {r.payload["witness_id"] for r in reports} == {"wei"}
    (report,) = [r for r in reports if r.payload["faction_id"] == "azure-cloud"]
    assert report.payload["moves"] and report.place_id == "inner-court"
    assert report.due_s >= 40 * MINUTE
    assert report.due_s < UNKNOWN_TRIP_S + 2 * MINUTE
    # He sets off within a couple of minutes, and the scene shows him going until then.
    assert 30 <= report.payload["sets_off_s"] - the_deed(after).world_s <= 2 * MINUTE
    assert [r.witness_id for r in carriers.runners(after)] == ["wei"]

    after, _ = idle(after, HOUR)

    assert after.characters["wei"].location_id == "inner-court"
    assert "azure-cloud" in the_deed(after).known_by_factions


# --- What the self-review turned up ----------------------------------------------------------


def kingdom() -> WorldState:
    """Two cities in one kingdom, two days apart, each with a building or two inside."""
    state = grounded_world()
    state.places = {
        "realm": Place(id="realm", name="the realm", kind="kingdom"),
        "a": Place(
            id="a",
            name="Alba",
            kind="city",
            parent_id="realm",
            routes=[Route(to_id="b", travel_s=2 * DAY)],
        ),
        "b": Place(id="b", name="Brenna", kind="city", parent_id="realm"),
        "c": Place(id="c", name="Corvo", kind="city", parent_id="realm"),
        "inn": Place(id="inn", name="the inn", kind="building", parent_id="a"),
        "keep": Place(id="keep", name="the keep", kind="building", parent_id="a"),
        "hall": Place(id="hall", name="the guildhall", kind="building", parent_id="b"),
    }
    return state


def test_travel_inside_a_city_is_a_short_walk_and_between_cities_takes_the_road():
    state = kingdom()

    assert travel_s(state, "inn", "a") == LOCAL_LINK_S
    assert travel_s(state, "inn", "keep") == 2 * LOCAL_LINK_S
    assert travel_s(state, "a", "b") == 2 * DAY
    assert travel_s(state, "inn", "hall") == 2 * DAY + 2 * LOCAL_LINK_S
    assert travel_s(state, "a", "c") is None  # nothing on the map joins them
    # A route between two places is what the trip takes.
    assert travel_s(cultivation_world(), "well", "inner-court") == 40 * MINUTE


def test_the_guards_of_another_city_dont_hear_of_a_crime_outside_their_reach():
    state = kingdom()
    state.factions = {
        "watch-a": Faction(id="watch-a", name="Alba's watch", kind="watch"),
        "watch-b": Faction(id="watch-b", name="Brenna's watch", kind="watch"),
    }
    state.places["keep"].controller_id = "watch-a"
    state.places["hall"].controller_id = "watch-b"
    state.bible.laws = [
        Law(id="law-a", text="No brawling.", enforcer_faction_id="watch-a"),
        Law(id="law-b", text="No brawling.", enforcer_faction_id="watch-b"),
    ]
    for cid in ("luca", "carmine", "bartender"):
        state.characters[cid].location_id = "inn"
        state.characters[cid].memberships = []
    state.scene.place_id = "inn"
    brawl = ProposedDeed(
        kind="assault", text="Luca breaks a chair on Carmine", victim_ids=["carmine"]
    )

    after = play(state, deed_step(brawl)).state

    told = {e.payload["faction_id"] for e in pending_of(after, Kind.REPORT)}
    assert told == {"watch-a"}


def test_when_a_secret_killing_comes_out_the_people_there_their_faction_and_region_learn():
    state = with_a_sister(grounded_world())
    state.characters["maria"].location_id = "bar"
    state.characters["bartender"].status = CharacterStatus.DEAD
    state.characters["bartender"].death_certainty = DeathCertainty.CONFIRMED
    deed = Deed(
        id="deed-1",
        actor_id="luca",
        kind="kill",
        text="Gennaro was strangled in the cellar",
        turn=1,
        world_s=0,
        place_id="bar",
        victim_ids=["bartender"],
        severity=4,
        visibility=Visibility.SECRET,
    )
    state.deeds[deed.id] = deed

    name_the_doer(at(state), deed)

    # What goes round the bar is talk, and nobody saw it done: she only half believes it (W4).
    attitude = state.characters["maria"].sheet.disposition.attitudes["luca"]
    assert "maria" in deed.heard_by and attitude.affinity < 0 and not attitude.grudges
    assert "carmine-crew" in deed.known_by_factions  # the finding is theirs
    assert state.places["naples"].player_reputation.fear > 0

    # Those who found it out tell his sister themselves, and then she holds it against him.
    (tidings,) = pending_of(state, Kind.TIDINGS)
    assert tidings.payload["character_id"] == "maria"
    state, _ = idle(state, state.world_s + HOUR)
    attitude = state.characters["maria"].sheet.disposition.attitudes["luca"]
    assert [g.deed_id for g in attitude.grudges] == ["deed-1"]
    assert "maria" in state.deeds["deed-1"].known_by
    assert "maria" not in state.deeds["deed-1"].heard_by


def test_someone_who_only_heard_nobody_knows_who_did_it_still_learns_the_truth_later():
    state = grounded_world()
    w = at(state)
    deed = Deed(
        id="deed-1",
        actor_id="luca",
        kind="kill",
        text="A man was found dead",
        turn=1,
        world_s=0,
        place_id="questura",
        victim_ids=["carmine"],
        severity=4,
        visibility=Visibility.SECRET,
    )
    state.deeds[deed.id] = deed
    start_rumor(
        w,
        text="Nobody knows who did it",
        is_true=True,
        place_id="questura",
        hops=0,
        deed=deed,
        about_ids=["carmine"],
        heard_by=["bartender"],
    )
    start_rumor(
        w,
        text="Luca did it",
        is_true=True,
        place_id="questura",
        hops=0,
        deed=deed,
        about_ids=["luca", "carmine"],
        heard_by=["bartender"],
        accuracy=80,
    )

    assert state.characters["bartender"].sheet.disposition.attitudes["luca"].fear > 0


def test_a_dormant_npc_the_story_comes_back_to_takes_the_stage_again():
    state = grounded_world()
    for i in range(ACTIVE_NPC_CAP):
        state.characters[f"capo-{i}"] = Character(
            id=f"capo-{i}", name=f"Capo {i}", prominence=Prominence.KEY, location_id="naples"
        )
        state.threads["revenge"].involved_ids.append(f"capo-{i}")
    state.scene.present_ids = ["luca"]
    state.threads["revenge"].involved_ids.remove("carmine")
    after, _ = idle(state, 2 * DAY)
    assert after.characters["carmine"].activity is Activity.DORMANT

    after.scene.present_ids = ["luca", "carmine"]
    after, _ = idle(after, 4 * DAY)

    assert after.characters["carmine"].activity is Activity.ACTIVE
    active = [
        c for c in after.npcs() if c.activity is Activity.ACTIVE and c.prominence is Prominence.KEY
    ]
    assert len(active) == ACTIVE_NPC_CAP


def test_a_clock_given_only_an_interval_starts_moving_from_now():
    state = cultivation_world()
    state.clocks["tournament"].next_step_s = None

    after, _ = idle(state, 20 * HOUR)

    assert after.clocks["tournament"].filled == 1
    assert after.clocks["tournament"].next_step_s == 32 * HOUR


def test_a_full_clock_set_back_no_longer_ends():
    state = grounded_world()
    del state.pending_events["council-meets"]
    clock = state.clocks["council"]
    clock.filled = 3
    clock.advances_on = ["kill:carmine"]
    clock.reverses_on = ["save"]
    kill = ProposedDeed(kind="kill", text="Luca kills Carmine", victim_ids=["carmine"])
    save = ProposedDeed(
        kind="save", text="Luca pulls a capo from the sea", target_ids=["bartender"]
    )

    after = play(state, deed_step(kill, save, dead=("carmine",))).state

    assert after.clocks["council"].filled == 3
    assert not pending_of(after, Kind.CLOCK_END)
    after, _ = idle(after, DAY)
    assert after.clocks["council"].status is ClockStatus.RUNNING


def test_a_witness_who_set_off_is_out_of_the_players_scene_whatever_its_end_listed():
    state = cultivation_world()
    state.places["inner-court"].controller_id = "azure-cloud"
    state.characters["wei"] = Character(id="wei", name="Wei", location_id="well")
    state.scene.present_ids.append("wei")
    shove = ProposedDeed(kind="assault", text="Lin shoves Zhao into the well", victim_ids=["zhao"])
    after = play(state, deed_step(shove)).state
    assert "wei" in after.scene.present_ids  # a moment in which he can still be stopped

    # The narrator's next scene end still lists him, two minutes on: code decides who runs.
    after.world_s += 2 * MINUTE
    assert carriers.settle(after) == ["wei"]
    assert "wei" not in after.scene.present_ids and "zhao" in after.scene.present_ids

    after, fired = idle(after, HOUR)

    reports = [e for e in fired if e.kind == Kind.REPORT and e.payload["witness_id"] == "wei"]
    assert reports and all(r.status is EventStatus.APPLIED for r in reports)
    assert after.characters["wei"].location_id == "inner-court"


def test_resolves_deeds_flow_into_the_world_whether_the_shot_kills_wounds_or_misses():
    shoot = IntentStep(
        text="shoot Carmine",
        verb="shoot",
        kind=ActionKind.EXCHANGE,
        proposed_duration_s=2,
        aim=Aim.KILL,
        target_ids=["carmine"],
        uses=[SheetUse(part=SheetPart.ITEM, ref="pistol")],
        # Carmine doesn't strike back here, so the shot's own deed is the only one; how a foe
        # answers is in tests/engine/resolve/test_answers.py.
        facts=StepFacts(foes_mean=Aim.NONE),
    )
    seen = set()
    for seed in range(200):  # three dice against Carmine's level 2 seldom miss
        state = grounded_world()
        stream = SeededRng.for_turn(f"seed-{seed}", "main", 2)
        resolution = pipeline.resolve(state, Intent(steps=[shoot]), ctx(), stream)
        played = pipeline.play_out(state, resolution, ctx(), stream)
        assert check_transition(state, played.state) == []
        after = played.state
        result = played.resolution.steps[0].result
        seen.add(result)
        deed = the_deed(after)

        # Kill, wound or miss, it is a crime the bartender reports, and Carmine, if he lives,
        # saw who did it.
        carmine = after.characters["carmine"]
        assert is_crime(after, deed)
        assert deed.witness_ids == (["bartender", "carmine"] if carmine.alive else ["bartender"])
        assert "police" in {e.payload["faction_id"] for e in pending_of(after, Kind.REPORT)}
        if result is StepResult.SUCCESS:
            assert not carmine.alive and deed.victim_ids == ["carmine"] and deed.severity >= 4
            continue
        assert deed.severity == 3
        assert deed.victim_ids == (["carmine"] if result is StepResult.PARTIAL else [])
        grudges = carmine.sheet.disposition.attitudes["luca"].grudges
        assert [g.deed_id for g in grudges] == [deed.id]
        (revenge,) = [e for e in pending_of(after, Kind.ANSWER) if e.payload["avenger_id"]]
        assert revenge.payload == revenge.payload | {"avenger_id": "carmine", "target_id": "luca"}
        assert not pending_of(after, Kind.TIDINGS)  # nobody died
    assert seen == set(StepResult)
