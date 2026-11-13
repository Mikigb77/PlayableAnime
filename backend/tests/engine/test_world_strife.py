"""W6, W7: the wider world moves over the years. Wars between factions come to a head.

"If you come back after ten years, two rival kingdoms have already fought a battle: maybe one
of them fell and the other is the one reigning, or both fell" (Miki, 2026-11-13), and "if a
month went by, obviously there is no time for such things". Nothing is made to happen, the
facts decide before any throw (A2), the story keeps what is its own, and the player character
knows of it when they live near or once a scene told them (C6).
"""

from collections import Counter

import pytest

from engine import pipeline
from engine.base import DAY, YEAR
from engine.context import Language
from engine.contracts import DirectorPlan, PlannedTalk
from engine.invariants import check_state
from engine.state import (
    Activity,
    Character,
    Faction,
    FactionStatus,
    Membership,
    Place,
    PlaceStatus,
    Route,
    WorldChange,
    WorldChangeKind,
    WorldState,
)
from engine.succession import carry_on
from engine.visibility import memory_view
from engine.world import strife, telling
from engine.world.scheduling import World
from engine.world.tuning import (
    CHANGES_KEPT,
    WAR_PAUSE_S,
    WAR_UNREST,
    WAR_WASTE,
)

from .test_world import ctx, rng
from .test_world_lives import YOU, valley

CROWN, LEAGUE = "crown", "league"
KEY = strife.pair_key(CROWN, LEAGUE)


def champion(cid: str, faction: str, might: int, where: str) -> Character:
    """Someone a faction can strike with: its strength in a war is its mightiest member's."""
    person = Character(
        id=cid, name=cid.title(), location_id=where, memberships=[Membership(faction_id=faction)]
    )
    person.sheet.axes.might = might
    return person


def realm(crown: int = 2, league: int = 2) -> WorldState:
    """Two kingdoms at war, far from Tomas's valley. The Crown of Harrow sits in Harrowgate,
    five days from his village, and holds Northfield beyond it. The Eastmark League sits in
    Eastmark and holds Willow Ford, two days from Harrowgate on the road between them. Each
    has a champion of the given might."""
    state = valley()
    places = state.places
    places["city"].controller_id = CROWN
    places["northfield"] = Place(id="northfield", name="Northfield", controller_id=CROWN)
    places["eastmark"] = Place(id="eastmark", name="Eastmark", kind="city", controller_id=LEAGUE)
    places["ford"] = Place(id="ford", name="Willow Ford", kind="village", controller_id=LEAGUE)
    places["city"].routes += [
        Route(to_id="ford", travel_s=2 * DAY),
        Route(to_id="northfield", travel_s=DAY),
    ]
    places["ford"].routes.append(Route(to_id="eastmark", travel_s=2 * DAY))
    state.factions[CROWN] = Faction(
        id=CROWN, name="the Crown of Harrow", relations={LEAGUE: -80}, known_by=[YOU]
    )
    state.factions[LEAGUE] = Faction(
        id=LEAGUE, name="the Eastmark League", relations={CROWN: -80}, known_by=[YOU]
    )
    state.characters["aldric"] = champion("aldric", CROWN, crown, "city")
    state.characters["serra"] = champion("serra", LEAGUE, league, "eastmark")
    return state


def years(state: WorldState, n: float = 1, *, strides: int = 1, seed: int = 0) -> WorldState:
    """The world's part in its wars over `n` years, in `strides` stretches, as the tick runs
    it: each stretch has a stream of its own."""
    span = int(n * YEAR) // strides
    for _ in range(strides):
        since = state.world_s
        state.world_s = since + span
        stream = rng().child("tick", seed, state.world_s)
        strife.strive(World(state=state, ctx=ctx(), at_s=state.world_s, rng=stream), since)
    return state


def sure(monkeypatch, **odds) -> None:
    """Make things certain, or impossible, so a test reads what happens, not how often."""
    for name, value in odds.items():
        monkeypatch.setattr(strife, name, value)


def changes(state: WorldState) -> list[WorldChange]:
    return sorted(state.changes.values(), key=lambda c: (c.world_s, c.id))


def kinds(state: WorldState) -> list[str]:
    return [c.kind.value for c in changes(state)]


# --- nothing is timed in turns, and nothing is made to happen (W10) ---------------------------


def test_a_month_or_a_year_is_no_time_for_a_war_to_come_to_a_head(monkeypatch):
    """A war comes to a head no sooner than a year after the world first saw it, however
    likely: "if a month went by, obviously there is no time for such things"."""
    sure(monkeypatch, WAR_RATE=1.0)
    for seed in range(20):
        month = years(realm(), 1 / 12, seed=seed)
        assert month.changes == {} and month.strife_s == {KEY: 0}
        year = years(realm(), 1, strides=12, seed=seed)
        assert year.changes == {}
        assert year.factions[CROWN].status is year.factions[LEAGUE].status is FactionStatus.INTACT

    # From then on it may, and with the odds certain it does in the next stretch.
    later = years(years(realm(), 1), 1)
    assert len(later.changes) == 1 and later.strife_s[KEY] == later.world_s


def test_over_ten_years_most_wars_are_fought_out_and_some_never_are():
    """Nothing is made to happen: by the odds alone, ten years settle most wars, a year none,
    and some stand as they were ("maybe 10 years go by" and things are "exactly the same")."""
    fought = Counter()
    for seed in range(60):
        state = years(realm(), 10, strides=24, seed=seed)
        fought[bool(state.changes)] += 1
        assert check_state(state) == []
    assert fought[True] > 40 and fought[False] > 0

    # The same years play the same way again (A3).
    again = years(realm(), 10, strides=24, seed=7)
    assert kinds(again) == kinds(years(realm(), 10, strides=24, seed=7))


def test_two_at_peace_or_asleep_fight_nothing_out(monkeypatch):
    sure(monkeypatch, WAR_RATE=1.0)
    peace = realm()
    peace.factions[CROWN].relations[LEAGUE] = -59
    peace.factions[LEAGUE].relations[CROWN] = -59
    assert years(peace, 10, strides=10).changes == {} and peace.strife_s == {}

    asleep = realm()
    for faction in asleep.factions.values():
        faction.activity = Activity.DORMANT
    assert years(asleep, 10, strides=10).changes == {}

    # One side's enmity is a war, and a pair that makes peace keeps no time.
    grudge = realm()
    grudge.factions[LEAGUE].relations[CROWN] = 0
    years(grudge, 1)
    assert grudge.strife_s == {KEY: 0}
    grudge.factions[CROWN].relations[LEAGUE] = 0
    assert years(grudge, 5).changes == {} and grudge.strife_s == {}


# --- how it ends: the facts first (A2) ----------------------------------------------------------


def test_a_far_mightier_side_wins_with_no_throw_and_the_other_falls(monkeypatch):
    """A2: a side two steps of might above the other wins, whatever the dice. The loser is
    destroyed, its people live on as its survivors (W15a), and what it held is the winner's:
    occupied, and less steady for it (W7)."""
    sure(monkeypatch, WAR_RATE=1.0)
    for seed in range(12):
        state = years(years(realm(crown=4, league=2), 1, seed=seed), 1, seed=seed)
        (change,) = changes(state)
        assert change.kind is WorldChangeKind.FELL
        assert change.faction_ids == [CROWN, LEAGUE] and change.place_ids == ["eastmark", "ford"]
        crown, league = state.factions[CROWN], state.factions[LEAGUE]
        assert crown.status is FactionStatus.INTACT
        assert league.status is FactionStatus.DESTROYED and league.survivors == ["serra"]
        assert league.status_history[-1].note == "Fell to the Crown of Harrow."
        assert state.characters["serra"].alive  # nobody is killed off screen
        for place_id in ("eastmark", "ford"):
            place = state.places[place_id]
            assert place.controller_id == CROWN and place.status is PlaceStatus.OCCUPIED
            assert place.stability == Place(id="x", name="X").stability - WAR_UNREST
            assert place.status_history[-1].note == "Taken in a war."
        assert check_state(state) == []
        # The war is over: nothing more comes of it.
        assert kinds(years(state, 10, strides=10, seed=seed)) == ["fell"]


def test_a_close_war_is_thrown_for_and_the_loser_is_weakened_and_loses_land(monkeypatch):
    """Closer than that a seeded throw decides (A3), each step of might worth its edge. The
    loser is weakened and loses the land nearest the winner beyond its own seat."""
    sure(monkeypatch, WAR_RATE=1.0, WAR_SPENT=0.0)
    winners = Counter()
    for seed in range(40):
        state = years(years(realm(), 1, seed=seed), 1, seed=seed)
        (change,) = changes(state)
        assert change.kind is WorldChangeKind.BEATEN
        winner, loser = change.faction_ids
        winners[winner] += 1
        assert state.factions[winner].status is FactionStatus.INTACT
        assert state.factions[loser].status is FactionStatus.WEAKENED
        lost = "ford" if loser == LEAGUE else "northfield"
        assert change.place_ids == [lost] and state.places[lost].controller_id == winner
        seat = "eastmark" if loser == LEAGUE else "city"
        assert state.places[seat].controller_id == loser  # its seat is still its own
    assert winners[CROWN] > 5 and winners[LEAGUE] > 5

    # One step of might tips the throw, and at a full edge settles it.
    sure(monkeypatch, WAR_EDGE=0.5)
    for seed in range(12):
        state = years(years(realm(crown=3, league=2), 1, seed=seed), 1, seed=seed)
        assert changes(state)[0].faction_ids == [CROWN, LEAGUE]


def test_a_side_that_loses_while_weak_or_twice_running_falls(monkeypatch):
    sure(monkeypatch, WAR_RATE=1.0, WAR_SPENT=0.0, WAR_EDGE=0.5)
    # Already weakened, the League is a step down and loses, and losing while weak is a fall.
    weak = realm()
    weak.factions[LEAGUE].status = FactionStatus.WEAKENED
    weak = years(years(weak, 1), 1)
    assert kinds(weak) == ["fell"] and weak.factions[LEAGUE].status is FactionStatus.DESTROYED

    # Beaten once, it is weakened and has lost the ford. Beaten again by the same side, it falls.
    twice = years(years(realm(crown=3, league=2), 1), 1)
    assert kinds(twice) == ["beaten"]
    assert strife.strength(twice, twice.factions[LEAGUE]) == 1  # a step less while weakened
    twice = years(twice, WAR_PAUSE_S / YEAR + 1, strides=2)
    assert kinds(twice) == ["beaten", "fell"]
    assert twice.places["eastmark"].controller_id == twice.places["ford"].controller_id == CROWN


def test_two_that_wear_each_other_down_twice_both_fall_and_someone_takes_the_land(monkeypatch):
    """An even fight may leave both the weaker and neither the winner. Twice running, or
    while both are weak, both fall, and what they held is nobody's (damaged, far less steady)
    until a faction that can reach it takes it."""
    sure(monkeypatch, WAR_RATE=1.0, WAR_SPENT=1.0, SEIZE_RATE=0.0)
    state = years(years(realm(), 1), 1)
    assert kinds(state) == ["spent"] and changes(state)[0].place_ids == []
    assert {f.status for f in state.factions.values()} == {FactionStatus.WEAKENED}
    assert state.places["ford"].controller_id == LEAGUE

    state = years(state, 2, strides=2)
    assert kinds(state) == ["spent", "both_fell"]
    assert {f.status for f in state.factions.values()} == {FactionStatus.DESTROYED}
    held = ["city", "northfield", "eastmark", "ford"]
    assert changes(state)[-1].place_ids == held
    for place_id in held:
        place = state.places[place_id]
        assert place.controller_id is None and place.status is PlaceStatus.DAMAGED
        assert place.stability == Place(id="x", name="X").stability - WAR_WASTE
    assert check_state(state) == []

    # Nobody who could reach it: it stays nobody's. A third power on the road takes it.
    sure(monkeypatch, SEIZE_RATE=1.0)
    assert kinds(years(state.model_copy(deep=True), 5, strides=5))[2:] == []
    state.factions["marsh"] = Faction(id="marsh", name="the Marsh Barons")
    state.places["fen"] = Place(id="fen", name="Blackfen", controller_id="marsh")
    state.places["ford"].routes.append(Route(to_id="fen", travel_s=DAY))
    state = years(state, 1)
    taken = [c for c in changes(state) if c.kind is WorldChangeKind.SEIZED]
    assert sorted(c.place_ids[0] for c in taken) == sorted(held)
    assert all(c.faction_ids == ["marsh"] for c in taken)
    assert all(state.places[i].controller_id == "marsh" for i in held)
    assert all(state.places[i].status is PlaceStatus.OCCUPIED for i in held)
    # A place nobody ever held is not the wars' to hand out.
    assert state.places["village"].controller_id is None


# --- what stays the story's to tell -------------------------------------------------------------


def test_a_side_that_fell_fights_no_other_war_in_the_same_stretch(monkeypatch):
    """The League is at war with two others, and in one stretch both wars come to a head: it
    falls to the first, and is gone, so it neither wins nor falls again in the second (C1)."""
    sure(monkeypatch, WAR_RATE=1.0)
    for seed in range(12):
        state = realm(crown=4, league=2)
        state.places["isle"] = Place(id="isle", name="Grey Isle", controller_id="isles")
        state.places["isle"].routes.append(Route(to_id="eastmark", travel_s=3 * DAY))
        state.factions["isles"] = Faction(
            id="isles", name="the Grey Isles", relations={LEAGUE: -90}
        )
        state.characters["ragna"] = champion("ragna", "isles", 4, "isle")
        assert [(a.id, b.id) for a, b in strife.wars(state)] == [(CROWN, LEAGUE), ("isles", LEAGUE)]
        state = years(years(state, 1, seed=seed), 1, seed=seed)

        league = state.factions[LEAGUE]
        fell = [h for h in league.status_history if h.status == FactionStatus.DESTROYED.value]
        assert league.status is FactionStatus.DESTROYED and len(fell) == 1
        (change,) = changes(state)
        assert change.kind is WorldChangeKind.FELL and change.faction_ids == [CROWN, LEAGUE]
        assert state.factions["isles"].status is FactionStatus.INTACT
        assert check_state(state) == []


def test_the_player_characters_own_faction_is_never_fought_over_by_the_dice(monkeypatch):
    sure(monkeypatch, WAR_RATE=1.0)
    for own in ("member", "leader"):
        state = realm(crown=4, league=1)
        if own == "member":
            state.characters[YOU].memberships.append(Membership(faction_id=LEAGUE))
        else:
            state.factions[LEAGUE].leader_ids.append(YOU)
        assert strife.wars(state) == []
        assert years(state, 10, strides=10).changes == {}


def test_nothing_changes_hands_under_the_player_characters_feet(monkeypatch):
    """A faction never falls while the player character stands on its land, and the place
    they are in never changes hands behind their back: it is the story's to tell."""
    sure(monkeypatch, WAR_RATE=1.0, WAR_SPENT=0.0)
    state = realm(crown=4, league=2)
    state.characters[YOU].location_id = "ford"
    state = years(years(state, 1), 1)
    (change,) = changes(state)
    assert change.kind is WorldChangeKind.BEATEN and change.place_ids == []
    assert state.factions[LEAGUE].status is FactionStatus.WEAKENED
    assert state.places["ford"].controller_id == LEAGUE

    # Both sides spent and fallen while they are elsewhere, nobody takes the place they
    # then stand in.
    sure(monkeypatch, WAR_SPENT=1.0, SEIZE_RATE=1.0)
    empty = years(years(realm(), 1), 3, strides=3)
    assert "both_fell" in kinds(empty)
    empty.factions["marsh"] = Faction(id="marsh", name="the Marsh Barons")
    empty.places["fen"] = Place(id="fen", name="Blackfen", controller_id="marsh")
    empty.places["ford"].routes.append(Route(to_id="fen", travel_s=DAY))
    empty.characters[YOU].location_id = "ford"
    empty = years(empty, 1)
    assert empty.places["ford"].controller_id is None
    assert empty.places["eastmark"].controller_id == "marsh"


# --- who hears of it (C6, W2) -------------------------------------------------------------------


def fallen(monkeypatch, where: str = "farm") -> WorldState:
    """The League has fallen to the Crown, with Tomas living at `where` all the while."""
    sure(monkeypatch, WAR_RATE=1.0)
    state = realm(crown=4, league=2)
    state.characters[YOU].location_id = where
    return years(years(state, 1), 1)


def test_far_away_it_is_news_and_memory_holds_none_of_it(monkeypatch):
    """C6: five days from the nearest of it, Tomas knows nothing. The record has the League
    destroyed; to him, and in Memory, it stands as it did. Word of it starts where it
    happened, as a rumor in the story's language (W2, S10)."""
    state = fallen(monkeypatch)
    (change,) = changes(state)
    assert change.known_by == [] and strife.unheard(state) == [change]
    assert strife.heard_in(state, ctx().turn) == []
    league = next(f for f in memory_view(state).factions if f.id == LEAGUE)
    assert league.lines == []  # nothing of a fall, no "Destroyed"

    rumor = state.rumors[change.rumor_id]
    assert rumor.text == telling.world_change(state, change)
    assert rumor.text == (
        "The Eastmark League fell to the Crown of Harrow in their war, and what was theirs is "
        "the Crown of Harrow's now."
    )
    assert rumor.origin_place_id == "eastmark" and rumor.is_true
    assert strife.by_rumor(state, rumor.id) == [change.id]
    assert strife.by_rumor(state, None) == []


def test_someone_who_takes_the_story_up_knows_what_came_to_those_they_know_of(monkeypatch):
    """N6: someone else becomes the player character. They grew up in this world, so what the
    years did to a faction or a place they know of is no news to them, and what came to those
    they have never heard of still is."""
    state = fallen(monkeypatch)
    (change,) = changes(state)
    for knows, heard in ((["bram"], True), ([], False)):
        after = state.model_copy(deep=True)
        after.player_id = "bram"
        after.factions[LEAGUE].known_by = list(knows)
        after.factions[CROWN].known_by = []
        strife.hand_over(after)
        assert ("bram" in after.changes[change.id].known_by) is heard
        assert (strife.unheard(after) == []) is heard
        assert ("bram" in after.factions[LEAGUE].status_history[-1].known_by) is heard
        assert YOU not in after.changes[change.id].known_by  # what Tomas knew is nothing to him

    # Through a succession, by the place they live in: Serra, of Eastmark, knows it fell.
    carried = carry_on(
        state, state.characters["serra"], "Dawn in Eastmark.", ending="chosen", turn=9
    )
    assert carried.player_id == "serra" and strife.unheard(carried) == []


def test_living_near_it_they_know_as_it_happens(monkeypatch):
    """Whoever lives within a day of a place it touched, or of land of those it came to,
    saw it come: it is nothing a scene has to tell them, and Memory has it with its day."""
    for where in ("ford", "northfield"):
        sure(monkeypatch, WAR_RATE=1.0)
        state = realm(crown=4, league=2)
        # Not on the League's own land, where the story would hold the fall back.
        state.characters[YOU].location_id = "city" if where == "ford" else where
        state = years(years(state, 1), 1)
        (change,) = changes(state)
        assert change.kind is WorldChangeKind.FELL
        assert change.known_by == [YOU] and strife.unheard(state) == []
        assert strife.heard_in(state, ctx().turn) == [change]
        assert strife.to_tell(state, state.player.location_id) == []
        league = next(f for f in memory_view(state).factions if f.id == LEAGUE)
        assert league.lines[0] == "Destroyed"
        assert league.lines[1].startswith("The Eastmark League fell to the Crown of Harrow")
        assert league.lines[1].endswith(", day 731.")
        ford = next(p for p in memory_view(state).places if p.id == "ford")
        assert "Occupied" in ford.lines


def test_a_scene_is_handed_it_where_it_happened_or_where_word_has_reached(monkeypatch):
    state = fallen(monkeypatch)
    (change,) = changes(state)
    # In a place it touched, the place itself shows it.
    assert strife.to_tell(state, "ford") == [change] and strife.touched(state, change, "ford")
    # Where it didn't reach and no word has come, there is nothing to tell.
    assert strife.to_tell(state, "farm") == [] and strife.to_tell(state, None) == []
    assert not strife.touched(state, change, "city")
    assert strife.to_tell(state, "city") == []
    # Once word has reached a place, a scene there can tell it.
    state.rumors[change.rumor_id].reached_place_ids.append("city")
    assert strife.to_tell(state, "city") == [change]
    # And somewhere inside a place it touched or word reached, too.
    state.places["inn"] = Place(id="inn", name="The Heron", parent_id="city")
    assert strife.to_tell(state, "inn") == [change]


def test_once_a_scene_told_it_they_know_and_memory_shows_it(monkeypatch):
    state = fallen(monkeypatch)
    (change,) = changes(state)
    after, heard = strife.hear(state, [change.id, "change-99"])
    assert heard == [change.id] and state.changes[change.id].known_by == []  # a new state
    assert after.changes[change.id].known_by == [YOU] and strife.unheard(after) == []
    assert strife.hear(after, [change.id]) == (after, [])
    league = next(f for f in memory_view(after).factions if f.id == LEAGUE)
    assert league.lines[0] == "Destroyed"
    places = {p.id: p for p in memory_view(after).places}
    # They learn the places it names, as anyone who hears it does.
    assert "Occupied" in places["ford"].lines and "Occupied" in places["eastmark"].lines
    assert any(line.startswith("The Eastmark League fell") for line in places["ford"].lines)

    # In Spanish and Catalan the line is the world's sentence in that language (S10).
    spanish = next(f for f in memory_view(after, Language.ES).factions if f.id == LEAGUE)
    assert spanish.lines[1].startswith(
        "La guerra entre the Crown of Harrow y the Eastmark League acabó con la caída"
    )


def test_a_change_is_told_where_the_scene_names_whom_it_came_to(monkeypatch):
    """C6: the narrator's list alone tells nothing. A change is told where the scene names a
    faction or a place it came to, other than the place the scene is in and whoever held it
    all along, whose names are there every day."""
    state = fallen(monkeypatch)
    (change,) = changes(state)
    told = [change.id]
    state.characters[YOU].location_id = "city"  # the winner's own city

    quiet = "Harrowgate is loud with carts. The Crown's banners hang over the gate, as ever."
    assert strife.borne_out(state, told, quiet) == []
    assert pipeline.settle_changes(state, told, scene=quiet) == (state, [])

    for said in (
        '"The League is gone," the carter says. "Two winters now."',
        "They took Eastmark in the end, the carter tells you.",
        "The Eastmark League fell, he says, and nobody mourned it here.",
    ):
        assert strife.borne_out(state, told, said) == told, said
    after, heard = pipeline.settle_changes(state, told, scene='"The League is gone."')
    assert heard == told and after.changes[change.id].known_by == [YOU]

    # A name without its capital names nothing, and what isn't on record can't be told.
    assert strife.borne_out(state, told, "you ford the stream and think of the league") == []
    assert strife.borne_out(state, ["change-99"], "The League is gone.") == []

    # In a town that changed hands, the town's own name is there every day: what tells it is
    # whoever holds it now, or whoever lost it.
    state.characters[YOU].location_id = "ford"
    assert strife.borne_out(state, told, "Willow Ford is quieter than you remember.") == []
    assert strife.borne_out(state, told, "The Crown's men hold the bridge now.") == told
    # No scene, no check: code that settles a scene it wrote itself vouches for what it told.
    assert pipeline.settle_changes(state, told)[1] == told


def test_word_of_it_heard_as_talk_is_the_change_heard(monkeypatch):
    """W2: the rumor of a change, caught as the talk of a place, is that change heard."""
    state = fallen(monkeypatch)
    (change,) = changes(state)
    state.characters[YOU].location_id = "city"
    state.rumors[change.rumor_id].reached_place_ids.append("city")
    plan = DirectorPlan(talk=PlannedTalk(rumor_id=change.rumor_id))

    after = pipeline.hear_talk(state, plan, ctx(), rng())

    assert after.changes[change.id].known_by == [YOU]
    assert state.changes[change.id].known_by == []
    league = next(f for f in memory_view(after).factions if f.id == LEAGUE)
    assert league.lines[0] == "Destroyed"


# --- the record -----------------------------------------------------------------------------------


def test_the_world_tells_each_kind_of_change_in_the_storys_language():
    state = realm()

    def said(kind: WorldChangeKind, sides: list[str], held: list[str], language=Language.EN):
        change = WorldChange(id="c", kind=kind, faction_ids=sides, place_ids=held)
        return telling.world_change(state, change, language)

    both = [CROWN, LEAGUE]
    assert said(WorldChangeKind.BEATEN, both, ["ford"]) == (
        "The Crown of Harrow beat the Eastmark League in their war and took Willow Ford."
    )
    assert said(WorldChangeKind.BEATEN, both, []) == (
        "The Crown of Harrow beat the Eastmark League in their war."
    )
    assert said(WorldChangeKind.SPENT, both, []) == (
        "The war between the Crown of Harrow and the Eastmark League wore both sides down, "
        "and neither won."
    )
    assert said(WorldChangeKind.BOTH_FELL, both, ["city", "ford"]) == (
        "The Crown of Harrow and the Eastmark League destroyed each other in their war, and "
        "what was theirs is nobody's now."
    )
    assert said(WorldChangeKind.SEIZED, [CROWN], ["ford"]) == (
        "The Crown of Harrow took Willow Ford, which nobody had held since the war."
    )
    # Spanish and Catalan tell a war's end of the war, so no verb has to agree with a name.
    assert said(WorldChangeKind.BEATEN, both, ["ford", "eastmark"], Language.ES) == (
        "La guerra entre the Crown of Harrow y the Eastmark League se decantó del lado de the "
        "Crown of Harrow, y Willow Ford y Eastmark pasaron a sus manos."
    )
    assert said(WorldChangeKind.FELL, both, ["ford"], Language.CA).startswith(
        "La guerra entre the Crown of Harrow i the Eastmark League va acabar amb la caiguda"
    )
    for kind in WorldChangeKind:
        for language in Language:
            sides = [CROWN] if kind is WorldChangeKind.SEIZED else both
            assert said(kind, sides, ["ford"], language).endswith(".")


def test_only_the_latest_changes_are_kept_and_each_is_about_records_on_record(monkeypatch):
    state = realm()
    for n in range(CHANGES_KEPT + 5):
        state.changes[f"change-{n}"] = WorldChange(
            id=f"change-{n}", kind=WorldChangeKind.SPENT, faction_ids=[CROWN, LEAGUE], world_s=n
        )
    years(state, 0.1)
    assert len(state.changes) == CHANGES_KEPT and "change-4" not in state.changes
    assert check_state(state) == []

    state.changes["change-0"] = WorldChange(
        id="change-0", kind=WorldChangeKind.SEIZED, faction_ids=["nobody"], place_ids=["nowhere"]
    )
    assert [v.subject for v in check_state(state)] == ["change change-0"]


@pytest.mark.parametrize("stride", [1, 4, 24])
def test_the_odds_are_the_same_however_the_years_are_cut(stride):
    """W10: the chance over a stretch follows from the chance in a year, so ten years bring
    about as much whether the world ticks through them in one stride or in many."""
    fought = sum(bool(years(realm(), 10, strides=stride, seed=seed).changes) for seed in range(80))
    assert 60 <= fought <= 80
