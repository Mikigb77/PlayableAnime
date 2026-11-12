"""T17's romance evals (W17): a romance is a bond on record that moves in stages, and the other
person has a heart of their own.

Code decides what each move does, from the bond and from how drawn the other is (A2): the checks
here read the record after every turn. Whether the telling follows the record, so that nobody is
told as a couple before the record makes them one, is the judge's in live mode.
"""

from __future__ import annotations

from engine import bonds
from engine.base import DAY, MINUTE
from engine.context import EventFrequency, StorySettings
from engine.contracts import (
    ActionKind,
    AttitudeShift,
    BondChange,
    CharacterChange,
    Intent,
    OutcomeClass,
    RomanceMove,
    SceneEnd,
    StateDelta,
)
from engine.state import BondStage, PowerAxis, StepResult
from engine.visibility import memory_view
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import as_read, facts, plan, step

scenario = REGISTRY.scenario

YOU, MARA = "tomas", worlds.MARA
REST = bonds.REST_S[bonds.pace(MARA)]
# The most one step can move her heart: a stretch of courting, thrown over the top.
MOST = bonds.NOTCH * (bonds.MOST_NOTCHES + 1)
WEEKS = 6  # of courting, at most, before the script gives up on getting somewhere


def to_mara(text: str, move: RomanceMove | None, **kw) -> Intent:
    """A step toward Mara, as the interpret step reads it: who it is with, and which move in a
    romance it is."""
    return plan(
        step(
            text,
            kw.pop("kind", ActionKind.CONVERSATION),
            kw.pop("duration_s", 10 * MINUTE),
            target_ids=[MARA],
            axis=PowerAxis.INFLUENCE,
            romance=move,
            facts=facts(opposition_ids=[MARA], can_respond=True),
            **kw,
        )
    )


ASK = "I ask Mara to be my sweetheart"
WALK = "I walk Mara home along the mill lane and tell her how much I like her company"
COURT = (
    "I spend the next week courting Mara: I walk her home from the mill each evening, bring "
    "her wildflowers and help her father with the wheel"
)
KISS = "I kiss Mara"
MARRY = "I marry Mara today, in front of the whole village"
PROPOSE = "I ask Mara to marry me"


def ask() -> Intent:
    return to_mara("ask Mara to be my sweetheart", RomanceMove.DECLARE, verb="ask")


def walk_home() -> Intent:
    return to_mara(
        "walk Mara home and tell her I like her company",
        RomanceMove.ADVANCE,
        verb="court",
        duration_s=30 * MINUTE,
    )


def court() -> Intent:
    return to_mara(
        "court Mara for a week",
        RomanceMove.ADVANCE,
        verb="court",
        kind=ActionKind.TIME_SKIP,
        duration_s=7 * DAY,
    )


def kiss() -> Intent:
    return to_mara("kiss Mara", RomanceMove.ADVANCE, verb="kiss", duration_s=MINUTE)


def marry() -> Intent:
    return to_mara("marry Mara", RomanceMove.WED, verb="marry", duration_s=3 * 60 * MINUTE)


def propose() -> Intent:
    return to_mara("ask Mara to marry me", RomanceMove.PROPOSE, verb="propose")


def says_yes() -> dict:
    """A scripted scene whose narrator says yes whatever the engine decided, and writes the
    couple and her love into its update: only the engine moves a bond or a heart (W17)."""
    update = StateDelta(
        characters=[
            CharacterChange(id=MARA, attitudes=[AttitudeShift(toward_id=YOU, attraction=60)])
        ],
        bonds=[BondChange(a_id=YOU, b_id=MARA, stage=BondStage.TOGETHER, by_id=YOU)],
        scene_end=SceneEnd(
            ended_on="Mara's hands are in Tomas's.", place_id="farm", present_ids=[YOU, MARA]
        ),
    )
    return {
        "narration": "(scripted) Mara laughs, takes Tomas's hands and says yes.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def heart(story: Story) -> int:
    return story.state.characters[MARA].attitude_toward(YOU).attraction


def stage(story: Story) -> BondStage | None:
    bond = bonds.live(story.state, YOU, MARA)
    return bond.stage if bond is not None else None


def remembered(story: Story) -> BondStage | None:
    """Where Memory says the two stand (C6): what the player reads on Mara's entry."""
    mara = next((p for p in memory_view(story.state).people if p.id == MARA), None)
    return mara.bond if mara is not None else None


def by_her_heart(drawn: int, no: int, sure: int) -> OutcomeClass | None:
    """How an ask is answered, from how drawn she is: None where it is thrown for."""
    if drawn >= sure:
        return OutcomeClass.CERTAIN
    return OutcomeClass.RULED_OUT if drawn < no else None


def answered_as(played: Played, expected: OutcomeClass | None) -> bool:
    """Whether the turn's first step was settled as her heart says: with nothing thrown where
    it is sure either way, and thrown for in between."""
    if not played.completed or not played.steps:
        return False
    done = played.steps[0]
    if expected is None:
        return done.roll is not None
    return done.outcome_class is expected and done.roll is None


async def courted(ev: Eval, story: Story, until: int) -> list[Played]:
    """Weeks of courting, until her heart is at `until` or the script gives up: each week is
    one stretch, which the valley may cut short (E7)."""
    played = []
    for _ in range(WEEKS):
        if heart(story) >= until:
            break
        before, was = heart(story), stage(story)
        week = await story.act(COURT, court())
        played.append(week)
        more = heart(story) - before
        seed = f"{story.seed}: {before} to {heart(story)}, {as_read([week])}"
        done = week.steps[0] if week.completed and week.steps else None
        ran = done.duration_s if done is not None else 0
        ev.check(
            "a stretch of courting moves her heart no further than its days allow",
            0 <= more <= MOST and (more == 0 or ran >= REST or not done.interrupted),
            seed,
        )
        ev.check(
            "courting that came to nothing moves no heart",
            more == 0 or (done is not None and done.result is not StepResult.FAILURE),
            seed,
        )
        ev.check(
            "it is a courtship only once an advance was answered and her heart is far enough",
            stage(story) is not BondStage.COURTING
            or was is BondStage.COURTING
            or (
                heart(story) >= bonds.COURTING_AT
                and done is not None
                and done.result is StepResult.SUCCESS
            ),
            seed,
        )
    return played


@scenario(
    "t17.slow-romance",
    suite="T17",
    title="Slow romance",
    requirements=("W17", "A2", "E7", "F3", "C6", "T17"),
    passes_when=(
        "Asked on the first day, she turns it down with nothing thrown and they are no couple, "
        "whatever the narrator tells. Sweet words twice in one day move her heart once. Weeks "
        "of courting move it as far as their days allow, and a week something cuts short keeps "
        "the days it ran. Asked again, she answers by her heart: yes with nothing thrown once "
        "she is in love. A kiss with a partner needs no throw, a wedding takes two who are "
        "promised, and the bond comes to married one stage at a time, over weeks of the "
        "story. Memory shows the two as the record holds them at each point"
    ),
)
async def slow_romance(ev: Eval) -> None:
    calm = StorySettings(event_frequency=EventFrequency.CALM)
    for seed in ev.seeds(12, live=1):
        story = ev.story(worlds.millers_daughter(), seed=seed, settings=calm, under_way=True)
        began_s = story.state.world_s

        # Day one: asked before anything was won.
        first = await story.act(ASK, ask(), narration=None if ev.live else says_yes())
        ev.check(
            "asked before anything was won, she turns it down with nothing thrown",
            answered_as(first, OutcomeClass.RULED_OUT),
            f"{seed}: {as_read([first])}",
        )
        ev.check(
            "an ask her heart isn't in makes no couple, whatever the telling says",
            stage(story) in (None, BondStage.INTEREST) and not bonds.partners(story.state, YOU),
            f"{seed}: {stage(story)}",
        )
        ev.check(
            "nothing the narrator says moves her heart",
            heart(story) == 0,
            f"{seed}: {heart(story)}",
            live=False,
        )
        ev.check(
            "Memory tells the romance as the record holds it",
            remembered(story) is stage(story),
            f"{seed}: after the first ask, {remembered(story)} for {stage(story)}",
        )
        await ev.judge(
            "an ask before anything was won",
            Rubric(
                must=(
                    "Mara turns Tomas down or puts him off, kindly or not: she does not agree "
                    "to be his sweetheart",
                ),
                must_not=(
                    "Mara agrees to be with Tomas, kisses him, or is told as his sweetheart",
                    "The narrator lectures the player or refuses to play the scene",
                ),
            ),
            [first],
        )

        if not ev.live:
            # Sweet words twice in one evening: her heart moves once and then rests.
            walked = await story.act(WALK, walk_home())
            once = heart(story)
            again = await story.act(WALK, walk_home())
            ev.check(
                "sweet words twice in one day move her heart once",
                heart(story) == once or once == 0,
                f"{seed}: {once} then {heart(story)}, {as_read([walked, again])}",
            )

        # Weeks of courting, until she is in love.
        weeks = await courted(ev, story, bonds.DECLARE_SURE)
        cut = [w for w in weeks if w.completed and w.steps and w.steps[0].interrupted]
        ev.metric("weeks_cut_short", len(cut))
        if heart(story) < bonds.DECLARE_SURE:
            # The dice never came good in the weeks the script gives it: the ask is still
            # answered by her heart, and nothing more can be played of this story.
            late = await story.act(ASK, ask())
            expected = by_her_heart(heart(story), bonds.DECLARE_NO, bonds.DECLARE_SURE)
            ev.check(
                "an ask is answered by her heart",
                answered_as(late, expected),
                f"{seed}: at {heart(story)}, {as_read([late])}",
            )
            continue

        # She is in love: asked, the answer is yes with nothing thrown.
        yes = await story.act(ASK, ask())
        ev.check(
            "an ask is answered by her heart",
            answered_as(yes, OutcomeClass.CERTAIN),
            f"{seed}: at {heart(story)}, {as_read([yes])}",
        )
        ev.check("a yes makes them a couple", stage(story) is BondStage.TOGETHER, seed)
        ev.check(
            "Memory tells the romance as the record holds it",
            remembered(story) is stage(story),
            f"{seed}: after the yes, {remembered(story)} for {stage(story)}",
        )
        kissed = await story.act(KISS, kiss())
        ev.check(
            "a kiss with a partner needs no throw",
            answered_as(kissed, OutcomeClass.CERTAIN),
            f"{seed}: {as_read([kissed])}",
        )
        await ev.judge(
            "a yes and a kiss",
            Rubric(
                must=(
                    "Mara says yes, in her own way, and from here the two are told as a couple",
                    "The kiss is welcome and returned",
                ),
                must_not=(
                    "Mara refuses, hesitates as if nothing had been won, or has to be persuaded",
                    "The scene goes beyond a kiss",
                ),
            ),
            [yes, kissed],
        )

        # A wedding takes two who are promised.
        hasty = await story.act(MARRY, marry())
        ev.check(
            "a wedding takes two who are promised",
            answered_as(hasty, OutcomeClass.RULED_OUT) and stage(story) is BondStage.TOGETHER,
            f"{seed}: {stage(story)}, {as_read([hasty])}",
        )
        await courted(ev, story, bonds.PROPOSE_SURE)
        asked = await story.act(PROPOSE, propose())
        expected = by_her_heart(heart(story), bonds.PROPOSE_NO, bonds.PROPOSE_SURE)
        ev.check(
            "a promise is answered by her heart",
            answered_as(asked, expected),
            f"{seed}: at {heart(story)}, {as_read([asked])}",
        )
        if stage(story) is not BondStage.PROMISED:
            continue
        wed = await story.act(MARRY, marry())
        ev.check(
            "two who are promised are wed with nothing thrown",
            answered_as(wed, OutcomeClass.CERTAIN) and stage(story) is BondStage.MARRIED,
            f"{seed}: {stage(story)}, {as_read([wed])}",
        )

        bond = bonds.live(story.state, YOU, MARA)
        came = [s.stage for s in bond.steps] if bond is not None else []
        ev.check(
            "the bond came to married one stage at a time",
            bool(came)
            and came[0] is BondStage.INTEREST
            and came[-1] is BondStage.MARRIED
            and all(b in bonds.FORWARD[a] for a, b in zip(came, came[1:], strict=False)),
            f"{seed}: {[s.value for s in came]}",
        )
        ev.check(
            "Memory tells the romance as the record holds it",
            remembered(story) is BondStage.MARRIED,
            f"{seed}: after the wedding, {remembered(story)}",
        )
        days = (story.state.world_s - began_s) / DAY
        ev.check(
            "the romance was won over weeks of the story",
            days >= 7,
            f"{seed}: {days:.1f} days",
        )
        await ev.judge(
            "the telling follows the record",
            Rubric(
                must=(
                    "In every scene, how warm Mara is toward Tomas fits what OUTCOME says of "
                    "her heart and of where the two stand",
                    "When Tomas wants to marry her the same day, no wedding takes place",
                    "The wedding is told once the two are promised, and not before",
                ),
                must_not=(
                    "Mara is told as his partner, his betrothed or his wife before OUTCOME "
                    "says the two are",
                ),
            ),
            story.turns,
        )
