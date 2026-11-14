"""T17's eval of a ladder that grows past its top in the middle of a story (G18, G7).

The story names a rung above a ladder's highest and code decides whether it holds
(`engine.path.beyond_problem`, `engine.apply`): the checks here read the record. Whether a
live scene named a realm the record doesn't hold is the judge's.
"""

from __future__ import annotations

import json
from collections import Counter

from engine import path
from engine.base import DAY, HOUR, MINUTE, YEAR
from engine.contracts import (
    ActionKind,
    CharacterChange,
    GrowthKind,
    Intent,
    NewRung,
    OutcomeClass,
    SceneEnd,
    StateDelta,
    Training,
)
from engine.invariants import check_state
from engine.resolve.power import rungs_above
from engine.resolve.powers import growth
from engine.state import (
    Character,
    CharacterSheet,
    LadderPosition,
    PendingEvent,
    PowerAxis,
    PowerLadder,
    SceneFrame,
    WorldState,
)
from engine.visibility import status_view
from engine.world import old_age
from evals import worlds
from evals.judge import Rubric
from evals.runner import Eval, Played, Story
from evals.scenario import REGISTRY
from evals.scenarios.common import act, facts, plan, step
from evals.scenarios.t17_lives import CALM, MONTH, TURNS, live_there
from graph.llm import Node
from graph.turn.check import RUNG_UNTOLD

scenario = REGISTRY.scenario

YOU = "lin"
TOP = 4  # Soul Transformation, the highest realm the mountain's world started with
VOID, INTEGRATION = "Void Refinement", "Body Integration"
ENVOY = "envoy_shen"
CEILING = "realm-ceiling"  # the open rule that nobody is known to have passed the top
PATRIARCH = "patriarch_yun"
ON_THE_SUMMIT = "Lin sits alone on the summit of Azure Peak, at the height of his realm."
REACH = "I sit in seclusion on the summit and reach for whatever lies above my realm"
BARRIER = "The barrier above him does not give."
GLIMPSE = (
    "The barrier does not give. Yet for one breath Lin feels what lies past it, vast and "
    f"still, and knows the name the oldest texts gave it: {VOID}."
)
ASK = "I rise, greet the one who came out of the sky, and ask their name and their realm"
RIFT = (
    "The sky splits over the summit and a stranger steps down out of it, calm, unhurried, and "
    "stronger than anyone this world has known: an envoy of a realm above Soul Transformation."
)


def on_the_summit(state: WorldState) -> None:
    """Lin is alone at the top of the mountain."""
    state.scene = SceneFrame(place_id="well", present_ids=[YOU], ended_on=ON_THE_SUMMIT)


def at_the_top(ev: Eval, seed: str, *, rung: int = TOP) -> Story:
    world = worlds.azure_peak_he_leaves(rung=rung)
    story = ev.story(world, seed=seed, settings=CALM, under_way=True)
    story.change(on_the_summit)
    return story


def realms(state: WorldState) -> PowerLadder:
    ladder = state.bible.ladder("realms")
    assert ladder is not None
    return ladder


def rung_of(state: WorldState, who: str) -> int | None:
    found = next((p for p in state.characters[who].sheet.ladders if p.ladder_id == "realms"), None)
    return found.rung if found is not None else None


def standing(state: WorldState) -> dict[str, int | None]:
    """The realm of everyone on record."""
    return {who: rung_of(state, who) for who in sorted(state.characters)}


def reach(*, against_the_rule: bool = False) -> Intent:
    """Setting out to break through to whatever lies above his realm. A model that reads the
    player's words may file it `against_the_rule` that nobody is known to have passed the
    top, as the live one did on the first run of this eval."""
    return plan(
        step(
            "reach in seclusion for the realm above his own",
            ActionKind.TASK,
            12 * HOUR,
            verb="cultivate",
            training=Training(
                kind=GrowthKind.BREAKTHROUGH,
                what="the realm above",
                ladder_id="realms",
                attempt=True,
            ),
            **({"facts": facts(against_rule_ids=[CEILING])} if against_the_rule else {}),
        )
    )


def scene(
    narration: str,
    *,
    rungs: list[NewRung] | None = None,
    people: list[CharacterChange] | None = None,
    present: tuple[str, ...] = (),
    above: str = "",
) -> dict:
    """A scripted scene on the summit, with what its update lists and what it answers where
    its form asks for the realm `above` the top (`NarratorOutput.rung_above`)."""
    end = SceneEnd(ended_on=ON_THE_SUMMIT, place_id="well", present_ids=[YOU, *present])
    update = StateDelta(scene_end=end, rungs=rungs or [], characters=people or [])
    return {
        "rung_above": above,
        "narration": f"(scripted) {narration}",
        "suggestions": [],
        "update": update.model_dump(mode="json"),
    }


def naming(narration: str, *, listed: bool, name: str = VOID) -> dict:
    """A scene that proposes a realm above the top: `listed` under its update, as the engine's
    contract has it, or else as its answer to the form's first question."""
    if listed:
        return scene(narration, rungs=[void(name=name)])
    return scene(narration, above=name)


def void(*, name: str = VOID, stands: tuple[str, ...] = ()) -> NewRung:
    return NewRung(
        ladder_id="realms",
        name=name,
        description="A realm past the one the world took for its last.",
        stands=list(stands),
    )


def outcome(brief: str) -> dict:
    """The first step of a brief's OUTCOME."""
    if "## OUTCOME\n" not in brief:
        return {}  # a live run keeps no brief
    told = json.loads(brief.split("## OUTCOME\n", 1)[1].split("\n\n## ", 1)[0])
    return told["steps"][0] if told.get("steps") else {}


def open_above(brief: str) -> str:
    """What WORLD tells the narrator on the realms about growing past their top, if anything."""
    if "## WORLD\n" not in brief:
        return ""
    told = json.loads(brief.split("## WORLD\n", 1)[1].split("\n\n## ", 1)[0])
    return next((ladder.get("above", "") for ladder in told.get("ladders", [])), "")


def rules(state: WorldState) -> list[str]:
    return [rule.id for rule in state.bible.rules]


def in_scene(brief: str, who: str) -> dict:
    if "## SCENE\n" not in brief:
        return {}
    told = json.loads(brief.split("## SCENE\n", 1)[1].split("\n\n## ", 1)[0])
    return next((p for p in told.get("present", []) if p["id"] == who), {})


def above(state: WorldState) -> list[tuple[str, bool]]:
    """The realms above his own on the character's screen, each with whether it is confirmed."""
    shown = next(iter(status_view(state).sheet.paths), None)
    return [(rung.name, rung.known) for rung in shown.above] if shown is not None else []


def at_his_peak(state: WorldState) -> None:
    """The eval's shortcut for the months that fill a rank (`t17.breakthrough` plays them)."""
    lin = state.characters[YOU].sheet
    lin.ladders = [
        LadderPosition(ladder_id=p.ladder_id, rung=p.rung, stage="peak") for p in lin.ladders
    ]
    lin.practice = [p for p in lin.practice if p.key != "ladder:realms"]


def a_young_patriarch(state: WorldState) -> None:
    """Someone else at the top of the world's realms, and young for it: by their own record
    the next realm is some fifty years' work for them."""
    state.characters[PATRIARCH] = Character(
        id=PATRIARCH,
        name="Patriarch Yun",
        age=60,
        description="The youngest ever to reach the mountain's highest realm.",
        location_id="well",
        known_by=[YOU],
        met_by=[YOU],
        sheet=CharacterSheet(ladders=[LadderPosition(ladder_id="realms", rung=TOP)]),
    )


def on_record(state: WorldState) -> str:
    """The realms the record holds and who stands above the old top, for the judge: the
    story is the eval's own (T16)."""
    ladder = realms(state)
    lines = ["The realms on record, lowest first: " + ", ".join(r.name for r in ladder.rungs) + "."]
    lines.append(f"Lin stands at {ladder.rungs[rung_of(state, YOU) or 0].name}.")
    for who, rung in standing(state).items():
        if who != YOU and rung is not None and rung > TOP:
            name = state.characters[who].name
            lines.append(f"{name} stands at {ladder.rungs[rung].name}.")
    return "\n".join(lines)


def told_above(state: WorldState) -> list[str]:
    """The realms the story added above the one the world started with as its highest."""
    return [rung.name for rung in realms(state).rungs[TOP + 1 :]]


@scenario(
    "t17.ladder-grows",
    suite="T17",
    title="The ladder grows past its top",
    requirements=("G18", "G7", "G19", "A4", "W6", "C6", "T17"),
    passes_when=(
        "A cultivator on his world's highest realm reaches for what lies above it. The climb "
        "stops there, whether it is filed as a breakthrough or against the world's open rule "
        "that nobody has passed that realm, and the narrator is told that the ladder is open, "
        "beside the step and on the ladder itself. A rung the update lists and the scene "
        "never named changes nothing. Once a scene names a realm above the top and lists it, "
        "the ladder has it, as far above the last realm as the realms lie apart, with no way "
        "there listed and no lifespan, and the open rule that held the ladder is struck; he "
        "has heard of it from that scene, stands where he stood, and his rank fills toward it "
        "at twice the effort of the realm before. A second realm above that one is refused "
        "until someone has climbed to the first, and holds once he has broken through. Beings "
        "the scene brings in can come standing on the new realm, a rung above him and beyond "
        "old age, and it is confirmed before them; nobody already on record is lifted onto "
        "it, and over a hundred years whoever else stands on it climbed there, as a patriarch "
        "young for the old top does in some stories and not in others. A cultivator who has "
        "not heard of the highest realm can be told of nothing above it, and a rule that "
        "never changes holds a ladder where it is. Live, the scene of his reach names a realm "
        "above the top and the ladder has it, though he stands where he stood, and when an "
        "envoy from above the top arrives, the scene names the envoy's realm and the record "
        "has the envoy on it"
    ),
)
async def ladder_grows(ev: Eval) -> None:
    tries: Counter[int] = Counter()
    reached: Counter[int] = Counter()
    for number, seed in enumerate(ev.seeds(6, live=0)):
        # He reaches past the top, and the scene has nothing to show him. In every other
        # story the reach is filed against the world's open rule, as a live model may.
        filed = number % 2 == 1
        story = at_the_top(ev, seed)
        first = realms(story.state)
        gap = path.above_tier(first)
        had = rules(story.state)
        played = await story.act(
            REACH, reach(against_the_rule=filed), narration=naming(BARRIER, listed=filed)
        )
        stopped = played.step(0)
        # An open rule filed against a climb is no wall (G19): the top of the ladder is what
        # stops it, whatever the reading filed.
        ev.check(
            "a climb stops on the highest realm, with the reason in the world's words",
            stopped.outcome_class is OutcomeClass.RULED_OUT
            and stopped.reason == growth.no_rung_above(first),
            f"{seed}: {stopped.outcome_class.value}, {stopped.reason}",
        )
        ev.check(
            "the narrator is told beside it to name what lies above, however it was filed",
            "rung_above" in outcome(story.prompt(Node.NARRATOR)).get("beyond", ""),
            f"{seed}: {outcome(story.prompt(Node.NARRATOR))}",
        )
        ev.check(
            "and reads on the ladder itself that it is open above its top",
            "rung_above" in open_above(story.prompt(Node.NARRATOR)),
            f"{seed}: {open_above(story.prompt(Node.NARRATOR))!r}",
        )
        ev.check(
            "a rung the scene never named changes nothing, listed or answered",
            len(realms(played.state).rungs) == TOP + 1 and RUNG_UNTOLD in played.issues,
            f"{seed}: {told_above(played.state)}, {played.issues}",
        )

        # Again, and this time the scene names what lies above.
        played = await story.act(
            REACH, reach(against_the_rule=filed), narration=naming(GLIMPSE, listed=filed)
        )
        state = played.state
        ladder = realms(state)
        new = ladder.rungs[-1]
        ev.check(
            "a realm the scene named above the top is on the ladder from then on",
            told_above(state) == [VOID] and "rejected" not in played.issues,
            f"{seed}: {told_above(state)}, {played.issues}",
        )
        ev.check(
            "it stands as far above the last as the realms lie apart, with nothing made up",
            (new.tier, new.needs, new.lifespan_years) == (gap, [], None)
            and new.added_s is not None,
            f"{seed}: tier {new.tier} for {gap}, {new.needs}, {new.lifespan_years}",
        )
        ev.check(
            "he has heard of it from that scene, and stands where he stood",
            above(state) == [(VOID, False)]
            and rung_of(state, YOU) == TOP
            and "rung_heard" in played.issues,
            f"{seed}: {above(state)}, rung {rung_of(state, YOU)}",
        )
        ev.check(
            "the open rule that held the ladder there is struck, and no other (G7)",
            CEILING in had and rules(state) == [rule for rule in had if rule != CEILING],
            f"{seed}: {rules(state)}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], seed)

        # He works toward it by the standing rule, even filed against the rule that is gone,
        # and a realm above it is not yet the story's to tell.
        played = await story.act(
            REACH,
            reach(against_the_rule=filed),
            narration=scene(
                f"Past {VOID} he thinks he feels another shore: {INTEGRATION}.",
                rungs=[void(name=INTEGRATION)],
            ),
        )
        state = played.state
        rank = growth.rank_of(state.characters[YOU], realms(state))
        ev.check(
            "his rank fills toward it, at twice the effort of the realm before",
            played.step(0).outcome_class is OutcomeClass.CERTAIN
            and rank is not None
            and 0 < rank.effort_s < rank.need_s
            and rank.need_s == 2 * growth.rung_need_s(TOP)
            and "beyond" not in outcome(story.prompt(Node.NARRATOR))
            and not open_above(story.prompt(Node.NARRATOR)),
            f"{seed}: {played.step(0).reason}",
        )
        ev.check(
            "a realm above one nobody has climbed to is refused",
            told_above(state) == [VOID] and "rejected" in played.issues,
            f"{seed}: {told_above(state)}, {played.issues}",
        )

        # Months later his rank is full, and he throws for it until he stands there.
        attempts = 0
        while rung_of(story.state, YOU) == TOP and attempts < 12:
            story.change(at_his_peak)
            attempts += 1
            played = await story.act("I go into seclusion to break through", reach())
        tries[attempts] += 1
        state = story.state
        ev.check(
            "he climbs to it by his own throw, and the climb is on his sheet",
            rung_of(state, YOU) == TOP + 1 and path.climbed_to(state, VOID),
            f"{seed}: rung {rung_of(state, YOU)} after {attempts} attempts",
        )
        played = await story.act(
            "I sit on the summit and look past the realm I have reached",
            reach(),
            narration=scene(
                f"Past {VOID} there is another shore after all: {INTEGRATION}.",
                rungs=[void(name=INTEGRATION)],
            ),
        )
        state = played.state
        ev.check(
            "once someone has climbed to it the ladder can grow again",
            told_above(state) == [VOID, INTEGRATION]
            and realms(state).rungs[-1].tier == path.above_tier(ladder)
            and above(state) == [(INTEGRATION, False)],
            f"{seed}: {told_above(state)}, {above(state)}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/again")

        # Beings from beyond: the scene brings one in, standing on the new realm.
        story = at_the_top(ev, f"{seed}/envoy")
        story.change(a_young_patriarch)
        before = story.state
        envoy = CharacterChange(
            id=ENVOY,
            name="Envoy Shen",
            age=3000,
            description="A stranger out of the split sky, in robes no sect here wears.",
            meets_player=True,
        )
        arrival = f"The sky splits. A stranger steps out of it. “{VOID},” he says, of himself."
        if filed:
            # The update lists the realm, and under it who stands there.
            told = scene(
                arrival,
                rungs=[void(stands=(ENVOY, worlds.ELDER_MO, YOU))],
                people=[envoy],
                present=(ENVOY,),
            )
        else:
            # The scene answers the form's question, and each change says its own realm.
            said = [worlds.ELDER_MO, YOU]
            told = scene(
                arrival,
                above=VOID,
                people=[
                    envoy.model_copy(update={"rung": VOID}),
                    *(CharacterChange(id=who, rung=VOID) for who in said),
                ],
                present=(ENVOY,),
            )
        played = await story.act(
            "I watch the sky over the summit",
            act("watch the sky over the summit", "watch", ActionKind.TASK, 10 * MINUTE),
            narration=told,
        )
        state = played.state
        was = standing(before)
        ev.check(
            "whoever the scene brought in stands on the realm it named",
            rung_of(state, ENVOY) == TOP + 1 and told_above(state) == [VOID],
            f"{seed}: {standing(state).get(ENVOY)}, {told_above(state)}",
        )
        ev.check(
            "nobody already on record is lifted onto it",
            {who: rung for who, rung in standing(state).items() if who != ENVOY} == was
            and played.issues.count("rejected") == 2,
            f"{seed}: {played.issues}",
        )
        being = state.characters[ENVOY]
        ev.check(
            "they stand a rung above him, beyond old age",
            rungs_above(state, PowerAxis.MIGHT, state.characters[YOU], being)[0] == 1
            and old_age.open_ended(state, being),
            f"{seed}: {rungs_above(state, PowerAxis.MIGHT, state.characters[YOU], being)[0]}",
        )
        ev.check(
            "the realm is confirmed before them, on his screen",
            above(state) == [(VOID, True)]
            and [k.known_from for k in path.known(state, state.characters[YOU], realms(state))]
            == [ENVOY],
            f"{seed}: {above(state)}",
        )
        played = await story.act(
            "I bow to the stranger and ask where he comes from",
            plan(
                step(
                    "bow to the stranger and ask where he comes from",
                    ActionKind.CONVERSATION,
                    5 * MINUTE,
                    verb="ask",
                    target_ids=[ENVOY],
                )
            ),
            narration=scene("The stranger only smiles.", present=(ENVOY,)),
        )
        shown = in_scene(story.prompt(Node.NARRATOR), ENVOY)
        ev.check(
            "the next scene's narrator reads them on that realm",
            [p["rung"] for p in shown.get("sheet", {}).get("ladders", [])] == [VOID]
            and "added_s" not in story.prompt(Node.NARRATOR),
            f"{seed}: {shown.get('sheet', {}).get('ladders')}",
        )

        # A hundred years on the mountain: the world climbs toward it at its own pace.
        left = story.state
        await live_there(story, 100 * YEAR + MONTH, where="on the summit", turns=TURNS)
        state = story.state
        top = len(realms(state).rungs) - 1
        now = standing(state)
        there = [who for who, rung in now.items() if rung == top and who not in (ENVOY, YOU)]
        reached[len(there)] += 1
        ev.check(
            "a hundred years went by",
            (state.world_s - left.world_s) // YEAR == 100,
            f"{seed}: {(state.world_s - left.world_s) / YEAR:.1f}",
        )
        ev.check(
            "over a hundred years nobody passes the top, and the ladder gains nothing by itself",
            top == TOP + 1 and all(rung is None or rung <= top for rung in now.values()),
            f"{seed}: {now}",
        )
        ev.check(
            "whoever else stands on the new realm climbed there, with the reason on their sheet",
            all(
                any(
                    gain.what == VOID
                    and gain.source == GrowthKind.BREAKTHROUGH.value
                    and gain.reason
                    and gain.world_s > left.world_s
                    for gain in state.characters[who].sheet.growth
                )
                for who in there
            ),
            f"{seed}: {there}",
        )
        ev.check(
            "the being who came with it is still there, and never rose",
            state.characters[ENVOY].alive and now[ENVOY] == TOP + 1,
            f"{seed}: {now[ENVOY]}",
        )
        ev.check("the record holds together (C1)", check_state(state) == [], f"{seed}/century")

        # The story hasn't reached the top: Lin on the lowest realm has heard of nothing
        # above it, so the world's own realms come first.
        story = at_the_top(ev, f"{seed}/low", rung=0)
        played = await story.act(
            "I listen to the elders' talk at the well",
            act("listen to the elders' talk", "listen", ActionKind.TASK, 10 * MINUTE),
            narration=scene(f"“Above it all lies {VOID},” one mutters.", rungs=[void()]),
        )
        state = played.state
        ev.check(
            "a realm above a top he hasn't heard of is refused, and he has heard of nothing",
            told_above(state) == []
            and "rejected" in played.issues
            and state.characters[YOU].sheet.rungs_heard == [],
            f"{seed}: {told_above(state)}, {played.issues}",
        )

        # A rule that never changes holds the ladder where it is (G7).
        story = at_the_top(ev, f"{seed}/fixed")

        def fix(state: WorldState) -> None:
            next(r for r in state.bible.rules if r.id == "realm-ceiling").fixed = True

        story.change(fix)
        played = await story.act(REACH, reach(), narration=scene(GLIMPSE, rungs=[void()]))
        ev.check(
            "where a fixed rule ends the ladder, nothing goes above it and nobody is told it could",
            told_above(played.state) == []
            and "rejected" in played.issues
            and "beyond" not in outcome(story.prompt(Node.NARRATOR)),
            f"{seed}: {told_above(played.state)}, {played.issues}",
        )
    ev.metric("attempts it took him to reach the new realm, in how many stories", dict(tries))
    ev.metric("others on the new realm after a hundred years, in how many stories", dict(reached))

    # Live: he reaches past the top, and the reach shows him that a realm lies there. The
    # stories are the eval's own, so a check that fails says what the scene told (T16).
    for seed in ev.seeds(0, live=3):
        story = at_the_top(ev, f"{seed}/reach")
        seen = await story.act(REACH, reach())
        state = story.state
        named = told_above(state)
        ev.metric(f"realms told above the top when he reached, {seed}", named)
        ev.metric(f"told beside the outcome, {seed}", _stopped(seen))
        ev.check(
            "the scene of his reach names the realm above the top, and the ladder has it",
            len(named) == 1,
            f"{seed}: {named}, {_stopped(seen)}, {seen.findings}; told: {seen.streamed}",
        )
        ev.check(
            "reaching past the top lifts him onto nothing",
            rung_of(state, YOU) == TOP,
            f"{seed}: rung {rung_of(state, YOU)}",
        )
        ev.check(
            "a realm the story told is one he has heard of, and at most one a scene",
            len(named) <= 1 and [name for name, _ in above(state)] == named,
            f"{seed}: {named}, {above(state)}",
        )
        await ev.judge(
            "reaching past the highest realm",
            Rubric(
                must=(
                    "Lin does not break through in this scene: as it ends he is still at "
                    "Soul Transformation",
                ),
                must_not=(
                    "The scene gives a name to a realm above Soul Transformation that "
                    "CONTEXT does not list among the realms on record",
                    "The scene says that nothing at all can ever lie above Soul "
                    "Transformation, as a fact of the world rather than as what people "
                    "believe",
                ),
            ),
            seen,
            context=on_record(state),
        )

        # Live: a being from beyond arrives. The scene names the realm they are of, and the
        # record has it, with them on it.
        story = at_the_top(ev, f"{seed}/rift")

        def rift(state: WorldState) -> None:
            state.pending_events["rift"] = PendingEvent(
                id="rift",
                kind="eval.rift",
                title=RIFT,
                due_s=state.world_s + HOUR,
                needs_player=True,
                subject_ids=[YOU],
                place_id="well",
            )

        story.change(rift)
        before = story.state
        seen = await story.act(
            "I meditate on the summit until dusk",
            act("meditate on the summit until dusk", "meditate", ActionKind.TIME_SKIP, DAY // 2),
        )
        state = story.state
        named = told_above(state)
        came = sorted(
            who for who, rung in standing(state).items() if rung is not None and rung > TOP
        )
        ev.metric(f"realms told above the top when the envoy came, {seed}", named)
        ev.metric(f"who came standing above the old top, {seed}", came)
        ev.check(
            "the scene of the arrival names the realm the envoy is of, and the ladder has it",
            len(named) == 1,
            f"{seed}: {named}, {seen.findings}; told: {seen.streamed}",
        )
        arrival = seen
        await ev.judge(
            "a being from above the highest realm arrives",
            Rubric(
                must=(
                    "A stranger arrives who is shown or said to be stronger than anyone at "
                    "Soul Transformation",
                ),
                must_not=(
                    "The scene gives a name to a realm above Soul Transformation that "
                    "CONTEXT does not list among the realms on record",
                    "Lin, or anyone the story already knew, is said to stand on a realm "
                    "above Soul Transformation",
                ),
            ),
            seen,
            context=on_record(state),
        )

        # A scene may leave a stranger without a name, and nobody nameless is on record (C1).
        # Once the character has asked who they are, the record has them, on their realm.
        seen = await story.act(ASK, None)
        state = story.state
        came = sorted(
            who for who, rung in standing(state).items() if rung is not None and rung > TOP
        )
        new = sorted(who for who in state.characters if who not in before.characters)
        ev.metric(f"who stood above the old top once he had asked, {seed}", came)
        ev.check(
            "someone the story brought in stands on that realm, above the old top",
            bool(came),
            f"{seed}: came {came} of {new}, {standing(state)}; the arrival: "
            f"{arrival.findings}; asked: {seen.findings}; told: {seen.streamed}",
        )
        ev.check(
            "whatever the scenes named, nobody on record before the arrival was lifted",
            all(
                now == standing(before).get(who, now) or who in came
                for who, now in standing(state).items()
            )
            and not [who for who in came if who in before.characters],
            f"{seed}: {came}",
        )
        ev.check(
            "the two scenes with the envoy add one realm, not two",
            len(told_above(state)) <= 1,
            f"{seed}: {told_above(state)}; asked: {seen.findings}",
        )


def _stopped(played: Played) -> str:
    """How a live turn settled the reach, for the run's report."""
    if not played.completed or not played.steps:
        return "no step"
    first = played.steps[0]
    return f"{first.outcome_class.value}: {first.reason}"
