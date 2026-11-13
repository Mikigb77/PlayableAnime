"""W6, G19, C6: what the narrator is told of people who climbed while the story was elsewhere.

Someone who rose stands on their new rung on the record the narrator reads, and the rise is
news under them until a scene tells it, like anything else the years brought them. A player
character who lived near knows already, and the scene that covers the time tells it in
passing. How fast the world has someone climb is its own bookkeeping, and stays out.
"""

from engine.base import HOUR
from engine.state import LadderPosition, LifeKind, Practice, WorldState
from engine.world import lives
from tests.engine.test_world_climbing import climbers, on, plain
from tests.engine.test_world_lives import YOU, a_year, news, villager
from tests.graph.test_turn_context import _section, brief
from tests.graph.test_turn_old_age import at

ROSE = LifeKind.ROSE


def risen(monkeypatch, where: str, *, fortune: bool = False) -> WorldState:
    """Kid stood on the lowest realm at sixteen, in the village. Nine years on they stand on
    the next, with Tomas living in `where` all the while. With `fortune` it took them half a
    year, and no work of theirs."""
    plain(monkeypatch)
    if fortune:
        monkeypatch.setattr(lives, "FORTUNE_RATE", 1.0)
    state = at(climbers(villager("kid", "Kid", 16)), where)
    on(state, "kid", 0)
    return a_year(state, 0.5 if fortune else 9)


def test_someone_met_again_stands_on_their_new_rung_and_brings_the_news_of_it(monkeypatch):
    state = risen(monkeypatch, "city")
    (event,) = news(state, ROSE)
    state = at(state, "village", "kid")

    told = brief(state)

    (kid,) = _section(told.user, "SCENE")["present"]
    assert kid["sheet"]["ladders"] == [{"ladder_id": "realms", "rung": "Realm 1"}]
    assert kid["news"] == [{"id": event.id, "what": "rose to Realm 1", "when": "moments ago"}]
    assert told.news == (event.id,)


def test_how_fast_the_world_has_someone_climb_stays_out_of_the_brief(monkeypatch):
    state = at(risen(monkeypatch, "city"), "village", "kid")
    (position,) = state.characters["kid"].sheet.ladders
    assert position.yearly_s and position == LadderPosition(
        ladder_id="realms", rung=1, yearly_s=position.yearly_s
    )

    told = brief(state)

    assert "yearly_s" not in told.user


def test_the_hours_toward_someones_next_rung_stay_out_and_their_stage_tells_it(monkeypatch):
    """What the world counts toward a rung sits on their sheet as the player character's own
    work does. The narrator reads how far along they are as their stage, not as seconds."""
    state = climbers(villager("kid", "Kid", 16), villager("smith", "Smith", 30))
    on(state, "kid", 0)
    state.characters["smith"].sheet.practice = [Practice(key="skill:smithing", what="smithing")]
    plain(monkeypatch)
    state = at(a_year(at(state, "city"), 5), "village", "kid", "smith")
    (work,) = state.characters["kid"].sheet.practice
    assert work.key == "ladder:realms" and work.effort_s > 50 * HOUR

    kid, smith = _section(brief(state).user, "SCENE")["present"]

    assert "practice" not in kid["sheet"]
    assert kid["sheet"]["ladders"] == [
        {"ladder_id": "realms", "rung": "Realm 0", "stage": "middle"}
    ]
    assert [work["key"] for work in smith["sheet"]["practice"]] == ["skill:smithing"]


def test_living_near_they_know_of_a_rise_and_the_scene_tells_it_in_passing(monkeypatch):
    state = risen(monkeypatch, "farm")

    told = brief(state)  # the same turn the tick ran in

    assert _section(told.user, "LIVES") == [
        {"who": {"id": "kid", "name": "Kid"}, "what": "rose to Realm 1", "when": "moments ago"}
    ]
    assert told.news == ()


def test_a_rise_by_fortune_leaves_what_it_was_to_the_scene_that_tells_it(monkeypatch):
    state = risen(monkeypatch, "city", fortune=True)
    (event,) = news(state, ROSE)
    assert event.fortune and YOU not in event.known_by
    state = at(state, "village", "kid")

    (kid,) = _section(brief(state).user, "SCENE")["present"]

    (piece,) = kid["news"]
    assert piece["what"].startswith("rose to Realm 1 by a stroke of fortune, not by the years")
    assert "this scene's to say" in piece["what"]
