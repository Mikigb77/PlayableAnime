"""C6: the Memory and status screens show only what the player character knows."""

import json

import pytest

from engine.apply import DeltaSource, apply_delta
from engine.base import DAY, HOUR
from engine.context import Language, TurnContext
from engine.contracts import CharacterChange, PlaceChange, StateDelta
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    CharacterStatus,
    DeathCertainty,
    Deed,
    Fact,
    FactionStatus,
    Lead,
    LeadStatus,
    Mastery,
    PlaceStatus,
    Reputation,
    Rumor,
    StatusChange,
    Technique,
    Trait,
    TraitKind,
    Visibility,
    WorldState,
)
from engine.visibility import (
    attitude_label,
    memory_view,
    speech_vocabulary,
    standing_label,
    status_view,
)


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
    assert carmine.attitude_label == "Friendly"


def test_people_are_the_ones_the_player_knows():
    state = grounded_world()
    names = [p.name for p in memory_view(state).people]
    state.characters["bartender"].known_by.append("luca")

    assert names == ["Carmine Russo"]
    assert [p.name for p in memory_view(state).people] == ["Carmine Russo", "Gennaro"]
    # Known but never met: no attitude to read.
    assert memory_view(state).people[1].attitude_label is None


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

    assert memory_view(back).people[0].status_label == "Missing"


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
    state.player.sheet.ladders[0].stage = "early stage"

    (path,) = sheet_of(state).paths

    assert path.name == "Cultivation realms"
    assert [(r.name, r.stage, r.description) for r in path.rungs] == [
        ("Qi Condensation", "", ""),
        ("Foundation Establishment", "", ""),
        ("Core Formation", "early stage", "A core of qi takes shape."),
    ]
    assert "Nascent Soul" not in dumped(status_view(state).sheet)
    # A ladder the world no longer has, or a rung past its end, shows no path.
    state.player.sheet.ladders[0].rung = 9
    assert sheet_of(state).paths == []
    assert sheet_of(grounded_world()).paths == []


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
