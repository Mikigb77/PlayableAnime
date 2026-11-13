"""W6, C6: what the narrator is told of people old age took while the story was elsewhere.

A death of old age is on record, and news to the player character until a scene tells it. The
dead are in no scene, so the brief hands the news to a scene where they lived, or with their
family or the partner they left in it, and says with it what the scene owes it. Everywhere
else it only marks, beside the dead, that the player character hasn't heard.
"""

from engine import pipeline
from engine.apply import apply_delta
from engine.base import YEAR
from engine.contracts import CharacterChange, StateDelta
from engine.state import (
    BondStage,
    CharacterStatus,
    LifeKind,
    Origin,
    OriginKind,
    PowerLadder,
    Rung,
    StatusChange,
    WorldState,
)
from engine.world import old_age
from graph.turn.outputs import NarratorOutput
from tests.engine.test_world import ctx
from tests.engine.test_world_lives import NARRATOR, YOU, a_year, couple, news, valley, villager
from tests.graph.test_turn_context import _section, brief

DIED = LifeKind.DIED
UNHEARD = "dead, which the player character hasn't heard: to them they are alive"
ONE_LINE = "Dead, though the player character hasn't heard, so to them not dead: "


def at(state: WorldState, where: str, *others: str) -> WorldState:
    """Tomas is in `where` now, with `others`."""
    state.characters[YOU].location_id = where
    state.scene.place_id, state.scene.present_ids = where, [YOU, *others]
    for other in others:
        state.characters[other].location_id = where
    return state


def passed(monkeypatch, *people, old: tuple[str, ...] = (), wed: str | None = None) -> WorldState:
    """Old Bram died of old age in the village two years ago, at seventy-two, and so did
    whoever else is `old`, with Tomas in the city all the while, five days off. Nobody else
    on record has an age for the years to take them at. `wed` is whom Old Bram was married
    to."""
    monkeypatch.setattr(old_age, "chance", lambda lives, from_age, to_age: 1.0)
    state = at(valley(*people), "city")
    if wed is not None:
        couple(state, "bram", wed, BondStage.MARRIED)
    for person in state.characters.values():
        if person.id not in (YOU, "bram", *old):
            person.age = None
    state = a_year(state, 1)
    state.world_s += 2 * YEAR
    return state


def test_far_from_where_they_lived_a_scene_is_told_only_that_it_is_news(monkeypatch):
    """No scene in the city can tell of a death in the village. The record shows the narrator
    the world as it is, so beside the dead the brief says that the player character hasn't
    heard: to them Old Bram is alive."""
    state = passed(monkeypatch)

    told = brief(state)

    assert "## WIDER WORLD" not in told.user and told.news == ()
    bram = next(p for p in _section(told.user, "KNOWN")["people"] if p["id"] == "bram")
    assert bram == {"id": "bram", "name": "Old Bram", "status": UNHEARD}
    continuity = _section(told.user, "CONTINUITY")
    assert ONE_LINE + "Old Bram (bram)." in continuity
    assert "Old Bram (bram) is dead." not in continuity


def test_a_hundred_years_of_deaths_take_one_line_of_the_brief(monkeypatch):
    people = [villager(f"v{i}", f"Villager {i}", 70) for i in range(6)]
    state = passed(monkeypatch, *people, old=tuple(p.id for p in people))

    continuity = _section(brief(state).user, "CONTINUITY")

    (line,) = [text for text in continuity if text.startswith(ONE_LINE)]
    assert "Old Bram (bram)" in line and "Villager 5 (v5)" in line
    assert not any(text.endswith(" is dead.") for text in continuity)


def test_someone_missing_whom_the_years_took_is_still_missing_to_them(monkeypatch):
    """Nobody saw it, so it is news to nobody and no scene has it to tell: the record has
    them dead for certain, and to the player character they are missing as before."""
    monkeypatch.setattr(old_age, "chance", lambda lives, from_age, to_age: 1.0)
    state = at(valley(), "village")
    state.characters["ilse"].age = None
    bram = state.characters["bram"]
    bram.status = CharacterStatus.MISSING
    bram.status_history.append(
        StatusChange(status="missing", from_status="alive", turn=1, world_s=0, known_by=[YOU])
    )

    state = a_year(state, 1)

    assert not state.characters["bram"].alive and news(state, DIED) == []
    told = brief(state)
    assert "## WIDER WORLD" not in told.user and "## LIVES" not in told.user
    known = next(p for p in _section(told.user, "KNOWN")["people"] if p["id"] == "bram")
    assert known["status"] == UNHEARD.replace("alive", "missing")
    assert ONE_LINE + "Old Bram (bram)." in _section(told.user, "CONTINUITY")


def test_a_scene_where_they_lived_is_handed_who_is_gone(monkeypatch):
    """The dead are in no scene, so their death is the place's to tell: at the village, and
    at the farm forty minutes from it."""
    state = at(passed(monkeypatch), "village")
    (event,) = news(state, DIED)

    told = brief(state)

    moved = _section(told.user, "WIDER WORLD")
    assert moved["gone"] == [
        {
            "id": event.id,
            "who": {"id": "bram", "name": "Old Bram"},
            "what": "died of old age",
            "when": "2 years ago",
            "aged": 72,
        }
    ]
    assert "news" not in moved and "lived" not in moved
    assert moved["tell"].startswith("gone are people the player character knew who have died")
    assert "They are dead, so nobody meets them." in moved["tell"]
    assert "list the id of each one the scene said by name had died" in moved["tell"]
    assert "back after years" not in moved["tell"]
    assert told.news == (event.id,)
    # Beside the dead, the brief still says that it is news.
    bram = next(p for p in _section(told.user, "KNOWN")["people"] if p["id"] == "bram")
    assert bram["status"] == UNHEARD

    assert _section(brief(at(state, "farm")).user, "WIDER WORLD")["gone"] == moved["gone"]


def test_a_homecoming_tells_at_least_one_piece_of_it(monkeypatch):
    """Miki, 2026-11-13: "wow, I'm really in a world where 10 years went by"."""
    state = passed(monkeypatch, villager("mara", "Mara"))
    state.characters["mara"].seen_s = 0
    state = at(state, "village", "mara")

    told = brief(state)

    assert _section(told.user, "MEETING AGAIN")["people"][0]["who"] == "Mara"
    tell = _section(told.user, "WIDER WORLD")["tell"]
    assert tell.endswith("This scene has them back after years: it tells at least one piece of it.")


def test_the_partner_they_left_has_it_as_their_news_wherever_the_two_meet(monkeypatch):
    state = passed(monkeypatch, villager("mara", "Mara"), wed="mara")
    event = next(e for e in news(state, DIED) if e.subject_ids == ["bram", "mara"])
    state = at(state, "city", "mara")

    told = brief(state)

    mara = _section(told.user, "SCENE")["present"][-1]
    assert mara["news"] == [
        {
            "id": event.id,
            "what": "lost their partner, who died of old age",
            "when": "2 years ago",
            "with": {"id": "bram", "name": "Old Bram"},
        }
    ]
    assert "## WIDER WORLD" not in told.user and told.news == (event.id,)

    # Where he lived, the place tells it too, with whom he left.
    home = _section(brief(at(state, "village")).user, "WIDER WORLD")
    assert home["gone"][0]["leaving"] == {"id": "mara", "name": "Mara"}


def test_their_family_in_the_scene_can_tell_it_far_from_where_they_lived(monkeypatch):
    """His daughter, met in the city fifty years on: nobody else there could say that the old
    man died, and she can."""
    daughter = villager("lena", "Lena", parent_ids=["bram"])
    state = passed(monkeypatch, daughter, villager("wil", "Wil"))
    (event,) = news(state, DIED)

    assert "## WIDER WORLD" not in brief(at(state, "city", "wil")).user

    told = brief(at(state, "city", "lena"))

    gone = _section(told.user, "WIDER WORLD")["gone"]
    assert [piece["id"] for piece in gone] == [event.id] and told.news == (event.id,)
    assert "or their family is in the scene" in _section(told.user, "WIDER WORLD")["tell"]


def test_someone_the_story_never_named_is_handed_for_the_scene_to_name(monkeypatch):
    """Mara's partner, whom Tomas knew of and the story never named, died too. The place
    hands that death like any other, marked as someone still to be named, and the scene that
    gives them a name and says it has told it."""
    partner = villager("npc-9", "Mara's partner", 79)
    partner.origin = Origin(kind=OriginKind.ENGINE, ref_id="mara", text="Found a life with Mara.")
    state = passed(monkeypatch, villager("mara", "Mara"), partner, old=("npc-9",))
    state.characters["bram"].age = None
    event = next(e for e in news(state, DIED) if e.subject_ids[0] == "npc-9")
    state = at(state, "village")

    told = brief(state)

    gone = {piece["id"]: piece for piece in _section(told.user, "WIDER WORLD")["gone"]}
    assert gone[event.id]["who"] == {"id": "npc-9", "name": "Mara's partner", "unnamed": True}

    naming = [CharacterChange(id="npc-9", name="Edrik Hale", known_to_player=True)]
    named = apply_delta(state, StateDelta(characters=naming), ctx(), source=NARRATOR).state
    scene = "Edrik lies by the mill wall now, the miller says."
    _, heard = pipeline.settle_lives(named, played=state, shown=told.news, scene=scene)

    assert event.id in heard


def test_what_they_lived_beside_is_told_in_passing_and_is_no_news(monkeypatch):
    """On his farm, forty minutes from the village, Tomas knew of it as it happened: the
    scene that covers that time is told it as something he knows, and nothing is left to
    tell."""
    monkeypatch.setattr(old_age, "chance", lambda lives, from_age, to_age: 1.0)
    state = at(valley(), "farm")
    state.characters["ilse"].age = None
    state = a_year(state, 1)

    told = brief(state)  # the same turn the tick ran in

    assert _section(told.user, "LIVES") == [
        {
            "who": {"id": "bram", "name": "Old Bram"},
            "what": "died of old age",
            "when": "moments ago",
        }
    ]
    assert "## WIDER WORLD" not in told.user and told.news == ()
    bram = next(p for p in _section(told.user, "KNOWN")["people"] if p["id"] == "bram")
    assert bram["status"] == "dead"
    continuity = _section(told.user, "CONTINUITY")
    assert "Old Bram (bram) is dead." in continuity
    assert not any(text.startswith(ONE_LINE) for text in continuity)


def test_a_scene_tells_it_by_naming_the_one_who_died(monkeypatch):
    """C6: a list the narrator fills in under a scene that never says his name tells nothing.
    Once a scene said it, he knows, and the brief has nothing left to say."""
    state = at(passed(monkeypatch), "village")
    (event,) = news(state, DIED)

    same, heard = pipeline.settle_lives(state, [event.id], scene="The mill stands shuttered.")

    assert heard == [] and YOU not in same.lives[event.id].known_by

    scene = "A fresh stone stands by the mill: Old Bram, laid to rest two winters back."
    after, heard = pipeline.settle_lives(state, [event.id], scene=scene)

    assert heard == [event.id]
    told = brief(after, context=ctx(turn=9))
    assert "## WIDER WORLD" not in told.user and told.news == ()
    bram = next(p for p in _section(told.user, "KNOWN")["people"] if p["id"] == "bram")
    assert bram["status"] == "dead"
    assert "Old Bram (bram) is dead." in _section(told.user, "CONTINUITY")


def test_the_narrator_reads_how_long_a_rung_lives_where_climbing_lengthens_life():
    """So a realm's elders are told at ages the record can hold. Ranks that lengthen no life
    say nothing of it, and neither does the world's own count of someone's years."""
    state = valley(villager("elder", "Elder Shan", 300, location_id="farm"))
    state.bible.ladders = [
        PowerLadder(
            id="realms",
            name="realms",
            rungs=[
                Rung(name="Mortal", tier=2, lifespan_years=0),
                Rung(name="Golden Core", tier=4, lifespan_years=500),
            ],
        )
    ]
    state = a_year(state, 1)
    state.scene.present_ids = [YOU, "elder"]
    assert state.characters["elder"].lifespan_years == 410

    told = brief(state)

    (ladder,) = _section(told.system + told.user, "WORLD")["ladders"]
    assert ladder["rungs"] == [
        {"name": "Mortal", "tier": 2},
        {"name": "Golden Core", "tier": 4, "lifespan_years": 500},
    ]
    elder = _section(told.user, "SCENE")["present"][-1]
    assert elder["age"] == 301 and "lifespan_years" not in elder


def test_the_narrator_is_told_what_to_list_for_someone_who_died():
    listed = NarratorOutput.model_fields["told_news"].description
    assert "or under WIDER WORLD" in listed and "or the one who died" in listed
