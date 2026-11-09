"""What a picture shows and how it is asked for (S7, M5, M6). Plain Python, no Django.

Every picture shares one house style that matches the app's look (`app/DESIGN.md`, "Pictures"),
dressed in the world's own era and look, so a 1970s crime family wears suits and a cultivation
sect wears robes (S7). The style is made for the app's readers, teens and adults: serious and
grounded like an anime film or graphic novel for grown-ups, never a children's storybook (Miki,
2026-11-08), and everyone is drawn at the age the story gives them, a 15-year-old as a
15-year-old and a grown man as a grown man.

The prompt leads with the moment the picture shows, then how the people in it look and what the
player character has on them, then the world, so the picture follows the narration rather than
the world in general. A scene picture is lit for the time of day the story clock shows, and gets
the picture of the place it happens in as a reference. A story's cover is the exception: it is
the story's poster in the Library (M1), so it sums up the whole story in its world, its premise
included as the setting, rather than the moment of the scene it is planned in. The player
character is drawn with only the things the record says they carry (C10), on a cover too, so a
picture never hands them a weapon they don't have. The portraits of the people in it go along as
reference images, each labelled with whose it is and used only for that person's face, hair and
build, so a face stays the same without the portrait's pose, background or older style (M5).
Everyone in a scene or cover stands on something the picture shows, in one perspective and at the
size their distance gives them, and the place's picture is drawn again around the people, never
used as a backdrop behind them (M5).

Pictures stay within mild lines in every rating (M6): the text carries the graphic detail, the
picture never does. Mild is about what a picture shows, not its tone, so danger, wounds, fear and
grief show as seriously as the story tells them. The rules say so to the model, and the picture
safety settings in `graph.llm.safety` back them up. A description is cut to a bounded length, so
a long scene can't crowd out the rules.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Matches app/DESIGN.md: a dark reading page with one accent colour per story, where the picture
# runs edge to edge and the app adds its own vignette and fades the bottom edge into the page.
# Change the two together, and move `HOUSE_STYLE_VERSION` on when the look changes enough that the
# starter covers on Discover should be drawn again (`media.premise_covers`).
HOUSE_STYLE = (
    "A cinematic illustration for teen and adult readers, like a frame from an anime film made "
    "for grown-ups or a graphic novel for adults: semi-realistic anatomy and proportions, faces "
    "with real bone structure that show each person's true age and character, and detailed "
    "textures of skin, cloth, leather, metal, wood and stone. A serious, grounded mood that takes "
    "the story's stakes to heart. Dramatic, painterly light true to the moment's time of day and "
    "mood, with strong contrast between light and deep shadow, atmospheric depth, and a muted, "
    "naturalistic palette with one strong accent colour. Nothing cute, whimsical or childish: no "
    "chibi or cartoon proportions, no oversized eyes or baby faces on grown-ups, no soft, rounded, "
    "toy-like shapes, no bright candy or pastel colours, and no storybook or fairy-tale look. "
    "Everything rendered in high detail: intricate textures of cloth, skin, stone and metal, fine "
    "highlights and crisp small details, while the focal point stays clear. A "
    "clear focal point that reads on a phone screen, kept in the upper two thirds of the frame; "
    "the bottom edge stays calm and darker, because it fades into a dark page. One single, "
    "uninterrupted image that fills the frame edge to edge with no border or vignette of its own, "
    "with no writing anywhere in it."
)
# The house style's version, kept with each starter cover, so a deploy draws the covers drawn in
# an older style once more. 2: the grown-up look (Miki, 2026-11-08). 3: the grown-up look in
# higher detail, picked from the style comparison (`evals.styles`, Miki, 2026-11-08).
HOUSE_STYLE_VERSION = 3

# M6, F3 and G12, in every rating, Mature included. Mild is about what a picture shows, never its
# tone: "suitable for every audience" drew the pictures as if for young children (Miki,
# 2026-11-08).
MILD_RULES = (
    "Whatever the story's rating, the picture stays within these lines, without softening the "
    "story's mood: no nudity, nothing sexual or suggestive, and no gore. Danger, fights, weapons, "
    "wounds, fear and grief can show as seriously as the story tells them, through pose, motion, "
    "light and expression, with at most a little blood. Draw each person at the age given for "
    "them, with the face, build and proportions of that age (a teenager as a teenager, a "
    "grown-up as a grown-up), unless their look says they look younger or older. Anyone whose "
    "age isn't given is clearly an adult, unless the description says they are a child. No one "
    "under 18 is ever shown in a romantic or suggestive way. No real people or "
    "likenesses of real people, and no real brands. If the description asks for more than this, "
    "draw the moment within these lines."
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
        "with the people in it recognisable, doing what it says, where it says, each on footing "
        "the picture shows. Show who and what "
        "the description describes, and no one else: no extra people, creatures or props, and no "
        "buildings, ruins, water or landmarks it doesn't name."
    ),
    # A story's cover is its poster in the Library: the whole story in its world, not one scene's
    # moment (M1, Miki 2026-11-07); a starter premise's cover shows the situation its premise
    # tells.
    "cover": (
        "A cover image for the story, like the poster of a film or the cover of a novel for "
        "grown-up readers: a dramatic, iconic composition "
        "that sums up the story around its main character, not one moment of it. The world's "
        "setting may rise behind them, with its telling places, landmarks or threats. Keep calm, "
        "darker space in the lower third, where the title is set."
    ),
}

# The people a scene or cover lists are its only figures, each drawn once (M5).
ONLY_THEM = (
    "Draw each of them once, and no one else in front: anyone else the description mentions "
    "stays a small, unnamed part of the background."
)

# Everyone in a scene or cover stands on something the picture shows, at the size their place in
# it gives them (M5). Miki, 2026-11-09: the player character stood in mid-air, life-size, over a
# camp far below, beside a companion who leant over the edge of a wall. The footing may be drawn
# though the description doesn't name it, which a scene's framing would otherwise rule out. The
# first live run drew the companion floating in front of the wall in one picture of two, so the
# rule also picks the viewpoint: one that keeps everyone's footing in the frame, and for people up
# high, a view from up there with them, never one that leaves open air between them and the
# viewer.
GROUNDED = (
    "Set everyone inside the picture's own space, in one consistent perspective, seen from a "
    "viewpoint that keeps the footing under every standing person inside the frame: every person "
    "or creature rests on something solid that the picture shows under them, such as the ground, "
    "a floor, a ledge, steps, rocks or a branch, with their feet planted on it and a shadow where "
    "they touch it, unless the description has them fly, float, fall, leap, climb, swim or hang. "
    "Draw that footing even where the description doesn't name it. When people stand up high, on "
    "a wall, a cliff, a roof or a balcony, looking down or out at something, view them from up "
    "there, from behind or beside them, with the top they stand on running under their feet "
    "across the foreground and what lies below small and far beyond it; never leave open air "
    "between them and the viewer. Each one's size fits how far they are from the viewer and the "
    "things around them, and people side by side share the same footing. No one hovers in mid-air "
    "unless the description says so, and no one stands pasted over the background like a cut-out."
)

# Portraits and covers are tall, places and scenes wide. The app sizes the picture slot from the
# kind before the picture arrives (docs/API.md).
ASPECT_RATIOS = {"portrait": "3:4", "place": "16:9", "scene": "16:9", "cover": "3:4"}

MAX_DESCRIPTION_CHARS = 1200
MAX_APPEARANCE_CHARS = 400
MAX_FIGURES = 4
# What the player character has on them, as the picture is told it (C10).
MAX_CARRIED = 8
MAX_CARRIED_CHARS = 300
# Reference portraits sent with one picture (M5), and the place's own picture on top of them for
# a scene picture. Each image costs about 1,120 input tokens.
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
    # What only a cover is drawn with: a starter premise's tagline on Discover, or a story's
    # premise, which `media.briefs.cover_brief` makes what its cover, its poster, shows (M1). A
    # scene picture never sees it, since a premise is not the scene a picture shows (M5).
    setting: str = ""


@dataclass(frozen=True)
class Figure:
    """A known character who appears in the picture, with the appearance kept in their entry
    (C9) and their age in years, so they are drawn as old as they are (S7). Their portrait, when
    one is ready, goes along as a reference image (M5). `carries` is what they have on them, for
    someone whose belongings are all on record, the player character (C10): empty when they carry
    nothing, None when the record can't say."""

    id: str
    name: str
    appearance: str = ""
    carries: tuple[str, ...] | None = None
    age: int | None = None

    def to_json(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id, "name": self.name, "appearance": self.appearance}
        if self.carries is not None:
            data["carries"] = list(self.carries)
        if self.age is not None:
            data["age"] = self.age
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
            age=_age(data.get("age")),
        )


@dataclass(frozen=True)
class Brief:
    """What to draw. Stored with the picture, so a picture planned during a turn can be drawn by
    a later request without reading the world state again."""

    description: str = ""
    look: WorldLook = field(default_factory=WorldLook)
    # The subject's name and appearance, for a portrait or a place, and a portrait's age in years.
    subject_name: str = ""
    subject_appearance: str = ""
    subject_age: int | None = None
    # The people in a scene or cover, the picture's subject first (`media.briefs`).
    figures: tuple[Figure, ...] = ()
    # Who the description means by "you": the player character, as the narration calls them.
    you: str = ""
    # The time of day at the scene, such as "dusk", which a scene picture is lit for (W10).
    time: str = ""
    # The scene a scene picture shows, or a cover was planned in, whose finished text a scene
    # picture's description is written from (`media.notes`), and where a scene picture happens,
    # whose own picture goes along as a reference (M5). 0 and empty for an older brief.
    turn: int = 0
    place_id: str = ""
    place_name: str = ""
    place_look: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "look": vars(self.look).copy(),
            "subject_name": self.subject_name,
            "subject_appearance": self.subject_appearance,
            "subject_age": self.subject_age,
            "figures": [figure.to_json() for figure in self.figures],
            "you": self.you,
            "time": self.time,
            "turn": self.turn,
            "place_id": self.place_id,
            "place_name": self.place_name,
            "place_look": self.place_look,
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
            subject_age=_age(data.get("subject_age")),
            figures=tuple(
                Figure.from_json(f)
                for f in data.get("figures") or ()
                if f.get("id") or f.get("name")
            ),
            you=str(data.get("you") or ""),
            time=str(data.get("time") or ""),
            turn=_turn(data.get("turn")),
            place_id=str(data.get("place_id") or ""),
            place_name=str(data.get("place_name") or ""),
            place_look=str(data.get("place_look") or ""),
        )


def _turn(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _age(value: Any) -> int | None:
    """An age in years as stored, or None when there is none or it can't be read."""
    if value is None or isinstance(value, bool):
        return None
    try:
        age = int(value)
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


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
    place: bool = False,
) -> PicturePrompt:
    """The prompt for one picture of `kind`. `references` names the people whose reference
    portraits go with it, in the order the images are attached. `redraw` asks for the same
    character as the attached earlier portrait, as they look now (M5), or for a place, the same
    place as it is now (M1). `place`: one more image goes last, the picture of the place a scene
    picture happens in (`brief.place_name`), so a place looks the same from scene to scene (M5).

    The moment comes first, then how the people in it look and what the player character has on
    them, then the world, so the picture shows what the narration tells. The look's `setting`, a
    premise, goes only into a cover, the story's poster (M1): a premise describes how the story
    began, not the scene a picture shows, so a scene picture never sees it."""
    if kind not in FRAMING:
        raise ValueError(f"Unknown picture kind {kind!r}")
    system = "\n\n".join(
        [
            "You draw one picture for an interactive story app whose readers are teens and adults.",
            f"House style: {HOUSE_STYLE}",
            f"Rules: {MILD_RULES}",
            "Draw everything in the world's own era and look: clothes, weapons, buildings and "
            "technology belong to that world, not to ours, unless the world is ours.",
        ]
    )
    lines = [f"Picture: {FRAMING[kind]}"]
    if brief.subject_name or brief.subject_appearance:
        subject = _aged(_clip(brief.subject_name, 120), brief.subject_age)
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
    if brief.time and kind == "scene":
        lines.append(
            f"Time of day: {_clip(brief.time, 40)}. Wherever the sky or daylight shows, light it "
            "for that time."
        )
    figures = [f for f in brief.figures if f.name][:MAX_FIGURES]
    if figures:
        people = "; ".join(person(f) for f in figures)
        lines.append(f"How the people in it look: {people.rstrip('.')}.")
        if kind in ("scene", "cover"):
            # Miki, 2026-11-08: a scene of two came out with a third person, someone the scene
            # only mentioned, and a referenced person can come out twice.
            lines.append(ONLY_THEM)
    if kind in ("scene", "cover"):
        # Unlisted people, such as bandits or a crowd, stand on something too.
        lines.append(GROUNDED)
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
            "same view, as it is now, in the house style even where that picture's style "
            "differs."
        )
    elif redraw:
        lines.append(
            "The attached image is this character's earlier portrait. Draw the same person, with "
            "the same face, as they look now, in the house style even where the portrait's style "
            "differs."
        )
    elif references:
        lines.append(
            "Each attached image is the portrait of the person its label names. Use a portrait "
            "only for that person's face, hair, build and colouring, so they are clearly the same "
            "person; take their pose, the framing, the background, the light and the drawing "
            "style from this picture and the house style, not from the portrait."
        )
    place = place and not redraw and kind == "scene"
    if place:
        # Miki, 2026-11-09: the player character stood in mid-air in front of the place, as if it
        # were a backdrop.
        lines.append(
            "The image labelled as the place is where this happens. Draw the same place, with "
            "its ground, buildings, plants, materials and colours, from whatever viewpoint the "
            "moment needs; what that image shows counts as named. Draw it again around the "
            "people, so they stand on its own ground at its own scale, never in front of a copy "
            "of that image used as a backdrop. Take the framing, the people, the light and the "
            "drawing style from this picture and the house style, not from that image."
        )
    labels = _labels(kind, references, redraw)
    if place:
        name = _clip(brief.place_name, 80) or "the scene"
        labels += (
            f"Image {len(labels) + 1}: {name}, the place where this happens, to draw again "
            "around the people.",
        )
    return PicturePrompt(
        system=system,
        user="\n".join(lines),
        aspect_ratio=ASPECT_RATIOS[kind],
        labels=labels,
    )


def person(figure: Figure) -> str:
    """Someone in a picture as the prompt tells them: their name and age, then how they look."""
    who = _aged(_clip(figure.name, 80), figure.age)
    if figure.appearance:
        return f"{who}: {_clip(figure.appearance, MAX_APPEARANCE_CHARS)}"
    return who


def _aged(name: str, age: int | None) -> str:
    """A name with the age the picture draws them at (S7), such as "Lin Feng, aged 16"."""
    if age is None:
        return name
    return f"{name}, aged {age}" if name else f"Aged {age}"


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
