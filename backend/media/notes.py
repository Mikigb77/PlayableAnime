"""A scene picture's description, written from the finished scene (M5). Plain Python, no Django.

The narrator writes a scene picture's description in the same answer as the scene, while the
scene is still being written, so the description can miss what the scene ends up telling: where
everyone is, what they are doing, what they hold. A small model step (`Node.PICTURE_NOTE`, the
cheapest text model) reads the scene as the player read it, with the record of who may be in the
picture and how they look, what the player character carries (C10) and where the scene happens,
and writes the description the picture is drawn from, and who can be seen in it. It runs in the
picture's own request, after the narration is shown (M3), so the story never waits for it, and on
the account that draws the picture, which pays for both. When it fails, the narrator's description
stands, and the picture is drawn from that.

Only a scene picture gets a note. A story's cover is its poster (M1), the whole story rather than
the moment of the scene it is planned in, portraits and places are drawn from their records, and a
starter premise's cover from its premise.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from media.briefs import mentions
from media.prompts import MAX_APPEARANCE_CHARS, SAYS_YOU, Brief, _clip, person

# The kinds of picture that show a scene's moment, and so get a note.
NOTED = ("scene",)
# The end of a long scene, where its moment is, so a note's prompt stays small.
MAX_SCENE_CHARS = 6000
MAX_NOTE_CHARS = 700

NOTE_SYSTEM = """\
You write the brief for one picture in an interactive story app. An illustrator who never read \
the story draws the picture from your brief alone.

Read SCENE, the scene as the player read it, and write one to three plain sentences that show \
the moment PICTURE asks for, at one instant:
- who can be seen, and exactly what each of them is doing: their pose, and where each one is \
(up on a branch, behind the bar, halfway down the stairs);
- where it happens, as the scene tells it;
- what anyone holds or wears that matters, and the light and the weather.

Only what the scene tells. Never add a place, building, ruin, river, creature, person or thing it \
doesn't mention, even one the world, PLACE or the narrator's note would make likely. PLACE says \
where the scene happens: use it to name the place, not to add to it. The player character, the \
narration's "you", has only what CARRIES lists, plus what this scene itself puts in their hands: \
never give them any other weapon, tool or gear. The others hold only what the scene gives them. \
Call everyone by name, the player character included, never "you".

The people in the picture are those from PEOPLE the moment shows, each once. Anyone else the \
scene tells of, such as a crowd, travellers or guards, is at most a small, unnamed part of the \
background, never a figure of their own beside them.

Keep it mild, whatever the story's rating: no nudity, nothing sexual, no gore. Show danger, \
fights and wounds through pose, motion, light and expression.

Write in English, whatever language the scene is in, keeping the names as they are. Describe only \
what can be seen: no dialogue, sounds, thoughts or backstory, and no words about style, camera or \
art.

In "people", list everyone from PEOPLE who can be seen in the picture, by name as PEOPLE writes \
it, and no one else."""

PICTURE = "the scene's picture: the moment that matters most, usually where the scene ends"

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class PictureNote(BaseModel):
    """What the note step answers: the picture's description, and who can be seen in it."""

    description: Note = Field(
        description="One to three sentences: the moment, who does what where, and the light."
    )
    people: list[str] = Field(
        default_factory=list,
        description="The names, from PEOPLE, of everyone who can be seen in the picture.",
    )


@dataclass(frozen=True, repr=False)
class SceneText:
    """The finished scene a picture shows: its narration as the player read it, and what the
    player said they do, when they said something."""

    narration: str
    action: str = ""

    def __repr__(self) -> str:
        # Story text never goes into a log line (T6).
        return f"SceneText(chars={len(self.narration)}, action={bool(self.action)})"


@dataclass(frozen=True, repr=False)
class NotePrompt:
    system: str
    user: str

    def __repr__(self) -> str:
        return f"NotePrompt(chars={len(self.system) + len(self.user)})"


def note_prompt(kind: str, brief: Brief, scene: SceneText) -> NotePrompt:
    """The note step's prompt for a picture of `kind` that shows `scene`, from its `brief`: the
    narrator's description as a draft, the people who may be in it, what the player character
    carries, where and when the scene happens, and the scene itself."""
    if kind not in NOTED:
        raise ValueError(f"A {kind} picture gets no note")
    lines = [f"PICTURE: {PICTURE}."]
    if brief.description:
        lines.append(
            "NARRATOR'S NOTE (written before the scene was finished, so trust SCENE over it): "
            + _clip(brief.description, MAX_NOTE_CHARS)
        )
    if brief.you:
        lines.append(f'PLAYER CHARACTER (the narration\'s "you"): {_clip(brief.you, 80)}')
    people = [f for f in brief.figures if f.name]
    if people:
        lines.append(
            "PEOPLE (who may be in the picture, with their age and how they look): "
            + "; ".join(person(f) for f in people)
        )
    for figure in people:
        if figure.carries is not None:
            things = ", ".join(_clip(t, 60) for t in figure.carries if t.strip())
            lines.append(f"{_clip(figure.name, 80)} CARRIES: {_clip(things, 300) or 'nothing'}")
    if brief.place_name:
        place = _clip(brief.place_name, 120)
        if brief.place_look:
            place = f"{place}: {_clip(brief.place_look, MAX_APPEARANCE_CHARS)}"
        lines.append(f"PLACE: {place}")
    if brief.time:
        lines.append(f"TIME OF DAY: {_clip(brief.time, 40)}")
    look = brief.look
    world = "; ".join(part for part in (_clip(look.genre, 120), _clip(look.era, 300)) if part)
    if world:
        lines.append(f"WORLD: {world}")
    if scene.action.strip():
        lines.append(f"PLAYER'S ACTION: {_clip(scene.action, 500)}")
    lines.append(f"SCENE:\n{_ending(scene.narration)}")
    return NotePrompt(system=NOTE_SYSTEM, user="\n".join(lines))


def apply_note(brief: Brief, note: PictureNote) -> Brief:
    """The brief drawn from the note: its description, and only the people it says can be seen,
    or whom it names, so no one else's look or portrait goes along (M5). A note with no
    description leaves the brief as it was."""
    description = _clip(note.description, MAX_NOTE_CHARS)
    if not description:
        return brief
    seen = {" ".join(name.split()).casefold() for name in note.people}
    says_you = bool(SAYS_YOU.search(description))
    figures = tuple(
        f
        for f in brief.figures
        if " ".join(f.name.split()).casefold() in seen
        or mentions(description, f.name)
        or (says_you and f.name == brief.you)
    )
    return replace(brief, description=description, figures=figures)


def _ending(text: str, limit: int = MAX_SCENE_CHARS) -> str:
    """The scene's paragraphs as written, or the end of a long one, from a paragraph's start."""
    text = text.strip()
    if len(text) <= limit:
        return text
    tail = text[-limit:]
    start = tail.find("\n")
    return tail[start + 1 :].lstrip() if 0 <= start < limit // 2 else tail
