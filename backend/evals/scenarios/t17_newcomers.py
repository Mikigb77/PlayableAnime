"""T17's evals of someone the story brings in: where they stand (G18, A4) and how old they
are (F3).

The narrator says once, as it creates a character, which rung of the world's ladders they
stand on, and code decides (`engine.apply`): the checks here read the record. Whether a live
scene said a realm of someone that the record doesn't give them is the judge's. Their age is
asked by the same form, since a romance is only with someone whose age the record has.
"""

from __future__ import annotations

from collections import Counter

from engine import limits
from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.contracts import ActionKind, CharacterChange, Intent, SceneEnd, StateDelta
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
    for number, seed in enumerate(ev.seeds(6, live=0)):
        story = on_the_mountain(ev, seed)
        before = story.state
        # In every other story the update leaves the elder's name out, as a live one did: the
        # scene calls him by it (C1).
        nameless = bool(number % 2)
        people = (
            CharacterChange(
                id=ELDER,
                name=None if nameless else "Elder Bai",
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
                "Elder Bai comes down the steps in grey, a boy at his heels.",
                *people,
                present=(ELDER, BOY),
            ),
        )
        state = played.state
        elder = state.characters[ELDER]
        ev.check(
            "an elder the update left nameless is on record by the name the scene calls him",
            elder.name == "Elder Bai" and ("named_by_scene" in played.issues) == nameless,
            f"{seed}: {elder.name}, {played.issues}",
        )
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
            "the next scene's narrator reads him on that realm, by its name",
            [p["rung"] for p in shown.get("sheet", {}).get("ladders", [])] == ["Core Formation"],
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
        arrival = seen
        ev.check(
            "nobody the story already had changed realm when the elder came",
            {who: rung for who, rung in standing(state).items() if who in before.characters}
            == standing(before),
            f"{seed}: {standing(state)}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/live")
        never = (
            "The scene says outright that someone who came into the story in these scenes "
            "stands on a realm other than the one CONTEXT gives them",
            "Lin, or anyone the story already knew, is said to have reached a new realm",
        )
        rubric = Rubric(
            must=("Someone of the inner court, senior to the outer disciples, is in the scene",),
            must_not=never,
        )
        await ev.judge("an elder comes down", rubric, seen, context=on_record(before, state))

        seen = await story.act(
            "I bow and ask the elder, with respect, which realm he has reached",
            None,
        )
        state = story.state
        ev.metric(f"where the record has them after he asked, {seed}", came(before, state))
        higher = [
            who
            for who in state.characters
            if who not in before.characters and (rung_of(state, who) or 0) > 0
        ]
        # A scene may leave the elder without a name, and nobody nameless is on record (C1):
        # once the character has spoken to him, the record has him. The story is the eval's
        # own, so a check that fails says what the scene told (T16).
        ev.check(
            "someone the story brought in is on record on a realm above the outer disciples'",
            bool(higher),
            f"{seed}: {came(before, state)}; the arrival: {arrival.findings}; asked: "
            f"{seen.findings}; told: {seen.streamed}",
        )
        ev.check(
            "nobody the story already had changed realm when he asked",
            {who: rung for who, rung in standing(state).items() if who in before.characters}
            == standing(before),
            f"{seed}: {standing(state)}",
        )
        asked = Rubric(
            must=("Lin speaks to an elder, someone senior to the outer disciples",),
            must_not=never,
        )
        await ev.judge("he asks the elder his realm", asked, seen, context=on_record(before, state))


TOMAS, CLARA, HANNE = "tomas", "clara", "old_hanne"
AT_THE_GATE = "Tomas stands at his gate, the lane empty either way."
COMES_BY = (
    "A widow who keeps the inn at Millbrook, a grown woman Tomas has never met, comes up the "
    "lane to buy eggs and stops at his gate to talk."
)
KISS = "I take Clara's hand and kiss her"


def at_the_gate(narration: str, *people: CharacterChange, present: tuple[str, ...] = ()) -> dict:
    """A scripted scene at Tomas's gate, with the characters its update lists."""
    end = SceneEnd(ended_on=AT_THE_GATE, place_id="farm", present_ids=[TOMAS, *present])
    update = StateDelta(scene_end=end, characters=list(people))
    return {
        "narration": f"(scripted) {narration}",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def kiss(who: str, name: str) -> Intent:
    return plan(step(f"kiss {name}", ActionKind.EXCHANGE, MINUTE, verb="kiss", target_ids=[who]))


def alone_at_the_gate(state: WorldState) -> None:
    """Tomas with nobody at his gate: whoever the scene has is someone it brings in."""
    state.characters[worlds.MARA].location_id = "village"
    state.scene = SceneFrame(place_id="farm", present_ids=[TOMAS], ended_on=AT_THE_GATE)


def knows_no_woman(state: WorldState) -> None:
    """Nobody on record for a scene to take the widow's name from. On the real models
    (2026-11-14) one scene called her Mara Voss, the miller's daughter the record has in the
    village: the record kept her there (W10), so nobody new came into the story, and a check
    of ages had nobody to read."""
    del state.characters[worlds.MARA]


@scenario(
    "t17.newcomers-come-with-an-age",
    suite="T17",
    title="Someone new comes with their age",
    requirements=("F3", "C1", "W10", "T17"),
    passes_when=(
        "A scene brings two women to a farmer's gate. The one whose change gives her age is on "
        "record with it, and a kiss with her the next turn plays. The other's change gives 0, "
        "the number a model fills a form with: she has no age on record, a kiss with her never "
        "plays, and the next scene she is in is asked for her age and gives it, with nothing "
        "refused. A scene's age for someone the record has one for changes nothing. Live, the "
        "world sends a widow to the gate: whoever the scene brings in is on record with an "
        "age, and a kiss with her is not refused as one with a minor"
    ),
    notes=(
        "The first live play to bring someone in (2026-11-14) put 'the widow, a weary woman "
        "named Clara' on record with no age, as Gemini leaves out what a form doesn't require, "
        "and the kiss the next turn was refused as one with a minor, for good. The form now "
        "asks everyone's age (`CharacterChange`), and a scene with someone whose age the "
        "record lacks reads that it is wanted."
    ),
)
async def newcomers_come_with_an_age(ev: Eval) -> None:
    for seed in ev.seeds(2, live=0):
        story = ev.story(worlds.millers_daughter(), seed=seed, settings=CALM, under_way=True)
        story.change(alone_at_the_gate)
        was = story.state.characters[TOMAS].age
        people = (
            CharacterChange(
                id=CLARA,
                name="Clara",
                age=41,
                description="The widow who keeps the inn at Millbrook, weary and dry.",
                location_id="farm",
                meets_player=True,
            ),
            CharacterChange(id=HANNE, name="Hanne", age=0, location_id="farm", meets_player=True),
            CharacterChange(id=TOMAS, age=(was or 0) + 7),
        )
        played = await story.act(
            "I lean on the gate and greet them",
            act("greet the two women", "greet", ActionKind.CONVERSATION, MINUTE),
            narration=at_the_gate(
                "Two women come up the lane with egg baskets: Clara, who keeps the inn, and Hanne.",
                *people,
                present=(CLARA, HANNE),
            ),
        )
        state = played.state
        ev.check(
            "someone a scene brings in is on record with the age its update gave",
            state.characters[CLARA].age == 41 and limits.is_adult(state.characters[CLARA]),
            f"{seed}: {state.characters[CLARA].age}",
        )
        ev.check(
            "a 0 is no age, and a scene's age for someone on record changes nothing",
            state.characters[HANNE].age is None
            and state.characters[TOMAS].age == was
            and "rejected" not in played.issues,
            f"{seed}: {state.characters[HANNE].age}, {state.characters[TOMAS].age}, "
            f"{played.issues}",
        )

        kissed = await story.act(
            KISS,
            kiss(CLARA, "Clara"),
            narration=at_the_gate("She lets him.", present=(CLARA, HANNE)),
        )
        ev.check(
            "a kiss with her the next turn plays",
            kissed.refused is None,
            f"{seed}: {kissed.refused!r}",
        )
        held = await story.act("I kiss Hanne", kiss(HANNE, "Hanne"))
        ev.check(
            "a kiss with someone whose age the record lacks never plays",
            held.refused is not None and tuple(held.refused.categories) == ("minor",),
            f"{seed}: {held.refused!r}",
        )

        asked = await story.act(
            "I ask Hanne how the hens are laying",
            plan(
                step(
                    "ask Hanne about her hens",
                    ActionKind.CONVERSATION,
                    MINUTE,
                    verb="ask",
                    target_ids=[HANNE],
                )
            ),
            narration=at_the_gate(
                "Badly, she says.", CharacterChange(id=HANNE, age=63), present=(CLARA, HANNE)
            ),
        )
        shown = in_scene(story.prompt(Node.NARRATOR), HANNE)
        ev.check(
            "the next scene she is in is asked for her age",
            "not on record" in str(shown.get("age")),
            f"{seed}: {shown.get('age')}",
        )
        ev.check(
            "and the record has it from then on, with nothing refused",
            asked.state.characters[HANNE].age == 63 and "rejected" not in asked.issues,
            f"{seed}: {asked.state.characters[HANNE].age}, {asked.issues}",
        )
        ev.check("the record holds together (C1)", check_state(asked.state) == [], seed)

    # Live: the world sends a widow to the gate. Whoever the scene brings in has an age.
    for seed in ev.seeds(0, live=2):
        story = ev.story(
            worlds.millers_daughter(), seed=f"{seed}/widow", settings=CALM, under_way=True
        )
        story.change(alone_at_the_gate)
        story.change(knows_no_woman)

        def comes_by(state: WorldState) -> None:
            state.pending_events["widow"] = PendingEvent(
                id="widow",
                kind="eval.widow",
                title=COMES_BY,
                due_s=state.world_s + HOUR,
                needs_player=True,
                subject_ids=[TOMAS],
                place_id="farm",
            )

        story.change(comes_by)
        before = story.state
        seen = await story.act(
            "I mend the gate until midday",
            act("mend the gate until midday", "mend", ActionKind.TIME_SKIP, DAY // 4),
        )
        spoke = await story.act("I ask her name, and tell her mine", None)
        state = story.state
        new = {
            c.name: c.age
            for who, c in sorted(state.characters.items())
            if who not in before.characters
        }
        ev.metric(f"who came into the story, and the age on record, {seed}", new)
        # The story is the eval's own, so a check that fails says what the scene told (T16).
        ev.check(
            "whoever the story brought in is on record with an age",
            bool(new) and all(age for age in new.values()),
            f"{seed}: {new}; the arrival: {seen.findings}; asked: {spoke.findings}; told: "
            f"{spoke.streamed}",
        )
        kissed = await story.act("I take her hand and kiss her", None)
        ev.check(
            "a kiss with her is not refused as one with a minor",
            kissed.refused is None or "minor" not in kissed.refused.categories,
            f"{seed}: {kissed.refused!r}; on record: {new}",
        )
        ev.check("the record holds together (C1)", check_state(story.state) == [], f"{seed}/live")
