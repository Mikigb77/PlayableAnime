"""Scenario worlds and builders for the resolve tests, from T17's scripts.

Intents here are what the interpret step would propose for each script, including its mistakes
where a test checks that code catches them.
"""

from engine.base import MINUTE
from engine.context import Difficulty, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    Beat,
    BeatUse,
    ChainLink,
    Intent,
    IntentStep,
    MeansVerdict,
    SheetPart,
    SheetUse,
    StepFacts,
    UseSource,
)
from engine.resolve import resolve_intent
from engine.rng import SeededRng
from engine.samples import cultivation_world, grounded_world
from engine.state import (
    Character,
    CharacterSheet,
    Condition,
    Extraordinary,
    Fact,
    Health,
    Item,
    ItemKind,
    LadderPosition,
    PassingState,
    Place,
    Power,
    PowerAxes,
    PowerAxis,
    Prevalence,
    Resources,
    RuleTopic,
    SceneFrame,
    WorldBible,
    WorldRule,
    WorldState,
)

SEEDS = range(300)
MANY_SEEDS = range(4000)


def ctx(difficulty: Difficulty = Difficulty.BALANCED, turn: int = 3) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings(difficulty=difficulty))


def rng(seed: int = 0) -> SeededRng:
    return SeededRng.for_turn(f"seed-{seed}", "main", 3)


def resolve(state: WorldState, intent: Intent, seed: int = 0, difficulty=Difficulty.BALANCED):
    return resolve_intent(state, intent, ctx(difficulty), rng(seed))


def step(text: str, kind: ActionKind = ActionKind.EXCHANGE, duration_s: int = 2, **kw):
    return IntentStep(
        text=text,
        verb=kw.pop("verb", text.split()[0]),
        kind=kind,
        proposed_duration_s=duration_s,
        **kw,
    )


def facts(**kw) -> StepFacts:
    return StepFacts(**kw)


def power(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.POWER, ref=ref)


def item(ref: str) -> SheetUse:
    return SheetUse(part=SheetPart.ITEM, ref=ref)


def stop_time() -> IntentStep:
    return step(
        "stop time", ActionKind.INSTANT, 0, proposed_personal_s=1, uses=[power("time-stop")]
    )


def add(state: WorldState, *characters: Character, present: bool = True) -> WorldState:
    for character in characters:
        state.characters[character.id] = character
        if present and character.id not in state.scene.present_ids:
            state.scene.present_ids.append(character.id)
    return state


def give(state: WorldState, character_id: str, *items: Item) -> WorldState:
    state.characters[character_id].sheet.resources.items.extend(items)
    return state


# --- the cultivation world (Lin Feng, the Azure Cloud Sect) --------------------------------------


def sect() -> WorldState:
    """Lin Feng at Qi Condensation with time stop, and a sword at his hip."""
    state = cultivation_world()
    return give(state, "lin", Item(id="sword", name="iron sword", kind=ItemKind.WEAPON))


def with_troll(state: WorldState) -> WorldState:
    troll = Character(
        id="troll",
        name="the cave troll",
        location_id="well",
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    return add(state, troll)


def with_dragon(state: WorldState) -> WorldState:
    dragon = Character(
        id="dragon",
        name="the ancient dragon",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=14),
            condition=Condition(states=[PassingState(name="asleep")]),
        ),
    )
    give(state, "lin", Item(id="kitchen-knife", name="kitchen knife", kind=ItemKind.GEAR))
    return add(state, dragon)


def wounded(state: WorldState, character_id: str, health: Health) -> WorldState:
    state.characters[character_id].sheet.condition.health = health
    return state


def disciple(character_id: str, name: str, rung: int = 0) -> Character:
    return Character(
        id=character_id,
        name=name,
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2 + 2 * rung),
            ladders=[LadderPosition(ladder_id="realms", rung=rung)],
        ),
    )


def strike(target: str, **kw) -> IntentStep:
    """A straight attack meant to kill, with Lin's sword."""
    kw.setdefault("facts", facts(opposition_ids=[target], can_respond=True))
    return step(
        f"cut down {target}",
        verb="attack",
        aim=Aim.KILL,
        target_ids=[target],
        axis=PowerAxis.MIGHT,
        uses=[item("sword")],
        **kw,
    )


# --- the workaround: a shielded mage three realms up ---------------------------------------------


def shielded_mage(*, teleport: bool = False) -> WorldState:
    """Su Yan at Nascent Soul, three realms above Lin, meditating behind a force field that keeps
    out blades, rounds and air. With `teleport`, her sheet has a way out."""
    state = sect()
    powers = [
        Power(
            id="su-field",
            name="Azure Barrier",
            description="A force field that keeps out blades, arrows, flames and air.",
        )
    ]
    if teleport:
        powers.append(
            Power(id="void-step", name="Void Step", description="Teleports her out of danger.")
        )
    su = Character(
        id="su-yan",
        name="Su Yan",
        location_id="hall",
        sheet=CharacterSheet(
            axes=PowerAxes(might=8, knowledge=7),
            ladders=[LadderPosition(ladder_id="realms", rung=3)],
            powers=powers,
        ),
    )
    state.places["hall"] = Place(id="hall", name="the meditation hall", kind="building")
    give(
        state, "lin", Item(id="oil", name="jars of lamp oil", kind=ItemKind.CONSUMABLE, quantity=6)
    )
    state.facts["no-exit"] = Fact(id="no-exit", text="The hall has a single door.")
    return add(state, su)


def burn_the_hall(**kw) -> IntentStep:
    """'I soak the hall in oil and set it alight from outside.' (A9)"""
    chain = kw.pop(
        "chain",
        [
            ChainLink(
                text="Oil and fire fill the hall around her field.",
                rests_on=["oil"],
                takes_s=2 * MINUTE,
            ),
            ChainLink(
                text="Her field keeps out air as well as flames.",
                rests_on=["su-field"],
            ),
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
    )
    return step(
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
        chain=chain,
        facts=kw.pop(
            "facts",
            facts(
                opposition_ids=["su-yan"],
                can_respond=False,
                why_not="deep in meditation behind her field",
            ),
        ),
        **kw,
    )


# --- the grounded world (Luca Esposito in Naples) ------------------------------------------------


def naples_with_sleeping_guard(*, asleep_on_sheet: bool = True) -> WorldState:
    state = grounded_world()
    states = [PassingState(name="asleep")] if asleep_on_sheet else []
    guard = Character(
        id="guard",
        name="Tonino",
        description="Carmine's door guard, dozing in a chair.",
        location_id="bar",
        sheet=CharacterSheet(axes=PowerAxes(might=2), condition=Condition(states=states)),
    )
    return add(state, guard)


# --- a modern city with hidden mages (cause and effect, A9) --------------------------------------


def hidden_city() -> WorldState:
    """Dante Moretti with a bazooka, a thug, a mage whose field stops anything he has, and a mage
    whose field is about as strong as the round."""
    field = "A shimmering force field that stops bullets and rockets."
    dante = Character(
        id="dante",
        name="Dante Moretti",
        location_id="docks",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2),
            resources=Resources(
                items=[Item(id="bazooka", name="bazooka", kind=ItemKind.WEAPON, quantity=3)]
            ),
        ),
    )
    thug = Character(
        id="thug", name="Rocco", location_id="docks", sheet=CharacterSheet(axes=PowerAxes(might=2))
    )
    vesna = Character(
        id="vesna",
        name="Vesna",
        location_id="docks",
        sheet=CharacterSheet(
            axes=PowerAxes(might=8),
            powers=[Power(id="ward", name="Iron Ward", description=field)],
        ),
    )
    ilya = Character(
        id="ilya",
        name="Ilya",
        location_id="docks",
        sheet=CharacterSheet(
            axes=PowerAxes(might=4),
            powers=[Power(id="ward", name="Glass Ward", description=field)],
        ),
    )
    return WorldState(
        bible=WorldBible(
            title="Night Shift",
            genre="urban fantasy",
            era="A modern port city with phones and police",
            extraordinary=[Extraordinary(id="magic", kind="magic", prevalence=Prevalence.HIDDEN)],
            rules=[
                WorldRule(
                    id="magic-hidden",
                    text="Magic is real and hidden from ordinary people.",
                    fixed=True,
                    topic=RuleTopic.EXISTENCE,
                )
            ],
        ),
        player_id="dante",
        characters={c.id: c for c in (dante, thug, vesna, ilya)},
        places={"docks": Place(id="docks", name="the docks", kind="wharf")},
        scene=SceneFrame(place_id="docks", present_ids=["dante", "thug", "vesna", "ilya"]),
    )


def fire_bazooka(target: str, means: MeansVerdict) -> IntentStep:
    return step(
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
