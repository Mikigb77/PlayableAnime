"""C6: the Memory and status screens show only what the player character knows."""

import json

import pytest

from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR
from engine.context import Language, TurnContext
from engine.contracts import CharacterChange, PlaceChange, StateDelta
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Calendar,
    CharacterStatus,
    DeathCertainty,
    Deed,
    EventStatus,
    Fact,
    Faction,
    FactionStatus,
    Fallen,
    Gain,
    Goal,
    GoalStatus,
    Lead,
    LeadStatus,
    Mastery,
    Origin,
    OriginKind,
    PendingEvent,
    PlaceStatus,
    Practice,
    Reputation,
    Rumor,
    RungHeard,
    StatusChange,
    Technique,
    Terms,
    Trait,
    TraitKind,
    Visibility,
    WorldState,
)
from engine.visibility import (
    GREW_LIMIT,
    Attitude,
    DeedSeen,
    Dread,
    Esteem,
    attitude_label,
    memory_view,
    speech_vocabulary,
    standing_label,
    status_view,
)
from engine.world import Kind


def dumped(view) -> str:
    return json.dumps(view.model_dump(mode="json"))


def engine(state: WorldState, **delta) -> WorldState:
    applied = apply_delta(
        state, StateDelta(**delta), TurnContext(story_id="s1", turn=4), source=DeltaSource.ENGINE
    )
    assert not applied.rejected
    return applied.state


def test_hidden_truth_never_reaches_the_memory_screen():
    state = grounded_world()
    state.rumors["r1"] = Rumor(
        id="r1",
        text="The Calabrians did it.",
        is_true=False,
        accuracy=10,
        heard_at={"luca": 0},
    )
    state.rumors["r2"] = Rumor(id="r2", text="Carmine gave the order.", is_true=True)
    state.facts["f1"] = Fact(
        id="f1", text="Carmine was at the docks that night.", subject_ids=["carmine"]
    )
    state.world_s = 2 * HOUR

    view = memory_view(state)
    text = dumped(view)

    for hidden in (
        "ordered the killing",  # Carmine's secret and agenda
        "Buy the crews",
        "Carmine Russo, the underboss.",  # the mystery's answer
        "Carmine gave the order.",  # a rumor Luca never heard
        "at the docks",  # a fact Luca doesn't know
        "is_true",
        "accuracy",
        "trust",
    ):
        assert hidden not in text
    assert [(r.text, r.heard_label, r.unconfirmed) for r in view.rumors] == [
        ("The Calabrians did it.", "Heard 2 hours ago", True)
    ]
    # Carmine smiles at Luca and hates him: the screen shows the smile (W4).
    (carmine,) = view.people
    assert (carmine.attitude, carmine.attitude_label) == (Attitude.FRIENDLY, "Friendly")


def test_people_are_the_ones_the_player_knows():
    state = grounded_world()
    names = [p.name for p in memory_view(state).people]
    state.characters["bartender"].known_by.append("luca")

    assert names == ["Carmine Russo"]
    assert [p.name for p in memory_view(state).people] == ["Carmine Russo", "Gennaro"]
    # Known but never met: no attitude to read.
    gennaro = memory_view(state).people[1]
    assert (gennaro.attitude, gennaro.attitude_label) == (None, None)


def test_known_facts_join_the_lines_true_or_not():
    state = grounded_world()
    state.facts["f1"] = Fact(
        id="f1",
        text="Carmine says he was in Rome that night.",
        is_true=False,
        subject_ids=["carmine"],
        known_by=["luca"],
    )

    (carmine,) = memory_view(state).people

    assert carmine.lines[-1] == "Carmine says he was in Rome that night."


def test_a_death_shows_only_once_the_player_knows_of_it():
    state = grounded_world()
    state.scene.present_ids = ["luca"]
    unseen = engine(state, characters=[CharacterChange(id="carmine", status=CharacterStatus.DEAD)])
    seen = engine(
        state,
        characters=[
            CharacterChange(id="carmine", status=CharacterStatus.DEAD, known_to_player=True)
        ],
    )
    presumed = engine(
        state,
        characters=[
            CharacterChange(
                id="carmine",
                status=CharacterStatus.DEAD,
                death_certainty=DeathCertainty.PRESUMED,
                known_to_player=True,
            )
        ],
    )

    assert memory_view(unseen).people[0].status_label == "Alive"
    assert memory_view(seen).people[0].status_label == "Dead"
    assert memory_view(presumed).people[0].status_label == "Presumed dead"
    # The value each label says travels with it, in any language, so a screen needn't read words.
    said = [
        (p.status, p.presumed, p.status_label)
        for view in (unseen, seen, presumed)
        for p in memory_view(view, ES).people[:1]
    ]
    assert said == [
        ("alive", False, "Con vida"),
        ("dead", False, "Ha muerto"),
        ("dead", True, "Se cree que ha muerto"),
    ]


def test_a_change_nobody_told_the_player_leaves_their_belief_alone():
    state = grounded_world()
    state.scene.present_ids = ["luca"]
    missing = engine(
        state,
        characters=[
            CharacterChange(id="carmine", status=CharacterStatus.MISSING, known_to_player=True)
        ],
    )
    back = engine(missing, characters=[CharacterChange(id="carmine", status=CharacterStatus.ALIVE)])

    carmine = memory_view(back).people[0]
    assert (carmine.status, carmine.presumed, carmine.status_label) == ("missing", False, "Missing")


def own_deed(state: WorldState, deed_id: str, **kwargs) -> None:
    fields = {
        "actor_id": state.player_id,
        "kind": "shoot",
        "text": f"Shot at Carmine ({deed_id})",  # each its own, so none folds into another
        "turn": 3,
        "world_s": 0,
    }
    state.deeds[deed_id] = Deed(id=deed_id, **(fields | kwargs))


def known_labels(state: WorldState) -> dict[str, str]:
    return {d.id: d.known_label for d in memory_view(state).deeds}


def test_who_saw_a_deed_as_far_as_the_player_knows():
    state = grounded_world()
    own_deed(state, "seen-by-strangers", witness_ids=["bartender"], visibility=Visibility.WITNESSED)
    own_deed(state, "seen-by-known", witness_ids=["carmine", "bartender"])
    own_deed(state, "secret")
    own_deed(state, "spied-on", witness_ids=["bartender"], unnoticed_witness_ids=["bartender"])
    own_deed(state, "public", visibility=Visibility.PUBLIC)

    assert known_labels(state) == {
        "seen-by-strangers": "You were seen",
        "seen-by-known": "Seen by Carmine Russo and 1 other",
        "secret": "No one saw, as far as you know",
        "spied-on": "No one saw, as far as you know",
        "public": "Done in public",
    }
    assert {d.id: d.seen for d in memory_view(state).deeds} == {
        "seen-by-strangers": DeedSeen.SEEN,
        "seen-by-known": DeedSeen.SEEN,
        "secret": DeedSeen.UNSEEN,
        "spied-on": DeedSeen.UNSEEN,  # C6: a watcher they never noticed
        "public": DeedSeen.PUBLIC,
    }


def trails(state: WorldState, language=Language.EN) -> dict[str, list[tuple[str, str]]]:
    return {
        d.id: [(t.kind.value, t.text) for t in d.trail] for d in memory_view(state, language).deeds
    }


def came(state: WorldState, event_id: str, *, found: bool = True, **payload) -> None:
    """Someone came to the player character over a deed: the answer the world applied, and the
    fact of it, which those who were there know."""
    state.pending_events[event_id] = PendingEvent(
        id=event_id,
        kind=Kind.ANSWER,
        due_s=state.world_s,
        status=EventStatus.APPLIED,
        applied_s=state.world_s,
        payload={"target_id": state.player_id} | payload,
    )
    state.facts[event_id] = Fact(
        id=event_id,
        text="They came",
        known_by=[state.player_id] if found else ["carmine"],
        origin=Origin(kind=OriginKind.EVENT, ref_id=event_id),
    )


def test_a_deed_tells_whom_the_character_saw_go_off_to_tell_and_who_of_them_is_dead():
    state = grounded_world()
    own_deed(
        state,
        "shot",
        severity=3,
        witness_ids=["carmine", "bartender", "spy"],
        unnoticed_witness_ids=["spy"],
        went_to_tell={"carmine": "police", "bartender": "ghosts", "spy": "police"},
    )
    own_deed(state, "quiet", witness_ids=["carmine"])

    assert trails(state)["shot"] == [
        # Gennaro is nobody they know by name, and the faction he went to none they know of.
        ("went", "Someone went off to tell what they saw"),
        ("went", "Carmine Russo went to tell the Polizia di Stato in Naples"),
    ]
    assert trails(state)["quiet"] == []

    state.scene.present_ids = ["luca", "carmine"]  # Gennaro is elsewhere by now
    dead = engine(
        state,
        characters=[
            CharacterChange(id="carmine", status=CharacterStatus.DEAD, known_to_player=True),
            CharacterChange(id="bartender", status=CharacterStatus.DEAD),
        ],
    )

    # C6: only a death they know of.
    assert [kind for kind, _ in trails(dead)["shot"]] == ["went", "went", "dead"]
    assert trails(dead)["shot"][-1] == ("dead", "Carmine Russo is dead")
    dead.characters["bartender"].status_history[-1].known_by.append("luca")
    assert trails(dead)["shot"][-2:] == [
        ("dead", "Someone who saw it is dead"),  # nobody they know by name
        ("dead", "Carmine Russo is dead"),
    ]
    assert trails(dead)["quiet"] == [("dead", "Carmine Russo is dead")]


def test_a_deed_tells_what_a_scene_said_of_it_and_who_came_over_it_in_the_order_it_happened():
    state = grounded_world()
    own_deed(state, "shot", severity=3)
    own_deed(state, "other")
    state.world_s = 3 * DAY
    state.rumors = {
        "told": Rumor(
            id="told",
            text="Someone shot at Carmine in his own bar",
            is_true=True,
            deed_id="shot",
            heard_at={"luca": 2 * DAY, "carmine": 0},
        ),
        "again": Rumor(  # the same words from another teller: one line, by the last hearing
            id="again",
            text="Someone shot at Carmine in his own bar",
            is_true=True,
            deed_id="shot",
            heard_at={"luca": DAY},
        ),
        "unheard": Rumor(
            id="unheard", text="Luca did it", is_true=True, deed_id="shot", heard_at={"carmine": 0}
        ),
        "elsewhere": Rumor(
            id="elsewhere", text="Rain is coming", is_true=True, heard_at={"luca": DAY}
        ),
    }
    state.world_s = DAY
    came(state, "faced", answer="confront", avenger_id="carmine", deed_id="shot")
    state.world_s = 3 * DAY - HOUR
    came(state, "arrest", answer="arrest", faction_id="police", deed_id="shot")
    came(state, "missed", found=False, answer="revenge", avenger_id="carmine", deed_id="shot")
    came(state, "bounty", answer="bounty", faction_id="police", deed_id="shot")
    came(state, "stranger", answer="hunters", faction_id="ghosts", deed_id="shot")
    state.pending_events["arrest"].applied_s = 3 * DAY - HOUR
    state.pending_events["on-its-way"] = PendingEvent(
        id="on-its-way",
        kind=Kind.ANSWER,
        due_s=4 * DAY,
        payload={"target_id": "luca", "answer": "revenge", "deed_id": "shot"},
    )
    state.world_s = 3 * DAY

    assert trails(state) == {
        "shot": [
            ("came", "Carmine Russo came to face you over it, 2 days ago"),
            ("heard", "Heard a day ago: “Someone shot at Carmine in his own bar”"),
            ("came", "The Polizia di Stato in Naples came to arrest you, an hour ago"),
            ("came", "Someone came for you over it, an hour ago"),
        ],
        "other": [],
    }


def test_who_else_knows_is_an_open_question_only_where_it_is_one():
    state = grounded_world()
    own_deed(state, "seen", severity=3, witness_ids=["carmine"])
    own_deed(state, "slight", severity=1, witness_ids=["carmine"])
    own_deed(state, "bout", severity=3, witness_ids=["carmine"], terms=Terms.NO_HARM)
    own_deed(state, "spied-on", severity=3, witness_ids=["x"], unnoticed_witness_ids=["x"])
    own_deed(state, "secret", severity=3)
    own_deed(state, "came-of-it", severity=3)
    own_deed(state, "public", severity=3, visibility=Visibility.PUBLIC, witness_ids=["carmine"])
    own_deed(
        state, "theirs", severity=3, actor_id="carmine", witness_ids=["luca"], known_by=["luca"]
    )
    state.rumors["r"] = Rumor(
        id="r", text="A man was shot", is_true=True, deed_id="came-of-it", heard_at={"luca": 0}
    )

    assert {d.id: d.open_label for d in memory_view(state).deeds} == {
        "seen": "Who else knows? You can't tell until you hear it, or go and find out.",
        "slight": None,  # nothing word travels about (W12)
        "bout": None,  # nobody's to report (W1)
        "spied-on": None,  # C6: a watcher they never noticed
        "secret": None,
        "came-of-it": "Who else knows? You can't tell until you hear it, or go and find out.",
        "public": None,  # everybody knows
        "theirs": None,
    }


def test_blows_that_read_as_one_deed_tell_what_became_of_any_of_them_once():
    state = grounded_world()
    for blow in ("b1", "b2"):
        own_deed(
            state,
            blow,
            text="Shot at Carmine",
            witness_ids=["carmine"],
            went_to_tell={"carmine": "police"},
        )
    state.rumors["r"] = Rumor(
        id="r", text="A man was shot", is_true=True, deed_id="b2", heard_at={"luca": 0}
    )

    assert trails(state) == {
        "b1": [
            ("went", "Carmine Russo went to tell the Polizia di Stato in Naples"),
            ("heard", "Heard moments ago: “A man was shot”"),
        ]
    }


def test_what_became_of_a_deed_in_spanish_and_catalan():
    state = grounded_world()
    state.factions["tigres"] = Faction(id="tigres", name="Los Tigres Negros", known_by=["luca"])
    own_deed(
        state,
        "shot",
        severity=3,
        witness_ids=["carmine", "bartender"],
        went_to_tell={"carmine": "police", "bartender": "ghosts"},
    )
    state.rumors["r"] = Rumor(
        id="r", text="A man was shot", is_true=True, deed_id="shot", heard_at={"luca": 0}
    )
    came(state, "faced", answer="confront", avenger_id="carmine", deed_id="shot")
    came(state, "hunt", answer="hunters", faction_id="tigres", deed_id="shot")
    came(state, "gifts", answer="appease", faction_id="police", deed_id="shot")
    state.world_s = 2 * DAY
    state = engine(
        state,
        characters=[
            CharacterChange(id="carmine", status=CharacterStatus.DEAD, known_to_player=True)
        ],
    )

    assert [text for _, text in trails(state, ES)["shot"]] == [
        "Alguien se fue a contar lo que vio",
        "Carmine Russo fue a contárselo a the Polizia di Stato in Naples",
        "Carmine Russo ha muerto",
        "Carmine Russo vino a pedirte cuentas, hace 2 días",
        "The Polizia di Stato in Naples vino a verte por ello, hace 2 días",
        "Los Tigres Negros vinieron a por ti por ello, hace 2 días",
        "Lo oíste hace 2 días: «A man was shot»",
    ]
    assert [text for _, text in trails(state, CA)["shot"]] == [
        "Algú va marxar a explicar el que havia vist",
        "Carmine Russo va anar a explicar-ho a the Polizia di Stato in Naples",
        "Carmine Russo ha mort",
        "Carmine Russo va venir a demanar-te comptes, fa 2 dies",
        "The Polizia di Stato in Naples va venir a veure't per això, fa 2 dies",
        "Los Tigres Negros van venir a buscar-te per això, fa 2 dies",
        "Ho vas sentir fa 2 dies: «A man was shot»",
    ]
    (deed,) = memory_view(state, ES).deeds
    assert deed.open_label == (
        "¿Quién más lo sabe? No lo sabrás hasta que lo oigas o vayas a averiguarlo."
    )
    (deed,) = memory_view(state, CA).deeds
    assert (
        deed.open_label == "Qui més ho sap? No ho sabràs fins que ho sentis o ho vagis a esbrinar."
    )


def test_others_deeds_show_only_when_the_player_knows_of_them():
    state = grounded_world()
    own_deed(state, "hidden", actor_id="carmine", text="Paid the killer")
    own_deed(state, "heard", actor_id="carmine", text="Threatened Gennaro", known_by=["luca"])
    own_deed(
        state,
        "saw",
        actor_id="carmine",
        text="Slapped Gennaro",
        witness_ids=["luca"],
        known_by=["luca"],
    )
    own_deed(state, "rewound", timeline_id="t2")

    assert known_labels(state) == {"heard": "You heard of it", "saw": "You saw it"}
    assert {d.id: d.seen for d in memory_view(state).deeds} == {
        "heard": DeedSeen.HEARD_OF,
        "saw": DeedSeen.WATCHED,
    }
    assert memory_view(state).deeds[0].when_label == "14 May 1974, 21:00"


def test_a_stopped_time_deed_seen_by_an_immune_elder_looks_unseen():
    from engine import pipeline
    from engine.context import TurnContext
    from engine.contracts import OutcomeClass, ProposedDeed, Resolution, StepResolution
    from engine.rng import SeededRng
    from engine.state import StepResult

    strike = ProposedDeed(
        kind="strike", text="Struck Zhao", witness_ids=["elder-mo"], in_stopped_time=True
    )
    step = StepResolution(
        index=0,
        text="strike",
        outcome_class=OutcomeClass.CERTAIN,
        reason="",
        result=StepResult.SUCCESS,
        duration_s=0,
        personal_s=2,
        deeds=[strike],
    )
    played = pipeline.play_out(
        cultivation_world(),
        Resolution(steps=[step]),
        TurnContext(story_id="s2", turn=3),
        SeededRng("s2"),
    )

    assert [d.known_label for d in memory_view(played.state).deeds] == [
        "No one saw, as far as you know"
    ]


def test_leads_goals_and_threads():
    state = grounded_world()
    state.world_s = DAY
    state.leads = {
        "open": Lead(id="open", text="Meet the priest", expires_s=DAY + 3 * HOUR),
        "forever": Lead(id="forever", text="The old ledger"),
        "gone": Lead(id="gone", text="A boat at midnight", expires_s=DAY - 1),
        "taken": Lead(id="taken", text="Taken", status=LeadStatus.TAKEN),
    }
    state.threads["revenge"].known_by = []

    view = memory_view(state)

    assert [(le.id, le.expires_label) for le in view.leads] == [
        ("forever", None),
        ("open", "Ends in 3 hours"),
    ]
    assert [g.id for g in view.goals] == ["find-killer"]
    assert view.threads == []


def with_goals() -> WorldState:
    """Luca's goals twelve days in: one from the start, one he stated, one Carmine asked of him,
    a lead from nobody in particular, and one from a stranger on a record older than dates."""
    state = grounded_world()  # 14 May 1974, 21:00
    state.world_s = 12 * DAY
    taken = LeadStatus.TAKEN
    state.leads = {
        "job": Lead(
            id="job", text="Who robs the till", from_id="carmine", offered_s=2 * DAY, status=taken
        ),
        "ledger": Lead(id="ledger", text="The old ledger", status=taken),
        "parcel": Lead(id="parcel", text="Carry the parcel", from_id="bartender", status=taken),
    }
    state.goals |= {
        "goal-2": Goal(id="goal-2", text="Leave Naples", set_turn=5, set_s=DAY),
        "goal-3": Goal(
            id="goal-3",
            text="Who robs the till",
            set_turn=6,
            set_s=3 * DAY,
            lead_id="job",
            moved_turn=9,
            progress="It happens at night.",
        ),
        "goal-4": Goal(
            id="goal-4", text="The old ledger", set_turn=7, set_s=4 * DAY, lead_id="ledger"
        ),
        "goal-5": Goal(id="goal-5", text="Carry the parcel", set_turn=8, lead_id="parcel"),
    }
    return state


def goals_of(state: WorldState, language: Language = Language.EN) -> list[tuple]:
    return [(g.id, g.kind.value, g.origin_label) for g in memory_view(state, language).goals]


def test_goals_show_the_thread_followed_first_and_where_each_came_from():
    """N2: the one the story last moved, then the player's own, then the ones on the side, the
    one set or moved last first in each. Who asked is named on the day they asked; a stranger
    isn't named (C6)."""
    state = with_goals()

    assert goals_of(state) == [
        ("goal-3", "followed", "Asked of you by Carmine Russo, 16 May 1974"),
        ("goal-2", "own", "You set it yourself, 15 May 1974"),
        ("find-killer", "own", "Yours from the start"),
        ("goal-5", "side", "A lead you took up"),
        ("goal-4", "side", "A lead you took up, 18 May 1974"),
    ]
    view = memory_view(state)
    assert [g.origin.value for g in view.goals] == ["asked", "stated", "start", "taken", "taken"]
    assert [g.progress for g in view.goals] == ["It happens at night.", None, None, None, None]
    assert "Gennaro" not in dumped(view)

    state.goals["find-killer"].moved_turn = 8  # a scene moved it, before the thread followed
    assert [g.id for g in memory_view(state).goals][:3] == ["goal-3", "find-killer", "goal-2"]

    state.bible.calendar = Calendar()  # a day count
    assert goals_of(state)[0] == ("goal-3", "followed", "Asked of you by Carmine Russo, day 3")


def test_goals_say_where_they_came_from_in_the_storys_language():
    state = with_goals()

    assert [label for _, _, label in goals_of(state, ES)] == [
        "Te lo pidió Carmine Russo, 16 de mayo de 1974",
        "Te la marcaste tú, 15 de mayo de 1974",
        "Tuya desde el principio",
        "Una pista que seguiste",
        "Una pista que seguiste, 18 de mayo de 1974",
    ]
    assert [label for _, _, label in goals_of(state, CA)] == [
        "T'ho va demanar Carmine Russo, 16 de maig de 1974",
        "Te la vas marcar tu, 15 de maig de 1974",
        "Teva des del principi",
        "Una pista que vas seguir",
        "Una pista que vas seguir, 18 de maig de 1974",
    ]
    state.bible.calendar = Calendar()
    assert goals_of(state, ES)[1][2] == "Te la marcaste tú, día 2"


def test_goals_that_are_over_are_listed_with_the_day_they_closed():
    """Achieved, failed or given up, in the order they closed. One that only said another again
    isn't listed, and neither is one of the character before them (N6)."""
    state = with_goals()
    goals = state.goals
    goals["find-killer"].status, goals["find-killer"].closed_turn = GoalStatus.ACHIEVED, 30
    goals["find-killer"].closed_s = 9 * DAY
    goals["goal-2"].status, goals["goal-2"].closed_turn = GoalStatus.ABANDONED, 12
    goals["goal-4"].status, goals["goal-4"].closed_turn = GoalStatus.FAILED, 20
    goals["goal-4"].closed_s = 6 * DAY
    goals["goal-5"].status, goals["goal-5"].merged_into = GoalStatus.MERGED, "goal-3"

    view = memory_view(state)

    assert [g.id for g in view.goals] == ["goal-3"]
    assert [(g.id, g.how.value, g.when_label) for g in view.goals_done] == [
        ("goal-2", "abandoned", None),  # closed before closing times were kept
        ("goal-4", "failed", "20 May 1974"),
        ("find-killer", "achieved", "23 May 1974"),
    ]
    assert memory_view(state, ES).goals_done[-1].when_label == "23 de mayo de 1974"

    state.fallen.append(
        Fallen(
            character_id="nonno",
            name="Nonno",
            ending="death",
            turn=25,
            world_s=7 * DAY,
            successor_id="luca",
        )
    )
    assert [g.id for g in memory_view(state).goals_done] == []


def test_places_and_factions_show_known_status_only():
    state = grounded_world()
    state.scene.present_ids = ["luca"]
    seen_ruin = engine(
        state, places=[PlaceChange(id="questura", status=PlaceStatus.RUINED, known_to_player=True)]
    )
    unseen_ruin = engine(state, places=[PlaceChange(id="naples", status=PlaceStatus.DAMAGED)])
    state.factions["police"].status = FactionStatus.WEAKENED  # no history: the start of the story

    places = {p.id: p.lines for p in memory_view(seen_ruin).places}
    unseen = {p.id: p.lines for p in memory_view(unseen_ruin).places}
    factions = {f.id: f.lines for f in memory_view(state).factions}

    assert "Ruined" in places["questura"]
    assert unseen["naples"] == ["City", "You haven't been there."]
    assert "You haven't been there." not in places["bar"]
    assert factions["police"][-1] == "Weakened"
    assert [f.name for f in memory_view(state).factions] == [
        "Carmine's crew",
        "the Esposito family",
        "the Polizia di Stato in Naples",
    ]


@pytest.mark.parametrize(
    ("esteem", "fear", "label"),
    [
        (0, 0, "Neutral"),
        (70, 0, "Admired"),
        (30, 70, "Respected and feared"),
        (-30, 30, "Disliked and wary of you"),
        (-90, 0, "Despised"),
        (0, 80, "Feared"),
    ],
)
def test_standing_in_words(esteem, fear, label):
    assert standing_label(Reputation(esteem=esteem, fear=fear)) == label


def test_a_faction_carries_the_esteem_and_the_dread_its_standing_says():
    state = grounded_world()
    state.factions["police"].player_reputation = Reputation(esteem=-30, fear=70)
    state.factions["esposito"].player_reputation = Reputation(esteem=70)

    stands = {f.id: (f.esteem, f.dread, f.standing_label) for f in memory_view(state).factions}

    assert stands["police"] == (Esteem.DISLIKED, Dread.FEARED, "Disliked and feared")
    assert stands["esposito"] == (Esteem.ADMIRED, Dread.NONE, "Admired")


@pytest.mark.parametrize(
    ("affinity", "label"),
    [(80, "Warm"), (30, "Friendly"), (0, "Neutral"), (-30, "Cold"), (-80, "Hostile")],
)
def test_attitudes_in_words(affinity, label):
    assert attitude_label(affinity) == label


def test_status_shows_the_sheet_the_clock_and_how_long_ago():
    state = cultivation_world()
    state.world_s = 2 * DAY
    lin = state.player
    lin.personal_offset_s = 10
    lin.sheet.powers[0].ready_at_personal_s = state.world_s + 10 + 3 * HOUR
    own_deed(state, "old", text="Beat Zhao at the well", world_s=0)
    own_deed(state, "new", text="Bowed to the elder", world_s=DAY)
    state.factions["outer-court"].player_reputation = Reputation(esteem=30)

    view = status_view(state)

    assert view.clock.label == "Day 3, morning" and view.clock.world_s == 2 * DAY
    assert "Time stop: ready in 3 hours" in view.character.lines
    assert "Qi: 40%" in view.character.lines
    assert [(s.text, s.ago_label) for s in view.since] == [
        ("Bowed to the elder", "a day ago"),
        ("Beat Zhao at the well", "2 days ago"),
    ]
    assert {r.name: r.label for r in view.reputation}["the outer court"] == "Respected"


def test_status_shows_what_each_power_costs_as_the_sheet_says():
    # G13: an ability's drawback is never a surprise: it is the sheet's, and Status shows it.
    lines = status_view(cultivation_world()).character.lines

    assert "Time stop, cost: Leaves him drained" in lines
    free = cultivation_world()
    free.player.sheet.powers[0].costs = []
    assert not any("cost:" in line for line in status_view(free).character.lines)


def test_status_shows_the_techniques_they_know_in_the_storys_language():
    # A4, G25: a move made their own in play shows, so the player can see it is theirs.
    state = cultivation_world()
    state.player.sheet.techniques.append(
        Technique(id="technique-cuchilla-de-aura", name="Cuchilla de aura")
    )

    # A technique saved before mastery was kept is practiced, with nothing counted yet.
    assert "Cuchilla de aura (technique, practiced, 0 of 15 uses)" in lines_of(state)
    assert "Cuchilla de aura (técnica, practicada, 0 de 15 usos)" in lines_of(state, ES)
    assert "Cuchilla de aura (tècnica, practicada, 0 de 15 usos)" in lines_of(state, CA)
    assert not any("technique" in line for line in lines_of(cultivation_world()))


def lines_of(state, language=Language.EN) -> list[str]:
    return status_view(state, language).character.lines


def test_status_shows_how_well_they_have_each_technique_and_the_uses_counted():
    # A4: mastery grows with use, with a count the player can see.
    state = cultivation_world()
    blade = Technique(id="blade", name="Aura blade", mastery=Mastery.LEARNING, uses=2)
    state.player.sheet.techniques.append(blade)

    assert "Aura blade (technique, learning, 2 of 6 uses)" in lines_of(state)
    assert "Aura blade (técnica, aprendiendo, 2 de 6 usos)" in lines_of(state, ES)
    assert "Aura blade (tècnica, aprenent, 2 de 6 usos)" in lines_of(state, CA)

    blade.mastery, blade.uses = Mastery.SKILLED, 29
    assert "Aura blade (technique, skilled, 29 of 30 uses)" in lines_of(state)
    assert "Aura blade (técnica, dominada, 29 de 30 usos)" in lines_of(state, ES)
    assert "Aura blade (tècnica, dominada, 29 de 30 usos)" in lines_of(state, CA)

    # Use alone takes a move no further than second nature, so no count is shown from there.
    blade.mastery, blade.uses = Mastery.SECOND_NATURE, 40
    assert "Aura blade (technique, second nature)" in lines_of(state)
    assert "Aura blade (técnica, segunda naturaleza)" in lines_of(state, ES)
    assert "Aura blade (tècnica, segona naturalesa)" in lines_of(state, CA)
    blade.mastery = Mastery.OWN
    assert "Aura blade (technique, made your own)" in lines_of(state)
    assert "Aura blade (técnica, hecha tuya)" in lines_of(state, ES)
    assert "Aura blade (tècnica, feta teva)" in lines_of(state, CA)


def test_status_counts_a_geniuss_uses_at_their_own_pace():
    # A4: a gift for learning takes a quarter of the uses, and Status says how many are left.
    state = cultivation_world()
    state.player.sheet.traits.append(Trait(name="Genius", kind=TraitKind.GIFT))
    blade = Technique(id="blade", name="Aura blade", mastery=Mastery.LEARNING, uses=1)
    state.player.sheet.techniques.append(blade)

    assert "Aura blade (technique, learning, 1 of 2 uses)" in lines_of(state)
    blade.mastery = Mastery.SKILLED
    assert "Aura blade (technique, skilled, 1 of 8 uses)" in lines_of(state)


def test_status_shows_money_and_what_is_carried():
    lines = status_view(grounded_world()).character.lines

    assert "200,000 lire" in lines and "Beretta pistol" in lines
    assert "Alfa Romeo Giulia" not in lines  # parked, not carried


def test_a_change_recorded_without_its_old_status_falls_back_to_the_kinds_start():
    from engine.state import StatusChange

    state = grounded_world()
    state.places["bar"].status = PlaceStatus.RUINED
    state.places["bar"].status_history.append(StatusChange(status="ruined", turn=1, world_s=0))
    state.factions["police"].status = FactionStatus.DESTROYED
    state.factions["police"].status_history.append(
        StatusChange(status="destroyed", turn=1, world_s=0)
    )

    view = memory_view(state)

    assert {p.id: p.lines for p in view.places}["bar"] == ["Building"]
    assert {f.id: f.lines for f in view.factions}["police"] == ["Police"]


# --- Deeds in the world's words (G16, C6) ---------------------------------------------------


def deed_texts(state: WorldState) -> dict[str, str]:
    return {d.id: d.text for d in memory_view(state).deeds}


def test_the_player_s_deeds_read_in_the_world_s_words():
    state = cultivation_world()
    state.characters["zhao"].status = CharacterStatus.DEAD
    state.characters["zhao"].status_history = [
        StatusChange(status="dead", from_status="alive", known_by=["lin"], turn=3, world_s=0)
    ]
    own_deed(
        state,
        "kill",
        kind="kill",
        text="cut Zhao down by the well (it worked)",
        victim_ids=["zhao"],
        place_id="well",
        severity=4,
    )
    own_deed(
        state,
        "hit",
        actor_id="zhao",
        kind="assault",
        text="punch Lin (it worked)",
        victim_ids=["lin"],
        place_id="well",
        known_by=["lin"],
        severity=2,
    )
    own_deed(state, "bow", text="Bowed to the elder")

    assert deed_texts(state) == {
        "kill": "You killed Zhao Kun at the outer-court well.",
        "hit": "Zhao Kun attacked you at the outer-court well.",
        "bow": "Bowed to the elder",  # no words for it in the world: its own text
    }
    (since, *_) = status_view(state).since
    assert since.text == "You killed Zhao Kun at the outer-court well."


def test_a_deed_names_only_whom_the_player_knows_and_deaths_they_know_of():
    """C6: Elder Mo is a stranger to Lin, so he is "someone"; and Lin doesn't know the strike
    killed him, so it reads as the wounding Lin saw."""
    state = cultivation_world()
    mo = state.characters["elder-mo"]
    mo.status = CharacterStatus.DEAD
    mo.status_history = [StatusChange(status="dead", from_status="alive", turn=3, world_s=0)]
    own_deed(
        state,
        "strike",
        kind="kill",
        text="strike the old man (it worked)",
        victim_ids=["elder-mo"],
        place_id="well",
        severity=4,
    )

    text = deed_texts(state)["strike"]

    assert text == "You wounded someone at the outer-court well."
    assert "Elder Mo" not in dumped(memory_view(state))


def test_a_death_is_laid_only_at_the_deed_that_caused_it():
    """A wound Lin dealt on turn 3 isn't a killing because Zhao died of something else on turn
    5, nor because he died on a timeline that was rewound."""

    def remembered(death: StatusChange) -> str:
        state = cultivation_world()
        zhao = state.characters["zhao"]
        zhao.status = CharacterStatus.DEAD
        zhao.status_history = [death]
        own_deed(
            state,
            "hit",
            kind="kill",
            text="stab Zhao (it partly worked)",
            victim_ids=["zhao"],
            place_id="well",
            severity=4,
        )
        return deed_texts(state)["hit"]

    def died(**fields) -> StatusChange:
        return StatusChange(
            status="dead", from_status="alive", known_by=["lin"], world_s=0, **fields
        )

    assert remembered(died(turn=3)) == "You killed Zhao Kun at the outer-court well."
    assert remembered(died(turn=5)) == "You wounded Zhao Kun at the outer-court well."
    rewound = died(turn=3, timeline_id="t0")
    assert remembered(rewound) == "You wounded Zhao Kun at the outer-court well."


def test_some_died_and_some_lived():
    state = cultivation_world()
    state.characters["elder-mo"].known_by.append("lin")
    mo = state.characters["elder-mo"]
    mo.status = CharacterStatus.DEAD
    mo.status_history = [
        StatusChange(status="dead", from_status="alive", known_by=["lin"], turn=3, world_s=0)
    ]
    own_deed(
        state,
        "blast",
        actor_id="zhao",
        kind="kill",
        text="blast them both (it worked)",
        victim_ids=["elder-mo", "lin"],
        place_id="well",
        known_by=["lin"],
        severity=4,
    )
    own_deed(state, "cut", kind="wound", text="cut myself", victim_ids=["lin"], severity=3)

    texts = deed_texts(state)

    assert texts["blast"] == "Zhao Kun killed Elder Mo and wounded you at the outer-court well."
    assert texts["cut"] == "You wounded yourself."


# V6: the speech model's custom vocabulary is the names the player character knows (C6).


def test_speech_vocabulary_is_the_names_the_character_knows_most_relevant_first():
    assert speech_vocabulary(cultivation_world()) == [
        "Lin Feng",  # the character's own name
        "Zhao Kun",  # in the scene
        "outer-court well",  # where the scene is
        "Azure Peak",
        "inner court",
        "Azure Cloud Sect",
        "outer court",
    ]


def test_speech_vocabulary_never_has_a_name_the_character_doesnt_know():
    state = grounded_world()
    assert "bartender" in state.scene.present_ids  # Gennaro is in the scene, but unnamed to Luca

    names = speech_vocabulary(state)

    assert "Gennaro" not in names
    assert names[:3] == ["Luca Esposito", "Carmine Russo", "Carmine's bar"]
    assert "Elder Mo" not in speech_vocabulary(cultivation_world())


def test_speech_vocabulary_learns_a_name_once_it_is_known():
    state = cultivation_world()
    state.characters["elder-mo"].known_by.append(state.player_id)

    assert "Elder Mo" in speech_vocabulary(state)


def test_speech_vocabulary_keeps_each_name_once_within_the_limit():
    state = cultivation_world()
    state.characters["zhao"].name = "  the  Azure   Peak "  # the same words as a place

    names = speech_vocabulary(state, limit=4)

    assert names == ["Lin Feng", "Azure Peak", "outer-court well", "inner court"]


def test_speech_vocabulary_keeps_a_name_that_starts_like_an_article():
    state = cultivation_world()
    state.characters["zhao"].name = "An Lushan"

    assert "An Lushan" in speech_vocabulary(state)


ES = Language.ES


@pytest.mark.parametrize(
    ("esteem", "fear", "label"),
    [
        (0, 0, "Neutral"),
        (70, 0, "Admiración"),
        (30, 70, "Respeto y temor"),
        (-30, 30, "Recelo y cautela"),
        (-90, 0, "Desprecio"),
        (0, 80, "Temor"),
    ],
)
def test_standing_in_spanish(esteem, fear, label):
    # S10: words that fit anyone, since a character's gender isn't recorded.
    assert standing_label(Reputation(esteem=esteem, fear=fear), ES) == label


def test_attitudes_in_spanish():
    labels = [attitude_label(a, ES) for a in (80, 30, 0, -30, -80)]

    assert labels == ["Cordial", "Afable", "Neutral", "Distante", "Hostil"]


def test_who_saw_a_deed_in_spanish():
    state = grounded_world()
    own_deed(state, "seen-by-strangers", witness_ids=["bartender"], visibility=Visibility.WITNESSED)
    own_deed(state, "seen-by-known", witness_ids=["carmine", "bartender"])
    own_deed(state, "secret")
    own_deed(state, "public", visibility=Visibility.PUBLIC)

    labels = {d.id: d.known_label for d in memory_view(state, ES).deeds}

    assert labels == {
        "seen-by-strangers": "Te vieron",
        "seen-by-known": "Te vieron Carmine Russo y 1 persona más",
        "secret": "Nadie lo vio, que tú sepas",
        "public": "A la vista de todos",
    }


def test_memory_in_spanish_keeps_the_world_s_own_words():
    state = grounded_world()
    state.world_s = DAY
    state.leads = {"open": Lead(id="open", text="Meet the priest", expires_s=DAY + 3 * HOUR)}

    view = memory_view(state, ES)

    assert [(le.text, le.expires_label) for le in view.leads] == [
        ("Meet the priest", "Termina en 3 horas")
    ]
    assert all(p.status_label == "Con vida" for p in view.people)


def test_status_in_spanish():
    state = cultivation_world()
    state.world_s = 2 * DAY
    lin = state.player
    lin.personal_offset_s = 10
    lin.sheet.powers[0].ready_at_personal_s = state.world_s + 10 + 3 * HOUR
    own_deed(state, "old", text="Beat Zhao at the well", world_s=0)
    state.factions["outer-court"].player_reputation = Reputation(esteem=30)

    view = status_view(state, ES)

    assert view.clock.label == "Día 3, mañana"
    assert "Time stop: disponible en 3 horas" in view.character.lines
    assert "Sin heridas" in view.character.lines
    assert [(s.text, s.ago_label) for s in view.since] == [("Beat Zhao at the well", "hace 2 días")]
    assert {r.name: r.label for r in view.reputation}["the outer court"] == "Respeto"
    assert "200.000 lire" in status_view(grounded_world(), ES).character.lines


CA = Language.CA


def test_standing_and_attitudes_in_catalan():
    assert standing_label(Reputation(esteem=30, fear=70), CA) == "Respecte i temor"
    assert standing_label(Reputation(esteem=-90), CA) == "Menyspreu"
    labels = [attitude_label(a, CA) for a in (80, 30, 0, -30, -80)]
    assert labels == ["Cordial", "Afable", "Neutral", "Distant", "Hostil"]


def test_memory_and_status_in_catalan():
    state = grounded_world()
    own_deed(state, "seen-by-known", witness_ids=["carmine", "bartender"])
    own_deed(state, "secret")
    state.world_s = DAY
    state.leads = {"open": Lead(id="open", text="Meet the priest", expires_s=DAY + 3 * HOUR)}

    memory = memory_view(state, CA)

    labels = {d.id: d.known_label for d in memory.deeds}
    assert labels == {
        "seen-by-known": "Et van veure Carmine Russo i 1 persona més",
        "secret": "Ningú no ho va veure, que tu sàpigues",
    }
    assert [le.expires_label for le in memory.leads] == ["Acaba d'aquí a 3 hores"]
    assert all(p.status_label == "Amb vida" for p in memory.people)
    lines = status_view(grounded_world(), CA).character.lines
    assert "200.000 lire" in lines and "Sense ferides" in lines


def test_status_tells_what_the_player_character_gained_and_lost_in_every_language():
    # C10: who has what they lost, named only if they know who it was (C6).
    from engine.contracts import ItemChange

    stranger = CharacterChange(id="stranger", name="Enzo", description="A man in a hat.")
    moves = [
        ItemChange(name="lire", money=True, quantity=50, from_id="luca", to_id="carmine"),
        ItemChange(name="a brass key", from_id="stranger", to_id="luca"),
        ItemChange(name="the flick knife", item_id="knife", from_id="luca", to_id="world"),
    ]
    state = engine(grounded_world(), characters=[stranger], items=moves)

    def since(language: Language) -> list[str]:
        return [s.text for s in status_view(state, language).since][:3]

    assert since(Language.EN) == [
        "Lost: flick knife",
        "From someone: brass key",
        "To Carmine Russo: 50 lire",
    ]
    assert since(ES) == [
        "Pérdida: flick knife",
        "De alguien: brass key",
        "Para Carmine Russo: 50 lire",
    ]
    assert since(CA) == ["Pèrdua: flick knife", "D'algú: brass key", "Per a Carmine Russo: 50 lire"]


def _talented():
    from engine.state import Talent, TalentCover, TalentFit, TalentRuling, TalentStrength

    state = cultivation_world()
    sheet = state.player.sheet
    sheet.talents = [
        Talent(
            id="sword",
            name="The sword",
            covers="anything fought with a blade",
            strength=TalentStrength.ONE_OF_A_KIND,
        ),
        Talent(id="architect", name="Architecture", strength=TalentStrength.GENIUS),
        Talent(id="hands", name="Quick hands", strength=TalentStrength.KNACK, covers="sleight"),
        Talent(id="words", name="Words", strength=TalentStrength.SLOW, covers="persuading"),
    ]
    sheet.talent_rulings = [
        TalentRuling(
            key="technique:aura-blade",
            what="Aura blade",
            covers=[
                TalentCover(talent_id="sword", fit=TalentFit.INSIDE),
                TalentCover(talent_id="architect", fit=TalentFit.RELATED),
            ],
        ),
        TalentRuling(
            key="technique:aura-wall",
            what="Aura wall",
            covers=[TalentCover(talent_id="architect", fit=TalentFit.RELATED)],
        ),
        TalentRuling(
            key="skill:haggling",
            what="Haggling",
            covers=[TalentCover(talent_id="words", fit=TalentFit.INSIDE)],
        ),
    ]
    return state


def test_status_shows_each_talent_with_its_strength_and_the_pace_it_gives():
    # A4: the player can see what the story reads on their sheet.
    state = _talented()

    assert lines_of(state)[-7:-3] == [
        "The sword (talent, one of a kind, eight times as fast): anything fought with a blade",
        "Architecture (talent, genius, four times as fast)",
        "Quick hands (talent, a knack, twice as fast): sleight",
        "Words (weakness, half the pace): persuading",
    ]
    assert lines_of(state, ES)[-7:-3] == [
        "The sword (talento único, ocho veces más rápido): anything fought with a blade",
        "Architecture (talento, genio, cuatro veces más rápido)",
        "Quick hands (talento, facilidad, el doble de rápido): sleight",
        "Words (punto débil, a la mitad de ritmo): persuading",
    ]
    assert lines_of(state, CA)[-7:-3] == [
        "The sword (talent únic, vuit vegades més ràpid): anything fought with a blade",
        "Architecture (talent, geni, quatre vegades més ràpid)",
        "Quick hands (talent, facilitat, el doble de ràpid): sleight",
        "Words (punt feble, a la meitat de ritme): persuading",
    ]


def test_status_shows_how_each_thing_ruled_on_stands_and_the_bridges_that_hold():
    # A4: the ruling the engine made, where the player can see it, with how fast it grows now.
    from engine.state import TalentBridge

    state = _talented()
    wall = "technique:aura-wall"
    state.player.sheet.bridges = [
        TalentBridge(key=wall, what="Aura wall", talent_id="architect", rests_on="the formula"),
        TalentBridge(key=wall, what="Aura wall", talent_id="architect", rests_on="a wish", steps=0),
        TalentBridge(
            key="skill:herb-lore", what="Herb lore", talent_id="hands", rests_on="deft picking"
        ),
    ]

    assert lines_of(state)[-6:] == [
        "Aura blade: grows ten times as fast, inside your talent (The sword), related to your"
        " talent (Architecture)",
        "Aura wall: grows four times as fast, inside your talent (Architecture)",
        "Bridge: the formula",
        "Haggling: grows at half the pace, slowed by your weakness (Words)",
        "Herb lore: grows twice as fast, inside your talent (Quick hands)",
        "Bridge: deft picking",
    ]
    assert lines_of(state, ES)[-6:] == [
        "Aura blade: crece diez veces más rápido, dentro de tu talento (The sword), afín a tu"
        " talento (Architecture)",
        "Aura wall: crece cuatro veces más rápido, dentro de tu talento (Architecture)",
        "Puente: the formula",
        "Haggling: crece a la mitad de ritmo, con el freno de tu punto débil (Words)",
        "Herb lore: crece el doble de rápido, dentro de tu talento (Quick hands)",
        "Puente: deft picking",
    ]
    assert lines_of(state, CA)[-6:] == [
        "Aura blade: creix deu vegades més ràpid, dins del teu talent (The sword), afí al teu"
        " talent (Architecture)",
        "Aura wall: creix quatre vegades més ràpid, dins del teu talent (Architecture)",
        "Pont: the formula",
        "Haggling: creix a la meitat de ritme, amb el fre del teu punt feble (Words)",
        "Herb lore: creix el doble de ràpid, dins del teu talent (Quick hands)",
        "Pont: deft picking",
    ]


def test_status_lists_what_no_talent_reaches_in_one_line():
    """A long story rules on dozens of things. What a talent reaches gets a line of its own;
    everything ruled outside them all shares one, so Status stays readable."""
    from engine.state import TalentBridge, TalentCover, TalentFit, TalentRuling

    state = _talented()
    sheet = state.player.sheet
    sheet.talent_rulings += [
        TalentRuling(
            key="skill:herb-lore",
            what="Herb lore",
            covers=[TalentCover(talent_id="sword", fit=TalentFit.OUTSIDE)],
        ),
        TalentRuling(key="technique:rope-trick", what="Rope trick"),
    ]
    # A bridge that didn't hold changes nothing here.
    sheet.bridges = [
        TalentBridge(
            key="skill:herb-lore", what="Herb lore", talent_id="hands", rests_on="luck", steps=0
        )
    ]

    assert lines_of(state)[-4:] == [
        "Aura blade: grows ten times as fast, inside your talent (The sword), related to your"
        " talent (Architecture)",
        "Aura wall: grows twice as fast, related to your talent (Architecture)",
        "Haggling: grows at half the pace, slowed by your weakness (Words)",
        "Outside your talents: Herb lore; Rope trick",
    ]
    assert lines_of(state, ES)[-1] == "Fuera de tus talentos: Herb lore; Rope trick"
    assert lines_of(state, CA)[-1] == "Fora dels teus talents: Herb lore; Rope trick"


def test_status_names_every_talent_that_reaches_a_thing_since_their_paces_add():
    """Miki's case: two one of a kind talents behind one technique."""
    from engine.state import Talent, TalentBridge, TalentCover, TalentFit, TalentStrength

    state = _talented()
    sheet = state.player.sheet
    sheet.talents.append(
        Talent(id="aura", name="Aura sense", strength=TalentStrength.ONE_OF_A_KIND)
    )
    sheet.talent_rulings[0].covers.append(TalentCover(talent_id="aura", fit=TalentFit.INSIDE))

    assert lines_of(state)[-3] == (
        "Aura blade: grows 18 times as fast, inside your talents (The sword and Aura sense),"
        " related to your talent (Architecture)"
    )
    assert lines_of(state, ES)[-3] == (
        "Aura blade: crece 18 veces más rápido, dentro de tus talentos (The sword y Aura sense),"
        " afín a tu talento (Architecture)"
    )
    assert lines_of(state, CA)[-3] == (
        "Aura blade: creix 18 vegades més ràpid, dins dels teus talents (The sword i Aura sense),"
        " afí al teu talent (Architecture)"
    )
    # A bridge from the third talent adds to what the other two give, and is shown with them.
    blade = "technique:aura-blade"
    sheet.bridges = [
        TalentBridge(key=blade, what="Aura blade", talent_id="architect", rests_on="the edge"),
    ]
    assert lines_of(state)[-4:-2] == [
        "Aura blade: grows 20 times as fast, inside your talents (The sword, Aura sense and"
        " Architecture)",
        "Bridge: the edge",
    ]


def test_status_says_related_until_a_bridge_carries_the_thing_all_the_way():
    state = _talented()

    assert "Aura wall: grows twice as fast, related to your talent (Architecture)" in lines_of(
        state
    )
    assert "Aura wall: crece el doble de rápido, afín a tu talento (Architecture)" in lines_of(
        state, ES
    )
    assert "Aura wall: creix el doble de ràpid, afí al teu talent (Architecture)" in lines_of(
        state, CA
    )


def test_a_sheet_saved_before_talent_was_a_record_shows_no_talent_lines():
    state = cultivation_world()
    state.player.sheet.traits.append(Trait(name="Genius", kind=TraitKind.GIFT))

    assert not any("talent" in line for line in lines_of(state))


def test_status_counts_a_techniques_uses_at_the_pace_its_own_ruling_gives():
    # A4: each technique at its own pace, not one pace for the whole sheet.
    state = _talented()
    state.player.sheet.techniques += [
        Technique(id="blade", name="Aura blade", mastery=Mastery.LEARNING),
        Technique(id="wall", name="Aura wall", mastery=Mastery.LEARNING),
        Technique(id="palm", name="Rising Palm", mastery=Mastery.LEARNING),
    ]

    lines = lines_of(state)

    assert "Aura blade (technique, learning, 0 of 1 uses)" in lines
    assert "Aura wall (technique, learning, 0 of 3 uses)" in lines
    assert "Rising Palm (technique, learning, 0 of 6 uses)" in lines


# --- the sheet, in sections (G13, G16) --------------------------------------------------------


def sheet_of(state, language=Language.EN):
    return status_view(state, language).sheet


def test_the_sheet_comes_in_sections_in_the_worlds_words():
    # G13, G16: the screen lays the sheet out, so each part comes on its own with the words
    # that say it, never as numbers.
    sheet = sheet_of(cultivation_world())

    assert sheet.about == ["Outer disciple, the outer court", "16 years old"]
    assert sheet.description.startswith("A thin outer disciple")
    assert (sheet.condition.health.value, sheet.condition.health_label) == ("unhurt", "Unhurt")
    assert [(r.name, r.level) for r in sheet.condition.reserves] == [("Qi", 40)]
    assert [(s.name, s.level_label, s.dice) for s in sheet.skills] == [("Herb lore", "Fair", 2)]
    assert [(t.name, t.kind_label) for t in sheet.traits] == [
        ("A past life's memories", "Gift"),
        ("A weak body", "Flaw"),
    ]
    assert sheet.temperament == ["calm", "patient"]
    (power,) = sheet.powers
    assert power.name == "Time stop" and power.secret
    assert power.limits == ["Three heartbeats per use", "A breath to recharge"]
    assert (power.cost, power.ready, power.ready_label) == ("Leaves him drained", True, "Ready")
    assert sheet.money_label is None and sheet.items == [] and sheet.techniques == []
    for number in ("attributes", "axes", "might", "tier"):  # G16: words, not numbers
        assert number not in dumped(sheet)


def test_the_path_stops_at_their_own_rung():
    # G18, C6: the rungs they climbed and the one they stand on. What lies above is the
    # world's to tell.
    state = cultivation_world()
    realms = state.bible.ladders[0]
    realms.rungs[2].description = "A core of qi takes shape."
    state.player.sheet.ladders[0].rung = 2
    state.player.sheet.ladders[0].stage = "late"

    (path,) = sheet_of(state).paths

    assert path.name == "Cultivation realms"
    assert [(r.name, r.stage, r.description) for r in path.rungs] == [
        ("Qi Condensation", "", ""),
        ("Foundation Establishment", "", ""),
        ("Core Formation", "Late stage", "A core of qi takes shape."),
    ]
    # G19: only their own rung says how full their rank is.
    assert [r.filled for r in path.rungs] == [None, None, 0.667]
    assert "Nascent Soul" not in dumped(status_view(state).sheet)
    # A ladder the world no longer has, or a rung past its end, shows no path.
    state.player.sheet.ladders[0].rung = 9
    assert sheet_of(state).paths == []
    assert sheet_of(grounded_world()).paths == []


def test_their_own_rung_says_how_full_their_rank_is_in_the_storys_language():
    # G19: the stage of their rank and how full it is, and at its peak that it can be tried.
    state = cultivation_world()
    effort = Practice(key="ladder:realms", what="Foundation Establishment", effort_s=40 * HOUR)
    state.player.sheet.practice.append(effort)

    def own(language=Language.EN):
        rung = sheet_of(state, language).paths[0].rungs[-1]
        return rung.stage, rung.filled

    assert own() == ("Middle stage", 0.4)
    assert own(Language.ES) == ("Etapa intermedia", 0.4)
    assert own(Language.CA) == ("Etapa intermèdia", 0.4)
    assert "Cultivation realms: Qi Condensation, middle stage" in status_view(state).character.lines

    effort.effort_s = 100 * HOUR
    assert own() == ("At its peak: you can try to break through", 1.0)
    assert own(Language.ES) == ("En su cima: puedes intentar dar el salto", 1.0)
    assert own(Language.CA) == ("Al seu cim: pots intentar fer el salt", 1.0)
    assert "Cultivation realms: Qi Condensation, at its peak" in status_view(state).character.lines

    # Effort kept toward another rung counts for nothing here, and neither does the top rung.
    effort.what = "Core Formation"
    assert own() == ("Early stage", 0.0)
    state.player.sheet.ladders[0].rung = len(state.bible.ladders[0].rungs) - 1
    assert own() == ("", None)
    assert "Cultivation realms: " + state.bible.ladders[0].rungs[-1].name in (
        status_view(state).character.lines
    )


def test_a_stage_their_rank_reached_is_told_among_how_they_grew():
    # G19, G17: "Qi Condensation: Late stage", with how it was made.
    state = cultivation_world()
    state.player.sheet.growth = [
        Gain(what="Qi Condensation", change="early to middle", source="use in play", reason=""),
        Gain(
            what="Qi Condensation",
            change="middle to peak",
            source="training (master)",
            reason="",
            world_s=3 * DAY,
        ),
    ]

    grew = sheet_of(state).grew
    assert [(g.kind.value, g.when, g.text, g.how) for g in grew] == [
        ("stage", "Day 4", "Qi Condensation: At its peak", "With a master"),
        ("stage", "Day 1", "Qi Condensation: Middle stage", "By doing it"),
    ]
    assert [g.text for g in sheet_of(state, Language.ES).grew] == [
        "Qi Condensation: En su cima",
        "Qi Condensation: Etapa intermedia",
    ]
    assert [g.text for g in sheet_of(state, Language.CA).grew] == [
        "Qi Condensation: Al seu cim",
        "Qi Condensation: Etapa intermèdia",
    ]


def test_the_path_says_when_each_rung_was_reached_and_left():
    # G18: a breakthrough is on record under the rung's name, with its day.
    state = cultivation_world()
    state.player.sheet.ladders[0].rung = 2
    state.player.sheet.growth = [
        Gain(
            what="Foundation Establishment",
            change="broke through to Foundation Establishment",
            source="breakthrough",
            reason="nine days alone",
            world_s=8 * DAY,
        ),
        Gain(
            what="Core Formation",
            change="broke through to Core Formation",
            source="breakthrough",
            reason="the storm",
            world_s=40 * DAY,
        ),
        Gain(what="Core Formation", change="read about it", source="study", reason="a scroll"),
    ]

    (path,) = sheet_of(state).paths
    assert [(r.name, r.note) for r in path.rungs] == [
        ("Qi Condensation", "Left behind, day 9"),
        ("Foundation Establishment", "Left behind, day 41"),
        ("Core Formation", "Reached, day 41"),
    ]
    (path,) = sheet_of(state, Language.ES).paths
    assert [r.note for r in path.rungs] == [
        "Quedó atrás, día 9",
        "Quedó atrás, día 41",
        "Lo alcanzaste, día 41",
    ]
    (path,) = sheet_of(state, Language.CA).paths
    assert [r.note for r in path.rungs] == [
        "Va quedar enrere, dia 9",
        "Va quedar enrere, dia 41",
        "Hi vas arribar, dia 41",
    ]
    # A rung they began on holds no day.
    state.player.sheet.growth = []
    assert [r.note for r in sheet_of(state).paths[0].rungs] == ["", "", ""]


def test_the_sheet_tells_how_they_grew_latest_first_in_the_storys_language():
    # A4, G17: each gain on record, read back and said with its day.
    state = cultivation_world()
    state.player.sheet.growth = [
        Gain(
            what="Falling Leaf Palm",
            change="learned",
            source="training (master)",
            reason="lessons at dawn",
            world_s=2 * DAY,
        ),
        Gain(
            what="swordsmanship",
            change="novice to fair",
            source="training (rival)",
            reason="sparring",
            world_s=5 * DAY,
        ),
        Gain(
            what="Foundation Establishment",
            change="broke through to Foundation Establishment",
            source="breakthrough",
            reason="nine days alone",
            world_s=8 * DAY,
        ),
        Gain(
            what="Falling Leaf Palm",
            change="learning to practiced",
            source="use in play",
            reason="the duel",
            world_s=11 * DAY,
        ),
        Gain(
            what="Gentle Release",
            change="a new way to use time stop",
            source="training (self)",
            reason="eight nights on the roof",
            world_s=12 * DAY,
        ),
        Gain(what="Cloud Step", change="learned", source="pulled off in play", reason="the roofs"),
        # A loss, and a gain in words nobody writes, are left out.
        Gain(what="left hand", change="lost", source="the duel", reason="", loss=True),
        Gain(what="luck", change="more of it", source="a wish", reason=""),
    ]
    state.player.sheet.growth[5].world_s = 13 * DAY

    grew = sheet_of(state).grew
    assert [(g.kind.value, g.when, g.text, g.how) for g in grew] == [
        ("learned", "Day 14", "Learned Cloud Step", "By doing it"),
        ("new_use", "Day 13", "Gentle Release: a new way to use time stop", "On your own"),
        ("mastery", "Day 12", "Falling Leaf Palm: Practiced", "By doing it"),
        ("breakthrough", "Day 9", "Broke through to Foundation Establishment", ""),
        ("skill", "Day 6", "Swordsmanship: Fair", "Against a rival"),
        ("learned", "Day 3", "Learned Falling Leaf Palm", "With a master"),
    ]
    assert [(g.when, g.text, g.how) for g in sheet_of(state, Language.ES).grew] == [
        ("Día 14", "Aprendiste Cloud Step", "Sobre la marcha"),
        ("Día 13", "Gentle Release: una nueva forma de usar time stop", "Por tu cuenta"),
        ("Día 12", "Falling Leaf Palm: Practicada", "Sobre la marcha"),
        ("Día 9", "Alcanzaste Foundation Establishment", ""),
        ("Día 6", "Swordsmanship: Soltura", "Frente a un rival"),
        ("Día 3", "Aprendiste Falling Leaf Palm", "Con un maestro"),
    ]
    assert [(g.when, g.text, g.how) for g in sheet_of(state, Language.CA).grew] == [
        ("Dia 14", "Vas aprendre Cloud Step", "Sobre la marxa"),
        ("Dia 13", "Gentle Release: una nova manera de fer servir time stop", "Pel teu compte"),
        ("Dia 12", "Falling Leaf Palm: Practicada", "Sobre la marxa"),
        ("Dia 9", "Vas assolir Foundation Establishment", ""),
        ("Dia 6", "Swordsmanship: Soltesa", "Davant d'un rival"),
        ("Dia 3", "Vas aprendre Falling Leaf Palm", "Amb un mestre"),
    ]


def test_how_they_grew_stops_at_the_latest_gains_and_is_empty_for_none():
    state = cultivation_world()
    assert sheet_of(state).grew == []

    state.player.sheet.growth = [
        Gain(what=f"Form {n}", change="learned", source="watching", reason="", world_s=n * DAY)
        for n in range(GREW_LIMIT + 5)
    ]
    grew = sheet_of(state).grew
    assert len(grew) == GREW_LIMIT
    assert (grew[0].text, grew[0].how) == (f"Learned Form {GREW_LIMIT + 4}", "By watching")
    assert grew[-1].text == "Learned Form 5"


def test_the_path_shows_the_rungs_above_as_far_as_the_story_told_them():
    # G18, C6: heard of once a scene named it, known once the story confirmed it, and room
    # left open for the rungs nobody has named. Never what a rung is or what it takes.
    state = cultivation_world()
    realms = state.bible.ladders[0]
    realms.rungs[1].description = "The qi settles into a foundation."
    realms.rungs[1].needs = ["a Foundation Pill"]
    state.player.sheet.rungs_heard = [
        RungHeard(ladder_id="realms", rung=1, heard_s=2 * DAY, known_s=5 * DAY, known_from="zhao"),
        RungHeard(ladder_id="realms", rung=3, heard_s=13 * DAY),
    ]
    state.facts["f-pill"] = Fact(
        id="f-pill",
        text="Master Wen reached Foundation Establishment with a pill and nine days alone.",
        known_by=["lin"],
    )

    (path,) = sheet_of(state).paths
    assert [r.name for r in path.rungs] == ["Qi Condensation"]
    assert [(r.name, r.known, r.note, r.gap_below) for r in path.above] == [
        ("Foundation Establishment", True, "Confirmed before Zhao Kun, day 6", False),
        ("Nascent Soul", False, "Heard of, day 14", True),
    ]
    assert path.above[0].said == [
        "Master Wen reached Foundation Establishment with a pill and nine days alone."
    ]
    assert path.above[1].said == []
    told = dumped(status_view(state).sheet)
    for hidden in ("Core Formation", "Soul Transformation", "settles into", "Foundation Pill"):
        assert hidden not in told

    (path,) = sheet_of(state, Language.ES).paths
    assert [r.note for r in path.above] == [
        "Lo comprobaste ante Zhao Kun, día 6",
        "Oíste hablar de ello, día 14",
    ]
    (path,) = sheet_of(state, Language.CA).paths
    assert [r.note for r in path.above] == [
        "Ho vas comprovar davant de Zhao Kun, dia 6",
        "En vas sentir a parlar, dia 14",
    ]

    # Someone they can't name confirms it all the same, and is not named (C6).
    state.characters["zhao"].known_by = []
    assert sheet_of(state).paths[0].above[0].note == "Confirmed, day 6"
    # A rung they know only from something they learned says so.
    state.player.sheet.rungs_heard = []
    (rung,) = sheet_of(state).paths[0].above
    assert (rung.name, rung.known, rung.note) == (
        "Foundation Establishment",
        True,
        "From what you have learned",
    )


def test_the_path_starts_with_what_everyone_knows_and_says_who_stands_higher_still():
    # G18, C6: the rungs everyone has heard of show from the start. Someone who stands above
    # every rung they know of widens the path, with no rung named and no distance told.
    state = cultivation_world()
    realms = state.bible.ladders[0]
    realms.known_to_all = 2
    mo = state.characters["elder-mo"]
    mo.met_by, mo.known_by = ["lin"], ["lin"]

    (path,) = sheet_of(state).paths
    assert [(r.name, r.known, r.note, r.gap_below) for r in path.above] == [
        ("Foundation Establishment", False, "Everyone has heard of it", False)
    ]
    assert path.higher == "Elder Mo stands somewhere up here."
    assert "Core Formation" not in dumped(status_view(state).sheet)
    (path,) = sheet_of(state, Language.ES).paths
    assert path.above[0].note == "Todo el mundo ha oído hablar de ello"
    assert path.higher == "Elder Mo está en algún punto de aquí arriba."
    (path,) = sheet_of(state, Language.CA).paths
    assert path.above[0].note == "Tothom n'ha sentit a parlar"
    assert path.higher == "Elder Mo és en algun punt d'aquí dalt."

    # Several are named together, and someone they can't name is only someone (C6).
    state.characters["zhao"].sheet.ladders[0].rung = 3
    assert sheet_of(state).paths[0].higher == "Elder Mo and Zhao Kun stand somewhere up here."
    assert (
        sheet_of(state, Language.ES).paths[0].higher
        == "Elder Mo y Zhao Kun están en algún punto de aquí arriba."
    )
    assert (
        sheet_of(state, Language.CA).paths[0].higher
        == "Elder Mo i Zhao Kun són en algun punt d'aquí dalt."
    )
    state.characters["zhao"].sheet.ladders[0].rung = 1
    mo.known_by = []
    assert sheet_of(state).paths[0].higher == "Someone you have met stands somewhere up here."
    assert sheet_of(state, Language.ES).paths[0].higher == (
        "Alguien con quien te has cruzado está en algún punto de aquí arriba."
    )
    assert sheet_of(state, Language.CA).paths[0].higher == (
        "Algú amb qui t'has creuat és en algun punt d'aquí dalt."
    )

    # Once the story names the elder's rung, it is his, confirmed, and nobody stands higher.
    mo.known_by = ["lin"]
    state.player.sheet.rungs_heard = [
        RungHeard(ladder_id="realms", rung=2, heard_s=DAY, known_s=DAY, known_from="elder-mo")
    ]
    (path,) = sheet_of(state).paths
    assert path.above[-1].note == "Confirmed before Elder Mo, day 2"
    assert path.higher == ""


def test_a_ladder_they_do_not_stand_on_shows_once_they_have_heard_of_it():
    # G18: the world's ladder is a scale beside their own way, as far as they know it.
    state = cultivation_world()
    state.player.sheet.ladders = []
    assert sheet_of(state).paths == []

    state.player.sheet.rungs_heard = [RungHeard(ladder_id="realms", rung=0, heard_s=0)]
    (path,) = sheet_of(state).paths
    assert path.rungs == []
    assert [(r.name, r.known, r.gap_below) for r in path.above] == [
        ("Qi Condensation", False, False)
    ]
    # Zhao, whom they have met, stands above the one rung they have heard of.
    assert path.higher == "Zhao Kun stands somewhere up here."


def test_the_sheet_lists_what_they_hold_with_what_they_carry_first():
    # C10, G13: the purse, then each belonging with its kind, what is on them before what is
    # kept elsewhere.
    from engine.state import Item, ItemKind

    state = grounded_world()
    items = state.player.sheet.resources.items
    items.append(Item(id="bullets", name="bullets", kind=ItemKind.CONSUMABLE, quantity=12))
    items.append(Item(id="spent", name="a spent match", quantity=0))
    items.append(Item(id="note", name="a folded note", description="In his father's hand."))

    sheet = sheet_of(state)

    assert sheet.money_label == "200,000 lire"
    assert [(i.name, i.kind_label, i.quantity, i.carried) for i in sheet.items] == [
        ("Bullets", "Consumable", 12, True),
        ("Flick knife", "Weapon", 1, True),
        ("A folded note", "", 1, True),
        ("Beretta pistol", "Weapon", 1, True),
        ("Alfa Romeo Giulia", "Vehicle", 1, False),
    ]
    assert sheet.items[2].description == "In his father's hand."
    assert sheet_of(state, ES).money_label == "200.000 lire"
    assert [i.kind_label for i in sheet_of(state, ES).items] == [
        "Consumible",
        "Arma",
        "",
        "Arma",
        "Vehículo",
    ]
    assert [i.kind_label for i in sheet_of(state, CA).items][-1] == "Vehicle"
    # An empty purse in a currency is still a purse: the story reads it, and so does the player.
    state.player.sheet.resources.money = 0
    assert sheet_of(state).money_label == "0 lire"


def test_the_sheet_says_when_a_power_is_ready_again():
    # W10a, G13: a power on its cooldown, on the character's own clock.
    state = cultivation_world()
    state.world_s = 2 * DAY
    lin = state.player
    lin.personal_offset_s = 10
    lin.sheet.powers[0].ready_at_personal_s = state.world_s + 10 + 3 * HOUR

    assert [(p.ready, p.ready_label) for p in sheet_of(state).powers] == [
        (False, "Ready in 3 hours")
    ]
    assert sheet_of(state, ES).powers[0].ready_label == "Disponible en 3 horas"
    assert sheet_of(state, CA).powers[0].ready_label == "Disponible d'aquí a 3 hores"
    # A power the world charges nothing for says no cost (G13).
    lin.sheet.powers[0].costs = []
    assert sheet_of(state).powers[0].cost == ""


def test_the_sheet_shows_each_technique_with_its_dice_and_its_count():
    # A3, A4: the dice a move throws by its mastery, and the uses counted toward the next at
    # their own pace.
    state = cultivation_world()
    blade = Technique(
        id="blade",
        name="aura blade",
        style="Azure Cloud style",
        effect="A blade of qi along the edge of the hand.",
        cost="a little qi",
        learned_from="zhao",
        mastery=Mastery.LEARNING,
        uses=2,
    )
    state.player.sheet.techniques.append(blade)

    (technique,) = sheet_of(state).techniques
    assert (technique.name, technique.mastery_label) == ("Aura blade", "Learning")
    assert (technique.dice, technique.uses, technique.need) == (1, 2, 6)
    assert (technique.style, technique.cost) == ("Azure Cloud style", "a little qi")
    assert technique.effect.startswith("A blade of qi")
    assert sheet_of(state, ES).techniques[0].mastery_label == "Aprendiendo"
    assert sheet_of(state, CA).techniques[0].mastery_label == "Aprenent"

    # Where they have it from, as far as the record names it: someone they know, or themselves.
    zhao = state.characters["zhao"].name
    assert technique.source_label == f"Learned from {zhao}"
    assert sheet_of(state, ES).techniques[0].source_label == f"Aprendida de {zhao}"
    assert sheet_of(state, CA).techniques[0].source_label == f"Apresa de {zhao}"
    state.characters["zhao"].name = "Aina"
    assert sheet_of(state, CA).techniques[0].source_label == "Apresa d'Aina"
    # Someone the world names by what they are takes the article in, as both languages do.
    state.characters["zhao"].name = "el viejo herrero"
    assert sheet_of(state, ES).techniques[0].source_label == "Aprendida del viejo herrero"
    state.characters["zhao"].name = "el vell ferrer"
    assert sheet_of(state, CA).techniques[0].source_label == "Apresa del vell ferrer"
    state.characters["zhao"].known_by.remove(state.player_id)
    assert sheet_of(state).techniques[0].source_label == ""  # C6: nobody they know
    blade.learned_from = "their own"
    assert sheet_of(state).techniques[0].source_label == "Your own"
    assert sheet_of(state, ES).techniques[0].source_label == "Creación tuya"
    assert sheet_of(state, CA).techniques[0].source_label == "Creació teva"
    blade.learned_from = "master"  # a kind of teacher, with nobody named
    assert sheet_of(state).techniques[0].source_label == ""

    # Use alone takes a move no further than second nature, so there is nothing left to count.
    blade.mastery, blade.uses = Mastery.SECOND_NATURE, 40
    (technique,) = sheet_of(state).techniques
    assert (technique.mastery_label, technique.dice, technique.need) == ("Second nature", 4, None)
    blade.mastery = Mastery.OWN
    assert sheet_of(state).techniques[0].dice == 5

    # A gift for learning takes a quarter of the uses (A4).
    state.player.sheet.traits.append(Trait(name="Genius", kind=TraitKind.GIFT))
    blade.mastery, blade.uses = Mastery.SKILLED, 1
    assert sheet_of(state).techniques[0].need == 8


def test_the_sheet_tells_wounds_passing_states_and_a_child_on_the_way():
    # G13, N6: how they are, each part on its own, with when a state passes on their own clock.
    from engine.state import Health, PassingState, Pregnancy, Wound

    state = cultivation_world()
    lin = state.player
    lin.personal_offset_s = 100
    condition = lin.sheet.condition
    condition.health = Health.WOUNDED
    condition.wounds = [Wound(text="a cut across the ribs"), Wound(text="a lost eye", lasting=True)]
    condition.states = [
        PassingState(name="drunk", effect="Slower to react.", until_personal_s=100 + 2 * HOUR),
        PassingState(name="grieving"),
        PassingState(name="winded", until_personal_s=50),  # over, and not yet cleared
    ]
    lin.expecting = Pregnancy(conceived_s=0, due_s=30 * DAY)

    told = sheet_of(state).condition

    assert (told.health.value, told.health_label) == ("wounded", "Wounded")
    assert [(w.text, w.lasting) for w in told.wounds] == [
        ("A cut across the ribs", False),
        ("A lost eye", True),
    ]
    assert [(s.name, s.effect, s.ends_label) for s in told.states] == [
        ("Drunk", "Slower to react.", "Passes in 2 hours"),
        ("Grieving", "", None),
        ("Winded", "", None),
    ]
    assert told.expecting_label == "Expecting a child, due in 4 weeks"
    spanish = sheet_of(state, ES).condition
    assert spanish.health_label == "Con heridas"
    assert spanish.states[0].ends_label == "Se pasa en 2 horas"
    assert sheet_of(state, CA).condition.states[0].ends_label == "Passa d'aquí a 2 hores"


def test_the_sheet_shows_each_talent_with_its_pace_and_what_was_ruled():
    # A4: the talents as the engine reads them, and after them every thing ruled on, in the
    # same words the plain lines use.
    state = _talented()

    sheet = sheet_of(state)

    assert [(t.name, t.strength_label, t.pace_label, t.covers) for t in sheet.talents] == [
        ("The sword", "One of a kind", "Eight times as fast", "anything fought with a blade"),
        ("Architecture", "Genius", "Four times as fast", ""),
        ("Quick hands", "A knack", "Twice as fast", "sleight"),
        ("Words", "Weakness", "At half the pace", "persuading"),
    ]
    assert sheet.talent_notes == lines_of(state)[-3:]
    assert len(sheet.talent_notes) == 3 and sheet.talent_notes[0].startswith("Aura blade: grows")
    assert [(t.strength_label, t.pace_label) for t in sheet_of(state, ES).talents] == [
        ("Talento único", "Ocho veces más rápido"),
        ("Genio", "Cuatro veces más rápido"),
        ("Facilidad", "El doble de rápido"),
        ("Punto débil", "A la mitad de ritmo"),
    ]
    assert [(t.strength_label, t.pace_label) for t in sheet_of(state, CA).talents][::3] == [
        ("Talent únic", "Vuit vegades més ràpid"),
        ("Punt feble", "A la meitat de ritme"),
    ]
    # A sheet saved before talent was a record shows none, as its lines show none.
    old = cultivation_world()
    old.player.sheet.traits.append(Trait(name="Genius", kind=TraitKind.GIFT))
    assert sheet_of(old).talents == [] and sheet_of(old).talent_notes == []


def test_the_sheet_words_skills_and_traits_in_spanish_and_catalan():
    # S10: the words the engine adds come in the story's language, and the world's own stay.
    from engine.state import Skill, SkillLevel

    state = grounded_world()
    state.player.sheet.skills.append(Skill(name="cooking", level=SkillLevel.UNTRAINED))
    state.player.sheet.skills.append(Skill(name="lying", level=SkillLevel.MASTER))

    def skills(language):
        return [(s.name, s.level_label, s.dice) for s in sheet_of(state, language).skills]

    assert skills(Language.EN) == [
        ("Lying", "Master", 5),
        ("Pistol", "Skilled", 3),
        ("Knife work", "Skilled", 3),
        ("Driving", "Fair", 2),
        ("Cooking", "Untrained", 1),
    ]
    assert [label for _, label, _ in skills(ES)] == [
        "Maestría",
        "Destreza",
        "Destreza",
        "Soltura",
        "Sin formación",
    ]
    assert [label for _, label, _ in skills(CA)][::4] == ["Mestratge", "Sense formació"]
    assert [t.kind_label for t in sheet_of(state, ES).traits] == ["Defecto", "Don"]
    assert [t.kind_label for t in sheet_of(state, CA).traits] == ["Defecte", "Do"]
    assert sheet_of(state, ES).about == ["The late boss's son, the Esposito family", "24 años"]
    assert sheet_of(state, CA).about[-1] == "24 anys"


def test_who_they_are_names_only_a_faction_they_know():
    # C6: a place in a faction the character hasn't learned the name of is its rank alone.
    state = cultivation_world()
    lin = state.player
    lin.sheet.resources.title = "Heir of the fallen Lin clan"

    assert sheet_of(state).about == [
        "Outer disciple, the outer court",
        "Heir of the fallen Lin clan",
        "16 years old",
    ]
    state.factions["outer-court"].known_by.remove(lin.id)
    assert sheet_of(state).about[0] == "Outer disciple"
    # With no place in any faction, their standing in the world's own ranks, said once.
    lin.memberships = []
    lin.sheet.resources.title = "outer disciple"
    lin.age = None
    assert sheet_of(state).about == ["Outer disciple"]


def test_hidden_truth_never_reaches_the_sheet():
    # C6: the sheet is the character's own, and still nothing of the world's hidden side.
    state = grounded_world()
    hidden = [s for c in state.characters.values() for s in c.secrets]
    hidden += [m.answer for m in state.bible.mysteries]
    assert hidden
    for world in (state, cultivation_world()):
        text = dumped(status_view(world))
        for secret in hidden:
            assert secret not in text
        for key in ("is_true", "accuracy", "trust", "agenda", "ready_at_personal_s"):
            assert key not in text
