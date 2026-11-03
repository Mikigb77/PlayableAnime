"""What a picture shows and how it is asked for (S7, M5, M6). Plain Python, no Django.

Every picture shares one house style that matches the app's look (`app/DESIGN.md`, "Pictures"),
dressed in the world's own era and look, so a 1970s crime family wears suits and a cultivation
sect wears robes (S7). Known characters' portraits go along as reference images so a face stays
the same (M5).

Pictures stay mild in every rating (M6): the text carries the graphic detail, the picture never
does. The rules say so to the model, and the picture safety settings in `graph.llm.safety` back
them up. A description is cut to a bounded length, so a long scene can't crowd out the rules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Matches app/DESIGN.md: a dark reading page with one accent colour per story, where the picture
# runs edge to edge and the app adds its own vignette and fades the bottom edge into the page.
# Change the two together.
HOUSE_STYLE = (
    "A stylised, cinematic illustration with an anime-influenced look: clean confident linework, "
    "painterly low-key lighting, atmospheric depth, deep ink-dark shadows and a restrained "
    "palette with one strong accent colour. A clear focal point that reads on a phone screen, "
    "kept in the upper two thirds of the frame; the bottom edge stays calm and dark, because it "
    "fades into a dark page. One single image that fills the frame edge to edge: no borders, "
    "panels, split screens, vignettes, text, lettering, captions, speech bubbles, signatures, "
    "watermarks, logos or interface."
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
        "A character portrait: head and shoulders, facing three-quarters toward the viewer, the "
        "face clearly lit and centred in the upper half of the frame, against a dark, simple "
        "background with a hint of the world, so it still reads cropped to a small circle."
    ),
    "place": (
        "A wide establishing shot of a place, with no one in the foreground, so its "
        "architecture, scale and mood come through."
    ),
    "scene": (
        "One key moment of the story, framed like a film still at the instant of highest "
        "tension, with the people in it recognisable."
    ),
    "cover": (
        "A cover image for the story: an evocative, iconic composition of its world and its "
        "main character, with calm, darker space in the lower third, where the title is set."
    ),
}

# Portraits and covers are tall, places and scenes wide. The app sizes the picture slot from the
# kind before the picture arrives (docs/API.md).
ASPECT_RATIOS = {"portrait": "3:4", "place": "16:9", "scene": "16:9", "cover": "3:4"}

MAX_DESCRIPTION_CHARS = 1200
MAX_APPEARANCE_CHARS = 400
MAX_FIGURES = 4
# Reference portraits sent with one picture (M5). Each costs about 1,120 input tokens.
MAX_REFERENCES = 3


@dataclass(frozen=True)
class WorldLook:
    """The world's look, from its bible (G6): what period and style everything is drawn in."""

    genre: str = ""
    era: str = ""
    tone: str = ""
    setting: str = ""


@dataclass(frozen=True)
class Figure:
    """A known character who appears in the picture, with the appearance kept in their entry
    (C9). Their portrait, when one is ready, goes along as a reference image (M5)."""

    id: str
    name: str
    appearance: str = ""


@dataclass(frozen=True)
class Brief:
    """What to draw. Stored with the picture, so a picture planned during a turn can be drawn by
    a later request without reading the world state again."""

    description: str = ""
    look: WorldLook = field(default_factory=WorldLook)
    # The subject's name and appearance, for a portrait or a place.
    subject_name: str = ""
    subject_appearance: str = ""
    figures: tuple[Figure, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "look": vars(self.look).copy(),
            "subject_name": self.subject_name,
            "subject_appearance": self.subject_appearance,
            "figures": [vars(figure).copy() for figure in self.figures],
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
                Figure(*(str(f.get(name) or "") for name in ("id", "name", "appearance")))
                for f in data.get("figures") or ()
                if f.get("id") or f.get("name")
            ),
        )


@dataclass(frozen=True, repr=False)
class PicturePrompt:
    system: str
    user: str
    aspect_ratio: str

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
    place as it is now (M1)."""
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
    look = brief.look
    world = [
        f"genre: {_clip(look.genre, 120)}" if look.genre else "",
        f"era and look: {_clip(look.era, 300)}" if look.era else "",
        f"tone: {_clip(look.tone, 200)}" if look.tone else "",
        f"setting: {_clip(look.setting, 400)}" if look.setting else "",
    ]
    if any(world):
        lines.append("World: " + "; ".join(part for part in world if part) + ".")
    if brief.subject_name or brief.subject_appearance:
        subject = _clip(brief.subject_name, 120)
        if brief.subject_appearance:
            appearance = _clip(brief.subject_appearance, MAX_APPEARANCE_CHARS)
            subject = f"{subject}: {appearance}" if subject else appearance
        lines.append(f"Subject: {subject}")
    if brief.description:
        lines.append(f"What it shows: {_clip(brief.description, MAX_DESCRIPTION_CHARS)}")
    figures = [f for f in brief.figures if f.name][:MAX_FIGURES]
    if figures:
        people = "; ".join(
            f"{_clip(f.name, 80)}: {_clip(f.appearance, MAX_APPEARANCE_CHARS)}"
            if f.appearance
            else _clip(f.name, 80)
            for f in figures
        )
        lines.append(f"People in it: {people}.")
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
        names = ", ".join(_clip(name, 80) for name in references)
        lines.append(
            f"The attached images are reference portraits of {names}, in that order. Keep each "
            "one's face, hair and build exactly the same."
        )
    return PicturePrompt(system=system, user="\n".join(lines), aspect_ratio=ASPECT_RATIOS[kind])


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
