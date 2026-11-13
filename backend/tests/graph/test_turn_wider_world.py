"""W6, C6: what the narrator is told of what the years did to the wider world.

A war that came to a head while the story was elsewhere is on record, and news to the player
character until a scene shows or tells it. The brief hands it to a scene in a place it touched
or that word of it has reached, says with it what the scene owes it, and marks beside whatever
it changed that the player character hasn't heard.
"""

from engine import pipeline
from engine.base import YEAR
from engine.contracts import DirectorPlan, PlannedTalk
from engine.state import Character, WorldState
from engine.world import strife
from graph.turn import prompts
from graph.turn.outputs import NarratorOutput
from tests.engine.test_world import ctx
from tests.engine.test_world_strife import CROWN, LEAGUE, YOU, changes, realm, years
from tests.graph.test_turn_context import _section, brief

FELL = (
    "The Eastmark League fell to the Crown of Harrow in their war, and what was theirs is the "
    "Crown of Harrow's now."
)
UNHEARD = "the player character hasn't heard what became of it: to them it is as it was"


def fallen(monkeypatch, where: str = "farm") -> WorldState:
    """The League fell to the Crown a year ago, with Tomas at `where` all the while. He has
    heard of both kingdoms and of their towns."""
    monkeypatch.setattr(strife, "WAR_RATE", 1.0)
    state = realm(crown=4, league=2)
    state.characters[YOU].location_id = where
    for place in state.places.values():
        place.known_by.append(YOU)
    state = years(years(state, 1), 1)
    state.world_s += YEAR
    return state


def at(state: WorldState, where: str) -> WorldState:
    """Tomas is in `where` now, alone."""
    state.characters[YOU].location_id = where
    state.scene.place_id, state.scene.present_ids = where, [YOU]
    return state


def test_far_from_it_a_scene_is_told_only_that_it_is_news(monkeypatch):
    """Where it didn't happen and no word has come, no scene can tell it. The record shows
    the narrator the world as it is, so beside what the years changed the brief says that the
    player character hasn't heard: to them the League still stands."""
    state = at(fallen(monkeypatch), "farm")

    told = brief(state)

    assert "## WIDER WORLD" not in told.user and told.news == ()
    known = _section(told.user, "KNOWN")
    league = next(f for f in known["factions"] if f["id"] == LEAGUE)
    assert league == {
        "id": LEAGUE,
        "name": "the Eastmark League",
        "status": "destroyed",
        "news_to_you": UNHEARD,
    }
    crown = next(f for f in known["factions"] if f["id"] == CROWN)
    assert crown["news_to_you"] == UNHEARD  # the war's end is news of both
    places = {p["id"]: p for p in known["places"]}
    assert places["ford"]["status"] == "occupied" and places["ford"]["news_to_you"] == UNHEARD
    assert "news_to_you" not in places["city"]
    continuity = _section(told.user, "CONTINUITY")
    assert (
        "the Eastmark League (league) is destroyed and no longer acts as one. The player "
        "character hasn't heard: to them it is as it was."
    ) in continuity
    assert (
        "Willow Ford (ford) is occupied. The player character hasn't heard: to them it is as "
        "it was."
    ) in continuity


def test_a_scene_where_it_happened_shows_the_place_as_it_is_now(monkeypatch):
    state = at(fallen(monkeypatch), "ford")
    (change,) = changes(state)

    told = brief(state)

    moved = _section(told.user, "WIDER WORLD")
    assert moved["news"] == [{"id": change.id, "what": FELL, "when": "a year ago", "here": True}]
    assert "lived" not in moved
    assert "hasn't heard" in moved["tell"] and "never undo it or add to it" in moved["tell"]
    assert "naming a faction or a place it came to" in moved["tell"]
    assert "One marked here touched this very place" in moved["tell"]
    assert "back after years" not in moved["tell"]
    assert told.news == (change.id,)


def test_where_word_has_reached_someone_may_tell_it_and_a_homecoming_tells_some(monkeypatch):
    """Word of it travels (W2). In a place it has reached, the scene may tell it, and where
    the scene is a meeting again after years it tells at least one piece: "wow, I'm really in
    a world where 10 years went by" (Miki, 2026-11-13)."""
    state = at(fallen(monkeypatch), "village")
    (change,) = changes(state)
    assert "## WIDER WORLD" not in brief(state).user  # no word has come this far
    state.rumors[change.rumor_id].reached_place_ids.append("village")

    told = brief(state)

    moved = _section(told.user, "WIDER WORLD")
    assert moved["news"] == [{"id": change.id, "what": FELL, "when": "a year ago"}]
    assert "One marked here" not in moved["tell"] and "back after years" not in moved["tell"]
    assert "## MEETING AGAIN" not in told.user

    # Old Bram, whom he hasn't seen in three years, is in the scene.
    state.scene.present_ids = [YOU, "bram"]
    state.characters["bram"].seen_s = 0
    state.characters["bram"].location_id = "village"
    home = brief(state)
    assert _section(home.user, "MEETING AGAIN")["people"][0]["who"] == "Old Bram"
    tell = _section(home.user, "WIDER WORLD")["tell"]
    assert tell.endswith("This scene has them back after years: it tells at least one piece of it.")

    # With talk to tell and nothing on record to say, the news is what there is to hear (W2).
    talk = brief(state, plan=DirectorPlan(talk=PlannedTalk(asked=True)))
    assert _section(talk.user, "TALK") == {"news": True, "asked": True}


def test_what_they_lived_through_is_told_in_passing_and_is_no_news(monkeypatch):
    """Living a day from Northfield, Tomas saw the war end: the scene that covers that time is
    told it as something he knows, and no later scene has anything to tell."""
    monkeypatch.setattr(strife, "WAR_RATE", 1.0)
    state = realm(crown=4, league=2)
    at(state, "northfield")
    state = years(years(state, 1), 1)

    told = brief(state)  # the same turn the tick ran in

    moved = _section(told.user, "WIDER WORLD")
    assert moved["lived"] == [{"what": FELL, "when": "moments ago"}]
    assert "news" not in moved and told.news == ()
    assert moved["tell"].startswith("lived came in the time this scene covers")
    assert "news_to_you" not in told.user and "hasn't heard" not in told.user

    later = brief(state, context=ctx(turn=9))
    assert "## WIDER WORLD" not in later.user


def test_once_a_scene_told_it_the_brief_has_nothing_left_to_say(monkeypatch):
    state = at(fallen(monkeypatch), "ford")
    (change,) = changes(state)

    heard, ids = pipeline.settle_changes(state, [change.id], scene="The Crown holds the ford.")

    assert ids == [change.id]
    told = brief(heard, context=ctx(turn=9))
    assert "## WIDER WORLD" not in told.user and told.news == ()
    assert "news_to_you" not in told.user and "hasn't heard" not in told.user


def test_the_briefs_news_of_people_and_of_the_world_are_told_apart_by_code(monkeypatch):
    """One list in the narrator's answer carries both kinds of news (`told_news`). Each is
    held to its own record, so a change's id tells no news of a person and the other way."""
    state = at(fallen(monkeypatch), "ford")
    (change,) = changes(state)
    state.characters["mara"] = Character(id="mara", name="Mara", location_id="ford")

    after, heard = pipeline.settle_lives(state, [change.id], scene="The Crown holds the ford.")
    assert heard == [] and after.changes[change.id].known_by == []
    after, heard = pipeline.settle_changes(state, ["life-1"], scene="Mara and the Crown.")
    assert heard == [] and after is state


def test_the_narrator_is_told_how_the_section_reads_and_what_to_list():
    system = " ".join(prompts.NARRATOR_SYSTEM.split())
    assert "- WIDER WORLD: what the years did to the wider world (W6), and tell:" in system
    assert "someone in SCENE or WHO ELSE, or WIDER WORLD, has news (W6)" in system
    listed = NarratorOutput.model_fields["told_news"].description
    assert "or under WIDER WORLD" in listed and "the faction or place it came to" in listed
