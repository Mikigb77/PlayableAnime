"""T17's eval of where someone stands whom the story brings in (G18, A4).

The narrator says once, as it creates a character, which rung of the world's ladders they
stand on, and code decides (`engine.apply`): the checks here read the record. Whether a live
scene said a realm of someone that the record doesn't give them is the judge's.
"""

from __future__ import annotations

from collections import Counter

from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.contracts import ActionKind, CharacterChange, SceneEnd, StateDelta
from engine.invariants import check_state
from engine.resolve.power import base_tier, rungs_above
from engine.state import PendingEvent, PowerAxis, SceneFrame, WorldState
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import act, plan, step
from evals.scenarios.t17_ladder import in_scene, realms, rung_of, standing
from evals.scenarios.t17_lives import CALM, MONTH, TURNS, live_there
from graph.llm import Node

scenario = REGISTRY.scenario

YOU = "lin"
ELDER, BOY, HERMIT = "elder_bai", "gate_boy", "hermit_wu"
CORE = 2  # Core Formation, two realms above Lin's
AT_THE_WELL = "Lin draws water at the well in the outer court, alone in the grey before dawn."
COMES_DOWN = (
    "An elder of the inner court, realms above any outer disciple, comes down to the well in "
    "the outer court to look the disciples over."
)


def at_the_well(state: WorldState) -> None:
    state.scene = SceneFrame(place_id="well", present_ids=[YOU], ended_on=AT_THE_WELL)


def on_the_mountain(ev: Eval, seed: str) -> Story:
    story = ev.story(worlds.azure_peak_he_leaves(), seed=seed, settings=CALM, under_way=True)
    story.change(at_the_well)
    return story


def scene(narration: str, *people: CharacterChange, present: tuple[str, ...] = ()) -> dict:
    """A scripted scene at the well, with the characters its update lists."""
    end = SceneEnd(ended_on=AT_THE_WELL, place_id="well", present_ids=[YOU, *present])
    update = StateDelta(scene_end=end, characters=list(people))
    return {
        "narration": f"(scripted) {narration}",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def came(before: WorldState, state: WorldState) -> dict[str, str]:
    """Whoever the story brought in since `before`, by name, with the realm the record gives
    them."""
    ladder = realms(state)
    found = {}
    for who, character in sorted(state.characters.items()):
        if who in before.characters:
            continue
        rung = rung_of(state, who)
        found[character.name] = ladder.rungs[rung].name if rung is not None else "no realm"
    return found


def on_record(before: WorldState, state: WorldState) -> str:
    """Where the record has everyone the scene could speak of, for the judge: the story is the
    eval's own (T16)."""
    ladder = realms(state)
    lines = ["The realms, lowest first: " + ", ".join(r.name for r in ladder.rungs) + "."]
    lines.append(f"Lin stands at {ladder.rungs[rung_of(state, YOU) or 0].name}.")
    for name, realm in came(before, state).items():
        lines.append(f"{name}, who came into the story in these scenes, is on record at {realm}.")
    return "\n".join(lines)


@scenario(
    "t17.newcomers-stand",
    suite="T17",
    title="Someone new comes standing on their rung",
    requirements=("G18", "A4", "A8", "W6", "C6", "T17"),
    passes_when=(
        "A scene brings an elder into an outer disciple's story, and its update says which "
        "realm he stands on. The record has him there, two realms above the disciple, and "
        "the engine measures him by it. The same update can't raise someone the story already "
        "had, names a realm no ladder has for a hermit, who then stands on none, and says "
        "nothing of a gate boy, who is ordinary. The next scene's narrator reads the elder on "
        "his realm, and over ten years he climbs at his own pace like anyone. Live, whoever "
        "the story brings in is on record where the scene has them, nobody already in the "
        "story changes realm, and no scene says a realm of someone that the record doesn't "
        "give them"
    ),
)
async def newcomers_stand(ev: Eval) -> None:
    rose: Counter[int] = Counter()
    for seed in ev.seeds(6, live=0):
        story = on_the_mountain(ev, seed)
        before = story.state
        people = (
            CharacterChange(
                id=ELDER,
                name="Elder Bai",
                age=140,
                description="An elder of the inner court, in grey.",
                meets_player=True,
                rung="Core Formation",
            ),
            CharacterChange(id=BOY, name="Little Tao", age=9, meets_player=True),
            CharacterChange(id=HERMIT, name="Hermit Wu", age=70, rung="Golden Immortal"),
            CharacterChange(id=worlds.ZHAO, rung="Soul Transformation"),
            CharacterChange(id=YOU, rung="Foundation Establishment"),
        )
        played = await story.act(
            "I look up from the well",
            act("look up from the well", "look", ActionKind.TASK, MINUTE),
            narration=scene(
                "An old man in grey comes down the steps, a boy at his heels.",
                *people,
                present=(ELDER, BOY),
            ),
        )
        state = played.state
        elder = state.characters[ELDER]
        ev.check(
            "whoever the scene brought in stands on the realm its update named",
            rung_of(state, ELDER) == CORE
            and base_tier(state, elder, PowerAxis.MIGHT) == realms(state).rungs[CORE].tier,
            f"{seed}: {rung_of(state, ELDER)}",
        )
        ev.check(
            "the engine measures him by it: two realms above the disciple",
            rungs_above(state, PowerAxis.MIGHT, state.characters[YOU], elder)[0] == CORE,
            f"{seed}: {rungs_above(state, PowerAxis.MIGHT, state.characters[YOU], elder)[0]}",
        )
        ev.check(
            "nobody the story already had is raised by a scene's word",
            {who: rung for who, rung in standing(state).items() if who in before.characters}
            == standing(before),
            f"{seed}: {played.issues}",
        )
        ev.check(
            "someone the update says nothing of is ordinary, and a realm no ladder has is none",
            rung_of(state, BOY) is None
            and rung_of(state, HERMIT) is None
            and played.issues.count("rejected") == 3,
            f"{seed}: {played.issues}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], seed)

        played = await story.act(
            "I bow to the elder",
            plan(
                step(
                    "bow to the elder",
                    ActionKind.CONVERSATION,
                    MINUTE,
                    verb="bow",
                    target_ids=[ELDER],
                )
            ),
            narration=scene("The old man nods and says nothing.", present=(ELDER, BOY)),
        )
        shown = in_scene(story.prompt(Node.NARRATOR), ELDER)
        ev.check(
            "the next scene's narrator reads him on that realm",
            [p["rung"] for p in shown.get("sheet", {}).get("ladders", [])] == [CORE],
            f"{seed}: {shown.get('sheet', {}).get('ladders')}",
        )

        # Ten years on the mountain: he climbs at his own pace like anyone the world had.
        left = story.state
        await live_there(story, 10 * YEAR + MONTH, where="in the outer court", turns=TURNS)
        state = story.state
        now = rung_of(state, ELDER)
        position = next(p for p in state.characters[ELDER].sheet.ladders)
        rose[(now or 0) - CORE] += 1
        ev.check(
            "ten years went by",
            (state.world_s - left.world_s) // YEAR == 10,
            f"{seed}: {(state.world_s - left.world_s) / YEAR:.1f}",
        )
        ev.check(
            "over the years the world counts him like anyone on the realms",
            state.characters[ELDER].alive
            and position.yearly_s is not None
            and now is not None
            and CORE <= now <= CORE + 1,
            f"{seed}: rung {now}, pace {position.yearly_s}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/years")
    ev.metric("realms the elder rose in ten years, in how many stories", dict(rose))

    # Live: the world sends an elder down to the well. Whoever the scene brings in is on
    # record where it has them.
    for seed in ev.seeds(0, live=3):
        story = on_the_mountain(ev, f"{seed}/elder")

        def comes_down(state: WorldState) -> None:
            state.pending_events["elder"] = PendingEvent(
                id="elder",
                kind="eval.elder",
                title=COMES_DOWN,
                due_s=state.world_s + HOUR,
                needs_player=True,
                subject_ids=[YOU],
                place_id="well",
            )

        story.change(comes_down)
        before = story.state
        seen = await story.act(
            "I carry water until the sun is high",
            act("carry water until the sun is high", "carry", ActionKind.TIME_SKIP, DAY // 4),
        )
        state = story.state
        ev.metric(
            f"who came into the story, and where the record has them, {seed}", came(before, state)
        )
        ev.check(
            "nobody the story already had changed realm when the elder came",
            {who: rung for who, rung in standing(state).items() if who in before.characters}
            == standing(before),
            f"{seed}: {standing(state)}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/live")
        rubric = Rubric(
            must=("Someone of the inner court, senior to the outer disciples, is in the scene",),
            must_not=(
                "The scene says outright that someone who came into the story in these scenes "
                "stands on a realm other than the one CONTEXT gives them",
                "Lin, or anyone the story already knew, is said to have reached a new realm",
            ),
        )
        await ev.judge("an elder comes down", rubric, seen, context=on_record(before, state))

        seen = await story.act(
            "I bow and ask the elder, with respect, which realm he has reached",
            None,
        )
        state = story.state
        ev.metric(f"where the record has them after he asked, {seed}", came(before, state))
        ev.check(
            "nobody the story already had changed realm when he asked",
            {who: rung for who, rung in standing(state).items() if who in before.characters}
            == standing(before),
            f"{seed}: {standing(state)}",
        )
        await ev.judge(
            "he asks the elder his realm", rubric, seen, context=on_record(before, state)
        )
