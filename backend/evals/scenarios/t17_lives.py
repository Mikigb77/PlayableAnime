"""T17's evals of other people's lives (W6, W10): the people the story knows lead lives of their
own while it is elsewhere.

Code decides what the years bring each of them and who has heard of it (`engine.world.lives`):
the checks here read the record. Whether a scene of meeting again shows those years, and makes
up nothing the record doesn't hold, is the judge's in live mode.
"""

from __future__ import annotations

from collections import Counter

from engine import bonds
from engine.base import DAY, MINUTE, YEAR
from engine.context import EventFrequency, StorySettings
from engine.contracts import ActionKind, CharacterChange, Intent, SceneEnd, StateDelta
from engine.invariants import check_state
from engine.labels import ago_label
from engine.state import LifeEvent, LifeKind, SceneFrame, WorldState
from engine.visibility import memory_view
from engine.world import lives
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import act, plan, step
from graph.llm import Node

scenario = REGISTRY.scenario

YOU = "tomas"
CALM = StorySettings(event_frequency=EventFrequency.CALM)
TEN = 10 * YEAR + 30 * DAY  # ten years and a few weeks, so ten whole years have gone by
MONTH = 30 * DAY
# A long stretch stops for whatever needs the player (E7), so the years take a few turns. A
# live run plays fewer: each is a scene from the real model.
TURNS, LIVE_TURNS = 40, 8
SPARE_NAMES = (
    "Edrik Hale",
    "Lena Marsh",
    "Tobin Reed",
    "Ysolde Carr",
    "Garrick Moor",
    "Wynn Alder",
)
IN_HARROWGATE = "Tomas has taken a room over a mason's yard in Harrowgate, three days from home."
ON_THE_LANE = "Tomas walks back up the mill lane in Millbrook, a pack on his shoulder."


def neighbours() -> dict[str, int | None]:
    """Everyone Tomas knows in Millbrook as the story opens, with their age then."""
    people = worlds.millbrook_he_knows().characters
    return {i: c.age for i, c in people.items() if i != YOU}


def in_harrowgate(state: WorldState) -> None:
    """Tomas has left the valley for the city, where no news of Millbrook reaches him."""
    state.characters[YOU].location_id = "city"
    state.scene = SceneFrame(place_id="city", present_ids=[YOU], ended_on=IN_HARROWGATE)


def span(left: int) -> tuple[str, int]:
    """A stretch still to live through, in the words a player would write and in seconds."""
    years = left // YEAR
    if years > 1:
        return f"{years} more years", years * YEAR
    if years == 1:
        return "one more year", YEAR
    days = max(1, left // DAY)
    return f"{days} more days", days * DAY


async def live_there(
    story: Story, length: int, *, where: str, turns: int
) -> list[tuple[Played, str]]:
    """The player lets `length` go by where they are, a stretch at a time, going back to it
    whenever the world stops it for something. Each turn comes back with the brief its
    narrator read (deterministic mode)."""
    until = story.state.world_s + length
    played: list[tuple[Played, str]] = []
    while (left := until - story.state.world_s) >= DAY and len(played) < turns:
        words, seconds = span(left)
        action = f"I keep to my work {where} for {words}"
        skip = act(f"Work {where} for {words}", "work", ActionKind.TIME_SKIP, seconds)
        turn = await story.act(action, skip)
        played.append((turn, story.prompt(Node.NARRATOR)))
    return played


def came(state: WorldState, who: str) -> list[LifeEvent]:
    return lives.of(state, who)


def heard(state: WorldState) -> list[LifeEvent]:
    return [e for e in state.lives.values() if YOU in e.known_by]


def life_lines(state: WorldState, who: str) -> list[str]:
    """What Memory says the years brought someone (C6): the lines of their entry that news of
    their life adds."""
    without = state.model_copy(update={"lives": {}})

    def entry(of: WorldState) -> list[str]:
        return next((p.lines for p in memory_view(of).people if p.id == who), [])

    plain = entry(without)
    return [line for line in entry(state) if line not in plain]


def of_age(state: WorldState, event: LifeEvent, known: dict[str, int | None]) -> bool:
    """Whether everyone a partner or a child came to was a recorded adult when it did (F3)."""
    for who in event.subject_ids:
        person = state.characters[who]
        if who in known:
            then = None if known[who] is None else known[who] + event.world_s // YEAR
        else:
            then = (
                None if person.age is None else person.age - (state.world_s - event.world_s) // YEAR
            )
        if then is None or then < 18:
            return False
    return True


def unnamed_in(state: WorldState, events: list[LifeEvent]) -> list[str]:
    """Whoever some news is about that still goes by the name the world gave them."""
    ids = dict.fromkeys(i for e in events for i in (*e.subject_ids, e.child_id) if i)
    return [i for i in ids if lives.unnamed(state.characters[i])]


def home_again(present: list[str]):
    def change(state: WorldState) -> None:
        state.characters[YOU].location_id = "village"
        state.scene = SceneFrame(
            place_id="village", present_ids=[YOU, *present], ended_on=ON_THE_LANE
        )

    return change


def greet(present: list[str]) -> Intent:
    return plan(
        step(
            "greet the people on the mill lane and ask how they have been",
            ActionKind.CONVERSATION,
            20 * MINUTE,
            verb="greet",
            target_ids=present,
        )
    )


def named_scene(present: list[str], names: dict[str, str]) -> dict:
    """A scripted scene of the meeting that gives each partner or child the world brought a
    name, under their own id, as the narrator is told to."""
    naming = [CharacterChange(id=i, name=n, known_to_player=True) for i, n in names.items()]
    end = SceneEnd(
        ended_on="The lane has filled with people who want a look at him.",
        place_id="village",
        present_ids=[YOU, *present],
    )
    return {
        "narration": "(scripted) Ten years show on every face that turns toward Tomas.",
        "suggestions": [],
        "update": StateDelta(characters=naming, scene_end=end).model_dump(mode="json"),
    }


def on_record(state: WorldState, present: list[str]) -> str:
    """What the record holds of the people in the scene, for the judge: the story is the eval's
    own (T16)."""
    away = ago_label(state.world_s - (state.characters[present[0]].seen_s or 0))
    lines = [f"Tomas last saw the people of Millbrook {away}, and nobody sent word since."]
    for who in present:
        person = state.characters[who]
        told = []
        for event in came(state, who):
            other = state.characters.get(event.other(who) or "")
            said = lives.said(event, who)
            when = ago_label(state.world_s - event.world_s)
            if other is not None and event.kind is not LifeKind.CHILD:
                name = "someone the scene may name" if lives.unnamed(other) else other.name
                said += f" ({name})"
            child = state.characters.get(event.child_id or "")
            if child is not None:
                said += f" (the child is {child.age} now)"
            told.append(f"{said}, {when}")
        age = f", {person.age} now" if person.age is not None else ""
        lines.append(f"{person.name}{age}: {'; '.join(told) or 'nothing came to them'}.")
    return "\n".join(lines)


@scenario(
    "t17.years-away",
    suite="T17",
    title="Ten years away",
    requirements=("W6", "W10", "C6", "N6", "W17", "F3", "T17"),
    passes_when=(
        "A man leaves his village for a city three days off and comes home ten years later. "
        "A month away brings nobody anything. Over the ten years everyone on record grows ten "
        "years older, and across many stories people find partners, marry, have children, "
        "part, make friends and fall out, while many are found just as they were left: nothing "
        "is made to happen. Only recorded adults find a partner or have a child, someone sworn "
        "to a life alone is given no partner, and the world gives the player character "
        "nothing of the kind. Far away he hears none of it, and Memory holds none of it. The "
        "scene he meets someone in is told how long it has been and what the years brought "
        "them, and after it he has heard it and Memory tells it with its day. A partner or a "
        "child the world brought is named by the story under their own id. Someone who stays "
        "in the valley instead hears what comes to his neighbours as it happens"
    ),
)
async def years_away(ev: Eval) -> None:
    known = neighbours()
    # A month away: no time for any of it (Miki, 2026-11-13).
    in_a_month = 0
    for seed in ev.seeds(24, live=0):
        story = ev.story(
            worlds.millbrook_he_knows(), seed=f"{seed}/month", settings=CALM, under_way=True
        )
        story.change(in_harrowgate)
        await live_there(story, MONTH, where="in Harrowgate", turns=TURNS)
        in_a_month += len(story.state.lives)
    ev.check("a month away brings nobody anything", in_a_month == 0, str(in_a_month), live=False)

    kinds: Counter[str] = Counter()
    as_left = people = 0
    for seed in ev.seeds(24, live=1):
        story = ev.story(worlds.millbrook_he_knows(), seed=seed, settings=CALM, under_way=True)
        story.change(in_harrowgate)
        left_s = story.state.world_s
        await live_there(story, TEN, where="in Harrowgate", turns=LIVE_TURNS if ev.live else TURNS)
        state = story.state
        years = (state.world_s - left_s) // YEAR
        ev.metric(f"years away, {seed}", years)
        ev.check("ten years went by", years == 10, f"{seed}: {years}", live=False)
        ev.check(
            "everyone on record is as many years older as went by",
            all(
                state.characters[who].age == age + years
                for who, age in known.items()
                if age is not None and state.characters[who].alive
            )
            and state.characters[YOU].age
            == worlds.millbrook_he_knows().characters[YOU].age + years,
            f"{seed}: {years} years, { {i: state.characters[i].age for i in known} }",
        )
        events = list(state.lives.values())
        kinds.update(e.kind.value for e in events)
        quiet = [who for who in known if not came(state, who)]
        as_left += len(quiet)
        people += len(known)
        ev.check(
            "far away he hears none of it, and Memory holds none of it",
            not heard(state) and not any(life_lines(state, who) for who in known),
            f"{seed}: {[e.id for e in heard(state)]}",
        )
        ev.check(
            "the world gives the player character no partner, child, friend or foe of its own",
            not any(YOU in (*e.subject_ids, e.by_id) for e in events)
            and bonds.partners(state, YOU) == []
            and not any(YOU in c.parent_ids for c in state.characters.values()),
            f"{seed}: {[e.id for e in events if YOU in e.subject_ids]}",
        )
        with_partner = [e for e in events if e.kind in (LifeKind.PAIRED, LifeKind.CHILD)]
        ev.check(
            "only recorded adults find a partner or have a child",
            all(of_age(state, e, known) for e in with_partner),
            f"{seed}: {[(e.kind.value, e.subject_ids) for e in with_partner]}",
        )
        ev.check(
            "someone sworn to a life alone is given no partner",
            bonds.partners(state, worlds.ALDITH) == [],
            f"{seed}: {bonds.partners(state, worlds.ALDITH)}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}")

        # Home again. He meets whoever the years brought the most, and someone they brought
        # nothing where there is one.
        at_home = [w for w in known if state.characters[w].alive]
        most = max(at_home, key=lambda w: (len(came(state, w)), w))
        present = [most, *quiet[:1]] if quiet[:1] != [most] else [most]
        news = came(state, most)
        story.change(home_again(present))
        before = story.state
        names = dict(zip(unnamed_in(before, news), SPARE_NAMES, strict=False))
        was = len(before.characters)
        met = await story.act(
            "I greet the people on the mill lane and ask how they have all been",
            greet(present),
            narration=None if ev.live else named_scene(present, names),
        )
        state = story.state
        away = ago_label(before.world_s - (before.characters[most].seen_s or 0))
        brief = story.prompt(Node.NARRATOR)
        ev.check(
            "the scene is told how long it has been and what the years brought them",
            f'"last_seen":"{away}"' in brief
            and brief.count('"what":"') >= min(len(news), 5)
            and (not news or '"news":[' in brief),
            f"{seed}: {away}, {len(news)} for {most}",
            live=False,
        )
        ev.check(
            "after the scene he has heard what came to the people in it, and has seen them",
            all(YOU in e.known_by for who in present for e in came(state, who))
            and all(state.characters[who].seen_s == state.world_s for who in present),
            f"{seed}: {[e.id for who in present for e in lives.unheard(state, who)]}",
        )
        told = life_lines(state, most)
        ev.check(
            "Memory tells what he heard of them, each with its day",
            len(told) == min(len(news), 6) and all("day " in line for line in told),
            f"{seed}: {told} of {len(news)}",
        )
        elsewhere = [e for e in state.lives.values() if not set(e.subject_ids) & set(present)]
        ev.check(
            "what came to people he hasn't met yet is still unheard",
            not any(YOU in e.known_by for e in elsewhere),
            f"{seed}: {[e.id for e in elsewhere if YOU in e.known_by]}",
        )
        ev.check(
            "a partner or a child the world brought is named by the story under their own id",
            all(
                state.characters[who].name == name
                and not lives.unnamed(state.characters[who])
                and YOU in state.characters[who].known_by
                for who, name in names.items()
            )
            and len(state.characters) == was
            and all(name in " ".join(told) for name in list(names.values())[:1]),
            f"{seed}: {names}, {told}",
            live=False,
        )
        if ev.live:
            still = unnamed_in(state, news)
            ev.metric(f"named in the scene, {seed}", f"{len(names) - len(still)} of {len(names)}")
            ev.metric(f"people the scene added, {seed}", len(state.characters) - was)
        must = [
            "The scene is told as a return after the years CONTEXT says: the people Tomas "
            "meets are older or changed by the time, or the years are spoken of",
        ]
        if news:
            must.append(
                "At least one thing CONTEXT says came to someone in the scene is shown or "
                "said in it"
            )
        await ev.judge(
            "meeting again after ten years",
            Rubric(
                must=tuple(must),
                must_not=(
                    "Someone in the scene is given a partner, a wedding, a child or a parting "
                    "that CONTEXT doesn't say came to them",
                    "Tomas knows what the years brought someone before anyone shows or tells him",
                    "A child CONTEXT gives an age is told as years younger or older than that",
                ),
            ),
            met,
            context=on_record(before, present),
        )

    ev.metric("what ten years brought", dict(kinds))
    ev.metric("found as they were left", f"{as_left} of {people}")
    ev.check(
        "over ten years people find partners, marry, have children and make friends or foes",
        all(kinds[k.value] > 0 for k in (LifeKind.PAIRED, LifeKind.MARRIED, LifeKind.CHILD))
        and kinds[LifeKind.FRIENDS.value] + kinds[LifeKind.FELL_OUT.value] > 0,
        str(dict(kinds)),
        live=False,
    )
    ev.check(
        "many are found just as they were left: nothing is made to happen",
        people > 0 and as_left * 5 >= people,
        f"{as_left} of {people}",
        live=False,
    )

    # Someone who stays in the valley hears what comes to his neighbours as it happens.
    told_of = 0
    for seed in ev.seeds(12, live=0):
        story = ev.story(
            worlds.millbrook_he_knows(), seed=f"{seed}/home", settings=CALM, under_way=True
        )
        played = await live_there(story, TEN, where="on the farm", turns=TURNS)
        state = story.state
        events = list(state.lives.values())
        ev.check(
            "living among them, he hears what comes to people as it happens",
            all(YOU in e.known_by for e in events),
            f"{seed}: {[e.id for e in events if YOU not in e.known_by]}",
            live=False,
        )
        ev.check(
            "Memory tells it without a meeting",
            all(life_lines(state, who) for who in known if came(state, who)),
            f"{seed}",
            live=False,
        )
        for turn, brief in played:
            since = [e for e in events if e.turn == turn.turn]
            told_of += bool(since)
            ev.check(
                "a scene that covers years is told what they brought the people around him",
                ("## LIVES" in brief) == bool(since),
                f"{seed} t{turn.turn}: {len(since)}",
                live=False,
            )
    ev.check("some of those scenes had news to tell", told_of > 0, str(told_of), live=False)
