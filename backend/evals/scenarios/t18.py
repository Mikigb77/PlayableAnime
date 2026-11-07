"""T18's narration, voice and picture evals (docs/REQUIREMENTS.md, T18).

Deterministic mode checks what code hands the narrator: the beats in order, the last moment, the
sheet, the player's own words, and a plan that stops at its first miss (R1 to R7). Live mode lets
the real interpret step read the player's words, and the judge reads the telling and the
pictures (V3, M5, M6).
"""

from __future__ import annotations

import math
import re

from engine.base import MINUTE
from engine.contracts import (
    ActionKind,
    Aim,
    Beat,
    BeatUse,
    BeatVerdict,
    CharacterChange,
    Harm,
    Intent,
    OutcomeClass,
    PictureKind,
    PictureTrigger,
    Plausibility,
    StateDelta,
    UseSource,
)
from engine.state import SkillLevel, StepResult
from evals import worlds
from evals.judge import PICTURE_INSTRUCTIONS, Rubric
from evals.pictures import Picture, ending, scene_brief
from evals.runner import Eval
from evals.scenario import LIVE_ONLY, REGISTRY
from evals.scenarios.common import act, attack, plan, step
from graph.llm import Node
from media.prompts import FRAMING, build_prompt
from moderation.evals import build_world, load_cases

scenario = REGISTRY.scenario
pending = REGISTRY.pending


def in_order(text: str, parts: list[str]) -> bool:
    """Whether every part appears in `text`, each after the one before."""
    at = 0
    for part in parts:
        found = text.find(part, at)
        if found < 0:
            return False
        at = found + len(part)
    return True


def words(text: str) -> str:
    """Lower case, curly quotes made straight, punctuation and spacing dropped."""
    text = text.replace("’", "'").casefold()
    return " ".join(re.sub(r"[^\w' ]+", " ", text).split())


# --- Stone and troll (R1 to R3) ----------------------------------------------------------------

STONE_BEATS = ("crouch and sweep a hand over the flagstones", "close on a loose stone", "throw it")


def grab_and_throw() -> Intent:
    stone = BeatUse(
        source=UseSource.NEW, thing="a loose stone", plausibility=Plausibility.PLAUSIBLE
    )
    return plan(
        attack(
            "troll",
            text="grab a stone and throw it at the troll",
            verb="throw",
            aim=Aim.WOUND,
            beats=[
                Beat(text=STONE_BEATS[0]),
                Beat(text=STONE_BEATS[1], uses=[stone]),
                Beat(
                    text=STONE_BEATS[2], uses=[stone.model_copy(update={"source": UseSource.CANON})]
                ),
            ],
        )
    )


@scenario(
    "t18.stone-and-troll",
    suite="T18",
    title="Stone and troll",
    requirements=("R1", "R2", "R3", "T18"),
    passes_when=(
        "The scene opens on the lunge and shows the search, the find and the throw, in that "
        "order, before any result, with no decision added (R1 to R3)"
    ),
)
async def stone_and_troll(ev: Eval) -> None:
    for seed in ev.seeds(5, live=2):
        story = ev.story(worlds.troll_lunges(), seed=seed, under_way=True)
        played = await story.act("I grab a stone and throw it at the troll", grab_and_throw())
        ev.check(
            "no decision is added", len(played.steps) == 1, f"{seed}: {len(played.steps)} steps"
        )
        beats = played.step(0).beats
        ev.check(
            "the courtyard plausibly holds a stone, so it is found (R2)",
            any(b.verdict is BeatVerdict.MADE_CANON for b in beats),
            f"{seed}: {[b.verdict for b in beats]}",
            live=False,
        )
        prompt = story.prompt(Node.NARRATOR)
        ev.check(
            "the narrator is told the last moment, the lunge (R3)",
            "lunges at Lin" in prompt,
            seed,
            live=False,
        )
        ev.check(
            "and the beats in order (R1, R2)",
            in_order(prompt, list(STONE_BEATS)),
            seed,
            live=False,
        )
        await ev.judge(
            "the stone and the troll",
            Rubric(
                must=(
                    "The scene opens on the troll's lunge",
                    "It shows the search, the find and the throw, in that order, before any result",
                ),
                must_not=("Adds a decision the player didn't make",),
            ),
            played,
        )


# --- The action told first (R1, R7) -------------------------------------------------------------

# Miki, 2026-11-07: the player wrote it like a story, and the scene opened on the merchant taking
# the coin. Every scene tells the character doing it first, in the story's own prose.
PAYING = (
    "I look at him firmly, hold out a gold tael between two fingers and say: I want this potion."
)
PAY_LINE = "I want this potion."


def pay_for_the_draught() -> Intent:
    tael = BeatUse(source=UseSource.CARRIED, thing="a gold tael", ref="gold-tael")
    return plan(
        step(
            "pay Old Hu a gold tael for the healing draught",
            ActionKind.CONVERSATION,
            10,
            verb="buy",
            target_ids=["old-hu"],
            beats=[
                Beat(text="look Old Hu firmly in the eye"),
                Beat(text="hold out a gold tael between two fingers", uses=[tael]),
                Beat(text="say he wants the potion"),
            ],
            lines=[PAY_LINE],
        )
    )


@scenario(
    "t18.action-told-first",
    suite="T18",
    title="The action told first",
    requirements=("R1", "R7", "T18"),
    passes_when=(
        "Even when the player writes the action like a story, the scene first tells Lin doing it "
        "in its own prose (the firm look, the tael held out, the line), and only then Old Hu's "
        "answer (R1)"
    ),
)
async def action_told_first(ev: Eval) -> None:
    for seed in ev.seeds(3, live=3):
        story = ev.story(worlds.potion_stall(), seed=seed, under_way=True)
        played = await story.act(PAYING, pay_for_the_draught())
        prompt = story.prompt(Node.NARRATOR)
        ev.check(
            "the narrator gets the player's own words, gestures and manner included (R1)",
            PAYING in prompt,
            seed,
            live=False,
        )
        if ev.live:
            issues = [i.code for i in played.result.issues] if played.result is not None else []
            ev.check(
                "the scene tells the action in its own part before what comes of it",
                "action_untold" not in issues,
                f"{seed}: {issues}",
            )
            ev.check(
                "Lin says the line word for word (R7)",
                words(PAY_LINE) in words(played.narration),
                seed,
            )
        await ev.judge(
            "the payment told before the answer",
            Rubric(
                must=(
                    "The scene opens on Lin doing what the player said: the firm look, the gold "
                    "tael held out and the line, before Old Hu takes the coin or answers",
                    "It tells that in the story's own prose, with more than the player wrote",
                ),
                must_not=(
                    "It opens on Old Hu taking the coin, answering or handing over the potion",
                    "It copies the player's sentence as written",
                ),
            ),
            played,
        )


# --- Result as action (R1, R5, A6) -------------------------------------------------------------


@scenario(
    "t18.result-as-action",
    suite="T18",
    title="Result as action",
    requirements=("R1", "R5", "A6", "A2", "T18"),
    passes_when=(
        "The kill is played as an attempt that succeeds at roughly the roll's odds, and a miss "
        "is shown as a swing that meets something (R1, R5, A6)"
    ),
)
async def result_as_action(ev: Eval) -> None:
    odds, wins, misses = [], 0, []
    kill = plan(attack("troll", "sword", text="kill the troll"))
    for seed in ev.seeds(200, live=4):
        story = ev.story(worlds.troll_lunges(), seed=seed, under_way=True)
        played = await story.act("I pick up the sword and kill the troll", kill)
        swing = played.step(0)
        ev.check(
            "the kill is an attempt, rolled",
            swing.roll is not None and swing.outcome_class is not OutcomeClass.CERTAIN,
            f"{seed}: {swing.outcome_class}",
        )
        if swing.roll is None:
            continue
        odds.append(swing.roll.odds)
        if swing.result is StepResult.SUCCESS:
            wins += 1
        else:
            misses.append(played)
            ev.check(
                "a miss leaves the troll alive",
                played.state.characters["troll"].alive,
                seed,
            )
    if odds and not ev.live:
        expected = sum(odds) / len(odds)
        rate = wins / len(odds)
        spread = 4 * math.sqrt(expected * (1 - expected) / len(odds))
        ev.metric("stated_odds", round(expected, 3))
        ev.metric("success_rate", round(rate, 3))
        ev.check(
            "it succeeds at roughly the roll's odds",
            abs(rate - expected) <= spread,
            f"{rate:.3f} against {expected:.3f}",
        )
    if misses:
        await ev.judge(
            "a miss is a swing that meets something",
            Rubric(
                must=(
                    "The kill is played as an attempt, and the miss meets something: a parry, "
                    "a dodge, a hide too thick",
                ),
                must_not=("The narration says the troll dies",),
            ),
            misses[:2],
        )


# --- Skill shows (R4) --------------------------------------------------------------------------


def leaf_cut() -> Intent:
    return act("cut the falling leaf in two", "cut", ActionKind.EXCHANGE, 2)


@scenario(
    "t18.skill-shows",
    suite="T18",
    title="Skill shows",
    requirements=("R4", "G13", "G14", "T18"),
    passes_when="The two scenes look clearly different, and each fits its sheet (R4)",
)
async def skill_shows(ev: Eval) -> None:
    for seed in ev.seeds(2, live=1):
        scenes = []
        for level in (SkillLevel.NOVICE, SkillLevel.MASTER):
            story = ev.story(worlds.sword_stroke(level), seed=f"{seed}/{level}", under_way=True)
            played = await story.act("I cut the falling leaf in two", leaf_cut())
            scenes.append((f"{level.value} swordsman", played))
            ev.check(
                "the narrator sees the sheet's skill level",
                "swordsmanship" in story.prompt(Node.NARRATOR)
                and level.value in story.prompt(Node.NARRATOR),
                f"{seed}: {level}",
                live=False,
            )
        await ev.judge(
            "a novice's stroke and a sword saint's",
            Rubric(
                must=(
                    "The two scenes look clearly different",
                    "The novice's stroke looks like a novice's and the master's like a master's",
                ),
            ),
            scenes,
        )


# --- Broken plan (R6) --------------------------------------------------------------------------


def throw_then_run() -> Intent:
    return plan(
        attack("troll", "stone", text="throw the stone at the troll", verb="throw", aim=Aim.WOUND),
        step("run for the tunnel", ActionKind.MOVE, 30, verb="run", target_ids=["tunnel"]),
    )


@scenario(
    "t18.broken-plan",
    suite="T18",
    title="Broken plan",
    requirements=("R6", "S2", "T18"),
    passes_when="After a miss the scene stops, and the player decides whether to run (R6)",
)
async def broken_plan(ev: Eval) -> None:
    misses = []
    for seed in ev.seeds(40, live=4):
        state = worlds.troll_lunges()
        worlds.give(
            state,
            "lin",
            worlds.Item(id="stone", name="a fist-sized stone", kind=worlds.ItemKind.GEAR),
        )
        story = ev.story(state, seed=seed, under_way=True)
        played = await story.act("I throw the stone, then run for the tunnel", throw_then_run())
        throw = played.step(0)
        if throw.result is StepResult.SUCCESS:
            # The troll strikes back all the same (N6); only a blow that lands stops the run.
            landed = any(a.harm is not Harm.NONE for a in throw.perils)
            ev.check(
                "a clean hit lets the run play, unless the troll's blow lands",
                len(played.steps) == (1 if landed else 2),
                f"{seed}: {[a.reason for a in throw.perils]}",
            )
            continue
        misses.append(played)
        ev.check(
            "after a miss the plan stops, and the run isn't played",
            len(played.steps) == 1
            and played.resolution.stopped_at_step == 0
            and any("tunnel" in u for u in played.resolution.unplayed),
            f"{seed}: {[s.text for s in played.steps]} unplayed {played.resolution.unplayed}",
        )
    ev.check("some seeds miss", bool(misses), str(len(misses)))
    if misses:
        await ev.judge(
            "the plan stops at the miss",
            Rubric(
                must=("After the throw misses, the scene stops before the run",),
                must_not=("Lin runs for the tunnel anyway",),
            ),
            misses[:2],
        )


# --- Nothing there (R2) ------------------------------------------------------------------------


def grab_a_stone() -> Intent:
    stone = BeatUse(source=UseSource.NEW, thing="a stone", plausibility=Plausibility.ABSENT)
    return plan(
        step(
            "grab a stone",
            ActionKind.INSTANT,
            2,
            verb="grab",
            beats=[Beat(text="look around for a stone", uses=[stone])],
        )
    )


@scenario(
    "t18.nothing-there",
    suite="T18",
    title="Nothing there",
    requirements=("R2", "T18"),
    passes_when=(
        "No stone appears from nowhere: the character finds something else, or nothing (R2)"
    ),
)
async def nothing_there(ev: Eval) -> None:
    for seed in ev.seeds(5, live=2):
        story = ev.story(worlds.throne_room(), seed=seed, under_way=True)
        played = await story.act("I grab a stone", grab_a_stone())
        grab = played.step(0)
        stones = [
            b for b in grab.beats if "stone" in b.thing and b.verdict is not BeatVerdict.EMPTY
        ]
        ev.check(
            "no stone appears in the marble hall",
            not stones,
            f"{seed}: {[(b.thing, b.verdict) for b in grab.beats]}",
        )
        await ev.judge(
            "no stone from nowhere",
            Rubric(
                must=("Lin finds no stone, or finds something else the hall really holds",),
                must_not=("A stone appears in the polished marble hall",),
            ),
            played,
        )


# --- Own words (R7) ----------------------------------------------------------------------------

LINE = "You'll pay for this with your life."


@scenario(
    "t18.own-words",
    suite="T18",
    title="Own words",
    requirements=("R7", "V3", "T18"),
    passes_when='The character says "You\'ll pay for this with your life" (R7)',
)
async def own_words(ev: Eval) -> None:
    said = "I tell him, um, you'll pay for this with your life"
    for seed in ev.seeds(3, live=3):
        story = ev.story(worlds.insulted(), seed=seed, under_way=True)
        played = await story.act(
            said,
            plan(
                step(
                    "tell Zhao he'll pay with his life",
                    ActionKind.CONVERSATION,
                    10,
                    verb="threaten",
                    target_ids=["zhao"],
                    lines=[LINE],
                )
            ),
        )
        ev.check(
            "the narrator gets the player's line, cleaned of filler",
            LINE in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        if ev.live:
            intent = played.result.intent if played.result is not None else None
            lines = [ln for s in (intent.steps if intent else []) for ln in s.lines]
            ev.check(
                "the interpret step keeps the words and drops the filler",
                any(words(LINE) == words(ln) for ln in lines),
                f"{seed}: {lines}",
            )
            ev.check(
                "the character says it word for word",
                words(LINE) in words(played.narration),
                seed,
            )


# --- Spoken mess (V3, S10) ---------------------------------------------------------------------

# (transcript, the person meant, the verb the player settled on, whether it harms them)
TRANSCRIPTS = (
    ("I attack Senior Brother Jo, no wait, I bow to him", "zhao", False),
    ("um so I uh ask Elder Moe about the the tournament", "elder-mo", False),
    ("I draw my sword on Way, I mean Wei, no, I just wave at Wei", "wei", False),
    ("I, uh, I punch Zhao, yeah, punch Senior Brother Zhao in the face", "zhao", True),
    ("Ataco al hermano mayor Jau, no, espera, le hago una reverencia", "zhao", False),
    ("Eh, le pregunto al anciano Mo, digo, al Anciano Mo, por el torneo", "elder-mo", False),
)


@scenario(
    "t18.spoken-mess",
    suite="T18",
    title="Spoken mess",
    requirements=("V3", "S10", "T18"),
    passes_when="The interpret step reads the final intent and the right person (V3)",
    modes=LIVE_ONLY,
    notes="The Spanish lines check S10's language support once it lands; they run today.",
)
async def spoken_mess(ev: Eval) -> None:
    state = worlds.sect_with_a_witness()
    state.characters["elder-mo"].location_id = "well"
    state.scene.present_ids.append("elder-mo")
    for n, (transcript, person, harmful) in enumerate(TRANSCRIPTS):
        story = ev.story(state.model_copy(deep=True), seed=f"{ev.scenario.id}/{n}", under_way=True)
        played = await story.act(transcript)
        intent = played.result.intent if played.result is not None else None
        targets = {t for s in (intent.steps if intent else []) for t in s.target_ids}
        harms = any(s.aim.harmful for s in (intent.steps if intent else []))
        ev.check("it reads the right person", person in targets, f"{transcript!r}: {targets}")
        ev.check(
            "it reads the final intent",
            harms is harmful,
            f"{transcript!r}: {[(s.verb, s.aim) for s in (intent.steps if intent else [])]}",
        )


pending(
    "t18.name-accuracy",
    suite="T18",
    title="Name accuracy",
    requirements=("V6", "V1", "T18"),
    passes_when=(
        "Reports the share of names heard right, per recognizer and language. This sets V6's "
        "default"
    ),
    waits_for="recorded clips of players speaking the story's names, and a recognizer to run",
)


# --- Same face (M5) ----------------------------------------------------------------------------

FACE_SCENES = (
    ("I bow to the grey mage and ask his name", "bow", ActionKind.CONVERSATION, 60),
    ("I spar with the grey mage by the well", "spar", ActionKind.EXCHANGE, 30),
    ("I follow the grey mage up the mountain path", "follow", ActionKind.MOVE, 10 * MINUTE),
    ("I share tea with the grey mage at dusk", "drink", ActionKind.CONVERSATION, 20 * MINUTE),
    ("I watch the grey mage meditate in the rain", "watch", ActionKind.TASK, 10 * MINUTE),
    ("I strike at the grey mage's face", "strike", ActionKind.EXCHANGE, 2),
    ("I ask the grey mage whether his eye still hurts", "ask", ActionKind.CONVERSATION, 60),
    ("I walk with the grey mage through the night market", "walk", ActionKind.MOVE, 20 * MINUTE),
    ("I train beside the grey mage at dawn", "train", ActionKind.TASK, 30 * MINUTE),
    ("I say goodbye to the grey mage at the gate", "say goodbye", ActionKind.CONVERSATION, 60),
)
MAIMED = 5  # the scene where the mage loses his eye


def maiming() -> dict:
    update = StateDelta(
        characters=[
            CharacterChange(
                id="mage",
                look_change="lost his left eye",
                appearance="Sixty, gaunt, grey robes, a staff of black wood, a scar where his "
                "left eye was.",
            )
        ]
    )
    return {
        "narration": "(scripted) Lin's blade opens the grey mage's face; the left eye is gone.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


@scenario(
    "t18.same-face",
    suite="T18",
    title="Same face",
    requirements=("M5", "M4", "M1", "G17", "T18"),
    passes_when=(
        "Judges see the same person every time (M5), and after a maiming the face is still the "
        "same person, with the change visible"
    ),
)
async def same_face(ev: Eval) -> None:
    for seed in ev.seeds(2, live=1):
        story = ev.story(worlds.mage_fight(), seed=seed, under_way=True)
        story.change(lambda s: s.characters["mage"].met_by.append("lin"))
        portrait = await ev.draw_portrait(story, "mage", "portrait-mage")
        pictures: list[tuple[str, Picture]] = []
        redrawn = None
        # How the mage looks after the strike, when it changed his look for good. The scripted
        # narration takes his left eye; a live narrator decides for itself, so the rubric asks
        # for whatever change it recorded, or none.
        maimed_look: str | None = None
        for n, (said, verb, kind, seconds) in enumerate(FACE_SCENES):
            hit = n == MAIMED
            interpretation = (
                plan(attack("mage", "sword", aim=Aim.WOUND, text="strike at the mage's face"))
                if hit
                else act(said.removeprefix("I ").lower(), verb, kind, seconds)
            )
            played = await story.act(
                said, interpretation, narration=maiming() if hit and not ev.live else None
            )
            if hit:
                mage = played.state.characters["mage"]
                ev.check(
                    "the maiming changes the mage's look for good",
                    mage.look_version == 2,
                    f"{seed}: version {mage.look_version}",
                    live=False,
                )
                if mage.look_version > 1:
                    maimed_look = mage.appearance
            if n == MAIMED + 1:
                ev.check(
                    "and his portrait is drawn once more (M4, M5)",
                    played.plan.picture is not None
                    and played.plan.picture.trigger is PictureTrigger.LOOK_CHANGED
                    and played.plan.picture.subject_id == "mage",
                    f"{seed}: {played.plan.picture}",
                    live=False,
                )
                if portrait is not None and maimed_look is not None:
                    redrawn = await ev.draw_portrait(story, "mage", "portrait-mage-maimed")
            after = n > MAIMED and maimed_look is not None
            reference = redrawn if after and redrawn is not None else portrait
            if reference is not None:
                drawn = await ev.draw_scene(
                    story,
                    played,
                    name=f"scene-{n + 1}",
                    people=["mage"],
                    references=[(story.state.characters["mage"].name, reference)],
                )
                if isinstance(drawn, Picture):
                    pictures.append(
                        (f"scene {n + 1}{' (after the maiming)' if after else ''}", drawn)
                    )
        if portrait is not None and pictures:
            shown = [("the portrait", portrait)]
            if redrawn is not None:
                shown.append(("the portrait after the maiming", redrawn))
            must = [
                "Every picture shows the same man as the first portrait: the same face, age and "
                "build, apart from a lasting change named below"
            ]
            if maimed_look is not None:
                must.append(
                    "The portrait after the maiming and every scene marked after the maiming show "
                    f"the lasting change to his face; he now looks like this: {maimed_look}"
                )
            await ev.judge_pictures(
                "the same face in ten scenes",
                Rubric(must=tuple(must), instructions=PICTURE_INSTRUCTIONS),
                shown + pictures,
            )


# --- Mild pictures (M6) ------------------------------------------------------------------------


@scenario(
    "t18.mild-pictures",
    suite="T18",
    title="Mild pictures",
    requirements=("M6", "F2", "T18"),
    passes_when=("No nudity or sexual content, and no more than mild gore, in any picture (M6)"),
    modes=LIVE_ONLY,
)
async def mild_pictures(ev: Eval) -> None:
    for case in load_cases():
        if case.expect.picture is None:
            continue
        world = build_world(case)
        if world is None:
            continue
        story = ev.story(
            world,
            seed=f"{ev.scenario.id}/{case.id}",
            rating=case.rating,
            prefs=case.content_prefs,
        )
        await story.open()
        played = None
        for line in case.script:
            played = await story.act(line)
        if played is None or played.result is None:
            continue
        picture = await ev.draw_scene(story, played, name=case.id)
        await ev.judge_mild(f"{case.id}: the picture is mild", picture)


# --- The moment as told (M5, C10), and the cover as the story's poster (M1) -------------------

LEAP = "I leap from branch to branch up the old pines, to see over the outer wall"
# Places and a weapon that are in the story's premise but not in the scene, as a premise often
# has them. None of them may reach a scene's picture; a cover may show the ruins and the river.
LEAP_PREMISE = (
    "You are Lin Feng, an orphan and an outer disciple of the Azure Cloud Sect. Across the great "
    "river below the mountain stand the ruins of the castle where your clan once ruled, and your "
    "father's dagger is said to wait there for you."
)


def _leap(ev: Eval, seed: str, *, cover: bool):
    """Lin's leap through the pines, in a story whose cover is still to come, or was drawn."""
    story = ev.story(worlds.among_the_pines(), seed=seed, premise=LEAP_PREMISE, under_way=True)
    if not cover:
        # The cover and the well were pictured earlier, so this scene is one the player
        # illustrates, drawn from its own text.
        story.change(lambda s: s.director.pictured.extend(["cover", "place:well", "place:well:v1"]))
    return story


@scenario(
    "t18.moment-as-told",
    suite="T18",
    title="The moment as told",
    requirements=("M5", "C10", "T18"),
    passes_when=(
        "A scene's picture shows what that scene tells: the player character doing what they "
        "did, where they did it, with only the things they have, and nothing from the premise "
        "that the scene doesn't have (M5, C10)"
    ),
)
async def moment_as_told(ev: Eval) -> None:
    for seed in ev.seeds(1, live=1):
        story = _leap(ev, seed, cover=False)
        played = await story.act(
            LEAP, act(LEAP.removeprefix("I ").split(",")[0], "leap", ActionKind.MOVE, 60)
        )
        if played.result is None:
            continue
        ev.check(
            "the leap plans no picture of its own, so it is illustrated from its text (M2)",
            played.scene.picture is None,
            f"{seed}: {played.scene.picture}",
            live=False,
        )
        prompt = build_prompt("scene", scene_brief(played.state, ending(played.narration))).user
        ev.check(
            "the scene is told Lin carries nothing, so it gives him no weapon (C10)",
            "Lin Feng carries no weapon" in prompt,
            f"{seed}: {prompt}",
            live=False,  # a live scene may hand him something on the way up
        )
        told = prompt.replace(FRAMING["scene"], "").casefold()  # what this picture is told
        ev.check(
            "and never sees the premise, whose ruins and dagger aren't in the scene (M5)",
            not any(word in told for word in ("castle", "ruins", "dagger")),
            f"{seed}: {prompt}",
        )
        ev.check("and is lit for the scene's time of day (W10)", "Time of day:" in prompt)
        picture = await ev.draw_scene(story, played, name="scene")
        if isinstance(picture, Picture):
            await ev.judge_pictures(
                "the picture shows the scene as told",
                Rubric(
                    must=(
                        "The picture shows the moment the scene below tells: Lin up in the pine "
                        "branches, leaping or climbing from one to the next, not standing or "
                        "crouching on a roof, a wall or the ground",
                        "Lin holds and wears no weapon: no sword, dagger or knife",
                        "Nothing the scene doesn't have: no castle, ruins, river or town",
                    ),
                    instructions=PICTURE_INSTRUCTIONS,
                ),
                [("the picture", picture)],
                context=f"The scene, as the player read it:\n{played.narration}",
            )


@scenario(
    "t18.cover-as-poster",
    suite="T18",
    title="The cover as the story's poster",
    requirements=("M1", "M5", "C10", "T18"),
    passes_when=(
        "The story's cover, planned in its second scene, is its poster: the main character in "
        "the story's world, premise included, dramatic rather than one scene's moment, with only "
        "the things they have (M1, C10)"
    ),
)
async def cover_as_poster(ev: Eval) -> None:
    for seed in ev.seeds(1, live=1):
        story = _leap(ev, seed, cover=True)
        played = await story.act(
            LEAP, act(LEAP.removeprefix("I ").split(",")[0], "leap", ActionKind.MOVE, 60)
        )
        if played.result is None:
            continue
        planned = played.scene.picture
        ev.check(
            "the second scene gets the story's cover, shown in that scene (M1)",
            planned is not None and planned.kind is PictureKind.COVER,
            f"{seed}: {planned}",
        )
        if planned is None:
            continue
        brief = scene_brief(played.state, planned.prompt, cover=True, premise=LEAP_PREMISE)
        prompt = build_prompt("cover", brief).user
        ev.check(
            "the cover is drawn with the premise, the story's world (M1)",
            "ruins of the castle where your clan once ruled" in prompt,
            f"{seed}: {prompt}",
        )
        ev.check(
            "as a poster, with no one scene's hour",
            FRAMING["cover"] in prompt and "Time of day:" not in prompt,
            f"{seed}: {prompt}",
        )
        ev.check(
            "and Lin still carries nothing, so it gives him no weapon (C10)",
            "Lin Feng carries no weapon" in prompt,
            f"{seed}: {prompt}",
            live=False,  # a live scene may hand him something on the way up
        )
        picture = await ev.draw_scene(story, played, name="cover")
        if isinstance(picture, Picture):
            await ev.judge_pictures(
                "the cover is the story's poster",
                Rubric(
                    must=(
                        "The picture works as the story's cover: a dramatic, iconic composition "
                        "around Lin in a world of cultivation sects, not a plain record of one "
                        "moment",
                        "It sums up the story below, and may show the castle ruins across the "
                        "river from its premise",
                        "Lin holds and wears no weapon: no sword, dagger or knife",
                    ),
                    instructions=PICTURE_INSTRUCTIONS,
                ),
                [("the cover", picture)],
                context=f"The story's premise:\n{LEAP_PREMISE}",
            )
