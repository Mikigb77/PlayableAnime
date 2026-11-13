"""T17's evals of others' power over the years (W6, G19): whoever is climbing goes on climbing
while the story is elsewhere, at the pace their own record shows, and nobody is lifted.

Code decides who rises and who has heard of it (`engine.world.climbing`,
`engine.world.lives`): the checks here read the record. Whether the scene of a homecoming
shows that someone rose, and has nobody else risen, is the judge's in live mode, and there
the record is held to the judge: it has the player character knowing of a rise exactly when
the scene told one.
"""

from __future__ import annotations

import json
from collections import Counter

from engine.base import HOUR, MINUTE, YEAR
from engine.contracts import ActionKind, GrowthKind, Intent, SceneEnd, StateDelta
from engine.invariants import check_state
from engine.labels import ago_label
from engine.state import LadderPosition, LifeEvent, LifeKind, SceneFrame, WorldState
from engine.world import climbing, lives, old_age
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval
from evals.scenario import REGISTRY
from evals.scenarios.common import plan, step
from evals.scenarios.t17_lives import CALM, LIVE_TURNS, MONTH, TEN, TURNS, live_there, ruled_out
from evals.scenarios.t17_old_age import in_memory
from graph.llm import Node

scenario = REGISTRY.scenario

YOU = "lin"
HUNDRED = 100 * YEAR + MONTH
# Whom Lin knows on the mountain, and who stands on the realms there: Elder Mo he never met.
KNOWN = (worlds.SU, worlds.WEN, worlds.ZHAO, worlds.OLD_HE, worlds.COOK_MA)
CLIMBERS = (worlds.SU, worlds.WEN, worlds.ZHAO, worlds.OLD_HE, worlds.ELDER_MO)
IN_GREYWATER = "Lin has taken a room over a dyer's yard in Greywater, five days down the river."
AT_THE_WELL = "Lin climbs the last steps to the outer-court well, a pack on his shoulder."


def in_greywater(state: WorldState) -> None:
    """Lin has left the mountain for a town where no word of it reaches him."""
    state.characters[YOU].location_id = "town"
    state.scene = SceneFrame(place_id="town", present_ids=[YOU], ended_on=IN_GREYWATER)


def alone_at_the_well(state: WorldState) -> None:
    """Lin stays on the mountain, with nobody beside him as the years begin."""
    state.scene = SceneFrame(place_id="well", present_ids=[YOU], ended_on=AT_THE_WELL)


def back_at_the_well(present: list[str]):
    def change(state: WorldState) -> None:
        state.characters[YOU].location_id = "well"
        state.scene = SceneFrame(place_id="well", present_ids=[YOU, *present], ended_on=AT_THE_WELL)

    return change


def on_realms(state: WorldState, who: str) -> LadderPosition | None:
    return next((p for p in state.characters[who].sheet.ladders if p.ladder_id == "realms"), None)


def rungs(state: WorldState) -> dict[str, int | None]:
    """Where everyone but the player character stands on the realms: nothing off them."""
    stand = {}
    for person in state.npcs():
        on = on_realms(state, person.id)
        stand[person.id] = on.rung if on is not None else None
    return stand


def standing(state: WorldState) -> dict[str, tuple]:
    """Everyone but the player character as the years left them: their rung, whether they
    live, and their age."""
    stand = rungs(state)
    return {c.id: (stand[c.id], c.alive, c.age) for c in state.npcs()}


def rose(state: WorldState, who: str | None = None) -> list[LifeEvent]:
    """The news of people rising, of everyone or of one of them."""
    return [
        e
        for e in state.lives.values()
        if e.kind is LifeKind.ROSE and (who is None or who in e.subject_ids)
    ]


def breakthroughs(state: WorldState, who: str, since_s: int) -> list:
    """The rungs someone's own sheet says they reached since a moment."""
    gains = state.characters[who].sheet.growth
    return [g for g in gains if g.source == GrowthKind.BREAKTHROUGH.value and g.world_s >= since_s]


def by_fortune(state: WorldState, who: str, since_s: int) -> bool:
    return any("fortune" in g.reason for g in breakthroughs(state, who, since_s))


def behind(state: WorldState, who: str) -> float:
    """The effort behind someone where they stand on the realms, in seconds."""
    ladder = state.bible.ladder("realms")
    return climbing.behind_s(state.characters[who], ladder, on_realms(state, who))


def rose_line(state: WorldState, who: str, rung: str) -> bool:
    """Whether Memory tells that someone rose to a rung, with its day."""
    return any(f"Rose to {rung}" in line and "day " in line for line in in_memory(state, who)[1])


def in_scene(brief: str, who: str) -> dict:
    """What a brief shows its scene of someone in it."""
    if "## SCENE\n" not in brief:
        return {}  # a live run keeps no brief
    scene = json.loads(brief.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
    return next((p for p in scene.get("present", []) if p["id"] == who), {})


def accounted(ev: Eval, seed: str, before: WorldState, state: WorldState) -> None:
    """What holds of every rise, however long the years (G19): it is on the riser's own
    sheet with its reason, their own pace over those years pays for it unless fortune
    brought it, and nobody stepped onto the realms or past the top of them."""
    since_s = before.world_s
    years = (state.world_s - since_s) / YEAR
    was, now = rungs(before), rungs(state)
    top = len(state.bible.ladder("realms").rungs) - 1
    ev.check(
        "nobody steps onto the realms, and nobody passes the top of them",
        all((now[who] is None) == (was[who] is None) for who in was)
        and all(rung is None or rung <= top for rung in now.values()),
        f"{seed}: {was} then {now}",
    )
    climbed = {who: now[who] - was[who] for who in was if was[who] is not None}
    ev.check(
        "nobody loses a rung, and every rung risen is on the riser's own sheet with its reason",
        all(
            risen >= 0
            and len(breakthroughs(state, who, since_s)) == risen
            and all(g.reason for g in breakthroughs(state, who, since_s))
            for who, risen in climbed.items()
        ),
        f"{seed}: {climbed}",
    )
    # In hours of work: what is behind them now, less what was behind them then.
    owed = {
        who: (behind(state, who) - behind(before, who)) / HOUR
        for who in climbed
        if not by_fortune(state, who, since_s)
    }
    paid = {who: (on_realms(state, who).yearly_s or 0) * years / HOUR for who in owed}
    ev.check(
        "every rise the years brought is paid for by those years at the riser's own pace",
        all(owed[who] <= paid[who] + 1 for who in owed),
        f"{seed}: over {years:.1f} years { {w: (round(owed[w]), round(paid[w])) for w in owed} }",
    )


def greet(present: list[str]) -> Intent:
    return plan(
        step(
            "greet my fellow disciples at the well and ask how far each has come",
            ActionKind.CONVERSATION,
            20 * MINUTE,
            verb="greet",
            target_ids=present,
        )
    )


def nod(present: list[str]) -> Intent:
    return plan(
        step(
            "nod to the disciples at the well and draw a bucket of water",
            ActionKind.CONVERSATION,
            5 * MINUTE,
            verb="nod",
            target_ids=present,
        )
    )


def at_the_well(present: list[str], ended_on: str) -> SceneEnd:
    return SceneEnd(ended_on=ended_on, place_id="well", present_ids=[YOU, *present])


def passing_scene(present: list[str], told: list[str]) -> dict:
    """A scripted scene at the well that names nobody, and lists every piece of news it was
    handed, as a narrator may."""
    end = at_the_well(present, "Lin drinks from the bucket, the court watching him.")
    return {
        "narration": "(scripted) Lin nods to the faces at the well and draws a bucket of water.",
        "told_news": told,
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


def risen_scene(present: list[str], name: str, rung: str, told: list[str]) -> dict:
    """A scripted scene that says, by name, that one of them rose, and lists every piece of
    news it was handed."""
    end = at_the_well(present, "The court has gathered at the well to look at him.")
    return {
        "narration": (
            f"(scripted) Ten years show on every face at the well. {name} stands at {rung} "
            "now, and carries it lightly."
        ),
        "told_news": told,
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


def on_record(before: WorldState, state: WorldState, present: list[str]) -> str:
    """What the record holds of who rose on the mountain and who didn't, for the judge: the
    story is the eval's own (T16). `before` is the mountain as he left it."""
    ladder = state.bible.ladder("realms")
    was = rungs(before)
    lines = [
        "Lin Feng left Azure Peak ten years ago for Greywater, five days off, and no word "
        "from the mountain has reached him since. He is back at the outer-court well now.",
        "The realms, lowest first: " + ", ".join(r.name for r in ladder.rungs) + ".",
        "The people of the outer court he knows, with the realm each stood on when he left "
        "and stands on now:",
    ]
    for who in KNOWN:
        person = state.characters[who]
        if not person.alive:
            lines.append(f"- {person.name} has died.")
            continue
        if was[who] is None:
            lines.append(f"- {person.name} ({person.age}): a mortal on no realm, then and now.")
            continue
        then, now = ladder.rungs[was[who]].name, ladder.rungs[rungs(state)[who]].name
        if then == now:
            lines.append(f"- {person.name} ({person.age}): {now} then, and still {now}.")
            continue
        gain = breakthroughs(state, who, before.world_s)[-1]
        when = ago_label(max(0, state.world_s - gain.world_s))
        how = "by a stroke of fortune" if "fortune" in gain.reason else "by years of their own work"
        lines.append(f"- {person.name} ({person.age}): {then} then, rose to {now} {when}, {how}.")
    lines.append("With him in the scene: " + ", ".join(state.characters[i].name for i in present))
    own = ladder.rungs[on_realms(state, YOU).rung].name
    lines.append(f"Lin himself stands at {own}. Nobody else he knows rose.")
    return "\n".join(lines)


@scenario(
    "t17.others-rise",
    suite="T17",
    title="Others climb while he is away",
    requirements=("W6", "W10", "G19", "C6", "A2", "A3", "T17"),
    passes_when=(
        "A disciple leaves his sect for a town five days off and comes home ten years later. "
        "A month away moves nobody. Over the ten years some of those who stood on the realms "
        "have risen, each at the pace their own record shows: who varies from story to story, "
        "the junior with a knack for it rises in more stories than the one without, and the "
        "gatekeeper who spent ninety years on the lowest realm stays on it unless a stroke of "
        "fortune lifts him. Every rung risen is on the riser's own sheet with its reason and "
        "is paid for by the years at their own pace, nobody steps onto the realms who never "
        "stood on them, and nobody passes the top. Far away he hears none of it, and Memory "
        "holds none of it. The scene of his return shows whoever rose on their new realm with "
        "the rise as news under them. A scene that names nobody leaves it news, whatever its "
        "answer lists, and once a scene said by name who rose he knows of that rise and of no "
        "other, and Memory tells it with its day. Someone who stays on the mountain instead "
        "knows of each rise as it happens. Over a hundred years the mortal dies of old age, "
        "and the gatekeeper too unless he broke through, whoever lives stands on a realm that "
        "lets them live so long, a rise of someone he never met is news to nobody, and the "
        "same years with him on the highest realm leave everyone exactly where they stand "
        "with him on the lowest: nobody is lifted to meet him"
    ),
)
async def others_rise(ev: Eval) -> None:
    # A month away: no time for any of it.
    in_a_month = 0
    for seed in ev.seeds(24, live=0):
        story = ev.story(
            worlds.azure_peak_he_leaves(), seed=f"{seed}/month", settings=CALM, under_way=True
        )
        story.change(in_greywater)
        was = rungs(story.state)
        await live_there(story, MONTH, where="in Greywater", turns=TURNS)
        in_a_month += len(rose(story.state)) + (rungs(story.state) != was)
    ev.check("a month away moves nobody", in_a_month == 0, str(in_a_month), live=False)

    risers: Counter[str] = Counter()
    lucky: Counter[str] = Counter()
    stories = 0
    for seed in ev.seeds(24, live=1):
        story = ev.story(worlds.azure_peak_he_leaves(), seed=seed, settings=CALM, under_way=True)
        story.change(in_greywater)
        left = story.state
        stretches = await live_there(
            story, TEN, where="in Greywater", turns=LIVE_TURNS if ev.live else TURNS
        )
        state = story.state
        years = (state.world_s - left.world_s) // YEAR
        was, now = rungs(left), rungs(state)
        climbed = sorted(who for who in CLIMBERS if now[who] != was[who])
        risers.update(climbed)
        lucky.update(who for who in climbed if by_fortune(state, who, left.world_s))
        stories += 1
        if ev.live:
            ev.metric(f"years away, {seed}", years)
            ev.metric(f"stretches ruled out, {seed}", ruled_out(stretches))
        ev.metric(f"who rose, {seed}", {who: now[who] for who in climbed})
        ev.check("ten years went by", years == 10, f"{seed}: {years}", live=False)
        accounted(ev, seed, left, state)
        news = rose(state)
        ev.check(
            "a rise is news only of someone he knows of, the latest rung they reached",
            sorted(e.subject_ids[0] for e in news) == [w for w in climbed if w in KNOWN]
            and all(
                e.rung == state.bible.ladder("realms").rungs[now[e.subject_ids[0]]].name
                for e in news
            ),
            f"{seed}: {[(e.subject_ids, e.rung) for e in news]} for {climbed}",
        )
        ev.check(
            "far away he hears none of it, and Memory holds none of it",
            all(YOU not in e.known_by for e in news)
            and not any(rose_line(state, e.subject_ids[0], e.rung or "") for e in news),
            f"{seed}: {[e.id for e in news if YOU in e.known_by]}",
            live=False,
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}")
        met = [e.subject_ids[0] for e in news if state.characters[e.subject_ids[0]].alive]
        if not met:
            continue  # nobody he knows rose in these years: there is no rise to come home to

        # Home again, with whoever rose and one of the juniors who didn't, where there is one.
        riser = next(who for who in KNOWN if who in met)
        same = [who for who in (worlds.WEN, worlds.SU, worlds.ZHAO) if who not in met][:1]
        present = [riser, *same]
        story.change(back_at_the_well(present))
        before = story.state
        (rise,) = rose(before, riser)
        person = before.characters[riser]
        handed = [e.id for e in lives.news_of(before, person)[-5:]]
        if rise.id not in handed:
            # The years brought them more news than a brief carries, or a live scene far from
            # home already told him of it.
            ev.metric(f"no rise left to tell at the well, {seed}", riser)
            continue
        if not ev.live:
            # A scene at the well that names nobody: it is still news.
            await story.act(
                "I nod to the disciples at the well and draw a bucket of water",
                nod(present),
                narration=passing_scene(present, handed),
            )
            brief = story.prompt(Node.NARRATOR)
            shown = in_scene(brief, riser)
            ev.check(
                "the scene of his return shows them on their new realm, the rise news under them",
                [p["rung"] for p in shown.get("sheet", {}).get("ladders", [])] == [rise.rung]
                and any(
                    piece.get("id") == rise.id and piece["what"].startswith(f"rose to {rise.rung}")
                    for piece in shown.get("news", [])
                )
                and "yearly_s" not in brief,
                f"{seed}: {shown.get('news')}",
            )
            state = story.state
            ev.check(
                "a scene that names nobody leaves it news, whatever its answer lists",
                YOU not in state.lives[rise.id].known_by
                and not rose_line(state, riser, rise.rung or ""),
                f"{seed}: {state.lives[rise.id].known_by}",
            )
        seen = await story.act(
            "I greet my fellow disciples at the well and ask how far each has come",
            greet(present),
            narration=None
            if ev.live
            else risen_scene(present, person.name, rise.rung or "", handed),
        )
        state = story.state
        heard = [e.subject_ids[0] for e in rose(state) if YOU in e.known_by]
        if ev.live:
            ev.metric(f"rises heard in the scene, {seed}", f"{len(heard)} of {len(met)}")
        ev.check(
            "once a scene said by name who rose he knows of that rise and of no other",
            heard == [riser],
            f"{seed}: heard {heard}, the scene named {riser}",
            live=False,
        )
        ev.check(
            "Memory tells a rise he heard of with its day, and no other",
            all(
                rose_line(state, e.subject_ids[0], e.rung or "") == (e.subject_ids[0] in heard)
                for e in rose(state)
            ),
            f"{seed}: {heard}",
        )
        judgement = await ev.judge(
            "home after ten years, and someone has risen",
            Rubric(
                must=(
                    "The scene shows, or someone in it says, that at least one of the people "
                    "CONTEXT says rose now stands on the realm CONTEXT gives them, or has "
                    "broken through since Lin left",
                ),
                must_not=(
                    "Someone CONTEXT says is still on the realm they stood on is shown or "
                    "said to have risen to a higher realm",
                    "Someone CONTEXT says rose is said to stand on a realm above the one "
                    "CONTEXT gives them",
                    "Lin already knows that someone rose before he sees it or is told",
                ),
            ),
            seen,
            context=on_record(left, before, present),
        )
        if judgement is not None and judgement.error is None:
            told = next((v.passed for v in judgement.verdicts if v.id == "M1"), None)
            if told is not None:
                # C6: Memory holds what the story told, so the record is held to the judge.
                ev.check(
                    "the record has him knowing of a rise exactly when the scene told one",
                    told == bool(heard),
                    f"{seed}: the judge found a rise told: {told}; on record: {heard}",
                )

    ev.metric("who rose in ten years, in how many stories", dict(risers))
    ev.metric("of them by a stroke of fortune", dict(lucky))
    ev.check(
        "who rises varies from story to story: nothing is made to happen",
        stories == 0 or all(0 < risers[who] < stories for who in (worlds.WEN, worlds.ZHAO)),
        f"{dict(risers)} of {stories}",
        live=False,
    )
    ev.check(
        "a knack for the climb tells, and so do ninety years on the lowest realm: only fortune "
        "lifts the gatekeeper",
        risers[worlds.SU] > risers[worlds.WEN] and risers[worlds.OLD_HE] == lucky[worlds.OLD_HE],
        f"{dict(risers)} of {stories}, by fortune {dict(lucky)}",
        live=False,
    )

    # Someone who stays on the mountain knows of each rise as it happens.
    for seed in ev.seeds(12, live=0):
        story = ev.story(
            worlds.azure_peak_he_leaves(), seed=f"{seed}/home", settings=CALM, under_way=True
        )
        story.change(alone_at_the_well)
        played = await live_there(story, TEN, where="on the mountain", turns=TURNS)
        state = story.state
        news = rose(state)
        ev.check(
            "living near, he knows of each rise as it happens, and Memory tells it",
            all(
                YOU in e.known_by and rose_line(state, e.subject_ids[0], e.rung or "") for e in news
            )
            and not any(lives.news_of(state, state.characters[who]) for who in KNOWN),
            f"{seed}: {[(e.subject_ids, e.known_by) for e in news]}",
            live=False,
        )
        told = [brief for _, brief in played if '"what":"rose to ' in brief]
        ev.check(
            "the scene that covers the time is told of it in passing",
            not news or bool(told),
            f"{seed}: {len(told)} briefs for {[e.subject_ids for e in news]}",
            live=False,
        )

    # A hundred years: nobody is lifted to meet him, whatever he made of them.
    after: Counter[str] = Counter()
    for seed in ev.seeds(12, live=0):
        ends = []
        for rung in (0, 4):
            story = ev.story(
                worlds.azure_peak_he_leaves(rung=rung),
                seed=f"{seed}/century",
                settings=CALM,
                under_way=True,
            )
            story.change(in_greywater)
            left = story.state
            await live_there(story, HUNDRED, where="in Greywater", turns=TURNS)
            ends.append(story.state)
            if rung == 0:
                accounted(ev, f"{seed}/century", left, story.state)
        state, lifted = ends
        people = state.characters
        ev.check(
            "a hundred years went by, and he is a hundred years older",
            people[YOU].age == 116 and people[YOU].alive,
            f"{seed}: {people[YOU].age}",
            live=False,
        )
        ev.check(
            "with him on the highest realm everyone stands exactly where they stand with him "
            "on the lowest: nobody is lifted to meet him",
            standing(state) == standing(lifted),
            f"{seed}: {standing(state)} against {standing(lifted)}",
            live=False,
        )
        now = rungs(state)
        after.update(
            f"{who}: {'dead' if not people[who].alive else now[who]}"
            for who in (*KNOWN, worlds.ELDER_MO)
        )
        ev.check(
            "a hundred years take the mortal, and the gatekeeper unless he broke through",
            not people[worlds.COOK_MA].alive
            and (not people[worlds.OLD_HE].alive or now[worlds.OLD_HE] > 0),
            f"{seed}: {standing(state)}",
            live=False,
        )
        ev.check(
            "whoever lives stands on a realm that lets them live so long",
            all(
                c.age is None or c.age <= 1.25 * old_age.span(state, c)
                for c in state.npcs()
                if c.alive
            ),
            f"{seed}: {standing(state)}",
            live=False,
        )
        ev.check(
            "a rise of someone he never met is news to nobody",
            not rose(state, worlds.ELDER_MO),
            f"{seed}: {[e.id for e in rose(state, worlds.ELDER_MO)]}",
            live=False,
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/century")
    ev.metric("where a hundred years left them, in how many stories", dict(sorted(after.items())))
