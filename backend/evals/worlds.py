"""The scenarios' starting worlds, from T15's, T17's and T18's scripts, built on the sample worlds
(`engine.samples`). Each call returns a fresh state, so a scenario can change it freely.
"""

from __future__ import annotations

from engine.base import DAY, HOUR, MINUTE
from engine.samples import cultivation_world, farm_world, grounded_world
from engine.state import (
    Attitude,
    Attributes,
    Bond,
    BondStage,
    BondStep,
    Character,
    CharacterSheet,
    Condition,
    Connection,
    ConnectionKind,
    CostKind,
    Creature,
    Disposition,
    Encounter,
    EncounterKind,
    Extraordinary,
    Fact,
    Faction,
    Faith,
    GiftStrength,
    Health,
    HitMode,
    Item,
    ItemKind,
    LadderPosition,
    Mastery,
    Membership,
    PassingState,
    PendingEvent,
    People,
    Place,
    PlaceSetting,
    Power,
    PowerAxes,
    PowerCost,
    Prevalence,
    Prominence,
    Resources,
    Route,
    RuleTopic,
    Rumor,
    SceneFrame,
    Skill,
    SkillLevel,
    Talent,
    TalentCover,
    TalentFit,
    TalentRuling,
    TalentStrength,
    Technique,
    Trait,
    TraitKind,
    Unions,
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
        description="A gaunt mage in grey robes, crackling with power, who means to test Lin, "
        "parrying and pressing him without striking to hurt.",
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


def one_witness() -> WorldState:
    """`sect_with_a_witness` with Zhao away at the inner court, so Wei is the only one at the
    well to see what is done to Han. The scene says the yard is otherwise empty: read on the
    real model (2026-11-11), a sect's courtyard by day could pass for a place with a crowd."""
    state = sect_with_a_witness()
    state.characters["zhao"].location_id = "inner-court"
    state.scene.present_ids.remove("zhao")
    state.scene.ended_on = (
        "Han Jie dozes against the well, and Wei draws water beside him. "
        "Nobody else is in the yard."
    )
    return state


IN_THE_BARN = (
    "In the barn, the drifter Jorn Hask sleeps in the hay with a ham from the Wellers' "
    "smokehouse beside him, and Pim, the hired hand, has stopped in the doorway with a pail."
)


def thief_in_the_barn(*, two_saw: bool = False) -> WorldState:
    """The farm world, where nobody keeps a law and no faction holds anything: what is done on
    the farm becomes talk, and whatever the dead man's own make of it. Jorn Hask, a drifter who
    has been stealing from the smokehouse, sleeps in the hay: his sheet says he is asleep, so
    whether a blade reaches him hangs on no roll (A2). Pim, the hired hand, stands in the
    doorway, the one person who would see it done. Jorn's elder brother Kasper is a carter who
    lodges in Millbrook, where Old Bram lives. Ilse is in the house and sees nothing of the
    barn. With `two_saw`, a second hand, Henk, is in the barn as well."""
    state = farm_world()
    give(state, "tomas", Item(id="knife", name="butchering knife", kind=ItemKind.WEAPON))
    jorn = Character(
        id="jorn",
        name="Jorn Hask",
        description="A drifter who has been stealing from the Wellers' smokehouse.",
        age=29,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
    )
    jorn.sheet.condition.states.append(PassingState(name="asleep"))
    pim = Character(
        id="pim",
        name="Pim",
        description="The Wellers' hired hand, a talkative lad from Millbrook.",
        age=19,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
    )
    kasper = Character(
        id="kasper",
        name="Kasper Hask",
        prominence=Prominence.KEY,
        description="Jorn's elder brother, a carter who lodges at the Millbrook inn.",
        age=36,
        location_id="village",
        known_by=["tomas"],
        met_by=["tomas"],
    )
    kasper.sheet.resources.connections.append(
        Connection(name="Jorn Hask", kind=ConnectionKind.FAMILY, character_id="jorn")
    )
    add(state, kasper, present=False)
    state.scene = state.scene.model_copy(
        update={
            "present_ids": ["tomas"],
            "positions": ["Jorn asleep in the hay", "Pim in the barn doorway", "Tomas inside"],
            "props": ["a pitchfork by the door", "a half-eaten ham in the hay"],
            "ended_on": IN_THE_BARN,
        }
    )
    add(state, jorn, pim)
    if two_saw:
        henk = Character(
            id="henk",
            name="Henk",
            description="The Wellers' older hired hand, forking hay down from the loft.",
            age=44,
            location_id="farm",
            known_by=["tomas"],
            met_by=["tomas"],
        )
        add(state, henk)
    return state


THRONGED_WELL = (
    "Noon at the outer-court well, and it is thronged: a long queue of disciples with buckets, "
    "hawkers calling, servants pushing through. Han Jie dozes on the rim of the well in the "
    "heat, and the queue shuffles round him."
)


def noon_at_the_well() -> WorldState:
    """The well at noon, thronged with people the scene doesn't name. Han Jie, who takes Lin's
    rations, dozes on its rim in the middle of them: his sheet says he is asleep, so whether a
    blade reaches him hangs on no roll (A2). His elder brother Han Lei is in the inner court and
    sees nothing of what happens at the well; nobody else the record holds is there."""
    state = sect()
    outer = Membership(faction_id="outer-court", rank="outer disciple", loyalty=60)
    han = disciple(
        "han",
        "Han Jie",
        description="An outer disciple who takes Lin's rations, dozing on the rim of the well.",
        memberships=[outer],
    )
    han.sheet.condition.states.append(PassingState(name="asleep"))
    lei = disciple(
        "han-lei",
        "Han Lei",
        rung=1,
        description="Han Jie's elder brother, who looks after him.",
        memberships=[outer.model_copy(update={"rank": "senior outer disciple"})],
    )
    lei.location_id = "inner-court"
    lei.sheet.resources.connections.append(
        Connection(name="Han Jie", kind=ConnectionKind.FAMILY, character_id="han")
    )
    state.characters["zhao"].location_id = "inner-court"
    add(state, han)
    add(state, lei, present=False)
    state.scene = state.scene.model_copy(
        update={
            "present_ids": ["lin", "han"],
            "positions": ["Han Jie asleep on the rim of the well", "Lin a few steps from him"],
            "props": ["the stone rim of the well", "a long queue of disciples with buckets"],
            "ended_on": THRONGED_WELL,
        }
    )
    return state


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


GUO_CHARGES = "Guo Tai lowers his shoulder and charges, blade first."
GUO_CIRCLES = "Guo Tai circles, blade low, waiting."


def duel(*, rung: int = 0, counter: bool = True, charging: bool = True) -> WorldState:
    """Lin and Guo Tai, two swordsmen, Guo on `rung` of the realms; Lin knows a counter to Guo's
    Iron Ox style when `counter` says so, as well as he knows his sword (G25). The scene left
    off with Guo charging, which is what the counter answers, unless `charging` says he only
    circles."""
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
                mastery=Mastery.SKILLED,
            )
        )
    state.scene.ended_on = GUO_CHARGES if charging else GUO_CIRCLES
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


def spark_palm() -> WorldState:
    """Lin in the yard at night with an unlit lantern and a small move he has practiced: a
    Spark Palm that lights a wick (A4, A2)."""
    state = sect()
    state.characters["lin"].sheet.techniques.append(
        Technique(
            id="spark-palm",
            name="Spark Palm",
            effect="A flick of qi off the palm that lights a wick or tinder.",
            mastery=Mastery.PRACTICED,
        )
    )
    state.scene.ended_on = "The lantern by the well has gone out."
    return state


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


def seclusion(
    *, stage: str = "peak", pill: bool = False, summons_in_s: int | None = None
) -> WorldState:
    """Lin at the peak of Qi Condensation, ready to try for Foundation Establishment (G19), or
    at an earlier `stage` of it. The world says the climb takes a Foundation Pill, which he
    doesn't have unless `pill` is set, and nothing a rung lists is required. With
    `summons_in_s`, the sect sends for him that long into his seclusion, and it needs him
    (W10)."""
    state = sect()
    state.bible.ladders[0].rungs[1].needs = ["a Foundation Pill"]
    state.characters["lin"].sheet.ladders = [
        LadderPosition(ladder_id="realms", rung=0, stage=stage)
    ]
    if pill:
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
    state.scene.ended_on = (
        "Young Master Wu laughs at Lin's patched robes in front of the well, "
        "with half the outer court looking on."
    )
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
            description="An unarmed envoy among the sect's elders, here to talk.",
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


def among_the_pines() -> WorldState:
    """Lin alone at dawn under the old pines behind the well, with nothing on him: no sword, no
    knife (T18's moment as told, M5, C10)."""
    state = cultivation_world()
    state.characters["zhao"].location_id = "inner-court"
    state.scene = SceneFrame(
        place_id="well",
        present_ids=["lin"],
        positions=["Lin at the foot of the old pines behind the well"],
        props=["old pines with low, thick branches", "the outer wall beyond them"],
        ended_on="Mist hangs in the old pines behind the well, and the outer wall rises past them.",
    )
    return state


def above_the_camp() -> WorldState:
    """Lin and Zhao on top of the old wall of the Broken Arches at dusk, with travelling clans
    camped far below among the arches (T18's feet on the ground, M5)."""
    state = cultivation_world()
    state.places["arches"] = Place(
        id="arches",
        name="the Broken Arches",
        kind="ruins",
        description=(
            "Colossal broken stone arches and an old wall along a snowy ridge, the ruin of an "
            "ancient gate, above a hollow where travelling clans camp among the arches."
        ),
        parent_id="azure-peak",
        setting=PlaceSetting.OUTDOORS,
        known_by=["lin"],
        visited_by=["lin"],
    )
    for character_id in ("lin", "zhao"):
        state.characters[character_id].location_id = "arches"
    state.world_s = 10 * HOUR + 30 * MINUTE  # 17:30 on a day that starts at 7: dusk
    state.scene = SceneFrame(
        place_id="arches",
        present_ids=["lin", "zhao"],
        positions=["Lin and Zhao on top of the old wall, above the camp"],
        props=["the broken top of the old wall", "tents and bonfires far below among the arches"],
        ended_on="Lin and Zhao stand on the old wall as dusk falls over the camp below.",
    )
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


def elder_bai(*, sparring: bool = False) -> WorldState:
    """Lin before Elder Bai, three realms above him, at the well: an enemy of the outer court, or
    his master sparring with him (N6)."""
    state = sect()
    about = (
        "Lin's master, sparring with him to test his footwork, holding back his strength."
        if sparring
        else "An elder who despises outer disciples, and kills those who raise a hand to him."
    )
    return add(state, disciple("bai", "Elder Bai", rung=3, description=about))


def bridge_ambush() -> WorldState:
    """Lin on a rope bridge high over a river gorge, with three thugs of his own strength closing
    in, knives out (N6)."""
    state = sect()
    state.places["bridge"] = Place(
        id="bridge", name="the rope bridge over the gorge", kind="bridge", parent_id="azure-peak"
    )
    state.characters["lin"].location_id = "bridge"
    state.scene = SceneFrame(
        place_id="bridge",
        present_ids=["lin"],
        ended_on="Three thugs step onto the bridge from both ends, knives out. The river roars "
        "thirty meters below.",
    )
    thugs = [
        disciple(f"thug-{n}", f"the {nth} thug", description="A hired thug with a long knife.")
        for n, nth in enumerate(("first", "second", "third"))
    ]
    for thug in thugs:
        thug.location_id = "bridge"
    return add(state, *thugs)


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


def potion_stall() -> WorldState:
    """Old Hu the herbalist by the well, a healing draught on his board, and a gold tael in Lin's
    purse: an action as small as paying, which the scene still tells before Hu answers (R1)."""
    state = give(
        sect(),
        "lin",
        Item(id="gold-tael", name="gold tael", kind=ItemKind.TREASURE, description="In his purse."),
    )
    herbalist = Character(
        id="old-hu",
        name="Old Hu",
        description="A stooped herbalist who sells pills and draughts from a board by the well.",
        location_id="well",
        sheet=CharacterSheet(axes=PowerAxes(might=1)),
    )
    state.scene.props.append("a stoppered green healing draught on Old Hu's board")
    state.scene.ended_on = (
        "Old Hu taps the green draught on his board. 'Mends any wound by morning, young master.'"
    )
    return add(state, herbalist)


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


def born_to_the_blade(*, talents: bool = True) -> WorldState:
    """Lin with an awakened aura, an Aura blade he is only starting to learn, an architect's
    training, and the two talents his player wrote when the story was made: one of a kind with
    the sword, and a genius for structure (A4). Without `talents` he is the same Lin with none,
    to measure the pace against."""
    state = sect()
    sheet = state.characters["lin"].sheet
    sheet.powers.append(
        Power(
            id="aura",
            name="Aura",
            description="An inner spring of aura that he shapes at will.",
            costs=[PowerCost(kind=CostKind.ENERGY, text="Spends aura.")],
        )
    )
    sheet.techniques.append(
        Technique(id="aura-blade", name="Aura blade", power_id="aura", mastery=Mastery.LEARNING)
    )
    sheet.skills.append(Skill(name="architecture", level=SkillLevel.EXPERT))
    if talents:
        sheet.talents = [
            Talent(
                id="talent-the-sword",
                name="The sword",
                covers="anything fought with a blade",
                strength=TalentStrength.ONE_OF_A_KIND,
                reason="He was born with a sword in his hand.",
            ),
            Talent(
                id="talent-genius-architect",
                name="Genius architect",
                covers="structure, load and geometry",
                strength=TalentStrength.GENIUS,
            ),
        ]
    state.scene.ended_on = "The practice post by the well stands scarred and waiting."
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


def buried_temple() -> WorldState:
    """Lin at the foot of the stairs out of a temple buried under the Whispering Wood, grey
    daylight far above (R8; Miki, 2026-11-08: a scene took the character from a temple under the
    earth to "un claro", and the next had them still inside it)."""
    state = sect()
    state.places["wood"] = Place(
        id="wood",
        name="the Whispering Wood",
        kind="wilds",
        setting=PlaceSetting.OUTDOORS,
        description="Old pines and ferns on the slopes below Azure Peak.",
        parent_id="azure-peak",
        known_by=["lin"],
        visited_by=["lin"],
    )
    state.places["temple"] = Place(
        id="temple",
        name="the Sunken Temple",
        kind="building",
        setting=PlaceSetting.UNDERGROUND,
        description="Carved halls under the earth, lit by blue runes on the pillars.",
        parent_id="wood",
        known_by=["lin"],
        visited_by=["lin"],
    )
    state.characters["lin"].location_id = "temple"
    state.characters["zhao"].location_id = "well"
    state.scene = SceneFrame(
        place_id="temple",
        present_ids=["lin"],
        positions=["Lin at the foot of the worn stairs"],
        ended_on="Lin stands at the foot of the worn stairs; far above, a thin grey daylight.",
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


MARA = "mara-voss"
AT_THE_GATE = (
    "Mara Voss has stopped at the gate with a sack of flour for the kitchen, and waits to see "
    "what Tomas wants."
)


def millers_daughter() -> WorldState:
    """The farm world with Tomas living alone, for a romance (W17): no wife, and nothing on
    record between him and anyone. Mara Voss, the miller's daughter, has stopped at his gate.
    She likes him well enough as a neighbour and feels nothing more for him yet, and her heart
    is one that rests a day after it moves (`engine.bonds.pace`, which follows from her id)."""
    state = farm_world()
    del state.characters["ilse"]
    state.bonds.clear()
    mara = Character(
        id=MARA,
        name="Mara Voss",
        prominence=Prominence.KEY,
        description="The miller's daughter, who brings the flour round and speaks her mind.",
        appearance="29, strong arms, flour in her dark hair.",
        age=29,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
    )
    mara.sheet.disposition.attitudes["tomas"] = Attitude(affinity=30, trust=30)
    state.scene = state.scene.model_copy(
        update={
            "present_ids": ["tomas"],
            "positions": ["Tomas at the gate", "Mara on the lane with a sack of flour"],
            "ended_on": AT_THE_GATE,
        }
    )
    state.summary = "Tomas Weller farms a small plot in the Long Valley, alone."
    return add(state, mara)


JORN = "jorn-hale"
AT_THE_MILL = (
    "Mara Voss is shutting the mill for the evening, and old Bram watches the lane from his "
    "bench across it."
)


def _evening_in_millbrook(state: WorldState, *, drawn: int) -> WorldState:
    """Tomas in Millbrook of an evening, with Mara Voss at the mill door and old Bram on his
    bench, who sees everything on the lane. `drawn` is how drawn Mara is to Tomas. The story
    opens at eight in the evening by its own clock: with the farm's dawn on it, a night
    together ran from dawn into the afternoon, and the real narrator told it as that
    (2026-11-13)."""
    state.bible.calendar.start_second_of_day = 20 * HOUR
    mara = state.characters[MARA]
    mara.location_id = "village"
    mara.sheet.disposition.attitudes["tomas"] = Attitude(affinity=40, trust=40, attraction=drawn)
    state.characters["tomas"].location_id = "village"
    state.scene = state.scene.model_copy(
        update={
            "place_id": "village",
            "present_ids": ["tomas", MARA, "bram"],
            "positions": ["Tomas on the mill lane", "Mara at the mill door", "Bram on his bench"],
            "props": ["the mill wheel, still turning"],
            "ended_on": AT_THE_MILL,
        }
    )
    return state


def wife_at_home(*, heart: int = 60, drawn: int = 70) -> WorldState:
    """The farm world for a romance that wrongs someone (W17): Tomas is married to Ilse, who is
    at home on the farm, forty minutes from Millbrook, where he stands with Mara Voss and old
    Bram. Mara's heart is his for the asking (`drawn`), and `heart` is how drawn his wife still
    is to him: at 60, a betrayal takes it under what a marriage lasts on
    (`engine.bonds.LEAVES_UNDER`), and at 80 it doesn't."""
    state = millers_daughter()
    ilse = farm_world().characters["ilse"]
    ilse.sheet.disposition.attitudes["tomas"].attraction = heart
    state.characters["ilse"] = ilse
    state.bonds = farm_world().bonds
    state.summary = "Tomas and Ilse farm a small plot in the Long Valley."
    return _evening_in_millbrook(state, drawn=drawn)


def husband_in_millbrook(
    *,
    there: bool = False,
    drawn: int = 70,
    faith: Faith = Faith.ROVING,
    theirs: int = 40,
    unions: Unions = Unions.HELD,
) -> WorldState:
    """`millers_daughter` for a rival (W17): Tomas lives alone, and Mara Voss is married to Jorn
    Hale, the Millbrook smith, who thinks nothing much of Tomas either way. With `there` he is
    on the lane with them, and otherwise at his forge, in the village and out of sight. `faith`
    is how Mara holds to him when someone else courts her: by default her husband stands in
    nobody's way, so the stories about a rival are about him. `theirs` is how drawn she still
    is to him, and `unions` what the valley makes of a marriage."""
    state = millers_daughter()
    state.bible.unions = unions
    jorn = Character(
        id=JORN,
        name="Jorn Hale",
        prominence=Prominence.KEY,
        description="The Millbrook smith, Mara's husband: a quiet man with a long memory.",
        appearance="33, heavy shoulders, burn scars on both forearms.",
        age=33,
        location_id="village",
        known_by=["tomas"],
        met_by=["tomas"],
        sheet=CharacterSheet(
            attributes=Attributes(strength=5, toughness=4),
            skills=[Skill(name="smithing", level=SkillLevel.EXPERT)],
            disposition=Disposition(
                attitudes={
                    "tomas": Attitude(affinity=10, trust=20),
                    MARA: Attitude(affinity=70, trust=70, attraction=70),
                }
            ),
        ),
    )
    state.characters[JORN] = jorn
    state.characters[MARA].description = "The miller's daughter and the smith's wife."
    state.characters[MARA].faith = faith
    state.characters[MARA].sheet.disposition.attitudes[JORN] = Attitude(
        affinity=50, trust=60, attraction=theirs
    )
    state.bonds["bond-1"] = Bond(
        id="bond-1",
        a_id=JORN,
        b_id=MARA,
        stage=BondStage.MARRIED,
        steps=[BondStep(stage=BondStage.MARRIED, how="As the story opens.")],
    )
    state = _evening_in_millbrook(state, drawn=drawn)
    if there:
        state.scene.present_ids.append(JORN)
        state.scene.positions.append("Jorn in the forge door, wiping his hands")
    return state


def sweethearts(*, heart: int = 75) -> WorldState:
    """`millers_daughter` with Tomas and Mara a couple these three months (W17), for a romance
    one of them ends: `heart` is how drawn she is to him."""
    state = millers_daughter()
    mara = state.characters[MARA]
    mara.sheet.disposition.attitudes["tomas"] = Attitude(affinity=60, trust=60, attraction=heart)
    state.bonds["bond-1"] = Bond(
        id="bond-1",
        a_id="tomas",
        b_id=MARA,
        stage=BondStage.TOGETHER,
        steps=[BondStep(stage=BondStage.TOGETHER, how="As the story opens.")],
    )
    state.scene.present_ids = ["tomas", MARA]
    state.summary = "Tomas Weller farms a small plot in the Long Valley, and walks out with Mara."
    return state


ALDITH = "sister-aldith"
PELL = "pell-voss"
MILLBROOK = (
    ("edda-marsh", "Edda Marsh", 24, "The baker's daughter, up before anyone in Millbrook."),
    ("wil-tanner", "Wil Tanner", 26, "The tanner's son, always a little too loud."),
    ("hanne-brook", "Hanne Brook", 31, "A weaver who came up the valley alone."),
    ("osric-fenn", "Osric Fenn", 35, "The carter who runs the Harrowgate road."),
    (ALDITH, "Sister Aldith", 40, "Keeper of the valley shrine, sworn to it for life."),
    (PELL, "Pell Voss", 12, "Mara's young brother, underfoot at the mill."),
)


def millbrook_he_knows() -> WorldState:
    """`husband_in_millbrook` with a village to come home to (W6): Tomas lives alone and knows
    everyone in Millbrook. Mara Voss and Jorn Hale are a settled couple, four neighbours are
    single, Sister Aldith keeps the shrine under a vow and takes no partner, and Pell is a boy
    of twelve. Harrowgate lies three days by cart beyond the village, far enough that no news
    of the valley reaches someone who lives there."""
    state = husband_in_millbrook(faith=Faith.STEADFAST, theirs=70)
    for character_id, name, age, about in MILLBROOK:
        state.characters[character_id] = Character(
            id=character_id,
            name=name,
            age=age,
            description=about,
            location_id="village",
            solitary=character_id == ALDITH,
            known_by=["tomas"],
            met_by=["tomas"],
        )
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        setting=PlaceSetting.OUTDOORS,
        routes=[Route(to_id="village", travel_s=3 * 24 * 60 * MINUTE, mode="by cart")],
        known_by=["tomas"],
    )
    state.summary = "Tomas Weller farms a small plot in the Long Valley, alone."
    return state


GRETA, ALDER, RUNA, EDDA, OSRIC = (
    "greta-marsh",
    "alder-fenn",
    "runa-fenn",
    "edda-marsh",
    "osric-fenn",
)
ELDERS = (
    (GRETA, "Greta Marsh", 79, "The old baker, Edda's grandmother, who still minds the ovens."),
    (ALDER, "Alder Fenn", 77, "Osric's father, who drove the Harrowgate road before him."),
    (RUNA, "Runa Fenn", 58, "Alder's wife and Osric's mother, who keeps the carter's books."),
)


def millbrook_grown_old() -> WorldState:
    """`millbrook_he_knows` with its old people (W6): Greta Marsh at seventy-nine, Alder Fenn
    at seventy-seven, married to Runa, nineteen years younger, the two of them Osric's
    parents, and Old Bram at seventy-one. Where people live eighty years, ten years take
    most of the three old ones and nobody else."""
    state = millbrook_he_knows()
    for character_id, name, age, about in ELDERS:
        state.characters[character_id] = Character(
            id=character_id,
            name=name,
            age=age,
            description=about,
            location_id="village",
            known_by=["tomas"],
            met_by=["tomas"],
        )
    state.characters[OSRIC].parent_ids = [ALDER, RUNA]
    state.bonds["bond-2"] = Bond(
        id="bond-2",
        a_id=ALDER,
        b_id=RUNA,
        stage=BondStage.MARRIED,
        steps=[BondStep(stage=BondStage.MARRIED, how="As the story opens.")],
    )
    return state


PEACH = "peach"


def millbrook_at_sixty(*, peach: bool = False) -> WorldState:
    """`millbrook_he_knows` years on, for his own old age (N6, W6): Tomas is sixty, on the farm
    he never left. The record gives him eighty years, as a new world's draft says of its
    character, so old age sets in for him at sixty-eight.
    With `peach` he has kept a peach from the Orchard of the Undying all his life, which gives
    whoever eats it three hundred years."""
    state = millbrook_he_knows()
    tomas = state.characters["tomas"]
    tomas.age = 60
    tomas.lifespan_years = 80
    tomas.appearance = "60, broad shoulders gone lean, grey hair, a farmer's hands."
    state.summary = "Tomas Weller has farmed a small plot in the Long Valley all his life, alone."
    if peach:
        fruit = Item(
            id=PEACH,
            name="peach from the Orchard of the Undying",
            kind=ItemKind.CONSUMABLE,
            description="A peach that never spoils. Whoever eats it lives three hundred years.",
        )
        give(state, "tomas", fruit)
    return state


def millbrook_elf_at_sixty() -> WorldState:
    """`millbrook_at_sixty` as a world drafted before peoples said how long they live (W6):
    Tomas is an elf among humans, the story has elves live for many centuries, and the record
    gives neither people a lifespan, nor him one of his own. The world takes his life for a
    human one."""
    state = millbrook_at_sixty()
    state.bible.peoples = [
        People(id="humans", name="humans"),
        People(
            id="elves",
            name="elves",
            description="Elves live for many centuries: one of sixty is barely grown.",
        ),
    ]
    for character in state.characters.values():
        character.people_id = "humans"
    tomas = state.characters["tomas"]
    tomas.people_id = "elves"
    tomas.lifespan_years = None
    tomas.description = "An elf who farms among humans, young for his kind at sixty."
    tomas.appearance = "Looks a man of twenty: fair hair, pointed ears, a farmer's hands."
    state.summary = "Tomas Weller, an elf, has farmed a small plot in the Long Valley for decades."
    return state


SAEL, WICK = "sael", "brother-wick"


def millbrook_of_three_peoples() -> WorldState:
    """`millbrook_grown_old` in a world of three peoples (G23, W6): humans, whose lifespan the
    record doesn't give, elves, who live six hundred years, and the unsleeping, the dead who
    walk, whom old age never takes. Sael, an elf of a hundred and forty, keeps bees above the
    village, and Brother Wick, seventy-one years risen, digs its graves."""
    state = millbrook_grown_old()
    state.bible.peoples = [
        People(id="humans", name="humans"),
        People(id="elves", name="elves", lifespan_years=600),
        People(id="unsleeping", name="the unsleeping", lifespan_years=0),
    ]
    for character in state.characters.values():
        character.people_id = "humans"
    for character_id, name, age, people_id, about in (
        (SAEL, "Sael", 140, "elves", "An elf who keeps bees on the slope above Millbrook."),
        (WICK, "Brother Wick", 71, "unsleeping", "One of the unsleeping dead, the gravedigger."),
    ):
        state.characters[character_id] = Character(
            id=character_id,
            name=name,
            age=age,
            people_id=people_id,
            description=about,
            location_id="village",
            known_by=["tomas"],
            met_by=["tomas"],
        )
    return state


HARROWGATE_TALK = "The old duke of Harrowgate is dead, and his two sons both claim the seat."


def long_road() -> WorldState:
    """The farm world with the city of Harrowgate three days by cart beyond Millbrook, for a
    journey (T17): the map says how far everything is, and the city has its own talk, which
    hasn't reached the valley."""
    state = farm_world()
    state.places["city"] = Place(
        id="city",
        name="Harrowgate",
        kind="city",
        setting=PlaceSetting.OUTDOORS,
        routes=[Route(to_id="village", travel_s=3 * 24 * 60 * MINUTE, mode="by cart")],
        known_by=["tomas"],
    )
    state.rumors["city-news"] = Rumor(
        id="city-news",
        text=HARROWGATE_TALK,
        is_true=True,
        origin_place_id="city",
        reached_place_ids=["city"],
        started_s=state.world_s,
    )
    return state


CROWN, LEAGUE = "crown", "league"
ALDRIC = "aldric-vane"


def kingdoms_at_war(*, marshal: bool = False) -> WorldState:
    """`long_road` with two kingdoms at war beyond the valley (W6, W7). The Crown of Harrow
    sits in Harrowgate, three days by cart from Millbrook. The Eastmark League sits in
    Eastmark and holds Willow Ford, two days from Harrowgate on the road between them. Tomas
    has heard of both and of their towns, and lives too far from any of it to see how the war
    goes. The two are evenly matched, unless the Crown has its `marshal`, a commander nothing
    the League has can stand against: then the facts settle who wins before any throw (A2)."""
    state = long_road()
    places = state.places
    places["city"].controller_id = CROWN
    places["city"].routes.append(Route(to_id="ford", travel_s=2 * DAY, mode="by road"))
    places["ford"] = Place(
        id="ford",
        name="Willow Ford",
        kind="village",
        description="A toll bridge and a row of inns where the river road crosses.",
        setting=PlaceSetting.OUTDOORS,
        controller_id=LEAGUE,
        routes=[Route(to_id="eastmark", travel_s=2 * DAY, mode="by road")],
        known_by=["tomas"],
    )
    places["eastmark"] = Place(
        id="eastmark",
        name="Eastmark",
        kind="city",
        setting=PlaceSetting.OUTDOORS,
        controller_id=LEAGUE,
        known_by=["tomas"],
    )
    state.factions[CROWN] = Faction(
        id=CROWN,
        name="the Crown of Harrow",
        kind="kingdom",
        description="The old kingdom of the upper river, ruled from Harrowgate.",
        relations={LEAGUE: -80},
        known_by=["tomas"],
    )
    state.factions[LEAGUE] = Faction(
        id=LEAGUE,
        name="the Eastmark League",
        kind="league of towns",
        description="The trading towns of the lower river, which take the Crown's tolls ill.",
        relations={CROWN: -80},
        known_by=["tomas"],
    )
    if marshal:
        state.characters[ALDRIC] = Character(
            id=ALDRIC,
            name="Marshal Aldric Vane",
            age=44,
            description="The Crown's marshal, who has never lost a field.",
            location_id="city",
            memberships=[Membership(faction_id=CROWN, rank="marshal", loyalty=90)],
            sheet=CharacterSheet(axes=PowerAxes(might=3)),
        )
    state.summary = (
        "Tomas Weller farms a small plot in the Long Valley. Down the river the Crown of "
        "Harrow and the Eastmark League have been at war for as long as he remembers."
    )
    return state


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


WEN, SU, OLD_HE, COOK_MA, ZHAO, ELDER_MO = (
    "wen-jie",
    "su-lan",
    "old-he",
    "cook-ma",
    "zhao",
    "elder-mo",
)
REALM_YEARS = (120, 250, 500, 1000, 2000)
OUTER_COURT = (
    (WEN, "Wen Jie", 16, 0, "A junior who came up the mountain the same spring as Lin."),
    (SU, "Su Lan", 15, 0, "A quiet junior the elders watch: qi gathers to her as if called."),
    (OLD_HE, "Old He", 90, 0, "The outer court's gatekeeper, at Qi Condensation all his life."),
    (COOK_MA, "Cook Ma", 40, None, "The outer court's cook, a mortal who never touched qi."),
)


def azure_peak_he_leaves(*, rung: int = 0) -> WorldState:
    """`sect` as a mountain to leave for years (W6, G19). The realms lengthen life, from 120
    years at Qi Condensation to 2,000 at Soul Transformation. Lin knows the outer court: Zhao
    Kun, at Foundation Establishment at nineteen, the juniors Wen Jie and Su Lan on the
    lowest realm, Su Lan with a knack for it, Old He the gatekeeper, still on it at ninety,
    and Cook Ma, a mortal on no realm at all. Elder Mo he has never met. The tournament is
    over and nothing is under way. Greywater lies five days down the river, far enough that
    no word of the mountain reaches someone who lives there. Lin stands on `rung`."""
    state = sect()
    for step, years in zip(state.bible.ladders[0].rungs, REALM_YEARS, strict=True):
        step.lifespan_years = years
    state.threads.clear()
    state.clocks.clear()
    state.characters["lin"].sheet.ladders = [LadderPosition(ladder_id="realms", rung=rung)]
    for character_id, name, age, on_rung, about in OUTER_COURT:
        ladders = [] if on_rung is None else [LadderPosition(ladder_id="realms", rung=on_rung)]
        state.characters[character_id] = Character(
            id=character_id,
            name=name,
            age=age,
            description=about,
            location_id="well",
            known_by=["lin"],
            met_by=["lin"],
            sheet=CharacterSheet(ladders=ladders),
        )
    gift = Talent(id="spirit-root", name="a clear spirit root", covers="gathering qi")
    cover = TalentCover(talent_id=gift.id, fit=TalentFit.INSIDE)
    sheet = state.characters[SU].sheet
    sheet.talents = [gift]
    sheet.talent_rulings = [TalentRuling(key="ladder:realms", covers=[cover])]
    state.places["town"] = Place(
        id="town",
        name="Greywater",
        kind="town",
        setting=PlaceSetting.OUTDOORS,
        routes=[Route(to_id="well", travel_s=5 * DAY, mode="on foot")],
        known_by=["lin"],
    )
    state.summary = "Lin Feng is an outer disciple of the Azure Cloud Sect, on Azure Peak."
    return state
