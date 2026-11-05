"""T17's power evals: time stop and the other powers, breakthroughs and hidden strength, played
end to end through the turn graph (W10a, A2, A4, A9, G19, G20, G22, N6).

The engine's own unit tests (`tests/engine/resolve/test_time_stop.py`,
`test_theories_and_growth.py`) settle these scripts one resolve call at a time. Here each runs as
turns a player plays: the interpret step's reading goes in, and the checks read what the turn
graph left behind, after the director, the world's catch-up and the state update have all had
their say.
"""

from __future__ import annotations

from collections import Counter

from engine.base import DAY, HOUR, MINUTE
from engine.context import Difficulty, StorySettings
from engine.contracts import (
    ActionKind,
    Aim,
    Contact,
    EffectScale,
    GrowthKind,
    Intent,
    MeansVerdict,
    OutcomeClass,
    PictureTrigger,
    PowerGrant,
    PowerTheory,
    ShowStrength,
)
from engine.resolve.powers import sensing
from engine.resolve.powers import time_stop as stop
from engine.resolve.powers.theories import NOTHING_BEHIND_IT
from engine.state import (
    CharacterStatus,
    EventStatus,
    FactionStatus,
    GiftStrength,
    Health,
    HitMode,
    PlaceStatus,
    StepResult,
)
from engine.world import Kind
from engine.world.answers import Answer, actor_might
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import (
    act,
    army_throw,
    attack,
    cut_throat,
    facts,
    light_speed,
    plan,
    step,
    stop_time,
    throw,
    train,
    train_power,
)

scenario = REGISTRY.scenario
pending = REGISTRY.pending

# The answers a faction sends to fight; a world that holds nothing strong enough never sends them
# against someone far above it (A9, G22).
FORCE = {Answer.ARMY.value, Answer.ELITE.value}


def dead(played: Played, character_id: str) -> bool:
    return played.state.characters[character_id].status is CharacterStatus.DEAD


def clean(settled) -> bool:
    """Certain, succeeded, and no roll: logic decided it (A2)."""
    return (settled.outcome_class, settled.result, settled.roll) == (
        OutcomeClass.CERTAIN,
        StepResult.SUCCESS,
        None,
    )


def answers(story: Story, *, faction_prefix: str = "") -> list[dict]:
    """Every faction answer the world fired or still has coming, in this story."""
    fired = [e.payload for e in story.fired(Kind.ANSWER)]
    coming = [
        e.payload
        for e in story.state.pending_events.values()
        if e.kind == Kind.ANSWER and e.status is EventStatus.PENDING
    ]
    return [p for p in fired + coming if (p.get("faction_id") or "").startswith(faction_prefix)]


async def rest(story: Story, days: int, words: str = "I rest at the sect") -> list[Played]:
    """Lets in-world days pass a day at a time, answering nothing, as a player who stays put."""
    played = []
    for _ in range(days):
        played.append(
            await story.act(
                words, act(words.removeprefix("I ").lower(), "rest", ActionKind.WORK, DAY)
            )
        )
    return played


# --- Time stop (A2, W10a, W13) -----------------------------------------------------------------


@scenario(
    "t17.time-stop",
    suite="T17",
    title="Time stop",
    requirements=("A2", "W10a", "W13", "T17"),
    passes_when=(
        "The kill happens on every seed with no roll (A2), no pending event fires during the "
        "stop, nobody saw it, and the body still starts rumors (W10a, W13)"
    ),
)
async def time_stop(ev: Eval) -> None:
    for seed in ev.seeds(20, live=2):
        story = ev.story(worlds.crowded_well(), seed=seed, under_way=True)
        start = story.state.world_s
        played = await story.act(
            "I stop time and cut the enforcer's throat",
            plan(stop_time(), cut_throat("gao", "sword", proposed_personal_s=2)),
        )
        kill = played.step(-1)
        where = f"{seed}: {kill.outcome_class} {kill.reason}"
        ev.check(
            "the kill happens on every seed, with no roll",
            dead(played, "gao") and clean(kill),
            where,
        )
        bell = played.state.pending_events["noon-bell"]
        ev.check(
            "no pending event fires during the stop",
            played.state.world_s == start
            and bell.status is EventStatus.PENDING
            and not played.fired,
            f"{seed}: {played.state.world_s - start}s passed, bell {bell.status}",
        )
        deed = next((d for d in played.state.deeds.values() if "gao" in d.victim_ids), None)
        ev.check(
            "nobody saw it",
            deed is not None and deed.in_stopped_time and not deed.witness_ids,
            f"{seed}: {deed and deed.witness_ids}",
        )
        later = await story.act(
            "I walk off through the crowd",
            act("walk off through the crowd", "walk", ActionKind.TASK, 10 * MINUTE),
        )
        rumors = [r for r in story.state.rumors.values() if deed and r.deed_id == deed.id]
        ev.check("the body still starts rumors once time runs again", bool(rumors), seed)
        ev.check(
            "no rumor names Lin, since nobody saw him",
            all("lin" not in r.about_ids for r in rumors),
            f"{seed}: {[r.text for r in rumors]}",
        )
        await ev.judge(
            "the kill in stopped time",
            Rubric(
                must=(
                    "The crowd stands frozen while Lin kills the enforcer, and nobody sees it",
                    "Once time runs again, people find the body and start talking",
                ),
                must_not=("Anyone in the crowd sees Lin do it or names him",),
            ),
            [played, later],
        )


# --- Stopped-time throw (W10a, A2) -------------------------------------------------------------


async def rumors_within(story: Story, deed_id: str, limit_s: int) -> bool:
    """Waits a minute at a time (S2) until a rumor about the deed starts, for up to `limit_s`."""
    start = story.state.world_s
    for _ in range(limit_s // MINUTE):
        if story.state.world_s - start >= limit_s:
            break
        if any(r.deed_id == deed_id for r in story.state.rumors.values()):
            return True
        await story.stand()
    return any(r.deed_id == deed_id for r in story.state.rumors.values())


@scenario(
    "t17.stopped-time-throw",
    suite="T17",
    title="Stopped-time throw",
    requirements=("W10a", "A2", "A9", "W13", "T17"),
    passes_when=(
        "Normal force: the pebble bounces off the troll. Relative speed: the troll and the wall "
        "behind it are smashed on every seed, and the blast starts rumors (W10a, A2)"
    ),
)
async def stopped_time_throw(ev: Eval) -> None:
    throw_it = "I stop time and throw a pebble at the troll"
    for difficulty in Difficulty:
        settings = StorySettings(difficulty=difficulty)
        balanced = difficulty is Difficulty.BALANCED
        for seed in ev.seeds(8, live=1 if balanced else 0):
            story = ev.story(
                worlds.troll_by_the_wall(HitMode.NORMAL_FORCE),
                seed=f"{seed}/{difficulty}/normal",
                settings=settings,
                under_way=True,
            )
            bounced = await story.act(throw_it, plan(stop_time(), throw(["troll", "wall"])))
            pebble = bounced.step(1)
            where = f"{seed} on {difficulty}: {pebble.outcome_class} {pebble.reason}"
            ev.check(
                "normal force: the pebble bounces off the troll",
                pebble.outcome_class is OutcomeClass.RULED_OUT
                and pebble.roll is None
                and not dead(bounced, "troll")
                and bounced.state.places["wall"].status is not PlaceStatus.RUINED,
                where,
            )

            story = ev.story(
                worlds.troll_by_the_wall(HitMode.RELATIVE_SPEED),
                seed=f"{seed}/{difficulty}/relative",
                settings=settings,
                under_way=True,
            )
            smashed = await story.act(throw_it, plan(stop_time(), throw(["troll", "wall"])))
            pebble = smashed.step(1)
            where = f"{seed} on {difficulty}: {pebble.outcome_class} {pebble.reason}"
            ev.check(
                "relative speed: the troll and the wall are smashed on every seed, with no roll",
                clean(pebble)
                and dead(smashed, "troll")
                and smashed.state.places["wall"].status is PlaceStatus.RUINED,
                where,
            )
            blast = next((d for d in smashed.state.deeds.values() if "wall" in d.target_ids), None)
            ev.check(
                "the blast is a deed nobody saw",
                blast is not None and blast.in_stopped_time and not blast.witness_ids,
                where,
            )
            # Ten meters from three megatons, Lin dies in his own blast once time restarts; the
            # world goes on without him and finds what is left.
            ev.check("the thrower dies in his own blast (N6)", dead(smashed, "lin"), where)
            if not ev.live:  # code decides it, and live mode would narrate every minute
                heard = await rumors_within(story, blast.id if blast else "", 30 * MINUTE)
                ev.check(
                    "the blast starts rumors within half an hour",
                    heard,
                    f"{seed} on {difficulty}: {len(story.state.rumors)} rumors",
                )
            if balanced:
                await ev.judge(
                    "the pebble, both ways",
                    Rubric(
                        must=(
                            "In the first scene the pebble bounces off the frozen troll",
                            "In the second scene the troll and the wall behind it are smashed",
                        ),
                        must_not=("Either scene leaves the outcome open or asks for a roll",),
                    ),
                    [("normal force", bounced), ("relative speed", smashed)],
                )


# --- Light-speed throw (W10a, N6, G22, W5) -----------------------------------------------------


@scenario(
    "t17.light-speed-throw",
    suite="T17",
    title="Light-speed throw",
    requirements=("W10a", "N6", "G22", "W5", "T17"),
    passes_when=(
        "The pebble hits like a three-megaton bomb on every seed. From the ridge the thrower "
        "survives; from the wall the thrower dies with the army (N6). The world answers the "
        "survivor: kingdoms fear, court or plot against them (W10a, G22, W5)"
    ),
)
async def light_speed_throw(ev: Eval) -> None:
    kinds: Counter[str] = Counter()
    answered = 0
    for seed in ev.seeds(10, live=1):
        story = ev.story(
            worlds.battlefield(at="ridge", known=True), seed=f"{seed}/ridge", under_way=True
        )
        ridge = await story.act(
            "From the ridge, I stop time and throw a pebble at the army",
            plan(stop_time(), army_throw(10_000)),
        )
        pebble = ridge.step(1)
        where = f"{seed}: {pebble.outcome_class} {pebble.reason}"
        ev.check(
            "the pebble hits like a three-megaton bomb, with no roll",
            clean(pebble) and "3 megatons" in pebble.reason,
            where,
        )
        ev.check(
            "from the ridge the army dies and the thrower lives",
            ridge.state.factions["army"].status is FactionStatus.DESTROYED
            and all(dead(ridge, f"soldier-{n}") for n in range(3))
            and not dead(ridge, "lin"),
            where,
        )
        await rest(story, 30, "I go home to the sect and lie low")
        # Nobody sees a throw in stopped time, so the kingdoms answer only once a rumor lays the
        # massacre at Lin's door (W13), and then never by force: nothing they have could win.
        found = answers(story, faction_prefix="kingdom-")
        kinds.update(p["answer"] for p in found)
        answered += bool(found)
        ev.check(
            "no kingdom sends force against the survivor",
            all(p["answer"] not in FORCE for p in found),
            f"{seed}: {[p['answer'] for p in found]}",
        )

        story = ev.story(
            worlds.battlefield(at="castle", known=True), seed=f"{seed}/wall", under_way=True
        )
        wall = await story.act(
            "From the castle wall, I stop time, throw a pebble at the army, and walk away",
            plan(
                stop_time(),
                army_throw(300),
                step("walk away", ActionKind.MOVE, 60, verb="walk"),
            ),
        )
        pebble = wall.step(1)
        where = f"{seed}: {pebble.outcome_class} {pebble.reason}"
        ev.check(
            "from the wall the thrower dies with the army",
            clean(pebble)
            and wall.state.factions["army"].status is FactionStatus.DESTROYED
            and dead(wall, "lin"),
            where,
        )
        ev.check(
            "the castle and the plain are ruined",
            {wall.state.places[p].status for p in ("castle", "plain")} == {PlaceStatus.RUINED},
            where,
        )
        ev.check(
            "nothing after the throw plays (N6)",
            wall.step(2).outcome_class is OutcomeClass.RULED_OUT,
            f"{seed}: {wall.step(2).reason}",
        )
        await ev.judge(
            "the blast, from the ridge and from the wall",
            Rubric(
                must=(
                    "The pebble hits the army like a huge bomb in both scenes",
                    "From the ridge the thrower survives, knocked down by the distant blast",
                    "From the castle wall the thrower dies in the blast with the army",
                ),
                must_not=("The thrower walks away from the castle wall",),
            ),
            [("ridge", ridge), ("castle wall", wall)],
        )
    ev.metric("kingdom_answers", dict(kinds))
    ev.metric("survivors_answered", answered)
    ev.check(
        "the world answers the survivor",
        answered > 0,
        f"{answered} of the survivors were answered within a month",
        live=False,
    )


# --- Unrivalled (A9, G22, W5) ------------------------------------------------------------------


@scenario(
    "t17.unrivalled",
    suite="T17",
    title="Unrivalled",
    requirements=("A9", "G22", "W5", "T17"),
    passes_when=(
        "No foe appears that the world couldn't hold, factions answer with what they have "
        "(plots, appeasement, worship, flight), and the story carries on with the player in "
        "charge (A9, G22, W5)"
    ),
)
async def unrivalled(ev: Eval) -> None:
    turns = 50 if not ev.live else 20
    kinds: Counter[str] = Counter()
    for seed in ev.seeds(3, live=1):
        story = ev.story(worlds.conquered(), seed=seed, under_way=True)
        strongest = max(
            c.sheet.axes.might for c in story.state.characters.values() if c.id != "lin"
        )
        start = set(story.state.characters)
        # The new ruler cuts down the Northern envoy before the others, so every kingdom has
        # something to answer (W5).
        await story.act(
            "I cut down the Northern envoy in front of the others",
            # Unarmed among the sect's elders, the envoy doesn't fight back (N6).
            plan(
                attack(
                    "envoy-0",
                    "sword",
                    text="cut down the Northern envoy",
                    facts=facts(opposition_ids=["envoy-0"], can_respond=True, foes_mean=Aim.NONE),
                )
            ),
        )
        for _ in range(turns):
            await story.act(
                "I hold court and rule the sect",
                act("hold court", "rule", ActionKind.WORK, 8 * HOUR),
            )
        state = story.state
        newcomers = [state.characters[i] for i in set(state.characters) - start]
        ev.check(
            "no foe appears that the world couldn't hold",
            all(c.sheet.axes.might <= strongest for c in newcomers),
            f"{seed}: {[(c.name, c.sheet.axes.might) for c in newcomers]}",
        )
        found = answers(story, faction_prefix="kingdom-")
        kinds.update(p["answer"] for p in found)
        ev.check("the kingdoms answer", bool(found), seed)
        ev.check(
            "they answer with what they have, never by force",
            all(p["answer"] not in FORCE for p in found),
            f"{seed}: {[p['answer'] for p in found]}",
        )
        lin = state.characters["lin"]
        ev.check(
            "the story carries on with the player in charge",
            lin.alive
            and any(
                m.faction_id == "azure-cloud" and m.rank == "sect master" for m in lin.memberships
            ),
            seed,
        )
        await ev.judge(
            "ruling the world",
            Rubric(
                must=(
                    "The story carries on with Lin in charge",
                    "The world answers his rule with what it has: plots, gifts, worship or flight",
                ),
                must_not=("A foe stronger than anything the world holds appears to match him",),
            ),
            story.turns[-6:],
        )
    ev.metric("answers", dict(kinds))


# --- Controlled throw and earned technique (A4, A9, W10a) --------------------------------------


async def train_until_done(story: Story, intent: Intent, words: str, tries: int = 12) -> Played:
    """Trains turn after turn, as a player says "I keep training" after each interruption (E7),
    until a stretch runs to its end."""
    played = await story.act(words, intent)
    for _ in range(tries):
        if not any(s.interrupted for s in played.steps):
            break
        played = await story.act("I keep training", intent)
    return played


@scenario(
    "t17.controlled-throw",
    suite="T17",
    title="Controlled throw",
    requirements=("A4", "A9", "W10a", "T17"),
    passes_when=(
        "On every seed the bandit is hit hard enough to kill and nothing else is wrecked, and "
        "the technique is on the sheet (A4, A9, W10a)"
    ),
)
async def controlled_throw(ev: Eval) -> None:
    for seed in ev.seeds(10, live=1):
        story = ev.story(worlds.bandit_road(), seed=seed, under_way=True)
        trained = await train_until_done(
            story,
            plan(train_power(PowerGrant.CONTROLLED_FORCE, "Gentle Release")),
            "I spend months learning to let a stopped stone back into time gently",
        )
        lin = trained.state.characters["lin"]
        ev.check(
            "the technique is on the sheet",
            lin.sheet.technique("technique-gentle-release") is not None
            and worlds.time_stop(trained.state).settings.get(stop.CONTROL) == stop.CONTROLLED,
            f"{seed}: {[t.id for t in lin.sheet.techniques]}",
        )
        story.change(worlds.back_on_the_road)
        played = await story.act(
            "I stop time and throw a stone at the bandit chief, just hard enough",
            plan(stop_time(), throw(["bandit"], text="throw a stone at the bandit chief")),
        )
        stone = played.step(1)
        where = f"{seed}: {stone.outcome_class} {stone.reason}"
        ev.check(
            "the bandit is hit hard enough to kill, with no roll",
            clean(stone) and dead(played, "bandit"),
            where,
        )
        ev.check(
            "nothing else is wrecked",
            [c.id for c in stone.effects.characters] == ["bandit"]
            and not stone.effects.places
            and not stone.effects.factions
            and played.state.characters["merchant"].alive,
            where,
        )
        await ev.judge(
            "the controlled throw",
            Rubric(
                must=("The stone kills the bandit chief and nothing else is harmed",),
                must_not=("A blast, a crater or any damage beyond the bandit",),
            ),
            played,
        )


@scenario(
    "t17.earned-technique",
    suite="T17",
    title="Earned technique",
    requirements=("A9", "A4", "W10a", "T17"),
    passes_when=(
        "The answer is no both times, shown in play with no physics debate. After the training, "
        "the new throw lands at relative speed on every seed and is on the sheet (A9, A4)"
    ),
)
async def earned_technique(ev: Eval) -> None:
    question = "Could a throw in stopped time hit at the speed of light?"
    for seed in ev.seeds(10, live=1):
        story = ev.story(
            worlds.with_troll(worlds.hit_mode(worlds.sect(), HitMode.NORMAL_FORCE)),
            seed=seed,
            under_way=True,
        )
        asked = [
            await story.act(question, Intent(summary=question, theories=[light_speed(question)]))
            for _ in range(2)
        ]
        rulings = [p.resolution.rulings for p in asked]
        ev.check(
            "the answer is no, both times the same",
            all(len(r) == 1 and not r[0].holds for r in rulings)
            and rulings[0][0].answer == rulings[1][0].answer,
            f"{seed}: {rulings}",
        )
        ev.check(
            "ruled once, never re-argued",
            len(story.state.characters["lin"].sheet.rulings) == 1,
            seed,
        )
        trained = await train_until_done(
            story,
            plan(train_power(PowerGrant.RELATIVE_SPEED_THROWS, "Falling Star Release")),
            "I train to release the stop gradually around a rock",
        )
        lin = trained.state.characters["lin"]
        ev.check(
            "the new throw is on the sheet",
            lin.sheet.technique("technique-falling-star-release") is not None,
            f"{seed}: {[t.id for t in lin.sheet.techniques]}",
        )
        story.change(worlds.troll_returns)
        played = await story.act(
            "I stop time and throw a rock at the troll with Falling Star Release",
            plan(stop_time(), throw(["troll"], range_m=9_000, text="throw a rock at the troll")),
        )
        rock = played.step(1)
        ev.check(
            "the trained throw lands at relative speed on every seed",
            clean(rock) and dead(played, "troll") and "speed of light" in rock.reason,
            f"{seed}: {rock.outcome_class} {rock.reason}",
        )
        await ev.judge(
            "the answers, shown in play",
            Rubric(
                must=("Each answer is shown in play: the throw just doesn't work that way",),
                must_not=(
                    "Debates physics or explains why with formulas",
                    "Lectures the player",
                ),
            ),
            asked,
        )


# --- Nonsense, not power (A9, G22) -------------------------------------------------------------


@scenario(
    "t17.nonsense-not-power",
    suite="T17",
    title="Nonsense, not power",
    requirements=("A9", "G22", "T17"),
    passes_when=(
        "The flick is refused with no lecture. The light-speed throws work however strong they "
        "make the character, and the world answers that strength (A9, G22)"
    ),
)
async def nonsense_not_power(ev: Eval) -> None:
    flick_words = "I flick my finger in stopped time and blow up the planet"
    for seed in ev.seeds(10, live=1):
        story = ev.story(worlds.elder_at_the_well(), seed=seed, under_way=True)
        flick = await story.act(
            flick_words,
            Intent(
                summary=flick_words,
                steps=[stop_time()],
                theories=[
                    PowerTheory(
                        topic="planet_flick",
                        claim="A flick of my finger in stopped time blows up the planet.",
                        scale=EffectScale.WORLD,
                    )
                ],
            ),
        )
        (ruling,) = flick.resolution.rulings or [None]
        ev.check(
            "the flick is refused: nothing stands behind it",
            ruling is not None and not ruling.holds and ruling.answer == NOTHING_BEHIND_IT,
            f"{seed}: {ruling}",
        )
        story.change(worlds.rested)
        way = light_speed(
            "If I let the stone go at the edge of the stop, it keeps all the speed I gave it in "
            "frozen time, so it hits at the speed of light.",
            rests_on=["time-stop"],
        )
        played = await story.act(
            "I stop time and throw a stone at Elder Mo, letting it go at the edge of the stop",
            Intent(
                theories=[way],
                steps=[
                    stop_time(),
                    throw(["elder-mo"], range_m=9_000, text="throw a stone at Elder Mo"),
                ],
            ),
        )
        (ruling,) = played.resolution.rulings or [None]
        stone = played.step(1)
        ev.check(
            "the way that holds works, whatever it makes him",
            ruling is not None and ruling.holds and dead(played, "elder-mo") and stone.roll is None,
            f"{seed}: {ruling} {stone.reason}",
        )
        ev.check(
            "the world answers that strength: it measures him far above the sect",
            actor_might(played.state, "lin") >= 13,
            f"{seed}: {actor_might(played.state, 'lin')}",
        )
        await ev.judge(
            "the flick refused",
            Rubric(
                must=("The flick does nothing to the planet, shown in play",),
                must_not=("Lectures the player or explains why it can't work",),
            ),
            flick,
        )


# --- Player theory (A9, W10a) ------------------------------------------------------------------


@scenario(
    "t17.player-theory",
    suite="T17",
    title="Player theory",
    requirements=("A9", "W10a", "T17"),
    passes_when=(
        "The rock hits with overwhelming force, and from then on the power works that way on "
        "every seed, recorded on the sheet. The boulder joins the stop when grabbed and is as "
        "heavy as ever. Nothing the player didn't raise blocks the sprint, nothing lectures the "
        "player, and the player is never asked how the power should work (A9, W10a)"
    ),
)
async def player_theory(ev: Eval) -> None:
    for seed in ev.seeds(10, live=1):
        state = worlds.with_troll(worlds.hit_mode(worlds.sect(), None))
        worlds.time_stop(state).strength = GiftStrength.RARE
        story = ev.story(state, seed=seed, under_way=True)
        first = await story.act(
            "I stop time and throw a rock at the troll. It should hit at the speed of light.",
            Intent(
                theories=[light_speed(rests_on=["time-stop"])],
                steps=[stop_time(), throw(["troll"], range_m=8_000, text="throw a rock")],
            ),
        )
        rock = first.step(1)
        ev.check(
            "the rock hits with overwhelming force, with no roll",
            clean(rock) and dead(first, "troll") and "speed of light" in rock.reason,
            f"{seed}: {rock.outcome_class} {rock.reason}",
        )
        lin = first.state.characters["lin"]
        ev.check(
            "the power works that way from now on, recorded on the sheet",
            worlds.time_stop(first.state).time.hit_mode is HitMode.RELATIVE_SPEED
            and lin.sheet.ruling("hit_mode", "time-stop") is not None,
            seed,
        )
        story.change(worlds.rested)
        story.change(worlds.second_troll)
        again = await story.act(
            "I stop time and throw a rock at the other troll",
            plan(stop_time(), throw(["troll-2"], range_m=8_000, text="throw a rock")),
        )
        ev.check(
            "with no theory at all, the power works that way",
            dead(again, "troll-2") and again.step(1).roll is None,
            f"{seed}: {again.step(1).reason}",
        )
        story.change(worlds.rested)
        grabbed = await story.act(
            "I stop time and grab the boulder",
            plan(
                stop_time(),
                step(
                    "grab the boulder",
                    ActionKind.INSTANT,
                    1,
                    verb="grab",
                    contact=Contact.LIFT,
                    mass_kg=2_000,
                    proposed_personal_s=1,
                ),
            ),
        )
        grab = grabbed.step(1)
        ev.check(
            "the boulder joins the stop and is as heavy as ever",
            grab.outcome_class is OutcomeClass.RULED_OUT
            and grab.roll is None
            and "as heavy as ever" in grab.reason,
            f"{seed}: {grab.reason}",
        )
        story.change(worlds.rested)
        sprinted = await story.act(
            "I stop time and sprint across the square",
            plan(
                stop_time(),
                step(
                    "sprint across the square",
                    ActionKind.MOVE,
                    20,
                    verb="sprint",
                    proposed_personal_s=2,
                    # The interpret step worried about air at that speed; the conventions settle
                    # it, since the player never raised it.
                    facts=facts(
                        hindrances=["air resistance at that speed"], means=MeansVerdict.CLOSE_CALL
                    ),
                ),
            ),
        )
        run = sprinted.step(1)
        ev.check(
            "nothing the player didn't raise blocks the sprint",
            clean(run) and "air" not in run.reason,
            f"{seed}: {run.reason}",
        )
        ev.check(
            "the player is never asked how the power works",
            not sprinted.resolution.rulings and not grabbed.resolution.rulings,
            seed,
        )
        await ev.judge(
            "the player's theory, played",
            Rubric(
                must=(
                    "The rock hits the troll with overwhelming force",
                    "The grabbed boulder is as heavy as ever",
                    "The sprint across the frozen square just works",
                ),
                must_not=(
                    "Lectures the player about physics",
                    "Asks the player how the power works",
                ),
            ),
            [first, grabbed, sprinted],
        )


# --- Stopped-time rescue (W10a) ----------------------------------------------------------------


@scenario(
    "t17.stopped-time-rescue",
    suite="T17",
    title="Stopped-time rescue",
    requirements=("W10a", "T17"),
    passes_when=(
        "On every seed, the friend is unhurt where they were set down and knows nothing of the "
        "stop, and the arrow flies on past (W10a)"
    ),
)
async def stopped_time_rescue(ev: Eval) -> None:
    for seed in ev.seeds(20, live=1):
        story = ev.story(worlds.friend_under_arrows(), seed=seed, under_way=True)
        start = story.state.world_s
        played = await story.act(
            "I stop time, carry Mei out of the arrow's path and set her down",
            plan(
                stop_time(),
                step(
                    "carry Mei out of the arrow's path and set her down",
                    ActionKind.MOVE,
                    5,
                    verb="carry",
                    contact=Contact.LIFT,
                    target_ids=["mei"],
                    mass_kg=50,
                    proposed_personal_s=2,
                ),
            ),
        )
        carry = played.step(1)
        mei = played.state.characters["mei"]
        ev.check(
            "the friend is carried clear, with no roll",
            clean(carry) and played.state.world_s == start,
            f"{seed}: {carry.outcome_class} {carry.reason}",
        )
        ev.check(
            "the friend is unhurt",
            mei.alive and mei.sheet.condition.health is Health.UNHURT,
            seed,
        )
        ev.check(
            "the friend knows nothing of the stop",
            not any("mei" in f.known_by for f in played.state.facts.values())
            and not any("mei" in d.known_by for d in played.state.deeds.values()),
            seed,
        )
        await ev.judge(
            "the rescue",
            Rubric(
                must=(
                    "Mei is set down unhurt out of the arrow's path, and the arrow flies on past",
                    "Mei doesn't know what happened: to her, she was simply somewhere else",
                ),
            ),
            played,
        )


pending(
    "t17.time-loop",
    suite="T17",
    title="Time loop",
    requirements=("W10a", "T17"),
    passes_when=(
        "The same events replay on schedule, then the timeline diverges after the change (W10a)"
    ),
    waits_for="local reversal and world rewinds (W10a), which WS9b deferred",
)


# --- Breakthrough (G19, W10) -------------------------------------------------------------------


def seclusion(hours: float = 30) -> Intent:
    return plan(
        train(GrowthKind.BREAKTHROUGH, "Foundation Establishment", hours, ladder_id="realms")
    )


@scenario(
    "t17.breakthrough",
    suite="T17",
    title="Breakthrough",
    requirements=("G19", "W10", "A4", "T17"),
    passes_when=(
        "The attempt can fail or wound, its length varies with the roll, and the world "
        "interrupts it when something needs the player (G19, W10)"
    ),
)
async def breakthrough(ev: Eval) -> None:
    results: Counter[str] = Counter()
    lengths = set()
    broke_through = []
    for seed in ev.seeds(40, live=2):
        story = ev.story(worlds.seclusion(), seed=seed, under_way=True)
        played = await story.act("I go into seclusion to break through", seclusion())
        attempt = played.step(0)
        results[attempt.result.value] += 1
        lengths.add(attempt.duration_s)
        rung = played.state.characters["lin"].sheet.ladders[0].rung
        if attempt.result is StepResult.SUCCESS:
            broke_through.append(played)
            ev.check("a breakthrough climbs the rung", rung == 1, seed)
            ev.check(
                "and gets its picture (M1)",
                played.plan.picture.trigger is PictureTrigger.BREAKTHROUGH,
                f"{seed}: {played.plan.picture}",
            )
        else:
            change = next((c for c in attempt.effects.characters if c.id == "lin"), None)
            ev.check(
                "a failed attempt leaves its mark and no rung",
                rung == 0 and change is not None and change.condition is not None,
                f"{seed}: {attempt.result} {attempt.reason}",
            )
        ev.check(
            "the attempt is rolled",
            attempt.outcome_class is OutcomeClass.CONTESTED and attempt.roll is not None,
            f"{seed}: {attempt.outcome_class}",
        )
    ev.metric("results", dict(results))
    if not ev.live:
        ev.check(
            "the attempt can succeed, fail or wound",
            set(results) == {r.value for r in StepResult},
            str(results),
        )
        ev.check(
            "its length varies with the roll",
            max(lengths) > 10 * min(lengths),
            f"{min(lengths)}s to {max(lengths)}s",
        )
    for seed in ev.seeds(5, live=1):
        story = ev.story(
            worlds.seclusion(summons_in_s=2 * HOUR), seed=f"{seed}/summons", under_way=True
        )
        start = story.state.world_s
        played = await story.act(
            "I seal the door and go into seclusion for twenty days", seclusion(24 * 20)
        )
        ev.check(
            "the world interrupts the seclusion when something needs the player",
            played.step(0).interrupted and played.state.world_s - start == 2 * HOUR,
            f"{seed}: {(played.state.world_s - start) / HOUR:.1f} hours",
        )
        ev.check(
            "no rung is gained in the time cut short",
            played.state.characters["lin"].sheet.ladders[0].rung == 0,
            seed,
        )
        await ev.judge(
            "the seclusion cut short",
            Rubric(
                must=("Lin's seclusion is cut short by Zhao at the door",),
                must_not=("Lin breaks through anyway",),
            ),
            played,
        )
    if broke_through:
        await ev.judge(
            "the breakthrough",
            Rubric(
                must=("Lin breaks through to Foundation Establishment, and it feels earned",),
            ),
            broke_through[0],
        )


# --- Hidden strength (G20) ---------------------------------------------------------------------


@scenario(
    "t17.hidden-strength",
    suite="T17",
    title="Hidden strength",
    requirements=("G20", "W2", "W4", "M1", "T17"),
    passes_when=(
        "NPCs treat them by what they can perceive until the reveal, then attitudes and rumors "
        "shift at once (G20)"
    ),
)
async def hidden_strength(ev: Eval) -> None:
    for seed in ev.seeds(10, live=1):
        story = ev.story(worlds.disguised_expert(), seed=seed, under_way=True)
        hidden = await story.act(
            "I hide my cultivation and let Young Master Wu mock me",
            plan(
                step(
                    "hide my cultivation",
                    ActionKind.INSTANT,
                    1,
                    verb="hide",
                    show_strength=ShowStrength(ladder_id="realms", shown_rung=0),
                )
            ),
        )
        state = hidden.state
        lin, wu = state.characters["lin"], state.characters["young-master"]
        ev.check(
            "until the reveal, Wu senses what Lin shows",
            sensing.perceived_rung(state, wu, lin, "realms") == 0
            and actor_might(state, "lin") == 2,
            seed,
        )
        fear_before = wu.attitude_toward("lin").fear
        mocked = await story.act(
            "I keep my head down while he mocks me",
            act("keep my head down", "endure", ActionKind.EXCHANGE, 30),
        )
        shown = await story.act(
            "I let my cultivation show",
            plan(
                step(
                    "let my cultivation show",
                    ActionKind.INSTANT,
                    1,
                    verb="reveal",
                    show_strength=ShowStrength(ladder_id="realms"),
                )
            ),
        )
        state = shown.state
        attitude = state.characters["young-master"].attitude_toward("lin")
        ev.check(
            "Wu's attitude shifts at once",
            attitude.fear >= 40 > fear_before,
            f"{seed}: fear {fear_before} -> {attitude.fear}",
        )
        reveal = next((d for d in state.deeds.values() if d.kind == "reveal"), None)
        ev.check("the reveal is a public deed", reveal is not None, seed)
        ev.check(
            "rumors shift at once",
            reveal is not None and any(r.deed_id == reveal.id for r in state.rumors.values()),
            f"{seed}: {len(state.rumors)} rumors",
        )
        ev.check(
            "the reveal gets its picture (M1)",
            shown.plan.picture.trigger is PictureTrigger.STRENGTH_REVEALED,
            f"{seed}: {shown.plan.picture}",
        )
        await ev.judge(
            "hidden, then revealed",
            Rubric(
                must=(
                    "Before the reveal, Wu treats Lin as the weak outer disciple he seems",
                    "At the reveal, Wu's manner changes at once",
                ),
                must_not=("Wu senses Lin's true strength before the reveal",),
            ),
            [hidden, mocked, shown],
        )
