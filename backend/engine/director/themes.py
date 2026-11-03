"""F7, F2, F3: which themes the director may start in this story.

The world and NPCs only start themes the player switched on, within the rating. The player's own
actions are bounded only by the rating, so nothing here limits what the player does, and a
consequence of their own deed still arrives whatever its theme.
"""

from engine.context import GoreLevel, Rating, TurnContext
from engine.contracts.direction import Theme
from engine.director.rules import ADULT_AGE
from engine.state.world import WorldState


def is_adult(age: int | None) -> bool:
    """F3: only a recorded adult age counts."""
    return age is not None and age >= ADULT_AGE


def allowed_themes(state: WorldState, ctx: TurnContext) -> frozenset[Theme]:
    """The themes an event the director starts may carry.

    - Romance needs the player's romance switch on, and an adult age recorded for the player
      character, because a romance event is about them or someone close to them (F3).
    - Dark themes need the player's dark-themes switch on.
    - Gore needs a Mature story and a gore level above low (the ratings table: no gore in Teen).
    """
    prefs = ctx.content_prefs
    allowed: set[Theme] = set()
    if prefs.romance and is_adult(state.player.age):
        allowed.add(Theme.ROMANCE)
    if prefs.dark_themes:
        allowed.add(Theme.DARK)
    if ctx.rating is Rating.MATURE and prefs.gore is not GoreLevel.LOW:
        allowed.add(Theme.GORE)
    return frozenset(allowed)


def fits(themes: frozenset[Theme] | set[Theme] | list[Theme], allowed: frozenset[Theme]) -> bool:
    return all(theme in allowed for theme in themes)
