"""What a picture shows and how it is asked for (S7, M5, M6). Plain Python, no Django.

Every picture shares one house style that matches the app's look (`app/DESIGN.md`, "Pictures"),
dressed in the world's own era and look, so a 1970s crime family wears suits and a cultivation
sect wears robes (S7). The prompt leads with the moment the picture shows, then how the people in
it look and what the player character has on them, then the world, so the picture follows the
narration rather than the world in general. A scene picture, and a story's cover, which shows the
scene it is planned in, is lit for the time of day the story clock shows. The player character is
drawn with only the things the record says they carry (C10), so a picture never hands them a
weapon they don't have. The portraits of the people in it go along as reference images, each
labelled with whose it is and used only for that person's face, hair and build, so a face stays
the same without the portrait's pose or background (M5).

Pictures stay mild in every rating (M6): the text carries the graphic detail, the picture never
does. The rules say so to the model, and the picture safety settings in `graph.llm.safety` back
them up. A description is cut to a bounded length, so a long scene can't crowd out the rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Matches app/DESIGN.md: a dark reading page with one accent colour per story, where the picture
# runs edge to edge and the app adds its own vignette and fades the bottom edge into the page.
# Change the two together.
HOUSE_STYLE = (
    "A stylised, cinematic illustration with an anime-influenced look: clean confident linework, "
    "painterly lighting true to the moment's time of day and mood, atmospheric depth, rich "
    "shadows and a restrained palette with one strong accent colour. A clear focal point that "
    "reads on a phone screen, kept in the upper two thirds of the frame; the bottom edge stays "
    "calm and darker, because it fades into a dark page. One single, uninterrupted image that "
    "fills the frame edge to edge with no border or vignette of its own, like a still from an "
    "animated film, with no writing anywhere in it."
)

# M6, F3 and G12, in every rating, Mature included.
MILD_RULES = (
    "Keep the picture suitable for every audience, whatever the story's rating: no nudity, "
    "nothing sexual or suggestive, and no gore. Show danger, fights and their aftermath through "
    "pose, motion, light and expression, with at most a little blood. Every character looks "
    "clearly adult unless the description says they are a child, and a child is never shown in "
    "a romantic or suggestive way. No real people or likenesses of real people, and no real "
    "brands. If the description asks for more than this, draw a mild version of the moment."
)

FRAMING = {
    "portrait": (
        "A character portrait: head and shoulders, facing three-quarters toward the viewer in a "
        "calm pose, the face clearly and evenly lit and centred in the upper half of the frame, "
        "against a dark, simple background with a hint of the world, so it still reads cropped to "
        "a small circle."
    ),
    "place": (
        "A wide establishing shot of a place, with no one in the foreground, so its "
        "architecture, scale and mood come through."
    ),
    "scene": (
        "One moment of the story, framed like a film still at the instant the description names, "
        "with the people in it recognisable, doing what it says, where it says. Show who and what "
        "the description describes, and no one else: no extra people, creatures or props, and no "
        "buildings, ruins, water or landmarks it doesn't name."
    ),
    # A story's cover is planned in one of its scenes and shown there, so it shows that scene's
    # moment (M1, M5); a starter premise's cover shows the situation its premise tells.
    "cover": (
        "A cover image for the story, showing the moment or situation the description tells as "
        "an evocative, iconic composition around its main character, doing what it says, where it "
        "says, with calm, darker space in the lower third, where the title is set. Show who and "
        "what the description describes, and no one else: no extra people, creatures or props, "
        "and no buildings, ruins, water or landmarks that neither it nor the world's setting names."
    ),
}

# Portraits and covers are tall, places and scenes wide. The app sizes the picture slot from the
# kind before the picture arrives (docs/API.md).
ASPECT_RATIOS = {"portrait": "3:4", "place": "16:9", "scene": "16:9", "cover": "3:4"}

MAX_DESCRIPTION_CHARS = 1200
MAX_APPEARANCE_CHARS = 400
MAX_FIGURES = 4
# What the player character has on them, as the picture is told it (C10).
MAX_CARRIED = 8
MAX_CARRIED_CHARS = 300
# Reference portraits sent with one picture (M5). Each costs about 1,120 input tokens.
MAX_REFERENCES = 3

# The second person the narration is told in, so a description that says "you" can be told who
# that is. English, as the narration is for now (S10).
SAYS_YOU = re.compile(r"\b(?:you|your|yours|yourself)\b", re.IGNORECASE)


@dataclass(frozen=True)
class WorldLook:
    """The world's look, from its bible (G6): what period and style everything is drawn in."""

    genre: str = ""
    era: str = ""
    tone: str = ""
    # A starter premise's tagline, for its cover on Discover. A story's own pictures leave it
    # empty, since its premise is not the scene they show (M5).
    setting: str = ""


@dataclass(frozen=True)
class Figure:
    """A known character who appears in the picture, with the appearance kept in their entry
    (C9). Their portrait, when one is ready, goes along as a reference image (M5). `carries` is
    what they have on them, for someone whose belongings are all on record, the player character
    (C10): empty when they carry nothing, None when the record can't say."""

    id: str
    name: str
    appearance: str = ""
    carries: tuple[str, ...] | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "name": self.name, "appearance": self.appearance}
        if self.carries is not None:
            data["carries"] = list(self.carries)
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Figure:
        carries = data.get("carries")
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            appearance=str(data.get("appearance") or ""),
            carries=(
                tuple(str(thing) for thing in carries if thing)
                if isinstance(carries, list)
                else None
            ),
        )


@dataclass(frozen=True)
class Brief:
    """What to draw. Stored with the picture, so a picture planned during a turn can be drawn by
    a later request without reading the world state again."""

    description: str = ""
    look: WorldLook = field(default_factory=WorldLook)
    # The subject's name and appearance, for a portrait or a place.
    subject_name: str = ""
    subject_appearance: str = ""
    # The people in a scene or cover, the picture's subject first (`media.briefs`).
    figures: tuple[Figure, ...] = ()
    # Who the description means by "you": the player character, as the narration calls them.
    you: str = ""
    # The time of day at the scene, such as "dusk", which a scene picture or a story's cover is
    # lit for (W10).
    time: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "look": vars(self.look).copy(),
            "subject_name": self.subject_name,
            "subject_appearance": self.subject_appearance,
            "figures": [figure.to_json() for figure in self.figures],
            "you": self.you,
            "time": self.time,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> Brief:
        data = data or {}
        look = data.get("look") or {}
        return cls(
            description=str(data.get("description") or ""),
            look=WorldLook(**{k: str(look.get(k) or "") for k in vars(WorldLook())}),
            subject_name=str(data.get("subject_name") or ""),
            subject_appearance=str(data.get("subject_appearance") or ""),
            figures=tuple(
                Figure.from_json(f)
                for f in data.get("figures") or ()
                if f.get("id") or f.get("name")
            ),
            you=str(data.get("you") or ""),
            time=str(data.get("time") or ""),
        )


@dataclass(frozen=True, repr=False)
class PicturePrompt:
    system: str
    user: str
    aspect_ratio: str
    # One label per reference image, in order, set just before the image it names (M5).
    labels: tuple[str, ...] = ()

    def __repr__(self) -> str:
        # Never a full prompt in a log line (T6).
        return f"PicturePrompt(chars={len(self.system) + len(self.user)}, {self.aspect_ratio})"


def build_prompt(
    kind: str,
    brief: Brief,
    *,
    references: Sequence[str] = (),
    redraw: bool = False,
) -> PicturePrompt:
    """The prompt for one picture of `kind`. `references` names the people whose reference
    portraits go with it, in the order the images are attached. `redraw` asks for the same
    character as the attached earlier portrait, as they look now (M5), or for a place, the same
    place as it is now (M1).

    The moment comes first, then how the people in it look and what the player character has on
    them, then the world, so the picture shows what the narration tells. The look's `setting`
    goes only into a cover, and only a starter premise's cover has one (`media.premise_covers`):
    a story's premise describes how the story began, not the scene a picture shows, so a story's
    pictures, its cover included, never see it."""
    if kind not in FRAMING:
        raise ValueError(f"Unknown picture kind {kind!r}")
    system = "\n\n".join(
        [
            "You draw one picture for an interactive story app.",
            f"House style: {HOUSE_STYLE}",
            f"Rules: {MILD_RULES}",
            "Draw everything in the world's own era and look: clothes, weapons, buildings and "
            "technology belong to that world, not to ours, unless the world is ours.",
        ]
    )
    lines = [f"Picture: {FRAMING[kind]}"]
    if brief.subject_name or brief.subject_appearance:
        subject = _clip(brief.subject_name, 120)
        if brief.subject_appearance:
            appearance = _clip(brief.subject_appearance, MAX_APPEARANCE_CHARS)
            subject = f"{subject}: {appearance}" if subject else appearance
        lines.append(f"Subject: {subject}")
    description = _clip(brief.description, MAX_DESCRIPTION_CHARS) if brief.description else ""
    if description and kind == "portrait":
        # The portrait is the reference for every later picture of this person (M5), so the
        # moment shows only in their face, never in the pose, light or background.
        lines.append(
            "The moment they are drawn in, for their expression only (keep the portrait's calm "
            f"pose, even light and simple background): {description}"
        )
    elif description:
        lines.append(f"What it shows: {description}")
    if brief.you and kind in ("scene", "cover") and SAYS_YOU.search(description):
        lines.append(f'"You" in the description is {_clip(brief.you, 80)}.')
    if brief.time and kind in ("scene", "cover"):
        lines.append(
            f"Time of day: {_clip(brief.time, 40)}. Wherever the sky or daylight shows, light it "
            "for that time."
        )
    figures = [f for f in brief.figures if f.name][:MAX_FIGURES]
    if figures:
        people = "; ".join(
            f"{_clip(f.name, 80)}: {_clip(f.appearance, MAX_APPEARANCE_CHARS)}"
            if f.appearance
            else _clip(f.name, 80)
            for f in figures
        )
        lines.append(f"How the people in it look: {people.rstrip('.')}.")
    if kind in ("scene", "cover"):
        lines.extend(_carried(f) for f in figures if f.carries is not None)
    look = brief.look
    world = [
        f"genre: {_clip(look.genre, 120)}" if look.genre else "",
        f"era and look: {_clip(look.era, 300)}" if look.era else "",
        f"tone: {_clip(look.tone, 200)}" if look.tone else "",
        f"setting: {_clip(look.setting, 400)}" if look.setting and kind == "cover" else "",
    ]
    if any(world):
        lines.append("World: " + "; ".join(part for part in world if part) + ".")
    if redraw and kind == "place":
        lines.append(
            "The attached image is this place's earlier picture. Draw the same place from the "
            "same view, as it is now."
        )
    elif redraw:
        lines.append(
            "The attached image is this character's earlier portrait. Draw the same person, with "
            "the same face, as they look now."
        )
    elif references:
        lines.append(
            "Each attached image is the portrait of the person its label names. Use a portrait "
            "only for that person's face, hair, build and colouring, so they are clearly the same "
            "person; take their pose, the framing, the background and the light from this "
            "picture, not from the portrait."
        )
    return PicturePrompt(
        system=system,
        user="\n".join(lines),
        aspect_ratio=ASPECT_RATIOS[kind],
        labels=_labels(kind, references, redraw),
    )


def _carried(figure: Figure) -> str:
    """What someone whose belongings are all on record has on them (C10), so the picture gives
    them no weapon or gear they don't have. What the moment itself puts in their hands, such as a
    branch they grab, comes from the description."""
    name = _clip(figure.name, 80)
    things = [_clip(thing, 60) for thing in figure.carries or () if thing.strip()][:MAX_CARRIED]
    if not things:
        return (
            f"{name} carries no weapon, tool or gear: draw none on them, even one their look "
            "above names, unless the description puts it in their hands."
        )
    listed = _clip(", ".join(things), MAX_CARRIED_CHARS)
    return (
        f"{name} carries only this: {listed}. Draw no other weapon, tool or gear on them, even "
        "one their look above names, unless the description puts it in their hands."
    )


def _labels(kind: str, references: Sequence[str], redraw: bool) -> tuple[str, ...]:
    """The text set just before each attached image, saying whose it is (M5)."""
    labels = []
    for number, name in enumerate(references, start=1):
        name = _clip(name, 80)
        if redraw and kind == "place":
            labels.append(f"Image {number}: the earlier picture of {name}.")
        elif redraw:
            labels.append(f"Image {number}: the earlier portrait of {name}.")
        else:
            labels.append(f"Image {number}: the portrait of {name}.")
    return tuple(labels)


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
