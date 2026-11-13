"""How the world weighs a deed (W1, W11, W12): what kind of act it is, and how severe.

Resolve proposes a severity from the world's norms as the interpret step read them. Code holds a
floor under it from the facts it can check: a killing is never a trifle, and the acts every world
treats as monstrous (killing children, sexual violence, a massacre) are severity 5, so they raise
fear and hostility faster and spread further (W12). Kinds are free-form verbs; nothing here
assumes a genre (G5).

A move in a romance that wrongs a partner (W17) is its own kind of act: it harms nobody, no law
is broken by it, and nobody but those it wrongs and those close to them minds it.

A beast or monster (G24) isn't a person: harm done only to beasts is a hunt, no crime in the law's
eyes, weighed by how notable the beast was rather than by the floors for harming people. Its own
kin, its pack or its mate, still remember (W4).
"""

from enum import StrEnum

from engine.state.bible import Creature
from engine.state.cast import Prominence
from engine.state.records import Deed
from engine.state.world import WorldState


class Nature(StrEnum):
    """What a deed does to the people it touches."""

    HARM = "harm"
    HUNT = "hunt"  # harm done only to beasts or monsters (G24)
    HELP = "help"
    DISPLAY = "display"  # a public show of power: fear, not hostility
    ROMANCE = "romance"  # a move in a romance that wrongs a partner (W17): theirs to mind
    OTHER = "other"


_ALIASES = {
    "murder": "kill",
    "slay": "kill",
    "assassinate": "kill",
    "execute": "kill",
    "behead": "kill",
    "slaughter": "massacre",
    "sexual_assault": "rape",
    "sexual_violence": "rape",
    "stab": "wound",
    "shoot": "wound",
    "maim": "wound",
    "injure": "assault",
    "attack": "assault",
    "beat": "assault",
    "strike": "assault",
    "punch": "assault",
    "abduct": "kidnap",
    "theft": "steal",
    "rob": "steal",
    "liberate": "free",
    "rescue": "save",
    "cure": "heal",
    "show_power": "display",
    "reveal_power": "display",
    "demonstrate": "display",
}

# The least severity each harmful kind can have, whatever was proposed.
HARM_FLOORS = {
    "massacre": 5,
    "rape": 5,
    "kill": 4,
    "torture": 4,
    "enslave": 4,
    "raze": 4,
    "wound": 3,
    "kidnap": 3,
    "poison": 3,
    "conquer": 3,
    "betray": 2,
    "assault": 2,
    "burn": 2,
    "destroy": 2,
    "extort": 2,
    "blackmail": 2,
    "frame": 2,
    "curse": 2,
    "steal": 1,
    "threaten": 1,
    "insult": 1,
    "humiliate": 1,
}
HELP_KINDS = frozenset(
    {"save", "heal", "protect", "defend", "free", "feed", "give", "help", "spare", "pardon"}
)
DISPLAY_KINDS = frozenset({"display", "reveal", "breakthrough"})
# W17. A move in a romance, as the engine records one that wrongs someone
# (`engine.resolve.romance.deed`): courting, a night together, a wedding.
COURT, LIE_WITH, WED = "court", "lie_with", "wed"
ROMANCE_KINDS = frozenset({COURT, LIE_WITH, WED})
KILLING = frozenset({"kill", "massacre"})
SEXUAL_VIOLENCE = frozenset({"rape"})

CHILD_AGE = 14  # under this, a victim is a child (W12)
MASSACRE_VICTIMS = 5  # killing this many at once is a massacre
# A hunt is as notable as the strongest beast it struck: one step of severity for every this many
# tiers (A8), so a forest wolf is a trifle and an ancient dragon is news everywhere.
HUNT_TIERS_PER_SEVERITY = 4


def creature_of(state: WorldState, being_id: str) -> Creature | None:
    """G24. The kind of beast or monster a character is: the bible creature their `people_id`
    names. None for a person, and for anything that isn't a character."""
    character = state.characters.get(being_id)
    if character is None or character.people_id is None:
        return None
    return next((c for c in state.bible.creatures if c.id == character.people_id), None)


def is_beast(state: WorldState, being_id: str) -> bool:
    return creature_of(state, being_id) is not None


def beastly(state: WorldState, being_id: str) -> bool:
    """G24. Whether what a deed struck is no person: a beast, or a host of them such as a wolf
    pack, whose every member is a beast."""
    if being_id not in state.factions:
        return is_beast(state, being_id)
    members = [c.id for c in state.characters.values() if c.member_of(being_id)]
    return bool(members) and all(is_beast(state, m) for m in members)


def struck_beings(state: WorldState, victim_ids: list[str], target_ids: list[str] = ()) -> list:
    """Who a harmful deed fell on: its victims and targets, leaving out places (a burned
    granary is struck, but it is nobody)."""
    return [i for i in dict.fromkeys([*victim_ids, *target_ids]) if i not in state.places]


def canonical(kind: str) -> str:
    """A deed kind in one spelling: 'Sexual assault' and 'murder' become 'rape' and 'kill'."""
    word = "_".join(kind.strip().casefold().replace("-", " ").split())
    return _ALIASES.get(word, word)


def nature(
    state: WorldState,
    kind: str,
    victim_ids: list[str],
    target_ids: list[str] = (),
    severity: int = 1,
) -> Nature:
    """What a deed does. An attempt on someone that harmed nobody is still harm when resolve
    weighed it as serious: the target noticed the swing (A8). Harm that fell only on beasts is a
    hunt (G24)."""
    word = canonical(kind)
    if word in HARM_FLOORS:
        harmful = True
    elif word in HELP_KINDS:
        return Nature.HELP
    elif word in DISPLAY_KINDS:
        return Nature.DISPLAY
    elif word in ROMANCE_KINDS and not victim_ids:
        return Nature.ROMANCE
    else:
        harmful = bool(victim_ids or (target_ids and severity >= 2))
    if not harmful:
        return Nature.OTHER
    struck = struck_beings(state, victim_ids, target_ids)
    if struck and all(beastly(state, b) for b in struck):
        return Nature.HUNT
    return Nature.HARM


def deed_nature(state: WorldState, deed: Deed) -> Nature:
    if deed.wronged_ids and not deed.victim_ids:
        return Nature.ROMANCE  # W17: it harmed nobody, and it is the wronged's to mind
    return nature(state, deed.kind, deed.victim_ids, deed.target_ids, deed.severity)


def killed(state: WorldState, victim_ids: list[str]) -> list[str]:
    """Victims who are dead: characters no longer alive, and nameless victims who aren't
    characters at all (the villagers of a massacre)."""
    return [v for v in victim_ids if v not in state.characters or not state.characters[v].alive]


def monstrous(state: WorldState, kind: str, victim_ids: list[str]) -> bool:
    """W12: killing or hurting children, sexual violence, or a massacre, of people."""
    word = canonical(kind)
    if nature(state, kind, victim_ids) is Nature.HUNT:
        return False
    if word in SEXUAL_VIOLENCE or word == "massacre":
        return True
    if word in KILLING and len(killed(state, victim_ids)) >= MASSACRE_VICTIMS:
        return True
    if nature(state, kind, victim_ids) is not Nature.HARM or HARM_FLOORS.get(word, 2) < 2:
        return False
    for victim_id in victim_ids:
        victim = state.characters.get(victim_id)
        if victim is not None and victim.age is not None and victim.age < CHILD_AGE:
            return True
    return False


def assess_severity(
    state: WorldState,
    kind: str,
    proposed: int,
    victim_ids: list[str],
    target_ids: list[str] = (),
) -> int:
    """The proposed severity, held above the floor the facts set (W1, W12). The floor needs
    someone harmed: an attempt that missed keeps resolve's guess, and a killing nobody died of
    counts as the wounding it was. A hunt is held below how notable its beast was instead."""
    severity = max(1, min(5, int(proposed)))
    what = nature(state, kind, victim_ids, target_ids, severity)
    if what is Nature.HUNT:
        return min(severity, hunt_severity(state, struck_beings(state, victim_ids, target_ids)))
    if monstrous(state, kind, victim_ids):
        return 5
    if not victim_ids or what is not Nature.HARM:
        return severity
    word = canonical(kind)
    floor = HARM_FLOORS.get(word, 1)
    if word in KILLING and not killed(state, victim_ids):
        floor = HARM_FLOORS["wound"]
    return max(severity, floor)


def hunt_severity(state: WorldState, beast_ids: list[str]) -> int:
    """G24. How notable a hunt is: by the strongest beast it struck, its kind's tier or its own
    might, whichever is higher, and one more for a beast with a part in the story (a key one)."""
    best = 1
    for beast_id in beast_ids:
        beast = state.characters.get(beast_id)
        creature = creature_of(state, beast_id)
        if beast is None or creature is None:
            continue
        tier = max(creature.tier, beast.sheet.axes.might)
        key = beast.prominence is Prominence.KEY
        notable = 1 + tier // HUNT_TIERS_PER_SEVERITY + (1 if key else 0)
        best = max(best, notable)
    return min(5, best)


def is_crime(state: WorldState, deed: Deed) -> bool:
    """W11: a harmful act against someone, or a serious attempt at one, serious enough for those
    who keep the law to act on. Insults and petty theft are left to the people involved, a hunt
    harms no person (G24), and what both sides of a fight agreed to is theirs to settle (W1)."""
    return deed_nature(state, deed) is Nature.HARM and deed.severity >= 2 and not deed.agreed
