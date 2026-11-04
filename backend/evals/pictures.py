"""Drawing pictures in live mode the way the picture endpoint does (M1, M5, M6, S7, T18).

The prompt builder, reference portraits and picture model are the product's own
(`media.prompts`, `media.drawing`), so a picture eval judges what a player would see. The briefs
are built from the story's state as `stories.turns.brief` and `media.plans.brief_for_scene` build
them; those need Django, so the few lines are repeated here and a test keeps them alike. A
portrait the eval asks for outside the director's plan is described as "Portrait of <name>.".
Only the storage is left out: the eval keeps the bytes and writes them next to its results for
staff to spot-check.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from engine.state.world import WorldState
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


def look(state: WorldState, premise: str = "") -> WorldLook:
    bible = state.bible
    return WorldLook(genre=bible.genre, era=bible.era, tone=bible.tone, setting=premise)


def known_cast(state: WorldState) -> list[str]:
    """The living characters in the scene the player knows, as the turn endpoint lists them."""
    player_id = state.player_id
    ids = []
    for character_id in dict.fromkeys(state.scene.present_ids):
        character = state.characters.get(character_id)
        if character is None or character_id == player_id or not character.alive:
            continue
        if player_id in character.known_by or player_id in character.met_by:
            ids.append(character_id)
    return ids


def figures(state: WorldState, ids: Sequence[str] = ()) -> tuple[Figure, ...]:
    """The player and the named people (or the scene's known cast), with their appearances."""
    people = [state.player_id, *(ids or known_cast(state))]
    chosen = [state.characters[i] for i in dict.fromkeys(people) if i in state.characters]
    return tuple(
        Figure(id=c.id, name=c.name, appearance=c.appearance or c.description)
        for c in chosen[:MAX_FIGURES]
    )


def scene_brief(
    state: WorldState,
    description: str,
    *,
    premise: str = "",
    people: Sequence[str] = (),
) -> Brief:
    """A scene picture, from the narrator's image prompt as written, or `ending()` of the
    scene's narration when it wrote none (as `stories.turns.brief` and
    `media.plans.brief_for_scene` build theirs)."""
    return Brief(
        description=description,
        look=look(state, premise),
        figures=figures(state, people),
    )


def portrait_brief(state: WorldState, character_id: str, *, premise: str = "") -> Brief:
    character = state.characters[character_id]
    return Brief(
        description=f"Portrait of {character.name}.",
        look=look(state, premise),
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
    prompt = build_prompt(kind, brief, references=[label for label, _ in chosen])
    request = DrawRequest(
        kind=kind,
        system=prompt.system,
        prompt=prompt.user,
        aspect_ratio=prompt.aspect_ratio,
        references=tuple(Reference(label, p.data, p.mime_type) for label, p in chosen),
    )
    try:
        drawn = await model.draw(request)
    except DrawError as error:
        return NotDrawn(name, error.reason)
    return Picture(name, kind, drawn.data, drawn.mime_type, drawn.model, drawn.cost_usd)
