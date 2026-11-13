"""T17's evals of old age (W6, W10): the old die while the story is elsewhere.

Code decides whom the years take and who has heard of it (`engine.world.old_age`,
`engine.world.lives`): the checks here read the record. Whether the scene of a homecoming shows
that someone died, and has nobody who died walk into it, is the judge's in live mode, and
there the record is held to the judge: it has the player character knowing of a death exactly
when the scene told one.
"""

from __future__ import annotations

import json
from collections import Counter

from engine import bonds
from engine.base import MINUTE, YEAR
from engine.contracts import ActionKind, Intent, StateDelta
from engine.invariants import check_state
from engine.labels import ago_label
from engine.state import LifeEvent, WorldState
from engine.visibility import memory_view
from engine.world import lives, old_age
from engine.world.tuning import OLD_AGE_FROM
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval
from evals.scenario import REGISTRY
from evals.scenarios.common import plan, step
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


@scenario(
    "t17.long-lived-peoples",
    suite="T17",
    title="How long each people lives",
    requirements=("G23", "W6", "A2", "T17"),
    passes_when=(
        "An elf beekeeper and one of the unsleeping dead live in Millbrook among its people. "
        "Tomas stays away a hundred years: old age takes every villager he knew, and neither "
        "the elf, whose people live six hundred years, nor the dead man, whose people old age "
        "never takes. Live, the real drafter is given a premise with humans, elves who live "
        "for centuries and risen dead who never age, and every people it writes says how long "
        "it lives: one far longer than a human life, and one that old age never takes or "
        "that lives ten thousand years and more"
    ),
    notes="Live mode drafts one world and plays no scene.",
)
async def long_lived_peoples(ev: Eval) -> None:
    for seed in ev.seeds(6, live=0):
        story = ev.story(
            worlds.millbrook_of_three_peoples(), seed=seed, settings=CALM, under_way=True
        )
        story.change(in_harrowgate)
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
