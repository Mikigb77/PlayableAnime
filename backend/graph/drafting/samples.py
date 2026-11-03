"""Two drafts as the model would propose them, from the requirements' examples (G1, G2): the
Naples vendetta and the reborn outer disciple with time stop. Tests script the fake model with
them, and the offline model (`LLM_PROVIDER=fake`) answers with them, so the create flow shows a
real-looking world without a model.

Each call returns a fresh proposal, so callers can change it freely.
"""

from graph.drafting.schema import (
    AgendaP,
    AttitudeP,
    AttributesP,
    AxesP,
    CalendarP,
    CharacterProposal,
    ClockP,
    ConnectionP,
    CostP,
    DraftProposal,
    ExtraordinaryP,
    FactionP,
    ItemP,
    LadderP,
    LadderPositionP,
    LawP,
    MedicineP,
    MembershipP,
    MysteryP,
    NpcP,
    OpeningP,
    PlaceP,
    PowerP,
    ReserveP,
    RouteP,
    RuleP,
    RungP,
    SkillP,
    TemperamentP,
    ThreadP,
    TimeP,
    TraitP,
    TravelP,
    WorldProposal,
)
from graph.llm.fake import FakeBackend, Reply
from graph.llm.types import Request

NAPLES_PREMISE = (
    "I'm the son of a mafia boss in 1970s Naples, and someone inside the family killed my father."
)
CULTIVATION_PREMISE = (
    "I'm reborn as the weakest outer disciple of the Azure Cloud Sect, with my past life's "
    "memories and the power to stop time."
)


def naples_world() -> WorldProposal:
    return WorldProposal(
        title="The Esposito Succession",
        genre="grounded crime",
        tone="noir",
        era="Naples, 1974: pistols, cars, telephones and the morning papers",
        extraordinary=[
            ExtraordinaryP(
                id="supernatural", kind="magic or anything supernatural", prevalence="none"
            ),
        ],
        rules=[
            RuleP(
                id="no-supernatural",
                fixed=True,
                topic="existence",
                about=["supernatural"],
                text="Grounded: no magic and nothing supernatural, and that won't change.",
            ),
            RuleP(
                id="human-limits",
                fixed=True,
                topic="limits",
                text="Nobody can do more than a real person could.",
            ),
            RuleP(
                id="omerta",
                fixed=False,
                topic="law",
                text="Nobody in the family talks to the police.",
            ),
        ],
        calendar=CalendarP(style="gregorian", clock_time=True, epoch="1974-05-14T21:00"),
        travel=TravelP(
            description="Cars, scooters and telephones. A witness can call within seconds.",
            instant_messages=True,
        ),
        medicine=MedicineP(healing="A hospital and weeks of rest."),
        laws=[
            LawP(
                id="state-law",
                text="Murder and assault are crimes.",
                enforcer="the Polizia di Stato",
                enforcer_faction_id="police",
                zeal="medium",
                corruptible=True,
            ),
        ],
        norms=["Killing a made man without the council's leave is the worst betrayal."],
        places=[
            PlaceP(id="naples", name="Naples", kind="city"),
            PlaceP(
                id="bar",
                name="Carmine's bar",
                kind="building",
                parent_id="naples",
                controller_id="carmine-crew",
                mood="smoky, watchful",
                routes=[RouteP(to_id="questura", travel_hours=0.2, mode="by car")],
            ),
            PlaceP(
                id="questura",
                name="the Questura",
                kind="building",
                parent_id="naples",
                controller_id="police",
            ),
        ],
        factions=[
            FactionP(
                id="esposito",
                name="the Esposito family",
                kind="crime family",
                description="Three crews and a council that picks the boss.",
                leader_ids=["carmine"],
                goal="Pick a new boss before the other families smell weakness.",
                strength="Three crews of soldiers, cops on the payroll.",
            ),
            FactionP(
                id="carmine-crew",
                name="Carmine's crew",
                kind="crew",
                description="The underboss's own soldiers.",
                parent_id="esposito",
                leader_ids=["carmine"],
                secrets=["The crew was paid to look away the night the boss died."],
            ),
            FactionP(
                id="police",
                name="the Polizia di Stato in Naples",
                kind="police",
                description="Patrol cars, detectives and a few honest men.",
            ),
        ],
        npcs=[
            NpcP(
                id="carmine",
                name="Carmine Russo",
                description=("The underboss, heavy and smiling, always in the back booth."),
                appearance="Fifties, broad, grey moustache, gold rings.",
                age=54,
                location_id="bar",
                memberships=[MembershipP(faction_id="esposito", rank="underboss", loyalty=20)],
                temperament=TemperamentP(
                    traits=["patient", "greedy"], voice="Warm, slow, never raises his voice."
                ),
                skills=[SkillP(name="negotiation", level="expert")],
                axes=AxesP(might=3, influence=4, wealth=3, knowledge=2, stealth=2),
                attitude_to_player=AttitudeP(affinity=-60, fear=20, trust=-40, shown_affinity=40),
                agenda=AgendaP(
                    goal="Be named boss by the council",
                    method="Buy the crews, blame the killing on outsiders",
                    secret="He ordered the killing of the boss himself.",
                    clock_id="council",
                ),
                secrets=["He ordered the killing of Luca's father in the alley behind the club."],
            ),
            NpcP(
                id="bartender",
                name="Gennaro",
                age=61,
                location_id="bar",
                description="The bartender, polishing the same glass for an hour.",
            ),
        ],
        clocks=[
            ClockP(
                id="council",
                name="The council picks the next boss",
                steps=[
                    "The capos start counting votes.",
                    "Carmine buys the second crew.",
                    "The council meets.",
                    "A new boss is named.",
                ],
                step_every_hours=60,
                owner_id="esposito",
                thread_id="revenge",
            ),
        ],
        threads=[
            ThreadP(
                id="revenge",
                title="Who killed the boss",
                kind="mystery",
                stakes="Luca's revenge, and the family's future.",
                involved_ids=["player", "carmine", "esposito"],
                clock_id="council",
            ),
        ],
        mysteries=[
            MysteryP(
                id="who-ordered",
                question="Who inside the family ordered the killing of my father?",
                answer="Carmine Russo, the underboss, paid two soldiers from his own crew.",
                clues=["Carmine's driver was seen near the club that night."],
                thread_id="revenge",
            ),
        ],
        known_facts=["My father was shot dead outside his own club a week ago."],
        opening=OpeningP(
            place_id="bar",
            present_ids=["player", "carmine", "bartender"],
            positions=["Carmine in the back booth", "Luca at the door"],
            props=["a bottle of grappa on the bar", "a telephone behind the bar"],
            situation="Carmine looks up from his cards and smiles at Luca.",
        ),
        summary="Luca is back in Naples after his father's murder.",
    )


def naples_character() -> CharacterProposal:
    return CharacterProposal(
        name="Luca Esposito",
        age=24,
        description="A young man in a dark suit with his father's eyes and a short fuse.",
        appearance="24, lean, dark hair combed back, a scar through one eyebrow.",
        location_id="bar",
        attributes=AttributesP(nerve=5, speed=4, wits=4, bearing=4),
        skills=[
            SkillP(name="pistol", level="skilled"),
            SkillP(name="knife work", level="skilled"),
            SkillP(name="driving", level="fair"),
        ],
        traits=[
            TraitP(name="steady nerves under fire", kind="gift"),
            TraitP(name="a hot temper", kind="flaw"),
        ],
        temperament=TemperamentP(
            traits=["hot-headed", "loyal"],
            wants=["revenge for his father"],
            voice="Short sentences, Neapolitan slang when angry.",
        ),
        items=[
            ItemP(name="Beretta pistol", kind="weapon"),
            ItemP(name="flick knife", kind="weapon"),
            ItemP(name="Alfa Romeo Giulia", kind="vehicle", carried=False),
        ],
        money=200_000,
        currency="lire",
        family_name="Esposito",
        connections=[ConnectionP(name="three loyal soldiers", kind="ally")],
        memberships=[MembershipP(faction_id="esposito", rank="the late boss's son", loyalty=80)],
        axes=AxesP(might=2, influence=2, wealth=2, knowledge=1, stealth=1),
        goals=["Find out who killed my father."],
    )


def naples() -> DraftProposal:
    return DraftProposal(world=naples_world(), character=naples_character())


def cultivation_world() -> WorldProposal:
    return WorldProposal(
        title="Three Heartbeats",
        genre="cultivation",
        tone="wonder, ambition and sect politics",
        era="An ancient realm of sects, swords, pills and spirit stones",
        extraordinary=[
            ExtraordinaryP(
                id="qi",
                kind="qi cultivation",
                prevalence="common",
                reach="Realms from Qi Condensation to Nascent Soul and beyond.",
            ),
            ExtraordinaryP(id="time-powers", kind="powers over time", prevalence="rare"),
        ],
        rules=[
            RuleP(
                id="qi-exists",
                fixed=True,
                topic="existence",
                about=["qi"],
                text="Qi cultivation is real and everywhere.",
            ),
            RuleP(
                id="time-powers-exist",
                fixed=True,
                topic="existence",
                about=["time-powers"],
                text="A rare few can bend time.",
            ),
            RuleP(
                id="realm-ceiling",
                fixed=False,
                topic="limits",
                text="Nobody is known to have passed Soul Transformation.",
            ),
        ],
        ladders=[
            LadderP(
                id="realms",
                name="cultivation realms",
                sensing=True,
                rungs=[
                    RungP(name="Qi Condensation"),
                    RungP(name="Foundation Establishment"),
                    RungP(name="Core Formation"),
                    RungP(name="Nascent Soul"),
                    RungP(name="Soul Transformation"),
                ],
            ),
        ],
        calendar=CalendarP(style="day_count", start_hour=7),
        travel=TravelP(description="On foot, by flying sword for the strong, by message talisman."),
        medicine=MedicineP(healing="Pills heal in days what would take months."),
        laws=[
            LawP(
                id="sect-rules",
                text="Disciples may not kill each other within the sect.",
                enforcer="the Law Enforcement Hall",
                enforcer_faction_id="azure-cloud",
                zeal="high",
            ),
        ],
        places=[
            PlaceP(id="azure-peak", name="Azure Peak", kind="region"),
            PlaceP(
                id="well",
                name="the outer-court well",
                kind="courtyard",
                parent_id="azure-peak",
                routes=[RouteP(to_id="inner-court", travel_hours=0.67, mode="on foot")],
            ),
            PlaceP(id="inner-court", name="the inner court", kind="halls", parent_id="azure-peak"),
        ],
        factions=[
            FactionP(
                id="azure-cloud",
                name="the Azure Cloud Sect",
                kind="sect",
                description="A proud sect on Azure Peak.",
                goal="Win the regional ranking.",
            ),
            FactionP(
                id="outer-court",
                name="the outer court",
                kind="court",
                parent_id="azure-cloud",
                description="Hundreds of disciples who fetch, fight and hope.",
            ),
            FactionP(
                id="inner-court",
                name="the inner court",
                kind="court",
                parent_id="azure-cloud",
                description="The sect's chosen few.",
            ),
        ],
        npcs=[
            NpcP(
                id="zhao",
                name="Zhao Kun",
                aliases=["Senior Brother Zhao"],
                age=19,
                description="A broad-shouldered senior disciple who enjoys kicking buckets over.",
                location_id="well",
                memberships=[
                    MembershipP(faction_id="outer-court", rank="senior disciple", loyalty=70)
                ],
                attributes=AttributesP(strength=5, toughness=5),
                skills=[SkillP(name="fist techniques", level="skilled")],
                ladders=[
                    LadderPositionP(
                        ladder_id="realms", rung="Foundation Establishment", stage="early stage"
                    )
                ],
                attitude_to_player=AttitudeP(affinity=-30),
            ),
            NpcP(
                id="elder-mo",
                name="Elder Mo",
                age=212,
                description="An inner-court elder who looks like a sleepy old man.",
                location_id="inner-court",
                memberships=[MembershipP(faction_id="inner-court", rank="elder", loyalty=90)],
                ladders=[
                    LadderPositionP(ladder_id="realms", rung="Core Formation", stage="late stage")
                ],
                secrets=["He felt the ripple of stopped time the night Lin Feng woke."],
                player_knows="heard_of",
            ),
        ],
        clocks=[
            ClockP(
                id="tournament",
                name="The ranking tournament",
                steps=["Names are posted.", "The brackets are drawn.", "The tournament begins."],
                step_every_hours=16,
                owner_id="outer-court",
                thread_id="tournament",
            ),
        ],
        threads=[
            ThreadP(
                id="tournament",
                title="The ranking tournament",
                kind="ambition",
                stakes="A place in the inner court, or a year more as everyone's servant.",
                involved_ids=["player", "zhao", "outer-court"],
                clock_id="tournament",
            ),
        ],
        opening=OpeningP(
            place_id="well",
            present_ids=["player", "zhao"],
            positions=["Lin at the well with a full bucket", "Zhao two steps away"],
            props=["a wooden bucket of water", "the stone rim of the well"],
            situation="Zhao grins and draws back his foot toward the bucket.",
        ),
        summary="Lin Feng wakes in the outer court with a past life's memories.",
    )


def cultivation_character() -> CharacterProposal:
    return CharacterProposal(
        name="Lin Feng",
        age=16,
        description="A thin outer disciple in a patched grey robe, calm beyond his years.",
        appearance="16, slight, black hair tied back, steady eyes.",
        location_id="well",
        attributes=AttributesP(strength=2, toughness=2, wits=5, willpower=5),
        skills=[SkillP(name="herb lore", level="fair")],
        traits=[
            TraitP(name="a past life's memories", kind="gift"),
            TraitP(name="a weak body", kind="flaw"),
        ],
        powers=[
            PowerP(
                id="time-stop",
                name="time stop",
                kind_id="time-powers",
                gift=True,
                strength="overpowered",
                secret=True,
                description="Stops the world for three heartbeats.",
                limits=["three heartbeats per use", "a breath to recharge"],
                costs=[CostP(kind="fatigue", text="Leaves him drained.")],
                time=TimeP(effect="stop"),
            ),
        ],
        temperament=TemperamentP(traits=["calm", "patient"], wants=["to climb"]),
        rank="outer disciple",
        family_name="the fallen Lin clan",
        memberships=[MembershipP(faction_id="outer-court", rank="outer disciple", loyalty=50)],
        ladders=[LadderPositionP(ladder_id="realms", rung="Qi Condensation", stage="third stage")],
        axes=AxesP(might=1, influence=1, wealth=1, knowledge=3, stealth=2),
        reserves=[ReserveP(name="qi", level=40)],
        goals=["Survive the ranking tournament."],
        hidden_past=["The boy whose body this was owed Zhao Kun twenty spirit stones."],
    )


def cultivation() -> DraftProposal:
    return DraftProposal(world=cultivation_world(), character=cultivation_character())


def offline_backend(*, grounded: bool) -> FakeBackend:
    """The offline drafter for `LLM_PROVIDER=fake`: the Naples draft for a grounded starter, the
    outer disciple otherwise, whatever the premise says."""
    sample = naples() if grounded else cultivation()

    def reply(request: Request) -> Reply:
        title = (request.json_schema or {}).get("title")
        if title == "WorldProposal":
            return Reply(json=sample.world)
        if title == "CharacterProposal":
            return Reply(json=sample.character)
        return Reply(json=sample)

    return FakeBackend(default=reply, keep_requests=False)
