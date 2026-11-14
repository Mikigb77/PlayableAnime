"""T17's evals of old age (W6, W10): the old die while the story is elsewhere.

Code decides whom the years take and who has heard of it (`engine.world.old_age`,
`engine.world.lives`): the checks here read the record. Whether the scene of a homecoming shows
that someone died, and has nobody who died walk into it, is the judge's in live mode, and
there the record is held to the judge: it has the player character knowing of a death exactly
when the scene told one.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from engine import bonds
from engine.base import DAY, MINUTE, YEAR
from engine.context import Language
from engine.contracts import ActionKind, CharacterChange, Intent, SceneEnd, StateDelta
from engine.invariants import check_state
from engine.labels import ago_label
from engine.state import LifeEvent, SceneFrame, WorldState
from engine.visibility import memory_view, status_view
from engine.world import last_years, lives, old_age
from engine.world.last_years import ASKED_TITLE, NEAR_TITLE
from engine.world.scheduling import Kind, pending
from engine.world.tuning import LAST_YEARS, LIFE_QUIET_S, OLD_AGE_FROM
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval
from evals.scenario import REGISTRY
from evals.scenarios.common import act, item, plan, step
from evals.scenarios.t17_lives import (
    CALM,
    LIVE_TURNS,
    MONTH,
    TEN,
    TURNS,
    YOU,
    home_again,
    in_harrowgate,
    live_there,
    nod,
    on_the_lane,
    passing_scene,
    ruled_out,
    span,
)
from evals.scenarios.t17_world import wider_world
from graph.llm import Node

scenario = REGISTRY.scenario

OLD = ("bram", worlds.GRETA, worlds.ALDER)


def dead(state: WorldState) -> list[str]:
    return sorted(c.id for c in state.characters.values() if not c.alive)


def in_memory(state: WorldState, who: str) -> tuple[str, list[str]]:
    """What Memory says of someone he knows (C6): whether they are alive, and their lines."""
    person = next(p for p in memory_view(state).people if p.id == who)
    return person.status, person.lines


def knew(state: WorldState, ids: list[str]) -> list[str]:
    """Whom of some people the player character knows of. A partner the world brought one of
    his neighbours while he was away, and took again, he never heard of."""
    return [i for i in ids if YOU in state.characters[i].known_by]


def died_line(state: WorldState, who: str) -> bool:
    """Whether Memory tells that someone died of old age, with its day."""
    return any("old age" in line and "day " in line for line in in_memory(state, who)[1])


def in_scene(brief: str) -> list[str]:
    """Who a brief has in its scene, by id."""
    if "## SCENE\n" not in brief:
        return []  # a live run keeps no brief
    scene = json.loads(brief.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
    return [p["id"] for p in scene.get("present", [])]


def ask_after(present: list[str]) -> Intent:
    return plan(
        step(
            "ask after the old people of the village, and where they are now",
            ActionKind.CONVERSATION,
            20 * MINUTE,
            verb="ask",
            target_ids=present,
        )
    )


def graveside_scene(present: list[str], name: str, told: list[str]) -> dict:
    """A scripted scene that says, by name, that one of the old people died, and lists every
    piece of news it was handed, as a narrator may."""
    end = on_the_lane(present, "Tomas stands at the churchyard wall with his cap in his hand.")
    return {
        "narration": (
            f"(scripted) They walk him to the churchyard wall. {name} lies there now, under a "
            "stone the frost has not yet marked."
        ),
        "told_news": told,
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


def on_record(state: WorldState, gone: list[LifeEvent], present: list[str]) -> str:
    """What the record holds of who died and who lives in Millbrook, for the judge: the story
    is the eval's own (T16)."""
    lines = [
        "Tomas left Millbrook ten years ago for Harrowgate, three days off, and no word from "
        "the valley has reached him since. He is back in Millbrook now.",
        "Died of old age in Millbrook while he was away, which he has not heard:",
    ]
    for event in gone:
        person = state.characters[event.subject_ids[0]]
        left = state.characters.get(event.other(person.id) or "")
        widowed = f", leaving {left.name}" if left is not None else ""
        when = ago_label(max(0, state.world_s - event.world_s))
        lines.append(f"- {person.name}, at {person.age}, {when}{widowed}.")
    lines.append("With him in the scene: " + ", ".join(state.characters[i].name for i in present))
    alive = [c for c in state.npcs() if c.alive and c.location_id == "village"]
    lines.append(
        "Alive in Millbrook: " + ", ".join(f"{c.name} ({c.age})" for c in alive if c.age) + "."
    )
    lines.append("Nobody else on record has died.")
    return "\n".join(lines)


@scenario(
    "t17.old-age",
    suite="T17",
    title="The old die while he is away",
    requirements=("W6", "W10", "C6", "C1", "W17", "A2", "T17"),
    passes_when=(
        "A man leaves his village for a city three days off and comes home ten years later. "
        "A month away takes nobody. Over the ten years old age takes some of the old people he "
        "knew, who varies from story to story, and nobody else: nothing is made to happen. "
        "Whoever died is on record dead for certain, where they lived, at the age they died "
        "at, with their marriage ended. Far away he hears none of it, and Memory has them "
        "alive. The scene of his return is handed who is gone, and nobody who died is in it. A "
        "scene that names none of them leaves it news, whatever its answer lists, and once a "
        "scene said by name that someone died he knows of that death and of no other, and "
        "Memory has them dead with the day. Someone who stays in the valley instead knows of "
        "each death as it happens"
    ),
)
async def old_age_takes(ev: Eval) -> None:
    # A month away: the years have had no time to take anyone.
    in_a_month = 0
    for seed in ev.seeds(24, live=0):
        story = ev.story(
            worlds.millbrook_grown_old(), seed=f"{seed}/month", settings=CALM, under_way=True
        )
        story.change(in_harrowgate)
        await live_there(story, MONTH, where="in Harrowgate", turns=TURNS)
        in_a_month += len(dead(story.state))
    ev.check("a month away takes nobody", in_a_month == 0, str(in_a_month), live=False)

    took: Counter[str] = Counter()
    stories = 0
    for seed in ev.seeds(24, live=1):
        story = ev.story(worlds.millbrook_grown_old(), seed=seed, settings=CALM, under_way=True)
        story.change(in_harrowgate)
        left_s = story.state.world_s
        was = {i: c.age for i, c in story.state.characters.items()}
        stretches = await live_there(
            story, TEN, where="in Harrowgate", turns=LIVE_TURNS if ev.live else TURNS
        )
        state = story.state
        years = (state.world_s - left_s) // YEAR
        gone_ids = dead(state)
        mourned = knew(state, gone_ids)
        took.update(gone_ids)
        stories += 1
        if ev.live:
            ev.metric(f"years away, {seed}", years)
            ev.metric(f"stretches ruled out, {seed}", ruled_out(stretches))
        ev.metric(f"whom the years took, {seed}", gone_ids)
        people = [state.characters[i] for i in gone_ids]
        ev.check(
            "old age takes only the old",
            all(
                lives.of_old_age(c) and c.age >= OLD_AGE_FROM * old_age.span(state, c)
                for c in people
            )
            and not any(state.characters[i].age < 60 for i in gone_ids),
            f"{seed}: { {c.id: c.age for c in people} }",
        )
        ev.check(
            "whoever died is on record dead for certain, where they lived, at the age they "
            "died at, with their marriage ended",
            all(
                c.death_certainty is not None
                and c.death_certainty.value == "confirmed"
                and c.location_id == "village"
                and was.get(c.id, 0) <= c.age <= was.get(c.id, c.age) + years
                and bonds.partners(state, c.id) == []
                for c in people
            ),
            f"{seed}: {[(c.id, c.age, c.location_id) for c in people]}",
        )
        ev.check(
            "far away he hears none of it, and Memory has them alive",
            all(in_memory(state, i)[0] == "alive" and not died_line(state, i) for i in mourned)
            and all(YOU not in e.known_by for e in state.lives.values() if lives.died(e)),
            f"{seed}: {[in_memory(state, i)[0] for i in mourned]}",
            live=False,
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}")
        if not mourned:
            continue  # the years took nobody he knew: there is no death to come home to

        # Home again, with the baker's daughter on the lane, and the widow where there is one.
        widow = state.characters[worlds.RUNA].alive and worlds.ALDER in gone_ids
        present = [worlds.EDDA, *([worlds.RUNA] if widow else [])]
        story.change(home_again(present))
        before = story.state
        gone = lives.gone(before, "village")
        handed = [e.id for e in gone]
        ev.check(
            "every death he hasn't heard of is the village's to tell",
            sorted(e.subject_ids[0] for e in gone) == mourned,
            f"{seed}: {handed} for {mourned}",
            live=False,
        )
        if not ev.live:
            # A scene at home that names none of them: it is still news.
            await story.act(
                "I nod to the people on the mill lane and stop at the trough for water",
                nod(present),
                narration=passing_scene(present) | {"told_news": handed},
            )
            brief = story.prompt(Node.NARRATOR)
            moved = wider_world(brief)
            ev.check(
                "the scene of his return is handed who is gone, and nobody who died is in it",
                [piece.get("id") for piece in moved.get("gone", [])] == handed
                and "They are dead, so nobody meets them." in moved.get("tell", "")
                and not set(in_scene(brief)) & set(gone_ids),
                f"{seed}: {moved.get('gone')}",
            )
            state = story.state
            ev.check(
                "a scene that names none of them leaves it news, whatever its answer lists",
                all(YOU not in state.lives[key].known_by for key in handed)
                and all(in_memory(state, i)[0] == "alive" for i in mourned),
                f"{seed}: {[key for key in handed if YOU in state.lives[key].known_by]}",
            )
        first = before.characters[gone[0].subject_ids[0]]
        seen = await story.act(
            "I ask after the old people of the village, and where they are now",
            ask_after(present),
            narration=None if ev.live else graveside_scene(present, first.name, handed),
        )
        state = story.state
        heard = [e.subject_ids[0] for e in gone if YOU in state.lives[e.id].known_by]
        if ev.live:
            ev.metric(f"deaths heard in the scene, {seed}", f"{len(heard)} of {len(gone)}")
        ev.check(
            "once a scene said by name that someone died he knows of that death and no other",
            heard == [first.id],
            f"{seed}: heard {heard}, the scene named {first.id}",
            live=False,
        )
        ev.check(
            "Memory has whoever he heard died as dead, with the day, and the others alive",
            all(
                (in_memory(state, i)[0] == "dead" and died_line(state, i))
                if i in heard
                else (in_memory(state, i)[0] == "alive" and not died_line(state, i))
                for i in mourned
            ),
            f"{seed}: { {i: in_memory(state, i)[0] for i in mourned} }",
        )
        ev.check(
            "nobody who died is in the scene",
            not set(state.scene.present_ids) & set(gone_ids),
            f"{seed}: {state.scene.present_ids}",
        )
        judgement = await ev.judge(
            "home after ten years, and some of the old are gone",
            Rubric(
                must=(
                    "The scene shows, or someone in it says, that at least one of the people "
                    "CONTEXT says died has died",
                ),
                must_not=(
                    "Someone CONTEXT says died is met alive in the scene: they speak, act or "
                    "are said to be living now",
                    "The scene has someone dead or dying whom CONTEXT doesn't say died",
                    "Tomas already knows that someone died before he sees it or is told",
                ),
            ),
            seen,
            context=on_record(before, gone, present),
        )
        if judgement is not None and judgement.error is None:
            shown = next((v.passed for v in judgement.verdicts if v.id == "M1"), None)
            if shown is not None:
                # C6: Memory holds what the story told, so the record is held to the judge.
                ev.check(
                    "the record has him knowing of a death exactly when the scene told one",
                    shown == bool(heard),
                    f"{seed}: the judge found a death told: {shown}; on record: {heard}",
                )

    ev.metric("whom ten years took, in how many stories", dict(took))
    ev.check(
        "who the years take varies from story to story: nothing is made to happen",
        stories == 0 or all(0 < took[who] < stories for who in OLD),
        f"{dict(took)} of {stories}",
        live=False,
    )

    # Someone who stays in the valley knows of each death as it happens.
    for seed in ev.seeds(12, live=0):
        story = ev.story(
            worlds.millbrook_grown_old(), seed=f"{seed}/home", settings=CALM, under_way=True
        )
        played = await live_there(story, TEN, where="on the farm", turns=TURNS)
        state = story.state
        gone_ids = knew(state, dead(state))
        ev.check(
            "living near, he knows of each death as it happens, and Memory tells it",
            all(in_memory(state, i)[0] == "dead" and died_line(state, i) for i in gone_ids)
            and lives.gone(state, "village") == [],
            f"{seed}: { {i: in_memory(state, i)[0] for i in gone_ids} }",
            live=False,
        )
        told = [brief for _, brief in played if '"what":"died of old age"' in brief]
        ev.check(
            "the scene that covers the time is told of it in passing",
            not gone_ids or bool(told),
            f"{seed}: {len(told)} briefs for {gone_ids}",
            live=False,
        )


# --- How long each people lives (G23, W6) ------------------------------------------------------

HUNDRED = 100 * YEAR + MONTH
# A made-up premise for the real drafter: a people that lives long, and one old age never
# takes.
THREE_PEOPLES = (
    "I am a human courier in Ashmere, a harbour city that humans share with elves, who live "
    "for centuries, and with the risen dead of the Bone Quarter, who never age. I carry "
    "letters between their quarters."
)
# What a human life never reaches, and what is as good as never dying, in years.
FAR_LONGER, AS_GOOD_AS_NEVER = 150, 10_000


def long_lived(state: WorldState) -> None:
    """Tomas lives as long as the elves do, by a span of his own: the hundred years come to
    everyone else alone (his own old age is `t17.own-old-age`)."""
    state.characters[YOU].lifespan_years = 600


@scenario(
    "t17.long-lived-peoples",
    suite="T17",
    title="How long each people lives",
    requirements=("G23", "W6", "A2", "T17"),
    passes_when=(
        "An elf beekeeper and one of the unsleeping dead live in Millbrook among its people. "
        "Tomas, his own old age set aside, stays away a hundred years: old age takes every "
        "villager he knew, and neither the elf, whose people live six hundred years, nor the "
        "dead man, whose people old age never takes. Live, the real drafter is given a premise "
        "with humans, elves who live for centuries and risen dead who never age, and every "
        "people it writes says how long it lives: one far longer than a human life, and one "
        "that old age never takes or that lives ten thousand years and more. The human courier "
        "it writes for the player has an age on record and a human life to live, so old age "
        "can come to them"
    ),
    notes="Live mode drafts one world and plays no scene.",
)
async def long_lived_peoples(ev: Eval) -> None:
    for seed in ev.seeds(6, live=0):
        story = ev.story(
            worlds.millbrook_of_three_peoples(), seed=seed, settings=CALM, under_way=True
        )
        story.change(in_harrowgate)
        story.change(long_lived)
        humans = [
            i
            for i, c in story.state.characters.items()
            if i != YOU and c.age is not None and c.people_id == "humans"
        ]
        await live_there(story, HUNDRED, where="in Harrowgate", turns=TURNS)
        state = story.state
        gone_ids = dead(state)
        ev.check(
            "a hundred years take every villager he knew",
            set(humans) <= set(gone_ids),
            f"{seed}: {sorted(set(humans) - set(gone_ids))} still live",
        )
        sael, wick = state.characters[worlds.SAEL], state.characters[worlds.WICK]
        ev.check(
            "and neither the elf nor the dead man, each a hundred years older",
            sael.alive and wick.alive and (sael.age, wick.age) == (240, 171),
            f"{seed}: Sael {sael.status.value} at {sael.age}, Wick {wick.status.value} "
            f"at {wick.age}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}")
    if not ev.live:
        return
    world = await ev.drafted(THREE_PEOPLES)
    spans = {p.name: p.lifespan_years for p in world.bible.peoples}
    ev.metric("how long each people lives, as the real drafter wrote it", spans)
    ev.check("the draft has the peoples of the premise", len(spans) >= 2, str(spans))
    ev.check(
        "every people says how long it lives",
        all(years is not None for years in spans.values()),
        str(spans),
    )
    ev.check(
        "one of them lives far longer than a human life",
        any(years and FAR_LONGER <= years < AS_GOOD_AS_NEVER for years in spans.values()),
        str(spans),
    )
    ev.check(
        "and one old age never takes, or as good as never",
        any(years == 0 or (years or 0) >= AS_GOOD_AS_NEVER for years in spans.values()),
        str(spans),
    )
    you = world.player
    found = last_years.years_of(world, world.world_s)
    ev.metric(
        "the human courier's years, as the real drafter wrote them",
        {
            "age": you.age,
            "lifespan_years": you.lifespan_years,
            "lives": None if found is None else found.span,
        },
    )
    ev.check(
        "old age can come to the human courier: an age on record, of a human life",
        found is not None and found.age < found.span < FAR_LONGER,
        f"age {you.age}, lifespan {you.lifespan_years}, span {old_age.span(world, you)}",
    )


# --- His own old age (N6, W6) ------------------------------------------------------------------

FORTY = 40 * YEAR
ON_THE_FARM = "Tomas is on his farm above Millbrook, alone, the day's work done."
PEACH_ACTION = "I eat the peach from the Orchard of the Undying, the one I have kept all my life."
# A made-up premise for the real drafter: someone old age never takes, played by the player.
RISEN_COURIER = (
    "I am one of the risen dead of the Bone Quarter in Ashmere, a harbour city where the dead "
    "who walk never age. I died two hundred years ago, and I have carried the city's letters "
    "ever since."
)
# A made-up premise for the real drafter: years that are running out, in the player's words.
# The first one played by hand (2026-11-14) got a countdown "Lifespan Depletion" of the drafter's
# own beside the record's age and years, so two clocks ran to one death, and the first check
# after the drafter was told never to got "The Lifespan Limit (2 Years Left)", with no owner.
COUNTS_A_LIFE = re.compile(r"life[ -]?span|old age|years? (?:left|remaining)|longevity", re.I)
SPENT_CULTIVATOR = (
    "An old cultivator, 148 years old, stuck at the peak of Foundation Establishment. My "
    "lifespan of 150 years is almost spent: I break through to Core Formation or I die."
)
THE_END_IS_CLOSE = Rubric(
    must=(
        "The scene shows that Tomas is old, in his own body or in how he moves or tires",
        "Tomas senses, or is made to understand, that the end of his life is close",
    ),
    must_not=(
        "Tomas dies in this scene",
        "The scene says how many years, months or days Tomas has left to live",
    ),
)
TAKES_HIM = Rubric(
    must=(
        "The scene tells the death of Tomas, of old age",
        "The scene ends on his death or on what it leaves behind, with nothing left for him "
        "to do or to decide",
    ),
    must_not=("Something other than his age kills Tomas: a blow, an accident, an illness named",),
)
# The record must hold the longer life (a check of code). Of the telling the judge asks only
# that the peach is seen to change him: a live run failed a scene in which his aches eased and
# his heart found a youthful rhythm, for not saying in words that he will live long.
LIVES_ON = Rubric(
    must=(
        "Tomas eats the peach, and the scene shows it changing him: his years ease, his "
        "strength or his youth comes back, or he knows he will live long",
    ),
    must_not=("Tomas dies in this scene",),
)
THE_PEACH = (
    "Tomas is the player character, told as 'you': an old man near the end of his life. The "
    "peach gives whoever eats it three hundred years."
)
STILL_YOUNG = Rubric(
    must_not=(
        "The scene shows Tomas as an old man near the end of his life: frail, failing, or "
        "with little time left",
        "Tomas dies in this scene",
    ),
)
AN_ELF = "Tomas is an elf of some seventy or eighty years. Elves live for many centuries."
# What the engine keeps of the day, which no brief may hold.
THE_DAY = "day_s"
# The stop's title, where the record says how long he lives and where the world assumes it.
STOP_TITLES = (NEAR_TITLE, ASKED_TITLE)


def on_his_farm(state: WorldState) -> None:
    state.characters[YOU].location_id = "farm"
    state.scene = SceneFrame(place_id="farm", present_ids=[YOU], ended_on=ON_THE_FARM)


def of_his_years(state: WorldState) -> str:
    """What the sheet says of his age (S10)."""
    return status_view(state, Language.EN).sheet.about[-1]


def stops(turn) -> bool:
    """Whether the turn's scene opened on the end of his life being close."""
    return turn.completed and turn.event is not None and turn.event.title in STOP_TITLES


async def to_the_end(story, length: int, *, turns: int, stop: bool = False) -> list[tuple]:
    """He lets `length` go by on the farm, a stretch at a time, going back to it whenever the
    world stops it for something, until the years are up or his story ends, or with `stop`
    until the years stop for the end of his life being close. Each turn comes back with the
    brief its narrator read (deterministic mode)."""
    until = story.state.world_s + length
    played: list[tuple] = []
    while (left := until - story.state.world_s) >= DAY and len(played) < turns:
        words, seconds = span(left)
        skip = act(f"Work on the farm for {words}", "work", ActionKind.TIME_SKIP, seconds)
        turn = await story.act(f"I keep to my work on the farm for {words}", skip)
        played.append((turn, story.prompt(Node.NARRATOR)))
        if turn.result is not None and turn.result.ending is not None:
            break
        if stop and stops(turn):
            break
    return played


def stopped(played: list[tuple]) -> tuple | None:
    """The turn whose scene opened on the end of his life being close, with its brief."""
    return next(((turn, told) for turn, told in played if stops(turn)), None)


def says_how_long(narration: str, ended_on: str, years: int) -> dict:
    """A scripted scene whose update says how long he now lives."""
    end = SceneEnd(ended_on=ended_on, place_id="farm", present_ids=[YOU])
    longer = CharacterChange(id=YOU, lifespan_years=years)
    return {
        "narration": f"(scripted) {narration}",
        "suggestions": [],
        "update": StateDelta(characters=[longer], scene_end=end).model_dump(mode="json"),
    }


def peach_scene() -> dict:
    return says_how_long(
        "The peach is cold and sweet, and the years fall from Tomas.",
        "Tomas turns the stone in his fingers.",
        300,
    )


def elf_scene() -> dict:
    return says_how_long(
        "The winters sit on Tomas like one: he is an elf, and young.",
        "Tomas goes back to the field.",
        800,
    )


@scenario(
    "t17.own-old-age",
    suite="T17",
    title="His own old age",
    requirements=("N6", "W6", "W10", "G23", "A2", "S10", "T17"),
    passes_when=(
        "A farmer of sixty, whose record gives him eighty years, sets out to work his farm "
        "for forty more. Nothing announces that old age has begun. The years stop once, some "
        "way before the day old age takes him, a distance that varies from story to story: "
        "the scene opens on the end of his life being close and is told so with no number, "
        "his sheet says his age and nothing of how long he lives, no brief holds the day, and "
        "he is alive. Going on, his story ends in a death of old age, never within a season of "
        "the stop and never by his own hand, in a scene handed his death as its task, at an "
        "age that varies from story to story between sixty-eight and a hundred. A farmer who "
        "eats a peach that gives three hundred years after the stop, in a scene whose update "
        "says so, lives through forty more years with three hundred on record. An elf of "
        "sixty in a world drafted before peoples said how long they live, whose life the "
        "record takes for a human one: the stop claims no "
        "loss, says the record doesn't say and asks first, and once the scene answers that he "
        "lives centuries no old age comes to him. A human in that world is asked too, told "
        "for a human life, and dies of old age going on. Live, the real drafter is given "
        "someone old age never takes to play, and the world it writes has no old age for "
        "them, and a cultivator whose years are almost spent, whose age and years are on "
        "record as the premise gives them with no countdown of the drafter's own beside them"
    ),
)
async def own_old_age(ev: Eval) -> None:
    ages: Counter[int] = Counter()
    gaps: Counter[float] = Counter()
    budget = 2 * LIVE_TURNS if ev.live else TURNS
    for seed in ev.seeds(12, live=1):
        story = ev.story(worlds.millbrook_at_sixty(), seed=seed, settings=CALM, under_way=True)
        story.change(on_his_farm)
        played = await to_the_end(story, FORTY, turns=budget)
        ev.metric(f"scenes his years took, {seed}", len(played))
        if ev.live:
            ev.metric(f"stretches ruled out, {seed}", ruled_out(played))
        found = stopped(played)
        last, last_told = played[-1]
        ending = last.result.ending if last.result is not None else None
        end = story.state
        if ev.live and found is None and ending is None and len(played) >= budget:
            # The real models let the years go by in shorter stretches than the turns allow.
            age = end.characters[YOU].age
            ev.metric(f"the turns ran out before his years did, at the age of, {seed}", age)
            continue
        ev.check("the years stop once when the end of his life is close", found is not None, seed)
        if found is None:
            continue
        turn, told = found
        then = turn.state
        you = then.characters[YOU]
        ev.metric(f"the age the years stopped at, {seed}", you.age)
        ev.check(
            "there he is alive, an old man of sixty-five or more",
            you.alive and 65 <= you.age <= 100,
            f"{seed}: {you.status.value} at {you.age}",
        )
        ev.check(
            "his sheet says his age, and nothing of how long he lives",
            of_his_years(then) == f"{you.age} years old",
            f"{seed}: {of_his_years(then)}",
            live=False,
        )
        ev.check(
            "the scene is told the end is close, with no number, and reads him so from then on",
            '"title":"Your years run short"' in told
            and "the end of their life is close" in told
            and "give no number of years or days left" in told
            and "record doesn't say" not in told
            and f'"old_age":"{you.age} of the about 80 years someone like them lives: the end'
            in told,
            f"{seed}",
            live=False,
        )
        ev.check(
            "no brief holds the day",
            not any(THE_DAY in each for _, each in played),
            f"{seed}",
            live=False,
        )
        await ev.judge(f"the end is close, {seed}", THE_END_IS_CLOSE, turn)
        you = end.characters[YOU]
        if ev.live and ending is None and len(played) >= budget:
            ev.metric(f"the turns ran out before his years did, at the age of, {seed}", you.age)
            continue
        ev.check(
            "going on, his story ends in a death of old age, never by his own hand",
            ending is not None
            and (ending.kind, ending.self_inflicted) == ("death", False)
            and not you.alive
            and lives.of_old_age(you),
            f"{seed}: {ending}, {you.status.value} at {you.age}",
        )
        if ending is None:
            continue
        ages[you.age] += 1
        gap = (end.world_s - then.world_s) / YEAR
        gaps[round(gap, 1)] += 1
        ev.metric(f"the age old age took him at, {seed}", you.age)
        ev.check(
            "never within a season of the stop, within the last of his span, before a hundred",
            LIFE_QUIET_S <= end.world_s - then.world_s <= LAST_YEARS[1] * 80 * YEAR + DAY
            and 68 <= you.age <= 100,
            f"{seed}: {gap:.2f} years after it, at {you.age}",
            live=False,
        )
        ev.check(
            "the last scene is handed his death of old age as its task",
            "ENDING: the player character dies of old age in this scene" in last_told
            and '"title":"Your years run out"' in last_told,
            f"{seed}",
            live=False,
        )
        ev.check("the record holds together (C1)", check_state(end) == [], f"{seed}")
        await ev.judge(f"old age takes him, {seed}", TAKES_HIM, last)
    ev.metric("the ages old age took him at", dict(sorted(ages.items())))
    ev.metric("years between the stop and the day", dict(sorted(gaps.items())))
    ev.check(
        "the day varies from story to story, and so does how far before it the years stop",
        len(ages) >= 5 and len(gaps) >= 5,
        f"{dict(sorted(ages.items()))}, {dict(sorted(gaps.items()))}",
        live=False,
    )

    # The story lengthens his life: a peach that gives three hundred years.
    for seed in ev.seeds(6, live=1):
        story = ev.story(
            worlds.millbrook_at_sixty(peach=True),
            seed=f"{seed}/peach",
            settings=CALM,
            under_way=True,
        )
        story.change(on_his_farm)
        played = await to_the_end(story, FORTY, turns=budget, stop=True)
        if stopped(played) is None or not story.state.characters[YOU].alive:
            if not ev.live or len(played) < budget:
                ev.check("the years stop once when the end of his life is close", False, seed)
            continue
        eats = plan(
            step(
                "eat the peach from the Orchard of the Undying",
                ActionKind.INSTANT,
                MINUTE,
                verb="eat",
                uses=[item(worlds.PEACH)],
            )
        )
        ate = await story.act(PEACH_ACTION, eats, narration=None if ev.live else peach_scene())
        you = ate.state.characters[YOU]
        ev.metric(f"how long he lives after the peach, {seed}", you.lifespan_years)
        ev.check(
            "a scene that lengthens his life puts it on record",
            (you.lifespan_years or 0) >= FAR_LONGER,
            f"{seed}: lifespan {you.lifespan_years}, issues "
            f"{[i.code for i in ate.result.issues] if ate.result else ate.refused}",
        )
        await ev.judge(f"the peach, {seed}", LIVES_ON, ate, context=THE_PEACH)
        if ev.live or not you.lifespan_years:
            continue
        later = await to_the_end(story, FORTY, turns=TURNS)
        end = story.state
        you = end.characters[YOU]
        ev.check(
            "and he lives through forty more years, of three hundred, his sheet still only his age",
            you.alive
            and you.age >= 105
            and stopped(later) is None
            and old_age.span(end, you) == 300
            and of_his_years(end) == f"{you.age} years old",
            f"{seed}: {you.status.value} at {you.age} of {old_age.span(end, you)}, "
            f"{of_his_years(end)}",
        )
        ev.check("the record holds together (C1)", check_state(end) == [], f"{seed}/peach")

    # A world drafted before peoples said how long they live: an elf whose life the record
    # takes for a human one. The stop says so, and the scene answers.
    for seed in ev.seeds(6, live=1):
        story = ev.story(
            worlds.millbrook_elf_at_sixty(), seed=f"{seed}/elf", settings=CALM, under_way=True
        )
        story.change(on_his_farm)
        ev.check(
            "his sheet says his age, and nothing of how long he lives",
            of_his_years(story.state) == "60 years old",
            f"{seed}/elf: {of_his_years(story.state)}",
            live=False,
        )
        if ev.live:
            played = await to_the_end(story, FORTY, turns=budget, stop=True)
        else:
            # A day, so the world has looked; then up to the day before the stop it keeps
            # pending; then the stretch the stop cuts short, with a scene that answers.
            played = await to_the_end(story, DAY, turns=1)
            (waits,) = pending(story.state, Kind.OLD_AGE)
            played += await to_the_end(story, waits.due_s - story.state.world_s - DAY, turns=TURNS)
            words, seconds = span(20 * YEAR)
            skip = act(f"Work on the farm for {words}", "work", ActionKind.TIME_SKIP, seconds)
            turn = await story.act(
                f"I keep to my work on the farm for {words}", skip, narration=elf_scene()
            )
            played.append((turn, story.prompt(Node.NARRATOR)))
        found = stopped(played)
        if found is None:
            if not ev.live or len(played) < budget:
                ev.check(
                    "the years stop once when the end of his life is close", False, f"{seed}/elf"
                )
            continue
        turn, told = found
        you = turn.state.characters[YOU]
        ev.check(
            "nothing reads him as old before the stop, where the span is only assumed",
            not any('"old_age":' in each for _, each in played[:-1]),
            f"{seed}/elf",
            live=False,
        )
        ev.check(
            "the stop claims no loss: it says the record takes his life for a human one, and "
            "asks first",
            f'"title":"{ASKED_TITLE}"' in told
            and '"kind":"discovery"' in told
            and '"brief":"The record doesn\'t say how long Tomas Weller lives' in told
            and "(lifespan_years, 1000000 for never)" in told
            and f'"old_age":"{you.age}. The record doesn\'t say how long they live' in told,
            f"{seed}/elf",
            live=False,
        )
        ev.metric(f"how long the elf lives, as the scene answered, {seed}", you.lifespan_years)
        ev.check(
            "the scene answers that he lives far longer, and the record has it",
            (you.lifespan_years or 0) >= FAR_LONGER,
            f"{seed}/elf: lifespan {you.lifespan_years}, issues "
            f"{[i.code for i in turn.result.issues] if turn.result else turn.refused}",
        )
        await ev.judge(f"an elf near eighty, {seed}", STILL_YOUNG, turn, context=AN_ELF)
        if ev.live or not you.lifespan_years:
            continue
        later = await to_the_end(story, FORTY, turns=TURNS)
        end = story.state
        you = end.characters[YOU]
        ev.check(
            "and no old age comes to him in the forty years after",
            you.alive
            and stopped(later) is None
            and old_age.span(end, you) == 800
            and '"old_age":' not in later[-1][1],
            f"{seed}/elf: {you.status.value} at {you.age} of {old_age.span(end, you)}",
        )
        ev.check("the record holds together (C1)", check_state(end) == [], f"{seed}/elf")

    # The same world, where he is the human the record takes him for: asked too, and told.
    for seed in ev.seeds(3, live=1):
        story = ev.story(
            worlds.millbrook_unsaid_at_sixty(),
            seed=f"{seed}/unsaid",
            settings=CALM,
            under_way=True,
        )
        story.change(on_his_farm)
        played = await to_the_end(story, FORTY, turns=budget, stop=True)
        found = stopped(played)
        if found is None:
            if not ev.live or len(played) < budget:
                ev.check(
                    "the years stop once when the end of his life is close",
                    False,
                    f"{seed}/unsaid",
                )
            continue
        turn, told = found
        you = turn.state.characters[YOU]
        ev.check(
            "a human whose span the record doesn't say is asked, and told for a human life",
            turn.event.title == ASKED_TITLE
            and you.alive
            and you.old_age_span == 80
            and old_age.span(turn.state, you) == 80,
            f"{seed}/unsaid: lifespan {you.lifespan_years}, told for {you.old_age_span}",
        )
        ev.check(
            "and his sheet still says only his age",
            of_his_years(turn.state) == f"{you.age} years old",
            f"{seed}/unsaid: {of_his_years(turn.state)}",
            live=False,
        )
        await ev.judge(f"a human the record doesn't speak for, {seed}", THE_END_IS_CLOSE, turn)
        if ev.live:
            continue
        await to_the_end(story, FORTY, turns=TURNS)
        end = story.state
        you = end.characters[YOU]
        ev.check(
            "going on, old age takes him as it takes anyone",
            not you.alive and lives.of_old_age(you) and you.age <= 100,
            f"{seed}/unsaid: {you.status.value} at {you.age}",
        )
        ev.check("the record holds together (C1)", check_state(end) == [], f"{seed}/unsaid")
    if not ev.live:
        return
    world = await ev.drafted(RISEN_COURIER)
    you = world.player
    people = next((p for p in world.bible.peoples if p.id == you.people_id), None)
    ev.metric(
        "someone old age never takes, as the real drafter wrote them",
        {
            "age": you.age,
            "lifespan_years": you.lifespan_years,
            "people": None if people is None else (people.name, people.lifespan_years),
        },
    )
    ev.check(
        "the world the drafter writes has no old age for them",
        last_years.years_of(world, world.world_s) is None,
        f"age {you.age}, lifespan {you.lifespan_years}, span {old_age.span(world, you)}",
    )
    # W6, E2: the record's age and years are the one countdown to the end of a life.
    world = await ev.drafted(SPENT_CULTIVATOR)
    you = world.player
    theirs = [
        clock.name
        for clock in world.clocks.values()
        if clock.owner_id == you.id or COUNTS_A_LIFE.search(clock.name)
    ]
    ev.metric(
        "years that are running out, as the real drafter wrote them",
        {
            "age": you.age,
            "lifespan_years": you.lifespan_years,
            "clocks": [clock.name for clock in world.clocks.values()],
        },
    )
    ev.check(
        "years the premise says are running out are the record's age and years",
        you.age == 148 and old_age.span(world, you) == 150,
        f"age {you.age}, lifespan {you.lifespan_years}, span {old_age.span(world, you)}",
    )
    ev.check(
        "and no countdown of the character's own runs beside them",
        not theirs,
        str(theirs),
    )


# --- Meeting the end of his years (N6) ---------------------------------------------------------

LETS_GO = "I sit down in my chair by the stove, close my eyes and let go."
LIVES_IT_OUT = "I live out the days I have left quietly on the farm, for as long as they last."
MEETS_IT = Rubric(
    must=(
        "The scene tells the death of Tomas, as something he lets come: quiet, at peace",
        "The scene ends on his death or on what it leaves behind, with nothing left for him "
        "to do or to decide",
    ),
    must_not=("Something other than his age kills Tomas: a blow, an accident, an illness named",),
)


def told_the_end(state: WorldState) -> None:
    """Tomas at 79 of his eighty years, on his farm, after the scene that told him the end of
    his life is close: what `t17.own-old-age` plays the years up to."""
    on_his_farm(state)
    you = state.characters[YOU]
    you.age, you.lifespan_years, you.old_age_span = 79, 80, 80
    state.scene.ended_on = (
        "Your heart has slowed these last weeks, and the strength does not come back. You "
        "know, sitting by the stove, that the end of your life is close."
    )


def meets_it(words: str, kind: ActionKind, seconds: int) -> Intent:
    """A step with which he lets death come, as the reading has it once he was told."""
    return plan(step(words, kind, seconds, verb="rest", lets_go=True))


@scenario(
    "t17.letting-go",
    suite="T17",
    title="Meeting the end of his years",
    requirements=("N6", "W6", "W10", "B8", "T17"),
    passes_when=(
        "A farmer of sixty whose record gives him eighty years works his farm until the years "
        "stop for the end of his life being close. In half the stories he then sits down, "
        "closes his eyes and lets go: his story ends in that scene, minutes later, in a death "
        "of old age that is never by his own hand, in a scene handed his death as its task "
        "and told that he chose it, read twice before code acted. In the other half he sets "
        "out to live out the days he has left: the stretch runs on, past whatever the reading "
        "made of it, and going back to it after anything the world stops him for ends his "
        "story on the day that was drawn for him and no other. A farmer who says the same "
        "words before any scene told him the end is close only rests, and lives"
    ),
    notes=(
        "Live mode plays one story of each, with the real models reading his words: there "
        "the scenes are also the judge's."
    ),
)
async def letting_go(ev: Eval) -> None:
    budget = LIVE_TURNS if ev.live else TURNS
    for number, seed in enumerate(ev.seeds(12, live=2)):
        story = ev.story(worlds.millbrook_at_sixty(), seed=seed, settings=CALM, under_way=True)
        story.change(on_his_farm)
        if ev.live:
            # Live, the years up to the stop are `t17.own-old-age`'s to play.
            story.change(told_the_end)
        else:
            played = await to_the_end(story, FORTY, turns=budget, stop=True)
            if stopped(played) is None or not story.state.characters[YOU].alive:
                ev.check("the years stop once when the end of his life is close", False, seed)
                continue
        then = story.state
        days = pending(then, Kind.OLD_AGE)
        if number % 2 == 0:
            last = await story.act(LETS_GO, meets_it(LETS_GO, ActionKind.REST, 10 * MINUTE))
            scenes = [last]
        else:
            # He goes back to it after whatever the world stops him for.
            scenes = []
            while story.state.characters[YOU].alive and len(scenes) < budget:
                lived = meets_it(LIVES_IT_OUT, ActionKind.TIME_SKIP, 30 * DAY)
                scenes.append(await story.act(LIVES_IT_OUT, lived))
            last = scenes[-1]
        end = story.state
        you = end.characters[YOU]
        ending = last.result.ending if last.result is not None else None
        ev.metric(f"scenes it took, and the age he met it at, {seed}", [len(scenes), you.age])
        ev.check(
            "his story ends in a death of old age, never by his own hand",
            ending is not None
            and (ending.kind, ending.self_inflicted) == ("death", False)
            and not you.alive
            and lives.of_old_age(you),
            f"{seed}: {ending}, {you.status.value} at {you.age}",
        )
        if ending is None:
            continue
        if number % 2 == 0:
            ev.check(
                "letting go, it ends in that scene, within the hour",
                end.world_s - then.world_s <= 60 * MINUTE,
                f"{seed}: {(end.world_s - then.world_s) / DAY:.2f} days later",
            )
        else:
            ev.check(
                "living out his days, it ends on the day that was drawn, and no other",
                len(days) == 1 and end.world_s == days[0].due_s,
                f"{seed}: at {end.world_s}, with {[d.due_s for d in days]} drawn",
                live=False,
            )
        issues = [(i.code, i.area) for i in last.result.issues]
        ev.check(
            "the words were read twice before code acted on them",
            ("read_again", "lets_go.confirmed") in issues,
            f"{seed}: {issues}",
        )
        told = story.prompt(Node.NARRATOR)
        ev.check(
            "the last scene is handed his death of old age as its task, and told he chose it",
            "ENDING: the player character dies of old age in this scene" in told
            and '"met":"by their own choice' in told,
            f"{seed}",
            live=False,
        )
        ev.check("the record holds together (C1)", check_state(end) == [], f"{seed}")
        await ev.judge(f"he meets it, {seed}", MEETS_IT, last)

    # Before any scene told him the end is close, the same words are only a rest.
    for seed in ev.seeds(3, live=0):
        story = ev.story(worlds.millbrook_at_sixty(), seed=f"{seed}/early", settings=CALM)
        story.change(on_his_farm)
        rested = await story.act(LETS_GO, meets_it(LETS_GO, ActionKind.REST, 10 * MINUTE))
        issues = [i.code for i in rested.result.issues]
        ev.check(
            "nobody's words bring old age on before a scene told them the end is close",
            story.state.characters[YOU].alive
            and rested.result.ending is None
            and "end_untold" in issues
            and "read_again" not in issues,
            f"{seed}: {issues}",
        )
