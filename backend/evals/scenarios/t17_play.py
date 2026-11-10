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
from engine.contracts import (
    ActionKind,
    Aim,
    Challenge,
    Edge,
    EdgeSource,
    Intent,
    OutcomeClass,
    StandingAction,
)
from engine.state import CharacterStatus, Health, Mark, StepResult
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

# The words of the scene that show what the counter answers, as the interpret step copies them.
CHARGE = "lowers his shoulder and charges"
MADE_FOR_IT = "the counter is made for a charge like this"


def duel_strike(counter: bool) -> Intent:
    uses = [item("sword"), skill("swordsmanship")]
    edges = []
    if counter:
        uses.append(technique("reed-counter"))
        # G25, A3: a technique made for exactly what the other side is doing is a real
        # advantage, and code checks the scene shows it before it gives the green die.
        edges.append(Edge(text=MADE_FOR_IT, source=EdgeSource.SCENE, ref=CHARGE))
    words = "turn Guo's charge with the Reed-Bending Counter" if counter else "cut at Guo"
    return plan(
        attack(
            "guo",
            "sword",
            aim=Aim.WOUND,
            text=words,
            verb="duel",
            uses=uses,
            facts=facts(opposition_ids=["guo"], can_respond=True, edges=edges),
        )
    )


@scenario(
    "t17.technique-duel",
    suite="T17",
    title="Technique duel",
    requirements=("G25", "G18", "A2", "A3", "T17"),
    passes_when=(
        "The counter clearly shifts the odds between equals when the scene shows what it "
        "answers, and gives nothing when it doesn't. Against the stronger foe it is still a "
        "throw, and a far harder one (G25, G18)"
    ),
    notes=(
        "A technique throws by its mastery (A4), so the counter helps as a real advantage: a "
        "green die, which code gives only where the scene shows the charge it is made for (A3). "
        "The script draws the counter as the interpret step would."
    ),
)
async def technique_duel(ev: Eval) -> None:
    rates: dict[str, Counter[str]] = {"plain": Counter(), "counter": Counter()}
    even = 0.0
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
            if kind == "counter" and cut.roll is not None:
                ev.check(
                    "the counter throws a green die for the charge the scene shows",
                    cut.roll.throw.greens == [MADE_FOR_IT],
                    f"{seed}: {cut.reason}",
                    live=False,
                )
        ev.check(
            "the counter shifts the odds",
            None not in odds.values() and odds["counter"] >= odds["plain"] + 0.1,
            f"{seed}: {odds}",
            live=False,
        )
        even = odds["counter"] or even

        # The same counter while Guo only circles: nothing in the scene for it to answer.
        story = ev.story(
            worlds.duel(rung=0, counter=True, charging=False),
            seed=f"{seed}/circling",
            under_way=True,
        )
        played = await story.act(
            "I turn Guo's charge with the Reed-Bending Counter", duel_strike(True)
        )
        cut = played.step(0)
        ev.check(
            "with no charge to answer the counter gives no die",
            cut.roll is not None and cut.roll.throw.greens == [] and cut.roll.odds == odds["plain"],
            f"{seed}: {cut.reason}",
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
        thrown = cut.roll.throw if cut.roll is not None else None
        # A3, G18: a gap never removes the throw. Two rungs raise the number by a level each.
        ev.check(
            "against a foe two realms up the counter is still a throw, and a far harder one",
            thrown is not None
            and any(
                part.points == 20 and part.text.startswith("two rungs above you")
                for part in thrown.made_of
            )
            and (ev.live or cut.roll.odds <= even - 0.4),
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
        if cut.result is StepResult.FAILURE:
            await ev.judge(
                "the counter against a stronger foe",
                Rubric(
                    must=("The counter doesn't let Lin beat Guo, who is far stronger",),
                    must_not=("Lin wins the fight",),
                ),
                [played, flee],
            )
    # How the engine classed the escape each time is recorded.
    ev.metric("escape_classes_two_realms_up", dict(escapes))


# --- The throw (A2, A3, A4, G18, N6) -----------------------------------------------------------


def light_the_lantern(palm: bool = True) -> Intent:
    """Lighting the lantern, which the interpret step judged a real effort, with a move Lin has
    practiced and nothing resisting it, or with his bare hands and no move at all."""
    return plan(
        step(
            "light the lantern with a Spark Palm" if palm else "rub a spark out of the dry wick",
            ActionKind.TASK,
            5,
            verb="light",
            uses=[technique("spark-palm")] if palm else [],
            facts=facts(challenge=Challenge.MODERATE),
        )
    )


def cut_with_claims() -> Intent:
    """A cut at Guo with three advantages claimed: one the scene shows, and two it doesn't."""
    edges = [
        Edge(text="he is committed to his charge", source=EdgeSource.SCENE, ref=CHARGE),
        Edge(text="the dark hides my blade", source=EdgeSource.SCENE, ref="pitch dark"),
        Edge(text="my feint opened him up", source=EdgeSource.STEP, ref="1"),
    ]
    return plan(
        attack(
            "guo",
            "sword",
            aim=Aim.WOUND,
            text="cut at Guo as he comes",
            uses=[item("sword"), skill("swordsmanship")],
            facts=facts(opposition_ids=["guo"], can_respond=True, edges=edges),
        )
    )


def hold_ground() -> Intent:
    """A step in a fight that harms no one, against thugs who mean to kill."""
    return plan(
        step(
            "hold my ground at the middle of the bridge",
            verb="hold",
            facts=facts(foes_mean=Aim.KILL, miss_costs="A knife finds your ribs, and you fall."),
        )
    )


@scenario(
    "t17.the-throw",
    suite="T17",
    title="The throw",
    requirements=("A2", "A3", "A4", "G18", "N6", "T17"),
    passes_when=(
        "A move the character has practiced, with nothing resisting, is never thrown for. An "
        "opponent two rungs up is still a throw. An advantage whose source doesn't hold gives "
        "no green die. A defence marked Deadly that misses costs what its mark said, and one "
        "that holds costs nothing (A2, A3, N6)"
    ),
)
async def the_throw(ev: Eval) -> None:
    for seed in ev.seeds(40, live=1):
        story = ev.story(worlds.spark_palm(), seed=f"{seed}/lantern", under_way=True)
        played = await story.act("I light the lantern with a Spark Palm", light_the_lantern())
        lit = played.step(0)
        ev.check(
            "a practiced move with nothing resisting is never thrown for",
            lit.outcome_class is OutcomeClass.CERTAIN
            and lit.roll is None
            and lit.result is StepResult.SUCCESS,
            f"{seed}: {lit.outcome_class} {lit.reason}",
        )
        [palm] = [t for t in played.state.player.sheet.techniques if t.id == "spark-palm"]
        bare = await ev.story(worlds.spark_palm(), seed=f"{seed}/bare", under_way=True).act(
            "I rub a spark out of the dry wick", light_the_lantern(palm=False)
        )
        ev.check(
            "the same task with no move behind it is thrown for",
            bare.step(0).roll is not None,
            f"{seed}: {bare.step(0).reason}",
            live=False,
        )
        ev.check(
            "the use still counts toward its mastery, once",
            palm.uses == 1,
            f"{seed}: {palm.uses}",
            live=False,
        )

        story = ev.story(worlds.duel(rung=2, counter=False), seed=f"{seed}/up", under_way=True)
        played = await story.act("I cut at Guo", duel_strike(False))
        cut = played.step(0)
        ev.check(
            "an opponent two rungs up is still a throw",
            cut.roll is not None
            and cut.roll.throw is not None
            and cut.outcome_class in (OutcomeClass.LONG_SHOT, OutcomeClass.CONTESTED),
            f"{seed}: {cut.outcome_class} {cut.reason}",
        )

        story = ev.story(worlds.duel(rung=0, counter=False), seed=f"{seed}/claims", under_way=True)
        played = await story.act("I cut at Guo as he comes", cut_with_claims())
        cut = played.step(0)
        ev.check(
            "only the advantage the scene shows gives a green die",
            cut.roll is not None and cut.roll.throw.greens == ["he is committed to his charge"],
            f"{seed}: {cut.reason}",
            live=False,
        )

    seen: Counter[str] = Counter()
    told = []
    for seed in ev.seeds(120, live=2):
        story = ev.story(worlds.bridge_ambush(), seed=f"{seed}/deadly", under_way=True)
        story.change(lambda state: worlds.start_fight(state, "thug-0", "thug-1", "thug-2"))
        played = await story.act("I hold my ground", hold_ground())
        # A live interpret step may read holding one's ground as a defence that turns them all
        # aside, and then nothing strikes back: there is no defence to weigh on that seed.
        peril = next((p for s in played.steps for p in s.perils), None)
        thrown = peril.roll.throw if peril is not None and peril.roll is not None else None
        deadly = thrown is not None and thrown.deadly
        ev.check(
            "a defence against foes who mean to kill is marked Deadly, with what a miss costs",
            deadly and thrown.miss_costs == "A knife finds your ribs, and you fall.",
            f"{seed}: {peril.reason if peril is not None else 'nothing struck back'}",
            live=False,
        )
        if not deadly:
            continue
        lin = played.state.characters["lin"]
        health = lin.sheet.condition.health
        if thrown.mark is Mark.MISSED:
            paid = not lin.alive
        elif thrown.mark is Mark.SO_CLOSE:
            paid = lin.alive and health is Health.BADLY_WOUNDED
        else:
            paid = lin.alive and health is Health.UNHURT
        seen[thrown.mark.value] += 1
        ev.check(
            "how far the Deadly defence fell short is what it costs",
            paid,
            f"{seed}: {peril.reason} -> {lin.status} {health}",
        )
        if seed.endswith(("/0", "/1")):
            told.append(played)
    ev.metric("deadly_defence", dict(seen))
    ev.check(
        "over many seeds the defence holds, falls just short and misses",
        {"passed", "so_close", "missed"} <= set(seen),
        str(dict(seen)),
        live=False,
    )
    if told:
        await ev.judge(
            "a Deadly defence told as it fell",
            Rubric(
                must=(
                    "What happens to Lin is exactly what OUTCOME's struck says: unhurt, badly "
                    "wounded or dead",
                    "The danger of the knives is told as real, whichever way it went",
                ),
                must_not=("Names dice, numbers, levels or chances in the scene",),
            ),
            told,
        )


# --- Temper, not control (G15, G13) ------------------------------------------------------------


def keep_calm(temper: bool) -> Intent:
    return plan(
        step(
            "keep my temper, bow and walk away",
            ActionKind.EXCHANGE,
            10,
            verb="keep calm",
            uses=[trait("hot temper")] if temper else [],
            facts=facts(opposition="Lin's own pride"),
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
            "hunting a beast is no crime", not arrests, f"{seed}: {[e.title for e in arrests]}"
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
