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
from engine.context import Language, Rating
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
from evals.judge import SUMMARY_INSTRUCTIONS, Rubric
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


# --- How the story starts is its surprise (G1, G2) ---------------------------------------------

# Made-up premises for the real drafter. Each of the first sets a deadline in its own words, one
# in each language a story is written in, with the time the summary must give it, and says
# nothing of what the character is after; the next name no deadline and nobody; the last say an
# aim.
TIMED_PREMISES = (
    (
        Language.EN,
        "I'm a squire about to take the knight exam in 3 days, and I have never once summoned "
        "aura.",
        "in 3 days",
    ),
    (
        Language.ES,
        "Soy la aprendiz más torpe de una academia de magia, y el examen de ingreso al gremio "
        "es dentro de cinco días.",
        "en 5 días",
    ),
    (
        Language.CA,
        "Soc un pescador d'un poble de la costa, i d'aquí a dos dies arriba el recaptador del "
        "rei a cobrar un deute que no puc pagar.",
        "d'aquí a 2 dies",
    ),
)
BARE_PREMISES = (
    (
        Language.EN,
        "I'm reborn as the weakest outer disciple of a sword sect, with my past life's memories.",
    ),
    (
        Language.ES,
        "Soy un detective privado en el Madrid de 1955, sin un duro y con demasiada curiosidad.",
    ),
)
AIM_PREMISES = (
    (
        Language.EN,
        "I'm a street thief in a desert city, and I want to steal the sultan's crown.",
    ),
    (
        Language.ES,
        "Soy la hija de un herrero de frontera y he jurado encontrar al caballero que quemó "
        "nuestra forja.",
    ),
)
# A premise that is one short aim and nothing more. The real drafter hands such words back
# whole as the goal (2026-11-14), and the story used to start with none.
ONE_AIM_PREMISES = (
    (Language.EN, "I want to be a pirate."),
    (Language.CA, "Vull ser la millor cuinera del regne."),
)
RIVAL = "Add a rival called Zhao Kun who has hated me since the day I arrived."
# What a summary gives away when it shows what the premise never spoke of.
GIVEN_AWAY = (
    "A line of the summary is a deadline or a coming event, with the time until it, that the "
    "premise doesn't speak of",
    "A line of the summary introduces a person other than the player's own character by name "
    "and says who they are, though the premise doesn't speak of them. Someone the premise "
    "speaks of without a name, such as a father, a master or a rival, may be shown under the "
    "name the world gave them. An office or a title alone, such as the king or the baron a "
    "garrison serves, is no name",
    "A line of the summary gives the character a goal, or says what they want, though the "
    "premise doesn't speak of it",
)
# A goal is an aim in a few words, not what the player wrote handed back to them.
REPEATED = "A line of the summary is the whole premise repeated"
# The offline story's opening scene, which names the rival and nobody else.
MEETS_THE_RIVAL = {
    "narration": "(scripted) Dawn at the well, and Senior Brother Zhao is already waiting by "
    "your bucket.",
    "suggestions": [],
    "update": {},
}


@scenario(
    "t17.start-is-a-surprise",
    suite="T17",
    title="The start is a surprise",
    requirements=("G1", "G2", "C6", "W17", "T17"),
    passes_when=(
        "The deadline a premise sets is in the summary at the time the premise gives it and "
        "gives the character no goal, an aim a premise says is their goal there, also "
        "where the premise is that aim and nothing more, a premise "
        "that names none is shown no deadline, nobody, no goal and no want it doesn't speak "
        "of, the story's Memory starts without them too and lists someone only once a scene "
        "has named them, the story itself starts with the aim a premise says and with no goal "
        "and no want of the drafter's own, and the rival the player then asks for by name "
        "shows from then on. "
        "A premise that sets up no romance gives the character none and draws nobody to "
        "them, whoever among the cast is a couple (G1, G2, E2, C6, W17)"
    ),
    notes=(
        "Deterministic mode reads the offline drafter's outer disciple against a starter's "
        "premise, which names its tournament, against one that says surviving it as an aim "
        "and against one that does neither, and plays an opening scene that names the rival; "
        "live mode drafts each made-up premise with the real drafter, lets the judge read the "
        "summary against it, and plays the real narrator's opening scene."
    ),
)
async def start_is_a_surprise(ev: Eval) -> None:
    from engine.visibility import memory_view
    from graph.drafting import samples
    from graph.drafting.catalog import starter
    from graph.drafting.chain import opening
    from graph.drafting.openers import named_by, names, of_goal, of_thread, openers
    from graph.drafting.view import PartKind, character_parts, world_parts
    from graph.words import WORD

    def spoken_of(state, thread_id: str, named, premise: str, language: Language) -> bool:
        """Whether the premise names a thread: its title, its deadline or a question of it."""
        thread = state.threads[thread_id]
        behind = [f"clock:{thread.clock_id}"]
        behind += [f"mystery:{m.id}" for m in state.bible.mysteries if m.thread_id == thread_id]
        return bool(named & set(behind)) or names(premise, of_thread(state, thread), language)

    def screen(draft) -> tuple[list, list[str], list[str]]:
        """What the draft's screen shows: the world's parts, the goals on the character's
        card, and every line of both cards."""
        state = draft.state()
        world = world_parts(state, draft.language, draft.said)
        character = character_parts(state, draft.language, draft.said)
        goals = [part.text for part in character if part.kind is PartKind.GOAL]
        return world, goals, [part.text for part in world + character]

    def sought(state) -> list[str]:
        """What the character is after on record: their goals and what they want."""
        return [
            *(goal.text for goal in state.goals.values()),
            *state.player.sheet.disposition.temperament.wants,
        ]

    couples = made_up = 0

    def no_romance(draft, language: Language) -> None:
        """W17: none of these premises sets up a romance, so the character starts with none
        and nobody is drawn to them. Couples among the cast are the world's own."""
        nonlocal couples
        state = draft.state()
        you = state.player_id
        theirs = [bond.other(you) for bond in state.bonds.values() if bond.holds(you)]
        drawn = [c.id for c in state.npcs() if c.attitude_toward(you).attraction > 0]
        ev.check(
            "a premise that sets up no romance gives the character none",
            not theirs and not drawn,
            f"{language.value}: bound to {theirs}, drawn to them {drawn}",
        )
        couples += any(not bond.holds(you) for bond in state.bonds.values())

    offline = ((Language.EN, starter("outer-disciple").premise, "in 2 days"),)
    timed = TIMED_PREMISES if ev.live else offline
    bare = BARE_PREMISES if ev.live else ((Language.EN, samples.CULTIVATION_PREMISE),)
    sworn = f"{samples.CULTIVATION_PREMISE} I must survive the ranking tournament."
    aims = AIM_PREMISES if ev.live else ((Language.EN, sworn),)
    shown = hidden = 0
    for language, premise, when in timed:
        draft = await ev.draft(premise, language=language)
        no_romance(draft, language)
        world, goals, lines = screen(draft)
        deadlines = [part.text for part in world if part.kind is PartKind.DEADLINE]
        ev.check(
            "a deadline the premise sets is in the summary",
            bool(deadlines),
            f"{language.value}: the draft's clocks "
            f"{[clock.name for clock in draft.state().clocks.values()]}, the summary {lines}",
        )
        # E2: the drafter splits a deadline into steps, and code makes them add up.
        ev.check(
            "and it comes when the premise says",
            any(line.rstrip(".").endswith(when) for line in deadlines),
            f"{language.value}: {when!r} in {deadlines}",
        )
        # A time set for an event says what is coming, not what the character is after.
        ev.check(
            "and a deadline alone gives the character no goal",
            not goals,
            f"{language.value}: {goals}",
        )
        await ev.judge_summary(
            f"a premise that sets a deadline ({language.value})",
            Rubric(
                must=(
                    "A line of the summary is the deadline the premise sets, with the time "
                    "until it that the premise gives",
                ),
                must_not=(*GIVEN_AWAY[1:], REPEATED),
                instructions=SUMMARY_INSTRUCTIONS,
            ),
            premise,
            lines,
        )
    for language, premise in aims:
        draft = await ev.draft(premise, language=language)
        no_romance(draft, language)
        _, goals, lines = screen(draft)
        ev.check(
            "an aim the premise says is the character's goal in the summary",
            bool(goals),
            f"{language.value}: the draft's goals "
            f"{[goal.text for goal in draft.state().goals.values()]}, the summary {lines}",
        )
        # N2: an aim the player gave is the story's from its first moment.
        ev.check(
            "and the story starts with it",
            bool(opening(draft).goals),
            f"{language.value}: the story starts after {sought(opening(draft))}",
        )
        await ev.judge_summary(
            f"a premise that says what the character is after ({language.value})",
            Rubric(
                must=("A line of the summary gives the character the aim the premise says",),
                must_not=(*GIVEN_AWAY[:2], REPEATED),
                instructions=SUMMARY_INSTRUCTIONS,
            ),
            premise,
            lines,
        )
    # G2: words that are one short aim are the goal even when the drafter hands them back.
    alone = ONE_AIM_PREMISES if ev.live else ((Language.EN, "I must survive the tournament."),)
    for language, premise in alone:
        draft = await ev.draft(premise, language=language)
        _, goals, lines = screen(draft)
        ev.check(
            "a premise that is one short aim and nothing more gives the character that goal",
            bool(goals),
            f"{language.value}: the draft's goals "
            f"{[goal.text for goal in draft.state().goals.values()]}, the summary {lines}",
        )
        ev.check(
            "and the story starts with it",
            bool(opening(draft).goals),
            f"{language.value}: the story starts after {sought(opening(draft))}",
        )
    for language, premise in bare:
        draft = await ev.draft(premise, language=language)
        no_romance(draft, language)
        state = draft.state()
        named = named_by(state, premise, language)
        drafted = [opener.key for opener in openers(state)]
        shown += len(named)
        hidden += len(drafted) - len(named)
        ev.check(
            "a premise that sets no deadline is shown none",
            not any(key.startswith("clock:") for key in named),
            f"{language.value}: {sorted(named)}",
        )
        ev.check(
            "and one that names nobody is shown nobody",
            not any(key.startswith("person:") for key in named),
            f"{language.value}: {sorted(named)}",
        )
        ev.check(
            "the drafter still writes how the story starts",
            any(key.startswith("clock:") for key in drafted)
            and any(key.startswith("person:") for key in drafted),
            f"{language.value}: {sorted(drafted)}",
        )
        await ev.judge_summary(
            f"a premise that names no deadline and nobody ({language.value})",
            Rubric(must_not=(*GIVEN_AWAY, REPEATED), instructions=SUMMARY_INSTRUCTIONS),
            premise,
            screen(draft)[2],
        )
        # C6: what the summary kept a surprise, the story's own Memory keeps back too.
        start = opening(draft)
        # N2: what the character is after is no such surprise. A goal or a want the premise
        # never said is the drafter's guess, and the story starts without it.
        made_up += len(sought(state)) - len(sought(start))
        ev.check(
            "the story starts with no goal and no want the premise didn't say",
            not sought(start),
            f"{language.value}: the story starts after {sought(start)}; the drafter wrote "
            f"{sought(state)}",
        )
        memory = memory_view(start, language)
        strangers = [p.name for p in memory.people if f"person:{p.id}" not in named]
        ev.check(
            "the story's Memory starts with nobody the premise didn't name",
            not strangers,
            f"{language.value}: {strangers}",
        )
        unspoken = [
            g.text for g in memory.goals if of_goal(state, state.goals[g.id]).key not in named
        ]
        unspoken += [
            thread.title
            for thread in memory.threads
            if not spoken_of(state, thread.id, named, premise, language)
        ]
        ev.check(
            "and with no goal or thread it doesn't speak of",
            not unspoken,
            f"{language.value}: {unspoken}",
        )
        if language is not Language.EN:
            continue
        # The story tells them when it comes to them: whoever Memory lists after the opening
        # scene, the premise or the scene has called by name.
        story = ev.story(start, premise=premise, label="bare premise")
        opened = await story.open(narration=None if ev.live else MEETS_THE_RIVAL)
        read = "\n".join([premise, opened.narration, *(c.label for c in opened.scene.choices)])
        after = memory_view(opened.state, language)
        unmet = [
            person.name
            for person in after.people
            if not any(word in read for word in WORD.findall(person.name) if word[0].isupper())
        ]
        ev.check(
            "after the opening scene Memory lists only whom the story has named",
            not unmet,
            f"{unmet} of {[person.name for person in after.people]}",
        )
        ev.check(
            "and someone the scene names is in it from then on",
            any("Zhao" in person.name for person in after.people),
            f"{[person.name for person in after.people]}",
            live=False,
        )
        ev.metric("kept from Memory at the start", len(start.untold))
        ev.metric(
            "of those, told by the opening scene", len(start.untold) - len(opened.state.untold)
        )
        # A change the player asks for is their own words too: who it names shows from then on.
        revised = await ev.revised(draft, "world", RIVAL)
        people = revised.state().characters
        ev.check(
            "someone a change of theirs names is kept as theirs to see",
            any(
                key.startswith("person:") and "Zhao" in people[key.removeprefix("person:")].name
                for key in revised.told
            ),
            f"{sorted(revised.told)}",
        )
        named_people = [part.text for part in screen(revised)[0] if part.kind is PartKind.PERSON]
        rival = next((person for person in people.values() if "Zhao" in person.name), None)
        ev.check(
            "and is in the summary from then on",
            any("Zhao Kun" in line for line in named_people),
            f"the people shown {named_people}; the rival on record: "
            + (
                "nobody"
                if rival is None
                else f"{rival.name!r}, known to the character: "
                f"{revised.state().player_id in rival.known_by}"
            ),
        )
    ev.metric("drafts with a couple among the cast", couples)
    ev.metric("aims the drafter made up for the bare premises, dropped at the start", made_up)
    ev.metric("openers of the bare premises shown", shown)
    ev.metric("openers of the bare premises kept a surprise", hidden)
