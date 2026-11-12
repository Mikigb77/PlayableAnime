"""Example worlds from the requirements (G1 to G3, T17), for tests and development.

- `grounded_world()`: Luca Esposito in Naples, 1974. No magic, and that won't change.
- `cultivation_world()`: Lin Feng, the weakest outer disciple of the Azure Cloud Sect, with a past
  life's memories and time stop that lasts three heartbeats.
- `farm_world()`: Tomas Weller, a farmer with a wife and no ambitions, for T17's quiet-life runs.

Both run on the same rules (G5). Each call returns a fresh state, so tests can change it freely.
"""

from engine.base import DAY, HOUR, MINUTE
from engine.state import (
    Agenda,
    Attitude,
    Attributes,
    Calendar,
    CalendarStyle,
    Character,
    CharacterSheet,
    Clock,
    Condition,
    Connection,
    ConnectionKind,
    CostKind,
    Disposition,
    Extraordinary,
    Faction,
    GiftStrength,
    Goal,
    HitMode,
    Item,
    ItemKind,
    LadderPosition,
    Law,
    Medicine,
    Membership,
    Mystery,
    Origin,
    OriginKind,
    PendingEvent,
    Place,
    Power,
    PowerAxes,
    PowerCost,
    PowerLadder,
    Prevalence,
    Prominence,
    Reserve,
    Resources,
    Route,
    RuleTopic,
    Rung,
    SceneFrame,
    Skill,
    SkillLevel,
    Temperament,
    Thread,
    ThreadKind,
    TimeEffect,
    TimeOfDayStyle,
    TimePower,
    Trait,
    TraitKind,
    Travel,
    WorldBible,
    WorldRule,
    WorldState,
    Zeal,
)


def grounded_world() -> WorldState:
    """'I'm the son of a mafia boss in 1970s Naples, and someone inside the family killed my
    father.' (G1)"""
    luca = Character(
        id="luca",
        name="Luca Esposito",
        prominence=Prominence.KEY,
        description="A young man in a dark suit with his father's eyes and a short fuse.",
        appearance="24, lean, dark hair combed back, a scar through one eyebrow.",
        age=24,
        location_id="bar",
        memberships=[Membership(faction_id="esposito", rank="the late boss's son", loyalty=80)],
        known_by=["luca"],
        met_by=["luca"],
        sheet=CharacterSheet(
            attributes=Attributes(nerve=5, speed=4, wits=4, bearing=4),
            skills=[
                Skill(name="pistol", level=SkillLevel.SKILLED),
                Skill(name="knife work", level=SkillLevel.SKILLED),
                Skill(name="driving", level=SkillLevel.FAIR),
            ],
            traits=[
                Trait(name="hot temper", kind=TraitKind.FLAW),
                Trait(name="steady nerves under fire", kind=TraitKind.GIFT),
            ],
            disposition=Disposition(
                temperament=Temperament(
                    traits=["hot-headed", "loyal"],
                    wants=["revenge for his father"],
                    voice="Short sentences, Neapolitan slang when angry.",
                )
            ),
            resources=Resources(
                items=[
                    Item(id="pistol", name="Beretta pistol", kind=ItemKind.WEAPON),
                    Item(id="knife", name="flick knife", kind=ItemKind.WEAPON),
                    Item(id="car", name="Alfa Romeo Giulia", kind=ItemKind.VEHICLE, carried=False),
                ],
                money=200_000,
                currency="lire",
                family_name="Esposito",
                connections=[
                    Connection(name="three loyal soldiers", kind=ConnectionKind.ALLY),
                ],
            ),
            axes=PowerAxes(might=2, influence=2, wealth=2, knowledge=1, stealth=1),
        ),
    )
    carmine = Character(
        id="carmine",
        name="Carmine Russo",
        prominence=Prominence.KEY,
        description="The underboss, heavy and smiling, always in the back booth.",
        appearance="Fifties, broad, grey moustache, gold rings.",
        age=54,
        location_id="bar",
        memberships=[Membership(faction_id="esposito", rank="underboss", loyalty=20)],
        agenda=Agenda(
            goal="Be named boss by the council",
            method="Buy the crews, blame the killing on outsiders",
            secret="He ordered the killing of Luca's father.",
            clock_id="council",
        ),
        secrets=["He ordered the killing of Luca's father."],
        known_by=["luca"],
        met_by=["luca"],
        sheet=CharacterSheet(
            skills=[Skill(name="negotiation", level=SkillLevel.EXPERT)],
            disposition=Disposition(
                attitudes={"luca": Attitude(affinity=-60, fear=20, trust=-40, apparent_affinity=40)}
            ),
            axes=PowerAxes(might=3, influence=4, wealth=3, knowledge=2, stealth=2),
        ),
    )
    bartender = Character(
        id="bartender",
        name="Gennaro",
        description="The bartender, polishing the same glass for an hour.",
        location_id="bar",
    )
    bible = WorldBible(
        title="The Esposito Succession",
        genre="grounded crime",
        tone="noir",
        era="Naples, 1974: pistols, cars, telephones and the morning papers",
        extraordinary=[
            Extraordinary(
                id="supernatural",
                kind="magic or anything supernatural",
                prevalence=Prevalence.NONE,
                rule_ids=["no-supernatural"],
            )
        ],
        calendar=Calendar(
            style=CalendarStyle.GREGORIAN,
            time_of_day=TimeOfDayStyle.CLOCK,
            epoch="1974-05-14T21:00",
        ),
        travel=Travel(
            description="Cars, scooters and telephones. A witness can call within seconds.",
            instant_messages=True,
        ),
        medicine=Medicine(healing="A hospital and weeks of rest."),
        laws=[
            Law(
                id="state-law",
                text="Murder and assault are crimes.",
                enforcer="the Polizia di Stato",
                enforcer_faction_id="police",
                zeal=Zeal.MEDIUM,
                corruptible=True,
            ),
            Law(
                id="omerta",
                text="Nobody talks to the police.",
                enforcer="the Esposito family",
                enforcer_faction_id="esposito",
                zeal=Zeal.HIGH,
            ),
        ],
        norms=["Killing a made man without the council's leave is the worst betrayal."],
        rules=[
            WorldRule(
                id="no-supernatural",
                text="Grounded: no magic and nothing supernatural, and that won't change.",
                fixed=True,
                topic=RuleTopic.EXISTENCE,
            ),
            WorldRule(
                id="human-limits",
                text="Nobody can do more than a real person could.",
                fixed=True,
                topic=RuleTopic.LIMITS,
            ),
        ],
        mysteries=[
            Mystery(
                id="who-ordered",
                question="Who inside the family ordered the killing of Luca's father?",
                answer="Carmine Russo, the underboss.",
                clues=["Carmine's driver was seen near the docks that night."],
                thread_id="revenge",
            )
        ],
    )
    return WorldState(
        bible=bible,
        player_id="luca",
        characters={c.id: c for c in (luca, carmine, bartender)},
        factions={
            "esposito": Faction(
                id="esposito",
                name="the Esposito family",
                kind="crime family",
                description="Three crews and a council that picks the boss.",
                leader_ids=["carmine"],
                goal="Pick a new boss before the other families smell weakness.",
                strength="Three crews of soldiers, cops on the payroll.",
                known_by=["luca"],
            ),
            "carmine-crew": Faction(
                id="carmine-crew",
                name="Carmine's crew",
                kind="crew",
                parent_id="esposito",
                leader_ids=["carmine"],
                known_by=["luca"],
            ),
            "police": Faction(
                id="police",
                name="the Polizia di Stato in Naples",
                kind="police",
                strength="Patrol cars, detectives, a few honest men.",
                known_by=["luca"],
            ),
        },
        places={
            "naples": Place(id="naples", name="Naples", kind="city", known_by=["luca"]),
            "bar": Place(
                id="bar",
                name="Carmine's bar",
                kind="building",
                parent_id="naples",
                controller_id="carmine-crew",
                mood="smoky, watchful",
                routes=[Route(to_id="questura", travel_s=12 * MINUTE, mode="by car")],
                known_by=["luca"],
                visited_by=["luca"],
            ),
            "questura": Place(
                id="questura",
                name="the Questura",
                kind="building",
                parent_id="naples",
                controller_id="police",
                routes=[Route(to_id="bar", travel_s=12 * MINUTE, mode="by car")],
                known_by=["luca"],
            ),
        },
        goals={
            "find-killer": Goal(id="find-killer", text="Find out who killed my father."),
        },
        threads={
            "revenge": Thread(
                id="revenge",
                title="Who killed the boss",
                kind=ThreadKind.MYSTERY,
                stakes="Luca's revenge, and the family's future.",
                involved_ids=["luca", "carmine", "esposito"],
                clock_id="council",
                origin=Origin(kind=OriginKind.PREMISE),
                known_by=["luca"],
            )
        },
        clocks={
            "council": Clock(
                id="council",
                name="The council picks the next boss",
                steps=[
                    "The capos start counting votes.",
                    "Carmine buys the second crew.",
                    "The council meets.",
                    "A new boss is named.",
                ],
                interval_s=60 * HOUR,
                next_step_s=60 * HOUR,
                owner_id="esposito",
                thread_id="revenge",
                known_by=["luca"],
            )
        },
        pending_events={
            "council-meets": PendingEvent(
                id="council-meets",
                kind="clock_end",
                title="The council names the next boss",
                due_s=10 * DAY,
                needs_player=False,
                subject_ids=["esposito"],
                origin=Origin(kind=OriginKind.CLOCK, ref_id="council"),
            )
        },
        scene=SceneFrame(
            place_id="bar",
            present_ids=["luca", "carmine", "bartender"],
            positions=["Carmine in the back booth", "Luca at the door"],
            props=["a bottle of grappa on the bar", "a telephone behind the bar"],
            ended_on="Carmine looks up from his cards and smiles at Luca.",
        ),
        summary="Luca is back in Naples after his father's murder.",
    )


def cultivation_world() -> WorldState:
    """'I'm reborn as the weakest outer disciple of the Azure Cloud Sect, with my past life's
    memories and the power to stop time.' (G1)"""
    lin = Character(
        id="lin",
        name="Lin Feng",
        prominence=Prominence.KEY,
        description="A thin outer disciple in a patched grey robe, calm beyond his years.",
        appearance="16, slight, black hair tied back, steady eyes.",
        age=16,
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="outer disciple", loyalty=50)],
        known_by=["lin"],
        met_by=["lin"],
        sheet=CharacterSheet(
            attributes=Attributes(strength=2, toughness=2, wits=5, willpower=5),
            skills=[Skill(name="herb lore", level=SkillLevel.FAIR)],
            traits=[
                Trait(name="a past life's memories", kind=TraitKind.GIFT),
                Trait(name="a weak body", kind=TraitKind.FLAW),
            ],
            powers=[
                Power(
                    id="time-stop",
                    name="time stop",
                    description="Stops the world for three heartbeats.",
                    strength=GiftStrength.OVERPOWERED,
                    limits=["three heartbeats per use", "a breath to recharge"],
                    costs=[PowerCost(kind=CostKind.FATIGUE, text="Leaves him drained.")],
                    secret=True,
                    time=TimePower(
                        effect=TimeEffect.STOP,
                        hit_mode=HitMode.RELATIVE_SPEED,
                        lasts_s=3,
                        recharge_s=5,
                    ),
                )
            ],
            disposition=Disposition(
                temperament=Temperament(traits=["calm", "patient"], wants=["to climb"])
            ),
            resources=Resources(rank="outer disciple", family_name="the fallen Lin clan"),
            condition=Condition(reserves=[Reserve(name="qi", level=40, recovery_s=DAY)]),
            axes=PowerAxes(might=2, influence=1, wealth=1, knowledge=3, stealth=2),
            ladders=[LadderPosition(ladder_id="realms", rung=0, stage="early")],
        ),
    )
    zhao = Character(
        id="zhao",
        name="Zhao Kun",
        aliases=["Senior Brother Zhao"],
        prominence=Prominence.KEY,
        description="A broad-shouldered senior disciple who enjoys kicking buckets over.",
        age=19,
        location_id="well",
        memberships=[Membership(faction_id="outer-court", rank="senior disciple", loyalty=70)],
        known_by=["lin"],
        met_by=["lin"],
        sheet=CharacterSheet(
            attributes=Attributes(strength=5, toughness=5),
            skills=[Skill(name="fist techniques", level=SkillLevel.SKILLED)],
            disposition=Disposition(attitudes={"lin": Attitude(affinity=-30, fear=0)}),
            axes=PowerAxes(might=4, influence=2),
            ladders=[LadderPosition(ladder_id="realms", rung=1, stage="early")],
        ),
    )
    elder = Character(
        id="elder-mo",
        name="Elder Mo",
        prominence=Prominence.KEY,
        description="An inner-court elder who looks like a sleepy old man.",
        age=212,
        location_id="inner-court",
        memberships=[Membership(faction_id="inner-court", rank="elder", loyalty=90)],
        sheet=CharacterSheet(
            axes=PowerAxes(might=6, influence=5, knowledge=6),
            ladders=[LadderPosition(ladder_id="realms", rung=2, stage="late")],
        ),
    )
    bible = WorldBible(
        title="Three Heartbeats",
        genre="cultivation",
        tone="wonder, ambition and sect politics",
        era="An ancient realm of sects, swords, pills and spirit stones",
        extraordinary=[
            Extraordinary(
                id="qi",
                kind="qi cultivation",
                prevalence=Prevalence.COMMON,
                reach="Realms from Qi Condensation to Nascent Soul and beyond.",
                rule_ids=["qi-exists", "realm-ceiling"],
            ),
            Extraordinary(
                id="time-powers",
                kind="powers over time",
                prevalence=Prevalence.RARE,
                rule_ids=["time-powers-exist"],
            ),
        ],
        ladders=[
            PowerLadder(
                id="realms",
                name="cultivation realms",
                rungs=[
                    Rung(name="Qi Condensation", tier=2),
                    Rung(name="Foundation Establishment", tier=4),
                    Rung(name="Core Formation", tier=6),
                    Rung(name="Nascent Soul", tier=8),
                    Rung(name="Soul Transformation", tier=10),
                ],
                sensing=True,
            )
        ],
        calendar=Calendar(style=CalendarStyle.DAY_COUNT, start_second_of_day=7 * HOUR),
        travel=Travel(description="On foot, by flying sword for the strong, by message talisman."),
        medicine=Medicine(healing="Pills heal in days what would take months."),
        laws=[
            Law(
                id="sect-rules",
                text="Disciples may not kill each other within the sect.",
                enforcer="the Law Enforcement Hall",
                enforcer_faction_id="azure-cloud",
                zeal=Zeal.HIGH,
            )
        ],
        rules=[
            WorldRule(
                id="qi-exists",
                text="Qi cultivation is real and everywhere.",
                fixed=True,
                topic=RuleTopic.EXISTENCE,
            ),
            WorldRule(
                id="time-powers-exist",
                text="A rare few can bend time.",
                fixed=True,
                topic=RuleTopic.EXISTENCE,
            ),
            WorldRule(
                id="realm-ceiling",
                text="Nobody is known to have passed Soul Transformation.",
                fixed=False,
                topic=RuleTopic.LIMITS,
            ),
        ],
    )
    return WorldState(
        bible=bible,
        player_id="lin",
        characters={c.id: c for c in (lin, zhao, elder)},
        factions={
            "azure-cloud": Faction(
                id="azure-cloud",
                name="the Azure Cloud Sect",
                kind="sect",
                goal="Win the regional ranking.",
                known_by=["lin"],
            ),
            "outer-court": Faction(
                id="outer-court",
                name="the outer court",
                kind="court",
                parent_id="azure-cloud",
                known_by=["lin"],
            ),
            "inner-court": Faction(
                id="inner-court",
                name="the inner court",
                kind="court",
                parent_id="azure-cloud",
                known_by=["lin"],
            ),
        },
        places={
            "azure-peak": Place(
                id="azure-peak", name="Azure Peak", kind="region", known_by=["lin"]
            ),
            "well": Place(
                id="well",
                name="the outer-court well",
                kind="courtyard",
                parent_id="azure-peak",
                routes=[Route(to_id="inner-court", travel_s=40 * MINUTE, mode="on foot")],
                known_by=["lin"],
                visited_by=["lin"],
            ),
            "inner-court": Place(
                id="inner-court",
                name="the inner court",
                kind="halls",
                parent_id="azure-peak",
                routes=[Route(to_id="well", travel_s=40 * MINUTE, mode="on foot")],
                known_by=["lin"],
            ),
        },
        threads={
            "tournament": Thread(
                id="tournament",
                title="The ranking tournament",
                kind=ThreadKind.AMBITION,
                stakes="A place in the inner court, or a year more as everyone's servant.",
                involved_ids=["lin", "zhao", "outer-court"],
                clock_id="tournament",
                origin=Origin(kind=OriginKind.PREMISE),
                known_by=["lin"],
            )
        },
        clocks={
            "tournament": Clock(
                id="tournament",
                name="The ranking tournament",
                steps=["Names are posted.", "The brackets are drawn.", "The tournament begins."],
                interval_s=16 * HOUR,
                next_step_s=16 * HOUR,
                owner_id="outer-court",
                thread_id="tournament",
                known_by=["lin"],
            )
        },
        scene=SceneFrame(
            place_id="well",
            present_ids=["lin", "zhao"],
            positions=["Lin at the well with a full bucket", "Zhao two steps away"],
            props=["a wooden bucket of water", "the stone rim of the well"],
            ended_on="Zhao grins and draws back his foot toward the bucket.",
        ),
        summary="Lin Feng wakes in the outer court with a past life's memories.",
    )


def farm_world() -> WorldState:
    """'I farm a small plot in a river valley with my wife, and I want nothing more.' (T17's quiet
    life: no ambitions, no factions, no clocks, so every event has to come from the director.)"""
    tomas = Character(
        id="tomas",
        name="Tomas Weller",
        prominence=Prominence.KEY,
        description="A broad, sunburnt farmer with a slow smile.",
        appearance="34, broad shoulders, sandy hair, a farmer's hands.",
        age=34,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
        sheet=CharacterSheet(
            attributes=Attributes(strength=4, toughness=4),
            skills=[
                Skill(name="farming", level=SkillLevel.EXPERT),
                Skill(name="carpentry", level=SkillLevel.FAIR),
            ],
            disposition=Disposition(
                temperament=Temperament(traits=["patient", "kind"], wants=["a quiet life"])
            ),
            resources=Resources(money=40, currency="silver pennies"),
        ),
    )
    ilse = Character(
        id="ilse",
        name="Ilse Weller",
        prominence=Prominence.KEY,
        description="Tomas's wife, quick-witted and quicker to laugh.",
        appearance="32, dark braid, flour on her sleeves.",
        age=32,
        location_id="farm",
        known_by=["tomas"],
        met_by=["tomas"],
        sheet=CharacterSheet(
            disposition=Disposition(attitudes={"tomas": Attitude(affinity=80, trust=80)})
        ),
    )
    bram = Character(
        id="bram",
        name="Old Bram",
        description="The neighbour, who has an opinion about every fence.",
        age=71,
        location_id="village",
        known_by=["tomas"],
        met_by=["tomas"],
        sheet=CharacterSheet(
            disposition=Disposition(attitudes={"tomas": Attitude(affinity=30, trust=40)})
        ),
    )
    bible = WorldBible(
        title="The Long Valley",
        genre="pastoral",
        tone="warm, with small joys and small troubles",
        era="A river valley of villages, ox carts and market days",
        extraordinary=[
            Extraordinary(
                id="supernatural",
                kind="magic or anything supernatural",
                prevalence=Prevalence.NONE,
                rule_ids=["no-supernatural"],
            )
        ],
        calendar=Calendar(style=CalendarStyle.DAY_COUNT, start_second_of_day=6 * HOUR),
        travel=Travel(description="On foot and by ox cart. News moves at market speed."),
        medicine=Medicine(healing="Herbs, rest and the village healer."),
        rules=[
            WorldRule(
                id="no-supernatural",
                text="Nothing supernatural, and that won't change.",
                fixed=True,
                topic=RuleTopic.EXISTENCE,
            )
        ],
    )
    return WorldState(
        bible=bible,
        player_id="tomas",
        characters={c.id: c for c in (tomas, ilse, bram)},
        places={
            "valley": Place(id="valley", name="the Long Valley", kind="region", known_by=["tomas"]),
            "farm": Place(
                id="farm",
                name="the Weller farm",
                kind="farm",
                parent_id="valley",
                mood="quiet, muddy, content",
                routes=[Route(to_id="village", travel_s=40 * MINUTE, mode="on foot")],
                known_by=["tomas"],
                visited_by=["tomas"],
            ),
            "village": Place(
                id="village",
                name="Millbrook",
                kind="village",
                parent_id="valley",
                routes=[Route(to_id="farm", travel_s=40 * MINUTE, mode="on foot")],
                known_by=["tomas"],
                visited_by=["tomas"],
            ),
        },
        scene=SceneFrame(
            place_id="farm",
            present_ids=["tomas", "ilse"],
            positions=["Tomas at the gate", "Ilse in the doorway"],
            props=["a hoe leaning on the fence", "a bucket of feed"],
            ended_on="Ilse calls from the doorway that supper is ready.",
        ),
        summary="Tomas and Ilse farm a small plot in the Long Valley.",
    )
