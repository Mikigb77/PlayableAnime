"""The scenarios' starting worlds, from T15's, T17's and T18's scripts, built on the sample worlds
(`engine.samples`). Each call returns a fresh state, so a scenario can change it freely.
"""

from __future__ import annotations

from engine.base import DAY, MINUTE
from engine.samples import cultivation_world, farm_world, grounded_world
from engine.state import (
    Attitude,
    Attributes,
    Character,
    CharacterSheet,
    Condition,
    Creature,
    Encounter,
    EncounterKind,
    Extraordinary,
    Fact,
    Faction,
    GiftStrength,
    Health,
    HitMode,
    Item,
    ItemKind,
    LadderPosition,
    Membership,
    PassingState,
    PendingEvent,
    People,
    Place,
    Power,
    PowerAxes,
    Prevalence,
    Prominence,
    Resources,
    Route,
    RuleTopic,
    SceneFrame,
    Skill,
    SkillLevel,
    Technique,
    Trait,
    TraitKind,
    WorldBible,
    WorldRule,
    WorldState,
)

__all__ = [
    "add",
    "cultivation_world",
    "farm_world",
    "give",
    "grounded_world",
]


def add(state: WorldState, *characters: Character, present: bool = True) -> WorldState:
    for character in characters:
        state.characters[character.id] = character
        if present and character.id not in state.scene.present_ids:
            state.scene.present_ids.append(character.id)
    return state


def give(state: WorldState, character_id: str, *items: Item) -> WorldState:
    state.characters[character_id].sheet.resources.items.extend(items)
    return state


# --- the cultivation world (Lin Feng, the Azure Cloud Sect) ------------------------------------


def sect() -> WorldState:
    """Lin Feng at Qi Condensation with time stop, and a sword at his hip."""
    state = cultivation_world()
    return give(state, "lin", Item(id="sword", name="iron sword", kind=ItemKind.WEAPON))


def with_troll(state: WorldState, *, asleep: bool = False) -> WorldState:
    troll = Character(
        id="troll",
        name="the cave troll",
        description="A grey-skinned cave troll with a club.",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=3),
            condition=Condition(states=[PassingState(name="asleep")] if asleep else []),
        ),
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


def disciple(character_id: str, name: str, rung: int = 0, **extra) -> Character:
    return Character(
        id=character_id,
        name=name,
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2 + 2 * rung),
            ladders=[LadderPosition(ladder_id="realms", rung=rung)],
        ),
        **extra,
    )


def mage_fight() -> WorldState:
    """Lin at the well with a grey mage who means to fight him (W10, M1). `start_fight` starts
    the fight itself."""
    state = cultivation_world()
    state.characters["mage"] = Character(
        id="mage",
        name="the grey mage",
        prominence=Prominence.KEY,
        description="A gaunt mage in grey robes, crackling with power.",
        appearance="Sixty, gaunt, grey robes, a staff of black wood.",
        age=60,
        location_id="well",
        sheet=CharacterSheet(axes=PowerAxes(might=4)),
    )
    state.scene.present_ids.append("mage")
    return state


def start_fight(state: WorldState, *opponent_ids: str) -> None:
    """Puts the scene in the middle of a key fight that started on the next turn, for a scenario
    about a fight already on. In play, the first blow starts it (`engine.encounters`)."""
    state.scene.encounter = Encounter(
        kind=EncounterKind.FIGHT,
        opponent_ids=list(opponent_ids),
        started_turn=state.turn + 1,
        started_s=state.world_s,
        key=True,
    )


def sect_with_a_witness() -> WorldState:
    """The cultivation sample with Han, an outer disciple who bullies Lin, dozing against the
    well, and a timid outer disciple, Wei, drawing water beside him. The sect has no phones, and
    the map doesn't say where its Law Enforcement Hall sits."""
    state = sect()
    han = disciple(
        "han",
        "Han Jie",
        description="An outer disciple who takes Lin's rations, dozing against the well.",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple", loyalty=60)],
    )
    han.sheet.condition.states.append(PassingState(name="asleep"))
    wei = Character(
        id="wei",
        name="Wei",
        description="A timid outer disciple with a bucket.",
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple", loyalty=40)],
    )
    return add(state, han, wei)


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


def crowded_well() -> WorldState:
    """The well at midday: an enforcer of the Law Enforcement Hall on his rounds, four outer
    disciples drawing water, and the noon bell due to ring in a second."""
    state = sect()
    gao = disciple(
        "gao",
        "Enforcer Gao",
        description="A Law Enforcement Hall enforcer on his rounds.",
        memberships=[Membership(faction_id="azure-cloud", rank="enforcer", loyalty=80)],
    )
    crowd = [
        disciple(
            f"onlooker-{n}",
            name,
            description="An outer disciple drawing water.",
            memberships=[Membership(faction_id="outer-court", rank="outer disciple", loyalty=50)],
        )
        for n, name in enumerate(("Fang Yu", "Lu Qi", "Shen Mei", "Bai Ren"))
    ]
    add(state, gao, *crowd)
    state.pending_events["noon-bell"] = PendingEvent(
        id="noon-bell",
        kind="eval.bell",
        title="The noon bell rings.",
        due_s=state.world_s + 1,
        place_id="well",
    )
    return state


def duel(*, rung: int = 0, counter: bool = True) -> WorldState:
    """Lin and Guo Tai, two swordsmen, Guo on `rung` of the realms; Lin knows a counter to Guo's
    Iron Ox style when `counter` says so (G25)."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders[0].rung = 0
    lin.sheet.skills.append(Skill(name="swordsmanship", level=SkillLevel.SKILLED))
    if counter:
        lin.sheet.techniques.append(
            Technique(
                id="reed-counter",
                name="Reed-Bending Counter",
                style="Flowing Reed",
                effect="Yields to a charging blow and turns its weight against the striker.",
            )
        )
    guo = disciple(
        "guo",
        "Guo Tai",
        rung=rung,
        description="A broad swordsman of the Iron Ox style, all charging blows.",
    )
    guo.sheet.skills.append(Skill(name="swordsmanship", level=SkillLevel.SKILLED))
    guo.sheet.techniques.append(
        Technique(id="ox-charge", name="Iron Ox Charge", style="Iron Ox", effect="A charging cut.")
    )
    return add(state, guo)


def insulted(*, temper: bool = True) -> WorldState:
    """Senior Brother Zhao sneers at Lin in front of the well. With `temper`, Lin is hot-headed
    (G13, G15)."""
    state = sect()
    lin = state.characters["lin"]
    if temper:
        lin.sheet.traits.append(
            Trait(name="hot temper", kind=TraitKind.FLAW, description="Flares at any insult.")
        )
        lin.sheet.disposition.temperament.traits.append("hot-headed")
    state.scene.ended_on = (
        "Zhao flicks water in Lin's face. 'Trash like you should be scrubbing my floor.'"
    )
    return state


def seclusion(*, summons_in_s: int | None = None) -> WorldState:
    """Lin ready to break through to Foundation Establishment (G19), which needs a Foundation
    Pill he has. With `summons_in_s`, the sect sends for him that long into his seclusion, and it
    needs him (W10)."""
    state = sect()
    state.bible.ladders[0].rungs[1].needs = ["a Foundation Pill"]
    give(state, "lin", Item(id="pill", name="Foundation Pill", kind=ItemKind.CONSUMABLE))
    if summons_in_s is not None:
        state.pending_events["summons"] = PendingEvent(
            id="summons",
            kind="eval.summons",
            title="Zhao bangs on the door: the sect summons Lin to the hall.",
            due_s=state.world_s + summons_in_s,
            needs_player=True,
            subject_ids=["lin"],
            place_id="well",
        )
    return state


def disguised_expert() -> WorldState:
    """Lin at Core Formation in an outer disciple's robes, and Young Master Wu at Foundation
    Establishment, who can sense strength only up to his own realm (G20)."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders = [LadderPosition(ladder_id="realms", rung=2)]
    lin.description = "A plain outer disciple in patched robes, by every sign."
    wu = Character(
        id="young-master",
        name="Young Master Wu",
        description="The sect's young master, never without an audience.",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=4), ladders=[LadderPosition(ladder_id="realms", rung=1)]
        ),
    )
    state.scene.ended_on = "Young Master Wu laughs at Lin's patched robes in front of the well."
    return add(state, wu)


# --- time stop and the powers (W10a, A9, G22) --------------------------------------------------


def hit_mode(state: WorldState, mode: HitMode | None) -> WorldState:
    """How Lin's stopped-time hits land; None leaves it for play to settle (A9)."""
    time_stop(state).time.hit_mode = mode
    return state


def time_stop(state: WorldState) -> Power:
    return state.characters["lin"].sheet.power("time-stop")


def troll_by_the_wall(mode: HitMode | None) -> WorldState:
    """The cave troll stands in front of the old wall by the well."""
    state = hit_mode(sect(), mode)
    state.places["wall"] = Place(id="wall", name="the old wall", kind="wall", parent_id="well")
    troll = Character(
        id="troll",
        name="the cave troll",
        location_id="wall",
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    return add(state, troll)


def battlefield(*, at: str = "castle", known: bool = False) -> WorldState:
    """The Black Banner army camped on the plain below Black Iron Castle, a ridge ten kilometers
    off, three kingdoms beyond, and Lin `at` the castle wall or on the ridge (N6). With `known`,
    the world knows what his time stop does."""
    state = sect()
    state.places["castle"] = Place(
        id="castle",
        name="Black Iron Castle",
        kind="castle",
        routes=[Route(to_id="plain", travel_s=5 * MINUTE)],
    )
    state.places["plain"] = Place(id="plain", name="the plain below the castle", kind="plain")
    state.places["ridge"] = Place(
        id="ridge",
        name="the ridge above the plain",
        kind="ridge",
        routes=[Route(to_id="plain", travel_s=3 * 60 * MINUTE), Route(to_id="well", travel_s=DAY)],
    )
    state.places["well"].routes.append(Route(to_id="ridge", travel_s=DAY))
    kingdoms(state)
    state.factions["army"] = Faction(
        id="army", name="the Black Banner army", kind="army", parent_id="kingdom-0"
    )
    for n in range(3):
        state.characters[f"soldier-{n}"] = Character(
            id=f"soldier-{n}",
            name=f"Black Banner soldier {n + 1}",
            location_id="plain",
            memberships=[Membership(faction_id="army", rank="soldier")],
            sheet=CharacterSheet(axes=PowerAxes(might=2)),
        )
    state.characters["lin"].location_id = at
    state.scene = SceneFrame(
        place_id=at,
        present_ids=["lin"],
        ended_on="Below, the Black Banner army's campfires cover the plain.",
    )
    time_stop(state).secret = not known
    return state


def conquered() -> WorldState:
    """After the conquest: Lin, whose stopped-time throws land at the speed of light, rules the
    Azure Cloud Sect, and the three kingdoms know what he did (A9, G22)."""
    state = kingdoms(hit_mode(sect(), HitMode.RELATIVE_SPEED))
    power = time_stop(state)
    power.secret = False
    lin = state.characters["lin"]
    lin.memberships = [Membership(faction_id="azure-cloud", rank="sect master", loyalty=100)]
    lin.sheet.axes.influence = 9  # the sect's master, and the one who took it
    state.factions["azure-cloud"].leader_ids = ["lin"]
    state.facts["conquest"] = Fact(
        id="conquest",
        text="Lin Feng took the Azure Cloud Sect with a stone thrown in stopped time.",
        known_by=["lin"],
    )
    for n, kingdom in enumerate(("Northern", "River", "Salt")):
        envoy = Character(
            id=f"envoy-{n}",
            name=f"the {kingdom} Kingdom's envoy",
            location_id="well",
            memberships=[Membership(faction_id=f"kingdom-{n}", rank="envoy", loyalty=80)],
            sheet=CharacterSheet(axes=PowerAxes(might=2, influence=4)),
        )
        add(state, envoy)
    state.scene.ended_on = (
        "The sect's elders kneel at the well, and three kingdoms' envoys wait for Lin's word."
    )
    return state


def elder_at_the_well() -> WorldState:
    """Elder Mo, at Core Formation, comes down to the well, and Lin's rare time stop hasn't yet
    been settled for how hard it hits (A9)."""
    state = hit_mode(sect(), None)
    power = time_stop(state)
    power.strength = GiftStrength.RARE
    power.secret = False
    state.characters["elder-mo"].location_id = "well"
    state.scene.present_ids.append("elder-mo")
    return state


# --- changes between turns ---------------------------------------------------------------------


def rested(state: WorldState) -> None:
    """Some time later: the stop has run out and recovered, and Lin has healed."""
    state.time_effects.clear()
    lin = state.characters["lin"]
    lin.personal_offset_s += 10 * MINUTE
    lin.sheet.condition.health = Health.UNHURT


def back_on_the_road(state: WorldState) -> None:
    """Months later, Lin is back on the road with the bandit chief and the merchant."""
    rested(state)
    for character_id in ("lin", "bandit", "merchant"):
        state.characters[character_id].location_id = "road"
    state.scene = SceneFrame(
        place_id="road",
        present_ids=["lin", "bandit", "merchant"],
        ended_on="The bandit chief holds a blade to the merchant's throat again.",
    )


def troll_returns(state: WorldState) -> None:
    """After the training, the troll lumbers back to the well."""
    rested(state)
    state.characters["troll"].location_id = state.characters["lin"].location_id
    state.scene.present_ids = list(dict.fromkeys([*state.scene.present_ids, "lin", "troll"]))


def second_troll(state: WorldState) -> None:
    """Another cave troll lumbers up to the well."""
    troll = Character(
        id="troll-2",
        name="the second cave troll",
        description="Another grey-skinned cave troll.",
        location_id=state.characters["lin"].location_id,
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    add(state, troll)


def kingdoms(state: WorldState) -> WorldState:
    """Three kingdoms, each with a champion: the strongest the world holds. The Northern Kingdom
    fields the Black Banner army where there is one."""
    for n, might in enumerate((10, 8, 6)):
        state.factions[f"kingdom-{n}"] = Faction(
            id=f"kingdom-{n}",
            name=f"the {('Northern', 'River', 'Salt')[n]} Kingdom",
            kind="kingdom",
        )
        state.characters[f"champion-{n}"] = Character(
            id=f"champion-{n}",
            name=f"Champion of the {('Northern', 'River', 'Salt')[n]} Kingdom",
            memberships=[Membership(faction_id=f"kingdom-{n}", rank="champion")],
            sheet=CharacterSheet(axes=PowerAxes(might=might)),
        )
    return state


def bandit_road() -> WorldState:
    """Lin on the mountain road with a bandit chief and a frightened merchant."""
    state = sect()
    state.places["road"] = Place(id="road", name="the mountain road", kind="road")
    bandit = Character(
        id="bandit",
        name="the bandit chief",
        location_id="road",
        sheet=CharacterSheet(axes=PowerAxes(might=3)),
    )
    merchant = Character(
        id="merchant",
        name="a frightened merchant",
        location_id="road",
        sheet=CharacterSheet(axes=PowerAxes(might=1)),
    )
    state.characters["lin"].location_id = "road"
    state.scene = SceneFrame(
        place_id="road",
        present_ids=["lin"],
        ended_on="The bandit chief holds a blade to the merchant's throat.",
    )
    return add(state, bandit, merchant)


def friend_under_arrows() -> WorldState:
    """Mei, Lin's friend, in an arrow's path, in a world where stopped-time hits land at relative
    speed."""
    state = hit_mode(sect(), HitMode.RELATIVE_SPEED)
    mei = Character(
        id="mei",
        name="Mei",
        location_id="well",
        sheet=CharacterSheet(attributes=Attributes(strength=2), axes=PowerAxes(might=2)),
    )
    state.characters["lin"].sheet.attributes.strength = 3
    state.scene.ended_on = "An arrow leaves a bandit's bow, flying straight at Mei."
    return add(state, mei)


def bandit(n: int) -> Character:
    """A bandit who ambushes Lin by the well."""
    return Character(
        id=f"bandit-{n}",
        name=f"a mountain bandit ({n})",
        description="A scarred mountain bandit with a hatchet.",
        location_id="well",
        sheet=CharacterSheet(
            axes=PowerAxes(might=4), ladders=[LadderPosition(ladder_id="realms", rung=1)]
        ),
    )


def days_later(days: int, *, back_to: str):
    """A change that lets `days` pass off-screen, as a scene that skips ahead, and puts Lin back
    at `back_to`. The world's own clock and pending events catch up on the next turn (W6)."""

    def change(state: WorldState) -> None:
        state.characters["lin"].location_id = back_to
        state.scene = SceneFrame(
            place_id=back_to,
            present_ids=["lin"],
            ended_on=f"{days} days later, Lin is back in {state.places[back_to].name}.",
        )

    return change


def foot_village() -> WorldState:
    """Lin, now at Core Formation, in Willow Ford, a mortal village at the foot of the mountain:
    six villagers in the square, a peddler passing through, and two farmers out in the fields
    (W5, W8)."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.ladders = [LadderPosition(ladder_id="realms", rung=2)]
    lin.sheet.axes.might = 6
    lin.location_id = "willow-ford"
    state.places["willow-ford"] = Place(
        id="willow-ford",
        name="Willow Ford",
        kind="village",
        parent_id="azure-peak",
        routes=[Route(to_id="well", travel_s=2 * 60 * MINUTE, mode="on foot")],
        known_by=["lin"],
        visited_by=["lin"],
    )
    state.places["fields"] = Place(
        id="fields", name="the Willow Ford fields", kind="fields", parent_id="willow-ford"
    )
    state.places["well"].routes.append(
        Route(to_id="willow-ford", travel_s=2 * 60 * MINUTE, mode="on foot")
    )
    state.factions["willow-ford"] = Faction(
        id="willow-ford", name="the people of Willow Ford", kind="village"
    )
    names = ("Old Pan", "Widow Lu", "Tian the smith", "Hua", "Little Bo's father", "Granny Ming")
    for n, name in enumerate(names):
        villager = Character(
            id=f"villager-{n}",
            name=name,
            description="A villager of Willow Ford.",
            location_id="willow-ford",
            memberships=[Membership(faction_id="willow-ford", rank="villager", loyalty=70)],
            sheet=CharacterSheet(axes=PowerAxes(might=1)),
        )
        villager.sheet.disposition.attitudes["lin"] = Attitude(affinity=40, trust=30)
        add(state, villager)
    peddler = Character(
        id="peddler",
        name="Fen the peddler",
        description="A peddler passing through with a mule.",
        location_id="willow-ford",
        sheet=CharacterSheet(axes=PowerAxes(might=1)),
    )
    add(state, peddler)
    for n, name in enumerate(("Shu the farmer", "Ah Qiang")):
        farmer = Character(
            id=f"farmer-{n}",
            name=name,
            description="A Willow Ford farmer, out in the fields.",
            location_id="fields",
            memberships=[Membership(faction_id="willow-ford", rank="villager", loyalty=70)],
            sheet=CharacterSheet(axes=PowerAxes(might=1)),
        )
        farmer.sheet.disposition.attitudes["lin"] = Attitude(affinity=40, trust=30)
        state.characters[farmer.id] = farmer
    state.scene = SceneFrame(
        place_id="willow-ford",
        present_ids=["lin", *(f"villager-{n}" for n in range(len(names))), "peddler"],
        ended_on="The villagers of Willow Ford bow as Lin walks into the square.",
    )
    return state


def back_in_willow_ford(state: WorldState) -> None:
    """Lin walks back into Willow Ford, where the farmers have come in from the fields to bury
    the dead, and the peddler has stayed to help."""
    for character_id in ("lin", "farmer-0", "farmer-1", "peddler"):
        state.characters[character_id].location_id = "willow-ford"
    present = [i for i in ("lin", "farmer-0", "farmer-1", "peddler") if state.characters[i].alive]
    state.scene = SceneFrame(
        place_id="willow-ford",
        present_ids=present,
        ended_on="Fresh graves line the road into Willow Ford.",
    )


# --- narration (T18: R1 to R7) ------------------------------------------------------------------


def troll_lunges() -> WorldState:
    """The cave troll, awake, lunging at Lin across the courtyard, with a tunnel behind him."""
    state = with_troll(sect())
    state.places["tunnel"] = Place(
        id="tunnel", name="the drainage tunnel", kind="tunnel", parent_id="well"
    )
    state.scene.ended_on = "The cave troll roars and lunges at Lin, its club already swinging."
    return state


def sword_stroke(level: SkillLevel) -> WorldState:
    """Lin before a falling leaf with his sword, at `level` with the blade (R4)."""
    state = sect()
    lin = state.characters["lin"]
    lin.sheet.skills = [Skill(name="swordsmanship", level=level)]
    if level is SkillLevel.MASTER:
        lin.sheet.traits.append(
            Trait(name="sword saint", kind=TraitKind.GIFT, description="One with the blade.")
        )
    state.scene.ended_on = "A maple leaf spins down from the branch above the well."
    return state


def throne_room() -> WorldState:
    """Lin before Elder Mo in the sect master's marble throne hall: polished floors, nothing
    loose anywhere (R2)."""
    state = sect()
    state.places["throne-hall"] = Place(
        id="throne-hall",
        name="the marble throne hall",
        kind="hall",
        description="Polished white marble from wall to wall, swept twice a day.",
        parent_id="azure-peak",
        known_by=["lin"],
    )
    state.characters["lin"].location_id = "throne-hall"
    state.characters["elder-mo"].location_id = "throne-hall"
    state.scene = SceneFrame(
        place_id="throne-hall",
        present_ids=["lin", "elder-mo"],
        ended_on="Elder Mo looks down at Lin from the dais of the marble throne hall.",
    )
    return state


# --- monsters and races (G23, G24) --------------------------------------------------------------


def ashwood() -> WorldState:
    """The Ashwood, three hours from the sect, where an ash wolf pack hunts. One wolf has strayed
    to the stream, its alpha watching from the treeline, and its fire core is worth what the
    bible says (G24)."""
    state = sect()
    state.bible.creatures.append(
        Creature(
            id="ash-wolf",
            name="ash wolf",
            description="A grey wolf with embers for eyes, hunting in packs.",
            tier=2,
            habitat="the Ashwood",
            worth="A fire core the size of a plum, worth ten silver taels at the sect's exchange.",
        )
    )
    state.places["ashwood"] = Place(
        id="ashwood",
        name="the Ashwood",
        kind="forest",
        parent_id="azure-peak",
        routes=[Route(to_id="well", travel_s=3 * 60 * MINUTE, mode="on foot")],
        known_by=["lin"],
    )
    state.places["den"] = Place(
        id="den", name="the pack's den", kind="den", parent_id="ashwood", known_by=["lin"]
    )
    state.places["well"].routes.append(
        Route(to_id="ashwood", travel_s=3 * 60 * MINUTE, mode="on foot")
    )
    state.factions["ash-pack"] = Faction(
        id="ash-pack", name="the Ashwood pack", kind="pack", leader_ids=["alpha"]
    )
    for wolf_id, name, place, might in (
        ("stray", "a lone ash wolf", "ashwood", 2),
        ("alpha", "the pack's alpha", "ashwood", 3),
        ("ash-wolf-2", "an ash wolf", "den", 2),
        ("ash-wolf-3", "an ash wolf", "den", 2),
    ):
        state.characters[wolf_id] = Character(
            id=wolf_id,
            name=name,
            description="A grey wolf with embers for eyes.",
            people_id="ash-wolf",  # a beast of the bible's kind, not a person (G24)
            location_id=place,
            memberships=[Membership(faction_id="ash-pack", rank="wolf", loyalty=90)],
            sheet=CharacterSheet(axes=PowerAxes(might=might)),
        )
    state.characters["lin"].location_id = "ashwood"
    state.scene = SceneFrame(
        place_id="ashwood",
        present_ids=["lin", "stray", "alpha"],
        ended_on=(
            "A lone ash wolf lifts its head from the stream, embers in its eyes. Further off, a "
            "bigger one watches from the treeline."
        ),
    )
    return state


def _peoples_world(
    *,
    title: str,
    player: Character,
    locals_: list[Character],
    place: Place,
    peoples: list[People],
    history: str,
) -> WorldState:
    return WorldState(
        bible=WorldBible(
            title=title,
            genre="high fantasy",
            era="An age of walled cities and old wars between the peoples",
            peoples=peoples,
            rules=[
                WorldRule(
                    id="peoples-exist",
                    text="Humans, elves and beastkin share the land.",
                    fixed=True,
                    topic=RuleTopic.EXISTENCE,
                )
            ],
        ),
        player_id=player.id,
        characters={c.id: c for c in (player, *locals_)},
        places={place.id: place},
        facts={"history": Fact(id="history", text=history)},
        scene=SceneFrame(
            place_id=place.id,
            present_ids=[player.id, *(c.id for c in locals_)],
            ended_on=f"{player.name} steps through the gate of {place.name}.",
        ),
        summary=f"{player.name} has just arrived at {place.name}.",
    )


PEOPLES = [
    People(
        id="humans",
        name="humans",
        relations=["Elves remember the human torches that burned Silverbough a century ago."],
    ),
    People(
        id="elves",
        name="elves",
        lifespan_years=600,
        culture="Old, proud and slow to forgive.",
        relations=["Distrust humans since the burning of Silverbough."],
    ),
    People(
        id="beastkin",
        name="beastkin",
        culture="Clans of wolf- and fox-folk.",
        relations=["Fought the humans of Thornford in the Border War twenty years ago."],
    ),
]


def elven_city() -> WorldState:
    """A human merchant walks into Silverbough, an elven city humans once burned (G23)."""
    player = Character(
        id="aldo",
        name="Aldo Brenn",
        description="A human cloth merchant with a mule.",
        people_id="humans",
        location_id="silverbough",
        known_by=["aldo"],
        met_by=["aldo"],
    )
    guard = Character(
        id="gate-warden",
        name="Ilyrien",
        description="An elven gate warden with a long spear.",
        people_id="elves",
        location_id="silverbough",
    )
    vendor = Character(
        id="vendor",
        name="Caelith",
        description="An elven fruit seller.",
        people_id="elves",
        location_id="silverbough",
    )
    return _peoples_world(
        title="Silverbough",
        player=player,
        locals_=[guard, vendor],
        place=Place(id="silverbough", name="Silverbough", kind="elven city", known_by=["aldo"]),
        peoples=PEOPLES,
        history="A century ago human soldiers burned half of Silverbough.",
    )


def border_town() -> WorldState:
    """A beastkin hunter walks into Thornford, a human town that fought the beastkin (G23)."""
    player = Character(
        id="kesh",
        name="Kesh",
        description="A wolf-eared beastkin hunter with a bow.",
        people_id="beastkin",
        location_id="thornford",
        known_by=["kesh"],
        met_by=["kesh"],
    )
    innkeeper = Character(
        id="innkeeper",
        name="Marta",
        description="The innkeeper of the Broken Spear, who lost a son in the Border War.",
        people_id="humans",
        location_id="thornford",
    )
    militia = Character(
        id="militia",
        name="Sergeant Hobb",
        description="A veteran of the Border War, now the town's militia sergeant.",
        people_id="humans",
        location_id="thornford",
    )
    return _peoples_world(
        title="Thornford",
        player=player,
        locals_=[innkeeper, militia],
        place=Place(id="thornford", name="Thornford", kind="border town", known_by=["kesh"]),
        peoples=PEOPLES,
        history="Twenty years ago Thornford fought the beastkin clans in the Border War.",
    )


# --- the grounded world (Luca Esposito in Naples) ----------------------------------------------


def naples_with_sleeping_guard() -> WorldState:
    state = grounded_world()
    guard = Character(
        id="guard",
        name="Tonino",
        description="Carmine's door guard, dozing in a chair.",
        location_id="bar",
        sheet=CharacterSheet(
            axes=PowerAxes(might=2), condition=Condition(states=[PassingState(name="asleep")])
        ),
    )
    return add(state, guard)


# --- a modern city with hidden mages (A9) ------------------------------------------------------


def hidden_city() -> WorldState:
    """Dante Moretti with a bazooka, a thug, a mage whose field stops anything he has, and a mage
    whose field is about as strong as the round."""
    field = "A shimmering force field that stops bullets and rockets."
    dante = Character(
        id="dante",
        name="Dante Moretti",
        location_id="docks",
        known_by=["dante"],
        met_by=["dante"],
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
        places={"docks": Place(id="docks", name="the docks", kind="wharf", known_by=["dante"])},
        scene=SceneFrame(
            place_id="docks",
            present_ids=["dante", "thug", "vesna", "ilya"],
            ended_on="Rocco cracks his knuckles while the two mages watch from the crane.",
        ),
        summary="Dante has come to the docks with a bazooka to settle things.",
    )


# --- the farm (Tomas Weller in the Long Valley) ------------------------------------------------


def farm() -> WorldState:
    return farm_world()


def village_far_off() -> WorldState:
    """The farm world with Millbrook a day's walk off, for a scenario that needs the news to
    travel before anyone can come."""
    state = farm_world()
    for place_id in ("farm", "village"):
        for route in state.places[place_id].routes:
            route.travel_s = 8 * 60 * MINUTE
    return state


def noodle_road() -> WorldState:
    """The cultivation sample with a market town down the mountain, for walking away (T17)."""
    state = cultivation_world()
    state.places["market-town"] = Place(
        id="market-town",
        name="Qinghe market town",
        kind="town",
        parent_id="azure-peak",
        routes=[Route(to_id="well", travel_s=6 * 60 * MINUTE, mode="on foot")],
        known_by=["lin"],
    )
    state.places["well"].routes.append(
        Route(to_id="market-town", travel_s=6 * 60 * MINUTE, mode="on foot")
    )
    return state
