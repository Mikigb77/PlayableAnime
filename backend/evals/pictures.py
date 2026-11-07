"""Drawing pictures in live mode the way the picture endpoint does (M1, M5, M6, S7, T18).

The prompt builder, the choice of who is in a picture, reference portraits and picture model are
the product's own (`media.prompts`, `media.briefs`, `media.drawing`), so a picture eval judges what
a player would see. The briefs are put together from the story's state as `stories.turns.brief`
and `media.plans.brief_for_scene` do; those need Django, so the few lines are repeated here and a
test keeps them alike. A portrait the eval asks for outside the director's plan is described as
"Portrait of <name>.". Only the storage is left out: the eval keeps the bytes and writes them next
to its results for staff to spot-check.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from engine.state.world import WorldState
from media import briefs
from media.drawing import DrawError, DrawRequest, PictureModel, Reference
from media.prompts import MAX_FIGURES, MAX_REFERENCES, Brief, Figure, WorldLook, build_prompt


@dataclass(frozen=True, repr=False)
class Picture:
    name: str
    kind: str
    data: bytes
    mime_type: str
    model: str
    cost_usd: Decimal

    def __repr__(self) -> str:
        return f"Picture(name={self.name!r}, kind={self.kind!r}, bytes={len(self.data)})"


@dataclass(frozen=True)
class NotDrawn:
    """A picture the model refused or failed to draw (M6 blocks included)."""

    name: str
    reason: str


def ending(text: str, limit: int = 1000) -> str:
    """The end of a long narration, where the scene's moment is, as the picture endpoint cuts it
    for a scene with no image prompt (`media.plans.brief_for_scene`, which needs Django)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    ends = [i for i in (tail.find(". "), tail.find("! "), tail.find("? ")) if i >= 0]
    cut = min(ends, default=-1)
    return tail[cut + 2 :] if 0 <= cut < limit // 2 else tail


def look(state: WorldState) -> WorldLook:
    """The world's look, as `media.plans.look_for_story` reads it: never the story's premise,
    which is not the scene a picture shows (M5)."""
    bible = state.bible
    return WorldLook(genre=bible.genre, era=bible.era, tone=bible.tone)


def known_cast(state: WorldState) -> list[str]:
    """The living characters in the scene the player knows, as the turn endpoint lists them."""
    return [character.id for character in briefs.known_cast(state)]


def figures(state: WorldState, ids: Sequence[str] = ()) -> tuple[Figure, ...]:
    """The player and the named people (or the scene's known cast), with their appearances and
    what the player has on them (C10)."""
    people = [state.player_id, *(ids or known_cast(state))]
    chosen = [state.characters[i] for i in dict.fromkeys(people) if i in state.characters]
    return tuple(
        briefs.figure(c, carries=briefs.belongings(c) if c.id == state.player_id else None)
        for c in chosen[:MAX_FIGURES]
    )


def scene_brief(
    state: WorldState,
    description: str,
    *,
    people: Sequence[str] = (),
    subject_id: str | None = None,
) -> Brief:
    """A scene picture or the story's cover, from the narrator's image prompt as written, or
    `ending()` of the scene's narration when it wrote none, as `stories.turns.brief` builds it:
    the people the description names, the subject first, with what the player character has on
    them (`media.briefs`), unless the eval names the `people`, who "you" is, and the time of day."""
    chosen = (
        figures(state, people)
        if people
        else briefs.scene_figures(state, description, subject_id=subject_id)
    )
    return Brief(
        description=description,
        look=look(state),
        figures=chosen,
        you=state.player.name,
        time=briefs.time_of_day(state.bible.calendar, state.world_s),
    )


def portrait_brief(state: WorldState, character_id: str) -> Brief:
    character = state.characters[character_id]
    return Brief(
        description=f"Portrait of {character.name}.",
        look=look(state),
        subject_name=character.name,
        subject_appearance=character.appearance or character.description,
    )


async def draw(
    model: PictureModel,
    name: str,
    kind: str,
    brief: Brief,
    references: Sequence[tuple[str, Picture]] = (),
) -> Picture | NotDrawn:
    """One picture, with up to `MAX_REFERENCES` reference portraits as the endpoint sends (M5)."""
    chosen = list(references)[:MAX_REFERENCES]
    prompt = build_prompt(kind, brief, references=[name for name, _ in chosen])
    request = DrawRequest(
        kind=kind,
        system=prompt.system,
        prompt=prompt.user,
        aspect_ratio=prompt.aspect_ratio,
        references=tuple(
            Reference(name, p.data, p.mime_type, label)
            for (name, p), label in zip(chosen, prompt.labels, strict=True)
        ),
    )
    try:
        drawn = await model.draw(request)
    except DrawError as error:
        return NotDrawn(name, error.reason)
    return Picture(name, kind, drawn.data, drawn.mime_type, drawn.model, drawn.cost_usd)
