"""T17's evals of other people's lives (W6, W10): the people the story knows lead lives of their
own while it is elsewhere.

Code decides what the years bring each of them and who has heard of it (`engine.world.lives`):
the checks here read the record. Whether a scene of meeting again shows those years, and makes
up nothing the record doesn't hold, is the judge's in live mode, and there the record is held
to the judge: it has the player character hearing news exactly when the scene told some.
"""

from __future__ import annotations

import json
from collections import Counter

from engine import bonds
from engine.base import DAY, MINUTE, YEAR
from engine.context import EventFrequency, StorySettings
from engine.contracts import (
    ActionKind,
    CharacterChange,
    Intent,
    OutcomeClass,
    SceneEnd,
    StateDelta,
)
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


def heard_there(played: list[tuple[Played, str]]) -> list[tuple[Played, list[LifeEvent]]]:
    """The scenes of a stretch in which the player character heard news of someone's life, each
    with what it had him hear: the record after it against the record before."""
    found = []
    for turn, _ in played:
        if turn.result is None:
            continue
        before = {e.id for e in heard(turn.before)}
        new = [e for e in heard(turn.result.state) if e.id not in before]
        if new:
            found.append((turn, new))
    return found


def ruled_out(played: list[tuple[Played, str]]) -> list[str]:
    """Why the engine ruled a stretch out with no throw, for a live run's report: the first
    live story (2026-11-13) lost a year of its ten to refusals nobody could read."""
    return [
        f"t{turn.turn}: {s.reason}"
        for turn, _ in played
        if turn.completed
        for s in turn.steps
        if s.outcome_class is OutcomeClass.RULED_OUT
    ]


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


def nod(present: list[str]) -> Intent:
    return plan(
        step(
            "nod to the people on the mill lane and stop at the trough for water",
            ActionKind.CONVERSATION,
            5 * MINUTE,
            verb="nod",
            target_ids=present,
        )
    )


def on_the_lane(present: list[str], ended_on: str) -> SceneEnd:
    return SceneEnd(ended_on=ended_on, place_id="village", present_ids=[YOU, *present])


def passing_scene(present: list[str]) -> dict:
    """A scripted scene with the people on the lane that tells nothing of their years."""
    end = on_the_lane(present, "Tomas drinks at the trough, the lane watching him.")
    return {
        "narration": "(scripted) Tomas nods to the faces on the lane and stops for water.",
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


def named_scene(
    present: list[str], names: dict[str, str], told: list[str], said: list[str]
) -> dict:
    """A scripted scene of the meeting that tells the news `told`, by id, saying the names
    `said` of whoever it came with, and gives each partner or child the world brought a name,
    under their own id, as the narrator is told to."""
    naming = [CharacterChange(id=i, name=n, known_to_player=True) for i, n in names.items()]
    end = on_the_lane(present, "The lane has filled with people who want a look at him.")
    spoken = f" They tell him of {', '.join(said)}." if said else ""
    return {
        "narration": f"(scripted) Ten years show on every face that turns toward Tomas.{spoken}",
        "told_news": told,
        "suggestions": [],
        "update": StateDelta(characters=naming, scene_end=end).model_dump(mode="json"),
    }


def came_with(state: WorldState, events: list[LifeEvent], who: str, names: dict[str, str]) -> list:
    """The names a scene says to tell `who` the news `events`: whoever each came with, by the
    name the scene gives them where the world brought them without one."""
    ids = dict.fromkeys(i for e in events for i in (*e.subject_ids, e.child_id) if i and i != who)
    return [names.get(i, state.characters[i].name) for i in ids]


def reads_the_years(brief: str, who: str, away: str | None, news: list[str]) -> bool:
    """Whether a brief hands its scene the `news` of someone in it, by id, and says the two
    were last together `away` ago, or nothing of that when they were together lately."""
    if "## SCENE\n" not in brief:
        return False  # a live run keeps no brief
    scene = json.loads(brief.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
    person = next((p for p in scene["present"] if p["id"] == who), {})
    return person.get("last_seen") == away and [n["id"] for n in person.get("news", [])] == news


def told_of(state: WorldState, who: str) -> str:
    """What the record holds of what the years brought someone, in a line for the judge."""
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
    return f"{person.name}{age}: {'; '.join(told) or 'nothing came to them'}."


def on_record(state: WorldState, present: list[str], others: list[str]) -> str:
    """What the record holds of the people in the scene, and of the `others` of the village it
    may bring in or speak of, for the judge: the story is the eval's own (T16)."""
    away = ago_label(lives.apart_s(state, state.characters[present[0]]) or 0)
    lines = [f"Tomas last saw the people of Millbrook {away}, and nobody sent word since."]
    lines += [told_of(state, who) for who in present]
    around = [who for who in others if who not in present and came(state, who)]
    if around:
        lines.append("Others in the village, whom the scene may bring in or speak of:")
        lines += [told_of(state, who) for who in around]
    lines.append("Nothing of the kind came to anyone else in Millbrook, nor to Tomas.")
    return "\n".join(lines)


def far_from_home(state: WorldState, known: list[str]) -> str:
    """What the record holds of the people of Millbrook while Tomas is in Harrowgate, for the
    judge of a scene there in which news of them reached him."""
    lines = ["Tomas is in Harrowgate, three days from Millbrook, where these people live:"]
    lines += [told_of(state, who) for who in known if came(state, who)]
    lines.append("Nothing of the kind came to anyone else in Millbrook, nor to Tomas.")
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
        "them. A scene that tells none of it leaves it news for the next, and once a scene "
        "told it, naming whom it came with, he has heard what it told, no more, and Memory "
        "tells it with its day. A partner or a child the world brought is named by the story "
        "under their own id. Someone who stays in the valley instead hears what comes to his "
        "neighbours as it happens, and has nobody there to meet again"
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
        stretches = await live_there(
            story, TEN, where="in Harrowgate", turns=LIVE_TURNS if ev.live else TURNS
        )
        state = story.state
        years = (state.world_s - left_s) // YEAR
        ev.metric(f"years away, {seed}", years)
        if ev.live:
            ev.metric(f"stretches ruled out, {seed}", ruled_out(stretches))
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
            f"{seed}: {years} years, Tomas {state.characters[YOU].age}, "
            f"{ {i: state.characters[i].age for i in known} }",
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
            live=False,
        )
        # A live scene may have the world bring someone of Millbrook to him, and what they
        # tell him he has heard: the record is held to what the judge reads in that scene.
        for turn, new in heard_there(stretches) if ev.live else ():
            told_there = await ev.judge(
                f"news that reached him far from home, turn {turn.turn}",
                Rubric(
                    must=(
                        "Someone of Millbrook is with Tomas in the scene, or sends him word, "
                        "and tells him at least one thing CONTEXT says came to someone",
                    ),
                ),
                turn,
                context=far_from_home(turn.result.state, list(known)),
            )
            if told_there is not None and told_there.error is None:
                ev.check(
                    "far from home he hears only what a scene told him",
                    all(v.passed for v in told_there.verdicts),
                    f"{seed} t{turn.turn}: heard {[e.id for e in new]}",
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
        away = ago_label(lives.apart_s(before, before.characters[most]) or 0)
        # What a brief hands a scene of someone's news: the latest five.
        handed = [e.id for e in lives.news_of(before, before.characters[most])[-5:]]

        if not ev.live:
            # A scene with them that tells none of it: it is still news, and the next scene
            # is handed it again.
            await story.act(
                "I nod to the people on the mill lane and stop at the trough for water",
                nod(present),
                narration=passing_scene(present),
            )
            ev.check(
                "the scene is told how long it has been and what the years brought them",
                reads_the_years(story.prompt(Node.NARRATOR), most, away, handed),
                f"{seed}: {away}, {len(news)} for {most}",
            )
            state = story.state
            ev.check(
                "a scene that tells none of it leaves it news, and Memory without it",
                not heard(state)
                and not life_lines(state, most)
                and lives.news_of(state, state.characters[most]) == news
                and all(state.characters[who].seen_s == state.world_s for who in present),
                f"{seed}: {[e.id for e in heard(state)]}",
            )
        names = dict(zip(unnamed_in(story.state, news), SPARE_NAMES, strict=False))
        was = len(story.state.characters)
        knew = {e.id for e in heard(story.state)}
        told_of = [e for e in news if e.id in handed]
        said = came_with(story.state, told_of, most, names)
        met = await story.act(
            "I greet the people on the mill lane and ask how they have all been",
            greet(present),
            narration=None if ev.live else named_scene(present, names, handed, said),
        )
        state = story.state
        ev.check(
            "the next scene with them is handed the news again",
            reads_the_years(story.prompt(Node.NARRATOR), most, None, handed),
            f"{seed}: {len(news)} for {most}",
            live=False,
        )
        now_heard = [e for e in heard(state) if e.id not in knew]
        ev.check(
            "after the scene that told it he has heard what it told, and no more",
            sorted(e.id for e in now_heard) == sorted(handed),
            f"{seed}: heard {[e.id for e in now_heard]}, told {handed}",
            live=False,
        )
        ev.check(
            "he has now been with whoever the scene ended with",
            all(
                state.characters[who].seen_s == state.world_s
                for who in present
                if who in state.scene.present_ids
            ),
            f"{seed}: {present}",
        )
        told = life_lines(state, most)
        ev.check(
            "Memory tells what he heard of them, each with its day",
            len(told) == min(len([e for e in now_heard if most in e.subject_ids]), 6)
            and all("day " in line for line in told),
            f"{seed}: {told} of {len(news)}",
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
            ev.metric(f"news heard in the scene, {seed}", f"{len(now_heard)} of {len(handed)}")
            ev.metric(f"news heard far from home, {seed}", len(knew))
        must = [
            "The scene is told as a return after the years CONTEXT says: the people Tomas "
            "meets are older or changed by the time, or the years are spoken of",
        ]
        if news:
            must.append(
                "At least one thing CONTEXT says came to someone in the scene is shown or "
                "said in it"
            )
        judgement = await ev.judge(
            "meeting again after ten years",
            Rubric(
                must=tuple(must),
                must_not=(
                    "Someone in the scene is given a romantic partner, a wedding, a child or a "
                    "parting of a couple that CONTEXT doesn't say came to them",
                    "Tomas knows what the years brought someone before anyone shows or tells him",
                    "A child CONTEXT gives an age is told as years younger or older than that",
                ),
            ),
            met,
            context=on_record(before, present, at_home),
        )
        shown = None
        if judgement is not None and judgement.error is None and news:
            shown = next((v.passed for v in judgement.verdicts if v.id == "M2"), None)
        if shown is not None:
            # C6: Memory holds what the story told, so the record is held to what the judge
            # read in the scene.
            ev.check(
                "the record has him hearing news exactly when the scene told some",
                shown == bool(now_heard),
                f"{seed}: the judge found news told: {shown}; heard {[e.id for e in now_heard]}",
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
        apart = {
            who: gone
            for who in known
            if state.characters[who].alive
            and ((gone := lives.apart_s(state, state.characters[who])) is None or gone >= MONTH)
        }
        ev.check(
            "nobody he lived beside all those years is someone he meets again",
            not apart and not any("## MEETING AGAIN" in brief for _, brief in played),
            f"{seed}: {apart}",
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
