"""How the world weighs a deed (W1, W11, W12): what kind of act it is, and how severe.

Resolve proposes a severity from the world's norms as the interpret step read them. Code holds a
floor under it from the facts it can check: a killing is never a trifle, and the acts every world
treats as monstrous (killing children, sexual violence, a massacre) are severity 5, so they raise
fear and hostility faster and spread further (W12). Kinds are free-form verbs; nothing here
assumes a genre (G5).
"""

from enum import StrEnum

from engine.state.world import WorldState


class Nature(StrEnum):
    """What a deed does to the people it touches."""

    HARM = "harm"
    HELP = "help"
    DISPLAY = "display"  # a public show of power: fear, not hostility
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
KILLING = frozenset({"kill", "massacre"})
SEXUAL_VIOLENCE = frozenset({"rape"})

CHILD_AGE = 14  # under this, a victim is a child (W12)
MASSACRE_VICTIMS = 5  # killing this many at once is a massacre


def canonical(kind: str) -> str:
    """A deed kind in one spelling: 'Sexual assault' and 'murder' become 'rape' and 'kill'."""
    word = "_".join(kind.strip().casefold().replace("-", " ").split())
    return _ALIASES.get(word, word)


def nature(kind: str, victim_ids: list[str]) -> Nature:
    word = canonical(kind)
    if word in HARM_FLOORS:
        return Nature.HARM
    if word in HELP_KINDS:
        return Nature.HELP
    if word in DISPLAY_KINDS:
        return Nature.DISPLAY
    return Nature.HARM if victim_ids else Nature.OTHER


def is_killing(kind: str) -> bool:
    return canonical(kind) in KILLING


def monstrous(state: WorldState, kind: str, victim_ids: list[str]) -> bool:
    """W12: killing or hurting children, sexual violence, or a massacre."""
    word = canonical(kind)
    if word in SEXUAL_VIOLENCE or word == "massacre":
        return True
    if word in KILLING and len(victim_ids) >= MASSACRE_VICTIMS:
        return True
    if nature(kind, victim_ids) is not Nature.HARM or HARM_FLOORS.get(word, 2) < 2:
        return False
    for victim_id in victim_ids:
        victim = state.characters.get(victim_id)
        if victim is not None and victim.age is not None and victim.age < CHILD_AGE:
            return True
    return False


def assess_severity(state: WorldState, kind: str, proposed: int, victim_ids: list[str]) -> int:
    """The proposed severity, held above the floor the facts set (W1, W12)."""
    severity = max(1, min(5, int(proposed)))
    if monstrous(state, kind, victim_ids):
        return 5
    if nature(kind, victim_ids) is Nature.HARM:
        severity = max(severity, HARM_FLOORS.get(canonical(kind), 1))
    return severity


def is_crime(kind: str, severity: int, victim_ids: list[str]) -> bool:
    """W11: a harmful act against someone, serious enough for those who keep the law to act on.
    Insults and petty theft are left to the people involved."""
    return nature(kind, victim_ids) is Nature.HARM and severity >= 2
