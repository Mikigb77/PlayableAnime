"""W16, W10: moments, the small things of here and now.

Stall pressure counts the player's quiet turns, and the story's clock decides what may come of
it (`engine.director.clock`). When too little time has passed for one of life's events, such as
the twentieth short scene of the same half hour, something still happens, sized to the minute:
someone drops what they carry, a sound that doesn't belong, a familiar face going by (Miki,
2026-11-11: "some stuff should happen ... 100 scenes in the same hour should get events that
make sense for this time lap"). A moment keeps minutes from the last small thing too, so a
short talk isn't broken into at every other line.

A moment asks nothing. It opens no thread, waits for no answer and plays nothing out when it is
ignored, so the player can answer it or let it go by, and the app marks no event. It only
becomes more when the player makes it more, by acting on it.

Moments are generic on purpose (G5): none names a tavern, a phone or an airlock. The narrator
dresses each draw in the world's own form (G9). Code draws them, never the model (W16), with the
story's frequency leaning them to good things or to trouble as it does the deck.
"""

from dataclasses import dataclass

from engine.context import TurnContext
from engine.contracts.direction import PlannedMoment
from engine.director import rules
from engine.director.deck import FREQUENCY_TONE, CastRole, Tone
from engine.director.sources import cast_for
from engine.rng import SeededRng
from engine.state.world import WorldState


@dataclass(frozen=True)
class Moment:
    id: str
    tone: Tone
    brief: str
    cast: CastRole = CastRole.NONE  # someone the character knows nearby, whom it needs
    weight: float = 1.0


MOMENTS: tuple[Moment, ...] = (
    Moment(
        "passer-by",
        Tone.MIXED,
        "Someone nearby draws the eye for a moment: they drop what they carry, argue, laugh too "
        "loud or hurry past, in whatever form this place has.",
        weight=1.5,
    ),
    Moment(
        "small-ask",
        Tone.MIXED,
        "Someone asks the character for something small: the way, a hand with a load, a word "
        "of advice, a moment of their time.",
    ),
    Moment(
        "sound",
        Tone.MIXED,
        "A sound from close by that doesn't belong to the moment: a crash, a shout, running "
        "feet, music starting up.",
    ),
    Moment(
        "surroundings",
        Tone.MIXED,
        "The surroundings shift a little: the weather or the light turns, a crowd gathers or "
        "thins, something nearby stops working or starts again.",
        weight=1.5,
    ),
    Moment(
        "small-find",
        Tone.GOOD,
        "Something small within reach catches the character's eye: a thing dropped, a mark, a "
        "door left ajar, a scrap of writing.",
    ),
    Moment(
        "familiar-face",
        Tone.GOOD,
        "Someone the character knows comes by, with a word, a look or a small favour to ask.",
        cast=CastRole.ANY,
        weight=1.5,
    ),
    Moment(
        "mishap",
        Tone.TROUBLE,
        "A small mishap of the character's own: a stumble, a spill, a thing that jams, tears or "
        "goes missing for a moment.",
    ),
    Moment(
        "watched",
        Tone.TROUBLE,
        "Someone looks at the character a little too long, and looks away when they notice.",
        weight=0.5,
    ),
    Moment(
        "kindness",
        Tone.GOOD,
        "A small kindness comes the character's way: something shared, a way made for them, a "
        "word of thanks or praise.",
    ),
    Moment(
        "small-life",
        Tone.GOOD,
        "Something alive that isn't a person crosses the scene: a stray, a bird, whatever small "
        "life this world has.",
    ),
    Moment(
        "small-chance",
        Tone.GOOD,
        "A small chance opens for a moment: a place comes free, someone's back is turned, a "
        "price drops, something is left unwatched.",
    ),
    Moment(
        "small-nuisance",
        Tone.TROUBLE,
        "A small nuisance gets in the way for a moment: a queue, a blocked way, someone who "
        "won't stop talking, a thing that has to be done first.",
    ),
)

BY_ID: dict[str, Moment] = {moment.id: moment for moment in MOMENTS}


def draw_moment(
    state: WorldState,
    ctx: TurnContext,
    rng: SeededRng,
    *,
    recent: list[str] | tuple[str, ...] = (),
) -> PlannedMoment:
    """One seeded draw. A moment drawn recently is passed over, and one that needs someone the
    character knows nearby is only drawn when there is someone (E4: existing characters before
    new ones)."""
    cast: dict[str, list[str]] = {}
    table: list[Moment] = []
    for moment in MOMENTS:
        if moment.id in recent:
            continue
        if moment.cast is not CastRole.NONE:
            cast[moment.id] = cast_for(
                state, moment.cast, rng.child("cast", moment.id), adults_only=False
            )
            if not cast[moment.id]:
                continue
        table.append(moment)
    tone = FREQUENCY_TONE[ctx.settings.event_frequency]
    drawn = rng.child("moment").weighted(table, [m.weight * tone[m.tone] for m in table])
    return PlannedMoment(id=drawn.id, brief=drawn.brief, cast_ids=cast.get(drawn.id, []))


def recent_after(recent: list[str], moment: PlannedMoment) -> list[str]:
    return [*recent, moment.id][-rules.RECENT_MOMENTS :]
