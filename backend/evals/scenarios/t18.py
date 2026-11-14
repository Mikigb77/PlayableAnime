"""T18's narration, voice and picture evals (docs/REQUIREMENTS.md, T18).

Deterministic mode checks what code hands the narrator: the beats in order, the last moment, the
sheet, the player's own words, and a plan that stops at its first miss (R1 to R7). Live mode lets
the real interpret step read the player's words, and the judge reads the telling and the
pictures (V3, M5, M6).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace

from engine.base import MINUTE
from engine.context import Language, StorySettings
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
    PlaceChange,
    Plausibility,
    SceneEnd,
    SceneWeight,
    StateDelta,
    UseSource,
)
from engine.resolve import throw as dice
from engine.state import PlaceSetting, SkillLevel, StepResult, WorldState
from engine.world.geography import is_within
from evals import worlds
from evals.judge import LINES_INSTRUCTIONS, PICTURE_INSTRUCTIONS, Rubric
from evals.pictures import Picture, ending, portrait_brief, scene_brief
from evals.runner import Eval, Played
from evals.scenario import LIVE_ONLY, REGISTRY
from evals.scenarios.common import act, attack, plan, skill, step
from graph.language import written_in
from graph.llm import Node
from graph.turn import saying
from media.notes import SceneText, note_prompt
from media.prompts import FRAMING, GROUNDED, build_prompt
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


def grab_and_throw(thing: str = "a loose stone") -> Intent:
    stone = BeatUse(source=UseSource.NEW, thing=thing, plausibility=Plausibility.PLAUSIBLE)
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


# --- A scene's ending is shown, never told (S4, R1) ---------------------------------------------

# The first plays on the real models (2026-11-14) had scenes that closed by telling the player
# their move: "You must decide whether to slip your sleeping powder into his wine, or keep him
# charmed here", "The time has come to slip away and secure the schedules", "It is time to
# rest, or perhaps to share what you have done". Each stands where the character has something
# to decide and hasn't yet, which is where a narrator is most tempted.
LOOK_AT_THE_THIEF = "I stop in the barn door and look at the man asleep in my hay"
STAND_ON_THE_BRIDGE = "I stop in the middle of the bridge and look at the three of them"
ENDING_SHOWN = Rubric(
    must=(
        "The scene's last lines show where things stand, so the player has something there to "
        "act on. A closing sentence about what the character sees or thinks doesn't undo that",
    ),
    must_not=(
        "The scene's last lines tell the player what they must or should do, decide or choose",
        "The scene's last lines say that it is time, or that the time has come, to do something",
        "The scene's last lines list the ways open to the character, as a choice between them",
    ),
)


@scenario(
    "t18.ending-shown",
    suite="T18",
    title="An ending shown, never told",
    requirements=("S4", "R1", "T18"),
    modes=LIVE_ONLY,
    passes_when=(
        "A farmer finds a thief asleep in his barn, and a disciple stands on a rope bridge "
        "with three thugs closing in: each only stops and looks. Each scene ends on where "
        "things stand, and never tells the player what they must do, decide or choose, that it "
        "is time to do something, or which ways are open to them (S4)"
    ),
    notes=(
        "Live only: what a scene's last lines do is the judge's to read. The rule is in the "
        "narrator's form, on the field the ending is written in (`NarratorOutput.narration`)."
    ),
)
async def ending_shown(ev: Eval) -> None:
    for seed in ev.seeds(0, live=2):
        barn = ev.story(worlds.thief_in_the_barn(), seed=f"{seed}/barn", under_way=True)
        looked = await barn.act(LOOK_AT_THE_THIEF, None)
        await ev.judge("the thief asleep in the hay", ENDING_SHOWN, looked)
        bridge = ev.story(worlds.bridge_ambush(), seed=f"{seed}/bridge", under_way=True)
        stood = await bridge.act(STAND_ON_THE_BRIDGE, None)
        await ev.judge("three thugs on the bridge", ENDING_SHOWN, stood)


# --- A scene's length follows its weight (R3) ---------------------------------------------------

# Miki's long story, read on 2026-11-10: the typical scene came to 258 words whether one question
# was asked or a duel was fought.
ASK_HU = "I ask Old Hu what the draught is for"
STRIKE_ZHAO = "I draw my sword and strike at Zhao Kun"
# At the medium setting the narrator is asked for 60 to 120 words for a passing moment and 250 to
# 400 for a turning point, and a telling may run a little over or under what it was asked for.
PASSING_AT_MOST, TURNING_AT_LEAST = 160, 200


def ask_about_the_draught() -> Intent:
    return plan(
        step(
            "ask Old Hu what the draught is for",
            ActionKind.CONVERSATION,
            20,
            verb="ask",
            target_ids=["old-hu"],
        )
    )


def strike_at_zhao() -> Intent:
    return plan(
        attack(
            "zhao",
            "sword",
            text="draw his sword and strike at Zhao Kun",
            verb="strike",
            aim=Aim.WOUND,
        )
    )


@scenario(
    "t18.length-follows-weight",
    suite="T18",
    title="Length follows weight",
    requirements=("R3", "S6", "T18"),
    passes_when=(
        "The question is weighed a passing moment and told short, the fight's start with a key "
        "character is weighed a turning point and given room, and the short scene still tells "
        "the asking and ends on something to act on (R3)"
    ),
)
async def length_follows_weight(ev: Eval) -> None:
    passing = 0
    for seed in ev.seeds(5, live=3):
        quiet = ev.story(worlds.potion_stall(), seed=f"{seed}/quiet", under_way=True)
        asked = await quiet.act(ASK_HU, ask_about_the_draught())
        fight = ev.story(worlds.potion_stall(), seed=f"{seed}/fight", under_way=True)
        struck = await fight.act(STRIKE_ZHAO, strike_at_zhao())

        given = asked.plan.event or asked.plan.moment or asked.plan.happenings or asked.plan.talk
        ev.check(
            "a question with nothing at stake is a passing moment, unless the scene was given "
            "something of its own to tell",
            asked.plan.weight is (SceneWeight.ORDINARY if given else SceneWeight.LIGHT),
            f"{seed}: {asked.plan.weight.value}",
            live=False,
        )
        ev.check(
            "a fight's start with a key character is a turning point",
            struck.plan.weight is SceneWeight.HEAVY,
            f"{seed}: {struck.plan.weight.value}",
        )
        ev.check(
            "the narrator is asked for each scene's length, within the player's setting (S6)",
            ("A passing moment: 60 to 120 words." in quiet.prompt(Node.NARRATOR))
            is (asked.plan.weight is SceneWeight.LIGHT)
            and "A turning point: 250 to 400 words." in fight.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        passing += asked.plan.weight is SceneWeight.LIGHT
        if not ev.live:
            continue
        short, long = len(asked.narration.split()), len(struck.narration.split())
        if asked.plan.weight is SceneWeight.LIGHT:
            ev.check(
                "the passing moment is told short",
                0 < short <= PASSING_AT_MOST,
                f"{seed}: {short} words",
            )
            await ev.judge(
                "a short scene is still a whole scene",
                Rubric(
                    must=(
                        "The scene tells Lin asking before Old Hu answers",
                        "It ends on something Lin could act on",
                    ),
                    must_not=("It fills the moment with happenings nobody asked for",),
                ),
                asked,
            )
        if struck.plan.weight is SceneWeight.HEAVY:
            ev.check(
                "the turning point gets room",
                long >= TURNING_AT_LEAST,
                f"{seed}: {long} words",
            )
        if asked.plan.weight is not struck.plan.weight:
            ev.check(
                "the question comes to fewer words than the fight",
                short < long,
                f"{seed}: {short} against {long} words",
            )
    ev.check(
        "most quiet questions are passing moments",
        passing >= 3,
        f"{passing} of 5",
        live=False,
    )


# --- Looks and stock phrases (R9) ---------------------------------------------------------------

# Miki's long story, read on 2026-11-10: "deep black eyes" in 16 scenes of 187 and the leather
# boots in 17, because the narrator had the character's looks on every turn.
PLAIN_QUESTIONS = (
    "I ask Old Hu what the draught is for",
    "I ask Old Hu where he gathers his herbs",
    "I ask Old Hu how long he has kept this stall",
)
TIE_HAIR = "I tie my hair back and ask Old Hu what he wants for the draught"
# What a scripted scene leans on, three scenes running.
STOCK = "Old Hu strokes his thin beard. Your steady eyes hold his gaze."


def ask_old_hu(text: str) -> Intent:
    return plan(
        step(
            text.removeprefix("I "),
            ActionKind.CONVERSATION,
            20,
            verb="ask",
            target_ids=["old-hu"],
        )
    )


def scripted_scene(n: int, *, rewrites_looks: bool = False) -> dict:
    """A scripted scene that leans on the same wording as the others and, when asked, writes
    Lin an appearance it was never handed, as a live one can."""
    looks = CharacterChange(id="lin", appearance="Tall, with golden hair and green eyes.")
    update = StateDelta(characters=[looks] if rewrites_looks else [])
    return {
        "narration": f"(scripted scene {n}) {STOCK}",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def player_record(prompt: str) -> str:
    return prompt.split("## PLAYER CHARACTER\n", 1)[-1].split("\n\n## ", 1)[0]


@scenario(
    "t18.looks-and-stock-phrases",
    suite="T18",
    title="Looks and stock phrases",
    requirements=("R9", "C9", "T18"),
    passes_when=(
        "The plain scenes are written without the character's appearance or the line on how "
        "they come across and don't describe how they look, a scene that writes them one "
        "leaves the kept appearance as it was, the "
        "hair they tie back is the hair on record, and wording three scenes repeated is handed "
        "to the narrator as worn (R9)"
    ),
)
async def looks_and_stock_phrases(ev: Eval) -> None:
    for seed in ev.seeds(3, live=2):
        story = ev.story(worlds.potion_stall(), seed=seed, under_way=True)
        kept = story.state.player.appearance
        plain: list[Played] = []
        for n, question in enumerate(PLAIN_QUESTIONS):
            scripted = None if ev.live else scripted_scene(n, rewrites_looks=n == 2)
            played = await story.act(question, ask_old_hu(question), narration=scripted)
            handed = played.result is not None and played.result.looks
            picture = played.plan.picture
            shown = picture is not None and (
                picture.kind is PictureKind.SCENE or picture.subject_id == "lin"
            )
            ev.check(
                "a plain scene is handed no appearance, unless its picture shows them",
                handed is shown,
                f"{seed}: turn {played.turn}",
            )
            # The record is read offline only: a live story's prompts aren't kept.
            record = json.loads(player_record(story.prompt(Node.NARRATOR)) or "{}")
            ev.check(
                "and its brief carries none, nor the line on how they come across",
                ("appearance" in record) is handed and ("description" in record) is handed,
                f"{seed}: turn {played.turn}",
                live=False,
            )
            if not handed:
                plain.append(played)
        ev.check(
            "the appearance on record is the one the story keeps (C9)",
            story.state.player.appearance == kept,
            seed,
        )
        tied = await story.act(TIE_HAIR, ask_old_hu(TIE_HAIR))
        ev.check(
            "an action about their hair is handed the appearance",
            tied.result is not None and tied.result.looks,
            seed,
        )
        prompt = story.prompt(Node.NARRATOR)
        ev.check(
            "with the hair on record",
            "black hair tied back" in player_record(prompt),
            seed,
            live=False,
        )
        worn = (
            prompt.split("## WORN\n", 1)[-1].split("\n\n## ", 1)[0] if "## WORN" in prompt else ""
        )
        ev.check(
            "wording three scenes repeated is handed over as worn",
            "eyes hold his gaze" in worn and "hu" not in words(worn).split(),
            f"{seed}: {worn}",
            live=False,
        )
        if plain:
            await ev.judge(
                "plain scenes that don't describe the character",
                Rubric(
                    must=("Each scene tells Lin's question and Old Hu's answer",),
                    # What the first live run showed (2026-11-12) is none of R9's: an expression
                    # ("your face serene") is no look, and Old Hu calling the sect's weakest
                    # disciple a weakling is the world answering, not the telling crediting a trait.
                    must_not=(
                        "The telling describes how Lin himself looks: the colour or shape of his "
                        "eyes, his hair, his build, the features of his face or his clothes. An "
                        "expression or a gesture is not a look",
                        "The telling itself brings up one of Lin's own traits or powers, such as "
                        "his past life's memories, though the action doesn't use it. What Old Hu "
                        "says of Lin in his answer is not the telling",
                    ),
                ),
                plain,
            )
        await ev.judge(
            "the hair on record",
            Rubric(
                must=("The scene shows Lin tying his hair back before Old Hu answers",),
                must_not=("Lin's hair is any colour but black",),
            ),
            tied,
        )


# --- Where the character is (R8) ----------------------------------------------------------------

# Miki, 2026-11-08: a Spanish story took the character from a temple under the earth to "un claro",
# and the next scene had them still inside the temple.
CLIMB_OUT = "Subo los últimos escalones y salgo del templo al bosque"
LOOK_AROUND = "Miro a mi alrededor"


def climb_out() -> Intent:
    return plan(
        step(
            "climb the last steps and walk out of the temple into the wood",
            ActionKind.MOVE,
            60,
            verb="climb",
            beats=[Beat(text="climb the last worn steps"), Beat(text="step out into the wood")],
        )
    )


def out_in_a_clearing() -> dict:
    """The scripted scene: out of the temple into a clearing it adds within the wood, named at
    its end by its name rather than its id, as a model may write it."""
    update = StateDelta(
        places=[
            PlaceChange(
                id="fern-clearing",
                name="the fern clearing",
                kind="clearing",
                setting=PlaceSetting.OUTDOORS,
                parent_id="wood",
                visited=True,
            )
        ],
        scene_end=SceneEnd(
            ended_on="Lin stands among the ferns, the temple's stairwell a dark mouth behind him.",
            place_id="The Fern Clearing",
            present_ids=["lin"],
        ),
    )
    return {
        "action": "(scripted) Lin climbs the last worn steps and comes out of the temple.",
        "narration": "(scripted) Grey daylight through the pines, and a clearing of ferns.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


@scenario(
    "t18.out-of-the-temple",
    suite="T18",
    title="Out of the temple",
    requirements=("R8", "R3", "W7", "T18"),
    passes_when=(
        "Climbing out of a temple under the earth is told as the crossing into the open air, the "
        "scene ends in a place outside the temple, and the next scene starts there, under the "
        "sky (R8)"
    ),
)
async def out_of_the_temple(ev: Eval) -> None:
    look = act("look around", "look", ActionKind.OBSERVE, 30)
    for seed in ev.seeds(1, live=2):
        story = ev.story(
            worlds.buried_temple(),
            seed=seed,
            under_way=True,
            settings=StorySettings(language=Language.ES),
        )
        out = await story.act(
            CLIMB_OUT, climb_out(), narration=None if ev.live else out_in_a_clearing()
        )
        brief = story.prompt(Node.NARRATOR)
        ev.check(
            "the narrator reads the temple as underground, within the wood (R8)",
            '"setting":"underground"' in brief and '"within":[{"id":"wood"' in brief,
            seed,
            live=False,
        )
        state = out.state
        here = state.scene.place_id
        ev.check(
            "the scene that leaves the temple ends in a place outside it (R8)",
            here is not None and not is_within(state, here, "temple"),
            f"{seed}: {here}",
        )
        ev.check(
            "the record has the player character where the scene ended (R8, C2)",
            state.player.location_id is not None
            and not is_within(state, state.player.location_id, "temple"),
            f"{seed}: {state.player.location_id}",
        )
        await ev.judge(
            "the way out told as the crossing",
            Rubric(
                must=(
                    "The scene shows Lin climbing the last steps and coming out of the temple "
                    "into the open air: the crossing itself is told",
                    "Once out, it is plainly outdoors, in the wood: sky, daylight, wind or trees "
                    "overhead",
                ),
                must_not=(
                    "It leaves it unclear whether Lin is still inside the temple",
                    "It calls a space inside the temple by a word for an open-air place, such as "
                    "a clearing ('claro')",
                ),
            ),
            out,
        )
        after = await story.act(LOOK_AROUND, look)
        ev.check(
            "the next scene starts where the last one ended (R3, R8)",
            '"id":"fern-clearing"' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        await ev.judge(
            "the next scene outside",
            Rubric(
                must=("The scene happens outdoors, in the wood where the last scene left Lin",),
                must_not=(
                    "It puts Lin back inside the temple: under its ceiling, among its pillars "
                    "or its walls",
                ),
            ),
            after,
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
    return plan(
        step(
            "cut the falling leaf in two",
            ActionKind.EXCHANGE,
            2,
            verb="cut",
            uses=[skill("swordsmanship")],
        )
    )


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
            stroke = played.step(0)
            ev.check(
                "the stroke is made with their swordsmanship, at the level the sheet gives",
                stroke.hand == f"Swordsmanship ({level.value})",
                f"{seed}: {level.value}: hand {stroke.hand!r}, {stroke.outcome_class.value}, "
                f"{stroke.result.value}, {stroke.reason}",
            )
            ev.check(
                "the narrator is told the hand beside the outcome, whatever the result",
                f'"hand":"Swordsmanship ({level.value})"' in story.prompt(Node.NARRATOR),
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


# --- Something natural (R2) --------------------------------------------------------------------

# However the interpret step files the branch, and with its judgement left out as often as not.
BRANCH_FILED = (
    (UseSource.NEW, Plausibility.PLAUSIBLE),
    (UseSource.NEW, None),
    (UseSource.SCENE, None),
    (UseSource.CANON, None),
    (UseSource.SCENE, Plausibility.PLAUSIBLE),
)


def snap_a_branch(source: UseSource, plausibility: Plausibility | None) -> Intent:
    branch = BeatUse(source=source, thing="a dead branch", plausibility=plausibility)
    return plan(
        step(
            "snap a dead branch off the nearest pine",
            ActionKind.INSTANT,
            4,
            verb="snap",
            beats=[Beat(text="reach up and snap off a dead branch", uses=[branch])],
        )
    )


@scenario(
    "t18.something-natural",
    suite="T18",
    title="Something natural",
    requirements=("R2", "A2", "T18"),
    passes_when=(
        "Lin has the branch, with no roll for it and no search that comes up empty: what a "
        "place of that kind would hold is simply there (R2)"
    ),
)
async def something_natural(ev: Eval) -> None:
    for n, seed in enumerate(ev.seeds(len(BRANCH_FILED), live=3)):
        story = ev.story(worlds.among_the_pines(), seed=seed, under_way=True)
        action = "I snap a dead branch off the nearest pine"
        played = await story.act(action, snap_a_branch(*BRANCH_FILED[n % len(BRANCH_FILED)]))
        beats = [b for s in played.steps for b in s.beats]
        ev.check(
            "nothing natural comes up empty or is rolled for (R2)",
            all(b.verdict is not BeatVerdict.EMPTY and b.roll is None for b in beats),
            f"{seed}: {[(b.thing, b.source, b.verdict, b.roll is not None) for b in beats]}",
        )
        ev.check(
            "and no step is ruled out (A2)",
            all(s.outcome_class is not OutcomeClass.RULED_OUT for s in played.steps),
            f"{seed}: {[(s.outcome_class, s.reason) for s in played.steps]}",
        )
        ev.check(
            "the scene's record keeps the branch for the next turn (R3)",
            "a dead branch" in played.state.scene.props,
            f"{seed}: {played.state.scene.props}",
            live=False,
        )
        await ev.judge(
            "the branch is simply there",
            Rubric(
                must=("Lin ends up with a branch from the pines in hand",),
                must_not=(
                    "The search for a branch fails, or comes up empty",
                    "The scene says there is no branch to be had",
                ),
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


# --- The engine's lines in the story's language (S10) -------------------------------------------

# The review of Miki's story, 2026-11-11: "Zephyr can push back: a real effort, your speed in your
# favour" stood in English under a Spanish scene, and no player talks like that.
THROWS_SAID = (
    (Language.ES, "Cojo una piedra y se la lanzo al trol"),
    (Language.CA, "Agafo una pedra i la llanço al trol"),
)

# The first word of a verb the reading may give the grab or the throw, as code reads it (B5).
THROW_VERBS = frozenset(
    "throw hurl toss fling lob pelt stone attack strike hit grab take pick seize snatch find "
    "search crouch get".split()
)

# Words an English sentence can hardly do without, and Spanish and Catalan don't have.
ENGLISH_ONLY = frozenset("the and with of at it its his her their from into".split())


def in_english(text: str) -> bool:
    """Whether `text` reads as English: it holds one of the words only English has."""
    return any(word in ENGLISH_ONLY for word in re.findall(r"[^\W\d_]+", text.casefold()))


# A story names its people, its places and its things in its own language (S10), and the engine
# keeps a name as it is spelled. So each story here has the troll's courtyard under its own
# names, and the stone as its interpret step would note it.
COURTYARD_SAID = {
    Language.ES: {
        "troll": "el trol de las cavernas",
        "looks": "Un trol de las cavernas de piel gris, con un garrote.",
        "well": "el pozo del patio exterior",
        "tunnel": "el túnel de desagüe",
        "ended_on": (
            "El trol de las cavernas ruge y se abalanza sobre Lin, con el garrote ya en alto."
        ),
        "stone": "una piedra suelta",
    },
    Language.CA: {
        "troll": "el trol de les coves",
        "looks": "Un trol de les coves de pell grisa, amb una porra.",
        "well": "el pou del pati exterior",
        "tunnel": "el túnel de desguàs",
        "ended_on": (
            "El trol de les coves rugeix i s'abraona sobre en Lin, amb la porra ja enlaire."
        ),
        "stone": "una pedra solta",
    },
}


def troll_lunges_in(language: Language) -> WorldState:
    """`worlds.troll_lunges` as a story in `language` names it."""
    said = COURTYARD_SAID[language]
    state = worlds.troll_lunges()
    troll = state.characters["troll"]
    troll.name, troll.description = said["troll"], said["looks"]
    state.places["well"].name = said["well"]
    state.places["tunnel"].name = said["tunnel"]
    state.scene.ended_on = said["ended_on"]
    return state


def as_met(lines: saying.Lines) -> list[str]:
    """Every line of `lines` the engine wrote, in the order the player meets them, repeats
    included, so two tellings of one turn line up."""
    met: list[str] = []

    def note(text: str) -> str:
        met.append(text)
        return text

    lines.reworded(note)
    return met


def lines_said(played: Played, language: Language) -> list[tuple[str, str]]:
    """(The engine's English line, how the saved scene has it), for each line of a turn that
    needs words."""
    english = saying.lines_of(played.resolution, played.plan, language)
    event = played.scene.event
    shown = replace(
        english, details=played.scene.details, event_title=event.title if event else None
    )
    pairs = zip(as_met(english), as_met(shown), strict=True)
    return [(was, said) for was, said in pairs if any(char.isalpha() for char in was)]


@scenario(
    "t18.story-language",
    suite="T18",
    title="The engine's lines in the story's language",
    requirements=("S10", "A3", "A8", "B5", "B8", "T18"),
    passes_when=(
        'In a Spanish and a Catalan story the dice and "How it played out" say every line the '
        "engine wrote in the story's language, as a player would say it, with each number and "
        "name kept; the dice still go out before the telling, the saved scene keeps the lines "
        "as they were shown, and the reading names each step's verb in English and writes the "
        "step and its beats in the story's language (S10)"
    ),
)
async def story_language(ev: Eval) -> None:
    for language, action in THROWS_SAID:
        pairs: dict[tuple[str, str], None] = {}
        for seed in ev.seeds(3, live=2):
            story = ev.story(
                troll_lunges_in(language),
                seed=f"{seed}/{language.value}",
                under_way=True,
                settings=StorySettings(language=language),
            )
            played = await story.act(action, grab_and_throw(COURTYARD_SAID[language]["stone"]))
            where = f"{seed} ({language.value})"
            if played.result is None:
                ev.check("the turn is played", False, where)
                continue
            decided = played.decided
            ev.check(
                "the dice go out before any of the telling (A3)",
                decided is not None and not played.told_first,
                where,
            )
            ev.check(
                "the saved scene keeps the lines as the dice showed them (S10)",
                decided is not None and played.scene.details == decided.details,
                where,
            )
            issues = [i.code for i in played.result.issues]
            ev.check(
                "every line is said in time, with its numbers and names (S10)",
                saying.UNSAID not in issues and saying.KEPT not in issues,
                f"{where}: {[(i.code, i.area, i.detail) for i in played.result.issues]}",
            )
            read = played.result.intent.steps
            ev.check(
                "the reading names each step's verb in English, for code to read (B5)",
                bool(read)
                and all(step.verb.casefold().partition(" ")[0] in THROW_VERBS for step in read),
                f"{where}: {[(step.verb, step.text) for step in read]}",
            )
            if ev.live:
                # The script's own steps are in English, so only a model's reading is checked.
                told = [t for step in read for t in (step.text, *(b.text for b in step.beats))]
                ev.check(
                    "and writes each step and its beats in the story's language, as the player "
                    'reads them under "How it played out" (S10)',
                    bool(told) and not any(in_english(text) for text in told),
                    f"{where}: {told}",
                )
            asked = [call for call in played.calls if call.node == Node.WORDING.value]
            ev.check(
                "one call to the cheapest model says them all (B8)",
                len(asked) <= 1,
                f"{where}: {len(asked)} calls",
            )
            thrown = [step for step in played.steps if step.roll and step.roll.throw]
            detail = played.scene.details.steps
            ev.check(
                "a reason leaves its throw to the dice (A3)",
                bool(thrown)
                and all(
                    dice.told(step.roll).casefold() not in shown.reason.casefold()
                    for step, shown in zip(played.steps, detail, strict=True)
                    if step.roll and step.roll.throw
                ),
                where,
                live=False,
            )
            pairs.update(dict.fromkeys(lines_said(played, language)))
        await ev.judge_lines(
            f"the lines in {language.value}",
            Rubric(
                must=(
                    "Every said line is in the language named under LANGUAGE; a name of a "
                    "person, place or technique may stay as it is spelled",
                    "Every said line tells what its English line tells: the same fact, with "
                    "nothing added and nothing left out",
                    "The said lines read as a native speaker would say them at a game table: "
                    "plain and natural, with no phrase that only makes sense in English",
                ),
                must_not=(
                    "A said line changes a number, or writes in words a number its English "
                    "line gives in figures",
                    "A said line is left in English",
                ),
                instructions=LINES_INSTRUCTIONS,
            ),
            list(pairs),
            language=written_in(language),
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
    # The words name the sword the scripted reading strikes with: Lin carries none here, and a
    # sword the player never named would be the reading's own prop, left out (`check._props`).
    ("I strike at the grey mage's face with my sword", "strike", ActionKind.EXCHANGE, 2),
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
        "The story's cover, planned in its second scene, is its poster: drawn from the premise "
        "around the main character, dramatic, and never that scene's moment, with only the "
        "things they have (M1, C10)"
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
        told = prompt.replace(GROUNDED, "").casefold()  # the rule's own examples aside
        ev.check(
            "and nothing of the scene it comes with, whose leap through the pines isn't the "
            "story (M1, Miki 2026-11-07)",
            not any(word in told for word in ("pine", "branch", "leap", "wall")),
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
                        "It sums up the story's premise below, and may show the castle ruins "
                        "across the river from it",
                        "It is not the second scene's moment: Lin is not leaping or climbing "
                        "from branch to branch up the pines",
                        "Lin holds and wears no weapon: no sword, dagger or knife",
                    ),
                    instructions=PICTURE_INSTRUCTIONS,
                ),
                [("the cover", picture)],
                context=(
                    f"The story's premise:\n{LEAP_PREMISE}\n\nThe second scene, which the cover "
                    f"comes with but is not a picture of:\n{played.narration}"
                ),
            )


# --- A grown-up look (S7) ----------------------------------------------------------------------

# Who is drawn, and the age the story gives each (`engine.samples`): a teenager, an old man and a
# young man, in a cultivation sect and in 1970s Naples.
GROWN_UP_PORTRAITS = (("sect", "lin", 16), ("sect", "mage", 60), ("crime", "luca", 24))


@scenario(
    "t18.grown-up-look",
    suite="T18",
    title="A grown-up look",
    requirements=("S7", "M5", "M6", "T18"),
    passes_when=(
        "Every picture looks made for teens and adults, serious and grounded, never a children's "
        "storybook, and each person looks the age the story gives them: Lin 16, the grey mage "
        "sixty, Luca Esposito 24 (S7, Miki 2026-11-08)"
    ),
)
async def grown_up_look(ev: Eval) -> None:
    for seed in ev.seeds(1, live=1):
        stories = {
            "sect": ev.story(worlds.mage_fight(), seed=seed, premise=LEAP_PREMISE),
            "crime": ev.story(worlds.grounded_world(), seed=seed),
        }
        pictures: list[tuple[str, Picture]] = []
        for world, character_id, age in GROWN_UP_PORTRAITS:
            story = stories[world]
            character = story.state.characters[character_id]
            prompt = build_prompt("portrait", portrait_brief(story.state, character_id)).user
            ev.check(
                f"{character.name}'s portrait is told their age, {age}",
                character.age == age and f"Subject: {character.name}, aged {age}" in prompt,
                f"{seed}: {prompt}",
            )
            drawn = await ev.draw_portrait(story, character_id, f"portrait-{character_id}")
            if drawn is not None:
                pictures.append((f"the portrait of {character.name}, aged {age}", drawn))
        cover = await ev.draw_cover(stories["sect"], "cover-lin")
        if isinstance(cover, Picture):
            pictures.append(("the cover of Lin Feng's story, Lin aged 16", cover))
        if pictures:
            await ev.judge_pictures(
                "a grown-up look, with everyone their own age",
                Rubric(
                    must=(
                        "Every picture looks made for teen and adult readers: a serious, grounded "
                        "mood, semi-realistic proportions and detailed rendering, like an anime "
                        "film or graphic novel for grown-ups",
                        "No picture looks like a children's book, a fairy tale, a cartoon or "
                        "chibi art: no oversized eyes or baby faces, no soft toy-like shapes, no "
                        "candy or pastel colours",
                        "Each person looks the age their caption gives: Lin Feng a teenager of "
                        "about 16, neither a child nor a grown man; the grey mage a man of about "
                        "sixty; Luca Esposito a man in his mid twenties",
                    ),
                    instructions=PICTURE_INSTRUCTIONS,
                ),
                pictures,
            )


# --- Feet on the ground (M5) -------------------------------------------------------------------

# Miki, 2026-11-09: a scene picture had the player character standing life-size in mid-air over
# a camp far below, beside a companion who leant over the edge of a wall. The same moment, written
# for the eval, drawn as the endpoint draws it: with both portraits and the place's picture.
ON_THE_WALL = (
    "You and Zhao Kun climb the last broken steps onto the old wall at the top of the ridge. Far "
    "below, among the colossal stone arches, travelling clans have pitched their tents in the "
    "snow, and their bonfires stain the mist orange. Zhao leans over the edge with his hands on "
    "his knees, grinning, while you stand beside him with your arms crossed, watching the camp as "
    "the light fades."
)


@scenario(
    "t18.feet-on-the-ground",
    suite="T18",
    title="Feet on the ground",
    requirements=("M5", "T18"),
    passes_when=(
        "Lin and Zhao both stand on the wall, side by side at a size that fits it, with the camp "
        "small and far below them, and nobody floats in the air; code tells the picture that "
        "everyone stands on something, and to draw the place again around them, never as a "
        "backdrop (M5, Miki 2026-11-09)"
    ),
)
async def feet_on_the_ground(ev: Eval) -> None:
    story = ev.story(worlds.above_the_camp(), under_way=True)
    brief = scene_brief(story.state, ending(ON_THE_WALL))
    names = [f.name for f in brief.figures]
    ev.check(
        "the picture shows Lin and Zhao, the player first",
        [f.id for f in brief.figures] == ["lin", "zhao"],
        f"{names}",
    )
    prompt = build_prompt("scene", brief, references=names, place=True)
    ev.check(
        "it is told everyone stands on something, at the size where they are gives them (M5)",
        GROUNDED in prompt.user,
        prompt.user,
    )
    ev.check(
        "and to draw the place again around them, never as a backdrop (M5)",
        "never in front of a copy of that image used as a backdrop" in prompt.user,
        prompt.user,
    )
    ev.check(
        "the place's picture goes along last, labelled as the place (M5)",
        prompt.labels[-1]
        == "Image 3: the Broken Arches, the place where this happens, to draw again around the "
        "people.",
        f"{prompt.labels}",
    )
    ev.check("and it is lit for dusk (W10)", "Time of day: dusk." in prompt.user, prompt.user)
    note = note_prompt("scene", brief, SceneText(ON_THE_WALL))
    ev.check(
        "the note is asked what each of them stands on (M5)",
        "what they stand, sit or lean on" in note.system
        and "PLACE: the Broken Arches" in note.user,
        note.user,
    )
    place = await ev.draw_place(story, "arches")
    portraits = []
    for character_id in ("lin", "zhao"):
        drawn = await ev.draw_portrait(story, character_id)
        if drawn is not None:
            portraits.append((story.state.characters[character_id].name, drawn))
    pictures: list[tuple[str, Picture]] = []
    for n in range(3):  # the first live run floated someone in one picture of two
        picture = await ev.draw_told(
            story, ON_THE_WALL, name=f"scene-{n + 1}", references=portraits, place=place
        )
        if isinstance(picture, Picture):
            pictures.append((f"picture {n + 1}", picture))
    if pictures:
        await ev.judge_pictures(
            "everyone stands on something",
            Rubric(
                must=(
                    "In every picture, Lin (arms crossed) and Zhao (leaning over the edge) both "
                    "stand on solid footing the picture shows, such as the top of the wall, with "
                    "their feet on it: no one floats or hovers in the air, or stands on nothing "
                    "in front of the camp",
                    "In every picture, the two of them are side by side on the same footing, at "
                    "about the same size, and the camp's tents, fires and people are small and "
                    "clearly far below them",
                    "In every picture, each of them appears once",
                ),
                instructions=PICTURE_INSTRUCTIONS,
            ),
            pictures,
            context=f"The scene, as the player read it:\n{ON_THE_WALL}",
        )
