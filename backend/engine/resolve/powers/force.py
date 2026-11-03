"""Raw force, for hits that don't come from an arm (A9, W10a).

A blow's force is usually the actor's might (A8). Some hits aren't: a pebble thrown in stopped
time at relative speed arrives at close to the speed of light, and its force comes from the power
that took the thrower out of time. This module puts such a hit on the world's tiers, so the
engine can follow it as logic: what it kills, how far its blast reaches and what survives it.

Rough figures, as A9 asks: 100 grams at 90% of the speed of light is about three megatons, and a
blast's deadly reach grows with the cube root of its yield, about 1.2 km for Hiroshima's 15
kilotons and about 7 km for three megatons. Nothing here caps a hit to hold a power level (A9).
"""

import math
from dataclasses import dataclass

from engine.contracts.intent import EffectScale
from engine.state.bible import ForceScale

LIGHT_SPEED_M_S = 299_792_458.0
JOULES_PER_KILOTON = 4.184e12
# W10a: a stopped-time throw at relative speed "really arrives at close to the speed of light".
RELATIVE_FRACTION = 0.9
# What is thrown or swung, when nothing says: a pebble, or a blade, a club or a fist.
PEBBLE_KG = 0.1
HELD_KG = 1.0
MIN_KG, MAX_KG = 0.001, 1e7

# A blast's deadly reach per cube root of kilotons, and how much further it still hurts.
LETHAL_M_PER_CBRT_KT = 500.0
HARM_FACTOR = 1.6
# A blast that kills this far out ruins the place it lands in; a smaller one damages it.
RUIN_LETHAL_M = 50.0
DAMAGE_LETHAL_M = 3.0
# A blast this wide wipes out a host gathered in the open, such as an army in its camp.
HOST_LETHAL_M = 1000.0

# How much energy an effect of each scale takes, roughly (A9's nonsense check).
SCALE_JOULES = {
    EffectScale.PERSON: 1e4,
    EffectScale.BUILDING: 1e10,
    EffectScale.TOWN: 1e13,
    EffectScale.CITY: 1e16,
    EffectScale.REGION: 1e19,
    EffectScale.WORLD: 2e32,  # what it takes to blow a planet apart
    EffectScale.STARS: 1e44,
}

# G13: what a body can lift by its strength attribute (0 to 10), in kg. What the user picks up in
# stopped time joins the stop "as heavy as ever" (W10a), so this is also what they can throw.
LIFT_KG = (0, 25, 50, 100, 200, 450, 1_000, 10_000, 100_000, 1_000_000, 10_000_000)


def bounded_kg(mass_kg: float | None, default: float) -> float:
    if mass_kg is None:
        return default
    return min(MAX_KG, max(MIN_KG, float(mass_kg)))


def relative_speed_joules(mass_kg: float) -> float:
    """The kinetic energy of `mass_kg` at the relative speed of a stopped-time hit."""
    gamma = 1 / math.sqrt(1 - RELATIVE_FRACTION**2)
    return (gamma - 1) * mass_kg * LIGHT_SPEED_M_S**2


def tier_for(joules: float, scale: ForceScale) -> float:
    """The tier of the toughest body a hit of this energy just matches, on the world's scale."""
    if joules <= 0:
        return 0.0
    return 1 + math.log(joules / scale.tier1_joules) / math.log(scale.per_tier)


def joules_for(tier: float, scale: ForceScale) -> float:
    """About how much energy a body at this tier takes."""
    return scale.tier1_joules * scale.per_tier ** (tier - 1)


def lift_kg(strength: int) -> float:
    return LIFT_KG[max(0, min(len(LIFT_KG) - 1, strength))]


@dataclass(frozen=True)
class Blast:
    """Where a hit's energy goes when it strikes: who dies, who is hurt and what is wrecked."""

    joules: float
    lethal_m: float
    harm_m: float

    @property
    def words(self) -> str:
        return tnt_words(self.joules)


def blast(joules: float) -> Blast:
    kilotons = joules / JOULES_PER_KILOTON
    lethal = LETHAL_M_PER_CBRT_KT * kilotons ** (1 / 3)
    return Blast(joules=joules, lethal_m=lethal, harm_m=lethal * HARM_FACTOR)


def _rough(value: float) -> str:
    """One significant figure, as people say it: 3, 30, 300, 0.3."""
    if value >= 1:
        digits = len(str(int(value))) - 1
        rounded = round(value, -digits)
        return f"{int(rounded):,}"
    return f"{float(f'{value:.1g}'):g}"


def tnt_words(joules: float) -> str:
    """'about 3 megatons', 'about 30 kilotons', 'about 2 tons of TNT'."""
    kilotons = joules / JOULES_PER_KILOTON
    if kilotons >= 1000:
        return f"about {_rough(kilotons / 1000)} megatons"
    if kilotons >= 1:
        return f"about {_rough(kilotons)} kilotons"
    tons = kilotons * 1000
    if tons >= 1:
        return f"about {_rough(tons)} tons of TNT"
    return f"about {_rough(tons * 1000)} kg of TNT"


def distance_words(meters: float) -> str:
    if meters >= 1000:
        return f"{_rough(meters / 1000)} km"
    return f"{_rough(meters)} m"
