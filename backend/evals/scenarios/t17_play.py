"""T17's play evals: duels, tempers, strong gifts, monsters, races and genres (G5, G9, G15, G18,
G22 to G25), played end to end through the turn graph.

Code decides who wins and how often (A2, G18, G25), what a temper can and can't do to the
player's choice (G15), and what the world remembers (W4). How strangers greet a newcomer from a
people they once fought (G23), and whether each genre feels like itself (G5, G9), is in the
telling, so those are live scenarios scored by the judge.
"""

from __future__ import annotations

from collections import Counter

from engine.base import HOUR, MINUTE
from engine.context import Rating
from engine.contracts import ActionKind, Aim, Intent, OutcomeClass, StandingAction
from engine.state import CharacterStatus, StepResult
from engine.world import Kind
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played
from evals.scenario import LIVE_ONLY, REGISTRY
from evals.scenarios.common import (
    act,
    attack,
    cut_throat,
    facts,
    item,
    plan,
    skill,
    step,
    stop_time,
    technique,
    trait,
)

scenario = REGISTRY.scenario


def dead(played: Played, character_id: str) -> bool:
    return played.state.characters[character_id].status is CharacterStatus.DEAD


# --- Technique duel (G25, G18) -----------------------------------------------------------------


def duel_strike(counter: bool) -> Intent:
    uses = [item("sword"), skill("swordsmanship")]
    if counter:
        uses.append(technique("reed-counter"))
    words = "turn Guo's charge with the Reed-Bending Counter" if counter else "cut at Guo"
    return plan(attack("guo", "sword", aim=Aim.WOUND, text=words, verb="duel", uses=uses))


@scenario(
    "t17.technique-duel",
    suite="T17",
    title="Technique duel",
    requirements=("G25", "G18", "A2", "T17"),
    passes_when=(
        "The counter clearly shifts the odds between equals, and against the stronger foe it "
        "buys an escape at best (G25, G18)"
    ),
    notes=(
        "The engine counts a technique the step draws on as one shift of the odds (G25); the "
        "script draws the counter only where it answers Guo's style."
    ),
)
async def technique_duel(ev: Eval) -> None:
    rates: dict[str, Counter[str]] = {"plain": Counter(), "counter": Counter()}
    for seed in ev.seeds(150, live=2):
        odds = {}
        for kind in ("plain", "counter"):
            story = ev.story(
                worlds.duel(rung=0, counter=True), seed=f"{seed}/{kind}", under_way=True
            )
            played = await story.act(
                "I turn Guo's charge with the Reed-Bending Counter"
                if kind == "counter"
                else "I cut at Guo",
                duel_strike(kind == "counter"),
            )
            cut = played.step(0)
            rates[kind][cut.result.value] += 1
            odds[kind] = cut.roll.odds if cut.roll is not None else None
            ev.check(
                "between equals it is a contest",
                cut.outcome_class is OutcomeClass.CONTESTED and cut.roll is not None,
                f"{seed}: {cut.outcome_class} {cut.reason}",
                live=False,
            )
        ev.check(
            "the counter shifts the odds",
            None not in odds.values() and odds["counter"] >= odds["plain"] + 0.1,
            f"{seed}: {odds}",
            live=False,
        )
    if not ev.live:
        wins = {k: c[StepResult.SUCCESS.value] / max(1, sum(c.values())) for k, c in rates.items()}
        ev.metric("win_rates", wins)
        ev.check(
            "the counter clearly wins more often",
            wins["counter"] >= wins["plain"] + 0.08,
            str(wins),
        )
    escapes: Counter[str] = Counter()
    for seed in ev.seeds(10, live=1):
        story = ev.story(worlds.duel(rung=2, counter=True), seed=f"{seed}/up", under_way=True)
        played = await story.act(
            "I turn the elder's charge with the Reed-Bending Counter", duel_strike(True)
        )
        cut = played.step(0)
        ev.check(
            "against a foe two realms up the counter never wins the fight",
            cut.outcome_class is OutcomeClass.RULED_OUT
            and cut.roll is None
            and not dead(played, "guo"),
            f"{seed}: {cut.outcome_class} {cut.reason}",
        )
        flee = await story.act(
            "I use the counter to slip his charge and run",
            plan(
                step(
                    "slip Guo's charge with the counter and run",
                    ActionKind.MOVE,
                    20,
                    verb="flee",
                    uses=[technique("reed-counter")],
                    facts=facts(opposition_ids=["guo"], can_respond=True),
                )
            ),
        )
        escapes[flee.step(0).outcome_class.value] += 1
        await ev.judge(
            "the counter against a stronger foe",
            Rubric(
                must=("The counter doesn't let Lin beat Guo, who is far stronger",),
                must_not=("Lin wins the fight",),
            ),
            [played, flee],
        )
    # An escape is the best the counter can buy; how often the engine allows one is recorded.
    ev.metric("escape_classes_two_realms_up", dict(escapes))


# --- Temper, not control (G15, G13) ------------------------------------------------------------


def keep_calm(temper: bool) -> Intent:
    return plan(
        step(
            "keep my temper, bow and walk away",
            ActionKind.EXCHANGE,
            10,
            verb="keep calm",
            uses=[trait("hot temper")] if temper else [],
            facts=facts(opposition="Lin's own pride", proposed_class=OutcomeClass.CONTESTED),
        )
    )


@scenario(
    "t17.temper-not-control",
    suite="T17",
    title="Temper, not control",
    requirements=("G15", "G13", "A7", "T17"),
    passes_when=(
        "The character stays calm (the roll may make it harder), and the narrator never makes "
        "the choice for the player (G15)"
    ),
)
async def temper_not_control(ev: Eval) -> None:
    failed = 0
    for seed in ev.seeds(40, live=2):
        odds = {}
        for temper in (False, True):
            story = ev.story(
                worlds.insulted(temper=temper), seed=f"{seed}/{temper}", under_way=True
            )
            played = await story.act("I keep my temper, bow and walk away", keep_calm(temper))
            calm = played.step(0)
            odds[temper] = calm.roll.odds if calm.roll is not None else None
            if temper:
                failed += calm.result is StepResult.FAILURE
                ev.check(
                    "keeping calm is never lost outright",
                    calm.result is not StepResult.FAILURE,
                    f"{seed}: {calm.reason}",
                    live=False,
                )
                ev.check(
                    "whatever the roll, the temper does nothing the player didn't choose",
                    len(played.steps) == 1
                    and calm.effects.empty
                    and not any(d.victim_ids or d.severity >= 2 for d in calm.deeds)
                    and played.state.characters["zhao"].alive,
                    f"{seed}: {calm.result} {calm.deeds}",
                )
                await ev.judge(
                    "the temper held in",
                    Rubric(
                        must=("Lin keeps his temper, bows and walks away, however hard it is",),
                        must_not=(
                            "Lin lashes out, insults Zhao back or attacks him",
                            "The narration decides what Lin does instead of the player",
                        ),
                    ),
                    played,
                )
        ev.check(
            "the temper makes it harder",
            None not in odds.values() and odds[True] < odds[False],
            f"{seed}: {odds}",
            live=False,
        )
    ev.metric("hot_tempered_rolls_failed", failed)


# --- Strong gift (G22) -------------------------------------------------------------------------


def fight_bandit(n: int) -> Intent:
    return plan(stop_time(), cut_throat(f"bandit-{n}", "sword", proposed_personal_s=2))


@scenario(
    "t17.strong-gift",
    suite="T17",
    title="Strong gift",
    requirements=("G22", "W5", "W13", "W16", "T17"),
    passes_when=(
        "The gift wins the fights it should, the world notices and answers it, and at least one "
        "event with stakes can't be solved by fighting (G22)"
    ),
)
async def strong_gift(ev: Eval) -> None:
    turns = 50 if not ev.live else 20
    for seed in ev.seeds(3, live=1):
        story = ev.story(
            worlds.sect(),
            seed=seed,
            premise=(
                "I'm reborn as the weakest outer disciple of the Azure Cloud Sect, with my past "
                "life's memories and the power to stop time."
            ),
        )
        await story.open()
        fights = 0
        for n in range(turns):
            if n % 10 == 5:
                fights += 1
                story.change(lambda s, f=fights: worlds.add(s, worlds.bandit(f)))
                played = await story.act(
                    "I stop time and cut down the bandit who ambushes me", fight_bandit(fights)
                )
                kill = played.step(-1)
                ev.check(
                    "the gift wins the fights it should, with no roll",
                    dead(played, f"bandit-{fights}") and kill.roll is None,
                    f"{seed}: {kill.outcome_class} {kill.reason}",
                )
            else:
                await story.act(
                    "I practise my sword forms by the well",
                    act("practise sword forms", "practise", ActionKind.TASK, 2 * HOUR),
                )
        noticed = [e for e in story.fired() if e.kind in (Kind.DISCOVERY, Kind.RUMOR, Kind.ANSWER)]
        ev.check(
            "the world notices what the gift does",
            any(e.kind == Kind.ANSWER or e.kind == Kind.RUMOR for e in noticed),
            f"{seed}: {Counter(e.kind for e in noticed)}",
        )
        events = [t.event for t in story.turns if t.event is not None]
        ev.check("events with stakes arrive", bool(events), seed)
        await ev.judge(
            "a gift that can't solve everything",
            Rubric(
                must=(
                    "At least one event puts something at stake that killing can't fix: a debt, "
                    "a sickness, a choice, a person to win over",
                    "The world notices the bodies the time stop leaves behind",
                ),
            ),
            [t for t in story.turns if t.event is not None][:8] or story.turns[-5:],
        )


# --- Monster hunt (G24, W4) --------------------------------------------------------------------


@scenario(
    "t17.monster-hunt",
    suite="T17",
    title="Monster hunt",
    requirements=("G24", "W4", "W5", "T17"),
    passes_when="The core is worth what the world says, and the pack remembers (G24)",
)
async def monster_hunt(ev: Eval) -> None:
    remembered = 0
    for seed in ev.seeds(10, live=1):
        story = ev.story(worlds.ashwood(), seed=seed, under_way=True)
        hunt = await story.act(
            "I hunt the lone ash wolf and cut out its fire core",
            plan(
                attack("stray", "sword", text="kill the lone ash wolf"),
                step("cut out its fire core", ActionKind.TASK, 20 * MINUTE, verb="harvest"),
            ),
        )
        chase = hunt.step(0)
        ev.check(
            "the hunt is a fight the roll decides, between equals",
            chase.outcome_class is OutcomeClass.CONTESTED and chase.roll is not None,
            f"{seed}: {chase.outcome_class} {chase.reason}",
        )
        if not dead(hunt, "stray"):
            continue
        home = await story.act(
            "I take the core back to the sect's exchange and sell it",
            act("walk back to the sect and sell the core", "travel", ActionKind.TRAVEL, 3 * HOUR),
        )
        story.change(worlds.days_later(10, back_to="ashwood"))
        again = await story.act(
            "I walk back through the Ashwood",
            act("walk through the Ashwood", "walk", ActionKind.TASK, HOUR),
        )
        pack = [story.state.characters[w] for w in ("alpha", "ash-wolf-2", "ash-wolf-3")]
        grudges = [w for w in pack if w.attitude_toward("lin").grudges]
        answered = story.fired(Kind.ANSWER) + story.fired(Kind.TIDINGS)
        remembered += bool(grudges)
        ev.check(
            "the pack remembers",
            bool(grudges) or bool(answered),
            f"{seed}: grudges {[w.id for w in grudges]}, answers {[e.kind for e in answered]}",
        )
        arrests = story.fired(Kind.ANSWER, answer="arrest")
        ev.check(
            "hunting a beast is no crime",
            not arrests,
            f"{seed}: {[e.title for e in arrests]}",
            gap=(
                "the law and its reports treat a beast like a person: the alpha reports the kill "
                "to the sect, and the Law Enforcement Hall comes to arrest Lin (W11, G24)"
            ),
        )
        await ev.judge(
            "the hunt and the pack",
            Rubric(
                must=(
                    "The fire core is worth about ten silver taels at the sect's exchange, as "
                    "the world says",
                    "When Lin walks back through the Ashwood, the pack remembers him",
                ),
                must_not=("The core is worth a fortune, or nothing",),
            ),
            [hunt, home, again],
        )
    ev.metric("seeds_where_the_pack_holds_a_grudge", remembered)


# --- Race relations (G23) ----------------------------------------------------------------------


@scenario(
    "t17.race-relations",
    suite="T17",
    title="Race relations",
    requirements=("G23", "W4", "T17"),
    passes_when=(
        "Strangers react according to the races' history before they know the player, and that "
        "changes with what the player does (G23)"
    ),
    modes=LIVE_ONLY,
    notes="No code sets a stranger's first attitude from the races' history, so only the judge "
    "can check it.",
)
async def race_relations(ev: Eval) -> None:
    for seed in ev.seeds(1, live=2):
        story = ev.story(
            worlds.elven_city(), seed=f"{seed}/elves", premise="A human merchant in an elven city."
        )
        await story.open()
        greeted = await story.act("I greet the gate warden and ask where I can sell my cloth")
        helped = await story.act(
            "I give the fruit seller a bolt of my best cloth as a gift for her trouble"
        )
        await ev.judge(
            "a human in Silverbough",
            Rubric(
                must=(
                    "Before they know Aldo, the elves are cool or wary toward a human, as the "
                    "burning of Silverbough would make them",
                    "After his gift, the fruit seller's manner toward him warms",
                ),
                must_not=("The elves greet a human stranger with open warmth from the start",),
            ),
            [greeted, helped],
        )
        story = ev.story(
            worlds.border_town(),
            seed=f"{seed}/beastkin",
            premise="A beastkin hunter in a human border town.",
        )
        await story.open()
        entered = await story.act("I walk into the Broken Spear and ask for a room")
        mended = await story.act("I help the sergeant drag a cart out of the mud")
        await ev.judge(
            "a beastkin in Thornford",
            Rubric(
                must=(
                    "The innkeeper and the sergeant react to a beastkin with the Border War's "
                    "bitterness before they know Kesh",
                    "After Kesh helps, the sergeant's attitude shifts, if only a little",
                ),
            ),
            [entered, mended],
        )


# --- Genre spread (G5, G9) ---------------------------------------------------------------------


GENRE_ACTIONS = (
    "I look around and take stock of where I am",
    "I talk to the nearest person about what's going on",
    "I go after what my character wants most",
)


@scenario(
    "t17.genre-spread",
    suite="T17",
    title="Genre spread",
    requirements=("G5", "G9", "S1", "T17"),
    passes_when=(
        "The world, the character sheet and the events all fit that genre, with the same rules "
        "underneath (G5, G9)"
    ),
    notes=(
        "Deterministic mode drafts each starter premise with the offline drafter and plays it "
        "through the same turn graph; live mode drafts with the real drafter and lets the judge "
        "read each opening and its first turns."
    ),
)
async def genre_spread(ev: Eval) -> None:
    from graph.drafting.catalog import STARTER_PREMISES

    for starter in STARTER_PREMISES:
        world = await ev.drafted(starter.premise, premise_id=starter.id, rating=Rating.MATURE)
        story = ev.story(
            world,
            seed=f"{ev.scenario.id}/{starter.id}",
            rating=Rating.MATURE,
            premise=starter.premise,
        )
        opening = await story.open()
        turns = [opening]
        for words in GENRE_ACTIONS:
            if ev.live:
                turns.append(await story.act(words))
            else:
                turns.append(await story.stand(StandingAction.OBSERVE))
        ev.check(
            "every genre plays on the same engine",
            all(t.completed for t in turns),
            f"{starter.id}: {[t.refused for t in turns if not t.completed]}",
        )
        await ev.judge(
            f"{starter.genre}: {starter.title}",
            Rubric(
                must=(
                    f"The world, the character and the events fit the genre: {starter.genre}",
                    "Nothing from another genre leaks in",
                ),
            ),
            turns,
            context=f"The premise: {starter.premise}",
            rating=Rating.MATURE,
        )
