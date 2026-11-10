"""T17's openness evals: the world stays open and keeps moving (docs/REQUIREMENTS.md, T17).

Every scenario here plays through the real turn graph. Deterministic mode checks what code
decides (the director, the clock, the world's answers, resolve's classes and rolls) over many
seeds; live mode plays fewer seeds with the real models and adds the judge where the table's
pass condition is about the telling.
"""

from __future__ import annotations

import math
from collections import Counter

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.context import ContentPrefs, Difficulty, EventFrequency, Rating, StorySettings
from engine.contracts import (
    ActionKind,
    Aim,
    Beat,
    EventSource,
    Harm,
    Intent,
    IntentStep,
    MeansVerdict,
    OutcomeClass,
    PictureTrigger,
    Theme,
)
from engine.director import rules
from engine.director.deck import CARDS
from engine.director.goals import lead_thread
from engine.director.montage import montage_steps
from engine.labels import clock_time, second_of_day
from engine.state import (
    CharacterStatus,
    ClockStatus,
    EventStatus,
    GoalStatus,
    Health,
    Mark,
    PassingState,
    PowerAxis,
    StepResult,
    ThreadStatus,
)
from engine.world import Kind
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
                    target_ids=["village"],
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
        ev.check(
            "the escape time is rolled",
            played.step(0).roll is not None and played.step(0).roll.duration_s == took,
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
    from engine.contracts import CharacterChange, SceneEnd, StateDelta

    sect_places = {"well", "inner-court"}
    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.noodle_road(), seed=seed)
        await story.open()
        # The narrator moves Lin and ends the scene in Qinghe, as its instructions ask.
        arrive = StateDelta(
            characters=[CharacterChange(id="lin", location_id="market-town")],
            scene_end=SceneEnd(
                ended_on="Lin sets down his bundle in an empty shopfront in Qinghe.",
                place_id="market-town",
                present_ids=["lin"],
            ),
        )
        await story.act(
            "I leave the academy and walk down to Qinghe to open a noodle shop",
            plan(
                step(
                    "walk down the mountain to Qinghe",
                    ActionKind.TRAVEL,
                    6 * HOUR,
                    verb="travel",
                    target_ids=["market-town"],
                )
            ),
            narration={
                "narration": "(scripted) Lin walks down the mountain road to Qinghe.",
                "suggestions": [],
                "update": arrive.model_dump(mode="json"),
            },
        )
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
