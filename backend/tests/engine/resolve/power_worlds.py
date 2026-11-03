"""Scenario worlds and steps for the powers tests (WS9b), from T17's scripts.

Intents here are what the interpret step would propose for each script, including the mistakes a
test checks that code overrides, such as judging that a pebble can't hurt a troll.
"""

from engine import pipeline
from engine.base import DAY, HOUR
from engine.context import Difficulty, StorySettings, TurnContext
from engine.contracts import (
    ActionKind,
    Aim,
    Contact,
    GrowthKind,
    Intent,
    IntentStep,
    MeansVerdict,
    PowerGrant,
    Training,
)
from engine.invariants import check_transition
from engine.pipeline import PlayOut
from engine.resolve import resolve_intent
from engine.rng import SeededRng
from engine.state import (
    Attributes,
    Character,
    CharacterSheet,
    Faction,
    HitMode,
    Place,
    PowerAxes,
    Route,
    WorldState,
)
from tests.engine.resolve.worlds import add, facts, power, sect, step

SEEDS = range(200)


def ctx(turn: int = 3, difficulty: Difficulty = Difficulty.BALANCED) -> TurnContext:
    return TurnContext(story_id="s1", turn=turn, settings=StorySettings(difficulty=difficulty))


def rng(seed: int = 0, turn: int = 3) -> SeededRng:
    return SeededRng.for_turn(f"seed-{seed}", "main", turn)


def resolve(
    state: WorldState,
    intent: Intent,
    seed: int = 0,
    turn: int = 3,
    difficulty: Difficulty = Difficulty.BALANCED,
):
    return resolve_intent(state, intent, ctx(turn, difficulty), rng(seed, turn))


def play(state: WorldState, intent: Intent, seed: int = 0, turn: int = 3) -> PlayOut:
    """Resolve and play one turn the way the turn loop does, checking C1 across it."""
    resolution = resolve(state, intent, seed, turn)
    played = pipeline.play_out(state, resolution, ctx(turn), rng(seed, turn))
    assert played.rejected == ()
    assert check_transition(state, played.state) == []
    return played


def lin_power(state: WorldState):
    return state.characters["lin"].sheet.power("time-stop")


def with_hit_mode(state: WorldState, mode: HitMode | None) -> WorldState:
    lin_power(state).time.hit_mode = mode
    return state


def with_wall(state: WorldState) -> WorldState:
    """The cave troll stands in front of the old wall by the well."""
    state.places["wall"] = Place(id="wall", name="the old wall", kind="wall", parent_id="well")
    troll = Character(
        id="troll",
        name="the cave troll",
        location_id="wall",
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    return add(state, troll)


def throw(target_ids: list[str], *, aim: Aim = Aim.KILL, **kw) -> IntentStep:
    """'I throw a pebble at it' in stopped time, where the interpret step judged that a pebble
    can't hurt it: code follows the power instead."""
    kw.setdefault(
        "facts",
        facts(
            opposition_ids=[t for t in target_ids if t not in ("wall", "plain")],
            can_respond=False,
            why_not="frozen in stopped time",
            means=MeansVerdict.CLEARLY_NOT,
            hindrances=["a pebble just bounces off"],
        ),
    )
    return step(
        "throw a pebble",
        ActionKind.INSTANT,
        1,
        verb="throw",
        aim=aim,
        target_ids=target_ids,
        contact=Contact.THROW,
        mass_kg=0.1,
        proposed_personal_s=1,
        **kw,
    )


def stop_time() -> IntentStep:
    return step(
        "stop time", ActionKind.INSTANT, 0, proposed_personal_s=1, uses=[power("time-stop")]
    )


def battlefield() -> WorldState:
    """An army camped on the plain outside a castle, with a ridge ten kilometers off (N6)."""
    state = sect()
    state.places["castle"] = Place(
        id="castle",
        name="Black Iron Castle",
        kind="castle",
        routes=[Route(to_id="plain", travel_s=5 * 60)],
    )
    state.places["plain"] = Place(id="plain", name="the plain below the castle", kind="plain")
    state.factions["army"] = Faction(id="army", name="the Black Banner army", kind="army")
    soldiers = [
        Character(
            id=f"soldier-{i}",
            name=f"Black Banner soldier {i}",
            location_id="plain",
            sheet=CharacterSheet(axes=PowerAxes(might=2)),
        )
        for i in range(3)
    ]
    for soldier in soldiers:
        state.characters[soldier.id] = soldier
    state.characters["lin"].location_id = "castle"
    state.scene.place_id = "castle"
    state.scene.present_ids = ["lin"]
    return state


def army_throw(range_m: float) -> IntentStep:
    return step(
        "throw a pebble at the army",
        ActionKind.INSTANT,
        1,
        verb="throw",
        aim=Aim.KILL,
        target_ids=["army", "plain"],
        contact=Contact.THROW,
        mass_kg=0.1,
        range_m=range_m,
        proposed_personal_s=1,
        facts=facts(opposition_ids=["army"], opposition="the Black Banner army"),
    )


def bandit_camp(state: WorldState) -> WorldState:
    state.places["road"] = Place(id="road", name="the mountain road", kind="road")
    bandit = Character(
        id="bandit",
        name="the bandit chief",
        location_id="road",
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    bystander = Character(
        id="merchant",
        name="a frightened merchant",
        location_id="road",
        sheet=CharacterSheet(axes=PowerAxes(might=1)),
    )
    state.characters["lin"].location_id = "road"
    state.scene.place_id = "road"
    state.scene.present_ids = ["lin"]
    return add(state, bandit, bystander)


def train_power(grants: PowerGrant, *, days: int = 60, what: str = "") -> IntentStep:
    """Months of practice letting a stopped stone back into time gradually (A4)."""
    what = (
        what
        or {
            PowerGrant.CONTROLLED_FORCE: "Gentle Release",
            PowerGrant.RELATIVE_SPEED_THROWS: "Falling Star Release",
        }[grants]
    )
    return step(
        f"practise {what} around a rock",
        ActionKind.TIME_SKIP,
        days * DAY,
        verb="train",
        training=Training(
            kind=GrowthKind.POWER,
            what=what,
            power_id="time-stop",
            grants=grants,
            rests_on=["time-stop"],
        ),
    )


def train(kind: GrowthKind, what: str, hours: float, **kw) -> IntentStep:
    action = ActionKind.TIME_SKIP if hours > 72 else ActionKind.TASK
    return step(
        f"train {what}",
        action,
        int(hours * HOUR),
        verb="train",
        training=Training(kind=kind, what=what, **kw),
    )


def friend(state: WorldState) -> WorldState:
    mei = Character(
        id="mei",
        name="Mei",
        location_id="well",
        sheet=CharacterSheet(attributes=Attributes(strength=2), axes=PowerAxes(might=2)),
    )
    state.characters["lin"].sheet.attributes.strength = 3
    return add(state, mei)


def train_until_done(state: WorldState, intent: Intent, turn: int, tries: int = 10) -> PlayOut:
    """Train turn after turn, as a player says "I keep training" after each interruption (E7),
    until a stretch runs to its end."""
    played = play(state, intent, turn=turn)
    for later in range(turn + 1, turn + tries):
        if played.interrupted_by is None:
            break
        played = play(played.state, intent, turn=later)
    assert played.interrupted_by is None
    return played
