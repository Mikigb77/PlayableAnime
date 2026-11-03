"""W16, E4, F3, F7: where events come from, in order, and the seeded deck with its filters."""

from collections import Counter

import pytest

from engine.context import ContentPrefs, EventFrequency, GoreLevel, Rating
from engine.contracts import EventSource, Theme
from engine.director import rules
from engine.director.deck import CARDS, DECK, CastRole, Tone, draw, playable, story_scale
from engine.director.sources import cast_for, pick_event
from engine.director.themes import allowed_themes, is_adult
from engine.rng import SeededRng
from engine.samples import farm_world, grounded_world
from engine.state import (
    Activity,
    Attitude,
    Character,
    CharacterSheet,
    Disposition,
    EventSize,
    Faction,
    Membership,
    Origin,
    OriginKind,
    Thread,
    ThreadKind,
    ThreadStatus,
)
from tests.engine.director.helpers import ctx

ALL = frozenset(Theme)
SEEDS = [f"seed-{i}" for i in range(60)]


def seeded(label: str) -> SeededRng:
    return SeededRng.for_turn(label, "main", 2)


def test_the_deck_has_one_table_per_size_with_good_things_in_each():
    assert len({card.id for card in DECK}) == len(DECK)
    for size in EventSize:
        table = [card for card in DECK if card.size is size and card.needs_decision]
        assert len(table) >= 5, size
        tones = {card.tone for card in table}
        assert {Tone.GOOD, Tone.TROUBLE} <= tones, size
    for card in DECK:
        if card.needs_decision:
            assert card.consequence, card.id  # ignored, it plays out instead of repeating (W16)
        assert card.window_s > 0
        if Theme.ROMANCE in card.themes:
            assert "adult" in card.brief, card.id  # F3, for the narrator


def test_themes_follow_the_switches_the_rating_and_an_adult_player():
    state = farm_world()
    assert allowed_themes(state, ctx()) == {Theme.ROMANCE, Theme.DARK}  # Teen: no gore
    mature = ctx(rating=Rating.MATURE)
    assert allowed_themes(state, mature) == ALL
    low_gore = ctx(rating=Rating.MATURE, prefs=ContentPrefs(gore=GoreLevel.LOW))
    assert Theme.GORE not in allowed_themes(state, low_gore)
    off = ctx(prefs=ContentPrefs(romance=False, dark_themes=False))
    assert allowed_themes(state, off) == frozenset()

    # F3: a romance event needs an adult age recorded for the player character.
    state.player.age = 16
    assert Theme.ROMANCE not in allowed_themes(state, ctx())
    state.player.age = None
    assert Theme.ROMANCE not in allowed_themes(state, ctx())
    assert not is_adult(17) and is_adult(18) and not is_adult(None)


def test_a_card_is_playable_only_within_the_rating_and_the_switched_on_themes():
    teen, mature = ctx(), ctx(rating=Rating.MATURE)
    assert not playable(CARDS["grisly-find"], teen, ALL)  # Mature only
    assert playable(CARDS["grisly-find"], mature, ALL)
    assert not playable(CARDS["grisly-find"], mature, frozenset({Theme.DARK}))
    assert not playable(CARDS["admirer"], teen, frozenset({Theme.DARK}))
    assert playable(CARDS["windfall"], teen, frozenset())


@pytest.mark.parametrize("prefs", [ContentPrefs(romance=False, dark_themes=False), None])
def test_draws_never_carry_a_theme_that_is_switched_off(prefs):
    state = farm_world()
    context = ctx(prefs=prefs, event_frequency=EventFrequency.DRAMATIC)
    allowed = allowed_themes(state, context)
    for story in SEEDS:
        card = draw(state, context, seeded(story), allowed)
        assert card is not None
        assert set(card.themes) <= allowed
        assert not card.mature_only


def test_the_story_scale_comes_from_the_world_and_bounds_the_draw():
    farm = farm_world()
    assert story_scale(farm) is EventSize.PERSONAL
    # A private life never draws a world event (G9: a farming story gets farm-sized drama).
    sizes = Counter(draw(farm, ctx(), seeded(s), ALL).size for s in SEEDS)
    assert sizes[EventSize.WORLD] == 0 and sizes[EventSize.PERSONAL] > sizes[EventSize.LOCAL]

    farm.characters["tomas"].memberships = [Membership(faction_id="guild", rank="member")]
    assert story_scale(farm) is EventSize.LOCAL
    farm.factions["guild"] = Faction(id="guild", name="the Millers' Guild", threat=4)
    assert story_scale(farm) is EventSize.WORLD
    sizes = Counter(draw(farm, ctx(), seeded(s), ALL).size for s in SEEDS)
    assert sizes[EventSize.WORLD] > 0


def test_a_draw_is_seeded_and_passes_over_recent_cards():
    state = farm_world()
    for story in SEEDS[:20]:
        first = draw(state, ctx(), seeded(story), ALL)
        assert draw(state, ctx(), seeded(story), ALL) == first
        again = draw(state, ctx(), seeded(story), ALL, recent=[first.source_key])
        assert again is not None and again.id != first.id and again.size is first.size


def test_small_good_things_without_a_decision_only_colour_a_time_skip():
    state = farm_world()
    quiet = {draw(state, ctx(), seeded(s), ALL).id for s in SEEDS}
    assert not {c.id for c in DECK if not c.needs_decision} & quiet
    skip = {draw(state, ctx(), seeded(s), ALL, decision_only=False).id for s in SEEDS * 3}
    assert "good-day" in skip


def test_calm_draws_more_good_things_and_dramatic_more_trouble():
    state = farm_world()

    def tones(frequency):
        context = ctx(event_frequency=frequency)
        return Counter(draw(state, context, seeded(s), ALL).tone for s in SEEDS * 4)

    calm, dramatic = tones(EventFrequency.CALM), tones(EventFrequency.DRAMATIC)
    assert calm[Tone.GOOD] > dramatic[Tone.GOOD]
    assert dramatic[Tone.TROUBLE] > calm[Tone.TROUBLE]


def test_the_world_state_comes_before_the_deck_in_w16s_order():
    # A key NPC with plans the player knows: the agenda comes first.
    state = grounded_world()
    pick = pick_event(state, ctx(), seeded("order"), ALL, recent=[])
    assert pick is not None and pick.event.source is EventSource.AGENDA

    # With no plans in the world, a dormant thread comes back.
    for npc in state.npcs():
        npc.agenda = None
    for faction in state.factions.values():
        faction.goal = ""
    state.threads["revenge"].status = ThreadStatus.DORMANT
    state.threads["revenge"].last_active_turn = 0
    pick = pick_event(state, ctx(20), seeded("order"), ALL, recent=[])
    assert pick.event.source is EventSource.THREAD and pick.event.thread_id == "revenge"

    # With no dormant thread either, an emerging character the player hasn't met.
    state.threads["revenge"].status = ThreadStatus.RESOLVED
    state.characters["stranger"] = Character(
        id="stranger",
        name="Gennaro Sarno",
        age=40,
        location_id="bar",
        origin=Origin(kind=OriginKind.EMERGENCE, text="a cousin back from Marseille"),
    )
    pick = pick_event(state, ctx(20), seeded("order"), ALL, recent=[])
    assert pick.event.source is EventSource.EMERGENCE
    assert "Gennaro" not in pick.event.title  # the title never names someone unmet (C6)

    # Only then a fresh draw from the deck.
    state.characters["stranger"].met_by = [state.player_id]
    pick = pick_event(state, ctx(20), seeded("order"), ALL, recent=[])
    assert pick.event.source is EventSource.DECK and pick.event.card_id in CARDS


def test_a_source_used_recently_waits_its_turn():
    state = grounded_world()
    first = pick_event(state, ctx(), seeded("cooldown"), ALL, recent=[])
    second = pick_event(state, ctx(), seeded("cooldown"), ALL, recent=[first.key])
    assert second is not None and second.key != first.key


def test_a_dormant_thread_returns_only_after_it_has_been_quiet_a_while():
    state = farm_world()
    state.threads["feud"] = Thread(
        id="feud",
        title="Bram's fence",
        kind=ThreadKind.RIVALRY,
        involved_ids=["tomas", "bram"],
        origin=Origin(kind=OriginKind.EVENT),
        status=ThreadStatus.DORMANT,
        last_active_turn=10,
        known_by=["tomas"],
    )
    soon = ctx(10 + rules.RETURN_AFTER_TURNS - 1)
    later = ctx(10 + rules.RETURN_AFTER_TURNS)
    assert pick_event(state, soon, seeded("return"), ALL, recent=[]).event.source is not (
        EventSource.THREAD
    )
    pick = pick_event(state, later, seeded("return"), ALL, recent=[])
    assert pick.event.source is EventSource.THREAD and pick.event.cast_ids == ["bram"]


def test_a_faction_the_player_never_heard_of_is_never_named_in_the_title():
    state = farm_world()
    state.factions["ring"] = Faction(id="ring", name="the Silent Ring", goal="Own the valley")
    state.characters["tomas"].memberships = []
    from engine.state import Clock

    state.clocks["ring"] = Clock(
        id="ring", name="The Ring's plan", steps=["a", "b"], owner_id="ring"
    )
    state.factions["ring"].threat = 1  # it has an eye on the player character
    pick = pick_event(state, ctx(), seeded("hidden"), ALL, recent=[])
    assert pick.event.source is EventSource.AGENDA
    assert pick.event.title == "Someone takes an interest in you"
    assert "Ring" not in pick.thread_title


def minor_nearby(state):
    state.characters["kid"] = Character(
        id="kid",
        name="Hanne",
        age=15,
        location_id="farm",
        met_by=["tomas"],
        sheet=CharacterSheet(
            disposition=Disposition(attitudes={"tomas": Attitude(affinity=95, trust=90)})
        ),
    )
    return state


def test_a_romance_event_only_casts_adults():
    state = minor_nearby(farm_world())
    romance = {tuple(cast_for(state, CastRole.CLOSE, seeded(s), adults_only=True)) for s in SEEDS}
    anyone = {tuple(cast_for(state, CastRole.CLOSE, seeded(s), adults_only=False)) for s in SEEDS}
    assert ("kid",) not in romance and ("ilse",) in romance
    assert ("kid",) in anyone  # a sick child can be the minor; a romance never can (F3)


def test_cast_reuses_only_people_the_player_knows_who_are_nearby_and_active():
    state = farm_world()
    state.characters["ilse"].activity = Activity.DORMANT
    state.characters["bram"].location_id = None  # gone to the city, nobody knows where
    assert cast_for(state, CastRole.CLOSE, seeded("cast"), adults_only=False) == []
    state.characters["bram"].location_id = "village"  # forty minutes away on foot
    assert cast_for(state, CastRole.ANY, seeded("cast"), adults_only=False) == ["bram"]
    state.characters["bram"].met_by = []
    assert cast_for(state, CastRole.ANY, seeded("cast"), adults_only=False) == []
    assert cast_for(state, CastRole.NONE, seeded("cast"), adults_only=False) == []


def test_a_minor_player_character_never_draws_a_romance_event():
    state = farm_world()
    state.player.age = 15
    allowed = allowed_themes(state, ctx(event_frequency=EventFrequency.DRAMATIC))
    for story in SEEDS:
        pick = pick_event(state, ctx(), seeded(story), allowed, recent=[])
        assert Theme.ROMANCE not in pick.event.themes


def test_a_returning_romance_thread_casts_only_adults():
    """F3: the dormant source checks ages too, not only the deck."""
    state = minor_nearby(farm_world())
    state.threads["crush"] = Thread(
        id="crush",
        title="A crush",
        kind=ThreadKind.ROMANCE,
        involved_ids=["tomas", "kid", "ilse"],
        origin=Origin(kind=OriginKind.EVENT),
        status=ThreadStatus.DORMANT,
        known_by=["tomas"],
    )
    pick = pick_event(state, ctx(30), seeded("crush"), ALL, recent=[])
    assert pick.event.source is EventSource.THREAD and Theme.ROMANCE in pick.event.themes
    assert pick.event.cast_ids == ["ilse"]
