"""Building what the model nodes read (B5 step 4), from the world state and the turn so far.

Every prompt is a few titled sections of JSON or plain text. What a section holds is chosen in code:
the scene the last turn ended on (R3), the people present, the player character's sheet, what the
engine resolved, the director's pick and the story so far (C3). Hidden truth a character could
never show, such as secrets or a mystery's answer, stays out. Retrieval over older facts and scenes
(C4) comes later; until then the rolling summary and the chapter summaries carry the past.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from engine import bonds, encounters, possessions
from engine import path as path_mod
from engine import talent as talent_mod
from engine.base import DAY, YEAR
from engine.context import Language, TurnContext
from engine.contracts import (
    BeatResolution,
    BeatVerdict,
    DirectorPlan,
    EventSource,
    Intent,
    ItemChange,
    OutcomeClass,
    PictureKind,
    Resolution,
    SceneWeight,
)
from engine.contracts.resolution import Peril, StepResolution
from engine.director import due
from engine.director import weight as scene_weight
from engine.invariants import ancestry
from engine.labels import ago_label, in_label, moment, passage_label, span_label
from engine.limits import is_adult
from engine.resolve import bouts
from engine.resolve.checks import rule_reason
from engine.resolve.powers import growth
from engine.state.bible import PowerLadder
from engine.state.cast import (
    Character,
    CharacterStatus,
    FactionStatus,
    Faith,
    Place,
    PlaceStatus,
    Prominence,
)
from engine.state.records import (
    EventStatus,
    GoalStatus,
    LeadStatus,
    LifeEvent,
    PendingEvent,
    RollRecord,
    WorldChange,
)
from engine.state.sheet import Attitude, TalentStrength
from engine.state.world import WorldState, natural_key
from engine.timekeeping import effect_over
from engine.visibility import believed_status
from engine.world import carriers, journeys, lives, returns, strife
from engine.world.geography import routes_from, scene_ids, together
from engine.world.telling import account, world_change
from graph.language import written_in
from graph.llm import Prompt
from graph.turn import prompts, worn
from graph.turn.form import Asks
from graph.turn.types import RECENT_SCENES, Ending, PastScene

# Facts this important, which the player character knows, always reach the narrator.
KEY_FACT_IMPORTANCE = 4

# What the interpret step needs of the world to judge what it allows (G6, G8), and how people
# get around in it, to judge how long a trip takes (W10).
_INTERPRET_WORLD = {
    "genre",
    "era",
    "physics",
    "extraordinary",
    "rules",
    "peoples",
    "creatures",
    "medicine",
    "travel",
}
_RECORD_NOISE = {
    "known_by",
    "met_by",
    "visited_by",
    "status_history",
    "origin",
    "look_version",
    # W6: the engine's own bookkeeping of people's lives. `last_seen` says the first in words.
    "seen_s",
    "near_s",
    "born_s",
    "solitary",
    "lifespan_years",
}
# Shown by name in a character's `family` (N6) instead of as ids and in-world seconds.
_KIN = {"parent_ids", "expecting"}
_NPC_HIDDEN = {
    "secrets": True,
    "personal_offset_s": True,
    "agenda": {"secret"},
    "sheet": {
        "rulings": True,
        "growth": True,
        "backstory": True,
        "disposition": {"attitudes"},
        # W6: how fast the world takes them to climb is its own bookkeeping.
        "ladders": {"__all__": {"yearly_s"}},
    },
}


def section(title: str, body: Any) -> str:
    text = body if isinstance(body, str) else _json(body)
    return f"## {title}\n{text}"


def render(sections: Iterable[tuple[str, Any]]) -> str:
    return "\n\n".join(section(title, body) for title, body in sections)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _dump(model: Any, exclude: Any = None, include: Any = None) -> dict[str, Any]:
    return model.model_dump(mode="json", include=include, exclude=exclude, exclude_defaults=True)


def present_characters(state: WorldState) -> list[Character]:
    """Who is in the scene with the player character, living, in a stable order. A dead character
    can't be present (C1)."""
    present = []
    for character_id in dict.fromkeys(state.scene.present_ids):
        character = state.characters.get(character_id)
        if character is None or character_id == state.player_id:
            continue
        if character.status is not CharacterStatus.ALIVE:
            continue
        present.append(character)
    return present


def place_name(state: WorldState) -> str | None:
    place_id = state.scene.place_id or state.player.location_id
    place = state.places.get(place_id) if place_id else None
    return place.name if place else None


# R9: how the player character looks, on their record: their appearance, and the line on how
# they come across, which says it too ("a thin disciple in a patched grey robe").
_LOOKS = ("appearance", "description")


def _player_view(state: WorldState, *, looks: bool = True) -> dict[str, Any]:
    """The player character as the record has them. `looks` false leaves out how they look,
    their appearance and how they come across: the narrator is handed those only in a scene
    with reason to show them (R9, `shows_looks`)."""
    hidden = {*_RECORD_NOISE, *_KIN, "personal_offset_s", *(() if looks else _LOOKS)}
    view = {"id": state.player_id} | _dump(state.player, exclude=hidden)
    # C10: what they have is exactly what this lists, so their money and their things show even
    # when they have none.
    resources = state.player.sheet.resources
    held = view.setdefault("sheet", {}).setdefault("resources", {})
    held.pop("currency", None)  # shown beside the amount
    held["money"] = resources.money
    if resources.currency:
        held["currency"] = resources.currency
    # So "nothing" reads as nothing, never as a list left out, and no scene or picture prompt
    # hands them a weapon the premise or the genre suggests (C10, M5).
    held.setdefault("items", [])
    # N6: their body is exactly what this lists, so their health shows even when they are unhurt,
    # and a scene never finds a wound on them that isn't here.
    condition = view["sheet"].setdefault("condition", {})
    condition["health"] = state.player.sheet.condition.health.value
    condition.setdefault("wounds", [])
    # The player character's own family, marking anyone of it they don't know of (C6).
    return view | _family_view(state, state.player, knower=state.player_id)


def _talents_view(state: WorldState) -> dict[str, Any] | None:
    """A4. What the interpret step rules on, gathered in one place so the question can't be
    missed: the player character's talents that reach some things and not others, each thing
    already ruled on with how every one of them stands to it, and the ground their bridges
    already tried. None when they have no such talent: a general one covers everything, with no
    ruling."""
    player = state.player
    theirs = [t for t in talent_mod.talents_of(player) if not t.general]
    if not theirs:
        return None
    talents = []
    for talent in theirs:
        entry: dict[str, Any] = {"id": talent.id, "name": talent.name, "covers": talent.covers}
        if talent.strength is TalentStrength.SLOW:
            entry["weakness"] = True
        talents.append(entry)
    ruled = []
    for ruling in player.sheet.talent_rulings:
        fits = {cover.talent_id: cover.fit.value for cover in ruling.covers}
        # A talent a ruling doesn't list is outside (`engine.talent`).
        stands = {talent.id: fits.get(talent.id, "outside") for talent in theirs}
        ruled.append({"what": ruling.what or ruling.key, "stands": stands})
    view: dict[str, Any] = {"talents": talents, "ruled": ruled}
    if player.sheet.bridges:
        view["bridges"] = [
            {
                "what": bridge.what or bridge.key,
                "talent_id": bridge.talent_id,
                "rests_on": bridge.rests_on,
                "held": bridge.steps > 0,
            }
            for bridge in player.sheet.bridges
        ]
    return view


def _family_view(
    state: WorldState, character: Character, *, knower: str | None = None
) -> dict[str, Any]:
    """N6, W17: a character's parents and children by name, whom they are a couple with, how
    they hold to that partner when someone else courts them (`bonds.faith`), and a child they
    carry, when due. With `knower`, kin that character doesn't know of are marked so."""
    children = [c for c in state.characters.values() if character.id in c.parent_ids]
    family: dict[str, Any] = {}
    for key, ids in (
        ("parents", character.parent_ids),
        ("children", [c.id for c in sorted(children, key=lambda c: natural_key(c.id))]),
    ):
        named = [_kin_name(state, i, knower) for i in ids if i in state.characters]
        if key == "children":
            # W10: a child grows with the world's years, and the scene shows them at that age.
            for kin in named:
                child = state.characters[kin["id"]]
                if child.age is not None and child.alive:
                    kin["age"] = child.age
        if named:
            family[key] = named
    # W17: whom they are a couple with, and how far it has come.
    partners = []
    for other_id in bonds.partners(state, character.id):
        bond = bonds.live(state, character.id, other_id)
        if other_id in state.characters and bond is not None:
            partners.append(_kin_name(state, other_id, knower) | {"bond": bond.stage.value})
    if partners:
        family["partners"] = partners
        if character.id != state.player_id and not state.bible.several_partners:
            # The player character's own heart is the player's (G15).
            family["faith"] = _FAITH[bonds.faith(state, character)]
    expecting = character.expecting
    if expecting is not None and character.alive:
        other = state.characters.get(expecting.other_parent_id or "")
        family["expecting"] = {
            "with": other.name if other is not None else None,
            "due": in_label(max(0, expecting.due_s - state.world_s)),
        }
    return {"family": family} if family else {}


def _kin_name(state: WorldState, character_id: str, knower: str | None) -> dict[str, Any]:
    kin = state.characters[character_id]
    view: dict[str, Any] = {"id": kin.id, "name": kin.name}
    if not kin.alive:
        view["dead"] = True
    if knower is not None and knower not in kin.known_by:
        view["unknown_to_you"] = True
    return view


def _npc_view(character: Character, state: WorldState) -> dict[str, Any]:
    hidden = dict.fromkeys({*_RECORD_NOISE, *_KIN}, True) | _NPC_HIDDEN
    view = {"id": character.id} | _dump(character, exclude=hidden) | _family_view(state, character)
    sheet = view.get("sheet", {})
    if "powers" in sheet:
        # A power kept secret stays out until it is used, and resolve's outcome tells of it then.
        shown = [_dump(power) for power in character.sheet.powers if not power.secret]
        if shown:
            sheet["powers"] = shown
        else:
            del sheet["powers"]
    climbs = {talent_mod.ladder_key(position.ladder_id) for position in character.sheet.ladders}
    if "practice" in sheet and climbs:
        # W6: the hours the world counts toward their next rung are its own bookkeeping too,
        # and their stage on the ladder says how far along they are.
        kept = [work for work in sheet["practice"] if work.get("key") not in climbs]
        if kept:
            sheet["practice"] = kept
        else:
            del sheet["practice"]
    attitude = character.sheet.disposition.attitudes.get(state.player_id)
    if attitude is not None:
        # W17: their heart is told in words, with the bond it belongs to.
        view["toward_you"] = _dump(attitude, exclude=_HEART)
    if heard := _heard_said(state, character.id):
        # W4: what they have only heard said of the player character, and half believe.
        view.setdefault("toward_you", {})["heard_said"] = heard
    if bond := _bond_view(state, character):
        view["bond_with_you"] = bond
    apart = lives.apart_s(state, character)
    if apart is not None and apart >= _APART_S:
        # W6: how long the two have been apart, so years that went by show on them. Whoever
        # they lived near all the while they haven't been apart from.
        view["last_seen"] = ago_label(apart)
    if news := lives.news_of(state, character):
        # W6, C6: what those years brought them that the player character hasn't heard, each
        # piece under its id, so the scene can say which of it it told (`told_news`).
        view["news"] = [
            {"id": event.id} | _life_view(state, event, character.id) for event in news[-_NEWS:]
        ]
    return view


# W6. From how long apart a brief says when the player character last saw someone, from how
# long it says outright that the two meet again (MEETING AGAIN), how much news of one person's
# life it carries, and how much of what the scene's own time brought.
_APART_S = 30 * DAY
_LONG_APART_S = YEAR
_NEWS = 5
_LIVES = 12


def _meeting_again(after: WorldState, shown: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """W6. Whom this scene has the player character meet again after a year or more
    (`_LONG_APART_S`), with how long it has been, and what the scene owes that: it is told as
    a meeting after that long, and where the years brought them news it tells some of it.

    The brief says so on its own, in as many words. `last_seen` under each person wasn't
    enough: in the second live story of a homecoming (2026-11-13) a man came back to his
    village after nine years and a neighbour said they hadn't expected him back so soon."""
    apart, news = [], False
    for view in shown:
        person = after.characters.get(view.get("id", ""))
        gone = lives.apart_s(after, person) if person is not None else None
        if gone is None or "last_seen" not in view:
            continue
        if gone >= _LONG_APART_S:
            apart.append({"who": person.name, "last_seen": ago_label(gone)})
            news = news or bool(view.get("news"))
    if not apart:
        return None
    tell = (
        "This scene is the first time the player character is with them since. Tell it as a "
        "meeting after that long: they are that much older and it shows, the time is spoken "
        "of, and nobody talks as if it had been days."
    )
    if news:
        tell += (
            " The scene shows or says at least one piece of the news under them, naming "
            "whoever it came with. The player character learns it there, from what they see "
            "or are told: the narration never gives it as something they already know."
        )
    return {"people": apart, "tell": tell}


def _life_named(state: WorldState, character_id: str) -> dict[str, Any]:
    """Someone a piece of news is about, by id and name. `unnamed` marks a partner or a child
    the world brought who still goes by its placeholder (`lives.unnamed`)."""
    person = state.characters[character_id]
    named: dict[str, Any] = {"id": person.id, "name": person.name}
    if lives.unnamed(person):
        named["unnamed"] = True
    return named


def _life_view(state: WorldState, event: LifeEvent, of_id: str) -> dict[str, Any]:
    """W6. Something that came to someone in their own life (`engine.world.lives`), as it is
    told of them: what, how long ago, with whom, the child for a birth, and for a death of
    old age the partner they left."""
    view: dict[str, Any] = {
        "what": lives.said(event, of_id),
        "when": ago_label(max(0, state.world_s - event.world_s)),
    }
    other = event.other(of_id)
    if other in state.characters:
        # Whoever died left the other; anything else came to the two together.
        view["leaving" if lives.died(event) == of_id else "with"] = _life_named(state, other)
    if event.child_id in state.characters:
        view["child"] = _life_named(state, event.child_id)
    return view


def _lives_view(after: WorldState, turn: int) -> list[dict[str, Any]]:
    """W6, C6. What the time this turn covered brought the people the player character knows,
    where they were in the place to learn of it as it happened: the latest `_LIVES`, oldest
    first. The time between the scenes counts as this turn's, as it does for FIRED."""
    you, people = after.player_id, after.characters
    told = []
    for event in lives.heard_in(after, turn)[-_LIVES:]:
        # It is told of whichever of the two the player character knows.
        known = [i for i in event.subject_ids if i in people and you in people[i].known_by]
        if known:
            who = known[0]
            told.append({"who": _life_named(after, who)} | _life_view(after, event, who))
    return told


# W6. How much of what the years did to the wider world a brief carries, of each kind, and
# what the scene owes it, said with it: a rule far from what it is about was read past (the
# second live story of a homecoming, 2026-11-13), and words that come with the news cost
# nothing in the scenes that have none.
_CHANGES = 5
_GONE = 8
_LIVED_TELL = (
    "lived came in the time this scene covers, near where the player character lives: they "
    "know of it, so the scene tells it in passing, as part of the time going by."
)
_NEWS_TELL = (
    "news is what the years did to the wider world that the player character hasn't heard. It "
    "is on record: never undo it or add to it. Someone tells it when the player character is "
    "back after a long time, when the scene covers a season or more of living here, when they "
    "ask what has happened or how things stand, or when the talk turns to it, and then it is "
    "this news before anything of your own making. Under told_news, list the id of each piece "
    "the scene showed or said, naming a faction or a place it came to: what a scene leaves out "
    "stays news."
)
_HERE_TELL = (
    "One marked here touched this very place: the scene shows the place as it is now, under "
    "whoever holds it, and the player character finding it so."
)
_BACK_TELL = "This scene has them back after years: it tells at least one piece of it."
_GONE_TELL = (
    "gone are people the player character knew who have died of old age, which they haven't "
    "heard: they lived here, or their family is in the scene. They are dead, so nobody meets "
    "them. The scene shows it or someone says it, a grave, an empty house, another at their "
    "work, when the player character is back after a long time, asks after them or looks for "
    "them, and they learn it there. Under told_news, list the id of each one the scene said "
    "by name had died."
)
# Beside a faction or a place such news changed, wherever the brief shows it as it is now.
_NEWS_TO_YOU = "the player character hasn't heard what became of it: to them it is as it was"


def _changes_view(
    after: WorldState, turn: int, language: Language, *, back: bool = False
) -> dict[str, Any] | None:
    """W6, C6. What the years did to the wider world by the world's own doing
    (`engine.world.strife`), as this scene has it, in the world's own words (S10). `lived` is
    what the time this turn covered brought near where the player character lives: they know
    of it already. `news` is what they haven't heard and this scene can show or tell, each
    under its id so the scene can say which of it it told (`told_news`): what touched the
    place the scene is in (`here`), and what word has reached it. The latest `_CHANGES` of
    each, oldest first. `gone` is who died of old age where the scene is, or whose family is
    in it, of the people the player character knew, which they haven't heard either
    (`lives.gone`): up to `_GONE`, those closest to them first. `tell` says what the scene
    owes them, and with `back`, a scene that has the player character meet people again
    after years, that it tells some of it."""
    place_id = after.player.location_id or after.scene.place_id

    def said(change: WorldChange) -> dict[str, Any]:
        return {
            "what": world_change(after, change, language),
            "when": ago_label(max(0, after.world_s - change.world_s)),
        }

    lived = [said(change) for change in strife.heard_in(after, turn)[-_CHANGES:]]
    news = []
    for change in strife.to_tell(after, place_id)[-_CHANGES:]:
        here = {"here": True} if strife.touched(after, change, place_id) else {}
        news.append({"id": change.id} | said(change) | here)
    gone = []
    family = [c.id for c in present_characters(after)]
    for event in lives.gone(after, place_id, most=_GONE, there=family):
        dead = after.characters[event.subject_ids[0]]
        gone.append(
            {"id": event.id, "who": _life_named(after, dead.id)}
            | _life_view(after, event, dead.id)
            # How old they lived to be: the record keeps the age they died at.
            | ({"aged": dead.age} if dead.age is not None else {})
        )
    if not lived and not news and not gone:
        return None
    view: dict[str, Any] = {}
    tell = []
    if lived:
        view["lived"] = lived
        tell.append(_LIVED_TELL)
    if news:
        view["news"] = news
        tell.append(_NEWS_TELL)
        if any("here" in piece for piece in news):
            tell.append(_HERE_TELL)
    if gone:
        view["gone"] = gone
        tell.append(_GONE_TELL)
    if back and (news or gone):
        tell.append(_BACK_TELL)
    return view | {"tell": " ".join(tell)}


def _dead_to_you(state: WorldState) -> dict[str, str]:
    """W6, C6. Who is dead on record while the player character, who knows of them, takes them
    to be alive or missing, with which: someone old age took far from them, say, whose death
    no scene has told yet (`visibility.believed_status`, as Memory has it)."""
    you = state.player_id
    found = {}
    for c in state.npcs():
        if c.status is not CharacterStatus.DEAD or not (you in c.known_by or you in c.met_by):
            continue
        believed, _ = believed_status(c.status_history, c.status.value, you, initial="alive")
        if believed != CharacterStatus.DEAD.value:
            found[c.id] = believed
    return found


# Beside someone dead whose death the player character hasn't heard of, in KNOWN.
_DEAD_TO_YOU = "dead, which the player character hasn't heard: to them they are {}"


def _news_to_you(state: WorldState) -> set[str]:
    """W6, C6. The factions and places the years changed in a way the player character hasn't
    heard of: the record shows the narrator how they are now, and the brief says beside each
    that it is news (`_NEWS_TO_YOU`)."""
    return {i for change in strife.unheard(state) for i in (*change.faction_ids, *change.place_ids)}


_HEART = {"attraction": True, "heart_moved_s": True}
_FAITH = {
    Faith.STEADFAST: "keeps to their partner: nobody else moves them while that bond holds",
    Faith.TORN: "could be moved by someone else, with their partner standing in the way",
    Faith.ROVING: "lets a partner stand in nobody's way",
}
_PACE = {
    bonds.Pace.SLOW: "slow to give their heart",
    bonds.Pace.STEADY: "neither quick nor slow to give their heart",
    bonds.Pace.QUICK: "quick to give their heart",
}


def _bond_view(state: WorldState, character: Character) -> dict[str, Any] | None:
    """W17. The romance between someone and the player character as the record has it: the
    stage it stands at and since when, or how the last one ended, the one that ended before
    it (`earlier`), and their own heart and pace in words: closed, while someone who ended it
    stays so (`bonds.Closed.ENDED`) and while someone keeps to a partner of their own
    (`bonds.Closed.BOUND`). None when there has been nothing between the two and they
    aren't drawn to the player character."""
    you = state.player_id
    drawn = character.attitude_toward(you).attraction
    bond = bonds.live(state, character.id, you)
    over = bonds.last_over(state, character.id, you)
    ended = None
    if over is not None:
        ended = {
            "ended": over.steps[-1].how if over.steps else "",
            "since": ago_label(max(0, state.world_s - over.since_s)),
        }
    view: dict[str, Any] = {}
    if bond is not None:
        view["stage"] = bond.stage.value
        begun = bool(bond.steps) and bond.steps[-1].turn > 0
        since = ago_label(max(0, state.world_s - bond.since_s))
        view["since"] = since if begun else "before the story began"
        if ended is not None:
            # What was between the two before this one began, which a new start doesn't undo.
            view["earlier"] = ended
    elif ended is not None:
        view |= {"stage": "over"} | ended
    elif drawn == 0:
        return None
    view["their_heart"] = bonds.heart_words(drawn, "you")
    closed = bonds.closed_to(state, character, you)
    if closed is bonds.Closed.ENDED:
        # They made up their mind, and for a good while nothing of the kind moves them.
        view["their_heart"] = "closed to you since they ended it"
    elif closed is bonds.Closed.BOUND:
        theirs = state.characters[bonds.keeps_to(state, character, you) or ""]
        view["their_heart"] = f"closed to you: they keep to {theirs.name}"
    view["their_pace"] = _PACE[bonds.pace(character.id)]
    return view


# How many deeds someone has only heard talk of are told to a model, the gravest first.
_HEARD_SAID = 3


def _heard_said(state: WorldState, character_id: str) -> list[str]:
    """W4: the player character's deeds this person has only heard talk of
    (`Deed.heard_by`), in the world's words, the gravest and then the latest first."""
    heard = [
        deed
        for deed in state.deeds.values()
        if deed.actor_id == state.player_id and character_id in deed.heard_by
    ]
    heard.sort(key=lambda d: (-d.severity, -d.world_s, natural_key(d.id)))
    return [account(state, deed) for deed in heard[:_HEARD_SAID]]


def _fallen_view(state: WorldState) -> list[dict[str, Any]]:
    """N6: the story's earlier player characters whom someone in the scene knew, so those people
    can remember them, and whether each of them knows how it ended (C6)."""
    present = [
        state.characters[cid]
        for cid in state.scene.present_ids
        if cid != state.player_id and cid in state.characters
    ]
    views = []
    for fallen in state.fallen:
        character = state.characters.get(fallen.character_id)
        if character is None:
            continue
        # `met_by` lists who met a character: the fallen, when they were the player character.
        knew = [
            c
            for c in present
            if c.alive
            and c.id != character.id
            and (character.id in c.met_by or character.id in c.sheet.disposition.attitudes)
        ]
        if not knew:
            continue
        died = fallen.ending == "death"
        told = _told_of_death(state, character) if died else set()
        views.append(
            {
                "name": fallen.name,
                "ending": "died" if died else "left the story's centre and lives on",
                "remembered_by": [
                    {"name": c.name, "knows_how_it_ended": not died or c.id in told} for c in knew
                ],
            }
        )
    return views


def _told_of_death(state: WorldState, character: Character) -> set[str]:
    """Who knows how a character died: who saw it or heard of it (`StatusChange.known_by`), and
    who knows of a deed that killed or harmed them, by seeing it or by word reaching them (W2,
    W4)."""
    death = next((s for s in reversed(character.status_history) if s.status == "dead"), None)
    told = set(death.known_by) if death is not None else set()
    for deed in state.deeds.values():
        if character.id in deed.victim_ids:
            told.update(deed.known_by, deed.witness_ids, deed.unnoticed_witness_ids)
    return told


def _knows_place(state: WorldState, place: Place) -> bool:
    you = state.player_id
    return you in place.known_by or you in place.visited_by


def _place_view(state: WorldState, place: Place) -> dict[str, Any]:
    """R8: the scene's place, with the places it lies within that the character knows of (C6),
    outermost last, so a chamber of a buried temple is never told as if it were out in the
    forest around it."""
    view = {"id": place.id} | _dump(place, exclude=_RECORD_NOISE)
    within = [
        {
            "id": outer.id,
            "name": outer.name,
            **({"kind": outer.kind} if outer.kind else {}),
            **({"setting": outer.setting.value} if outer.setting else {}),
        }
        for outer in (state.places[i] for i in ancestry(state.places, place.id)[1:])
        if _knows_place(state, outer)
    ]
    if within:
        view["within"] = within
    return view


def _scene_view(state: WorldState) -> dict[str, Any]:
    frame = state.scene
    place_id = frame.place_id or state.player.location_id
    place = state.places.get(place_id) if place_id else None
    view = {
        "place": _place_view(state, place) if place else None,
        "present": [_npc_view(c, state) for c in present_characters(state)],
        "positions": frame.positions,
        "props": frame.props,
        "encounter": _dump(frame.encounter, exclude={"last_s"}) if frame.encounter else None,
    }
    journey = journeys.under_way(state, place_id)
    if journey is not None and journey.to_id in state.places:
        # W10: a trip that stopped on the way, and what is left of it.
        view["on_the_way"] = {
            "to": journey.to_id,
            "name": state.places[journey.to_id].name,
            "travel_s": journey.left_s,
            "left": span_label(journey.left_s),
        }
    return view


# How many people outside the scene a brief shows as the record has them: those the turn
# names or brings first, then those the record has at the place.
_WHO_ELSE = 8


def _who_else_view(
    before: WorldState,
    after: WorldState,
    intent: Intent | None,
    resolution: Resolution,
    plan: DirectorPlan,
    seen: Sequence[PendingEvent],
    turn: int,
) -> list[dict[str, Any]]:
    """W4, C6, E4. The living people this turn may bring into the scene who weren't in it when
    it began, each as SCENE shows its own, so they are who the record says from their first
    line. Under KNOWN the narrator has such people by name alone: in the first live story
    about it (2026-11-11) the player character walked over to a neighbour who had heard talk
    of a killing, and the scene played him as a friend.

    First those the turn is about, wherever they are: whom the action names, who stood in its
    way or struck back, and the people of an event, a happening or a moment the director
    planned and of a fired event the scene tells. Then those the record has where the scene
    plays (`here`), which is where a trip of this turn took the character, and nowhere on
    record while a trip is still on its way: whoever feels something about the player
    character or has heard talk of them, then whom they know, then the place's key people.
    `stranger` marks someone the player character neither knows nor has met. Where someone is
    stays out unless they are here (C6), save for someone of this place who is away from it
    and coming back (`_away_view`). Someone a step made real is told under OUTCOME's met.

    How long the two have been apart and the news of someone's own life (W6) come only with
    someone the scene can meet: who is here, or whom an event brings.

    Whoever a move in a romance made this turn (`turn`) wrongs who didn't see it is left out,
    wherever the record has them (W17, `bonds.unseen`): this scene can't have them walk in on
    it, and OUTCOME's wrongs says so. Only an event, a happening or a moment that is about
    them brings them, as the world's own doing."""
    you = after.player_id
    people = after.characters
    shown = {you, *(c.id for c in present_characters(before))}
    shown |= {i for step in resolution.steps for i in step.strangers}
    # Whom the world itself brings to the scene: an event's people, never a moment's, which
    # may be about someone far away.
    brought = [i for p in (plan.event, *plan.happenings) if p is not None for i in p.cast_ids]
    brought += [i for event in seen if due.brings(event, after) for i in event.subject_ids]
    came = [*(plan.moment.cast_ids if plan.moment is not None else ()), *brought]
    shown |= set(bonds.unseen(after, turn)) - set(came)
    # A trip that stopped on the way ends the scene in a place only the narrator's scene names.
    on_the_way = any(
        step.trip is not None and (step.trip.to_id or step.trip.to) and not step.trip.arrived
        for step in resolution.steps
    )
    spot = None if on_the_way else after.player.location_id or after.scene.place_id

    def here(character: Character) -> bool:
        where = character.location_id
        return spot is not None and where is not None and together(after, where, spot)

    about: list[str] = []
    for step in intent.steps if intent is not None else []:
        about += [*step.target_ids, *step.facts.opposition_ids]
        about += [exchange.with_id for exchange in step.exchanges if exchange.with_id]
        if step.training is not None and step.training.teacher_id:
            about.append(step.training.teacher_id)
    for done in resolution.steps:
        about += [*done.opponent_ids, *(i for peril in done.perils for i in peril.by_ids)]
    for planned in (plan.event, plan.moment, *plan.happenings):
        if planned is not None:
            about += planned.cast_ids
    for event in seen:
        about += event.subject_ids

    def weight(character: Character) -> int | None:
        attitude = character.sheet.disposition.attitudes.get(you)
        if (attitude is not None and attitude != Attitude()) or _heard_said(after, character.id):
            return 0
        if you in character.known_by or you in character.met_by:
            return 1
        return 2 if character.prominence is Prominence.KEY else None

    around = [(weight(c), natural_key(c.id), c.id) for c in after.npcs() if here(c)]
    about += [i for rank, _, i in sorted(a for a in around if a[0] is not None)]

    others = []
    for character_id in dict.fromkeys(about):
        character = people.get(character_id)
        if character is None or character_id in shown:
            continue
        if character.status is not CharacterStatus.ALIVE:
            continue
        view = _npc_view(character, after)
        if here(character):
            view["here"] = True
        else:
            view.pop("location_id", None)
            away = _away_view(after, character, spot)
            if away is not None:
                view["away"] = away
            if character_id not in brought:
                # W6, C6: the years show, and their news is told, when the two meet. Someone
                # the scene only thinks or speaks of is far away, and so is their news: in the
                # second live story of a homecoming (2026-11-13) a man heard in a city three
                # days off what had come to two of his village.
                view.pop("last_seen", None)
                view.pop("news", None)
        if you not in character.known_by and you not in character.met_by:
            view["stranger"] = True
        others.append(view)
    return others[:_WHO_ELSE]


def _away_view(state: WorldState, character: Character, spot: str | None) -> dict | None:
    """W6. Someone who belongs at the scene's place and is off on a round trip of the world's
    making (`engine.world.returns`): about when they are back, and where they went when the
    player character knows of that place (C6). The people of the place know that much of a
    neighbour, so the scene has something true to say of someone it can't show."""
    trip = returns.trip_of(state, character.id)
    if trip is None or spot is None or not together(state, trip.place_id, spot):
        return None
    away = {"back": in_label(max(0, trip.due_s - state.world_s))}
    place = state.places.get(character.location_id or "")
    if place is not None and _knows_place(state, place):
        away["to"] = place.name
    return away


def _leaving_view(
    state: WorldState, *, turn: int | None = None, scene: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """W11. Who is off to tell a faction what they saw (`carriers.runners`), and whom they go
    to when the player character knows of that faction (C6). With `turn`, for the scene that
    tells that turn, of those it began with (`scene`) and those who saw what it did: each by
    name, since it may not have listed them yet, and whether they got away while it played
    (`gone`). That scene is also told who would run and is held by its fight (`held`,
    `carriers.held`): they are going nowhere while it lasts."""
    leaving = []
    for runner in carriers.runners(state, turn=turn, scene=scene):
        entry: dict[str, Any] = {"id": runner.witness_id}
        if turn is not None:
            entry["who"] = state.characters[runner.witness_id].name
        if state.player_id in state.factions[runner.faction_id].known_by:
            entry["to_tell"] = state.factions[runner.faction_id].name
        if turn is not None:
            entry["gone"] = runner.sets_off_s <= state.world_s
        leaving.append(entry)
    if turn is not None:
        shown = {entry["id"] for entry in leaving}
        for runner in carriers.held(state):
            if runner.witness_id in shown:
                continue
            entry = {"id": runner.witness_id, "who": state.characters[runner.witness_id].name}
            if state.player_id in state.factions[runner.faction_id].known_by:
                entry["to_tell"] = state.factions[runner.faction_id].name
            leaving.append(entry | {"gone": False, "held": True})
    return leaving


def _known_view(state: WorldState) -> dict[str, Any]:
    """Names the player character knows, for mapping misheard names (V3) and for continuity.
    A place the map's routes reach from the scene's comes with what the trip takes (W10)."""
    you = state.player_id
    present = {c.id for c in present_characters(state)}
    away = routes_from(state, state.scene.place_id or state.player.location_id)
    news = _news_to_you(state)
    unheard = _dead_to_you(state)
    people = [
        {
            "id": c.id,
            "name": c.name,
            **({"aliases": c.aliases} if c.aliases else {}),
            **({"status": c.status.value} if c.status is not CharacterStatus.ALIVE else {}),
            **({"status": _DEAD_TO_YOU.format(unheard[c.id])} if c.id in unheard else {}),
        }
        for c in sorted(state.npcs(), key=lambda c: c.id)
        if c.id not in present and (you in c.known_by or you in c.met_by)
    ]
    places = [
        {
            "id": p.id,
            "name": p.name,
            **(
                {"within": p.parent_id}
                if p.parent_id in state.places and _knows_place(state, state.places[p.parent_id])
                else {}
            ),
            **({"setting": p.setting.value} if p.setting else {}),
            **({"status": p.status.value} if p.status is not PlaceStatus.THRIVING else {}),
            **({"news_to_you": _NEWS_TO_YOU} if p.id in news else {}),
            **({"travel_s": away[p.id]} if p.id in away else {}),
        }
        for p in sorted(state.places.values(), key=lambda p: p.id)
        if _knows_place(state, p)
    ]
    factions = [
        {"id": f.id, "name": f.name, "status": f.status.value}
        | ({"news_to_you": _NEWS_TO_YOU} if f.id in news else {})
        for f in sorted(state.factions.values(), key=lambda f: f.id)
        if you in f.known_by
    ]
    return {"people": people, "places": places, "factions": factions}


# G18, G7. Said on a ladder the story can reach past (`engine.path.top_problem`), for the
# narrator alone: beings from above its top can come into a scene with no climb to stop
# beside. It stays the same from turn to turn, so it costs the cache nothing.
_OPEN_ABOVE = (
    "Open: nobody on record stands above {top}. Only if beings stronger than {top} come into "
    "the story, or someone finds what lies beyond it, the scene gives the rung above a name "
    "and update.rungs lists it, with whoever this update brings in who stands on it."
)


def _narrator_world(state: WorldState) -> dict[str, Any]:
    """WORLD as the narrator reads it: the bible, and on each ladder the story can reach past,
    that it is open above its highest rung."""
    view = _world_view(state)
    for shown, ladder in zip(view.get("ladders", ()), state.bible.ladders, strict=True):
        if path_mod.top_problem(state, ladder) is None:
            shown["above"] = _OPEN_ABOVE.format(top=ladder.rungs[-1].name)
    return view


def _world_view(state: WorldState, include: set[str] | None = None) -> dict[str, Any]:
    """The world bible without its hidden answers. The settings a model can't assume are always
    shown, defaults included: how strict physics is (A9), whether the dead can come back (C1) and
    whether news travels instantly (W2)."""
    bible = state.bible
    view = _dump(bible, include=include, exclude={"mysteries", "title"})
    view["physics"] = bible.physics.value
    if include is None or "medicine" in include:
        view.setdefault("medicine", {})["resurrection"] = bible.medicine.resurrection.value
    if include is None or "travel" in include:
        view.setdefault("travel", {})["instant_messages"] = bible.travel.instant_messages
    for ladder in view.get("ladders", ()):
        for rung in ladder.get("rungs", ()):
            # W6: how long a rung lives is said where climbing lengthens life, nowhere else.
            if not rung.get("lifespan_years"):
                rung.pop("lifespan_years", None)
            # G18: when the story put a rung above the top is the record's own.
            rung.pop("added_s", None)
    return view


def _continuity(state: WorldState) -> list[str]:
    """Lines the narrator must never contradict (C1), worked out in code."""
    lines = []
    # W6, C6: whose death the player character hasn't heard of is dead all the same, and to
    # them alive, or missing. One line names them all: a hundred years leave many.
    dead_to_you = _dead_to_you(state)
    for c in sorted(state.npcs(), key=lambda c: c.id):
        if c.status is CharacterStatus.DEAD and c.id not in dead_to_you:
            lines.append(f"{c.name} ({c.id}) is dead.")
    if dead_to_you:
        names = ", ".join(
            f"{c.name} ({c.id})"
            for c in sorted(state.npcs(), key=lambda c: c.id)
            if c.id in dead_to_you
        )
        lines.append(
            f"Dead, though the player character hasn't heard, so to them not dead: {names}."
        )
    # W6, C6: what the years did that the player character hasn't heard of is so, and news.
    news = _news_to_you(state)
    unheard = " The player character hasn't heard: to them it is as it was."
    for f in sorted(state.factions.values(), key=lambda f: f.id):
        if f.status is FactionStatus.DESTROYED:
            line = f"{f.name} ({f.id}) is destroyed and no longer acts as one."
            lines.append(line + (unheard if f.id in news else ""))
    for p in sorted(state.places.values(), key=lambda p: p.id):
        if p.status is not PlaceStatus.THRIVING:
            line = f"{p.name} ({p.id}) is {p.status.value}."
            lines.append(line + (unheard if p.id in news else ""))
    you = state.player_id
    for fact in sorted(state.facts.values(), key=lambda f: (-f.importance, f.id)):
        if fact.importance >= KEY_FACT_IMPORTANCE and you in fact.known_by:
            belief = "" if fact.is_true else " (the character believes this; it isn't true)"
            lines.append(f"{fact.text}{belief}")
    return lines


def _past(state: WorldState, scenes: Sequence[PastScene]) -> dict[str, Any]:
    return {
        "chapters": [
            {"turns": f"{c.from_turn}-{c.to_turn}", "summary": c.summary}
            for c in sorted(state.chapters, key=lambda c: c.index)
        ],
        "summary": state.summary or "(the story is just beginning)",
        "recent_scenes": [
            {"turn": s.turn, "action": s.player_action, "narration": s.narration}
            for s in scenes[-RECENT_SCENES:]
        ],
    }


def _changed_hands(state: WorldState) -> list[str]:
    """C10. The player character's latest gains and losses, and who has what they lost, so no
    model forgets that the coins are gone (`engine.possessions`)."""
    return possessions.prompt_lines(state) or ["(nothing yet)"]


def _goals_and_threads(state: WorldState, goals: WorldState | None = None) -> dict[str, Any]:
    """The player's active goals with their ids, so a model can name one that is over, that the
    scene moved or that the player drops, each with where it stands when a scene said, the open
    threads they know of and the leads on offer (N1, N2). `goals` is the state to take the goals
    from, when it isn't `state`."""
    you = state.player_id
    return {
        "goals": [
            {"id": g.id, "text": g.text} | ({"progress": g.progress} if g.progress else {})
            for g in sorted(
                (state if goals is None else goals).goals.values(), key=lambda g: natural_key(g.id)
            )
            if g.status is GoalStatus.ACTIVE
        ],
        "threads": [
            {"id": t.id, "title": t.title, "stakes": t.stakes, "status": t.status.value}
            for t in sorted(state.threads.values(), key=lambda t: t.id)
            if not t.status.closed and you in t.known_by
        ],
        "leads": [
            {"id": lead.id, "text": lead.text}
            for lead in sorted(state.leads.values(), key=lambda lead: lead.id)
            if lead.status is LeadStatus.OPEN
        ],
    }


# The most of the last scene's text the interpret step reads: its end, where the player acts.
LAST_SCENE_CHARS = 6000


def asks(state: WorldState) -> Asks:
    """B5. What this turn's form asks the interpret step beyond what every turn's does
    (`graph.turn.form`), read from the state: a power over time the player character holds or
    one at work (W10a), a ladder in the world (G18, G20), talents of theirs to rule on (A4), a
    goal they could give up (N2), a thread or a lead open to take up (W16, N1), and a romance
    that could be: the player character and someone else on record are adults (W17, F3)."""
    you = state.player
    open_to_them = _goals_and_threads(state)
    return Asks(
        time=any(power.time is not None for power in you.sheet.powers)
        or any(not effect_over(state, effect) for effect in state.time_effects),
        ladders=bool(state.bible.ladders),
        talents=_talents_view(state) is not None,
        goals=bool(open_to_them["goals"]),
        threads=bool(open_to_them["threads"] or open_to_them["leads"]),
        romance=is_adult(you) and any(c.alive and is_adult(c) for c in state.npcs()),
    )


def interpret_prompt(
    state: WorldState,
    action: str,
    language: Language = Language.EN,
    last_scene: str = "",
    asked: Asks | None = None,
) -> Prompt:
    """B5 step 2: what the interpret model reads to turn the player's words into an `Intent`,
    with the story's language for its notes (S10). `last_scene` is the text of the scene the
    player is answering, so that what it showed counts as there (R2) and "the one she is holding
    out" means something: the scene's record lists only a few things. `asked` is what the turn's
    form asks (`asks`, worked out here when it isn't given): the guide explains only that."""
    frame = state.scene
    asked = asks(state) if asked is None else asked
    told = last_scene.strip()[-LAST_SCENE_CHARS:]
    # The world comes first and alone: it stays the same from turn to turn, so the backend can
    # keep it cached with the system text (`Prompt.stable_chars`).
    seen = _world_view(state, include=_INTERPRET_WORLD)
    if state.bible.ladders:
        # G20: the world's ladders by their rungs' names, lowest first, so "I pass for an
        # outer disciple" names a rung to show. What a rung is worth stays code's.
        seen["ladders"] = [
            {"id": ladder.id, "name": ladder.name, "rungs": [rung.name for rung in ladder.rungs]}
            for ladder in state.bible.ladders
        ]
    world = ("WORLD", seen)
    talents = _talents_view(state)
    you = _player_view(state)
    # A4: what is ruled on and bridged is told once, under TALENTS, with how each talent stands.
    for told_there in ("talent_rulings", "bridges"):
        you["sheet"].pop(told_there, None)
    scene = _scene_view(state)
    if leaving := _leaving_view(state):
        scene["leaving"] = leaving  # W11: the player may go after them before they are gone
    user = render(
        [
            world,
            ("PLAYER CHARACTER", you),
            ("CHANGED HANDS", _changed_hands(state)),
            ("SCENE", scene),
            # As JSON, like the narrator's recent scenes, so no line of it reads as a section.
            ("LAST SCENE", {"narration": told} if told else "(none yet)"),
            ("LAST MOMENT", frame.ended_on or "(the story is just beginning)"),
            ("NOW", _now_view(state)),
            ("KNOWN", _known_view(state)),
            ("GOALS AND THREADS", _goals_and_threads(state)),
            # A4: only for a character whose talents want ruling on, and next to the action,
            # where the player makes their case.
            *([("TALENTS", talents)] if talents is not None else []),
            ("LANGUAGE", written_in(language)),
            ("ACTION", action.strip()),
        ]
    )
    system = prompts.interpret_system(asked)
    return Prompt.build(system, user, stable_chars=len(render([world])))


@dataclass(frozen=True)
class NarrationBrief:
    """Everything the narrate node needs: the prompt, and what its fallbacks use (F4)."""

    system: str
    user: str
    place: str | None
    suggestions: int
    # How much of `user` stays the same from turn to turn (`Prompt.stable_chars`).
    stable_chars: int = 0
    # The story's language, for the template line (S10).
    language: Language = Language.EN
    # R9: whether the scene was handed the player character's appearance, and the worn phrases
    # it was handed to say another way.
    looks: bool = True
    worn: tuple[str, ...] = ()
    # W6: the news the scene was handed to tell, by id, of people's lives and of the wider
    # world: only that can it say it told.
    news: tuple[str, ...] = ()

    def prompt(self, *, cutaway: bool = False) -> Prompt:
        if cutaway:
            # A cutaway is rare, so a cache made for its system text would go unused.
            return Prompt.build(self.system + prompts.CUTAWAY_SYSTEM, self.user)
        return Prompt.build(self.system, self.user, stable_chars=self.stable_chars)

    def template_line(self) -> str:
        here, there = prompts.TEMPLATE_PLACE[self.language]
        where = here.format(place=self.place) if self.place else there
        return prompts.TEMPLATE_LINE[self.language].format(where=where)


def shows_looks(
    *,
    before: WorldState,
    after: WorldState,
    intent: Intent | None,
    resolution: Resolution,
    plan: DirectorPlan,
    words: str | None,
    language: Language,
    ending: Ending | None = None,
) -> bool:
    """R9: whether this scene has reason to show how the player character looks, so the
    narrator is handed their appearance. In Miki's long story the narrator had it on every
    turn and kept using it: "deep black eyes" in 16 scenes of 187.

    A scene has reason to when it introduces the character (an opening has no steps) or ends
    their story, when the turn brings them before someone they have never met, when their look
    changed this turn, when the player's own words are about how they look (`worn.touches`),
    and when the scene gets a picture that shows them, a picture of the scene or their own
    portrait, which is drawn true to their appearance (M5)."""
    you = after.player
    if ending is not None or not resolution.steps:
        return True
    picture = plan.picture
    if picture is not None and (
        picture.kind is PictureKind.SCENE or picture.subject_id == after.player_id
    ):
        return True
    if you.look_version != before.player.look_version or you.appearance != before.player.appearance:
        return True
    if _meets_someone(before, after, intent, resolution, plan):
        return True
    said = " ".join(
        [words or "", *(line for step in (intent.steps if intent else ()) for line in step.lines)]
    )
    return worn.touches(said, you.appearance, language)


def _meets_someone(
    before: WorldState,
    after: WorldState,
    intent: Intent | None,
    resolution: Resolution,
    plan: DirectorPlan,
) -> bool:
    """Whether the turn brings the player character before someone they have never met and who
    wasn't in the scene when it began: a stranger a step made real, whom the action names, or
    someone of an event, a happening or a moment the director planned."""
    you = after.player_id
    there = {you, *before.scene.present_ids}
    new = [i for step in resolution.steps for i in step.strangers]
    for step in intent.steps if intent is not None else ():
        new += step.target_ids
    for planned in (plan.event, plan.moment, *plan.happenings):
        if planned is not None:
            new += planned.cast_ids
    for character_id in dict.fromkeys(new):
        character = after.characters.get(character_id)
        if character is None or character_id in there or not character.alive:
            continue
        if you not in character.met_by:
            return True
    return False


def _names(state: WorldState) -> list[str]:
    """What the story calls its people, its places and the things of its world: people with
    their aliases, places, factions, peoples, creatures, the ladders with their rungs and the
    player character's money. A name has no other way to be said, so it is never wording to
    avoid (R9). What is on the character's own sheet is left to count: a trait or a pair of
    boots said in scene after scene is the wording that wore."""
    bible = state.bible
    names: list[str] = []
    for character in state.characters.values():
        names += [character.name, *character.aliases]
    names += [place.name for place in state.places.values()]
    names += [faction.name for faction in state.factions.values()]
    names += [people.name for people in bible.peoples]
    names += [creature.name for creature in bible.creatures]
    for ladder in bible.ladders:
        names += [ladder.name, *(rung.name for rung in ladder.rungs)]
    names.append(state.player.sheet.resources.currency)
    return [name for name in names if name]


def fired_in_sight(
    fired: Sequence[PendingEvent], after: WorldState, plan: DirectorPlan
) -> list[PendingEvent]:
    """The events that came due while the scene played and that the player character could
    notice (`due.noticed`): what the narrator is told under FIRED. The director tells its own
    events, and the world's events it made the scene's event or a happening, as EVENT and
    HAPPENINGS (W16, E7), so nothing is told twice."""
    told = {
        e.source_id
        for e in (plan.event, *plan.happenings)
        if e is not None and e.source is EventSource.DUE
    }
    return [
        e
        for e in fired
        if due.noticed(e, after)
        and not e.kind.startswith("director.")
        and e.id not in told
        and e.status is not EventStatus.CANCELLED  # it came to nothing, such as a birth
    ]


def narration_brief(
    *,
    before: WorldState,
    after: WorldState,
    ctx: TurnContext,
    intent: Intent | None,
    resolution: Resolution,
    plan: DirectorPlan,
    fired: Sequence[PendingEvent],
    scenes: Sequence[PastScene],
    premise: str = "",
    words: str | None = None,
    ending: Ending | None = None,
    wish: str | None = None,
    left_out: Sequence[str] = (),
) -> NarrationBrief:
    """B5 step 4: the narrator's prompt.

    `before` is the state the turn started from, so the scene picks up where the last one ended
    (R3). `after` is the state once the steps played out, with the time that passed and every
    consequence the engine recorded. `words` are the player's own words for the action, so the
    scene can tell it with their gestures and manner before what comes of it (R1). `ending` is
    set when this scene ends the player character's story (N6), with `wish`, the player's note
    on how, for an ending they chose, or `left_out`, the parts of it the world refused when the
    player ended without them.
    """
    settings = ctx.settings
    tone = before.bible.tone or "the genre's own voice"
    if settings.tone:
        tone = f"{tone}; the player asked for: {settings.tone}"
    style = {
        "genre": before.bible.genre,
        "tone": tone,
        "length": prompts.LENGTHS[settings.narration_length],
        "language": written_in(settings.language),
    }
    content = prompts.content_rules(
        ctx.rating,
        ctx.content_prefs.gore,
        romance=ctx.content_prefs.romance,
        dark_themes=ctx.content_prefs.dark_themes,
    )
    # R9: their appearance only in a scene with reason to show it, and the wording the last
    # scenes repeated, to say another way.
    looks = shows_looks(
        before=before,
        after=after,
        intent=intent,
        resolution=resolution,
        plan=plan,
        words=words,
        language=settings.language,
        ending=ending,
    )
    tired = worn.worn_phrases(scenes, settings.language, _names(after))
    seen = fired_in_sight(fired, after, plan)
    # What stays the same from turn to turn comes first, so the backend can keep it cached with
    # the system text and Gemini bills it at its cached rate (`Prompt.stable_chars`).
    stable: list[tuple[str, Any]] = [
        ("STYLE", style),
        ("CONTENT", content),
        ("WORLD", _narrator_world(before)),
    ]
    scene = _scene_view(before)
    sections: list[tuple[str, Any]] = [
        *stable,
        *([("PREMISE", premise)] if premise and ctx.turn <= 1 else []),
        ("STORY SO FAR", _past(before, scenes)),
        ("CONTINUITY", _continuity(after) or ["(nothing yet)"]),
        # The goals as the director left them, with any the player stated or took up this turn,
        # so the scene can close one it achieves at once (N2).
        ("GOALS AND THREADS", _goals_and_threads(before, goals=after)),
        ("PLAYER CHARACTER", _player_view(after, looks=looks)),
        ("CHANGED HANDS", _changed_hands(after)),
        ("KNOWN", _known_view(after)),
        ("LAST MOMENT", before.scene.ended_on or "(the story is just beginning)"),
        ("SCENE", scene),
    ]
    others = _who_else_view(before, after, intent, resolution, plan, seen, ctx.turn)
    if others:
        # W4, E4: whom the turn may bring into the scene, as the record has them.
        sections.append(("WHO ELSE", others))
    # W6: the news this scene has to tell, of whoever it shows, and whom it meets again
    # after years.
    shown = (*scene["present"], *others)
    news = tuple(dict.fromkeys(n["id"] for view in shown for n in view.get("news", ())))
    if again := _meeting_again(after, shown):
        sections.append(("MEETING AGAIN", again))
    if fallen := _fallen_view(after):
        sections.append(("FALLEN", fallen))

    if intent is None and not resolution.steps and ending is None:
        sections.append(("NOW", _now_view(after)))
        # N6: someone new carries the story on after its ending.
        opening = prompts.SUCCESSION_TASK if before.opening_due else prompts.OPENING_TASK
        if before.opening_due and before.fallen:
            # An heir's story may start years after the ending, once they can act.
            last = before.fallen[-1]
            since = before.world_s - last.world_s
            if since >= DAY:
                sections.append(("ENDED", f"{last.name}'s story ended {ago_label(since)}."))
        sections.append(("TASK", opening))
    else:
        if intent is not None:
            sections.append(("ACTION", _action_view(_as_held(intent, resolution), words)))
        sections.append(("OUTCOME", _outcome_view(resolution, after)))
        sections.append(("TIME", _time_view(before, after, settings.language)))
        if witnesses := _leaving_view(after, turn=ctx.turn, scene=before.scene.present_ids):
            # W11: who runs to tell what they saw, so the scene shows it and the player can act.
            sections.append(("WITNESSES", witnesses))
    # R3: the length follows the scene's weight. It changes from turn to turn, so it stays out
    # of STYLE, which is kept cached.
    weight = scene_weight.told(plan, ending=ending is not None)
    if weight is not SceneWeight.ORDINARY:
        sections.append(("LENGTH", prompts.WEIGHT_LENGTHS[weight][settings.narration_length]))
    if tired:
        sections.append(("WORN", tired))
    if seen:
        sections.append(("FIRED", [_event_view(e) for e in seen]))
    if years := _lives_view(after, ctx.turn):
        sections.append(("LIVES", years))
    if moved := _changes_view(after, ctx.turn, settings.language, back=again is not None):
        # W6: what the years did to the wider world, and of it the news this scene can tell.
        sections.append(("WIDER WORLD", moved))
        told = (*moved.get("news", ()), *moved.get("gone", ()))
        news = (*news, *(piece["id"] for piece in told))
    if plan.event is not None:
        sections.append(("EVENT", _dump(plan.event, exclude=_PLANNED_HIDDEN)))
    if plan.happenings:
        sections.append(
            ("HAPPENINGS", [_dump(h, exclude=_PLANNED_HIDDEN) for h in plan.happenings])
        )
    if plan.moment is not None:
        # W16: a small thing of here and now, when too little time has passed for an event.
        sections.append(("MOMENT", _dump(plan.moment, exclude={"id"})))
    callbacks = [after.threads[t] for t in plan.callbacks if t in after.threads]
    if callbacks:
        sections.append(
            ("CALLBACKS", [{"id": t.id, "title": t.title, "stakes": t.stakes} for t in callbacks])
        )
    talk = _talk_view(plan, after, news=bool(news))
    if talk is not None:
        sections.append(("TALK", talk))
    suggestions = plan.suggestions.count
    kinds = [kind.value for kind in plan.suggestions.kinds][:suggestions]
    asked: dict[str, Any] = {"count": suggestions, "kinds": kinds}
    current = after.threads.get(plan.suggestions.thread_id or "")
    if suggestions and current is not None and "thread" in kinds:
        asked["thread"] = {"id": current.id, "title": current.title}  # what thread choices follow
    sections.append(("SUGGESTIONS", asked))
    # The cover, the story's poster, is drawn from its premise, never from this scene, so the
    # narrator writes it no image prompt (M1, Miki 2026-11-07, `media.briefs.cover_brief`).
    if plan.picture is not None and plan.picture.kind is not PictureKind.COVER:
        subject = plan.picture.subject_id
        sections.append(
            (
                "PICTURE",
                {
                    "kind": plan.picture.kind.value,
                    "subject": _subject_name(after, subject) if subject else None,
                    "why": plan.picture.reason,
                },
            )
        )
    if ending is not None:
        told_ending: dict[str, Any] = {"kind": ending.kind}
        if wish:
            told_ending["wish"] = wish
        if left_out:
            told_ending["left_out"] = list(left_out)
        sections.append(("ENDING", told_ending))
        task = prompts.DEATH_TASK if ending.kind == "death" else prompts.EPILOGUE_TASK
        sections.append(("TASK", task))
    return NarrationBrief(
        system=prompts.NARRATOR_SYSTEM,
        user=render(sections),
        place=place_name(after),
        suggestions=suggestions,
        stable_chars=len(render(stable)),
        language=settings.language,
        looks=looks,
        worn=tuple(tired),
        news=news,
    )


def _as_held(intent: Intent, resolution: Resolution) -> Intent:
    """W1. The plan with each blow of an agreed bout aimed as its terms held it, so a sparring
    blow the interpret step read as a killing one isn't told as an attempt on someone's life."""
    fought = {s.index: s.bout for s in resolution.steps if s.bout is not None}
    steps = list(intent.steps)
    for index, bout in fought.items():
        if index < len(steps):
            aim = bouts.held(bout.terms, steps[index].aim)
            steps[index] = steps[index].model_copy(update={"aim": aim})
    return intent.model_copy(update={"steps": steps}) if fought else intent


def _action_view(intent: Intent, words: str | None) -> dict[str, Any]:
    """The player's own words first, then what the interpret step read in them (R1, R7)."""
    view = _dump(intent, exclude={"actor_id"})
    if words and words.strip():
        return {"words": words.strip(), **view}
    return view


def _throw_view(roll: RollRecord | None) -> dict[str, Any]:
    """A3. A throw of the character's own dice as the narrator is told it: how it fell, what it
    was up against and whether a miss could kill. No dice, numbers or odds, and nothing for the
    world's die, whose answer the step's why already gives."""
    thrown = roll.throw if roll is not None else None
    if thrown is None or thrown.of_the_world:
        return {}
    view: dict[str, Any] = {"fell": thrown.mark.value}
    if thrown.against:
        view["against"] = thrown.against
    if thrown.deadly:
        view["deadly"] = True
    return view


def _struck_view(peril: Peril) -> dict[str, Any]:
    """N6: what struck back, with how the character's defence fared when they threw one."""
    view: dict[str, Any] = {
        "by": peril.by,
        "means": peril.aim.value,
        "harm": peril.harm.value,
        "why": peril.reason,
    }
    defence = _throw_view(peril.roll)
    if defence:
        view["defence"] = defence
    return view


def _trip_view(step: StepResolution, state: WorldState) -> dict[str, Any]:
    """W10: where the step took the character, as code followed it: the place they reached, or
    how much of the way is left when something stopped them before. `arrived` is left out for
    a trip the player timed over ground no route covers: the scene says how far they got.
    `first_visit` marks an arrival somewhere they have never been.
    """
    trip = step.trip
    assert trip is not None
    place = state.places.get(trip.to_id) if trip.to_id else None
    view: dict[str, Any] = {"to": place.name if place is not None else trip.to}
    if place is not None:
        view["to_id"] = place.id
    if trip.arrived is not None:
        view["arrived"] = trip.arrived
    journey = state.journey
    if (
        trip.arrived is False
        and journey is not None
        and trip.to_id in (journey.to_id, journey.from_id)
    ):
        left = journey.left_s if trip.to_id == journey.to_id else max(1, journey.done_s)
        view["left"] = span_label(left)
    if trip.arrived and trip.first_visit:
        view["first_visit"] = True
    return view


def _talk_view(
    plan: DirectorPlan, state: WorldState, *, news: bool = False
) -> dict[str, Any] | None:
    """W2. The talk of the place this scene may carry, if it has room for it: something the
    place is saying that the character hasn't heard, in the world's words (`saying`), or, when
    the record holds nothing new to them, talk of the narrator's own making (`own`). `asked`
    marks talk the player character asked or listened for this turn, which the scene tells.

    With `news`, someone the scene shows has news of their own life the player character
    hasn't heard (W6), and that is what there is to hear in place of talk made up: in the first
    live story of a homecoming (2026-11-13) a man asked his neighbours how the ten years had
    been, and the scene answered with talk of its own making about him."""
    talk = plan.talk
    if talk is None:
        return None
    asked = {"asked": True} if talk.asked else {}
    if talk.rumor_id is None:
        return ({"news": True} if news else {"own": True}) | asked
    rumor = state.rumors.get(talk.rumor_id)
    return {"saying": rumor.text} | asked if rumor is not None else None


def wronged_view(step: StepResolution, state: WorldState) -> list[dict[str, Any]]:
    """W17. Whom a step's move in a romance wrongs (`Deed.wronged_ids`): whoever is a couple
    with either of the two, by name, and `saw_it`: whether they were there to see it, by the
    deed as the world recorded it. The others know nothing of it yet (W2), and the scene is
    told so of each in as many words: left unsaid, the real model walked a wife in on it.

    Someone who saw it from among the people around, while the step took the player character
    on to another place, gets `stayed_in`, the place it was done at: they saw it there and
    are still there, and the door keeps them out of the scene where it ends (W4). Told only
    `saw_it`, the real model listed a husband among those present forty minutes on."""
    proposed = next((d for d in step.deeds if d.wronged_ids), None)
    if proposed is None:
        return []
    recorded = max(
        (
            d
            for d in state.deeds.values()
            if d.text == proposed.text and d.wronged_ids == proposed.wronged_ids
        ),
        key=lambda d: (d.world_s, natural_key(d.id)),
        default=None,
    )
    saw = set(recorded.witness_ids) if recorded is not None else set()
    cast, spot = scene_ids(state), state.player.location_id
    wronged = []
    for who in proposed.wronged_ids:
        person = state.characters.get(who)
        if person is None:
            continue
        view: dict[str, Any] = {"id": who, "who": person.name, "saw_it": who in saw}
        done_at = state.places.get(recorded.place_id or "") if recorded is not None else None
        behind = spot is not None and not together(state, person.location_id, spot)
        if who in saw and who not in cast and behind and done_at is not None:
            view["stayed_in"] = done_at.name
        wronged.append(view)
    return wronged


# G18, G7. Said beside a step that stopped on a ladder's highest rung, where the story can
# reach past it (`engine.path.top_problem`): the moment the narrator has to know that it can.
# The rung is the scene's to name and the engine's to accept (`engine.apply`).
_BEYOND_TELL = (
    "How far {ladder} goes is open: nobody on record stands above {top}. This step still "
    "fails. If the scene shows that something lies above {top} and gives that rung a name, "
    "list it under update.rungs. Reaching it would be a climb of its own."
)


def _stopped_at_top(reason: str, state: WorldState, ladder: PowerLadder) -> bool:
    """Whether a step was ruled out because the ladder ends at its highest rung: a climb from
    it (`growth.no_rung_above`), or anything an open rule that holds the ladder there stopped
    (`engine.path.ceilings`), which is how a model that reads the player's words files a
    reach past the top when the world has such a rule."""
    if reason == growth.no_rung_above(ladder):
        return True
    return any(
        not rule.fixed and reason == rule_reason(rule.text)
        for rule in path_mod.ceilings(state, ladder)
    )


def _beyond(step: StepResolution, state: WorldState) -> str | None:
    """G18, G7. What the narrator is told beside a step that stopped at the top of a ladder
    the story can pass, or None for any other step."""
    if step.outcome_class is not OutcomeClass.RULED_OUT:
        return None
    for ladder in state.bible.ladders:
        if not _stopped_at_top(step.reason, state, ladder):
            continue
        if path_mod.top_problem(state, ladder) is None:
            return _BEYOND_TELL.format(ladder=ladder.name, top=ladder.rungs[-1].name)
    return None


def _outcome_view(resolution: Resolution, state: WorldState) -> dict[str, Any]:
    steps = []
    for step in resolution.steps:
        view: dict[str, Any] = {
            "step": step.text,
            "class": step.outcome_class.value,
            "result": step.result.value,
            "why": step.reason,
        }
        if beyond := _beyond(step, state):
            view["beyond"] = beyond
        thrown = _throw_view(step.roll)
        if thrown:
            # A3: how the dice fell and what they were up against, never the odds.
            view["throw"] = thrown
        if step.extra:
            view["extra"] = step.extra
        if step.hand:
            # R4: what they did it with and how well they have it, so a novice who succeeds
            # still looks a novice.
            view["hand"] = step.hand
        if step.drew_on:
            # R1, A3: their own powers and techniques the step used, which work as they know
            # them to, so a miss is told in what stood in the way.
            view["drew_on"] = step.drew_on
        if step.costs:
            view["costs"] = [c.text for c in step.costs]
        if step.effects.items and not step.interrupted:
            # C10: what the step moved, already recorded; the narrator shows it, never again. A
            # step an event cut short moved nothing.
            view["changed_hands"] = [_moved(change) for change in step.effects.items]
        if any(beat.verdict is not BeatVerdict.HOLDS for beat in step.beats):
            # R2: the beats as checked, in order, when one found something new or came up empty.
            # A step stops at its empty beat, so the beats after it never happen.
            view["beats"] = [_beat_view(beat) for beat in step.beats]
        if step.chain:
            view["chain"] = [
                {"link": link.text, "holds": link.holds, "why": link.reason} for link in step.chain
            ]
        if step.strangers:
            # F1, W2: who this step made real, so the narrator meets them under these ids.
            made: dict[str, Any] = {}
            for change in step.effects.characters:  # the first change per id is the one that
                made.setdefault(change.id, change)  # made them; a kill or a wound comes after
            view["met"] = [
                {"id": i, "who": made[i].name, "about": made[i].description}
                for i in step.strangers
                if i in made
            ]
        if step.perils:
            # N6: what struck back at the player character after their step, in order.
            view["struck"] = [_struck_view(p) for p in step.perils]
        if wronged := wronged_view(step, state):
            # W17: whose partner the move was made with or by, and who of them saw it.
            view["wrongs"] = wronged
        if step.bout is not None:
            # W1: fought in a bout both sides agreed to, under these terms: no attack on anyone.
            view["bout"] = step.bout.terms.value
        if step.broke_terms:
            view["broke_terms"] = True  # W1: a blow went beyond them, and the bout is over
        if step.interrupted:
            view["interrupted"] = True
        if step.trip is not None and (step.trip.to_id or step.trip.to):
            view["trip"] = _trip_view(step, state)
        steps.append(view)
    outcome: dict[str, Any] = {"steps": steps}
    encounter, facing = state.scene.encounter, encounters.facing(state)
    if encounter is not None and facing:
        # W10: the fight, chase or talks still on as the scene ends, which the telling never ends.
        outcome["still_on"] = {"kind": encounter.kind.value, "with": facing}
        if encounter.bout is not None:
            outcome["still_on"]["bout"] = encounter.bout.terms.value
    if resolution.stopped_at_step is not None:
        outcome["stopped_at_step"] = resolution.stopped_at_step
        outcome["stop_reason"] = resolution.stop_reason.value if resolution.stop_reason else None
    if resolution.unplayed:
        outcome["unplayed"] = resolution.unplayed
    if resolution.canon:
        outcome["now_canon"] = resolution.canon
    # A9. Rulings made this turn: on the player's theories, and those a step settled by trying.
    rulings = [*resolution.rulings]
    rulings += [r for s in resolution.steps for c in s.effects.characters for r in c.rulings]
    if rulings:
        outcome["rulings"] = [_dump(r) for r in rulings]
    if resolution.claims:
        outcome["backstory"] = [
            {"claim": c.text, "recorded": c.accepted, "why": c.reason} for c in resolution.claims
        ]
    return outcome


def _moved(change: ItemChange) -> dict[str, Any]:
    view: dict[str, Any] = {
        "what": change.name,
        "amount": change.quantity,
        "from": change.from_id,
        "to": change.to_id,
    }
    if change.money:
        view["money"] = True
    return view


def _beat_view(beat: BeatResolution) -> dict[str, Any]:
    view: dict[str, Any] = {"beat": beat.text, "uses": beat.thing, "check": beat.verdict.value}
    if beat.reason:
        view["why"] = beat.reason
    return view


def _now_view(state: WorldState) -> dict[str, Any]:
    """W10. Where the world's clock stands, so the models judge times and tell the hour as the
    clock shows it."""
    return moment(state.bible.calendar, state.world_s).model_dump()


def _time_view(before: WorldState, after: WorldState, language: Language) -> dict[str, Any]:
    """W10. When the scene began and what time it is now, with the time the action took: the
    telling keeps to the clock. `heading` is what the player reads over a scene that hours or
    days passed in, in the story's language (`labels.passage_label`), so the telling doesn't
    say it twice."""
    elapsed = after.world_s - before.world_s
    lived = after.player.personal_s(after.world_s) - before.player.personal_s(before.world_s)
    view: dict[str, Any] = {
        "began": _now_view(before),
        "now": _now_view(after),
        "passed": span_label(elapsed),
        "world_seconds_passed": elapsed,
    }
    if lived != elapsed:
        view["your_seconds_lived"] = lived
    heading = passage_label(after.bible.calendar, before.world_s, after.world_s, language)
    if heading is not None:
        view["heading"] = heading
    return view


# Bookkeeping in a `PlannedEvent` that the narrator has no use for.
_PLANNED_HIDDEN = {"source", "source_id", "card_id", "plays_out_s"}


def _event_view(event: PendingEvent) -> dict[str, Any]:
    return {
        "title": event.title or event.kind,
        "kind": event.kind,
        "needs_you": event.needs_player,
    }


def _subject_name(state: WorldState, subject_id: str) -> str:
    for records in (state.characters, state.places, state.deeds, state.threads):
        record = records.get(subject_id)
        if record is not None:
            return (
                getattr(record, "name", None)
                or getattr(record, "title", None)
                or getattr(record, "text", subject_id)
            )
    return subject_id


def chapter_prompt(scenes: Sequence[PastScene], language: Language = Language.EN) -> Prompt:
    """C3: the summarizer's prompt for one chapter of scenes, summarized in the story's language
    (S10)."""
    body = [{"turn": s.turn, "action": s.player_action, "narration": s.narration} for s in scenes]
    return Prompt.build(
        prompts.SUMMARIZER_SYSTEM, render([("LANGUAGE", written_in(language)), ("SCENES", body)])
    )
