"""The starter premises (S1), flagship genres first, each with the rules its genre can't break.

A starter's template is what code holds the draft to (G7, G8, G18, G22): the fixed rules the genre
needs, the extraordinary things that must exist or must not, the power ladder, the peoples, and
the gift the premise grants. The model sees the template in its prompt, and
`graph.drafting.assemble` enforces it on whatever the model proposes, until the player lets one of
its rules go while setting up the story (G7).

Every person and organisation here is fictional (G12). Real cities and history are backdrops only.
"""

from dataclasses import dataclass, field
from typing import Any

from engine.context import Language
from engine.state import (
    Extraordinary,
    GiftStrength,
    People,
    PowerAxis,
    PowerLadder,
    Prevalence,
    RuleTopic,
    Rung,
    WorldRule,
)
from graph.drafting.catalog_es import SPANISH, PremiseText


@dataclass(frozen=True)
class PremiseTemplate:
    """What a starter premise's genre fixes (G7).

    - `rules`: fixed rules the draft must hold, by stable id.
    - `extraordinary`: kinds that must exist at this prevalence, or must not (`none`).
    - `grounded_rule_id`: while this rule holds, nothing extraordinary exists at all and nobody
      has a power (G8).
    - `ladder`: the genre's power ladder, used when the model proposes none (G18).
    - `peoples`: races the world must have (G23).
    - `gift`: the gift strength the premise grants unless the player picks another (G22).
    - `notes`: what the drafter must keep from the premise, for the prompt.
    """

    rules: tuple[WorldRule, ...] = ()
    extraordinary: tuple[Extraordinary, ...] = ()
    grounded_rule_id: str | None = None
    ladder: PowerLadder | None = None
    peoples: tuple[People, ...] = ()
    gift: GiftStrength | None = None
    notes: str = ""

    @property
    def rule_ids(self) -> frozenset[str]:
        return frozenset(rule.id for rule in self.rules)


@dataclass(frozen=True)
class StarterPremise:
    id: str
    title: str
    genre: str
    tagline: str
    premise: str
    flagship: bool
    template: PremiseTemplate = field(default_factory=PremiseTemplate)

    def text(self, language: Language = Language.EN) -> PremiseText:
        """The words the player reads, in `language` (S10): English, or the starter's Spanish
        from `graph.drafting.catalog_es`."""
        if language is Language.ES and (spanish := SPANISH.get(self.id)):
            return spanish
        return PremiseText(
            title=self.title, genre=self.genre, tagline=self.tagline, premise=self.premise
        )

    def public(
        self, cover_url: str | None = None, language: Language = Language.EN
    ) -> dict[str, Any]:
        """The `Premise` shape from docs/API.md, in `language`. `cover_url` is the cover's signed
        URL, when the house has drawn one (`media.premise_covers`)."""
        text = self.text(language)
        return {
            "id": self.id,
            "title": text.title,
            "genre": text.genre,
            "tagline": text.tagline,
            "premise": text.premise,
            "flagship": self.flagship,
            "cover_url": cover_url,
        }


def _rule(rule_id: str, text: str, topic: RuleTopic = RuleTopic.EXISTENCE) -> WorldRule:
    return WorldRule(id=rule_id, text=text, fixed=True, topic=topic)


def _kind(kind_id: str, kind: str, prevalence: Prevalence, rule_id: str, reach: str = ""):
    return Extraordinary(
        id=kind_id, kind=kind, prevalence=prevalence, reach=reach, rule_ids=[rule_id]
    )


def _ladder(ladder_id: str, name: str, rungs: list[str], *, sensing: bool) -> PowerLadder:
    # Rungs sit two tiers apart, so a wounded or weakened character can fall between them (A8).
    return PowerLadder(
        id=ladder_id,
        name=name,
        axis=PowerAxis.MIGHT,
        rungs=[Rung(name=rung, tier=2 * (i + 1)) for i, rung in enumerate(rungs)],
        sensing=sensing,
    )


GROUNDED = PremiseTemplate(
    rules=(
        _rule(
            "no-supernatural",
            "Grounded: no magic and nothing supernatural, and that won't change.",
        ),
        _rule(
            "human-limits",
            "Nobody can do more than a real person could.",
            RuleTopic.LIMITS,
        ),
    ),
    extraordinary=(
        _kind("supernatural", "magic or anything supernatural", Prevalence.NONE, "no-supernatural"),
    ),
    grounded_rule_id="no-supernatural",
)

_REALMS = _ladder(
    "realms",
    "cultivation realms",
    [
        "Qi Condensation",
        "Foundation Establishment",
        "Core Formation",
        "Nascent Soul",
        "Soul Transformation",
    ],
    sensing=True,
)
_QI_RULE = _rule("qi-exists", "Qi cultivation is real, and the strong climb the realms.")
_QI = _kind(
    "qi",
    "qi cultivation",
    Prevalence.COMMON,
    "qi-exists",
    "Realms from Qi Condensation to Nascent Soul and beyond.",
)

STARTER_PREMISES: tuple[StarterPremise, ...] = (
    # The flagship: magic, monsters and power ladders (S1, G18 to G25).
    StarterPremise(
        id="outer-disciple",
        title="The Last Outer Disciple",
        genre="Cultivation",
        tagline="The weakest disciple of the sect, two days before the ranking tournament.",
        premise=(
            "You are the weakest outer disciple of the Azure Cloud Sect, stuck at the third "
            "stage of Qi Condensation while everyone around you breaks through. The ranking "
            "tournament starts in two days, and the disciples who finish last are sent down the "
            "mountain for good."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(_QI_RULE,),
            extraordinary=(_QI,),
            ladder=_REALMS,
            notes="The ranking tournament starts in two days.",
        ),
    ),
    StarterPremise(
        id="ashen-squire",
        title="Squire of the Ashen Crown",
        genre="Knights and aura",
        tagline="Nine days to the trial of knighthood, no aura, and a dead master.",
        premise=(
            "In the kingdom of Valdmark, knights are ranked by the aura they can draw: squire, "
            "knight, aura master, sword saint. You are a squire who has never drawn a spark of "
            "it. The trial of knighthood is in nine days, and this morning your master was found "
            "dead in the stables with his sword still in its sheath."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "aura-exists",
                    "Aura is real: trained knights draw it to strengthen body and blade.",
                ),
            ),
            extraordinary=(
                _kind("aura", "aura", Prevalence.COMMON, "aura-exists", "From squire to saint."),
            ),
            ladder=_ladder(
                "aura-ranks",
                "aura ranks",
                ["Squire", "Knight", "Aura Master", "Sword Saint"],
                sensing=True,
            ),
            notes="The trial of knighthood is in nine days. Who killed the master is a mystery.",
        ),
    ),
    StarterPremise(
        id="beast-tide",
        title="When the Beast Tide Comes",
        genre="Races and monsters",
        tagline="Four peoples behind one wall, and the beast tide is coming early.",
        premise=(
            "Elves, dwarves, beastkin and humans share the walled frontier town of Greywatch, "
            "and none of them trust each other. Every ten years the beast tide pours out of the "
            "Deepwood, and the scouts say this one is coming early. You are a half-elf monster "
            "hunter who owes the dwarven guild more than you can pay."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "many-peoples",
                    "Humans, elves, dwarves and beastkin share this world, and monsters roam "
                    "its wilds.",
                    RuleTopic.PEOPLES,
                ),
                _rule("magic-exists", "Magic is real, and monsters carry it in their cores."),
            ),
            extraordinary=(_kind("magic", "magic", Prevalence.COMMON, "magic-exists"),),
            ladder=_ladder(
                "hunter-ranks",
                "hunter ranks",
                ["Iron", "Bronze", "Silver", "Gold", "Mithril"],
                sensing=False,
            ),
            peoples=(
                People(id="humans", name="humans"),
                People(id="elves", name="elves", lifespan_years=600),
                People(id="dwarves", name="dwarves", lifespan_years=300),
                People(id="beastkin", name="beastkin"),
            ),
            notes="The beast tide comes every ten years, and this one is early.",
        ),
    ),
    StarterPremise(
        id="three-heartbeats",
        title="Three Heartbeats",
        genre="Reincarnation",
        tagline="Reborn in a world of sects, with the power to stop time.",
        premise=(
            "You died in our world and woke up as a sixteen-year-old outer disciple of the "
            "Moonfall Sect, with every memory of your past life and a power nobody else has: "
            "you can stop time for three heartbeats. The boy whose body you woke in had "
            "enemies, and one of them is already waiting for you by the well."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _QI_RULE,
                _rule("time-powers-exist", "A rare few can bend time, and almost nobody knows."),
            ),
            extraordinary=(
                _QI,
                _kind("time-powers", "powers over time", Prevalence.RARE, "time-powers-exist"),
            ),
            ladder=_REALMS,
            gift=GiftStrength.OVERPOWERED,
            notes=(
                "The character keeps their past life's memories and has time stop that lasts "
                "three heartbeats. The body's old enemies remember things the character doesn't."
            ),
        ),
    ),
    StarterPremise(
        id="demon-lord-accountant",
        title="The Demon Lord's Accountant",
        genre="Reincarnation",
        tagline="Reborn with no combat skills, hired to save a bankrupt dark army.",
        premise=(
            "You were reborn in a fantasy world with no combat skills, only an uncanny talent "
            "for numbers. The Demon Lord's army is bankrupt, and its terrifying lord has just "
            "hired you to fix the books before the heroes arrive."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _rule("magic-exists", "Magic and monsters are real, and so is the Demon Lord."),
            ),
            extraordinary=(_kind("magic", "magic", Prevalence.COMMON, "magic-exists"),),
            gift=GiftStrength.SMALL,
            notes="The character's only edge is a talent for numbers. The heroes are coming.",
        ),
    ),
    # Beyond the flagship: grounded, science fiction and a hidden supernatural city (S1).
    StarterPremise(
        id="naples-vendetta",
        title="The Esposito Succession",
        genre="Grounded crime",
        tagline="Naples, 1974. Someone inside the family killed your father.",
        premise=(
            "Naples, 1974. You are the son of the boss of the Esposito family, who was shot dead "
            "outside his own club a week ago. You're sure the killer is someone inside the "
            "family, and the family council will name the next boss in ten days."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=GROUNDED.rules,
            extraordinary=GROUNDED.extraordinary,
            grounded_rule_id=GROUNDED.grounded_rule_id,
            notes=(
                "Naples in May 1974. The Esposito family is fictional. The council names the "
                "next boss in ten days. Who ordered the killing is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="kestrel-debt",
        title="The Kestrel's Debt",
        genre="Science fiction",
        tagline="Thirty days to pay, and a crate in the hold worth killing for.",
        premise=(
            "You captain the Kestrel, a battered cargo hauler with a crew of four and a debt to "
            "the Halloran Syndicate that comes due in thirty days. The job that was meant to "
            "clear it left a sealed crate in your hold, and three different factions have just "
            "offered to buy it, or take it."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "no-supernatural",
                    "No magic and nothing supernatural: only science, and that won't change.",
                ),
                _rule(
                    "jump-drives",
                    "Jump drives carry ships between stars in days, and no message travels "
                    "faster than a ship.",
                    RuleTopic.TECHNOLOGY,
                ),
            ),
            extraordinary=(
                _kind(
                    "supernatural",
                    "magic or anything supernatural",
                    Prevalence.NONE,
                    "no-supernatural",
                ),
            ),
            grounded_rule_id="no-supernatural",
            notes="The debt comes due in thirty days. What is in the crate is a mystery.",
        ),
    ),
    StarterPremise(
        id="night-shift",
        title="Night Shift",
        genre="Hidden supernatural",
        tagline="Lisbon, today. The dead man in your ambulance just sat up.",
        premise=(
            "Lisbon, today. You drive the night shift for the city's ambulance service, and an "
            "hour ago the dead man in the back of your ambulance sat up, thanked you, and walked "
            "off into the dark. Since then, people who don't show up in mirrors have started "
            "asking about you."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(_rule("vampires-hidden", "Vampires are real, and they hide among the living."),),
            extraordinary=(_kind("vampires", "vampires", Prevalence.HIDDEN, "vampires-hidden"),),
            notes="Modern Lisbon, where almost nobody knows vampires exist.",
        ),
    ),
    StarterPremise(
        id="hollowmere",
        title="Last Exam at Hollowmere",
        genre="Academy fantasy",
        tagline="Fail the final exam and your memories go to auction.",
        premise=(
            "You are a scholarship student at Hollowmere, a sky-island academy of magic where "
            "anyone who fails the final exam has their memories auctioned off. The exam starts "
            "in seven days, and your magic still refuses to answer you."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(_rule("magic-exists", "Magic is real, and Hollowmere teaches it."),),
            extraordinary=(_kind("magic", "magic", Prevalence.COMMON, "magic-exists"),),
            notes="The final exam starts in seven days.",
        ),
    ),
    StarterPremise(
        id="drowned-capital",
        title="Ronin of the Drowned Capital",
        genre="Samurai drama",
        tagline="Clans fight over the rooftops of a city the sea swallowed.",
        premise=(
            "The old capital sank beneath the sea a century ago, and its clans still fight over "
            "the rooftops that remain above the waves. You are a masterless swordsman who just "
            "woke up holding a clan heir's broken seal."
        ),
        flagship=False,
    ),
    StarterPremise(
        id="dead-god-courier",
        title="Courier for a Dead God",
        genre="Neon urban fantasy",
        tagline="The god died yesterday. The package in your bag is addressed to them.",
        premise=(
            "In the harbour city of Lumen, gods are worshipped like pop idols, and one of them "
            "died yesterday. You are a night-shift courier, and the package in your bag is "
            "addressed to that god."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(_rule("gods-exist", "Gods are real, worshipped like pop idols, and mortal."),),
            extraordinary=(
                _kind("gods", "gods and their miracles", Prevalence.COMMON, "gods-exist"),
            ),
        ),
    ),
)

_BY_ID = {premise.id: premise for premise in STARTER_PREMISES}


def starter(premise_id: str) -> StarterPremise | None:
    return _BY_ID.get(premise_id)
