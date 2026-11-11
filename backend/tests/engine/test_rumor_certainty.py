"""C6, W2, W13: what the player character lived is no unconfirmed rumor; the same words show once.

Miki, 2026-11-08: the Memory screen listed "Zephyr attacked Leo in El Bosque de los Susurros" four
times, each marked unconfirmed, though Leo had lived through that fight.
"""

from engine import pipeline
from engine.base import HOUR, MINUTE
from engine.context import Language, StorySettings, TurnContext
from engine.contracts import OutcomeClass, ProposedDeed, Resolution, StepResolution
from engine.invariants import check_transition
from engine.rng import SeededRng
from engine.samples import grounded_world
from engine.state import Deed, Rumor, StepResult, Visibility, WorldState
from engine.state.records import GARBLED_LEAD
from engine.state.sheet import Attitude
from engine.visibility import memory_view, status_view
from engine.world import hearsay
from engine.world.clocks import on_clock_end
from engine.world.rumors import Certainty, believes, certainty, start_rumor
from engine.world.scheduling import Kind, World, schedule


def ctx(turn: int = 2) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings())


def rng(turn: int = 2) -> SeededRng:
    return SeededRng.for_turn("s1", "main", turn)


def at(state: WorldState) -> World:
    return World(state=state, ctx=ctx(), at_s=state.world_s, rng=rng())


def blows(
    state: WorldState, count: int, *, actor_id: str = "carmine", severity: int = 2
) -> WorldState:
    """A fight of several blows, one deed each, as resolve records them."""
    steps = [
        StepResolution(
            index=i,
            text="a blow",
            outcome_class=OutcomeClass.CERTAIN,
            reason="",
            result=StepResult.SUCCESS,
            duration_s=10,
            deeds=[
                ProposedDeed(
                    actor_id=actor_id,
                    kind="assault",
                    text="Carmine hits Luca",
                    victim_ids=["luca"],
                    severity=severity,
                )
            ],
        )
        for i in range(count)
    ]
    played = pipeline.play_out(state, Resolution(actor_id=actor_id, steps=steps), ctx(), rng())
    assert check_transition(state, played.state) == []
    return played.state


def player_deed(state: WorldState, **kwargs) -> Deed:
    deed = Deed(
        id=kwargs.pop("id", "deed-1"),
        actor_id=kwargs.pop("actor_id", "luca"),
        kind="kill",
        text="Killed the bartender",
        turn=1,
        world_s=0,
        place_id="bar",
        victim_ids=["bartender"],
        severity=4,
        **kwargs,
    )
    state.deeds[deed.id] = deed
    return deed


def told(state: WorldState) -> WorldState:
    """A scene tells the player character what the place is saying, one piece at a time."""
    for rumor in hearsay.talk_of(state, state.player_id, state.player.location_id, state.world_s):
        assert hearsay.hear(at(state), state.player_id, rumor.id)
    return state


def test_a_fight_the_player_lived_is_a_deed_and_no_rumor_until_a_scene_tells_the_talk():
    state = blows(grounded_world(), 4)

    deeds = [d for d in state.deeds.values() if d.actor_id == "carmine"]
    assert len(deeds) == 4 and all("luca" in d.known_by for d in deeds)
    view = memory_view(state)

    # What they lived is in their memory as a deed. Nobody told them any talk of it.
    assert view.rumors == []
    assert not any("luca" in r.heard_at for r in state.rumors.values())
    (deed,) = [d for d in view.deeds if d.text.startswith("Carmine")]
    assert deed.text == "Carmine Russo attacked you at Carmine's bar."
    assert deed.known_label == "You saw it"

    # Once a scene tells what the bar says of it, it is one rumor, and they know it is so.
    (rumor,) = memory_view(told(state)).rumors
    assert rumor.text == "Carmine Russo attacked Luca Esposito at Carmine's bar."
    assert rumor.certainty is Certainty.CONFIRMED
    assert rumor.unconfirmed is False


def test_status_lists_a_moment_once_however_many_blows_it_took():
    state = blows(grounded_world(), 4, severity=3)

    texts = [s.text for s in status_view(state).since]

    assert texts.count("Carmine Russo attacked you at Carmine's bar.") == 1


def test_the_same_words_heard_twice_show_once_by_when_last_heard():
    state = grounded_world()
    state.rumors["r1"] = Rumor(
        id="r1", text="The Calabrians did it.", is_true=False, heard_at={"luca": 0}
    )
    state.rumors["r2"] = Rumor(
        id="r2", text="the calabrians did it", is_true=False, heard_at={"luca": HOUR}
    )
    state.rumors["r3"] = Rumor(
        id="r3", text="Carmine is buying the crews.", is_true=True, heard_at={"luca": 30 * MINUTE}
    )
    state.world_s = 2 * HOUR

    view = memory_view(state)

    assert [(r.id, r.text, r.heard_label, r.certainty) for r in view.rumors] == [
        ("r3", "Carmine is buying the crews.", "Heard an hour ago", Certainty.UNCONFIRMED),
        ("r2", "the calabrians did it", "Heard an hour ago", Certainty.UNCONFIRMED),
    ]


def test_a_rumor_the_player_only_heard_stays_unconfirmed_whoever_knows_the_truth():
    state = grounded_world()
    deed = player_deed(state, actor_id="carmine", known_by=["carmine", "bartender"])
    state.rumors["r1"] = Rumor(
        id="r1",
        text="Carmine killed the bartender.",
        is_true=True,
        deed_id=deed.id,
        about_ids=["carmine", "bartender"],
        heard_at={"luca": 0},
    )

    assert certainty(state, "luca", state.rumors["r1"]) is Certainty.UNCONFIRMED
    (rumor,) = memory_view(state).rumors
    assert (rumor.certainty, rumor.unconfirmed) == (Certainty.UNCONFIRMED, True)

    # Word from someone close settles it, as the deed's own knowledge does (W4).
    deed.known_by.append("luca")
    assert memory_view(state).rumors[0].certainty is Certainty.CONFIRMED


def test_a_wrong_rumor_about_the_players_own_deed_is_false_to_them():
    state = grounded_world()
    deed = player_deed(state, visibility=Visibility.SECRET, known_by=["luca"])
    state.rumors["r1"] = Rumor(
        id="r1",
        text="The bartender was found dead at Carmine's bar: an accident, people say.",
        is_true=False,
        deed_id=deed.id,
        about_ids=["bartender"],
        heard_at={"luca": 0, "carmine": 0},
    )

    (rumor,) = memory_view(state).rumors
    assert (rumor.certainty, rumor.unconfirmed) == (Certainty.FALSE, False)
    # Someone who only heard it can't tell.
    assert certainty(state, "carmine", state.rumors["r1"]) is Certainty.UNCONFIRMED


def test_whoever_saw_it_believes_a_rumor_only_if_it_is_so():
    state = grounded_world()
    deed = player_deed(state, witness_ids=["carmine"], known_by=["luca", "carmine"])
    wrong = Rumor(id="r1", text="An accident.", is_true=False, deed_id=deed.id, accuracy=90)
    right = Rumor(
        id="r2",
        text="Luca killed the bartender.",
        is_true=True,
        deed_id=deed.id,
        about_ids=["luca", "bartender"],
        accuracy=10,
    )
    # Carmine is devoted to Luca: hearsay against Luca he would wave away, but he saw it.
    state.characters["carmine"].sheet.disposition.attitudes["luca"] = Attitude(affinity=90)

    assert not believes(state, "carmine", wrong, wrong.accuracy)
    assert believes(state, "carmine", right, right.accuracy)
    # Gennaro, the bartender, wasn't there: only the telling's accuracy decides for him.
    assert believes(state, "bartender", wrong, wrong.accuracy)
    assert not believes(state, "bartender", right, right.accuracy)


def test_a_clocks_end_is_confirmed_for_those_there_and_talk_elsewhere():
    state = grounded_world()
    w = at(state)
    start_rumor(
        w,
        text="The council: Carmine is named boss.",
        is_true=True,
        place_id="bar",
        hops=2,
        heard_by=["luca", "carmine"],
        seen_by=["luca", "carmine"],
    )
    elsewhere = start_rumor(
        w,
        text="The police chief resigns.",
        is_true=True,
        place_id="questura",
        hops=2,
        heard_by=["luca"],
    )

    by_text = {r.text: r.certainty for r in memory_view(state).rumors}
    assert by_text == {
        "The council: Carmine is named boss.": Certainty.CONFIRMED,
        "The police chief resigns.": Certainty.UNCONFIRMED,
    }
    assert elsewhere.seen_by == []


def test_a_clock_that_ends_where_the_player_is_is_seen_not_heard():
    for place_id, sure in (("bar", Certainty.CONFIRMED), ("questura", None)):
        state = grounded_world()
        state.characters["bartender"].location_id = "questura"
        w = at(state)
        end = schedule(
            w,
            Kind.CLOCK_END,
            w.at_s,
            title="The end",
            place_id=place_id,
            payload={"clock_id": "council"},
        )
        on_clock_end(w, end)

        (rumor,) = state.rumors.values()
        # Seen there by whoever was there; Luca, in the bar, hears it only if it ends there.
        assert rumor.seen_by == rumor.heard_by and rumor.heard_by
        view = {r.text: r.certainty for r in memory_view(state).rumors}
        assert view.get(rumor.text) is sure


def test_a_retelling_of_a_deed_the_player_saw_is_confirmed_not_false():
    state = grounded_world()
    deed = player_deed(
        state, actor_id="carmine", witness_ids=["luca"], known_by=["carmine", "luca"]
    )
    garbled = Rumor(
        id="r1",
        text="A garbled account goes round: someone killed the bartender at Carmine's bar.",
        is_true=True,
        deed_id=deed.id,
        about_ids=["bartender"],
        heard_at={"luca": 0},
    )
    state.rumors[garbled.id] = garbled

    assert memory_view(state).rumors[0].certainty is Certainty.CONFIRMED


def test_the_wire_carries_certainty_whatever_the_story_language():
    state = told(blows(grounded_world(), 2))

    dumped = memory_view(state, Language.ES).model_dump(mode="json")

    assert dumped["rumors"][0]["certainty"] == "confirmed"
    assert dumped["rumors"][0]["unconfirmed"] is False
    assert dumped["rumors"][0]["heard_label"].startswith("Lo oíste")


def test_the_same_words_known_and_only_heard_stay_apart():
    state = grounded_world()
    seen = player_deed(state, id="deed-1", actor_id="carmine", known_by=["carmine", "luca"])
    unseen = player_deed(state, id="deed-2", actor_id="carmine", known_by=["carmine"])
    for i, deed in enumerate((seen, unseen)):
        state.rumors[f"r{i}"] = Rumor(
            id=f"r{i}",
            text="Carmine killed the bartender.",
            is_true=True,
            deed_id=deed.id,
            about_ids=["carmine", "bartender"],
            heard_at={"luca": i * HOUR},
        )
    state.world_s = 2 * HOUR

    view = memory_view(state)

    assert [(r.id, r.certainty, r.heard_label) for r in view.rumors] == [
        ("r0", Certainty.CONFIRMED, "Heard 2 hours ago"),
        ("r1", Certainty.UNCONFIRMED, "Heard an hour ago"),
    ]


def test_a_garbled_retelling_saved_before_it_kept_its_truth_loads_true():
    saved = {
        "id": "r1",
        "text": f"{GARBLED_LEAD}someone attacked Luca Esposito at Carmine's bar.",
        "is_true": False,
        "deed_id": "deed-1",
    }

    assert Rumor.model_validate(saved).is_true
    # A wrong rumor that only looks alike stays wrong.
    assert not Rumor.model_validate(saved | {"text": "An accident, people say."}).is_true


def test_a_clock_that_ends_with_the_player_is_seen_wherever_they_stand_in_it():
    state = grounded_world()
    w = at(state)
    # The council ends in Naples as a whole; Luca is in the bar inside it.
    end = schedule(
        w,
        Kind.CLOCK_END,
        w.at_s,
        title="The end",
        place_id="naples",
        payload={"clock_id": "council"},
    )
    on_clock_end(w, end)

    (rumor,) = state.rumors.values()
    assert "luca" in rumor.seen_by and "luca" in rumor.heard_at
    assert memory_view(state).rumors[0].certainty is Certainty.CONFIRMED
