"""W16, S10: the director's titles in the story's language, and the threads and leads the
player keeps of an event."""

import pytest

from engine.context import EventFrequency, Language
from engine.contracts import EventSource
from engine.director import titles
from engine.director.deck import DECK, ROAD
from engine.director.due import world_event
from engine.director.sources import pick_event
from engine.rng import SeededRng
from engine.samples import farm_world, grounded_world
from engine.state import (
    Character,
    Clock,
    Faction,
    Origin,
    OriginKind,
    PendingEvent,
    ThreadStatus,
)
from tests.engine.director.helpers import ctx, farming, play_turn
from tests.engine.director.test_sources import ALL

EN, ES, CA = Language.EN, Language.ES, Language.CA


def test_every_card_has_its_title_in_spanish_and_in_catalan():
    for card in (*DECK, *ROAD):
        assert titles.written(card.title), card.id
        for language in (ES, CA):
            said = titles.said(card.title, language)
            assert said and said != card.title, (card.id, language)
        assert titles.said(card.title, EN) == card.title


def test_no_title_is_left_without_its_other_languages():
    for english, said in titles._FIXED.items():
        assert len(said) == 2 and all(said), english
        assert english not in said, english


@pytest.mark.parametrize(
    ("english", "spanish", "catalan"),
    [
        ("Elder Mo seeks you out", "Elder Mo te busca", "Elder Mo et busca"),
        ("Elder Mo's plans", "Los planes de Elder Mo", "Els plans d'Elder Mo"),
        ("el viejo Hu's plans", "Los planes del viejo Hu", "Els plans del viejo Hu"),
        ("Word from the Silent Ring", "Noticias de the Silent Ring", "Notícies de the Silent Ring"),
        ("Los Lobos's designs", "Las intenciones de Los Lobos", "Les intencions de Los Lobos"),
        ("The rise of el Loto Negro", "El ascenso del Loto Negro", "L'ascens del Loto Negro"),
        ("A stranger appears", "Aparece una cara nueva", "Apareix una cara nova"),
        ("Something comes due", "Algo pendiente llega", "Arriba una cosa pendent"),
    ],
)
def test_a_title_built_around_a_name_keeps_the_name(english, spanish, catalan):
    assert titles.written(english)
    assert titles.said(english, ES) == spanish
    assert titles.said(english, CA) == catalan
    assert titles.said(english, EN) == english


def test_a_title_the_director_didnt_write_stands_as_it_is():
    """A thread's own title is in the story's language already, and the turn's wording says an
    event the living world titled."""
    for title in ("La valla de Bram", "The bailiff comes", "Zhao Kun comes to arrest Lin Feng"):
        assert not titles.written(title)
        assert titles.said(title, ES) == title


def seeded(label: str) -> SeededRng:
    return SeededRng.for_turn(label, "main", 2)


def test_every_source_writes_titles_the_book_knows():
    """W16's sources in order: an agenda, a returning thread the player doesn't know of, someone
    new, a new power, and the deck."""
    picks = []
    state = grounded_world()
    picks.append(pick_event(state, ctx(), seeded("order"), ALL, recent=[]))  # a key NPC's plans
    assert picks[-1].event.source is EventSource.AGENDA

    for npc in state.npcs():
        npc.agenda = None
    for faction in state.factions.values():
        faction.goal = ""
    state.threads["revenge"].status = ThreadStatus.DORMANT
    state.threads["revenge"].last_active_turn = 0
    state.threads["revenge"].known_by = []
    picks.append(pick_event(state, ctx(20), seeded("order"), ALL, recent=[]))
    assert picks[-1].event.source is EventSource.THREAD

    state.threads["revenge"].status = ThreadStatus.RESOLVED
    emerged = Origin(kind=OriginKind.EMERGENCE, text="a cousin back from Marseille")
    state.characters["stranger"] = Character(
        id="stranger", name="Gennaro Sarno", age=40, location_id="bar", origin=emerged
    )
    picks.append(pick_event(state, ctx(20), seeded("order"), ALL, recent=[]))
    assert picks[-1].event.source is EventSource.EMERGENCE

    state.characters["stranger"].met_by = [state.player_id]
    state.factions["new"] = Faction(id="new", name="the Quay Boys", origin=emerged)
    picks.append(pick_event(state, ctx(20), seeded("order"), ALL, recent=[]))
    assert picks[-1].event.source is EventSource.EMERGENCE

    state.factions["new"].known_by = [state.player_id]
    picks.append(pick_event(state, ctx(20), seeded("order"), ALL, recent=[]))
    assert picks[-1].event.source is EventSource.DECK

    # A faction's move, by one the player knows and by one they never heard of.
    farm = farm_world()
    farm.factions["ring"] = Faction(id="ring", name="the Silent Ring", goal="Own the valley")
    farm.factions["ring"].threat = 1
    farm.characters["tomas"].memberships = []
    farm.clocks["ring"] = Clock(id="ring", name="The plan", steps=["a", "b"], owner_id="ring")
    picks.append(pick_event(farm, ctx(), seeded("hidden"), ALL, recent=[]))
    farm.factions["ring"].known_by = ["tomas"]
    picks.append(pick_event(farm, ctx(), seeded("hidden"), ALL, recent=[]))
    assert picks[-1].event.title == "Word from the Silent Ring"

    for pick in picks:
        for title in filter(None, (pick.event.title, pick.thread_title)):
            assert titles.written(title), title
    assert titles.written(world_event(PendingEvent(id="e", kind="x", title="", due_s=0)).title)


def quiet_spanish_life(turns: int = 30):
    state = farm_world()
    plans = []
    for turn in range(1, turns + 1):
        played = play_turn(
            state,
            turn,
            farming(),
            story="seed-1",
            event_frequency=EventFrequency.DRAMATIC,
            language=ES,
        )
        state = played.state
        plans.append(played.plan)
    return state, plans


def test_a_spanish_story_keeps_its_threads_and_leads_in_spanish():
    """N1, N2: the event is the director's, in the engine's words for the narrator, and the
    thread and the lead the player keeps of it are titled in the story's language."""
    state, plans = quiet_spanish_life()
    opened = [thread for plan in plans for thread in plan.updates.new_threads]
    leads = [lead for plan in plans for lead in plan.updates.new_leads]
    events = [plan.event for plan in plans if plan.event is not None]

    assert opened and events
    returned = [event for event in events if event.source is EventSource.THREAD]
    assert returned
    for event in events:
        if not titles.written(event.title):
            # A thread of the story's own comes back, or plays out, under the title it keeps.
            assert event.title == state.threads[event.thread_id].title
            assert event.title in {e.title for e in returned}
    for kept in (*(thread.title for thread in opened), *(lead.text for lead in leads)):
        assert not titles.written(kept), kept
    assert opened[0].title == titles.said(events[0].title, ES) != events[0].title
