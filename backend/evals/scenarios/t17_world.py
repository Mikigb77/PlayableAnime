"""T17's evals of the wider world over the years (W6, W7): wars come to a head while the story
is elsewhere.

Code decides whether a war is fought out, how it ends and who has heard of it
(`engine.world.strife`): the checks here read the record. Whether the scene of a return shows
the world as it is now, and makes up no other end to the war, is the judge's in live mode, and
there the record is held to the judge: it has the player character knowing of the war's end
exactly when the scene showed or told it.
"""

from __future__ import annotations

import json
from collections import Counter

from engine.base import DAY, MINUTE, YEAR
from engine.context import EventFrequency, StorySettings
from engine.contracts import ActionKind, Intent, SceneEnd, StateDelta
from engine.invariants import check_state
from engine.state import FactionStatus, SceneFrame, WorldChange, WorldChangeKind, WorldState
from engine.visibility import memory_view
from engine.world import lives, telling
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval
from evals.scenario import REGISTRY
from evals.scenarios.common import plan, step
from evals.scenarios.t17_lives import live_there, ruled_out
from graph.llm import Node

scenario = REGISTRY.scenario

YOU = "tomas"
CROWN, LEAGUE = worlds.CROWN, worlds.LEAGUE
CALM = StorySettings(event_frequency=EventFrequency.CALM)
TEN = 10 * YEAR + 30 * DAY
MONTH = 30 * DAY
TURNS, LIVE_TURNS = 40, 8
AT_THE_FORD = "Tomas comes down the river road to the toll bridge at Willow Ford."


def changes(state: WorldState) -> list[WorldChange]:
    return sorted(state.changes.values(), key=lambda c: (c.world_s, c.id))


def killed(state: WorldState) -> list[str]:
    """Who is dead by anything but old age, which takes whom it takes over ten years (W6)."""
    return sorted(
        c.id for c in state.characters.values() if not c.alive and not lives.of_old_age(c)
    )


def lines_of(state: WorldState, faction_id: str) -> list[str]:
    """What Memory says under a faction."""
    return next((f.lines for f in memory_view(state).factions if f.id == faction_id), [])


def at_the_ford(state: WorldState) -> None:
    """Tomas has made the five days' road to Willow Ford, which he last saw ten years ago."""
    state.characters[YOU].location_id = "ford"
    state.scene = SceneFrame(place_id="ford", present_ids=[YOU], ended_on=AT_THE_FORD)


def look_around() -> Intent:
    return plan(
        step(
            "walk up to the toll bridge and look at who keeps it now",
            ActionKind.OBSERVE,
            10 * MINUTE,
            verb="look",
        )
    )


def scripted(narration: str, told: list[str]) -> dict:
    end = SceneEnd(ended_on="Tomas stands at the bridge.", place_id="ford", present_ids=[YOU])
    return {
        "narration": f"(scripted) {narration}",
        "told_news": told,
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


def wider_world(brief: str) -> dict:
    """The WIDER WORLD section of a brief, or nothing (a live run keeps no brief)."""
    if "## WIDER WORLD\n" not in brief:
        return {}
    return json.loads(brief.split("## WIDER WORLD\n", 1)[1].split("\n\n## ", 1)[0])


def on_record(state: WorldState) -> str:
    """What the record holds of the war and of Willow Ford, for the judge: the story is the
    eval's own (T16)."""
    ford = state.places["ford"]
    holder = state.factions.get(ford.controller_id or "")
    lines = [
        "Tomas was last at Willow Ford ten years ago, when the Eastmark League held it, and "
        "the League and the Crown of Harrow were at war. He has lived five days' road away "
        "since, and no word of the war has reached him.",
    ]
    for change in changes(state):
        years = max(1, (state.world_s - change.world_s) // YEAR)
        lines.append(f"About {years} years ago: {telling.world_change(state, change)}")
    if not state.changes:
        lines.append("The war has not been fought out: nothing has changed.")
    lines.append(f"Willow Ford is held by {holder.name if holder else 'nobody'} now.")
    lines.append("Nothing else has come of the war.")
    return "\n".join(lines)


@scenario(
    "t17.world-moves",
    suite="T17",
    title="The world moves on",
    requirements=("W6", "W7", "W10", "C6", "W2", "A2", "T17"),
    passes_when=(
        "Two kingdoms are at war, far from a farmer's valley. A month brings nothing. Over ten "
        "years most such wars are fought out, some more than once, and some never are: nothing "
        "is made to happen. Evenly matched, either side may win, a loser is weakened and loses "
        "land or falls, and both may fall. Where one side has a commander nothing the other "
        "has can stand against, that side wins whenever it comes to it, with no throw. The war "
        "kills nobody off screen: whoever died in those years died of old age. Far away the "
        "farmer hears none of it, and Memory holds none of it. When he comes to a town that "
        "changed hands, the scene is handed what became of the war, marked as having touched "
        "this place. A scene that says none of it leaves it news, whatever its answer lists, "
        "and once a scene told it, naming whom it came to, he knows, and Memory tells it with "
        "its day"
    ),
)
async def world_moves(ev: Eval) -> None:
    # A month: no time for any of it (Miki, 2026-11-13).
    in_a_month = 0
    for seed in ev.seeds(24, live=0):
        story = ev.story(
            worlds.kingdoms_at_war(), seed=f"{seed}/month", settings=CALM, under_way=True
        )
        await live_there(story, MONTH, where="on the farm", turns=TURNS)
        in_a_month += len(story.state.changes)
    ev.check("a month brings the war nowhere", in_a_month == 0, str(in_a_month), live=False)

    # Ten years, evenly matched: what the years bring varies, and nothing is made to happen.
    kinds: Counter[str] = Counter()
    winners: Counter[str] = Counter()
    fought = late = stories = 0
    for seed in ev.seeds(36, live=0):
        story = ev.story(
            worlds.kingdoms_at_war(), seed=f"{seed}/even", settings=CALM, under_way=True
        )
        began_s = story.state.world_s
        await live_there(story, TEN, where="on the farm", turns=TURNS)
        state = story.state
        stories += 1
        fought += bool(state.changes)
        first_s = min((c.world_s for c in state.changes.values()), default=None)
        late += first_s is None or first_s - began_s > 5 * YEAR
        for change in changes(state):
            kinds[change.kind.value] += 1
            if change.kind in (WorldChangeKind.BEATEN, WorldChangeKind.FELL):
                winners[change.faction_ids[0]] += 1
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}", live=False)
        ev.check(
            "far away he hears none of it, and Memory holds none of it",
            all(YOU not in c.known_by for c in state.changes.values())
            and not lines_of(state, CROWN)[2:]
            and not lines_of(state, LEAGUE)[2:],
            f"{seed}: {lines_of(state, CROWN)} {lines_of(state, LEAGUE)}",
            live=False,
        )
        ev.check(
            "the war kills nobody off screen: whoever died, died of old age",
            killed(state) == [],
            f"{seed}: {killed(state)}",
            live=False,
        )
    ev.metric("what ten years brought an even war", dict(kinds))
    ev.metric("wars fought out in ten years", f"{fought} of {stories}")
    ev.metric("wars not fought out in the first five", f"{late} of {stories}")
    # One war in four takes more than five years or never comes to it, and one in twenty-five
    # is never fought in the ten: a check on the second alone failed one run in four by the
    # luck of its 36 seeds.
    ev.check(
        "over ten years most wars are fought out, at no set time: some only late, or never",
        stories == 0 or (fought * 3 >= stories * 2 and 0 < late < stories),
        f"{fought} of {stories} fought out, {late} of them late or never",
        live=False,
    )
    ev.check(
        "evenly matched, either side may win, and a side may be beaten or fall",
        stories == 0
        or (
            winners[CROWN] > 0 and winners[LEAGUE] > 0 and kinds["beaten"] > 0 and kinds["fell"] > 0
        ),
        f"{dict(winners)} {dict(kinds)}",
        live=False,
    )

    # Ten years with the Crown's marshal in the field, and then the road to Willow Ford.
    for seed in ev.seeds(24, live=1):
        story = ev.story(
            worlds.kingdoms_at_war(marshal=True), seed=seed, settings=CALM, under_way=True
        )
        stretches = await live_there(
            story, TEN, where="on the farm", turns=LIVE_TURNS if ev.live else TURNS
        )
        state = story.state
        if ev.live:
            ev.metric(f"years on the farm, {seed}", (state.world_s) // YEAR)
            ev.metric(f"stretches ruled out, {seed}", ruled_out(stretches))
            ev.metric(f"what the years brought, {seed}", [c.kind.value for c in changes(state)])
        happened = changes(state)
        league = state.factions[LEAGUE]
        ev.check(
            "with nothing to stand against its marshal, the Crown wins whenever it comes to it",
            all(
                c.kind is WorldChangeKind.FELL and c.faction_ids == [CROWN, LEAGUE]
                for c in happened
            )
            and len(happened) <= 1
            and (league.status is FactionStatus.DESTROYED) == bool(happened),
            f"{seed}: {[(c.kind.value, c.faction_ids) for c in happened]}",
        )
        ev.check(
            "far from it he knows nothing of it",
            all(YOU not in c.known_by for c in happened),
            f"{seed}",
            live=False,
        )
        if not happened:
            continue  # the war was never fought out: there is nothing to come back to
        (fall,) = happened
        ev.check(
            "what the League held is the Crown's, occupied, and its people live on",
            all(state.places[p].controller_id == CROWN for p in ("ford", "eastmark"))
            and killed(state) == [],
            f"{seed}: {killed(state)}",
        )

        story.change(at_the_ford)
        if not ev.live:
            await story.act(
                "I walk up to the toll bridge and look at who keeps it now",
                look_around(),
                narration=scripted(
                    "The bridge is where it was. Tomas pays and crosses.", [fall.id]
                ),
            )
            handed = wider_world(story.prompt(Node.NARRATOR))
            ev.check(
                "the scene in a town that changed hands is handed what became of the war",
                [n.get("id") for n in handed.get("news", [])] == [fall.id]
                and handed["news"][0].get("here") is True
                and "One marked here" in handed.get("tell", ""),
                f"{seed}: {handed}",
            )
            state = story.state
            ev.check(
                "a scene that says none of it leaves it news, and Memory without it",
                YOU not in state.changes[fall.id].known_by
                and "Destroyed" not in lines_of(state, LEAGUE),
                f"{seed}: {lines_of(state, LEAGUE)}",
            )
        seen = await story.act(
            "I walk up to the toll bridge and look at who keeps it now",
            look_around(),
            narration=None
            if ev.live
            else scripted("The Crown's men keep the toll now, in Harrow's colours.", [fall.id]),
        )
        state = story.state
        knows = YOU in state.changes[fall.id].known_by
        if ev.live:
            ev.metric(f"heard in the scene, {seed}", knows)
        ev.check(
            "once a scene told it, naming whom it came to, he knows",
            knows,
            f"{seed}",
            live=False,
        )
        told = lines_of(state, LEAGUE)
        ev.check(
            "Memory tells what he learned of it, with its day",
            not knows or ("Destroyed" in told and any("day " in line for line in told)),
            f"{seed}: {told}",
        )
        judgement = await ev.judge(
            "back at the ford after ten years",
            Rubric(
                must=(
                    "The scene shows Willow Ford under whoever CONTEXT says holds it now, or "
                    "someone in it says what CONTEXT says became of the war",
                ),
                must_not=(
                    "The scene gives the war an end, a winner or a loser that CONTEXT doesn't",
                    "Tomas already knows how the war ended before he sees or is told",
                ),
            ),
            seen,
            context=on_record(state),
        )
        if judgement is not None and judgement.error is None:
            shown = next((v.passed for v in judgement.verdicts if v.id == "M1"), None)
            if shown is not None:
                # C6: Memory holds what the story told, so the record is held to the judge.
                ev.check(
                    "the record has him knowing of it exactly when the scene showed or told it",
                    shown == knows,
                    f"{seed}: the judge found it shown: {shown}; on record: {knows}",
                )
