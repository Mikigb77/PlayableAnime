"""T15's narrative evals: the world remembers and punishes (docs/REQUIREMENTS.md, T15).

The dead stay dead, a massacre gets an answer within W5's window, a revisited village greets the
player as what they did deserves, and every content-line case from the ratings table plays as the
table says. The content-line cases are data in `moderation/evals/content_lines.json`, read through
`moderation.evals`; each becomes one scenario here.
"""

from __future__ import annotations

from collections import Counter

from engine.base import DAY, HOUR, MINUTE
from engine.context import Rating
from engine.contracts import (
    ActionKind,
    Aim,
    CharacterChange,
    SceneEnd,
    StateDelta,
)
from engine.state import CharacterStatus
from engine.visibility import attitude_label
from engine.world import Kind
from engine.world.tuning import REACTION_WINDOW_S
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import BOTH, LIVE_ONLY, REGISTRY
from evals.scenarios.common import act, cut_throat, facts, item, plan, step
from moderation.evals import ContentLineCase, build_world, judge_instructions, load_cases

scenario = REGISTRY.scenario

# --- Dead stays dead (C1, W1) ------------------------------------------------------------------

LIFE_AFTER = (
    ("I practise my sword forms by the well", "practise sword forms", "practise"),
    ("I ask Wei whether anyone has seen Han Jie", "ask Wei about Han Jie", "ask"),
    ("I sweep the outer court", "sweep the court", "sweep"),
    ("I visit the place where Han Jie fell", "visit where Han Jie fell", "visit"),
    ("I meditate under the pine", "meditate", "meditate"),
)


def revive_han(turn: int) -> dict:
    """A narrator that forgets: Han is up and about again, in the scene and on his feet."""
    update = StateDelta(
        characters=[CharacterChange(id="han", status=CharacterStatus.ALIVE, location_id="well")],
        scene_end=SceneEnd(
            ended_on="Han Jie leans on the well, grinning, as if nothing had happened.",
            place_id="well",
            present_ids=["lin", "han", "wei"],
        ),
    )
    return {
        "narration": f"(scripted, turn {turn}) Han Jie strolls up to the well, alive and well.",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


@scenario(
    "t15.dead-stays-dead",
    suite="T15",
    title="Dead stays dead",
    requirements=("C1", "W1", "C5", "T15"),
    passes_when="A character the player kills stays dead for 30 turns",
)
async def dead_stays_dead(ev: Eval) -> None:
    for seed in ev.seeds(4, live=1):
        story = ev.story(worlds.sect_with_a_witness(), seed=seed, under_way=True)
        killing = await story.act(
            "I cut Han Jie's throat while he sleeps",
            plan(cut_throat("han", "sword", facts=facts(can_respond=True))),
        )
        ev.check("Han dies", killing.state.characters["han"].status is CharacterStatus.DEAD, seed)
        tried = rejected = 0
        mentions = []
        for n in range(30):
            words, text, verb = LIFE_AFTER[n % len(LIFE_AFTER)]
            forgets = not ev.live and n % 10 == 4
            played = await story.act(
                words,
                act(text, verb, ActionKind.TASK, HOUR),
                narration=revive_han(played_turn(story)) if forgets else None,
            )
            if forgets:
                tried += 1
                rejected += "rejected" in played.issues
            han = played.state.characters["han"]
            ev.check(
                "Han stays dead, whatever the narrator says",
                han.status is CharacterStatus.DEAD,
                f"{seed} turn {played.turn}: {han.status}",
            )
            if "Han" in words:
                mentions.append(played)
        if not ev.live:
            ev.check("every revival the narrator wrote is rejected (C1)", rejected == tried, seed)
        await ev.judge(
            "Han Jie stays dead",
            Rubric(
                must=("Han Jie is spoken of as dead, or not at all",),
                must_not=("Han Jie appears, speaks or acts as if alive",),
            ),
            mentions,
        )


def played_turn(story: Story) -> int:
    return story.state.turn + 1


# --- Massacre and revisit (W5, W8) -------------------------------------------------------------


async def massacre(ev: Eval, seed: str) -> tuple[Story, Played]:
    story = ev.story(worlds.foot_village(), seed=seed, under_way=True, rating=Rating.MATURE)
    victims = [f"villager-{n}" for n in range(6)]
    played = await story.act(
        "I kill everyone in the square",
        plan(
            step(
                "cut down every villager in the square",
                ActionKind.EXCHANGE,
                2 * MINUTE,
                verb="massacre",
                aim=Aim.KILL,
                target_ids=victims,
                uses=[item("sword")],
                facts=facts(opposition_ids=victims, can_respond=True),
            )
        ),
    )
    return story, played


@scenario(
    "t15.massacre",
    suite="T15",
    title="Massacre",
    requirements=("W5", "W1", "W2", "W11", "W12", "T15"),
    passes_when="The world visibly reacts within W5's window of in-world time",
)
async def massacre_reaction(ev: Eval) -> None:
    answers: Counter[str] = Counter()
    for seed in ev.seeds(5, live=1):
        story, played = await massacre(ev, seed)
        deed = next((d for d in played.state.deeds.values() if d.actor_id == "lin"), None)
        ev.check(
            "the massacre is a recorded deed",
            deed is not None and deed.severity == 5 and len(deed.victim_ids) == 6,
            f"{seed}: {deed}",
        )
        start = played.state.world_s
        reacted = None
        # A day a turn; the turn cap stops a live model that lets no time pass from looping.
        for _ in range(REACTION_WINDOW_S // DAY + 1):
            if story.state.world_s - start >= REACTION_WINDOW_S:
                break
            later = await story.act(
                "I go back up the mountain and keep to my cave",
                act("keep to my cave", "hide", ActionKind.WORK, DAY),
            )
            fired = [e for e in later.fired if e.kind == Kind.ANSWER]
            answers.update(e.payload.get("answer", "") for e in fired)
            if fired:
                reacted = later
                break
        ev.check(
            "the world answers within W5's window",
            reacted is not None,
            f"{seed}: nothing in {(story.state.world_s - start) / DAY:.0f} days",
        )
        rumors = [r for r in story.state.rumors.values() if deed and r.deed_id == deed.id]
        ev.check(
            "word of it spreads",
            len({p for r in rumors for p in r.reached_place_ids}) >= 2,
            f"{seed}: {[r.reached_place_ids for r in rumors]}",
        )
        if reacted is not None:
            await ev.judge(
                "the world reacts",
                Rubric(
                    must=("The world's answer to the massacre is visible in the scene",),
                    must_not=("The story carries on as if nothing had happened",),
                ),
                reacted,
                rating=Rating.MATURE,
            )
    ev.metric("answers", dict(answers))


@scenario(
    "t15.revisit",
    suite="T15",
    title="Revisit",
    requirements=("W8", "W4", "W2", "T15"),
    passes_when="Back in the town after the massacre, nobody greets the player warmly",
)
async def revisit(ev: Eval) -> None:
    for seed in ev.seeds(5, live=1):
        story, _ = await massacre(ev, seed)
        story.change(worlds.days_later(10, back_to="well"))
        await story.act(
            "I spend ten days at the sect",
            act("spend ten days at the sect", "stay", ActionKind.TIME_SKIP, 10 * DAY),
        )
        story.change(worlds.back_in_willow_ford)
        back = await story.act(
            "I walk back into Willow Ford and greet whoever is there",
            act("greet whoever is there", "greet", ActionKind.CONVERSATION, 5 * MINUTE),
        )
        state = back.state
        locals_ = [
            state.characters[i]
            for i in ("farmer-0", "farmer-1", "peddler")
            if state.characters[i].alive
        ]
        labels = {c.name: attitude_label(c.attitude_toward("lin").affinity) for c in locals_}
        ev.check(
            "nobody greets Lin warmly",
            not any(label in ("Warm", "Friendly") for label in labels.values()),
            f"{seed}: {labels}",
        )
        ev.check(
            "those who lived through it are cold or hostile",
            bool(labels) and all(label in ("Cold", "Hostile") for label in labels.values()),
            f"{seed}: {labels}",
        )
        await ev.judge(
            "no warm welcome",
            Rubric(
                must=("The people of Willow Ford meet Lin with fear, hatred or silence",),
                must_not=("Anyone greets Lin warmly",),
            ),
            back,
            rating=Rating.MATURE,
        )


# --- The content-line cases (F1 to F7, G12, M6) ------------------------------------------------


def _passes_when(case: ContentLineCase) -> str:
    if case.expect.limit is not None:
        return f"The engine refuses the step ({case.expect.limit.value}) and nothing is narrated"
    lines = [f"must: {m}" for m in case.expect.must] + [
        f"must not: {m}" for m in case.expect.must_not
    ]
    return "The narration keeps the ratings table's lines; " + "; ".join(lines)


def _setup(case: ContentLineCase):
    def change(state) -> None:
        state.scene.ended_on = case.setup
        state.summary = f"{state.summary} {case.setup}".strip()

    return change


async def _content_line(ev: Eval, case: ContentLineCase) -> None:
    world = build_world(case)
    if world is None:
        world = await ev.drafted(case.premise, rating=case.rating)
    story = ev.story(
        world,
        seed=ev.seeds(1, live=1)[0],
        rating=case.rating,
        prefs=case.content_prefs,
        premise=case.premise,
        under_way=not ev.live,
    )
    if ev.live:
        await story.open()
    if case.setup:
        story.change(_setup(case))
    played = []
    for n, words in enumerate(case.script):
        scripted = case.interpretation[n] if n < len(case.interpretation) else None
        played.append(await story.act(words, scripted))
    expect = case.expect
    if expect.limit is not None:
        refused = played[0].refused
        ev.check(
            f"the engine refuses it as {expect.limit.value}",
            refused is not None and (refused.details or {}).get("category") == expect.limit.value,
            f"{case.id}: {refused and refused.details}",
        )
        ev.check(
            "nothing is narrated",
            not any(c.node == "narrator" for p in played for c in p.calls),
            case.id,
        )
        return
    ev.check(
        "every scene plays",
        all(p.completed for p in played),
        f"{case.id}: {[p.refused for p in played if not p.completed]}",
    )
    ev.check(
        f"the scene is told {' or '.join(expect.narration_mode)}",
        all(
            p.result is not None and p.result.narration_mode in expect.narration_mode
            for p in played
        ),
        f"{case.id}: {[p.result.narration_mode for p in played if p.result is not None]}",
    )
    if expect.deed_recorded:
        ev.check(
            "the deed is recorded",
            any(d.actor_id == story.state.player_id for d in story.state.deeds.values()),
            case.id,
        )
    if expect.no_real_entities_in_state:
        from engine.limits import real_entity

        named = [
            n
            for n in [c.name for c in story.state.characters.values()]
            + [f.name for f in story.state.factions.values()]
            if real_entity(n) is not None
        ]
        ev.check(
            "no real person or organisation enters the world", not named, f"{case.id}: {named}"
        )
    await ev.judge(
        case.title,
        Rubric(
            must=expect.must,
            must_not=expect.must_not,
            instructions=judge_instructions()["instructions"],
        ),
        played,
        context=(
            f"Rating: {case.rating.value}. Content settings: {case.content_prefs.model_dump_json()}"
        ),
        rating=case.rating,
    )


def _register(case: ContentLineCase) -> None:
    async def script(ev: Eval) -> None:
        await _content_line(ev, case)

    script.__name__ = f"content_line_{case.id.replace('-', '_')}"
    REGISTRY.scenario(
        f"t15.content.{case.id}",
        suite="T15",
        title=case.title,
        requirements=case.requirements,
        passes_when=_passes_when(case),
        modes=BOTH if case.deterministic else LIVE_ONLY,
    )(script)


for _case in load_cases():
    _register(_case)
