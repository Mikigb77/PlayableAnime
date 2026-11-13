"""T17's romance evals (W17): a romance is a bond on record that moves in stages, and the other
person has a heart of their own.

Code decides what each move does, from the bond and from how drawn the other is (A2): the checks
here read the record after every turn. Whether the telling follows the record, so that nobody is
told as a couple before the record makes them one, is the judge's in live mode.
"""

from __future__ import annotations

from collections import Counter

from engine import bonds
from engine.base import DAY, HOUR, MINUTE
from engine.context import EventFrequency, Rating, StorySettings
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
from engine.state import (
    BondEnd,
    BondStage,
    Deed,
    EventStatus,
    PendingEvent,
    Place,
    PowerAxis,
    StepResult,
    WorldState,
)
from engine.visibility import memory_view
from engine.world import Kind, returns
from engine.world.answers import Answer
from engine.world.geography import together
from engine.world.norms import is_crime
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import as_left, as_read, facts, full_day, plan, step
from graph.llm import Node

scenario = REGISTRY.scenario

YOU, MARA, ILSE, JORN, BRAM = "tomas", worlds.MARA, "ilse", worlds.JORN, "bram"
REST = bonds.REST_S[bonds.pace(MARA)]
# The most one step can move her heart: a stretch of courting, thrown over the top.
MOST = bonds.NOTCH * (bonds.MOST_NOTCHES + 1)
WEEKS = 6  # of courting, at most, before the script gives up on getting somewhere


def to_mara(text: str, move: RomanceMove | None, *, who: str = MARA, **kw) -> Intent:
    """A step toward Mara (or `who`), as the interpret step reads it: who it is with, and
    which move in a romance it is."""
    return plan(
        step(
            text,
            kw.pop("kind", ActionKind.CONVERSATION),
            kw.pop("duration_s", 10 * MINUTE),
            target_ids=[who],
            axis=PowerAxis.INFLUENCE,
            romance=move,
            facts=facts(opposition_ids=[who], can_respond=True),
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


def walk_to_the_farm() -> Intent:
    """The walk as the real model read it once (2026-11-13): one step that goes somewhere, to
    Tomas's own farm, and is a move toward Mara on the way. What a step does as the going
    itself is done as they set out, before the scene's people (W2)."""
    return plan(
        step(
            "walk Mara home along the mill lane and tell her I like her company",
            ActionKind.TRAVEL,
            40 * MINUTE,
            verb="walk",
            target_ids=[MARA],
            romance=RomanceMove.ADVANCE,
            destination="farm",
        )
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


def bare_kiss() -> Intent:
    """The kiss as the real model read it once (2026-11-13): aimed at Mara, with nothing it
    is measured on and nobody named as standing in its way. Code says whom a move in a
    romance is made to, so her heart answers it all the same (A2)."""
    return plan(
        step(
            "kiss Mara",
            ActionKind.EXCHANGE,
            MINUTE,
            verb="kiss",
            target_ids=[MARA],
            romance=RomanceMove.ADVANCE,
        )
    )


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


def remembered(story: Story, who: str = MARA) -> BondStage | None:
    """Where Memory says the two stand (C6): what the player reads on their entry."""
    person = next((p for p in memory_view(story.state).people if p.id == who), None)
    return person.bond if person is not None else None


def home_at_the_mill(state: WorldState) -> None:
    """Mara has gone home to the mill in Millbrook, forty minutes off, and Tomas is alone at
    his own gate."""
    state.characters[MARA].location_id = "village"
    state.characters[YOU].location_id = "farm"
    state.scene = state.scene.model_copy(
        update={
            "place_id": "farm",
            "present_ids": [YOU],
            "positions": ["Tomas at his own gate"],
            "props": [],
            "ended_on": "Tomas is at his own gate. Mara went home to the mill an hour ago.",
        }
    )


def gone_to_harrow(state: WorldState) -> None:
    """Mara has gone to her aunt's in Harrow, a town beyond the hills that no road on the map
    reaches, and Tomas is alone on the mill lane."""
    state.places["harrow"] = Place(id="harrow", name="Harrow", kind="town", known_by=[YOU])
    state.characters[MARA].location_id = "harrow"
    where = state.characters[YOU].location_id
    state.scene = state.scene.model_copy(
        update={
            "place_id": where,
            "present_ids": [YOU],
            "positions": ["Tomas on the mill lane"],
            "props": [],
            "ended_on": "Tomas is on the mill lane. Mara left for her aunt's in Harrow at dawn.",
        }
    )


def back_from_harrow(state: WorldState) -> None:
    """Mara is back, and the two are on the mill lane."""
    where = state.characters[YOU].location_id
    state.characters[MARA].location_id = where
    state.scene = state.scene.model_copy(
        update={
            "place_id": where,
            "present_ids": [YOU, MARA],
            "positions": ["Tomas and Mara on the mill lane"],
            "props": [],
            "ended_on": "Mara is back from Harrow, and the two are on the mill lane.",
        }
    )


def with_her(story: Story) -> bool:
    """Whether the record has Tomas where Mara is (W10)."""
    state = story.state
    spot, hers = state.characters[YOU].location_id, state.characters[MARA].location_id
    return spot in state.places and hers in state.places and together(state, spot, hers)


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
    requirements=("W17", "A2", "E7", "W10", "F3", "C6", "T17"),
    passes_when=(
        "Asked on the first day, she turns it down with nothing thrown and they are no couple, "
        "whatever the narrator tells. Sweet words twice in one day move her heart once. Weeks "
        "of courting move it as far as their days allow, and a week something cuts short keeps "
        "the days it ran. Asked again, she answers by her heart: yes with nothing thrown once "
        "she is in love, and when she has gone home the ask starts with going to her. A kiss "
        "with a partner needs no throw, and one for a partner who is far away reaches nobody. "
        "A wedding takes two who are promised, and the bond comes to married one stage at a "
        "time, over weeks of the story. Memory shows the two as the record holds them at each "
        "point"
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

        # She is in love, and she has gone home: asking her starts with going to her (W10),
        # and the answer is yes with nothing thrown.
        story.change(home_at_the_mill)
        yes = await story.act(ASK, ask())
        ev.check(
            "an ask is answered by her heart",
            answered_as(yes, OutcomeClass.CERTAIN),
            f"{seed}: at {heart(story)}, {as_read([yes])}",
        )
        trip = yes.steps[0].trip if yes.completed and yes.steps else None
        ev.check(
            "an ask to someone a short walk away goes to her",
            with_her(story),
            f"{seed}: Tomas in {story.state.characters[YOU].location_id}, "
            f"Mara in {story.state.characters[MARA].location_id}",
        )
        ev.check(
            "the step that went to her is the trip there, and takes the walk at the least",
            trip is not None
            and (trip.to_id, trip.arrived) == ("village", True)
            and yes.steps[0].duration_s >= 40 * MINUTE,
            f"{seed}: {trip}",
            live=False,
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
                    "Tomas goes to where Mara is before he asks, and she answers him there",
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

        # She has gone to her aunt's, beyond the hills: a kiss for someone who isn't here.
        story.change(gone_to_harrow)
        was = (heart(story), stage(story))
        missed = await story.act(KISS, kiss())
        done = missed.steps[0] if missed.completed and missed.steps else None
        ev.check(
            "a move toward someone far off reaches nobody",
            done is not None
            and done.outcome_class is OutcomeClass.RULED_OUT
            and done.trip is None
            and (heart(story), stage(story)) == was,
            f"{seed}: {as_read([missed])}, {was} to {(heart(story), stage(story))}",
        )
        await ev.judge(
            "a kiss for someone who isn't here",
            Rubric(
                must=("Tomas finds that Mara isn't around, and no kiss takes place",),
                must_not=(
                    "Mara appears, answers, kisses him or sends word in this scene",
                    "The narrator lectures the player or refuses to play the scene",
                ),
            ),
            [missed],
        )
        story.change(back_from_harrow)

        # A wedding takes two who are promised.
        hasty = await story.act(MARRY, marry())
        ev.check(
            "a wedding takes two who are promised",
            answered_as(hasty, OutcomeClass.RULED_OUT) and stage(story) is BondStage.TOGETHER,
            f"{seed}: {stage(story)}, {as_read([hasty])}",
        )
        promised = stage(story) is BondStage.PROMISED  # a live reading may have made it an ask
        await courted(ev, story, bonds.PROPOSE_SURE)
        asked = await story.act(PROPOSE, propose())
        expected = by_her_heart(heart(story), bonds.PROPOSE_NO, bonds.PROPOSE_SURE)
        ev.check(
            "a promise is answered by her heart",
            answered_as(asked, OutcomeClass.CERTAIN if promised else expected),
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
                    "In a scene whose OUTCOME says the two aren't promised yet, no wedding "
                    "takes place, whatever Tomas asks for",
                    "The wedding is told once the two are promised, and not before",
                ),
                must_not=(
                    "Mara is told as his partner, his betrothed or his wife before OUTCOME "
                    "says the two are",
                ),
            ),
            story.turns,
        )


# --- the world reacting: an affair, a rival and a breakup (W17) --------------------------------

NIGHT = "I spend the night with Mara, and we sleep together"
HOME = "I work my fields all day and sleep in my own bed"
IN_MILLBROOK = "I help at the mill all day and sleep in my bed at the alehouse"
TAKE_ME_BACK = "I take Ilse's hands and ask her to stay my wife"
END = "I tell Mara it is over between us, and that I won't change my mind"
ASK_AGAIN = "I ask Mara to be my sweetheart again"
CALM = StorySettings(event_frequency=EventFrequency.CALM)
DAYS_AT_HOME = 6  # at most, for word to get round and for whoever it wronged to come


def night() -> Intent:
    return to_mara(
        "spend the night with Mara", RomanceMove.ADVANCE, verb="sleep with", duration_s=8 * HOUR
    )


def part() -> Intent:
    return to_mara("tell Mara it is over between us", RomanceMove.PART, verb="end")


def take_me_back() -> Intent:
    return to_mara("ask Ilse to stay my wife", RomanceMove.DECLARE, who=ILSE, verb="ask")


def mends_it(who: str, stage: BondStage) -> dict:
    """A scripted scene whose narrator mends everything, and writes it into its update."""
    update = StateDelta(
        characters=[
            CharacterChange(id=who, attitudes=[AttitudeShift(toward_id=YOU, attraction=60)])
        ],
        bonds=[BondChange(a_id=YOU, b_id=who, stage=stage, by_id=who)],
    )
    return {
        "narration": "(scripted) All is forgiven, and the two are as they were.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def walks_in(who: str, at: str = "village") -> dict:
    """A scripted scene whose narrator has `who` walk in on it, whatever the engine decided,
    as the real model did in the first stories about an affair (2026-11-13): its update puts
    them where the scene ends (`at`: Millbrook, or the farm a walk went to), among those
    present, having met Tomas there and taken it badly. Only the world brings someone into a
    scene (W10), and what a move is to someone who didn't see it is the engine's, once word
    reaches them (W17, W2)."""
    seen = AttitudeShift(toward_id=YOU, affinity=-10, trust=-10)
    there = [YOU, MARA, BRAM, who] if at == "village" else [YOU, MARA, who]
    update = StateDelta(
        characters=[CharacterChange(id=who, location_id=at, meets_player=True, attitudes=[seen])],
        scene_end=SceneEnd(
            ended_on="Someone stands at the end of the lane, and has seen it all.",
            place_id=at,
            present_ids=there,
        ),
    )
    return {
        "narration": "(scripted) At the end of the lane someone has stopped, and stares.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def who_else(story: Story) -> str:
    """WHO ELSE of the last brief the narrator was sent, or nothing when it had none."""
    _, found, rest = story.prompt(Node.NARRATOR).partition("\n## WHO ELSE\n")
    return rest.partition("\n## ")[0] if found else ""


def goes_home(state: WorldState) -> None:
    """Tomas is back on his farm and alone at his gate: whoever saw what he did is free to
    talk of it (W2)."""
    state.characters[YOU].location_id = "farm"
    state.scene = state.scene.model_copy(
        update={
            "place_id": "farm",
            "present_ids": [YOU],
            "positions": ["Tomas at his own gate"],
            "props": [],
            "ended_on": "Tomas is back at his own gate, with the day's work waiting.",
        }
    )


def stays_in_millbrook(state: WorldState) -> None:
    """Tomas has taken a bed over the Millbrook alehouse and is alone in its yard: he is where
    he was last seen, and whoever saw what he did is free to talk of it (W2)."""
    state.scene = state.scene.model_copy(
        update={
            "place_id": "village",
            "present_ids": [YOU],
            "positions": ["Tomas in the alehouse yard"],
            "props": [],
            "ended_on": "Tomas is alone in the alehouse yard, with the morning still cold.",
        }
    )


def day_in_millbrook() -> Intent:
    return plan(
        step("Help at the mill all day", ActionKind.WORK, 12 * HOUR, verb="work"),
        step("Sleep at the alehouse", ActionKind.REST, 12 * HOUR, verb="sleep"),
    )


def feels(story: Story, who: str, toward: str = YOU) -> tuple[int, int, int]:
    felt = story.state.characters[who].attitude_toward(toward)
    return felt.affinity, felt.trust, felt.attraction


def wrongs(story: Story, who: str) -> list[Deed]:
    """The deeds on record that wronged `who`, in the order they were done."""
    return [d for d in story.state.deeds.values() if who in d.wronged_ids]


def knows(story: Story, who: str) -> list[Deed]:
    return [d for d in wrongs(story, who) if who in d.known_by]


def looked_for(story: Story, who: str, answer: Answer = Answer.CONFRONT) -> list[PendingEvent]:
    """The times `who` came for the player character, whether or not they found them."""
    return story.fired(Kind.ANSWER, avenger_id=who, answer=answer.value)


def came(story: Story, who: str, answer: Answer = Answer.CONFRONT) -> list[PendingEvent]:
    """The times `who` came to the player character and found them."""
    return [e for e in looked_for(story, who, answer) if e.needs_player]


def coming(story: Story, who: str, answer: Answer) -> list[PendingEvent]:
    """`who` on their way, or already come, with `answer`."""
    return [
        e
        for e in story.state.pending_events.values()
        if e.kind == Kind.ANSWER
        and e.status in (EventStatus.PENDING, EventStatus.APPLIED)
        and e.payload.get("avenger_id") == who
        and e.payload.get("answer") == answer.value
    ]


async def days_at_home(story: Story, who: str, *, away: bool = False) -> list[Played]:
    """Days on the farm (or, `away`, in Millbrook) until `who` has come, or the script gives
    up on it."""
    played = []
    for _ in range(DAYS_AT_HOME):
        if came(story, who):
            break
        if away:
            played.append(await story.act(IN_MILLBROOK, day_in_millbrook()))
        else:
            played.append(await story.act(HOME, full_day()))
    return played


def gravity_as_played(played: Played, was: BondStage | None, now: BondStage | None) -> int:
    """How grave the record should hold a turn's one move to be (`engine.bonds.gravity`), from
    how it was settled and where the two stood before and after."""
    done = played.steps[0]
    answered = (
        done.outcome_class is not OutcomeClass.RULED_OUT and done.result is not StepResult.FAILURE
    )
    intimate = "night" in done.text
    return bonds.gravity(asked=False, intimate=intimate, answered=answered, before=was, after=now)


def trail(story: Story) -> list[str]:
    """What Memory's deeds say came of them (C6)."""
    return [entry.text for deed in memory_view(story.state).deeds for entry in deed.trail]


@scenario(
    "t17.an-affair",
    suite="T17",
    title="An affair comes home",
    requirements=("W17", "W1", "W2", "W4", "W10", "C6", "T17"),
    passes_when=(
        "A married man walks someone home and spends the night with them, with a neighbour "
        "looking on. Each move is a deed on record that wrongs his wife, graver the further it "
        "went, and no crime: nobody reports it and the neighbour thinks no less of him. At "
        "home she knows nothing and feels as before, until word reaches her from someone who "
        "saw it, and no scene brings her into it from the farm, whatever its narrator tells. "
        "Then she loses liking, trust and heart by how far it went, and comes to have it out, "
        "never for revenge. A wife whose heart is gone ends the marriage when she finds him, "
        "and nothing the scene tells or he asks mends it or moves her so soon; one whose heart "
        "holds stays married. Memory tells the marriage as the record holds it"
    ),
)
async def an_affair(ev: Eval) -> None:
    ends: Counter[str] = Counter()
    for index, seed in enumerate(ev.seeds(12, live=1)):
        devoted = index % 3 == 2  # a wife whose heart holds through it
        world = worlds.wife_at_home(heart=80 if devoted else 60)
        story = ev.story(world, seed=seed, settings=CALM, under_way=True, rating=Rating.MATURE)
        at_first, bram_at_first = feels(story, ILSE), feels(story, BRAM)

        # Offline, the narrator walks his wife in on both scenes, and the record keeps her out.
        barges = None if ev.live else walks_in(ILSE)
        walked = await story.act(WALK, walk_home(), narration=barges)
        courting = stage(story)
        slept = await story.act(NIGHT, night(), narration=barges)
        deeds = wrongs(story, ILSE)
        ev.check(
            "a move in a romance with someone else is a deed that wrongs the partner on record",
            bool(deeds) and all(d.wronged_ids == [ILSE] and d.target_ids == [MARA] for d in deeds),
            f"{seed}: {[(d.kind, d.wronged_ids) for d in story.state.deeds.values()]}, "
            f"{as_read([walked, slept])}",
        )
        if len(deeds) == 2 and walked.steps and slept.steps:
            expected = [
                gravity_as_played(walked, None, courting),
                gravity_as_played(slept, courting, stage(story)),
            ]
            ev.check(
                "how grave it is follows how far it went",
                [d.severity for d in deeds] == expected,
                f"{seed}: {[(d.kind, d.severity) for d in deeds]} for {expected}",
                live=False,  # it reads the scripted steps' own words
            )
        ev.check(
            "it is no crime, and nobody reports it",
            not any(is_crime(story.state, d) for d in deeds) and not story.fired(Kind.REPORT),
            f"{seed}: {[e.title for e in story.fired(Kind.REPORT)]}",
        )
        ev.check(
            "someone it is nothing to thinks no less of him for it",
            feels(story, BRAM) == bram_at_first,
            f"{seed}: {bram_at_first} to {feels(story, BRAM)}",
            live=False,
        )
        # A live telling may take the evening somewhere the script doesn't: then whoever saw
        # it may have told her already, and she may have set out (W2, W10). That is the
        # world's doing, and no flaw of the scene's.
        told_her = any(
            e.kind == Kind.TIDINGS and ILSE in e.subject_ids
            for turn in (walked, slept)
            for e in turn.fired
        )
        ev.check(
            "a partner who is elsewhere knows nothing and feels as before",
            told_her
            or (
                feels(story, ILSE) == at_first
                and not any(ILSE in d.known_by or ILSE in d.heard_by for d in deeds)
            ),
            f"{seed}: {at_first} to {feels(story, ILSE)}, "
            f"{as_left(walked, ILSE)}, {as_left(slept, ILSE)}, {as_read([walked, slept])}",
        )
        ev.check(
            "nothing a scene tells brings her into it from the farm",
            bool(looked_for(story, ILSE))
            or (
                ILSE not in walked.state.scene.present_ids
                and ILSE not in slept.state.scene.present_ids
                and story.state.characters[ILSE].location_id == "farm"
            ),
            f"{seed}: {as_left(walked, ILSE)}, {as_left(slept, ILSE)}, {as_read([walked, slept])}",
        )
        await ev.judge(
            "an evening with someone else",
            Rubric(
                must=("Mara is as warm to Tomas as OUTCOME says of her heart and of each step",),
                must_not=(
                    "Ilse is in these scenes, or anyone says she already knows",
                    "The night is told in explicit sexual detail",
                ),
            ),
            [walked, slept],
        )

        story.change(goes_home)
        days = await days_at_home(story, ILSE)
        known = knows(story, ILSE)
        gravest = max((d.severity for d in known), default=0)
        faced = came(story, ILSE)
        ev.check(
            "word of an affair reaches her from someone who saw it, and she comes to have it out",
            bool(faced) == (gravest >= bonds.FACED_FROM) and bool(known) == bool(deeds),
            f"{seed}: knows {[(d.kind, d.severity) for d in known]}, came {len(faced)} times, "
            f"{as_read(days[-2:])}",
        )
        if not known:
            ends["she never heard"] += 1
            continue
        lost = at_first[2] - feels(story, ILSE)[2]
        least = bonds.WRONGED_HEART * gravest
        most = least + bonds.WRONGED_HEART * bonds.AGAIN * (len(known) - 1)
        ev.check(
            "her heart falls by how far it went, and more of the same adds little",
            least <= lost <= most and feels(story, ILSE)[0] < at_first[0],
            f"{seed}: lost {lost}, between {least} and {most}; {at_first} to {feels(story, ILSE)}",
        )
        ev.check(
            "nobody comes for revenge on their own partner",
            not coming(story, ILSE, Answer.REVENGE),
            seed,
        )
        if not faced:
            ends["she never came"] += 1
            continue
        marriage = story.state.bonds["bond-1"]
        over = marriage.stage is BondStage.OVER
        ends["she ended it" if over else "she stayed"] += 1
        heart_gone = feels(story, ILSE)[2] < bonds.LEAVES_UNDER
        ev.check(
            "a partner whose heart is gone ends it when they find them, and one whose heart "
            "holds stays",
            over == heart_gone
            and (not over or (marriage.end is BondEnd.PARTED and marriage.steps[-1].by_id == ILSE)),
            f"{seed}: {marriage.stage.value} with her heart at {feels(story, ILSE)[2]}",
        )
        told = "it is over between them" if over else "to hear it answered and not to attack"
        ev.check(
            "the scene is told what she came to do",
            told in story.prompt(Node.NARRATOR),
            f"{seed}: {faced[-1].title}",
            live=False,
        )
        person = next(p for p in memory_view(story.state).people if p.id == ILSE)
        line = person.bond_line or ""
        ev.check(
            "Memory tells the marriage as the record holds it",
            person.bond is marriage.stage
            and (not over or line.startswith("You were married until they ended it"))
            and any(
                text.startswith("Ilse Weller came to face you over it") for text in trail(story)
            ),
            f"{seed}: {person.bond} {line!r}, {trail(story)}",
        )
        if not over:
            await ev.judge(
                "she has it out with him",
                Rubric(
                    must=(
                        "Ilse puts what Tomas did with Mara to him, as someone who knows of it",
                        "Ilse is hurt, angry or cold, and the two are still married as the "
                        "scene ends",
                    ),
                    must_not=(
                        "Ilse attacks Tomas",
                        "Ilse ends the marriage or leaves him for good",
                        "Ilse behaves as if nothing had happened",
                    ),
                ),
                days[-1:],
            )
            continue

        mended = None if ev.live else mends_it(ILSE, BondStage.MARRIED)
        hers = feels(story, ILSE)
        asked = await story.act(TAKE_ME_BACK, take_me_back(), narration=mended)
        ev.check(
            "she ended it, so nothing he asks or does moves her so soon",
            answered_as(asked, OutcomeClass.RULED_OUT) and feels(story, ILSE) == hers,
            f"{seed}: {hers} to {feels(story, ILSE)}, {as_read([asked])}",
        )
        ev.check(
            "what she ended stays ended, whatever the scene tells",
            story.state.bonds["bond-1"].stage is BondStage.OVER
            and ILSE not in bonds.partners(story.state, YOU)
            and remembered(story, ILSE) is BondStage.OVER,
            f"{seed}: {[(b.id, b.stage.value) for b in story.state.bonds.values()]}",
        )
        await ev.judge(
            "she comes to end it",
            Rubric(
                must=(
                    "Ilse comes to Tomas knowing what he did with Mara, and says so",
                    "Ilse tells Tomas it is over between them, and it is still over when the "
                    "scene ends",
                    "Asked to stay his wife, Ilse does not take him back",
                ),
                must_not=(
                    "Ilse forgives Tomas, or the two make up",
                    "Ilse attacks Tomas",
                    "The narrator lectures the player or refuses to play a scene",
                ),
            ),
            [*days[-1:], asked],
        )
    ev.metric("ends", dict(ends))
    ev.check(
        "some wives end it and some stay, by their hearts",
        ends["she ended it"] > 0 and ends["she stayed"] > 0,
        str(dict(ends)),
        live=False,
    )


RIVALS = ("told of it all", "saw it", "told of the walk", "walked her to his farm")


@scenario(
    "t17.a-rival",
    suite="T17",
    title="A rival",
    requirements=("W17", "W1", "W2", "W4", "W6", "W10", "C6", "T17"),
    passes_when=(
        "A man courts the smith's wife. The move wrongs her husband on record, and the scene "
        "is told whether he saw it. A husband who saw it holds it against the man at once, by "
        "how far it went, and one who was out of sight feels as before until someone who saw "
        "it tells him, also when the walk is one step that takes the two of them to the "
        "man's farm: the scene isn't offered him, and he isn't in it whatever its narrator "
        "tells. Knowing of an affair, he comes to have it out, and the scene is told he "
        "came to hear it answered and not to attack. He comes for revenge afterwards only "
        "when what he knows of went as far as a night together. It is no crime, and Memory "
        "says who came over it. Wherever he has gone, to the farm to have it out or on an "
        "outing of his own, he is due back in Millbrook"
    ),
)
async def a_rival(ev: Eval) -> None:
    ends: Counter[str] = Counter()
    away = 0
    for index, seed in enumerate(ev.seeds(16, live=1)):
        how = RIVALS[index % len(RIVALS)]
        saw, to_farm = how == "saw it", how == "walked her to his farm"
        world = worlds.husband_in_millbrook(there=saw)
        story = ev.story(world, seed=seed, settings=CALM, under_way=True, rating=Rating.MATURE)
        at_first, his_wife = feels(story, JORN), feels(story, JORN, MARA)

        # Offline, a husband who is out of sight is walked in on it by the narrator, where its
        # scene ends, and the record keeps him out.
        barges = None if ev.live or saw else walks_in(JORN, "farm" if to_farm else "village")
        if saw:
            first = await story.act(KISS, kiss())
        elif to_farm:
            first = await story.act(WALK, walk_to_the_farm(), narration=barges)
        else:
            first = await story.act(WALK, walk_home(), narration=barges)
        deeds = wrongs(story, JORN)
        ev.check(
            "courting someone's partner is a deed that wrongs them on record",
            len(deeds) >= 1 and all(d.wronged_ids == [JORN] for d in deeds),
            f"{seed}, he {how}: {[(d.kind, d.wronged_ids) for d in story.state.deeds.values()]}, "
            f"{as_read([first])}",
        )
        if not deeds:
            continue
        told = f'"wrongs":[{{"id":"jorn-hale","who":"Jorn Hale","saw_it":{str(saw).lower()}}}]'
        ev.check(
            "the scene is told whose partner it was, and whether they saw it",
            told in story.prompt(Node.NARRATOR),
            f"{seed}, he {how}",
            live=False,
        )
        if not saw:
            ev.check(
                "a husband who didn't see it is not among those the scene may bring in",
                JORN not in who_else(story),
                f"{seed}, he {how}: {who_else(story)[:300]}",
                live=False,
            )
        severity = deeds[0].severity
        if saw:
            ev.check(
                "a husband who saw it holds it against him by how far it went",
                feels(story, JORN)
                == (
                    at_first[0] - bonds.RIVAL_LIKING * severity,
                    at_first[1] - bonds.RIVAL_TRUST * severity,
                    at_first[2],
                ),
                f"{seed}: {at_first} to {feels(story, JORN)} for severity {severity}",
                live=False,
            )
        elif ev.live and any(JORN in d.witness_ids for d in deeds):
            # A live reading may put the walk before a crowd, and then he is one of the crowd
            # (W2): the record says he saw it, so he knows and thinks the worse of the man,
            # and no scene has him anywhere but where the record does.
            now, jorn = feels(story, JORN), first.state.characters[JORN]
            ev.check(
                "a husband the record says saw it knows of it and thinks the worse of him",
                bool(knows(story, JORN)) and now[0] < at_first[0] and now[1] < at_first[1],
                f"{seed}: {at_first} to {now}, {as_left(first, JORN)}, {as_read([first])}",
            )
            ev.check(
                "a husband who saw it from the crowd is in no scene away from where he is",
                JORN not in first.state.scene.present_ids
                or together(first.state, jorn.location_id, first.state.scene.place_id),
                f"{seed}: {as_left(first, JORN)}, {as_read([first])}",
            )
        else:
            # A live telling may take the two out of the village, and then whoever saw them
            # may have told him before the turn is over (W2): that is the world's doing.
            told_him = any(e.kind == Kind.TIDINGS and JORN in e.subject_ids for e in first.fired)
            ev.check(
                "a husband who is elsewhere knows nothing and feels as before",
                told_him or (feels(story, JORN) == at_first and not knows(story, JORN)),
                f"{seed}: {at_first} to {feels(story, JORN)}, {as_left(first, JORN)}, "
                f"{as_read([first])}",
            )
            ev.check(
                "nothing a scene tells brings him into it",
                JORN not in first.state.scene.present_ids or bool(came(story, JORN)),
                f"{seed}: {as_left(first, JORN)}, {as_read([first])}",
            )
        ev.check(
            "what he feels for his own wife is his, and nothing the move touches",
            feels(story, JORN, MARA) == his_wife,
            f"{seed}: {his_wife} to {feels(story, JORN, MARA)}",
            live=False,
        )
        played = [first]
        if how == "told of it all":
            played.append(await story.act(NIGHT, night(), narration=barges))
            ev.check(
                "nothing a scene tells brings him into it",
                JORN not in played[-1].state.scene.present_ids or bool(came(story, JORN)),
                f"{seed}: {as_left(played[-1], JORN)}, {as_read(played[-1:])}",
            )
        await ev.judge(
            "courting the smith's wife",
            Rubric(
                must=(
                    "Mara is as warm to Tomas as OUTCOME says of her heart and of each step",
                    "When wrongs under a step says Jorn saw it (saw_it true), the scene shows "
                    "what it is to him, and with stayed_in it leaves him in that place; when it "
                    "says he didn't, Jorn is not in the scene and nobody says he knows",
                ),
                must_not=("The night, if there is one, is told in explicit sexual detail",),
            ),
            played,
        )

        # Seen by her husband, he stays where he was seen. Seen by a neighbour, he goes home.
        story.change(stays_in_millbrook if saw else goes_home)
        days = await days_at_home(story, JORN, away=saw)
        known = knows(story, JORN)
        gravest = max((d.severity for d in known), default=0)
        faced = came(story, JORN)
        # In a live telling he may have set out for where the man no longer was (W10): he
        # looked there, found him gone, and is still looking or has given it up.
        missed = [e for e in looked_for(story, JORN) if not e.needs_player]
        ev.check(
            "a husband who knows of an affair comes to have it out",
            bool(faced) == (gravest >= bonds.FACED_FROM) or (ev.live and bool(missed)),
            f"{seed}, he {how}: knows {[(d.kind, d.severity) for d in known]}, came "
            f"{len(faced)} times, looked in vain {len(missed)} times, {as_read(days[-2:])}",
        )
        ev.check(
            "it is no crime, and nobody reports it",
            not any(is_crime(story.state, d) for d in wrongs(story, JORN))
            and not story.fired(Kind.REPORT),
            f"{seed}: {[e.title for e in story.fired(Kind.REPORT)]}",
        )
        is_at, home = story.state.characters[JORN].location_id, returns.trip_of(story.state, JORN)
        ev.check(
            "wherever the smith has gone, he is due back in Millbrook",
            is_at == "village" or (home is not None and home.place_id == "village"),
            f"{seed}, he {how}: he is at {is_at}, due back at {home.place_id if home else None}, "
            f"{' | '.join(as_left(day, JORN) for day in days)}",
        )
        away += is_at != "village"
        if not faced:
            ends["he never came"] += 1
            ev.check(
                "nobody comes for revenge who has not had it out first",
                not coming(story, JORN, Answer.REVENGE),
                seed,
            )
            continue
        after = bool(coming(story, JORN, Answer.REVENGE))
        ends["revenge after having it out" if after else "had it out, and no more"] += 1
        ev.check(
            "the scene is told he came to hear it answered and not to attack",
            "Jorn Hale comes to have it out with Tomas Weller, to hear it answered and not to "
            "attack" in story.prompt(Node.NARRATOR),
            f"{seed}: {faced[-1].title}",
            live=False,
        )
        ev.check(
            "a rival comes for revenge only over a night together",
            after == (gravest >= bonds.BETRAYAL),
            f"{seed}, he {how}: the gravest he knows of is {gravest}, revenge "
            f"{[e.status.value for e in coming(story, JORN, Answer.REVENGE)]}",
            live=False,  # in a live scene his liking may mend, and then he lets it rest (W4)
        )
        ev.check(
            "Memory says who came over it",
            any(text.startswith("Jorn Hale came to face you over it") for text in trail(story)),
            f"{seed}: {trail(story)}",
        )
        await ev.judge(
            "the husband has it out with him",
            Rubric(
                must=(
                    "Jorn puts what Tomas did with Mara to him, as someone who knows of it, "
                    "and waits for his answer",
                ),
                must_not=(
                    "Jorn attacks Tomas in this scene",
                    "Jorn is friendly, or behaves as if nothing had happened",
                ),
            ),
            days[-1:],
        )
    ev.metric("ends", dict(ends))
    ev.check(
        "some husbands come for revenge afterwards and some have it out and no more",
        ends["revenge after having it out"] > 0 and ends["had it out, and no more"] > 0,
        str(dict(ends)),
        live=False,
    )
    ev.metric("away from Millbrook as the story stops", away)
    ev.check(
        "some husbands are away from Millbrook as the story stops, with the way home ahead",
        away > 0,
        str(away),
        live=False,
    )


@scenario(
    "t17.a-breakup",
    suite="T17",
    title="A breakup",
    requirements=("W17", "A2", "C6", "T17"),
    passes_when=(
        "A man tells his sweetheart it is over. Ending it is his to do, with nothing thrown: "
        "it is over on record by his doing, whatever the scene tells, and it costs her some of "
        "what she felt for him. Memory says the two were a couple until he ended it. A kiss "
        "afterwards is no partner's kiss, and is thrown for. Asked to be his again, she "
        "answers by her heart as it now stands, and a yes is a new romance on record beside "
        "the one that ended"
    ),
)
async def a_breakup(ev: Eval) -> None:
    ends: Counter[str] = Counter()
    for seed in ev.seeds(12, live=1):
        story = ev.story(worlds.sweethearts(), seed=seed, settings=CALM, under_way=True)
        at_first = feels(story, MARA)

        mended = None if ev.live else mends_it(MARA, BondStage.TOGETHER)
        ended = await story.act(END, part(), narration=mended)
        old = story.state.bonds["bond-1"]
        ev.check(
            "ending it is the character's to do, with nothing thrown",
            answered_as(ended, OutcomeClass.CERTAIN),
            f"{seed}: {as_read([ended])}",
        )
        ev.check(
            "it is over on record, by the one who ended it, whatever the scene tells",
            (old.stage, old.end, old.steps[-1].by_id) == (BondStage.OVER, BondEnd.PARTED, YOU)
            and bonds.partners(story.state, YOU) == [],
            f"{seed}: {old.stage.value}, {[s.by_id for s in old.steps]}",
        )
        ev.check(
            "it costs the one who was left some of what they felt",
            feels(story, MARA)[2] == at_first[2] - bonds.PARTED_HEART_COUPLE
            and feels(story, MARA)[0] < at_first[0],
            f"{seed}: {at_first} to {feels(story, MARA)}",
        )
        ev.check(
            "ending it costs her liking and trust by the rule, and no more",
            feels(story, MARA)[:2]
            == (at_first[0] - bonds.PARTED_COUPLE, at_first[1] - bonds.PARTED_COUPLE),
            f"{seed}: {at_first} to {feels(story, MARA)}",
            live=False,
        )
        person = next(p for p in memory_view(story.state).people if p.id == MARA)
        ev.check(
            "Memory says they were a couple until he ended it",
            person.bond is BondStage.OVER
            and (person.bond_line or "").startswith("You were a couple until you ended it"),
            f"{seed}: {person.bond} {person.bond_line!r}",
        )
        await ev.judge(
            "he ends it",
            Rubric(
                must=(
                    "Tomas ends it, and Mara takes it as an ending, in her own way",
                    "As the scene ends the two are no longer a couple",
                ),
                must_not=(
                    "Mara talks him out of it, or the two are still together as the scene ends",
                    "The narrator lectures the player or refuses to play the scene",
                ),
            ),
            [ended],
        )

        kissed = await story.act(KISS, bare_kiss())
        ev.check(
            "a kiss after the end is no partner's kiss: it is thrown for",
            answered_as(kissed, None),
            f"{seed}: {as_read([kissed])}",
        )
        ev.check(
            "what ended stays ended, and nothing less than an ask makes a couple",
            story.state.bonds["bond-1"].stage is BondStage.OVER
            and stage(story) in (None, BondStage.INTEREST, BondStage.COURTING),
            f"{seed}: {[(b.id, b.stage.value) for b in story.state.bonds.values()]}",
        )

        drawn = feels(story, MARA)[2]
        again = await story.act(ASK_AGAIN, ask())
        expected = by_her_heart(drawn, bonds.DECLARE_NO, bonds.DECLARE_SURE)
        ev.check(
            "asked again, she answers by her heart as it now stands",
            answered_as(again, expected),
            f"{seed}: at {drawn}, {as_read([again])}",
        )
        new = bonds.live(story.state, YOU, MARA)
        again_a_couple = new is not None and new.stage.couple
        ends["a couple again" if again_a_couple else "not a couple again"] += 1
        ev.check(
            "a yes is a new romance on record, beside the one that ended",
            story.state.bonds["bond-1"].stage is BondStage.OVER
            and (new is None or new.id != "bond-1")
            and remembered(story) is (new.stage if new is not None else BondStage.OVER),
            f"{seed}: {[(b.id, b.stage.value) for b in story.state.bonds.values()]}, Memory "
            f"{remembered(story)}",
        )
        await ev.judge(
            "after the end",
            Rubric(
                must=(
                    "Mara answers the kiss and the ask as OUTCOME says of each, as someone he "
                    "left and not as his sweetheart",
                ),
                must_not=(
                    "Mara is told as his sweetheart again before OUTCOME says the two are together",
                ),
            ),
            [kissed, again],
        )
    ev.metric("ends", dict(ends))
