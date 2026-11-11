"""T17's openness evals: the world stays open and keeps moving (docs/REQUIREMENTS.md, T17).

Every scenario here plays through the real turn graph. Deterministic mode checks what code
decides (the director, the clock, the world's answers, resolve's classes and rolls) over many
seeds; live mode plays fewer seeds with the real models and adds the judge where the table's
pass condition is about the telling.
"""

from __future__ import annotations

import json
import math
from collections import Counter

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import ContentPrefs, Difficulty, EventFrequency, Rating, StorySettings
from engine.contracts import (
    ActionKind,
    Aim,
    AttitudeShift,
    Beat,
    CharacterChange,
    ChoiceKind,
    EventSource,
    GrowthKind,
    Harm,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    PictureTrigger,
    SceneEnd,
    StandingAction,
    StateDelta,
    Theme,
)
from engine.director import rules
from engine.director.deck import CARDS
from engine.director.goals import lead_thread
from engine.director.montage import montage_steps
from engine.labels import clock_time, second_of_day
from engine.resolve.bouts import against
from engine.resolve.power import helpless_state
from engine.state import (
    Attitude,
    CharacterStatus,
    ClockStatus,
    EventStatus,
    GoalStatus,
    Health,
    Mark,
    PassingState,
    PowerAxis,
    StepResult,
    Terms,
    ThreadStatus,
    Visibility,
)
from engine.visibility import memory_view
from engine.world import Kind
from engine.world.knowledge import proven
from engine.world.norms import Nature, deed_nature
from engine.world.tuning import MAX_TICKS_PER_PASSAGE, UNKNOWN_TRIP_S
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import (
    LIFE,
    act,
    attack,
    cut_throat,
    facts,
    farming,
    full_day,
    item,
    plan,
    power,
    step,
    stop_time,
    train,
)
from graph.llm import Node

scenario = REGISTRY.scenario


def needs_decision(played: Played) -> bool:
    event = played.event
    return event is not None and event.needs_decision


# --- Quiet life (W16, E4, E6, N1) --------------------------------------------------------------


async def quiet_life(
    ev: Eval,
    seed: str,
    frequency: EventFrequency,
    *,
    turns: int = 30,
    prefs: ContentPrefs | None = None,
) -> tuple[Story, list[Played]]:
    """30 turns of farming with a spouse and no ambitions. When an event needs a decision, the
    player deals with it on the next turn, then goes back to the farm."""
    story = ev.story(
        worlds.farm(),
        seed=seed,
        settings=StorySettings(event_frequency=frequency),
        prefs=prefs,
        premise="I farm a small plot in a river valley with my wife, and I want nothing more.",
    )
    await story.open()
    answer: list[str] = []
    played = []
    for n in range(turns):
        words, interpret = LIFE[n % len(LIFE)]
        if answer:
            words = "I deal with what came up, then go back to the farm"
        turn = await story.act(words, interpret(responds_to=answer))
        played.append(turn)
        event = turn.event
        answer = [event.thread_id] if needs_decision(turn) and event.thread_id else []
    return story, played


def quiet_runs(played: list[Played]) -> list[int]:
    """Runs of turns with no decision to make: no event that needs one, and not answering one."""
    runs, run, answering = [], 0, False
    for turn in played:
        decision = needs_decision(turn)
        if decision:
            runs.append(run)
            run = 0
        elif not answering:
            run += 1
        answering = decision
    return runs


@scenario(
    "t17.quiet-life",
    suite="T17",
    title="Quiet life",
    requirements=("W16", "E4", "E6", "N1", "T17"),
    passes_when=(
        "Events with stakes arrive at least as often as W16's threshold, stay farm-sized, and "
        "calm returns after each one"
    ),
)
async def quiet_life_eval(ev: Eval) -> None:
    rubric = Rubric(
        must=(
            "Each event that arrives is farm-sized: it touches the farm, the family, the "
            "neighbours or the village, not kingdoms",
            "After an event is dealt with, the following scenes return to calm farm life",
        ),
        must_not=("Turns the quiet life into an epic quest the player never asked for",),
    )
    counts = {}
    for frequency in (EventFrequency.CALM, EventFrequency.NORMAL):
        band = math.ceil(rules.THRESHOLDS[frequency] * (1 + rules.DRIFT_SPAN))
        events = 0
        for seed in ev.seeds(12, live=1):
            story, played = await quiet_life(ev, f"{seed}/{frequency}", frequency)
            decisions = [t.event for t in played if needs_decision(t)]
            runs = quiet_runs(played)
            events += len(decisions)
            where = f"{seed} on {frequency}: quiet runs {runs}"
            ev.check("an event with stakes arrives", bool(decisions), where)
            ev.check(f"never more than {band} quiet turns on {frequency}", max(runs) <= band, where)
            ev.check(
                "farm-sized: a private life never draws a world event",
                all(e.size.value != "world" for e in decisions),
                where,
            )
            ev.check(
                "calm returns: never two events back to back", min(runs, default=2) >= 2, where
            )
            await ev.judge(f"farm-sized and calm ({frequency})", rubric, story.turns)
        counts[frequency.value] = events
        ev.metric(f"events_{frequency.value}", events)
    ev.check(
        "events come faster on normal than on calm",
        counts["normal"] > counts["calm"],
        str(counts),
        live=False,
    )


# --- Long fight (W10, W16, M1) -----------------------------------------------------------------


# The mage parries and presses without striking to hurt: this scenario is about the fight's clock,
# and how a foe's blows land is t17.mortal-fight's (N6).
HOLDS_BACK = facts(foes_mean=Aim.NONE)


def strike(n: int) -> Intent:
    return plan(
        step(f"Strike at the mage ({n})", ActionKind.EXCHANGE, 10, verb="strike", facts=HOLDS_BACK)
    )


@scenario(
    "t17.long-fight",
    suite="T17",
    title="Long fight",
    requirements=("W10", "W16", "M1", "T17"),
    passes_when=(
        "Only a few in-world minutes pass, no unrelated W16 event interrupts, and the world "
        "off-screen barely moves"
    ),
)
async def long_fight(ev: Eval) -> None:
    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.mage_fight(), seed=f"{seed}/first-blow", under_way=True)
        first = await story.act("I attack the grey mage", plan(attack("mage", facts=HOLDS_BACK)))
        fight = first.state.scene.encounter
        # A realm up the mage is a hard throw, not a wall (A3, G18): where the first blow kills
        # him, the fight began and ended with it.
        fell = not first.state.characters["mage"].alive
        ev.check(
            "attacking a key NPC starts a fight, unless the first blow ends it",
            (fight is None)
            if fell
            else fight is not None
            and fight.kind.value == "fight"
            and fight.opponent_ids == ["mage"],
            f"{seed}: {fight}",
            live=False,
        )
        # One picture a scene: the fight's start, or its decisive blow when the first blow is it.
        ev.check(
            "the fight's first blow is pictured",
            first.plan.picture is not None
            and first.plan.picture.trigger
            in (PictureTrigger.FIGHT_START, PictureTrigger.DECISIVE_BLOW, PictureTrigger.DEATH)
            and first.plan.picture.subject_id == "mage",
            f"{seed}: {first.plan.picture} after {first.step(0).reason}",
            live=False,
        )

        story = ev.story(worlds.mage_fight(), seed=seed)
        await story.open()

        def fight_starts(state) -> None:
            state.director.turns_without_stakes = 20  # pressure was high before the fight
            worlds.start_fight(state, "mage")

        story.change(fight_starts)
        start_s = story.state.world_s
        events = []
        pictures = []
        for n in range(30):
            played = await story.act("I strike at the grey mage", strike(n))
            if played.event is not None:
                events.append(played.event.title)
            if played.plan.picture is not None:
                pictures.append(played.plan.picture.trigger)
            ev.check(
                "the fight holds the director's pressure at zero",
                played.plan.stall_pressure == 0,
                seed,
            )
        state = story.state
        elapsed = state.world_s - start_s
        ev.metric("fight_world_s", elapsed)
        ev.check(
            "thirty exchanges are a few in-world minutes",
            elapsed <= 10 * MINUTE,
            f"{seed}: {elapsed}s",
        )
        ev.check(
            "the world off-screen barely moves: the tournament clock hasn't stepped",
            state.clocks["tournament"].filled == 0,
            seed,
        )
        ev.check("no unrelated event interrupts the fight", events == [], f"{seed}: {events}")
        ev.check(
            "the fight's start is a key scene",
            PictureTrigger.FIGHT_START in pictures,
            f"{seed}: {pictures}",
        )
        await ev.judge(
            "a fight that stays a fight",
            Rubric(
                must=("Every scene stays inside the fight with the grey mage",),
                must_not=("Brings in an unrelated event, visitor or summons mid-fight",),
            ),
            story.turns[-5:],
        )


# --- Mortal fight (N6, A2, A5) -----------------------------------------------------------------

THUGS = ["thug-0", "thug-1", "thug-2"]


def leap() -> IntentStep:
    return step(
        "leap off the bridge into the river",
        ActionKind.MOVE,
        3,
        verb="leap",
        facts=facts(
            opposition_ids=THUGS,
            can_respond=True,
            danger="the thirty-meter drop to the river",
            danger_class=OutcomeClass.CONTESTED,
            danger_harm=Aim.KILL,
        ),
    )


def on_the_bridge(seed: str, ev: Eval) -> Story:
    story = ev.story(worlds.bridge_ambush(), seed=seed, under_way=True)
    story.change(lambda state: worlds.start_fight(state, *THUGS))
    return story


@scenario(
    "t17.mortal-fight",
    suite="T17",
    title="Mortal fight",
    requirements=("N6", "A2", "A5", "T17"),
    passes_when=(
        "An elder three realms up cuts the player down unless a Deadly throw they almost never "
        "make holds, but sparring he only brings them down; against three thugs the player can "
        "kill one, be cut, die, or leap from the bridge and get away, and every blow and fall is "
        "told as the engine settled it (N6)"
    ),
)
async def mortal_fight(ev: Eval) -> None:
    told = []
    for seed in ev.seeds(6, live=1):
        story = ev.story(worlds.elder_bai(), seed=f"{seed}/enemy", under_way=True)
        played = await story.act("I cut down Elder Bai", plan(attack("bai", "sword")))
        swing = played.step(0)
        struck = swing.perils
        ev.check(
            "a plain sword can't hurt an elder three realms up, with no roll (A2, G18)",
            swing.outcome_class is OutcomeClass.RULED_OUT and swing.roll is None,
            f"{seed}: {swing.reason}",
            live=False,
        )
        # No gap reaches zero, and none is kind (A3): Lin throws his own defence, marked Deadly
        # before the dice, against a number three rungs up that he almost never reaches.
        thrown = [p.roll.throw for p in struck if p.roll is not None and p.roll.throw is not None]
        ev.check(
            "the elder's answer is a Deadly throw Lin almost never makes (A3, N6)",
            len(struck) == 1
            and len(thrown) == 1
            and thrown[0].deadly
            and struck[0].roll.odds < 0.03
            and (struck[0].harm is Harm.DEAD) == (thrown[0].mark is Mark.MISSED)
            and played.state.characters["lin"].alive == (struck[0].harm is not Harm.DEAD),
            f"{seed}: {[p.reason for p in struck]}",
            live=False,
        )
        told.append(("the elder", played))

        story = ev.story(worlds.elder_bai(sparring=True), seed=f"{seed}/sparring", under_way=True)
        spar = attack(
            "bai",
            aim=Aim.SUBDUE,
            text="spar with Elder Bai",
            verb="spar",
            facts=facts(opposition_ids=["bai"], can_respond=True, foes_mean=Aim.SUBDUE),
        )
        played = await story.act("I spar with Elder Bai", plan(spar))
        harms = {p.harm for s in played.steps for p in s.perils}
        ev.check(
            "sparring, the master only brings Lin down",
            harms <= {Harm.NONE, Harm.HURT, Harm.SUBDUED} and played.state.characters["lin"].alive,
            f"{seed}: {harms}",
        )
        told.append(("sparring", played))

    seen: Counter[str] = Counter()
    for seed in ev.seeds(60, live=2):
        story = on_the_bridge(f"{seed}/fight", ev)
        played = await story.act(
            "I cut down the first thug, then the second",
            plan(attack("thug-0", "sword"), attack("thug-1", "sword")),
        )
        steps = played.steps
        ev.check(
            "a blow that lands stops the plan there, for the player to react (R6)",
            not any(s.hurt_by_peril for s in steps[:-1]),
            f"{seed}: {[[p.reason for p in s.perils] for s in steps]}",
        )
        after = played.state
        lin = after.characters["lin"]
        killed = sum(not after.characters[t].alive for t in THUGS)
        seen["killed a thug and was cut"] += bool(
            killed and lin.alive and lin.sheet.condition.health is not Health.UNHURT
        )
        seen["died"] += not lin.alive
        if seed.endswith("/0") or seed.endswith("/1"):
            told.append(("the thugs", played))

        story = on_the_bridge(f"{seed}/leap", ev)
        played = await story.act("I leap off the bridge into the river", plan(leap()))
        after = played.state
        lin = after.characters["lin"]
        got_away = lin.alive and after.scene.encounter is None
        seen["leapt and got away"] += got_away
        seen["the fall killed him"] += any(
            p.harm is Harm.DEAD and not p.by_ids for p in played.step(0).perils
        )
        if seed.endswith("/0"):
            told.append(("the leap", played))
    ev.metric("bridge", dict(seen))
    ev.check(
        "Lin can kill a thug and be cut, die, or leap and get away, and the fall can kill (N6)",
        all(seen[k] for k in ("killed a thug and was cut", "died", "leapt and got away"))
        and seen["the fall killed him"] > 0,
        str(dict(seen)),
        live=False,
    )
    await ev.judge(
        "what strikes back is told as settled",
        Rubric(
            must=(
                "Every blow or fall that strikes Lin plays exactly as OUTCOME's struck says: a "
                "miss misses, a wound wounds, and a killing blow kills",
                "When the plan stopped, the scene stops there and hands the choice back",
            ),
            must_not=(
                "Lin survives what OUTCOME says killed him",
                "A foe strikes harder or more often than OUTCOME says",
            ),
        ),
        told,
    )


# --- Ignored event (W16) -----------------------------------------------------------------------


@scenario(
    "t17.ignored-event",
    suite="T17",
    title="Ignored event",
    requirements=("W16", "W10", "N1", "T17"),
    passes_when="The event plays out with its consequence instead of repeating",
)
async def ignored_event(ev: Eval) -> None:
    for seed in ev.seeds(12, live=1):
        story = ev.story(worlds.farm(), seed=seed)
        await story.open()

        def restless(state) -> None:
            state.director.turns_without_stakes = 9

        story.change(restless)
        first = await story.act("I farm all day and sleep at night", full_day())
        event = first.event
        if not ev.check("an event that needs a decision arrives", needs_decision(first), seed):
            continue
        later = [
            await story.act("I ignore it, farm all day and sleep at night", full_day())
            for _ in range(5)
        ]
        outcomes = [
            planned
            for turn in later
            for planned in ([turn.event] if turn.event else []) + turn.plan.happenings
            if planned.thread_id == event.thread_id
        ]
        ev.check("it plays out exactly once", len(outcomes) == 1, f"{seed}: {len(outcomes)}")
        if len(outcomes) == 1:
            out = outcomes[0]
            ev.check(
                "it plays out with its consequence, needing no decision",
                out.source is EventSource.DUE
                and not out.needs_decision
                and out.brief == event.consequence,
                seed,
            )
        fresh = [t.event for t in later if needs_decision(t)]
        ev.check(
            "it never comes back as a fresh event",
            all(e.thread_id != event.thread_id for e in fresh)
            and all(e.card_id is None or e.card_id != event.card_id for e in fresh),
            seed,
        )
        thread = story.state.threads[event.thread_id]
        lingers = CARDS[event.card_id].lingers if event.card_id else True
        expected = ThreadStatus.DORMANT if lingers else ThreadStatus.RESOLVED_WITHOUT_PLAYER
        ev.check("its thread is settled", thread.status is expected, f"{seed}: {thread.status}")
        await ev.judge(
            "the ignored event plays out",
            Rubric(
                must=("A later scene tells what came of the matter the player ignored",),
                must_not=("The ignored matter arrives again as if new",),
            ),
            story.turns[-6:],
        )


# --- Themes off (F7) ---------------------------------------------------------------------------


@scenario(
    "t17.themes-off",
    suite="T17",
    title="Themes off",
    requirements=("F7", "W16", "T17"),
    passes_when="No romance or dark events are drawn",
)
async def themes_off(ev: Eval) -> None:
    off = ContentPrefs(romance=False, dark_themes=False)
    banned = {Theme.ROMANCE, Theme.DARK}
    drawn = []
    for seed in ev.seeds(12, live=1):
        story, played = await quiet_life(ev, f"{seed}/off", EventFrequency.DRAMATIC, prefs=off)
        events = [t.event for t in played if t.event is not None]
        drawn += events
        ev.check(
            "no romance or dark event is drawn",
            not [e for e in events if banned & set(e.themes)],
            f"{seed}: {[e.title for e in events if banned & set(e.themes)]}",
        )
        await ev.judge(
            "no romance or dark themes",
            Rubric(
                must_not=(
                    "Starts a romance, flirtation or seduction",
                    "Starts something dark: cruelty, abuse, torture or despair",
                )
            ),
            story.turns,
        )
    ev.check("the run drew events", bool(drawn), live=False)
    # With the themes on, the same runs do draw them, so the filter is what keeps them out.
    themes = set()
    for seed in ev.seeds(12, live=0):
        _, played = await quiet_life(ev, f"{seed}/on", EventFrequency.DRAMATIC)
        themes |= {t for p in played if p.event is not None for t in p.event.themes}
    ev.check(
        "with the themes on, romance and dark events are drawn",
        {Theme.ROMANCE, Theme.DARK} <= themes,
        str(sorted(themes)),
        live=False,
    )


# --- Time skip (E7, K8) ------------------------------------------------------------------------


@scenario(
    "t17.time-skip",
    suite="T17",
    title="Time skip",
    requirements=("E7", "K8", "W10", "T17"),
    passes_when=(
        "The skip stops early when an event needs a decision, and the turn's cost stays within "
        "K8's cap"
    ),
)
async def time_skip(ev: Eval) -> None:
    from billing.pricing import K8_MAX_COST_MULTIPLE

    stopped = finished = 0
    for seed in ev.seeds(24, live=2):
        story = ev.story(worlds.farm(), seed=seed)
        await story.open()
        quiet = await story.act("I work the fields", farming())
        played = await story.act(
            "I farm here for a year",
            act("Farm here for a year", "farm", ActionKind.TIME_SKIP, YEAR),
        )
        step_ = played.step(0)
        spread = played.cost_usd / quiet.cost_usd if quiet.cost_usd else 0
        ev.check(
            f"the skip costs at most {K8_MAX_COST_MULTIPLE} times a quiet turn (K8)",
            0 < spread <= K8_MAX_COST_MULTIPLE,
            f"{seed}: {spread:.2f}",
        )
        ev.check(
            "the skip costs no more model calls than a quiet turn",
            len(played.calls) <= len(quiet.calls),
            seed,
        )
        rolled = [e for e in played.state.pending_events.values() if e.kind == "director.event"]
        ev.check(
            "the skip rolls at most the montage's capped steps",
            len(rolled) <= rules.MONTAGE_MAX_STEPS,
            f"{seed}: {len(rolled)}",
        )
        lived = played.world_seconds
        if not step_.interrupted:
            finished += 1
            ev.check("an unbroken skip runs the whole year", lived == YEAR, f"{seed}: {lived}")
            continue
        stopped += 1
        event = played.event
        ev.check(
            "the skip stops at an event that needs a decision",
            event is not None and event.needs_decision and lived < YEAR,
            f"{seed}: stopped after {lived}s",
        )
        ev.check("the montage is cut where it stopped", step_.duration_s == lived, seed)
        later = [
            e
            for e in played.state.pending_events.values()
            if e.kind == "director.event" and e.due_s > played.state.world_s
        ]
        ev.check("nothing was rolled for the months after the stop", later == [], seed)
        await ev.judge(
            "the skip stops for the event",
            Rubric(
                must=(
                    "Tells the passing time as a montage, then stops on the event that needs the "
                    "player",
                ),
                must_not=("Decides the event for the player",),
            ),
            played,
        )
    ev.metric("skips_stopped", stopped)
    ev.metric("skips_finished", finished)
    # A year of calm life almost always holds something that needs the player.
    ev.check("most year-long skips stop for an event", stopped > finished, live=False)
    ev.check(
        "a thousand years still rolls in capped steps",
        len(montage_steps(0, 1000 * YEAR)) == rules.MONTAGE_MAX_STEPS,
        live=False,
    )

    # Miki, 2026-11-11: "maybe I say, I train for a week. Well, we will see if you just train for
    # a week, or maybe during that week there is something happening that forces a scene."
    week = 7 * DAY
    whole = cut = 0
    for seed in ev.seeds(24, live=2):
        story = ev.story(worlds.cultivation_world(), seed=f"{seed}/week")
        await story.open()
        played = await story.act(
            "I train with the sword for a week",
            plan(train(GrowthKind.SKILL, "swordsmanship", 7 * 24)),
        )
        step_ = played.step(0)
        lived = played.world_seconds
        sheet = played.state.characters["lin"].sheet
        effort = sheet.practiced("skill:swordsmanship")
        earned = sheet.skill("swordsmanship") is not None  # enough before the stop: it climbed
        if not step_.interrupted:
            whole += 1
            ev.check("a week nothing cut short is a whole week", lived == week, f"{seed}: {lived}")
            continue
        cut += 1
        ev.check(
            "a week cut short stops at something that needs the player",
            needs_decision(played) and 0 < lived < week,
            f"{seed}: stopped after {lived}s",
        )
        ev.check(
            "the training put in before it is kept (A4)",
            earned or (effort is not None and 0 < effort.effort_s <= lived),
            f"{seed}: {effort}",
        )
    ev.metric("weeks_whole", whole)
    ev.metric("weeks_cut_short", cut)
    ev.check(
        "a week of training is the story's to grant: some pass whole and some are cut short",
        whole >= 4 and cut >= 4,
        f"{whole} whole, {cut} cut short",
        live=False,
    )


# --- The same hour (W16, W10) ------------------------------------------------------------------


# Scenes of a minute, each a different small thing to do, so none is a repeated action.
MINUTES = (
    ("I look out over the yard", "Look out over the yard", "look"),
    ("I say a word to Ilse", "Say a word to Ilse", "say"),
    ("I pick up the bucket", "Pick up the bucket", "pick up"),
    ("I scratch the dog's ears", "Scratch the dog's ears", "scratch"),
    ("I kick a stone off the path", "Kick a stone off the path", "kick"),
    ("I straighten the gate", "Straighten the gate", "straighten"),
    ("I drink from the well", "Drink from the well", "drink"),
)


def minute(n: int, seconds: int = MINUTE, **intent) -> tuple[str, Intent]:
    words, text, verb = MINUTES[n % len(MINUTES)]
    return words, act(text, verb, ActionKind.TASK, seconds, **intent)


@scenario(
    "t17.same-hour",
    suite="T17",
    title="The same hour",
    requirements=("W16", "W10", "E4", "T17"),
    passes_when=(
        "Inside one hour of story time one of life's events comes at most, with a few small "
        "moments ten minutes or more apart and no event marked for them, and a way to let time "
        "pass among the suggestions once in twelve scenes at most; once two hours have passed "
        "since the event, the next one comes"
    ),
)
async def same_hour(ev: Eval) -> None:
    rubric = Rubric(
        must=(
            "The small thing the scene was given happens around the character in a line or "
            "two, in this world's own form, and the scene goes on",
        ),
        must_not=(
            "Turns the small thing into danger, news or a new plot line by itself",
            "Has the character answer the small thing when the player didn't say so",
        ),
    )
    personal_gap = rules.EVENT_GAP_S["personal"]
    for frequency in EventFrequency:
        for seed in ev.seeds(8, live=1):
            story = ev.story(
                worlds.farm(),
                seed=f"{seed}/{frequency}",
                settings=StorySettings(event_frequency=frequency),
                premise="I farm a small plot in a river valley with my wife, and I want nothing "
                "more.",
            )
            await story.open()
            start = story.state.world_s
            played: list[Played] = []
            answer: list[str] = []
            for n in range(60):
                words, intent = minute(n, responds_to=answer)
                turn = await story.act(words, intent)
                played.append(turn)
                event = turn.event
                answer = [event.thread_id] if needs_decision(turn) and event.thread_id else []
            where = f"{seed} on {frequency}"
            events = [t for t in played if t.event is not None]
            moments = [t for t in played if t.plan.moment is not None]
            ev.check(
                "sixty scenes of a minute are one hour",
                story.state.world_s - start == HOUR,
                where,
                live=False,
            )
            ev.check(
                "one of life's events at most inside the hour",
                len(events) <= 1,
                f"{where}: {[t.event.title for t in events]}",
                live=False,
            )
            ev.check(
                "small things still happen, a few of them",
                2 <= len(moments) <= 6,
                f"{where}: {len(moments)} moments",
                live=False,
            )
            ev.check(
                "a moment marks no event and opens nothing",
                all(
                    t.scene.event is None
                    and not t.plan.updates.new_threads
                    and not t.plan.updates.schedule
                    for t in moments
                ),
                where,
            )
            came = [t for t in played if t.event or t.plan.moment or t.plan.talk]
            apart = [
                later.state.world_s - earlier.state.world_s
                for earlier, later in zip(came, came[1:], strict=False)
                if later.event is None
            ]
            ev.check(
                "a small thing keeps ten minutes from what came before it",
                all(gap >= rules.SMALL_GAP_S for gap in apart),
                f"{where}: {apart}",
                live=False,
            )
            # S2: the pace is the player's, so nothing pushes the clock on: a way to let time
            # pass is one choice among the others, once in a long run of short scenes.
            offered = [
                n for n, t in enumerate(played) if ChoiceKind.TIME in t.plan.suggestions.kinds
            ]
            ev.check(
                "a way to let time pass is offered now and then, never pushed",
                1 <= len(offered) <= 60 // rules.SLOW_CLOCK_SCENES
                and all(
                    later - sooner >= rules.SLOW_CLOCK_SCENES
                    for sooner, later in zip(offered, offered[1:], strict=False)
                )
                and not any(needs_decision(played[n]) for n in offered),
                f"{where}: offered in scenes {offered}",
                live=False,
            )
            if moments:
                told = moments[0]
                await ev.judge(
                    f"small things stay small ({frequency})",
                    rubric,
                    told,
                    context=f"The scene was given this small thing: {told.plan.moment.brief}",
                )

            # Then the scenes take half an hour each, and life's events come again.
            first_s = events[0].state.world_s if events else start
            turn = played[-1]
            for n in range(60, 80):
                words, intent = minute(n, 30 * MINUTE, responds_to=answer)
                turn = await story.act(words, intent)
                if turn.event is not None:
                    break
            ev.check(
                "once the hours have passed, the next event comes",
                turn.event is not None and turn.state.world_s - first_s >= personal_gap,
                f"{where}: {(turn.state.world_s - first_s) / HOUR:.1f} h after the first",
                live=False,
            )


# --- Goal ownership (N2) -----------------------------------------------------------------------


# N2: what makes a goal the player's, which nothing ever rewrites.
WORDS = ("id", "text", "set_turn", "lead_id")


def _closed_rightly(state, goal_id: str) -> bool:
    """N2: while the player only drinks, a goal closes only as a repeat of another, or with the
    thread of its lead or of a goal merged into it."""
    goal = state.goals[goal_id]
    if goal.status is GoalStatus.MERGED:
        return True
    carried = [g for g in state.goals.values() if g.id == goal_id or g.merged_into == goal_id]
    return any((t := lead_thread(state, g)) is not None and t.status.closed for g in carried)


@scenario(
    "t17.goal-ownership",
    suite="T17",
    title="Goal ownership",
    requirements=("N2", "N1", "W16", "T17"),
    passes_when=(
        "The player's goals are never rewritten and never change without the player's input; "
        "while the player only drinks, a goal closes only as a repeat of another or with its "
        "lead's thread (N2)"
    ),
)
async def goal_ownership(ev: Eval) -> None:
    offered = taken = 0
    stated = {10: "Take over the family", 30: "Get out of Naples alive"}
    for seed in ev.seeds(6, live=1):
        story = ev.story(worlds.grounded_world(), seed=seed)
        await story.open()
        answer: list[str] = []
        before = {g.id: g.model_dump() for g in story.state.goals.values()}
        for n in range(1, 51):
            goals = [stated[n]] if n in stated else []
            state = story.state
            open_leads = [i for i, lead in state.leads.items() if lead.status.value == "open"]
            if n % 7 == 0 and open_leads:
                answer = [*answer, open_leads[0]]
                taken += 1
            words = "I drink at the bar" + (f". From now on: {goals[0]}" if goals else "")
            intent = act(
                "Drink at the bar",
                "drink",
                ActionKind.TASK,
                2 * HOUR,
                goals=goals,
                responds_to=answer,
            )
            played = await story.act(words, intent)
            offered += len(played.plan.updates.new_leads)
            event = played.event
            answer = [event.thread_id] if needs_decision(played) and n % 2 else []
            after = {g.id: g.model_dump() for g in story.state.goals.values()}
            ev.check(
                "no goal is ever rewritten",
                all(all(after.get(i, {}).get(k) == g[k] for k in WORDS) for i, g in before.items()),
                f"{seed} turn {n}",
            )
            closed = [i for i, g in before.items() if after.get(i, g)["status"] is not g["status"]]
            ev.check(
                "while the player only drinks, a goal closes only as a repeat or with its thread",
                all(_closed_rightly(story.state, i) for i in closed),
                f"{seed} turn {n}: {[before[i]['text'] for i in closed]}",
            )
            added = [after[i] for i in after if i not in before]
            ev.check(
                "every new goal is one the player stated or accepted",
                all(g["text"] in goals or g["lead_id"] in intent.responds_to for g in added),
                f"{seed} turn {n}: {[g['text'] for g in added]}",
                live=False,
            )
            before = after
        texts = {g.text for g in story.state.goals.values()}
        ev.check(
            "the stated goals are kept",
            {"Find out who killed my father.", *stated.values()} <= texts,
            f"{seed}: {sorted(texts)}",
            live=False,
        )
    ev.check("the run offered leads and the player took some", bool(offered and taken), live=False)


# --- Fleeing witness and interrupted sleep (W10, W11) ------------------------------------------


async def kill_then_brew(ev: Eval, seed: str) -> Story:
    """Kill someone with a witness at hand, then ten short turns brewing a potion."""
    story = ev.story(worlds.sect_with_a_witness(), seed=seed)
    await story.open()
    killing = await story.act(
        "I cut Han's throat while he dozes against the well",
        plan(
            cut_throat(
                "han",
                "sword",
                facts=facts(opposition_ids=["han"], can_respond=False, why_not="asleep"),
            )
        ),
    )
    ev.check(
        "the killing lands",
        killing.result is not None
        and killing.state.characters["han"].status is CharacterStatus.DEAD,
        seed,
    )
    for _ in range(10):
        await story.act(
            "I stir the potion and add the next herb",
            act("stir the potion", "brew", ActionKind.TASK, 18),
        )
    return story


@scenario(
    "t17.fleeing-witness",
    suite="T17",
    title="Fleeing witness",
    requirements=("W10", "W11", "W2", "T17"),
    passes_when=(
        "No guards arrive until the report could really have been made and they could have "
        "travelled (W10)"
    ),
)
async def fleeing_witness(ev: Eval) -> None:
    for seed in ev.seeds(6, live=1):
        story = await kill_then_brew(ev, seed)
        deeds = list(story.state.deeds.values())
        ev.check(
            "the killing is a deed the witness saw",
            len(deeds) == 1 and "wei" in deeds[0].witness_ids,
            f"{seed}: {[d.witness_ids for d in deeds]}",
            live=False,
        )
        if not deeds:
            continue
        deed = deeds[0]
        elapsed = story.state.world_s - deed.world_s
        ev.check(
            "the brewing takes minutes, not hours", elapsed < UNKNOWN_TRIP_S, f"{seed}: {elapsed}s"
        )
        ev.check("nobody has heard yet", story.fired(Kind.REPORT) == [], seed)
        ev.check("nobody has come", story.fired(Kind.ANSWER) == [], seed)
        reports = [
            e
            for e in story.state.pending_events.values()
            if e.kind == Kind.REPORT and e.status is EventStatus.PENDING
        ]
        ev.check(
            "the witness is on the way to tell the sect",
            {r.payload["faction_id"] for r in reports} >= {"azure-cloud"},
            f"{seed}: {[r.payload for r in reports]}",
        )
        ev.check(
            "a report takes at least the trip",
            all(r.due_s >= deed.world_s + UNKNOWN_TRIP_S for r in reports),
            seed,
        )
        await ev.judge(
            "no guards yet",
            Rubric(
                must_not=(
                    "Guards, enforcers or elders arrive or confront the player about the killing",
                ),
            ),
            story.turns[-10:],
        )


@scenario(
    "t17.interrupted-sleep",
    suite="T17",
    title="Interrupted sleep",
    requirements=("W10", "W11", "W5", "T17"),
    passes_when=(
        "The engine plays the night in time order, and the guards wake the player at the moment "
        "they arrive"
    ),
)
async def interrupted_sleep(ev: Eval) -> None:
    for seed in ev.seeds(6, live=1):
        story = await kill_then_brew(ev, seed)
        asleep_at = story.state.world_s
        played = await story.act(
            "I lie down by the well and sleep for eight hours",
            act("sleep", "sleep", ActionKind.REST, 8 * HOUR),
        )
        answers = [e for e in played.fired if e.kind == Kind.ANSWER]
        ev.check("the guards come during the night", bool(answers), seed)
        if not answers:
            continue
        guards = answers[-1]
        ev.check(
            "they come for the player",
            guards.payload.get("target_id") == "lin" and guards.needs_player,
            f"{seed}: {guards.payload}",
        )
        times = [e.applied_s for e in played.fired]
        ev.check("the night is played in time order", times == sorted(times), seed)
        ev.check(
            "the scene starts when they arrive",
            story.state.world_s == guards.applied_s < asleep_at + 8 * HOUR,
            f"{seed}: woke at {story.state.world_s - asleep_at}s",
        )
        ev.check("the sleep is cut short", played.step(0).interrupted, seed)
        reports = story.fired(Kind.REPORT, faction_id=guards.payload.get("faction_id"))
        ev.check(
            "they came only after the report reached them and the trip",
            bool(reports) and guards.applied_s - reports[0].applied_s >= UNKNOWN_TRIP_S,
            seed,
        )
        await ev.judge(
            "woken by the guards",
            Rubric(
                must=("The player is woken by the guards arriving",),
                must_not=("The night passes in full before anything happens",),
            ),
            played,
        )


# --- Stop the witness (W2, W11, W13) -----------------------------------------------------------


def _witnesses(story: Story) -> list[dict]:
    """Who the narrator's last brief said is off to tell what they saw (deterministic mode)."""
    brief = story.prompt(Node.NARRATOR)
    if "## WITNESSES\n" not in brief:
        return []
    return json.loads(brief.split("## WITNESSES\n", 1)[1].split("\n", 1)[0])


def _leaving(story: Story) -> list[str]:
    """Who the last reading was told is leaving the scene to tell of it (deterministic mode)."""
    asked = story.prompt(Node.INTERPRET)
    if "## SCENE\n" not in asked:
        return []
    scene = json.loads(asked.split("## SCENE\n", 1)[1].split("\n", 1)[0])
    return [w["id"] for w in scene.get("leaving", [])]


@scenario(
    "t17.stop-the-witness",
    suite="T17",
    title="Stop the witness",
    requirements=("W2", "W11", "W13", "W10", "C6", "T17"),
    passes_when=(
        "The scene of the killing shows the witness making to run. Cut down before he gets "
        "away, he tells nobody: no report reaches the sect, no rumor names the killer and "
        "nobody comes on his word. Left to run, he reaches the sect and it answers (W11)"
    ),
)
async def stop_the_witness(ev: Eval) -> None:
    ends: Counter[str] = Counter()
    for seed in ev.seeds(8, live=1):
        story = ev.story(worlds.one_witness(), seed=seed, under_way=True)
        killing = await story.act(
            "I cut Han's throat while he dozes against the well",
            plan(
                cut_throat(
                    "han",
                    "sword",
                    facts=facts(opposition_ids=["han"], can_respond=False, why_not="asleep"),
                )
            ),
        )
        ev.check(
            "the scene of the killing is told Wei is off to tell of it, still within reach",
            [(w["id"], w["gone"]) for w in _witnesses(story)] == [("wei", False)],
            f"{seed}: {_witnesses(story)}",
            live=False,
        )
        await ev.judge(
            "the witness makes to run",
            Rubric(
                must=(
                    "Wei is shown reacting to the killing by backing away, turning to run, "
                    "bolting or otherwise making to get away",
                ),
                must_not=(
                    "Guards, enforcers or elders arrive or confront the player about the killing",
                ),
            ),
            killing,
        )
        chase = await story.act(
            "I go after Wei and cut him down before he is out of the yard",
            plan(cut_throat("wei", "sword", facts=facts(opposition_ids=["wei"], can_respond=True))),
        )
        ev.check(
            "the next reading is told Wei is leaving, so the player can go after him",
            _leaving(story) == ["wei"],
            f"{seed}: {_leaving(story)}",
            live=False,
        )
        wei = chase.state.characters["wei"]
        silenced = wei.status is not CharacterStatus.ALIVE or helpless_state(wei) is not None
        ends["silenced" if silenced else "got away"] += 1
        night = await story.act(
            "I lie down by the well and sleep for eight hours",
            act("sleep", "sleep", ActionKind.REST, 8 * HOUR),
        )
        han = next((d for d in story.state.deeds.values() if "han" in d.victim_ids), None)
        ev.check("the killing is a deed", han is not None, seed)
        if han is None:
            continue
        told = [e for e in story.fired(Kind.REPORT) if e.status is EventStatus.APPLIED]
        came = [e for e in story.fired(Kind.ANSWER) if e.payload.get("deed_id") == han.id]
        if silenced:
            ev.check("a silenced witness reaches nobody", told == [], f"{seed}: {len(told)}")
            ev.check(
                "no faction knows who killed Han unless the world worked it out from the body",
                han.known_by_factions == [] or han.discovered,
                f"{seed}: {han.known_by_factions}",
            )
            ev.check(
                "word of it is out only if the world found it out (W13)",
                han.word_out_s is None or han.discovered,
                f"{seed}: out at {han.word_out_s}",
            )
            ev.check(
                "nobody comes on a witness's word",
                came == [] or han.discovered,
                f"{seed}: {[e.payload.get('answer') for e in came]}",
            )
        else:
            ev.check(
                "a witness who got away reaches the sect",
                "azure-cloud" in han.known_by_factions,
                f"{seed}: {han.known_by_factions}",
            )
            ev.check(
                "and no sooner than he could have got there (W10)",
                all(e.applied_s >= han.world_s + UNKNOWN_TRIP_S for e in told),
                f"{seed}: {[e.applied_s - han.world_s for e in told]}",
            )
        if silenced:
            await ev.judge(
                "the night after",
                Rubric(
                    must_not=(
                        "Wei, who was killed or left helpless, is shown up and about, talking "
                        "or bringing others",
                        "Guards, enforcers or elders say that Wei told them of the killing",
                    ),
                ),
                night,
            )
    ev.metric("ends", dict(ends))
    ev.check("some seeds silence the witness", ends["silenced"] > 0, str(dict(ends)), live=False)


# --- One man's word (W4, W5) -------------------------------------------------------------------


def _scene_person(story: Story, character_id: str) -> dict | None:
    """How the narrator's last brief showed someone in the scene (deterministic mode)."""
    brief = story.prompt(Node.NARRATOR)
    if "## SCENE\n" not in brief:
        return None
    scene = json.loads(brief.split("## SCENE\n", 1)[1].split("\n", 1)[0])
    return next((c for c in scene["present"] if c["id"] == character_id), None)


def _came_for(story: Story, avenger_id: str) -> list:
    """The times someone came to the player character over a deed, in the order they came."""
    return [
        e
        for e in story.fired(Kind.ANSWER, avenger_id=avenger_id)
        if e.status is EventStatus.APPLIED and e.needs_player
    ]


def a_day_in_millbrook() -> Intent:
    return plan(
        step("Help with the harvest in Millbrook", ActionKind.WORK, 12 * HOUR, verb="work"),
        step("Sleep at the inn", ActionKind.REST, 12 * HOUR, verb="sleep"),
    )


def bram_at_his_fence() -> dict:
    """A scripted scene that ends with Old Bram in it, as a live one that walks up to him does."""
    end = SceneEnd(
        ended_on="Old Bram leans on his fence and looks Tomas over.",
        place_id="village",
        present_ids=["tomas", "bram"],
    )
    return {
        "narration": "(scripted) Old Bram straightens up from his fence as Tomas comes over.",
        "suggestions": [],
        "update": StateDelta(scene_end=end).model_dump(mode="json"),
    }


@scenario(
    "t17.one-mans-word",
    suite="T17",
    title="One man's word",
    requirements=("W4", "W5", "W2", "W10", "T17"),
    passes_when=(
        "After a killing one person saw, whoever only hears it said thinks worse of the player "
        "and holds nothing against them, and nobody comes on talk. The dead man's brother, "
        "told by someone who knows, comes to face the player with it, and for revenge only "
        "after, hours later. When two saw it, he comes for revenge with no accusation first"
    ),
)
async def one_mans_word(ev: Eval) -> None:
    ends: Counter[str] = Counter()
    for n, seed in enumerate(ev.seeds(8, live=1)):
        two_saw = n % 2 == 1  # live plays the story one man saw
        story = ev.story(worlds.thief_in_the_barn(two_saw=two_saw), seed=seed, under_way=True)
        await story.act(
            "I cut Jorn's throat with my knife while he sleeps in the hay",
            plan(
                cut_throat(
                    "jorn",
                    "knife",
                    facts=facts(opposition_ids=["jorn"], can_respond=False, why_not="asleep"),
                )
            ),
        )
        await story.act(
            "I leave the barn and walk down the road into Millbrook",
            plan(
                step(
                    "walk into Millbrook",
                    ActionKind.TRAVEL,
                    40 * MINUTE,
                    verb="walk",
                    destination="village",
                )
            ),
        )
        await story.act(
            "I take a seat outside the Millbrook inn and rest there for an hour",
            act("rest outside the inn for an hour", "rest", ActionKind.TASK, HOUR),
        )
        deed = next((d for d in story.state.deeds.values() if "jorn" in d.victim_ids), None)
        ev.check("the killing is a deed", deed is not None, seed)
        if deed is None:
            continue
        saw = sorted(deed.witness_ids)
        ev.check(
            "who saw it is who was in the barn",
            saw == (["henk", "pim"] if two_saw else ["pim"]),
            f"{seed}: {saw}",
            live=False,
        )
        ev.check(
            "what one saw is one man's word, and what two saw is beyond it",
            proven(story.state, deed) is two_saw,
            f"{seed}: saw {saw}",
            live=False,
        )

        # Old Bram, who has no tie to the dead man, has only what goes round Millbrook.
        bram = story.state.characters["bram"].attitude_toward("tomas")
        heard = "bram" in deed.heard_by
        if heard and not _came_for(story, "kasper"):
            ends["Bram heard it said"] += 1
            ev.check(
                "someone who only heard it said thinks worse of the player, with no grudge",
                bram.affinity < 30 and not bram.grudges,
                f"{seed}: {bram}",
            )
            await story.act(
                "I walk over to Old Bram at his fence and wish him a good day",
                plan(
                    step(
                        "wish Old Bram a good day",
                        ActionKind.CONVERSATION,
                        5 * MINUTE,
                        verb="greet",
                        target_ids=["bram"],
                    )
                ),
                narration=None if ev.live else bram_at_his_fence(),
            )
            talk = await story.act(
                "I ask Bram how his fences are holding, and what people are saying in the "
                "village these days",
                plan(
                    step(
                        "ask Bram what people are saying",
                        ActionKind.CONVERSATION,
                        10 * MINUTE,
                        verb="ask",
                        target_ids=["bram"],
                    )
                ),
            )
            shown = _scene_person(story, "bram")
            ev.check(
                "the narrator is told what Bram has only heard said, and no grudge",
                shown is not None
                and len(shown["toward_you"].get("heard_said", [])) == 1
                and "Jorn Hask" in shown["toward_you"]["heard_said"][0]
                and "grudges" not in shown["toward_you"],
                f"{seed}: {shown and shown.get('toward_you')}",
                live=False,
            )
            if not ev.live or "bram" in talk.state.scene.present_ids:
                await ev.judge(
                    "someone who has only heard it said",
                    Rubric(
                        must=(
                            "Old Bram is cooler, warier or more guarded with Tomas than a "
                            "friendly neighbour would be, or he hints at, repeats or asks "
                            "about what is being said of Tomas",
                        ),
                        must_not=(
                            "Old Bram states as a certain fact that Tomas killed Jorn, as "
                            "someone who saw it or knows it would",
                            "Old Bram attacks Tomas, tries to seize him or calls on others "
                            "to seize him",
                        ),
                    ),
                    talk,
                )
        elif two_saw:
            ev.check(
                "talk of what two saw counts as knowing",
                "bram" not in deed.heard_by,
                f"{seed}: {deed.heard_by}",
            )

        # Kasper, the dead man's brother, is sent word by someone who knows. He takes up to two
        # days to come and face Tomas, and up to a week to come for revenge (W10).
        for _ in range(9 if two_saw else 4):
            if _came_for(story, "kasper"):
                break
            await story.act(
                "I take a room at the inn and stay in Millbrook until tomorrow, helping with "
                "the harvest",
                a_day_in_millbrook(),
            )
        came = _came_for(story, "kasper")
        deed = story.state.deeds[deed.id]
        kasper = story.state.characters["kasper"].attitude_toward("tomas")
        ev.check(
            "told by someone who knows, the brother holds it against the player",
            "kasper" in deed.known_by and [g.deed_id for g in kasper.grudges] == [deed.id],
            f"{seed}: known by {deed.known_by}, {kasper}",
        )
        only_heard = [
            cid
            for cid in deed.heard_by
            if any(
                g.deed_id == deed.id
                for g in story.state.characters[cid].attitude_toward("tomas").grudges
            )
            or story.fired(Kind.ANSWER, avenger_id=cid)
        ]
        ev.check(
            "nobody who only heard it said holds it against the player or comes for them",
            only_heard == [],
            f"{seed}: {only_heard}",
        )
        ev.check("the brother comes to the player", bool(came), f"{seed}: nobody came")
        if not came:
            continue
        first = came[0].payload
        if two_saw:
            ends["revenge at once"] += 1
            ev.check(
                "for what two saw he comes for revenge, with no accusation first",
                first["answer"] == "revenge" and not first.get("faced"),
                f"{seed}: {first}",
            )
            continue
        ev.check(
            "on one man's word he comes to face the player with it, not for revenge",
            first["answer"] == "confront",
            f"{seed}: {first}",
        )
        ev.check(
            "the scene is told he came to hear it answered and not to attack",
            "to hear it answered and not to attack" in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        await ev.judge(
            "the brother puts it to the player's face",
            Rubric(
                must=(
                    "Kasper Hask comes to Tomas and puts it to him that he killed Jorn, or "
                    "demands to know whether it is true",
                ),
                must_not=(
                    "Kasper strikes, stabs or otherwise attacks Tomas in this scene",
                    "Kasper speaks as someone who saw the killing with his own eyes",
                ),
            ),
            story.last,
        )
        faced_s = came[0].applied_s
        await story.act(
            "I tell Kasper the truth: his brother had been robbing my smokehouse, I found him "
            "in my barn and I killed him, and I am sorry for his loss",
            plan(
                step(
                    "tell Kasper what happened",
                    ActionKind.CONVERSATION,
                    10 * MINUTE,
                    verb="tell",
                    target_ids=["kasper"],
                )
            ),
        )
        for _ in range(9):
            if len(_came_for(story, "kasper")) > 1:
                break
            await story.act(
                "I stay on in Millbrook for another day, helping with the harvest",
                a_day_in_millbrook(),
            )
        after = _came_for(story, "kasper")[1:]
        ends["revenge after facing him" if after else "no revenge yet"] += 1
        ev.check(
            "an accusation that changed nothing brings revenge",
            bool(after) and after[0].payload["answer"] == "revenge" and after[0].payload["faced"],
            f"{seed}: {[e.payload for e in after]}",
            live=False,
        )
        ev.check(
            "and no sooner than six hours after he faced the player (W10)",
            all(e.applied_s >= faced_s + 6 * HOUR for e in after),
            f"{seed}: {[e.applied_s - faced_s for e in after]}",
        )
    ev.metric("ends", dict(ends))
    ev.check(
        "some seeds leave Bram with what he heard said",
        ends["Bram heard it said"] > 0,
        str(dict(ends)),
        live=False,
    )


# --- A day in town (W10) -----------------------------------------------------------------------


@scenario(
    "t17.day-in-town",
    suite="T17",
    title="A day in town",
    requirements=("W10", "R3", "T17"),
    passes_when=(
        "Each action moves the clock by what it really takes, the wait ends at nightfall on the "
        "clock, and every scene's light and time of day match the clock (W10)"
    ),
)
async def day_in_town(ev: Eval) -> None:
    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.farm(), seed=seed)  # the farm, at 06:00 on day 1
        await story.open()
        ev.check(
            "the opening is told at the hour the story opens",
            '"clock":"06:00"' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        walk = await story.act(
            "I walk down the road into Millbrook to see the market",
            plan(
                step(
                    "walk into Millbrook",
                    ActionKind.TRAVEL,
                    40 * MINUTE,
                    verb="walk",
                    destination="village",
                )
            ),
        )
        ev.check(
            "every action is read as a step",
            "no_step" not in walk.issues,
            f"{seed}: {walk.issues}",
        )
        ev.check(
            "the walk into town takes minutes, not seconds",
            walk.world_seconds >= 10 * MINUTE,
            f"{seed}: {walk.world_seconds}s",
        )
        meal = await story.act(
            "I sit down at the inn and eat a bowl of stew",
            act("eat a bowl of stew", "eat", ActionKind.TASK, 40 * MINUTE),
        )
        ev.check(
            "a meal takes a while",
            "no_step" not in meal.issues and meal.world_seconds >= 10 * MINUTE,
            f"{seed}: {meal.issues}, {meal.world_seconds}s",
        )
        wait = await story.act(
            "I stay at the inn until nightfall",
            plan(step("wait until nightfall", ActionKind.WAIT, 60, verb="wait", until="19:00")),
        )
        if not ev.check("the wait is played", wait.completed, f"{seed}: {wait.refused!r}"):
            continue
        if wait.steps and wait.step(-1).interrupted:
            continue  # something that needed the player came first (W10)
        ended = second_of_day(wait.state.bible.calendar, wait.state.world_s)
        ev.check(
            "the wait ends at nightfall on the clock",
            18 * HOUR <= ended <= 21 * HOUR,
            f"{seed}: ended at {clock_time(ended)}",
        )
        ev.check(
            "the wait ends exactly when the clock shows the time asked for",
            ended == 19 * HOUR,
            f"{seed}: ended at {ended}s",
            live=False,
        )
        ev.check(
            "the narrator is told what time it is now",
            '"now":{"date":"Day 1, evening","clock":"19:00"' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        await ev.judge(
            "the telling keeps to the clock",
            Rubric(
                must=(
                    "Each scene's light, meals and time of day fit the clock it ends at "
                    "(morning light in the morning, dusk or lamplight in the evening)",
                    "The last scene ends at nightfall or in the evening",
                ),
                must_not=(
                    "A scene lets night fall, a day end or a meal of another hour come round "
                    "before its clock reaches that time",
                    "A scene skips ahead in time beyond what its clock shows",
                ),
            ),
            story.turns[-4:],
        )


# --- The long road (W10, W7, W16) ---------------------------------------------------------------

ROAD_TO_THE_CITY = 3 * DAY
# A scripted scene that says it let the character catch the talk it was offered (W2).
CAUGHT_THE_TALK = {
    "narration": "(Scripted scene: at the next stall two carters are talking about the duke.)",
    "told_talk": True,
    "suggestions": [],
    "update": {},
}


@scenario(
    "t17.long-road",
    suite="T17",
    title="The long road",
    requirements=("W10", "W7", "W16", "W2", "R8", "T17"),
    passes_when=(
        "A trip takes the time the map says whatever the first model proposed, the character "
        "ends up where the trip took them, a journey can be walked in stretches and is stopped "
        "on the way by what the road brings, and the way there and back adds up to the map's "
        "time (W10). Arriving brings no news: what the city is saying is offered to a later, "
        "quiet scene, and only what a scene told is heard (W2)"
    ),
)
async def long_road(ev: Eval) -> None:
    met_something = arrived_at_once = 0
    for seed in ev.seeds(12, live=1):
        story = ev.story(worlds.long_road(), seed=seed)
        await story.open()
        # The first model's usual mistake: a walk to the village as a two-minute move.
        walk = await story.act(
            "I walk down the road into Millbrook",
            plan(step("walk into Millbrook", ActionKind.MOVE, 2 * MINUTE, destination="Millbrook")),
        )
        ev.check(
            "the walk takes what the map says, not what was proposed",
            walk.world_seconds == 40 * MINUTE,
            f"{seed}: {walk.world_seconds}s",
            live=False,
        )
        ev.check(
            "a walk to the next village takes minutes to hours, never seconds",
            10 * MINUTE <= walk.world_seconds <= 4 * HOUR,
            f"{seed}: {walk.world_seconds}s",
        )
        ev.check(
            "the character is where the trip took them",
            walk.state.scene.place_id == "village" and walk.state.player.location_id == "village",
            f"{seed}: {walk.state.scene.place_id}",
        )
        # A journey in stretches: half an hour toward the city, then on.
        stretch = await story.act(
            "I set out for Harrowgate and walk for half an hour",
            plan(
                step(
                    "walk toward Harrowgate for half an hour",
                    ActionKind.TRAVEL,
                    30 * MINUTE,
                    destination="city",
                    timed=True,
                )
            ),
        )
        ev.check(
            "a stretch the player sets stops when its time is up, on the way",
            stretch.world_seconds == 30 * MINUTE and stretch.state.scene.place_id != "city",
            f"{seed}: {stretch.world_seconds}s in {stretch.state.scene.place_id}",
            live=False,
        )
        ev.check(
            "the narrator is told the trip stopped on the way, and how much is left",
            '"arrived":false,"left":"2 d 23 h"' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        # At the stop they do something else, off the road: the journey is still theirs.
        rest = await story.act(
            "I go down to the stream by the road and rest a while",
            plan(
                step(
                    "go down to the stream and rest",
                    ActionKind.REST,
                    20 * MINUTE,
                    destination="the stream",
                )
            ),
        )
        ev.check(
            "what they do at a stop on the way leaves the journey as it is",
            rest.state.journey is not None
            and rest.state.journey.left_s == ROAD_TO_THE_CITY - 30 * MINUTE,
            f"{seed}: {rest.state.journey}",
            live=False,
        )
        ev.check(
            "a rest by the road leaves the journey to go on",
            rest.state.journey is not None,
            f"{seed}: in {rest.state.scene.place_id}",
        )
        on_the_road = stretch.world_seconds
        stops = 0
        legs: list[Played] = [stretch]
        for _ in range(12):
            if story.state.scene.place_id == "city":
                break
            leg = await story.act(
                "I walk on to Harrowgate",
                # However little the first model proposes, the rest takes what is left.
                plan(step("walk on", ActionKind.TRAVEL, 5 * MINUTE)),
            )
            legs.append(leg)
            if not leg.steps or leg.step(-1).trip is None:
                continue
            on_the_road += leg.world_seconds
            if leg.step(-1).interrupted:
                stops += 1
                ev.check(
                    "what the road brings stops the trip on the way, never at its end",
                    leg.state.scene.place_id != "city" and leg.state.journey is not None,
                    f"{seed}: {leg.state.scene.place_id}",
                )
                ev.check(
                    "a stop on the way is the scene's event, from the road's own table",
                    leg.event is not None
                    and leg.event.card_id is not None
                    and leg.event.card_id.startswith("road-"),
                    f"{seed}: {leg.event}",
                    live=False,
                )
        ev.check(
            "the journey arrives",
            story.state.scene.place_id == "city" and story.state.journey is None,
            f"{seed}: in {story.state.scene.place_id} after {len(legs)} stretches",
        )
        # W2: the city was talking before they came, and arriving brings no news of it.
        ev.check(
            "nothing is heard by arriving: the scene is told it is a first visit, and no talk",
            story.state.rumors["city-news"].heard_at == {}
            and '"arrived":true,"first_visit":true}' in story.prompt(Node.NARRATOR)
            and "## TALK" not in story.prompt(Node.NARRATOR),
            f"{seed}: {story.state.rumors['city-news'].heard_at}",
            live=False,
        )
        # They stop and look on, the one scene that is always offered what the place is saying
        # unless something else is going on in it.
        offered = False
        looks: list[Played] = []
        for _ in range(3):
            looks.append(await story.stand(StandingAction.OBSERVE, narration=CAUGHT_THE_TALK))
            if "## TALK" in story.prompt(Node.NARRATOR):
                offered = True
                break
            ev.check(
                "a scene that wasn't offered the talk records none, whatever it says it told",
                story.state.rumors["city-news"].heard_at == {},
                seed,
                live=False,
            )
        ev.check(
            "looking on in the city, a scene is offered what the city is saying",
            offered and f'{{"saying":"{worlds.HARROWGATE_TALK}"}}' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        ev.check(
            "what that scene told is heard, and Memory keeps it",
            "tomas" in story.state.rumors["city-news"].heard_at
            and worlds.HARROWGATE_TALK in [r.text for r in memory_view(story.state).rumors],
            f"{seed}: {story.state.rumors['city-news'].heard_at}",
            live=False,
        )
        ev.check(
            "however many stretches it took, the way took the map's three days",
            on_the_road == ROAD_TO_THE_CITY,
            f"{seed}: {on_the_road}s in {len(legs)} stretches",
            live=False,
        )
        ev.check(
            "a journey of days takes days",
            2 * DAY <= on_the_road <= 5 * DAY,
            f"{seed}: {on_the_road}s",
        )
        ev.check(
            "a long way is a few scenes on the road, never a stop at every bend",
            stops <= 4,
            f"{seed}: {stops} stops",
        )
        met_something += stops > 0
        arrived_at_once += len(legs) == 2
        await ev.judge(
            "the telling of the journey",
            Rubric(
                must=(
                    "A stretch of days on the road is told as days passing on the way: the "
                    "land, the weather, the nights",
                    "The scene in which the character reaches Harrowgate is set in Harrowgate",
                ),
                must_not=(
                    "A scene lists several rumors or pieces of news the character hears one "
                    "after another",
                    "The scene in which the character reaches Harrowgate stops for someone to "
                    "tell them news they didn't ask for",
                    "A scene has the character in Harrowgate before the trip there has arrived",
                    "A journey of days is told as if it took minutes",
                    "A scene that stops on the way ends back in Millbrook or at the farm",
                ),
            ),
            [*legs, *looks],
        )
    ev.check(
        "some journeys meet something on the way and some go straight through",
        0 < met_something and 0 < arrived_at_once,
        f"{met_something} met something, {arrived_at_once} went straight through",
        live=False,
    )


# --- Phone witness (G6, W10) -------------------------------------------------------------------


def shoot_carmine() -> Intent:
    return plan(
        step(
            "shoot Carmine in the back",
            verb="shoot",
            aim=Aim.KILL,
            target_ids=["carmine"],
            uses=[item("pistol")],
            facts=facts(
                opposition_ids=["carmine"],
                can_respond=False,
                why_not="unaware, his back turned",
                means=MeansVerdict.CLEARLY_ENOUGH,
            ),
        )
    )


@scenario(
    "t17.phone-witness",
    suite="T17",
    title="Phone witness",
    requirements=("G6", "W10", "W11", "T17"),
    passes_when=(
        "The police are called within minutes and arrive after the drive time, neither at once "
        "nor never"
    ),
)
async def phone_witness(ev: Eval) -> None:
    for seed in ev.seeds(6, live=1):
        story = ev.story(worlds.grounded_world(), seed=seed)
        await story.open()
        await story.act("I shoot Carmine in the back as he plays cards", shoot_carmine())
        deeds = list(story.state.deeds.values())
        if not ev.check("the shooting is a deed", len(deeds) == 1, seed):
            continue
        shot_at = deeds[0].world_s
        ev.check("the bartender saw it", deeds[0].witness_ids == ["bartender"], seed, live=False)
        waited = 0
        while not story.fired(Kind.ANSWER, faction_id="police") and waited < 24:
            waited += 1
            await story.act(
                "I wait at the bar", act("wait at the bar", "wait", ActionKind.WAIT, 5 * MINUTE)
            )
        police = story.fired(Kind.ANSWER, faction_id="police")
        ev.check("the police come", bool(police), f"{seed}: never came")
        reports = story.fired(Kind.REPORT, faction_id="police")
        if not police or not reports:
            continue
        report, arrival = reports[0], police[0]
        ev.check(
            "the call is made within minutes",
            report.applied_s - shot_at <= 3 * MINUTE,
            f"{seed}: {report.applied_s - shot_at}s",
        )
        drive = 12 * MINUTE
        ev.check(
            "they arrive after the drive, not at once",
            arrival.applied_s >= report.applied_s + drive,
            f"{seed}: {arrival.applied_s - report.applied_s}s",
        )
        ev.check("the police come for the shooter", arrival.payload.get("answer") == "arrest", seed)


# --- Idle world (W6, E2, K8) -------------------------------------------------------------------


@scenario(
    "t17.idle-world",
    suite="T17",
    title="Idle world",
    requirements=("W6", "E2", "E3", "K8", "T17"),
    passes_when="Factions and key NPCs have each changed something",
)
async def idle_world(ev: Eval) -> None:
    from engine.state import Activity, FactionStatus, OriginKind, Prominence

    for seed in ev.seeds(3, live=1):
        story = ev.story(worlds.grounded_world(), seed=seed)
        await story.open()
        turns = 0
        while story.state.world_s < 100 * DAY and turns < 12:
            turns += 1
            left = 100 * DAY - story.state.world_s
            await story.act(
                "I idle at the bar and let the days go by",
                act("idle at the bar", "idle", ActionKind.TIME_SKIP, left),
            )
        state = story.state
        ev.check(
            "100 idle days pass in a handful of turns",
            state.world_s >= 100 * DAY,
            f"{seed}: {state.world_s / DAY:.1f} days in {turns} turns",
        )
        ticks = [e for e in story.fired(Kind.TICK)]
        ev.check(
            "each turn's catch-up stays bounded (K8)",
            all(
                sum(1 for e in p.fired if e.kind == Kind.TICK) <= MAX_TICKS_PER_PASSAGE * 2
                for p in story.turns
            ),
            f"{seed}: {len(ticks)} ticks",
        )
        movers = {
            f.origin.ref_id
            for f in state.facts.values()
            if f.origin is not None and f.origin.kind is OriginKind.AGENDA
        }
        factions = {
            f.id
            for f in state.factions.values()
            if f.activity is Activity.ACTIVE and f.status is not FactionStatus.DESTROYED
        }
        key_npcs = {
            c.id
            for c in state.npcs()
            if c.alive and c.prominence is Prominence.KEY and c.activity is Activity.ACTIVE
        }
        idle = sorted((factions | key_npcs) - movers)
        ev.check(
            "every active faction and key NPC changed something", not idle, f"{seed}: idle {idle}"
        )
        ev.check(
            "the council met on its own time",
            state.clocks["council"].status is ClockStatus.ENDED,
            seed,
        )


# --- Ignored hook (E2, N5) ---------------------------------------------------------------------


@scenario(
    "t17.ignored-hook",
    suite="T17",
    title="Ignored hook",
    requirements=("E2", "N5", "W6", "T17"),
    passes_when="The hook's clock advances and resolves without the player (the exam happens)",
)
async def ignored_hook(ev: Eval) -> None:
    for seed in ev.seeds(3, live=1):
        story = ev.story(worlds.cultivation_world(), seed=seed)
        await story.open()
        for _ in range(20):
            await story.act(
                "I cultivate in seclusion and ignore the tournament",
                act("cultivate in seclusion", "cultivate", ActionKind.WORK, 3 * HOUR),
            )
        clock = story.state.clocks["tournament"]
        ev.check(
            "the tournament's clock ran out without the player",
            clock.status is ClockStatus.ENDED and clock.filled == len(clock.steps),
            f"{seed}: {clock.status} {clock.filled}",
        )
        thread = story.state.threads["tournament"]
        ev.check(
            "its thread resolved without the player",
            thread.status is ThreadStatus.RESOLVED_WITHOUT_PLAYER,
            f"{seed}: {thread.status}",
        )
        ev.check(
            "word of it goes round",
            any("tournament" in r.text.lower() for r in story.state.rumors.values()),
            seed,
        )
        await ev.judge(
            "the tournament happens without him",
            Rubric(must=("A scene lets the player learn that the tournament went ahead",)),
            story.turns[-8:],
        )


# --- Trapped (W10, A3) -------------------------------------------------------------------------


@scenario(
    "t17.trapped",
    suite="T17",
    title="Trapped",
    requirements=("W10", "A3", "W6", "T17"),
    passes_when=(
        "Escape times vary with the roll, from minutes to days, and the world moves on by that time"
    ),
)
async def trapped(ev: Eval) -> None:
    durations = []
    for seed in ev.seeds(60, live=2):
        story = ev.story(worlds.cultivation_world(), seed=seed)
        await story.open()

        def caught(state) -> None:
            state.characters["lin"].sheet.condition.states.append(
                PassingState(name="caught in a binding array")
            )
            state.scene.ended_on = (
                "The binding array flares under Lin's feet and locks him in place."
            )

        story.change(caught)
        start = story.state.world_s
        tournament_before = story.state.clocks["tournament"].filled
        played = await story.act(
            "I work at the array's seams until I break free",
            plan(
                step(
                    "break out of the binding array",
                    ActionKind.TASK,
                    6 * HOUR,
                    verb="escape",
                    duration_uncertain=True,
                )
            ),
        )
        took = played.step(0).duration_s
        durations.append(took)
        roll = played.step(0).roll
        ev.check(
            "the escape time is rolled",
            # Days in the array may be cut short by something that needs them (E7).
            roll is not None and (roll.duration_s == took or played.step(0).interrupted),
            seed,
        )
        lived = story.state.world_s - start
        ev.check(
            "the clock moves by the time it took, unless something cut it short",
            lived == took or played.step(0).interrupted,
            f"{seed}: {lived} vs {took}",
        )
        if took > 2 * DAY:
            ev.check(
                "the world moved on meanwhile",
                story.state.clocks["tournament"].filled > tournament_before,
                seed,
                live=False,
            )
    if not ev.live:
        ev.metric("escape_s_min", min(durations))
        ev.metric("escape_s_max", max(durations))
    ev.check(
        "escapes range from minutes to days",
        bool(durations) and min(durations) < HOUR and max(durations) > DAY,
        f"{min(durations, default=0)}s to {max(durations, default=0)}s",
        live=False,
    )


# --- Logic over dice (A2, A5) ------------------------------------------------------------------


def killed(played: Played, character_id: str) -> bool:
    return played.state.characters[character_id].status is CharacterStatus.DEAD


def no_roll(played: Played, index: int = -1) -> bool:
    return played.step(index).roll is None


@scenario(
    "t17.logic-over-dice",
    suite="T17",
    title="Logic over dice",
    requirements=("A2", "A5", "W10a", "T17"),
    passes_when=(
        "The first two succeed every time and the dragon is never hurt, with no roll recorded "
        "and the reason in the scene details (A2, A5)"
    ),
)
async def logic_over_dice(ev: Eval) -> None:
    for difficulty in Difficulty:
        settings = StorySettings(difficulty=difficulty)
        for seed in ev.seeds(20, live=1 if difficulty is Difficulty.BALANCED else 0):
            # The interpret step forgot the guard was asleep; his sheet says so.
            story = ev.story(
                worlds.naples_with_sleeping_guard(),
                seed=f"{seed}/{difficulty}/guard",
                settings=settings,
                under_way=True,
            )
            played = await story.act(
                "I cut the sleeping guard's throat",
                plan(cut_throat("guard", "knife", facts=facts(can_respond=True))),
            )
            settled = played.step(0)
            where = f"{seed} on {difficulty}: {settled.outcome_class} {settled.reason}"
            ev.check("the sleeping guard dies every time", killed(played, "guard"), where)
            ev.check(
                "the guard's death is certain, with no roll",
                settled.outcome_class is OutcomeClass.CERTAIN and no_roll(played),
                where,
            )
            ev.check(
                "the reason is in the scene details",
                "asleep" in played.scene.details.steps[0].reason,
                where,
            )

            story = ev.story(
                worlds.with_troll(worlds.sect()),
                seed=f"{seed}/{difficulty}/troll",
                settings=settings,
                under_way=True,
            )
            played = await story.act(
                "I stop time and cut the troll's throat",
                plan(stop_time(), cut_throat("troll", "sword", proposed_personal_s=2)),
            )
            kill = played.step(-1)
            where = f"{seed} on {difficulty}: {kill.outcome_class} {kill.reason}"
            ev.check("the frozen troll dies every time", killed(played, "troll"), where)
            ev.check(
                "the troll's death is certain, with no roll",
                kill.outcome_class is OutcomeClass.CERTAIN and kill.roll is None,
                where,
            )
            ev.check(
                "the world stood still while it happened (W10a)",
                (kill.duration_s, kill.personal_s) == (0, 2),
                where,
            )
            ev.check("the reason is in the scene details", "stopped time" in kill.reason, where)

            story = ev.story(
                worlds.with_dragon(worlds.sect()),
                seed=f"{seed}/{difficulty}/dragon",
                settings=settings,
                under_way=True,
            )
            # However generous the interpret step was about the knife, the dragon's body decides.
            played = await story.act(
                "I stab the sleeping ancient dragon with my kitchen knife",
                plan(
                    cut_throat(
                        "dragon",
                        "kitchen-knife",
                        axis=PowerAxis.MIGHT,
                        facts=facts(
                            can_respond=False, why_not="asleep", means=MeansVerdict.CLEARLY_ENOUGH
                        ),
                    )
                ),
            )
            stab = played.step(0)
            where = f"{seed} on {difficulty}: {stab.outcome_class} {stab.reason}"
            ev.check(
                "the dragon is never hurt",
                stab.outcome_class is OutcomeClass.RULED_OUT
                and stab.effects.empty
                and played.state.characters["dragon"].alive,
                where,
            )
            ev.check("the dragon's case has no roll", stab.roll is None, where)
            ev.check(
                "the reason is in the scene details",
                "harm from that far below can't get through"
                in played.scene.details.steps[0].reason,
                where,
            )
    if ev.live:
        await ev.judge(
            "outcomes told as decided",
            Rubric(
                must=(
                    "The sleeping guard dies, the frozen troll dies, and the dragon is not hurt, "
                    "as the engine decided",
                ),
                must_not=("Turns any of the three into a struggle or a lucky break",),
            ),
            [(s.label or s.seed, s.last) for s in ev.stories[-3:]],
        )


# --- Power gap and fair long shots (A2, A3, A5, A8, G18) ---------------------------------------


def elder_here(state) -> None:
    elder = state.characters["elder-mo"]
    elder.location_id = "well"
    state.scene.present_ids.append("elder-mo")


def strike_at(target: str, **kw) -> Intent:
    return plan(
        attack(target, "sword", text=f"cut down {target}", **kw),
    )


@scenario(
    "t17.power-gap",
    suite="T17",
    title="Power gap",
    requirements=("G18", "A8", "A2", "W1", "T17"),
    passes_when=(
        "Two realms up it is still a throw, and it fails almost every time; the elder reacts "
        "to the insult. Against a gravely wounded elder, the same attack succeeds more often "
        "(G18, A8). Using time stop, the result is the same on every seed, with no roll"
    ),
)
async def power_gap(ev: Eval) -> None:
    head_on = Counter()
    for seed in ev.seeds(300, live=2):
        story = ev.story(worlds.sect(), seed=f"{seed}/head-on", under_way=True)
        story.change(elder_here)
        before = story.state.characters["elder-mo"].sheet.disposition.attitudes.get("lin")
        played = await story.act("I attack Elder Mo head-on with my sword", strike_at("elder-mo"))
        settled = played.step(0)
        head_on[settled.result] += 1
        where = f"{seed}: {settled.outcome_class} {settled.reason}"
        # A gap never removes the throw (A3): two rungs raise the number by a level each.
        thrown = settled.roll.throw if settled.roll is not None else None
        ev.check(
            "a head-on attack two realms up is still a throw, and a long shot",
            settled.outcome_class is OutcomeClass.LONG_SHOT
            and thrown is not None
            and any(
                part.points == 20 and part.text.startswith("two rungs above you")
                for part in thrown.made_of
            ),
            where,
        )
        deeds = [
            d for d in played.state.deeds.values() if "elder-mo" in [*d.target_ids, *d.victim_ids]
        ]
        ev.check("the attempt is a deed against the elder", bool(deeds), where)
        elder = played.state.characters["elder-mo"]
        after = elder.sheet.disposition.attitudes.get("lin")
        ev.check(
            "the elder reacts to the insult",
            not elder.alive
            or (after is not None and (before is None or after.affinity < before.affinity)),
            f"{seed}: {before} -> {after}",
        )
        if settled.result is StepResult.FAILURE:
            await ev.judge(
                "the insult and the elder's answer",
                Rubric(
                    must=(
                        "The attack fails against the elder's strength",
                        "The elder reacts to it",
                    ),
                    must_not=("The disciple wounds the elder",),
                ),
                played,
            )
    tried = sum(head_on.values())
    if not ev.live:
        ev.metric("head_on_win_rate", round(head_on[StepResult.SUCCESS] / tried, 3))
        ev.check(
            "two realms up it fails almost every time, and not every time",
            0 < head_on[StepResult.SUCCESS] < 0.15 * tried,
            str(dict(head_on)),
        )

    wins = total = 0
    for seed in ev.seeds(300, live=0):
        story = ev.story(worlds.sect(), seed=f"{seed}/wounded", under_way=True)

        def gravely_wounded(state) -> None:
            elder_here(state)
            state.characters["elder-mo"].sheet.condition.health = Health.BADLY_WOUNDED

        story.change(gravely_wounded)
        played = await story.act(
            "I attack the wounded Elder Mo with my sword", strike_at("elder-mo")
        )
        settled = played.step(0)
        total += 1
        wins += killed(played, "elder-mo")
        thrown = settled.roll.throw if settled.roll is not None else None
        ev.check(
            "against a gravely wounded elder his wound takes 10 off the number (A8)",
            thrown is not None
            and any(
                part.points == -10 and part.text.endswith("is badly wounded")
                for part in thrown.made_of
            ),
            f"{seed}: {settled.outcome_class} {settled.reason}",
            live=False,
        )
    if total:
        ev.metric("wounded_elder_win_rate", round(wins / total, 3))
        ev.check(
            "the wounded elder falls more often than the unhurt one, and still not often",
            head_on[StepResult.SUCCESS] / tried < wins / total < 0.5,
            f"{wins} of {total} against {head_on[StepResult.SUCCESS]} of {tried}",
            live=False,
        )

    outcomes = set()
    for seed in ev.seeds(30, live=1):
        story = ev.story(worlds.sect(), seed=f"{seed}/time-stop", under_way=True)
        story.change(elder_here)
        played = await story.act(
            "I stop time and strike Elder Mo",
            plan(stop_time(), attack("elder-mo", "sword", proposed_personal_s=2)),
        )
        strike = played.step(-1)
        outcomes.add((strike.outcome_class, strike.result, strike.roll is None))
        ev.check(
            "in stopped time there is no roll",
            strike.roll is None and strike.outcome_class is not OutcomeClass.CONTESTED,
            f"{seed}: {strike.outcome_class} {strike.reason}",
        )
    ev.check(
        "in stopped time it ends the same on every seed",
        len(outcomes) == 1,
        str(outcomes),
        live=False,
    )


@scenario(
    "t17.fair-long-shots",
    suite="T17",
    title="Fair long shots",
    requirements=("A2", "A3", "A5", "T17"),
    passes_when="It succeeds at roughly its stated odds (A2)",
)
async def fair_long_shots(ev: Eval) -> None:
    results = []
    for seed in ev.seeds(400, live=3):
        story = ev.story(worlds.sect(), seed=seed, under_way=True)
        played = await story.act("I attack Zhao Kun with my sword", strike_at("zhao"))
        settled = played.step(0)
        ev.check(
            "one realm up is a rolled long shot",
            settled.outcome_class is OutcomeClass.LONG_SHOT and settled.roll is not None,
            f"{seed}: {settled.outcome_class}",
        )
        if settled.roll is not None:
            results.append((settled.roll.odds, settled.result is StepResult.SUCCESS))
    if ev.live or not results:
        return
    stated = {odds for odds, _ in results}
    ev.check("the odds come from the facts, not the seed", len(stated) == 1, str(sorted(stated)))
    odds = results[0][0]
    rate = sum(won for _, won in results) / len(results)
    margin = 4 * math.sqrt(odds * (1 - odds) / len(results))
    ev.metric("stated_odds", round(odds, 3))
    ev.metric("success_rate", round(rate, 3))
    ev.check(
        "it succeeds at its stated odds",
        abs(rate - odds) <= margin,
        f"{rate:.3f} against {odds:.3f} (within {margin:.3f})",
    )
    # A5: the difficulty moves the odds of a rolled step.
    by_difficulty = {}
    for difficulty in Difficulty:
        story = ev.story(
            worlds.sect(),
            seed=f"odds/{difficulty}",
            settings=StorySettings(difficulty=difficulty),
            under_way=True,
        )
        played = await story.act("I attack Zhao Kun with my sword", strike_at("zhao"))
        by_difficulty[difficulty.value] = played.step(0).roll.odds
    ev.check(
        "the difficulty shifts a long shot's odds",
        by_difficulty["story"] > by_difficulty["balanced"] > by_difficulty["brutal"],
        str(by_difficulty),
    )


# --- A friendly bout (W1, W4, N6) ----------------------------------------------------------------

LESSON_BLOWS = 24


def lesson_begins(state) -> None:
    """Elder Mo, who is fond of Lin, has agreed to test him at the well, and Lin holds the
    practice sword he was tossed: what the last scene told is on record. In the second live
    lessons (2026-11-11) it wasn't, so a first blow with that sword was stopped before it was
    tried and the lesson went on as an open fight."""
    elder_here(state)
    state.characters["elder-mo"].sheet.disposition.attitudes["lin"] = Attitude(affinity=20)
    sword = worlds.Item(
        id="practice-sword", name="wooden practice sword", kind=worlds.ItemKind.WEAPON
    )
    worlds.give(state, "lin", sword)
    state.scene.ended_on = (
        "Elder Mo tosses Lin a wooden practice sword. 'Come at me, boy. Touches only. Show me "
        "what the outer court has taught you.'"
    )


# The shapes an interpret step gives a practice blow: its verb, what it aims to do, and whether it
# names the elder as its target or leaves him as what stands in its way. The first live lesson
# (2026-11-11) had one read as an attack that aims no harm and names no target, and it was filed
# as an attack on him.
BLOW_SHAPES = [
    ("strike", Aim.SUBDUE, True),
    ("attack", Aim.NONE, False),
    ("strike", Aim.WOUND, True),
    ("attack", Aim.NONE, True),
    ("strike", Aim.KILL, True),
    ("lunge", Aim.NONE, False),
    ("swing", Aim.WOUND, False),
]


def lesson_blow(n: int, shape: int = 0) -> Intent:
    """A blow of the lesson as the interpret step might read it: the terms at the start and
    only now and then after it, in any shape at all, with any guess at what the elder means in
    answer. `shape` is the shape of the first blow, so over the seeds a lesson begins with
    each. One lesson in three begins with a blow that never comes off, made with a staff Lin
    doesn't hold: the agreement to spar stands all the same."""
    told = facts(
        opposition_ids=["elder-mo"],
        can_respond=True,
        terms=Terms.NO_HARM if n % 5 == 0 else None,
        foes_mean=(None, Aim.SUBDUE, Aim.WOUND, Aim.KILL)[n % 4],
    )
    verb, aim, named = BLOW_SHAPES[(n + shape) % len(BLOW_SHAPES)]
    return plan(
        step(
            "strike at Elder Mo with the practice sword",
            verb=verb,
            aim=aim,
            target_ids=["elder-mo"] if named else [],
            axis=PowerAxis.MIGHT,
            uses=[item("bamboo staff")] if n == 0 and never_comes_off(shape) else [],
            facts=told,
        )
    )


def never_comes_off(shape: int) -> bool:
    """Whether a scripted lesson begins with a blow that is stopped before it is tried."""
    return shape % 3 == 2


REASON_CHARS = 90  # of a ruled-out step's reason, in a failed check's detail
ENDING_CHARS = 200  # of how the scene before a misread turn ended, in a failed check's detail


def as_read(turns: list[Played]) -> str:
    """How each step of some turns was read and what code made of it, for the detail of a
    failed check: a live run's log is all that can be read of it afterwards (T18). The story
    is the eval's own, so nothing of a player's is shown (T16)."""
    lines = []
    for played in turns:
        if played.result is None:
            lines.append(f"t{played.turn} refused")
            continue
        read = played.result.intent.steps if played.result.intent is not None else []
        for settled in played.steps:
            said = "unread"
            if settled.index < len(read):
                step_ = read[settled.index]
                told = step_.facts
                terms = told.terms.value if told.terms is not None else "null"
                said = (
                    f"{step_.verb}/{step_.kind.value}/{step_.aim.value} at={step_.target_ids} "
                    f"in_way={told.opposition_ids} terms={terms}"
                    f"{' beyond' if told.breaks_terms else ''}"
                    f"{' unanswered' if told.can_respond is False else ''}"
                )
            how = f"{settled.outcome_class.value}/{settled.result.value}"
            if settled.outcome_class is OutcomeClass.RULED_OUT:
                how += f" ({settled.reason[:REASON_CHARS]})"  # why it was never tried
            bout = settled.bout.terms.value if settled.bout is not None else "none"
            deeds = [d.kind for d in settled.deeds]
            lines.append(
                f"t{played.turn}.{settled.index} {said} -> {how} bout={bout} deeds={deeds}"
            )
    return " | ".join(lines)


def aimed_at(state, played: Played) -> set[str]:
    """Who a turn was read as aimed at: each step's targets, or when it names none, those who
    stand in its way (`bouts.against`)."""
    intent = played.result.intent if played.result is not None else None
    steps = intent.steps if intent is not None else []
    return {i for s in steps for i in against(state, state.player_id, s)}


def blinding_blow() -> Intent:
    told = facts(
        opposition_ids=["elder-mo"], can_respond=True, breaks_terms=True, foes_mean=Aim.NONE
    )
    text = "drive my fingers at Elder Mo's eyes to blind him"
    return plan(attack("elder-mo", aim=Aim.WOUND, text=text, verb="maim", facts=told))


def unharmed(state, character_id: str) -> bool:
    condition = state.characters[character_id].sheet.condition
    return condition.health is Health.UNHURT and not condition.states and not condition.wounds


@scenario(
    "t17.friendly-bout",
    suite="T17",
    title="A friendly bout",
    requirements=("W1", "W4", "N6", "V3", "T17"),
    passes_when=(
        "A long lesson with a mentor is one bout: nobody is hurt, and it leaves no grudge, fear, "
        'report or revenge. A blow meant to maim "him", with nobody named, is read as aimed '
        "at the mentor and is an attack that he remembers, and a partner who bears the "
        "character ill will can use a friendly bout to hurt them"
    ),
)
async def friendly_bout(ev: Eval) -> None:
    for shape, seed in enumerate(ev.seeds(14, live=3)):
        story = ev.story(worlds.cultivation_world(), seed=seed)
        await story.open()
        story.change(lesson_begins)
        before = story.state.characters["elder-mo"].attitude_toward("lin").model_copy(deep=True)
        lesson = [
            await story.act(
                "I bow, take up the practice sword and come at Elder Mo as he asked",
                lesson_blow(0, shape),
            )
        ]
        for n in range(1, 6 if ev.live else LESSON_BLOWS):
            lesson.append(
                await story.act(
                    "I come at Elder Mo again with the practice sword", lesson_blow(n, shape)
                )
            )
        state = story.state
        blows = [s for played in lesson for s in played.steps]
        read = f"{seed}: {as_read(lesson)}"
        ev.check(
            "the lesson is read as a bout both agreed to",
            any(s.bout is not None and s.bout.terms is Terms.NO_HARM for s in blows),
            read,
        )
        ev.check(
            "every blow of it comes under its terms, however it was read",
            all(s.bout is not None and not s.broke_terms for s in blows),
            read,
            live=False,
        )
        if never_comes_off(shape) and not ev.live:  # live, the model reads the blow itself
            first = blows[0]
            ev.check(
                "a first blow that never came off still agrees the bout",
                first.outcome_class is OutcomeClass.RULED_OUT and first.bout is not None,
                read,
                live=False,
            )
        ev.check(
            "nobody is hurt or left helpless by it",
            unharmed(state, "lin") and unharmed(state, "elder-mo"),
            seed,
        )
        with_elder = [
            d
            for d in state.deeds.values()
            if "elder-mo" in (d.actor_id, *d.victim_ids, *d.target_ids)
        ]
        # A bow to him may be on record beside the bout; nothing that is harm by the world's
        # norms may.
        harm = [d.kind for d in with_elder if deed_nature(state, d) is Nature.HARM]
        ev.check(
            "no blow of it is on record as an attack",
            any(d.is_bout for d in with_elder) and not harm,
            f"{[d.kind for d in with_elder]} from {read}",
        )
        ev.check("the whole lesson is one deed", len(with_elder) == 1, seed, live=False)
        elder = state.characters["elder-mo"].attitude_toward("lin")
        ev.check(
            "the mentor bears no grudge and isn't afraid",
            not elder.grudges and elder.fear <= before.fear,
            f"{elder} from {read}",
        )
        ev.check(
            "he thinks a little better of his student for it",
            elder.affinity > before.affinity and elder.trust > before.trust,
            f"{seed}: {elder}",
            live=False,
        )
        answers = [
            e
            for e in state.pending_events.values()
            if e.kind in (Kind.REPORT, Kind.ANSWER) and e.status is EventStatus.PENDING
        ]
        ev.check("nobody reports it or comes for revenge", not answers, seed)
        ev.check("no word of an attack goes round", not state.rumors, seed, live=False)
        ev.check(
            "the narrator is told the blow was one of a friendly bout",
            '"bout":"no_harm"' in story.prompt(Node.NARRATOR),
            seed,
            live=False,
        )
        await ev.judge(
            "the lesson is told as a lesson",
            Rubric(
                must=(
                    "The scenes tell a sparring lesson between a teacher and his student, with "
                    "practice blows that are pulled, parried or land as touches",
                ),
                # Tiring is no wound: the fourth live lessons (2026-11-11) failed "left unable
                # to go on" for a student worn out by the end of a long lesson.
                must_not=(
                    "A blow of the lesson wounds Lin or Elder Mo, draws blood or knocks one of "
                    "them senseless (being worn out, winded, disarmed or bested is none of these)",
                    "Elder Mo turns hostile, afraid or resentful over a blow of the lesson",
                ),
            ),
            lesson,
        )

        # Beyond the terms: a blow meant to maim, under cover of the lesson. The player names
        # nobody, as players do. In the third live lessons (2026-11-11) two of three read "his
        # eyes" as those of Zhao, who stands by at the well, and the blow fell on him.
        moment = story.state.scene.ended_on
        played = await story.act(
            "While he corrects my stance I drop the sword and drive my fingers at his eyes, "
            "meaning to blind him for good",
            blinding_blow(),
        )
        state = story.state
        at_him = aimed_at(state, played) == {"elder-mo"}
        ev.check(
            "someone meant but not named is the one they are sparring with",
            at_him,
            f"{seed}: {as_read([played])} after a scene that ended: {moment[-ENDING_CHARS:]}",
        )
        if not at_him:
            continue  # the blow went at someone else, so nothing below is about it
        ev.check(
            "a blow meant to maim goes beyond the terms",
            any(s.broke_terms for s in played.steps),
            f"{seed}: {as_read([played])}",
        )
        encounter = state.scene.encounter
        ev.check("the bout is over", encounter is None or encounter.bout is None, seed)
        ev.check(
            "that blow is on record as an attack on him",
            any(
                d.broke_terms and not d.agreed and "elder-mo" in (*d.victim_ids, *d.target_ids)
                for d in state.deeds.values()
            ),
            seed,
        )
        after = state.characters["elder-mo"].attitude_toward("lin")
        ev.check(
            "he remembers it and trusts them less",
            bool(after.grudges) and after.trust < elder.trust,
            f"{seed}: {after}",
        )

    # The other way round: Zhao dislikes Lin, so his "friendly" bout can be a lure.
    for seed in ev.seeds(12, live=0):
        story = ev.story(worlds.cultivation_world(), seed=f"{seed}/lure", under_way=True)
        offer = facts(
            opposition_ids=["zhao"], can_respond=True, terms=Terms.NO_HARM, foes_mean=Aim.SUBDUE
        )
        played = await story.act(
            "I take Zhao up on his friendly bout and trade blows with him",
            plan(attack("zhao", aim=Aim.SUBDUE, text="trade blows with Zhao", facts=offer)),
        )
        ev.check("his offer starts a bout", played.step(0).bout is not None, seed)
        played = await story.act(
            "I circle him, looking for an opening",
            plan(step("circle Zhao, looking for an opening", facts=facts(foes_mean=Aim.WOUND))),
        )
        ev.check(
            "a partner who bears them ill will can go beyond the terms",
            played.step(0).broke_terms and played.step(0).bout is None,
            seed,
        )
        ev.check(
            "his blow is on record as his attack",
            any(d.actor_id == "zhao" and d.broke_terms for d in story.state.deeds.values()),
            seed,
        )


# --- Before a crowd, and who could know (W2, W4, W11, C6) --------------------------------------

IN_FRONT_OF_EVERYONE = (
    "In the middle of the crowded queue at the well, in front of everyone, I draw my sword and "
    "cut Han Jie's throat while he dozes"
)


def in_front_of_everyone() -> Intent:
    """The killing as the interpret step reads it: Han is asleep, and people the scene doesn't
    name are all around."""
    told = facts(opposition_ids=["han"], can_respond=False, why_not="asleep", crowd=True)
    return plan(cut_throat("han", "sword", facts=told))


def brother_hates_him_already() -> dict:
    """A narrator that has the dead man's brother, who is in the inner court, hate Lin on the
    spot."""
    grief = AttitudeShift(affinity=-10, grudge="Lin Feng murdered his brother at the well")
    update = StateDelta(characters=[CharacterChange(id="han-lei", attitudes=[grief])])
    return {
        "narration": "(scripted) Han Jie falls, and the queue breaks apart, screaming.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


@scenario(
    "t17.before-a-crowd",
    suite="T17",
    title="Before a crowd",
    requirements=("W2", "W4", "W11", "C6", "T17"),
    passes_when=(
        "A killing before a crowd is public: someone of the crowd saw it and goes to those who "
        "keep the law, and word of it starts at once. The dead man's brother, who was "
        "elsewhere, feels nothing about it until word reaches him, whatever the scene says, "
        "and the player character has heard no talk of it that no scene told"
    ),
)
async def before_a_crowd(ev: Eval) -> None:
    for seed in ev.seeds(6, live=1):
        # Under way, so the scene is the one the world holds: an opening told live could wake
        # him or turn him round, and the first live story (2026-11-11) rolled for the blow.
        story = ev.story(worlds.noon_at_the_well(), seed=seed, under_way=True)
        before = story.state.characters["han-lei"].attitude_toward("lin").model_copy(deep=True)
        killing = await story.act(
            IN_FRONT_OF_EVERYONE,
            in_front_of_everyone(),
            narration=None if ev.live else brother_hates_him_already(),
        )
        state = killing.state
        read = f"{seed}: {as_read([killing])}"
        ev.check("the killing lands", state.characters["han"].status is CharacterStatus.DEAD, read)
        deeds = [d for d in state.deeds.values() if "han" in d.victim_ids]
        ev.check(
            "it is one deed, done before a crowd: public",
            [d.visibility for d in deeds] == [Visibility.PUBLIC],
            f"{[(d.kind, d.visibility.value) for d in deeds]} from {read}",
        )
        if len(deeds) != 1:
            continue
        deed = deeds[0]
        made = killing.steps[0].strangers if killing.steps else []
        ev.check("someone of the crowd saw it", bool(deed.witness_ids), read)
        ev.check(
            "the witness is one of the crowd, made real by the deed",
            bool(made) and deed.witness_ids == made,
            f"{seed}: saw {deed.witness_ids}, made {made}",
            live=False,
        )
        ev.check(
            "word of it starts at once, told as it happened",
            any(r.deed_id == deed.id and r.accuracy == 100 for r in state.rumors.values()),
            seed,
        )
        reports = [
            e
            for e in state.pending_events.values()
            if e.kind == Kind.REPORT and e.payload.get("witness_id") in deed.witness_ids
        ]
        ev.check(
            "someone of the crowd goes to those who keep the law",
            {r.payload["faction_id"] for r in reports} >= {"azure-cloud"},
            f"{seed}: {[r.payload for r in reports]}",
        )
        brother = state.characters["han-lei"].attitude_toward("lin")
        ev.check(
            "his brother, who was elsewhere, feels as he did",
            brother == before,
            f"{seed}: {brother}",
        )
        ev.check(
            "the scene's word that he hates Lin already is refused",
            "rejected" in killing.issues,
            f"{seed}: {killing.issues}",
            live=False,
        )
        ev.check(
            "Lin has heard no talk of it that no scene told",
            not memory_view(state).rumors,
            seed,
            live=False,
        )
        await ev.judge(
            "the killing is told as done in front of a crowd",
            Rubric(
                must=("People in the crowd see the killing and react to it",),
                must_not=(
                    "Nobody notices the killing, or the well is told as empty",
                    "Han Lei, his brother, is in the scene or learns of it in the scene",
                ),
            ),
            [killing],
        )

        # Word travels at the pace people do: by the time it reaches the inner court, he knows.
        for _ in range(3):
            await story.act(
                "I slip away into the pines above the court and wait there for an hour",
                act("hide in the pines for an hour", "hide", ActionKind.TASK, HOUR),
            )
        brother = story.state.characters["han-lei"].attitude_toward("lin")
        ev.check(
            "once word reaches him, he holds it against Lin",
            bool(brother.grudges) and brother.affinity < before.affinity,
            f"{seed}: {brother}",
            live=False,
        )


# --- Cause and effect (A2, A9) -----------------------------------------------------------------


def fire_bazooka(target: str, means: MeansVerdict) -> Intent:
    return plan(
        step(
            f"fire the bazooka at {target}",
            verb="shoot",
            aim=Aim.KILL,
            target_ids=[target],
            axis=PowerAxis.MIGHT,
            uses=[item("bazooka")],
            facts=facts(
                opposition_ids=[target],
                can_respond=False,
                why_not="too close to dodge a rocket",
                means=means,
            ),
        )
    )


@scenario(
    "t17.cause-and-effect",
    suite="T17",
    title="Cause and effect",
    requirements=("A2", "A9", "T17"),
    passes_when=(
        "The thug dies and the strong field holds on every seed, with no roll. Only the evenly "
        "matched field is a close call, rolled between outcomes the facts allow (A2, A9)"
    ),
)
async def cause_and_effect(ev: Eval) -> None:
    close: set[StepResult] = set()
    for seed in ev.seeds(40, live=1):
        story = ev.story(worlds.hidden_city(), seed=seed, under_way=True)
        thug = await story.act(
            "I fire the bazooka at Rocco", fire_bazooka("thug", MeansVerdict.CLEARLY_ENOUGH)
        )
        ev.check(
            "the unshielded thug dies, with no roll",
            killed(thug, "thug") and no_roll(thug),
            f"{seed}: {thug.step(0).outcome_class}",
        )
        vesna = await story.act(
            "I fire the bazooka at Vesna", fire_bazooka("vesna", MeansVerdict.CLEARLY_ENOUGH)
        )
        settled = vesna.step(0)
        ev.check(
            "the strong field holds, with no roll",
            settled.outcome_class is OutcomeClass.RULED_OUT
            and settled.effects.empty
            and no_roll(vesna),
            f"{seed}: {settled.outcome_class} {settled.reason}",
        )
        ilya = await story.act(
            "I fire the bazooka at Ilya", fire_bazooka("ilya", MeansVerdict.CLEARLY_ENOUGH)
        )
        settled = ilya.step(0)
        ev.check(
            "the evenly matched field is a rolled close call",
            settled.outcome_class is OutcomeClass.CONTESTED and settled.roll is not None,
            f"{seed}: {settled.outcome_class}",
        )
        close.add(settled.result)
        await ev.judge(
            "cause and effect told plainly",
            Rubric(
                must=(
                    "Rocco dies from the rocket",
                    "Vesna's field holds against the rocket",
                    "Ilya's field and the rocket are a close match, told as the engine decided",
                ),
            ),
            story.turns,
        )
    ev.check(
        "the close call goes both ways between outcomes the facts allow",
        close == {StepResult.SUCCESS, StepResult.PARTIAL},
        str(sorted(close)),
        live=False,
    )


# --- Workaround (A9, G18, W10) -----------------------------------------------------------------


def burn_the_hall() -> Intent:
    from engine.contracts import Beat, BeatUse, ChainLink, UseSource

    return plan(
        step(
            "soak the hall in oil and set it alight",
            ActionKind.TASK,
            10 * MINUTE,
            verb="burn",
            aim=Aim.KILL,
            target_ids=["su-yan"],
            beats=[
                Beat(
                    text="splash oil along the walls",
                    uses=[BeatUse(source=UseSource.CARRIED, thing="lamp oil", ref="oil")],
                ),
                Beat(
                    text="strike a light",
                    uses=[BeatUse(source=UseSource.NEW, thing="a flint", plausibility="plausible")],
                ),
            ],
            chain=[
                ChainLink(
                    text="Oil and fire fill the hall around her field.",
                    rests_on=["oil"],
                    takes_s=2 * MINUTE,
                ),
                ChainLink(text="Her field keeps out air as well as flames.", rests_on=["su-field"]),
                ChainLink(
                    text="The air inside the field runs out within minutes.",
                    rests_on=["su-field", "no-exit"],
                    takes_s=4 * MINUTE,
                ),
                ChainLink(
                    text="Dropping the field lets in flames and smoke with no air: she dies.",
                    answers=["teleport", "breathe without air", "put out the fire"],
                ),
            ],
            facts=facts(
                opposition_ids=["su-yan"],
                can_respond=False,
                why_not="deep in meditation behind her field",
            ),
        )
    )


@scenario(
    "t17.workaround",
    suite="T17",
    title="Workaround",
    requirements=("A9", "G18", "W10", "W1", "T17"),
    passes_when=(
        "With no way out, she dies on every seed once the air runs out, minutes of in-world time "
        "later, with no roll and the chain in the scene details. With the teleport, she escapes "
        "and hunts for whoever tried. A head-on attack on her stays ruled out"
    ),
)
async def workaround(ev: Eval) -> None:
    for seed in ev.seeds(30, live=1):
        story = ev.story(worlds.shielded_mage(), seed=f"{seed}/trapped", under_way=True)
        played = await story.act(
            "I soak the meditation hall in lamp oil and set it alight from outside", burn_the_hall()
        )
        settled = played.step(0)
        where = f"{seed}: {settled.outcome_class} {settled.reason}"
        ev.check(
            "with no way out she dies, with no roll",
            killed(played, "su-yan") and settled.roll is None,
            where,
        )
        ev.check(
            "she dies once the air runs out, minutes later",
            settled.duration_s == 16 * MINUTE,
            f"{seed}: {settled.duration_s}s",
            live=False,
        )
        chain = played.scene.details.steps[0].model_dump(mode="json")
        ev.check(
            "the chain is in the scene details",
            bool(played.scene.details.chain) or bool(settled.chain),
            str(chain)[:200],
        )

        story = ev.story(
            worlds.shielded_mage(teleport=True), seed=f"{seed}/teleport", under_way=True
        )
        played = await story.act(
            "I soak the meditation hall in lamp oil and set it alight from outside", burn_the_hall()
        )
        settled = played.step(0)
        ev.check(
            "with a teleport she escapes, with no roll",
            settled.outcome_class is OutcomeClass.RULED_OUT
            and played.state.characters["su-yan"].alive
            and settled.roll is None,
            f"{seed}: {settled.outcome_class} {settled.reason}",
        )
        ev.check(
            "the attempt is a deed against her",
            any("su-yan" in d.target_ids for d in played.state.deeds.values()),
            seed,
        )
        head_on = await story.act("I attack Su Yan head-on", strike_at("su-yan"))
        ev.check(
            "a head-on attack on her stays ruled out",
            head_on.step(0).outcome_class is OutcomeClass.RULED_OUT and no_roll(head_on),
            f"{seed}: {head_on.step(0).reason}",
        )


# --- Secret holds (C6, S5) ---------------------------------------------------------------------


@scenario(
    "t17.secret-holds",
    suite="T17",
    title="Secret holds",
    requirements=("C6", "S5", "W4", "T17"),
    passes_when=(
        "The betrayal isn't visible on the Memory screen or through `/thoughts` before it happens"
    ),
    notes=(
        "Carmine, the grounded world's underboss, ordered the killing and acts warm. `/thoughts` "
        "(S5) doesn't exist yet, so only the Memory screen is checked until it does."
    ),
)
async def secret_holds(ev: Eval) -> None:
    from engine.visibility import attitude_label, memory_view

    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.grounded_world(), seed=seed)
        await story.open()
        lines = [
            (
                "I drink with Carmine and ask about my father",
                "drink with Carmine",
                ActionKind.CONVERSATION,
            ),
            ("I watch who comes and goes at the bar", "watch the bar", ActionKind.OBSERVE),
            (
                "I ask Gennaro who was here the night my father died",
                "ask Gennaro",
                ActionKind.CONVERSATION,
            ),
        ]
        for n in range(24):
            words, text, kind = lines[n % len(lines)]
            played = await story.act(words, act(text, text.split()[0], kind, 30 * MINUTE))
            view = memory_view(played.state).model_dump(mode="json")
            dumped = str(view).lower()
            ev.check(
                "the Memory screen never shows the secret",
                "ordered the killing" not in dumped
                and "carmine russo, the underboss" not in dumped,
                f"{seed} turn {played.turn}",
            )
            carmine = next((p for p in view["people"] if p["id"] == "carmine"), None)
            ev.check(
                "the Memory screen shows the warmth he acts, not what he feels",
                carmine is not None and carmine["attitude_label"] == attitude_label(40),
                f"{seed} turn {played.turn}: {carmine and carmine['attitude_label']}",
                live=False,
            )
        await ev.judge(
            "the traitor stays hidden",
            Rubric(
                must_not=(
                    "Reveals or states outright that Carmine ordered the killing",
                    "Shows Carmine's private thoughts or hatred of Luca",
                ),
            ),
            story.turns,
        )


# --- Grounded world (G7, G8) -------------------------------------------------------------------


@scenario(
    "t17.grounded-world",
    suite="T17",
    title="Grounded world",
    requirements=("G7", "G8", "N4", "C1", "T17"),
    passes_when=(
        "Nothing supernatural happens, the people present react to the gesture, the scene "
        "details give the reason, and nothing fantastic (magic, levels, monsters) appears in 50 "
        "turns (G7, G8)"
    ),
)
async def grounded_world(ev: Eval) -> None:
    from engine.contracts import (
        BeatUse,
        CharacterChange,
        PastClaim,
        RuleChange,
        StateDelta,
        UseSource,
    )
    from engine.state import Cause, CauseMechanism, CauseRef, Gain

    for seed in ev.seeds(3, live=1):
        story = ev.story(worlds.grounded_world(), seed=seed, rating=Rating.MATURE)
        await story.open()
        fireball = plan(
            step(
                "throw a fireball at Carmine",
                verb="cast",
                aim=Aim.KILL,
                target_ids=["carmine"],
                uses=[power("fireball")],
                beats=[
                    Beat(
                        text="gather fire in his palm",
                        uses=[BeatUse(source=UseSource.POWER, thing="a fireball", ref="fireball")],
                    )
                ],
                facts=facts(opposition_ids=["carmine"], can_respond=True, world_allows=False),
            ),
            # The interpret step reads the claim for what it is: a power the grounded world's
            # fixed rule doesn't allow (N4, G7).
            backstory=[
                PastClaim(
                    text="Luca has secretly been a wizard all his life.",
                    grants_power=True,
                    against_rule_ids=["no-supernatural"],
                )
            ],
        )
        # The narrator tries to make it magic anyway: a power, a rule change, a wizard's past.
        magic = StateDelta(
            characters=[
                CharacterChange(
                    id="luca",
                    gains=[
                        Gain(
                            what="fireball",
                            change="Luca can throw fire.",
                            source="the narrator",
                            reason="he always could",
                        )
                    ],
                    backstory=["Luca is a secret wizard."],
                )
            ],
            rule_changes=[
                RuleChange(
                    rule_id="no-supernatural",
                    text="Magic is real.",
                    cause=Cause(
                        mechanism=CauseMechanism.DISCOVERY,
                        ref_kind=CauseRef.DEED,
                        ref_id="fireball",
                        text="Luca's fireball",
                    ),
                )
            ],
        )
        played = await story.act(
            "I throw a fireball at Carmine. I've always secretly been a wizard.",
            fireball,
            narration={
                "narration": "(scripted) Fire leaps from Luca's hand.",
                "suggestions": [],
                "update": magic.model_dump(mode="json"),
            },
        )
        settled = played.step(0)
        ev.check(
            "nothing supernatural happens",
            settled.result is StepResult.FAILURE
            and played.state.characters["carmine"].alive
            and settled.effects.empty,
            f"{seed}: {settled.outcome_class} {settled.reason}",
        )
        ev.check(
            "the scene details give the reason",
            bool(played.scene.details.steps and played.scene.details.steps[0].reason),
            seed,
        )
        state = played.state
        rule = next(r for r in state.bible.rules if r.id == "no-supernatural")
        ev.check(
            "the world stays grounded: the fixed rule holds",
            rule.text.startswith("Grounded") and not state.characters["luca"].sheet.powers,
            seed,
            live=False,
        )
        claims = played.resolution.claims
        ev.check(
            "the wizard claim is refused and held only as Luca's belief (N4)",
            [c.accepted for c in claims] == [False]
            and any(
                f.kind.value == "belief" and not f.is_true and "wizard" in f.text
                for f in state.facts.values()
            ),
            f"{seed}: {claims}",
            live=False,
        )
        ev.check(
            "the narrator can't make it magic",
            "rejected" in played.issues
            and not any(
                "wizard" in b.text.lower() for b in state.characters["luca"].sheet.backstory
            ),
            f"{seed}: {played.issues}",
            live=False,
        )
        turns = 49 if not ev.live else 9
        for _ in range(turns):
            await story.act(
                "I drink at the bar and watch Carmine",
                act("drink at the bar", "drink", ActionKind.TASK, HOUR),
            )
        ev.check(
            "nothing fantastic appears in the world",
            not any(c.sheet.powers for c in story.state.characters.values())
            and all(e.prevalence.value == "none" for e in story.state.bible.extraordinary),
            seed,
        )
        await ev.judge(
            "the fireball and what follows",
            Rubric(
                must=(
                    "Nothing supernatural happens when Luca tries to throw a fireball",
                    "The people present react to the gesture",
                ),
                must_not=("Magic, monsters, levels or anything fantastic appears in any scene",),
            ),
            story.turns[1:],
            rating=Rating.MATURE,
        )


# --- Divergence (W16, A3) ----------------------------------------------------------------------


@scenario(
    "t17.divergence",
    suite="T17",
    title="Divergence",
    requirements=("W16", "A3", "E4", "W15", "T17"),
    passes_when="The worlds differ in events, threads and new characters",
)
async def divergence(ev: Eval) -> None:
    runs = []
    turns = 15 if ev.live else 50
    for seed in ev.seeds(5, live=2):
        story = ev.story(worlds.grounded_world(), seed=seed)
        await story.open()
        for _ in range(turns):
            await story.act(
                "I drink at the bar", act("drink at the bar", "drink", ActionKind.TASK, 2 * HOUR)
            )
        start = set(worlds.grounded_world().characters)
        runs.append(
            {
                "events": tuple(t.event.title for t in story.turns if t.event is not None),
                "threads": frozenset(t.title for t in story.state.threads.values()),
                "people": frozenset(set(story.state.characters) - start),
            }
        )
    events = [r["events"] for r in runs]
    threads = [r["threads"] for r in runs]
    ev.metric("new_characters", [len(r["people"]) for r in runs])
    ev.check(
        "every run's events differ", len(set(events)) == len(events), str([len(e) for e in events])
    )
    ev.check("the runs' threads differ", len(set(threads)) > 1, live=False)
    if ev.live:
        # The offline narrator brings in nobody, so only live mode can check the new people.
        ev.check(
            "the runs meet different new people",
            len({r["people"] for r in runs}) > 1,
            str([sorted(r["people"]) for r in runs]),
        )


# --- Walk away (N5, E2) ------------------------------------------------------------------------


@scenario(
    "t17.walk-away",
    suite="T17",
    title="Walk away",
    requirements=("N5", "E2", "W6", "W16", "T17"),
    passes_when="The story follows the noodle shop, and the academy threads go on off-screen",
)
async def walk_away(ev: Eval) -> None:
    sect_places = {"well", "inner-court"}
    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.noodle_road(), seed=seed)
        await story.open()
        # Code takes the six hours from the map and leaves Lin in Qinghe (W10). What the road
        # brings may stop him on the way, and then he walks on.
        walk = plan(
            step(
                "walk down the mountain to Qinghe",
                ActionKind.TRAVEL,
                20 * MINUTE,
                verb="travel",
                destination="market-town",
            )
        )
        await story.act("I leave the academy and walk down to Qinghe to open a noodle shop", walk)
        for _ in range(6):
            if story.state.scene.place_id == "market-town":
                break
            await story.act("I walk on to Qinghe", walk)
        events = []
        for _ in range(20):
            played = await story.act(
                "I run the noodle shop",
                act("run the noodle shop", "cook", ActionKind.WORK, 8 * HOUR),
            )
            if played.event is not None:
                events.append(played.event)
        state = story.state
        ev.check("the story stays at the noodle shop", state.scene.place_id == "market-town", seed)
        ev.check(
            "no event drags the player back to the academy",
            all(e.place_id not in sect_places for e in events),
            f"{seed}: {[(e.title, e.place_id) for e in events]}",
        )
        clock = state.clocks["tournament"]
        ev.check(
            "the academy's threads go on off-screen",
            clock.status is ClockStatus.ENDED
            and state.threads["tournament"].status is ThreadStatus.RESOLVED_WITHOUT_PLAYER,
            f"{seed}: {clock.status}",
        )
        await ev.judge(
            "the story follows the noodle shop",
            Rubric(
                must=("The scenes follow Lin's noodle shop and life in Qinghe",),
                must_not=("The story pulls Lin back into academy life against his choice",),
            ),
            story.turns[-6:],
        )


# --- First session (K1, W16, N5) ---------------------------------------------------------------


@scenario(
    "t17.first-session",
    suite="T17",
    title="First session",
    requirements=("K1", "K2", "M7", "W16", "N5", "T17"),
    passes_when="At least one event the player didn't cause arrives before the credit runs out",
    notes=(
        "Deterministic mode prices the real prompts with fixed answer sizes; live mode prices "
        "what the models really used. The pictures the director plans are priced at the "
        "picture model's price: the first story's first pictures on the house while its "
        "allowance lasts (K1, M7), the rest from the credit."
    ),
)
async def first_session(ev: Eval) -> None:
    from decimal import Decimal

    from billing.pricing import bill, charge_cents, house_has_room
    from engine.contracts import FIRST_PICTURES
    from graph.llm import Node
    from graph.llm.config import DEFAULT_NODES
    from graph.llm.pricing import estimate_cost
    from graph.llm.types import Usage
    from lucid.env import Env

    defaults = Env.model_fields
    starter = Decimal(defaults["starter_credit_cents"].default)
    margin = Decimal(defaults["billing_margin"].default)
    allowance = Decimal(defaults["house_pictures_cents"].default)
    model = DEFAULT_NODES[Node.PICTURE].model
    picture = charge_cents(estimate_cost(model, Usage(500, 0), images=1)[0], margin)
    afforded, on_the_house = [], []
    for seed in ev.seeds(6, live=1):
        story = ev.story(
            worlds.cultivation_world(),
            seed=seed,
            premise=(
                "I'm reborn as the weakest outer disciple of the Azure Cloud Sect, with my past "
                "life's memories and the power to stop time."
            ),
        )
        spent = house = Decimal(0)
        turns = free = 0
        arrived = None
        played = await story.open()
        while True:
            spent += bill(played.calls, margin).charge_cents
            if spent > starter:
                break
            turns += 1
            drawn = played.plan.picture if played.completed else None
            if drawn is not None:
                if drawn.trigger in FIRST_PICTURES and house_has_room(house, 0, allowance):
                    house += picture
                    free += 1
                elif spent + picture <= starter:
                    spent += picture
                # Otherwise the picture is skipped and the story goes on (M7).
            if played.event is not None and played.event.source is not EventSource.DUE:
                arrived = arrived or played.turn
            if turns >= 60:
                break
            played = await story.act(
                "I practise my sword forms by the well",
                act("practise sword forms", "practise", ActionKind.TASK, HOUR),
            )
        afforded.append(turns)
        on_the_house.append(free)
        ev.check(
            "an event the player didn't cause arrives before the credit runs out",
            arrived is not None,
            f"{seed}: {turns} turns on the starter credit, no event",
        )
    ev.metric("turns_on_starter_credit", afforded)
    ev.metric("first_pictures_on_the_house", on_the_house)
