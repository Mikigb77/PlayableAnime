"""E4: the seeded event deck, one table per event size (personal, local, world).

Cards are generic on purpose (G5): no card names a monster, a gun or a starship. The narrator
dresses each draw in the world's own form (G9), so "armed outsiders" are bandits in a farming
valley, a rival crew in Naples and a pirate cutter in space. The deck holds good things as well as
trouble (W16), and each card says what happens if nobody takes it up, so an ignored event plays
out instead of repeating.

Weights come from the story's scale (a farming story gets farm-sized drama), the event-frequency
setting (calm leans to good things, dramatic to trouble) and the themes the player switched on
(F7), within the rating. Story wishes (N8) will weight it too once they exist.
"""

from dataclasses import dataclass
from enum import StrEnum

from engine.base import DAY, HOUR
from engine.context import EventFrequency, Rating, TurnContext
from engine.contracts.direction import EventKind, Theme
from engine.director.themes import fits
from engine.rng import SeededRng
from engine.state.records import ThreadKind
from engine.state.world import EventSize, WorldState


class Tone(StrEnum):
    GOOD = "good"
    MIXED = "mixed"
    TROUBLE = "trouble"


class CastRole(StrEnum):
    """Who among the existing characters the event should reuse before anyone new (E4)."""

    NONE = "none"
    CLOSE = "close"  # someone who likes the player character
    HOSTILE = "hostile"  # someone who doesn't
    ANY = "any"  # anyone the player character knows nearby


@dataclass(frozen=True)
class Card:
    id: str
    size: EventSize
    kind: EventKind
    tone: Tone
    title: str
    brief: str
    consequence: str = ""
    thread_kind: ThreadKind = ThreadKind.QUEST
    themes: frozenset[Theme] = frozenset()
    weight: float = 1.0
    needs_decision: bool = True
    window_s: int = DAY
    lingers: bool = False  # ignored, its thread goes dormant and can return, rather than closing
    cast: CastRole = CastRole.NONE
    mature_only: bool = False
    lead: bool = False  # it offers something the player can take up (N2)

    @property
    def source_key(self) -> str:
        return f"deck:{self.id}"


P, L, W = EventSize.PERSONAL, EventSize.LOCAL, EventSize.WORLD

DECK: tuple[Card, ...] = (
    # Personal: a life's own drama.
    Card(
        "old-friend",
        P,
        EventKind.ARRIVAL,
        Tone.MIXED,
        "An old friend in trouble",
        "Someone from the character's past turns up needing help that won't be easy to give.",
        "Turned away or left waiting, they leave, and their trouble finds its way back to the "
        "character's door.",
        ThreadKind.QUEST,
        lingers=True,
    ),
    Card(
        "falls-ill",
        P,
        EventKind.LOSS,
        Tone.TROUBLE,
        "Someone close falls ill",
        "Someone the character cares about falls sick, and the usual remedies aren't working.",
        "Untended, the illness takes its course and they get worse.",
        ThreadKind.THREAT,
        themes=frozenset({Theme.DARK}),
        window_s=2 * DAY,
        lingers=True,
        cast=CastRole.CLOSE,
    ),
    Card(
        "admirer",
        P,
        EventKind.TEMPTATION,
        Tone.MIXED,
        "An admirer",
        "Someone takes a romantic interest in the character or in someone close to them, and "
        "keeps finding reasons to be near. Everyone in it is an adult.",
        "Left alone, the admirer grows bolder, and people start to talk.",
        ThreadKind.ROMANCE,
        themes=frozenset({Theme.ROMANCE}),
        window_s=3 * DAY,
        lingers=True,
        cast=CastRole.CLOSE,
    ),
    Card(
        "windfall",
        P,
        EventKind.WINDFALL,
        Tone.GOOD,
        "An unexpected gift",
        "Something valuable comes the character's way, such as an inheritance, a lucky find or a "
        "debt repaid, in whatever form this world has. Others will hear of it.",
        "Unclaimed or unspent, word of it spreads, and someone comes asking for a share.",
        ThreadKind.AMBITION,
        window_s=2 * DAY,
    ),
    Card(
        "shortcut",
        P,
        EventKind.TEMPTATION,
        Tone.MIXED,
        "A tempting shortcut",
        "Someone offers the character something they want, at a price that isn't clear yet.",
        "Met with silence, the offer goes to someone else, who now owes the one who made it.",
        ThreadKind.DEBT,
        lead=True,
    ),
    Card(
        "rival",
        P,
        EventKind.RIVAL,
        Tone.TROUBLE,
        "A rival",
        "Someone sets out to beat the character at what they care about most, and makes sure "
        "they know it.",
        "Unanswered, the rival takes the ground the character didn't defend.",
        ThreadKind.RIVALRY,
        window_s=3 * DAY,
        lingers=True,
        cast=CastRole.HOSTILE,
    ),
    Card(
        "talk",
        P,
        EventKind.RUMOR,
        Tone.MIXED,
        "People are talking",
        "A story about the character is going around, and it isn't quite true.",
        "Left alone, the story hardens into what everyone knows.",
        ThreadKind.MYSTERY,
        window_s=2 * DAY,
    ),
    Card(
        "visitor",
        P,
        EventKind.VISITOR,
        Tone.GOOD,
        "A welcome visitor",
        "Someone the character is glad to see arrives with news and a request.",
        "Left waiting, the visitor leaves a little hurt, with the request unanswered.",
        ThreadKind.QUEST,
        cast=CastRole.CLOSE,
    ),
    Card(
        "hidden-thing",
        P,
        EventKind.DISCOVERY,
        Tone.MIXED,
        "Something hidden",
        "The character comes across something hidden close to home: a message, a cache, or a "
        "trace of someone's secret.",
        "Ignored, it is found by someone else, who learns what it means first.",
        ThreadKind.MYSTERY,
        window_s=2 * DAY,
    ),
    Card(
        "secret",
        P,
        EventKind.BETRAYAL,
        Tone.TROUBLE,
        "A confidant's secret",
        "Someone the character trusts has been hiding something that concerns them.",
        "Unconfronted, the secret does its damage before it comes out.",
        ThreadKind.MYSTERY,
        themes=frozenset({Theme.DARK}),
        window_s=3 * DAY,
        lingers=True,
        cast=CastRole.CLOSE,
    ),
    Card(
        "good-day",
        P,
        EventKind.CELEBRATION,
        Tone.GOOD,
        "A good day",
        "A small good thing happens in the character's life: a birth, a reunion, a job well done.",
        needs_decision=False,
    ),
    # Local: the place the character lives in.
    Card(
        "nature-turns",
        L,
        EventKind.DISASTER,
        Tone.TROUBLE,
        "Nature turns",
        "Nature threatens the place: a flood, a fire, a storm, or whatever this world's land and "
        "weather can do.",
        "Unprepared for, it takes what it can: a building, a field, a store of food.",
        ThreadKind.THREAT,
        window_s=6 * HOUR,
    ),
    Card(
        "outsiders",
        L,
        EventKind.DISASTER,
        Tone.TROUBLE,
        "Trouble comes to the place",
        "Armed outsiders threaten the place, such as raiders, enforcers or a patrol, in whatever "
        "form this world has, and they want something.",
        "Unopposed, they take what they came for and remember the place as easy.",
        ThreadKind.THREAT,
        window_s=12 * HOUR,
        lingers=True,
    ),
    Card(
        "bad-season",
        L,
        EventKind.LOSS,
        Tone.TROUBLE,
        "A bad season",
        "The place's livelihood fails: a bad harvest, a trade gone dry, a road closed.",
        "Left alone, hardship spreads, and people start to leave or turn on each other.",
        ThreadKind.THREAT,
        window_s=5 * DAY,
        lingers=True,
    ),
    Card(
        "celebration",
        L,
        EventKind.CELEBRATION,
        Tone.GOOD,
        "A celebration",
        "The place celebrates something and everyone is expected to take part, which puts people "
        "who don't get along in the same room.",
        "The celebration goes on without the character, and their absence is noticed.",
        ThreadKind.QUEST,
    ),
    Card(
        "newcomers",
        L,
        EventKind.ARRIVAL,
        Tone.MIXED,
        "Newcomers",
        "Strangers settle nearby and change the balance of the place.",
        "Unwelcomed and unchallenged, the newcomers make their own place, on their own terms.",
        ThreadKind.MYSTERY,
        window_s=4 * DAY,
        lingers=True,
    ),
    Card(
        "work-offered",
        L,
        EventKind.OFFER,
        Tone.GOOD,
        "Work on offer",
        "Someone with means needs something done and offers a fair reward.",
        "Nobody takes it, so someone else does, and gets the reward and the gratitude.",
        ThreadKind.QUEST,
        window_s=3 * DAY,
        lead=True,
    ),
    Card(
        "local-power",
        L,
        EventKind.RIVAL,
        Tone.TROUBLE,
        "A local power pushes",
        "Someone with influence in the place starts pushing people around, the character's "
        "people included.",
        "Unchecked, they grow bolder, and their hold on the place tightens.",
        ThreadKind.RIVALRY,
        window_s=3 * DAY,
        lingers=True,
        cast=CastRole.HOSTILE,
    ),
    Card(
        "find-nearby",
        L,
        EventKind.DISCOVERY,
        Tone.MIXED,
        "A find nearby",
        "Something old or valuable is found near the place, and more than one person wants it.",
        "Unclaimed by the character, it goes to whoever was quickest or strongest.",
        ThreadKind.MYSTERY,
        window_s=2 * DAY,
    ),
    Card(
        "crime",
        L,
        EventKind.LOSS,
        Tone.TROUBLE,
        "A crime in the community",
        "Someone in the place is hurt or killed, and nobody knows who did it.",
        "Uninvestigated, suspicion falls on whoever is easiest to blame.",
        ThreadKind.MYSTERY,
        themes=frozenset({Theme.DARK}),
        window_s=2 * DAY,
        lingers=True,
    ),
    Card(
        "grisly-find",
        L,
        EventKind.DISCOVERY,
        Tone.TROUBLE,
        "A grisly find",
        "A body is found nearby, torn apart in a way that makes people afraid.",
        "Left alone, fear grows, and the place looks for someone to blame.",
        ThreadKind.THREAT,
        themes=frozenset({Theme.DARK, Theme.GORE}),
        window_s=2 * DAY,
        lingers=True,
        mature_only=True,
    ),
    Card(
        "good-season",
        L,
        EventKind.WINDFALL,
        Tone.GOOD,
        "A good season",
        "The place has a good stretch: plenty, peace and full tables.",
        needs_decision=False,
    ),
    # World: the wider world reaching the character.
    Card(
        "calamity",
        W,
        EventKind.DISASTER,
        Tone.TROUBLE,
        "A great calamity",
        "Something vast strikes the wider world, such as a war, a plague or a fallen star, as "
        "far as this world's scale allows, and its effects reach the place.",
        "Unprepared for, its effects arrive anyway: shortages, refugees and fear.",
        ThreadKind.THREAT,
        window_s=7 * DAY,
        lingers=True,
    ),
    Card(
        "power-moves",
        W,
        EventKind.ARRIVAL,
        Tone.TROUBLE,
        "A great power on the move",
        "A great power marches, sails or flies, and its path crosses the character's.",
        "Unanswered, it passes through on its own terms and takes what it needs.",
        ThreadKind.THREAT,
        window_s=5 * DAY,
        lingers=True,
    ),
    Card(
        "far-news",
        W,
        EventKind.RUMOR,
        Tone.MIXED,
        "News from afar",
        "News arrives that changes the wider world: a ruler falls, a border closes, an alliance "
        "breaks.",
        "The change arrives whether or not the character prepared for it.",
        ThreadKind.MYSTERY,
        window_s=7 * DAY,
    ),
    Card(
        "summons",
        W,
        EventKind.OFFER,
        Tone.MIXED,
        "A summons",
        "A great power calls on the character, or on everyone like them, to serve.",
        "Ignored, the summons is taken as an answer, and the power remembers it.",
        ThreadKind.QUEST,
        window_s=5 * DAY,
        lingers=True,
        lead=True,
    ),
    Card(
        "shaken-truth",
        W,
        EventKind.DISCOVERY,
        Tone.MIXED,
        "The world shifts",
        "A discovery shakes what people thought they knew about the world, and people want to "
        "know where the character stands.",
        "Others decide what it means, and the character has to live with their answer.",
        ThreadKind.MYSTERY,
        window_s=7 * DAY,
    ),
    Card(
        "rising-power",
        W,
        EventKind.RIVAL,
        Tone.TROUBLE,
        "A rising power",
        "A new power rises and sets its sights on the region.",
        "Unopposed, it takes the region's loyalty one place at a time.",
        ThreadKind.THREAT,
        window_s=10 * DAY,
        lingers=True,
    ),
    Card(
        "good-news",
        W,
        EventKind.WINDFALL,
        Tone.GOOD,
        "Good news from afar",
        "Good news spreads across the land, such as a peace, a rich year or a new road, and with "
        "it come chances and people who want them.",
        "The chance passes to those who moved first.",
        ThreadKind.AMBITION,
        window_s=7 * DAY,
    ),
)

CARDS: dict[str, Card] = {card.id: card for card in DECK}

# How likely each size is, by the story's scale: a farming story gets farm-sized drama, and world
# events only reach a character the wider world already notices (W16).
SIZE_WEIGHTS: dict[EventSize, dict[EventSize, float]] = {
    P: {P: 3.0, L: 1.0, W: 0.0},
    L: {P: 2.0, L: 2.0, W: 0.4},
    W: {P: 1.0, L: 1.5, W: 1.0},
}
FREQUENCY_SIZE: dict[EventFrequency, dict[EventSize, float]] = {
    EventFrequency.CALM: {P: 1.25, L: 1.0, W: 0.75},
    EventFrequency.NORMAL: {P: 1.0, L: 1.0, W: 1.0},
    EventFrequency.DRAMATIC: {P: 1.0, L: 1.25, W: 1.5},
}
FREQUENCY_TONE: dict[EventFrequency, dict[Tone, float]] = {
    EventFrequency.CALM: {Tone.GOOD: 1.5, Tone.MIXED: 1.0, Tone.TROUBLE: 0.75},
    EventFrequency.NORMAL: {Tone.GOOD: 1.0, Tone.MIXED: 1.0, Tone.TROUBLE: 1.0},
    EventFrequency.DRAMATIC: {Tone.GOOD: 0.75, Tone.MIXED: 1.0, Tone.TROUBLE: 1.5},
}


def story_scale(state: WorldState) -> EventSize:
    """How far the player character's life reaches, from what the world records: the threat the
    factions see in them and the fear they inspire (W3, W5), and their place in factions (G10).

    - World: a faction rates them a threat of 4 or more, or they are widely feared.
    - Local: they belong to or lead a faction, or someone already sees a threat or fears them.
    - Personal: a private life, such as a farmer with a spouse and no ambitions.
    """
    player = state.player
    factions = list(state.factions.values())
    threat = max((f.threat for f in factions), default=0)
    fear = max(
        [f.player_reputation.fear for f in factions]
        + [p.player_reputation.fear for p in state.places.values()],
        default=0,
    )
    if threat >= 4 or fear >= 70:
        return EventSize.WORLD
    leads = any(player.id in f.leader_ids for f in factions)
    if threat >= 2 or fear >= 30 or player.memberships or leads:
        return EventSize.LOCAL
    return EventSize.PERSONAL


def playable(card: Card, ctx: TurnContext, allowed: frozenset[Theme]) -> bool:
    """Within the rating and the player's switched-on themes (F2, F7)."""
    if card.mature_only and ctx.rating is not Rating.MATURE:
        return False
    return fits(card.themes, allowed)


def draw(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    allowed: frozenset[Theme],
    *,
    recent: list[str] | tuple[str, ...] = (),
    decision_only: bool = True,
) -> Card | None:
    """One seeded draw: first the size from its weights, then a card from that size's table.

    Cards drawn recently are passed over while the table has others. `decision_only` keeps out the
    small good things that need no choice, which only colour a time skip (E7). Returns None when
    nothing in the deck fits, which can only happen if every card is filtered out.
    """
    frequency = ctx.settings.event_frequency
    scale = story_scale(state)
    tables: dict[EventSize, list[Card]] = {}
    for card in DECK:
        if decision_only and not card.needs_decision:
            continue
        if playable(card, ctx, allowed):
            tables.setdefault(card.size, []).append(card)
    sizes = [s for s in EventSize if tables.get(s)]
    weights = [SIZE_WEIGHTS[scale][s] * FREQUENCY_SIZE[frequency][s] for s in sizes]
    if not any(weights):
        return None
    size = rng.child("size").weighted(sizes, weights)
    table = tables[size]
    fresh = [card for card in table if card.source_key not in recent] or table
    tone = FREQUENCY_TONE[frequency]
    return rng.child("card").weighted(fresh, [card.weight * tone[card.tone] for card in fresh])
