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
    - `exclusive_rule_id`: while this rule holds, the template's own kinds are the only
      extraordinary things there are (G8), such as implants in a world without magic.
    - `ladder`: the genre's power ladder, used when the model proposes none (G18).
    - `peoples`: races the world must have (G23).
    - `gift`: the gift strength the premise grants unless the player picks another (G22).
    - `notes`: what the drafter must keep from the premise, for the prompt.
    """

    rules: tuple[WorldRule, ...] = ()
    extraordinary: tuple[Extraordinary, ...] = ()
    grounded_rule_id: str | None = None
    exclusive_rule_id: str | None = None
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

_HUMANS = People(id="humans", name="humans")
_ELVES = People(id="elves", name="elves", lifespan_years=600)
_DWARVES = People(id="dwarves", name="dwarves", lifespan_years=300)
_AURA_RANKS = _ladder(
    "aura-ranks",
    "aura ranks",
    ["Squire", "Knight", "Aura Master", "Sword Saint"],
    sensing=True,
)
_AURA_RULE = _rule(
    "aura-exists", "Aura is real: trained knights draw it to strengthen body and blade."
)
_AURA = _kind("aura", "aura", Prevalence.COMMON, "aura-exists", "From squire to saint.")
# Science fiction with something beyond what a real person could do, such as implants or giant
# war machines, is not grounded (G8), but it still has no magic: its template's kinds are the only
# extraordinary things in it (`exclusive_rule_id`).
_NO_MAGIC_RULE = _rule(
    "no-supernatural", "No magic and nothing supernatural: only science, and that won't change."
)
_NO_MAGIC = _kind(
    "supernatural", "magic or anything supernatural", Prevalence.NONE, "no-supernatural"
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
            rules=(_AURA_RULE,),
            extraordinary=(_AURA,),
            ladder=_AURA_RANKS,
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
            peoples=(_HUMANS, _ELVES, _DWARVES, People(id="beastkin", name="beastkin")),
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
    StarterPremise(
        id="sword-tomb",
        title="Keeper of the Sword Tomb",
        genre="Cultivation",
        tagline="A servant with no qi, three days before the Sword Choosing.",
        premise=(
            "You sweep the Sword Tomb of the Heavenly Edge Sect, where ten thousand swords of dead "
            "masters lie buried, and you have never drawn a strand of qi. Last night one of those "
            "swords spoke your name. In three days the disciples enter the tomb for the Sword "
            "Choosing, and the sword says it will choose no one but you."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _QI_RULE,
                _rule("sword-spirits", "A rare few ancient swords hold a spirit that can speak."),
            ),
            extraordinary=(
                _QI,
                _kind("sword-spirits", "sword spirits", Prevalence.RARE, "sword-spirits"),
            ),
            ladder=_REALMS,
            notes=(
                "The Sword Choosing is in three days. Why the sword speaks to the character is a "
                "mystery."
            ),
        ),
    ),
    StarterPremise(
        id="river-saint",
        title="The Saint at the River",
        genre="Knights and aura",
        tagline="An enemy sword saint crossed the border alone, and asked for you.",
        premise=(
            "You are a knight who can barely draw aura, holding a border fort of eleven soldiers "
            "at the edge of the kingdom of Aldreth. This morning a sword saint of the Varn Empire "
            "crossed the frozen river alone and sat down in the snow outside your gate. He asks "
            "for you by name, and says he will wait three days."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(_AURA_RULE,),
            extraordinary=(_AURA,),
            ladder=_AURA_RANKS,
            notes=(
                "The sword saint waits outside the fort for three days. Why he wants the "
                "character is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="ninth-floor",
        title="Left on the Ninth Floor",
        genre="Races and monsters",
        tagline="Left for dead in the Spire, beside a dragon egg that's starting to hatch.",
        premise=(
            "The Spire rose out of the desert a year ago, and adventurers of every race climb "
            "its monster-filled floors for treasure. Your own party left you for dead on the "
            "ninth floor. You woke in a hidden chamber beside a dragon egg that has started to "
            "crack, and you can hear your old party coming back for it."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "many-peoples",
                    "Humans, elves, dwarves and lizardfolk climb the Spire side by side, and "
                    "monsters fill its floors.",
                    RuleTopic.PEOPLES,
                ),
                _rule("magic-exists", "Magic is real, and monsters carry it in their cores."),
            ),
            extraordinary=(_kind("magic", "magic", Prevalence.COMMON, "magic-exists"),),
            ladder=_ladder(
                "adventurer-ranks",
                "adventurer ranks",
                ["D-rank", "C-rank", "B-rank", "A-rank", "S-rank"],
                sensing=False,
            ),
            peoples=(_HUMANS, _ELVES, _DWARVES, People(id="lizardfolk", name="lizardfolk")),
            notes=(
                "The dragon egg is hatching, and the party that betrayed the character is coming "
                "back for it. Why they did it is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="seven-day-villainess",
        title="The Villainess Has Seven Days",
        genre="Reincarnation",
        tagline="Reborn as a novel's villainess, a week before her downfall.",
        premise=(
            "You died in our world and woke up as the villainess of a romance novel you once read, "
            "a duke's daughter engaged to the crown prince. In seven days, at the spring ball, he "
            "breaks off the engagement in front of everyone, and in the book she is exiled that "
            "night. You remember how the story goes, and the heroine is already watching you "
            "strangely."
        ),
        flagship=True,
        template=PremiseTemplate(
            rules=(
                _rule("magic-exists", "Magic is real, and the royal academy teaches it to nobles."),
            ),
            extraordinary=(_kind("magic", "magic", Prevalence.COMMON, "magic-exists"),),
            gift=GiftStrength.SMALL,
            notes=(
                "The character keeps their past life's memories, and their only edge is knowing "
                "how the novel goes, which the world needn't follow. The spring ball is in seven "
                "days. Why the heroine watches the character is a mystery."
            ),
        ),
    ),
    # Beyond the flagship: grounded, science fiction, a hidden supernatural city and more (S1).
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
                _NO_MAGIC_RULE,
                _rule(
                    "jump-drives",
                    "Jump drives carry ships between stars in days, and no message travels "
                    "faster than a ship.",
                    RuleTopic.TECHNOLOGY,
                ),
            ),
            extraordinary=(_NO_MAGIC,),
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
    StarterPremise(
        id="mask-maker",
        title="The Mask-Maker of Venice",
        genre="Grounded mystery",
        tagline="Venice, carnival of 1750. A murderer wore the mask you made.",
        premise=(
            "Venice, carnival of 1750. You make masks for the nobility, and three nights ago a "
            "stranger paid you in gold for a mask of a senator's face, down to the scar. This "
            "morning the senator was found dead in a canal, and the guard has your mask. They will "
            "name the killer before the carnival ends in five days, and right now that is you."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=GROUNDED.rules,
            extraordinary=GROUNDED.extraordinary,
            grounded_rule_id=GROUNDED.grounded_rule_id,
            notes=(
                "Venice during the carnival of 1750. The senator and everyone around him are "
                "fictional. The carnival ends in five days. Who wore the mask is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="war-frame",
        title="The Frame That Chose You",
        genre="Mecha",
        tagline="The oldest war-frame in the hangar woke up and bonded with its mechanic.",
        premise=(
            "In the fortress city of Halcyon, giant war-frames hold back the swarm, and each one "
            "bonds with a single pilot for life. You are a junior mechanic, and last night the "
            "oldest frame in the hangar, silent for forty years, bonded with you instead of the "
            "commander's heir. The swarm's next wave reaches the walls in five days."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _NO_MAGIC_RULE,
                _rule(
                    "war-frames",
                    "Giant war-frames are real, and each one bonds with a single pilot for life.",
                ),
            ),
            extraordinary=(
                _NO_MAGIC,
                _kind(
                    "war-frames",
                    "bonded war-frames",
                    Prevalence.RARE,
                    "war-frames",
                    "A frame stands as tall as a tower and answers only its pilot.",
                ),
            ),
            exclusive_rule_id="no-supernatural",
            notes=(
                "The swarm's next wave reaches the walls in five days. Why the old frame woke "
                "for the character is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="ashgrove",
        title="Thirteen Nights at Ashgrove",
        genre="Gothic horror",
        tagline="Sleep thirteen nights in the manor to inherit it. Something knows your name.",
        premise=(
            "England, 1893. You inherited Ashgrove, a manor on the northern moors, from a "
            "great-aunt you never met. Her will says it is yours only if you sleep under its "
            "roof for thirteen nights in a row. On the first night, someone behind the locked "
            "door of the east wing called you by a childhood nickname nobody alive should know."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(_rule("ghosts-hidden", "The dead can linger, and almost nobody believes it."),),
            extraordinary=(_kind("ghosts", "ghosts", Prevalence.HIDDEN, "ghosts-hidden"),),
            notes=(
                "The character must sleep at Ashgrove for thirteen nights in a row to inherit it. "
                "Who is in the east wing is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="won-at-cards",
        title="Won at Cards",
        genre="Pirate fantasy",
        tagline="You won a pirate ship at cards. The navy is on the horizon.",
        premise=(
            "Last night, in a tavern on the Shattered Isles, you won the pirate ship Gilded Gull "
            "at cards. Now you are its captain, with a crew who think you cheated, an old captain "
            "who wants his ship back, and a navy frigate on the horizon. Folded into the deed is a "
            "chart of an island no map has ever named."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "sea-magic-rare",
                    "Magic is rare: a few storm-callers can speak to wind and wave.",
                ),
            ),
            extraordinary=(_kind("sea-magic", "sea magic", Prevalence.RARE, "sea-magic-rare"),),
            notes="A navy frigate is closing in. Where the unnamed island leads is a mystery.",
        ),
    ),
    StarterPremise(
        id="old-net",
        title="The Girl in the Old Net",
        genre="Cyberpunk",
        tagline="Someone lives inside a dead server, and it's wiped at midnight tomorrow.",
        premise=(
            "Sable City, 2091. You dive the abandoned old net for scrap data, to pay off the "
            "clinic that fitted your neural jack. Today, in a server untouched for thirty years, "
            "you found someone living there: a girl who says she was uploaded as a child. The "
            "corporation that owns the server wipes it at midnight tomorrow."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _NO_MAGIC_RULE,
                _rule(
                    "cybernetics",
                    "Cybernetic implants are everywhere, and anyone with a neural jack can dive "
                    "into the net.",
                ),
            ),
            extraordinary=(
                _NO_MAGIC,
                _kind(
                    "cybernetics",
                    "cybernetics",
                    Prevalence.COMMON,
                    "cybernetics",
                    "Implants push a body past its limits, at a price.",
                ),
            ),
            exclusive_rule_id="no-supernatural",
            notes=(
                "The server is wiped at midnight tomorrow. Who the girl was, and whether she is "
                "still a person, is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="last-lantern",
        title="A Room for the Dragon",
        genre="Cozy fantasy",
        tagline="Your inn is failing, and the only guest is a dragon who pays in riddles.",
        premise=(
            "You inherited the Last Lantern, a crumbling inn where the roads of three kingdoms "
            "meet, along with every one of its debts. The tax collector comes with the first "
            "snow, in thirty days. Your only guest is an old dragon in human shape who wants a "
            "room for the winter, and pays in riddles instead of coin."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "magic-rare", "Magic and dragons are real, though most folk never meet either."
                ),
            ),
            extraordinary=(_kind("magic", "magic and dragons", Prevalence.RARE, "magic-rare"),),
            notes=(
                "A warm, low-stakes story: the tax collector comes in thirty days, and the inn "
                "needs guests. Where the dragon's riddles lead is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="dry-basin",
        title="Two Days to the Well",
        genre="Post-apocalyptic",
        tagline="A caravan lies dead beside full water barrels, two days from the well.",
        premise=(
            "Thirty years after the bombs, water is money. You lead a caravan of six wagons "
            "across the dry Basin, two days from the next well. This morning you found the "
            "caravan that left a day ahead of you: every traveller dead, every water barrel full "
            "and untouched, and one set of boot prints leading north."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=GROUNDED.rules,
            extraordinary=GROUNDED.extraordinary,
            grounded_rule_id=GROUNDED.grounded_rule_id,
            notes=(
                "Thirty years after a nuclear war. The next well is two days away. What killed "
                "the caravan ahead is a mystery."
            ),
        ),
    ),
    StarterPremise(
        id="what-things-remember",
        title="What Things Remember",
        genre="Superpowers",
        tagline="Your power woke today: what you hold shows you its memories.",
        premise=(
            "In Port Vesper, one teenager in a hundred wakes up with a power at sixteen. Yours "
            "came this morning: anything you hold shows you what it remembers. The first thing you "
            "picked up was your missing sister's phone, and what it showed you is not what the "
            "police were told."
        ),
        flagship=False,
        template=PremiseTemplate(
            rules=(
                _rule(
                    "powers-rare",
                    "One person in a hundred gains a power at sixteen, and everyone knows it.",
                ),
            ),
            extraordinary=(_kind("powers", "superpowers", Prevalence.RARE, "powers-rare"),),
            gift=GiftStrength.RARE,
            notes=(
                "The character's power: anything they hold shows them what it remembers. Where "
                "the sister went, and why the police were lied to, is a mystery."
            ),
        ),
    ),
)

_BY_ID = {premise.id: premise for premise in STARTER_PREMISES}


def starter(premise_id: str) -> StarterPremise | None:
    return _BY_ID.get(premise_id)
